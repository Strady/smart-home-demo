from apscheduler.schedulers.background import BackgroundScheduler
from pubsub import pub
print('scheduler', id(pub))


class LogicScheduler:

    def __init__(self):

        self.scheduler = BackgroundScheduler()
