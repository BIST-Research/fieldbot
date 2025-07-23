import numpy as np
import queue
import matplotlib.mlab as mlab
from scipy import signal
from PyQt5.QtCore import QObject, pyqtSignal, QThread
from getData import DataWorker

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
SERIAL_TIMEOUT = 2.0
SERIAL_PORT = "COM4" # CHANGE IF YOU HAVE A TROUBLE CONNECTING



class Backend(QObject):
    new_spectrogram_data = pyqtSignal(np.ndarray, np.ndarray)
    new_signal_data = pyqtSignal(np.ndarray)
    new_fft_data = pyqtSignal(np.ndarray, np.ndarray)
    
    def __init__(self, fbl, fbh, dB_range):
        super().__init__()
        self.fbl = fbl
        self.fbh = fbh
        self.dB_range = dB_range
        self.data_queue = queue.Queue(maxsize=QUEUE_SIZE)
        self.absoluteScaling = True # Set to 0 to scale decibels to max by frequency

        
        # Precomputations
        self.time_vector = np.arange(N_SAMPLES) / FS
        self.precomputed_window = signal.windows.hann(NFFT)
        freqs_full = np.fft.rfftfreq(NFFT, TS)
        self.idx_low = np.searchsorted(freqs_full, fbl)
        self.idx_high = np.searchsorted(freqs_full, fbh)
        self.freqs_band = freqs_full[self.idx_low:self.idx_high]
        self.fft_window = np.hanning(N_SAMPLES)
        self.fft_freqs_full = np.fft.rfftfreq(N_SAMPLES, TS)
        
        # Filter parameters
        self.filter_b, self.filter_a = signal.butter(4, (self.fbl*0.95, self.fbh*1.05), btype='bandpass', fs=FS)
        self.filter_zi = signal.lfilter_zi(self.filter_b, self.filter_a)

        self.chirp_bytes = self.generate_chirp()
        self.dataThreadInit()
    
    def reset(self):
        # Precomputations
        self.time_vector = np.arange(N_SAMPLES) / FS
        self.precomputed_window = signal.windows.hann(NFFT)
        freqs_full = np.fft.rfftfreq(NFFT, TS)
        self.idx_low = np.searchsorted(freqs_full, self.fbl)
        self.idx_high = np.searchsorted(freqs_full, self.fbh)
        self.freqs_band = freqs_full[self.idx_low:self.idx_high]
        
        # Filter parameters
        self.filter_b, self.filter_a = signal.butter(4, (self.fbl*0.95, self.fbh*1.05), btype='bandpass', fs=FS)
        self.filter_zi = signal.lfilter_zi(self.filter_b, self.filter_a)

    def toggleAbsolute(self):
        self.absoluteScaling = not self.absoluteScaling
    
    def stopDataWorker(self):
        self.worker.stop()
    
    def startDataWorker(self):
        self.worker.stop()

    def generate_chirp(self):
        time_vector = np.arange(0, CHIRP_DURATION - TS/2, TS)
        chirp_signal = signal.chirp(
            time_vector, 100e3, CHIRP_DURATION, 30e3, method="linear"
        )
        chirp_biased = np.rint(2048 + 512 * chirp_signal).astype(np.uint16)
        return chirp_biased.tobytes()

    def dataThreadInit(self):
        self.worker = DataWorker(SERIAL_PORT, self.chirp_bytes)
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        
        self.worker.data_ready.connect(self.processData)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        
        self.thread.started.connect(self.worker.run)
        self.thread.start()

    def processData(self, raw_data):
        signal_data = np.frombuffer(raw_data, dtype=np.uint16).astype(np.float32)
    
        count = signal_data.size
        signal_data -= np.sum(signal_data) / (count + (count == 0))

        signal_data, self.filter_zi = signal.lfilter(
            self.filter_b, self.filter_a, signal_data, zi=self.filter_zi
        )

        if self.data_queue.full():
            try:
                self.data_queue.get_nowait()
            except queue.Empty:
                pass
        self.data_queue.put(signal_data[0:])

    def compute(self):
        if not self.data_queue.empty():
            processed_data = self.data_queue.get()
            self.new_signal_data.emit(processed_data)

            spectrum, freqs, times = mlab.specgram(
                processed_data,
                Fs=FS,
                NFFT=NFFT,
                noverlap=OVERLAP,
                window=self.precomputed_window
            )
            
            if spectrum.size == 0:
                return
            
            spectrum_band = spectrum[self.idx_low:self.idx_high]
            np.maximum(spectrum_band, 1e-10, out=spectrum_band)
            np.log10(spectrum_band, out=spectrum_band)
            spectrum_band *= 20
            
            if (self.absoluteScaling):
                max_dB = np.max(spectrum_band)
                np.clip(spectrum_band, max_dB - self.dB_range, max_dB, out=spectrum_band)
                spectrum_band -= max_dB

            else:
                row_max_dB = np.max(spectrum_band, axis=1, keepdims=True)
                np.clip(spectrum_band, row_max_dB - self.dB_range, row_max_dB, out=spectrum_band)
                spectrum_band -= row_max_dB

            self.new_spectrogram_data.emit(spectrum_band, times)
            
            # Compute FFT
            n = len(processed_data)
            if n > 0:
                windowed_data = processed_data * self.fft_window
                fft_result = np.fft.rfft(windowed_data)
                fft_magnitude = np.abs(fft_result)
                freqs_fft = self.fft_freqs_full
                
                # Convert to dB
                fft_db = 20 * np.log10(fft_magnitude + 1e-12)
                
                # Filter to current frequency band
                mask = (freqs_fft >= self.fbl) & (freqs_fft <= self.fbh)
                freqs_band = freqs_fft[mask]
                fft_db_band = fft_db[mask]
                
                self.new_fft_data.emit(freqs_band, fft_db_band)

    def close(self):
        self.worker.running = False
        self.worker.exit_flag.set()
        self.worker.cleanup()
        if self.thread.isRunning():
            self.thread.quit()
            self.thread.wait(2000)
