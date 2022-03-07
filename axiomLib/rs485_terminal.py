#!/usr/bin/env python
# -*- coding: utf-8 -*-

import serial, time
from RPi import GPIO


def get_ch_execution_flag(cmd):
    gpio_wr(4, 1)
    serObj.clearFIFO()
    print('status flg m2')
    serObj.write_byte('status flg m2')
    gpio_wr(4, 0)
    ans = serObj.read()
    print(ans)
    serObj.clearFIFO()

    if ans:
        try:
            ans = ans.decode()
        except UnicodeDecodeError as e:
            print(e)
            return False

        try:
            flgs = ans.split('|')[1:]
            output = not any(bool(int(flg)) for flg in flgs)
            if output:
                print('\x1b[32mВозвращаемое значение {}\x1b[0m'.format(output))
            else:
                print('\x1b[31mВозвращаемое значение {}\x1b[0m'.format(output))
        except Exception as e:
            print(e)
            return False

        return output

    else:
        return False


class RpiSerial():
    def __init__(self, port, baudrate, stopbits, parity, bytesizes):
        self.port = port
        self.baudrate = int(baudrate)
        self.stopbits = int(stopbits)
        self.bytesizes = int(bytesizes)
        self.parity = parity

        try:
            self.ser = serial.Serial(port=self.port, baudrate=self.baudrate, stopbits=self.stopbits,
                                     bytesize=self.bytesizes, parity=self.parity, timeout=0.1, xonxoff=False,
                                     rtscts=False, writeTimeout=0.1, dsrdtr=False, interCharTimeout=None)
        except serial.SerialException:
            print("вставь COM-PORT")

    def open(self):
        try:
            self.ser.open()

        except serial.SerialException:
            print("cant open port")
            return -1

    def write(self, data):

        try:
            self.ser.write(data)
        except serial.SerialException:
            print("cant write data")
            return -1

        return 0

    def write_byte(self, data):
        for i in data:
            self.write(i.encode())
            time.sleep(0.01)
        self.write('\n'.encode())
        self.clearFIFO()

    def read(self):
        try:
            # readdata = self.ser.readlines()
            readdata = self.ser.read_until(terminator=b'\r', size=None)
        except serial.SerialException:
            print("cant read data")
            return
        if not readdata:
            print("error read data")

        return readdata

    def close(self):
        try:
            self.ser.close()
        except Exception as e:
            print('Some error on closing serial port: ', e)

    def clearFIFO(self):
        try:
            self.ser.flushInput()
            self.ser.flushOutput()
        except serial.SerialException:
            pass

    def led_test(self):
        for i in range(0, 32):
            cmd1 = "lr 0x0 " + str(hex(2 ** i)) + " m1"
            cmd2 = "lr 0x0 " + str(hex(2 ** i)) + " m2"
            self.write_byte(cmd1)
            self.write_byte(cmd2)
            print(cmd1, cmd2)
        self.write_byte("lr 0x0 0x0 m1")
        self.write_byte("lr 0x0 0x0 m2")


def gpio_init(num_pad, direction):
    GPIO.setmode(GPIO.BCM)
    if direction == 'OUT':
        GPIO.setup(int(num_pad), GPIO.OUT)
    elif direction == 'IN':
        GPIO.setup(int(num_pad), GPIO.IN)
    else:
        print("error direction mode gpio")


def gpio_wr(num_pad, data):
    if data == 1:
        GPIO.output(int(num_pad), GPIO.HIGH)
    elif data == 0:
        GPIO.output(int(num_pad), GPIO.LOW)
    else:
        print("data must be 1 or 0")


def terminal():
    return input("command: ")


if __name__ == '__main__':
    gpio_init(4, 'OUT')

    serObj = RpiSerial(port="/dev/ttyS0", baudrate=500000, stopbits=1, parity="N", bytesizes=8)
    serObj.close()
    serObj.open()
    serObj.clearFIFO()

    while 1:
        cmd = terminal()
        if len(cmd) == 1:
            if ord(cmd) == 27:
                print("Exiting...")
                serObj.close()
                GPIO.cleanup()
                break

        elif len(cmd) > 1:
            if cmd == 'test leds':
                gpio_wr(4, 1)
                serObj.clearFIFO()
                serObj.led_test()
                gpio_wr(4, 0)
                serObj.clearFIFO()
                print("Test pass")

            if cmd == 'adc test':
                while True:
                    gpio_wr(4, 1)
                    serObj.clearFIFO()
                    serObj.write_byte('adc rms all m3')
                    gpio_wr(4, 0)
                    print(serObj.read())
                    serObj.clearFIFO()
                    time.sleep(0.01)

            elif cmd == 'reload test':
                for ch_position in range(1, 19):
                    if ch_position == 7:
                        msg = 'ch 7 on m2'
                    else:
                        msg = 'ch {} off m2'.format(ch_position)
                    # msg = 'ch grp 0x40 m2'

                    print('\x1b[36mхочу отправить {}\x1b[0m'.format(msg))

                    # while not get_ch_execution_flag(msg):
                    #     time.sleep(0.01)

                    print(msg)
                    gpio_wr(4, 1)
                    serObj.clearFIFO()
                    serObj.write_byte(msg)
                    gpio_wr(4, 0)
                    ans = serObj.read()
                    print(ans)
                    serObj.clearFIFO()

                    for _ in range(3):
                        if ans == b'':
                            # while not get_ch_single_execution_flag(msg):
                            #     time.sleep(0.1)
                            print(msg)
                            gpio_wr(4, 1)
                            serObj.clearFIFO()
                            serObj.write_byte(msg)
                            gpio_wr(4, 0)
                            ans = serObj.read()
                            print(ans)
                            serObj.clearFIFO()
                        else:
                            break

                    time.sleep(0.1)

            else:
                gpio_wr(4, 1)
                serObj.clearFIFO()
                serObj.write_byte(cmd)
                gpio_wr(4, 0)
                print(serObj.read())
                serObj.clearFIFO()







