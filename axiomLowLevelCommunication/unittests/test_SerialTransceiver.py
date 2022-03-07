import threading
import time
from unittest import TestCase, skip
from unittest.mock import MagicMock, patch
from axiomLowLevelCommunication.serialTransceiver import SerialTransceiver, logger
import serial


class TestSerialTransceiver(TestCase):

    def setUp(self):

        from axiomLowLevelCommunication.serialTransceiver import logger
        logger.write_log = MagicMock()
        self.logger = logger

        from axiomLowLevelCommunication.serialTransceiver import SerialTransceiver
        self.SerialTransceiver = SerialTransceiver

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_serialTransceiver_connects_to_serial_port_with_correct_arguments(self):
        """
        Тест проверяет, что подключение к последовательному порту
        производится с верными настройками
        """
        SerialTransceiver(port='/dev/ttyS0')
        serial.Serial.assert_called_once_with(port='/dev/ttyS0', baudrate=115200, stopbits=1,
                                              bytesize=8, parity='N', timeout=0.1, xonxoff=False, rtscts=False,
                                              writeTimeout=0, dsrdtr=False, interCharTimeout=None)

    @patch('axiomLowLevelCommunication.serialTransceiver.logger', MagicMock(spec=logger))
    @patch('serial.Serial', MagicMock(spec=serial.Serial, side_effect=serial.SerialException))
    def test_writes_error_to_log_if_connection_fails(self):
        """
        Тест проверяет, что в лог записывается сообщение об ошибке в случае
        возникновения исключения serial.SerialException при попытке
        подключения к последовательному порту
        """
        from axiomLowLevelCommunication.serialTransceiver import logger
        SerialTransceiver(port='/dev/ttyS0')

        logger.write_log.assert_called_once_with('Ошибка при подключении к последовательному порту', 'ERROR')

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_serialTransceiver_open_returns_True_on_success(self):
        """
        Тест проверят, что в случае успешного открытия последовательного порта
        функция SerialTransceiver.open возвращает True
        """
        self.assertTrue(SerialTransceiver(port='/dev/ttyS0').open())

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_serialTransceiver_open_returns_False_on_failure(self):
        """
        Тест проверят, что в случае неудачного открытия последовательного порта
        функция SerialTransceiver.open возвращает False
        """
        trasceiver = SerialTransceiver(port='/dev/ttyS0')
        trasceiver.ser.open.side_effect = serial.SerialException
        self.assertFalse(trasceiver.open())

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_writes_error_to_log_if_open_fails(self):
        """
        Тест проверяет, что в лог записывается сообщение об ошибке в случае
        возникновения исключения serial.SerialException при попытке
        подключения к последовательному порту
        """
        transceiver = SerialTransceiver(port='/dev/ttyS0')
        transceiver.ser.open.side_effect = serial.SerialException('some error')
        transceiver.open()
        self.logger.write_log.assert_called_once_with('Ошибка при открытии последовательного порта: {}'.format(
            'some error'), 'ERROR')

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_calls_serial_close_to_close(self):
        """
        Тест проверяет, что вызывается функция serial.Serial.close
        при закрытии подключения к последовательному порту
        """
        trasceiver = SerialTransceiver(port='/dev/ttyS0')
        trasceiver.close()
        trasceiver.ser.close.assert_called()

    # <editor-fold desc="DEPRECATED TEST">
    # @patch('serial.Serial', MagicMock(spec=serial.Serial))
    # def test_write_calls_serial_write_with_each_symbol(self):
    #     """
    #     Тест проверяет, что функция SerialTransceiver.write
    #     вызывает функцию serial.Serial.write отдельно для
    #     каждого символа переданной строки и завершает посылку
    #     символом новой строки
    #     """
    #     transceiver = SerialTransceiver(port='/dev/ttyS0')
    #     write_calls = []
    #     transceiver.ser.write.side_effect = lambda symbol: write_calls.append(symbol)
    #     transceiver.write('test string')
    #     self.assertEqual(write_calls, [symbol.encode() for symbol in 'test string\n'])
    # </editor-fold>

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_write_calls_serial_write(self):
        """
        Тест проверяет, что функция SerialTransceiver.write
        вызывает функцию serial.Serial.write для записи в
        последователный порт и добавляет терминальные символы
        """
        transceiver = SerialTransceiver(port='/dev/ttyS0')
        transceiver.write('test string')
        transceiver.ser.write.assert_called_once_with(b'test string\r\n')

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_write_returns_True_on_success(self):
        """
        Тест проверяет, что функция SerialTransceiver.write
        возвращает True, если все символы переданной строки
        были успешно записаны в последовательный порт
        """
        transceiver = SerialTransceiver(port='/dev/ttyS0')
        self.assertEqual(transceiver.write('test string'), True)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_write_function_log_error_on_failure(self):
        """
        Тест проверяет, что функция SerialTransceiver.write логирует ошибку
         в случае возникновения исключения serial.SerialException
        """
        transceiver = SerialTransceiver(port='/dev/ttyS0')
        transceiver.ser.write.side_effect = serial.SerialException('some error')
        transceiver.write('test string')
        log_msg = 'Ошибка при записи команды {} в последовательный порт: {}'.format('test string', 'some error')
        self.logger.write_log.assert_called_with(log_msg=log_msg, log_level='ERROR')

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_write_function_returns_False_on_failure(self):
        """
        Тест проверяет, что функция SerialTransceiver.write возвращает False
         в случае возникновения исключения serial.SerialException
        """
        transceiver = SerialTransceiver(port='/dev/ttyS0')
        transceiver.ser.write.side_effect = serial.SerialException('some error')
        self.assertEqual(transceiver.write('test string'), False)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_write_function_set_lock(self):
        """
        Тест проверяет, что функция SerialTransceiver.write
        устанавливает блокировку на время записи в последовательный порт
        """
        transceiver = SerialTransceiver(port='/dev/ttyS0')
        transceiver.ser_lock = MagicMock(spec=transceiver.ser_lock)
        transceiver.write('test string')
        transceiver.ser_lock.acquire.assert_called_once()
        transceiver.ser_lock.release.assert_called_once()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_write_function_set_write_event(self):
        """
        Тест проверяет, что функция SerialTransceiver.write
        устанавливает блокировку чтения на время записи
        """
        transceiver = SerialTransceiver(port='/dev/ttyS0')
        transceiver.write_event = MagicMock(spec=transceiver.write_event)
        transceiver.write('test string')
        transceiver.write_event.clear.assert_called_once()
        transceiver.write_event.set.assert_called_once()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_write_function_can_not_write_data_if_write_lock_is_already_acquired(self):
        """
        Тест проверяет, что функция SerialTransceiver.write
        ничего не записывает в последовательный порт, если он заблокирован
        """
        transceiver = SerialTransceiver(port='/dev/ttyS0')
        transceiver.ser_lock.acquire()
        transceiver.write('test string')
        transceiver.ser.write.assert_not_called()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_write_function_wait_for_lock_to_be_released_and_write_data(self):
        """
        Тест проверяет, что функция SerialTransceiver.write
        записывает данные в последовательный порт, после того
        как он разблокируется, если время ожидания не превышает
        заданный порог (3 секунды)
        """
        transceiver = SerialTransceiver(port='/dev/ttyS0')
        transceiver.ser_lock.acquire()
        threading.Thread(target=transceiver.write, args=('test string',)).start()
        transceiver.ser.write.assert_not_called()
        time.sleep(0.5)
        transceiver.ser_lock.release()
        time.sleep(0.5)
        transceiver.ser.write.assert_called()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_write_function_log_error_if_lock_is_not_released_before_timeout(self):
        """
        Тест проверяет, что функция SerialTransceiver.write
        записывает ошибку в лог, если блокировка записи в
        последовательный порт не снята до истечения таймаута
        """
        transceiver = SerialTransceiver(port='/dev/ttyS0')
        transceiver.ser_lock.acquire()
        transceiver.write('test string')
        log_msg = 'Невозможно записать команду "{}" в последовательный порт {}.' \
                  ' Запись заблокирована другим потоком'.format('test string', transceiver.port)
        self.logger.write_log.assert_called_with(log_msg=log_msg, log_level='ERROR')

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_write_function_returns_False_if_lock_is_not_released_before_timeout(self):
        """
        Тест проверяет, что функция SerialTransceiver.write
        возвращает False, если блокировка записи в
        последовательный порт не снята до истечения таймаута
        """
        transceiver = SerialTransceiver(port='/dev/ttyS0')
        transceiver.ser_lock.acquire()
        self.assertEqual(transceiver.write('test string'), False)

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_read_return_data_on_success(self):
        """
        Тест проверяет, что в случае успешного чтения данных,
        функция SerialTransceiver.read возвращает прочитанные данные
        """
        transceiver = SerialTransceiver(port='/dev/ttyS0')
        transceiver.ser.read_until.return_value = b'some data'
        self.assertEqual(transceiver.read(), b'some data')

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_read_return_False_on_failure(self):
        """
        Тест проверяет, что в случае возникновения исключения при чтении данных,
        функция SerialTransceiver.read возвращает False
        """
        transceiver = SerialTransceiver(port='/dev/ttyS0')
        transceiver.ser.read_until.side_effect = serial.SerialException
        self.assertFalse(transceiver.read())

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_read_function_log_error_on_failure(self):
        """
        Тест проверяет, что функция SerialTransceiver.read логирует ошибку
         в случае возникновения исключения serial.SerialException
        """
        transceiver = SerialTransceiver(port='/dev/ttyS0')
        transceiver.ser.read_until.side_effect = serial.SerialException
        transceiver.read()
        self.assertTrue('Ошибка при чтении из последовательного порта:' in self.logger.write_log.call_args[0][0])

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_read_function_dont_read_if_write_event_isnt_set(self):
        """
        Тест проверяет, что функция SerialTransceiver.read не читает данные
        из последовательного порта, если чтение заблоркировано в
        потоке записи в этот последовательный порт
        """
        transceiver = SerialTransceiver(port='/dev/ttyS0')
        transceiver.write_event.clear()
        transceiver.read()
        transceiver.ser.read.assert_not_called()

    @patch('serial.Serial', MagicMock(spec=serial.Serial))
    def test_read_function_read_after_write_event_has_been_set(self):
        """
        Тест проверяет, что функция SerialTransceiver.read читает данные
        после того, как блокировка чтения снимается
        """
        transceiver = SerialTransceiver(port='/dev/ttyS0')
        transceiver.write_event.clear()
        threading.Thread(target=transceiver.read).start()
        time.sleep(0.5)
        transceiver.ser.read.assert_not_called()
        transceiver.write_event.set()
        time.sleep(0.5)
        transceiver.ser.read_until.assert_called_once()
