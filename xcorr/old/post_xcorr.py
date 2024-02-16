import matplotlib.pyplot as plt
import scipy.signal as signal
import numpy as np
import matplotlib.mlab as mlab
import matplotlib.colors as colors
import matplotlib.gridspec as gs

# setup plotting
fig = plt.figure(figsize=(25,9))
super_grid = plt.GridSpec(nrows=2, ncols=1)

top_row = fig.add_subplot(super_grid[0])
top_row.set_axis_off()
#top_row_gs = gs.GridSpecFromSubplotSpec(1, 3, subplot_spec=super_grid[0], width_ratios=[8,8,0.3], wspace=0.4)
top_row_gs = gs.GridSpecFromSubplotSpec(1, 2, subplot_spec=super_grid[0], width_ratios=[8,8], wspace=0.4)

time_ax = fig.add_subplot(top_row_gs[0])
spec_ax = fig.add_subplot(top_row_gs[1])
#spec_colorbar_ax = figure.add_subplot(top_row_gs[2])

bottom_row = fig.add_subplot(super_grid[1])
bottom_row.set_axis_off()
bottom_row_gs = gs.GridSpecFromSubplotSpec(1, 2, subplot_spec=super_grid[1], width_ratios=[8,8], wspace=0.4)

impulse_ax = fig.add_subplot(bottom_row_gs[0])
xcorr_ax = fig.add_subplot(bottom_row_gs[1])

fig2, ax2 = plt.subplots(nrows = 2, ncols = 1, sharex=True)


# Hz
Fs = 1E6
Ts = 1/Fs
# samples
N = 16000
# ms
chirp_duration = 3E-3

record_period = (N/Fs) - chirp_duration
N_start_record = int(Fs * chirp_duration)

t_chirp = np.arange(0, chirp_duration, Ts)
chirp = signal.chirp(t_chirp, 90E3, chirp_duration, 20E3, method='linear')

#chirp_raw = np.load("chirp_signal/20231104_200622046.npy")
#chirp = chirp_raw[0:N_start_record]


data_dir = "1m_noear_prod"
data = np.load(f"{data_dir}/20231104_193725969.npy")

print(len(data))

# remove DC bias
data_balanced = data - np.mean(data)

print(len(data_balanced))
print(len(chirp))
print(len(t_chirp))

# split data into chirp emitted and record window
chirp_data = data[0:N_start_record]
record_data = data[N_start_record:]

chirp_data_balanced = data_balanced[0:N_start_record]
record_data_balanced = data_balanced[N_start_record:]

print(N_start_record)

assert len(chirp_data) + len(record_data) == N

# compute the cross-correlation of chirp and record
xcorr = signal.correlate(chirp_data_balanced, record_data_balanced, mode='full', method='fft')

# normalize cross-correlation to the maximum correlation
xcorr_norm = xcorr / np.max(xcorr)

# grab index of maximum correlation
# this tells us where in the record data has the highest "similarity" to the chirp
max_corr_idx = max(range(len(xcorr_norm)), key=xcorr_norm.__getitem__)

# deconvolve record with chirp to obtain impulse response h[n] = (x * y)[n] + e[n]
# x is record, y is chirp, e is noise
impulse, remainder = signal.deconvolve(data, chirp)

# normalize impulse
impulse_norm = impulse / np.max(impulse)

x_time = np.arange(0, (N-1)*Ts, Ts)
time_ax.plot(x_time, data[0:N-1])

# load in norm
norm_dat = np.load("norm.npy")
sn,fn,tn = mlab.specgram(norm_dat, Fs=Fs, NFFT=512, noverlap=400)

# compute spectrogram of balanced data
s,f,t = mlab.specgram(data_balanced, Fs=Fs, NFFT=512, noverlap=400)
spec_ax.pcolormesh(t, f, s, cmap='jet', shading='auto', norm=colors.LogNorm(vmin=sn.min(), vmax=sn.max())) 
spec_ax.set_ylim(10E3, 100E3)
#spec_ax.specgram(data_balanced, Fs=Fs, NFFT=512, noverlap=400)

impulse_ax.plot(np.flip(impulse_norm))
xcorr_ax.plot(np.flip(xcorr_norm))

ax2[0].pcolormesh(t, f, s, cmap='jet', shading='auto', norm=colors.LogNorm(vmin=sn.min(), vmax=sn.max()))
ax2[0].set_ylim(10E3, 100E3)

#ax2[1].plot(t_chirp, xcorr_norm)

plt.show(block=True)


