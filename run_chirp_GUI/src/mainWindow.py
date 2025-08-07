import numpy as np

from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout
from src.widgets.spectrogram import Spectrogram
from src.widgets.signal import Signal
from src.widgets.dBScale import dBScale
from src.widgets.fft import FFT
from src.widgets.controlPanel import ControlPanel

from src.signalProcessor import SignalProcessor


FS = 1e6
TS = 1 / FS
NFFT = 512
OVERLAP = 400

class MainWindow(QMainWindow):
    def __init__(self, fbl, fbh, dB_range, saveCycles, fname):
        super().__init__()
        self.setWindowTitle("Run Chirp Provisional GUI")
        self.resize(1200, 800)

        self._currentData = bytes(int(1e6))

        self.central = QWidget()
        self.setCentralWidget(self.central)
        layout = QVBoxLayout(self.central)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)

        self.control_panel = ControlPanel({
            "fname": fname,
            "saveCycles": saveCycles,
            "fbl": fbl,
            "fbh": fbh,
            "dB_range": dB_range
        })
        layout.addWidget(self.control_panel)

        spectrogram_container = QWidget()
        spectrogram_lyt = QHBoxLayout(spectrogram_container)
        spectrogram_lyt.setContentsMargins(0, 0, 0, 0)
        spectrogram_lyt.setSpacing(0)
        self.spectrogram = Spectrogram(fbl, fbh, dB_range)
        self.dB_scale = dBScale(dB_range)
        spectrogram_lyt.addWidget(self.spectrogram, 90)
        spectrogram_lyt.addWidget(self.dB_scale, 10)

        signal_container = QWidget()
        signal_lyt = QHBoxLayout(signal_container)
        signal_lyt.setContentsMargins(0, 0, 0, 0)
        signal_lyt.setSpacing(0)
        self.signal = Signal()
        self.fft = FFT(fbl, fbh)
        signal_lyt.addWidget(self.signal, 80)
        signal_lyt.addWidget(self.fft, 20)

        layout.addWidget(spectrogram_container, 70)
        layout.addWidget(signal_container, 30)

        self.processor = SignalProcessor(
            fs=FS,
            nfft=NFFT,
            overlap=OVERLAP,
            fbl=fbl,
            fbh=fbh,
            dB_range=dB_range
        )

    def update(self, data: bytes):
        self._currentData = data

        filtered = self.processor.preprocess(np.frombuffer(data, dtype=np.uint16))

        self.signal.update(*self.processor.compute_signal(filtered))
        self.fft.update(*self.processor.compute_fft(filtered))
        self.spectrogram.update(*self.processor.compute_spectrogram(filtered))
    
    def reconfigure(self):
        self.processor.reconfigure(self.fbl, self.fbh, self.dB_range)
        self.update(self._currentData)

