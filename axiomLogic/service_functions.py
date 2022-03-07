import scipy.integrate
import redis
from time import sleep, time
import threading
import os
import sqlite3
import datetime as dt
import dateutil.relativedelta as rd
from axiomLogic import log_writer

def di_queue_updater_target(settings, *args, **kwargs):
    """
    При получении нового состояния входов di обновляется очередь состояний
    """

    # Подключаемся к брокеру
    r = redis.StrictRedis()
    # Подписываемся на сообщения с состоянием di для каждого модуля
    p = r.pubsub(ignore_subscribe_messages=True)
    for unit in settings['units']:
        p.subscribe('di:%s:state_info' % unit)

    # Создаем очередь состояний di для каждого модуля
    di_queue = {unit: [[0] * settings['num of di']] * settings['di queue len'] for unit in settings['units']}

    # Ждем сообщений
    for message in p.listen():
        # Определяем для какого модуля получили состояние di
        channel_name = message['channel'].decode()
        unit = channel_name.split(':')[1]
        raw_di_state = message['data'].decode()
        try:
            di_state = [int(i) for i in raw_di_state]
        except ValueError:
            print('incorrect raw_di_state: ', raw_di_state)
            continue
        # Добавляем новое состояние в соответствующую очередь и публикуем на брокер
        di_queue[unit].pop(0)
        di_queue[unit].append(di_state)
        r.publish('di_queue:{}'.format(unit), di_queue[unit])

def db_updater_target(*args, **kwargs):
    """
    При получении сообщения об изменении состояния
    новое состояние записывается в БД
    """

    # Подключаемся к брокеру
    r = redis.StrictRedis()
    # Подписываемся на сообщения с новым состоянием
    p = r.pubsub(ignore_subscribe_messages=True)
    p.subscribe('axiomRS485Transceiver:info:state')

    # При получении сообщения об изменении состояния
    # записываем новое состояние в БД
    for message in p.listen():
        input_json = eval(message['data'].decode())
        addr = input_json['id']
        state = input_json['state']
        r.set(addr, state)

def mounting_service_handler_target(settings, handlersON, *args, **kwargs):
    """
    Обработчик сообщений от монтажного интерфейса
    Подсвечивает индикаторы входов, для которых осуществляется подключение
    """

    # Подключаемся к брокеру
    r = redis.StrictRedis()
    # Подписываемся на сообщения с адресом, которым нужно моргать
    p = r.pubsub(ignore_subscribe_messages=True)
    p.subscribe('mounting service commands')

    addr = ''

    while True:
        message = p.get_message()
        if message:
            if addr == '':
                handlersON.value = 0

                for unit in settings['units']:
                    # Выключаем светодиоды
                    r.publish('axiomLogic:cmd:state (no check)', {'id': 'lr:%s' % unit,
                                                                'state': {'value_ao': 8 * '0',
                                                                          'value_do': 32 * '0'}})
                    r.publish('axiomLogic:cmd:state (no check)', {'id': 'll:%s' % unit,
                                                                'state': {'value_di': 32 * '0',
                                                                          'value_gr': 8 * '0'}})

                    # Выключаем аналоговые выходы
                    for ao_position in range(settings["num of ao"]):
                        ao_addr = 'ao:{}:{}'.format(unit, str(ao_position))
                        r.publish('axiomLogic:cmd:state (no_info)', {'id': ao_addr,
                                                                   'state': {'status': False,
                                                                             'value': 0}})

                    # Выключаем цифровые выходы
                    for do_position in range(settings['num of do']):
                        do_addr = 'do:{}:{}'.format(unit, str(do_position))
                        r.publish('axiomLogic:cmd:state (no_info)', {'id': do_addr,
                                                                   'state': {'status': False}})

            addr = message['data'].decode()

        # Выход из монтажного интерфейса
        if 'lights off' in addr:
            addr = ''
            handlersON.value = 1
            for unit in settings['units']:
                r.publish('axiomRS485Transceiver:cmd:reload', unit)

        elif 'ao' in addr:
            unit = addr.split(':')[1]
            position = int(addr.split(':')[2])
            ao_led_value = (8 * '0')[:position] + '1' + (8 * '0')[position + 1:]
            ledON = {'id': 'lr:%s' % unit, 'state': {'value_ao': ao_led_value, 'value_do': 32 * '0'}}
            lefOFF = {'id': 'lr:%s' % unit, 'state': {'value_ao': 8 * '0', 'value_do': 32 * '0'}}
            r.publish('axiomLogic:cmd:state (no check)', ledON)
            sleep(0.5)
            r.publish('axiomLogic:cmd:state (no check)', lefOFF)
            sleep(0.5)

        elif 'di' in addr:
            unit = addr.split(':')[1]
            position = int(addr.split(':')[2])
            di_led_value = (32 * '0')[:position] + '1' + (32 * '0')[position + 1:]
            ledON = {'id': 'll:%s' % unit, 'state': {'value_di': di_led_value, 'value_gr': 8 * '0'}}
            lefOFF = {'id': 'll:%s' % unit, 'state': {'value_di': 32 * '0', 'value_gr': 8 * '0'}}
            r.publish('axiomLogic:cmd:state (no check)', ledON)
            sleep(0.5)
            r.publish('axiomLogic:cmd:state (no check)', lefOFF)
            sleep(0.5)

        elif 'gr' in addr:
            unit = addr.split(':')[1]
            position = int(addr.split(':')[2])
            gr_led_value = (8 * '0')[:position] + '1' + (8 * '0')[position + 1:]
            ledON = {'id': 'll:%s' % unit, 'state': {'value_di': 32 * '0', 'value_gr': gr_led_value}}
            lefOFF = {'id': 'll:%s' % unit, 'state': {'value_di': 32 * '0', 'value_gr': 8 * '0'}}
            r.publish('axiomLogic:cmd:state (no check)', ledON)
            sleep(0.5)
            r.publish('axiomLogic:cmd:state (no check)', lefOFF)
            sleep(0.5)

        sleep(0.01)

def state_reloader_target(settings, *args, **kwargs):
    """
    устанавливает состояние из БД в случае перезагрузки какого-либо модуля
    (если пришел ответ со значение счетчика "0")
    """

    # Подключаемся к брокеру
    r = redis.StrictRedis(decode_responses=True)
    # Подписываемся на сообщения с новым состоянием
    p = r.pubsub(ignore_subscribe_messages=True)
    p.subscribe('axiomRS485Transceiver:cmd:reload')

    units = settings['units']
    power_units = settings['power units']
    num_of_ch = settings['num of ch']
    num_of_ao = settings['num of ao']
    num_of_di = settings['num of di']

    # При получении сообщения об изменении состояния
    # записываем новое состояние в БД
    for message in p.listen():
        unit = message['data']

        log_writer('От модуля обмена по UART получен запрос на повторную инициализацию модуля {}'.format(unit), 'DEBUG')

        if unit in power_units:
            # Пытаемся установить пороги и выбрать каналы для измерения потребления
            while not eval(r.get('power unit set up')):

                log_writer('Задаются пороги и выбираются каналы для измерения потребления на силовых модулях', 'DEBUG')

                channels_to_measure = ':'.join(str(channel) for channel in settings['measure channels'][unit])
                r.publish('axiomLogic:cmd:setup_power_unit', 'set {} {}'.format(channels_to_measure, unit))

                # Ждем пока пройдут все команды на низком уровне
                # если за 10 секунд положительного результата нет,
                # пытаемся повторить
                for _ in range(10):
                    if eval(r.get('power unit set up')):
                        break
                    else:
                        sleep(1)

            # Включаем силовые выходы
            # Собираем групповое состояние выходов и отправляем на брокер
            bin_ch_grp_state = ''

            for ch_position in range(num_of_ch):
                ch_addr = 'ch:{}:{}'.format(unit, ch_position)
                raw_ch_state = r.get(ch_addr)
                if raw_ch_state:
                    ch_state = eval(raw_ch_state)
                    bin_ch_grp_state += str(int(ch_state['status']))
                else:
                    ch_state = {'status': False}
                    bin_ch_grp_state += str(int(ch_state['status']))
                    r.set(ch_addr, ch_state)

            hex_ch_grp_str = hex(int(bin_ch_grp_state[::-1], 2))
            r.publish('axiomLogic:cmd:setup_power_unit', {'id': 'ch:{}'.format(unit), 'state': hex_ch_grp_str})

        if unit in units:

            # Включаем аналоговые выходы
            # Собираем групповое состояние выходов и отправляем на брокер
            ao_values = []

            for ao_position in range(num_of_ao):
                ao_addr = 'ao:{}:{}'.format(unit, ao_position)
                raw_ao_state = r.get(ao_addr)
                if raw_ao_state:
                    ao_state = eval(raw_ao_state)
                    ao_values.append(int(ao_state['value']))
                else:
                    ao_state = {'value': 0}
                    ao_values.append(int(ao_state['value']))
                    r.set(ao_addr, ao_state)

            r.publish('axiomLogic:cmd:state', {'id': 'ao:{}'.format(unit), 'state': ao_values})


            # Включаем дискретные выходы
            for di_position in range(num_of_di):
                di_addr = 'di:{}:{}'.format(unit, di_position)
                di_state = eval(r.get(di_addr))
                print('axiomLogic:cmd:state', {'id': di_addr, 'state': di_state})
                r.publish('axiomLogic:cmd:state', {'id': di_addr, 'state': di_state})
                sleep(0.01)

            # Включаем светодиоды
            leds_state = eval(r.get('lr:{}'.format(unit)))
            print('axiomLogic:cmd:state', {'id': 'lr:{}'.format(unit), 'state': leds_state})
            r.publish('axiomLogic:cmd:state', {'id': 'lr:{}'.format(unit), 'state': leds_state})

def power_consumption_update_target(settings, *args, **kwargs):
    """
    Запрашивает потребление на каналах
    Записывает полученные данные в таблицу <power_unit_name>_minute
    :param settings: настройки
    """
    # Подключаемся к брокеру
    r = redis.StrictRedis(charset='utf-8', decode_responses=True)
    # Подписываемся на сообщения с состоянием di для каждого модуля
    p = r.pubsub(ignore_subscribe_messages=True)
    p.subscribe('axiomLowLevelCommunication:info:consumption')

    power_units = settings['power units']
    # Структура для накопления секундных значений потребления для каждого модуля
    consumptions = {unit_addr: [] for unit_addr in power_units}

    def update_consumption_from_msg():
        """
        Получает от брокера сообщения со значениями потребления
        в каналах силовых модулей, парсит их и складывает
        в словарь для накопления
        """
        for message in p.listen():
            ch1_value, ch2_value, unit_addr, timestamp = message['data'].split(' ')
            consumptions[unit_addr].append({'ch1': float(ch1_value) / (3600 * 1000),
                                            'ch2': float(ch2_value) / (3600 * 1000),
                                            'timestamp': float(timestamp)})

    def minute_consumption_table_updater():
        # Абсолютный путь к базе данных
        db_name = 'consumption.db'
        axiom_root_directory = settings['root directory']
        db_path = os.path.join(axiom_root_directory, db_name)

        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()

        while True:
            for unit_addr in power_units:
                if consumptions[unit_addr] and time() - consumptions[unit_addr][0]['timestamp'] >= 59.99:
                    ch1_values = []
                    ch2_values = []
                    timestamps = []
                    for entry in consumptions[unit_addr]:
                        ch1_values.append(entry['ch1'])
                        ch2_values.append(entry['ch2'])
                        timestamps.append(entry['timestamp'])

                    consumptions[unit_addr] = []

                    ch1_minute_consumption = sum(ch1_values)
                    ch2_minute_consumption = sum(ch2_values)

                    # Строки, содержащие все каналы и соответствующие им значения потребления. Вставляются в SQL выражение
                    sql_channels_str = ', '.join('channel_{}'.format(channel) for channel in ('1', '2'))
                    sql_values_str = ', '.join(str(value) for value in (ch1_minute_consumption, ch2_minute_consumption))

                    # Составляем и выполняем SQL команду
                    sql_cmd = 'INSERT INTO {}_minute (timestamp, {}) VALUES ({}, {})'.format(unit_addr,
                                                                                             sql_channels_str,
                                                                                             time(), sql_values_str)

                    # unix время месяц назад
                    month_ago = (dt.datetime.now() + rd.relativedelta(months=-1)).timestamp()
                    with connection:
                        # Записываем новые значения
                        cursor.execute(sql_cmd)
                        # Удаляем значения, которым больше месяца
                        cursor.execute('DELETE FROM {}_minute WHERE timestamp < {}'.format(unit_addr, month_ago))


            sleep(0.01)


    # def request_consumption_data_target():
    #     """
    #     Запрашивает потребление и сохраняет в БД.
    #     Выполняется в отдельном потоке
    #     """
    #     while True:
    #         for unit in settings['power units']:
    #             r.publish('axiomLogic:request:consumption', unit)
    #         sleep(1)

    def get_consumption_response_target():

        # Абсолютный путь к базе данных
        db_name = 'consumption.db'
        axiom_root_directory = settings['root directory']
        db_path = os.path.join(axiom_root_directory, db_name)

        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()

        for message in p.listen():
            print(message)
            ch1_consumption, ch2_consumption, unit_addr, timestamp = message['data'].split(' ')

            # Строки, содержащие все каналы и соответствующие им значения потребления. Вставляются в SQL выражение
            sql_channels_str = ', '.join('channel_{}'.format(channel) for channel in ('1', '2'))
            sql_values_str = ', '.join(value for value in (ch1_consumption, ch2_consumption))

            # Составляем и выполняем SQL команду
            sql_cmd = 'INSERT INTO {}_minute (timestamp, {}) VALUES ({}, {})'.format(unit_addr, sql_channels_str,
                                                                                     time(), sql_values_str)

            # unix время месяц назад
            month_ago = (dt.datetime.now() + rd.relativedelta(months=-1)).timestamp()
            with connection:
                # Записываем новые значения
                cursor.execute(sql_cmd)
                # Удаляем значения, которым больше месяца
                cursor.execute('DELETE FROM {}_minute WHERE timestamp < {}'.format(unit_addr, month_ago))

    update_thread = threading.Thread(target=update_consumption_from_msg)
    update_minute_thread = threading.Thread(target=minute_consumption_table_updater)

    update_thread.start()
    update_minute_thread.start()
    update_thread.join()
    update_minute_thread.join()

def journal_updater_target(settings, *args):
    """
    Заносит в БД записи для журнала веб-интерфейса
    :param settings: настройки ПО системы
    :param args: ненужные аргументы
    :return:
    """
    # Подключение к Redis, подписка на сообщения для журнала
    r = redis.StrictRedis(decode_responses=True)
    p = r.pubsub(ignore_subscribe_messages=True)
    p.subscribe('axiomLowLevelCommunication:journal:error')

    # Подключение к БД sqlite3 для сохранения записи в журнале
    axiom_root = settings['root directory']
    journal_db = 'axiomWebserver/site.db'
    db_path = os.path.join(axiom_root, journal_db)
    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()

    # Вычисляем unix время месяц назад
    month_ago = dt.datetime.now() + rd.relativedelta(months=-1)
    month_ago_timestamp = month_ago.timestamp()

    for message in p.listen():
        with connection:
            data = message['data']
            # Добавляем новую запись в журнал
            cursor.execute('INSERT INTO log_entries (timestamp, event) VALUES ({}, "{}")'.format(time(), data))
            # Удаляем записи, которым более месяца
            del_cmd = 'DELETE FROM log_entries WHERE timestamp < {}'.format(month_ago_timestamp)
            cursor.execute(del_cmd)

# def failing_test_thread(*args, **kwargs):
#     print('test thread started')
#     r = redis.StrictRedis(decode_responses=True)
#     p = r.pubsub(ignore_subscribe_messages=True)
#     p.subscribe('stop')
#
#     for _ in p.listen():
#         print('raising exception in test thread')
#         raise Exception

