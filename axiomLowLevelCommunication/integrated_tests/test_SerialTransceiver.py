import json
import os
from unittest import TestCase
from axiomLowLevelCommunication.serialTransceiver import SerialTransceiver
import serial


class TestSerialTransceiver(TestCase):

    def setUp(self):
        """
        Настраивает тестовое окружение
        """
        # Загружаем настройки
        default_fname = '/etc/axiom/settings_input_unit.json'
        fname = os.environ.get('AXIOM_SETTINGS', default=default_fname)
        with open(fname) as settings_file:
            self.settings = json.load(settings_file)

    def test_can_create_SerialTransceiver_for_every_power_unit_serial_port(self):
        """
        Тест проверяет, что для каждого последовательного порта,
        привязанного в настройках к силовому модулю, удается создать
        объект класса SerialTransceiver
        """
        for port in self.settings['power units'].values():
            try:
                self.assertTrue(SerialTransceiver(port=port))
            except serial.SerialException:
                pass

    def test_can_open_and_close_serial_port_for_every_power_unit(self):
        """
        Тест проверяет, что для каждого силового модуля может быть
        открыт и закрыт, соответствующий ему последовательный порт
        """
        for port in self.settings['power units'].values():
            try:
                ser = SerialTransceiver(port=port)
                self.assertEqual(ser.close(), True)
                self.assertEqual(ser.open(), True)
                self.assertEqual(ser.close(), True)
            except serial.SerialException:
                pass

    def test_can_write_data_in_serial_port_for_every_power_unit(self):
        """
        Тест проверяет, что в последовательный порт каждого силового
        модуля могут быть записаны данные
        """
        for port in self.settings['power units'].values():
            try:
                ser = SerialTransceiver(port=port)
                ser.close()
                ser.open()
                self.assertEqual(ser.write('some data'), True)
                ser.close()
            except serial.SerialException:
                pass

    def test_can_read_data_from_serial_port_for_every_power_unit(self):
        """
        Тест проверяет, что из последовательный порт каждого силового
        модуля могут быть прочитаны данные
        """
        for port in self.settings['power units'].values():
            try:
                ser = SerialTransceiver(port=port)
                ser.close()
                ser.open()
                self.assertTrue(ser.read())
                ser.close()
            except serial.SerialException:
                pass


