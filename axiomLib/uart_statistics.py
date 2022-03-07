import redis

r = redis.StrictRedis()

commands = int(r.get('commands').decode())
success = int(r.get('success').decode())
retries = int(r.get('retries').decode())
failures = int(r.get('failures').decode())
empty_answers = int(r.get('empty answers').decode())
wrong_counter = int(r.get('wrong counter').decode())

print('commands', commands)
print('success', success)
print('retries', retries)
print('failures', failures)
print('empty answers', empty_answers)
print('wrong counter', wrong_counter)

print('mistakes rate', retries / (commands))
