import json
import ujson
import math
import os
import re
import sys
import threading
import time
import numpy as np
import redis
from axiomLib.loggers import create_logger
from axiomLowLevelCommunication.serialTransceiver import SerialTransceiver
from axiomLowLevelCommunication.config import CRC8TABLE, POWER_UNIT_STATES_TABLE, POWER_UNIT_SIGNALS_TABLE, \
    INPUT_CMD_STATE_CHANNEL, OUTPUT_INFO_STATE_CHANNEL, INPUT_REQUEST_INSULATION_CHANNEL, OUTPUT_INFO_METRICS_CHANNEL, \
    LOG_FILE_DIRECTORY, LOG_FILE_NAME
from apscheduler.schedulers.background import BackgroundScheduler


class HighLowTransceiver:

    def __init__(self):
        """
        Инициализирует экземпляр класса

        :ivar settings: конфигурация аппаратных модулей системы
        :ivar redis: объект подключения к БД Redis
        :ivar isRunning: флаг работы/остановки
        :ivar power_unit_addrs: список адресов силовых модулей
        :ivar input_unit_addrs: список адресов модулей ввода
        :ivar unit_addrs_to_transceivers_map: таблица соответствия адресов модулей объектам
         :class:`~axiomLowLevelCommunication.serialTransceiver.SerialTransceiver`,
         подключенным к COM портам, соответствующего модуля
        :ivar power_units_state_dicts: структура состояния силовых модулей
        :ivar input_units_state_dicts: структура состояния модулей ввода
        :ivar power_units_maintenance: флаги силовых модулей обслуживание/штатная работа
        :ivar humanreadable_states: таблица соответствия цифровых кодов состояний
        силовых модулей и их словесного описания
        :ivar humanreadable_signals: таблица соответствия цифровых кодов сигналов
        силовых модулей и их словесного описания
        :ivar ch_locks: словарь с объектами блокировки управления каналами силовых модулей
        :ivar scheduler: планировщик задач
        :ivar Crc8Table: таблица для рассчета контрольных сумм CRC8 табличным способом
        :ivar pu_regex: шаблон регулярного выражения для парсинга посылок от силовых модулей
        :ivar iu_regex: шаблон регулярного выражения для парсинга посылок от модулей ввода
        :ivar P_passive: мощность потребляемая системой без учета подключенных к ней потребителей
        """
        self.logger = create_logger(logger_name=__name__,
                                    logfile_directory=LOG_FILE_DIRECTORY,
                                    logfile_name=LOG_FILE_NAME)

        # Загружаем настройки
        self.settings = self.load_settings()
        if not self.settings:
            sys.exit(0)

        # Подключаемся к брокеру
        self.redis = redis.StrictRedis(decode_responses=True)

        # Флаг для остановки потоков чтения/записи
        self.isRunning = False

        # Привязка адресов модулей ввода к адресам силовых модулей
        self.hardware_units = self.settings['hardware units']

        # список силовых модулей
        self.power_unit_addrs = self.settings['power units'].keys()

        # список модулей ввода
        self.input_unit_addrs = self.settings['input units'].keys()

        # таблица соответствия адресов модулей и объектов трансиверов
        self.unit_addrs_to_transceivers_map = {}

        # Подключаемся к com порту каждого силового модуля
        for power_unit_addr, params in self.settings['power units'].items():
            self.unit_addrs_to_transceivers_map[power_unit_addr] = SerialTransceiver(port=params['port'])
            self.unit_addrs_to_transceivers_map[power_unit_addr].close()
            self.unit_addrs_to_transceivers_map[power_unit_addr].open()

        # Подключаемся к com порту каждого модуля ввода
        for input_unit_addr, params in self.settings['input units'].items():
            self.unit_addrs_to_transceivers_map[input_unit_addr] = SerialTransceiver(port=params['port'])
            self.unit_addrs_to_transceivers_map[input_unit_addr].close()
            self.unit_addrs_to_transceivers_map[input_unit_addr].open()

        # Создаем структуру состояния для каждого силового модуля
        self.power_units_state_dicts = dict()
        for power_unit_addr in self.power_unit_addrs:
            self.power_units_state_dicts[power_unit_addr] = {
                'link': False,
                'st': {key: value for key, value in zip(('state1', 'state2', 'signal1', 'signal2', 'addr', 'cnt'),
                                                        (None, None, None, None, '{}'.format(power_unit_addr), None))},
                'adc': {key: value for key, value in zip(('sample1', 'sample2', 'addr', 'cnt'),
                                                         (None, None, '{}'.format(power_unit_addr), None))},
                'ld': {key: value for key, value in zip(('load1', 'load2', 'angle1', 'angle2', 'addr', 'cnt'),
                                                        (None, None, None, None, '{}'.format(power_unit_addr), None))},
                'tmpr': {key: value for key, value in zip(('temp1', 'temp2', 'addr', 'cnt'),
                                                          (None, None, '{}'.format(power_unit_addr), None))},
                'isol': {key: value for key, value in zip(('isol1', 'isol2'), (None, None))}
            }

        # Создаем структуру состояния для каждого модуля ввода
        self.input_units_state_dicts = dict()
        for input_unit_addr in self.input_unit_addrs:
            self.input_units_state_dicts[input_unit_addr] = {
                'st': {'state': None, 'signal': None, 'addr': '{}'.format(input_unit_addr), 'cnt': None},
                'volt': {'Vin': None, 'freq': None, 'addr': '{}'.format(input_unit_addr), 'cnt': None},
                'cur': {'Iin': None, 'Iout': None, 'Iypr': None, 'addr': '{}'.format(input_unit_addr), 'cnt': None}
            }

        # Флаг, показывающий, что модуль находится в режиме обслуживания/монтажа
        self.power_units_maintenance = {power_unit_addr: False for power_unit_addr in self.power_unit_addrs}

        # объекты блокировки управления каналами
        self.ch_locks = {}
        for unit_addr in self.power_unit_addrs:
            for output in ['1', '2']:
                ch_addr = 'ch:{}:{}'.format(unit_addr, output)
                self.ch_locks[ch_addr] = threading.Lock()

        # Счетчики команд силовых модулей
        self.power_units_counters = {}.fromkeys(self.power_unit_addrs, 0)

        # Планировщик для отправки на модуль "Логика" текущих значений потребляемой мощности в каналах
        self.scheduler = BackgroundScheduler()
        self.scheduler.add_job(self.publish_current_characteristics, 'interval', seconds=10)

        # Регулярные выражения для посылок от модулей ввода и силовых модулей
        pu_st_regex = r'(?P<type_st>st) (?P<state1>\d{1,4}) (?P<state2>\d{1,4}) ' \
                      r'(?P<signal1>\d{1,4}) (?P<signal2>\d{1,4})'
        # pu_adc_regex = r'(?P<type_adc>adc) (?P<sample1>\d{1,2}\.\d{0,100}) ' \
        #                r'(?P<sample2>\d{1,2}\.\d{0,100}) (?P<freq>\d{0,2})'
        pu_adc_regex = r'(?P<type_adc>adc) (?P<sample1>\d{1,2}\.\d{0,100}) (?P<sample2>\d{1,2}\.\d{0,100})'
        pu_tmpr_regex = r'(?P<type_tmpr>tmpr) (?P<temp1>\d{1,3}) (?P<temp2>\d{1,3})'
        iu_st_regex = r'(?P<type_st>st) (?P<state>\d{1,4}) (?P<signal>\d{1,4})'
        volt_regex = r'(?P<type_volt>volt) (?P<Vin>\d{1,3}\.\d{0,100}) (?P<freq>\d{0,2})'
        cur_regex = r'(?P<type_cur>cur) (?P<Iin>\d{1,2}\.\d{0,100}) (?P<Iout>\d{1,2}\.\d{0,100}) ' \
                    r'(?P<Iypr>\d{1,2}\.\d{0,100})'
        # iu_adc_regex = r'(?P<type_adc>adc) (?P<sample>\d{1,4}) \d{1,4}'
        ld_regex = r'(?P<type_ld>ld) (?P<load1>\d{1,4}) (?P<load2>\d{1,4}) (?P<angle1>\d{1,4}) (?P<angle2>\d{1,4})'
        rply_regex = r'(?P<reply>(?P<type_rply>rply) .+)'
        counter_regex = r'(?P<cnt>\d{1,10})'
        unit_addr_regex = r'(?P<addr>%s)'

        self.pu_regex = r'(({st}|{adc}|{ld}|{tmpr}) {cnt}{addr})|{rply}'.format(st=pu_st_regex,
                                                                                adc=pu_adc_regex,
                                                                                ld=ld_regex,
                                                                                tmpr=pu_tmpr_regex,
                                                                                cnt=counter_regex,
                                                                                addr=unit_addr_regex,
                                                                                rply=rply_regex)

        self.iu_regex = r'(({st}|{volt}|{cur}) {cnt}{addr})|{rply}'.format(st=iu_st_regex,
                                                                           volt=volt_regex,
                                                                           cur=cur_regex,
                                                                           cnt=counter_regex,
                                                                           addr=unit_addr_regex,
                                                                           rply=rply_regex)

        # Пассивная потреблямая схемой мощность
        self.P_passive = self.calc_passive_consumption()

    def calc_crc8(self, buff, crc):
        """
        Рассчитывает контрольную сумму по алгоритму CRC8

        :type buff: numpy.ndarray
        :param buff: массив с байтами числа
        :type crc: int
        :param crc: инициализирующее значение
        :rtype: numpy.int64
        :return: рассчитанная контрольная сумма
        """
        i = 0
        while i < len(buff):
            crc = CRC8TABLE[int(crc ^ (buff[i]))]
            i += 1

        return crc

    def split_to_bytes(self, number, num_byte):
        """
        Представляет число в виде массива байтов, из которых оно состоит
        :type number: numpy.uint8
        :param number: исходное число
        :type num_byte: int
        :param num_byte: количество байт занимаемых числом
        :rtype: numpy.ndarray
        :return: массив с байтами числа
        """
        buff = np.zeros(num_byte, np.uint8)

        for i in range(num_byte):
            buff[i] = ((number >> (i * 8)) & 0xff)

        return buff

    def load_settings(self):
        """
        Загружает настройки ПО из файла с настройками

        :rtype: dict
        :return: словарь с настройками
        """
        settings = {}
        default_fname = '/etc/axiom/settings.json'
        fname = os.environ.get('AXIOM_SETTINGS', default=default_fname)
        # Пытаемся загрузить настройки
        try:
            with open(fname) as settings_file:
                settings = json.load(settings_file)
        except (IOError, FileNotFoundError) as e:
            # Если не удается открыть файл
            self.logger.error('Ошибка при попытке открыть файл настроек: {}'.format(e))
        except (TypeError, ValueError) as e:
            # Если не удается загрузить настройки из файла
            self.logger.error('Ошибка при попытке загрузить настройки из файла настроек: {}'.format(e))

        # Если не удалось загрузить настройки,
        # пытаемся загрузить настройки из файла по умолчанию
        if not settings and fname != default_fname:
            try:
                with open(default_fname) as settings_file:
                    settings = json.load(settings_file)
            except (IOError, FileNotFoundError) as e:
                # Если не удается открыть файл
                self.logger.error('Ошибка при попытке открыть файл настроек по умолчанию: {}'.format(e))
            except (TypeError, ValueError) as e:
                # Если не удается загрузить настройки из файла
                self.logger.error('Ошибка при попытке загрузить настройки из файла настроек по умолчанию: {}'.format(e))

        return settings

    def check_power_unit_counter(self, counter, unit_addr, type_cmd):
        """
        Контролирует корректность счетчика в посылке от ПО силового модуля

        :type counter: str
        :param counter: значение счетчика
        :type unit_addr: str
        :param unit_addr: адрес силового модуля, от которого пришла посылка
        :type type_cmd: str
        :param type_cmd: тип посылки

        .. figure:: _static/check_power_unit_counter.png
           :scale: 50%
           :align: center
        """

        # Если счетчик None, значит модуль до этого не был инициализирован
        if self.power_units_state_dicts[unit_addr][type_cmd]['cnt'] is None:
            self.logger.info('Модуль {} впервые зафиксирован с системе'.format(unit_addr))

            threading.Thread(target=self.init_power_unit, args=(unit_addr,)).start()

            # Для всех посылок устанавливается максимально возможное значение счетчика,
            # чтобы избежать повторного запуска инициализации при получении других типов посылок
            self.power_units_state_dicts[unit_addr]['st']['cnt'] = str(2 ** 32 - 1)
            self.power_units_state_dicts[unit_addr]['adc']['cnt'] = str(2 ** 32 - 1)
            self.power_units_state_dicts[unit_addr]['ld']['cnt'] = str(2 ** 32 - 1)
            self.power_units_state_dicts[unit_addr]['tmpr']['cnt'] = str(2 ** 32 - 1)

        # Если получен нулевой счетчик, а предыдущее значение счетчика не было максимально возможным -
        # значит модуль перезагрузился и требуется выполнить его инициализацию

        elif counter == '0' and self.power_units_state_dicts[unit_addr][type_cmd]['cnt'] != str(2 ** 32 - 1) \
                and not self.power_units_maintenance[unit_addr]:
            log_msg = 'От модуля {} получена посылка со значением счетчика 0. Текущее значение счетчика {}.' \
                      ' ПО модуля перезагружалось'.format(
                       unit_addr, self.power_units_state_dicts[unit_addr][type_cmd]['cnt'])
            self.logger.error(log_msg)

            threading.Thread(target=self.init_power_unit, args=(unit_addr,)).start()

            self.power_units_state_dicts[unit_addr]['st']['cnt'] = str(2 ** 32 - 1)
            self.power_units_state_dicts[unit_addr]['adc']['cnt'] = str(2 ** 32 - 1)
            self.power_units_state_dicts[unit_addr]['ld']['cnt'] = str(2 ** 32 - 1)

    def check_input_unit_counter(self, counter, unit_addr, type_cmd):
        pass

    def on_new_state_parcel(self, parcel):
        """
        Обрабатывает новые посылки типа "st" от силовых модулей

        Если состояние какого-либо из каналов силового модуля изменилось то:

        #. новое состояние публикуется в канал ``axiomLowLevelCommunication:info:state``
        #. если канал перешел в одно из состояний ('2', '4', '5', '6', '7'), то новое состояние сохраняется в Redis
        #. сообщение о переходе канала в новое состояние пишется в лог

        :type parcel: dict
        :param parcel: разобранная посылка от низкого уровня

        Если состояние одного из каналов '0' и модуль не находится в режиме "обслуживание",
        выполняется инициализация модуля

        .. figure:: _static/on_new_state_parcel.png
           :align: center
        """
        power_unit_addr = parcel['addr']

        # Случай, когда с модуль был в режиме обслуживания, а потом был из него выведен
        # Нужно выполнить инициализацию
        if (parcel['state1'] == '0' or parcel['state2'] == '0') and parcel['cnt'] != '0' \
                and not self.power_units_maintenance[power_unit_addr]:
            print('инициализируем модуль')

            log_msg = 'От модуля {} получена посылка с каналом в состоянии "0" (idle) и' \
                      ' значением счетчика отличным от нуля. ' \
                      'Требуется выполнить инициализацию модуля'.format(power_unit_addr)
            self.logger.info(log_msg)

            threading.Thread(target=self.init_power_unit, args=(power_unit_addr,)).start()

        for i in ('1', '2'):
            # предыдущее и новое состояния
            prev_state = self.power_units_state_dicts[power_unit_addr]['st']['state{}'.format(i)]
            new_state = parcel['state{}'.format(i)]

            # если состояние изменилось
            if prev_state != new_state:
                self.redis.publish(channel=OUTPUT_INFO_STATE_CHANNEL,
                                   message=ujson.dumps({'addr': 'ch:{}:{}'.format(power_unit_addr, i),
                                                        'state': {'status': new_state}}))
                # Сохраняем в БД только стабильные состояния
                if new_state in ('2', '4', '5', '6', '7'):
                    self.redis.set(name='ch:{}:{}'.format(power_unit_addr, i), value={'status': new_state})
                # Логируем изменение
                humanreadable_state = POWER_UNIT_STATES_TABLE[new_state]
                new_signal = parcel['signal{}'.format(i)]
                humanreadable_signal = POWER_UNIT_SIGNALS_TABLE[new_signal]
                log_msg = 'Выход "{}" модуля "{}" перешел в состояние "{}".' \
                          ' Сигнал перехода: "{}"'.format('ch:{}:{}'.format(power_unit_addr, i), power_unit_addr,
                                                          humanreadable_state, humanreadable_signal)
                self.logger.info(log_msg)

    def handle_reply(self, reply):
        """
        Обрабатывает ответы по ПО низкого уровня

        Отправляет ответы на запросы измерения сопротивления изоляции в канал Redis
        ``axiomLowLevelCommunication:response:insulation`` в формате
        ``<адрес выхода силового модуля> <измеренное значение>``. Записывает измеренное значение
        в структуру состояния силовых модулей :attr:`power_units_state_dicts`

        :type reply: str
        :param reply: посылка типа "rply" от ПО низкого уровня
        """
        self.logger.info('Сообщение от низкого уровня: {}'.format(reply))

        if 'isol' in reply:
            try:
                _, _, channel, isol_value, cntAddr = reply.split(' ')
                channel_position = channel[-1]
                unit_addr = reply[reply.find('m'):]

                self.power_units_state_dicts[unit_addr]['isol']['isol{}'.format(channel_position)] = isol_value

                self.redis.publish('axiomLowLevelCommunication:response:insulation', 'ch:{}:{} {}'.format(
                    unit_addr, channel_position, isol_value))
            except Exception as e:
                print(e)

    def update_power_unit_state(self, unit_addr):
        """
        Обрабатывает посылки от ПО силовых модулей

        * для посылок типа "rply" вызывается функция :func:`handle_reply`
        * для посылок типа "st" вызывается функция :func:`on_new_state_parcel`;
        * для посылок тика "st", "adc", "ld", "tmpr" обновляются соответстующие поля структуры
        :attr:`power_units_state_dicts`;
        * для всех посылок вызываетс функция :func:`check_power_unit_counter`.

        :type unit_addr: str
        :param unit_addr: адрес силового модуля

        .. figure:: _static/update_power_unit_state.png
           :scale: 50%
           :align: center
        """

        # Компилируем регулярное выражение для парсинга посылок
        binary_pu_regex = (self.pu_regex % unit_addr).encode()
        power_unit_parcel_regex = re.compile(binary_pu_regex)

        for raw_data in self.unit_addrs_to_transceivers_map[unit_addr].read_generator():
            if not self.isRunning:
                break
            # Разбираем считанные данные с помощью регулярного выражения
            byte_parcel = power_unit_parcel_regex.search(raw_data)
            # print('byte_parcel', byte_parcel)
            if not byte_parcel:
                continue

            # декодируем посылку
            parcel = {key: value.decode() for key, value in byte_parcel.groupdict().items() if value}

            # Определяем тип посылки
            parcel_type = parcel.get('type_st') or \
                          parcel.get('type_adc') or \
                          parcel.get('type_ld') or \
                          parcel.get('type_tmpr') or \
                          parcel.get('type_rply')

            self.power_units_state_dicts[unit_addr]['link'] = True

            # <editor-fold desc="ответ на ранее отправленную команду">
            if parcel_type == 'rply':
                reply = parcel['reply'].strip()
                self.handle_reply(reply)
                continue
            # </editor-fold>

            # Счетчик посылки
            counter = parcel['cnt']

            # Проверка счетчика посылок
            self.check_power_unit_counter(counter, unit_addr, parcel_type)

            # В случае изменения состояния силовых выходов
            if parcel_type == 'st':
                # print(raw_data)
                self.on_new_state_parcel(parcel)

            # Обновление структуры состояния модуля
            for key in self.power_units_state_dicts[unit_addr][parcel_type]:
                self.power_units_state_dicts[unit_addr][parcel_type][key] = parcel[key]

    def update_input_unit_state(self, unit_addr):
        """
        Обрабатывает посылки от ПО модулей ввода

        * для посылок типа "rply" вызывается функция :func:`handle_reply`
        * для посылок тика "st", "volt", "cur" обновляются соответстующие поля структуры
        :attr:`input_units_state_dicts`;
        * для всех посылок вызываетс функция :func:`check_input_unit_counter`.

        :type unit_addr: str
        :param unit_addr: адрес модуля ввода

        .. figure:: _static/update_input_unit_state.png
           :scale: 50%
           :align: center
        """

        binary_iu_regex = (self.iu_regex % unit_addr).encode()
        input_unit_parcel_regex = re.compile(binary_iu_regex)

        for raw_data in self.unit_addrs_to_transceivers_map[unit_addr].read_generator():
            if not self.isRunning:
                break

            # Разбираем считанные данные с помощью регулярного выражения
            byte_parcel = input_unit_parcel_regex.search(raw_data)
            if not byte_parcel:
                continue

            # декодируем посылку
            parcel = {key: value.decode() for key, value in byte_parcel.groupdict().items() if value}

            # Определяем тип посылки
            parcel_type = parcel.get('type_st') or \
                          parcel.get('type_volt') or \
                          parcel.get('type_cur') or \
                          parcel.get('type_rply')

            # <editor-fold desc="ответ на ранее отправленную команду">
            if parcel_type == 'rply':
                reply = parcel['reply'].replace('\n', '')
                self.logger.info('Сообщение от низкого уровня: {}'.format(reply))
                continue
            # </editor-fold>

            # Счетчик посылки
            counter = parcel['cnt']

            # Проверка счетчика посылок
            self.check_input_unit_counter(counter, unit_addr, parcel_type)

            # Обновление структуры состояния модуля
            for key in self.input_units_state_dicts[unit_addr][parcel_type]:
                self.input_units_state_dicts[unit_addr][parcel_type][key] = parcel[key]

            # pprint(self.input_units_state_dicts)

    def reader_target(self):
        """
        Осуществляет прием данных от низкоуровневого ПО

        Для каждого силового и вводного модуля запускает в отдельном потоке функцию
        :func:`update_power_unit_state` или :func:`update_input_unit_state` соответственно
        и контролирует работу запущенных потоков

        .. figure:: _static/reader_target.png
           :scale: 50%
           :align: center
        """
        # Создаем потоки для обновления структуры состояния для каждого модуля
        updaters = {}

        for unit_addr in self.power_unit_addrs:
            updaters[unit_addr] = threading.Thread(target=self.update_power_unit_state, args=(unit_addr,))
            updaters[unit_addr].start()

        for unit_addr in self.input_unit_addrs:
            updaters[unit_addr] = threading.Thread(target=self.update_input_unit_state, args=(unit_addr,))
            updaters[unit_addr].start()

        # Контролируем, чтобы все потоки были в рабочем состоянии
        while self.isRunning:
            # self.event.wait()
            # self.collect_units_state()
            for unit_addr in self.power_unit_addrs:
                if not updaters[unit_addr].isAlive():
                    updaters[unit_addr] = threading.Thread(target=self.update_power_unit_state, args=(unit_addr,))
                    updaters[unit_addr].start()
            for unit_addr in self.input_unit_addrs:
                if not updaters[unit_addr].isAlive():
                    updaters[unit_addr] = threading.Thread(target=self.update_input_unit_state, args=(unit_addr,))
                    updaters[unit_addr].start()
            time.sleep(1)

    def init_power_unit(self, unit_addr):
        """
        Инициализирует силовой модуль

        Отправляет на силовой модуль команды запуска и установки порогов и
        проверяет их исполнение. После запуска и установки порогов
        включает выходы, которые были включены до перезагрузки модуля

        :type unit_addr: str
        :param unit_addr: адрес силового модуля
        :rtype: bool
        :return: True - инициализация прошла успешно, False - возникли ошибки

        .. figure:: _static/init_power_unit.png
           :scale: 50%
           :align: center
        """
        time.sleep(0.1)

        # Смотрим в каком состоянии были каналы до перезагрузки
        raw_ch1_prev_state = self.redis.get('ch:{}:1'.format(unit_addr))
        raw_ch2_prev_state = self.redis.get('ch:{}:2'.format(unit_addr))

        # блокировщики управления в каналах модуля
        ch1_lock = self.ch_locks['ch:{}:1'.format(unit_addr)]
        ch2_lock = self.ch_locks['ch:{}:2'.format(unit_addr)]

        # Если удалось установить блокировку управления первым каналом -
        # пытаемся установить блокировку управления вторым каналом
        if ch1_lock.acquire(timeout=3):
            # Если блокировку управления вторым каналом установить не удалось:
            if not ch2_lock.acquire(timeout=3):
                # 0. снимаем блокировку управления первым каналом
                ch1_lock.release()
                # 1. Проверяем, возможно инициализация уже выполнена в другом потоке
                check_time = time.time()
                while time.time() - check_time < 3:
                    ch1_current_state = self.power_units_state_dicts[unit_addr]['st']['state1']
                    ch2_current_state = self.power_units_state_dicts[unit_addr]['st']['state2']
                    if ch1_current_state not in ('0', '3') and ch2_current_state not in ('0', '3'):
                        return True
                    else:
                        time.sleep(0.1)

                # Если модуль не переходит в инициализированное состояние
                # 2. логируем ошибку
                log_msg = 'Ошибка при инициализации модуля "{}":' \
                          ' не удается заблокировать управление вторым каналом'.format(unit_addr)
                self.logger.error(log_msg)

                # 3. Возвращаем False
                return False
        # Если блокировку управления первым каналом установить не удалось:
        else:
            # 0. Проверяем, возможно инициализация уже выполнена в другом потоке
            check_time = time.time()
            while time.time() - check_time < 3:
                ch1_current_state = self.power_units_state_dicts[unit_addr]['st']['state1']
                ch2_current_state = self.power_units_state_dicts[unit_addr]['st']['state2']
                if ch1_current_state not in ('0', '3') and ch2_current_state not in ('0', '3'):
                    return True
                else:
                    time.sleep(0.1)
            # 1. Если модуль не переходит в инициализированное состояние - логируем ошибку, возвращаем False
            log_msg = 'Ошибка при инициализации модуля "{}":' \
                      ' не удается заблокировать управление первым каналом'.format(unit_addr)
            self.logger.error(log_msg)
            return False

        # После блокировки управления в обоих каналах модуля, смотрим состояние каналов
        ch1_current_state = self.power_units_state_dicts[unit_addr]['st']['state1']
        ch2_current_state = self.power_units_state_dicts[unit_addr]['st']['state2']

        # Если хотя бы один из каналов в состоянии 1 (idle) - вызываем функцию запуска модуля
        if ch1_current_state == '0' or ch2_current_state == '0':
            if not self.run_power_unit(unit_addr=unit_addr):
                ch1_lock.release() or ch2_lock.release()
                return False

        # Если функция запуска завершилась успешно - снова смотрим состояние каналов
        ch1_current_state = self.power_units_state_dicts[unit_addr]['st']['state1']
        ch2_current_state = self.power_units_state_dicts[unit_addr]['st']['state2']

        # Если хотя бы один из каналов в состоянии 3 (nuse) - вызываем функцию конфигурации модуля
        if ch1_current_state == '3' or ch2_current_state == '3':
            if not self.configure_power_unit(unit_addr=unit_addr):
                ch1_lock.release() or ch2_lock.release()
                return False

        # Если функция конфигурации завершилась успешно:
        # 1.снимаем блокировку управления каналами
        ch1_lock.release() or ch2_lock.release()

        # 2. восстанавливаем состояние выходов сохраненное в БД (если это возможно)
        for ch_position in ('1', '2'):
            raw_prev_ch_state = eval('raw_ch{}_prev_state'.format(ch_position))
            try:
                prev_ch_state = eval(raw_prev_ch_state)
                if prev_ch_state['status'] == '5':
                    self.set_ch_state(channel_addr='ch:{}:{}'.format(unit_addr, ch_position),
                                      new_state_dict=prev_ch_state)
            # Если в БД было сохранено некорректное значение (или не записано никакое) - ничего не делаем
            except Exception:
                pass

        # 3. возвращаем True
        return True

    def run_power_unit(self, unit_addr, retries=3):
        """
        Запускает ПО силового модуля

        Отправляет на модуль команду запуска ``run start <unit_addr>``.
        Контролирует исполнение команды. Команда считается выполненной
        успешно, если ни один из каналов не остался в состоянии '0' (idle)

        :type unit_addr: str
        :param unit_addr: адрес силового модуля
        :type retries: int
        :param retries: количество возможных повторых попыток
        :rtype: bool
        :return: True - успешное исполнение команды), False - неуспешное

        .. figure:: _static/run_power_unit.png
           :align: center
        """
        # Команда запуска модуля:
        run_cmd = 'run start {}'.format(unit_addr)

        while retries + 1:
            # Фиксируем время отправки
            send_time = time.time()

            # Если команда записана в последовательный порт успешно:
            # self.event.clear()
            time.sleep(0.01)
            if self.unit_addrs_to_transceivers_map[unit_addr].write(run_cmd):
                # self.event.set()
                # Пока не истек таймаут, смотрим на состояние выходов
                while time.time() - send_time < 10:
                    ch1_state = self.power_units_state_dicts[unit_addr]['st']['state1']
                    ch2_state = self.power_units_state_dicts[unit_addr]['st']['state2']

                    # Если состояние хотя бы одного остается '0' - ждем дальше
                    if ch1_state in ('0', '1') or ch2_state in ('0', '1'):
                        time.sleep(0.01)
                        continue
                    # Если состояние обоих выходов не '0' - запуск модуля завершен. Логируем успех, возвращаем True
                    else:
                        ch1_state = self.power_units_state_dicts[unit_addr]['st']['state1']
                        ch2_state = self.power_units_state_dicts[unit_addr]['st']['state2']

                        ch1_humanreadable_state = POWER_UNIT_STATES_TABLE[ch1_state]
                        ch2_humanreadable_state = POWER_UNIT_STATES_TABLE[ch2_state]

                        channel1_addr = 'ch:{}:1'.format(unit_addr)
                        channel2_addr = 'ch:{}:2'.format(unit_addr)

                        log_msg = 'Запуск модуля "{}" выполнен.' \
                                  ' Текущее состояние выходов: "{}" - "{}", "{}" - "{}"'.format(
                                   unit_addr, channel1_addr, ch1_humanreadable_state,
                                   channel2_addr, ch2_humanreadable_state)
                        self.logger.error(log_msg)

                        return True
                retries -= 1
            # Если при записи команды возникли ошибки - пробуем еще
            else:
                # self.event.set()
                retries -= 1

        # Если дошли до сюда, значит, запуск выполнить не удалось. Логируем ошибку, возвращаем False
        ch1_state = self.power_units_state_dicts[unit_addr]['st']['state1']
        ch2_state = self.power_units_state_dicts[unit_addr]['st']['state2']

        ch1_humanreadable_state = POWER_UNIT_STATES_TABLE[ch1_state]
        ch2_humanreadable_state = POWER_UNIT_STATES_TABLE[ch2_state]

        channel1_addr = 'ch:{}:1'.format(unit_addr)
        channel2_addr = 'ch:{}:2'.format(unit_addr)

        log_msg = 'Ошибка при выполнении запуска модуля "{}".' \
                  ' Текущее состояние выходов: "{}" - "{}", "{}" - "{}"'.format(
                   unit_addr, channel1_addr, ch1_humanreadable_state,
                   channel2_addr, ch2_humanreadable_state)
        self.logger.error(log_msg)

        return False

    def configure_power_unit(self, unit_addr, retries=3):
        """
        Конфигурирует ПО силового модуля:

        Отправляет на силовой модуль команды конфигурации:

        * установка порогов по току потребления : ``adc hgrp <Imax1> <Imax2> <crc8-1> <crc8-2> <unit_addr>``;
        * установка порогов по току утечки: ``adc hlgrp <Imax1> <Imax2> <crc8-1> <crc8-2> <unit_addr>``.

        Контролирует исполнение команд. Команды считается выполненными успешно,
        если ни один из каналов не остался в состоянии '3' (nuse)

        :type unit_addr: str
        :param unit_addr: адрес силового модуля
        :type retries: int
        :param retries: количество возможных повторых попыток
        :rtype: bool
        :return: True - успешное исполнение команды), False - неуспешное

        .. figure:: _static/configure_power_unit.png
           :align: center
        """
        # Команда установки порогов по току потребления:
        max_consumption_current_1 = self.settings['power units'][unit_addr]['max consumption current'][0]
        max_consumption_current_2 = self.settings['power units'][unit_addr]['max consumption current'][1]

        Iconsumption1 = math.ceil((24 * 33 * max_consumption_current_1) / 50)
        Iconsumption2 = math.ceil((24 * 33 * max_consumption_current_2) / 50)

        buff1_consumption = self.split_to_bytes(np.uint8(Iconsumption1), 1)
        buff2_consumption = self.split_to_bytes(np.uint8(Iconsumption2), 1)

        crc1_consumption = self.calc_crc8(buff1_consumption, 0xff)
        crc2_consumption = self.calc_crc8(buff2_consumption, 0xff)

        consumption_current_cmd = 'adc hgrp {} {} {} {} {}'.format(
            Iconsumption1, Iconsumption2, crc1_consumption, crc2_consumption, unit_addr)
        # consumption_current_cmd = 'adc h 255 all 1 {}'.format(unit_addr)
        # print(consumption_current_cmd)

        # Команда установки порогов по току утечки:
        max_leak_current_1 = self.settings['power units'][unit_addr]['max leak current'][0]
        max_leak_current_2 = self.settings['power units'][unit_addr]['max leak current'][1]

        Ileak1 = round((65534 * 33 * max_leak_current_1) / 1500)
        Ileak2 = round((65534 * 33 * max_leak_current_2) / 1500)

        buff1_leak = self.split_to_bytes(np.uint8(Ileak1), 1)
        buff2_leak = self.split_to_bytes(np.uint8(Ileak2), 1)

        crc1_leak = self.calc_crc8(buff1_leak, 0xff)
        crc2_leak = self.calc_crc8(buff2_leak, 0xff)

        leak_current_cmd = 'adc hlgrp {} {} {} {} {}'.format(Ileak1, Ileak2, crc1_leak, crc2_leak, unit_addr)
        print(leak_current_cmd)

        while retries + 1:
            # Фиксируем время отправки
            send_time = time.time()

            # self.event.clear()
            time.sleep(0.01)
            # Если команда записана в последовательный порт успешно:
            if self.unit_addrs_to_transceivers_map[unit_addr].write(consumption_current_cmd):
                time.sleep(0.5)
                if self.unit_addrs_to_transceivers_map[unit_addr].write(leak_current_cmd):
                    time.sleep(0.5)
                    # Пока не истек таймаут, смотрим на состояние выходов
                    while time.time() - send_time < 3:
                        ch1_state = self.power_units_state_dicts[unit_addr]['st']['state1']
                        ch2_state = self.power_units_state_dicts[unit_addr]['st']['state2']

                        # Если состояние хотя бы одного остается '3' - ждем дальше
                        if ch1_state == '3' or ch2_state == '3':
                            time.sleep(0.01)
                            continue
                        # Если состояние обоих выходов не '3' - запуск модуля завершен. Логируем успех, возвращаем True
                        else:
                            ch1_state = self.power_units_state_dicts[unit_addr]['st']['state1']
                            ch2_state = self.power_units_state_dicts[unit_addr]['st']['state2']

                            ch1_humanreadable_state = POWER_UNIT_STATES_TABLE[ch1_state]
                            ch2_humanreadable_state = POWER_UNIT_STATES_TABLE[ch2_state]

                            channel1_addr = 'ch:{}:1'.format(unit_addr)
                            channel2_addr = 'ch:{}:2'.format(unit_addr)

                            log_msg = 'Конфигурация модуля "{}" выполнена.' \
                                      ' Текущее состояние выходов: "{}" - "{}", "{}" - "{}"'.format(
                                       unit_addr, channel1_addr, ch1_humanreadable_state,
                                       channel2_addr, ch2_humanreadable_state)
                            self.logger.info(log_msg)

                            return True
                    retries -= 1
                # Если при записи команды возникли ошибки - пробуем еще
                else:
                    retries -= 1
            else:
                retries -= 1

        # Если дошли до сюда, значит, конфигурацию выполнить не удалось. Логируем ошибку, возвращаем False
        ch1_state = self.power_units_state_dicts[unit_addr]['st']['state1']
        ch2_state = self.power_units_state_dicts[unit_addr]['st']['state2']

        ch1_humanreadable_state = POWER_UNIT_STATES_TABLE[ch1_state]
        ch2_humanreadable_state = POWER_UNIT_STATES_TABLE[ch2_state]

        channel1_addr = 'ch:{}:1'.format(unit_addr)
        channel2_addr = 'ch:{}:2'.format(unit_addr)

        log_msg = 'Ошибка1 при выполнении конфигурации модуля "{}".' \
                  ' Текущее состояние выходов: "{}" - "{}", "{}" - "{}"'.format(
                   unit_addr, channel1_addr, ch1_humanreadable_state, channel2_addr, ch2_humanreadable_state)
        self.logger.error(log_msg)

        return False

    def before_return_from_set_ch_state(self, log_msg, channel_addr, current_state, redis_error_msg=None):
        """
        Вызывается перед выходом из фунции :func:`set_ch_state`

        Выполняет следущие действия:

        #. Публикует на брокер текущее состояние силового выхода;
        #. Записывает в лог результат выполнения команды;
        #. Публикует на брокер сообщение об ошибке, если она есть;

        :type log_msg: str
        :param log_msg: сообщение для записи в лог
        :type channel_addr: str
        :param channel_addr: адрес канала силового модуля
        :type current_state: str
        :param current_state: текущее состояние канала силового модуля ('0'...'7')
        :type redis_error_msg: str
        :param redis_error_msg: сообщение об ошибке для публикации на брокер (по умолчанию None)

        .. figure:: _static/before_return_from_set_ch_state.png
           :align: center
        """

        log_level = 'ERROR' if redis_error_msg else 'INFO'

        state_to_publish = {'addr': channel_addr, 'state': {'status': current_state}}
        self.redis.publish(channel=OUTPUT_INFO_STATE_CHANNEL, message=ujson.dumps(state_to_publish))

        if log_level == 'ERROR':
            self.logger.error(log_msg)
        elif log_level == 'INFO':
            self.logger.info(log_msg)

        if redis_error_msg:
            self.redis.publish(channel='axiomLowLevelCommunication:info:error', message=redis_error_msg)

    def set_ch_state(self, channel_addr, new_state_dict):
        """
        Выполняет команду установки нового состояния выхода силового модуля

        Отправляет на низкий уровень команду ``ch 1|2 on|off <unit_addr>``.
        Контролирует исполнение команды. Перед выходом вызывает метод :meth:`before_return_from_set_ch_state`.

        :type channel_addr: str
        :param channel_addr: адрес канала силового модуля
        :type new_state_dict: dict
        :param new_state_dict: состояние канала силового модуля, которое нужно установить.
        Формат: ``{'status': '4'|'5'}``
        :rtype: bool
        :return: True - команда выполнена, False - возникли ошибки

        .. figure:: _static/set_ch_state.png
           :scale: 50%
           :align: center
        """
        # Валидация команды
        invalid_cmd_log_msg = 'Получены некорректные данные для установки нового состояния силового выхода:' \
                              ' адрес канала: {}, новое состояние: {}'.format(channel_addr, new_state_dict)

        try:
            unit_addr = channel_addr.split(':')[1]
            channel_position = channel_addr.split(':')[2]
        except (IndexError, AttributeError):
            self.logger.error(invalid_cmd_log_msg)
            return False

        try:
            new_state = new_state_dict['status']
        except KeyError:
            self.logger.error(invalid_cmd_log_msg)
            return False

        if unit_addr not in self.power_unit_addrs:
            self.logger.error(invalid_cmd_log_msg)
            return False
        if channel_position not in ['1', '2']:
            self.logger.error(invalid_cmd_log_msg)
            return False
        if new_state not in ['4', '5']:
            self.logger.error(invalid_cmd_log_msg)
            return False

        # Если команда прошла валидацию, пишем в лог сообщение, что получена команда
        log_msg = 'Получена команда на установку состояния "{}" на выходе "{}"'.format(
            POWER_UNIT_STATES_TABLE[new_state], channel_addr)
        self.logger.info(log_msg)

        ###############################################
        # проверяем можно ли управлять данным каналом #
        ###############################################

        current_state = self.power_units_state_dicts[unit_addr]['st']['state{}'.format(channel_position)]

        # Проверяем проинициализирован ли модуль
        if current_state in ['0', '3']:
            # Если не проинициализирован - пишем об этом в лог и вызываем функцию инициализации
            log_msg = 'Силовой выход {} находится в состоянии {}. Требуется инициализация модуля'.format(
                channel_addr, current_state)
            self.logger.warning(log_msg)

            # Если инициализация не удалась - снимаем блокировку управления,
            # вызываем before_return_from_set_ch_state и выходим
            if not self.init_power_unit(unit_addr):
                current_signal = self.power_units_state_dicts[unit_addr]['st']['signal{}'.format(channel_position)]

                humanreadable_current_state = POWER_UNIT_STATES_TABLE[current_state]
                humanreadable_new_state = POWER_UNIT_STATES_TABLE[new_state]
                humanreadable_current_signal = POWER_UNIT_SIGNALS_TABLE[current_signal]

                log_msg = 'Невозможно установить в канале "{}" состояние "{}".' \
                          ' Канал находится в состоянии: "{}", сигнал перехода: "{}"'.format(
                           channel_addr, humanreadable_new_state, humanreadable_current_state,
                           humanreadable_current_signal)

                self.before_return_from_set_ch_state(channel_addr=channel_addr,
                                                     current_state=current_state,
                                                     log_msg=log_msg,
                                                     redis_error_msg=log_msg)

                return False

        # Заново записываем состояние в переменную, потому что оно могло измениться
        # после вызова init_power_unit
        current_state = self.power_units_state_dicts[unit_addr]['st']['state{}'.format(channel_position)]

        # Проверяем, что силовой выход не находится в состоянии fault, poff или lock
        # Если в одном из этих состояний, то выходим:
        if self.power_units_state_dicts[unit_addr]['st']['state{}'.format(channel_position)] in ['2', '6', '7']:
            current_signal = self.power_units_state_dicts[unit_addr]['st']['signal{}'.format(channel_position)]
            humanreadable_current_state = POWER_UNIT_STATES_TABLE[current_state]
            humanreadable_new_state = POWER_UNIT_STATES_TABLE[new_state]
            humanreadable_current_signal = POWER_UNIT_SIGNALS_TABLE[current_signal]

            log_msg = 'Невозможно установить в канале "{}" состояние "{}". Канал находится в состоянии: "{}", ' \
                      'сигнал перехода: "{}"'.format(channel_addr, humanreadable_new_state, humanreadable_current_state,
                                                     humanreadable_current_signal, )

            self.before_return_from_set_ch_state(channel_addr=channel_addr,
                                                 current_state=current_state,
                                                 log_msg=log_msg,
                                                 redis_error_msg=log_msg)

            return False

        # Если состояние, которое требуется установить и так уже установлено - выходим
        if current_state == new_state:
            humanreadable_state = POWER_UNIT_STATES_TABLE[current_state]

            log_msg = 'Выполнение команды не требуется. Выход "{}" уже находится в состоянии "{}"'.format(
                channel_addr, humanreadable_state)
            self.before_return_from_set_ch_state(log_msg=log_msg, channel_addr=channel_addr,
                                                 current_state=current_state)

            return True

        ###############################################
        #               Отправляем команду            #
        ###############################################

        # Если удалось захватить управление каналом
        if self.ch_locks[channel_addr].acquire(timeout=3):
            # команда для отправки + команда для светодиода
            if new_state == '4':
                ch_cmd = 'ch {} off {}'.format(channel_position, unit_addr)
                led_cmd = 'led inst {} off {}'.format(channel_position, unit_addr)
            elif new_state == '5':
                ch_cmd = 'ch {} on {}'.format(channel_position, unit_addr)
                led_cmd = 'led inst {} on {}'.format(channel_position, unit_addr)
            else:
                return False

            sending_time = time.time()

            # Если команда записана в последовательный порт успешно -
            # начинаем мониторить структуру состояния пока не истечет таймаут
            if self.unit_addrs_to_transceivers_map[unit_addr].write(ch_cmd):
                while time.time() - sending_time < 2:
                    current_state = self.power_units_state_dicts[unit_addr]['st']['state{}'.format(channel_position)]

                    # 1. Если текущее состояние стало таким, каким его хотели сделать -
                    # включаем/выключаем светодиод, снимаем блокировку и выходим
                    if current_state == new_state:
                        self.unit_addrs_to_transceivers_map[unit_addr].write(led_cmd)
                        self.ch_locks[channel_addr].release()
                        return True

                    # 2. Канал перешел в нерабочее состояние
                    elif current_state in ['2', '6', '7']:
                        # Выключаем светодиод
                        led_cmd = 'led inst {} off {}'.format(channel_position, unit_addr)
                        self.unit_addrs_to_transceivers_map[unit_addr].write(led_cmd)

                        self.ch_locks[channel_addr].release()

                        current_signal = self.power_units_state_dicts[unit_addr]['st'][
                            'signal{}'.format(channel_position)]

                        humanreadable_new_state = POWER_UNIT_STATES_TABLE[new_state]
                        humanreadable_result_state = POWER_UNIT_STATES_TABLE[current_state]
                        humanreadable_result_signal = POWER_UNIT_SIGNALS_TABLE[current_signal]

                        redis_msg = 'Ошибка при установке состояния "{}" на выходе "{}".' \
                                    ' Текущее состояние: "{}", сигнал перехода в состояние: "{}"'.format(
                                     humanreadable_new_state, channel_addr,
                                     humanreadable_result_state, humanreadable_result_signal)
                        log_msg = redis_msg

                        self.before_return_from_set_ch_state(channel_addr=channel_addr,
                                                             current_state=current_state,
                                                             redis_error_msg=redis_msg,
                                                             log_msg=log_msg)
                        return False

                    time.sleep(0.001)

                # Если до истечения таймаута состояние не изменилось

                current_signal = self.power_units_state_dicts[unit_addr]['st'][
                    'signal{}'.format(channel_position)]

                self.ch_locks[channel_addr].release()

                humanreadable_new_state = POWER_UNIT_STATES_TABLE[new_state]
                humanreadable_result_state = POWER_UNIT_STATES_TABLE[current_state]
                humanreadable_result_signal = POWER_UNIT_SIGNALS_TABLE[current_signal]

                redis_msg = 'Ошибка при установке состояния "{}" на выходе "{}".' \
                            ' Текущее состояние: "{}", сигнал перехода в состояние: "{}"'.format(
                             humanreadable_new_state, channel_addr, humanreadable_result_state,
                             humanreadable_result_signal)
                log_msg = redis_msg

                self.before_return_from_set_ch_state(channel_addr=channel_addr,
                                                     current_state=current_state,
                                                     redis_error_msg=redis_msg,
                                                     log_msg=log_msg)

                return False

            # Если не удалось записать команду в последовательный порт -
            # вызываем before_set_ch_state, снимаем блокировку управления и выходим
            else:
                # self.event.set()
                self.ch_locks[channel_addr].release()

                humanreadable_new_state = POWER_UNIT_STATES_TABLE[new_state]

                log_msg = 'Произошла ошибка записи в последовательный порт' \
                          ' при установке состояния "{}" на выходе "{}". Команда не выполнена.'.format(
                           humanreadable_new_state, channel_addr)

                self.before_return_from_set_ch_state(channel_addr=channel_addr,
                                                     current_state=current_state,
                                                     log_msg=log_msg,
                                                     redis_error_msg=log_msg)

                return False

        # Если до истечения таймаута блокировка на управление каналом не снимается - выходим
        else:
            humanreadable_new_state = POWER_UNIT_STATES_TABLE[new_state]
            log_msg = 'Невозможно установить состояние "{}" на выходе "{}":' \
                      ' управление заблокировано другим потоком'.format(humanreadable_new_state, channel_addr)

            self.before_return_from_set_ch_state(channel_addr=channel_addr,
                                                 current_state=current_state,
                                                 log_msg=log_msg,
                                                 redis_error_msg=log_msg)
            return False

    def measure_insulation_resistance(self, channel_addr):
        """
        Выполняет команду измерения сопротивления изоляции канала силового модуля

        Переводит силовой модуль в состояния "обслуживание". Отправляет на низкий уровень
        команду сброса: ``rst <unit_addr>``. Отравляет на низкий уровень команду
        на измерение сопротивления изоляции: ``resist start 1|2 <unit_addr>``.
        Контролирует выполнение команды

        :type channel_addr: str
        :param channel_addr: адрес канала силового модуля

        .. figure:: _static/measure_insulation_resistance.png
           :scale: 50%
           :align: center
        """

        _, unit_addr, channel_position = channel_addr.split(':')

        # Переводим модуль в режим обслуживания
        self.power_units_maintenance[unit_addr] = True

        # затираем предыдущее измеренное значение
        self.power_units_state_dicts[unit_addr]['isol']['isol{}'.format(channel_position)] = None
        # self.power_units_state_dicts[unit_addr]['isol']['isol2'] = None

        # блокировщики управления в каналах модуля
        ch_lock = self.ch_locks['ch:{}:{}'.format(unit_addr, channel_position)]
        # ch2_lock = self.ch_locks['ch:{}:2'.format(channel_position)]

        # Сбрасываем модуль
        rst_timeout = 10
        check_time = time.time()
        if self.unit_addrs_to_transceivers_map[unit_addr].write('rst {}'.format(unit_addr)):
            while time.time() - check_time < rst_timeout:
                if self.power_units_state_dicts[unit_addr]['st']['state1'] == '0' and \
                        self.power_units_state_dicts[unit_addr]['st']['state2'] == '0':
                    break
                else:
                    time.sleep(0.1)
            if self.power_units_state_dicts[unit_addr]['st']['state1'] != '0' or \
                    self.power_units_state_dicts[unit_addr]['st']['state2'] != '0':
                log_msg = 'Ошибка при измерении сопротивления изоляции силового модуля {}:' \
                          ' не удается осуществить сброс модуля'.format(unit_addr)
                self.logger.error(log_msg)
                self.power_units_maintenance[unit_addr] = False
                return
        else:
            log_msg = 'Не удалось выполнить измерение сопротивления изоляции силового модуля {}' \
                      ' из-за ошибки записи  в последовательный порт команды сброса'.format(unit_addr)
            self.logger.error(log_msg)
            self.power_units_maintenance[unit_addr] = False
            return

        # Блокируем управление каналом
        if ch_lock.acquire(timeout=3):
            # Отправляем команду
            isol_cmd = 'resist start {} {}'.format(channel_position, unit_addr)
            isol_timeout = 3
            check_time = time.time()

            if self.unit_addrs_to_transceivers_map[unit_addr].write(isol_cmd):
                # Ждем результата выполнения команды
                while time.time() - check_time < isol_timeout:
                    if self.power_units_state_dicts[unit_addr]['isol']['isol{}'.format(channel_position)]:
                        break
                    else:
                        time.sleep(0.1)
                ch_lock.release()
                if not self.power_units_state_dicts[unit_addr]['isol']['isol{}'.format(channel_position)]:
                    log_msg = 'Не удалось выполнить измерение сопротивления изоляции в {} канале силового модуля {}' \
                              ' нет ответа от ПО низкого уровня'.format(channel_position, unit_addr)
                    self.logger.error(log_msg)
            # Если не удалось отправить команду
            else:
                ch_lock.release()
                log_msg = 'Не удалось выполнить измерение сопротивления изоляции в {} канале силового модуля {}' \
                          ' из-за ошибки записи команды в последовательный порт'.format(channel_position, unit_addr)
                self.logger.error(log_msg)
        # Если не удалось заблокировать управление каналом
        else:
            log_msg = 'Не удалось выполнить измерение сопротивления изоляции в {} канале силового модуля {}:' \
                      ' управление каналом заблокировано в другом потоке'.format(channel_position, unit_addr)
            self.logger.error(log_msg)

        self.power_units_maintenance[unit_addr] = False

    def writer_target(self):
        """
        Обрабатывает команды от функционального модуля "Логика"

        При получении команды вызывает соответствующий метод для ее обработки.
        Поддерживаемые команды:

        #. Установка нового состояния выхода силового модуля:
            * канал Redis: ``axiomLogic:cmd:state``;
            * формат команды: ``{'addr': <channel_addr>, 'state': {'status': '4'|'5'}}``;
            * метод для обработки: :meth:`set_ch_state`.
        #. Измерение сопротивления изоляции канала силового модуля:
            * канал Redis: ``axiomLogic:request:insulation``;
            * формат команды: ``<channel_addr>``;
            * метод для обработки: :meth:`measure_insulation_resistance`.

        .. figure:: _static/writer_target.png
           :scale: 50%
           :align: center
        """
        # Подписываемся на команды изменения состояния от модуля "Логика"
        subscriber_state_cmd = self.redis.pubsub(ignore_subscribe_messages=True)
        subscriber_state_cmd.subscribe(INPUT_CMD_STATE_CHANNEL)

        # Подписываемся на команды измерения сопротивления изоляции
        subscriber_isol_cmd = self.redis.pubsub(ignore_subscribe_messages=True)
        subscriber_isol_cmd.subscribe(INPUT_REQUEST_INSULATION_CHANNEL)

        ch_template = r'^ch:(m[1-9]):([1-2])$'

        while self.isRunning:
            # <editor-fold desc="Обработка команд на изменение состояния выходов">
            message_state = subscriber_state_cmd.get_message()
            if message_state:
                try:
                    cmd_str = message_state['data']
                except KeyError:
                    log_msg = 'redis KeyError'
                    self.logger.debug(log_msg)
                    continue
                try:
                    cmd_dict = json.loads(cmd_str)
                except (TypeError, ValueError) as e:
                    log_msg = 'redis dict "{}" "{}"'.format(e, cmd_str)
                    self.logger.debug(log_msg)
                    continue

                try:
                    channel_addr = cmd_dict['addr']
                    new_state_dict = cmd_dict['state']
                except (KeyError, UnboundLocalError) as e:
                    self.logger.debug(log_msg)
                    continue

                if re.match(ch_template, channel_addr):
                    log_msg = 'redis rcv run thread'
                    self.logger.debug(log_msg)

                    threading.Thread(target=self.set_ch_state, kwargs={
                        'channel_addr': channel_addr, 'new_state_dict': new_state_dict}).start()
                else:
                    log_msg = 'redis not match'
                    self.logger.debug(log_msg)

            # </editor-fold>

            # <editor-fold desc="Обработка команд на измерение сопротивления изоляции">
            message_isol = subscriber_isol_cmd.get_message()
            if message_isol:
                self.logger.info(
                    'Получена команда на измерение сопротивления изоляции: {}'.format(message_isol['data']))
                channel_addr = message_isol['data']
                threading.Thread(target=self.measure_insulation_resistance, args=(channel_addr,)).start()
            time.sleep(0.01)
            # </editor-fold>

    def sigterm_handler(self, signum, frame):
        """
        Корректно останавливает программу при получении сигнала SIGTERM, SIGINT

        :param signum: signal number (не используется)
        :param frame:  current stack frame (не используется)
        """
        log_msg = 'Остановка программы'
        self.logger.info(log_msg)
        self.scheduler.shutdown()
        self.isRunning = False

    def publish_current_characteristics(self):
        """
        Публикует на брокер текущие значения энергетических характеристик аппаратных модулей

        Запускается как задача планировщика :attr:`scheduler`. Выполняется каждые 10 секунд. Отправляет
        следующие характеристики:

        * Напряжение электросети на модулях ввода;
        * Частота электросети на модулях ввода;
        * Активная потребляемая мощность в каналах силовых модулей;
        * Реактивная потребляемая мощность в каналах силовых модулей;
        * Ток, потребляемый в каналах силовых модулей;
        * Температура каналов силовых модулей.

        Канал Redis для отправки сообщений: ``axiomLowLevelCommunication:info:metrics_data``.
        """
        # for input_unit_addr in self.hardware_units:
        #
        #     # Считаем напряжение на модуле ввода
        #     voltage_sample = int(self.input_units_state_dicts[input_unit_addr]['adc']['sample'])
        #
        #     Um = abs(voltage_sample * (3/4096) - 1.5) * 253.557     # амплитудное значение напряжения
        #     U = Um * 0.707                                          # действующее значение напряжения
        #
        #     # Публикуем рассчитанное значение
        #     voltage_message = {'U': U, 'addr': input_unit_addr, 'timestamp': time.time()}
        #
        #     self.r.publish(channel='axiomLowLevelCommunication:info:voltage',
        #                    message=json.dumps(voltage_message))

        # for input_unit_addr in self.input_unit_addrs:
        #     U = self.input_units_state_dicts[input_unit_addr]['volt']['Vin']
        #     F = self.input_units_state_dicts[input_unit_addr]['volt']['freq']
        #     P_own = self.calc_system_own_power(input_unit_addr)
        #
        #     metrics_data = {'U': U, 'F': F, 'P_own': P_own, 'addr': input_unit_addr}
        #
        #     self.r.publish(channel='axiomLowLevelCommunication:info:metrics_data',
        #                    message=ujson.dumps(metrics_data))

        U = 220

        for power_unit_addr in self.power_unit_addrs:
            # Значения температур каналов силовых модулей
            T1 = int(self.power_units_state_dicts[power_unit_addr]['tmpr']['temp1'])
            T2 = int(self.power_units_state_dicts[power_unit_addr]['tmpr']['temp2'])

            # Действующее значение тока
            I1 = float(self.power_units_state_dicts[power_unit_addr]['adc']['sample1'])
            I2 = float(self.power_units_state_dicts[power_unit_addr]['adc']['sample2'])

            angle1 = int(self.power_units_state_dicts[power_unit_addr]['ld']['angle1'])
            angle2 = int(self.power_units_state_dicts[power_unit_addr]['ld']['angle2'])

            # # Амплитудное значение тока в первом и втором каналах
            # Im1 = (abs(1.5 - (3 * current_sample1 / 4096)) / 0.066)
            # Im2 = (abs(1.5 - (3 * current_sample2 / 4096)) / 0.066)
            #
            # # Действующее значение тока в первом и втором каналах
            # I1 = Im1 * 0.707
            # I2 = Im2 * 0.707

            # Фазовый сдвиг в первом и втором каналах
            phi1 = (angle1 * math.pi) / 80
            phi2 = (angle2 * math.pi) / 80

            # Активная мощность потребляемая мощность в первом и втором каналах
            Pa1 = U * I1 * math.cos(phi1)
            Pa2 = U * I2 * math.cos(phi2)
            # print('Мощность1: {}, Фи1: {}, Ток1: {}, Косинус1: {}'.format(Pa1, phi1, I1, math.cos(phi1)))
            # print('Мощность2: {}, Фи2: {}, Ток2: {}, Косинус2: {}'.format(Pa2, phi2, I2, math.cos(phi2)))
            # print()

            # Реактивная потребляемая мощность в первом и втором каналах
            Pr1 = U * I1 * math.sin(phi1)
            Pr2 = U * I2 * math.sin(phi2)

            # Полная потребляемая мощности в первом и втором каналах
            # P1 = U * I1
            # P2 = U * I2

            # Частота на модуле
            # F = int(self.power_units_state_dicts[power_unit_addr]['adc']['freq'])
            F = 0

            # Публикуем рассчитанные значения потребления и тока
            active_power_message = {'P1': Pa1, 'P2': Pa2, 'addr': power_unit_addr, 'timestamp': time.time()}

            reactive_power_message = {'P1': Pr1, 'P2': Pr2, 'addr': power_unit_addr, 'timestamp': time.time()}

            current_message = {'I1': I1, 'I2': I2, 'addr': power_unit_addr, 'timestamp': time.time()}

            frequency_message = {'F': F, 'addr': power_unit_addr, 'timestamp': time.time()}

            self.redis.publish(channel='axiomLowLevelCommunication:info:active_power',
                               message=json.dumps(active_power_message))

            self.redis.publish(channel='axiomLowLevelCommunication:info:reactive_power',
                               message=json.dumps(reactive_power_message))

            self.redis.publish(channel='axiomLowLevelCommunication:info:current',
                               message=json.dumps(current_message))

            self.redis.publish(channel='axiomLowLevelCommunication:info:frequency',
                               message=json.dumps(frequency_message))

            characteristics_dict = {'Pa1': Pa1, 'Pa2': Pa2, 'Pr1': Pr1, 'Pr2': Pr2, 'I1': I1, 'I2': I2,
                                    'T1': T1, 'T2': T2, 'U': U, 'F': F, 'addr': power_unit_addr}
            self.redis.publish(channel=OUTPUT_INFO_METRICS_CHANNEL,
                               message=ujson.dumps(characteristics_dict))

    def calc_passive_consumption(self):
        """
        Расчет пассивной потребляемой мощности схемы
        в режиме ожидания

        :deprecated:
        :return: пассивная потребляемая мощность
        """

        P_chassis = 3.3 * 0.033  # мощность, потребляемая пассивными элементами монтажа на шасси
        P_controller = 0.308  # мощность, потребляемая использованным микроконтроллером
        P_relay1 = 0.4  # мощность, потребляемая реле К1..К16 на шасси
        P_transformer = 0.35  # мощность, потребляемая трасформатором TV1
        P_relay_input = 0.31  # мощность, потребляемая реле ввода K17
        P_power_supply = 0.1  # мощность, потребляемая блоком питания шасси U1, U2
        P_transistor = 0.15  # мощность, потребляемая тразисторами VT1, VT2 в восьми розеточных автоматах
        P_automatic = 0  # мощность, потребляемая автоматом управления

        # Полная пассивная потребляемая мощность
        P_passive = P_chassis + 9 * P_controller + 16 * P_relay1 + P_transformer + P_relay_input + \
                    2 * P_power_supply + 16 * P_transistor + P_automatic

        return P_passive

    def calc_system_own_power(self, input_unit_addr):
        """
        Рассчитывает собственную (без учета потребителей) мощность
        расходуемую платой, на которой установлен модуль ввода

        Расчет производится по формуле
        :math:`P = U_{in} \cdot I_{in} + U_{in} \cdot I_{out} + U_{in} \cdot I_{ypr}`, где

        * :math:`U_{in}` - действующее значение напряжение сети [В];
        * :math:`I_{in}` - значение тока, потребляемого внутренними модулями модуля ввода [A];
        * :math:`I_{out}` - значение тока, потребляемого внешними модулями [A];
        * :math:`I_{ypr}` - значение тока, потребляемого автоматом управления [A].

        :type input_unit_addr: str
        :param input_unit_addr: адрес модуля ввода
        :rtype: float
        :return: рассчитанная мощность [Вт]
        """

        Vin = float(self.input_units_state_dicts[input_unit_addr]['volt']['Vin'])
        Iin = float(self.input_units_state_dicts[input_unit_addr]['cur']['Iin'])
        Iout = float(self.input_units_state_dicts[input_unit_addr]['cur']['Iout'])
        Iypr = float(self.input_units_state_dicts[input_unit_addr]['cur']['Iypr'])

        Pin = Vin * Iin
        Pout = Vin * Iout
        Pypr = Vin * Iypr

        return Pin + Pout + Pypr

    def run(self):
        """
        Запускает основной цикл работы функционального модуля.

        #. Запускает в потоке метод опроса аппаратных модулей :meth:`reader_target`;
        #. Запускает выполнение задач планировщика :attr:`scheduler`;
        #. Запускает в потоке метод обработки команд от модуля "Логика" :meth:`writer_target`.

        Контролирует рабочее состояние потоков опроса и обработки команд

        .. figure:: _static/run.png
           :align: center
        """
        self.logger.info('Программа запущена')

        self.isRunning = True
        # 1. Запуск потока опроса
        reader = threading.Thread(target=self.reader_target)
        reader.start()

        # 2. Запуск отправки данных о потреблении в каналах
        self.scheduler.start()

        # 3. Запуск потока посылки команд
        writer = threading.Thread(target=self.writer_target)
        writer.start()

        # 4. Контроль рабочего состояния опроса и посылки команд
        try:
            while self.isRunning:
                if not reader.is_alive():
                    reader = threading.Thread(target=self.reader_target)
                    reader.start()
                if not writer.is_alive():
                    writer = threading.Thread(target=self.writer_target())
                    writer.start()
                time.sleep(5)
        except KeyboardInterrupt:
            self.scheduler.shutdown()
            self.isRunning = False
        finally:
            for transceiver in self.unit_addrs_to_transceivers_map.values():
                transceiver.close()
            sys.exit(0)
