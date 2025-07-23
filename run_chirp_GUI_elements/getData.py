import serial
import threading
from PyQt5.QtCore import QObject, pyqtSignal

# =============
#    OPCODES
# =============
OP_AMP_START = 0xFE
OP_AMP_STOP = 0xFF
OP_START_JOB = 0x10
OP_GET_CHIRP = 0x2F
OP_CHIRP_EN = 0x2E
DO_CHIRP = 0x01
DONT_CHIRP = 0x00

N_SAMPLES = 16000



class DataWorker(QObject):
    data_ready = pyqtSignal(bytes)
    finished = pyqtSignal()

    def __init__(self, port, chirp_bytes):
        super().__init__()
        self.port = port
        self.chirp_bytes = chirp_bytes
        self.running = True
        self.exit_flag = threading.Event()
        self.serial = None

    def setup_serial(self):
        self.serial = serial.Serial(
            self.port, 
            115200,
            timeout=2000
        )
        self.serial.write([OP_AMP_START])
        self.serial.write([OP_GET_CHIRP])
        self.serial.write(self.chirp_bytes)
        self.serial.write([OP_START_JOB, DONT_CHIRP])
        
        # Discard initial buffers
        self.serial.read(2 * N_SAMPLES)
        self.serial.read(2 * N_SAMPLES)
        return True

    def get_data(self):
        try:
            if self.exit_flag.is_set():
                return

            self.serial.write([OP_START_JOB, DO_CHIRP])

            # Discard first buffer
            self.serial.read(2 * N_SAMPLES)
            return self.serial.read(2 * N_SAMPLES)
        except:
            return

    def cleanup(self):
        if self.serial and self.serial.is_open:
            try:
                self.serial.write([OP_AMP_STOP])
                self.serial.close()
            except:
                pass

    def run(self):
        if not self.setup_serial():
            self.finished.emit()
            return

        while self.running and not self.exit_flag.is_set():
            raw_data = self.get_data()
            if raw_data is not None:
                self.data_ready.emit(raw_data)
            elif self.exit_flag.is_set():
                break
        self.cleanup()
        self.finished.emit()

    def stop(self):
        self.running = False

    def start(self):
        self.running = True