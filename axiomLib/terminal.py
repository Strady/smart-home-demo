#!/usr/bin/env python
# -*- coding: utf-8 -*- 

import serial, time, struct
#import matplotlib.pyplot as plt
import numpy as np
#from Running_Average_lib import Running_Average
#import matplotlib
#matplotlib.use('pdf')
#import matplotlib.animation as animation
from collections import deque, namedtuple 

from threading import Thread, Event
#from RPi import GPIO



class RpiSerial():
	def __init__(self,port,baudrate,stopbits,parity,bytesizes):
		self.port="/dev/ttyS0"
		self.baudrate=int(baudrate)
		self.stopbits=int(stopbits)
		self.bytesizes=int(bytesizes)
		self.parity=parity

		try:
			self.ser=serial.Serial(port=self.port,baudrate=self.baudrate,stopbits=self.stopbits,\
				bytesize=self.bytesizes,parity=self.parity,timeout=0.8, xonxoff=False, rtscts=False,\
				writeTimeout=0.01, dsrdtr=False, interCharTimeout=None)
		except serial.SerialException:
			print "вставь COM-PORT"
			#return -1

		self.isRunning = True
		self.event = Event()
		self.event.set()

	def open(self):
		try:
			self.ser.open()
			
		except serial.SerialException:
			print "cant open port"
			return -1

	def write(self,data):

		try:
			self.ser.write(str(data))
		except serial.SerialException:
			print "cant write data"
			return -1

		return 0	
	def write_byte(self,data):
		self.ser.flushInput()
		for i in data:
			self.write(i)
			time.sleep(0.001) #0.2
			self.ser.flushInput()
		#self.write('\r')
		self.write('\n')
		#self.clearFIFO()		

	def read(self):
		try:
			#readdata = self.ser.readline()
			readdata = self.ser.read_until(terminator='\r\n',size=None)
			#self.clearFIFO()
		except serial.SerialException:
			#print "cant read data"
			return 0
		#if readdata==[]: print "error read data"
		
		return readdata

	def close(self):
		try: self.ser.close()
		except Exception: pass

	def clearFIFO(self):
		try:
			self.ser.flushInput()
			self.ser.flushOutput()
		except serial.SerialException: pass	


class Terminal(RpiSerial):
	def __init__(self,port,baudrate,stopbits,parity,bytesizes):
		RpiSerial.__init__(self,port,baudrate,stopbits,parity,bytesizes)

		#Описание структур
		st_struct = namedtuple("st_t", #структура состояний каналов
		"state1 \
		state2 \
		signal1 \
		signal2 \
		addr \
		cnt"\
		) 
		adc_struct = namedtuple("adc_t", "sample1 sample2 addr cnt")	# структура данных с датчиков тока
		ld_struct = namedtuple("ld_t", "load1 load2 angle1 angle2 addr cnt")	# структура даных о типе нагрузке на каналах 1 и 2
		main_struct = namedtuple("main_t", "link st adc ld") # общая структура полей данных

		#инициализация структур
		st = st_struct(0,0,0,0,'m1',0)
		adc = adc_struct(0,0,'m1',0)
		ld = ld_struct(0,0,0,0,'m1',0)
		self.struct = main_struct(False,st,adc,ld)

		#перевод главной структуры в упорядоченный словарь
		self.d = self.struct._asdict()


	def terminal(self):
		return raw_input("command: ")		

	def start(self):
		#self.th_read()
		self.t1 = Thread(target=self.th_read, args=())
		self.t2 = Thread(target=self.th_write, args=())
		self.t1.start()
		self.t2.start()
		self.t1.join()
		self.t2.join()



	def collect(self):
		self.read_str = self.read()
		if self.read_str:
		#	print self.read_str

			if 'rply' in self.read_str:
				print(self.read_str)

			if(len(self.read_str)!=0):
				self.d['link'] = True
				if self.read_str.split()[0] in self.d.keys()[1:]:  #проверяем наличие идентификатора в словаре, кроме первого элемента словаря
					#print self.d.keys()[1:]
					type_cmd = self.read_str.split()[0] #идентификатор сообщения

					if len(self.read_str.split())==len(self.d[type_cmd]):
						list_args = self.read_str.split()[1:-1] # записываем все элементы кроме первого и последнего
						list_args.append(self.read_str.split()[-1][-2:]) # добавляем в конец списка адресс устройства
						list_args.append(self.read_str.split()[-1][:-2]) # добавляем в конец списка счетчик пакетов

						self.d[type_cmd] = list_args # переписываем все в структуру


	
			else:
				self.d['link'] = False	
				#print self.struct	
			#print self.d		


	def th_read(self):
		while self.isRunning:
			# self.event.wait()
			self.collect()
			#time.sleep(0.01)
			

	
	def th_write(self):
	
		while 1:
			#print "2"
			#time.sleep(0.5)
			self.cmd=self.terminal()
			if len(self.cmd)==1:
				if ord(self.cmd)==27:
					print"Exiting..."
					self.isRunning = False
					self.close
					break
			elif len(self.cmd)>1:
				if self.cmd=='print':
					print self.d
				else:
					# self.event.clear()
					self.write_byte(self.cmd)
					# self.event.set()

				
		
						




if __name__ =='__main__':

	serObj = Terminal(port="/dev/ttyS0",baudrate=115200,stopbits=1,parity="N",bytesizes=8)
	serObj.close()
	serObj.open()
	serObj.clearFIFO()
	serObj.start()











