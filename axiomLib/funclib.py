import redis


def get_state_from_redis(addr, client):
    """
    Функция запрашивает состояние элемента в redis,
    преобразует его в словарь и возвращает.
    Если состояние считать не удалось, возвращается
    значение по умолчанию, соответствующее типу элемента
    :param addr: адрес элемента
    :param client: экземпляр клиента redis
    :return: словарь с состоянием
    """
    kind = addr.split(':')[0]

    raw_state = client.get(addr)

    if raw_state:
        state = eval(raw_state.decode())
        if kind == 'ao':
            state['value'] = int(state['value'])
        return state
    else:
        if kind == 'ao':
            return {'status': False, 'value': 0}
        elif kind == 'do':
            return {'status': False}


def calculate_click_tokens(queue_length):
    """
    Рассчитываеются признаки длинного и короткого нажатия,
    в зависимости от заданной длины очереди
    :param queue_length: длина очереди
    :return: признаки длинного и короткого нажатия
    """
    short_click_tokens = []
    empty = [0] * queue_length
    for i in range(queue_length - 2):
        empty[i + 1] = 1
        temp = empty[:]
        short_click_tokens.append(temp)

    long_click_tokens = [[0] + [1] * (queue_length - 1),
                        [1] * queue_length,
                        [1] * (queue_length - 1) + [0]]

    return short_click_tokens, long_click_tokens


def reduce_repeats(queue):
    """
    Убирает одинаковые подряд идущие символы в строке (0111001 -> 0101)
    :param queue: очередь состояний выключателя
    :return: очередь без повторяющихся состояний
    """
    output = [queue[0]]
    for s in queue[1:]:
        if s == output[-1]:
            continue
        output.append(s)
    return output