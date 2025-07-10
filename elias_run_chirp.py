import numpy as np
import serial
import sys
import pyqtgraph as pg
from pyqtgraph.Qt import QtCore, QtWidgets
from scipy import signal
import matplotlib.mlab as mlab
import threading
import queue

# For debugging
# import time






# =============
#   CONSTANTS
# =============
FS = 1e6
TS = 1 / FS
N_SAMPLES = 16000
CHIRP_DURATION = 3e-3
SAMPLES_PER_CHIRP = int(FS * CHIRP_DURATION)
NFFT = 512
OVERLAP = 400


QUEUE_SIZE = 2




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





# ===================================
#   THREADING FOR DATA ACQUISITION
# ===================================
#
# The response from the sonar board takes about 120 ms,
# so we don't want to wait for it. Hence threading.
#
class DataWorker(QtCore.QObject):
    data_ready = QtCore.pyqtSignal(bytes)
    finished = QtCore.pyqtSignal()

    def __init__(self, serial_port):
        super().__init__()
        self.serial = serial_port
        self.running = True
        self.lock = threading.Lock()
        self.exit_flag = threading.Event()

    def getData(self):
        with self.lock:
            if self.exit_flag.is_set():
                return None
            self.serial.write([OP_START_JOB, DO_CHIRP])
            self.serial.read(2 * N_SAMPLES)  # Discard first buffer
            return self.serial.read(2 * N_SAMPLES)

    def run(self):
        while self.running and not self.exit_flag.is_set():
            raw_data = self.getData()
            self.data_ready.emit(raw_data)
        self.finished.emit()


# ==================
#   DRAWING THE UI
# ==================
class Spectrogram(QtWidgets.QMainWindow):
    def __init__(self, fname, offset, fbl, fbh, dB_range):
        super().__init__()
        self.serial = serial.Serial("/dev/ttyACM0", 115200)
        self.fname = fname
        self.offset = offset
        self.fbl = fbl
        self.fbh = fbh
        self.dB_range = dB_range
        self.data_queue = queue.Queue(maxsize=QUEUE_SIZE)
        

        # Precomputations
        self.time_vector = np.arange(N_SAMPLES - offset) / FS
        self.precomputed_window = signal.windows.hann(NFFT)
        freqs_full = np.fft.rfftfreq(NFFT, TS)
        self.idx_low = np.searchsorted(freqs_full, fbl)
        self.idx_high = np.searchsorted(freqs_full, fbh)
        self.freqs_band = freqs_full[self.idx_low:self.idx_high]
        
        # Takeoff
        self.UIInit()
        self.chirpInit()
        self.ampInit()
        self.dataThreadInit()

    def UIInit(self):
        self.setWindowTitle("Spectrogram")
        self.resize(1200, 800)

        central_widget = QtWidgets.QWidget()
        self.setCentralWidget(central_widget)
        layout = QtWidgets.QVBoxLayout(central_widget)

        # Spectrogram
        self.spec_plot = pg.PlotWidget(title="Spectrogram")
        self.spec_plot.setLabel("left", "Frequency", "Hz")
        self.spec_plot.setLabel("bottom", "Time", "s")
        self.spec_plot.setYRange(self.fbl, self.fbh)
        layout.addWidget(self.spec_plot, 70)
        self.spec_img = pg.ImageItem()
        self.spec_plot.addItem(self.spec_img)

        # Signal
        self.signal_plot = pg.PlotWidget(title="Signal")
        self.signal_plot.setLabel("left", "Amplitude")
        self.signal_plot.setLabel("bottom", "Time", "s")
        layout.addWidget(self.signal_plot, 30)
        self.signal_curve = self.signal_plot.plot(pen="y")
        
        # Colors
        self.hist = pg.HistogramLUTItem()
        self.hist.setImageItem(self.spec_img)
        self.hist.setLevels(-self.dB_range, 0)
        self.hist.autoHistogramRange = False

        # TODO: Replace this with a lookup table of sorts???
        self.hist.gradient.restoreState({
            "mode": "rgb",
            "ticks": [
                (0.0, (0, 0, 127, 255)),
                (0.25, (0, 0, 255, 255)),
                (0.5, (0, 255, 255, 255)),
                (0.75, (255, 255, 0, 255)),
                (1.0, (255, 0, 0, 255)),
            ],
        })
    
    def chirpInit(self):
        time_vector = np.arange(0, CHIRP_DURATION - TS/2, TS)
        chirp_signal = signal.chirp(
            time_vector, 100e3, CHIRP_DURATION, 30e3, method="linear"
        )
        chirp_biased = np.rint(2048 + 512 * chirp_signal).astype(np.uint16)
        self.chirp_bytes = chirp_biased.tobytes()

    def ampInit(self):
        self.serial.write([OP_AMP_START])
        self.serial.write([OP_GET_CHIRP])
        self.serial.write(self.chirp_bytes)
        self.serial.write([OP_START_JOB, DONT_CHIRP])
        self.serial.read(2 * N_SAMPLES)  # Discard initial buffers
        self.serial.read(2 * N_SAMPLES)

    def dataThreadInit(self):
        self.worker = DataWorker(self.serial)
        self.thread = QtCore.QThread()
        self.worker.moveToThread(self.thread)
        
        self.worker.data_ready.connect(self.processData)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        
        self.thread.start()

    def processData(self, raw_data):
        signal_data = np.frombuffer(raw_data, dtype=np.uint16).astype(np.float32)
        signal_data -= np.mean(signal_data)
        if self.data_queue.full():
            self.data_queue.get_nowait()
        self.data_queue.put(signal_data[self.offset:])

    def upd(self):
        if not self.data_queue.empty():
            processed_data = self.data_queue.get()
            self.signal_curve.setData(self.time_vector, processed_data)

            spectrum, freqs, times = mlab.specgram(
                processed_data,
                Fs=FS,
                NFFT=NFFT,
                noverlap=OVERLAP,
                window=self.precomputed_window
            )
            
            spectrum_band = spectrum[self.idx_low:self.idx_high]
            
            np.maximum(spectrum_band, 1e-10, out=spectrum_band)
            np.log10(spectrum_band, out=spectrum_band)
            spectrum_band *= 20
            
            max_dB = np.max(spectrum_band)
            np.clip(spectrum_band, max_dB - self.dB_range, max_dB, out=spectrum_band)
            spectrum_band -= max_dB

            # Upd image
            self.spec_img.setImage(
                spectrum_band       .T, 
                levels=(-self.dB_range, 0),
                autoLevels=False
            )
            self.spec_img.setRect(QtCore.QRectF(
                times[0], self.fbl,
                times[-1] - times[0],
                self.fbh - self.fbl
            ))

    def closeEvent(self, event):
        self.worker.exit_flag.set()
        self.worker.running = False
        self.thread.quit()
        # self.thread.wait(2000)
        self.serial.write([OP_AMP_STOP])
        self.serial.close()
        event.accept()





# =================================
#   ENTRY POINT AND PARAM PARSING
# =================================
def main():
    fname = str(sys.argv[1])
    offset = int(sys.argv[2])
    fbl = 1000 * int(sys.argv[3])
    fbh = 1000 * int(sys.argv[4])
    dB_range = int(sys.argv[5]) / 2

    app = QtWidgets.QApplication([])
    window = Spectrogram(fname, offset, fbl, fbh, dB_range)
    window.show()
    
    # Timer
    timer = QtCore.QTimer()
    timer.timeout.connect(window.upd)
    timer.start(20)
    
    app.exec_()


if __name__ == "__main__":
    main()