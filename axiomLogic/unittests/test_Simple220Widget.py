import ujson
from pubsub import pub
from unittest import TestCase, skip
from unittest.mock import MagicMock, patch
from axiomLogic.config import *


class Simple220WidgetTestBase(TestCase):
    pass


class TestInit(Simple220WidgetTestBase):
    """
    Юнит-тесты метода Simple220Widget.__init__()
    """

    @skip
    @patch('pubsub.pub', MagicMock())
    def test_subscribes_input_listener_input(self):
        """
        Тест проверяет, что метод Simple220Widget.input_listener() подписывается
        на сообщения от входа блока

        Тест нужно запускать отдельно (убрать @skip)
        """
        from pubsub import pub
        from axiomLogic.nodes import Simple220Widget
        widget = Simple220Widget(identifier='we:1', node_input='sd:1', function='освещение',
                                 location='кухня', name='лампа')

        pub.subscribe.assert_called_with(topicName=widget.input + '_out', listener=widget.input_listener)

    @skip
    @patch('pubsub.pub', MagicMock())
    def test_subscribes_state_cmd_listener(self):
        """
        Тест проверяет, что метод Simple220Widget.state_cmd_listener() подписывается
        на командные сообщения от модуля "Веб-сервер"

        Тест нужно запускать отдельно (убрать @skip)
        """
        from pubsub import pub
        from axiomLogic.nodes import Simple220Widget
        widget = Simple220Widget(identifier='we:1', node_input='sd:1', function='освещение',
                                 location='кухня', name='лампа')

        pub.subscribe.assert_called_with(topicName=widget.id, listener=widget.state_cmd_listener)


class TestLoadState(Simple220WidgetTestBase):
    """
    Юнит-тесты метода Simple220Widget.load_state()
    """

    @patch('redis.StrictRedis', MagicMock())
    def test_returns_saved_in_redis_state(self):
        """
        Тест проверяет, что если в Redis есть сохраненное
        состояние, то возвращается оно
        """
        import redis
        redis = redis.StrictRedis()
        saved_state = {"saved": "state"}
        redis.get = MagicMock(return_value=ujson.dumps(saved_state))
        from axiomLogic.nodes import Simple220Widget

        widget = Simple220Widget(identifier='we:1', node_input='sd:1', function='освещение',
                                 location='кухня', name='лампа')

        self.assertEqual(saved_state, widget.load_state())

    @patch('redis.StrictRedis', MagicMock())
    def test_saves_default_state_if_there_is_no_saved(self):
        """
        Тест проверяет, что если в Redis нет сохраненного
        ранее значения, сохраняется значение по умолчанию
        """
        import redis
        redis = redis.StrictRedis()
        redis.get = MagicMock(return_value=None)
        from axiomLogic.nodes import Simple220Widget

        widget = Simple220Widget(identifier='we:1', node_input='sd:1', function='освещение',
                                 location='кухня', name='лампа')

        default_state = {'status': '4'}
        redis.set.assert_called_once_with(widget.id, ujson.dumps(default_state))

    @patch('redis.StrictRedis', MagicMock())
    def test_returns_default_state_if_there_is_no_saved(self):
        """
        Тест проверяет, что если в Redis нет сохраненного
        ранее значения, возвращается значение по умолчанию
        """
        import redis
        redis = redis.StrictRedis()
        redis.get = MagicMock(return_value=None)
        from axiomLogic.nodes import Simple220Widget

        widget = Simple220Widget(identifier='we:1', node_input='sd:1', function='освещение',
                                 location='кухня', name='лампа')

        default_state = {'status': '4'}
        self.assertEqual(default_state, widget.load_state())


class TestInputListener(Simple220WidgetTestBase):
    """
    Юнит-тесты метода Simple220Widget.input_listener()
    """

    def test_calls_handle_msg_from_input(self):
        """
        Тест проверяет, что вызывается метод Simple220Widget.handle_msg_from_input()
        """
        from axiomLogic.nodes import Simple220Widget

        widget = Simple220Widget(identifier='we:1', node_input='sd:1', function='освещение',
                                 location='кухня', name='лампа')

        widget.handle_msg_from_input = MagicMock()
        test_msg = {'status': '4'}
        widget.input_listener(msg=test_msg)
        widget.handle_msg_from_input.assert_called_once_with(test_msg)


class TestHandleMsgFromInput(Simple220WidgetTestBase):
    """
    Юнит-тесты метода Simple220Widget.handle_msg_from_input()
    """

    @patch('redis.StrictRedis', MagicMock())
    def setUp(self):
        import redis
        redis_connection = redis.StrictRedis()
        saved_state = {'status': '4'}
        redis_connection.get = MagicMock(return_value=ujson.dumps(saved_state))
        from axiomLogic.nodes import Simple220Widget
        self.widget = Simple220Widget(identifier='we:1', node_input='sd:1', function='освещение',
                                      location='кухня', name='лампа')

    def test_set_new_node_state(self):
        """
        Тест проверяет, что состояние блока устанавливается таким же
        как в полученном со входа сообщении
        """
        state_msg = {'status': '5'}
        self.widget.handle_msg_from_input(msg=state_msg)
        self.assertEqual(state_msg, self.widget.state)

    def test_save_new_state_in_redis(self):
        """
        Тест проверяет, что новое состояние блока
        сохраняется в Redis
        """
        state_msg = {'status': '5'}
        self.widget.handle_msg_from_input(msg=state_msg)

        self.widget.redis_connection.set.assert_called_once_with(self.widget.id, ujson.dumps(state_msg))

    def test_publish_new_state_to_redis_broker(self):
        """
        Тест проверяет, что новое состояние блока
        публикуется на брокер Redis для модуля "Веб-сервер"
        """
        state_msg = {'status': '5'}
        self.widget.handle_msg_from_input(msg=state_msg)

        msg_to_publish = {'id': self.widget.id, 'state': state_msg}
        self.widget.redis_connection.publish.assert_called_once_with(channel=OUTPUT_INFO_CHANNEL,
                                                                     message=ujson.dumps(msg_to_publish))


class TestStateCmdListener(Simple220WidgetTestBase):
    """
    Юнит-тесты метода Simple220Widget.state_cmd_listener()
    """
    @patch('redis.StrictRedis', MagicMock())
    def setUp(self):
        import redis
        redis_connection = redis.StrictRedis()
        saved_state = {'status': '4'}
        redis_connection.get = MagicMock(return_value=ujson.dumps(saved_state))
        from axiomLogic.nodes import Simple220Widget
        self.widget = Simple220Widget(identifier='we:1', node_input='sd:1', function='освещение',
                                      location='кухня', name='лампа')

    def calls_handle_state_cmd(self):
        """
        Тест проверяет, что вызывается метод Simple220Widget.handle_state_cmd()
        """
        new_state = {'status': '5'}
        self.widget.handle_state_cmd = MagicMock()
        self.widget.state_cmd_listener(state=new_state)
        self.widget.handle_state_cmd.assert_called_once_with(new_state)


class TestHandleStateCmd(Simple220WidgetTestBase):
    """
    Юнит-тесты метода Simple220Widget.handle_state_cmd()
    """

    @patch('redis.StrictRedis', MagicMock())
    @patch('pubsub.pub', MagicMock())
    def setUp(self):
        import redis
        redis_connection = redis.StrictRedis()
        saved_state = {'status': '4'}
        redis_connection.get = MagicMock(return_value=ujson.dumps(saved_state))

        from pubsub import pub
        self.pub = pub

        from axiomLogic.nodes import Simple220Widget
        self.widget = Simple220Widget(identifier='we:1', node_input='sd:1', function='освещение',
                                      location='кухня', name='лампа')

    def test_send_new_state_to_broker(self):
        """
        Тест проверяет, что полученное в команде состояние
        отправляется на внутренний брокер
        """
        new_state = {'status': '5'}
        self.widget.handle_state_cmd(state=new_state)
        self.pub.sendMessage.assert_called_once_with(topicName=self.widget.id + '_out', msg=new_state)


