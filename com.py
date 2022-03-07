import serial, time
from RPi import GPIO
from time import sleep
from loggers import debug_colors, create_loggers
import os
import sys
import redis
import objgraph
import gc
import re
from datetime import datetime as dt

class RpiSerial():
    def __init__(self, port, baudrate, stopbits, parity, bytesizes, loglevel):

        # Инициализируем GPIO
        gpio_init(4, 'OUT')

        # Подключаемся к redis
        self.r = redis.StrictRedis()
        # Поля для хранения статистики по командам
        self.r.set('commands', 0)
        self.r.set('success', 0)
        self.r.set('retries', 0)
        self.r.set('failures', 0)
        self.r.set('empty answers', 0)
        self.r.set('wrong counter', 0)

        self.r.set(name='start_time', value=str(dt.now()))
        for unit_addr in ('m1', 'm2', 'm3', 'm4', 'm5', 'm6'):
            self.r.set(name='{}_sended'.format(unit_addr), value=0)
            self.r.set(name='{}_failures'.format(unit_addr), value=0)

        self.port = port
        self.baudrate = int(baudrate)
        self.stopbits = int(stopbits)
        self.bytesizes = int(bytesizes)
        self.parity = parity

        self.setup_logging(loglevel)

        try:
            self.ser = serial.Serial(port=self.port, baudrate=self.baudrate, stopbits=self.stopbits,
                                     bytesize=self.bytesizes, parity=self.parity, timeout=0.05, xonxoff=False,
                                     rtscts=False, writeTimeout=0.05, dsrdtr=False, interCharTimeout=None)
            sleep(1)
        except serial.SerialException:
            self.stream_logger.critical(self.debug_colors['ERROR'] % 'Не удалось открыть com порт %s. Завершение программы' % self.port)
            self.file_logger.critical('Не удалось открыть com порт %s. Завершение программы' % self.port)
            sys.exit(1)

    def open(self):
        try:
            self.ser.open()

        except serial.SerialException:
            self.stream_logger.critical(
                self.debug_colors['ERROR'] % 'Не удалось открыть com порт %s. Завершение программы' % self.port)
            self.file_logger.critical('Не удалось открыть com порт %s. Завершение программы' % self.port)
            sys.exit(1)

    def write(self, data):
        try:
            self.ser.write(data)
        except serial.SerialException as e:
            log_msg = 'Ошибка при записи в com порт: {}'.format(str(e))
            self.stream_logger.debug(self.debug_colors['ERROR'] % log_msg)
            self.file_logger.error(log_msg)
            # with open('/home/pi/office/socket-io_test/gc.log', 'a') as f:
            #     f.write(str(gc.collect()) + '\n')
            #     f.write('\x1b[31mserial exception!\x1b[0m\n')
            #     f.write(str(e) + '\n')
            #     objgraph.show_growth(file=f)
            return False
        else:
            return True

    def write_byte(self, data):
        for i in data:
            if not self.write(i.encode()):
                self.clearFIFO()
                return False
            time.sleep(0.001)
        if not self.write('\n'.encode()):
            self.stream_logger.debug(debug_colors['WARNING'] % 'Ошибка при записи строки "%s" в com порт' % data)
            self.file_logger.warning('Ошибка при записи строки "%s" в com порт' % data)
            self.clearFIFO()
            return False
        self.clearFIFO()
        return True

    def read(self):
        try:
            readdata = self.ser.read_until(terminator=b'\r', size=None)
        except serial.SerialException:
            self.stream_logger.debug(debug_colors['WARNING'] % 'Ошибка при чтении из com порта')
            self.file_logger.warning('Ошибка при чтении из com порта')
            return
        return readdata

    def close(self):
        try:
            self.ser.close()
        except Exception:
            self.stream_logger.debug(debug_colors['ERROR'] % 'Ошибка при по закрытии com порта')
            self.file_logger.error('Ошибка при по закрытии com порта')
            pass

    def clearFIFO(self):
        try:
            self.ser.flushInput()
            self.ser.flushOutput()
        except serial.SerialException:
            self.stream_logger.debug(debug_colors['WARNING'] % 'Ошибка сбросе FIFO com порта')
            self.file_logger.warning('Ошибка сбросе FIFO com порта')
            pass

    def send_command(self, cmd, counter, num_of_retries=10):
        """
        Переключает ножку на запись, записывает команду,
        переключает ножку на чтение, читает результат выпонения команды
        :param counter: счетчик команд
        :param cmd: команда
        :param num_of_retries: количество повторных попыток послать команду в случае неудачи
        :return: результат выполенения команды
        """
        search_result = re.search(r'm\d', cmd)
        unit_addr = search_result.group(0)

        self.r.incr('{}_sended'.format(unit_addr))

        # self.r.incr('commands')
        gpio_wr(4, 1)
        self.clearFIFO()
        self.write_byte(cmd)
        gpio_wr(4, 0)
        output = self.read()
        # return '123m1 ' + '0' * 32, counter

        try:
            str_output = output.decode()
            answer_counter = int(str_output.split('m')[0])
        except Exception:
            answer_counter = None
        self.clearFIFO()

        # Если счетчики совпали, значит команда выполнена успешно
        if counter == answer_counter:
            # self.r.incr('success')
            # if 'di' not in cmd:
            #     print('answer_counter', answer_counter)
            return str_output, answer_counter

        # Если получен пустой ответ, но количество повторных попыток не исчерпано
        elif output == b'' and num_of_retries > 0:
            self.r.incr('{}_failures'.format(unit_addr))
            # self.r.incr('retries')
            # self.r.incr('empty answers')
            self.stream_logger.debug(debug_colors['WARNING'] % 'Нет ответа на команду "{}". Повторная отправка команды'.format(cmd))
            self.file_logger.warning('Нет ответа на команду "{}". Повторная отправка команды'.format(cmd))
            return self.send_command(cmd, counter, num_of_retries - 1)

        # Если получен пустой ответ, но не осталось повторных попыток
        elif output == b'' and num_of_retries == 0:
            self.r.incr('{}_failures'.format(unit_addr))
            # self.r.incr('failures')
            # self.r.incr('empty answers')
            self.stream_logger.debug(debug_colors['ERROR'] % 'Нет ответа на команду "{}". Команда не отправлена'.format(cmd))
            self.file_logger.error('Нет ответа на команду "{}". Команда не отправлена'.format(cmd))
            return False, answer_counter

        # Если ответ был, но счетчик не совпадает, либо не может быть считан (ответ некорректный)
        elif counter != answer_counter:
            self.r.incr('{}_failures'.format(unit_addr))
            # self.r.incr('failures')
            # self.r.incr('wrong counter')
            # Пишем лог, выводим debug сообщения на экран
            log_msg = 'Не совпадают счетчики при выполнении команды "{}".\nЗначение счетчика: {}, полученный ответ: {}'.format(cmd, counter, output)
            self.stream_logger.debug(self.debug_colors['ERROR'] % log_msg)
            self.file_logger.error(log_msg)
            return False, answer_counter

    def setup_logging(self, loglevel):

        self.debug_colors = {'DEBUG': '\x1b[36m%s\x1b[0m',
                             'INFO': '\x1b[32m%s\x1b[0m',
                             'WARNING': '\x1b[33m%s\x1b[0m',
                             'ERROR': '\x1b[31m%s\x1b[0m'}

        module_name = os.path.basename(__file__).split('.')[0]

        self.stream_logger, self.file_logger = create_loggers(loglevel=loglevel, logfilename='/var/log/axiom/RS485_handler.log', logger_id=module_name)


def gpio_init(num_pad, direction):
    GPIO.setmode(GPIO.BCM)
    if direction == 'OUT':
        GPIO.setup(int(num_pad), GPIO.OUT)
    elif direction == 'IN':
        GPIO.setup(int(num_pad), GPIO.IN)
    else:
        # print("error direction mode gpio")
        pass


def gpio_wr(num_pad, data):
    if data == 1:
        GPIO.output(int(num_pad), GPIO.HIGH)
    elif data == 0:
        GPIO.output(int(num_pad), GPIO.LOW)
    else:
        # print("data must be 1 or 0")
        pass

