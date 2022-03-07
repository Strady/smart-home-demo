import re
import time

import influxdb
import werkzeug
from flask import jsonify, request, make_response, redirect, url_for
from flask_api import status
from axiomWebserver import app, bcrypt, r
from flask_login import login_user, current_user, logout_user, login_required
from .APIerrors import error_response
from .models import User, WebElement, LogEntry
import sqlite3
import os
import json
import ujson
import redis
from datetime import datetime as dt
import dateutil.relativedelta as rd

settings_path = app.config['AXIOM_SETTINGS_PATH']
settings = json.load(open(settings_path))
redis_connection = redis.StrictRedis(decode_responses=True)


@app.route('/api/markup')
@login_required
def send_markup():
    """
    API для запроса информации с разметкой для интерфейса
    :return: список json представлений веб элементов
    """
    # Список веб элементов доступных данному пользователю
    we_list = [we.to_dict() for we in WebElement.query.all() if current_user.group in we.viewers]
    print("we_list")
    print(we_list)
    try:
        r = redis.StrictRedis()
        # Если в redis сохранено состояние веб элемента для данного адреса,
        # то устанавливаем его в словарь веб элемента. Если нет, то сохраняем
        # в redis значение по умолчанию для данного элемента
        for we in we_list:
            # if we['addr']=='we:1':
            #     we_addr='ch:m2:1'
            # elif we['addr']=='we:2':
            #     we_addr='ch:m2:2'
            we_addr = we['addr']
            state = r.get(we_addr)
            print("we adrr {} state {}".format(we_addr, state))
            if state:
                state = eval(state.decode())
                we['state'] = state
            else:
                r.set(we_addr, we['state'])
    except redis.exceptions.ConnectionError as e:
        print(e)

    return jsonify(we_list)

@app.route('/api/journal')
@login_required
def send_journal():
    log_entries = LogEntry.query.all()
    journal = []
    for log_entry in log_entries:
        journal.append({'timestamp': log_entry.timestamp,
                        'event': log_entry.event})

    return jsonify(journal)

@app.route('/api/ar')
def ar():
    """
    URL для поиска IP адреса аксиома в сети
    :return: пустой ответ со статусом ОК
    """
    return '', 204

# DEPRECATED
@app.route('/api/consumption_data')
def send_consumption():
    """
    API для запроса данных о потреблении в каналах силового модуля
    :return: http response
    """
    payload = {}

    # Проверка корректности параметров запроса
    time_unit = request.args.get('time_unit')
    if time_unit not in ['minute', 'hour', 'day', 'month', 'year']:
        error_msg = "'{}' period is not valid".format(time_unit)
        payload['error'] = error_msg
        response = jsonify(payload)
        response.status_code = 400
        return response

    beginning = request.args.get('beginning')
    try:
        beginning = float(beginning)
        dt.fromtimestamp(beginning)
    except (OSError, OverflowError, ValueError, TypeError):
        error_msg = "'{}' beginning timestamp is not valid".format(beginning)
        payload['error'] = error_msg
        response = jsonify(payload)
        response.status_code = 400
        return response

    ending = request.args.get('ending')
    try:
        ending = float(ending)
        dt.fromtimestamp(ending)
    except (OSError, OverflowError, ValueError, TypeError):
        error_msg = "'{}' ending timestamp is not valid".format(ending)
        payload['error'] = error_msg
        response = jsonify(payload)
        response.status_code = 400
        return response

    # Подключение к БД
    db_path = os.path.join(app.config['AXIOM_ROOT_PATH'], app.config['CONSUMPTION_DB_NAME'])
    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()

    for unit in settings['power units']:

        # Чтение из БД
        sql_query = 'SELECT * FROM {}_{}_consumption WHERE timestamp >= {} AND timestamp < {}'.format(
            unit, time_unit, beginning, ending)
        with connection:
            query_result = cursor.execute(sql_query)
        data = query_result.fetchall()

        # В случае отсутствия данных, удовлетворяющих параметрам запроса
        if not data:
            error_msg = "no consumption data found for requested period"
            payload['error'] = error_msg
            response = jsonify(payload)
            response.status_code = 404
            return response

        # Формирование json ответа
        payload[unit] = []

        for entry in data:
            entry_dict = {'timestamp': entry[0]}
            chanel_value_dict = {str(i + 1): value for i, value in enumerate(entry[1:])}
            entry_dict.update(chanel_value_dict)
            payload[unit].append(entry_dict)

    return jsonify(payload)

# DEPRECATED
@app.route('/api/cost_data')
def send_cost():
    """
    API для запроса данных о расходах на электроэнергию в каналах силового модуля
    :return: http response
    """
    payload = {}

    # Проверка корректности параметров запроса
    time_unit = request.args.get('time_unit')
    if time_unit not in ['minute', 'hour', 'day', 'month', 'year']:
        error_msg = "'{}' period is not valid".format(time_unit)
        payload['error'] = error_msg
        response = jsonify(payload)
        response.status_code = 400
        return response

    beginning = request.args.get('beginning')
    try:
        beginning = float(beginning)
        dt.fromtimestamp(beginning)
    except (OSError, OverflowError, ValueError, TypeError):
        error_msg = "'{}' beginning timestamp is not valid".format(beginning)
        payload['error'] = error_msg
        response = jsonify(payload)
        response.status_code = 400
        return response

    ending = request.args.get('ending')
    try:
        ending = float(ending)
        dt.fromtimestamp(ending)
    except (OSError, OverflowError, ValueError, TypeError):
        error_msg = "'{}' ending timestamp is not valid".format(ending)
        payload['error'] = error_msg
        response = jsonify(payload)
        response.status_code = 400
        return response

    # Подключение к БД
    db_path = os.path.join(app.config['AXIOM_ROOT_PATH'], app.config['CONSUMPTION_DB_NAME'])
    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()

    for unit in settings['power units']:

        # Чтение из БД
        sql_query = 'SELECT * FROM {}_{}_cost WHERE timestamp >= {} AND timestamp < {}'.format(
            unit, time_unit, beginning, ending)
        with connection:
            query_result = cursor.execute(sql_query)
        data = query_result.fetchall()

        # В случае отсутствия данных, удовлетворяющих параметрам запроса
        if not data:
            error_msg = "no cost data found for requested period"
            payload['error'] = error_msg
            response = jsonify(payload)
            response.status_code = 404
            return response

        # Формирование json ответа
        payload[unit] = []

        for entry in data:
            entry_dict = {'timestamp': entry[0]}
            chanel_value_dict = {str(i + 1): value for i, value in enumerate(entry[1:])}
            entry_dict.update(chanel_value_dict)
            payload[unit].append(entry_dict)

    return jsonify(payload)

# DEPRECATED
@app.route('/api/current_data')
def send_current():
    """
    API для запроса данных о потребляемом токе в каналах силового модуля
    :return: http response
    """
    payload = {}

    # Проверка корректности параметров запроса
    time_unit = request.args.get('time_unit')
    if time_unit not in ['minute', 'hour', 'day', 'month', 'year']:
        error_msg = "'{}' period is not valid".format(time_unit)
        payload['error'] = error_msg
        response = jsonify(payload)
        response.status_code = 400
        return response

    beginning = request.args.get('beginning')
    try:
        beginning = float(beginning)
        dt.fromtimestamp(beginning)
    except (OSError, OverflowError, ValueError, TypeError):
        error_msg = "'{}' beginning timestamp is not valid".format(beginning)
        payload['error'] = error_msg
        response = jsonify(payload)
        response.status_code = 400
        return response

    ending = request.args.get('ending')
    try:
        ending = float(ending)
        dt.fromtimestamp(ending)
    except (OSError, OverflowError, ValueError, TypeError):
        error_msg = "'{}' ending timestamp is not valid".format(ending)
        payload['error'] = error_msg
        response = jsonify(payload)
        response.status_code = 400
        return response

    # Подключение к БД
    db_path = os.path.join(app.config['AXIOM_ROOT_PATH'], app.config['CONSUMPTION_DB_NAME'])
    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()


    for unit in settings['power units']:
        # Чтение из БД
        sql_query = 'SELECT * FROM {}_{}_current WHERE timestamp >= {} AND timestamp < {}'.format(
            unit, time_unit, beginning, ending)
        with connection:
            query_result = cursor.execute(sql_query)
        data = query_result.fetchall()

        # В случае отсутствия данных, удовлетворяющих параметрам запроса
        if not data:
            error_msg = "no current data found for requested period"
            payload['error'] = error_msg
            response = jsonify(payload)
            response.status_code = 404
            return response

        # Формирование json ответа
        payload[unit] = [{'timestamp': entry[0], 'current1': entry[1], 'current2': entry[2]} for entry in data]

    return jsonify(payload)

# DEPRECATED
@app.route('/api/voltage_data')
def send_voltage():
    """
    API для запроса данных о напряжении на модулях ввода
    :return: http response
    """
    payload = {}

    # Проверка корректности параметров запроса
    time_unit = request.args.get('time_unit')
    if time_unit not in ['minute', 'hour', 'day', 'month', 'year']:
        error_msg = "'{}' period is not valid".format(time_unit)
        payload['error'] = error_msg
        response = jsonify(payload)
        response.status_code = 400
        return response

    beginning = request.args.get('beginning')
    try:
        beginning = float(beginning)
        dt.fromtimestamp(beginning)
    except (OSError, OverflowError, ValueError, TypeError):
        error_msg = "'{}' beginning timestamp is not valid".format(beginning)
        payload['error'] = error_msg
        response = jsonify(payload)
        response.status_code = 400
        return response

    ending = request.args.get('ending')
    try:
        ending = float(ending)
        dt.fromtimestamp(ending)
    except (OSError, OverflowError, ValueError, TypeError):
        error_msg = "'{}' ending timestamp is not valid".format(ending)
        payload['error'] = error_msg
        response = jsonify(payload)
        response.status_code = 400
        return response

    # Подключение к БД
    db_path = os.path.join(app.config['AXIOM_ROOT_PATH'], app.config['CONSUMPTION_DB_NAME'])
    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()

    for unit in settings['input units']:

        # Чтение из БД
        sql_query = 'SELECT * FROM {}_{}_voltage WHERE timestamp >= {} AND timestamp < {}'.format(
            unit, time_unit, beginning, ending)
        with connection:
            query_result = cursor.execute(sql_query)
        data = query_result.fetchall()

        # В случае отсутствия данных, удовлетворяющих параметрам запроса
        if not data:
            error_msg = "no voltage data found for requested period"
            payload['error'] = error_msg
            response = jsonify(payload)
            response.status_code = 404
            return response

        # Формирование json ответа
        payload[unit] = [{'timestamp': entry[0], 'voltage': entry[1]} for entry in data]

    return jsonify(payload)

# DEPRECATED
@app.route('/api/login')
def api_login():
    """
    API для авторизации пользователя
    :return: HTTP response
    """
    auth = request.authorization

    if not auth or not auth.username or not auth.password:
        return error_response(401)

    user = User.query.filter_by(username=auth.username).first()

    if not user:
        return error_response(401)

    if bcrypt.check_password_hash(user.password, auth.password):
        login_user(user)

        return jsonify({'User group': str(user.group)})
    else:
        return error_response(401)

# DEPRECATED
@app.route('/api/logout')
def api_logout():
    """
    API для разлогинивания пользователя
    """
    if current_user.is_authenticated:
        logout_user()
    return redirect(url_for('login'))

@app.route('/api/consumption_rates', methods=['GET', 'POST'])
def consumption_rates():
    if request.method == 'POST':
        try:
            zones = request.get_json()
        except werkzeug.exceptions.BadRequest:
            return make_response(jsonify('invalid request JSON'), 400)

        # Если нет ни одного значения - что-то пошло не так
        if not zones:
            return make_response(jsonify('no rate value received'), 400)

        time_template = r'^(([0-1]{0,1}[0-9])|(2[0-3])):[0-5]{0,1}[0-9]$'

        for i, zone in enumerate(zones):
            try:
                float(zone.get('rate'))
            except ValueError:
                return make_response(jsonify('invalid rate value for zone {}'.format(i)), 400)
            if not re.match(time_template, zone.get('beginning')):
                return make_response(jsonify('invalid beginning time for time zone {}'.format(i)), 400)

        # Проверяем, что каждое последующее значение начала тарифной зоны больше предыдущего
        for i in range(len(zones) - 1):
            lower_value = int(zones[i]['beginning'].split(':')[0]) * 60 + int(zones[i]['beginning'].split(':')[1])
            greater_value = int(zones[i + 1]['beginning'].split(':')[0]) * 60 + int(zones[i + 1]['beginning'].split(':')[1])
            if lower_value > greater_value:
                return make_response(jsonify('time zone {} must start earlier then time zone {}'.format(
                    i + 1, i + 2)), 400)

        r.set('consumption_rate', zones)

        return make_response('', 200)

    elif request.method == 'GET':

        output_json = []

        for i in range(4):
            zone = {}
            rate = r.get('zone{}:rate'.format(i + 1))
            if rate:
                zone['rate'] = float(rate)
                beginning = r.get('zone{}:beginning'.format(i + 1))
                if beginning:
                    zone['beginning'] = beginning
                output_json.append(zone)

        return jsonify(output_json)

@app.route('/api/chart_data/<parameter>')
def send_chart_data(parameter):
    """
    API для запроса данных для графиков энергетических характеристик
    """
    # Проверка доступности запрашиваемой характеристики
    if parameter not in ('consumption', 'cost', 'current', 'voltage', 'frequency', 'active_power', 'reactive_power'):
        return make_response(jsonify('Invalid parameter \'{}\''.format(parameter)), status.HTTP_400_BAD_REQUEST)

    # Проверка корректности параметров запроса
    time_unit = request.args.get('time_unit')
    if time_unit not in ['minute', 'hour', 'day', 'month', 'year']:
        return make_response(jsonify('"{}" period is not valid'.format(time_unit)), status.HTTP_400_BAD_REQUEST)

    beginning = request.args.get('beginning')
    try:
        beginning = float(beginning)
        dt.fromtimestamp(beginning)
    except (OSError, OverflowError, ValueError, TypeError):
        return make_response(jsonify('"{}" beginning timestamp is not valid'.format(beginning)), status.HTTP_400_BAD_REQUEST)

    ending = request.args.get('ending')
    try:
        ending = float(ending)
        dt.fromtimestamp(ending)
    except (OSError, OverflowError, ValueError, TypeError):
        return make_response(jsonify('"{}" ending timestamp is not valid'.format(ending)), status.HTTP_400_BAD_REQUEST)

    payload = {}

    # Подключение к БД
    db_path = os.path.join(app.config['AXIOM_ROOT_PATH'], app.config['CONSUMPTION_DB_NAME'])
    connection = sqlite3.connect(db_path)
    cursor = connection.cursor()

    if parameter in ('consumption', 'cost', 'current', 'active_power', 'reactive_power', 'frequency'):

        for unit in settings['power units']:
            # Чтение из БД
            sql_query = 'SELECT * FROM {}_{}_{} WHERE timestamp >= {} AND timestamp < {}'.format(
                unit, time_unit, parameter, beginning, ending)
            with connection:
                query_result = cursor.execute(sql_query)
            data = query_result.fetchall()

            # Формирование json ответа
            payload[unit] = [{'timestamp': entry[0],
                              '{}_1'.format(parameter): entry[1],
                              '{}_2'.format(parameter): entry[2]} for entry in data]

    # if parameter in ('frequency'):
    #
    #     for unit in settings['power units']:
    #         # Чтение из БД
    #         sql_query = 'SELECT * FROM {}_{}_{} WHERE timestamp >= {} AND timestamp < {}'.format(
    #             unit, time_unit, parameter, beginning, ending)
    #         with connection:
    #             query_result = cursor.execute(sql_query)
    #         data = query_result.fetchall()
    #
    #         if data:
    #             # Формирование json ответа
    #             payload[unit] = [{'timestamp': entry[0], 'frequency': entry[1]} for entry in data]

    elif parameter in ('voltage',):
        for unit in settings['input units']:
            # Чтение из БД
            sql_query = 'SELECT * FROM {}_{}_{} WHERE timestamp >= {} AND timestamp < {}'.format(
                unit, time_unit, parameter, beginning, ending)
            with connection:
                query_result = cursor.execute(sql_query)
            data = query_result.fetchall()

            if data:
                # Формирование json ответа
                payload[unit] = [{'timestamp': entry[0], 'voltage': entry[1]} for entry in data]

    if not payload:
        return make_response(jsonify('no data found for the requested period'), status.HTTP_404_NOT_FOUND)
    else:
        return jsonify(payload)

@app.route('/api/chart_data_influx/<parameter>', methods=['GET', 'POST'])
def send_influx_chart_data(parameter):
    """
    Выдает точки для построения графиков метрик,
    хранящиеся в БД influxdb
    :param parameter: метрика (напряжение, ток и т.д.)
    """
    # Проверка доступности запрашиваемой характеристики
    if parameter not in ('consumption', 'cost', 'current', 'voltage', 'frequency', 'active_power', 'reactive_power', 'temperature'):
        return make_response(jsonify('Invalid parameter \'{}\''.format(parameter)), status.HTTP_400_BAD_REQUEST)

    # channel_addrs = request.json.get('channels')
    try:
        channel_addrs = [channel.strip() for channel in request.args.get('channels').split(',') if channel]
    except Exception as e:
        return make_response(jsonify('invalid "channels" value: {}'.format(e)), status.HTTP_400_BAD_REQUEST)
    if not channel_addrs:
        return make_response(jsonify('"channels" field is empty'), status.HTTP_400_BAD_REQUEST)

    try:
        # beginning = dt.fromtimestamp(request.json['beginning'])
        beginning = dt.fromtimestamp(int(request.args.get('beginning')))
    except Exception as e:
        return make_response(jsonify('invalid "beginning" field value: {}'.format(e)), status.HTTP_400_BAD_REQUEST)

    try:
        # ending = dt.fromtimestamp(request.json['ending'])
        ending = dt.fromtimestamp(int(request.args.get('ending')))
    except Exception as e:
        return make_response(jsonify('invalid "ending" field value: {}'.format(e)), status.HTTP_400_BAD_REQUEST)

    # now = dt.now()

    if not ending > beginning:
        return make_response(jsonify('ending > beginning is not satisfied'), status.HTTP_400_BAD_REQUEST)

    hour_ago = dt.now() + rd.relativedelta(hours=-1)
    day_ago = dt.now() + rd.relativedelta(days=-1)
    week_ago = dt.now() + rd.relativedelta(weeks=-1)

    client = influxdb.InfluxDBClient(host='localhost', port=8086)
    client.switch_database('axiom_metrics')

    # Определяем разрешение по времени для полученного запроса

    if beginning < week_ago:
        rt = 'infinity'
    elif beginning < day_ago:
        rt = 'week'
    else:
        rt = 'day'

    output_json = {}

    # Делаем запрос для каждого канала
    for channel_addr in channel_addrs:

        _, unit_addr, channel = channel_addr.split(':')

        query = ('SELECT "value" FROM "axiom_metrics"."{rt}"."{measurement}" WHERE '
                 '"unit_addr" = \'{unit_addr}\' and '
                 '"channel" = \'{channel}\' and '
                 '"time" >= {beginning} and '
                 '"time" <= {ending}'.format(rt=rt,
                                             measurement=parameter,
                                             unit_addr=unit_addr,
                                             channel=channel,
                                             beginning=int(beginning.timestamp() * 1e9),
                                             ending=int(ending.timestamp() * 1e9)))
        print(query)
        result = client.query(query=query, epoch='s')

        output_json[channel_addr] = list(result.get_points())

    return jsonify(output_json)


@app.route('/api/schedule', methods=['GET', 'POST'])
def create_or_read_job():
    """
    HTTP интерфейс для получения списка запланированных задач или
    добавления новой задачи в планировщик

    JSON тела запроса для добавления новой задачи (пример):

    {
        "func": "configurable_change_ch_state",
        "kwargs": {"addr": "ch:m2:1", "status': "4"],
        "trigger": "interval",
        "minutes": 10
    }
    """
    # добавление новой задачи
    if request.method == 'POST':

        job_parameters = request.get_json()
        redis_connection.publish(channel='axiomWebserver:schedule:create', message=ujson.dumps(job_parameters))

        db_path = os.path.join(app.config['AXIOM_ROOT_PATH'], app.config['JOBS_DB_NAME'])
        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()

        # ждем некоторое время, пока задача добавляется в БД
        time.sleep(1)

        # Читаем задачи из БД
        with connection:
            cursor.execute('SELECT * FROM schedule_jobs')
            query_result = cursor.fetchall()

        # Отправляем клиенту только что созданную задачу
        jobs = {}
        for job_id, str_job_kwargs in query_result:
            job_kwargs = ujson.loads(str_job_kwargs)
            if job_kwargs == job_parameters:
                jobs[job_id] = job_kwargs

        return jsonify(jobs)

    elif request.method == 'GET':
        db_path = os.path.join(app.config['AXIOM_ROOT_PATH'], app.config['JOBS_DB_NAME'])
        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()

        # Читаем задачи из БД
        with connection:
            cursor.execute('SELECT * FROM schedule_jobs')
            query_result = cursor.fetchall()

        # Форматируем список задач для передачи клиенту
        jobs = {}
        for job_id, str_job_kwargs in query_result:
            job_kwargs = ujson.loads(str_job_kwargs)
            jobs[job_id] = job_kwargs

        return jsonify(jobs)


@app.route('/api/schedule/<job_id>', methods=['DELETE', 'PUT'])
def delete_or_update_job(job_id):
    """
    HTTP интерфейс для удаления или изменения задачи

    JSON тела запроса для изменения задачи (пример):

    {
        "func": "configurable_change_ch_state",
        "kwargs": {"addr": "ch:m2:1", "status': "4"],
        "trigger": "interval",
        "minutes": 10
    }
    """
    if request.method == 'DELETE':

        redis_connection.publish(channel='axiomWebserver:schedule:delete', message=job_id)

        db_path = os.path.join(app.config['AXIOM_ROOT_PATH'], app.config['JOBS_DB_NAME'])
        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()

        # ждем некоторое время, пока задача добавляется в БД
        time.sleep(1)

        # Читаем задачи из БД
        with connection:
            cursor.execute('SELECT * FROM schedule_jobs')
            query_result = cursor.fetchall()

        # Форматируем список задач для передачи клиенту
        jobs = {}
        for job_id, str_job_kwargs in query_result:
            job_kwargs = ujson.loads(str_job_kwargs)
            jobs[job_id] = job_kwargs

        return jsonify(jobs)

    elif request.method == 'PUT':

        job_parameters = request.get_json()

        # добавим id задачи в параметры, чтобы передать на логику и то, и то
        job_parameters['id'] = job_id

        redis_connection.publish(channel='axiomWebserver:schedule:update', message=ujson.dumps(job_parameters))

        db_path = os.path.join(app.config['AXIOM_ROOT_PATH'], app.config['JOBS_DB_NAME'])
        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()

        # ждем некоторое время, пока задача обновляется в БД
        time.sleep(1)

        # Читаем задачи из БД
        with connection:
            cursor.execute('SELECT * FROM schedule_jobs')
            query_result = cursor.fetchall()

        # Форматируем список задач для передачи клиенту
        jobs = {}
        for job_id, str_job_kwargs in query_result:
            job_kwargs = ujson.loads(str_job_kwargs)
            jobs[job_id] = job_kwargs

        return jsonify(jobs)

