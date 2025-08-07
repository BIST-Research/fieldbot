import os, time, queue, threading
import numpy as np

class DataSaver(threading.Thread):
    def __init__(self):
        super().__init__()
        self.daemon = True
        self._queue = queue.Queue()
        self._stop = threading.Event()
        self._counter = 0

        self.saving = False
        self.directory = ""
        self.counter = 0
        self.interval = 20

    def run(self):
        while not self._stop.is_set():
            try:
                data = self._queue.get(timeout=0.5)
                filename = time.strftime(f"raw_%Y%m%d_%H%M%S_{self._counter:05d}.npy")
                path = os.path.join(self.directory, filename)
                np.save(path, data)
                self._counter += 1
            except queue.Empty:
                continue
    
    # def isSaving(self):
    #     return self.saving

    def enqueue(self, data):
        if self.counter % self.interval == 0:
            self.counter = 0
            self._queue.put(data)
        self.counter += 1
        
    def stop(self):
        self._stop.set()
        self.join()