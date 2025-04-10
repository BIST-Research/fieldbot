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
import sys

from scipy import signal
from datetime import datetime
from bb_utils import bin2dec

def plot_spec(ax, fig, spec_tup, fbounds = (20E3, 100E3), dB_range = 40, plot_title = 'spec'):
    
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
        
def plot_sig(ax, fig, sig):
	t = np.arange(0, len(sig))/Fs_ADC
	cf = ax.plot(t, sig)
	ax.set_ylabel('Signal')
	ax.set_xlabel('Time (sec)')
	ax.set_xlim(0, np.max(t))

    
def process(raw, N_chirp, spec_settings, time_offs = 0):

    unraw = bin2dec(raw)
    unraw_balanced = unraw - np.mean(unraw)
    
    pt_cut = unraw_balanced[time_offs:]
    remainder = unraw_balanced[:time_offs]
    
    Fs_ADC, NFFT, noverlap, window = spec_settings
    spec_tup = mlab.specgram(pt_cut, Fs=Fs_ADC, NFFT=NFFT, noverlap=noverlap, window=window)
    
    return spec_tup, pt_cut, remainder
    

fname = str(sys.argv[1])
toffset = int(sys.argv[2])
fbl = int(sys.argv[3])
fbh = int(sys.argv[4])

if toffset < 0:
    time_offset = 4000
else:
    time_offset = toffset
    
if fbl < 0 or fbh < 0:
    f_plot_bounds = (30E3, 100E3)
else:
    f_plot_bounds = (fbl, fbh)

# ADAM HINSON - There should be multiple sample rates as the ADC and DAC do not use the same clock nor have the exact same sample rate
# based on the original parameters we were using ~1 MHz parameters:
# DAC: 1 MHz
# ADC: 1.071 MHz 
TCC_set_period = 29
Fs_DAC = 12E6/(TCC_set_period + 1) # Hz
#Fs_DAC = 400E3 # Hz, NOTE: when you change Fs_DAC you also need to change N_DAC_SAMPLES in ml_main.cpp as it = Fs_DAC*T_chirp
# NOTE: also probably going to run into some more issues when you don't end up with whole numbers here, probably should rewrite the code to focus around N_chirp more than T_chirp or at least think about it more
print(Fs_DAC)

sample_len = 6
prescaler = 16
time_to_convert_12bit = 13 # from diagram 45-3 in the ATSAMD51G19A data sheet
Fs_main_clock = 120E6
Fs_ADC = Fs_main_clock/prescaler/(time_to_convert_12bit+sample_len) # Hz
print(Fs_ADC)
Ts_DAC = 1/Fs_DAC
NFFT = 256
noverlap = int(0.6*NFFT) # CHANGE - convert overlap to a percent
#window = signal.windows.kaiser(NFFT, beta = 0.1)
window = signal.windows.hann(NFFT)
spec_settings = (Fs_ADC, NFFT, noverlap, window)
new_plots = 1

DB_range = 110 # dB
#f_plot_bounds = (30E3, 100E3)

N = 4000 # samples, listening time
T_listen = N/Fs_ADC
T_chirp = 3E-3 # ms, chirping time
#time_offset = round(T_chirp*10E5 + 200)
#print(T_chirp*1000)
#time_offset=4000
#print(time_offset)
f0_chirp = 100E3
f1_chirp = 30E3

offs_chirp = 2048
gain_chirp = 512

#T_record = T_listen - T_chirp
#print(T_listen-T_chirp)
#print("T_record: " + str(T_record) + "\nT_listen: " + str(T_listen) + "\nT_chirp: " + str(T_chirp) + "\n------------------\nT_chirp + T_record = " + str(T_chirp + T_record))
N_chirp = int(Fs_DAC * T_chirp)
N_record = N - N_chirp

#print(f"T={T}\t T_record={T_record}\t N_chirp={N_chirp}\t N_record={N_record}")

assert N_chirp + N_record == N
#assert T_chirp + T_record == T_listen # assertion error will occur because of fp math. Check that difference is within a threshold if you want to use this line but for now don't really see a reason for it

# create chirp time vector
tv_chirp = np.arange(0, T_chirp - Ts_DAC/2, Ts_DAC)

# create chirp
chirp = signal.chirp(tv_chirp, f0_chirp, T_chirp, f1_chirp, method='linear')
window = signal.windows.hann(N_chirp, False)

# bias chirp into range that DAC can output
#chirp_biased = (np.rint((4096/2)*(1 + window*chirp))).astype(int)
chirp_biased = (np.rint(offs_chirp + gain_chirp*chirp)).astype(int)

cbias = chirp_biased.tolist()

byterr = bytearray()
for num in cbias:
    b = num.to_bytes(2, 'big')
    byterr.append(b[1])
    byterr.append(b[0])
        
# verify chirp on spectrogram
#fig_chirp, ax_chirp = plt.subplots(nrows=1)
#ax_chirp.plot(chirp_biased)
#ax_chirp.specgram(chirp, Fs=Fs, NFFT=NFFT, noverlap=noverlap, cmap='jet')
#ax_chirp.set_ylim(0, 500E3)
#plt.show(block=True)

# Establish serial
baud = 115200
sercom = serial.Serial("COM5", baud)

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
sercom.write([OP_AMP_START])

print("Give MCU chirp data!!!\n")
# Give MCU chirp data
sercom.write([OP_GET_CHIRP])
print("Write the byterr")
print(len(byterr))
sercom.write(byterr)

print("Flush out ADCS!!!\n")
# Flush out ADCs
sercom.write([OP_START_JOB, DONT_CHIRP])
print("One more print")
sercom.read(2*N)
sercom.read(2*N)

print("Starting Chirp!!!!\n")
# send start run, chirp enabled
sercom.write([OP_START_JOB, DO_CHIRP])

# read and unpack echo data
raw1 = sercom.read(2 * N)
raw2 = sercom.read(2 * N)

with open(r'C:\Users\adamh\OneDrive - Virginia Tech\Desktop\BatLab\DRL Project\Ear RL Codes\chirp_test_data\{fname}.npy', 'wb') as fd:
    np.save(fd, raw1)
    np.save(fd, raw2)

if new_plots == 0: 
	fig_spec, ax_spec = plt.subplots(nrows=2, figsize=(9,7))
	plt.subplots_adjust(left=0.1,
		            bottom=0.1,
		            right=0.9,
		            top=0.9,
		            wspace=0.4,
		            hspace=0.4)

	spec_tup1, pt_cut1, pt1 = process(raw1, N_chirp, spec_settings, time_offs=time_offset)
	plot_spec(ax_spec[0], fig_spec, spec_tup1, fbounds = f_plot_bounds, dB_range = DB_range, plot_title='ear')

	spec_tup2, pt_cut2, pt2 = process(raw2, N_chirp, spec_settings, time_offs=time_offset)
	plot_spec(ax_spec[1], fig_spec, spec_tup2, fbounds = f_plot_bounds, dB_range = DB_range, plot_title='no ear')

	plt.show(block=True)
elif new_plots == 1:
	fig_1, ax_1 = plt.subplots(nrows = 2, figsize = (9, 7))
	plt.subplots_adjust(left=0.1,
		            bottom=0.1,
		            right=0.9,
		            top=0.9,
		            wspace=0.4,
		            hspace=0.4)
	fig_1.suptitle("Line 1")
	spec_tup1, pt_cut1, pt1 = process(raw1, N_chirp, spec_settings, time_offs=time_offset)


	plot_spec(ax_1[0], fig_1, spec_tup1, fbounds = f_plot_bounds, dB_range = DB_range, plot_title='spectrogram')
	plot_sig(ax_1[1], fig_1, pt_cut1)
	
	fig_2, ax_2 = plt.subplots(nrows = 2, figsize = (9, 7))
	plt.subplots_adjust(left=0.1,
		            bottom=0.1,
		            right=0.9,
		            top=0.9,
		            wspace=0.4,
		            hspace=0.4)
	fig_2.suptitle("Line 2")
	spec_tup2, pt_cut2, pt2 = process(raw2, N_chirp, spec_settings, time_offs=time_offset)


	plot_spec(ax_2[0], fig_2, spec_tup2, fbounds = f_plot_bounds, dB_range = DB_range, plot_title='spectrogram')
	plot_sig(ax_2[1], fig_2, pt_cut2)

	
	plt.show(block = True)
                
                

                
    
    
    
