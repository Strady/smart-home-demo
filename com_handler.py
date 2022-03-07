import argparse
import json
import os
import redis
import serial
import setproctitle
import signal
import sys
import time
from RPi import GPIO
from com import RpiSerial, gpio_init, gpio_wr
from loggers import debug_colors, create_loggers
from time import sleep, time


class COMhandler:

    def __init__(self, loglevel):
        # Загружаем настройки
        self.setup_configuration(settings_fname='settings.json')
        self.setup_logging(loglevel)


        # Открываем com порт
        self.ser = RpiSerial(port="/dev/ttyS0", baudrate=500000, stopbits=1, parity="N", bytesizes=8, loglevel=loglevel)
        self.ser.close()
        self.ser.open()
        self.ser.clearFIFO()

        # Обработчик сигнала SIGTERM
        signal.signal(signal.SIGTERM, self.sigterm_handler)

        # Подключаемся к redis и подписывамся на сообщения
        self.r = redis.StrictRedis()
        self.p = self.r.pubsub(ignore_subscribe_messages=True)
        self.p.subscribe('AxiomLogic command')
        self.p.subscribe('AxiomLogic command (no check)')
        self.p.subscribe('AxiomLogic command (no_info)')

        # Создадим счетчик команд для каждого модуля
        self.counters = {}
        for unit in self.units:
            self.counters[unit] = 0
        for unit in self.power_units:
            self.counters[unit['master']] = 0
            self.counters[unit['slave']] = 0

        # Словарь для хранения состояния блокировки на силовых модулях
        self.blk_states = {}
        for unit in self.power_units:
            self.blk_states[unit['master']] = '00000'

    def sigterm_handler(self, signum, frame):
        self.stream_logger.debug(debug_colors['INFO'] % 'Остановка программы RS485_handler')
        self.file_logger.info('Остановка программы RS485_handler')
        self.ser.clearFIFO()
        self.ser.close()
        GPIO.cleanup()
        sys.exit(0)

    def setup_configuration(self, settings_fname):
        # settings_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), settings_fname)
        settings_path = '/etc/axiom/settings.json'
        settings = json.load(open(settings_path))
        self.units = settings['units']
        self.power_units = settings['power units']
        self.ao_min_value = settings['ao min value']
        self.ao_max_value = settings['ao max value']
        self.ao_increment_value = settings['ao increment value']
        self.num_of_di = settings['num of di']
        self.adc_thresholds = settings['adc thresholds']

    def setup_logging(self, loglevel):

        self.debug_colors = {'DEBUG': '\x1b[36m%s\x1b[0m',
                             'INFO': '\x1b[32m%s\x1b[0m',
                             'WARNING': '\x1b[33m%s\x1b[0m',
                             'ERROR': '\x1b[31m%s\x1b[0m'}

        module_name = os.path.basename(__file__).split('.')[0]

        self.stream_logger, self.file_logger = create_loggers(loglevel=loglevel, logfilename='/var/log/axiom/RS485_handler.log', logger_id=module_name)

    def di_state_request(self):
        for unit in self.units:
            # Опрашиваем состояние цифровых входов
            answer = self.send_command_wrapper('di %s' % unit, 3)
            # Если удалось считать ответ, вытаскиваем из него состояние di
            if answer:
                try:
                    # if 'm1' in answer:
                    #     print(answer)
                    # Декодируем ответ, если он корректный
                    current_di = answer.split(' ')[1]
                    if len(current_di) != self.num_of_di:
                        log_msg = 'При опросе состояния цифровых входов получен некорректный ответ "%s"' % answer
                        self.stream_logger.debug(debug_colors['WARNING'] % log_msg)
                        self.file_logger.warning(log_msg)
                        return
                except Exception:
                    log_msg = 'При опросе состояния цифровых входов получен некорректный ответ "%s"' % answer
                    self.stream_logger.debug(debug_colors['WARNING'] % log_msg)
                    self.file_logger.warning(log_msg)
                    return

                self.r.publish('di:%s:state_info' % unit, current_di)

    def blk_request(self):
        for unit in self.power_units:
            # Опрашиваем состояние блокировки выходов силового модуля
            master = unit['master']
            slave = unit['slave']

            cmd = 'st {}'.format(master)
            answer = self.send_command_wrapper(cmd, 3)

            if answer:
                data = answer.split(' ')[1].strip()
                self.blk_states[master] = data

    def master_state_retranslation(self):
        for unit in self.power_units:
            # Опрашиваем состояние блокировки выходов силового модуля
            master = unit['master']
            slave = unit['slave']

            cmd = 'st {}'.format(master)
            answer = self.send_command_wrapper(cmd, 3)
            if answer:
                sleep(0.01)
                try:
                    data = answer.split(' ')[1].strip()
                    cmd = 'blk {} {}'.format(hex(int(data, 16)), slave)
                    self.send_command_wrapper(cmd, 3)
                except Exception:
                    pass
                    # print('некорректный ответ:', answer)

    def slave_state_retranslation(self):
        for unit in self.power_units:
            # Опрашиваем состояние блокировки выходов силового модуля
            master = unit['master']
            slave = unit['slave']

            cmd = 'st {}'.format(slave)
            answer = self.send_command_wrapper(cmd, 3)
            if answer:
                sleep(0.01)
                try:
                    data = answer.split(' ')[1]
                    cmd = 'blk {} {}'.format(hex(int(data, 16)), master)
                    self.send_command_wrapper(cmd, 3)
                except Exception:
                    pass
                    # print('некорректный ответ:', answer)

    def handle_AxiomLogic_commands(self):
        """
        Функция подписывается на управляющие команды от модуля AxiomLogic
        и вызывают функцию обработки, соответсвующую типу входа/выхода платы,
        для которого нужно осуществить управление
        """

        # Читаем сообщение с брокера
        message = self.p.get_message()

        if message:
            input_json = eval(message['data'].decode())
            # Распарсиваем информацию из JSON'а
            addr = input_json['id']
            state = input_json['state']

            channel_name = message['channel'].decode()
            write_only = True if 'no check' in channel_name else False
            no_info = True if 'no_info' in channel_name else False

            # Аналоговый выход
            if 'ao' in addr:
                self.set_ao_state(addr, state, write_only=write_only, no_info=no_info)

            # Цифровой выход
            elif 'do' in addr:
                print('do control')

            # Светодиоды аналоговых и цифровых выходов
            elif 'lr' in addr:
                channel_name = message['channel'].decode()
                self.set_lr_state(addr, state, write_only=write_only)

            # Светодиоды цифровых входов и земли
            elif 'll' in addr:
                self.set_ll_state(addr, state, write_only=write_only)

            # Выходы силового модуля
            elif 'ch' in addr:
                self.set_ch_state(addr, state)


            # Рекурсивно вызываем функцию, пока в очереди на брокере есть управляющие команды
            self.handle_AxiomLogic_commands()

    def set_ao_state(self, addr, state, write_only=False, no_info=False):
        """
        Функция формирует команду управления аналоговым выходом
        :param addr: адрес аналогового выхода
        :param state: состояние, которое нужно установить на выходе
        :param write_only: если True, то не проверяется статус выполнения команды
        """

        # Модуль и номер выхода
        unit = addr.split(':')[1]
        position = addr.split(':')[2]

        # Значения ползунка и чекбокса из интерфейса
        status = state['status']
        value = state['value']

        # Значение для случаев, когда снята галочка, либо ползунов в нуле (либо и то, и то)
        hex_value = '0x0'

        # Если галочка стоит и ползунок не в нуле, рассчитываем значение
        if status and bool(int(value)):
            hex_value = hex(int((self.ao_max_value - self.ao_min_value) * float(value) ** 3 / 100 ** 3 + self.ao_min_value))

        # Команда для отправления
        ao_cmd = 'ao %d %s %s' % (int(position) + 1, hex_value, unit)

        self.stream_logger.debug(debug_colors['INFO'] % 'Отправлена команда "%s"' % ao_cmd)
        self.file_logger.info('Отправлена команда "%s"' % ao_cmd)

        # Случай отработки команды без проверки статуса
        # (как показывает практика, работает плохо)
        if write_only:
            gpio_wr(4, 1)
            self.ser.clearFIFO()
            self.ser.write_byte(ao_cmd)
            self.ser.clearFIFO()
            # Отправляем на брокер новое состояние в любом случае
            self.r.publish('COM handler info', {'id': addr, 'state': state})
            return

        # Обычный случай отправки с чтением статуса
        answer = self.send_command_wrapper(ao_cmd, 3)
        if answer:
            self.stream_logger.debug(debug_colors['DEBUG'] % 'Команда "%s" выполнена успешно' % ao_cmd)
            self.file_logger.debug('Команда "%s" выполнена успешно' % ao_cmd)
            # Если команда выполнена успешно, отправляем на брокер сообщение об изменении состояния
            if not no_info:
                self.r.publish('COM handler info', {'id': addr, 'state': state})

    def set_lr_state(self, addr, state, write_only=False):
        unit = addr.split(':')[1]
        ao_led_state = state['value_ao']
        do_led_state = state['value_do']
        lr_cmd = 'lr %s %s %s' % (hex(int(ao_led_state[::-1], 2)), hex(int(do_led_state[::-1], 2)), unit)

        # Случай отправки команды без подтверждения
        if write_only:
            gpio_wr(4, 1)
            self.ser.clearFIFO()
            self.ser.write_byte(lr_cmd)
            self.ser.clearFIFO()
            # Отправляем на броке новое состояние в любом случае
            #self.r.publish('COM handler info', {'id': addr, 'state': state})
            return

        if self.send_command_wrapper(lr_cmd, 3):
            self.r.publish('COM handler info', {'id': addr, 'state': state})

    def set_ll_state(self, addr, state, write_only=False):
        unit = addr.split(':')[1]
        di_led_state = state['value_di']
        gr_led_state = state['value_gr']
        ll_cmd = 'll %s %s %s' % (hex(int(gr_led_state[::-1], 2)), hex(int(di_led_state[::-1], 2)), unit)

        # Случай отправки команды без подтверждения
        if write_only:
            gpio_wr(4, 1)
            self.ser.clearFIFO()
            self.ser.write_byte(ll_cmd)
            self.ser.clearFIFO()
            # Отправляем на броке новое состояние в любом случае
            #self.r.publish('COM handler info', {'id': addr, 'state': state})
            return

        if self.send_command_wrapper(ll_cmd, 3):
            self.r.publish('COM handler info', {'id': addr, 'state': state})

    def set_ch_state(self, addr, state):
        __, ch_unit, ch_position  = addr.split(':')
        ch_position = int(ch_position) + 1
        ch_status = state['status']
        ch_cmd = 'ch {} {} {}'.format(ch_position, 'on' if ch_status else 'off', ch_unit)
        answer = self.send_command_wrapper(ch_cmd, 3)
        if answer:
            self.stream_logger.debug(debug_colors['DEBUG'] % 'Команда "%s" выполнена успешно' % ch_cmd)
            self.file_logger.debug('Команда "%s" выполнена успешно' % ch_cmd)
            self.r.publish('COM handler info', {'id': addr, 'state': state})

    def set_adc_thresholds(self, unit):

        adc_cmd = 'adc hgrp {} {}'.format(' '.join([str(t) for t in self.adc_thresholds]), unit)

        self.stream_logger.debug(debug_colors['INFO'] % 'Установка порогов АЦП командой "%s"' % adc_cmd)
        self.file_logger.info('Установка порогов АЦП командой "%s"' % adc_cmd)

        if not self.send_command_wrapper(adc_cmd, 3):
            self.set_adc_thresholds(unit)

    def send_command_wrapper(self, cmd, num_of_retries):

        unit = cmd.split(' ')[-1]
        answer, counter = self.ser.send_command(cmd, self.counters[unit], num_of_retries)

        if answer:
            self.counters[unit] += 1
            return answer
        else:

            self.stream_logger.debug(debug_colors['ERROR'] % 'Команда "%s" не выполнена' % cmd)
            self.file_logger.error('Команда "%s" не выполнена' % cmd)
            if counter == 0:
                # print('счетчик 0')
                # Видимо произошла перезагрузка, отправляем на логику сообщение, что нужно
                # заново установить состояние всех выходов
                self.r.publish('com handler reload', unit)
            # Если счетчики разбежались, синхронизируем счетчик микроконтроллера с местным
            reset_cnt_cmd = 'cnt {} {}'.format(self.counters[unit], unit)
            answer, counter = self.ser.send_command(reset_cnt_cmd, self.counters[unit], 0)
            if answer:
                self.counters[unit] += 1
            elif not answer and counter == 0:
                self.r.publish('com handler reload', unit)

            # # Если сброс счетчика произошел на силовом модуле надо восстановить блокировку каналов
            # if unit in self.blk_states.keys():
            #     blk_cmd = 'blk {} {}'.format(self.blk_states[unit], unit)
            #     self.ser.send_command(blk_cmd, self.counters[unit], num_of_retries)

    def run(self):
        # Обнуляем счетчики
        print('run again')
        for unit in self.counters:
            if unit != 'm3' and self.counters[unit] == 0:
                answer, counter = self.ser.send_command('cnt 0 {}'.format(unit), self.counters[unit])
                if answer:
                    self.counters[unit] += 1
                    print(unit, 'ok', self.counters[unit])
                else:
                    print(unit, 'fail', self.counters[unit])
                    sleep(3)
                    self.run()

        # Устанавливаем пороги АЦП на мастере и слейве для каждого силового модуля
        # for power_unit in self.power_units:
        #     unit = power_unit['master']
        #     self.set_adc_thresholds(unit)
        #     unit = power_unit['slave']
        #     self.set_adc_thresholds(unit)

        # Счетчик для пропуска тактов опроса силового модуля

        master_st_request_counter = 0
        slave_st_request_counter = 100
        # blk_state_counter = 0


        while True:
            # Смотрим чтобы счетчик не превысил максимальное значение
            for unit in self.counters:
                if self.counters[unit] > 65000:
                    answer, counter = self.ser.send_command('cnt 0 {}'.format(unit), 0)
                    if answer:
                        self.counters[unit] = 1

            # # Опрашиваем состояние блокировки на силовых модулях
            # if not blk_state_counter:
            #     self.blk_request()
            #     print(self.blk_states)
            #     blk_state_counter = 100
            # else:
            #     blk_state_counter -= 1

            self.handle_AxiomLogic_commands()

            self.di_state_request()

            sleep(0.01)

            if not master_st_request_counter:
                self.master_state_retranslation()
                master_st_request_counter = 10
                sleep(0.01)
            else:
                master_st_request_counter -= 1

            if not slave_st_request_counter:
                self.slave_state_retranslation()
                slave_st_request_counter = 100
                sleep(0.01)
            else:
                slave_st_request_counter -= 1

            sleep(0.01)

def main():
    # Парсим аргументы командной строки
    parser = argparse.ArgumentParser()
    parser.add_argument('-d', '--debug', action='store_true', help='enable debug mode')
    args = parser.parse_args()
    # Включаем дебаговый режим, если нужно
    if args.debug:
        loglevel = 10
    else:
        loglevel = 20



    com_hanlder = COMhandler(loglevel)

    com_hanlder.stream_logger.debug(debug_colors['INFO'] % 'Запуск программы RS485_handler')
    com_hanlder.file_logger.info('Запуск программы RS485_handler')

    try:
        com_hanlder.run()
    except KeyboardInterrupt:
        com_hanlder.sigterm_handler(None, None)


if __name__ == '__main__':
    setproctitle.setproctitle('COM handler')
    main()
