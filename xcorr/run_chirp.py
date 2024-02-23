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

def plot_spec(ax, fig, spec_tup, fbounds = (20E3, 100E3), dB_range = 150, plot_title = 'spec'):
    
    fmin, fmax = fbounds
    s, f, t = spec_tup
    
    lfc = (f >= fmin).argmax()
    s = 20*np.log(s)
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
        
    
def process(raw, N_chirp, spec_settings, time_offs = 0):

    unraw = [((y << 8) | x) for x, y in zip(raw[::2], raw[1::2])]
    unraw_balanced = unraw - np.mean(unraw)
    
    pt_cut = unraw_balanced[time_offs:]
    remainder = unraw_balanced[:time_offs]
    
    Fs, NFFT, noverlap = spec_settings
    spec_tup = mlab.specgram(pt_cut, Fs=Fs, NFFT=NFFT, noverlap=noverlap)
    
    return spec_tup, pt_cut, remainder
    

Fs = 1E6
Ts = 1/Fs
NFFT = 512
noverlap = 400
spec_settings = (Fs, NFFT, noverlap)


DB_range = 150
f_plot_bounds = (20E3, 100E3)

N = 30000
T = N/Fs

T_chirp = 5E-3
f0_chirp = 100E3
f1_chirp = 30E3

offs_chirp = 2048
gain_chirp = 512

T_record = T - T_chirp

N_chirp = int(Fs * T_chirp)
N_record = N - N_chirp

#print(f"T={T}\t T_record={T_record}\t N_chirp={N_chirp}\t N_record={N_record}")

assert N_chirp + N_record == N
assert T_chirp + T_record == T

# create chirp time vector
tv_chirp = np.arange(0, T_chirp - Ts/2, Ts)

# create chirp
chirp = signal.chirp(tv_chirp, f0_chirp, T_chirp, f1_chirp, method='linear')
window = signal.windows.hann(N_chirp, False)

# bias chirp into range that DAC can output
#chirp_biased = (np.rint((4096/2)*(1 + window*chirp))).astype(int)
chirp_biased = (np.rint(offs_chirp + gain_chirp*chirp)).astype(int)

cbias = chirp_biased.tolist()

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
baud = 115200
sercom = serial.Serial("/dev/ttyACM0", baud)

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

# Give MCU chirp data
sercom.write([OP_GET_CHIRP])
sercom.write(byterr)

# Flush out ADCs
sercom.write([OP_START_JOB, DONT_CHIRP])
sercom.read(2*N)
sercom.read(2*N)

# send start run, chirp enabled
sercom.write([OP_START_JOB, DO_CHIRP])

# read and unpack echo data
raw1 = sercom.read(2 * N)
raw2 = sercom.read(2 * N)

fig_spec, ax_spec = plt.subplots(nrows=2, figsize=(9,7))
plt.subplots_adjust(left=0.1,
                    bottom=0.1,
                    right=0.9,
                    top=0.9,
                    wspace=0.4,
                    hspace=0.4)

spec_tup1, pt_cut1, pt1 = process(raw1, N_chirp, spec_settings, time_offs=0)
plot_spec(ax_spec[0], fig_spec, spec_tup1, fbounds = f_plot_bounds, dB_range = DB_range, plot_title='ear')

spec_tup2, pt_cut2, pt2 = process(raw2, N_chirp, spec_settings, time_offs=0)
plot_spec(ax_spec[1], fig_spec, spec_tup2, fbounds = f_plot_bounds, dB_range = DB_range, plot_title='no ear')

plt.show(block=True)



                
                

                
    
    
    
