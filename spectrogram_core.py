import numpy as np
import scipy.signal as sig

def sclip_spectrogram(data, dB_range):

    '''    
    Purpose
    ----------
    Clip the spectrogram magnitudes to fit the range [0, -dB_range] 
    
    Parameters
    ----------
    data : matrix-like [N x M]
        the magntitudes of the spectrogram
    dB_range : single-value
        the maximum range of the spectrogram values
        
    Returns
    -------
    data : vector-like
        clipped S values of the spectrogram 
    '''
    
    return np.clip(data - np.amax(data), a_min = -dB_range, a_max = None) # subtract max and clip values smaller than -dB_ranges

def fclip_spectrogram(s, f, f_bounds):
    
    '''
    Purpose
    ----------
    clip the frequency and magnitude values of the spectrogram to fit f_bounds (if you don't clip it will throw off your color bar)

    Parameters
    ----------
    s : matrix-like (N_f, N_t)
        magnitude values of the spectrogram 
    f : vector-like (N_f)
        frequency values of the spectrogram in Hertz
    f_bounds : vector-like (2x1)
        the frequency bounds of which to keep the spectrogram in Hertz

    Returns
    -------
    s : matrix-like
        clipped spectrogram magnitudes
    f : vector-like
        clipped frequency values
    '''
    # trim the spectrogram based on f_bounds
    fmin, fmax = f_bounds

    # remove values outside of frequency bounds
    lfc = (f >= fmin).argmax() # finds the index of the first value that is >= fmin
    mfc = (f <= fmax).argmin()  
    f = f[lfc:mfc]
    s = s[:][lfc:mfc] # remove magnitudes that correspond to those f values

    return s, f

def get_cleaned_spectrogram(signal, Fs, window_length, noverlap, NFFT, T0 = 0, clipF = True, f_bounds = [0, 5e5], clipS = True, dB_range = 1e6):
    
    '''
    Purpose
    ----------
    return spectrogram values with the cleaned up values of s, t, and f to fit our formatting
    
    Parameters
    ----------
    signal : vector-like
        signal that the spectrogram is performed on
    Fs : single-value
        sample rate of the signal.
    window_length : single-value
        length of the window used for windowing the spectrogram
    noverlap : integer
        number of points that will be overlapped for the spectrogram
    NFFT : integer
        number of points used for calculating FFT.
    T0 : single-value
        first time value, is added onto the time vector
    clipF : Boolean, optional
        whether to clip the freq range of the spectrogram. The default is True.
    f_bounds : vector-like [1, 2], optional
        the frequency bounds used for the spectrogram. The default is [0, 5e5].
    clipS : Boolean, optional
        whether to clip the s-values of the spectrogram ornot. The default is True.
    dB_range : single-value, optional
        maximum -dB value of the spectrogram. The default is 1e6.

    Returns
    -------
    s : matrix-like [N_t, N_f]
        magnitudes of the spectrogram.
    f : vector-like [N_f, 1]
        frequencies values of the spectrogram.
    t : vector-like [N_t, 1]
        time values of the spectrogram.
    '''

    ## calculate the spectrogram            
    f, t, s = sig.spectrogram(signal, fs = Fs, nperseg = window_length, noverlap = noverlap, nfft = NFFT)
    t = t+T0 # shift to match t_bounds
    
    # clip spectrogram in f_spec (must do this before clipping in s)
    if clipF:
        s, f = fclip_spectrogram(s, f, f_bounds) # still good to do it but it becomes a little less important when you have butterworth filter
    
    # clip the spectrogram in s and convert to dB
    if clipS:
        s = sclip_spectrogram(10*np.log10(s), dB_range)

    return s, f, t

def compute_model_spectrogram(signal, Fs, window_length, per_overlap, NFFT, window="hann", transform_mode="log_power", eps=1e-10, trim_freq=False, f_bounds=None, per_sample_normalize=True, T0=0):
    '''
    Purpose
    ----------
    Compute a spectrogram for deep learning input from a waveform.

    This is separate from get_cleaned_spectrogram(), which is more plotting-oriented.
    This function returns the raw numeric spectrogram representation for model input.

    Parameters
    ----------
    signal : vector-like
        Input waveform.
    Fs : single-value
        Sample rate in Hz.
    window_length : int
        Spectrogram window length (nperseg).
    per_overlap : float
        Fractional overlap between windows, usually in [0, 1).
    NFFT : int
        Number of FFT points.
    window : str, optional
        Window type passed to scipy.signal.spectrogram.
    transform_mode : str, optional
        One of:
            "power"         -> return linear power spectrogram
            "log_power"     -> return log10(power + eps)
            "log_magnitude" -> return log10(magnitude + eps)
    eps : float, optional
        Small constant to avoid log(0).
    trim_freq : bool, optional
        Whether to trim the frequency axis using f_bounds.
    f_bounds : sequence-like of length 2, optional
        Frequency bounds [fmin, fmax] in Hz if trim_freq is True.
    per_sample_normalize : bool, optional
        If True, z-score normalize the final spectrogram per sample.
    T0 : single-value, optional
        Time offset added to returned t vector.

    Returns
    -------
    s : np.ndarray
        Spectrogram array of shape (N_f, N_t), dtype float32.
    f : np.ndarray
        Frequency vector in Hz.
    t : np.ndarray
        Time vector in seconds.
    '''

    signal = np.asarray(signal, dtype=np.float32).squeeze()

    if signal.ndim != 1:
        raise ValueError(f"signal must be 1D after squeeze, got shape {signal.shape}")

    if not (0 <= per_overlap < 1):
        raise ValueError(f"per_overlap must be in [0, 1), got {per_overlap}")

    noverlap = int(round(window_length * per_overlap))
    if noverlap >= window_length:
        noverlap = window_length - 1

    ## calculate the spectrogram
    f, t, s = sig.spectrogram(signal, fs=Fs, window=window, nperseg=window_length, noverlap=noverlap, nfft=NFFT, mode="psd")
    t = t + T0  # shift to match t_bounds

    # optional frequency trimming
    if trim_freq:
        if f_bounds is None or len(f_bounds) != 2:
            raise ValueError("f_bounds must be length-2 when trim_freq=True")
        s, f = fclip_spectrogram(s, f, f_bounds) 

    # transform for learning
    transform_mode = str(transform_mode).lower().strip()

    if transform_mode == "power":
        s = s
    elif transform_mode == "log_power":
        s = np.log10(s + eps)
    elif transform_mode == "log_magnitude":
        s = np.log10(np.sqrt(np.maximum(s, 0.0)) + eps)
    else:
        raise ValueError(f"Unsupported transform_mode: {transform_mode}")

    s = np.asarray(s, dtype=np.float32)

    # optional per-sample normalization over the full matrix
    if per_sample_normalize:
        mean = float(np.mean(s))
        std = float(np.std(s))
        if std > 0:
            s = (s - mean) / std
        else:
            s = s - mean

    if not np.all(np.isfinite(s)):
        raise ValueError("compute_model_spectrogram produced NaN or inf values")

    return s, f, t

def plot_spectrogram(s, f, t, fig, ax, bulk, bare_bones = False, title = "Spectrogram", colorbar_title = 'Amplitude (dB)', show_plots = True, save_plots = False, save_str = "spectrogram.jpg"):
    '''
    Purpose
    ----------
    Produce the spectrogram plot
    
    Parameters
    ----------
    s : matrix-like (N_f, N_t)
        magnitudes of the spectrogram            
    f : vector-like (N_f)
        frequencies of the spectrogram
    t : vector-like (N_t)
        times of the spectrogram      
    fig : figure object
        figure that will be used to plot the spectrogram                
    ax : axis object
        axis that the spectrogram will be plotted on            
    bulk : boolean
        whether the spectrogram plot is being used for a bulk plot (subplot) or not
    bare_bones : boolean, optional
        whether to plot the plot with the axis and color bar or not, if true will make the bare_bones plot which is just the data and nothing else            
    title : string, optional
        title for the plot        
    colorbar_title : string, optional
        title for the color bar        
    show_plots : boolean, optional
        whether to show the plot or not
    save_plots : boolean, optional
        whether to save the plot or not
        
    Returns
    -------
    No true returns, but creates a plot
        
    '''
    
    import matplotlib.pyplot as plt

    assert np.all(np.isfinite(s)), "Spectrogram contains NaN or infinite values."
    assert np.all(np.isfinite(t)), "Time vector contains NaN or infinite values."
    assert np.all(np.isfinite(f)), "Frequency vector contains NaN or infinite values."

    try:
        c = ax.pcolormesh(t*1000, f/1000, s, cmap='jet', shading='auto')  # axis are in kHz and ms 
        ax.set_ylim(np.min(f)/1000, np.max(f)/1000)
        
        # add plot labels and colorbar or not
        if not bare_bones:
            # Adding axis labels
            ax.set_xlabel('Time (ms)')
            ax.set_ylabel('Frequency (kHz)')
    
            # add title
            if not title == None:
                ax.set_title(title)
    
            # Adding color bar
            fig.colorbar(c, ax=ax, label=colorbar_title)
        elif bare_bones: # useful for feeding raw images into NN
            ax.axis('off')
         
        # show or save plot
        if show_plots == True and not bulk:
            fig.show()
        if save_plots == True and not bulk:
            fig.savefig(save_str, bbox_inches = 'tight')
            plt.close(fig)

    except Exception as e:
        print("Error plotting spectrogram:", e)
        print("Shape of s:", s.shape)
        print("Shape of t:", t.shape)
        print("Shape of f:", f.shape)  