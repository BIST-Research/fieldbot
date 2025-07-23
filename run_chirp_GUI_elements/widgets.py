import pyqtgraph as pg
import numpy as np

# ==============
#   PARAMETERS
# ==============
MIN_DECIBELS = -3
CMAP = [
            (0.0, (0, 0, 127, 255)),
            (0.25, (0, 0, 255, 255)),
            (0.5, (0, 255, 255, 255)),
            (0.75, (255, 255, 0, 255)),
            (1.0, (255, 0, 0, 255))
        ]

# =======================
#   SPECTROGRAM WIDGET
# =======================
class Spectrogram(pg.PlotWidget):
    def __init__(self, fbl, fbh, dB_range):
        super().__init__()
        self.setLabel("left", "Frequency", "Hz")
        self.setLabel("bottom", "Time", "s")
        self.setYRange(fbl, fbh)

        self.fbl = fbl
        self.fbh = fbh
        self.dB_range = dB_range
        
        self.image_item = pg.ImageItem()
        self.addItem(self.image_item)
        
        # Color settings
        self.hist = pg.HistogramLUTItem()
        self.hist.setImageItem(self.image_item)
        self.hist.setLevels(-dB_range, 0)
        self.hist.autoHistogramRange = False
        self.hist.gradient.restoreState({
            "mode": "rgb",
            "ticks": CMAP,
        })

    def update_spectrogram(self, spectrum_band, times):
        self.image_item.setImage(
            spectrum_band.T, 
            levels=(-self.dB_range, -3),
            autoLevels=False
        )
        self.image_item.setRect(pg.QtCore.QRectF(
            times[0], self.fbl,
            times[-1] - times[0],
            self.fbh - self.fbl
        ))

# =======================
#      SIGNAL WIDGET
# =======================
class Signal(pg.PlotWidget):
    def __init__(self):
        super().__init__()
        self.setLabel("left", "Amplitude")
        self.setLabel("bottom", "Time", "s")
        self.curve = self.plot(pen="y")

    def update_signal(self, time_vector, data):
        self.curve.setData(time_vector, data)

# ===================
#   DB SCALE WIDGET
# ===================
class dBScale(pg.PlotWidget):
    def __init__(self, dB_range):
        super().__init__()
        self.dB_range = dB_range
        
        self.setMaximumWidth(100)
        self.hideAxis('bottom')
        self.showAxis('right')
        self.setYRange(-dB_range, MIN_DECIBELS)
        self.setLabel('left', 'strength', 'dB')
        
        gradient = np.linspace(0, 1, 256).reshape(1, -1)
        self.img = pg.ImageItem(gradient)
        self.addItem(self.img)
        self.img.setRect(0, -dB_range, 1, MIN_DECIBELS + dB_range)

        
        colormap = pg.ColorMap(*zip(*CMAP))
        self.img.setLookupTable(colormap.getLookupTable())

class FFTWidget(pg.PlotWidget):
    def __init__(self):
        super().__init__()
        self.setLabel("left", "Magnitude", "dB")
        self.setLabel("bottom", "Frequency", "Hz")
        self.curve = self.plot(pen="c")
        self.setBackground("k")
        self.setLogMode(x=False, y=False)
        self.set_freq_range(0, 24000)  # Default range
        
    def update_fft(self, freqs, magnitudes):
        self.curve.setData(freqs, magnitudes)
        
    def set_freq_range(self, f_low, f_high):
        self.setXRange(f_low, f_high)
