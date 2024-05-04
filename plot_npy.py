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


     
def process(raw, N_chirp, spec_settings, time_offs = 0):


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


T_chirp = 3E-3
f0_chirp = 100E3
f1_chirp = 30E3
#time_offset = int(T_chirp*10E5 + 500)
time_offset = 8000
#time_offset = 0
offs_chirp = 2048
gain_chirp = 512


T_record = T - T_chirp


N_chirp = int(Fs * T_chirp)
N_record = N - N_chirp


#print(f"T={T}\t T_record={T_record}\t N_chirp={N_chirp}\t N_record={N_record}")


assert N_chirp + N_record == N
assert T_chirp + T_record == T


# create chirp time vector
t0_chirp = 0
t1_chirp = T_chirp - Ts/2
tv_chirp = np.arange(t0_chirp, t1_chirp, Ts)


# create chirp
chirp = signal.chirp(tv_chirp, f0_chirp, T_chirp, f1_chirp, method='linear')
window = signal.windows.hann(N_chirp, False)


# bias chirp into range that DAC can output
#chirp_biased = (np.rint((4096/2)*(1 + window*chirp))).astype(int)
chirp_biased = (np.rint(offs_chirp + gain_chirp*chirp)).astype(int)


cbias = chirp_biased.tolist()


ft_chirp = lambda t: f0_chirp + (f1_chirp - f0_chirp) * t / t1_chirp
fN_chirp = lambda N: ft_chirp(N/Fs)


dist2samples = lambda d: (d/343) * Fs


min_distance = 1
max_distance = 3


byterr = bytearray()
for num in cbias:
    b = num.to_bytes(2)
    byterr.append(b[1])
    byterr.append(b[0])
        
# verify chirp on spectrogram
#fig_chirp, ax_chirp = plt.subplots(nrows=1)
#ax_chirp.plot(chirp_biased)
#ax_chirp.specgram(chirp, Fs=Fs, NFFT=NFFT, noverlap=noverlap, cmap='jet')
#ax_chirp.set_ylim(0, 500E3)
#plt.show(block=True)


# Establish serial
#baud = 115200
#sercom = serial.Serial("/dev/sonar", baud)


# define opcodes
OP_AMP_START = 0xfe
OP_AMP_STOP = 0xff
OP_START_JOB = 0x10
OP_GET_CHIRP = 0x2f
OP_CHIRP_EN = 0x2e
DO_CHIRP = 0x01
DONT_CHIRP = 0x00


# send chirp data
#[print(n) for n in chirp_biased]


# send amp start
#sercom.write([OP_AMP_START])


# Give MCU chirp data
#sercom.write([OP_GET_CHIRP])
#sercom.write(byterr)


# Flush out ADCs
#sercom.write([OP_START_JOB, DONT_CHIRP])
#sercom.read(2*N)
#sercom.read(2*N)


# send start run, chirp enabled
#sercom.write([OP_START_JOB, DO_CHIRP])


# read and unpack echo data
#raw1 = sercom.read(2 * N)
#raw2 = sercom.read(2 * N)


Tk().withdraw() # we don't want a full GUI, so keep the root window from appearing
filename = askopenfilename(initialdir = (r"C:\Users\adamh\OneDrive - Virginia Tech\Desktop\BatLab\Sonar Localization\Field Rig\fieldbot-vehicle"))
print(filename)


with open(filename, 'rb') as fd:
    raw1 = bytearray(np.load(fd))
    raw2 = bytearray(np.load(fd))




fig_spec, ax_spec = plt.subplots(nrows=2, figsize=(9,7))


plt.subplots_adjust(left=0.1,
                    bottom=0.1,
                    right=0.9,
                    top=0.9,
                    wspace=0.4,
                    hspace=0.4)
                    
#plt.tight_layout()


#N_adj = N_chirp + 3000
#N_remainder = N - N_adj


## process the raw binary data
spec_tup1, pt_cut1, pt1 = process(raw1, N_chirp, spec_settings, time_offs=time_offset)
spec_tup2, pt_cut2, pt2 = process(raw2, N_chirp, spec_settings, time_offs=time_offset)


## choose which plots to make (spec and time = "time", spec and xcorr = "xcorr")
plot_options = "time"


if (plot_options == "time"):
    ## do this 
    fig_1, ax_1 = plt.subplots(nrows = 2, figsize = (9, 7))
    plt.subplots_adjust(left=0.1,
                    bottom=0.1,
                    right=0.9,
                    top=0.9,
                    wspace=0.4,
                    hspace=0.4)
    fig_1.suptitle("With Ear")
    spec_tup1, pt_cut1, pt1 = process(raw1, N_chirp, spec_settings, time_offs=time_offset)
    filt_pt_cut1 = high_pass(pt_cut1, 30E3, 75E3, Fs, 7)


    plot_spec(ax_1[0], fig_1, spec_tup1, fbounds = f_plot_bounds, dB_range = DB_range, plot_title='spectrogram')
    plot_sig(ax_1[1], fig_1, filt_pt_cut1)
    
    fig_2, ax_2 = plt.subplots(nrows = 2, figsize = (9, 7))
    plt.subplots_adjust(left=0.1,
                    bottom=0.1,
                    right=0.9,
                    top=0.9,
                    wspace=0.4,
                    hspace=0.4)
    fig_2.suptitle("Without Ear")
    spec_tup2, pt_cut2, pt2 = process(raw2, N_chirp, spec_settings, time_offs=time_offset)
    filt_pt_cut2 = high_pass(pt_cut2, 30E3, 75E3, Fs, 7)


    plot_spec(ax_2[0], fig_2, spec_tup2, fbounds = f_plot_bounds, dB_range = DB_range, plot_title='spectrogram')
    plot_sig(ax_2[1], fig_2, filt_pt_cut2)
elif (plot_options == "xcorr"):
    plot_spec(ax_spec[0], fig_spec, spec_tup1, fbounds = f_plot_bounds, dB_range = DB_range, plot_title='Left')


    #xcor1 = signal.correlate(pt_cut1, chirp, mode='same', method='auto')
    #vv = np.linspace(0, 0.023, num=22000)
    #ax_spec_1[0].plot(vv, pt_cut1)
    #ax_spec_1[2].plot(vv, xcor1)


    plot_spec(ax_spec[1], fig_spec, spec_tup2, fbounds = f_plot_bounds, dB_range = DB_range, plot_title='Right')


    fig_xcorr, ax_xcorr = plt.subplots(nrows=2, figsize=(9,7))


    mindist = 2*dist2samples(min_distance)


    xcor1, peaks1 = autocorr(pt_cut1, chirp, min_dist=mindist)
    xcor2, peaks2 = autocorr(pt_cut2, chirp, min_dist=mindist)


    fpeak1 = np.round(fN_chirp(peaks1[0]), decimals=-1).astype(np.int64)
    fpeak2 = np.round(fN_chirp(peaks2[0]), decimals=-1).astype(np.int64)


    print(f"{fpeak1}, {fpeak2}")
    print(f"{peaks1}, {peaks2}")


    xcor_tvec = np.linspace(0, N_remainder/Fs, N_remainder)


    plotcorr(xcor1, peaks1, ax_xcorr[0], plot_title='Left')
    plotcorr(xcor2, peaks2, ax_xcorr[1], plot_title='Right')


    ax_spec[0].plot(peaks1[0]/Fs, fpeak1, 'x', color='w')
    ax_spec[1].plot(peaks2[0]/Fs, fpeak2, 'x', color='w')








plt.show(block=True)




                
                

                
    
    
    
