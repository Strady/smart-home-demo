import copy
import json
import sqlite3
import sys
import threading
import time
import ujson
from unittest import TestCase, skip
from unittest.mock import MagicMock, patch
import builtins


class ConfigurableLogicTestBase(TestCase):

    @property
    def test_axiom_settings(self):
        """
        :return: Псевдо настройки для использования в тестах
        """
        return {
            'root directory': '/root/directory',
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

    def setUp(self):

        from axiomLogic import logger
        logger.write_log = MagicMock()
        self.logger = logger

        # <editor-fold desc="Настройка изоляции от sqlite3">
        sqlite3.connect = MagicMock(spec=sqlite3.connect)
        self.connection = sqlite3.connect()
        self.cursor = self.connection.cursor()
        # </editor-fold>

        # <editor-fold desc="Настройка изоляции от Redis">
        class SubscirberMock(MagicMock):
            """
            Имитирует подписчик. Возвращает разные значения
            в зависимости от того, на какой канал подписан.
            Возвращаемые значения задаются в тестах как
            атрибуты класса
            """

            axiomWebserver_cmd_state_return_value = None
            axiomLowLevelCommunication_info_state_return_value = None

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.channel = None

            def subscribe(self, channel):
                self.channel = channel

            def listen(self):
                if self.channel == 'axiomWebserver:cmd:state':
                    yield self.__class__.axiomWebserver_cmd_state_return_value
                elif self.channel == 'axiomLowLevelCommunication:info:state':
                    yield self.__class__.axiomLowLevelCommunication_info_state_return_value

        self.SubscirberMockClass = SubscirberMock

        from axiomLogic.base_logic import redis
        redis.StrictRedis = MagicMock(spec=redis.StrictRedis)
        self.redis = redis.StrictRedis()
        self.redis.pubsub.side_effect = lambda *args, **kwargs: self.SubscirberMockClass()
        # </editor-fold>

        builtins.open = MagicMock(spec=builtins.open)
        from axiomLogic.configurable_logic import ConfigurableLogic

        self.ConfigurableLogic = ConfigurableLogic

        # словарь настроек, с которыми работают тесты
        # self.test_axiom_settings = {
        #     'root directory': '/root/directory',
        #     'hardware units': {
        #         'm5': ['m1'],
        #         'm6': ['m2'],
        #         'm7': ['m3'],
        #         'm8': ['m4'],
        #     },
        #     'power units': {
        #         'm1': '/dev/ttyS0',
        #         'm2': '/dev/ttyS1',
        #         'm3': '/dev/ttyS2',
        #         'm4': '/dev/ttyS3',
        #     },
        #     'power units thresholds': {
        #         'm1': [1, 2],
        #         'm2': [3, 4],
        #         'm3': [5, 6],
        #         'm4': [7, 8],
        #     },
        #     'input units': {
        #         'm5': '/dev/ttyS4',
        #         'm6': '/dev/ttyS5',
        #         'm7': '/dev/ttyS6',
        #         'm8': '/dev/ttyS7',
        #     }
        # }

        self.test_configurator_output = [
                                          {'function': 'configurable_function_1', 'args': ['arg1']},
                                          {'function': 'configurable_function_2', 'args': ['arg2']},
                                          {'function': 'configurable_function_3', 'args': ['arg3']},
                                        ]


class TestCreateBundles(ConfigurableLogicTestBase):
    """
    Тесты функции ConfigurableLogic.create_bundles
    """

    def test_creates_bundles_for_all_configured_functions(self):
        """
        Тест проверяет, что для каждой привязки в конфигурационном
        файле создается связка вида:

        "{'function': <имя конфигурационной функции>,
        'args': <аргументы конфигурационной функции>}"
        """
        json.load = MagicMock(side_effect=[self.test_axiom_settings,
                                           self.test_configurator_output])

        # Добавляем псевдо конфигурационные функции в класс
        for bundle in self.test_configurator_output:
            funcname = bundle['function']
            exec('self.ConfigurableLogic.{} = MagicMock()'.format(funcname))
        cl = self.ConfigurableLogic()

        result_bundles = []

        for bundle in self.test_configurator_output:
            result_bundles.append(ujson.dumps(bundle))

        self.assertEqual(cl.create_workers(), result_bundles)

        # Удаляем псевдо функции из класса
        for bundle in self.test_configurator_output:
            funcname = bundle['function']
            exec('del self.ConfigurableLogic.{}'.format(funcname))

    def test_doesnt_include_not_existing_func_in_bundle(self):
        """
        Тест проверяет, что если в конфигурационном файле задана
        привязка с использованием неопределенной в классе ConfigurableLogic
        функцией, то она не будет включена в создаваемый функцией
        create_bundles список
        """

        json.load = MagicMock(side_effect=[self.test_axiom_settings,
                                           self.test_configurator_output])

        # Добавляем псевдо конфигурационные функции в класс
        # Кроме несуществующей
        for bundle in self.test_configurator_output[:-1]:
            funcname = bundle['function']
            exec('self.ConfigurableLogic.{} = MagicMock()'.format(funcname))
        cl = self.ConfigurableLogic()

        result_bundles = []

        for bundle in self.test_configurator_output[:-1]:
            result_bundles.append(ujson.dumps(bundle))

        self.assertEqual(cl.create_workers(), result_bundles)

        # Удаляем псевдо функции из класса
        for bundle in self.test_configurator_output[:-1]:
            funcname = bundle['function']
            exec('del self.ConfigurableLogic.{}'.format(funcname))

    def test_logs_error_if_config_func_doesnt_exist(self):
        """
        Тест, проверяет, что функция ConfigurableLogic.create_bundles
        логирует ошибку, если в конфигурационном файле задана функция,
        неопределенная в классе
        """
        json.load = MagicMock(side_effect=[self.test_axiom_settings,
                                           self.test_configurator_output])

        # Добавляем псевдо конфигурационные функции в класс
        # Кроме несуществующей
        for bundle in self.test_configurator_output[:-1]:
            funcname = bundle['function']
            exec('self.ConfigurableLogic.{} = MagicMock()'.format(funcname))
        cl = self.ConfigurableLogic()

        cl.create_workers()

        non_existing_func = self.test_configurator_output[-1]['function']

        log_msg = 'Функции {} нет в списке конфигурационных функций'.format(non_existing_func)
        self.logger.write_log.assert_called_once_with(log_msg=log_msg, log_level='ERROR')

        # Удаляем псевдо функции из класса
        for bundle in self.test_configurator_output[:-1]:
            funcname = bundle['function']
            exec('del self.ConfigurableLogic.{}'.format(funcname))


class TestConfigurableConnectCheckboxToCh(ConfigurableLogicTestBase):

    def test_publish_cmd_on_message_from_webserver(self):
        """
        Тест проверяет, что по сообщению от веб-сервера формируется и
        публикуется на брокер команда для модуля "Взаимодействие с
        низким уровнем" на установку нового состояния выхода силового модуля
        """

        we_addr = 'we:1'
        ch_addr = 'ch:m1:1'

        # Настройки
        json.load = MagicMock(side_effect=[self.test_axiom_settings])

        # Сообщение, полученное от веб-сервера
        data = ujson.dumps({'id': we_addr, 'state': {'status': '5'}})

        # Настраиваем подписчик
        self.SubscirberMockClass.axiomWebserver_cmd_state_return_value = {'data': data}

        cl = self.ConfigurableLogic()

        cl.isRunning = True

        threading.Thread(target=cl.configurable_connect_checkbox_to_ch, args=(we_addr, ch_addr)).start()

        cl.isRunning = False

        time.sleep(0.01)

        # Сообщение, которое должно быть отправлено на брокер
        message = ujson.dumps({'addr': ch_addr, 'state': {'status': '5'}})

        self.redis.publish.assert_called_once_with('axiomLogic:cmd:state', message)

    def test_log_on_receiving_cmd_message_from_webserver(self):
        """
        Тест проверяет, что при получении от веб-сервера команды
        на изменение состояния выхода силового модуля пишется
        сообщение в лог
        """

        we_addr = 'we:1'
        ch_addr = 'ch:m1:1'

        # Настройки
        json.load = MagicMock(side_effect=[self.test_axiom_settings])

        # Сообщение, полученное от веб-сервера
        data = ujson.dumps({'id': we_addr, 'state': {'status': '5'}})

        # Настраиваем подписчик
        self.SubscirberMockClass.axiomWebserver_cmd_state_return_value = {'data': data}

        cl = self.ConfigurableLogic()

        cl.isRunning = True

        threading.Thread(target=cl.configurable_connect_checkbox_to_ch, args=(we_addr, ch_addr)).start()

        cl.isRunning = False

        time.sleep(0.01)

        log_msg = 'Получена команда от модуля "Веб-сервер": "{}"'.format({'id': we_addr, 'state': {'status': '5'}})

        self.logger.write_log.assert_any_call(log_msg=log_msg, log_level='INFO')

    def test_log_on_publishing_cmd_message_for_low_level(self):
        """
        Тест проверяет, что при публикации командного сообщения на
        брокер в лог пишется соответствующее сосбщение
        """

        we_addr = 'we:1'
        ch_addr = 'ch:m1:1'

        # Настройки
        json.load = MagicMock(side_effect=[self.test_axiom_settings])

        # Сообщение, полученное от веб-сервера
        data = ujson.dumps({'id': we_addr, 'state': {'status': '5'}})

        # Настраиваем подписчик
        self.SubscirberMockClass.axiomWebserver_cmd_state_return_value = {'data': data}

        cl = self.ConfigurableLogic()

        cl.isRunning = True

        threading.Thread(target=cl.configurable_connect_checkbox_to_ch, args=(we_addr, ch_addr)).start()

        cl.isRunning = False

        time.sleep(0.01)

        log_msg = 'Отправлена команда на модуль "Взаимодействие с низким уровнем": "{}"'.format(
            {'addr': ch_addr, 'state': {'status': '5'}})

        self.logger.write_log.assert_any_call(log_msg=log_msg, log_level='INFO')

    def test_doesnt_publish_cmd_on_message_from_webserver_with_wrong_we_addr(self):
        """
        Тест проверяет, что если получено сообщение от веб-сервера для
        другого адреса ВЭК, командное сообщение на брокер не публикуется
        """

        we_addr = 'we:1'
        ch_addr = 'ch:m1:1'

        # Настройки
        json.load = MagicMock(side_effect=[self.test_axiom_settings])

        # Сообщение, полученное от веб-сервера
        data = ujson.dumps({'id': 'we:2', 'state': {'status': '5'}})

        # Настраиваем подписчик
        self.SubscirberMockClass.axiomWebserver_cmd_state_return_value = {'data': data}

        cl = self.ConfigurableLogic()

        cl.isRunning = True

        threading.Thread(target=cl.configurable_connect_checkbox_to_ch, args=(we_addr, ch_addr)).start()

        cl.isRunning = False

        time.sleep(0.01)

        self.redis.publish.assert_not_called

    def test_doesnt_publish_cmd_on_incorrect_message_from_webserver(self):
        """
        Тест проверяет, что если полученное от веб-сервера сообщение
        содержит некорректные данные поток не падает и сообщения
        на брокер не публикуются
        """

        we_addr = 'we:1'
        ch_addr = 'ch:m1:1'

        # Настройки
        json.load = MagicMock(side_effect=[self.test_axiom_settings])

        # Сообщение, полученное от веб-сервера
        data = 'incorrect data'

        # Настраиваем подписчик
        self.SubscirberMockClass.axiomWebserver_cmd_state_return_value = {'data': data}

        cl = self.ConfigurableLogic()

        cl.isRunning = True

        threading.Thread(target=cl.configurable_connect_checkbox_to_ch, args=(we_addr, ch_addr)).start()

        cl.isRunning = False

        time.sleep(0.01)

        self.redis.publish.assert_not_called

    def test_publish_info_msg_on_info_msg_from_low_level(self):
        """
        Тест проверяет, что при получении информационного сообщения
        от модуля "Взаимодействие с низким уровнем" об изменении
        состояния подконтрольного выхода силового модуля публикуется
        информационное сообщение для веб-сервера
        """

        we_addr = 'we:1'
        ch_addr = 'ch:m1:1'

        # Настройки
        json.load = MagicMock(side_effect=[self.test_axiom_settings])

        # Сообщение, полученное от модуля "Взаимодействие с низким уровнем"
        data = ujson.dumps({'addr': ch_addr, 'state': {'status': '5'}})

        # Настраиваем подписчик
        self.SubscirberMockClass.axiomLowLevelCommunication_info_state_return_value = {'data': data}

        cl = self.ConfigurableLogic()

        cl.isRunning = True

        threading.Thread(target=cl.configurable_connect_checkbox_to_ch, args=(we_addr, ch_addr)).start()

        cl.isRunning = False

        time.sleep(0.01)

        # Сообщение, которое должно быть отправлено на брокер
        message = ujson.dumps({'id': we_addr, 'state': {'status': '5'}})

        self.redis.publish.assert_called_once_with('axiomLogic:info:state', message)

    def test_log_on_receiving_info_msg_from_low_level(self):
        """
        Тест проверяет, что при получении информационного сообщения
        от модуля "Взаимодействие с низким уровнем" об изменении
        состояния подконтрольного выхода силового модуля делается
        запись в лог
        """
        we_addr = 'we:1'
        ch_addr = 'ch:m1:1'

        # Настройки
        json.load = MagicMock(side_effect=[self.test_axiom_settings])

        # Сообщение, полученное от модуля "Взаимодействие с низким уровнем"
        data = ujson.dumps({'addr': ch_addr, 'state': {'status': '5'}})

        # Настраиваем подписчик
        self.SubscirberMockClass.axiomLowLevelCommunication_info_state_return_value = {'data': data}

        cl = self.ConfigurableLogic()

        cl.isRunning = True

        threading.Thread(target=cl.configurable_connect_checkbox_to_ch, args=(we_addr, ch_addr)).start()

        cl.isRunning = False

        time.sleep(0.01)

        log_msg = 'Получено информационное сообщение от модуля' \
                  ' "Взаимодействие с низким уровнем": "{}"'.format({'addr': ch_addr, 'state': {'status': '5'}})
        self.logger.write_log.assert_any_call(log_msg=log_msg, log_level='INFO')

    def test_log_on_publishing_info_msg_for_webserver(self):
        """
        Тест проверяет, что делается запись в лог при отправке
        информационного сообщения на модуль "Веб-сервер"
        """
        we_addr = 'we:1'
        ch_addr = 'ch:m1:1'

        # Настройки
        json.load = MagicMock(side_effect=[self.test_axiom_settings])

        # Сообщение, полученное от модуля "Взаимодействие с низким уровнем"
        data = ujson.dumps({'addr': ch_addr, 'state': {'status': '5'}})

        # Настраиваем подписчик
        self.SubscirberMockClass.axiomLowLevelCommunication_info_state_return_value = {'data': data}

        cl = self.ConfigurableLogic()

        cl.isRunning = True

        threading.Thread(target=cl.configurable_connect_checkbox_to_ch, args=(we_addr, ch_addr)).start()

        cl.isRunning = False

        time.sleep(0.01)

        # Логируем отправку информационного сообещния
        log_msg = 'Отправлено информационное сообщение на модуль "Веб-сервер": "{}"'.format(
            {'id': we_addr, 'state': {'status': '5'}})
        self.logger.write_log.assert_any_call(log_msg=log_msg, log_level='INFO')

    def test_doesnt_publish_info_msg_on_info_msg_from_low_level_for_wrong_ch(self):
        """
        Тест проверяет, что при получении информационного сообщения
        от модуля "Взаимодействие с низким уровнем" об изменении
        состояния неподконтрольного выхода силового модуля, не
        публикуется информационных сообщений для веб-сервера
        """

        we_addr = 'we:1'
        ch_addr = 'ch:m1:1'

        # Настройки
        json.load = MagicMock(side_effect=[self.test_axiom_settings])

        # Сообщение, полученное от модуля "Взаимодействие с низким уровнем"
        data = ujson.dumps({'addr': 'ch:m1:2', 'state': {'status': '5'}})

        # Настраиваем подписчик
        self.SubscirberMockClass.axiomLowLevelCommunication_info_state_return_value = {'data': data}

        cl = self.ConfigurableLogic()

        cl.isRunning = True

        threading.Thread(target=cl.configurable_connect_checkbox_to_ch, args=(we_addr, ch_addr)).start()

        cl.isRunning = False

        time.sleep(0.01)

        self.redis.publish.assert_not_called()

    def test_doesnt_publish_info_msg_on_incorrect_info_msg_from_low_level(self):
        """
        Тест проверяет, что при получении некорректного информационного сообщения
        от модуля "Взаимодействие с низким уровнем" не публикуется информационных
        сообщений для веб-сервера
        """

        we_addr = 'we:1'
        ch_addr = 'ch:m1:1'

        # Настройки
        json.load = MagicMock(side_effect=[self.test_axiom_settings])

        # Сообщение, полученное от модуля "Взаимодействие с низким уровнем"
        data = 'incorrect data'

        # Настраиваем подписчик
        self.SubscirberMockClass.axiomLowLevelCommunication_info_state_return_value = {'data': data}

        cl = self.ConfigurableLogic()

        cl.isRunning = True

        threading.Thread(target=cl.configurable_connect_checkbox_to_ch, args=(we_addr, ch_addr)).start()

        cl.isRunning = False

        time.sleep(0.01)

        self.redis.publish.assert_not_called()

    @patch('time.time', MagicMock(return_value=12345))
    def test_write_event_to_the_journal_DB(self):
        """
        Тест проверяет, что при получении информационного сообщения
        от модуля "Взаимодействие с низким уровнем" об изменении
        состояния подконтрольного выхода силового модуля в бд
        с журналом делается соответствующая запись
        """

        we_addr = 'we:1'
        ch_addr = 'ch:m1:1'

        self.cursor.execute().fetchone.return_value = ['we name']

        # Настройки
        json.load = MagicMock(return_value=self.test_axiom_settings)

        # Сообщение, полученное от модуля "Взаимодействие с низким уровнем" (включение)
        data = ujson.dumps({'addr': ch_addr, 'state': {'status': '5'}})

        # Настраиваем подписчик
        self.SubscirberMockClass.axiomLowLevelCommunication_info_state_return_value = {'data': data}

        cl = self.ConfigurableLogic()

        cl.isRunning = True

        threading.Thread(target=cl.configurable_connect_checkbox_to_ch, args=(we_addr, ch_addr)).start()

        cl.isRunning = False

        time.sleep(0.01)

        sql_entry = 'INSERT INTO log_entries (timestamp, event) VALUES ({}, "we name включен")'.format(time.time())

        self.cursor.execute.assert_any_call(sql_entry)
        self.cursor.execute.reset_mock()

        del(cl)


        # Сообщение, полученное от модуля "Взаимодействие с низким уровнем" (выключение)
        data = ujson.dumps({'addr': ch_addr, 'state': {'status': '4'}})

        # Настраиваем подписчик
        self.SubscirberMockClass.axiomLowLevelCommunication_info_state_return_value = {'data': data}

        cl = self.ConfigurableLogic()

        cl.isRunning = True

        threading.Thread(target=cl.configurable_connect_checkbox_to_ch, args=(we_addr, ch_addr)).start()

        cl.isRunning = False

        time.sleep(0.01)

        sql_entry = 'INSERT INTO log_entries (timestamp, event) VALUES ({}, "we name выключен")'.format(time.time())

        self.cursor.execute.assert_any_call(sql_entry)

    def test_query_name_for_we_addr(self):
        """
        Тест проверяет, что для записи сообщений в журнал
        из базы данных читается имя подконтрольного ВЭК
        """

        we_addr = 'we:1'
        ch_addr = 'ch:m1:1'

        # Настройки
        json.load = MagicMock(return_value=self.test_axiom_settings)

        cl = self.ConfigurableLogic()

        cl.isRunning = True

        threading.Thread(target=cl.configurable_connect_checkbox_to_ch, args=(we_addr, ch_addr)).start()

        cl.isRunning = False

        time.sleep(0.01)

        sql_query = 'SELECT name FROM web_element WHERE addr == "{}"'.format(we_addr)

        self.cursor.execute.assert_called_once_with(sql_query)
