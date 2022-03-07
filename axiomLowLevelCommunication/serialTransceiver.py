import threading
import serial
from time import sleep
from axiomLib.loggers import create_logger
from axiomLowLevelCommunication.config import LOG_FILE_DIRECTORY, LOG_FILE_NAME


class SerialTransceiver:
	"""
	Класс предоставляет API для работы с последовательным портом.
	Основан на библиотеке pySerial
	"""
	def __init__(self, port):
		"""
		Инициализирует экземпляр класса

		:type port: str
		:param port: имя файла последовательного порта в ОС

		:ivar port: имя файла COM порта в ОС
		:ivar ser_lock: блокировка записи/чтения из последовательного порта
		:ivar write_event: блокировка чтения из последовательного порта
		:ivar ser: объект подключения к последовательному порту
		"""
		self.logger = create_logger(logger_name=__name__,
									logfile_directory=LOG_FILE_DIRECTORY,
									logfile_name=LOG_FILE_NAME)
		self.port = port
		self.ser_lock = threading.Lock()
		self.write_event = threading.Event()
		self.write_event.set()

		try:
			self.ser = serial.Serial(port=port, baudrate=115200, stopbits=1,
									 bytesize=8, parity='N', timeout=0.1,
									 xonxoff=False, rtscts=False, writeTimeout=0,
									 dsrdtr=False, interCharTimeout=None)
		except serial.SerialException as e:
			self.logger.error('Ошибка при подключении к последовательному порту: {}'.format(e))

	def open(self):
		"""
		Открывает последовательный порт

		:rtype: bool
		:return: True в случае успеха, False - в случае ошибки
		"""
		try:
			self.ser.open()
			return True
		except serial.SerialException as e:
			self.logger.error('Ошибка при открытии последовательного порта: {}'.format(e))
			return False

	def close(self):
		"""
		Безопасно закрывает поключение к последовательному порту

		:rtype: bool
		:return: True в случае успеха, False - в случае ошибки
		"""
		try:
			self.ser.close()
			# TODO написать тест
			return True
		except Exception as e:
			# TODO написать тест
			self.logger.error('Ошибка при закрытии последовательного порта: {}'.format(e))
			return False

	def write(self, data):
		"""
		Записывает данные в последовательный порт

		При записи последовательный порт блокируется (для других потоков) как на запись, так и на чтение

		:type data: str
		:param data: строка для записи
		:rtype: bool
		:return: True - нет ошибок при записи, False - возникли ошибки

		.. figure:: _static/write.png
			:scale: 40%
			:align: center
		"""
		self.write_event.clear()
		if self.ser_lock.acquire(timeout=3):
			self.write_event.set()
			try:
				self.ser.reset_output_buffer()
				self.ser.reset_input_buffer()
				for i in data:
					self.ser.write(str(i).encode())
					sleep(0.001)
					self.ser.reset_input_buffer()
					self.ser.reset_output_buffer()
				self.ser.write('\n'.encode())

			except serial.SerialException as e:
				log_msg = 'Ошибка при записи команды {} в последовательный порт: {}'.format(data, e)
				self.logger.error(log_msg)
				return False
			finally:
				self.ser_lock.release()
			return True
		# Если блокировка записи не снята до истечения таймаута
		else:
			self.write_event.set()
			log_msg = 'Невозможно записать команду "{}" в последовательный порт {}. ' \
					  'Запись заблокирована другим потоком'.format(data, self.port)
			self.logger.error(log_msg)
			return False

	def read(self):
		"""
		Читает данные из последовательного порта

		Блокирует чтение/запись из последовательного порта до появления терминальной последовательности \r\n

		:rtype: bytes
		:return: прочитанные данные

		.. figure:: _static/read.png
			:scale: 40%
			:align: center
		"""
		try:
			self.write_event.wait(timeout=3)  # Запись имеет приоритет, ждем, пока закончится запить
			if self.ser_lock.acquire(timeout=3):
				data = self.ser.read_until(terminator=b'\r\n', size=None)
				return data
		except serial.SerialException as e:
			self.logger.error('Ошибка при чтении из последовательного порта: {}'.format(e))
			return False
		finally:
			self.ser_lock.release()

	def read_generator(self):
		"""
		Читает данные из последовательного порта

		Работает аналогично функции :func:`read`, но в формате генератора

		:пример: ``for data in ser.read_generator(): pass``
		:rtype: bytes
		:return: прочитанные данные
		"""
		while threading.main_thread().isAlive():
			data = None
			try:
				self.write_event.wait(timeout=3)  # Запись имеет приоритет, ждем, пока закончится запить
				if self.ser_lock.acquire(timeout=3):
					data = self.ser.read_until(terminator=b'\r\n', size=None)
			except serial.SerialException as e:
				self.logger.error('Ошибка при чтении из последовательного порта: {}'.format(e))
			finally:
				self.ser_lock.release()
				if data:
					yield data
				sleep(0.01)
