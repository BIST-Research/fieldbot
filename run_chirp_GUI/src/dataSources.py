import os, serial, time
import numpy as np


# =============== OPCODES ===============
OP_AMP_START = 0xFE
OP_AMP_STOP = 0xFF
OP_START_JOB = 0x10
OP_GET_CHIRP = 0x2F
DO_CHIRP = 0x01
DONT_CHIRP = 0x00
N_SAMPLES = 16000


# =============== I/O INTERFACE ===============
class DataSource:
    def start(self): ...
    def next(self) -> bytes: ...
    def prev(self) -> bytes: ...
    def close(self): ...


# =============== SERIAL I/O ===============
class SerialDataSource(DataSource):
    def __init__(self, port: str, chirp: bytes):
        self.port = port
        self.chirp = chirp
        self.serial = None

    def start(self):
        self.serial = serial.Serial(self.port, 115200, timeout=2)
        self.serial.write([OP_AMP_START])
        self.serial.write([OP_GET_CHIRP])
        self.serial.write(self.chirp)
        self.serial.write([OP_START_JOB, DONT_CHIRP])
        self.serial.read(2 * N_SAMPLES)  # discard
        self.serial.read(2 * N_SAMPLES)  # discard

    def next(self) -> bytes:
        self.serial.write([OP_START_JOB, DO_CHIRP])
        self.serial.read(2 * N_SAMPLES)  # discard
        return self.serial.read(2 * N_SAMPLES)
    
    def prev(self) -> bytes:
        return

    def close(self):
        if self.serial and self.serial.is_open:
            self.serial.write([OP_AMP_STOP])
            self.serial.close()


# =============== FILE I/O ===============
class FileDataSource(DataSource):
    def __init__(self, directory: str):
        self.directory = directory
        self.paths = []
        self.index = 0
        self.empty = True

    def start(self):
        self.paths = [
            os.path.join(self.directory, f)
            for f in sorted(os.listdir(self.directory))
            if f.endswith('.npy')
        ]
        self.empty = len(self.paths) == 0
        self.index = 0
    
    def _slider(self, step):
        if self.empty:
            time.sleep(0.1)
            return bytes()
        print(self.index)
        path = self.paths[self.index]
        self.index = (self.index + step) % len(self.paths)
        data = np.load(path)
        time.sleep(0.1)
        return data.tobytes()

    def next(self) -> bytes:
        return self._slider(1)

    def prev(self) -> bytes:
        return self._slider(-1)

    def close(self):
        pass

class NullDataSource(DataSource):
    def __init__(self):
        pass

    def start(self):
        pass

    def next(self) -> bytes:
        return bytes()
    
    def prev(self) -> bytes:
        return bytes()
    
    def close(self):
        pass