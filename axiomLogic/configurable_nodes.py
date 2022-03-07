import threading
from abc import ABC, abstractmethod
import redis
import ujson
from pubsub import pub
from axiomLogic.config import LOG_FILE_DIRECTORY, LOG_FILE_NAME, OUTPUT_CMD_CHANNEL, OUTPUT_INFO_CHANNEL
from axiomLib.loggers import create_logger


class ConfigurableNode(ABC):
    """
    Базовый класс типового блока логики
    """
    logger = create_logger(logger_name=__name__,
                           logfile_directory=LOG_FILE_DIRECTORY,
                           logfile_name=LOG_FILE_NAME)

    def __init__(self, identifier, name=None):
        """
        Инициализирует экземпляр класса

        :ivar identifier: идентификатор блока
        :ivar inputs: блоки, от которых приходят сообщения
        :ivar name: имя блока
        """

        self.id = identifier
        self.name = name or identifier
        self.redis_connection = redis.StrictRedis(decode_responses=True)

    @abstractmethod
    def input_listener(self, msg):
        pass

    @abstractmethod
    def handle_msg_from_input(self, msg):
        pass


class Simple220Device(ConfigurableNode):
    """
    Данный блок подключается к блоку типа Simple220Device и служит для
    создания в веб-интерфейсе соответствующего ему виджета, предоставляющего
    возможности контроля и управления.
    """

    def __init__(self, identifier, node_inputs, power_output, function, location, name=None):
        """
        Инициализирует экземпляр класса

        :ivar identifier: идентификатор блока
        :ivar node_inputs: блоки, от которых приходят сообщения
        :ivar power_output: адрес выхода силового модуля, к которому подключено устройство
        :ivar function: функция устройства (например освещение, бытовая техника)
        :ivar location: размещение устройства (например кухня, гостиная)
        :ivar name: имя блока
        """
        super(Simple220Device, self).__init__(identifier, name)

        self.logger.debug('Создается блок логики типа Simple220Device: '
                          'identifier={}, node_inputs={}, power_output={},'
                          ' function={}, location={}, name={}'.format(
            identifier, node_inputs, power_output, function, location, name))

        self.inputs = node_inputs
        self.power_output = power_output
        self.function = function
        self.location = location

        self.state = self.load_state()

        # Подписываем обработчик на сообщения об изменении состояния силового выхода
        pub.subscribe(topicName=self.power_output, listener=self.state_info_listener)
        self.logger.debug('Блок "{}" подписывается на сообщения от внутреннего брокера с топиком "{}"'.format(
            self.id, self.power_output))

        # Подписываем обработчики на сообщения со входов блока
        for node_input in self.inputs:
            pub.subscribe(topicName=node_input + '_out', listener=self.input_listener)
            self.logger.debug('Блок "{}" подписывается на сообщения от внутреннего брокера с топиком "{}"'.format(
                self.id, node_input + '_out'))

    def load_state(self):
        """
        Возвращает сохраненное в Redis состояние блока, если оно есть,
        или значение по умолчанию, если сохраненного значения нет

        Если сохраненного значения нет, в Redis записывается значение по умолчанию
        """
        saved_state_str = self.redis_connection.get(self.id)

        try:
            saved_state_dict = ujson.loads(saved_state_str)

            if self.validate_state(saved_state_dict):
                self.logger.debug('Для блока "{}" загружено сохраненное в Redis состояние: '
                                  '{}'.format(self.id, saved_state_dict))
                return saved_state_dict
            else:
                raise ValueError
        except Exception:
            default_state = {'status': '4'}
            self.redis_connection.set(self.id, ujson.dumps(default_state))
            self.logger.debug('Для блока "{}" установлено состояние по умолчанию: {}'.format(self.id, default_state))
            return default_state

    def validate_state(self, state):
        """
        Проверяет, что сохраненное состояние имеет подходящий
        для блока данного типа формат

        :param state: состояние
        :type state: dict
        :return: True - формат подходит, False - формат не подходит
        :rtype: bool
        """

        if list(state.keys()) != ['status']:
            self.logger.error('Состояние имеет формат не соответствующий блоку типа Simple220Device')
            return False

        if state['status'] not in ['2', '4', '5', '6', '7']:

            self.logger.error('Состояние имеет значение поля "status" '
                              'недопустимое для блока типа Simple220Device: "{}"'.format(state['status']))
            return False

        return True

    def input_listener(self, msg, topic=pub.AUTO_TOPIC):
        """
        При получении сообщения от брокера вызывает
        обработчик внутренних сообщений логики в
        новом потоке

        :param topic: топик, из которого пришло сообщение
        :type msg: dict
        :param msg: сообщение от другого блока логики (одного из заданных параметром inputs)
        """
        self.logger.debug('Блок "{}" получил на вход сообщение от блока "{}": {}'.format(
            self.id, topic.getName().replace('_out', ''), msg))
        threading.Thread(target=self.handle_msg_from_input, args=(msg,)).start()

    def handle_msg_from_input(self, msg):
        """
        При получении сообщения со входа пытается использовать
        его для установки нового состояния выхода силового модуля

        :type msg: dict
        :param msg: сообщение со входа
        """

        if not isinstance(msg, dict) or not self.validate_state(msg):
            self.logger.warning('Полученное блоком "{}" сообщение "{}" не может быть использовано блоком, '
                                'т.к. имеет несовместимый формат'.format(self.id, msg))
            return

        if msg.get('status') in ['4', '5']:
            self.set_power_output_state(state=msg)

    def set_power_output_state(self, state):
        """
        Отправляет на брокер Redis новое состояние для
        установки на выходе силового модуля

        :type state: dict
        :param state: состояние выхода силового модуля
        """
        msg = {'addr': self.power_output, 'state': state}
        self.logger.debug('Блок "{}" отправил сообщение на брокер Redis: {}'.format(self.id, msg))
        self.redis_connection.publish(channel=OUTPUT_CMD_CHANNEL, message=ujson.dumps(msg))

    def state_info_listener(self, state):
        """
        При получении сообщения от брокера вызывает
        обработчик сообщений от модуля "Взаимодействие
        с низким уровнем" в новом потоке

        :type state: dict
        :param state: состояние выхода силового модуля
        """
        self.logger.debug('Блок "{}" получил сообщение с новым состоянием силового выхода: {}'.format(self.id, state))
        threading.Thread(target=self.handle_state_info, args=(state,)).start()

    def handle_state_info(self, state):
        """
        Обрабатывает новое состояние силового выхода

        * Состоние блока устанавливается таким же, как состояние выхода.
        * Новое состояние сохраняется в Redis
        * Новое состояние блока отправляется на внутренний брокер.

        :type state: dict
        :param state: состояние выхода силового выхода
        """
        self.state = state

        self.redis_connection.set(self.id, ujson.dumps(self.state))
        self.logger.debug('Новое состояние блока "{}" отправляется в канала внутреннего брокера "{}"'.format(
            self.id, self.id + '_out'))
        pub.sendMessage(topicName=self.id + '_out', msg=state)


class Simple220Widget(ConfigurableNode):
    """
    Блок управляющий виджетом, соответствующим простому
    устройству (блок Simple220Device)
    """
    def __init__(self, identifier, node_input, function, location, name=None):
        """
        Инициализирует экземпляр класса

        :ivar identifier: идентификатор блока
        :ivar node_input: блок, от которого приходят сообщения
        :ivar function: функция соответствующего устройства (например освещение, бытовая техника)
        :ivar location: размещение соответствующего устройства (например кухня, гостиная)
        :ivar name: имя блока
        """
        super(Simple220Widget, self).__init__(identifier, name)

        self.logger.debug('Создается блок логики типа Simple220Device: '
                          'identifier={}, node_input={}, function={}, '
                          'location={}, name={}'.format(
            identifier, node_input, function, location, name))

        self.input = node_input
        self.function = function
        self.location = location

        self.state = self.load_state()

        pub.subscribe(topicName=self.input + '_out', listener=self.input_listener)
        self.logger.debug('Блок "{}" подписывается на сообщения от внутреннего брокера с топиком "{}"'.format(
            self.id, self.input + '_out'))
        pub.subscribe(topicName=self.id, listener=self.state_cmd_listener)
        self.logger.debug('Блок "{}" подписывается на сообщения от внутреннего брокера с топиком "{}"'.format(
            self.id, self.id))

    def load_state(self):
        """
        Возвращает сохраненное в Redis состояние блока, если оно есть,
        или значение по умолчанию, если сохраненного значения нет

        Если сохраненного значения нет, в Redis записывается значение по умолчанию
        """
        saved_state = self.redis_connection.get(self.id)
        if saved_state:
            self.logger.debug('Для блока "{}" загружено сохраненное в Redis состояние: {}'.format(self.id, saved_state))
            return ujson.loads(saved_state)
        else:
            default_state = {'status': '4'}
            self.redis_connection.set(self.id, ujson.dumps(default_state))
            self.logger.debug('Для блока "{}" установлено состояние по умолчанию: {}'.format(self.id, default_state))
            return default_state

    def input_listener(self, msg, topic=pub.AUTO_TOPIC):
        """
        При получении сообщения от брокера вызывает
        обработчик внутренних сообщений логики в
        новом потоке

        :param topic: топик, из которого пришло сообщение
        :type msg: dict
        :param msg: сообщение от другого блока логики (заданного параметром input)
        """
        self.logger.debug('Блок "{}" получил на вход сообщение от блока "{}": {}'.format(
            self.id, topic.getName().replace('_out', ''), msg))
        threading.Thread(target=self.handle_msg_from_input, args=(msg,)).start()

    def handle_msg_from_input(self, msg):
        """
        Обрабатывает сообщения об изменении состояния
        подключенного блока типа Simple220Device.

        * Состоние виджета устанавливается таким же, как состояние подключенного блока устройства.
        * Новое состояние сохраняется в Redis
        * Новое состояние виджета отправляется на брокер Redis для отображения на веб-интерфейсе.

        :param msg: сообщение от подключенного блока устройства
        :type msg: dict
        """
        self.state = msg

        self.redis_connection.set(self.id, ujson.dumps(msg))

        output_msg = {'id': self.id, 'state': msg}

        self.logger.debug('Блок "{}" отправил сообщение на брокер Redis: {}'.format(self.id, output_msg))
        self.redis_connection.publish(channel=OUTPUT_INFO_CHANNEL, message=ujson.dumps(output_msg))

    def state_cmd_listener(self, state):
        """
        Запускает в отдельном потоке метод Simple220Widget.handle_state_cmd()
        обработки команд на изменение состояния от модуля "Веб-сервер"

        :param state: новое состояние
        :type state: dict
        """
        self.logger.debug('Блок "{}" получил команду для управления силовым выходом: {}'.format(self.id, state))
        threading.Thread(target=self.handle_state_cmd, args=(state,)).start()

    def handle_state_cmd(self, state):
        """
        Транслирует полученную команду на выход

        :param state: новое состояние
        :type state: dict
        """
        self.logger.debug('Блок "{}" отправил на внутренний брокер команду'
                          ' управления силовым выходом с топиком "{}"'.format(self.id, self.id + '_out'))
        pub.sendMessage(topicName=self.id + '_out', msg=state)
