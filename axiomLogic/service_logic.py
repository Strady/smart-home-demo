import os
import sqlite3
import statistics
import threading
import time
from axiomLogic.base_logic import BaseLogic
from axiomLogic.config import *
import datetime as dt
import dateutil.relativedelta as rd
import ujson
import influxdb
from axiomLib.loggers import create_logger
import prctl


class ServiceLogic(BaseLogic):

    def __init__(self):
        super().__init__()

        self.logger = create_logger(logger_name=__name__,
                                    logfile_directory=LOG_FILE_DIRECTORY,
                                    logfile_name=LOG_FILE_NAME)

    def create_workers(self):
        """
        Создает словарь вида {bundle: worker_thread,...}
        bundle - объект типа collections.namedtuple с полями "function" и "args"
        function - сервисная функция (с приставкой "service_")
        args - аргументы сервисной функцияи
        worker_thread - объект типа threading.Thread, поток, в котором запускается
        сервисная функция
        """

        service_functions = (self.__getattribute__(funcname) for funcname in self.__dir__()
                             if funcname.startswith('service_'))
        workers = {}
        for function in service_functions:
            bundle = self.Bundle(function=function, args=())
            workers[bundle] = threading.Thread(target=bundle.function, args=bundle.args)
        return workers

    def service_electric_characteristics_updater(self, *args, **kwargs):
        """
        Получает от модуля "Взаимодействие с низким уровнем" сообщения
        с текущими значения энергопотребления, тока и напряжения.
        Записывает в БД аккумлированные за минуту значения
        """
        prctl.set_name('char_updater')
        # Подписываемся на сообщения с потреблением
        p = self.r.pubsub(ignore_subscribe_messages=True)
        p.subscribe('axiomLowLevelCommunication:info:active_power')
        p.subscribe('axiomLowLevelCommunication:info:reactive_power')
        p.subscribe('axiomLowLevelCommunication:info:current')
        p.subscribe('axiomLowLevelCommunication:info:voltage')
        p.subscribe('axiomLowLevelCommunication:info:frequency')

        power_units = self.settings['power units']
        input_units = self.settings['input units']

        # Абсолютный путь к базе данных
        db_name = 'consumption.db'
        axiom_root_directory = self.settings['root directory']
        db_path = os.path.join(axiom_root_directory, db_name)

        # Буфер для накопления сообщений в течение минуты
        messages_buffer = {characteristic: {unit_addr: [] for unit_addr in power_units}
                           for characteristic in ('active_power', 'reactive_power', 'current', 'voltage', 'frequency')}

        def save_message_to_buffer():
            """
            Получает от брокера сообщения со значениями потребления
            в каналах силовых модулей, парсит их и складывает
            в словарь для накопления
            """
            prctl.set_name('bufferizator')
            while self.isRunning:
                message = p.get_message()
                if message:
                    channel = message['channel']
                    characteristic = channel.split(':')[-1]

                    data = ujson.loads(message['data'])
                    # Пересчитываем потребленную мощность в кВт*ч
                    # second_consumption['P1'] /= (3600 * 1000)
                    # second_consumption['P2'] /= (3600 * 1000)

                    # ch1_value, ch2_value, unit_addr, timestamp = message['data'].split(' ')
                    # consumptions[unit_addr].append({'ch1': float(ch1_value) / (3600 * 1000),
                    #                                 'ch2': float(ch2_value) / (3600 * 1000),
                    #                                 'timestamp': float(timestamp)})
                    messages_buffer[characteristic][data['addr']].append(data)
                time.sleep(0.01)

        def active_power_and_consumption_and_cost_table_updater_target():
            """
            Когда в буфере (consumption_messages) накапливаются сообщения за минуту,
            вычисляет суммарное потребление электроэнергии, а также стоимость израсходованной
            электроэнергии по каналам силовых модулей и записывает рассчитанные значения в БД.
            Удаляет минутные значения из БД, которые были сделаны более месяца назад
            """
            prctl.set_name('apower_cons_cost')
            connection = sqlite3.connect(db_path)
            cursor = connection.cursor()

            def calc_cost(consumption):
                """
                Рассчитывает стоимость израсходованной электроэнергии с
                учетом параметров тарифа, сохраненных в редис и текущего времени
                :float consumption: потребление электроэнергии в кВт⋅ч
                :return: стоимость
                """

                # zones = json.loads(self.r.get('consumption_rates'))
                zones = [{'beginning': '00:00', 'rate': 1}, {'beginning': '06:00', 'rate': 2},
                         {'beginning': '12:00', 'rate': 3}, {'beginning': '18:00', 'rate': 4}]

                # Случай, когда одна тарифная зона
                if len(zones) == 1:
                    return consumption * zones[0]['rate']

                # Если тарифная зона не одна - рассчитываем в какую мы попадаем
                # Считываем из БД начала тарифных зон
                beginnings = []
                for zone in zones:
                    beginning = zone['beginning']
                    # Пересчитываем в минуты от начала суток
                    beginning_minutes = int(beginning.split(':')[0]) * 60 + int(beginning.split(':')[1])
                    beginnings.append(beginning_minutes)

                # Время в минутах от начала суток минуту назад
                date_minute_ago = dt.datetime.now() + rd.relativedelta(minutes=-1)
                minutes = date_minute_ago.hour * 60 + date_minute_ago.minute

                # Ищем в какую тарифную зону мы сейчас попадаем
                # и рассчитываем стоимость электроэнергии

                # случай, когда последняя тарифная зона заканчивается в следующих сутках
                if minutes < beginnings[0]:
                    return consumption * zones[-1]['rate']

                full_day = beginnings + [24 * 60]
                for i in range(len(full_day[:-1])):
                    if full_day[i] <= minutes < full_day[i + 1]:
                        return consumption * zones[i]['rate']

            while self.isRunning:
                for unit_addr in power_units:
                    if messages_buffer['active_power'].get(unit_addr) and \
                            time.time() - messages_buffer['active_power'][unit_addr][0]['timestamp'] >= 59.5:
                        # Из буфера сообщений формируем списки значений активной мощности в каналах силового модуля
                        ch1_active_power_values = [message['P1'] for message in messages_buffer['active_power'][unit_addr]]
                        ch2_active_power_values = [message['P2'] for message in messages_buffer['active_power'][unit_addr]]

                        # Время, когда было принято последнее сообщение за минуту
                        last_timestamp = messages_buffer['active_power'][unit_addr][-1]['timestamp']

                        # Чистим буфер сообщений
                        messages_buffer['active_power'][unit_addr].clear()

                        # Пересчитываем значения мощности в потребление
                        ch1_consumption_values = [power_value / (3600 * 1000) for power_value in ch1_active_power_values]
                        ch2_consumption_values = [power_value / (3600 * 1000) for power_value in ch2_active_power_values]

                        # Медианные значения активной мощности в каналах за минуту
                        ch1_median_active_power = statistics.median(ch1_active_power_values)
                        ch2_median_active_power = statistics.median(ch2_active_power_values)

                        # Суммарное потребеление в каналах за минуту
                        ch1_sum_consumption = sum(ch1_consumption_values)
                        ch2_sum_consumption = sum(ch2_consumption_values)

                        # Рассчитываем стоимость электроэнергии
                        ch1_cost = calc_cost(ch1_sum_consumption)
                        ch2_cost = calc_cost(ch2_sum_consumption)

                        # Составляем SQL команду для вставки активной мощности
                        sql_cmd_active_power = 'INSERT INTO {}_minute_active_power (timestamp, channel_1, channel_2) ' \
                                              'VALUES ({}, {}, {})'.format(
                            unit_addr, last_timestamp, ch1_median_active_power, ch2_median_active_power)

                        # Составляем SQL команду для вставки энергопотребления
                        sql_cmd_consumption = 'INSERT INTO {}_minute_consumption (timestamp, channel_1, channel_2) ' \
                                              'VALUES ({}, {}, {})'.format(
                            unit_addr, last_timestamp, ch1_sum_consumption, ch2_sum_consumption)

                        # Составляем SQL команду для вставки стоимости электроэнергии
                        sql_cmd_cost = 'INSERT INTO {}_minute_cost (timestamp, channel_1, channel_2) ' \
                                       'VALUES ({}, {}, {})'.format(
                            unit_addr, last_timestamp, ch1_cost, ch2_cost)

                        # unix время месяц назад
                        month_ago = (dt.datetime.now() + rd.relativedelta(months=-1)).timestamp()

                        with connection:
                            # Записываем новые значения активной мощности, энергопотребления и стоимости электроэнергии
                            # print(sql_cmd_active_power)
                            cursor.execute(sql_cmd_active_power)
                            # print(sql_cmd_consumption)
                            cursor.execute(sql_cmd_consumption)
                            # print(sql_cmd_cost)
                            cursor.execute(sql_cmd_cost)

                            # Удаляем значения, которым больше месяца
                            cursor.execute('DELETE FROM {}_minute_active_power WHERE timestamp < {}'.format(
                                unit_addr, month_ago))
                            cursor.execute('DELETE FROM {}_minute_consumption WHERE timestamp < {}'.format(
                                unit_addr, month_ago))
                            cursor.execute('DELETE FROM {}_minute_cost WHERE timestamp < {}'.format(
                                unit_addr, month_ago))
                time.sleep(0.1)

        def reactive_power_table_updater_target():
            """
            Когда в буфере накапливаются сообщения за минуту, вычисляет медианные значения
            реактивной мощности в каналах силовых модулей и записывает их в БД.
            Удаляет минутные значения из БД, которые были сделаны более месяца назад
            """
            prctl.set_name('re_power')
            connection = sqlite3.connect(db_path)
            cursor = connection.cursor()

            while self.isRunning:
                for unit_addr in power_units:
                    # Если накопились сообщения за минуту времени
                    if messages_buffer['reactive_power'].get(unit_addr) and \
                            time.time() - messages_buffer['reactive_power'][unit_addr][0]['timestamp'] >= 59.5:
                        # Из буфера сообщений формируем списки значений токов в каналах силового модуля
                        ch1_reactive_power_values = [message['P1'] for message in messages_buffer['reactive_power'][unit_addr]]
                        ch2_reactive_power_values = [message['P2'] for message in messages_buffer['reactive_power'][unit_addr]]

                        # Время, когда было принято последнее сообщение за минуту
                        last_timestamp = messages_buffer['reactive_power'][unit_addr][-1]['timestamp']

                        # Чистим буфер сообщений
                        messages_buffer['reactive_power'][unit_addr].clear()

                        # Считаем медианное значение за минуту
                        ch1_median_reactive_power = statistics.median(ch1_reactive_power_values)
                        ch2_median_reactive_power = statistics.median(ch2_reactive_power_values)

                        # Составляем SQL команду для вставки тока
                        sql_cmd_reactive_power = 'INSERT INTO {}_minute_reactive_power (timestamp, channel_1, channel_2) ' \
                                          'VALUES ({}, {}, {})'.format(
                            unit_addr, last_timestamp, ch1_median_reactive_power, ch2_median_reactive_power)

                        # unix время месяц назад
                        month_ago = (dt.datetime.now() + rd.relativedelta(months=-1)).timestamp()

                        with connection:
                            # Записываем новые значения
                            # print(sql_cmd_current)
                            cursor.execute(sql_cmd_reactive_power)
                            # Удаляем значения, которым больше месяца
                            cursor.execute('DELETE FROM {}_minute_reactive_power WHERE timestamp < {}'.format(
                                unit_addr, month_ago))
                time.sleep(0.1)

        def current_table_updater_target():
            """
            Когда в буфере (current_messages) накапливаются сообщения за минуту,
            вычисляет медианные значения токов в каналах силовых модулей и
            записывает их в БД. Удаляет минутные значения из БД, которые были
            сделаны более месяца назад
            """
            prctl.set_name('current')
            connection = sqlite3.connect(db_path)
            cursor = connection.cursor()

            # print("current_table_updater_target")

            while self.isRunning:
                for unit_addr in power_units:
                    # Если накопились сообщения за минуту времени
                    if messages_buffer['current'].get(unit_addr) and \
                            time.time() - messages_buffer['current'][unit_addr][0]['timestamp'] >= 59.5:
                        # Из буфера сообщений формируем списки значений токов в каналах силового модуля
                        ch1_current_values = [message['I1'] for message in messages_buffer['current'][unit_addr]]
                        ch2_current_values = [message['I2'] for message in messages_buffer['current'][unit_addr]]

                        # Время, когда было принято последнее сообщение за минуту
                        last_timestamp = messages_buffer['current'][unit_addr][-1]['timestamp']

                        # Чистим буфер сообщений
                        messages_buffer['current'][unit_addr].clear()

                        # Считаем медианное значение за минуту
                        ch1_median_current = statistics.median(ch1_current_values)
                        ch2_median_current = statistics.median(ch2_current_values)

                        # Составляем SQL команду для вставки тока
                        sql_cmd_current = 'INSERT INTO {}_minute_current (timestamp, channel_1, channel_2) ' \
                                          'VALUES ({}, {}, {})'.format(
                            unit_addr, last_timestamp, ch1_median_current, ch2_median_current)

                        # unix время месяц назад
                        month_ago = (dt.datetime.now() + rd.relativedelta(months=-1)).timestamp()

                        with connection:
                            # Записываем новые значения
                            # print(sql_cmd_current)
                            cursor.execute(sql_cmd_current)
                            # Удаляем значения, которым больше месяца
                            cursor.execute('DELETE FROM {}_minute_current WHERE timestamp < {}'.format(
                                unit_addr, month_ago))
                time.sleep(0.1)

        def voltage_table_updater_target():
            """
            Когда в буфере (voltage_messages) накапливаются сообщения за минуту,
            вычисляет медианное значение напряжения на модулях ввода и
            записывает его в БД. Удаляет минутные значения из БД, которые были
            сделаны более месяца назад
            """
            prctl.set_name('voltage')
            connection = sqlite3.connect(db_path)
            cursor = connection.cursor()

            # print("voltage_table_updater_target")

            while self.isRunning:
                for unit_addr in input_units:
                    # Если накопились сообщения за минуту времени
                    if messages_buffer['voltage'].get(unit_addr) and \
                            time.time() - messages_buffer['voltage'][unit_addr][0]['timestamp'] >= 59.5:
                        # Из буфера сообщений формируем список значений напряжения
                        voltage_values = [message['U'] for message in messages_buffer['voltage'][unit_addr]]

                        # Время, когда было принято последнее сообщение за минуту
                        last_timestamp = messages_buffer['voltage'][unit_addr][-1]['timestamp']

                        # Чистим буфер сообщений
                        messages_buffer['voltage'][unit_addr].clear()

                        # Считаем медианное значение за минуту
                        median_voltage = statistics.median(voltage_values)

                        # Составляем SQL команду для вставки напряжения
                        sql_cmd_voltage = 'INSERT INTO {}_minute_voltage (timestamp, voltage) VALUES ({}, {})'.format(
                            unit_addr, last_timestamp, median_voltage)

                        # unix время месяц назад
                        month_ago = (dt.datetime.now() + rd.relativedelta(months=-1)).timestamp()

                        with connection:
                            # Записываем новые значения
                            # print(sql_cmd_voltage)
                            cursor.execute(sql_cmd_voltage)
                            # Удаляем значения, которым больше месяца
                            cursor.execute('DELETE FROM {}_minute_voltage WHERE timestamp < {}'.format(
                                unit_addr, month_ago))
                time.sleep(0.1)

        def frequency_table_updater_target():
            """
            Раз в минуту записывает текущее значение частоты
            на силовом модуле в базу данных
            """
            prctl.set_name('frequency')
            connection = sqlite3.connect(db_path)
            cursor = connection.cursor()

            while self.isRunning:
                for unit_addr in power_units:
                    # Если накопились сообщения за минуту времени
                    if messages_buffer['frequency'].get(unit_addr) and \
                            time.time() - messages_buffer['frequency'][unit_addr][0]['timestamp'] >= 59.5:
                        # Время, когда было принято последнее сообщение за минуту
                        last_timestamp = messages_buffer['frequency'][unit_addr][-1]['timestamp']

                        # Последнее принятое значение частоты на модуле
                        current_frequency = messages_buffer['frequency'][unit_addr][-1]['F']

                        # Чистим буфер сообщений
                        messages_buffer['frequency'][unit_addr].clear()

                        # Составляем SQL команду для вставки частоты
                        sql_cmd_frequency = 'INSERT INTO {}_minute_frequency (timestamp, frequency) VALUES ({}, {})'.format(
                            unit_addr, last_timestamp, current_frequency)

                        # unix время месяц назад
                        month_ago = (dt.datetime.now() + rd.relativedelta(months=-1)).timestamp()

                        with connection:
                            # Записываем новые значения
                            # print(sql_cmd_frequency)
                            cursor.execute(sql_cmd_frequency)
                            # Удаляем значения, которым больше месяца
                            cursor.execute('DELETE FROM {}_minute_frequency WHERE timestamp < {}'.format(
                                unit_addr, month_ago))
                time.sleep(0.1)

        msg_bufferizator = threading.Thread(target=save_message_to_buffer)
        consumption_table_updater = threading.Thread(target=active_power_and_consumption_and_cost_table_updater_target)
        reactive_power_table_updater = threading.Thread(target=reactive_power_table_updater_target)
        current_table_updater = threading.Thread(target=current_table_updater_target)
        voltage_table_updater = threading.Thread(target=voltage_table_updater_target)
        frequency_table_updater = threading.Thread(target=frequency_table_updater_target)

        msg_bufferizator.start()
        consumption_table_updater.start()
        reactive_power_table_updater.start()
        current_table_updater.start()
        voltage_table_updater.start()
        frequency_table_updater.start()

        # Контролируем работоспособность потоков
        while self.isRunning:
            if not msg_bufferizator.isAlive():
                msg_bufferizator = threading.Thread(target=save_message_to_buffer)
                msg_bufferizator.start()
            elif not consumption_table_updater.isAlive():
                consumption_table_updater = threading.Thread(target=active_power_and_consumption_and_cost_table_updater_target)
                consumption_table_updater.start()
            elif not reactive_power_table_updater.isAlive():
                reactive_power_table_updater = threading.Thread(target=reactive_power_table_updater_target)
                reactive_power_table_updater.start()
            elif not current_table_updater.isAlive():
                current_table_updater = threading.Thread(target=current_table_updater_target)
                current_table_updater.start()
            elif not voltage_table_updater.isAlive():
                voltage_table_updater = threading.Thread(target=voltage_table_updater_target)
                voltage_table_updater.start()
            elif not frequency_table_updater.isAlive():
                frequency_table_updater = threading.Thread(target=frequency_table_updater_target)
                frequency_table_updater.start()
            time.sleep(1)

    def service_electric_characteristics_translator(self, *args, **kwargs):
        prctl.set_name('char_translator')
        subscriber = self.r.pubsub(ignore_subscribe_messages=True)
        subscriber.subscribe('axiomLowLevelCommunication:info:metrics_data')

        while self.isRunning:
            message = subscriber.get_message()

            if not message:
                time.sleep(0.01)
                continue

            data = ujson.loads(message['data'])

            unit_addr = data['addr']

            if unit_addr in self.settings['power units']:
                msg1 = {'hardware_addr': 'ch:{}:1'.format(unit_addr),
                        'active_power': data['Pa1'],
                        'reactive_power': data['Pr1'],
                        'current': data['I1'],
                        'temperature': data['T1'],
                        'voltage': data['U'],
                        'frequency': data['F']}
                self.r.publish(channel='axiomLogic:info:characteristics', message=ujson.dumps(msg1))

                msg2 = {'hardware_addr': 'ch:{}:2'.format(unit_addr),
                        'active_power': data['Pa2'],
                        'reactive_power': data['Pr2'],
                        'current': data['I2'],
                        'temperature': data['T2'],
                        'voltage': data['U'],
                        'frequency': data['F']}
                self.r.publish(channel='axiomLogic:info:characteristics', message=ujson.dumps(msg2))

            time.sleep(0.01)

    def service_metrics_messages_handler(self, *args, **kwargs):
        """
        Обрабатывает сообщения с текущими показаниями датчиков силовых модулей.
        Сохраняет метрики в influxdb
        """
        prctl.set_name('metrics_messages_handler')
        def calc_cost(consumption):
            """
            Рассчитывает стоимость израсходованной электроэнергии с
            учетом параметров тарифа, сохраненных в редис и текущего времени
            :float consumption: потребление электроэнергии в кВт⋅ч
            :return: стоимость
            """

            # zones = json.loads(self.r.get('consumption_rates'))
            zones = [{'beginning': '00:00', 'rate': 1}, {'beginning': '06:00', 'rate': 2},
                     {'beginning': '12:00', 'rate': 3}, {'beginning': '18:00', 'rate': 4}]

            # Случай, когда одна тарифная зона
            if len(zones) == 1:
                return consumption * zones[0]['rate']

            # Если тарифная зона не одна - рассчитываем в какую мы попадаем
            # Считываем из БД начала тарифных зон
            beginnings = []
            for zone in zones:
                beginning = zone['beginning']
                # Пересчитываем в минуты от начала суток
                beginning_minutes = int(beginning.split(':')[0]) * 60 + int(beginning.split(':')[1])
                beginnings.append(beginning_minutes)

            # Время в минутах от начала суток минуту назад
            date_minute_ago = dt.datetime.now() + rd.relativedelta(minutes=-1)
            minutes = date_minute_ago.hour * 60 + date_minute_ago.minute

            # Ищем в какую тарифную зону мы сейчас попадаем
            # и рассчитываем стоимость электроэнергии

            # случай, когда последняя тарифная зона заканчивается в следующих сутках
            if minutes < beginnings[0]:
                return consumption * zones[-1]['rate']

            full_day = beginnings + [24 * 60]
            for i in range(len(full_day[:-1])):
                if full_day[i] <= minutes < full_day[i + 1]:
                    return consumption * zones[i]['rate']

        # Подписываемся на сообщения с метриками
        subscriber = self.r.pubsub(ignore_subscribe_messages=True)
        subscriber.subscribe('axiomLowLevelCommunication:info:metrics_data')

        # Подключаемся к influxdb
        client = influxdb.InfluxDBClient(host='localhost', port=8086)
        client.switch_database('axiom_metrics')

        input_units = self.settings['input units'].keys()
        power_units = self.settings['power units'].keys()
        # power_units = []
        # for params in self.settings['input units'].values():
        #     power_units += list(params['power units'].keys())

        while self.isRunning:
            message = subscriber.get_message()

            if not message:
                time.sleep(0.01)
                continue

            data = ujson.loads(message['data'])
            unit_addr = data['addr']

            points = []

            # Метрики силовых модулей
            if unit_addr in power_units:

                # Активная мощность
                points.append({'measurement': 'active_power',
                               'tags': {'unit_addr': '{}'.format(unit_addr), 'channel': '1'},
                               'fields': {'value': data['Pa1']}})
                points.append({'measurement': 'active_power',
                               'tags': {'unit_addr': '{}'.format(unit_addr), 'channel': '2'},
                               'fields': {'value': data['Pa2']}})

                # Реактивная мощность
                points.append({'measurement': 'reactive_power',
                               'tags': {'unit_addr': '{}'.format(unit_addr), 'channel': '1'},
                               'fields': {'value': data['Pr1']}})
                points.append({'measurement': 'reactive_power',
                               'tags': {'unit_addr': '{}'.format(unit_addr), 'channel': '2'},
                               'fields': {'value': data['Pr2']}})

                # Ток
                points.append({'measurement': 'current',
                               'tags': {'unit_addr': '{}'.format(unit_addr), 'channel': '1'},
                               'fields': {'value': data['I1']}})
                points.append({'measurement': 'current',
                               'tags': {'unit_addr': '{}'.format(unit_addr), 'channel': '2'},
                               'fields': {'value': data['I2']}})

                # Напряжение
                points.append({'measurement': 'voltage',
                               'tags': {'unit_addr': '{}'.format(unit_addr), 'channel': '1'},
                               'fields': {'value': data['U']}})
                points.append({'measurement': 'voltage',
                               'tags': {'unit_addr': '{}'.format(unit_addr), 'channel': '2'},
                               'fields': {'value': data['U']}})

                # Частота
                points.append({'measurement': 'frequency',
                               'tags': {'unit_addr': '{}'.format(unit_addr), 'channel': '1'},
                               'fields': {'value': data['F']}})
                points.append({'measurement': 'frequency',
                               'tags': {'unit_addr': '{}'.format(unit_addr), 'channel': '2'},
                               'fields': {'value': data['F']}})

                # Температура
                points.append({'measurement': 'temperature',
                               'tags': {'unit_addr': '{}'.format(unit_addr), 'channel': '1'},
                               'fields': {'value': data['T1']}})
                points.append({'measurement': 'temperature',
                               'tags': {'unit_addr': '{}'.format(unit_addr), 'channel': '2'},
                               'fields': {'value': data['T2']}})

                # Потребление
                consumption1 = data['Pa1'] / (360 * 1000)
                consumption2 = data['Pa2'] / (360 * 1000)

                points.append({'measurement': 'consumption',
                               'tags': {'unit_addr': '{}'.format(unit_addr), 'channel': '1'},
                               'fields': {'value': consumption1}})
                points.append({'measurement': 'consumption',
                               'tags': {'unit_addr': '{}'.format(unit_addr), 'channel': '2'},
                               'fields': {'value': consumption2}})

                # Стоимость
                cost1 = calc_cost(consumption1)
                cost2 = calc_cost(consumption2)

                points.append({'measurement': 'cost',
                               'tags': {'unit_addr': '{}'.format(unit_addr), 'channel': '1'},
                               'fields': {'value': cost1}})
                points.append({'measurement': 'cost',
                               'tags': {'unit_addr': '{}'.format(unit_addr), 'channel': '2'},
                               'fields': {'value': cost2}})

                client.write_points(points)

            # Метрики модулей ввода
            elif unit_addr in input_units:

                # Мощность потребляемая системой
                points.append({'measurement': 'power',
                               'tags': {'unit_addr': '{}'.format(unit_addr)},
                               'fields': {'value': data['P_own']}})
                points.append({'measurement': 'power',
                               'tags': {'unit_addr': '{}'.format(unit_addr)},
                               'fields': {'value': data['P_own']}})

                # Напряжение электропитания системы
                points.append({'measurement': 'voltage',
                               'tags': {'unit_addr': '{}'.format(unit_addr)},
                               'fields': {'value': data['U']}})
                points.append({'measurement': 'voltage',
                               'tags': {'unit_addr': '{}'.format(unit_addr)},
                               'fields': {'value': data['U']}})

                # Частота напряжения электропитания системы
                points.append({'measurement': 'frequency',
                               'tags': {'unit_addr': '{}'.format(unit_addr)},
                               'fields': {'value': data['F']}})
                points.append({'measurement': 'frequency',
                               'tags': {'unit_addr': '{}'.format(unit_addr)},
                               'fields': {'value': data['F']}})

                # Собственное потребление электроэнергии системой
                consumption1 = data['P1'] / (360 * 1000)
                consumption2 = data['P2'] / (360 * 1000)

                points.append({'measurement': 'consumption',
                               'tags': {'unit_addr': '{}'.format(unit_addr)},
                               'fields': {'value': consumption1}})
                points.append({'measurement': 'consumption',
                               'tags': {'unit_addr': '{}'.format(unit_addr)},
                               'fields': {'value': consumption2}})

                # Стоимость электроэнергии потребленной системой
                cost1 = calc_cost(consumption1)
                cost2 = calc_cost(consumption2)

                points.append({'measurement': 'cost',
                               'tags': {'unit_addr': '{}'.format(unit_addr)},
                               'fields': {'value': cost1}})
                points.append({'measurement': 'cost',
                               'tags': {'unit_addr': '{}'.format(unit_addr)},
                               'fields': {'value': cost2}})

                client.write_points(points)

            time.sleep(0.01)

    def service_journal_updater(self, *args, **kwargs):
        """
        Заносит в БД записи для журнала веб-интерфейса
        :param args: ненужные позиционные аргументы
        :param kwargs: ненужные именованные аргументы
        """
        prctl.set_name('journal')
        # подписка на сообщения для журнала
        p = self.r.pubsub(ignore_subscribe_messages=True)
        p.subscribe('axiomLowLevelCommunication:journal:error')

        # Подключение к БД sqlite3 для сохранения записи в журнале
        axiom_root = self.settings['root directory']
        db_path = os.path.join(axiom_root, site_db)
        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()

        # Вычисляем unix время месяц назад
        month_ago = dt.datetime.now() + rd.relativedelta(months=-1)
        month_ago_timestamp = month_ago.timestamp()

        while self.isRunning:
            message = p.get_message()

            if not message:
                time.sleep(0.01)
                continue

            with connection:
                data = message['data']
                # Добавляем новую запись в журнал
                cursor.execute('INSERT INTO log_entries (timestamp, event) VALUES ({}, "{}")'.format(time.time(), data))
                # Удаляем записи, которым более месяца
                del_cmd = 'DELETE FROM log_entries WHERE timestamp < {}'.format(month_ago_timestamp)
                cursor.execute(del_cmd)

            time.sleep(0.01)

    def service_insulation_massages_translator(self, *args, **kwargs):
        """
        Транслирует запросы на измерение сопротивление изоляции
        и ответы со значениями сопротивления между модулями
        "Веб-сервер" и "Взаимодейсвтие с низким уровнем"
        """
        prctl.set_name('insulation')
        subscriber = self.r.pubsub(ignore_subscribe_messages=True)
        subscriber.subscribe('axiomWebserver:request:insulation', 'axiomLowLevelCommunication:response:insulation')

        while self.isRunning:

            message = subscriber.get_message()

            if not message:
                time.sleep(0.01)
                continue

            channel = message['channel']

            if channel == 'axiomWebserver:request:insulation':
                self.r.publish('axiomLogic:request:insulation', message['data'])
            elif channel == 'axiomLowLevelCommunication:response:insulation':
                self.r.publish('axiomLogic:response:insulation', message['data'])

            time.sleep(0.01)
