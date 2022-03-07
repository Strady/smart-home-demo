import redis

r = redis.StrictRedis(decode_responses=True)

print('program start time: ', r.get('start_time'))
for unit_addr in ('m1', 'm2', 'm3', 'm4', 'm5', 'm6'):
    sended = r.get('{}_sended'.format(unit_addr))
    failures = r.get('{}_failures'.format(unit_addr))
    print('unit addres: ', unit_addr,
          'commands_sended: ', sended,
          'failures: ', failures,
          'failures percentage: ', '{0:.2f}'.format((int(failures)/int(sended))*100))
