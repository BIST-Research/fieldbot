#
# Date created: 4/3/23
# Author: Ben Westcott
#
import matplotlib.pyplot as plt
import matplotlib.gridspec as gs
import matplotlib.colors as colors
import matplotlib.ticker as mticker
from matplotlib import mlab as mlab
from scipy import signal

import numpy as np
import yaml
import logging

class BBADCPlotter:

    def __init__(self, bat_log, echo_book, initial_data, fig, super_grid_idx, grid_name):
        
        self.bat_log = bat_log
        
        self.echo_Fs = 1/echo_book['sampling_period'];
        self.echo_num_adc_samples = echo_book['num_adc_samples']/2;
        self.echo_f0 = echo_book['f0']
        self.echo_f1 = echo_book['f1']
        
        self.sos = signal.butter(4, [self.echo_f1 - 2E3, self.echo_f0 + 2E3], 'bp', fs = self.echo_fs, output= = 'sos')
        
        plot_settings = echo_book['plot_settings'];
        
        self.echo_plot_interval = plot_settings['plot_interval']
        self.echo_calibration_interval = plot_settings['calibration_interval']
        self.echo_y_amplitude_padding = plot_settings['y_amplitude_padding']
        self.echo_y_spec_padding = plot_settings['y_spec_padding']
        self.echo_spec_cmap = plot_settings['spec_color_map']

        fft_settings = echo_book['fft_settings']
        
        self.echo_NFFT = fft_settings['NFFT']
        self.echo_noverlap = fft_settings['noverlap']
        
        adc_grid_row = fig.add_subplot(super_grid_idx)
        adc_grid_row.set_title(grid_name, fontweight='semibold', size=14, pad=20)
        adc_grid_row.set_axis_off()
       
        adc_gs = gs.GridSpecFromSubplotSpec(1, 3, subplot_spec=super_grid_idx, width_ratios=[8, 8, 0.3], wspace=0.4)
        self.adc_amplitude_ax = fig.add_subplot(adc_gs[0])
        self.adc_spec_ax = fig.add_subplot(adc_gs[1])
        self.adc_spec_cax = fig.add_subplot(adc_gs[2])
        
        self.calib_s = 0
        
    def echo_calibration_run(self, data):
        cs, cf, ct = mlab.specgram(data, Fs=self.echo_Fs, NFFT=self.echo_NFFT, noverlap=self.echo_noverlap)
        self.calib_s = cs0
      
    def clear_plots(self):
        self.adc_amplitude_ax.clear()
        self.adc_spec_ax.clear()
        self.adc_spec_cax.clear()
       
        
    def reset_plot_labels(self):
        self.adc_amplitude_ax.set_xlabel('Time (usec)')
        self.adc_amplitude_ax.set_ylabel('Amplitude (mV)')
       
        self.adc_spec_ax.set_xlabel('Time (sec)')
        self.adc_spec_ax.set_ylabel('Frequency (Hz)')
        
    def update_plot_limits(self, amplitude_data):
        self.adc0_amplitude_ax.set_ylim(min(amplitude_data) - self.echo_y_amplitude_padding, max(amplitude_data) + self.echo_y_amplitude_padding)        
        self.adc0_spec_ax.set_ylim(self.echo_f1 - self.echo_y_spec_padding, self.echo_f0 + self.echo_y_spec_padding)

    
    def update_plots(self, data):
    
        self.clear_plots()
        self.reset_plot_labels()
        self.update_plot_limits(data)
    
        self.adc_amplitude_ax.plot(data)
        
        s, f, t = mlab.specgram(signal.sosfilt(self.sos, data), NFFT=self.echo_NFFT, Fs=self.echo_Fs, noverlap=self.echo_noverlap)
        
        pcm = self.adc_spec_ax.pcolormesh(t, f, s, cmap=self.echo_spec_cmap, shading='auto', norm=colors.LogNorm(vmin=self.calib_s.min(), vmax=self.calib_s.max()))
        
        self.figure.colorbar(pcm, cax=self.adc_spec_cax)
        
        self.echo_calibration_run(initial_data)

class BBPlotter:

    def __init__(self, bat_log, echo_book, initial_data0, initial_data1=0):
    
        self.figure = plt.figure(figsize=(25,9))
        
        self.stereo_adc = echo_book['stereo_adc']
 
        super_grid = plt.GridSpec(2, 1)
        
        if not self.stereo_adc:
                
                super_grid = plt.GridSpec(1, 1)
                
                gs_adc0 = BBADCPlotter(self.bat_log, self.echo_book, ititial_data0, self.figure, super_grid[0], "ADC0")
                gs_adc1 = BBADCPlotter(self.bat_log, self.echo_book, initial_data1, self.figure, super_grid[1], "ADC1")
        
        
        
    def echo_calibration_run(self, data):
        cs0, cf0, ct0 = mlab.specgram(data[0], Fs=self.echo_Fs, NFFT=self.echo_NFFT, noverlap=self.echo_noverlap)
        self.calib_s0 = cs0
        
        cs1, cf1, ct1 = mlab.specgram(data[1], Fs=self.echo_Fs, NFFT=self.echo_NFFT, noverlap=self.echo_noverlap)
        self.calib_s1 = cs1
        
        
    def clear_plots(self):
        self.adc0_amplitude_ax.clear()
        self.adc0_spec_ax.clear()
        self.adc0_spec_cax.clear()
        
        self.adc1_amplitude_ax.clear()
        self.adc1_spec_ax.clear()
        self.adc1_spec_cax.clear()
        
    def reset_plot_labels(self):
        self.adc0_amplitude_ax.set_xlabel('Time (usec)')
        self.adc0_amplitude_ax.set_ylabel('Amplitude (mV)')
        
        self.adc1_amplitude_ax.set_xlabel('Time (usec)')
        self.adc1_amplitude_ax.set_ylabel('Amplitude (mV)')
        
        self.adc0_spec_ax.set_xlabel('Time (sec)')
        self.adc0_spec_ax.set_ylabel('Frequency (Hz)')
        
        self.adc1_spec_ax.set_xlabel('Time (sec)')
        self.adc1_spec_ax.set_ylabel('Frequency (Hz)')
        
    def update_super_title(self, time_elapsed, nruns_idx):
        self.figure.suptitle(f"{nruns_idx} echos - {str(time_elapsed)[:-7]}\n{int(nruns_idx/max(time_elapsed.seconds,1)*60)} echos/min")
        
    def update_plot_limits(self, amplitude_data):
    
        self.adc0_amplitude_ax.set_ylim(min(amplitude_data[0]) - self.echo_y_amplitude_padding, max(amplitude_data[0]) + self.echo_y_amplitude_padding)
        self.adc1_amplitude_ax.set_ylim(min(amplitude_data[1]) - self.echo_y_amplitude_padding, max(amplitude_data[1]) + self.echo_y_amplitude_padding)
        
        self.adc0_spec_ax.set_ylim(self.echo_f1 - self.echo_y_spec_padding, self.echo_f0 + self.echo_y_spec_padding)
        self.adc1_spec_ax.set_ylim(self.echo_f1 - self.echo_y_spec_padding, self.echo_f0 + self.echo_y_spec_padding)
    
    def update_plots(self, data):
    
        self.clear_plots()
        self.reset_plot_labels()
        self.update_plot_limits(data)
    
        self.adc0_amplitude_ax.plot(data[0])
        self.adc1_amplitude_ax.plot(data[1])
        
        s0, f0, t0 = mlab.specgram(signal.sosfilt(self.sos, data[0]), NFFT=self.echo_NFFT, Fs=self.echo_Fs, noverlap=self.echo_noverlap)
        
        pcm0 = self.adc0_spec_ax.pcolormesh(t0, f0, s0, cmap=self.echo_spec_cmap, shading='auto', norm=colors.LogNorm(vmin=self.calib_s0.min(), vmax=self.calib_s0.max()))
        
        self.figure.colorbar(pcm0, cax=self.adc0_spec_cax)
        
        s1, f1, t1 = mlab.specgram(signal.sosfilt(self.sos, data[1]), NFFT=self.echo_NFFT, Fs=self.echo_Fs, noverlap=self.echo_noverlap)
        
        pcm1 = self.adc1_spec_ax.pcolormesh(t1, f1, s1, cmap=self.echo_spec_cmap, shading='auto', norm=colors.LogNorm(vmin=self.calib_s1.min(), vmax=self.calib_s1.max()))
        
        self.figure.colorbar(pcm1, cax=self.adc1_spec_cax)
        
        plt.show(block=False)
        plt.pause(0.0001)
        
    
        
        

