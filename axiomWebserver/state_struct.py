import redis
from .models import WebElement

default_we_states = {'checkbox': {'status': False, 'value': None},
                  'range': {'status': False, 'value': 0},
                  'indicator': {'status': False, 'value': None}}

web_elements = {
            'we:0': {'room': 0, 'type': 'свет', 'name': 'Диммер', 'we_type': 'range', 'state': {'status': False, 'value': 0}},
            'we:1': {'room': 0, 'type': 'свет', 'name': 'Лампа накаливания', 'we_type': 'checkbox', 'state': {'status': False, 'value': None}},
            'we:2': {'room': 0, 'type': 'свет', 'name': 'Геркон', 'we_type': 'indicator', 'state': {'status': False, 'value': None}},
            'we:3': {'room': 0, 'type': 'свет', 'name': 'Отдел разработки 1', 'we_type': 'range', 'state': {'status': False, 'value': 0}},
            'we:4': {'room': 0, 'type': 'свет', 'name': 'Отдел проектирования 1', 'we_type': 'range', 'state': {'status': False, 'value': 0}},
            'we:5': {'room': 0, 'type': 'свет', 'name': 'Отдел разработки 2', 'we_type': 'range', 'state': {'status': False, 'value': 0}},
            'we:6': {'room': 0, 'type': 'свет', 'name': 'Отдел проектирования 2', 'we_type': 'range', 'state': {'status': False, 'value': 0}},
            'we:7': {'room': 0, 'type': 'свет', 'name': 'МатЛаб', 'we_type': 'range', 'state': {'status': False, 'value': 0}},
            'we:8': {'room': 0, 'type': 'свет', 'name': 'ОКР', 'we_type': 'range', 'state': {'status': False, 'value': 0}},
            'we:9': {'room': 0, 'type': 'свет', 'name': 'Лампа на столе', 'we_type': 'range', 'state': {'status': False, 'value': 0}},
            'we:10': {'room': 0, 'type': 'свет', 'name': 'Кран', 'we_type': 'checkbox', 'state': {'status': False, 'value': None}},
        }

def get_current_state():
    """
    Функция опрашивает БД и выдает актуальное тех. состояние
    :return: словарь с тех. состоянием
    """

    structure = {
        "rooms": {
            0: {
                "name": "Комната1",
                "icon": "/static/img/room.png"

            },
            1: {
                "name": "Комната2",
                "icon": "/static/img/room.png"
            }
        },
        "states": web_elements
    }

    # Подключаемся к БД
    r = redis.StrictRedis()

    exception = None

    # Опрашиваем БД, актуализируем состояния
    for key in structure['states'].keys():
        try:
            state = r.get(key)
            if state:
                state = eval(state.decode())
                structure['states'][key]['state'] = state
        except redis.exceptions.ConnectionError as e:
            exception = e

    if exception:
        print(exception)

    return structure

def get_we_from_db(user):
    r = redis.StrictRedis()

    we_list = WebElement.query.all()
    we_dict = {}
    output_we_list = []
    for we in we_list:
        if user.group not in we.viewers:
            print('we.viewers', we.viewers)
            print('user', user)
            print('Пропускаем элемент {}'.format(we))
            continue
        output_we_list.append({'addr': 'we:' + str(we.id),
                               'room': we.room_id,'type': we.type,
                               'name': we.name,
                               'we_type': we.we_type,
                               'viewers': [viewer.id for viewer in we.viewers],
                               'controllers': [controller.id for controller in we.controllers],
                               'state': default_we_states[we.we_type]})

        # we_dict['we:' + str(we.id)] = {'room': we.room_id,
        #                   'type': we.type,
        #                   'name': we.name,
        #                   'we_type': we.we_type,
        #                   'viewers': [viewer.id for viewer in we.viewers],
        #                   'controllers': [controller.id for controller in we.controllers],
        #                   'state': default_we_states[we.we_type]}

    for we in output_we_list:
        we_addr = we['addr']
        try:
            state = r.get(we_addr)
            if state:
                state = eval(state.decode())
                we['state'] = state
            else:
                r.set(we_addr, we['state'])
        except redis.exceptions.ConnectionError as e:
            exception = e

    return output_we_list
