import pyqtgraph as pg
import numpy as np

CMAP = [
            (0.0, (0, 0, 127, 255)),
            (0.25, (0, 0, 255, 255)),
            (0.5, (0, 255, 255, 255)),
            (0.75, (255, 255, 0, 255)),
            (1.0, (255, 0, 0, 255))
        ]

class dBScale(pg.PlotWidget):
    def __init__(self, dB_range):
        super().__init__()
        self.dB_range = dB_range
        
        self.setMaximumWidth(100)
        self.hideAxis('bottom')
        self.showAxis('right')
        self.setYRange(-dB_range, -3)
        self.setLabel('left', 'strength', 'dB')
        
        gradient = np.linspace(0, 1, 256).reshape(1, -1)
        self.img = pg.ImageItem(gradient)
        self.addItem(self.img)
        self.img.setRect(0, -dB_range, 1, -3 + dB_range)

        
        colormap = pg.ColorMap(*zip(*CMAP))
        self.img.setLookupTable(colormap.getLookupTable())