import prctl
import setproctitle
import threading
import sys
import time
from axiomLogic.configurable_logic import ConfigurableLogic
from axiomLogic.service_logic import ServiceLogic
from axiomLogic.node_logic import NodeLogic
from axiomLogic.config import LOG_FILE_DIRECTORY, LOG_FILE_NAME
from axiomLib.loggers import create_logger


class AxiomLogic:

    def __init__(self):

        self.isRunning = False

        self.serviceLogic = ServiceLogic()
        self.configurableLogic = ConfigurableLogic()
        # self.nodeLogic = NodeLogic()

        self.service_thread = threading.Thread(target=self.serviceLogic.run)
        self.configurable_thread = threading.Thread(target=self.configurableLogic.run)
        self.node_thread = threading.Thread(target=self.nodeLogic.run)

        self.logger = create_logger(logger_name=__name__,
                                    logfile_directory=LOG_FILE_DIRECTORY,
                                    logfile_name=LOG_FILE_NAME)

    def sigterm_handler(self, signum, frame):
        """
        Останавливает работу функционального модуля "Логика"

        При получении сигнала SIGTERM или SIGINT останавливаются
        сервисной и конфигурационной логики после чего завершается процесс-мастер
        """
        self.configurableLogic.isRunning = False
        self.nodeLogic.isRunning = False
        self.serviceLogic.isRunning = False
        self.isRunning = False
        self.logger.info('остановка модуля "Логика"')
        sys.exit(0)

    def run(self):
        """
        1. Устанавливает имя процесса
        2. Назначает обработчик для сигнала SIGTERM
        3. Запускает сервисную и конфигурационную логику
        4. Контролирует работоспособность сервисной и конфигурационной логики
        """
        # Задаем имя процессу
        setproctitle.setproctitle('axiom logic')
        prctl.set_name('main_run')

        # Запускаем потоки сервисной и конфигурационной логики
        self.isRunning = True

        self.service_thread.start()
        self.configurable_thread.start()
        # self.node_thread.start()

        # Контролируем работоспособность
        while self.isRunning:
            if not self.service_thread.isAlive():
                self.service_thread = threading.Thread(target=self.serviceLogic.run)
                self.service_thread.start()
            elif not self.configurable_thread.isAlive():
                self.configurable_thread = threading.Thread(target=self.configurableLogic.run)
                self.configurable_thread.start()
            # elif not self.node_thread.isAlive():
            #     self.node_thread = threading.Thread(target=self.nodeLogic.run)
            #     self.node_thread.start()

            time.sleep(5)
