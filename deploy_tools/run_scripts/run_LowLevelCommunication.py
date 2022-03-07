import signal
import setproctitle
from axiomLowLevelCommunication import hlt

if __name__ == '__main__':

    # Имя процесса
    setproctitle.setproctitle('axiom low level communication')

    # Обработчик сигналов SIGTERM, SIGINT
    signal.signal(signal.SIGTERM, hlt.sigterm_handler)
    signal.signal(signal.SIGINT, hlt.sigterm_handler)

    hlt.run()
