import math
import os
import sys
import threading
import time
from unittest import TestCase, skip
from unittest.mock import MagicMock, patch
import serial
from axiomLowLevelCommunication.serialTransceiver import SerialTransceiver
import builtins
import json
from apscheduler.schedulers.background import BackgroundScheduler


class HighLowTransceiverTestBase(TestCase):

    def setUp(self):
        # Подменяем open, чтобы при попытке считать настройки тесты
        # не пытались открывать несуществующие в тестовом окружении файлы
        # builtins.open = MagicMock()

        # словарь настроек, с которыми работают тесты
        self.test_axiom_settings = {
            'hardware units': {
                'm5': ['m1'],
                'm6': ['m2'],
                'm7': ['m3'],
                'm8': ['m4'],
            },
            'power units': {
                'm1': '/dev/ttyS0',
                'm2': '/dev/ttyS1',
                'm3': '/dev/ttyS2',
                'm4': '/dev/ttyS3',
            },
            'power units thresholds': {
                'm1': [1, 2],
                'm2': [3, 4],
                'm3': [5, 6],
                'm4': [7, 8],
            },
            'input units': {
                'm5': '/dev/ttyS4',
                'm6': '/dev/ttyS5',
                'm7': '/dev/ttyS6',
                'm8': '/dev/ttyS7',
            }
        }
        json.load = MagicMock(return_value=self.test_axiom_settings)

        from axiomLowLevelCommunication.highLowTransceiver import logger
        logger.write_log = MagicMock()
        self.logger = logger

        from axiomLowLevelCommunication.highLowTransceiver import redis
        redis.StrictRedis = MagicMock(spec=redis.StrictRedis)
        self.redis = redis

        from axiomLowLevelCommunication.highLowTransceiver import HighLowTransceiver
        self.HighLowTransceiver = HighLowTransceiver
        self.HighLowTransceiver.load_settings = MagicMock(return_value=self.test_axiom_settings)


class TestSettingsLoading(HighLowTransceiverTestBase):

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    @patch('os.environ.get', MagicMock(return_value='/file/from/environ/var'))
    def test_load_settings_function_read_environ_var_if_it_exists(self):
        """
        Тест проверяет, что если задана переменная окружения AXIOM_SETTINGS,
        функция HighLowTransceiver.load_settings загружает настройки из файла
        заданного в этой переменной
        """
        self.HighLowTransceiver()
        os.environ.get.assert_called_with('AXIOM_SETTINGS', default='/etc/axiom/settings_input_unit.json')
        builtins.open.assert_called_with('/file/from/environ/var')

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_load_settings_function_open_default_file_if_envvar_does_not_exist(self):
        """
        Тест проверяет, что если переменная окружения AXIOM_SETTINGS не задана,
        функция HighLowTransceiver.load_settings загружает настройки из файла
        /etc/axiom/settings_input_unit.json
        """
        self.HighLowTransceiver()
        builtins.open.assert_called_with('/etc/axiom/settings_input_unit.json')

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    @patch('os.environ.get', MagicMock(return_value='/file/from/environ/var'))
    def test_load_settings_function_open_default_file_if_file_set_in_envvar_can_not_be_opened(self):
        """
        Тест проверяет, что если файл заданный в переменной окружения AXIOM_SETTINGS,
        не удается открыть, функция HighLowTransceiver.load_settings загружает настройки
        из файла /etc/axiom/settings_input_unit.json
        """

        # Нет прав на открытие файла
        def open_side_effect(fname):
            if fname == '/file/from/environ/var':
                raise IOError

        builtins.open = MagicMock(side_effect=open_side_effect)
        threading.Thread(target=self.HighLowTransceiver).start()
        time.sleep(0.01)
        builtins.open.assert_called_with('/etc/axiom/settings_input_unit.json')

        # Файл не найден
        def open_side_effect(fname):
            if fname == '/file/from/environ/var':
                raise FileNotFoundError

        builtins.open = MagicMock(side_effect=open_side_effect)
        threading.Thread(target=self.HighLowTransceiver).start()
        time.sleep(0.01)
        builtins.open.assert_called_with('/etc/axiom/settings_input_unit.json')

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    @patch('os.environ.get', MagicMock(return_value='/file/from/environ/var'))
    def test_load_settings_function_log_error_if_file_can_not_be_opened(self):
        """
        Тест проверяет, что если файл с настройками не удается открыть,
        функция HighLowTransceiver.load_settings логирует ошибку
        """

        # Нет прав на открытие файла
        builtins.open.side_effect = IOError('some error')

        threading.Thread(target=self.HighLowTransceiver).start()
        time.sleep(0.01)

        self.logger.write_log.assert_any_call(log_level='ERROR',
                                              log_msg='Ошибка при попытке открыть файл настроек: some error')
        self.logger.write_log.assert_any_call(log_level='ERROR',
                                              log_msg='Ошибка при попытке открыть файл настроек по умолчанию: some '
                                                      'error')

        # Файл не найден
        builtins.open.side_effect = FileNotFoundError('some error')

        threading.Thread(target=self.HighLowTransceiver).start()
        time.sleep(0.01)

        self.logger.write_log.assert_any_call(log_level='ERROR',
                                              log_msg='Ошибка при попытке открыть файл настроек: some error')
        self.logger.write_log.assert_any_call(log_level='ERROR',
                                              log_msg='Ошибка при попытке открыть файл настроек по умолчанию: some '
                                                      'error')

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    @patch('os.environ.get', MagicMock(return_value='/file/from/environ/var'))
    def test_load_settings_function_log_error_if_settings_can_not_be_loaded_from_file(self):
        """
        Тест проверяет, что если не удается загрузить настройки из открытого файла,
        функция HighLowTransceiver.load_settings логирует ошибку
        """

        json.load = MagicMock(side_effect=TypeError('some error'))

        threading.Thread(target=self.HighLowTransceiver).start()
        time.sleep(0.01)

        self.logger.write_log.assert_any_call(log_level='ERROR',
                                              log_msg='Ошибка при попытке загрузить настройки из файла настроек: some '
                                                      'error')
        self.logger.write_log.assert_any_call(log_level='ERROR',
                                              log_msg="Ошибка при попытке загрузить настройки из файла настроек по "
                                                      "умолчанию: some error")

        json.load = MagicMock(side_effect=ValueError('some error'))

        threading.Thread(target=self.HighLowTransceiver).start()
        time.sleep(0.01)

        self.logger.write_log.assert_any_call(log_level='ERROR',
                                              log_msg='Ошибка при попытке загрузить настройки из файла настроек: some '
                                                      'error')
        self.logger.write_log.assert_any_call(log_level='ERROR',
                                              log_msg='Ошибка при попытке загрузить настройки из файла настроек по '
                                                      'умолчанию: some error')


class TestTransceiverInitialization(HighLowTransceiverTestBase):

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_HighLowTransceiver_connects_to_com_for_every_power_unit(self):
        """
        Тест проверяет, что при создании объекта HighLowTransceiver
        происходит создание объектов SerialTransceiver для каждого
        силового модуля
        """

        hlTransceiver = self.HighLowTransceiver()
        for unit, port in self.test_axiom_settings['power units'].items():
            self.assertEqual(hlTransceiver.unit_addrs_to_transceivers_map[unit].port, port)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_HighLowTransceiver_connects_to_com_for_every_input_unit(self):
        """
        Тест проверяет, что при создании объекта HighLowTransceiver
        происходит создание объектов SerialTransceiver для каждого
        модуля ввода
        """

        hlTransceiver = self.HighLowTransceiver()
        for unit, port in self.test_axiom_settings['input units'].items():
            self.assertEqual(hlTransceiver.unit_addrs_to_transceivers_map[unit].port, port)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_valid_state_structure_is_created_for_every_power_unit(self):
        """
        Тест проверяет, что при создании объекта HighLowTransceiver
        происходит создание структуры для хранения состояния
        каждого силового модуля
        """
        hlTransceiver = self.HighLowTransceiver()
        for unit in self.test_axiom_settings['power units']:
            correct_state_struct = {
                'link': False,
                'st': {'state1': None, 'state2': None, 'signal1': None, 'signal2': None, 'addr': '{}'.format(unit),
                       'cnt': None},
                'adc': {'sample1': None, 'sample2': None, 'addr': '{}'.format(unit), 'cnt': None},
                'ld': {'load1': None, 'load2': None, 'angle1': None, 'angle2': None, 'addr': '{}'.format(unit),
                       'cnt': None},
            }
            self.assertEqual(hlTransceiver.power_units_state_dicts[unit], correct_state_struct)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_valid_state_structure_is_created_for_every_input_unit(self):
        """
        Тест проверяет, что при создании объекта HighLowTransceiver
        происходит создание структуры для хранения состояния
        каждого модуля ввода
        """
        hlTransceiver = self.HighLowTransceiver()
        for unit in self.test_axiom_settings['input units']:
            correct_state_struct = {
                'st': {'state': None, 'signal': None, 'addr': '{}'.format(unit), 'cnt': None},
                'adc': {'sample': None, 'addr': '{}'.format(unit), 'cnt': None},
            }
            self.assertEqual(hlTransceiver.input_units_state_dicts[unit], correct_state_struct)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_lock_object_is_created_for_every_ch(self):
        """
        Тест проверяет, что при создании объекта HighLowTransceiver
        происходит создание блокировщика (threading.Lock) для
        каждого выхода каждого силового модуля
        """
        hlTransceiver = self.HighLowTransceiver()

        ch_addrs = []

        for unit in self.test_axiom_settings['power units']:
            for output in ['1', '2']:
                ch_addrs.append('ch:{}:{}'.format(unit, output))


        # Вычислим объект какого класса создает threading.Lock() на данной платформе
        lock_class = threading.Lock().__class__

        # Проверим, что для каждого выхода создан объект типа threading.Lock
        for ch_addr in ch_addrs:
            self.assertTrue(isinstance(hlTransceiver.ch_locks[ch_addr], lock_class))

        # Проверим, что все блокировщики уникальны
        self.assertTrue(len(set(hlTransceiver.ch_locks.values())) == len(hlTransceiver.ch_locks.values()))

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_lock_object_is_created_for_every_serial_transceiver(self):
        """
        Тест проверяет, что при создании объекта HighLowTransceiver
        происходит создание блокировщика (threading.Lock) для
        каждого последовательного порта
        """
        hlTransceiver = self.HighLowTransceiver()

        # Вычислим объект какого класса создает threading.Lock() на данной платформе
        lock_class = threading.Lock().__class__

        # Проверим, что для каждого силового модуля создан объект типа threading.Lock
        # для блокировки работы с последовательным портом данного модуля
        for unit_addr in hlTransceiver.power_unit_addrs:
            self.assertTrue(isinstance(hlTransceiver.com_locks[unit_addr], lock_class))

        # Проверим, что все блокировщики уникальны
        self.assertTrue(len(set(hlTransceiver.com_locks.values())) == len(hlTransceiver.com_locks.values()))


class TestStateCollection(HighLowTransceiverTestBase):

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_collect_function_update_unit_state_structure_for_st_cmd(self):
        """
        Тест проверяет, что корректно обновляется поле 'st' структуры состояния модуля
        при чтении данных из последовательного порта
        """
        hlTransceiver = self.HighLowTransceiver()

        # Для каждого трансивера добавляем возвращамое значение для функции read,
        # соответствующее адресу модуля, которому он соответствует
        for unit in self.test_axiom_settings['power units']:
            hlTransceiver.unit_addrs_to_transceivers_map[unit].read = MagicMock(
                return_value='st 1 2 3 4 5491{}'.format(unit).encode())

        hlTransceiver.collect_units_state()

        for unit in self.test_axiom_settings['power units']:
            self.assertTrue(hlTransceiver.power_units_state_dicts[unit]['link'])
            self.assertEqual(hlTransceiver.power_units_state_dicts[unit]['st'], {'state1': '1',
                                                                                 'state2': '2',
                                                                                 'signal1': '3',
                                                                                 'signal2': '4',
                                                                                 'addr': '{}'.format(unit),
                                                                                 'cnt': '5491'})

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_collect_function_publishes_new_state_if_it_changes(self):
        """
        Тест проверяет, функция HighLowTransceiver.collect_units_state
        публикует на брокер новое состояние, если оно изменилось
        """
        hlTransceiver = self.HighLowTransceiver()
        hlTransceiver.redis.get = MagicMock(return_value=str({'status': '0'}))
        # Для каждого трансивера добавляем возвращамое значение для функции read,
        # соответствующее адресу модуля, которому он соответствует
        for unit in self.test_axiom_settings['power units']:
            hlTransceiver.unit_addrs_to_transceivers_map[unit].read = MagicMock(
                return_value='st 1 2 3 4 5491{}'.format(unit).encode())

        hlTransceiver.collect_units_state()

        for unit_addr in self.test_axiom_settings['power units']:
            hlTransceiver.redis.publish.assert_any_call(channel='axiomLowLevelCommunication:info:state',
                                                        message={'addr': 'ch:{}:1'.format(unit_addr),
                                                             'state': {'status': '1'}})
            hlTransceiver.redis.publish.assert_any_call(channel='axiomLowLevelCommunication:info:state',
                                                        message={'addr': 'ch:{}:2'.format(unit_addr),
                                                             'state': {'status': '2'}})

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_collect_function_saves_new_state_if_it_changes(self):
        """
        Тест проверяет, функция HighLowTransceiver.collect_units_state
        сохраняет в redis новое состоние выхода, если оно изменилось
        """
        hlTransceiver = self.HighLowTransceiver()
        hlTransceiver.redis.get = MagicMock(return_value=str({'status': '0'}))
        # Для каждого трансивера добавляем возвращамое значение для функции read,
        # соответствующее адресу модуля, которому он соответствует
        for unit in self.test_axiom_settings['power units']:
            hlTransceiver.unit_addrs_to_transceivers_map[unit].read = MagicMock(
                return_value='st 1 2 3 4 5491{}'.format(unit).encode())

        hlTransceiver.collect_units_state()

        for unit_addr in self.test_axiom_settings['power units']:
            hlTransceiver.redis.set.assert_any_call(name='ch:{}:1'.format(unit_addr), value={'status': '1'})
            hlTransceiver.redis.set.assert_any_call(name='ch:{}:2'.format(unit_addr), value={'status': '2'})

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_collect_function_logs_new_state_if_it_changes(self):
        """
        Тест проверяет, функция HighLowTransceiver.collect_units_state
        сохраняет в redis новое состоние выхода, если оно изменилось
        """
        hlTransceiver = self.HighLowTransceiver()
        hlTransceiver.redis.get = MagicMock(return_value=str({'status': '0'}))

        for unit_addr in self.test_axiom_settings['power units']:
            hlTransceiver.power_units_state_dicts[unit_addr]['st']['signal1'] = '0'
            hlTransceiver.power_units_state_dicts[unit_addr]['st']['signal2'] = '0'

        # Для каждого трансивера добавляем возвращамое значение для функции read,
        # соответствующее адресу модуля, которому он соответствует
        for unit in self.test_axiom_settings['power units']:
            hlTransceiver.unit_addrs_to_transceivers_map[unit].read = MagicMock(
                return_value='st 1 1 1 1 5491{}'.format(unit).encode())

        hlTransceiver.collect_units_state()

        for unit_addr in self.test_axiom_settings['power units']:
            for i in ('1', '2'):
                humanreadable_state = hlTransceiver.humanreadable_states['1']
                humanreadable_signal = hlTransceiver.humanreadable_signals['1']
                log_msg = 'Выход "{}" модуля "{}" перешел в состояние "{}". Сигнал перехода: "{}"'.format(
                    'ch:{}:{}'.format(unit_addr, i), unit_addr, humanreadable_state, humanreadable_signal
                )
                self.logger.write_log.assert_any_call(log_msg=log_msg, log_level='INFO')

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_collect_function_update_unit_state_structure_for_adc_cmd(self):
        """
        Тест проверяет, что корректно обновляется поле 'adc' структуры состояния модуля
        при чтении данных из последовательного порта
        """
        hlTransceiver = self.HighLowTransceiver()

        # Для каждого трансивера добавляем возвращамое значение для функции read,
        # соответствующее адресу модуля, которому он соответствует
        for unit in self.test_axiom_settings['power units']:
            hlTransceiver.unit_addrs_to_transceivers_map[unit].read = MagicMock(
                return_value='adc 2048 2048 5489{}'.format(unit).encode())

        hlTransceiver.collect_units_state()

        for unit in self.test_axiom_settings['power units']:
            self.assertTrue(hlTransceiver.power_units_state_dicts[unit]['link'])
            self.assertEqual(hlTransceiver.power_units_state_dicts[unit]['adc'], {'sample1': '2048',
                                                                                  'sample2': '2048',
                                                                                  'addr': '{}'.format(unit),
                                                                                  'cnt': '5489'})

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_collect_function_update_unit_state_structure_for_ld_cmd(self):
        """
        Тест проверяет, что корректно обновляется поле 'ld' структуры состояния модуля
        при чтении данных из последовательного порта
        """
        hlTransceiver = self.HighLowTransceiver()

        # Для каждого трансивера добавляем возвращамое значение для функции read,
        # соответствующее адресу модуля, которому он соответствует
        for unit in self.test_axiom_settings['power units']:
            hlTransceiver.unit_addrs_to_transceivers_map[unit].read = MagicMock(
                return_value='ld 12 13 14 15 5492{}'.format(unit).encode())

        hlTransceiver.collect_units_state()

        for unit in self.test_axiom_settings['power units']:
            self.assertTrue(hlTransceiver.power_units_state_dicts[unit]['link'])
            self.assertEqual(hlTransceiver.power_units_state_dicts[unit]['ld'], {'load1': '12',
                                                                                 'load2': '13',
                                                                                 'angle1': '14',
                                                                                 'angle2': '15',
                                                                                 'addr': '{}'.format(unit),
                                                                                 'cnt': '5492'})

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_collect_function_set_link_to_False_if_there_is_no_data(self):
        """
        Тест проверяет, что для поля 'link' структуры состояния модуля
        устанавливается значение False в случае отсутствия данных в последовательном порте
        """
        hlTransceiver = self.HighLowTransceiver()

        for unit in self.test_axiom_settings['power units']:
            hlTransceiver.power_units_state_dicts[unit]['link'] = True
            hlTransceiver.unit_addrs_to_transceivers_map[unit].read = MagicMock(return_value=''.encode())

        hlTransceiver.collect_units_state()

        for unit in self.test_axiom_settings['power units']:
            self.assertFalse(hlTransceiver.power_units_state_dicts[unit]['link'])

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_collect_function_does_nothing_for_invalid_cmd_type(self):
        """
        Тест проверяет, что функция HighLowTransceiver.collect_units_state
        не изменяет структуру состояния модуля в случае получения
        некорректного значения типа команды
        """
        hlTransceiver = self.HighLowTransceiver()
        state_before_collect_call = hlTransceiver.power_units_state_dicts

        # Для каждого трансивера добавляем возвращамое значение для функции read,
        # соответствующее адресу модуля, которому он соответствует
        for unit in self.test_axiom_settings['power units']:
            hlTransceiver.unit_addrs_to_transceivers_map[unit].read = MagicMock(
                return_value='invalid 12 13 14 15 5492{}'.format(unit).encode())

        hlTransceiver.collect_units_state()

        self.assertEqual(state_before_collect_call, hlTransceiver.power_units_state_dicts)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_collect_units_state_does_not_crash_on_invalid_read_data(self):
        """
        Тест проверяет, что функция HighLowTransceiver.collect_units_state
        не изменяет структуру состояния модуля и не создает исключений в случае получения
        некорректных данных из последовательного порта
        """
        hlTransceiver = self.HighLowTransceiver()
        state_before_collect_call = hlTransceiver.power_units_state_dicts

        # Для каждого трансивера добавляем возвращамое значение для функции read,
        # соответствующее адресу модуля, которому он соответствует
        for unit in self.test_axiom_settings['power units']:
            hlTransceiver.unit_addrs_to_transceivers_map[unit].read = MagicMock(
                return_value='somerandomdata'.encode())

        hlTransceiver.collect_units_state()

        self.assertEqual(state_before_collect_call, hlTransceiver.power_units_state_dicts)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_collect_units_state_does_not_crash_on_invalid_arguments(self):
        """
        Тест проверяет, что функция HighLowTransceiver.collect_units_state
        не изменяет структуру состояния модуля и не создает исключений в случае получения
        некорректного списка аргументов для какой-либо структуры
        """
        hlTransceiver = self.HighLowTransceiver()
        state_before_collect_call = hlTransceiver.power_units_state_dicts

        # Для каждого трансивера добавляем возвращамое значение для функции read,
        # соответствующее адресу модуля, которому он соответствует
        for unit in self.test_axiom_settings['power units']:
            hlTransceiver.unit_addrs_to_transceivers_map[unit].read = MagicMock(
                return_value='st some random arguments 123{}'.format(unit).encode())

        hlTransceiver.collect_units_state()

        self.assertEqual(state_before_collect_call, hlTransceiver.power_units_state_dicts)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_check_counter_calls_init_power_unit_on_appearance(self):
        """
        Тест проверяет, что в случае, когда значение счетчика None,
        а от силового модуля начинают поступать сообщения, функция check_counter
        вызывает функцию инициализации HighLowTransceiver.init_power_unit
        """
        self.HighLowTransceiver.load_settings = MagicMock(return_value=self.test_axiom_settings)
        hlTransceiver = self.HighLowTransceiver()

        hlTransceiver.init_power_unit = MagicMock()

        for unit_addr in self.test_axiom_settings['power units']:
            type_cmd = 'st'
            hlTransceiver.check_power_unit_counter('0', unit_addr, type_cmd)
            hlTransceiver.init_power_unit.assert_called_once_with(unit_addr)
            hlTransceiver.init_power_unit.reset_mock()

            type_cmd = 'adc'
            hlTransceiver.check_power_unit_counter('0', unit_addr, type_cmd)

            type_cmd = 'ld'
            hlTransceiver.check_power_unit_counter('0', unit_addr, type_cmd)

            hlTransceiver.init_power_unit.assert_not_called()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_check_counter_calls_init_power_unit_on_wrong_counter(self):
        """
        Тест проверяет, что в случае когда значение счетчика посылок 0, а предыдущее
        сохраненное в структуре состояние значение не равно 2^32 - 1,
        функция check_counter вызывает функцию инициализации модуля
        """
        self.HighLowTransceiver.load_settings = MagicMock(return_value=self.test_axiom_settings)
        hlTransceiver = self.HighLowTransceiver()

        hlTransceiver.init_power_unit = MagicMock()

        for unit_addr in self.test_axiom_settings['power units']:

            # Устанавливаем значение счетчика отличное от 2^32 - 1
            hlTransceiver.power_units_state_dicts[unit_addr]['st']['cnt'] = '1'
            hlTransceiver.power_units_state_dicts[unit_addr]['adc']['cnt'] = '1'
            hlTransceiver.power_units_state_dicts[unit_addr]['ld']['cnt'] = '1'

            type_cmd = 'st'
            hlTransceiver.check_power_unit_counter('0', unit_addr, type_cmd)
            hlTransceiver.init_power_unit.assert_called_once_with(unit_addr)
            hlTransceiver.init_power_unit.reset_mock()

            type_cmd = 'adc'
            hlTransceiver.check_power_unit_counter('0', unit_addr, type_cmd)

            type_cmd = 'ld'
            hlTransceiver.check_power_unit_counter('0', unit_addr, type_cmd)

            hlTransceiver.init_power_unit.assert_not_called()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_check_counter_doesnt_call_init_power_unit_on_correct_counter(self):
        """
        Тест проверяет, что в случае значение счетчика посылок 0, а предыдущее
        сохраненное в структуре состояние значение равно 2^32 - 1,
        функция check_counter не вызывает функцию инициализации модуля
        """
        self.HighLowTransceiver.load_settings = MagicMock(return_value=self.test_axiom_settings)
        hlTransceiver = self.HighLowTransceiver()

        hlTransceiver.init_power_unit = MagicMock()

        for unit_addr in self.test_axiom_settings['power units']:

            # Устанавливаем значение счетчика отличное от 2^32 - 1
            hlTransceiver.power_units_state_dicts[unit_addr]['st']['cnt'] = str(2**32 - 1)
            hlTransceiver.power_units_state_dicts[unit_addr]['adc']['cnt'] = str(2**32 - 1)
            hlTransceiver.power_units_state_dicts[unit_addr]['ld']['cnt'] = str(2**32 - 1)

            type_cmd = 'st'
            hlTransceiver.check_power_unit_counter('0', unit_addr, type_cmd)

            type_cmd = 'adc'
            hlTransceiver.check_power_unit_counter('0', unit_addr, type_cmd)

            type_cmd = 'ld'
            hlTransceiver.check_power_unit_counter('0', unit_addr, type_cmd)

            hlTransceiver.init_power_unit.assert_not_called()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_check_counter_log_on_appearance(self):
        """
        Тест проверяет, что в случае, когда значение счетчика None,
        а от силового модуля начинают поступать сообщения, функция check_counter
        записывает это событие в лог
        """
        self.HighLowTransceiver.load_settings = MagicMock(return_value=self.test_axiom_settings)
        hlTransceiver = self.HighLowTransceiver()

        hlTransceiver.init_power_unit = MagicMock()

        for unit_addr in self.test_axiom_settings['power units']:
            type_cmd = 'st'
            hlTransceiver.check_power_unit_counter('0', unit_addr, type_cmd)

            log_msg = 'Модуль {} впервые зафиксирован с системе'.format(unit_addr)
            self.logger.write_log.assert_called_once_with(log_msg=log_msg, log_level='INFO')
            self.logger.write_log.reset_mock()

            type_cmd = 'adc'
            hlTransceiver.check_power_unit_counter('0', unit_addr, type_cmd)

            type_cmd = 'ld'
            hlTransceiver.check_power_unit_counter('0', unit_addr, type_cmd)

            self.logger.write_log.assert_not_called()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_check_counter_log_on_power_unit_reboot(self):
        """
        Тест проверяет, что в случае значение счетчика посылок 0, а предыдущее
        сохраненное в структуре состояние значение равно 2^32 - 1, функция check_counter
        пишет в лог сообщение об ошибке
        """
        self.HighLowTransceiver.load_settings = MagicMock(return_value=self.test_axiom_settings)
        hlTransceiver = self.HighLowTransceiver()

        hlTransceiver.init_power_unit = MagicMock()

        for unit_addr in self.test_axiom_settings['power units']:
            # Устанавливаем значение счетчика отличное от 2^32 - 1
            hlTransceiver.power_units_state_dicts[unit_addr]['st']['cnt'] = '1000'
            hlTransceiver.power_units_state_dicts[unit_addr]['adc']['cnt'] = '1000'
            hlTransceiver.power_units_state_dicts[unit_addr]['ld']['cnt'] = '1000'

            type_cmd = 'st'
            hlTransceiver.check_power_unit_counter('0', unit_addr, type_cmd)

            log_msg = 'От модуля {} получена посылка со значением счетчика 0. Текущее значение счетчика 1000.' \
                      ' ПО модуля перезагружалось'.format(unit_addr)
            self.logger.write_log.assert_any_call(log_msg=log_msg, log_level='ERROR')
            self.logger.write_log.reset_mock()

            type_cmd = 'adc'
            hlTransceiver.check_power_unit_counter('0', unit_addr, type_cmd)

            type_cmd = 'ld'
            hlTransceiver.check_power_unit_counter('0', unit_addr, type_cmd)

            self.logger.write_log.assert_not_called()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_collect_function_calls_check_counter(self):
        """
        Тест проверяет, что корректно обновляется поле 'st' структуры состояния модуля
        при чтении данных из последовательного порта
        """
        self.HighLowTransceiver.load_settings = MagicMock(return_value=self.test_axiom_settings)
        hlTransceiver = self.HighLowTransceiver()

        hlTransceiver.check_power_unit_counter = MagicMock()
        hlTransceiver.run_power_unit = MagicMock(return_value=True)
        hlTransceiver.configure_power_unit = MagicMock(return_value=True)

        # Для каждого трансивера добавляем возвращамое значение для функции read,
        # соответствующее адресу модуля, которому он соответствует
        for unit in self.test_axiom_settings['power units']:
            hlTransceiver.unit_addrs_to_transceivers_map[unit].read = MagicMock(
                return_value='st 1 2 3 4 5491{}'.format(unit).encode())

        hlTransceiver.collect_units_state()

        for unit in self.test_axiom_settings['power units']:
            hlTransceiver.check_power_unit_counter.assert_any_call('5491', unit, 'st')


class TestReaderAndWriterThreads(HighLowTransceiverTestBase):

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_reader_target_constantly_calls_collect_unit_state(self):
        """
        Тест проверяет, что функция  HighLowTransceiver.reader_target
        постоянно вызывает функцию HighLowTransceiver.collect_units_state,
        пока установлен флаг HighLowTransceiver.isRunning = True
        """
        hlTransceiver = self.HighLowTransceiver()

        # после 10 вызовов поток опроса нужно остановить
        num_of_calls = 10

        def collect_units_state_side_effect_func():
            nonlocal num_of_calls
            if num_of_calls == 1:
                hlTransceiver.isRunning = False
            num_of_calls -= 1

        hlTransceiver.collect_units_state = MagicMock(side_effect=collect_units_state_side_effect_func)
        hlTransceiver.isRunning = True
        reader = threading.Thread(target=hlTransceiver.reader_target())
        reader.start()
        self.assertEqual(hlTransceiver.collect_units_state.call_count, 10)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    @patch('axiomLowLevelCommunication.highToLowTransceiver.SerialTransceiver', MagicMock(spec=SerialTransceiver))
    def test_reader_and_writer_stop_when_isRunning_is_False(self):
        """
        Тест проверяет, потоки reader и writer останавливаются,
        когда HighLowTransceiver.isRunning = False
        """
        # TODO добавить проверку потока writer
        hlTransceiver = self.HighLowTransceiver()
        hlTransceiver.collect_units_state = MagicMock()
        t = threading.Thread(target=hlTransceiver.run).start()
        time.sleep(0.01)
        try:
            # проверяем, что функция сбора состояния вызывалась
            hlTransceiver.collect_units_state.assert_called()
            # останавливаем потоки
            hlTransceiver.isRunning = False
            # сбрасываем mock и проверяем, что функция
            # сбора состояния перестала вызываться
            hlTransceiver.collect_units_state.reset_mock()
            time.sleep(0.1)
            hlTransceiver.collect_units_state.assert_not_called()
        except AssertionError:
            raise
        finally:
            hlTransceiver.isRunning = False

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_reader_restart_after_crashing(self):
        """
        Тест проверяет, поток reader запускается снова после падения
        """

        hlTransceiver = self.HighLowTransceiver()
        hlTransceiver.collect_units_state = MagicMock(side_effect=lambda: sys.exit(0))
        hlTransceiver.init_power_unit = MagicMock(return_value=True)

        threading.Thread(target=hlTransceiver.run).start()
        time.sleep(0.5)
        try:
            hlTransceiver.collect_units_state.reset_mock()
            time.sleep(6)
            hlTransceiver.collect_units_state.assert_called()
        except AssertionError:
            raise
        finally:
            hlTransceiver.isRunning = False

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_writer_restart_after_crashing(self):
        """
        Тест проверяет, поток отправки команд запускается снова после падения
        """

        hlTransceiver = self.HighLowTransceiver()
        subscriber = self.redis.StrictRedis().pubsub()
        self.redis.StrictRedis().pubsub().get_message.side_effect = lambda: sys.exit(0)

        hlTransceiver.init_power_unit = MagicMock(return_value=True)
        threading.Thread(target=hlTransceiver.run).start()
        try:
            subscriber.get_message.reset_mock()
            time.sleep(6)
            subscriber.get_message.assert_called()
        except AssertionError:
            raise
        finally:
            hlTransceiver.isRunning = False

    @patch('time.sleep', MagicMock(side_effect=KeyboardInterrupt))
    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_run_start_reader_thread_and_stop_on_KeyboardInterrupt(self):
        """
        Тест проверяет, что функция  HighLowTransceiver.run запускает
        в потоке функцию HighLowTransceiver.reader_target,
        которая работает до появления исключения KeyboardInterrupt
        """
        hlTransceiver = self.HighLowTransceiver()
        hlTransceiver.collect_units_state = MagicMock()
        try:
            threading.Thread(target=hlTransceiver.run).start()
        except KeyboardInterrupt:
            try:
                hlTransceiver.collect_units_state.assert_called()
                self.assertFalse(hlTransceiver.isRunning)
            except AttributeError:
                raise
            finally:
                hlTransceiver.isRunning = False
        finally:
            hlTransceiver.isRunning = False


class TestHandleSetPowerUnitStateExit(HighLowTransceiverTestBase):
    """
    Тесты проверки функции HighLowTransceiver.before_return_from_set_ch_state
    """

    # <editor-fold desc="Функциональность удалена. Новое состояние силового выхода публикуется функцией collect_units_state при его изменении">
    @skip
    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_before_return_from_set_ch_state_publish_current_state(self):
        """
        Тест проверяет, что функция  HighLowTransceiver.before_return_from_set_ch_state
        публикует на брокер текущее состояние силового выхода
        """
        channel_addr = 'ch:m1:1'
        current_state = '0'
        redis_msg = ''
        log_msg = ''

        hlTransceiver = self.HighLowTransceiver()

        hlTransceiver.before_return_from_set_ch_state(channel_addr, current_state, redis_msg, log_msg)

        hlTransceiver.redis.publish.assert_any_call(
            channel='axiomLowLevelCommunication:info:state',
            message={'addr': channel_addr, 'state': {'status': current_state}})
    # </editor-fold>

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_before_return_from_set_ch_state_publish_error(self):
        """
        Тест проверяет, что функция  HighLowTransceiver.before_return_from_set_ch_state
        публикует на брокер сообщение об ошибке
        """
        channel_addr = ''
        current_state = ''
        redis_msg = 'redis error message'
        log_msg = ''

        hlTransceiver = self.HighLowTransceiver()

        hlTransceiver.before_return_from_set_ch_state(channel_addr, current_state, log_msg, redis_msg)

        hlTransceiver.redis.publish.assert_any_call(
            channel='axiomLowLevelCommunication:info:error', message=redis_msg)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_before_return_from_set_ch_state_log_info(self):
        """
        Тест проверяет, что функция  HighLowTransceiver.before_return_from_set_ch_state
        пишет в лог сообщение об ошибке
        """
        channel_addr = ''
        current_state = ''
        redis_msg = ''
        log_msg = 'log message'

        hlTransceiver = self.HighLowTransceiver()

        hlTransceiver.before_return_from_set_ch_state(log_msg, channel_addr, current_state, redis_msg)

        self.logger.write_log.assert_called_once_with(log_msg=log_msg, log_level='INFO')

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_before_return_from_set_ch_state_log_error(self):
        """
        Тест проверяет, что функция  HighLowTransceiver.before_return_from_set_ch_state
        пишет в лог сообщение об ошибке
        """
        channel_addr = ''
        current_state = ''
        redis_msg = 'redis error message'
        log_msg = 'log message'

        hlTransceiver = self.HighLowTransceiver()

        hlTransceiver.before_return_from_set_ch_state(log_msg, channel_addr, current_state, redis_msg)

        self.logger.write_log.assert_called_once_with(log_msg=log_msg, log_level='ERROR')

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_before_return_from_set_ch_state_save_state(self):
        """
        Тест проверяет, что функция  HighLowTransceiver.before_return_from_set_ch_state
        сохраняет в redis текущее состояние канала
        """
        channel_addr = 'channel addr'
        current_state = 'current state'
        redis_msg = 'redis error message'
        log_msg = 'log message'

        hlTransceiver = self.HighLowTransceiver()

        hlTransceiver.before_return_from_set_ch_state(channel_addr, current_state, log_msg, redis_msg)


class TestSetPowerUnitState(HighLowTransceiverTestBase):
    """
    Тесты функции установки состояния силового выхода
    HighLowTransceiver.set_ch_state
    """

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_set_ch_state_function_rejects_invalid_cmd(self):
        """
        Тест проверяет, что функция  HighLowTransceiver.set_ch_state
        отбрасывает некорректные команды (возвращает False)
        """
        hlTransceiver = self.HighLowTransceiver()
        # Неверный адрес модуля и номер канала
        self.assertEqual(hlTransceiver.set_ch_state(channel_addr='ch:m0:3', new_state_dict={'status': '5'}), False)
        # Неверный номер канала
        self.assertEqual(hlTransceiver.set_ch_state(channel_addr='ch:m1:3', new_state_dict={'status': '5'}), False)
        # Неверный адрес модуля
        self.assertEqual(hlTransceiver.set_ch_state(channel_addr='ch:m5:1', new_state_dict={'status': '5'}), False)
        # Некорректный адрес канала
        self.assertEqual(hlTransceiver.set_ch_state(channel_addr='::', new_state_dict={'status': '5'}), False)
        self.assertEqual(hlTransceiver.set_ch_state(channel_addr='some random string', new_state_dict={'status': '5'}), False)
        self.assertEqual(hlTransceiver.set_ch_state(channel_addr=123, new_state_dict={'status': '5'}), False)
        # Новое состояние вне допустимого диапазона значений ('4', '5')
        self.assertEqual(hlTransceiver.set_ch_state(channel_addr='ch:m1:1', new_state_dict={'status': '3'}), False)
        # Некоректное новое состояние
        self.assertEqual(hlTransceiver.set_ch_state(channel_addr='ch:m1:1', new_state_dict={}), False)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_set_ch_state_function_logs_error_when_gets_invalid_cmd(self):
        """
        Тест проверяет, что функция  HighLowTransceiver.set_ch_state
        логирует ошибку, если полученная команда не проходит валидацию
        """
        hlTransceiver = self.HighLowTransceiver()

        # Неверный адрес модуля и номер канала
        channel_addr = 'ch:m0:3'
        new_state_dict = {'status': '5'}
        hlTransceiver.set_ch_state(channel_addr=channel_addr, new_state_dict=new_state_dict)
        invalid_cmd_log_msg = 'Получены некорректные данные для установки нового состояния силового выхода:' \
                              ' адрес канала: {}, новое состояние: {}'.format(channel_addr, new_state_dict)
        self.logger.write_log.assert_called_once_with(log_msg=invalid_cmd_log_msg, log_level='ERROR')
        self.logger.write_log.reset_mock()

        # Неверный номер канала
        channel_addr = 'ch:m1:3'
        new_state_dict = {'status': '5'}
        hlTransceiver.set_ch_state(channel_addr=channel_addr, new_state_dict=new_state_dict)
        invalid_cmd_log_msg = 'Получены некорректные данные для установки нового состояния силового выхода:' \
                              ' адрес канала: {}, новое состояние: {}'.format(channel_addr, new_state_dict)
        self.logger.write_log.assert_called_once_with(log_msg=invalid_cmd_log_msg, log_level='ERROR')
        self.logger.write_log.reset_mock()

        # Неверный адрес модуля
        channel_addr = 'ch:m5:1'
        new_state_dict = {'status': '5'}
        hlTransceiver.set_ch_state(channel_addr=channel_addr, new_state_dict=new_state_dict)
        invalid_cmd_log_msg = 'Получены некорректные данные для установки нового состояния силового выхода:' \
                              ' адрес канала: {}, новое состояние: {}'.format(channel_addr, new_state_dict)
        self.logger.write_log.assert_called_once_with(log_msg=invalid_cmd_log_msg, log_level='ERROR')
        self.logger.write_log.reset_mock()

        # Некорректный адрес канала
        channel_addr = '::'
        new_state_dict = {'status': '5'}
        hlTransceiver.set_ch_state(channel_addr=channel_addr, new_state_dict=new_state_dict)
        invalid_cmd_log_msg = 'Получены некорректные данные для установки нового состояния силового выхода:' \
                              ' адрес канала: {}, новое состояние: {}'.format(channel_addr, new_state_dict)
        self.logger.write_log.assert_called_once_with(log_msg=invalid_cmd_log_msg, log_level='ERROR')
        self.logger.write_log.reset_mock()

        channel_addr = 'some random string'
        new_state_dict = {'status': '5'}
        hlTransceiver.set_ch_state(channel_addr=channel_addr, new_state_dict=new_state_dict)
        invalid_cmd_log_msg = 'Получены некорректные данные для установки нового состояния силового выхода:' \
                              ' адрес канала: {}, новое состояние: {}'.format(channel_addr, new_state_dict)
        self.logger.write_log.assert_called_once_with(log_msg=invalid_cmd_log_msg, log_level='ERROR')
        self.logger.write_log.reset_mock()

        channel_addr = 123
        new_state_dict = {'status': '5'}
        hlTransceiver.set_ch_state(channel_addr=channel_addr, new_state_dict=new_state_dict)
        invalid_cmd_log_msg = 'Получены некорректные данные для установки нового состояния силового выхода:' \
                              ' адрес канала: {}, новое состояние: {}'.format(channel_addr, new_state_dict)
        self.logger.write_log.assert_called_once_with(log_msg=invalid_cmd_log_msg, log_level='ERROR')
        self.logger.write_log.reset_mock()

        # Новое состояние вне допустимого диапазона значений ('4', '5')
        channel_addr = 'ch:m1:1'
        new_state_dict = {'status': '3'}
        hlTransceiver.set_ch_state(channel_addr=channel_addr, new_state_dict=new_state_dict)
        invalid_cmd_log_msg = 'Получены некорректные данные для установки нового состояния силового выхода:' \
                              ' адрес канала: {}, новое состояние: {}'.format(channel_addr, new_state_dict)
        self.logger.write_log.assert_called_once_with(log_msg=invalid_cmd_log_msg, log_level='ERROR')
        self.logger.write_log.reset_mock()

        # Некоректное новое состояние
        channel_addr = 'ch:m1:1'
        new_state_dict = {}
        hlTransceiver.set_ch_state(channel_addr=channel_addr, new_state_dict=new_state_dict)
        invalid_cmd_log_msg = 'Получены некорректные данные для установки нового состояния силового выхода:' \
                              ' адрес канала: {}, новое состояние: {}'.format(channel_addr, new_state_dict)
        self.logger.write_log.assert_called_once_with(log_msg=invalid_cmd_log_msg, log_level='ERROR')
        self.logger.write_log.reset_mock()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_set_ch_state_write_to_log_when_get_correct_cmd(self):
        """
        Тест проверяет, что функция HighLowTransceiver.set_ch_state
        пишет в лог сообщение при получении корректной команды
        """
        hlTransceiver = self.HighLowTransceiver()

        for unit_addr in self.test_axiom_settings['power units']:
            for channel_position in ['1', '2']:
                channel_addr = 'ch:{}:{}'.format(unit_addr, channel_position)

                for new_state in ['5', '4']:

                    hlTransceiver.power_units_state_dicts[unit_addr]['st']['state{}'.format(
                        channel_position)] = new_state

                    hlTransceiver.set_ch_state(channel_addr=channel_addr, new_state_dict={'status': new_state})

                    log_msg = 'Получена команда на установку состояния "{}" на выходе "{}"'.format(
                        hlTransceiver.humanreadable_states[new_state], channel_addr)

                    self.logger.write_log.assert_any_call(log_msg=log_msg, log_level='INFO')
                    self.logger.write_log.reset_mock()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_set_ch_state_function_calls_init_unit_function_if_unit_is_not_initialized(self):
        """
        Тест проверяет, что функция  HighLowTransceiver.set_ch_state
        вызывает функцию инициализации модуля HighLowTransceiver.init_power_unit
        в случае, когда значение поля 'state' равно 0 или 3
        """
        hlTransceiver = self.HighLowTransceiver()

        unit = list(self.test_axiom_settings['power units'].keys())[0]

        # силовой выход находится в состоянии 0 (idle)
        hlTransceiver.power_units_state_dicts[unit]['st']['state1'] = '0'
        hlTransceiver.power_units_state_dicts[unit]['st']['signal1'] = '0'
        hlTransceiver.init_power_unit = MagicMock()
        hlTransceiver.set_ch_state(channel_addr='ch:{}:1'.format(unit), new_state_dict={'status': '5'})
        hlTransceiver.init_power_unit.assert_called_with(unit)

        # силовой выход находится в состоянии 3 (nuse)
        hlTransceiver.power_units_state_dicts[unit]['st']['state1'] = '3'
        hlTransceiver.power_units_state_dicts[unit]['st']['signal1'] = '2'
        hlTransceiver.init_power_unit = MagicMock()
        hlTransceiver.set_ch_state(channel_addr='ch:{}:1'.format(unit), new_state_dict={'status': '5'})
        hlTransceiver.init_power_unit.assert_called_with(unit)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_set_ch_state_function_write_in_log_if_unit_is_not_initialized(self):
        """
        Тест проверяет, что функция  HighLowTransceiver.set_ch_state
        пишет сообщение в лог в случае, когда значение поля 'state' равно 0 или 3
        """
        hlTransceiver = self.HighLowTransceiver()
        hlTransceiver.run_power_unit = MagicMock(return_value=True)
        hlTransceiver.configure_power_unit= MagicMock(return_value=True)

        unit = list(self.test_axiom_settings['power units'].keys())[0]

        # силовой выход находится в состоянии 0 (idle)
        for current_state, current_signal in zip(['0', '3'], ['0', '2']):
            hlTransceiver.power_units_state_dicts[unit]['st']['state1'] = current_state
            hlTransceiver.power_units_state_dicts[unit]['st']['signal1'] = current_signal
            channel_addr = 'ch:{}:1'.format(unit)
            hlTransceiver.set_ch_state(channel_addr=channel_addr, new_state_dict={'status': '5'})
            log_msg = 'Силовой выход {} находится в состоянии {}. Требуется инициализация модуля'.format(
                channel_addr, current_state)
            self.logger.write_log.assert_any_call(log_msg=log_msg, log_level='WARNING')
            self.logger.write_log.reset_mock()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_set_ch_state_function_calls_before_return_from_set_ch_state_if_init_unit_function_returns_False(self):
        """
        Тест проверяет, что если функции HighLowTransceiver.init_power_unit
        не удается проинициализировать силовой модуль, вызывается функция
        HighLowTransceiver.before_return_from_set_ch_state
        """
        hlTransceiver = self.HighLowTransceiver()

        # Функции инициализации не удается проинициализировать модуль, возвращает False
        hlTransceiver.init_power_unit = MagicMock(return_value=False)
        hlTransceiver.before_return_from_set_ch_state = MagicMock()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]
        channel_addr = 'ch:{}:1'.format(unit_addr)
        new_state = '5'

        # Проверяем, что для любого из состояний логируется ошибка
        for current_state, current_signal in zip(['0', '3'], ['0', '2']):
            # Устанавливаем тестовое состояние и сигнал
            hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = current_state
            hlTransceiver.power_units_state_dicts[unit_addr]['st']['signal1'] = current_signal

            humanreadable_current_state = hlTransceiver.humanreadable_states[current_state]
            humanreadable_new_state = hlTransceiver.humanreadable_states[new_state]
            humanreadable_current_signal = hlTransceiver.humanreadable_signals[current_signal]

            hlTransceiver.set_ch_state(channel_addr=channel_addr, new_state_dict={'status': new_state})

            log_msg = 'Невозможно установить в канале "{}" состояние "{}".' \
                      ' Канал находится в состоянии: "{}", сигнал перехода: "{}"'.format(
                       channel_addr, humanreadable_new_state, humanreadable_current_state,
                       humanreadable_current_signal, )

            redis_error_msg = log_msg

            hlTransceiver.before_return_from_set_ch_state.assert_called_once_with(channel_addr=channel_addr,
                                                                                  current_state=current_state,
                                                                                  redis_error_msg=redis_error_msg,
                                                                                  log_msg=log_msg)
            hlTransceiver.before_return_from_set_ch_state.reset_mock()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_set_ch_state_function_does_not_write_in_COM_if_init_unit_function_returns_False(self):
        """
        Тест проверяет, что если функции HighLowTransceiver.init_power_unit
        не удается проинициализировать силовой модуль, функция HighLowTransceiver.set_ch_state
        ничего не записывает в последовательный порт
        """
        hlTransceiver = self.HighLowTransceiver()

        hlTransceiver.init_power_unit = MagicMock(return_value=False)

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]
        channel_addr = 'ch:{}:1'.format(unit_addr)
        new_state = {'status': '5'}

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['signal1'] = '0'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['signal2'] = '0'

        # силовой выход находится в состоянии 0 (idle)
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '0'

        hlTransceiver.set_ch_state(channel_addr=channel_addr, new_state_dict=new_state)

        hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].ser.write.assert_not_called()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_set_ch_state_function_calls_before_return_from_set_ch_state_if_channel_in_fault_power_off_or_lock_state(self):
        """
        Тест проверяет, что если канал находится в состоянии 2 (fault), 6 (poff)
        или 7 (lock) функция HighLowTransceiver.set_ch_state вызывает функцию
        HighLowTransceiver.before_return_from_set_ch_state
        """

        hlTransceiver = self.HighLowTransceiver()
        hlTransceiver.before_return_from_set_ch_state = MagicMock()

        # Первый модуль из тестовой конфигурации.
        # Для проверки будет использоваться его адрес
        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]
        channel_addr = 'ch:{}:1'.format(unit_addr)

        # Проверяем, что для любого из состояний логируется ошибка
        for current_state, current_signal in zip(['2', '6', '7'], ['3', '10', '14']):
            # Устанавливаем тестовое состояние и сигнал
            hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = current_state
            hlTransceiver.power_units_state_dicts[unit_addr]['st']['signal1'] = current_signal

            new_state = '5'
            hlTransceiver.set_ch_state(channel_addr=channel_addr, new_state_dict={'status': new_state})

            humanreadable_current_state = hlTransceiver.humanreadable_states[current_state]
            humanreadable_new_state = hlTransceiver.humanreadable_states[new_state]
            humanreadable_current_signal = hlTransceiver.humanreadable_signals[current_signal]

            log_msg = 'Невозможно установить в канале "{}" состояние "{}". Канал находится в состоянии: "{}", ' \
                      'сигнал перехода: "{}"'.format(channel_addr, humanreadable_new_state, humanreadable_current_state,
                                                     humanreadable_current_signal)

            hlTransceiver.before_return_from_set_ch_state.assert_called_once_with(channel_addr=channel_addr,
                                                                                  current_state=current_state,
                                                                                  log_msg=log_msg,
                                                                                  redis_error_msg=log_msg)
            hlTransceiver.before_return_from_set_ch_state.reset_mock()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_set_ch_state_function_does_not_write_in_COM_if_channel_in_fault_power_off_or_lock_state(self):
        """
        Тест проверяет, что если силовой выход находится в состоянии fault, poff или lock
        функция HighLowTransceiver.set_ch_state ничего не записывает в последовательный порт
        """
        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]
        channel_addr = 'ch:{}:1'.format(unit_addr)
        new_state = {'status': '5'}

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['signal1'] = '0'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['signal2'] = '0'

        for current_state in ['2', '6', '7']:
            hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = current_state

            hlTransceiver.set_ch_state(channel_addr=channel_addr, new_state_dict=new_state)

            hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].ser.write.assert_not_called()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_set_ch_state_function_calls_before_return_from_set_ch_state_if_new_state_is_already_set(self):
        """
        Тест проверяет, что если функцией HighLowTransceiver.set_ch_state получено
        новое состояние, которое уже и так установлено на силовом выходе,
        то она вызывает функцию HighLowTransceiver.before_return_from_set_ch_state
        """
        hlTransceiver = self.HighLowTransceiver()
        hlTransceiver.before_return_from_set_ch_state = MagicMock()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]
        channel_addr = 'ch:{}:1'.format(unit_addr)

        for new_state in ['4', '5']:
            hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = new_state

            hlTransceiver.set_ch_state(channel_addr=channel_addr, new_state_dict={'status': new_state})

            humanreadable_state = hlTransceiver.humanreadable_states[new_state]

            log_msg = 'Выполнение команды не требуется. Выход "{}" уже находится в состоянии "{}"'.format(
                channel_addr, humanreadable_state)

            hlTransceiver.before_return_from_set_ch_state.assert_called_once_with(channel_addr=channel_addr,
                                                                                  current_state=new_state,
                                                                                  log_msg=log_msg)
            hlTransceiver.before_return_from_set_ch_state.reset_mock()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_set_ch_state_function_does_not_write_in_COM_if_new_state_is_already_set(self):
        """
        Тест проверяет, что если функцией HighLowTransceiver.set_ch_state получено
        новое состояние, которое уже и так установлено на силовом выходе,
        то она ничего не записывает в последовательный порт
        """
        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]
        channel_addr = 'ch:{}:1'.format(unit_addr)

        for new_state in ['4', '5']:
            hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = new_state

            hlTransceiver.set_ch_state(channel_addr=channel_addr, new_state_dict={'status': new_state})

            hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].ser.write.assert_not_called()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_set_ch_state_function_use_ch_lock_during_command_sending(self):
        """
        Тест проверяет, что функция HighLowTransceiver.set_ch_state
        блокирует управление каналом на время отправки команды
        и проверки результата ее выполнения
        """
        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]
        channel_addr = 'ch:{}:1'.format(unit_addr)

        hlTransceiver.ch_locks[channel_addr] = MagicMock(spec=threading.Lock())

        for new_state, current_state in zip(['4', '5'], ['5', '4']):

            hlTransceiver.power_units_state_dicts[unit_addr]['st']['signal1'] = '0'
            hlTransceiver.power_units_state_dicts[unit_addr]['st']['signal2'] = '0'

            hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = current_state

            hlTransceiver.set_ch_state(channel_addr=channel_addr, new_state_dict={'status': new_state})

            hlTransceiver.ch_locks[channel_addr].acquire.assert_called()
            hlTransceiver.ch_locks[channel_addr].release.assert_called()
            hlTransceiver.ch_locks[channel_addr].acquire.reset_mock()
            hlTransceiver.ch_locks[channel_addr].release.reset_mock()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_set_ch_state_function_does_not_call_serialTransceiver_write_if_channel_is_locked(self):
        """
        Тест проверяет, что функция HighLowTransceiver.set_ch_state
        не вызывает функцию SerialTransceiver.write, если управление
        каналом заблокировано
        """
        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]
        channel_addr = 'ch:{}:1'.format(unit_addr)

        serTransceiver = hlTransceiver.unit_addrs_to_transceivers_map[unit_addr]
        serTransceiver.write = MagicMock()

        hlTransceiver.ch_locks[channel_addr].acquire()

        for new_state, current_state in zip(['4', '5'], ['5', '4']):
            hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = current_state
            hlTransceiver.set_ch_state(channel_addr=channel_addr, new_state_dict={'status': new_state})
            serTransceiver.write.assert_not_called()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_set_ch_state_function_calls_serialTransceiver_write_after_channel_is_unlocked(self):
        """
        Тест проверяет, что функция HighLowTransceiver.set_ch_state вызавает
        функцию SerialTransceiver.write, после того, как снимается
        блокировка управления каналом
        """
        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]
        channel_addr = 'ch:{}:1'.format(unit_addr)

        serTransceiver = hlTransceiver.unit_addrs_to_transceivers_map[unit_addr]
        serTransceiver.write = MagicMock()

        for new_state, current_state, current_signal in zip(['4', '5'], ['5', '4'], ['0', '0']):
            hlTransceiver.ch_locks[channel_addr].acquire()
            hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = current_state
            hlTransceiver.power_units_state_dicts[unit_addr]['st']['signal1'] = current_signal
            threading.Thread(target=hlTransceiver.set_ch_state, args=(channel_addr, {'status': new_state})).start()
            time.sleep(0.1)
            # пока управление каналом заблокировано, функция SerialTransceiver.write не вызывается
            serTransceiver.write.assert_not_called()
            hlTransceiver.ch_locks[channel_addr].release()
            time.sleep(0.1)
            # после того, как было разблокировано управление каналом, функция SerialTransceiver.write была вызвана
            serTransceiver.write.assert_called()
            serTransceiver.write.reset_mock()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_set_ch_state_calls_before_return_from_set_ch_state_if_lock_is_not_released_before_timeout_expiration(self):
        """
        Тест проверяет, что функция HighLowTransceiver.set_ch_state
        вызывает функцию HighLowTransceiver.before_return_from_set_ch_state,
        если блокировка управления каналом не снимается до истечения таймаута
        """
        hlTransceiver = self.HighLowTransceiver()
        hlTransceiver.before_return_from_set_ch_state = MagicMock()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]
        channel_addr = 'ch:{}:1'.format(unit_addr)

        for new_state, current_state in zip(['4', '5'], ['5', '4']):
            hlTransceiver.ch_locks[channel_addr].acquire()
            hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = current_state
            hlTransceiver.set_ch_state(channel_addr=channel_addr, new_state_dict={'status': new_state})

            humanreadable_new_state = hlTransceiver.humanreadable_states[new_state]
            log_msg = 'Невозможно установить состояние "{}" на выходе "{}":' \
                      ' управление заблокировано другим потоком'.format(humanreadable_new_state, channel_addr)

            hlTransceiver.before_return_from_set_ch_state.assert_called_once_with(channel_addr=channel_addr,
                                                                                  current_state=current_state,
                                                                                  log_msg=log_msg,
                                                                                  redis_error_msg=log_msg)
            hlTransceiver.before_return_from_set_ch_state.reset_mock()

            hlTransceiver.ch_locks[channel_addr].release()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_set_ch_state_function_write_correct_cmd(self):
        """
        Тест проверяет, что функция HighLowTransceiver.set_ch_state
        правильно формирует команду для записи в последовательный порт
        """
        hlTransceiver = self.HighLowTransceiver()

        for unit_addr in self.test_axiom_settings['power units']:

            hlTransceiver.power_units_state_dicts[unit_addr]['st']['signal1'] = '0'
            hlTransceiver.power_units_state_dicts[unit_addr]['st']['signal2'] = '0'

            for channel_position in ['1', '2']:
                channel_addr = 'ch:{}:{}'.format(unit_addr, channel_position)

                serTransceiver = hlTransceiver.unit_addrs_to_transceivers_map[unit_addr]
                serTransceiver.write = MagicMock()

                for new_state, current_state in zip(['4', '5'], ['5', '4']):

                    hlTransceiver.power_units_state_dicts[unit_addr]['st']['state{}'.format(channel_position)] = current_state

                    # команда для отправки
                    if new_state == '4':
                        ch_cmd = 'ch {} off {}'.format(channel_position, unit_addr)
                    elif new_state == '5':
                        ch_cmd = 'ch {} on {}'.format(channel_position, unit_addr)

                    hlTransceiver.set_ch_state(channel_addr=channel_addr, new_state_dict={'status': new_state})
                    serTransceiver.write.assert_called_with(ch_cmd)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_set_ch_state_calls_before_return_from_set_ch_state_if_SerialTransceiver_write_fails(self):
        """
        Тест проверяет, что функция HighLowTransceiver.set_ch_state
        вызывает функцию HighLowTransceiver.before_return_from_set_ch_state
        в случае неудачной записи в последовательный порт
        """
        hlTransceiver = self.HighLowTransceiver()
        hlTransceiver.before_return_from_set_ch_state = MagicMock()

        for unit_addr in self.test_axiom_settings['power units']:
            for channel_position in ['1', '2']:
                channel_addr = 'ch:{}:{}'.format(unit_addr, channel_position)

                serTransceiver = hlTransceiver.unit_addrs_to_transceivers_map[unit_addr]
                serTransceiver.write = MagicMock(return_value=False)

                for new_state, current_state in zip(['4', '5'], ['5', '4']):

                    hlTransceiver.power_units_state_dicts[unit_addr]['st']['state{}'.format(channel_position)] = current_state

                    hlTransceiver.set_ch_state(channel_addr=channel_addr, new_state_dict={'status': new_state})

                    humanreadable_new_state = hlTransceiver.humanreadable_states[new_state]

                    log_msg = 'Произошла ошибка записи в последовательный порт' \
                              ' при установке состояния "{}" на выходе "{}". Команда не выполнена.'.format(
                               humanreadable_new_state, channel_addr)

                    hlTransceiver.before_return_from_set_ch_state.assert_called_once_with(channel_addr=channel_addr,
                                                                                          current_state=current_state,
                                                                                          log_msg=log_msg,
                                                                                          redis_error_msg=log_msg)
                    hlTransceiver.before_return_from_set_ch_state.reset_mock()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_set_ch_state_calls_before_return_from_set_ch_state_on_success(self):
        """
        Тест проверяет, что функция HighLowTransceiver.set_ch_state
        вызывает HighLowTransceiver.before_return_from_set_ch_state
        при успешном выполнении команды
        """
        hlTransceiver = self.HighLowTransceiver()
        hlTransceiver.before_return_from_set_ch_state = MagicMock()

        for unit_addr in self.test_axiom_settings['power units']:
            for channel_position in ['1', '2']:
                channel_addr = 'ch:{}:{}'.format(unit_addr, channel_position)

                serTransceiver = hlTransceiver.unit_addrs_to_transceivers_map[unit_addr]
                serTransceiver.write = MagicMock()

                for new_state, current_state in zip(['4', '5'], ['5', '4']):

                    hlTransceiver.power_units_state_dicts[unit_addr]['st']['state{}'.format(channel_position)] = current_state

                    threading.Thread(target=hlTransceiver.set_ch_state,
                                     args=(channel_addr, {'status': new_state})).start()

                    time.sleep(0.01)

                    hlTransceiver.power_units_state_dicts[unit_addr]['st'][
                        'state{}'.format(channel_position)] = new_state

                    time.sleep(0.05)

                    humanreadable_new_state = hlTransceiver.humanreadable_states[new_state]
                    log_msg = 'Установлено состояние "{}" на выходе "{}"'.format(humanreadable_new_state, channel_addr)
                    hlTransceiver.before_return_from_set_ch_state.assert_called_once_with(channel_addr=channel_addr,
                                                                                          current_state=new_state,
                                                                                          log_msg=log_msg)
                    hlTransceiver.before_return_from_set_ch_state.reset_mock()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_set_ch_state_calls_before_return_from_set_ch_state_if_new_state_is_2_6_7(self):
        """
        Тест проверяет, что функция HighLowTransceiver.set_ch_state
        вызывает функцию HighLowTransceiver.before_return_from_set_ch_state,
        если после отправки записи команды в последовательный порт, силовой
        выход переходит в состояние 2 (fault), 6(poff) или 7(lock)
        """
        hlTransceiver = self.HighLowTransceiver()

        for unit_addr in self.test_axiom_settings['power units']:
            for channel_position in ['1', '2']:
                channel_addr = 'ch:{}:{}'.format(unit_addr, channel_position)

                hlTransceiver.before_return_from_set_ch_state = MagicMock()

                for new_state, current_state in zip(['4', '5'], ['5', '4']):
                    for result_state, result_signal in zip(['2', '6', '7'], ['3', '10', '14']):

                        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state{}'.format(channel_position)] = current_state

                        threading.Thread(target=hlTransceiver.set_ch_state,
                                         args=(channel_addr, {'status': new_state})).start()

                        time.sleep(0.1)

                        # Устанавливаем состояние и сигнал, получившиеся после отправки команды
                        hlTransceiver.power_units_state_dicts[unit_addr]['st'][
                            'state{}'.format(channel_position)] = result_state
                        hlTransceiver.power_units_state_dicts[unit_addr]['st'][
                            'signal{}'.format(channel_position)] = result_signal

                        time.sleep(0.1)

                        humanreadable_new_state = hlTransceiver.humanreadable_states[new_state]
                        humanreadable_result_state = hlTransceiver.humanreadable_states[result_state]
                        humanreadable_result_signal = hlTransceiver.humanreadable_signals[result_signal]

                        redis_msg = 'Ошибка при установке состояния "{}" на выходе "{}".' \
                                    ' Текущее состояние: "{}", сигнал перехода в состояние: "{}"'.format(
                                     humanreadable_new_state, channel_addr, humanreadable_result_state,
                                     humanreadable_result_signal)
                        log_msg = redis_msg
                        hlTransceiver.before_return_from_set_ch_state.assert_called_with(channel_addr=channel_addr,
                                                                                         current_state=result_state,
                                                                                         redis_error_msg=redis_msg,
                                                                                         log_msg=log_msg)
                        hlTransceiver.before_return_from_set_ch_state.reset_mock()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_set_ch_state_calls_before_return_from_set_ch_state_if_state_does_not_change(self):
        """
        Тест проверяет, что функция HighLowTransceiver.set_ch_state
        вызывает функцию обработки выхода HighLowTransceiver.before_return_from_set_ch_state,
        если после отправки записи команды в последовательный порт состояние
        выхода не меняется до истечения таймаута
        """
        hlTransceiver = self.HighLowTransceiver()

        for unit_addr in self.test_axiom_settings['power units']:
            for channel_position in ['1', '2']:
                channel_addr = 'ch:{}:{}'.format(unit_addr, channel_position)

                hlTransceiver.before_return_from_set_ch_state = MagicMock()

                for new_state, current_state, current_signal in zip(['4', '5'], ['5', '4'], ['12', '13']):

                    hlTransceiver.power_units_state_dicts[unit_addr]['st']['state{}'.format(channel_position)] = current_state
                    hlTransceiver.power_units_state_dicts[unit_addr]['st']['signal{}'.format(channel_position)] = current_signal

                    threading.Thread(target=hlTransceiver.set_ch_state,
                                     args=(channel_addr, {'status': new_state})).start()

                    time.sleep(3.1)

                    humanreadable_new_state = hlTransceiver.humanreadable_states[new_state]
                    humanreadable_result_state = hlTransceiver.humanreadable_states[current_state]
                    humanreadable_result_signal = hlTransceiver.humanreadable_signals[current_signal]

                    redis_msg = 'Ошибка при установке состояния "{}" на выходе "{}".' \
                                ' Текущее состояние: "{}", сигнал перехода в состояние: "{}"'.format(
                                 humanreadable_new_state, channel_addr, humanreadable_result_state,
                                 humanreadable_result_signal)
                    log_msg = redis_msg
                    hlTransceiver.before_return_from_set_ch_state.assert_called_with(channel_addr=channel_addr,
                                                                                     current_state=current_state,
                                                                                     redis_error_msg=redis_msg,
                                                                                     log_msg=log_msg)
                    hlTransceiver.before_return_from_set_ch_state.reset_mock()\


class TestInitPowerUnit(HighLowTransceiverTestBase):
    """
    Тесты функции инициализации силового модуля
    HighLowTransceiver.init_power_unit
    """

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_init_power_unit_acquires_lock_for_both_channel(self):
        """
        Тест проверяет, что функция HighLowTransceiver.init_power_unit
        блокирует управление обоими каналами модуля
        """

        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        ch1_lock = hlTransceiver.ch_locks['ch:{}:1'.format(unit_addr)] = MagicMock(
            spec=hlTransceiver.ch_locks['ch:{}:1'.format(unit_addr)])
        ch2_lock = hlTransceiver.ch_locks['ch:{}:2'.format(unit_addr)] = MagicMock(
            spec=hlTransceiver.ch_locks['ch:{}:2'.format(unit_addr)])

        ch1_lock.acquire = MagicMock(return_value=True)
        ch2_lock.acquire = MagicMock(return_value=True)

        hlTransceiver.init_power_unit(unit_addr)

        ch1_lock.acquire.assert_called_once()
        ch2_lock.acquire.assert_called_once()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_init_power_unit_returns_False_if_cant_acquire_first_lock(self):
        """
        Тест проверяет, что функция HighLowTransceiver.init_power_unit
        возвращает False, если не может заблокировать управление первым каналом
        """
        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '0'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '0'

        ch1_lock = hlTransceiver.ch_locks['ch:{}:1'.format(unit_addr)] = MagicMock(
            spec=hlTransceiver.ch_locks['ch:{}:1'.format(unit_addr)])
        ch1_lock.acquire.return_value = False

        self.assertEqual(hlTransceiver.init_power_unit(unit_addr), False)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_init_power_unit_log_error_if_cant_acquire_first_lock(self):
        """
        Тест проверяет, что функция HighLowTransceiver.init_power_unit
        логирует ошибку, если не может заблокировать управление первым каналом
        """
        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '0'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '0'

        ch1_lock = hlTransceiver.ch_locks['ch:{}:1'.format(unit_addr)] = MagicMock(
            spec=hlTransceiver.ch_locks['ch:{}:1'.format(unit_addr)])
        ch1_lock.acquire.return_value = False

        hlTransceiver.init_power_unit(unit_addr)

        log_msg = 'Ошибка при инициализации модуля "{}":' \
                  ' не удается заблокировать управление первым каналом'.format(unit_addr)

        self.logger.write_log.assert_called_once_with(log_msg=log_msg, log_level='ERROR')

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_init_power_unit_returns_False_if_cant_acquire_second_lock(self):
        """
        Тест проверяет, что функция HighLowTransceiver.init_power_unit
        возвращает False, если не может заблокировать управление вторым каналом
        """
        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '0'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '0'

        ch2_lock = hlTransceiver.ch_locks['ch:{}:2'.format(unit_addr)] = MagicMock(
            spec=hlTransceiver.ch_locks['ch:{}:2'.format(unit_addr)])
        ch2_lock.acquire.return_value = False

        self.assertEqual(hlTransceiver.init_power_unit(unit_addr), False)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_init_power_unit_log_error_if_cant_acquire_second_lock(self):
        """
        Тест проверяет, что функция HighLowTransceiver.init_power_unit
        логирует ошибку, если не может заблокировать управление вторым каналом
        """
        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '0'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '0'

        ch2_lock = hlTransceiver.ch_locks['ch:{}:2'.format(unit_addr)] = MagicMock(
            spec=hlTransceiver.ch_locks['ch:{}:2'.format(unit_addr)])
        ch2_lock.acquire.return_value = False

        hlTransceiver.init_power_unit(unit_addr)

        log_msg = 'Ошибка при инициализации модуля "{}":' \
                  ' не удается заблокировать управление вторым каналом'.format(unit_addr)

        self.logger.write_log.assert_called_once_with(log_msg=log_msg, log_level='ERROR')

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_init_power_unit_releases_first_lock_if_cant_get_second(self):
        """
        Тест проверяет, что функция HighLowTransceiver.init_power_unit
        снимает блокировку управления первым каналом, если не может
        получить блокировку управления вторым
        """

        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        ch1_lock = hlTransceiver.ch_locks['ch:{}:1'.format(unit_addr)] = MagicMock(
            spec=hlTransceiver.ch_locks['ch:{}:1'.format(unit_addr)])
        ch2_lock = hlTransceiver.ch_locks['ch:{}:2'.format(unit_addr)] = MagicMock(
            spec=hlTransceiver.ch_locks['ch:{}:2'.format(unit_addr)])

        ch1_lock.acquire = MagicMock(return_value=True)
        ch2_lock.acquire = MagicMock(return_value=False)

        hlTransceiver.init_power_unit(unit_addr)

        ch1_lock.acquire.assert_called()
        ch2_lock.acquire.assert_called()
        ch1_lock.release.assert_called_once()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_init_power_unit_calls_run_power_unit_if_current_state_is_0(self):
        """
        Тест проверяет, что функция HighLowTransceiver.init_power_unit
        вызывает функцию HighLowTransceiver.run_power_unit, если состояние
        одного или двух выходов '0'
        """

        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '0'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '0'

        hlTransceiver.run_power_unit = MagicMock()

        # Оба выхода находятся в состоянии 0
        hlTransceiver.init_power_unit(unit_addr)

        hlTransceiver.run_power_unit.assert_called_once_with(unit_addr=unit_addr)
        hlTransceiver.run_power_unit.reset_mock()

        # первый выход находится в состоянии 2, второй - 0
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '2'

        hlTransceiver.init_power_unit(unit_addr)

        hlTransceiver.run_power_unit.assert_called_once_with(unit_addr=unit_addr)
        hlTransceiver.run_power_unit.reset_mock()

        # первый выход находится в состоянии 0, второй - 2
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '0'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '2'

        hlTransceiver.init_power_unit(unit_addr)

        hlTransceiver.run_power_unit.assert_called_once_with(unit_addr=unit_addr)
        hlTransceiver.run_power_unit.reset_mock()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_init_power_unit_returns_False_if_unit_cant_be_run(self):
        """
        Тест проверяет, что функция HighLowTransceiver.init_power_unit
        возвращает False, если модуль не может быть запущен (функция
        HighLowTransceiver.run_power_unit возвращает False)
        """

        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '0'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '0'

        hlTransceiver.run_power_unit = MagicMock(return_value=False)

        self.assertEqual(hlTransceiver.init_power_unit(unit_addr), False)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_init_power_unit_releases_locks_if_unit_cant_be_run(self):
        """
        Тест проверяет, что функция HighLowTransceiver.init_power_unit
        снимает блокировку управления каналами, если модуль не может быть запущен
        (функция HighLowTransceiver.run_power_unit возвращает False)
        """

        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.run_power_unit = MagicMock(return_value=False)

        hlTransceiver.init_power_unit(unit_addr)

        self.assertEqual(hlTransceiver.ch_locks['ch:{}:1'.format(unit_addr)].locked(), False)
        self.assertEqual(hlTransceiver.ch_locks['ch:{}:2'.format(unit_addr)].locked(), False)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_init_power_unit_calls_configure_power_unit_if_current_state_is_3(self):
        """
        Тест проверяет, что функция HighLowTransceiver.init_power_unit
        вызывает функцию HighLowTransceiver.configure_power_unit, если состояние
        одного или двух выходов '0'
        """

        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.configure_power_unit = MagicMock()

        # Оба выхода находятся в состоянии 3
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '3'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '3'

        hlTransceiver.init_power_unit(unit_addr)

        hlTransceiver.configure_power_unit.assert_called_once_with(unit_addr=unit_addr)
        hlTransceiver.configure_power_unit.reset_mock()

        # первый выход находится в состоянии 2, второй - 3
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '2'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '3'

        hlTransceiver.init_power_unit(unit_addr)

        hlTransceiver.configure_power_unit.assert_called_once_with(unit_addr=unit_addr)
        hlTransceiver.configure_power_unit.reset_mock()

        # первый выход находится в состоянии 3, второй - 2
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '3'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '2'

        hlTransceiver.init_power_unit(unit_addr)

        hlTransceiver.configure_power_unit.assert_called_once_with(unit_addr=unit_addr)
        hlTransceiver.configure_power_unit.reset_mock()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_init_power_unit_returns_False_if_unit_cant_be_configured(self):
        """
        Тест проверяет, что функция HighLowTransceiver.init_power_unit
        возвращает False, если модуль не может быть сконфигурирован (функция
        HighLowTransceiver.configure_power_unit возвращает False)
        """

        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.configure_power_unit = MagicMock(return_value=False)

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '3'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '3'

        self.assertEqual(hlTransceiver.init_power_unit(unit_addr), False)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_init_power_unit_releases_locks_if_unit_cant_be_configured(self):
        """
        Тест проверяет, что функция HighLowTransceiver.init_power_unit
        снимает блокировку управления каналами, если модуль не может быть сконфигурирован
        (функция HighLowTransceiver.configure_power_unit возвращает False)
        """

        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '3'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '3'

        hlTransceiver.configure_power_unit = MagicMock(return_value=False)

        hlTransceiver.init_power_unit(unit_addr)

        self.assertEqual(hlTransceiver.ch_locks['ch:{}:1'.format(unit_addr)].locked(), False)
        self.assertEqual(hlTransceiver.ch_locks['ch:{}:2'.format(unit_addr)].locked(), False)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_init_power_unit_calls_configure_after_run(self):
        """
        Тест проверяет, что если после вызова функции HighLowTransceiver.run_power_unit
        один или оба выхода переходят в состояние '3', вызывается функция
        HighLowTransceiver.configure_power_unit
        """

        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '0'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '0'

        def run_power_unit_side_effect(**args):
            hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '3'
            hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '3'
            return True

        hlTransceiver.run_power_unit = MagicMock(return_value=True, side_effect=run_power_unit_side_effect)
        hlTransceiver.configure_power_unit = MagicMock(return_value=True)

        hlTransceiver.init_power_unit(unit_addr)

        hlTransceiver.run_power_unit.assert_called_once_with(unit_addr=unit_addr)
        hlTransceiver.configure_power_unit.assert_called_once_with(unit_addr=unit_addr)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_init_power_unit_returns_True_if_unit_is_run_and_configured(self):
        """
        Тест проверяет, что если функции HighLowTransceiver.run_power_unit
        и HighLowTransceiver.configure_power_unit возвращают True,
        функция HighLowTransceiver.init_power_unit возвращает True
        """

        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '0'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '0'

        def run_power_unit_side_effect(**args):
            hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '3'
            hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '3'
            return True

        hlTransceiver.run_power_unit = MagicMock(return_value=True, side_effect=run_power_unit_side_effect)
        hlTransceiver.configure_power_unit = MagicMock(return_value=True)

        result = hlTransceiver.init_power_unit(unit_addr)

        hlTransceiver.run_power_unit.assert_called_once_with(unit_addr=unit_addr)
        hlTransceiver.configure_power_unit.assert_called_once_with(unit_addr=unit_addr)

        self.assertEqual(result, True)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_init_power_unit_returns_True_if_unit_is_initialized_by_another_thread(self):
        """
        Тест проверяет, что если функция HighLowTransceiver.init_power_unit
        не может установить блокировку управления каналов, выполяется проверка
        того, не был ли модуль проинициализирован в другом потоке, и возвращает
        True, если это так
        """

        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        # Устанавливаем блокировку
        hlTransceiver.ch_locks['ch:{}:1'.format(unit_addr)].acquire()
        hlTransceiver.ch_locks['ch:{}:2'.format(unit_addr)].acquire()

        # Устанавливаем состояние выходов, такое, как будто они были проинициализированы в другом потоке
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '4'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '4'

        self.assertTrue(hlTransceiver.init_power_unit(unit_addr))

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_init_power_unit_releases_locks_if_unit_is_run_and_configured(self):
        """
        Тест проверяет, что если функции HighLowTransceiver.run_power_unit
        и HighLowTransceiver.configure_power_unit возвращают True,
        функция HighLowTransceiver.init_power_unit снимает блокировку управления каналами
        """

        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '0'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '0'

        def run_power_unit_side_effect(**args):
            hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '3'
            hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '3'
            return True

        hlTransceiver.run_power_unit = MagicMock(return_value=True, side_effect=run_power_unit_side_effect)
        hlTransceiver.configure_power_unit = MagicMock(return_value=True)

        hlTransceiver.init_power_unit(unit_addr)

        hlTransceiver.run_power_unit.assert_called_once_with(unit_addr=unit_addr)
        hlTransceiver.configure_power_unit.assert_called_once_with(unit_addr=unit_addr)

        self.assertEqual(hlTransceiver.ch_locks['ch:{}:1'.format(unit_addr)].locked(), False)
        self.assertEqual(hlTransceiver.ch_locks['ch:{}:2'.format(unit_addr)].locked(), False)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_init_power_unit_restore_saved_channels_state(self):
        """
        Тест проверяет, что функция HighLowTransceiver.run_power_unit
        после завершения инициализации устанавливает на выходах состояние
        сохраненное в redis
        """

        hlTransceiver = self.HighLowTransceiver()
        hlTransceiver.redis.get = MagicMock(return_value="{'status': '5'}")
        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '4'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '4'

        hlTransceiver.run_power_unit = MagicMock(return_value=True)
        hlTransceiver.configure_power_unit = MagicMock(return_value=True)
        hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write = MagicMock(return_value=True)

        hlTransceiver.init_power_unit(unit_addr)

        hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write.assert_any_call('ch 1 on {}'.format(unit_addr))
        hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write.assert_any_call('ch 2 on {}'.format(unit_addr))

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_init_power_unit_save_defective_channel_state(self):
        """
        Тест проверяет, что функция HighLowTransceiver.run_power_unit
        после завершения инициализации сохраняет в БД состояние канала,
        если оно стало 2, 6 или 7
        """

        hlTransceiver = self.HighLowTransceiver()
        hlTransceiver.redis.get = MagicMock(return_value="{'status': '5'}")
        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.run_power_unit = MagicMock(return_value=True)
        hlTransceiver.configure_power_unit = MagicMock(return_value=True)
        hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write = MagicMock(return_value=True)

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '2'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '2'

        hlTransceiver.init_power_unit(unit_addr)

        hlTransceiver.redis.set.assert_any_call(name='ch:{}:1'.format(unit_addr), value={'status': '2'})
        hlTransceiver.redis.set.assert_any_call(name='ch:{}:2'.format(unit_addr), value={'status': '2'})

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '6'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '6'

        hlTransceiver.init_power_unit(unit_addr)

        hlTransceiver.redis.set.assert_any_call(name='ch:{}:1'.format(unit_addr), value={'status': '6'})
        hlTransceiver.redis.set.assert_any_call(name='ch:{}:2'.format(unit_addr), value={'status': '6'})

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '7'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '7'

        hlTransceiver.init_power_unit(unit_addr)

        hlTransceiver.redis.set.assert_any_call(name='ch:{}:1'.format(unit_addr), value={'status': '7'})
        hlTransceiver.redis.set.assert_any_call(name='ch:{}:2'.format(unit_addr), value={'status': '7'})

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_init_power_unit_save_channel_state_if_cant_read_from_redis(self):
        """
        Тест проверяет, что функция HighLowTransceiver.run_power_unit
        после завершения инициализации сохраняет в БД текущее состояние канала,
        если в БД записано некорректное значение или не записано никакого
        """

        hlTransceiver = self.HighLowTransceiver()
        hlTransceiver.redis.get = MagicMock(return_value=None)
        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.run_power_unit = MagicMock(return_value=True)
        hlTransceiver.configure_power_unit = MagicMock(return_value=True)
        hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write = MagicMock(return_value=True)

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '4'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '4'

        hlTransceiver.init_power_unit(unit_addr)

        hlTransceiver.redis.set.assert_any_call(name='ch:{}:1'.format(unit_addr), value={'status': '4'})
        hlTransceiver.redis.set.assert_any_call(name='ch:{}:2'.format(unit_addr), value={'status': '4'})

        hlTransceiver.redis.get = MagicMock(return_value='corrupted value')

        hlTransceiver.init_power_unit(unit_addr)

        hlTransceiver.redis.set.assert_any_call(name='ch:{}:1'.format(unit_addr), value={'status': '4'})
        hlTransceiver.redis.set.assert_any_call(name='ch:{}:2'.format(unit_addr), value={'status': '4'})

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_init_power_unit_doesnt_crash_if_unit_isnt_connected(self):
        """
        Тест проверяет, что вызов функции HighLowTransceiver.run_power_unit
        не приводит к ошибкам, если силовой модуль не подключен (структура
        состояния заполнена None)
        """

        hlTransceiver = self.HighLowTransceiver()
        hlTransceiver.redis.get = MagicMock(return_value=None)
        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        self.assertTrue(hlTransceiver.init_power_unit(unit_addr))

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_init_power_restrore_turn_on_state(self):
        """
        Тест проверяет, функция HighLowTransceiver.run_power_unit
        устанавливает состояние включено на выходах, которые были
        включены до перезагрузки
        """

        hlTransceiver = self.HighLowTransceiver()

        hlTransceiver.set_ch_state = MagicMock()

        redis_side_effect = [str({'status': '5'}), str({'status': '5'})]
        hlTransceiver.redis.get = MagicMock(side_effect=redis_side_effect)

        hlTransceiver.run_power_unit = MagicMock(return_value=True)

        def conf_side_effect(**kwargs):
            hlTransceiver.redis.get.side_effect = [str({'status': '4'}), str({'status': '4'})]
            return True

        hlTransceiver.configure_power_unit = MagicMock(side_effect=conf_side_effect)

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '3'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '3'

        hlTransceiver.init_power_unit(unit_addr)

        hlTransceiver.set_ch_state.assert_any_call(channel_addr='ch:{}:1'.format(unit_addr),
                                                   new_state_dict={'status': '5'})
        hlTransceiver.set_ch_state.assert_any_call(channel_addr='ch:{}:2'.format(unit_addr),
                                                   new_state_dict={'status': '5'})


class TestRunPowerUnit(HighLowTransceiverTestBase):
    """
    Тесты функции запуска силового модуля
    HighLowTransceiver.run_power_unit
    """

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_run_power_unit_calls_serial_write_with_correct_cmd(self):
        """
        Тест проверяет, что функция HighLowTransceiver.run_power_unit
        вызывает функцию SerialTransceiver.write с правильной командой
        запуска силового модуля
        """

        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '0'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '0'

        hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write = MagicMock()

        run_cmd = 'run start {}'.format(unit_addr)

        hlTransceiver.run_power_unit(unit_addr=unit_addr)

        hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write.assert_called_with(run_cmd)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_run_power_unit_calls_serial_write_again_if_it_returns_False(self):
        """
        Тест проверяет, что функция HighLowTransceiver.run_power_unit
        вызывает функцию SerialTransceiver.write количество раз равное
        retries + 1, если она возвращает False
        """

        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '0'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '0'

        hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write = MagicMock(return_value=False)

        retries = 1

        hlTransceiver.run_power_unit(unit_addr=unit_addr, retries=retries)

        self.assertEqual(hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write.call_count, retries + 1)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_run_power_unit_returns_False_if_serial_write_returns_False(self):
        """
        Тест проверяет, что функция HighLowTransceiver.run_power_unit
        возвращает False, если функция SerialTransceiver.write возвращает False
        """

        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '0'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '0'

        hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write = MagicMock(return_value=False)

        self.assertEqual(hlTransceiver.run_power_unit(unit_addr=unit_addr), False)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_run_power_unit_log_error_if_serial_write_returns_False(self):
        """
        Тест проверяет, что функция HighLowTransceiver.run_power_unit
        логирует ошибку, если функция SerialTransceiver.write возвращает False
        """

        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '0'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '0'

        hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write = MagicMock(return_value=False)

        hlTransceiver.run_power_unit(unit_addr=unit_addr)

        ch1_humanreadable_state = hlTransceiver.humanreadable_states['0']
        ch2_humanreadable_state = ch1_humanreadable_state

        channel1_addr = 'ch:{}:1'.format(unit_addr)
        channel2_addr = 'ch:{}:2'.format(unit_addr)

        log_msg = 'Ошибка при выполнении запуска модуля "{}".' \
                  ' Текущее состояние выходов: "{}" - "{}", "{}" - "{}"'.format(
                   unit_addr, channel1_addr, ch1_humanreadable_state, channel2_addr, ch2_humanreadable_state)

        self.logger.write_log.assert_called_once_with(log_msg=log_msg, log_level='ERROR')

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_run_power_unit_calls_serial_write_again_if_state_doesnt_change_before_timeout_expired(self):
        """
        Тест проверяет, что функция HighLowTransceiver.run_power_unit
        что, если функция SerialTransceiver.write вернула True, но состояние
        хотя бы одного из выходов осталось '0', команда записывается в
        последовательный снова (количество раз равно retries + 1)
        """

        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '0'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '0'

        hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write = MagicMock(return_value=True)

        retries = 3

        hlTransceiver.run_power_unit(unit_addr=unit_addr, retries=retries)

        self.assertEqual(hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write.call_count, retries + 1)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_run_power_unit_returns_False_if_state_doesnt_change_before_timeout_expired(self):
        """
        Тест проверяет, что функция HighLowTransceiver.run_power_unit
        возвращает False, если состояние хотя бы одного из выходов
        остается '0'
        """

        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '0'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '0'

        hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write = MagicMock(return_value=True)

        self.assertEqual(hlTransceiver.run_power_unit(unit_addr=unit_addr, retries=1), False)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_run_power_unit_log_error_if_state_doesnt_change_before_timeout_expired(self):
        """
        Тест проверяет, что функция HighLowTransceiver.run_power_unit
        логирует ошибку, если состояние хотя бы одного из выходов остается 0
        """

        self.logger.write_log.reset_mock()

        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '0'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '0'

        hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write = MagicMock(return_value=True)

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '3'

        hlTransceiver.run_power_unit(unit_addr=unit_addr, retries=1)

        ch1_state = hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1']
        ch2_state = hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2']

        ch1_humanreadable_state = hlTransceiver.humanreadable_states[ch1_state]
        ch2_humanreadable_state = hlTransceiver.humanreadable_states[ch2_state]

        channel1_addr = 'ch:{}:1'.format(unit_addr)
        channel2_addr = 'ch:{}:2'.format(unit_addr)

        log_msg = 'Ошибка при выполнении запуска модуля "{}".' \
                  ' Текущее состояние выходов: "{}" - "{}", "{}" - "{}"'.format(
                   unit_addr, channel1_addr, ch1_humanreadable_state, channel2_addr, ch2_humanreadable_state)

        self.logger.write_log.assert_called_once_with(log_msg=log_msg, log_level='ERROR')

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_run_power_unit_doesnt_calls_serial_write_again_if_state_changes_before_timeout_expired(self):
        """
        Тест проверяет, что если состояние обоих выходов стало не '0'
        до истечения таймаута функция SerialTransceiver.write повторно не вызывается
        """

        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '3'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '3'

        hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write = MagicMock(return_value=True)

        retries = 1
        timeout = 3

        threading.Thread(target=hlTransceiver.run_power_unit, args=(unit_addr, retries)).start()

        time.sleep(1)

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '3'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '3'

        time.sleep((retries + 1) * timeout)

        hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write.assert_called_once()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_run_power_unit_returns_True_if_state_changes(self):
        """
        Тест проверяет, что функция HighLowTransceiver.run_power_unit
        возвращает True, если состояние обоих выходов становится не '0'
        """

        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write = MagicMock(return_value=True)

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '3'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '3'

        self.assertEqual(hlTransceiver.run_power_unit(unit_addr=unit_addr, retries=1), True)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_run_power_unit_log_success_if_state_changes(self):
        """
        Тест проверяет, что функция HighLowTransceiver.run_power_unit
        делает запись в лог о завершении запуска, если состояние
        обоих выходов становится не '0'
        """

        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write = MagicMock(return_value=True)

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '3'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '3'

        hlTransceiver.run_power_unit(unit_addr=unit_addr, retries=1)

        ch1_humanreadable_state = hlTransceiver.humanreadable_states['3']
        ch2_humanreadable_state = ch1_humanreadable_state

        channel1_addr = 'ch:{}:1'.format(unit_addr)
        channel2_addr = 'ch:{}:2'.format(unit_addr)

        log_msg = 'Запуск модуля "{}" выполнен.' \
                  ' Текущее состояние выходов: "{}" - "{}", "{}" - "{}"'.format(
                   unit_addr, channel1_addr, ch1_humanreadable_state, channel2_addr, ch2_humanreadable_state)

        self.logger.write_log.assert_called_once_with(log_msg=log_msg, log_level='INFO')


class TestConfigurePowerUnit(HighLowTransceiverTestBase):
    """
    Тесты функции конфигурации силового модуля
    HighLowTransceiver.configure_power_unit
    """

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_configure_power_unit_calls_serial_write_with_correct_cmd(self):
        """
        Тест проверяет, что функция HighLowTransceiver.configure_power_unit
        вызывает функцию SerialTransceiver.write с правильной командой
        конфигурации силового модуля
        """
        self.HighLowTransceiver.load_settings = MagicMock(return_value=self.test_axiom_settings)
        hlTransceiver = self.HighLowTransceiver()

        for unit_addr in self.test_axiom_settings['power units']:

            hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '0'
            hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '0'

            hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write = MagicMock()

            value1 = self.test_axiom_settings['power units thresholds'][unit_addr][0]
            value2 = self.test_axiom_settings['power units thresholds'][unit_addr][1]

            configure_cmd = 'adc hgrp {} {} 1 2 {}'.format(value1, value2, unit_addr)

            hlTransceiver.configure_power_unit(unit_addr=unit_addr)

            hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write.assert_called_with(configure_cmd)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_configure_power_unit_calls_serial_write_again_if_it_returns_False(self):
        """
        Тест проверяет, что функция HighLowTransceiver.configure_power_unit
        вызывает функцию SerialTransceiver.write количество раз равное
        retries + 1, если она возвращает False
        """

        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '0'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '0'

        hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write = MagicMock(return_value=False)

        retries = 1

        hlTransceiver.configure_power_unit(unit_addr=unit_addr, retries=retries)

        self.assertEqual(hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write.call_count, retries + 1)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_configure_power_unit_returns_False_if_serial_write_returns_False(self):
        """
        Тест проверяет, что функция HighLowTransceiver.configure_power_unit
        возвращает False, если функция SerialTransceiver.write возвращает False
        """

        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '0'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '0'

        hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write = MagicMock(return_value=False)

        self.assertEqual(hlTransceiver.configure_power_unit(unit_addr=unit_addr), False)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_configure_power_unit_log_error_if_serial_write_returns_False(self):
        """
        Тест проверяет, что функция HighLowTransceiver.configure_power_unit
        логирует ошибку, если функция SerialTransceiver.write возвращает False
        """

        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '3'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '3'

        hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write = MagicMock(return_value=False)

        hlTransceiver.configure_power_unit(unit_addr=unit_addr)

        ch1_humanreadable_state = hlTransceiver.humanreadable_states['3']
        ch2_humanreadable_state = ch1_humanreadable_state

        channel1_addr = 'ch:{}:1'.format(unit_addr)
        channel2_addr = 'ch:{}:2'.format(unit_addr)

        log_msg = 'Ошибка при выполнении конфигурации модуля "{}".' \
                  ' Текущее состояние выходов: "{}" - "{}", "{}" - "{}"'.format(
                   unit_addr, channel1_addr, ch1_humanreadable_state, channel2_addr, ch2_humanreadable_state)

        self.logger.write_log.assert_called_once_with(log_msg=log_msg, log_level='ERROR')

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_configure_power_unit_calls_serial_write_again_if_state_doesnt_change_before_timeout_expired(self):
        """
        Тест проверяет, что функция HighLowTransceiver.configure_power_unit
        что, если функция SerialTransceiver.write вернула True, но состояние
        хотя бы одного из выходов осталось '3', команда записывается в
        последовательный снова (количество раз равно retries + 1)
        """

        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '3'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '3'

        hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write = MagicMock(return_value=True)

        retries = 1

        hlTransceiver.configure_power_unit(unit_addr=unit_addr, retries=retries)

        self.assertEqual(hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write.call_count, retries + 1)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_configure_power_unit_returns_False_if_state_doesnt_change_before_timeout_expired(self):
        """
        Тест проверяет, что функция HighLowTransceiver.configure_power_unit
        возвращает False, если состояние хотя бы одного из выходов
        остается '3'
        """

        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '3'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '4'

        hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write = MagicMock(return_value=True)

        self.assertEqual(hlTransceiver.configure_power_unit(unit_addr=unit_addr, retries=1), False)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_configure_power_unit_log_error_if_state_doesnt_change_before_timeout_expired(self):
        """
        Тест проверяет, что функция HighLowTransceiver.configure_power_unit
        логирует ошибку, если состояние хотя бы одного из выходов остается 3
        """

        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '3'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '4'

        hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write = MagicMock(return_value=True)

        hlTransceiver.configure_power_unit(unit_addr=unit_addr, retries=1)

        ch1_state = hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1']
        ch2_state = hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2']

        ch1_humanreadable_state = hlTransceiver.humanreadable_states[ch1_state]
        ch2_humanreadable_state = hlTransceiver.humanreadable_states[ch2_state]

        channel1_addr = 'ch:{}:1'.format(unit_addr)
        channel2_addr = 'ch:{}:2'.format(unit_addr)

        log_msg = 'Ошибка при выполнении конфигурации модуля "{}".' \
                  ' Текущее состояние выходов: "{}" - "{}", "{}" - "{}"'.format(
                   unit_addr, channel1_addr, ch1_humanreadable_state, channel2_addr, ch2_humanreadable_state)

        self.logger.write_log.assert_called_once_with(log_msg=log_msg, log_level='ERROR')

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_configure_power_unit_doesnt_calls_serial_write_again_if_state_changes_before_timeout_expired(self):
        """
        Тест проверяет, что если состояние обоих выходов стало не '3'
        до истечения таймаута функция SerialTransceiver.write повторно не вызывается
        """

        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '3'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '3'

        hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write = MagicMock(return_value=True)

        retries = 1
        timeout = 3

        threading.Thread(target=hlTransceiver.configure_power_unit, args=(unit_addr, retries)).start()

        time.sleep(1)

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '4'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '4'

        time.sleep((retries + 1) * timeout)

        hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write.assert_called_once()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_configure_power_unit_returns_True_if_state_changes(self):
        """
        Тест проверяет, что функция HighLowTransceiver.configure_power_unit
        возвращает True, если состояние обоих выходов становится не '3'
        """

        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '4'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '4'

        hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write = MagicMock(return_value=True)

        self.assertEqual(hlTransceiver.configure_power_unit(unit_addr=unit_addr, retries=1), True)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_configure_power_unit_log_success_if_state_changes(self):
        """
        Тест проверяет, что функция HighLowTransceiver.configure_power_unit
        делает запись в лог о завершении конфигурации, если состояние
        обоих выходов становится не '3'
        """

        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write = MagicMock(return_value=True)

        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] = '4'
        hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] = '4'

        hlTransceiver.configure_power_unit(unit_addr=unit_addr, retries=1)

        ch1_humanreadable_state = hlTransceiver.humanreadable_states['4']
        ch2_humanreadable_state = ch1_humanreadable_state

        channel1_addr = 'ch:{}:1'.format(unit_addr)
        channel2_addr = 'ch:{}:2'.format(unit_addr)

        log_msg = 'Конфигурация модуля "{}" выполнена.' \
                  ' Текущее состояние выходов: "{}" - "{}", "{}" - "{}"'.format(
                   unit_addr, channel1_addr, ch1_humanreadable_state, channel2_addr, ch2_humanreadable_state)

        self.logger.write_log.assert_called_once_with(log_msg=log_msg, log_level='INFO')


class TestWriterTarget(HighLowTransceiverTestBase):
    """
    Тесты функции обработки команд от брокера
    HighLowTransceiver.writer_target
    """

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_writer_target_subscribes_to_correct_channels(self):
        """
        Тест проверяет, что функция HighLowTransceiver.writer_target
        создает подписчиков на каналы redis с командами изменения состояния
        и запросы потребления на модуле от модуля "Логика"
        """
        hlTransceiver = self.HighLowTransceiver()
        hlTransceiver.writer_target()
        cmd_channel = 'axiomLogic:cmd:state'
        req_channel = 'axiomLogic:request:consumption'
        subscriber = self.redis.StrictRedis().pubsub()
        subscriber.subscribe.assert_any_call(cmd_channel)
        subscriber.subscribe.assert_any_call(req_channel)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_writer_target_calls_subscriber_get_message_while_isRunning(self):
        """
        Тест проверяет, что функция HighLowTransceiver.writer_target
        читает сообщения с брокера пока HighLowTransceiver.isRunning=True
        """
        hlTransceiver = self.HighLowTransceiver()
        subscriber = self.redis.StrictRedis().pubsub()

        hlTransceiver.isRunning = True
        threading.Thread(target=hlTransceiver.writer_target).start()

        subscriber.get_message.assert_called()

        hlTransceiver.isRunning = False

        time.sleep(1)

        subscriber.get_message.reset_mock()

        time.sleep(0.1)

        subscriber.get_message.assert_not_called()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_writer_target_calls_set_ch_state_if_gets_cmd_for_ch(self):
        """
        Тест проверяет, что функция HighLowTransceiver.writer_target
        вызывает функцию установки нового состояния силового выхода
        если получает от логики команду с адресом силового выхода
        """
        hlTransceiver = self.HighLowTransceiver()
        hlTransceiver.set_ch_state = MagicMock()
        subscriber = self.redis.StrictRedis().pubsub()

        channel_addr = 'ch:m2:1'
        new_state_dict = {'status': '4'}
        cmd = {'addr': channel_addr, 'state': new_state_dict}
        msg = {'data': str(cmd)}
        subscriber.get_message.return_value = msg

        hlTransceiver.isRunning = True
        threading.Thread(target=hlTransceiver.writer_target).start()

        time.sleep(0.1)

        try:
            hlTransceiver.set_ch_state.assert_called_with(channel_addr=channel_addr, new_state_dict=new_state_dict)
        except AssertionError:
            raise
        finally:
            hlTransceiver.isRunning = False

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_writer_target_doesnt_call_set_ch_state_if_gets_cmd_not_for_ch(self):
        """
        Тест проверяет, что функция HighLowTransceiver.writer_target
        вызывает функцию установки нового состояния силового выхода
        если получает от логики команду не для силового выхода
        """
        hlTransceiver = self.HighLowTransceiver()
        hlTransceiver.set_ch_state = MagicMock()
        subscriber = self.redis.StrictRedis().pubsub()

        channel_addr = 'do:m2:1'
        new_state_dict = {'status': '4'}
        cmd = {'addr': channel_addr, 'state': new_state_dict}
        msg = {'data': str(cmd)}
        subscriber.get_message.return_value = msg

        hlTransceiver.isRunning = True
        threading.Thread(target=hlTransceiver.writer_target).start()

        time.sleep(0.1)

        try:
            hlTransceiver.set_ch_state.assert_not_called()
        except AssertionError:
            raise
        finally:
            hlTransceiver.isRunning = False

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_writer_target_calls_publish_unit_consumption_on_request(self):
        """
        Тест проверяет, что функция HighLowTransceiver.writer_target
        вызывает функцию отправки текущего потребления в каналах,
        при получении запроса от модуля "Логика"
        """
        hlTransceiver = self.HighLowTransceiver()

        hlTransceiver.publish_unit_consumption = MagicMock()

        subscriber1 = MagicMock()
        subscriber2 = MagicMock()

        subscriber1.get_message = MagicMock(return_value=None)
        subscriber2.get_message = MagicMock(return_value={'data': 'm1'})

        self.redis.StrictRedis().pubsub.side_effect = [subscriber1, subscriber2]

        hlTransceiver.isRunning = True
        threading.Thread(target=hlTransceiver.writer_target).start()

        time.sleep(0.01)

        try:
            hlTransceiver.publish_unit_consumption.assert_called_with('m1')
            pass
        except AssertionError:
            raise
        finally:
            hlTransceiver.isRunning = False


class TestRun(HighLowTransceiverTestBase):
    """
    Тесты функции HighLowTransceiver, запускающей основного рабочий
    цикл модуля взаимодействия с низкоуровневым ПО
    """

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_run_calls_reader_target(self):
        """
        Тест проверяет, что HighLowTransceiver.init_power_unit
        вызывает фукнцию HighLowTransceiver.reader_target
        """

        hlTransceiver = self.HighLowTransceiver()

        hlTransceiver.init_power_unit = MagicMock(return_value=True)
        hlTransceiver.reader_target = MagicMock()

        threading.Thread(target=hlTransceiver.run).start()

        time.sleep(0.1)

        hlTransceiver.isRunning = False

        hlTransceiver.reader_target.assert_called()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_run_log_on_start(self):
        """
        Тест проверяет, что функция HighLowTransceiver.run
        пишет в лог сообщение о запуске программы
        """

        hlTransceiver = self.HighLowTransceiver()

        threading.Thread(target=hlTransceiver.run).start()
        time.sleep(0.01)

        try:
            log_msg = 'Программа запущена'
            self.logger.write_log.assert_called_once_with(log_msg=log_msg, log_level='INFO')
        except AssertionError:
            raise
        finally:
            hlTransceiver.isRunning = False

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_sigterm_handler_log_on_exit(self):
        """
        Тест проверяет, что HighLowTransceiver.sigterm_handler
        пишет в лог сообщение о завершении программы
        """

        hlTransceiver = self.HighLowTransceiver()

        hlTransceiver.sigterm_handler(None, None)

        log_msg = 'Остановка программы'
        self.logger.write_log.assert_called_once_with(log_msg=log_msg, log_level='INFO')

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_sigterm_handler_set_isRunning_False(self):
        """
        Тест проверяет, что HighLowTransceiver.sigterm_handler
        останавливает работу программы, устанавливая isRunning = False
        """

        hlTransceiver = self.HighLowTransceiver()
        hlTransceiver.isRunning = True

        hlTransceiver.sigterm_handler(None, None)

        self.assertEqual(hlTransceiver.isRunning, False)

    # DEPRECATED
    @skip
    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_run_calls_init_power_unit_for_every_power_unit(self):
        """
        Тест проверяет, что для каждого силового модуля вызывается
        функция инициализации HighLowTransceiver.init_power_unit
        """

        hlTransceiver = self.HighLowTransceiver()

        hlTransceiver.init_power_unit = MagicMock(return_value=True)

        threading.Thread(target=hlTransceiver.run).start()

        time.sleep(0.1)

        hlTransceiver.isRunning = False

        for unit_addr in self.test_axiom_settings['power units']:
            hlTransceiver.init_power_unit.assert_any_call(unit_addr=unit_addr)


class TestPublishUnitConsumption(HighLowTransceiverTestBase):
    """
    Тесты функции HighLowTransceiver.publish_unit_consumption,
    публикующеий на брокер потребление в каналах модуля
    """

    @skip
    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    @patch('time.time', MagicMock(return_value=12345))
    def test_publish_unit_consumption_calculate_correct_consumption_value(self):
        """
        Тест проверяет, что фукнция публикуюет правильно рассчитанные
        значения потребления в каналах
        """

        hlTransceiver = self.HighLowTransceiver()

        unit_addr = list(self.test_axiom_settings['power units'].keys())[0]

        sample1 = sample2 = 4096
        angle1 = 15
        angle2 = 30

        hlTransceiver.power_units_state_dicts[unit_addr]['adc']['sample1'] = str(sample1)
        hlTransceiver.power_units_state_dicts[unit_addr]['adc']['sample2'] = str(sample2)

        hlTransceiver.power_units_state_dicts[unit_addr]['ld']['angle1'] = str(angle1)
        hlTransceiver.power_units_state_dicts[unit_addr]['ld']['angle2'] = str(angle2)

        I1 = (abs(1.5 - (3 * sample1/4096)) / 0.066) * 0.707
        I2 = (abs(1.5 - (3 * sample2/4096)) / 0.066) * 0.707

        phi1 = (angle1 * math.pi)/2000
        phi2 = (angle2 * math.pi)/2000

        P1 = 220 * I1 * math.cos(phi1)
        P2 = 220 * I2 * math.cos(phi2)

        hlTransceiver.publish_unit_consumption(unit_addr)

        hlTransceiver.redis.publish.assert_called_with(channel='axiomLowLevelCommunication:response:consumption',
                                                       message='{} {} {} 12345'.format(P1, P2, unit_addr))


class TestUpdateInputUnitState(HighLowTransceiverTestBase):
    """
    Тесты функции HighLowTransceiver.update_input_unit_state,
    обновляющей структуру состояния модулей ввода
    """

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_update_st(self):
        """
        Тест проверяет, что правильно обновляется
        поле 'st' структуры состояния модуля ввода
        """
        hlTransceiver = self.HighLowTransceiver()
        hlTransceiver.isRunning = True

        for unit_addr in self.test_axiom_settings['input units']:
            hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].read_generator = MagicMock()

            def side_effect():
                parcel = 'st 3 4 70{}\r\n'.format(unit_addr)
                yield parcel.encode()

            hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].read_generator.side_effect = side_effect

            hlTransceiver.update_input_unit_state(unit_addr=unit_addr)

            self.assertEqual(hlTransceiver.input_units_state_dicts[unit_addr]['st'], {'state': '3',
                                                                                      'signal': '4',
                                                                                      'addr': unit_addr,
                                                                                      'cnt': '70'})

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_update_adc(self):
        """
        Тест проверяет, что правильно обновляется
        поле 'adc' структуры состояния модуля ввода
        """
        hlTransceiver = self.HighLowTransceiver()
        hlTransceiver.isRunning = True

        for unit_addr in self.test_axiom_settings['input units']:
            hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].read_generator = MagicMock()

            def side_effect():
                parcel = 'adc 3743 103 65{}\r\n'.format(unit_addr)
                yield parcel.encode()

            hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].read_generator.side_effect = side_effect

            hlTransceiver.update_input_unit_state(unit_addr=unit_addr)

            self.assertEqual(hlTransceiver.input_units_state_dicts[unit_addr]['adc'], {'sample': '3743',
                                                                                       'addr': unit_addr,
                                                                                       'cnt': '65'})

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_log_rply(self):
        """
        Тест проверяет, что если тип посылки 'rply',
        сообщение от низкого уровня записывается в лог
        """
        hlTransceiver = self.HighLowTransceiver()
        hlTransceiver.isRunning = True

        for unit_addr in self.test_axiom_settings['input units']:
            hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].read_generator = MagicMock()

            reply = 'rply some reply text\r\n'.format(unit_addr)

            def side_effect():
                parcel = reply
                yield parcel.encode()

            hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].read_generator.side_effect = side_effect

            hlTransceiver.update_input_unit_state(unit_addr=unit_addr)

            log_msg = 'Сообщение от низкого уровня: {}'.format(reply.replace('\n', ''))

            self.logger.write_log.assert_called_with(log_msg=log_msg, log_level='INFO')


class TestPublishCurrentConsumption(HighLowTransceiverTestBase):
    """
    Тесты функции HighLowTransceiver.publish_current_consumption,
    отправляющей на брокер текущие значения электрических характеристик
    """

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    @patch('time.time', MagicMock(return_value=12345))
    def test_calculate_and_publish_correct_consumption_values(self):
        """
        Тест проверяет, что фукнция публикуюет правильно рассчитанные
        значения потребления в каналах для всех силовых модулей
        """

        self.HighLowTransceiver.load_settings = MagicMock(return_value=self.test_axiom_settings)
        hlTransceiver = self.HighLowTransceiver()

        voltage_sample = 3970
        current_sample1 = current_sample2 = 4096
        angle1 = 15
        angle2 = 30

        I1 = (abs(1.5 - (3 * current_sample1 / 4096)) / 0.066)
        I2 = (abs(1.5 - (3 * current_sample2 / 4096)) / 0.066)

        Um = abs(voltage_sample * (3 / 4096) - 1.5) * 253.557

        phi1 = (angle1 * math.pi) / 2000
        phi2 = (angle2 * math.pi) / 2000

        P1 = 2 * Um * I1 * math.cos(phi1)
        P2 = 2 * Um * I2 * math.cos(phi2)

        for unit_addr in self.test_axiom_settings['input units']:
            hlTransceiver.input_units_state_dicts[unit_addr]['adc']['sample'] = str(voltage_sample)

        for unit_addr in self.test_axiom_settings['power units']:

            hlTransceiver.power_units_state_dicts[unit_addr]['adc']['sample1'] = str(current_sample1)
            hlTransceiver.power_units_state_dicts[unit_addr]['adc']['sample2'] = str(current_sample2)

            hlTransceiver.power_units_state_dicts[unit_addr]['ld']['angle1'] = str(angle1)
            hlTransceiver.power_units_state_dicts[unit_addr]['ld']['angle2'] = str(angle2)

        hlTransceiver.publish_current_characteristics()

        for unit_addr in self.test_axiom_settings['power units']:
            consumption_message = {'P1': P1, 'P2': P2, 'addr': unit_addr, 'timestamp': 12345}

            hlTransceiver.redis.publish.assert_any_call(channel='axiomLowLevelCommunication:info:consumption',
                                                        message=json.dumps(consumption_message))

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    @patch('time.time', MagicMock(return_value=12345))
    def test_calculate_and_publish_correct_current_values(self):
        """
        Тест проверяет, что фукнция публикуюет правильно рассчитанные
        значения потребляемого тока в каналах для всех силовых модулей
        """

        self.HighLowTransceiver.load_settings = MagicMock(return_value=self.test_axiom_settings)
        hlTransceiver = self.HighLowTransceiver()

        voltage_sample = 3970
        current_sample1 = current_sample2 = 4096
        angle1 = 15
        angle2 = 30

        I1 = (abs(1.5 - (3 * current_sample1 / 4096)) / 0.066)
        I2 = (abs(1.5 - (3 * current_sample2 / 4096)) / 0.066)


        for unit_addr in self.test_axiom_settings['input units']:
            hlTransceiver.input_units_state_dicts[unit_addr]['adc']['sample'] = str(voltage_sample)

        for unit_addr in self.test_axiom_settings['power units']:

            hlTransceiver.power_units_state_dicts[unit_addr]['adc']['sample1'] = str(current_sample1)
            hlTransceiver.power_units_state_dicts[unit_addr]['adc']['sample2'] = str(current_sample2)

            hlTransceiver.power_units_state_dicts[unit_addr]['ld']['angle1'] = str(angle1)
            hlTransceiver.power_units_state_dicts[unit_addr]['ld']['angle2'] = str(angle2)

        hlTransceiver.publish_current_characteristics()

        for unit_addr in self.test_axiom_settings['power units']:
            current_message = {'I1': I1, 'I2': I2, 'addr': unit_addr, 'timestamp': 12345}

            hlTransceiver.redis.publish.assert_any_call(channel='axiomLowLevelCommunication:info:current',
                                                        message=json.dumps(current_message))\

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    @patch('time.time', MagicMock(return_value=12345))
    def test_calculate_and_publish_correct_voltage_values(self):
        """
        Тест проверяет, что фукнция публикуюет правильно рассчитанные
        значения напряжения на модуле ввода
        """

        self.HighLowTransceiver.load_settings = MagicMock(return_value=self.test_axiom_settings)
        hlTransceiver = self.HighLowTransceiver()

        voltage_sample = 3970
        current_sample1 = current_sample2 = 4096
        angle1 = 15
        angle2 = 30

        Um = abs(voltage_sample * (3 / 4096) - 1.5) * 253.557
        U = Um * 0.707

        for unit_addr in self.test_axiom_settings['input units']:
            hlTransceiver.input_units_state_dicts[unit_addr]['adc']['sample'] = str(voltage_sample)

        for unit_addr in self.test_axiom_settings['power units']:

            hlTransceiver.power_units_state_dicts[unit_addr]['adc']['sample1'] = str(current_sample1)
            hlTransceiver.power_units_state_dicts[unit_addr]['adc']['sample2'] = str(current_sample2)

            hlTransceiver.power_units_state_dicts[unit_addr]['ld']['angle1'] = str(angle1)
            hlTransceiver.power_units_state_dicts[unit_addr]['ld']['angle2'] = str(angle2)

        hlTransceiver.publish_current_characteristics()

        for unit_addr in self.test_axiom_settings['input units']:
            voltage_message = {'U': U, 'addr': unit_addr, 'timestamp': 12345}

            hlTransceiver.redis.publish.assert_any_call(channel='axiomLowLevelCommunication:info:voltage',
                                                        message=json.dumps(voltage_message))