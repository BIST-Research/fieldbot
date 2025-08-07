import pyqtgraph as pg
import numpy as np

class FFT(pg.PlotWidget):
    def __init__(self, fbl, fbh):
        super().__init__()
        self.setLabel("left", "Magnitude", "dB")
        self.setLabel("bottom", "Frequency", "Hz")
        self.curve = self.plot(pen="c")
        self.fbl = fbl
        self.fbh = fbh
        
    def update(self, freqs, magnitudes):
        self.curve.setData(freqs, magnitudes)
        self.getViewBox().setLimits(
            xMin=self.fbl*0.95,
            xMax=self.fbh*1.05,
            yMin=0,
            yMax=np.max(magnitudes)*1.05
        )