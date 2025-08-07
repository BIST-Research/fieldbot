import pyqtgraph as pg

CMAP = [
            (0.0, (0, 0, 127, 255)),
            (0.25, (0, 0, 255, 255)),
            (0.5, (0, 255, 255, 255)),
            (0.75, (255, 255, 0, 255)),
            (1.0, (255, 0, 0, 255))
        ]

class Spectrogram(pg.PlotWidget):
    def __init__(self, fbl, fbh, dB_range):
        super().__init__()
        self.setLabel("left", "Frequency", "Hz")
        self.setLabel("bottom", "Time", "s")
        self.setYRange(fbl, fbh)

        self.fbl = fbl
        self.fbh = fbh
        self.dB_range = dB_range
        
        self.spectrogramImage = pg.ImageItem()
        self.addItem(self.spectrogramImage)
        
        # Color settings
        self.hist = pg.HistogramLUTItem()
        self.hist.setImageItem(self.spectrogramImage)
        self.hist.setLevels(-dB_range, 0)
        self.hist.autoHistogramRange = False
        self.hist.gradient.restoreState({
            "mode": "rgb",
            "ticks": CMAP,
        })

    def update(self, spectrum_band, times):
        self.spectrogramImage.setImage(
            spectrum_band.T, 
            levels=(-self.dB_range, -3),
            autoLevels=False
        )
        self.spectrogramImage.setRect(pg.QtCore.QRectF(
            times[0], self.fbl,
            times[-1] - times[0],
            self.fbh - self.fbl
        ))

        # self.getViewBox().setLimits(
        #     xMin=times[0], 
        #     xMax=times[-1]*1.05,
        #     yMin=self.fbl*0.95,
        #     yMax=self.fbh*1.05
        # )