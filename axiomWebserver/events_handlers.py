import ujson

from flask import request, json, session
from flask_socketio import join_room, leave_room, disconnect, emit
from flask_login import current_user, login_user
from axiomWebserver import socketio, stream_logger, file_logger, debug_colors, bcrypt
from threading import Lock
import redis
import functools
from .models import User, WebElement


sub_thread = None  # поток, в котором читаются публикуемые в redis сообщения
thread_lock = Lock()
num_of_clients = 0  # количество подключенных клиентов. Если 0, то sub_thread останавливается
we_proxy = WebElement.query
r = redis.StrictRedis(port=6379, charset='utf-8', decode_responses=True)


def authenticated_only(f):
    @functools.wraps(f)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            print('current user is not authenticated -> do nothing')
            emit('info', 'you are not authorized')
            # disconnect()
        else:
            print('current user is ', current_user)
            return f(*args, **kwargs)
    return wrapped


def sub_thread_target():
    """
    функция запускается в потоке sub_thread
    подписывается на сообщения в redis
    """
    subscriber = r.pubsub(ignore_subscribe_messages=True)
    subscriber.subscribe('axiomLogic:info:state')

    characteristics_subscriber = r.pubsub(ignore_subscribe_messages=True)
    characteristics_subscriber.subscribe('axiomLogic:info:characteristics')

    isol_subscriber = r.pubsub(ignore_subscribe_messages=True)
    isol_subscriber.subscribe('axiomLogic:response:insulation')
    
    # print('num of clients', num_of_clients)
    while num_of_clients:
        message = subscriber.get_message()
        # print("state mesage {}".format(message))
        if message:
            try:
                data = ujson.loads(message['data'])
            except (TypeError, ValueError) as e:
                print("except state {}".format(e))
                continue

            print('\x1b[33mstate change data: {}\x1b[0m'.format(data))
            file_logger.info('Получено сообщение от логики: {}'.format(data))
            socketio.emit('state change', data, json=True, broadcast=True)

        characteristics_message = characteristics_subscriber.get_message()
        if characteristics_message:
            try:
                characteristics_dict = ujson.loads(characteristics_message['data'])
            except (TypeError, ValueError) as e:
                file_logger.error('Ошибка при разборе сообщения: {}'.format(e))
                continue
            socketio.emit('characteristics', characteristics_dict, json=True, broadcast=True)

        isol_message = isol_subscriber.get_message()
        if isol_message:
            socketio.emit('insulation:response', isol_message['data'], json=True, broadcast=True)

        socketio.sleep(seconds=0.01)


@socketio.on('pushdata', namespace='/')
def pushdata(data):
    """
    Принимает команды управления и пересылает их
    на модуль "Логика", если клиент авторизован и
    имеет право на управление данным ВЭК. Иначе на
    клиент отправляется сообщение с текущим
    состоянием ВЭК.
    :param data: команда на изменение состояния
    """
    log_msg = 'Получено сообщение от клиента {}'.format(data)
    stream_logger.debug(debug_colors['INFO'] % log_msg)
    file_logger.info(log_msg)
    we_addr = data['id']
    we = WebElement.query.filter_by(addr=we_addr).first()

    if current_user.is_authenticated and current_user.group in we.controllers:
        print('\x1b[36mpublishing message: {}\x1b[0m'.format(data))
        r.publish('axiomWebserver:cmd:state', json.dumps(data))
    else:
        prev_state = eval(r.get(we_addr))
        socketio.emit('state change', {'id': we_addr, 'state': prev_state}, json=True)


@socketio.on('insulation:request', namespace='/')
def insulation_request(channel_addr):
    """
    Принимает запрос от веб-клиента на измерение
    сопротивления изоляции канала силового модуля, и,
    если пользователь авторизован, передает его
    на модуль "Логика"
    :param channel_addr: адрес канала силового модуля 
    """
    if current_user.is_authenticated:
        r.publish('axiomWebserver:request:insulation', channel_addr)


@socketio.on('connect', namespace='/')
def on_connect():

    print('client connected', request.sid)
    print('current user:', current_user)
    print('\x1b[31mrequest {}\x1b[0m'.format(request))
    print('\x1b[32msession {}\x1b[0m'.format(session))

    global num_of_clients, sub_thread

    if not current_user.is_authenticated:
        num_of_clients += 1
        print('disconnecting unauthorized user')
        emit('disconnected', 'you are not authenticated. disconnecting')
        disconnect()
    else:
        room = str(current_user.group)
        log_msg = 'Пользователь {} добавлен в комнату {}'.format(current_user.username, room)
        stream_logger.debug(debug_colors['INFO'] % log_msg)
        file_logger.info(log_msg)
        join_room(room=room)
        # если это первый подключенный клиент, то запускаем поток подписчик
        with thread_lock:
            # print('add client')
            num_of_clients += 1
            if sub_thread is None:
                sub_thread = socketio.start_background_task(target=sub_thread_target)


# @socketio.on('test', namespace='/')
# @authenticated_only
# def test(data):
#     print('\x1b[35min test channel: %s\x1b[0m' % data)
#     group = str(current_user.group)
#     socketio.emit('test response', 'in test channel: %s' % data, broadcast=True, room=group)
#
#
# @socketio.on('join')
# def on_join(data):
#     print('\x1b[35msomeone joined some room\x1b[0m')
#     print('data', data)


@socketio.on('disconnect')
def on_disconnect():
    """
    при отключении клиента уменьшаем количество подключенных клиентов на 1
    если подключенных клиентов не осталось останавливаем поток подписчик
    :return:
    """
    # print('Client disconnected', current_user)
    if current_user.is_authenticated:

        group = str(current_user.group)
        leave_room(group)

        log_msg = 'Пользователь {} вышел из комнаты {}'.format(current_user.username, group)
        stream_logger.debug(debug_colors['INFO'] % log_msg)
        file_logger.info(log_msg)

    global num_of_clients, sub_thread
    with thread_lock:
        # if num_of_clients:
        #     num_of_clients -= 1
        if not num_of_clients:
            sub_thread = None

# @socketio.on('ready for mounting')
# def on_ready_for_mounting():
#     print('get ready for mounting')
#     with open('/etc/axiom/elements_list.json') as f:
#         elements_list = json.load(f)
#     socketio.emit('getData', elements_list, json=True, broadcast=True)
#
# @socketio.on('blink')
# def on_blink(addr):
#     print('\x1b[33mgot address %s\x1b[0m' % addr)
#     r.publish('mounting service commands', addr)

#DEPRECATED
# @socketio.on('auth')
# def auth(data):
#     """
#     Авторизация пользователя (с использованием websocket)
#     """
#     print('autorization data from client', request.sid)
#     print('data', data)
#     username = data.get('username')
#     password = data.get('password')
#
#     if username and password:
#         if not current_user.is_authenticated:
#             user = User.query.filter_by(username=username).first()
#             if user and bcrypt.check_password_hash(user.password, password):
#                 login_user(user)
#                 print('user logged in:', user)
#                 emit('auth_status', 'authorized')
#                 group = str(user.group)
#                 join_room(group)
#             else:
#                 print('invalid authorization data: ', data)
#                 emit('auth_status', 'rejected')
#     else:
#         print('invalid authorization data: ', data)
#         emit('auth_status', 'rejected')
