import pyqtgraph as pg
import numpy as np

class Signal(pg.PlotWidget):
    def __init__(self):
        super().__init__()
        self.setLabel("left", "Amplitude")
        self.setLabel("bottom", "Time", "s")
        self.curve = self.plot(pen="y")

    def update(self, time_vector, data):
        self.curve.setData(time_vector, data)
        self.getViewBox().setLimits(
            xMin=time_vector[0],
            xMax=time_vector[-1]*1.05,
            yMin=np.min(data)*0.95,
            yMax=np.max(data)*1.05
        )