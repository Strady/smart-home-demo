import json
import redis
from time import sleep, time
from statistics import mean
from copy import deepcopy
from axiomLib.funclib import get_state_from_redis, calculate_click_tokens, reduce_repeats
from axiomLogic import stream_logger, file_logger, debug_colors, log_writer, logger
from threading import Thread
import sqlite3
import os
from axiomWebserver.models import WebElement

journal_db = 'axiomWebserver/site.db'


# DEPRECATED
def connect_di_to_ao(di_list, ao_list, settings):
    """
    Подключение цифрового входа к аналоговому выходу
    :param di_list: список цифровых входов
    :param ao_list: список аналоговых выходов
    :param settings: словарь настроек
    """

    short_click_tokens, long_click_tokens = calculate_click_tokens(settings['di queue len'])

    # Собираем имена модулей, с которых берем di_queue
    units = set()
    for di in di_list:
        unit = di.split(':')[1]
        units.add(unit)

    # Разобьем di на группы по принадлежности к модулям
    di_dict = {unit: [] for unit in units}
    for di in di_list:
        unit = di.split(':')[1]
        di_dict[unit].append(di)

    # Подписываемся на сообщения от каждого модуля
    r = redis.StrictRedis()
    p = r.pubsub(ignore_subscribe_messages=True)
    for unit in units:
        p.subscribe('di_queue:{}'.format(unit))

    # Последнее значение, которое отправляли
    last_sent_ao_state = {ao_addr: None for ao_addr in ao_list}

    # Количество тактов опроса, которое нужно пропустить
    num_to_skip = {ao_addr: 0 for ao_addr in ao_list}

    for message in p.listen():

        # Выясним от какого модуля пришло сообщение
        channel = message['channel'].decode()
        unit = channel.split(':')[1]

        di_queue = eval(message['data'].decode())

        # Поочередно проверяем очередь состояний для всех входов этого модуля
        for di_address in di_dict[unit]:
            # номер текущего входа
            output = int(di_address.split(':')[-1])
            # формируем очередь сообщений для текущего входа
            single_di_queue = [di_state[output] for di_state in di_queue]

            if single_di_queue in short_click_tokens:
                # Выясним в каком состоянии сейчас находятся подконтрольные выходы
                ao_state_list = []
                for ao in ao_list:
                    raw_ao_state = r.get(ao)
                    if raw_ao_state:
                        ao_state = eval(raw_ao_state.decode())
                        ao_state_list.append(ao_state)
                    else:
                        ao_state_list.append({'status': False, 'value': 0})

                # Вычисляем среднее состояние. Если больше половины включены, то True, иначе False
                average_ao_status = True if sum([int(state['status']) for state in ao_state_list]) > len(
                    ao_list) / 2 else False

                # Выясним в каком состоянии сейчас светодиоды
                raw_led_value = r.get('lr:{}'.format(unit))
                if raw_led_value:
                    led_value = eval(raw_led_value.decode())
                else:
                    led_value = {'value_ao': '0' * settings['num of ao'],
                                 'value_do': '0' * settings['num of do']}

                led_value_ao = led_value['value_ao']
                led_value_do = led_value['value_do']

                # Меняем статус подконтрольных выходов и соответствующих светодиодов
                for ao, ao_state in zip(ao_list, ao_state_list):
                    ao_state['status'] = not average_ao_status
                    ao_position = int(ao.split(':')[2])
                    led_value_ao = led_value_ao[:ao_position] + str(int(not average_ao_status)) + led_value_ao[
                                                                                                  ao_position + 1:]

                    # Отправляем команду на изменение через редис
                    cmd = {'id': ao, 'state': ao_state}
                    stream_logger.debug(
                        debug_colors['INFO'] % 'Отправлена команда "{}" по нажатию на выключатель "{}"'.format(cmd,
                                                                                                               di_address))
                    file_logger.info('Отправлена команда "{}" по нажатию на выключатель "{}"'.format(cmd, di_address))
                    r.publish('axiomLogic:cmd:state', cmd)

                # Отправляем новое состояние светодиодов на брокер
                cmd = {'id': 'lr:%s' % unit, 'state': {'value_ao': led_value_ao,
                                                       'value_do': led_value_do}}
                stream_logger.debug(
                    debug_colors['INFO'] % 'Отправлена команда "{}" по нажатию на выключатель "{}"'.format(cmd,
                                                                                                           di_address))
                file_logger.info('Отправлена команда "{}" по нажатию на выключатель "{}"'.format(cmd, di_address))
                r.publish('axiomLogic:cmd:state', cmd)

            elif single_di_queue in long_click_tokens[:-1]:
                # print('длинное нажатие на выключатель', di_address)
                # Выясним в каком состоянии сейчас находятся подконтрольные выходы
                ao_state_list = []
                for ao in ao_list:
                    raw_ao_state = r.get(ao)
                    if raw_ao_state:
                        ao_state = eval(raw_ao_state.decode())
                        ao_state_list.append(ao_state)
                    else:
                        print('не удалось считать из БД состояние', ao)
                        ao_state_list.append({'status': False, 'value': 0})

                # Выясним в каком состоянии сейчас светодиоды
                raw_led_value = r.get('lr:{}'.format(unit))
                if raw_led_value:
                    led_value = eval(raw_led_value.decode())
                else:
                    led_value = {'value_ao': '0' * settings['num of ao'],
                                 'value_do': '0' * settings['num of do']}

                led_value_ao = led_value['value_ao']
                temp_led_value_ao = led_value_ao
                led_value_do = led_value['value_do']

                # Меняем статус подконтрольных выходов и соответствующих светодиодов
                for ao, ao_state in zip(ao_list, ao_state_list):
                    # Пропускаем такты, если до этого дошли до максимума
                    if num_to_skip[ao]:
                        num_to_skip[ao] -= 1
                        # print('Осталось пропустить тактов %s на выходе %s: ' % (num_to_skip, ao))
                        continue

                    ao_state['status'] = True
                    new_ao_value = int(ao_state['value'])
                    new_ao_value += settings['ao increment value']

                    if new_ao_value > 100:
                        new_ao_value -= 100
                    ao_state['value'] = int(new_ao_value)
                    # Если состояние повторяется, пропускаем такт
                    if ao_state == last_sent_ao_state[ao]:
                        # print('пропускаем такт')
                        continue
                    ao_position = int(ao.split(':')[2])
                    temp_led_value_ao = temp_led_value_ao[:ao_position] + '1' + temp_led_value_ao[ao_position + 1:]

                    # Отправляем команду на изменение через редис
                    cmd = {'id': ao, 'state': ao_state}
                    stream_logger.debug(
                        debug_colors['INFO'] % 'Отправлена команда "{}" по нажатию на выключатель "{}"'.format(cmd,
                                                                                                               di_address))
                    file_logger.info('Отправлена команда "{}" по нажатию на выключатель "{}"'.format(cmd, di_address))
                    r.publish('axiomLogic:cmd:state', cmd)
                    # Обновляем последнее отправленное состояние
                    last_sent_ao_state[ao] = ao_state

                    # Если дошли до максимума
                    if 100 - settings['ao increment value'] < new_ao_value <= 100:
                        num_to_skip[ao] = settings['delay on dimmer max value']
                        continue

                if temp_led_value_ao != led_value_ao:
                    cmd = {'id': 'lr:%s' % unit, 'state': {'value_ao': temp_led_value_ao, 'value_do': led_value_do}}
                    stream_logger.debug(
                        debug_colors['INFO'] % 'Отправлена команда "{}" по нажатию на выключатель "{}"'.format(cmd,
                                                                                                               di_address))
                    file_logger.info('Отправлена команда "{}" по нажатию на выключатель "{}"'.format(cmd, di_address))
                    r.publish('axiomLogic:cmd:state', cmd)

            elif single_di_queue == long_click_tokens[-1]:
                # Обнуляем количество тактов для пропуска
                num_to_skip = {ao_addr: 0 for ao_addr in ao_list}

            elif reduce_repeats(single_di_queue) == [0, 1, 0, 1, 0]:
                print('двойное нажатие на выключатель', di_address)


# DEPRECATED
def connect_range_to_ao(we, ao_list, settings):
    # # Создаем логгеры
    # stream_logger, file_logger = create_loggers(loglevel=loglevel, logfilename='/var/log/axiom/axiomLogic.log',
    #                                             logger_id=str(random.random()))

    # setproctitle.setproctitle('axiomlogic:connection %s to %s' % (we, ','.join(ao_list)))

    # Обработка сигнала на завершение процесса
    # signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))

    # Подключаемся к брокеру
    r = redis.StrictRedis()
    # Подписываемся на сообщения от веб клиента
    p_web = r.pubsub(ignore_subscribe_messages=True)
    p_web.subscribe('Axiom commands')
    # Подписываемся на сообщения об изменении состояния от COMhandler'а
    p_com_handler = r.pubsub(ignore_subscribe_messages=True)
    p_com_handler.subscribe('axiomRS485Transceiver:info:state')

    # Составим перечень модулей, выходами которых управляем
    units = [ao_addr.split(':')[1] for ao_addr in ao_list]

    while True:
        # Цикл опроса очереди сообщений с веб-интерфейса
        message = p_web.get_message()
        if message:
            input_json = eval(message['data'].decode())
            if input_json['id'] == we:

                new_we_state = input_json['state']

                # Смотрим предыдущее состояние веб элемента
                raw_prev_we_state = r.get(we)
                if raw_prev_we_state:
                    prev_we_state = eval(raw_prev_we_state.decode())
                else:
                    prev_we_state = {'status': False, 'value': 0}

                # Логика связи чекбокса с ползунком
                if ((prev_we_state['status'] and int(prev_we_state['value'])) and
                        (not new_we_state['status'] and int(new_we_state['value']))):
                    input_json['state'] = {'status': False, 'value': new_we_state['value']}

                elif ((prev_we_state['status'] and int(prev_we_state['value'])) and
                      (new_we_state['status'] and not int(new_we_state['value']))):
                    input_json['state'] = {'status': False, 'value': 0}

                elif ((not prev_we_state['status'] and not int(prev_we_state['value'])) and
                      (new_we_state['status'] and not int(new_we_state['value']))):
                    input_json['state'] = {'status': True, 'value': 50}

                elif ((not prev_we_state['status'] and not int(prev_we_state['value'])) and
                      (not new_we_state['status'] and int(new_we_state['value']))):
                    input_json['state'] = {'status': True, 'value': new_we_state['value']}

                # Выясним текущее состояние светодиодов соответствующих подконтрольным выходам
                led_value = dict()

                for unit in units:
                    raw_led_value = r.get('lr:{}'.format(unit))
                    if raw_led_value:
                        led_value[unit] = eval(raw_led_value.decode())
                    else:
                        led_value[unit] = {'value_ao': '0' * settings['num of ao'],
                                           'value_do': '0' * settings['num of do']}

                # Создадим копию, для последующего сравнения
                temp_led_value = deepcopy(led_value)

                for ao_addr in ao_list:
                    # Определим к какому модулю относится данный выход
                    unit = ao_addr.split(':')[1]
                    # Определим номер данного выхода
                    ao_position = int(ao_addr.split(':')[2])

                    # Устанавливаем новое состояние светодиода
                    new_led_state = str(int(input_json['state']['status'] and bool(int(input_json['state']['value']))))
                    temp_led_value[unit]['value_ao'] = temp_led_value[unit]['value_ao'][:ao_position] + new_led_state + \
                                                       temp_led_value[unit]['value_ao'][ao_position + 1:]

                    # Отравляем на брокер новое состояние ao
                    r.publish('axiomLogic:cmd:state', {'id': ao_addr, 'state': input_json['state']})

                # Отправляем на брокер состояние светодиодов для каждого модуля, если оно изменилось
                for unit in units:
                    if temp_led_value[unit] != led_value[unit]:
                        cmd = {'id': 'lr:%s' % unit, 'state': temp_led_value[unit]}
                        stream_logger.debug(
                            debug_colors['INFO'] % 'Отправлена команда "{}" по команде от веб клиента "{}"'.format(cmd,
                                                                                                                   input_json))
                        file_logger.info(
                            'Отправлена команда "{}" по команде от веб клиента "{}"'.format(cmd, input_json))
                        r.publish('axiomLogic:cmd:state', cmd)

                # Записываем новое состояние we в БД
                r.set(we, input_json['state'])

        # Цикл опроса очереди сообщений с COMhandler'a
        messages = []  # сюда сложим полученные сообщения
        message = p_com_handler.get_message()
        while message:
            input_json = eval(message['data'].decode())
            if input_json['id'] in ao_list:
                messages.append(input_json)
            message = p_com_handler.get_message()

        # Если были сообщения
        if messages:
            ao_statuses_in_messages = [input_json['state']['status'] for input_json in messages]
            ao_values_in_messages = [int(input_json['state']['value']) for input_json in messages]

            # Если хотя бы один выход включен, то общий чекбокс включен
            total_status = any(ao_statuses_in_messages)

            # Положение ползунка на всякий случай возьмем как среднее от полученных в сообщениях значений
            total_value = mean(ao_values_in_messages)

            # Записываем новое состояние we в БД
            r.set(we, {'status': total_status, 'value': total_value})
            # Отправляем на брокер новое состояние we
            cmd = {'id': we, 'state': {'status': total_status, 'value': total_value}}
            stream_logger.debug(debug_colors['INFO'] % 'Отправлено сообщение веб клиенту: "{}"'.format(cmd))
            file_logger.info('Отправлено сообщение веб клиенту: "{}"'.format(cmd))
            r.publish('AxiomLogic info', cmd)

            del messages

        sleep(0.01)


def connect_turnoff_we_to_ao_ch(we, ao_list, ch_list, settings):
    """
    По команде от веб элемента we отключаются все аналоговые выходы ao
    :param we: адрес веб элемента
    :param ao_list: контролируемые выходы ao
    :param settings: словарь с настройками
    :return:
    """

    # Подключаемся к брокеру
    r = redis.StrictRedis()
    # Подписываемся на сообщения от веб клиента
    p_web = r.pubsub(ignore_subscribe_messages=True)
    p_web.subscribe('Axiom commands')
    # Подписываемся на сообщения об изменении состояния от COMhandler'а
    p_com_handler = r.pubsub(ignore_subscribe_messages=True)
    p_com_handler.subscribe('axiomRS485Transceiver:info:state')

    # Составим перечень модулей, выходами которых управляем
    units = [ao_addr.split(':')[1] for ao_addr in ao_list]

    def web_messages_handler_target():
        """
        Запускается в потоке и обрабатывает сообщения от веб клиента
        Выключает все привязанные выходы
        """
        for message in p_web.listen():
            input_json = eval(message['data'].decode())
            if input_json['id'] == we:

                if input_json['state']['status'] == True:
                    print('Получено некорректное состояние %s от %s' % (input_json, we))
                    r.set(we, {'status': False})
                    r.publish('AxiomLogic info', {'id': we, 'state': {'status': False}})
                    continue

                # Выясним текущее состояние светодиодов соответствующих подконтрольным выходам
                led_value = dict()
                for unit in units:
                    led_value[unit] = eval(r.get('lr:{}'.format(unit)).decode())

                for ao_addr in ao_list:
                    # Определим к какому модулю относится данный выход
                    unit = ao_addr.split(':')[1]
                    # Определим номер данного выхода
                    ao_position = int(ao_addr.split(':')[2])

                    # Устанавливаем новое состояние светодиода
                    led_value[unit]['value_ao'] = led_value[unit]['value_ao'][:ao_position] + '0' + led_value[unit][
                                                                                                        'value_ao'][
                                                                                                    ao_position + 1:]

                    # Узнаем текущее состояние выхода
                    ao_state = get_state_from_redis(ao_addr, r)

                    # Отравляем на брокер новое состояние ao
                    cmd = {'id': ao_addr, 'state': {'status': False, 'value': ao_state['value']}}
                    log_msg = 'Отправлена команда "{}" по команде от веб клиента "{}"'.format(cmd, input_json)
                    stream_logger.debug(debug_colors['INFO'] % log_msg)
                    file_logger.info(log_msg)
                    r.publish('axiomLogic:cmd:state', cmd)

                # Отправляем на брокер состояние светодиодов для каждого модуля
                for unit in units:
                    cmd = {'id': 'lr:%s' % unit, 'state': led_value[unit]}
                    log_msg = 'Отправлена команда "{}" по команде от веб клиента "{}"'.format(cmd, input_json)
                    stream_logger.debug(debug_colors['INFO'] % log_msg)
                    file_logger.info(log_msg)
                    r.publish('axiomLogic:cmd:state', {'id': 'lr:%s' % unit, 'state': led_value[unit]})

                # Отправляем новое состояние для каждого выхода силового модуля на брокер
                for ch_addr in ch_list:
                    cmd = {'id': ch_addr, 'state': {'status': False}}
                    log_msg = 'Отправлена команда "{}" по команде от веб клиента "{}"'.format(cmd, input_json)
                    stream_logger.debug(debug_colors['INFO'] % log_msg)
                    file_logger.info(log_msg)
                    r.publish('axiomLogic:cmd:state', cmd)

    def web_updater_target():
        """
        Запускается в потоке и обновляет состояние веб элемента по сообещениям от com_handler
        """
        for message in p_com_handler.listen():
            input_json = eval(message['data'].decode())
            ch_addr = input_json['id']
            ch_state = input_json['state']

            if ch_addr in ch_list:
                if ch_state['status']:
                    # Если хотя бы один выход включен отправляем True
                    # (если состояние отличается от сохраненного в БД)
                    we_state = {'status': True}
                    if we_state != eval(r.get(we).decode()):
                        cmd = {'id': we, 'state': we_state}
                        log_msg = 'Отправлено сообщение веб клиенту: "{}" по сообщению от модуля обмена по UART: "{}"'.format(
                            cmd, input_json)
                        stream_logger.debug(debug_colors['INFO'] % log_msg)
                        file_logger.info(log_msg)
                        r.set(we, we_state)
                        r.publish('AxiomLogic info', cmd)

                else:
                    # Выясним в каком состоянии сейчас находятся привязанные выходы силовых модулей
                    # кроме того, для которого пришло сообщение
                    ch_statuses_list = []
                    temp_ch_list = ch_list[:]
                    temp_ch_list.remove(ch_addr)
                    for temp_ch_addr in temp_ch_list:
                        raw_ch_state = r.get(temp_ch_addr)
                        temp_ch_status = eval(raw_ch_state.decode())['status']
                        ch_statuses_list.append(temp_ch_status)

                    # Выясним включен ли хоть один из выходов
                    is_anyone_on = any(ch_statuses_list)
                    we_state = {'status': is_anyone_on}
                    if we_state != eval(r.get(we).decode()):
                        cmd = {'id': we, 'state': we_state}
                        log_msg = 'Отправлено сообщение веб клиенту: "{}" по сообщению от модуля обмена по UART: "{}"'.format(
                            cmd, input_json)
                        stream_logger.debug(debug_colors['INFO'] % log_msg)
                        file_logger.info(log_msg)
                        r.set(we, we_state)
                        r.publish('AxiomLogic info', cmd)

    # Создаем и запускаем потоки для обработки сообщений от веб клиента и com_handler
    web_messages_handler = Thread(target=web_messages_handler_target)
    web_updater = Thread(target=web_updater_target)

    web_messages_handler.start()
    web_updater.start()
    # web_messages_handler.join()
    # web_updater.join()

    # контроль работоспособности потоков
    while True:
        if not web_messages_handler.isAlive():
            log_writer('Перезапуск потока-обработчика команд от веб элемента {}'.format(we), 'ERROR')
            web_messages_handler = Thread(target=web_messages_handler_target)
            web_messages_handler.start()
        elif not web_updater.isAlive():
            log_writer('Перезапуск потока обновляющего состояние веб элемента {}'.format(we), 'ERROR')
            web_updater = Thread(target=web_updater_target)
            web_updater.start()
        sleep(1)


def connect_turnoff_button_to_ao_ch(di_list, ao_list, ch_list, settings):
    # Рассчитываем признаки короткого и длинного нажатия выключателя
    short_click_tokens, _ = calculate_click_tokens(settings['di queue len'])

    # Собираем имена модулей, с которых берем di_queue
    units = set()
    for di in di_list:
        unit = di.split(':')[1]
        units.add(unit)

    # Разобьем di на группы по принадлежности к модулям
    di_dict = {unit: [] for unit in units}
    for di in di_list:
        unit = di.split(':')[1]
        di_dict[unit].append(di)

    # Подписываемся на сообщения от каждого модуля
    r = redis.StrictRedis()
    p = r.pubsub(ignore_subscribe_messages=True)
    for unit in units:
        p.subscribe('di_queue:{}'.format(unit))

    for message in p.listen():

        # Выясним от какого модуля пришло сообщение
        channel = message['channel'].decode()
        unit = channel.split(':')[1]

        di_queue = eval(message['data'].decode())

        # Поочередно проверяем очередь состояний для всех входов этого модуля
        for di_address in di_dict[unit]:
            # номер текущего входа
            output = int(di_address.split(':')[-1])
            # формируем очередь сообщений для текущего входа
            single_di_queue = [di_state[output] for di_state in di_queue]

            if single_di_queue in short_click_tokens:

                # Выясним в каком состоянии сейчас светодиоды
                led_value = eval(r.get('lr:{}'.format(unit)).decode())

                led_value_ao = led_value['value_ao']
                led_value_do = led_value['value_do']
                new_led_value_ao = led_value_ao

                # Меняем статус подконтрольных выходов и соответствующих светодиодов
                for ao_addr in ao_list:

                    ao_position = int(ao_addr.split(':')[2])
                    new_led_value_ao = new_led_value_ao[:ao_position] + '0' + new_led_value_ao[ao_position + 1:]

                    # Если предыдущий статус True меняем его на False и отправляем на брокер
                    ao_state = eval(r.get(ao_addr).decode())
                    if ao_state['status']:
                        ao_state['status'] = False
                        cmd = {'id': ao_addr, 'state': ao_state}
                        log_msg = 'Отправлена команда "{}" по нажатию на выключатель "{}"'.format(cmd, di_address)
                        stream_logger.debug(debug_colors['INFO'] % log_msg)
                        file_logger.info(log_msg)
                        r.publish('axiomLogic:cmd:state', {'id': ao_addr, 'state': ao_state})

                # Отправляем новое состояние светодиодов на брокер если оно изменилось:
                if new_led_value_ao != led_value_ao:
                    cmd = {'id': 'lr:%s' % unit, 'state': {'value_ao': new_led_value_ao,
                                                           'value_do': led_value_do}}
                    log_msg = 'Отправлена команда "{}" по нажатию на выключатель "{}"'.format(cmd, di_address)
                    stream_logger.debug(debug_colors['INFO'] % log_msg)
                    file_logger.info(log_msg)
                    r.publish('axiomLogic:cmd:state', cmd)

                # Отправляем новое состояние для каждого выхода силового модуля на брокер
                for ch_addr in ch_list:
                    ch_state = eval(r.get(ch_addr).decode())
                    if ch_state['status']:
                        cmd = {'id': ch_addr, 'state': {'status': False}}
                        log_msg = 'Отправлена команда "{}" по нажатию на выключатель "{}"'.format(cmd, di_address)
                        stream_logger.debug(debug_colors['INFO'] % log_msg)
                        file_logger.info(log_msg)
                        r.publish('axiomLogic:cmd:state', cmd)


def connect_di_to_ch(di_list, ch_list, settings):
    # Создаем логгеры
    # stream_logger, file_logger = create_loggers(loglevel=loglevel, logfilename='/var/log/axiom/axiomLogic.log', logger_id=str(random.random()))

    # Устанавливаем имя процесса
    # setproctitle.setproctitle('axiomlogic:connection %s to %s' % (','.join(di_list), ','.join(ch_list)))

    # Обработка сигнала на завершение процесса
    # signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))

    # Рассчитываем признаки короткого и длинного нажатия выключателя
    short_click_tokens, long_click_tokens = calculate_click_tokens(settings['di queue len'])

    # Рассчитываем признак начала длинного нажатия на выключатель
    long_click_start_token = [0] + [1] * (settings['di queue len'] - 1)

    # Собираем имена модулей, с которых берем di_queue
    di_units = set()
    for di_addr in di_list:
        unit = di_addr.split(':')[1]
        di_units.add(unit)

    # Разобьем di на группы по принадлежности к модулям
    di_dict = {unit: [] for unit in di_units}
    for di in di_list:
        unit = di.split(':')[1]
        di_dict[unit].append(di)

    # Подписываемся на сообщения от каждого модуля
    r = redis.StrictRedis()
    p = r.pubsub(ignore_subscribe_messages=True)
    for unit in di_units:
        p.subscribe('di_queue:{}'.format(unit))

    # Проверим, чтобы в БД было состояние выходов ch, с котороыми мы работаем
    for ch_addr in ch_list:
        if not r.get(ch_addr):
            r.set(ch_addr, {'status': False})

    for message in p.listen():
        # Выясним от какого модуля пришло сообщение
        channel = message['channel'].decode()
        unit = channel.split(':')[1]

        di_queue = eval(message['data'].decode())

        # Поочередно проверяем очередь состояний для всех входов этого модуля
        for di_address in di_dict[unit]:
            # номер текущего входа
            output = int(di_address.split(':')[-1])
            # формируем очередь сообщений для текущего входа
            single_di_queue = [di_state[output] for di_state in di_queue]

            if single_di_queue in short_click_tokens:
                # Выясним в каком состоянии сейчас находятся подконтрольные выходы
                ch_status_list = []
                for ch_addr in ch_list:
                    ch_status = eval(r.get(ch_addr).decode())['status']
                    ch_status_list.append(ch_status)
                # Посчитаем среднее состояние контролируемых выходов
                average_ch_status = True if sum(int(ch_status) for ch_status in ch_status_list) > len(
                    ch_list) / 2 else False

                # Новый статус противоположен среднему предыдущему:
                new_ch_status = not average_ch_status

                # Отправляем новое состояние для каждого выхода на брокер
                for ch_addr in ch_list:
                    cmd = {'id': ch_addr, 'state': {'status': new_ch_status}}
                    stream_logger.debug(
                        debug_colors['INFO'] % 'Отправлена команда "{}" по нажатию на выключатель "{}"'.format(cmd,
                                                                                                               di_address))
                    file_logger.info('Отправлена команда "{}" по нажатию на выключатель "{}"'.format(cmd, di_address))
                    r.publish('axiomLogic:cmd:state', cmd)

            elif single_di_queue == long_click_start_token:
                # Отправляем новое состояние для каждого выхода на брокер
                for ch_addr in ch_list:
                    # Меняем состояние только если предыдущее не было True
                    if not eval(r.get(ch_addr).decode())['status']:
                        cmd = {'id': ch_addr, 'state': {'status': True}}
                        stream_logger.debug(
                            debug_colors['INFO'] % 'Отправлена команда "{}" по нажатию на выключатель "{}"'.format(cmd,
                                                                                                                   di_address))
                        file_logger.info(
                            'Отправлена команда "{}" по нажатию на выключатель "{}"'.format(cmd, di_address))
                        r.publish('axiomLogic:cmd:state', cmd)


def connect_checkbox_to_ch(we, ch_list, settings):
    """
    Управление выходами силового модуля по командам от веб элемента (чекбокс)
    :param we: адрес веб элемента
    :param ch_list: контролируемые выходы ch
    :param settings: словарь с настройками
    """
    # Подключаемся к брокеру
    r = redis.StrictRedis()
    # Подписываемся на сообщения от веб клиента
    p_web = r.pubsub(ignore_subscribe_messages=True)
    p_web.subscribe('Axiom commands')
    # Подписываемся на сообщения об изменении состояния от COMhandler'а
    p_com_handler = r.pubsub(ignore_subscribe_messages=True)
    p_com_handler.subscribe('axiomRS485Transceiver:info:state')

    db_we = WebElement.query.filter_by(addr=we).first()

    def web_messages_handler_target():
        """
        Запускается в потоке и обрабатывает сообщения от веб клиента
        """
        for message in p_web.listen():
            input_json = eval(message['data'].decode())
            if input_json['id'] == we:
                # Отправляем новое состояние для каждого модуля на брокер
                for ch_addr in ch_list:
                    ch_status = input_json['state']['status']
                    cmd = {'id': ch_addr, 'state': {'status': ch_status}}
                    stream_logger.debug(
                        debug_colors['INFO'] % 'Отправлена команда "{}" по команде от веб клиента "{}"'.format(cmd,
                                                                                                               input_json))
                    file_logger.info('Отправлена команда "{}" по команде от веб клиента "{}"'.format(cmd, input_json))
                    r.publish('axiomLogic:cmd:state', cmd)

    def web_updater_target():
        """
        Запускается в потоке и обновляет состояние веб элемента по сообещениям от com_handler
        """

        axiom_root = settings['root directory']
        db_path = os.path.join(axiom_root, journal_db)

        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()

        for message in p_com_handler.listen():
            input_json = eval(message['data'].decode())
            ch_addr = input_json['id']
            ch_state = input_json['state']
            if ch_addr in ch_list:
                if ch_state['status']:
                    # Если хотя бы один выход включен отправляем True
                    new_state = {'status': True}
                    cmd = {'id': we, 'state': new_state}
                    log_msg = 'Отправлено сообщение веб клиенту: "{}" по сообщению от модуля обмена по UART: "{}"'.format(
                        cmd, input_json)
                    stream_logger.debug(
                        debug_colors['INFO'] % log_msg)
                    file_logger.info(log_msg)
                    r.set(we, new_state)
                    r.publish('AxiomLogic info', {'id': we, 'state': new_state})

                else:
                    # Выясним в каком состоянии сейчас находятся подконтрольные выходы
                    # кроме того, для которого пришло сообщение
                    ch_state_list = []
                    temp_ch_list = ch_list[:]
                    temp_ch_list.remove(ch_addr)
                    for temp_ch_addr in temp_ch_list:
                        raw_ch_state = r.get(temp_ch_addr)
                        temp_ch_status = eval(raw_ch_state.decode())['status']
                        ch_state_list.append(temp_ch_status)

                    # Выясним включен ли хоть один из выходов
                    is_anyone_on = any(ch_state_list)
                    # Если хотя бы один выход включен отправляем True
                    new_state = {'status': is_anyone_on}
                    cmd = {'id': we, 'state': new_state}
                    log_msg = 'Отправлено сообщение веб клиенту: "{}" по сообщению от модуля обмена по UART: "{}"'.format(
                        cmd, input_json)
                    stream_logger.debug(debug_colors['INFO'] % log_msg)
                    file_logger.info(log_msg)
                    r.set(we, new_state)
                    r.publish('AxiomLogic info', cmd)

                log_status = 'включен' if new_state['status'] else 'выключен'
                event = '{} {}'.format(db_we.name, log_status)
                print('INSERT INTO log_entries (timestamp, event) VALUES ({}, "{}")'.format(time(), event))
                with connection:
                    cursor.execute('INSERT INTO log_entries (timestamp, event) VALUES ({}, "{}")'.format(time(), event))

    # Создаем и запускаем потоки для обработки сообщений от веб клиента и com_handler
    web_messages_handler = Thread(target=web_messages_handler_target)
    web_updater = Thread(target=web_updater_target)

    web_messages_handler.start()
    web_updater.start()
    # web_messages_handler.join()
    # web_updater.join()

    # контроль работоспособности потоков
    while True:
        if not web_messages_handler.isAlive():
            log_writer('Перезапуск потока-обработчика команд от веб элемента {}'.format(we), 'ERROR')
            web_messages_handler = Thread(target=web_messages_handler_target)
            web_messages_handler.start()
        elif not web_updater.isAlive():
            log_writer('Перезапуск потока обновляющего состояние веб элемента {}'.format(we), 'ERROR')
            web_updater = Thread(target=web_updater_target)
            web_updater.start()
        sleep(1)


# DEPRECATED
def connect_range_to_ch(we, ch_list, settings):
    """
    Управление выходами силового модуля по командам от веб элемента (слайдер+чекбокс)
    :param we: адрес веб элемента
    :param ch_list: контролируемые выходы ch
    :param settings: словарь с настройками
    """
    # setproctitle.setproctitle('axiomlogic:connection %s to %s' % (we, ','.join(ch_list)))

    # Обработка сигнала на завершение процесса
    # signal.signal(signal.SIGTERM, lambda signum, frame: sys.exit(0))

    # Подключаемся к брокеру
    r = redis.StrictRedis()
    # Подписываемся на сообщения от веб клиента
    p_web = r.pubsub(ignore_subscribe_messages=True)
    p_web.subscribe('Axiom commands')
    # Подписываемся на сообщения об изменении состояния от COMhandler'а
    p_com_handler = r.pubsub(ignore_subscribe_messages=True)
    p_com_handler.subscribe('axiomRS485Transceiver:info:state')

    # Проверим, чтобы в БД было состояние выходов ch, с котороыми мы работаем
    for ch_addr in ch_list:
        if not r.get(ch_addr):
            r.set(ch_addr, {'status': False})

    while True:
        # Цикл опроса очереди сообщений с веб-интерфейса
        message = p_web.get_message()
        if message:
            input_json = eval(message['data'].decode())
            if input_json['id'] == we:

                new_we_state = input_json['state']

                # Смотрим предыдущее состояние веб элемента
                prev_we_state = eval(r.get(we).decode())

                # Логика связи чекбокса с ползунком
                if ((prev_we_state['status'] and int(prev_we_state['value'])) and
                        (not new_we_state['status'] and int(new_we_state['value']))):
                    input_json['state'] = {'status': False, 'value': new_we_state['value']}

                elif ((prev_we_state['status'] and int(prev_we_state['value'])) and
                      (new_we_state['status'] and not int(new_we_state['value']))):
                    input_json['state'] = {'status': False, 'value': 0}

                elif ((not prev_we_state['status'] and not int(prev_we_state['value'])) and
                      (new_we_state['status'] and not int(new_we_state['value']))):
                    input_json['state'] = {'status': True, 'value': 50}

                elif ((not prev_we_state['status'] and not int(prev_we_state['value'])) and
                      (not new_we_state['status'] and int(new_we_state['value']))):
                    input_json['state'] = {'status': True, 'value': new_we_state['value']}

                # Отправляем новое состояние для каждого модуля на брокер
                for ch_addr in ch_list:
                    print('отправляем команду от %s' % we, {'status': input_json['state']['status']})
                    r.publish('axiomLogic:cmd:state',
                              {'id': ch_addr, 'state': {'status': input_json['state']['status']}})


def connect_watersensor_to_aquacontrol(we_crane, we_sensor_list, di_list, ch_list, *args):
    ch_addrs = []
    for ch_pair in ch_list:
        ch_addrs.append(ch_pair['open'])
        ch_addrs.append(ch_pair['close'])

    # Собираем имена модулей, с которых берем di_queue
    di_units = set()
    for di_addr in di_list:
        unit = di_addr.split(':')[1]
        di_units.add(unit)

    # Разобьем di на группы по принадлежности к модулям
    di_dict = {unit: [] for unit in di_units}
    for di in di_list:
        unit = di.split(':')[1]
        di_dict[unit].append(di)

    # словарь соответствия адресов цифровых входов датчиков протечки и их веб элементов
    di_to_we_sensor_mapping = {di_addr: we_addr for di_addr, we_addr in zip(di_list, we_sensor_list)}

    # Собираем имена модулей, на которых управляем выходами
    ch_units = set()
    for ch_addrs in ch_list:
        close_ch_addr = ch_addrs['close']
        open_ch_addr = ch_addrs['open']
        ch_unit = close_ch_addr.split(':')[1]
        ch_units.add(ch_unit)
        ch_unit = open_ch_addr.split(':')[1]
        ch_units.add(ch_unit)

    # Разобьем открывающие и закрывающие выходы по модулям, к которым они относятся
    open_ch_list = []
    close_ch_list = []
    for ch_addrs in ch_list:
        open_ch_list.append(ch_addrs['open'])
        close_ch_list.append(ch_addrs['close'])

    # Подписываемся на сообщения от каждого модуля
    r = redis.StrictRedis()
    p_di = r.pubsub(ignore_subscribe_messages=True)
    for unit in di_units:
        p_di.subscribe('di_queue:{}'.format(unit))
    p_web = r.pubsub(ignore_subscribe_messages=True)
    p_web.subscribe('Axiom commands')
    p_com = r.pubsub(ignore_subscribe_messages=True)
    p_com.subscribe('axiomRS485Transceiver:info:state')

    # Проверим, чтобы в БД было состояние выходов ch, с котороыми мы работаем
    for ch_addrs in ch_list:
        if not r.get(ch_addrs['open']):
            r.set(ch_addrs['open'], {'status': False})
        if not r.get(ch_addrs['close']):
            r.set(ch_addrs['close'], {'status': False})

    # Кран открыт
    crane_opened = True

    def rotate_crane(action):
        if action == 'open':
            open_ch_state = True
            close_ch_state = False
        elif action == 'close':
            open_ch_state = False
            close_ch_state = True
        elif action == 'reset':
            open_ch_state = False
            close_ch_state = False
        else:
            return

        # Отправляем новое состояние для каждого модуля на брокер
        for ch_addr in open_ch_list:
            cmd = {'id': ch_addr, 'state': {'status': open_ch_state}}
            stream_logger.debug(debug_colors['INFO'] % 'Отправлена команда "{}"'.format(cmd))
            file_logger.info('Отправлена команда "{}"'.format(cmd))
            r.publish('axiomLogic:cmd:state', cmd)
        for ch_addr in close_ch_list:
            cmd = {'id': ch_addr, 'state': {'status': close_ch_state}}
            stream_logger.debug(debug_colors['INFO'] % 'Отправлена команда "{}"'.format(cmd))
            file_logger.info('Отправлена команда "{}"'.format(cmd))
            r.publish('axiomLogic:cmd:state', cmd)

        last_action_time = time()

        # Ждем пока кран прокрутится, вытаскиваем сообщения, чтобы не накапливались
        exec_success_dict = {ch_unit: False for ch_unit in ch_units}
        while time() - last_action_time < 18:
            # Если мы сбрасываем управляющие сигналы, то после получения сообщений об установке
            # нового состояния на всех модулях, выходим из функции
            if action == 'reset':
                return
            # Если в течение 3 секунд после посылки команд не пришло сообщение об изменении состояния,
            # то считаем, что команды выполнить не удалось и посылаем снова

            p_di.get_message()
            p_web.get_message()
            p_com.get_message()

            sleep(0.01)
        # Помечаем кран как закрытый

        if action == 'open':
            crane_opened = True
        elif action == 'close':
            crane_opened = False

        # Записываем новое состояние we в БД
        we_state = {'status': crane_opened}
        cmd = {'id': we_crane, 'state': {'status': crane_opened}}

        log_msg = 'Отправлено сообщение веб клиенту: "{}" после завершения вращения вентиля'.format(cmd)
        stream_logger.debug(debug_colors['INFO'] % log_msg)
        file_logger.info(log_msg)

        r.set(we_crane, we_state)
        r.publish('AxiomLogic info', cmd)

        # Снимаем открывающий сигнал
        rotate_crane(action='reset')

    while True:
        message = p_di.get_message()
        if message:
            # Выясним от какого модуля пришло сообщение
            channel = message['channel'].decode()
            unit = channel.split(':')[1]

            di_queue = eval(message['data'].decode())

            # Поочередно проверяем очередь состояний для всех входов этого модуля
            for di_address in di_dict[unit]:
                # номер текущего входа
                output = int(di_address.split(':')[-1])
                # формируем очередь сообщений для текущего входа
                single_di_queue = [di_state[output] for di_state in di_queue]

                we_sensor_addr = di_to_we_sensor_mapping[di_address]

                if 1 in single_di_queue:
                    # Отправляем сообщение на индикатор датчика протечки в интерфейсе
                    prev_we_state = eval(r.get(we_sensor_addr).decode())
                    new_we_state = {'status': True}
                    if new_we_state != prev_we_state:
                        cmd = {'id': we_sensor_addr, 'state': {'status': True}}

                        log_msg = 'Отправлено сообщение веб клиенту: "{}" в следствие изменения состояния сигнала с датчика протечки'.format(
                            cmd)
                        stream_logger.debug(debug_colors['INFO'] % log_msg)
                        file_logger.info(log_msg)

                        r.set(we_sensor_addr, new_we_state)
                        r.publish('AxiomLogic info', cmd)

                    if crane_opened:
                        log_msg = 'Получен сигнал с датчика протечки "{}". Закрываем кран'.format(di_address)
                        stream_logger.debug(debug_colors['INFO'] % log_msg)
                        file_logger.info(log_msg)
                        rotate_crane(action='close')



                else:
                    # Отправляем сообщение на индикатор датчика протечки в интерфейсе
                    prev_we_state = eval(r.get(we_sensor_addr).decode())
                    new_we_state = {'status': False}
                    if new_we_state != prev_we_state:
                        cmd = {'id': we_sensor_addr, 'state': {'status': False}}

                        log_msg = 'Отправлено сообщение веб клиенту: "{}" в следствие изменения состояния сигнала с датчика протечки'.format(
                            cmd)
                        stream_logger.debug(debug_colors['INFO'] % log_msg)
                        file_logger.info(log_msg)

                        r.set(we_sensor_addr, new_we_state)
                        r.publish('AxiomLogic info', cmd)

        # Сообщения от веб клиента
        message = p_web.get_message()
        if message:
            input_json = eval(message['data'].decode())
            if input_json['id'] == we_crane:
                stream_logger.debug(
                    debug_colors['INFO'] % 'Получено сообщение от веб клиента "{}"'.format(input_json))
                file_logger.info('Получено сообщение от веб клиента "{}"'.format(input_json))
                # Открытие крана
                if input_json['state']['status']:
                    rotate_crane(action='open')
                # Закрытие крана
                else:
                    rotate_crane(action='close')

        sleep(0.01)


def connect_range_to_dimmer(we, ao_list, ch_list, settings):
    # Подключаемся к брокеру
    r = redis.StrictRedis(decode_responses=True)
    # Подписываемся на сообщения от веб клиента
    p_web = r.pubsub(ignore_subscribe_messages=True)
    p_web.subscribe('Axiom commands')
    # Подписываемся на сообщения об изменении состояния от COMhandler'а
    p_com_handler = r.pubsub(ignore_subscribe_messages=True)
    p_com_handler.subscribe('axiomRS485Transceiver:info:state')

    # Составим перечень модулей, аналоговыми выходами которых управляем
    # (для подсвечивания светодиодов)
    ao_units = [ao_addr.split(':')[1] for ao_addr in ao_list]

    if not r.get(we):
        r.set(we, {'value': 0, 'status': False})

    def web_messages_handler_target():
        """
        Запускается в потоке и обрабатывает сообщения от веб клиента
        """
        for message in p_web.listen():
            input_json = eval(message['data'])

            if input_json.get('id') == we:

                try:
                    new_we_state = input_json['state']

                    # Смотрим предыдущее состояние веб элемента
                    prev_we_state = eval(r.get(we))

                    # Логика связи чекбокса с ползунком
                    if ((prev_we_state['status'] and int(prev_we_state['value'])) and
                            (not new_we_state['status'] and int(new_we_state['value']))):
                        input_json['state'] = {'status': False, 'value': new_we_state['value']}

                    elif ((prev_we_state['status'] and int(prev_we_state['value'])) and
                          (new_we_state['status'] and not int(new_we_state['value']))):
                        input_json['state'] = {'status': False, 'value': 0}

                    elif ((not prev_we_state['status'] and not int(prev_we_state['value'])) and
                          (new_we_state['status'] and not int(new_we_state['value']))):
                        input_json['state'] = {'status': True, 'value': 50}

                    elif ((not prev_we_state['status'] and not int(prev_we_state['value'])) and
                          (not new_we_state['status'] and int(new_we_state['value']))):
                        input_json['state'] = {'status': True, 'value': new_we_state['value']}
                except Exception as e:
                    log_writer('Ошибка при попытке обработать сообщение от модуля сервера: {}'.format(e), 'DEBUG')
                    log_writer('некорректное сообщение от модуля сервера: {}'.format(input_json), 'ERROR')
                    continue

                # Отправляем новое состояние для каждого выхода силового модуля на брокер
                for ch_addr in ch_list:
                    cmd = {'id': ch_addr, 'state': {'status': input_json['state']['status']}}
                    log_msg = 'Отправлена команда "{}" по команде от веб клиента "{}"'.format(cmd, input_json)
                    stream_logger.debug(debug_colors['INFO'] % log_msg)
                    file_logger.info(log_msg)
                    r.publish('axiomLogic:cmd:state', cmd)

                # Выясним текущее состояние светодиодов соответствующих подконтрольным выходам
                led_value = dict()

                for unit in ao_units:
                    raw_led_value = r.get('lr:{}'.format(unit))
                    if raw_led_value:
                        led_value[unit] = eval(raw_led_value)
                    else:
                        led_value[unit] = {'value_ao': '0' * settings['num of ao'],
                                           'value_do': '0' * settings['num of do']}

                # Создадим копию, для последующего сравнения
                temp_led_value = deepcopy(led_value)

                for ao_addr in ao_list:
                    # Определим к какому модулю относится данный выход
                    ao_unit = ao_addr.split(':')[1]
                    # Определим номер данного выхода
                    ao_position = int(ao_addr.split(':')[2])

                    # Устанавливаем новое состояние светодиода
                    new_led_state = str(
                        int(input_json['state']['status'] and bool(int(input_json['state']['value']))))
                    temp_led_value[ao_unit]['value_ao'] = temp_led_value[ao_unit]['value_ao'][
                                                          :ao_position] + new_led_state + temp_led_value[ao_unit][
                                                                                              'value_ao'][
                                                                                          ao_position + 1:]

                    # Отравляем на брокер новое состояние ao
                    cmd = {'id': ao_addr, 'state': input_json['state']}
                    stream_logger.debug(
                        debug_colors['INFO'] % 'Отправлена команда "{}" по команде от веб клиента "{}"'.format(
                            cmd, input_json))
                    file_logger.info(
                        'Отправлена команда "{}" по команде от веб клиента "{}"'.format(cmd, input_json))
                    r.publish('axiomLogic:cmd:state', cmd)

                # Отправляем на брокер состояние светодиодов для каждого модуля, если оно изменилось
                for unit in ao_units:
                    if temp_led_value[unit] != led_value[unit]:
                        cmd = {'id': 'lr:%s' % unit, 'state': temp_led_value[unit]}
                        stream_logger.debug(debug_colors[
                                                'INFO'] % 'Отправлена команда "{}" по команде от веб клиента "{}"'.format(
                            cmd, input_json))
                        file_logger.info(
                            'Отправлена команда "{}" по команде от веб клиента "{}"'.format(cmd, input_json))
                        r.publish('axiomLogic:cmd:state', cmd)

    def web_updater_target():
        """
        Запускается в потоке и обновляет состояние веб элемента по сообещениям от com_handler
        """
        for message in p_com_handler.listen():
            input_json = eval(message['data'])
            addr = input_json['id']

            # Обработка сообщений об изменении состояния аналоговых выходов слаботочных модулей
            if addr in ao_list:
                ao_state = input_json['state']

                # значение поля status берем из БД
                we_state = eval(r.get(we))
                we_status = we_state['status']

                # Обновляется поле value у ВЭК
                cmd = {'id': we, 'state': {'status': we_status, 'value': ao_state['value']}}
                log_msg = 'Отправлено сообщение веб клиенту: "{}" по сообщению от модуля обмена по UART: "{}"'.format(
                    cmd, input_json)
                stream_logger.debug(debug_colors['INFO'] % log_msg)
                file_logger.info(log_msg)
                r.set(we, {'status': we_status, 'value': ao_state['value']})
                r.publish('AxiomLogic info', cmd)

            # Обработка сообщений об изменении состояни выходов силовых модулей
            elif addr in ch_list:
                ch_state = input_json['state']

                # значение поля value берем из БД
                we_state = eval(r.get(we))
                we_value = we_state['value']

                if ch_state['status']:
                    # Если хотя бы один выход включен отправляем True
                    new_state = {'status': True, 'value': we_value}
                    cmd = {'id': we, 'state': new_state}
                    log_msg = 'Отправлено сообщение веб клиенту: "{}" по сообщению от модуля обмена по UART: "{}"'.format(
                        cmd, input_json)
                    stream_logger.debug(debug_colors['INFO'] % log_msg)
                    file_logger.info(log_msg)
                    r.set(we, new_state)
                    r.publish('AxiomLogic info', cmd)

                else:
                    # Выясним в каком состоянии сейчас находятся подконтрольные выходы
                    # кроме того, для которого пришло сообщение
                    ch_state_list = []
                    temp_ch_list = ch_list[:]
                    temp_ch_list.remove(addr)
                    for temp_ch_addr in temp_ch_list:
                        raw_ch_state = r.get(temp_ch_addr)
                        temp_ch_status = eval(raw_ch_state)['status']
                        ch_state_list.append(temp_ch_status)

                    # Выясним включен ли хоть один из выходов
                    is_anyone_on = any(ch_state_list)
                    # Если хотя бы один выход включен отправляем True
                    new_state = {'status': is_anyone_on, 'value': we_value}
                    cmd = {'id': we, 'state': new_state}
                    log_msg = 'Отправлено сообщение веб клиенту: "{}" по сообщению от модуля обмена по UART: "{}"'.format(
                        cmd, input_json)
                    stream_logger.debug(debug_colors['INFO'] % log_msg)
                    file_logger.info(log_msg)
                    r.set(we, new_state)
                    r.publish('AxiomLogic info', cmd)

    # Создаем и запускаем потоки для обработки сообщений от веб клиента и com_handler
    web_messages_handler = Thread(target=web_messages_handler_target)
    web_updater = Thread(target=web_updater_target)

    web_messages_handler.start()
    web_updater.start()
    # web_messages_handler.join()
    # web_updater.join()

    # контроль работоспособности потоков
    while True:
        if not web_messages_handler.isAlive():
            log_writer('Перезапуск потока-обработчика команд от веб элемента {}'.format(we), 'ERROR')
            web_messages_handler = Thread(target=web_messages_handler_target)
            web_messages_handler.start()
        elif not web_updater.isAlive():
            log_writer('Перезапуск потока обновляющего состояние веб элемента {}'.format(we), 'ERROR')
            web_updater = Thread(target=web_updater_target)
            web_updater.start()
        sleep(1)


def connect_button_to_dimmer(di_list, ao_list, ch_list, settings):
    # Рассчитываем признаки короткого и длинного нажатия выключателя
    short_click_tokens, long_click_tokens = calculate_click_tokens(settings['di queue len'])

    # Рассчитываем признак начала длинного нажатия на выключатель
    long_click_start_token = [0] + [1] * (settings['di queue len'] - 1)

    # Собираем имена модулей, с которых берем di_queue
    di_units = set()
    for di_addr in di_list:
        di_unit = di_addr.split(':')[1]
        di_units.add(di_unit)

    # Разобьем di на группы по принадлежности к модулям
    di_dict = {di_unit: [] for di_unit in di_units}
    for di_addr in di_list:
        unit = di_addr.split(':')[1]
        di_dict[unit].append(di_addr)

    # Составим перечень модулей, аналоговыми выходами которых управляем
    # (для подсвечивания светодиодов)
    ao_units = [ao_addr.split(':')[1] for ao_addr in ao_list]

    # Подписываемся на сообщения от каждого модуля
    r = redis.StrictRedis()
    p = r.pubsub(ignore_subscribe_messages=True)
    for di_unit in di_units:
        p.subscribe('di_queue:{}'.format(di_unit))

    # Последнее значение, которое отправляли
    last_sent_ao_state = {ao_addr: None for ao_addr in ao_list}

    # Количество тактов опроса, которое нужно пропустить
    num_to_skip = {ao_addr: 0 for ao_addr in ao_list}

    for message in p.listen():
        # Выясним от какого модуля пришло сообщение
        channel = message['channel'].decode()
        unit = channel.split(':')[1]

        di_queue = eval(message['data'].decode())

        # Поочередно проверяем очередь состояний для всех входов этого модуля
        for di_address in di_dict[unit]:
            # номер текущего входа
            output = int(di_address.split(':')[-1])
            # формируем очередь сообщений для текущего входа
            single_di_queue = [di_state[output] for di_state in di_queue]

            # if di_address == 'di:m4:1':
            #     print(single_di_queue)

            if single_di_queue in short_click_tokens:
                # Выясним в каком состоянии сейчас находятся подконтрольные выходы
                ao_state_list = []
                for ao in ao_list:
                    ao_state = eval(r.get(ao).decode())
                    ao_state_list.append(ao_state)

                # Вычисляем среднее состояние. Если больше половины включены, то True, иначе False
                average_status = True if sum([int(state['status']) for state in ao_state_list]) > len(
                    ao_list) / 2 else False

                # Выясним в каком состоянии сейчас светодиоды
                led_value = eval(r.get('lr:{}'.format(unit)).decode())

                led_value_ao = led_value['value_ao']
                led_value_do = led_value['value_do']

                # Меняем статус подконтрольных выходов и соответствующих светодиодов
                for ao_addr, ao_state in zip(ao_list, ao_state_list):
                    ao_state['status'] = not average_status
                    ao_position = int(ao_addr.split(':')[2])
                    led_value_ao = led_value_ao[:ao_position] + str(int(not average_status)) + led_value_ao[
                                                                                               ao_position + 1:]

                    # Отправляем команду на изменение через редис
                    cmd = {'id': ao_addr, 'state': ao_state}
                    stream_logger.debug(
                        debug_colors['INFO'] % 'Отправлена команда "{}" по нажатию на выключатель "{}"'.format(cmd,
                                                                                                               di_address))
                    file_logger.info('Отправлена команда "{}" по нажатию на выключатель "{}"'.format(cmd, di_address))
                    r.publish('axiomLogic:cmd:state', cmd)

                # Отправляем новое состояние светодиодов на брокер
                cmd = {'id': 'lr:%s' % unit, 'state': {'value_ao': led_value_ao, 'value_do': led_value_do}}
                stream_logger.debug(
                    debug_colors['INFO'] % 'Отправлена команда "{}" по нажатию на выключатель "{}"'.format(cmd,
                                                                                                           di_address))
                file_logger.info('Отправлена команда "{}" по нажатию на выключатель "{}"'.format(cmd, di_address))
                r.publish('axiomLogic:cmd:state', cmd)

                # Отправляем новое состояние для каждого выхода силового модуля на брокер
                for ch_addr in ch_list:
                    cmd = {'id': ch_addr, 'state': {'status': not average_status}}
                    stream_logger.debug(
                        debug_colors['INFO'] % 'Отправлена команда "{}" по нажатию на выключатель "{}"'.format(cmd,
                                                                                                               di_address))
                    file_logger.info('Отправлена команда "{}" по нажатию на выключатель "{}"'.format(cmd, di_address))
                    r.publish('axiomLogic:cmd:state', cmd)

            elif single_di_queue in long_click_tokens[:-1]:
                print('длинное нажатие на выключатель', di_address)
                # Выясним в каком состоянии сейчас находятся подконтрольные выходы
                ao_state_list = []
                for ao in ao_list:
                    ao_state = eval(r.get(ao).decode())
                    ao_state_list.append(ao_state)

                # Выясним в каком состоянии сейчас светодиоды
                led_value = eval(r.get('lr:{}'.format(unit)).decode())

                led_value_ao = led_value['value_ao']
                temp_led_value_ao = led_value_ao
                led_value_do = led_value['value_do']

                # Меняем статус подконтрольных выходов и соответствующих светодиодов
                for ao, ao_state in zip(ao_list, ao_state_list):
                    # Пропускаем такты, если до этого дошли до максимума
                    if num_to_skip[ao]:
                        num_to_skip[ao] -= 1
                        continue

                    prev_ao_state = ao_state.copy()
                    ao_state['status'] = True
                    new_ao_value = int(ao_state['value'])
                    new_ao_value += settings['ao increment value']

                    if new_ao_value > 100:
                        new_ao_value -= 100
                    ao_state['value'] = int(new_ao_value)
                    # Если состояние повторяется, пропускаем такт
                    if ao_state == last_sent_ao_state[ao]:
                        last_sent_ao_state[ao] = prev_ao_state
                        continue
                    ao_position = int(ao.split(':')[2])
                    temp_led_value_ao = temp_led_value_ao[:ao_position] + '1' + temp_led_value_ao[ao_position + 1:]

                    # Отправляем команду на изменение через редис
                    cmd = {'id': ao, 'state': ao_state}
                    stream_logger.debug(
                        debug_colors['INFO'] % 'Отправлена команда "{}" по нажатию на выключатель "{}"'.format(cmd,
                                                                                                               di_address))
                    file_logger.info('Отправлена команда "{}" по нажатию на выключатель "{}"'.format(cmd, di_address))
                    r.publish('axiomLogic:cmd:state', cmd)
                    # Обновляем последнее отправленное состояние
                    last_sent_ao_state[ao] = ao_state

                    # Если дошли до максимума
                    if 100 - settings['ao increment value'] < new_ao_value <= 100:
                        num_to_skip[ao] = settings['delay on dimmer max value']
                        continue

                if temp_led_value_ao != led_value_ao:
                    cmd = {'id': 'lr:%s' % unit, 'state': {'value_ao': temp_led_value_ao, 'value_do': led_value_do}}
                    stream_logger.debug(
                        debug_colors['INFO'] % 'Отправлена команда "{}" по нажатию на выключатель "{}"'.format(cmd,
                                                                                                               di_address))
                    file_logger.info('Отправлена команда "{}" по нажатию на выключатель "{}"'.format(cmd, di_address))
                    r.publish('axiomLogic:cmd:state', cmd)

                if single_di_queue == long_click_start_token:
                    # Отправляем новое состояние для каждого выхода на брокер
                    for ch_addr in ch_list:
                        # Меняем состояние только если предыдущее не было True
                        if not eval(r.get(ch_addr).decode())['status']:
                            cmd = {'id': ch_addr, 'state': {'status': True}}
                            stream_logger.debug(
                                debug_colors['INFO'] % 'Отправлена команда "{}" по нажатию на выключатель "{}"'.format(
                                    cmd, di_address))
                            file_logger.info(
                                'Отправлена команда "{}" по нажатию на выключатель "{}"'.format(cmd, di_address))
                            r.publish('axiomLogic:cmd:state', cmd)

            elif single_di_queue == long_click_tokens[-1]:
                # Обнуляем количество тактов для пропуска
                num_to_skip = {ao_addr: 0 for ao_addr in ao_list}


def connect_reed_switch_to_we(di_list, we_list, *args, **kwargs):
    # Собираем имена модулей, с которых берем di_queue
    di_units = set(di_addr.split(':')[1] for di_addr in di_list)

    # Разобьем di на группы по принадлежности к модулям
    di_dict = dict().fromkeys(di_units, [])
    for di_addr in di_list:
        unit = di_addr.split(':')[1]
        di_dict[unit].append(di_addr)

    # словарь соответствия цифровых входов веб элементам:
    di_we_matching = {di: we for di, we in zip(di_list, we_list)}

    # Подписываемся на сообщения от каждого модуля
    r = redis.StrictRedis()
    p = r.pubsub(ignore_subscribe_messages=True)
    for di_unit in di_units:
        p.subscribe('di_queue:{}'.format(di_unit))

    for message in p.listen():
        # Выясним от какого модуля пришло сообщение
        channel = message['channel'].decode()
        unit = channel.split(':')[1]

        di_queue = eval(message['data'].decode())

        # Поочередно проверяем очередь состояний для всех входов этого модуля
        for di_address in di_dict[unit]:
            # номер текущего входа
            output = int(di_address.split(':')[-1])
            # формируем очередь сообщений для текущего входа
            single_di_queue = [di_state[output] for di_state in di_queue]

            # Если все единицы, значит окно закрыто
            if all(single_di_queue):
                new_we_state = {'status': True}

            # Если все нули, значит окно открыто
            elif not any(single_di_queue):
                new_we_state = {'status': False}

            else:
                continue

            # Смотрим предыдущее состояние вебэлемента
            we_address = di_we_matching[di_address]
            prev_we_state = eval(r.get(we_address).decode())

            if new_we_state != prev_we_state:
                msg = {'id': we_address, 'state': new_we_state}
                log_msg = 'Отправлено сообщение веб клиенту: "{}" в следствие изменения сигнала поступающего с геркона'.format(
                    msg)
                stream_logger.debug(debug_colors['INFO'] % log_msg)
                file_logger.info(log_msg)
                r.set(we_address, new_we_state)
                r.publish('AxiomLogic info', msg)


def connect_checkbox_to_new_ch(we_addr, ch_addr, settings):
    """
    Управление выходом нового силового модуля по командам от веб элемента (чекбокс)
    :param ch_addr: адрес силового выхода
    :param we_addr: адрес веб элемента
    :param settings: словарь с настройками
    """
    # Подключаемся к брокеру
    r = redis.StrictRedis()
    # Подписываемся на сообщения от модуля "Веб-сервер"
    p_web = r.pubsub(ignore_subscribe_messages=True)
    p_web.subscribe('axiomWebserver:cmd:state')
    # Подписываемся на сообщения об изменении состояния от модуля "Логика"
    p_low = r.pubsub(ignore_subscribe_messages=True)
    p_low.subscribe('axiomLowLevelCommunication:info:state')

    db_we = WebElement.query.filter_by(addr=we_addr).first()

    def web_messages_handler_target():
        """
        Запускается в потоке и обрабатывает сообщения от модуля "Веб-сервер"
        """
        for message in p_web.listen():
            input_json = eval(message['data'].decode())
            if input_json['id'] == we_addr:
                # Отправляем новое состояние для каждого модуля на брокер
                ch_status = input_json['state']['status']
                cmd = {'addr': ch_addr, 'state': {'status': ch_status}}
                log_msg = 'Отправлена команда "{}" по команде от веб клиента "{}"'.format(cmd, input_json)
                logger.write_log(log_msg=log_msg, log_level='INFO')
                r.publish('axiomLogic:cmd:state', json.dumps(cmd))

    def web_updater_target():
        """
        Запускается в потоке и обновляет состояние веб элемента
        по сообщениям от модуля "Взаимодействие с низким уровнем"
        """
        axiom_root = settings['root directory']
        db_path = os.path.join(axiom_root, journal_db)

        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()

        for message in p_low.listen():
            input_json = eval(message['data'].decode())

            msg_ch_addr = input_json['addr']

            if msg_ch_addr == ch_addr:

                ch_state = input_json['state']

                # Транслируем полученное новое состояние силового выхода на модуль "Веб-сервер"
                r.publish('axiomLogic:info:state', {'id': we_addr, 'state': ch_state})
                cmd = {'id': we_addr, 'state': ch_state}
                log_msg = 'Отправлено сообщение веб клиенту: "{}" по сообщению от модуля' \
                          ' "Взаимодействие с низким уровнем": "{}"'.format(cmd, input_json)
                logger.write_log(log_msg=log_msg, log_level='INFO')
                r.set(we_addr, ch_state)

                log_status = 'включен' if ch_state['status'] == '5' else 'выключен'
                event = '{} {}'.format(db_we.name, log_status)
                with connection:
                    cursor.execute('INSERT INTO log_entries (timestamp, event) VALUES ({}, "{}")'.format(time(), event))

    # <editor-fold desc="запуск и контроль работы потоков">
    web_messages_handler = Thread(target=web_messages_handler_target)
    web_updater = Thread(target=web_updater_target)

    web_messages_handler.start()
    web_updater.start()
    # web_messages_handler.join()
    # web_updater.join()

    # контроль работоспособности потоков
    while True:
        if not web_messages_handler.isAlive():
            log_writer('Перезапуск потока-обработчика команд от веб элемента {}'.format(we_addr), 'ERROR')
            web_messages_handler = Thread(target=web_messages_handler_target)
            web_messages_handler.start()
        elif not web_updater.isAlive():
            log_writer('Перезапуск потока обновляющего состояние веб элемента {}'.format(we_addr), 'ERROR')
            web_updater = Thread(target=web_updater_target)
            web_updater.start()
        sleep(1)
    # </editor-fold>


axiom_functions = {
    connect_di_to_ao.__name__: connect_di_to_ao,
    connect_range_to_ao.__name__: connect_range_to_ao,
    connect_turnoff_we_to_ao_ch.__name__: connect_turnoff_we_to_ao_ch,
    connect_turnoff_button_to_ao_ch.__name__: connect_turnoff_button_to_ao_ch,
    connect_di_to_ch.__name__: connect_di_to_ch,
    connect_checkbox_to_ch.__name__: connect_checkbox_to_ch,
    connect_watersensor_to_aquacontrol.__name__: connect_watersensor_to_aquacontrol,
    connect_range_to_ch.__name__: connect_range_to_ch,
    connect_range_to_dimmer.__name__: connect_range_to_dimmer,
    connect_button_to_dimmer.__name__: connect_button_to_dimmer,
    connect_reed_switch_to_we.__name__: connect_reed_switch_to_we,
    connect_checkbox_to_new_ch.__name__: connect_checkbox_to_new_ch,

}
