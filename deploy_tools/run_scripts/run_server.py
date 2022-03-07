import argparse
from axiomWebserver import app, socketio, file_logger, stream_logger, debug_colors

if __name__ == '__main__':
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

    log_msg = 'Вебсервер запущен'
    stream_logger.debug(debug_colors['INFO'] % log_msg)
    file_logger.info(log_msg)

    # запускаем главный цикл фласка
    socketio.run(app, host='0.0.0.0', debug=True)
