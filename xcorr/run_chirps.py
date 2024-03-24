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

def unpack(raw):
    return [((y << 8) | x) for x, y in zip(raw[::2], raw[1::2])]

Fs = 1E6
Ts = 1/Fs
NFFT = 512
noverlap = 400
spec_settings = (Fs, NFFT, noverlap)

DB_range = 100
f_plot_bounds = (25E3, 100E3)

N = 16000
T = N/Fs

T_chirp = 3E-3
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

nruns = 10
for n in range(nruns):
    # send start run, chirp enabled
    sercom.write([OP_START_JOB, DO_CHIRP])

    # read and unpack echo data
    raw1 = sercom.read(2 * N)
    raw2 = sercom.read(2 * N)
    
    #unraw1 = unpack(raw1)
    #unraw2 = unpack(raw2)
    
    with open(f'{datetime.now()}.npy', 'wb') as fd:
        np.save(fd, raw1)
        np.save(fd, raw2)
        
    
    
    
    
    
        
