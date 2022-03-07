import signal

from axiomLogic import AxiomLogic
from axiomLogic.config import LOG_FILE_NAME, LOG_FILE_DIRECTORY
from axiomLib.loggers import create_logger


if __name__ == '__main__':

    logic = AxiomLogic()

    # Обработчик сигналов SIGTERM, SIGINT
    signal.signal(signal.SIGTERM, logic.sigterm_handler)
    signal.signal(signal.SIGINT, logic.sigterm_handler)

    logger = create_logger(logger_name=__name__,
                           logfile_directory=LOG_FILE_DIRECTORY,
                           logfile_name=LOG_FILE_NAME)

    logger.info('модуль "Логика" запущен')

    logic.run()
