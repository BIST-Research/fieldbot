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

def process(s, f, t, fmin, DB_range):
    
    lfc = (f >= fmin).argmax()
    s = 20*np.log(s)
    f_cut = f[lfc:]
    s_cut = s[:][lfc:]

    
    max_s = np.amax(s_cut)
    s_cut = s_cut - max_s
    
    [rows_s, cols_s] = np.shape(s_cut)
    
    for col in range(cols_s):
        for row in range(rows_s):
            if s_cut[row][col] < -1*DB_range:
                s_cut[row][col] = -1*DB_range
                
    return s_cut, f_cut

Fs = 1E6
Ts = 1/Fs

NFFT = 512
noverlap = 400

N = 30000
T = N/Fs

T_chirp = 5E-3
f0_chirp = 100E3
f1_chirp = 30E3

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

offs = 2048
gain = 512

chirp_biased = (np.rint(offs + gain*chirp)).astype(int)

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
sercom = serial.Serial("/dev/cu.usbmodem14101", baud)

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

#print("Send chirp ack")

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
unraw1 = [((y << 8) | x) for x, y in zip(raw1[::2], raw1[1::2])]
unraw2 = [((y << 8) | x) for x, y in zip(raw2[::2], raw2[1::2])]
# send amp stop
#sercom.write([OP_AMP_STOP])

unraw1_balanced = unraw1 - np.mean(unraw1)
unraw2_balanced = unraw2 - np.mean(unraw2)

pt_cut1 = unraw1_balanced[N_chirp:]
pt_cut2 = unraw2_balanced[N_chirp:]

s1,f1,t1 = mlab.specgram(pt_cut1, Fs=Fs, NFFT=512, noverlap=400)
s2,f2,t2 = mlab.specgram(pt_cut2, Fs=Fs, NFFT=512, noverlap=400)

f_min = 20E3

DB_range = 200

fig_recv, ax_recv = plt.subplots(nrows=2)

sc1,fc1 = process(s1, f1, t1, f_min, DB_range)
sc2,fc2 = process(s2, f2, t2, f_min, DB_range)

cf1 = ax_recv[0].pcolormesh(t1, fc1, sc1, cmap='jet', shading='auto')
cf2 = ax_recv[1].pcolormesh(t2, fc2, sc2, cmap='jet', shading='auto')

ax_recv[0].set_ylim(f_min, 100000)
ax_recv[1].set_ylim(f_min, 100000)

fig_recv.subplots_adjust(right=0.8)


cbar_ax1 = fig_recv.add_axes([0.85,0.55,0.05,0.3])
cbar_ax2 = fig_recv.add_axes([0.85,0.15,0.05,0.3])

fig_recv.colorbar(cf1, cax=cbar_ax1)
fig_recv.colorbar(cf2, cax=cbar_ax2)

ax_recv[0].title.set_text("Ear")
ax_recv[0].set_xlabel("time (s)")
ax_recv[1].set_xlabel("time (s)")
ax_recv[0].set_ylabel("freq (Hz)")
ax_recv[1].set_ylabel("freq (Hz)")
ax_recv[1].title.set_text("No Ear")

plt.show(block=True)






                
                

                
    
    
    
