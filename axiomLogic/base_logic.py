import json
import threading
import time
from collections import namedtuple

import prctl
import redis
from axiomLogic import logger
from axiomLogic.config import settings_path, LOG_FILE_DIRECTORY, LOG_FILE_NAME


class BaseLogic:
    """
    Базовый класс для сервисной и конфигурируемой логики
    """
    def __init__(self):
        self.settings = json.load(open(settings_path))

        self.r = redis.StrictRedis(decode_responses=True)

        self.isRunning = False

        self.Bundle = namedtuple('Bundle', ['function', 'args'])

    def create_workers(self):
        """
        Создает словарь вида {bundle: worker_thread,...}
        Метод должен быть реализован в классах-наследниках
        """
        raise NotImplementedError

    def run(self):
        """
        Запускает потоки-обработчики
        контролирует их работоспособность
        """
        prctl.set_name('service')
        workers = self.create_workers()

        for worker in workers.values():
            worker.start()

        self.isRunning = True

        # контроль работоспособности запущенных обработчиков
        while self.isRunning:
            for bundle, worker in workers.items():
                if not worker.isAlive():
                    logger.write_log('Перезапущен поток для связки {}'.format(bundle), 'ERROR')
                    workers[bundle] = threading.Thread(target=bundle.function, args=bundle.args)
                    workers[bundle].start()
            time.sleep(5)

