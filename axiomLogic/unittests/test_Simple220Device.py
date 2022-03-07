import ujson
from pubsub import pub
from unittest import TestCase, skip
from unittest.mock import MagicMock, patch
from axiomLogic.config import *

class Simple220DeviceTestBase(TestCase):
    pass
    pass

class TestInit(Simple220DeviceTestBase):
    """
    Юнит-тесты метода Simple220Device.__init__()
    """

    @skip
    @patch('pubsub.pub', MagicMock())
    def test_subscribes_state_info_listener_to_its_channel(self):
        """
        Тест проверяет, что метод Simple220Device.state_info_listener() подписывается
        на соответствующий объекту канал брокера (имя канала - идентификатор выхода силового модуля)

        Тест нужно запускать отдельно (убрать @skip)
        """
        from pubsub import pub
        from axiomLogic.configurable_nodes import Simple220Device
        device = Simple220Device(identifier='sd:1', node_inputs=['we:1'], power_output='po:m2:1', function='освещение',
                                 location='кухня', name='лампа')
        pub.subscribe.assert_called_with(topicName=device.power_output, listener=device.state_info_listener)

    @skip
    @patch('pubsub.pub', MagicMock())
    def test_subscribes_input_listener_to_all_inputs(self):
        """
        Тест проверяет, что метод Simple220Device.input_listener() подписывается
        на сообщения от каждого входа блока

        Тест нужно запускать отдельно (убрать @skip)
        """
        from pubsub import pub
        from axiomLogic.configurable_nodes import Simple220Device
        device = Simple220Device(identifier='sd:1', node_inputs=['we:1', 'we:2'], power_output='po:m2:1', function='освещение',
                                 location='кухня', name='лампа')
        for node_input in device.inputs:
            pub.subscribe.assert_any_call(topicName=node_input + '_out', listener=device.input_listener)


class TestStateInfoListener(Simple220DeviceTestBase):
    """
    Юнит-тесты метода Simple220Device.state_info_listener()
    """

    def test_calls_handle_state_info(self):
        """
        Тест проверяет, что вызывается метод Simple220Device.handle_state_info
        """
        from axiomLogic.configurable_nodes import Simple220Device
        device = Simple220Device(identifier='sd:1', node_inputs=['we:1'], power_output='po:m2:1', function='освещение',
                                 location='кухня', name='лампа')
        device.handle_state_info = MagicMock()

        state_msg = {'status': '4'}
        device.state_info_listener(state_msg)
        device.handle_state_info.assert_called_once_with(state_msg)


class TestLoadState(Simple220DeviceTestBase):
    """
    Юнит-тесты метода Simple220Device.load_state()
    """

    @patch('axiomLib.loggers.create_logger', MagicMock())
    @patch('redis.StrictRedis', MagicMock())
    def test_returns_saved_in_redis_state(self):
        """
        Тест проверяет, что если в Redis есть корректное
        сохраненное состояние, то возвращается оно
        """
        import redis
        redis = redis.StrictRedis()
        saved_state = {"status": "5"}
        redis.get = MagicMock(return_value=ujson.dumps(saved_state))
        from axiomLogic.configurable_nodes import Simple220Device

        device = Simple220Device(identifier='sd:1', node_inputs=['we:1'], power_output='po:m2:1', function='освещение',
                                 location='кухня', name='лампа')
        self.assertEqual(saved_state, device.load_state())

    @patch('axiomLib.loggers.create_logger', MagicMock())
    @patch('redis.StrictRedis', MagicMock())
    def test_saves_default_state_if_there_is_no_saved(self):
        """
        Тест проверяет, что если в Redis нет сохраненного
        ранее значения, сохраняется значение по умолчанию
        """
        import redis
        redis = redis.StrictRedis()
        redis.get = MagicMock(return_value=None)
        from axiomLogic.configurable_nodes import Simple220Device

        device = Simple220Device(identifier='sd:1', node_inputs=['we:1'], power_output='po:m2:1', function='освещение',
                                 location='кухня', name='лампа')

        default_state = {'status': '4'}
        redis.set.assert_called_once_with(device.id, ujson.dumps(default_state))

    @patch('axiomLib.loggers.create_logger', MagicMock())
    @patch('redis.StrictRedis', MagicMock())
    def test_returns_default_state_if_there_is_no_saved(self):
        """
        Тест проверяет, что если в Redis нет сохраненного
        ранее значения, возвращается значение по умолчанию
        """
        import redis
        redis = redis.StrictRedis()
        redis.get = MagicMock(return_value=None)
        from axiomLogic.configurable_nodes import Simple220Device

        device = Simple220Device(identifier='sd:1', node_inputs=['we:1'], power_output='po:m2:1', function='освещение',
                                 location='кухня', name='лампа')

        default_state = {'status': '4'}
        self.assertEqual(default_state, device.load_state())


class TestValidateState(Simple220DeviceTestBase):
    """
    Юнит-тесты метода Simple220Device.validate_saved_state()
    """

    # @patch('axiomLib.loggers.create_logger', MagicMock())
    # @patch('redis.StrictRedis', MagicMock())
    # def test_return_false_if_saved_state_isnt_a_json(self):
    #     """
    #     Тест проверяет, что если загруженное из Redis значение
    #     не является корректным JSON, возвращается False
    #     """
    #     import redis
    #     redis = redis.StrictRedis()
    #     saved_state = 'not a JSON'
    #     redis.get = MagicMock(return_value=saved_state)
    #     from axiomLogic.configurable_nodes import Simple220Device
    #
    #     device = Simple220Device(identifier='sd:1', node_inputs=['we:1'], power_output='po:m2:1', function='освещение',
    #                              location='кухня', name='лампа')
    #
    #     self.assertEqual(False, device.validate_state(saved_state))
    #
    # @patch('axiomLib.loggers.create_logger', MagicMock())
    # @patch('redis.StrictRedis', MagicMock())
    # def test_log_error_if_saved_state_isnt_a_json(self):
    #     """
    #     Тест проверяет, что если загруженное из Redis значение
    #     не является корректным JSON, в лог пишется сообщение об ошибке
    #     """
    #     import redis
    #     redis = redis.StrictRedis()
    #     saved_state = 'not a JSON'
    #     redis.get = MagicMock(return_value=saved_state)
    #     from axiomLogic.configurable_nodes import Simple220Device
    #
    #     device = Simple220Device(identifier='sd:1', node_inputs=['we:1'], power_output='po:m2:1', function='освещение',
    #                              location='кухня', name='лампа')
    #
    #     self.assertIn('Загруженное состояние не является корректным JSON:',
    #                   device.logger.error.call_args_list[0].__str__())

    @patch('axiomLib.loggers.create_logger', MagicMock())
    @patch('redis.StrictRedis', MagicMock())
    def test_return_false_if_contains_wrong_fields(self):
        """
        Тест проверяет, что если в списке полей состояния
        есть что-либо кроме 'status', возвращается False
        """
        from axiomLogic.configurable_nodes import Simple220Device

        device = Simple220Device(identifier='sd:1', node_inputs=['we:1'], power_output='po:m2:1', function='освещение',
                                 location='кухня', name='лампа')

        self.assertEqual(False, device.validate_state({'status': '4', 'value': 100}))

    @patch('axiomLib.loggers.create_logger', MagicMock())
    @patch('redis.StrictRedis', MagicMock())
    def test_log_error_if_contains_wrong_fields(self):
        """
        Тест проверяет, что если в списке полей состояния
        есть что-либо кроме 'status', в лог пишется сообщение об ошибке
        """
        from axiomLogic.configurable_nodes import Simple220Device

        device = Simple220Device(identifier='sd:1', node_inputs=['we:1'], power_output='po:m2:1', function='освещение',
                                 location='кухня', name='лампа')

        device.validate_state({'status': '4', 'value': 100})

        device.logger.error.assert_called_with(
            'Состояние имеет формат не соответствующий блоку типа Simple220Device')

    @patch('axiomLib.loggers.create_logger', MagicMock())
    @patch('redis.StrictRedis', MagicMock())
    def test_return_false_if_contains_wrong_value(self):
        """
        Тест проверяет, что если в состоянии для поля 'status'
        задано значение не принадлежащее списку
        ['2', '4', '5', '6', '7'], возвращается False
        """

        from axiomLogic.configurable_nodes import Simple220Device

        device = Simple220Device(identifier='sd:1', node_inputs=['we:1'], power_output='po:m2:1',
                                 function='освещение', location='кухня', name='лампа')

        self.assertEqual(False, device.validate_state({'status': '1'}))

    @patch('axiomLib.loggers.create_logger', MagicMock())
    @patch('redis.StrictRedis', MagicMock())
    def test_log_error_if_contains_wrong_value(self):
        """
        Тест проверяет, что если в состоянии, для поля 'status'
        задано значение не принадлежащее списку ['2', '4', '5', '6', '7'],
        в лог пишется сообщение об ошибке
        """

        from axiomLogic.configurable_nodes import Simple220Device

        device = Simple220Device(identifier='sd:1', node_inputs=['we:1'], power_output='po:m2:1',
                                 function='освещение', location='кухня', name='лампа')

        invalid_state = {'status': '1'}

        self.assertEqual(False, device.validate_state(invalid_state))

        device.logger.error.assert_called_with('Состояние имеет значение поля "status" '
                                               'недопустимое для блока типа Simple220Device: '
                                               '"{}"'.format(invalid_state['status']))

    @patch('axiomLib.loggers.create_logger', MagicMock())
    @patch('redis.StrictRedis', MagicMock())
    def test_return_true_for_valid_saved_state(self):
        """
        Тест проверяет, что если состояние, является
        корректным для данного типа блока, возвращается True
        """

        from axiomLogic.configurable_nodes import Simple220Device

        device = Simple220Device(identifier='sd:1', node_inputs=['we:1'], power_output='po:m2:1',
                                 function='освещение', location='кухня', name='лампа')

        self.assertEqual(True, device.validate_state({'status': '5'}))


class TestHandleStateInfo(Simple220DeviceTestBase):
    """
    Юнит-тесты метода Simple220Device.handle_state_info()
    """

    def test_set_new_node_state(self):
        """
        Тест проверяет, что состояние блока устанавливается таким же
        как полученное от брокера состояние
        """
        from axiomLogic.configurable_nodes import Simple220Device
        device = Simple220Device(identifier='sd:1', node_inputs=['we:1'], power_output='po:m2:1', function='освещение',
                                 location='кухня', name='лампа')

        state_msg = {'status': '4'}
        device.handle_state_info(state=state_msg)
        self.assertEqual(state_msg, device.state)

    @patch('pubsub.pub', MagicMock())
    def test_send_new_state_to_broker(self):
        """
        Тест проверяет, что новое состояние блока
        отправляется на брокер
        """
        from pubsub import pub
        from axiomLogic.configurable_nodes import Simple220Device
        device = Simple220Device(identifier='sd:1', node_inputs=['we:1'], power_output='po:m2:1', function='освещение',
                                 location='кухня', name='лампа')

        state_msg = {'status': '4'}
        device.handle_state_info(state=state_msg)

        pub.sendMessage.assert_called_once_with(topicName=device.id + '_out', msg=state_msg)

    @patch('redis.StrictRedis', MagicMock())
    def test_save_new_state_in_redis(self):
        import redis
        redis_connection = redis.StrictRedis()
        saved_state = {'status': '4'}
        redis_connection.get = MagicMock(return_value=ujson.dumps(saved_state))

        from axiomLogic.configurable_nodes import Simple220Device
        device = Simple220Device(identifier='sd:1', node_inputs=['we:1'], power_output='po:m2:1', function='освещение',
                                 location='кухня', name='лампа')

        new_state = {'status': '5'}
        device.handle_state_info(state=new_state)

        redis_connection.set.assert_called_once_with(device.id, new_state)
        

class TestInputListener(Simple220DeviceTestBase):
    """
    Юнит-тесты метода Simple220Device.input_listener()
    """
    
    def test_calls_handle_msg_from_input(self):
        """
        Тест проверяет, что вызывается метод Simple220device.handle_msg_from_input() 
        """
        from axiomLogic.configurable_nodes import Simple220Device
        device = Simple220Device(identifier='sd:1', node_inputs=['we:1'], power_output='po:m2:1', function='освещение',
                                 location='кухня', name='лампа')

        device.handle_msg_from_input = MagicMock()
        test_msg = {'status': '4'}
        device.input_listener(msg=test_msg)
        device.handle_msg_from_input.assert_called_once_with(test_msg)


class TestHandleMsgFromInput(Simple220DeviceTestBase):
    """
    Юнит-тесты метода Simple220Device.handle_msg_from_input()
    """

    def test_doesnt_call_set_power_output_state_for_unsupported_msg(self):
        """
        Тест проверяет, что метод Simple220Device.set_power_output_state()
        не вызывается, если содержимое msg не поддерживается
        """
        from axiomLogic.configurable_nodes import Simple220Device
        device = Simple220Device(identifier='sd:1', node_inputs=['we:1'], power_output='po:m2:1', function='освещение',
                                 location='кухня', name='лампа')
        device.set_power_output_state = MagicMock()

        test_msg = {'unsupported': 'msg'}
        device.handle_msg_from_input(msg=test_msg)
        device.set_power_output_state.assert_not_called()

        test_msg = {'status': '7'}
        device.handle_msg_from_input(msg=test_msg)
        device.set_power_output_state.assert_not_called()

    def test_calls_set_power_output_state_for_supported_msg(self):
        """
        Тест проверяет, что вызывается метод Simple220Device.set_power_output_state()
        в случае подходящего содержимого msg
        """

        from axiomLogic.configurable_nodes import Simple220Device
        device = Simple220Device(identifier='sd:1', node_inputs=['we:1'], power_output='po:m2:1', function='освещение',
                                 location='кухня', name='лампа')
        device.set_power_output_state = MagicMock()

        test_msg = {'status': '4'}
        device.handle_msg_from_input(msg=test_msg)
        device.set_power_output_state.assert_called_once_with(state=test_msg)

        device.set_power_output_state.reset_mock()

        test_msg = {'status': '5'}
        device.handle_msg_from_input(msg=test_msg)
        device.set_power_output_state.assert_called_once_with(state=test_msg)


class TestSetPowerOutputState(Simple220DeviceTestBase):
    """
    Юнит-тесты метода Simple220Device.set_power_output_state()
    """

    @patch('redis.StrictRedis', MagicMock())
    def test_send_new_state_to_redis(self):
        """
        Тест проверяет, что новое состояние отправляется на
        брокер Redis в канал исходящих командных сообщений модуля "Логика"
        """
        import redis
        redis_connection = redis.StrictRedis()
        redis_connection.get = MagicMock(return_value=None)

        from axiomLogic.configurable_nodes import Simple220Device
        device = Simple220Device(identifier='sd:1', node_inputs=['we:1'], power_output='po:m2:1', function='освещение',
                                 location='кухня', name='лампа')

        test_state = {'status': '4'}
        device.set_power_output_state(state=test_state)

        msg = {'addr': device.power_output, 'state': test_state}
        redis_connection.publish.assert_called_once_with(channel=OUTPUT_CMD_CHANNEL, message=msg)

