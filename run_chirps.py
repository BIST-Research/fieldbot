#Import what needed 
# numpy, refers to Numerical Python, is imported in order to deal with arrays, matrices, and collection of functions
import numpy as np

# pyserial
#This allows to open, read, and write to serial ports 
#With this I can configure parameters such as baud rate, parity, stop bits to match the specifications of the devices we use
import serial

# it allows us to get port information and list which ports are available
import serial.tools.list_ports

# this provides various functions related to time
import time

# this allow us to use mathematical built-in functions
import math

# this allow users to use built-in os module 
# this module allows users to manipulate file, directory, and system. 
import os

# required for creation and customization of plots
import matplotlib.pyplot as plt

#import numpy as np

# shroten the names of modules for easier use
import matplotlib.mlab as mlab
import matplotlib.colors as colors

# required to handle command-line arguments and environment
import sys

# this tool is required to process signals in python, such as filtering, analyzing, and manipulating signals
from scipy import signal

# required to work with date and time
from datetime import datetime

# obtain current timestamp, it is useful for logging things and other operations related to time.
from bb_utils import get_timestamp_now

# Frequency 1MHz
Fs = 1E6

#Time: Time = Frequency^-1
Ts = 1/Fs

# Number of points used in FFT (Fast Fourier Transform)
NFFT = 512

# Number of overlaps
noverlap = 400

# Create a Tuple that contains Fs, NFFT, and noverlap
spec_settings = (Fs, NFFT, noverlap)

# Set Database Range = 100 
DB_range = 100

# Tuple that holds bounds for plot 
f_plot_bounds = (25E3, 100E3)

# N is the number of I divide the frequency
N = 16000

# T = Period 
T = N/Fs

# Period of chirp
T_chirp = 3E-3
f0_chirp = 100E3
f1_chirp = 30E3

# Offset for chirp
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
sercom = serial.Serial("COM8", baud)

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

folder_name = str(sys.argv[1]) 
nruns = int(sys.argv[2])
save_folder = "data/" + folder_name


if not os.path.exists(save_folder):
	os.mkdir(save_folder)

for n in range(nruns):
    # send start run, chirp enabled
    sercom.write([OP_START_JOB, DO_CHIRP])

    # read and unpack echo data
    raw1 = sercom.read(2 * N)
    raw2 = sercom.read(2 * N)
    
    #unraw1 = unpack(raw1)
    #unraw2 = unpack(raw2)
    
    if n % 100 == 0:
	    print(f"{n}/{nruns}\n")
    
    with open((save_folder +  "/" + f'{get_timestamp_now()}.npy'), 'wb') as fd:
        np.save(fd, raw1)
        np.save(fd, raw2)
        
print(str(nruns) + " runs saved in folder " + folder_name)
    
    
    
    
        
