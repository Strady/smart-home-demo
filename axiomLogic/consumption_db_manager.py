import argparse
import json
import os
import sqlite3
import datetime as dt
import statistics
import dateutil.relativedelta as rd
import time
import numpy as np
from config import settings_path, consumption_db_name


class ConsumptionDBManager:

    def __init__(self):
        self.settings = self.read_settings()

        db_path = os.path.join(self.settings['root directory'], consumption_db_name)
        self.connection = sqlite3.connect(db_path)
        self.cursor = self.connection.cursor()

    @property
    def hour_ago(self):
        """
        :return: время час назад в формате unix time
        """
        hour_ago = dt.datetime.now() + rd.relativedelta(hours=-1)
        return hour_ago.timestamp()

    @property
    def day_ago(self):
        """
        :return: время день назад в формате unix time
        """
        day_ago = dt.datetime.now() + rd.relativedelta(days=-1)
        return day_ago.timestamp()

    @property
    def month_ago(self):
        """
        :return: время месяц назад в формате unix time
        """
        month_ago = dt.datetime.now() + rd.relativedelta(months=-1)
        return month_ago.timestamp()

    @property
    def year_ago(self):
        """
        :return: время год назад в формате unix time
        """
        year_ago = dt.datetime.now() + rd.relativedelta(years=-1)
        return year_ago.timestamp()

    def read_settings(self):
        """
        Чтение из файла настроек корневой директории и каналов,
        для которых произоводится измерение потребления
        """
        # TODO добавить обработку ошибок при чтении файла
        return json.load(open(settings_path))

    def create_DB(self):
        """
        Создает таблицы для записи значений электрических характеристик
        по минутам, часам, дням, месяцам и годам
        """

        def create_cost_table(unit, period):
            """
            Создает таблицу для хранения значений
            расходов на электроэнергию
            :param unit: адрес силового модуля
            :param period: период времени, для которого рассчитывается расход
            """
            try:
                self.cursor.execute(
                    """CREATE TABLE {}_{}_cost (timestamp DATETIME, channel_1 REAL, channel_2 REAL)""".format(
                        unit, period))
            except sqlite3.OperationalError as e:
                print(e)

        def create_active_power_table(unit, period):
            """
            Создает таблицу для хранения значений активной мощности
            :param unit: адрес силового модуля
            :param period: период времени, для которого рассчитывается расход
            """
            try:
                self.cursor.execute(
                    """CREATE TABLE {}_{}_active_power (timestamp DATETIME, channel_1 REAL, channel_2 REAL)""".format(
                        unit, period))
            except sqlite3.OperationalError as e:
                print(e)

        def create_reactive_power_table(unit, period):
            """
            Создает таблицу для хранения значений реактивной мощности
            :param unit: адрес силового модуля
            :param period: период времени, для которого рассчитывается расход
            """
            try:
                self.cursor.execute(
                    """CREATE TABLE {}_{}_reactive_power (timestamp DATETIME, channel_1 REAL, channel_2 REAL)""".format(
                        unit, period))
            except sqlite3.OperationalError as e:
                print(e)

        def create_consumption_table(unit, period):
            """
            Создает таблицу для хранения значений потребления электроэнергии
            :param unit: адрес силового модуля
            :param period: период времени, для которого рассчитывается расход
            """
            try:
                self.cursor.execute(
                    """CREATE TABLE {}_{}_consumption (timestamp DATETIME, channel_1 REAL, channel_2 REAL)""".format(
                        unit, period))
            except sqlite3.OperationalError as e:
                print(e)

        def create_current_table(unit, period):
            """
            Создает таблицу для хранения значений тока
            :param unit: адрес силового модуля
            :param period: период времени, для которого рассчитывается расход
            """
            try:
                self.cursor.execute(
                    """CREATE TABLE {}_{}_current (timestamp DATETIME, channel_1 REAL, channel_2 REAL)""".format(
                        unit, period))
            except sqlite3.OperationalError as e:
                print(e)

        def create_voltage_table(unit, period):
            """
            Создает таблицу для хранения значений напряжения
            :param unit: адрес силового модуля
            :param period: период времени, для которого рассчитывается расход
            """
            try:
                self.cursor.execute("""CREATE TABLE {}_{}_voltage (timestamp DATETIME, voltage REAL)""".format(
                    unit, period))
            except sqlite3.OperationalError as e:
                print(e)

        def create_frequency_table(unit, period):
            """
            Создает таблицу для хранения значений частоты
            :param unit: адрес силового модуля
            :param period: период времени, для которого рассчитывается расход
            """
            try:
                self.cursor.execute(
                    """CREATE TABLE {}_{}_frequency (timestamp DATETIME, frequency REAL)""".format(
                        unit, period))
            except sqlite3.OperationalError as e:
                print(e)

        with self.connection:
            for unit in self.settings['power units']:
                for period in ('minute', 'hour', 'day', 'month', 'year'):
                    create_consumption_table(unit, period)
                    create_current_table(unit, period)
                    create_cost_table(unit, period)
                    create_active_power_table(unit, period)
                    create_reactive_power_table(unit, period)

            for unit in self.settings['power units']:
                for period in ('minute', 'hour', 'day', 'month', 'year'):
                    create_frequency_table(unit, period)

            for unit in self.settings['input units']:
                for period in ('minute', 'hour', 'day', 'month', 'year'):
                    create_voltage_table(unit, period)

    def get_total_value(self, unit_addr, period, characteristic):
        """
        Запрашивает в БД данные для электрической характеристики за прошедший период
        и расчитывает обобщенное значение (сумма для энергопотребления, медиана - для тока и напряжения)
        :param characteristic: электрическая характеристика ('current', 'voltage', 'consumption')
        :param unit_addr: адрес модуля
        :param period: период времени, для которого рассчитывается обобщенное значение
        :return: обобщенное значение(я)
        """
        # Хитро составленное выражение для формирования SQL запроса
        sql_select_exp = 'SELECT * FROM {}_{}_{} WHERE timestamp > {}'.format(
            unit_addr,
            {'hour': 'minute', 'day': 'hour', 'month': 'day', 'year': 'month'}[period],
            characteristic,
            {'hour': self.hour_ago, 'day': self.day_ago, 'month': self.month_ago, 'year': self.year_ago}[period])

        with self.connection:
            query_result = self.cursor.execute(sql_select_exp)
            db_entries = query_result.fetchall()

        array_entries = np.array(db_entries)

        transposed_entries = array_entries.transpose().tolist()

        if characteristic == 'consumption':
            # Значения потребления по каждому каналу
            ch1_consumption_values = transposed_entries[1]
            ch2_consumption_values = transposed_entries[2]

            # потребление энергии за рассматриваемый период
            ch1_total_consumption = sum(ch1_consumption_values)
            ch2_total_consumption = sum(ch2_consumption_values)

            return ch1_total_consumption, ch2_total_consumption

        elif characteristic == 'active_power':
            # Значения активной мощности по каждому каналу
            ch1_active_power_values = transposed_entries[1]
            ch2_active_power_values = transposed_entries[2]

            # активная мощность за рассматриваемый период
            ch1_median_active_power = statistics.median(ch1_active_power_values)
            ch2_median_active_power = statistics.median(ch2_active_power_values)

            return ch1_median_active_power, ch2_median_active_power

        elif characteristic == 'reactive_power':
            # Значения реактивной мощности по каждому каналу
            ch1_reactive_power_values = transposed_entries[1]
            ch2_reactive_power_values = transposed_entries[2]

            # реактивная мощность за рассматриваемый период
            ch1_median_reactive_power = statistics.median(ch1_reactive_power_values)
            ch2_median_reactive_power = statistics.median(ch2_reactive_power_values)

            return ch1_median_reactive_power, ch2_median_reactive_power

        elif characteristic == 'cost':
            # расходы на электроэнергию по каждому каналу
            ch1_cost_values = transposed_entries[1]
            ch2_cost_values = transposed_entries[2]

            # суммарные расходы на электроэнергию за рассматриваемый период
            ch1_total_cost = sum(ch1_cost_values)
            ch2_total_cost = sum(ch2_cost_values)

            return ch1_total_cost, ch2_total_cost

        elif characteristic == 'current':
            # Значения тока по каждому каналу
            ch1_current_values = transposed_entries[1]
            ch2_current_values = transposed_entries[2]

            # потребление энергии за рассматриваемый период
            ch1_median_current = statistics.median(ch1_current_values)
            ch2_median_current = statistics.median(ch2_current_values)

            return ch1_median_current, ch2_median_current

        elif characteristic == 'frequency':
            # Значения частоты
            frequency_values = transposed_entries[1]

            max_frequency = max(frequency_values)

            return max_frequency

        elif characteristic == 'voltage':
            # Значения напряжения
            voltage_values = transposed_entries[1]

            # медианное значение напряжения за рассматриваемый период
            median_voltage = statistics.median(voltage_values)

            return median_voltage

    def insert_new_and_delete_old(self, unit_addr, period, characteristic, values):

        # SQL команды для добавления новой записи и удаления старых в таблицы
        sql_insert_template = 'INSERT INTO {unit}_{time_unit}_{characteristic} (timestamp, {value_columns}) ' \
                              'VALUES ({time}, {values})'

        sql_insert_expression = sql_insert_template.format(unit=unit_addr,
                                                           time_unit=period,
                                                           characteristic=characteristic,
                                                           value_columns={'active_power': 'channel_1, channel_2',
                                                                          'reactive_power': 'channel_1, channel_2',
                                                                          'consumption': 'channel_1, channel_2',
                                                                          'cost': 'channel_1, channel_2',
                                                                          'current': 'channel_1, channel_2',
                                                                          'voltage': 'voltage',
                                                                          'frequecy': 'frequency'}[characteristic],
                                                           time=time.time(),
                                                           values=', '.join(str(value) for value in values))

        # Добавляем новую запись
        with self.connection:
            self.cursor.execute(sql_insert_expression)

        # Удаляем старые записи, если требуется
        delete_before = {'hour': self.month_ago, 'day': self.month_ago}.get(period)
        if delete_before:
            sql_delete_expression = 'DELETE FROM {}_{}_{} WHERE timestamp < {}'.format(
                unit_addr, period, characteristic, delete_before)

            with self.connection:
                self.cursor.execute(sql_delete_expression)

    def make_db_entry(self, period):
        """
        Читает из таблицы <unit>_<period>_<characteristic> данные потребления,
        тока и напряжения для каждого канала, сделанные за последний час и
        записывает обобщенное значение в БД.
        Удаляет записи, сделанные более месяца назад
        """

        # Делаем записи потребления и тока для каждого силового модуля
        for unit in self.settings['power units']:
            # потребление энергии за период
            total_consumption = self.get_total_value(unit, period, 'consumption')
            self.insert_new_and_delete_old(unit, period, 'consumption', total_consumption)

            # стоимость потребленной за период электроэнергии
            total_cost = self.get_total_value(unit, period, 'cost')
            self.insert_new_and_delete_old(unit, period, 'cost', total_cost)

            # медианное значение тока за период
            total_current = self.get_total_value(unit, period, 'current')
            self.insert_new_and_delete_old(unit, period, 'current', total_current)

            # медианное значение активной мощности за период
            total_active_power = self.get_total_value(unit, period, 'active_power')
            self.insert_new_and_delete_old(unit, period, 'active_power', total_active_power)

            # медианное значение реактивной мощности за период
            total_reactive_power = self.get_total_value(unit, period, 'reactive_power')
            self.insert_new_and_delete_old(unit, period, 'reactive_power', total_reactive_power)

            # максимальное значение частоты за период
            total_frequency = self.get_total_value(unit, period, 'frequency')
            self.insert_new_and_delete_old(unit, period, 'frequency', total_frequency)

        # Делаем записи напряжения для каждого модуля ввода
        for unit in self.settings['input units']:
            # медианное значение напряжения за период
            total_voltage = self.get_total_value(unit, period, 'voltage')
            self.insert_new_and_delete_old(unit, period, 'voltage', (total_voltage,))


if __name__ == '__main__':
    # Парсим аргументы командной строки
    parser = argparse.ArgumentParser()
    parser.add_argument('-i', '--init', action='store_true', help='create database')
    parser.add_argument('-hr', '--hour', action='store_true', help='write hour consumption to DB')
    parser.add_argument('-d', '--day', action='store_true', help='write day consumption to DB')
    parser.add_argument('-m', '--month', action='store_true', help='write month consumption to DB')
    parser.add_argument('-y', '--year', action='store_true', help='write year consumption to DB')

    args = parser.parse_args()

    db_manager = ConsumptionDBManager()

    if args.init:
        db_manager.create_DB()
    elif args.hour:
        db_manager.make_db_entry('hour')
    elif args.day:
        db_manager.make_db_entry('day')
    elif args.month:
        db_manager.make_db_entry('month')
    elif args.year:
        db_manager.make_db_entry('year')
