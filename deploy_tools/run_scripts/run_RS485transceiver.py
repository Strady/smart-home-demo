import argparse
from axiomRS485Transceiver import transceiver, stream_logger, file_logger, debug_colors
import setproctitle
import signal

if __name__ == '__main__':

    # Имя процесса
    setproctitle.setproctitle('RS485Transciever')

    # Парсим аргументы командной строки
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--debug', action='store_true', help='enable debug mode')
    args = parser.parse_args()
    # Включаем дебаговый режим, если нужно
    if args.debug:
        loglevel = 10
    else:
        loglevel = 20

    # Устанавливаем уровень логирования
    stream_logger.setLevel(loglevel)
    file_logger.setLevel(loglevel)

    log_msg = 'Модуль обмена по UART запущен'
    stream_logger.debug(debug_colors['INFO'] % log_msg)
    file_logger.info(log_msg)

    # Обработчик сигнала SIGTERM
    signal.signal(signal.SIGTERM, transceiver.sigterm_handler)
    
    try:
        transceiver.run()
    except KeyboardInterrupt:
        transceiver.sigterm_handler(None, None)