import numpy as np
import serial
import serial.tools.list_ports
import time
import math
import os
import matplotlib.pyplot as plt
import numpy as np
import matplotlib.mlab as mlab
import matplotlib.colors as colors
from scipy import signal
from datetime import datetime
import glob
from scipy.signal import butter, lfilter

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
from PyQt5.QtWidgets import QMainWindow, QApplication, QWidget, QTabWidget, QVBoxLayout
import matplotlib.pyplot as plt
import sys
import random


from plot_utils import plot_spec, high_pass, process, plot_sig


class plotWindow():
    def __init__(self, parent=None):
        self.app = QApplication(sys.argv)
        self.MainWindow = QMainWindow()
        self.MainWindow.__init__()
        self.MainWindow.setWindowTitle("Specs")
        self.canvases = []
        self.figure_handles = []
        self.toolbar_handles = []
        self.tab_handles = []
        self.current_window = -1
        self.tabs = QTabWidget()
        self.MainWindow.setCentralWidget(self.tabs)
        #self.MainWindow.resize(1280, 900)
        self.MainWindow.resize(1300, 600)
        self.MainWindow.show()

    def addPlot(self, title, figure):
        new_tab = QWidget()
        layout = QVBoxLayout()
        new_tab.setLayout(layout)

        #figure.subplots_adjust(left=0.05, right=0.99, bottom=0.05, top=0.91, wspace=0.2, hspace=0.2)
        figure.subplots_adjust(left=0.1,
                    bottom=0.1,
                    right=0.9,
                    top=0.9,
                    wspace=0.4,
                    hspace=0.4)
        new_canvas = FigureCanvas(figure)
        new_toolbar = NavigationToolbar(new_canvas, new_tab)

        layout.addWidget(new_canvas)
        layout.addWidget(new_toolbar)
        self.tabs.addTab(new_tab, title)

        self.toolbar_handles.append(new_toolbar)
        self.canvases.append(new_canvas)
        self.figure_handles.append(figure)
        self.tab_handles.append(new_tab)

    def show(self):
        self.app.exec_()


Fs = 1E6
Ts = 1/Fs
NFFT = 512
noverlap = 400
#NFFT = 2**9
#noverlap = int(400/512*NFFT)
spec_settings = (Fs, NFFT, noverlap)

DB_range = 40
f_plot_bounds = (25E3, 100E3)

N = 16000
T = N/Fs

T_chirp = 5E-3
f0_chirp = 100E3
f1_chirp = 30E3
#time_offset = int(T_chirp*10E5 + 2000)
time_offset = 5000
offs_chirp = 2048
gain_chirp = 512

T_record = T - T_chirp


N_chirp = int(Fs * T_chirp)
N_record = N - N_chirp

if __name__ == '__main__':

    pw = plotWindow()

    fdir = 'data/nrl_path1_test1'
    
    nplots = 25
    fnames = [np_name for np_name in glob.glob(f'{fdir}/*.np[yz]')]
    
    pltis = random.sample(range(len(fnames)), nplots)

    nplist = ([], [])
    for i in pltis:
        with open(f'{fnames[i]}', 'rb') as fd:

            fig, ax = plt.subplots(nrows = 2, figsize = (9, 7))
            
            s1, pr1, pc1 = process(bytearray(np.load(fd)), spec_settings, time_offset)
            s2, pr2, pc2 = process(bytearray(np.load(fd)), spec_settings, time_offset)

            #filtd1 = high_pass(pr1, 30E3, 75E3, Fs, 7)
            plot_spec(ax[0], fig, s1, fbounds = f_plot_bounds, dB_range = 40, plot_title = 'With ear')
            #plot_sig(ax[0], fig, filtd1)
            
            #filtd2 = high_pass(pr2, 30E3, 75E3, Fs, 7)
            plot_spec(ax[1], fig, s2, fbounds = f_plot_bounds, dB_range = 40, plot_title = 'Without ear')
            #plot_sig(ax[1], fig, filtd2)

            pw.addPlot("spec", fig)

    pw.show()


            
            

    #print(fnames)

    
    

