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
from tkinter import Tk     # from tkinter import Tk for Python 3.x
from tkinter.filedialog import askopenfilename
from scipy.signal import butter, lfilter

Fs = 1E6
Ts = 1/Fs
NFFT = 512
noverlap = 400
#NFFT = 2**9
#noverlap = int(400/512*NFFT)
spec_settings = (Fs, NFFT, noverlap)

DB_range = 40
f_plot_bounds = (30E3, 100E3)

N = 16000
T = N/Fs

T_chirp = 5E-3
f0_chirp = 100E3
f1_chirp = 30E3
#time_offset = int(T_chirp*10E5 + 2000)
time_offset = 8000
offs_chirp = 2048
gain_chirp = 512

T_record = T - T_chirp


N_chirp = int(Fs * T_chirp)
N_record = N - N_chirp

def plot_spec(ax, fig, spec_tup, fbounds = (20E3, 100E3), dB_range = 150, plot_title = 'spec'):
    
    fmin, fmax = fbounds
    s, f, t = spec_tup
    
    lfc = (f >= fmin).argmax()
    s = 20*np.log10(s)
    f_cut = f[lfc:]
    s_cut = s[:][lfc:]

    max_s = np.amax(s_cut)
    s_cut = s_cut - max_s
    
    [rows_s, cols_s] = np.shape(s_cut)
    
    dB = -dB_range
    #for vc in cols_s:
    #    vc = [dB if n < dB else n for n in vc]
    
    for col in range(cols_s):
        for row in range(rows_s):
            if s_cut[row][col] < dB:
                s_cut[row][col] = dB
        
    cf = ax.pcolormesh(t, f_cut, s_cut, cmap='jet', shading='auto')
    cbar = fig.colorbar(cf, ax=ax)
    
    ax.set_ylim(fmin, fmax)
    ax.set_ylabel('Frequency (Hz)')
    ax.set_xlabel('Time (sec)')
    ax.title.set_text(plot_title)


    cbar.ax.set_ylabel('dB')


def autocorr(unraw, chirp, min_dist=None):


    xcor = signal.correlate(unraw, chirp, mode='same', method='auto')
    xcor = np.abs(xcor)/np.max(xcor)
    
    primary_height = 0.4
    
    peaks, apeaks = signal.find_peaks(
        xcor, 
        height=primary_height, 
        prominence=[0.9, 2.0], 
        distance = min_dist
    )
    
    return xcor, peaks
    
    
def plotcorr(xcorr, peaks, ax, plot_title='xcorr', xprange=None):
    
    ax.plot(xcorr)
    ax.plot(peaks, xcorr[peaks], "x")
    ax.set_ylabel('Amplitude')
    ax.set_xlabel('Time (sec)')
    ax.title.set_text(plot_title)


def plot_sig(ax, fig, sig):
    t = np.arange(0, len(sig))/Fs
    cf = ax.plot(t, sig)
    ax.set_ylabel('Signal')
    ax.set_xlabel('Time (sec)')
    ax.set_xlim(0, np.max(t))


     
def process(raw, spec_settings, time_offs = 0):

    unraw = [((y << 8) | x) for x, y in zip(raw[::2], raw[1::2])]
    unraw_balanced = unraw - np.mean(unraw)
    
    pt_cut = unraw_balanced[time_offs:]
    remainder = unraw_balanced[:time_offs]
    
    Fs, NFFT, noverlap = spec_settings
    spec_tup = mlab.specgram(pt_cut, Fs=Fs, NFFT=NFFT, noverlap=noverlap)
    
    return spec_tup, pt_cut, remainder
    
def high_pass(sig, lowcut, highcut, Fs, order = 5):
    b, a = butter(order, [lowcut, highcut], fs = Fs, btype = 'bandpass')
    filt_sig = lfilter(b, a, sig)
    return filt_sig
