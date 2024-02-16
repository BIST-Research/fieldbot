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

Fs = 1E6
Ts = 1/Fs

NFFT = 512
noverlap = 400

N = 30000
T = N/Fs

T_chirp = 5E-3
f0_chirp = 90E3
f1_chirp = 15E3

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
chirp_biased = (np.rint((4096/2)*(1 + window*chirp))).astype(int)

cbias = chirp_biased.tolist()

byterr = bytearray()
for num in cbias:
    b = num.to_bytes(2)
    byterr.append(b[1])
    byterr.append(b[0])
    
print(byterr)
    
# verify chirp on spectrogram
fig_chirp, ax_chirp = plt.subplots(nrows=1)
ax_chirp.plot(chirp_biased)
#ax_chirp.specgram(chirp, Fs=Fs, NFFT=NFFT, noverlap=noverlap, cmap='jet')
#ax_chirp.set_ylim(0, 500E3)
#plt.show(block=True)

# Establish serial
baud = 115200
sercom = serial.Serial("/dev/cu.usbmodem14301", baud)

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
sercom.write([OP_START_JOB, 0x00])
sercom.read(2 * N)

# send start run, chirp disabled
sercom.write([OP_START_JOB, 0x00])

# Get norm data (no chirp, just listen) and unpack
raw_norm = sercom.read(2 * N)
norm = [((y << 8) | x) for x, y in zip(raw_norm[::2], raw_norm[1::2])]

# send start run, chirp enabled
sercom.write([OP_START_JOB, 0x01])

# read and unpack echo data
raw = sercom.read(2 * N)
unraw = [((y << 8) | x) for x, y in zip(raw[::2], raw[1::2])]

# send amp stop
#sercom.write([OP_AMP_STOP])

fig_recv, ax_recv = plt.subplots(nrows=2)

norm_balanced = norm - np.mean(norm)

sn,fn,tn = mlab.specgram(norm, Fs=Fs, NFFT=512, noverlap=400)

unraw_balanced = unraw - np.mean(unraw)

s,f,t = mlab.specgram(unraw_balanced, Fs=Fs, NFFT=512, noverlap=400)

xcorr = signal.correlate(window*chirp/np.max(chirp), unraw_balanced/np.max(unraw_balanced), mode='full', method='fft')

xcorr /= np.max(xcorr)
xcorr = np.flip(xcorr)

xcorr_chopped = xcorr[0:N]
print(len(xcorr_chopped))
ax_recv[0].pcolormesh(t,f,s, cmap='jet', shading='auto', norm=colors.LogNorm(vmin=sn.min(), vmax=sn.max()))
#ax_recv[0].specgram(unraw_balanced, Fs=Fs, NFFT=512, noverlap=400)
ax_recv[0].set_ylim(0, 100E3)

ax_recv[1].plot(xcorr_chopped)
plt.show(block=True)
