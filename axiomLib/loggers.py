# -*- coding: utf-8 -*-
import logging, logging.handlers
import sys
import os

debug_colors = {'DEBUG': '\x1b[37m%s\x1b[0m',
                    'INFO': '\x1b[32m%s\x1b[0m',
                    'WARNING': '\x1b[33m%s\x1b[0m',
                    'ERROR': '\x1b[31m%s\x1b[0m'}


def create_loggers(loglevel, logfilename, logger_id):


    # Форматтеры для вывода сообщений
    stream_formatter = logging.Formatter('%(message)s')
    file_formatter = logging.Formatter('[%(levelname)s]\t%(asctime)s\t%(message)s')


    # хэндлеры для разных логгеров
    stream_handler = logging.StreamHandler(sys.stdout)
    file_handler = logging.handlers.RotatingFileHandler(filename=logfilename, maxBytes=52428800, backupCount=3)


    # Устанавливаем форматтеры для хэндлеров
    stream_handler.setFormatter(stream_formatter)
    file_handler.setFormatter(file_formatter)


    # Создаем логгеры и устанавливаем для них логлевелы и хэндлеры
    stream_logger = logging.getLogger(logger_id + 'stream_logger')
    stream_logger.setLevel(loglevel)
    stream_logger.addHandler(stream_handler)

    file_logger = logging.getLogger(logger_id + 'file_logger')
    file_logger.setLevel(loglevel)
    file_logger.addHandler(file_handler)


    return stream_logger, file_logger


def create_log_writer(stream_logger, file_logger):
    def write_log(log_msg, log_level):
        stream_logger.debug(debug_colors['DEBUG'] % log_msg)
        lowcase_runlevel = log_level.lower()
        file_logger.__getattribute__(lowcase_runlevel)(log_msg)
    return write_log


def create_logger(logger_name, logfile_directory, logfile_name):
    """
    Создает и настраивает объект для записи событий в файл и вывода в консоль

    :type logger_name: str
    :param logger_name: имя логгера
    :type logfile_directory: str
    :param logfile_directory: директория хранения логов
    :type logfile_name: str
    :param logfile_name: имя файла лога

    :rtype: logging.Logger
    :return: логгер
    """

    log_file_path = os.path.join(logfile_directory, logfile_name)

    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter('[%(levelname)s]\t%(asctime)s\t%(message)s')

    # DEBUG
    debug_formatter = logging.Formatter('\x1b[36m[%(levelname)s]\x1b[0m\t\t%(asctime)s\t%(message)s')
    debug_stream_handler = logging.StreamHandler(sys.stdout)
    debug_stream_handler.setLevel(logging.DEBUG)
    debug_stream_handler.setFormatter(debug_formatter)
    debug_stream_handler.addFilter(lambda record: record if record.levelname == 'DEBUG' else None)

    # INFO
    info_formatter = logging.Formatter('\x1b[32m[%(levelname)s]\x1b[0m\t\t%(asctime)s\t%(message)s')
    info_stream_handler = logging.StreamHandler(sys.stdout)
    info_stream_handler.setLevel(logging.INFO)
    info_stream_handler.setFormatter(info_formatter)
    info_stream_handler.addFilter(lambda record: record if record.levelname == 'INFO' else None)

    # WARNING
    warning_formatter = logging.Formatter('\x1b[33m[%(levelname)s]\x1b[0m\t%(asctime)s\t%(message)s')
    warning_stream_handler = logging.StreamHandler(sys.stdout)
    warning_stream_handler.setLevel(logging.WARNING)
    warning_stream_handler.setFormatter(warning_formatter)
    warning_stream_handler.addFilter(lambda record: record if record.levelname == 'WARNING' else None)

    # ERROR
    error_formatter = logging.Formatter('\x1b[31m[%(levelname)s]\x1b[0m\t\t%(asctime)s\t%(message)s')
    error_stream_handler = logging.StreamHandler(sys.stdout)
    error_stream_handler.setLevel(logging.ERROR)
    error_stream_handler.setFormatter(error_formatter)
    error_stream_handler.addFilter(lambda record: record if record.levelname == 'ERROR' else None)

    file_handler = logging.handlers.RotatingFileHandler(filename=log_file_path, maxBytes=10485760, backupCount=5)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    logger.addHandler(debug_stream_handler)
    logger.addHandler(info_stream_handler)
    logger.addHandler(warning_stream_handler)
    logger.addHandler(error_stream_handler)
    logger.addHandler(file_handler)

    return logger

class AxiomLogger:

    def __init__(self, logfile_name, logger_id):
        self.logfile_name = logfile_name,
        self.logger_id = logger_id
        self.log_level = int(os.environ.get('AXIOM_LOG_LEVEL') or 20)

        self.debug_colors = {'DEBUG': '\x1b[37m%s\x1b[0m',
                             'INFO': '\x1b[32m%s\x1b[0m',
                             'WARNING': '\x1b[33m%s\x1b[0m',
                             'ERROR': '\x1b[31m%s\x1b[0m'}

        # Форматтеры для вывода сообщений
        stream_formatter = logging.Formatter('%(message)s')
        file_formatter = logging.Formatter('[%(levelname)s]\t%(asctime)s\t%(message)s')

        # хэндлеры для разных логгеров
        stream_handler = logging.StreamHandler(sys.stdout)
        file_handler = logging.handlers.RotatingFileHandler(filename=logfile_name, maxBytes=52428800, backupCount=3)

        # Устанавливаем форматтеры для хэндлеров
        stream_handler.setFormatter(stream_formatter)
        file_handler.setFormatter(file_formatter)

        # Создаем логгеры и устанавливаем для них логлевелы и хэндлеры
        self.stream_logger = logging.getLogger(logger_id + 'stream_logger')
        self.stream_logger.setLevel(self.log_level)
        self.stream_logger.addHandler(stream_handler)

        self.file_logger = logging.getLogger(logger_id + 'file_logger')
        self.file_logger.setLevel(self.log_level)
        self.file_logger.addHandler(file_handler)

    def write_log(self, log_msg, log_level):
        self.stream_logger.debug(debug_colors['DEBUG'] % log_msg)
        lowcase_runlevel = log_level.lower()
        self.file_logger.__getattribute__(lowcase_runlevel)(log_msg)
