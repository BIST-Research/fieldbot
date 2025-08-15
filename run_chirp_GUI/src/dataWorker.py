import time, threading

class DataWorker(threading.Thread):
    def __init__(self, callback=None):
        super().__init__(daemon=True)
        self.running = False
        self.paused = True
        self.source = None
        self._lock = threading.Lock()
        self.callback = callback

    def run(self):
        self.running = True
        while self.running:
            if self.paused:
                time.sleep(0.01)
                continue

            with self._lock:
                source = self.source
                if not source:
                    time.sleep(0.01)
                    continue

                data = source.next()

            if data and self.callback:
                self.callback(data)
            else:
                time.sleep(0.01)

    def next(self):
        with self._lock: source = self.source
        if not source: return
        data = source.next()
        if data and self.callback:
            self.callback(data)

    def prev(self):
        with self._lock: source = self.source
        if not source: return
        data = source.prev()
        if data and self.callback:
            self.callback(data)

    def stop(self):
        self.running = False
        self.join(timeout=0.5)
        with self._lock:
            if self.source:
                self.source.close()

    def load(self, source):
        with self._lock:
            if self.source: self.source.close()
            self.source = source
            if self.source: self.source.start()
