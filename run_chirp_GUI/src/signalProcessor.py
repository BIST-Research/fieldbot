import numpy as np
from scipy import signal

class SignalProcessor:
    def __init__(self, fs, nfft, overlap, fbl, fbh, dB_range):
        self.fs = fs
        self.ts = 1 / fs
        self.nfft = nfft
        self.overlap = overlap
        self.fbl = fbl
        self.fbh = fbh
        self.dB_range = dB_range
        self.absolute_scaling = True

        self.spectrum_window = signal.windows.hann(nfft)
        self.freqs = np.fft.rfftfreq(nfft, self.ts)
        self.freq_mask = (self.freqs >= fbl) & (self.freqs <= fbh)
        self.freqs_band = self.freqs[self.freq_mask]

        self.filter_feedforward, self.filter_feedback = signal.butter(4, (fbl, fbh), 'bandpass', fs=fs)
        self.filter_zi = signal.lfilter_zi(self.filter_feedforward, self.filter_feedback)

    def preprocess(self, raw_data):
        data = np.frombuffer(raw_data, np.uint16).astype(np.float32)
        data -= np.mean(data)
        filtered, self.filter_zi = signal.lfilter(
            self.filter_feedforward, self.filter_feedback, data, zi=self.filter_zi
        )
        return filtered

    def reconfigure(self, fbl, fbh, dB_range):
        self.fbl = fbl
        self.fbh = fbh
        self.dB_range = dB_range
        
        self.freq_mask = (self.freqs >= fbl) & (self.freqs <= fbh)
        self.freqs_band = self.freqs[self.freq_mask]
        
        self.filter_feedforward, self.filter_feedback = signal.butter(
            4, (fbl, fbh), 'bandpass', fs=self.fs
        )
        self.filter_zi = signal.lfilter_zi(self.filter_feedforward, self.filter_feedback)

    def compute_signal(self, data):
        return np.arange(len(data)) * self.ts, data

    def compute_spectrogram(self, data):
        freqs, times, spec = signal.spectrogram(
            data,
            fs=self.fs,
            window=self.spectrum_window,
            nperseg=self.nfft,
            noverlap=self.overlap,
            scaling='density',
            mode='psd'
        )
        spec_band = spec[self.freq_mask]
        spec_db = 10 * np.log10(np.maximum(spec_band, 1e-10))

        if self.absolute_scaling:
            max_db = np.max(spec_db)
            spec_db = np.clip(spec_db, max_db - self.dB_range, max_db) - max_db
        else:
            row_max = spec_db.max(axis=1, keepdims=True)
            spec_db = np.clip(spec_db, row_max - self.dB_range, row_max) - row_max

        return spec_db, times

    def compute_fft(self, data):
        fft_window = np.hanning(len(data))
        windowed = data * fft_window
        fft = np.abs(np.fft.rfft(windowed))
        fft_db = 10 * np.log10(fft + 1e-12)

        fft_freqs = np.fft.rfftfreq(len(data), self.ts)
        fft_mask = (fft_freqs >= self.fbl) & (fft_freqs <= self.fbh)
        return fft_freqs[fft_mask], fft_db[fft_mask]
