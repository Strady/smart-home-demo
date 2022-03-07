import hashlib
import os
import sqlite3
import time
import ujson
import redis
from pubsub import pub
from axiomLib.loggers import create_logger
from axiomLogic.config import (LOG_FILE_DIRECTORY, LOG_FILE_NAME, CONFIGURATION_FILES_PATH,
                               CONFIGURATION_FILE_NAME, INPUT_INFO_CHANNEL, INPUT_CMD_CHANNEL)
from axiomLogic.configurable_nodes import Simple220Device, Simple220Widget
from axiomLogic.logic_scheduler import LogicScheduler


class NodeLogic:
    """
    Реализует логику основанную на представлении системы
    в виде совокупности взаимодействующих типовых блоков (nodes)
    """
    def __init__(self):
        print('node_logic', id(pub))
        """
        Инициализирует экземпляр класса

        :ivar logger: журналирует события
        :ivar configuration: словарь с конфигурацией блоков логики
        :ivar node_types: словарь, сопоставляющий типы узлов классам, которые их реализуют
        :ivar isRunning: флаг работы
        """

        self.logger = create_logger(logger_name=__name__,
                                    logfile_directory=LOG_FILE_DIRECTORY,
                                    logfile_name=LOG_FILE_NAME)

        self.scheduler = LogicScheduler()

        self.node_types = {'simple220device': Simple220Device,
                           'simple220widget': Simple220Widget}

        self.configuration = self.load_configuration()

        self.nodes = self.create_nodes(self.configuration)

        self.isRunning = False

        self.logger.debug('создан объект класса NodeLogic')

    def load_configuration(self):
        """
        Загружает конфигурационный JSON из файла конфигурации логики

        :return: словарь с конфигурацией
        :rtype: dict
        """
        fname = os.path.join(CONFIGURATION_FILES_PATH, CONFIGURATION_FILE_NAME)

        try:
            with open(fname, 'r') as f:
                configuration = ujson.load(f)
            if not isinstance(configuration, list):
                self.logger.error('Неверный формат файла конфигурации')
                return
            self.logger.debug('Загружена конфигурация: {}'.format(
                '\n\t\t' + '\n\t\t'.join([str(node) for node in configuration])))
            return configuration
        except FileNotFoundError:
            self.logger.error('Нет файла конфигурации {}'.format(fname))
        except Exception as e:
            self.logger.error('Ошибка при загрузке конфигурации из файла: {}'.format(e))

    def create_nodes(self, configuration):
        """
        Создает объекты логический блоков по загруженной конфигурации

        :param configuration: конфигурация модуля "Логика"
        :type configuration: dict
        :return: словарь с логическими блоками
        :rtype: dict
        """
        created_nodes = {}

        for node_description in configuration:
            # Если элемент списка не словарь - логируем ошибку, переходим к следующему
            if not isinstance(node_description, dict):
                self.logger.error('Неверный формат конфигурации блока логики: {}'.format(node_description))
                continue

            if not node_description.get('identifier'):
                self.logger.error('Не задан параметр "identifier" для блока логики: {}'.format(node_description))
                continue

            if created_nodes.get(node_description['identifier']):
                self.logger.error(
                    'Повторное использование идентификатора для блока логики: {}'.format(node_description))
                continue

            try:
                # Параметр 'node_type' нужен для определения типа блока,
                # который нужно создать, но для создания блока не нужен,
                # поэтому удаляем его из словаря
                node_type = node_description['node_type']
                node_kwargs = node_description.copy()
                node_kwargs.pop('node_type')
            except KeyError:
                self.logger.error('Не задан параметр "node_type" для блока логики: {}'.format(node_description))
                continue

            try:
                created_nodes[node_kwargs['identifier']] = self.node_types[node_type](**node_kwargs)
            except Exception as e:
                self.logger.error('Ошибка при создании блока логики "{}": {}'.format(node_description, e))
                continue

        self.logger.debug('Созданы блоки: {}'.format(created_nodes))
        return created_nodes

    def add_job_to_schedule(self, job_kwargs):
        """
        Добавляет задачу в планировщик и в базу данных

        "Задача" в контексте записи в базу данных является набором именованных
        аргументов функции BackgroundScheduler.add_job, за исключением аргумента "func",
        который представляет собой строку с именем функции вместо объекта функции

        При добавлении задачи в планировщик значение для ключа "func" заменяется на
        объект конфигурационной функции с таким именем

        При добавлении задачи в базу данных ей присваивается id рассчитанный по
        алгоритму md5 для job_kwargs

        Добавление идентичных задач не допускается

        :type job_kwargs: dict
        :param job_kwargs: набор именнованных аргументов
        """
        sqlite_connection = sqlite3.connect(self.jobs_DB_path)
        sqlite_cursor = sqlite_connection.cursor()

        str_job_kwargs = ujson.dumps(job_kwargs)
        job_id = hashlib.md5(ujson.dumps(str_job_kwargs).encode()).hexdigest()

        try:
            # Добавляем задачу в базу данных
            self.logger.debug('добавляем в базу данных {}'.format(str_job_kwargs))
            with sqlite_connection:
                sqlite_cursor.execute('INSERT INTO schedule_jobs VALUES (\'{}\', \'{}\')'.format(job_id, str_job_kwargs))
        except sqlite3.IntegrityError:
            self.logger.write_log(log_msg='Задача {} уже добавлена в планировщик'.format(str_job_kwargs), log_level='ERROR')
            self.r.pubsub(channel='axiomLogic:info:error', message='Такая задача уже существует')
            return

        # Заменяем название функции на объект функции
        job_kwargs['func'] = self.__getattribute__(job_kwargs['func'])
        # Добавляем id к описанию задачи
        job_kwargs['id'] = job_id
        try:
            self.scheduler.add_job(**job_kwargs)
        except Exception as e:
            self.logger.error('Ошибка при добавлении задачи в планировщик: {}', e)

    def dispatcher(self):
        """
        Транслирует сообщения от брокера Redis в соответствующие каналы внутреннего брокера
        """
        self.logger.debug('Запущен диспетчер сообщений от брокера Redis')
        # Подписываемся на сообщения от брокера Redis
        redis_connection = redis.StrictRedis(decode_responses=True)
        redis_subscriber = redis_connection.pubsub(ignore_subscribe_messages=True)
        redis_subscriber.subscribe(INPUT_INFO_CHANNEL)
        redis_subscriber.subscribe(INPUT_CMD_CHANNEL)

        # Слушаем и распределяем сообщения
        while self.isRunning:
            msg = redis_subscriber.get_message()

            if not msg:
                time.sleep(0.01)
                continue

            if msg['channel'] == INPUT_INFO_CHANNEL:
                self.logger.info('Получено сообщение от модуля "Взаимодействие с низким уровнем": {}'.format(
                    msg['data']))
                try:
                    data = ujson.loads(msg['data'])
                except Exception as e:
                    self.logger.error('Ошибка при распаковке сообщения: {}'.format(e))
                    continue
                pub.sendMessage(data['addr'], state=data['state'])

            elif msg['channel'] == INPUT_CMD_CHANNEL:
                self.logger.info('Получено сообщение от модуля "Веб-сервер": {}'.format(msg['data']))
                try:
                    data = ujson.loads(msg['data'])
                except Exception as e:
                    self.logger.error('Ошибка при распаковке сообщения: {}'.format(e))
                    continue
                pub.sendMessage(data['id'], state=data['state'])

            time.sleep(0.01)

    def run(self):
        """
        Запускает основной цикл работы
        """
        self.logger.debug('Запущен метод run()')
        self.isRunning = True
        self.dispatcher()
        self.logger.debug('Остановка модуля node_logic')