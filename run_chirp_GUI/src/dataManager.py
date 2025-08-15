import numpy as np
from collections import deque
from PyQt5.QtCore import QObject, pyqtSignal, QTimer

from src.dataWorker import DataWorker
from src.dataSources import SerialDataSource, FileDataSource, NullDataSource
from src.dataSaver import DataSaver

# Chirp Generation
FS = 1e6
TS = 1/FS
N_SAMPLES = 16000
CHIRP_DURATION = 3e-3
SAMPLES_PER_CHIRP = int(FS * CHIRP_DURATION)

QUEUE_SIZE = 10
TIMER_SPEED = 20 # ms

class DataManager(QObject):
    dataReady = pyqtSignal(bytes)

    def __init__(self):
        super().__init__()
        self.queue = deque(maxlen=QUEUE_SIZE)
        self.data = None

        # Data thread
        self.worker = DataWorker(callback=self._storeData)
        self.worker.start()

        # Saver thread
        self.saver = DataSaver()
        self.saver.start()

        # Timer
        self.timer = QTimer()
        self.timer.timeout.connect(self.compute)
        self.timer.start(TIMER_SPEED)

        # Serial setup
        try:
            self._serial_source = SerialDataSource("COM22", self._generateChirp())
            self.worker.load(self._serial_source)
        except:
            self._serial_source = NullDataSource()
            self.worker.load(self._serial_source)

    def _generateChirp(self):
        t = np.arange(0, CHIRP_DURATION, TS)
        chirp = np.cos(2 * np.pi * (100e3 * t + (30e3 - 100e3) / (2 * CHIRP_DURATION) * t**2))
        return np.rint(2048 + 512 * chirp).astype(np.uint16).tobytes()

    def _storeData(self, data):
        self.data = data
        if len(self.queue) >= self.queue.maxlen:
            self.queue.popleft()
        self.queue.append(data)

    def compute(self):
        if not self.queue:
            return

        self.data = self.queue.popleft()

        self.dataReady.emit(self.data)

        if self.saver.saving:
            raw_array = np.frombuffer(self.data, dtype=np.uint16)
            self.saver.enqueue(raw_array.copy())

        return self.data

    # ====================
    #   Public interface
    # ====================
    def pause(self):
        self.worker.paused = True

    def next(self):
        if self.worker.paused:
            self.save_counter = 0
            self.worker.next()

    def prev(self):
        if self.worker.paused:
            self.save_counter = 0
            self.worker.prev()


    def resume(self):
        self.worker.paused = False

    def save(self, interval, directory):
        self.saver.interval = interval
        self.saver.directory = directory
        self.saver.counter = 0
        self.saver.saving = True

        if self.data is not None:
            self.saver.enqueue(np.frombuffer(self.data, dtype=np.uint16))

    def unsave(self):
        self.saver.saving = False

    def load(self, directory):
        self.saver.saving = False
        self.worker.load(FileDataSource(directory))

    def unload(self):
        self.worker.load(self._serial_source)

    def close(self):
        self.worker.stop()
        self.saver.stop()
