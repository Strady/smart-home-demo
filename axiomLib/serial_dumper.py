import threading

import serial

s_1 = serial.Serial(port='COM4', baudrate=115200)
s_2 = serial.Serial(port='COM5', baudrate=115200)
prev = None
current = None
i = 1

def f1():
    while True:
        with open('serial_dump2.txt', 'a') as f:
            line = s_1.read_until(terminator=b'\r\n')
            # print(line)
            # if b'run start' in line or b'adc h' in line or b'ch' in line:
            #     current = line
            #     if current == prev:
            #         print(str(i) + '!!!')
            #     prev = current

            f.write('s_1:' + str(line) + '\n')
            # i += 1


def f2():
    while True:
        with open('serial_dump2.txt', 'a') as f:
            line = s_2.read_until(terminator=b'\r\n')
            # print(line)
            # if b'run start' in line or b'adc h' in line or b'ch' in line:
            #     current = line
            #     if current == prev:
            #         print(str(i) + '!!!')
            #     prev = current

            f.write('s_2:' + str(line) + '\n')
            # i += 1


threading.Thread(target=f1).start()
threading.Thread(target=f2).start()