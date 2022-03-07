import hashlib
import json

import prctl

from axiomLib.loggers import create_logger
import os
import sqlite3
import time
import ujson
from axiomLogic import logger
from axiomLogic.base_logic import BaseLogic
from axiomLogic.config import *
import threading
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime as dt


class ConfigurableLogic(BaseLogic):

    def __init__(self):
        super().__init__()
        self.logger = create_logger(logger_name=__name__,
                                    logfile_directory=LOG_FILE_DIRECTORY,
                                    logfile_name=LOG_FILE_NAME)

        self.scheduler = BackgroundScheduler()

        self.jobs_DB_path = os.path.join(self.settings['root directory'], JOBS_DB_NAME)

    def dispatcher(self):
        """
        Распределяет сообщения, полученные от брокера по соответствующим обработчикам
        """
        prctl.set_name('dispatcher')
        redis_subscriber = self.r.pubsub(ignore_subscribe_messages=True)
        redis_subscriber.subscribe(CREATE_JOB_CHANNEL,
                                   DELETE_JOB_CHANNEL,
                                   UPDATE_JOB_CHANNEL)

        # Подключение к БД создается здесь, а не в __init__, потому что необходимо, чтобы оно создавалось
        # в том же потоке, в котором будет использоваться (особенности реализации библиотеки sqlite3).

        while self.isRunning:
            message = redis_subscriber.get_message()
            if message is None:
                time.sleep(0.01)
                continue
            logger.write_log(log_msg='получено сообщение {}'.format(message['data']), log_level='INFO')
            if message['channel'] == CREATE_JOB_CHANNEL:
                job_kwargs = ujson.loads(message['data'])
                threading.Thread(target=self.add_job_to_schedule, args=(job_kwargs,)).start()
            elif message['channel'] == DELETE_JOB_CHANNEL:
                job_id = message['data']
                threading.Thread(target=self.delete_job_from_schedule, args=(job_id,)).start()
            elif message['channel'] == UPDATE_JOB_CHANNEL:
                job_kwargs = ujson.loads(message['data'])
                threading.Thread(target=self.update_job_in_schedule, args=(job_kwargs,)).start()
            time.sleep(0.01)

    def create_jobs_table_if_not_exists(self):
        """
        Создает таблицу для хранения задач планировщика, если ее нет
        """
        sqlite_connection = sqlite3.connect(self.jobs_DB_path)
        sqlite_cursor = sqlite_connection.cursor()
        with sqlite_connection:
            sqlite_cursor.execute(
                'CREATE TABLE IF NOT EXISTS schedule_jobs (id VARCHAR PRIMARY KEY, job VARCHAR UNIQUE)')

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
            logger.write_log(log_msg='Задача {} уже добавлена в планировщик'.format(str_job_kwargs), log_level='ERROR')
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

    def delete_job_from_schedule(self, job_id):
        """
        Удаляет задачу из планировщика и БД

        :type job_id: str
        :param job_id: id задачи
        """
        self.scheduler.remove_job(job_id=job_id)

        sqlite_connection = sqlite3.connect(self.jobs_DB_path)
        sqlite_cursor = sqlite_connection.cursor()

        with sqlite_connection:
            sqlite_cursor.execute("DELETE FROM schedule_jobs WHERE id == (?)", (job_id,))

    def update_job_in_schedule(self, job_kwargs):
        """
        Обновляет задачу в планировщике

        Старая задача удаляется и записывается новая. В результате id задачи
        изменяется, поскольку id задачи представляет собой hash ее аргументов

        :type job_kwargs: dict
        :param job_kwargs: набор именнованных аргументов
        """
        job_id = job_kwargs.pop('id')
        self.delete_job_from_schedule(job_id=job_id)
        self.add_job_to_schedule(job_kwargs=job_kwargs)

    def load_jobs_from_db(self):
        """
        Загружает сохраненные в БД задачи и добавляет их в планировщик
        """
        sqlite_connection = sqlite3.connect(self.jobs_DB_path)
        sqlite_cursor = sqlite_connection.cursor()

        with sqlite_connection:
            sqlite_cursor.execute('SELECT * FROM schedule_jobs')
            query_result = sqlite_cursor.fetchall()

        for job_id, str_job_kwargs in query_result:
            job_kwargs = ujson.loads(str_job_kwargs)
            # Заменяем название функции на объект функции
            job_kwargs['func'] = self.__getattribute__(job_kwargs['func'])
            # Добавляем id к описанию задачи
            job_kwargs['id'] = job_id
            self.scheduler.add_job(**job_kwargs)

    def run(self):
        """
        Запускает цикл работы конфигурируемой логики
        """
        prctl.set_name('configurable')
        workers = self.create_workers()

        for worker in workers.values():
            worker.start()

        self.isRunning = True

        # Запускаем диспетчер
        threading.Thread(target=self.dispatcher).start()
        # Добавляем в планировщик задачи из БД
        self.load_jobs_from_db()
        # Запускаем планировщик
        self.scheduler.start()

        # контроль работоспособности запущенных обработчиков
        while self.isRunning:
            for bundle, worker in workers.items():
                if not worker.isAlive():
                    logger.write_log('Перезапущен поток для связки {}'.format(bundle), 'ERROR')
                    workers[bundle] = threading.Thread(target=bundle.function, args=bundle.args)
                    workers[bundle].start()
            time.sleep(5)

        self.scheduler.shutdown()

    def create_workers(self):
        """
        Создает словарь вида {bundle: worker_thread,...}
        bundle - объект типа collections.namedtuple с полями "function" и "args"
        function - конфигурируемая функция (с приставкой "configurable_")
        args - аргументы конфигурируемой функцияи
        worker_thread - объект типа threading.Thread, поток, в котором запускается
        конфигурируемая функция
        """

        with open(configurator_output_path) as f:
            bundles = json.load(f)

        # Список существующих конфигурационных функций
        configurable_functions = list(filter(lambda name: name.startswith('configurable_'), self.__dir__()))

        workers = {}

        for bundle in bundles:
            if bundle['function'] in configurable_functions:
                # Связки сохраняются в виде объектов типа namedtuple
                function = self.__getattribute__(bundle['function'])
                args = tuple(bundle['args'])
                tuple_bundle = self.Bundle(function=function, args=args)
                workers[tuple_bundle] = threading.Thread(target=tuple_bundle.function, args=tuple_bundle.args)
            else:
                logger.write_log(log_msg='Функции {} нет в списке конфигурационных функций'.format(bundle['function']),
                                 log_level='ERROR')
        return workers

    def configurable_connect_checkbox_to_new_ch(self, we_addr, ch_addr):
        """
        Управление выходом нового силового модуля по командам от веб элемента (чекбокс)
        :param ch_addr: адрес силового выхода
        :param we_addr: адрес веб элемента
        """
        prctl.set_name('chbox_to_ch')
        # Подписываемся на сообщения от модуля "Веб-сервер"
        p_web = self.r.pubsub(ignore_subscribe_messages=True)
        p_web.subscribe(INPUT_CMD_CHANNEL)

        # print("configurable_connect_checkbox_to_ch")

        # Подписываемся на сообщения об изменении состояния от модуля "Логика"
        p_low = self.r.pubsub(ignore_subscribe_messages=True)
        p_low.subscribe(INPUT_INFO_CHANNEL)

        axiom_root = self.settings['root directory']
        db_path = os.path.join(axiom_root, site_db)
        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()

        # Смотрим в БД имя ВЭК
        select_query = 'SELECT name FROM web_element WHERE addr == "{}"'.format(we_addr)
        with connection:
            query_result_consumption = cursor.execute(select_query)
        we_name = query_result_consumption.fetchone()[0]

        def web_messages_handler_target():
            """
            Запускается в потоке и обрабатывает сообщения от модуля "Веб-сервер"
            """
            prctl.set_name('web_handler')
            while self.isRunning:

                message = p_web.get_message()

                if not message:
                    time.sleep(0.01)
                    continue

                try:
                    input_json = ujson.loads(message['data'])
                except (TypeError, ValueError) as e:
                    print(e)
                    continue

                if input_json['id'] == we_addr:
                    # Логируем получение команды
                    self.logger.info('Получена команда от модуля "Веб-сервер": "{}"'.format(input_json))

                    # Отправляем команду на низкий уровень
                    ch_status = input_json['state']['status']
                    cmd = {'addr': ch_addr, 'state': {'status': ch_status}}
                    self.r.publish(OUTPUT_CMD_CHANNEL, ujson.dumps(cmd))

                    # Логируем отправку команды
                    log_msg = 'Отправлена команда на модуль "Взаимодействие с низким уровнем": "{}"'.format(cmd)
                    logger.write_log(log_msg=log_msg, log_level='INFO')

                time.sleep(0.01)

        def web_updater_target():
            """
            Запускается в потоке и обновляет состояние веб элемента
            по сообщениям от модуля "Взаимодействие с низким уровнем"
            """
            prctl.set_name('web_updater')
            axiom_root = self.settings['root directory']
            db_path = os.path.join(axiom_root, site_db)

            connection = sqlite3.connect(db_path)
            cursor = connection.cursor()

            while self.isRunning:
                message = p_low.get_message()

                if not message:
                    time.sleep(0.01)
                    continue

                try:
                    input_json = ujson.loads(message['data'])
                except (TypeError, ValueError) as e:
                    print("exc web_updater_target {}".format(e))
                    print("received: {}".format(message['data']))
                    continue

                if ch_addr == input_json.get('addr'):
                    # Логируем получение информационного сообщения
                    log_msg = 'Получено информационное сообщение от модуля' \
                              ' "Взаимодействие с низким уровнем": "{}"'.format(input_json)
                    logger.write_log(log_msg=log_msg, log_level='INFO')

                    # Транслируем полученное новое состояние силового выхода на модуль "Веб-сервер"
                    ch_state = input_json['state']
                    self.r.publish('axiomLogic:info:state', ujson.dumps({'id': we_addr, 'state': ch_state}))
                    cmd = {'id': we_addr, 'state': ch_state}
                    self.r.set(we_addr, ujson.dumps(ch_state))

                    # Логируем отправку информационного сообещния
                    log_msg = 'Отправлено информационное сообщение на модуль "Веб-сервер": "{}"'.format(cmd)
                    logger.write_log(log_msg=log_msg, log_level='INFO')

                    # Делаем запись в журнал об изменении состояния
                    log_status = 'включен' if ch_state['status'] == '5' else 'выключен'
                    event = '{} {}'.format(we_name, log_status)
                    with connection:
                        cursor.execute(
                            'INSERT INTO log_entries (timestamp, event) VALUES ({}, "{}")'.format(time.time(), event))

                time.sleep(0.01)

        web_messages_handler = threading.Thread(target=web_messages_handler_target)
        web_updater = threading.Thread(target=web_updater_target)

        web_messages_handler.start()
        web_updater.start()

        # контроль работоспособности потоков
        while self.isRunning:
            if not web_messages_handler.isAlive():
                logger.write_log('Перезапуск потока-обработчика команд от веб элемента {}'.format(we_addr), 'ERROR')
                web_messages_handler = threading.Thread(target=web_messages_handler_target)
                web_messages_handler.start()
            if not web_updater.isAlive():
                logger.write_log('Перезапуск потока обновляющего состояние веб элемента {}'.format(we_addr), 'ERROR')
                web_updater = threading.Thread(target=web_updater_target)
                web_updater.start()
            time.sleep(1)

    def configurable_change_ch_state(self, addr, status):
        # Отправляем команду на низкий уровень
        cmd = {'addr': addr, 'state': {'status': status}}
        self.logger.debug('отправляем команду: {}, время: {}'.format(cmd, dt.now()))
        self.r.publish(OUTPUT_CMD_CHANNEL, ujson.dumps(cmd))


