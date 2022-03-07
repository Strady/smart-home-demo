import copy
import json
import os
import threading
import time
from unittest import TestCase, skip

import redis

from axiomLowLevelCommunication.highLowTransceiver import HighLowTransceiver


class TestHighLowTransceiver(TestCase):

    def setUp(self):
        """
        Настраивает тестовое окружение
        """
        # Загружаем настройки
        default_fname = '/etc/axiom/settings_input_unit.json'
        fname = os.environ.get('AXIOM_SETTINGS', default=default_fname)
        with open(fname) as settings_file:
            self.settings = json.load(settings_file)

        # Подключаемся к брокеру
        self.r = redis.StrictRedis(decode_responses=True)

        # Создаем экземляр трансивера
        self.hlt = HighLowTransceiver()


class TestInit(TestHighLowTransceiver):
    """
    Тесты функции __init__
    """

    def test_load_correct_settings(self):
        """
        Тест проверяет, что при инициализации объекта HighLowTransceiver
        загружается корректный набор настроек
        """
        # TODO hlTransceiver - кандидат на перемещение в self.setUp
        hlTransceiver = HighLowTransceiver()

        self.assertEqual(hlTransceiver.settings, self.settings)

    def test_open_serial_port_for_every_power_unit(self):
        """
        Тест проверяет, что при инициализации объекта HighLowTransceiver
        для каждого силового модуля открывается последовательный порт,
        заданный ему в настройках
        """
        hlTransceiver = HighLowTransceiver()

        for unit_addr, com_addr in self.settings['power units'].items():
            self.assertEqual(hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].ser.port, com_addr)
            self.assertEqual(hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].ser.isOpen(), True)


class TestRead(TestHighLowTransceiver):
    """
    Тесты опроса состояния силовых модулей
    """

    def test_can_collect_state_for_every_power_unit(self):
        """
        Тест проверяет, что функция collect_units_state актуализирует
        структуру состояния всех силовых модулей
        """
        hlTransceiver = HighLowTransceiver()
        time.sleep(1)
        for _ in range(3):
            hlTransceiver.collect_units_state()
            time.sleep(0.01)

        for unit_addr in self.settings['power units']:
            self.assertNotEqual(hlTransceiver.power_units_state_dicts[unit_addr]['st']['cnt'], '0')
            self.assertNotEqual(hlTransceiver.power_units_state_dicts[unit_addr]['adc']['cnt'], '0')
            self.assertNotEqual(hlTransceiver.power_units_state_dicts[unit_addr]['ld']['cnt'], '0')

    def test_reader_target_constantly_updates_state_struct_for_every_power_unit(self):
        """
        Тест проверяет, что функция reader_target постоянно
        обновляет структуру состояния для каждого силового модуля
        """
        hlTransceiver = HighLowTransceiver()

        hlTransceiver.isRunning = True

        threading.Thread(target=hlTransceiver.reader_target).start()

        time.sleep(1)

        state1 = copy.deepcopy(hlTransceiver.power_units_state_dicts)

        time.sleep(1)

        state2 = copy.deepcopy(hlTransceiver.power_units_state_dicts)

        try:
            self.assertTrue(state1 != state2)
        except AssertionError:
            raise
        finally:
            hlTransceiver.isRunning = False


class TestInitPowerUnit(TestHighLowTransceiver):
    """
    Тесты инициализации низкоуровневого ПО силовых модулей
    """

    def test_run_power_unit(self):
        """
        Тест проверяет, что функция run_power_unit может запустить
        каждый силовой модуль
        """

        hlTransceiver = HighLowTransceiver()

        hlTransceiver.isRunning = True
        threading.Thread(target=hlTransceiver.reader_target).start()

        time.sleep(1)

        for unit_addr in self.settings['power units']:

            tries = 3

            rst_cmd = 'rst {}'.format(unit_addr)

            # Сбрасываем состояние модуля (не всегда работает с первого раза)
            while tries:
                send_time = time.time()
                hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write(rst_cmd)

                while True:
                    try:
                        self.assertEqual(hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'], '0')
                        self.assertEqual(hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'], '0')
                        tries = 1
                        break
                    except AssertionError:
                        if time.time() - send_time > 3:
                            if not tries - 1:
                                hlTransceiver.isRunning = False
                                raise
                            else:
                                break
                        else:
                            time.sleep(0.1)
                tries -= 1

            hlTransceiver.run_power_unit(unit_addr)

            time.sleep(1)

            hlTransceiver.isRunning = False

            self.assertNotEqual(hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'], '0')
            self.assertNotEqual(hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'], '0')

    def test_configure_power_unit(self):
        """
        Тест проверяет, что функция configure_power_unit может запустить
        каждый силовой модуль
        """

        hlTransceiver = HighLowTransceiver()

        hlTransceiver.isRunning = True
        threading.Thread(target=hlTransceiver.reader_target).start()

        time.sleep(1)

        for unit_addr in self.settings['power units']:

            tries = 3

            rst_cmd = 'rst {}'.format(unit_addr)

            # Сбрасываем состояние модуля (не всегда работает с первого раза)
            while tries:
                send_time = time.time()
                hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write(rst_cmd)

                while True:
                    try:
                        self.assertEqual(hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'], '0')
                        self.assertEqual(hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'], '0')
                        tries = 1
                        break
                    except AssertionError:
                        if time.time() - send_time > 3:
                            if not tries - 1:
                                hlTransceiver.isRunning = False
                                raise
                            else:
                                break
                        else:
                            time.sleep(0.1)
                tries -= 1

            # Запускаем силовой модуль
            hlTransceiver.run_power_unit(unit_addr)

            time.sleep(1)

            self.assertNotEqual(hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'], '0')
            self.assertNotEqual(hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'], '0')

            # Проверяем, что хотя бы один из выходов находится в состоянии 3
            check_state_time = time.time()
            while True:
                try:
                    self.assertTrue(hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] == '3' or
                                    hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] == '3')
                    break
                except AssertionError:
                    if time.time() - check_state_time < 5:
                        time.sleep(0.1)
                        continue
                    else:
                        hlTransceiver.isRunning = False
                        raise

            hlTransceiver.configure_power_unit(unit_addr)
            time.sleep(1)

            # Проверяем, что ни один из выходов не находится в состоянии 3
            check_state_time = time.time()
            while True:
                try:
                    self.assertTrue(hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] != '3' and
                                    hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] != '3')
                    break
                except AssertionError:
                    if time.time() - check_state_time < 3:
                        time.sleep(0.1)
                        continue
                    else:
                        hlTransceiver.isRunning = False
                        raise

            # Останавливаем поток опроса
            hlTransceiver.isRunning = False

    def test_init_power_unit(self):
        """
        Тест проверяет, что функция init_power_unit может инициализировать
        (запустить и конфигурировать) каждый силовой модуль
        """

        hlTransceiver = HighLowTransceiver()

        hlTransceiver.isRunning = True
        threading.Thread(target=hlTransceiver.reader_target).start()

        time.sleep(1)

        for unit_addr in self.settings['power units']:

            tries = 3

            rst_cmd = 'rst {}'.format(unit_addr)

            # Сбрасываем состояние модуля (не всегда работает с первого раза)
            while tries:
                send_time = time.time()
                hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write(rst_cmd)

                while True:
                    try:
                        self.assertEqual(hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'], '0')
                        self.assertEqual(hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'], '0')
                        tries = 1
                        break
                    except AssertionError:
                        if time.time() - send_time > 3:
                            if not tries - 1:
                                hlTransceiver.isRunning = False
                                raise
                            else:
                                break
                        else:
                            time.sleep(0.1)
                tries -= 1

            # Запускаем силовой модуль
            hlTransceiver.init_power_unit(unit_addr)


            # Проверяем, что один из выходов не находится в состоянии 0 или 3
            check_state_time = time.time()
            while True:
                try:
                    self.assertTrue(hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] != '0' and
                                    hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] != '0')

                    self.assertTrue(hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] != '3' and
                                    hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] != '3')
                    break
                except AssertionError:
                    if time.time() - check_state_time < 5:
                        time.sleep(0.1)
                        continue
                    else:
                        hlTransceiver.isRunning = False
                        raise

            # Останавливаем поток опроса
            hlTransceiver.isRunning = False

    def test_init_power_unit_if_unit_is_not_configured(self):
        """
        Тест проверяет, что функция init_power_unit может конфигурировать
        модуль, если хотя бы один из выходов находится в состоянии 3
        """

        hlTransceiver = HighLowTransceiver()

        hlTransceiver.isRunning = True
        threading.Thread(target=hlTransceiver.reader_target).start()

        time.sleep(1)

        for unit_addr in self.settings['power units']:

            tries = 3

            rst_cmd = 'rst {}'.format(unit_addr)

            # Сбрасываем состояние модуля (не всегда работает с первого раза)
            while tries:
                send_time = time.time()
                hlTransceiver.unit_addrs_to_transceivers_map[unit_addr].write(rst_cmd)

                while True:
                    try:
                        self.assertEqual(hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'], '0')
                        self.assertEqual(hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'], '0')
                        tries = 1
                        break
                    except AssertionError:
                        if time.time() - send_time > 3:
                            if not tries - 1:
                                hlTransceiver.isRunning = False
                                raise
                            else:
                                break
                        else:
                            time.sleep(0.1)
                tries -= 1

            # Запускаем силовой модуль
            self.assertTrue(hlTransceiver.run_power_unit(unit_addr),
                            msg='Не удалось запустить силовой модуль {}'.format(unit_addr))


            # Проверяем, что хотя бы один из выходов находится в состоянии 3
            check_state_time = time.time()
            while True:
                try:
                    self.assertTrue(hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] == '3' or
                                    hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] == '3')
                    break
                except AssertionError:
                    if time.time() - check_state_time < 5:
                        time.sleep(0.1)
                        continue
                    else:
                        hlTransceiver.isRunning = False
                        raise

            hlTransceiver.configure_power_unit(unit_addr)
            time.sleep(1)

            # Проверяем, что ни один из выходов не находится в состоянии 3
            check_state_time = time.time()
            while True:
                try:
                    self.assertTrue(hlTransceiver.power_units_state_dicts[unit_addr]['st']['state1'] != '3' and
                                    hlTransceiver.power_units_state_dicts[unit_addr]['st']['state2'] != '3')
                    break
                except AssertionError:
                    if time.time() - check_state_time < 3:
                        time.sleep(0.1)
                        continue
                    else:
                        hlTransceiver.isRunning = False
                        raise

            # Останавливаем поток опроса
            hlTransceiver.isRunning = False


class TestWrite(TestHighLowTransceiver):
    """
    Тесты приема и отправки команд на силовые модули
    """

    # Включает все выходы! Запускать только на макете!
    # (или если ты знаешь, что делаешь)
    @skip
    def test_can_turn_on_outputs(self):
        """
        Тест проверяет, что при отправке через брокер
        команды на включение выхода, происходит включение выхода
        """

        self.hlt.isRunning = True

        # Запускаем потоки опроса и отправки команд
        threading.Thread(target=self.hlt.reader_target).start()
        threading.Thread(target=self.hlt.writer_target).start()

        time.sleep(1)

        for unit_addr in self.settings['power units']:

            tries = 3

            rst_cmd = 'rst {}'.format(unit_addr)

            # Сбрасываем состояние модуля (не всегда работает с первого раза)
            while tries:
                send_time = time.time()
                self.hlt.unit_addrs_to_transceivers_map[unit_addr].write(rst_cmd)

                while True:
                    try:
                        self.assertEqual(self.hlt.power_units_state_dicts[unit_addr]['st']['state1'], '0')
                        self.assertEqual(self.hlt.power_units_state_dicts[unit_addr]['st']['state2'], '0')
                        tries = 1
                        break
                    except AssertionError:
                        if time.time() - send_time > 3:
                            if not tries - 1:
                                self.hlt.isRunning = False
                                raise
                            else:
                                break
                        else:
                            time.sleep(0.1)
                tries -= 1

            # Инициализируем силовой модуль
            self.hlt.init_power_unit(unit_addr)

            # Проверяем, что один из выходов не находится в состоянии 0 или 3
            check_state_time = time.time()
            while True:
                try:
                    self.assertTrue(self.hlt.power_units_state_dicts[unit_addr]['st']['state1'] != '0' and
                                    self.hlt.power_units_state_dicts[unit_addr]['st']['state2'] != '0')

                    self.assertTrue(self.hlt.power_units_state_dicts[unit_addr]['st']['state1'] != '3' and
                                    self.hlt.power_units_state_dicts[unit_addr]['st']['state2'] != '3')
                    break
                except AssertionError:
                    if time.time() - check_state_time < 5:
                        time.sleep(0.1)
                        continue
                    else:
                        self.hlt.isRunning = False
                        raise

            # Отправляем через брокер команду включения первого выхода
            cmd = str({'addr': 'ch:{}:1'.format(unit_addr), 'state': {'status': '5'}})
            self.r.publish(channel='axiomLogic:cmd:state', message=cmd)

            # Отправляем через брокер команду включения второго выхода
            cmd = str({'addr': 'ch:{}:2'.format(unit_addr), 'state': {'status': '5'}})
            self.r.publish(channel='axiomLogic:cmd:state', message=cmd)

            check_state_time = time.time()
            while True:
                try:
                    self.assertEqual(self.hlt.power_units_state_dicts[unit_addr]['st']['state1'], '5',
                                     msg='Первый канал модуля {} не включился'.format(unit_addr))

                    self.assertEqual(self.hlt.power_units_state_dicts[unit_addr]['st']['state2'], '5',
                                     msg='Второй канал модуля {} не включился'.format(unit_addr))
                    break
                except AssertionError:
                    if time.time() - check_state_time < 2:
                        time.sleep(0.1)
                        continue
                    else:
                        self.hlt.isRunning = False
                        raise

            # Останавливаем потоки опроса и отправки команд
            self.hlt.isRunning = False

    # Включает все выходы! Запускать только на макете!
    # (или если ты знаешь, что делаешь)
    @skip
    def test_can_turn_on_outputs_if_unit_not_initialized(self):
        """
        Тест проверяет, что при отправке через брокер
        команды на включение выхода, происходит включение выхода,
        если модуль не был инициализирован
        """

        self.hlt.isRunning = True

        # Запускаем потоки опроса и отправки команд
        threading.Thread(target=self.hlt.reader_target).start()
        threading.Thread(target=self.hlt.writer_target).start()

        time.sleep(1)

        for unit_addr in self.settings['power units']:

            tries = 3

            rst_cmd = 'rst {}'.format(unit_addr)

            # Сбрасываем состояние модуля (не всегда работает с первого раза)
            while tries:
                send_time = time.time()
                self.hlt.unit_addrs_to_transceivers_map[unit_addr].write(rst_cmd)

                while True:
                    try:
                        self.assertEqual(self.hlt.power_units_state_dicts[unit_addr]['st']['state1'], '0')
                        self.assertEqual(self.hlt.power_units_state_dicts[unit_addr]['st']['state2'], '0')
                        tries = 1
                        break
                    except AssertionError:
                        if time.time() - send_time > 3:
                            if not tries - 1:
                                self.hlt.isRunning = False
                                raise
                            else:
                                break
                        else:
                            time.sleep(0.1)
                tries -= 1

            # Отправляем через брокер команду включения первого выхода
            cmd = str({'addr': 'ch:{}:1'.format(unit_addr), 'state': {'status': '5'}})
            self.r.publish(channel='axiomLogic:cmd:state', message=cmd)
            # Отправляем через брокер команду включения второго выхода
            cmd = str({'addr': 'ch:{}:2'.format(unit_addr), 'state': {'status': '5'}})
            self.r.publish(channel='axiomLogic:cmd:state', message=cmd)

            check_state_time = time.time()
            while True:
                try:
                    self.assertEqual(self.hlt.power_units_state_dicts[unit_addr]['st']['state1'], '5',
                                     msg='Первый канал модуля {} не включился'.format(unit_addr))

                    self.assertEqual(self.hlt.power_units_state_dicts[unit_addr]['st']['state2'], '5',
                                     msg='Первый канал модуля {} не включился'.format(unit_addr))
                    break
                except AssertionError:
                    if time.time() - check_state_time < 5:
                        time.sleep(0.1)
                        continue
                    else:
                        self.hlt.isRunning = False
                        raise

            # Останавливаем потоки опроса и отправки команд
            self.hlt.isRunning = False

    def test_can_turn_off_outputs(self):
        """
        Тест проверяет, что при отправке через брокер
        команды на выключение выхода, происходит выключение выхода
        """

        self.hlt.isRunning = True

        # Запускаем потоки опроса и отправки команд
        threading.Thread(target=self.hlt.reader_target).start()
        threading.Thread(target=self.hlt.writer_target).start()

        time.sleep(1)

        for unit_addr in self.settings['power units']:

            tries = 3

            rst_cmd = 'rst {}'.format(unit_addr)

            # Сбрасываем состояние модуля (не всегда работает с первого раза)
            while tries:
                send_time = time.time()
                self.hlt.unit_addrs_to_transceivers_map[unit_addr].write(rst_cmd)

                while True:
                    try:
                        self.assertEqual(self.hlt.power_units_state_dicts[unit_addr]['st']['state1'], '0')
                        self.assertEqual(self.hlt.power_units_state_dicts[unit_addr]['st']['state2'], '0')
                        tries = 1
                        break
                    except AssertionError:
                        if time.time() - send_time > 3:
                            if not tries - 1:
                                self.hlt.isRunning = False
                                raise
                            else:
                                break
                        else:
                            time.sleep(0.1)
                tries -= 1

            # Инициализируем силовой модуль
            self.assertTrue(self.hlt.init_power_unit(unit_addr),
                            msg='Силовой модуль {} не удается инициализировать'.format(unit_addr))

            # Записываем в последовательный порт команды включения первого и второго выходов
            self.hlt.unit_addrs_to_transceivers_map[unit_addr].write('ch 1 on {}'.format(unit_addr))
            self.hlt.unit_addrs_to_transceivers_map[unit_addr].write('ch 2 on {}'.format(unit_addr))

            # Проверяем, что хотя бы один из каналов включился
            check_state_time = time.time()
            while True:
                try:
                    self.assertTrue(self.hlt.power_units_state_dicts[unit_addr]['st']['state1'] == '5' or
                                    self.hlt.power_units_state_dicts[unit_addr]['st']['state2'] == '5')
                    break
                except AssertionError:
                    if time.time() - check_state_time < 2:
                        time.sleep(0.1)
                        continue
                    else:
                        self.hlt.isRunning = False
                        raise

            # Результаты выполенения команд включения каналов
            result1 = self.hlt.power_units_state_dicts[unit_addr]['st']['state1'] == '5'
            result2 = self.hlt.power_units_state_dicts[unit_addr]['st']['state2'] == '5'

            if result1:
                cmd = str({'addr': 'ch:{}:1'.format(unit_addr), 'state': {'status': '4'}})
                self.r.publish(channel='axiomLogic:cmd:state', message=cmd)
            else:
                print('Первый канал модуля {} не был включен, проверка выключения не проводится'.format(unit_addr))

            if result2:
                cmd = str({'addr': 'ch:{}:2'.format(unit_addr), 'state': {'status': '4'}})
                self.r.publish(channel='axiomLogic:cmd:state', message=cmd)
            else:
                print('Второй канал модуля {} не был включен, проверка выключения не проводится'.format(unit_addr))

            # Проверяем, что команды выключения выполнились
            check_state_time = time.time()
            while True:
                try:
                    if result1:
                        self.assertEqual(self.hlt.power_units_state_dicts[unit_addr]['st']['state1'], '4',
                                         msg='Первый канал модуля {} не выключился'.format(unit_addr))
                    if result2:
                        self.assertEqual(self.hlt.power_units_state_dicts[unit_addr]['st']['state2'], '4',
                                         msg='Второй канал модуля {} не выключился'.format(unit_addr))
                    break
                except AssertionError:
                    if time.time() - check_state_time < 2:
                        time.sleep(0.1)
                        continue
                    else:
                        self.hlt.isRunning = False
                        raise


            # Останавливаем потоки опроса и отправки команд
            self.hlt.isRunning = False

    def test_can_turn_off_outputs_if_not_initialized(self):
        """
        Тест проверяет, что при отправке через брокер
        команды на выключение выхода, и при этом модуль
        не инициализирован, в результате работы фукнции
        set_ch_state модуль инициализируется, а выход,
        который нужно было выключить остается выключенным
        """

        self.hlt.isRunning = True

        # Запускаем потоки опроса и отправки команд
        threading.Thread(target=self.hlt.reader_target).start()
        threading.Thread(target=self.hlt.writer_target).start()

        time.sleep(1)

        for unit_addr in self.settings['power units']:

            tries = 3

            rst_cmd = 'rst {}'.format(unit_addr)

            # Сбрасываем состояние модуля (не всегда работает с первого раза)
            while tries:
                send_time = time.time()
                self.hlt.unit_addrs_to_transceivers_map[unit_addr].write(rst_cmd)

                while True:
                    try:
                        self.assertEqual(self.hlt.power_units_state_dicts[unit_addr]['st']['state1'], '0')
                        self.assertEqual(self.hlt.power_units_state_dicts[unit_addr]['st']['state2'], '0')
                        tries = 1
                        break
                    except AssertionError:
                        if time.time() - send_time > 3:
                            if not tries - 1:
                                self.hlt.isRunning = False
                                raise
                            else:
                                break
                        else:
                            time.sleep(0.1)
                tries -= 1

            # Отправляем команды выключения
            cmd = str({'addr': 'ch:{}:1'.format(unit_addr), 'state': {'status': '4'}})
            self.r.publish(channel='axiomLogic:cmd:state', message=cmd)

            cmd = str({'addr': 'ch:{}:2'.format(unit_addr), 'state': {'status': '4'}})
            self.r.publish(channel='axiomLogic:cmd:state', message=cmd)

            # Проверяем, что команды выключения выполнились
            check_state_time = time.time()
            while True:
                try:
                    self.assertEqual(self.hlt.power_units_state_dicts[unit_addr]['st']['state1'], '4',
                                     msg='Первый канал модуля {} не перешел в состояние "Выключен"'.format(unit_addr))

                    self.assertEqual(self.hlt.power_units_state_dicts[unit_addr]['st']['state2'], '4',
                                     msg='Второй канал модуля {} не перешел в состояние "Выключен"'.format(unit_addr))
                    break
                except AssertionError:
                    if time.time() - check_state_time < 3:
                        time.sleep(0.1)
                        continue
                    else:
                        self.hlt.isRunning = False
                        raise

            # Останавливаем потоки опроса и отправки команд
            self.hlt.isRunning = False

    def test_turn_on_off_stress_test(self):
        """
        Тест собирает статистику успешного/неудачного
        выполнения команд включения/выключения выходов
        """

        self.hlt.isRunning = True

        success = 0
        failure = 0

        # Запускаем потоки опроса и отправки команд
        threading.Thread(target=self.hlt.reader_target).start()
        threading.Thread(target=self.hlt.writer_target).start()

        time.sleep(1)

        for unit_addr in self.settings['power units']:

            tries = 3

            rst_cmd = 'rst {}'.format(unit_addr)
            print(rst_cmd)
            # Сбрасываем состояние модуля (не всегда работает с первого раза)
            while tries:
                send_time = time.time()
                self.hlt.unit_addrs_to_transceivers_map[unit_addr].write(rst_cmd)

                while True:
                    try:
                        self.assertEqual(self.hlt.power_units_state_dicts[unit_addr]['st']['state1'], '0')
                        self.assertEqual(self.hlt.power_units_state_dicts[unit_addr]['st']['state2'], '0')
                        tries = 1
                        break
                    except AssertionError:
                        if time.time() - send_time > 3:
                            if not tries - 1:
                                self.hlt.isRunning = False
                                raise
                            else:
                                break
                        else:
                            time.sleep(0.1)
                tries -= 1

            # Инициализируем силовой модуль
            self.hlt.init_power_unit(unit_addr)

            # Проверяем, что один из выходов не находится в состоянии 0 или 3
            check_state_time = time.time()
            while True:
                try:
                    self.assertTrue(self.hlt.power_units_state_dicts[unit_addr]['st']['state1'] != '0' and
                                    self.hlt.power_units_state_dicts[unit_addr]['st']['state2'] != '0')

                    self.assertTrue(self.hlt.power_units_state_dicts[unit_addr]['st']['state1'] != '3' and
                                    self.hlt.power_units_state_dicts[unit_addr]['st']['state2'] != '3')
                    break
                except AssertionError:
                    if time.time() - check_state_time < 5:
                        time.sleep(0.1)
                        continue
                    else:
                        self.hlt.isRunning = False
                        raise

        for unit_addr in self.settings['power units']:
            for i in range(25):
                print(i)
                # Первый канал
                if self.hlt.power_units_state_dicts[unit_addr]['st']['state1'] == '4':
                    # self.hlt.event.clear()
                    if self.hlt.set_ch_state(channel_addr='ch:{}:1'.format(unit_addr),
                                             new_state_dict={'status': '5'}):
                        success += 1
                    else:
                        failure += 1
                    # self.hlt.event.set()

                if self.hlt.power_units_state_dicts[unit_addr]['st']['state1'] == '5':
                    # self.hlt.event.clear()
                    if self.hlt.set_ch_state(channel_addr='ch:{}:1'.format(unit_addr),
                                             new_state_dict={'status': '4'}):
                        success += 1
                    else:
                        failure += 1
                    # self.hlt.event.set()

                # Второй канал
                if self.hlt.power_units_state_dicts[unit_addr]['st']['state2'] == '4':
                    send_time = time.time()
                    self.r.publish("axiomLogic:cmd:state", json.dumps({'addr': 'ch:m2:2', 'state': {'status': '5'}}))
                    while True:
                        try:
                            self.assertEqual(self.hlt.power_units_state_dicts[unit_addr]['st']['state2'], '5')
                            success += 1
                            break
                        except AssertionError:
                            if time.time() - send_time < 2:
                                time.sleep(0.01)
                                continue
                            else:
                                failure += 1
                                break

                if self.hlt.power_units_state_dicts[unit_addr]['st']['state2'] == '5':
                    send_time = time.time()
                    self.r.publish("axiomLogic:cmd:state", json.dumps({'addr': 'ch:m2:2', 'state': {'status': '4'}}))
                    while True:
                        try:
                            self.assertEqual(self.hlt.power_units_state_dicts[unit_addr]['st']['state2'], '4')
                            success += 1
                            break
                        except AssertionError:
                            if time.time() - send_time < 2:
                                time.sleep(0.01)
                                continue
                            else:
                                failure += 1
                                break

        self.hlt.isRunning = False

        print('команд выполнено: ', success)
        print('команд не выполнено: ', failure)

    def test_version_cmd(self):
        """
        Тест собирает статистику успешного/неудачного
        выполнения команд включения/выключения выходов
        """

        self.hlt.isRunning = True

        success = 0
        failure = 0

        # Запускаем потоки опроса и отправки команд
        threading.Thread(target=self.hlt.reader_target).start()
        threading.Thread(target=self.hlt.writer_target).start()

        time.sleep(1)


        for unit_addr in self.settings['power units']:
            for i in range(25):
                print(i)
                self.hlt.unit_addrs_to_transceivers_map[unit_addr].write('version m2')
                time.sleep(0.5)

        self.hlt.isRunning = False

        print('команд выполнено: ', success)
        print('команд не выполнено: ', failure)

class TestRun(TestHighLowTransceiver):
    """
    Тесты, проверяющие функцию HighLowTransceiver.run
    """
    def test_run_starts_state_updating(self):
        """
        Тест проверяет, что после запуска начинает
        собираться текущее состояние силовых модулей
        """
        threading.Thread(target=self.hlt.run).start()

        time.sleep(1)

        state1 = copy.deepcopy(self.hlt.power_units_state_dicts)

        time.sleep(1)

        state2 = copy.deepcopy(self.hlt.power_units_state_dicts)

        try:
            self.assertTrue(state1 != state2)
        except AssertionError:
            raise
        finally:
            self.hlt.isRunning = False

    def test_run_initializes_power_units(self):
        """
        Тест проверяет, что после запуска
        инициализируются все силовые модули
        """

        # Сбрасываем состояние модуля (не всегда работает с первого раза)
        for unit_addr in self.settings['power units']:

            self.hlt.power_units_state_dicts[unit_addr]['st']['state1'] = None
            self.hlt.power_units_state_dicts[unit_addr]['st']['state2'] = None

            tries = 3
            rst_cmd = 'rst {}'.format(unit_addr)

            while tries:
                send_time = time.time()
                self.hlt.unit_addrs_to_transceivers_map[unit_addr].write(rst_cmd)
                while True:
                    self.hlt.collect_units_state()
                    try:
                        self.assertEqual(self.hlt.power_units_state_dicts[unit_addr]['st']['state1'], '0')
                        self.assertEqual(self.hlt.power_units_state_dicts[unit_addr]['st']['state2'], '0')
                        tries = 1
                        break
                    except AssertionError:
                        if time.time() - send_time > 3:
                            if not tries - 1:
                                self.hlt.isRunning = False
                                raise
                            else:
                                break
                        else:
                            time.sleep(0.01)
                tries -= 1

        # Запуск трансивера
        threading.Thread(target=self.hlt.run).start()

        # Расчитывает задержку, которая нужна на инициализацию всхе модулей
        delay = 5 * len(self.settings['power units']) + 1

        error = None
        check_time = time.time()
        while time.time() - check_time < delay:
            try:
                for unit_addr in self.settings['power units']:
                    ch1_state = self.hlt.power_units_state_dicts[unit_addr]['st']['state1']
                    ch2_state = self.hlt.power_units_state_dicts[unit_addr]['st']['state2']

                    self.assertTrue(ch1_state not in ('0', '1', '3'),
                                    msg='Первый канал модуля {} не был проинициализирован, текущее состояние: {}'.format(
                                        unit_addr, ch1_state))
                    self.assertTrue(ch2_state not in ('0', '1', '3'),
                                    msg='Второй канал модуля {} не был проинициализирован, текущее состояние: {}'.format(
                                        unit_addr, ch2_state)
                                    )
            except AssertionError as e:
                error = e
                time.sleep(0.1)
                continue
            self.hlt.isRunning = False
            return

        self.hlt.isRunning = False
        raise error

    # Включает все выходы! Запускать только на макете!
    # (или если ты знаешь, что делаешь)
    # @skip
    def test_run_start_handling_set_ch_state_commands(self):
        """
        Тест проверяет, что после запуска
        начинается отработка команд на
        изменения состояния выходов модуля
        """

        # Сбрасываем состояние модуля (не всегда работает с первого раза)
        for unit_addr in self.settings['power units']:

            # Заодно установим состояние "Выключено" для выходов этого модуля
            self.hlt.redis.set(name='ch:{}:1'.format(unit_addr), value={'status': '4'})
            self.hlt.redis.set(name='ch:{}:2'.format(unit_addr), value={'status': '4'})

            self.hlt.power_units_state_dicts[unit_addr]['st']['state1'] = None
            self.hlt.power_units_state_dicts[unit_addr]['st']['state2'] = None

            tries = 3
            rst_cmd = 'rst {}'.format(unit_addr)

            while tries:
                send_time = time.time()
                self.hlt.unit_addrs_to_transceivers_map[unit_addr].write(rst_cmd)
                while True:
                    self.hlt.collect_units_state()
                    try:
                        self.assertEqual(self.hlt.power_units_state_dicts[unit_addr]['st']['state1'], '0')
                        self.assertEqual(self.hlt.power_units_state_dicts[unit_addr]['st']['state2'], '0')
                        tries = 1
                        break
                    except AssertionError:
                        if time.time() - send_time > 3:
                            if not tries - 1:
                                self.hlt.isRunning = False
                                raise
                            else:
                                break
                        else:
                            time.sleep(0.01)
                tries -= 1

        # Запуск трансивера
        threading.Thread(target=self.hlt.run).start()

        # Расчитывает задержку, которая нужна на инициализацию всхе модулей
        delay = 5 * len(self.settings['power units']) + 3

        # Ждем, когда модули проинициализируются
        check_time = time.time()
        while time.time() - check_time < delay:
            try:
                for unit_addr in self.settings['power units']:
                    ch1_state = self.hlt.power_units_state_dicts[unit_addr]['st']['state1']
                    ch2_state = self.hlt.power_units_state_dicts[unit_addr]['st']['state2']

                    self.assertTrue(ch1_state not in ('0', '1', '3') and
                                    ch2_state not in ('0', '1', '3'))
            except AssertionError:
                time.sleep(0.1)
                continue
            break

        for unit_addr in self.settings['power units']:
            # Проверяем отработку команд включения
            ch1_state = self.hlt.power_units_state_dicts[unit_addr]['st']['state1']
            if ch1_state != '4':
                print('Первый канал модуля "{}" находится в состоянии "{}".'
                      ' Проверка отработки команды включения проводиться не будет!'.format(
                    unit_addr, self.hlt.humanreadable_states[ch1_state]))
            else:
                cmd = str({'addr': 'ch:{}:1'.format(unit_addr), 'state': {'status': '5'}})
                self.r.publish(channel='axiomLogic:cmd:state', message=cmd)

            ch2_state = self.hlt.power_units_state_dicts[unit_addr]['st']['state2']
            if ch2_state != '4':
                print('Второй канал модуля "{}" находится в состоянии "{}".'
                      ' Проверка отработки команды включения проводиться не будет!'.format(
                    unit_addr, self.hlt.humanreadable_states[ch2_state]))
            else:
                cmd = str({'addr': 'ch:{}:2'.format(unit_addr), 'state': {'status': '5'}})
                self.r.publish(channel='axiomLogic:cmd:state', message=cmd)

            # Проверяем, что команды включения выполены
            check_state_time = time.time()
            while True:
                try:
                    if ch1_state == '4':
                        self.assertEqual(self.hlt.power_units_state_dicts[unit_addr]['st']['state1'], '5',
                                         msg='Первый канал модуля "{}" не включился'.format(unit_addr))
                    if ch2_state == '4':
                        self.assertEqual(self.hlt.power_units_state_dicts[unit_addr]['st']['state2'], '5',
                                         msg='Второй канал модуля "{}" не включился'.format(unit_addr))
                    break
                except AssertionError:
                    if time.time() - check_state_time < 2:
                        time.sleep(0.1)
                        continue
                    else:
                        self.hlt.isRunning = False
                        raise

            # Проверяем отработку команд выключения
            ch1_state = self.hlt.power_units_state_dicts[unit_addr]['st']['state1']
            if ch1_state != '5':
                print('Первый канал модуля "{}" находится в состоянии "{}".'
                      ' Проверка отработки команды выключения проводиться не будет!'.format(
                    unit_addr, self.hlt.humanreadable_states[ch1_state]))
            else:
                cmd = str({'addr': 'ch:{}:1'.format(unit_addr), 'state': {'status': '4'}})
                self.r.publish(channel='axiomLogic:cmd:state', message=cmd)

            ch2_state = self.hlt.power_units_state_dicts[unit_addr]['st']['state2']
            if ch2_state != '5':
                print('Второй канал модуля "{}" находится в состоянии "{}".'
                      ' Проверка отработки команды выключения проводиться не будет!'.format(
                    unit_addr, self.hlt.humanreadable_states[ch2_state]))
            else:
                cmd = str({'addr': 'ch:{}:2'.format(unit_addr), 'state': {'status': '4'}})
                self.r.publish(channel='axiomLogic:cmd:state', message=cmd)

            # Проверяем, что команды выключения выполены
            check_state_time = time.time()
            while True:
                try:
                    if ch1_state == '5':
                        self.assertEqual(self.hlt.power_units_state_dicts[unit_addr]['st']['state1'], '4',
                                         msg='Первый канал модуля "{}" не выключился'.format(unit_addr))
                    if ch2_state == '5':
                        self.assertEqual(self.hlt.power_units_state_dicts[unit_addr]['st']['state2'], '4',
                                         msg='Второй канал модуля "{}" не выключился'.format(unit_addr))
                    break
                except AssertionError:
                    if time.time() - check_state_time < 2:
                        time.sleep(0.1)
                        continue
                    else:
                        self.hlt.isRunning = False
                        raise



        # Останавливаем потоки опроса и отправки команд
        self.hlt.isRunning = False

    # Включает все выходы! Запускать только на макете!
    # (или если ты знаешь, что делаешь)
    # @skip
    def test_run_restores_saved_state(self):
        """
        Тест проверяет, что после запуска
        восстанавливается сохраненное состояние
        выходов силового модуля
        """

        # Сбрасываем состояние модуля (не всегда работает с первого раза)
        for unit_addr in self.settings['power units']:

            # Заодно установим состояние "Включено" для выходов этого модуля
            self.hlt.redis.set(name='ch:{}:1'.format(unit_addr), value=str({'status': '5'}))
            self.hlt.redis.set(name='ch:{}:2'.format(unit_addr), value=str({'status': '5'}))

            self.hlt.power_units_state_dicts[unit_addr]['st']['state1'] = None
            self.hlt.power_units_state_dicts[unit_addr]['st']['state2'] = None

            tries = 3
            rst_cmd = 'rst {}'.format(unit_addr)

            while tries:
                send_time = time.time()
                self.hlt.unit_addrs_to_transceivers_map[unit_addr].write(rst_cmd)
                while True:
                    self.hlt.collect_units_state()
                    try:
                        self.assertEqual(self.hlt.power_units_state_dicts[unit_addr]['st']['state1'], '0')
                        self.assertEqual(self.hlt.power_units_state_dicts[unit_addr]['st']['state2'], '0')
                        tries = 1
                        break
                    except AssertionError:
                        if time.time() - send_time > 3:
                            if not tries - 1:
                                self.hlt.isRunning = False
                                raise
                            else:
                                break
                        else:
                            time.sleep(0.01)
                tries -= 1

        # Запуск трансивера
        threading.Thread(target=self.hlt.run).start()

        # Расчитывает задержку, которая нужна на инициализацию всхе модулей
        delay = 5 * len(self.settings['power units']) + 3

        # Ждем, когда модули проинициализируются
        check_time = time.time()
        while time.time() - check_time < delay:
            try:
                for unit_addr in self.settings['power units']:
                    ch1_state = self.hlt.power_units_state_dicts[unit_addr]['st']['state1']
                    ch2_state = self.hlt.power_units_state_dicts[unit_addr]['st']['state2']

                    self.assertTrue(ch1_state not in ('0', '1', '3') and
                                    ch2_state not in ('0', '1', '3'))
            except AssertionError:
                time.sleep(0.1)
                continue
            break

        # Проверяем, что исправные выходы включились
        for unit_addr in self.settings['power units']:

            # Текущее состояние выхода
            ch1_state = self.hlt.power_units_state_dicts[unit_addr]['st']['state1']
            ch2_state = self.hlt.power_units_state_dicts[unit_addr]['st']['state2']

            # Проверяем, что команды включения выполены
            check_state_time = time.time()
            while True:
                try:
                    if ch1_state not in ('2', '6', '7'):
                        self.assertEqual(self.hlt.power_units_state_dicts[unit_addr]['st']['state1'], '5',
                                         msg='Первый канал модуля "{}" не включился'.format(unit_addr))
                    if ch2_state not in ('2', '6', '7'):
                        self.assertEqual(self.hlt.power_units_state_dicts[unit_addr]['st']['state2'], '5',
                                         msg='Второй канал модуля "{}" не включился'.format(unit_addr))
                    break
                except AssertionError:
                    if time.time() - check_state_time < 2:
                        time.sleep(0.1)
                        continue
                    else:
                        self.hlt.isRunning = False
                        raise

        # Останавливаем потоки опроса и отправки команд
        self.hlt.isRunning = False

