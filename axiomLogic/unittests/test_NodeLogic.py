from unittest import TestCase
from unittest.mock import MagicMock, patch
import os
from axiomLogic.config import LOG_FILE_DIRECTORY, LOG_FILE_NAME, CONFIGURATION_FILES_PATH, \
    CONFIGURATION_FILE_NAME, INPUT_CMD_CHANNEL, INPUT_INFO_CHANNEL
from axiomLogic.nodes import Node, Simple220Widget, Simple220Device
import ujson
import redis
# Этот импорт здесь нужен, чтобы сделать patch, все очень запутанно...
from pubsub import pub


class NodeLogicTestBase(TestCase):

    test_configuration = [
        {
            'node_type': 'simple220widget',
            'identifier': 'we:1',
            'name': 'lamp',
            'function': 'light',
            'location': 'kitchen',
            'node_input': 'sd:1'
        },
        {
            'node_type': 'simple220device',
            'identifier': 'sd:1',
            'name': 'lamp',
            'function': 'light',
            'location': 'kitchen',
            'node_inputs': ['we:1'],
            'power_output': 'po:m2:1'
        },
    ]

    @patch('axiomLib.loggers.create_logger', MagicMock())
    @patch('pubsub.pub', MagicMock())
    def setUp(self):
        # Трюк, чтобы подменить функцию создающую логгер
        # и проверить, что она вызывается при создании объекта
        from axiomLib.loggers import create_logger
        self.create_logger = create_logger

        # Трюк, чтобы подменить модуль pubsub
        from pubsub import pub as pub_mock
        global pub
        pub = pub_mock

        global NodeLogic
        from axiomLogic.node_logic import NodeLogic as imported_NodeLogic
        NodeLogic = imported_NodeLogic


class TestInit(NodeLogicTestBase):
    """
    Юнит-тесты метода NodeLogic.__init__()
    """

    @patch('axiomLogic.node_logic.NodeLogic.load_configuration', MagicMock())
    def test_init_load_configuration(self):
        """
        Тест проверяет, что при создании экземляра класса NodeLogic
        вызывается метод загрузки конфигурации NodeLogic.load_configuration()
        """
        node_logic = NodeLogic()
        node_logic.load_configuration.assert_called_once()

    @patch('axiomLib.loggers.create_logger', MagicMock())
    def test_init_create_logger(self):
        """
        Тест проверяет, что при создании объекта NodeLogic
        вызывается метод, создания логгера с корректными аргументами
        """
        NodeLogic()
        self.create_logger.assert_called_with(
            logger_name='axiomLogic.node_logic',
            logfile_directory=LOG_FILE_DIRECTORY,
            logfile_name=LOG_FILE_NAME)

    @patch('axiomLib.loggers.create_logger', MagicMock())
    @patch('axiomLogic.node_logic.NodeLogic.load_configuration', MagicMock())
    def test_create_dictionary_with_all_node_types(self):
        """
        Тест проверяет, что у объекта логики есть словарь
        со всеми типами существующих узлов, определенных
        в модуле axiomLogic.nodes
        """
        nl = NodeLogic()
        for obj in globals().values():
            try:
                if issubclass(obj, Node) and obj is not Node:
                    self.assertTrue(obj in nl.node_types.values())
            except TypeError:
                pass


class TestLoadConfiguration(NodeLogicTestBase):
    """
    Юнит-тесты метода NodeLogic.load_configuration
    """

    @patch('builtins.open', MagicMock())
    def test_use_correct_file(self):
        """
        Тест проверяет, что при загрузке конфигурации открывается
        файл с правильным именем
        """
        NodeLogic()
        config_fname = os.path.join(CONFIGURATION_FILES_PATH, CONFIGURATION_FILE_NAME)
        open.assert_called_once_with(config_fname, 'r')

    @patch('builtins.open', MagicMock())
    @patch('ujson.load', MagicMock())
    def test_call_ujson_load_with_opened_file(self):
        """
        Тест проверяет, что выгрузка конфигурации происходит
        из открытого файла
        """
        config_fname = os.path.join(CONFIGURATION_FILES_PATH, CONFIGURATION_FILE_NAME)
        NodeLogic()
        with open(config_fname, 'r') as f:
            ujson.load.assert_called_with(f)

    @patch('builtins.open', MagicMock())
    @patch('ujson.load', MagicMock(return_value=NodeLogicTestBase.test_configuration))
    def test_return_correct_configuration(self):
        """
        Тест проверяет, что загружается правильная
        """
        nl = NodeLogic()
        self.assertEqual(nl.configuration, NodeLogicTestBase.test_configuration)

    @patch('builtins.open', MagicMock(side_effect=FileNotFoundError))
    @patch('axiomLib.loggers.create_logger', MagicMock())
    def test_log_error_if_file_not_found(self):
        """
        Тест проверяет, что если файл с конфигурацией не найден,
        пишется соответствующее сообщение в лог
        """
        nl = NodeLogic()
        config_fname = os.path.join(CONFIGURATION_FILES_PATH, CONFIGURATION_FILE_NAME)
        nl.logger.error.assert_called_with('Нет файла конфигурации {}'.format(config_fname))

    @patch('builtins.open', MagicMock())
    @patch('ujson.load', MagicMock(return_value={}))
    def test_log_error_if_configuration_not_a_list(self):
        """
        Тест проверяет, что если загруженная конфигурация - это не список,
        в лог пишется сообщение об ошибке
        """
        nl = NodeLogic()
        nl.logger.error.assert_called_with('Неверный формат файла конфигурации')

    @patch('builtins.open', MagicMock(return_value='invalid JSON'))
    def test_log_error_if_not_valid_JSON(self):
        """
        Тест проверяет, что если содержимое файла конфигурации не является
        корректным JSON, в лог пишется сообщение об ошибке
        """
        nl = NodeLogic()
        self.assertTrue('Ошибка при загрузке конфигурации из файла:' in nl.logger.error.call_args_list[0].__str__())


class TestRun(NodeLogicTestBase):
    """
    Юнит-тесты метода NodeLogic.run()
    """

    def setUp(self):
        super().setUp()
        global NodeLogic
        NodeLogic.load_configuration = lambda self: NodeLogicTestBase.test_configuration

    def test_calls_dispatcher(self):
        """
        Тест проверяет, что метод NodeLogic.run() вызывает метод NodeLogic.dispatcher()
        """
        nl = NodeLogic()
        nl.dispatcher = MagicMock()
        nl.run()
        nl.dispatcher.assert_called_once()


class TestDispatcher(NodeLogicTestBase):
    """
    Юнит-тесты метода NodeLogic.dispatcher()
    """
    def setUp(self):
        super().setUp()
        global NodeLogic
        NodeLogic.load_configuration = lambda self: NodeLogicTestBase.test_configuration

    @patch('redis.StrictRedis', MagicMock())
    def test_subscribes_input_info_channel(self):
        """
        Тест проверяет, что диспетчер подписывается на информационные
        сообщения от модуля "Взаимодействие с низким уровнем"
        """
        nl = NodeLogic()
        nl.run()
        redis_connection_mock = redis.StrictRedis(decode_responses=True)
        subscriber_mock = redis_connection_mock.pubsub()
        subscriber_mock.subscribe.assert_any_call(INPUT_INFO_CHANNEL)

    @patch('redis.StrictRedis', MagicMock())
    def test_subscribes_input_cmd_channel(self):
        """
        Тест проверяет, что диспетчер подписывается на командные
        сообщения от модуля "Веб-сервер"
        """
        nl = NodeLogic()
        nl.run()
        redis_connection_mock = redis.StrictRedis(decode_responses=True)
        subscriber_mock = redis_connection_mock.pubsub()
        subscriber_mock.subscribe.assert_any_call(INPUT_CMD_CHANNEL)

    @patch('redis.StrictRedis', MagicMock())
    def test_dispatch_msg_from_low_level(self):
        """
        Тест проверяет, что сообщение, полученное от модуля
        "Взаимодействие с низким уровнем", разбирается и
        отправляется в соответствующий канал внутреннего брокера
        """
        redis_connection_mock = redis.StrictRedis(decode_responses=True)
        subscriber_mock = redis_connection_mock.pubsub()
        test_data = {'id': 'ch:m1:1', 'state': {'status': '4'}}
        subscriber_mock.listen.return_value = [{'channel': INPUT_INFO_CHANNEL, 'data': ujson.dumps(test_data)}]
        nl = NodeLogic()
        nl.run()
        pub.sendMessage.assert_called_with(test_data['id'], state=test_data['state'])

    @patch('redis.StrictRedis', MagicMock())
    def test_dispatch_msg_from_webserver(self):
        """
        Тест проверяет, что сообщение, полученное от
        модуля "Веб-сервер", разбирается и отправляется
        в соответствующий канал внутреннего брокера
        """
        redis_connection_mock = redis.StrictRedis(decode_responses=True)
        subscriber_mock = redis_connection_mock.pubsub()
        test_data = {'id': 'we:1', 'state': {'status': '4'}}
        subscriber_mock.listen.return_value = [{'channel': INPUT_CMD_CHANNEL, 'data': ujson.dumps(test_data)}]
        nl = NodeLogic()
        nl.run()
        pub.sendMessage.assert_called_with(test_data['id'], state=test_data['state'])


class TestCreateNodes(NodeLogicTestBase):
    """
    Юнит-тесты метода NodeLogic.dispatcher()
    """

    def setUp(self):
        super().setUp()
        global NodeLogic, Simple220Device, Simple220Widget
        NodeLogic.load_configuration = lambda self: NodeLogicTestBase.test_configuration
        Simple220Device.load_state = lambda self: {'status': '4'}
        Simple220Widget.load_state = lambda self: {'status': '4'}

    @patch('redis.StrictRedis', MagicMock())
    def test_log_error_if_node_args_is_not_a_dict(self):
        """
        Тест проверяет, что если элемент списка configuration
        не является словарем, в лог пишется сообщение об ошибке
        """
        nl = NodeLogic()
        invalid_element = 'invalid element'
        nl.configuration.append(invalid_element)
        nl.create_nodes(nl.configuration)
        nl.logger.error.assert_called_once_with('Неверный формат конфигурации блока логики: {}'.format(invalid_element))

    @patch('redis.StrictRedis', MagicMock())
    def test_log_error_if_node_type_is_not_defined(self):
        """
        Тест проверяет, что если в описании блока логики
        не задан тип блока, в лог пишется сообщение об ошибке
        """
        nl = NodeLogic()
        nl.configuration[0].pop('node_type')
        nl.create_nodes(nl.configuration)
        nl.logger.error.assert_called_once_with(
            'Не задан параметр "node_type" для блока логики: {}'.format(nl.configuration[0]))

    @patch('redis.StrictRedis', MagicMock())
    def test_log_error_if_identifier_is_not_set(self):
        """
        Тест проверяет, что если в описании блока логики
        не задан идентификатор, в лог пишется сообщение об ошибке
        """
        nl = NodeLogic()
        nl.configuration[0].pop('identifier')
        nl.create_nodes(nl.configuration)
        nl.logger.error.assert_called_once_with(
            'Не задан параметр "identifier" для блока логики: {}'.format(nl.configuration[0]))

    @patch('redis.StrictRedis', MagicMock())
    def test_log_error_if_identifier_is_already_used(self):
        """
        Тест проверяет, что если в описании блока логики
        использован идентификатор, для которого уже создан
        другой блок логики, в лог пишется сообщение об ошибке
        """
        nl = NodeLogic()
        nl.nodes.clear()
        nl.configuration.append(nl.configuration[0])
        nl.create_nodes(nl.configuration)
        nl.logger.error.assert_called_once_with(
            'Повторное использование идентификатора для блока логики: {}'.format(nl.configuration[0]))

    @patch('redis.StrictRedis', MagicMock())
    def test_log_error_if_cant_create_node(self):
        """
        Тест проверяет, что если возникает ошибка при попытке создать
        объект блока логики по заданной конфигурации, в лог пишется
        сообщение об ошибке
        """
        nl = NodeLogic()
        nl.configuration[0].pop('identifier')
        nl.create_nodes(nl.configuration)
        self.assertTrue('Ошибка при создании блока логики' in nl.logger.error.call_args_list[0].__str__())

    @patch('redis.StrictRedis', MagicMock())
    def test_create_all_nodes(self):
        """
        Тест проверяет, что для каждого элемента списка конфигурации
        создается объект блока логики
        """
        nl = NodeLogic()

        for node_description in nl.configuration:
            self.assertIn(node_description['identifier'], nl.nodes.keys())

            node_class = nl.node_types[node_description['node_type']]
            node = nl.nodes[node_description['identifier']]
            self.assertIsInstance(node, node_class)