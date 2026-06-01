"""
Spectrogram_Visualization_GUI_project_core_only.py

Project-only spectrogram plot generator.

Run this file from VS Code or a terminal. A GUI opens where students can:
    - choose a folder of .npy and/or .wav recordings
    - choose your spectrogram_core.py file
    - choose how many files to plot
    - make a GIF, MP4, PNG frames, and/or a contact sheet
    - trim raw recordings before spectrogram creation so the electrical passthrough is removed
    - keep all files from one run inside one clearly named output folder

Important design choice
-----------------------
This script does NOT use a built-in fallback spectrogram renderer. It loads and uses the
selected spectrogram_core.py file for both:
    - get_cleaned_spectrogram()
    - plot_spectrogram()

That keeps the plots consistent with your project code. The only extra logic here is for
loading files, optional raw-recording trimming, and saving outputs.

Recommended folder layout for students
--------------------------------------
Put this script next to the spectrogram folder you send them, for example:

    Student_Plotter/
    ├── Spectrogram_Visualization_GUI_project_core_only.py
    └── spectrogram/
        ├── __init__.py
        └── spectrogram_core.py

If the script cannot auto-find spectrogram_core.py, use the Browse button in the GUI.

Dependencies
------------
Required:
    pip install numpy scipy matplotlib imageio

Recommended for MP4 export:
    pip install imageio-ffmpeg

Notes
-----
- .wav sample rate is read automatically.
- .npy sample rate comes from the GUI setting.
- Your raw Echo_Data .npy files may be scalar byte strings; those are supported.
- N files = 0 means use all files found.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import os
import queue
import random
import re
import subprocess
import sys
import threading
import traceback
import wave
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable

import imageio.v2 as imageio
import matplotlib

# Non-interactive backend: works from VS Code, terminal, and headless machines.
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

try:
    from scipy.io import wavfile as scipy_wavfile
    SCIPY_WAV_AVAILABLE = True
except Exception:
    scipy_wavfile = None
    SCIPY_WAV_AVAILABLE = False

import tkinter as tk
from tkinter import filedialog, messagebox, ttk


RAW_NPY_BYTE_DTYPE_CHOICES = [
    "Auto: ADC/uint16 little-endian",
    "uint16 little-endian",
    "int16 little-endian",
    "float32 little-endian",
    "float64 little-endian",
    "uint8 raw bytes",
]

FILE_MODE_CHOICES = ["Both (.npy + .wav)", ".npy only", ".wav only"]
OUTPUT_TYPE_CHOICES = ["GIF", "MP4", "PNG frames only"]


@dataclass
class RunConfig:
    spectrogram_core_path: str
    input_folder: str
    output_folder: str
    recursive: bool
    file_mode: str
    n_files: int
    random_sample: bool
    random_seed: int
    output_type: str
    save_png_frames: bool
    save_contact_sheet: bool
    contact_sheet_max: int
    output_prefix: str
    add_timestamp: bool
    create_run_subfolder: bool
    fs_npy_hz: float
    raw_npy_byte_dtype: str
    remove_dc: bool
    trim_waveform: bool
    trim_start_ms: float
    trim_end_ms_text: str
    t0_from_trim_start: bool
    t0_ms: float
    window_length: int
    percent_overlap: float
    nfft: int
    fmin_hz: float
    fmax_hz: float
    db_range: float
    fps: int
    dpi: int
    fig_width: float
    fig_height: float
    bare_bones: bool
    open_output_folder: bool


@dataclass
class ProcessResult:
    output_folder: str
    output_files: list[str]
    total_files: int
    successful_count: int
    failed_count: int
    failed_csv: str | None
    animation_path: str | None


def safe_stem(text: str) -> str:
    """Make a string safe to use in filenames."""
    text = text.strip() or "spectrograms"
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", text)
    return text.strip("_") or "spectrograms"


def make_unique_path(path: Path) -> Path:
    """Return a non-existing path by adding _02, _03, ... when needed."""
    if not path.exists():
        return path
    parent = path.parent
    stem = path.name
    for i in range(2, 1000):
        candidate = parent / f"{stem}_{i:02d}"
        if not candidate.exists():
            return candidate
    return parent / f"{stem}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"


def find_default_spectrogram_core() -> str:
    """Try to auto-find spectrogram_core.py near this script or the current working directory."""
    candidates: list[Path] = []
    try:
        script_dir = Path(__file__).resolve().parent
        candidates.extend([
            script_dir / "spectrogram" / "spectrogram_core.py",
            script_dir / "spectrogram_core.py",
            script_dir / "src" / "spectrogram" / "spectrogram_core.py",
        ])
    except Exception:
        pass

    cwd = Path.cwd().resolve()
    candidates.extend([
        cwd / "spectrogram" / "spectrogram_core.py",
        cwd / "spectrogram_core.py",
        cwd / "src" / "spectrogram" / "spectrogram_core.py",
    ])

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return ""


def load_spectrogram_core(core_path: Path):
    """Load the selected spectrogram_core.py and verify required functions exist."""
    if not core_path.exists() or not core_path.is_file():
        raise FileNotFoundError(f"spectrogram_core.py not found: {core_path}")

    spec = importlib.util.spec_from_file_location("student_spectrogram_core", str(core_path))
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not import spectrogram_core.py from: {core_path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    missing = [name for name in ("get_cleaned_spectrogram", "plot_spectrogram") if not hasattr(module, name)]
    if missing:
        raise AttributeError(f"{core_path} is missing required function(s): {missing}")

    return module


def normalize_audio_array(data: np.ndarray) -> np.ndarray:
    """Convert common audio arrays to mono float32 in roughly [-1, 1]."""
    x = np.asarray(data)

    if x.ndim > 1:
        x = x.astype(np.float32, copy=False).mean(axis=1)

    if np.issubdtype(x.dtype, np.unsignedinteger):
        info = np.iinfo(x.dtype)
        midpoint = (info.max + info.min + 1) / 2.0
        x = (x.astype(np.float32) - midpoint) / midpoint
    elif np.issubdtype(x.dtype, np.integer):
        info = np.iinfo(x.dtype)
        scale = float(max(abs(info.min), abs(info.max)))
        x = x.astype(np.float32) / scale
    else:
        x = x.astype(np.float32, copy=False)

    x = np.nan_to_num(np.squeeze(x), nan=0.0, posinf=0.0, neginf=0.0)
    return x.astype(np.float32, copy=False)


def read_wav_with_wave_module(path: Path) -> tuple[np.ndarray, float]:
    """Read PCM WAV without scipy. Handles 8/16/24/32-bit PCM."""
    with wave.open(str(path), "rb") as wf:
        n_channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        fs_hz = float(wf.getframerate())
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    if sample_width == 1:
        data = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        data = (data - 128.0) / 128.0
    elif sample_width == 2:
        data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sample_width == 3:
        bytes_ = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        sign = (bytes_[:, 2] & 0x80) != 0
        expanded = np.zeros((bytes_.shape[0], 4), dtype=np.uint8)
        expanded[:, :3] = bytes_
        expanded[sign, 3] = 0xFF
        data = expanded.view("<i4").reshape(-1).astype(np.float32) / float(2**23)
    elif sample_width == 4:
        data = np.frombuffer(raw, dtype="<i4").astype(np.float32) / float(2**31)
    else:
        raise ValueError(f"Unsupported WAV sample width: {sample_width} bytes")

    if n_channels > 1:
        data = data.reshape(-1, n_channels).mean(axis=1)

    return data.astype(np.float32, copy=False), fs_hz


def load_wav(path: Path) -> tuple[np.ndarray, float]:
    """Load a WAV file and return waveform, sample_rate_hz."""
    if SCIPY_WAV_AVAILABLE:
        fs_hz, data = scipy_wavfile.read(path)  # type: ignore[union-attr]
        return normalize_audio_array(data), float(fs_hz)
    return read_wav_with_wave_module(path)


def decode_scalar_bytes_waveform(raw: bytes | bytearray | memoryview | np.bytes_, mode: str) -> np.ndarray:
    """Decode scalar byte-string .npy files, including raw ADC byte payloads."""
    b = bytes(raw)
    if not b:
        raise ValueError("Scalar byte .npy contained zero bytes")

    mode = str(mode).strip().lower()
    if mode.startswith("auto"):
        dtype = "<u2"  # Your Echo_Data examples decode correctly as little-endian uint16 ADC samples.
    elif "uint16" in mode:
        dtype = "<u2"
    elif "int16" in mode:
        dtype = "<i2"
    elif "float32" in mode:
        dtype = "<f4"
    elif "float64" in mode:
        dtype = "<f8"
    elif "uint8" in mode:
        dtype = "u1"
    else:
        raise ValueError(f"Unknown scalar-byte .npy decode mode: {mode}")

    itemsize = np.dtype(dtype).itemsize
    if len(b) % itemsize != 0:
        raise ValueError(f"Cannot decode {len(b)} bytes as dtype {dtype}")

    return np.frombuffer(b, dtype=np.dtype(dtype)).astype(np.float32, copy=False)


def bytes_payload_from_obj(obj: object) -> bytes | None:
    """Return raw bytes if obj is a scalar byte-string .npy payload."""
    if isinstance(obj, (bytes, bytearray, memoryview, np.bytes_)):
        return bytes(obj)

    if isinstance(obj, np.ndarray):
        arr = obj
        if arr.shape == () and arr.dtype.kind in {"S", "a", "V"}:
            try:
                item = arr.item()
                if isinstance(item, (bytes, bytearray, memoryview, np.bytes_)):
                    return bytes(item)
            except Exception:
                pass
            try:
                return arr.tobytes()
            except Exception:
                pass

    return None


def numeric_array_to_waveform(arr: np.ndarray) -> np.ndarray | None:
    """Convert a numeric array into a 1D waveform when the shape is reasonable."""
    if not np.issubdtype(arr.dtype, np.number):
        return None

    x = np.asarray(arr)
    x = np.squeeze(x)

    if x.ndim == 0:
        return None

    if x.ndim == 1:
        return np.nan_to_num(x.astype(np.float32, copy=False), nan=0.0, posinf=0.0, neginf=0.0)

    if x.ndim == 2:
        # Handles channel x samples or samples x channel. Pick channel 0 along the shorter axis.
        if x.shape[0] <= x.shape[1]:
            x = x[0, :]
        else:
            x = x[:, 0]
        return np.nan_to_num(np.squeeze(x).astype(np.float32, copy=False), nan=0.0, posinf=0.0, neginf=0.0)

    return None


def find_waveform_in_object(obj: object, raw_npy_byte_dtype: str, depth: int = 0, visited: set[int] | None = None) -> np.ndarray | None:
    """Recursively search common npy/dict/object formats for a waveform."""
    if visited is None:
        visited = set()
    if depth > 8:
        return None

    obj_id = id(obj)
    if obj_id in visited:
        return None
    visited.add(obj_id)

    raw_bytes = bytes_payload_from_obj(obj)
    if raw_bytes is not None:
        return decode_scalar_bytes_waveform(raw_bytes, raw_npy_byte_dtype)

    if isinstance(obj, dict):
        lower_to_key = {str(k).lower(): k for k in obj.keys()}
        preferred = [
            "waveform", "filtered_waveform", "trimmed_waveform", "signal", "x", "y", "data",
            "samples", "audio", "echo", "echo_data", "raw_echo", "adc", "adc_data", "mic", "voltage",
        ]
        for name in preferred:
            if name in lower_to_key:
                candidate = find_waveform_in_object(obj[lower_to_key[name]], raw_npy_byte_dtype, depth + 1, visited)
                if candidate is not None:
                    return candidate
        for value in obj.values():
            candidate = find_waveform_in_object(value, raw_npy_byte_dtype, depth + 1, visited)
            if candidate is not None:
                return candidate
        return None

    if isinstance(obj, (list, tuple)):
        for item in obj:
            candidate = find_waveform_in_object(item, raw_npy_byte_dtype, depth + 1, visited)
            if candidate is not None:
                return candidate
        return None

    if isinstance(obj, np.ndarray):
        arr = obj

        if arr.dtype.fields:
            preferred_fields = ["waveform", "filtered_waveform", "signal", "data", "samples", "echo", "adc_data"]
            lower_to_field = {str(name).lower(): name for name in arr.dtype.fields.keys()}
            for name in preferred_fields:
                if name in lower_to_field:
                    candidate = find_waveform_in_object(arr[lower_to_field[name]], raw_npy_byte_dtype, depth + 1, visited)
                    if candidate is not None:
                        return candidate
            for name in arr.dtype.fields.keys():
                candidate = find_waveform_in_object(arr[name], raw_npy_byte_dtype, depth + 1, visited)
                if candidate is not None:
                    return candidate
            return None

        if arr.dtype == object:
            if arr.shape == () or arr.size == 1:
                try:
                    return find_waveform_in_object(arr.item(), raw_npy_byte_dtype, depth + 1, visited)
                except Exception:
                    return None
            for item in arr.ravel():
                candidate = find_waveform_in_object(item, raw_npy_byte_dtype, depth + 1, visited)
                if candidate is not None:
                    return candidate
            return None

        return numeric_array_to_waveform(arr)

    try:
        arr = np.asarray(obj)
        return numeric_array_to_waveform(arr)
    except Exception:
        return None


def load_npy(path: Path, raw_npy_byte_dtype: str) -> np.ndarray:
    """Load normal arrays, dict/object arrays, and scalar-byte raw ADC .npy files."""
    loaded = np.load(path, allow_pickle=True)
    waveform = find_waveform_in_object(loaded, raw_npy_byte_dtype)
    if waveform is None:
        try:
            arr = np.asarray(loaded)
            shape = arr.shape
            dtype = arr.dtype
        except Exception:
            shape = "unknown"
            dtype = "unknown"
        raise ValueError(f"{path}: could not find a 1D waveform in npy payload; loaded shape={shape}, dtype={dtype}")
    if waveform.ndim != 1:
        raise ValueError(f"{path}: waveform ended up with shape {waveform.shape}, expected 1D")
    if waveform.size == 0:
        raise ValueError(f"{path}: waveform is empty")
    return waveform.astype(np.float32, copy=False)


def load_waveform(path: Path, cfg: RunConfig) -> tuple[np.ndarray, float]:
    """Load .npy or .wav and return waveform, sample_rate_hz."""
    suffix = path.suffix.lower()
    if suffix == ".npy":
        return load_npy(path, cfg.raw_npy_byte_dtype), float(cfg.fs_npy_hz)
    if suffix == ".wav":
        return load_wav(path)
    raise ValueError(f"Unsupported file type: {path.suffix}")


def parse_trim_end_ms(text: str) -> float | None:
    """Parse trim end text. Empty, 0, or negative means trim to end of file."""
    text = str(text).strip()
    if text == "":
        return None
    value = float(text)
    if value <= 0:
        return None
    return value


def preprocess_waveform(waveform: np.ndarray, fs_hz: float, cfg: RunConfig) -> tuple[np.ndarray, float, dict[str, object]]:
    """Optional time trimming/DC removal before calling spectrogram_core.py."""
    x = np.asarray(waveform, dtype=np.float32).ravel()
    original_samples = int(x.size)
    trim_start_idx = 0
    trim_end_idx = original_samples
    trim_end_ms = parse_trim_end_ms(cfg.trim_end_ms_text)

    if cfg.trim_waveform:
        if cfg.trim_start_ms < 0:
            raise ValueError("Trim start must be >= 0 ms")
        trim_start_idx = int(round((cfg.trim_start_ms / 1000.0) * fs_hz))
        if trim_end_ms is not None:
            if trim_end_ms <= cfg.trim_start_ms:
                raise ValueError("Trim end must be greater than trim start")
            trim_end_idx = int(round((trim_end_ms / 1000.0) * fs_hz))
        trim_start_idx = max(0, min(trim_start_idx, original_samples))
        trim_end_idx = max(trim_start_idx, min(trim_end_idx, original_samples))
        x = x[trim_start_idx:trim_end_idx]

    if x.size == 0:
        raise ValueError(
            f"Waveform became empty after trimming. Original samples={original_samples}, "
            f"trim_start_idx={trim_start_idx}, trim_end_idx={trim_end_idx}, Fs={fs_hz:g} Hz."
        )

    if cfg.remove_dc:
        x = x - float(np.mean(x))

    x = np.nan_to_num(x.astype(np.float32, copy=False), nan=0.0, posinf=0.0, neginf=0.0)

    if cfg.t0_from_trim_start and cfg.trim_waveform:
        t0_s = cfg.trim_start_ms / 1000.0
    else:
        t0_s = cfg.t0_ms / 1000.0

    meta = {
        "original_samples": original_samples,
        "processed_samples": int(x.size),
        "trim_start_idx": int(trim_start_idx),
        "trim_end_idx": int(trim_end_idx),
        "trim_enabled": bool(cfg.trim_waveform),
        "t0_seconds_used": float(t0_s),
    }
    return x, t0_s, meta


def choose_files(files: list[Path], n_files: int, random_sample: bool, random_seed: int) -> list[Path]:
    """Choose N files. n_files <= 0 means all files."""
    files = sorted(files)
    if n_files <= 0 or n_files >= len(files):
        if random_sample:
            rng = random.Random(random_seed)
            files = files[:]
            rng.shuffle(files)
        return files
    if random_sample:
        rng = random.Random(random_seed)
        return rng.sample(files, k=n_files)
    return files[:n_files]


def find_waveform_files(input_folder: Path, recursive: bool, file_mode: str) -> list[Path]:
    """Find waveform files based on GUI settings."""
    mode_to_suffixes = {
        "Both (.npy + .wav)": [".npy", ".wav"],
        ".npy only": [".npy"],
        ".wav only": [".wav"],
    }
    suffixes = set(mode_to_suffixes.get(file_mode, [".npy", ".wav"]))
    iterator: Iterable[Path] = input_folder.rglob("*") if recursive else input_folder.glob("*")
    return sorted(p for p in iterator if p.is_file() and p.suffix.lower() in suffixes)


def validate_spectrogram_settings(fs_hz: float, cfg: RunConfig) -> tuple[float, float, int]:
    """Validate settings and return fmin, fmax, noverlap for spectrogram_core."""
    if fs_hz <= 0:
        raise ValueError("Sample rate must be > 0 Hz")
    if cfg.window_length < 8:
        raise ValueError("Window length must be at least 8 samples")
    if not (0 <= cfg.percent_overlap < 0.98):
        raise ValueError("Overlap fraction must be between 0 and 0.98")
    if cfg.nfft < cfg.window_length:
        raise ValueError("NFFT should be greater than or equal to window length")
    if cfg.db_range <= 0:
        raise ValueError("dB range must be > 0")

    nyquist = fs_hz / 2.0
    fmin = max(0.0, float(cfg.fmin_hz))
    fmax = min(float(cfg.fmax_hz), np.nextafter(nyquist, 0.0))
    if fmax <= fmin:
        raise ValueError(
            f"Invalid frequency range for Fs={fs_hz:g} Hz. "
            f"Need 0 <= fmin < fmax < Nyquist={nyquist:g} Hz."
        )

    noverlap = int(round(cfg.percent_overlap * cfg.window_length))
    noverlap = min(max(noverlap, 0), cfg.window_length - 1)
    return fmin, fmax, noverlap


def fig_to_rgb_array(fig: plt.Figure) -> np.ndarray:
    """Convert a Matplotlib figure canvas to an RGB uint8 image."""
    fig.canvas.draw()
    try:
        rgba = np.asarray(fig.canvas.buffer_rgba())
        img = rgba[:, :, :3].copy()
    except Exception:
        width, height = fig.canvas.get_width_height()
        argb = np.frombuffer(fig.canvas.tostring_argb(), dtype=np.uint8).reshape(height, width, 4)
        img = argb[:, :, 1:4].copy()
    return img


def render_spectrogram_frame(core, waveform: np.ndarray, fs_hz: float, title: str | None, cfg: RunConfig, t0_s: float) -> np.ndarray:
    """Render one waveform as one RGB spectrogram frame using only spectrogram_core.py."""
    fmin_hz, fmax_hz, noverlap = validate_spectrogram_settings(fs_hz, cfg)

    s, f, t = core.get_cleaned_spectrogram(
        signal=waveform,
        Fs=fs_hz,
        window_length=cfg.window_length,
        noverlap=noverlap,
        NFFT=cfg.nfft,
        T0=t0_s,
        clipF=True,
        f_bounds=[fmin_hz, fmax_hz],
        clipS=True,
        dB_range=cfg.db_range,
    )

    if s.size == 0 or len(f) == 0 or len(t) == 0:
        raise ValueError(
            "spectrogram_core returned an empty spectrogram. Check Fs, Fmin/Fmax, "
            "window length, NFFT, and whether the waveform was over-trimmed."
        )

    fig, ax = plt.subplots(figsize=(cfg.fig_width, cfg.fig_height), dpi=cfg.dpi)
    try:
        core.plot_spectrogram(
            s=s,
            f=f,
            t=t,
            fig=fig,
            ax=ax,
            bulk=False,
            bare_bones=cfg.bare_bones,
            title=title,
            show_plots=False,
            save_plots=False,
        )
        img = fig_to_rgb_array(fig)
    finally:
        plt.close(fig)

    return img


def save_contact_sheet(frames: list[tuple[np.ndarray, str]], output_path: Path, dpi: int) -> None:
    """Save a compact grid of example frames."""
    if not frames:
        return
    n = len(frames)
    cols = min(4, n)
    rows = int(np.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 3.5, rows * 2.6), dpi=dpi)
    axes_array = np.asarray(axes).reshape(-1)
    for ax, (img, label) in zip(axes_array, frames):
        ax.imshow(img)
        ax.set_title(label, fontsize=8)
        ax.axis("off")
    for ax in axes_array[len(frames):]:
        ax.axis("off")
    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)


def write_manifest(manifest_path: Path, selected_files: list[Path], input_folder: Path) -> None:
    """Write a CSV record of which files were selected."""
    with manifest_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["index", "filename", "relative_path", "absolute_path"])
        for i, path in enumerate(selected_files, start=1):
            try:
                rel = path.relative_to(input_folder)
            except ValueError:
                rel = path.name
            writer.writerow([i, path.name, str(rel), str(path.resolve())])


def open_folder(path: Path) -> None:
    """Open a folder in the OS file manager."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception:
        pass


def run_processing(
    cfg: RunConfig,
    log: Callable[[str], None],
    progress: Callable[[int, int], None],
) -> ProcessResult:
    """Main processing function used by the GUI worker thread."""
    core_path = Path(cfg.spectrogram_core_path).expanduser().resolve()
    input_folder = Path(cfg.input_folder).expanduser().resolve()
    output_parent = Path(cfg.output_folder).expanduser().resolve()

    if not input_folder.exists() or not input_folder.is_dir():
        raise FileNotFoundError(f"Input folder not found: {input_folder}")

    log(f"Loading spectrogram core: {core_path}")
    core = load_spectrogram_core(core_path)

    prefix = safe_stem(cfg.output_prefix or input_folder.name)
    if cfg.add_timestamp:
        prefix = f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    output_folder = make_unique_path(output_parent / prefix) if cfg.create_run_subfolder else output_parent
    output_folder.mkdir(parents=True, exist_ok=True)

    files = find_waveform_files(input_folder, cfg.recursive, cfg.file_mode)
    if not files:
        raise RuntimeError(f"No waveform files found in {input_folder} using mode: {cfg.file_mode}")

    selected_files = choose_files(files, cfg.n_files, cfg.random_sample, cfg.random_seed)
    total = len(selected_files)
    if total == 0:
        raise RuntimeError("No files selected")

    log(f"Output folder for this run: {output_folder}")
    log(f"Found {len(files)} waveform file(s). Plotting {total} file(s).")
    log("Spectrogram rendering mode: project core only. No fallback renderer will be used.")
    if cfg.trim_waveform:
        trim_end = parse_trim_end_ms(cfg.trim_end_ms_text)
        end_msg = "end of file" if trim_end is None else f"{trim_end:g} ms"
        log(f"Waveform trimming ON: {cfg.trim_start_ms:g} ms to {end_msg} before spectrogram creation.")
    else:
        log("Waveform trimming OFF: T0 only shifts the plot axis; it does not remove passthrough samples.")

    output_files: list[Path] = [output_folder]
    manifest_path = output_folder / f"{prefix}_selected_files.csv"
    settings_path = output_folder / f"{prefix}_settings.json"
    readme_path = output_folder / "README_WHERE_ARE_MY_FILES.txt"
    summary_path = output_folder / f"{prefix}_RUN_SUMMARY.txt"

    write_manifest(manifest_path, selected_files, input_folder)
    settings_payload = asdict(cfg)
    settings_payload["actual_output_folder"] = str(output_folder)
    settings_path.write_text(json.dumps(settings_payload, indent=2), encoding="utf-8")
    readme_path.write_text(
        "This folder contains every file created by one spectrogram plotting run.\n\n"
        "Main output to look for:\n"
        "  - .gif or .mp4 animation, if animation export was selected and at least one file rendered successfully\n"
        "  - *_contact_sheet.png, if contact sheet export was selected\n"
        "  - *_png_frames/ folder, if PNG frame export was selected\n"
        "  - *_selected_files.csv lists the files selected for plotting\n"
        "  - *_failed_files.csv lists files that could not be plotted and why\n"
        "  - *_settings.json records the settings used for this run\n"
        "  - *_RUN_SUMMARY.txt gives a quick success/failure summary\n\n"
        "Important: T0 only changes the time axis. To remove electrical passthrough from raw recordings,\n"
        "enable 'Trim waveform before spectrogram' and set a start time such as 4.5 ms.\n",
        encoding="utf-8",
    )
    output_files.extend([readme_path, manifest_path, settings_path])

    save_animation = cfg.output_type in {"GIF", "MP4"}
    animation_path: Path | None = None
    writer = None

    if save_animation:
        suffix = ".gif" if cfg.output_type == "GIF" else ".mp4"
        animation_path = output_folder / f"{prefix}{suffix}"

    png_dir: Path | None = None
    if cfg.save_png_frames or cfg.output_type == "PNG frames only":
        png_dir = output_folder / f"{prefix}_png_frames"
        png_dir.mkdir(parents=True, exist_ok=True)
        output_files.append(png_dir)

    contact_frames: list[tuple[np.ndarray, str]] = []
    failed_files: list[tuple[Path, str]] = []
    per_file_rows: list[dict[str, object]] = []
    successful_count = 0

    try:
        for i, path in enumerate(selected_files, start=1):
            try:
                waveform_raw, fs_hz = load_waveform(path, cfg)
                waveform, t0_s, meta = preprocess_waveform(waveform_raw, fs_hz, cfg)
                title = None if cfg.bare_bones else path.stem
                frame = render_spectrogram_frame(core, waveform, fs_hz, title, cfg, t0_s)
                successful_count += 1

                if writer is None and animation_path is not None:
                    if cfg.output_type == "GIF":
                        writer = imageio.get_writer(animation_path, mode="I", fps=cfg.fps)
                    else:
                        writer = imageio.get_writer(animation_path, mode="I", fps=cfg.fps, codec="libx264", quality=8)

                if writer is not None:
                    writer.append_data(frame)

                if png_dir is not None:
                    png_path = png_dir / f"{i:04d}_{safe_stem(path.stem)}.png"
                    imageio.imwrite(png_path, frame)

                if cfg.save_contact_sheet and len(contact_frames) < cfg.contact_sheet_max:
                    contact_frames.append((frame, path.name))

                row = {"filename": path.name, "absolute_path": str(path.resolve()), "fs_hz": fs_hz, **meta, "status": "ok", "error": ""}
                per_file_rows.append(row)

                if i == 1 or i % 10 == 0 or i == total:
                    log(f"Rendered {i}/{total}: {path.name}")
                progress(i, total)
            except Exception as exc:
                failed_files.append((path, str(exc)))
                per_file_rows.append({"filename": path.name, "absolute_path": str(path.resolve()), "status": "failed", "error": str(exc)})
                log(f"FAILED: {path.name} -> {exc}")
                progress(i, total)
    finally:
        if writer is not None:
            writer.close()

    if animation_path is not None and successful_count > 0 and animation_path.exists():
        output_files.append(animation_path)
        log(f"Saved animation: {animation_path}")
    elif animation_path is not None and successful_count == 0:
        log("No animation was saved because zero files rendered successfully. Check *_failed_files.csv.")

    if cfg.save_contact_sheet and contact_frames:
        contact_path = output_folder / f"{prefix}_contact_sheet.png"
        save_contact_sheet(contact_frames, contact_path, cfg.dpi)
        output_files.append(contact_path)
        log(f"Saved contact sheet: {contact_path}")

    failed_path: Path | None = None
    if failed_files:
        failed_path = output_folder / f"{prefix}_failed_files.csv"
        with failed_path.open("w", newline="", encoding="utf-8") as f:
            writer_csv = csv.writer(f)
            writer_csv.writerow(["filename", "absolute_path", "error"])
            for path, err in failed_files:
                writer_csv.writerow([path.name, str(path.resolve()), err])
        output_files.append(failed_path)
        log(f"Some files failed. Saved failure list: {failed_path}")

    per_file_path = output_folder / f"{prefix}_per_file_summary.csv"
    if per_file_rows:
        keys: list[str] = []
        for row in per_file_rows:
            for key in row.keys():
                if key not in keys:
                    keys.append(key)
        with per_file_path.open("w", newline="", encoding="utf-8") as f:
            writer_csv = csv.DictWriter(f, fieldnames=keys)
            writer_csv.writeheader()
            writer_csv.writerows(per_file_rows)
        output_files.append(per_file_path)

    failed_count = len(failed_files)
    summary_text = (
        f"Spectrogram plotting run summary\n"
        f"================================\n\n"
        f"Input folder: {input_folder}\n"
        f"Output folder: {output_folder}\n"
        f"spectrogram_core.py: {core_path}\n"
        f"Files selected: {total}\n"
        f"Files rendered successfully: {successful_count}\n"
        f"Files failed: {failed_count}\n"
        f"Animation: {animation_path if animation_path is not None and successful_count > 0 else 'not saved'}\n"
        f"Contact sheet frames: {len(contact_frames)}\n\n"
        f"Trimming enabled: {cfg.trim_waveform}\n"
        f"Trim start ms: {cfg.trim_start_ms}\n"
        f"Trim end ms: {cfg.trim_end_ms_text or 'end'}\n"
        f"T0 from trim start: {cfg.t0_from_trim_start}\n"
        f"Manual T0 ms: {cfg.t0_ms}\n\n"
        f"Reminder: T0 only changes the plotted time axis. It does not clip the waveform.\n"
        f"To remove electrical passthrough from raw recordings, trim the waveform before spectrogram creation.\n"
    )
    summary_path.write_text(summary_text, encoding="utf-8")
    output_files.append(summary_path)

    if successful_count == 0:
        raise RuntimeError(
            f"All {total} selected files failed. No plots were created. "
            f"Check the failure CSV in: {output_folder}"
        )

    log("Done.")
    if cfg.open_output_folder:
        open_folder(output_folder)

    return ProcessResult(
        output_folder=str(output_folder),
        output_files=[str(p) for p in output_files],
        total_files=total,
        successful_count=successful_count,
        failed_count=failed_count,
        failed_csv=str(failed_path) if failed_path is not None else None,
        animation_path=str(animation_path) if animation_path is not None and successful_count > 0 and animation_path.exists() else None,
    )


class SpectrogramGui(tk.Tk):
    """Small Tkinter GUI for project-core-only spectrogram export."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Project Spectrogram Plot Generator")
        self.geometry("980x860")
        self.minsize(860, 720)

        self.queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker_thread: threading.Thread | None = None

        self._build_variables()
        self._build_layout()
        self.after(100, self._poll_queue)

    def _build_variables(self) -> None:
        cwd = Path.cwd()
        default_core = find_default_spectrogram_core()
        self.spectrogram_core_path_var = tk.StringVar(value=default_core)
        self.input_folder_var = tk.StringVar(value=str(cwd))
        self.output_folder_var = tk.StringVar(value=str(cwd / "Spectrogram_Plots"))
        self.recursive_var = tk.BooleanVar(value=True)
        self.file_mode_var = tk.StringVar(value="Both (.npy + .wav)")
        self.n_files_var = tk.StringVar(value="300")
        self.random_sample_var = tk.BooleanVar(value=True)
        self.random_seed_var = tk.StringVar(value="0")
        self.output_type_var = tk.StringVar(value="GIF")
        self.save_png_frames_var = tk.BooleanVar(value=False)
        self.save_contact_sheet_var = tk.BooleanVar(value=True)
        self.contact_sheet_max_var = tk.StringVar(value="24")
        self.output_prefix_var = tk.StringVar(value="spectrogram_examples")
        self.add_timestamp_var = tk.BooleanVar(value=True)
        self.create_run_subfolder_var = tk.BooleanVar(value=True)
        self.fs_npy_var = tk.StringVar(value="1000000")
        self.raw_npy_byte_dtype_var = tk.StringVar(value="Auto: ADC/uint16 little-endian")
        self.remove_dc_var = tk.BooleanVar(value=True)
        self.trim_waveform_var = tk.BooleanVar(value=True)
        self.trim_start_ms_var = tk.StringVar(value="4.5")
        self.trim_end_ms_var = tk.StringVar(value="12.5")
        self.t0_from_trim_start_var = tk.BooleanVar(value=True)
        self.t0_ms_var = tk.StringVar(value="4.5")
        self.window_length_var = tk.StringVar(value="400")
        self.percent_overlap_var = tk.StringVar(value="0.7")
        self.nfft_var = tk.StringVar(value="512")
        self.fmin_var = tk.StringVar(value="30000")
        self.fmax_var = tk.StringVar(value="100000")
        self.db_range_var = tk.StringVar(value="50")
        self.fps_var = tk.StringVar(value="12")
        self.dpi_var = tk.StringVar(value="120")
        self.fig_width_var = tk.StringVar(value="6.4")
        self.fig_height_var = tk.StringVar(value="4.0")
        self.bare_bones_var = tk.BooleanVar(value=False)
        self.open_output_folder_var = tk.BooleanVar(value=True)

    def _build_layout(self) -> None:
        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)

        canvas = tk.Canvas(outer, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        self.content = ttk.Frame(canvas)
        self.content.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.content, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self._add_core_section()
        self._add_folder_section()
        self._add_file_section()
        self._add_output_section()
        self._add_preprocess_section()
        self._add_spectrogram_section()
        self._add_run_section()

    def _section(self, title: str) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(self.content, text=title, padding=10)
        frame.pack(fill="x", expand=True, pady=(0, 10))
        frame.columnconfigure(1, weight=1)
        return frame

    def _add_labeled_entry(self, parent: ttk.LabelFrame | ttk.Frame, row: int, label: str, variable: tk.StringVar, width: int = 16) -> ttk.Entry:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        entry = ttk.Entry(parent, textvariable=variable, width=width)
        entry.grid(row=row, column=1, sticky="we", pady=4)
        return entry

    def _add_core_section(self) -> None:
        frame = self._section("Required project plotting code")
        ttk.Label(frame, text="spectrogram_core.py").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.spectrogram_core_path_var).grid(row=0, column=1, sticky="we", pady=4)
        ttk.Button(frame, text="Browse...", command=self._browse_core).grid(row=0, column=2, padx=(8, 0), pady=4)
        ttk.Label(
            frame,
            text="This script uses only this file's get_cleaned_spectrogram() and plot_spectrogram().",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))

    def _add_folder_section(self) -> None:
        frame = self._section("Folders")
        ttk.Label(frame, text="Input folder").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.input_folder_var).grid(row=0, column=1, sticky="we", pady=4)
        ttk.Button(frame, text="Browse...", command=self._browse_input).grid(row=0, column=2, padx=(8, 0), pady=4)

        ttk.Label(frame, text="Output folder").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.output_folder_var).grid(row=1, column=1, sticky="we", pady=4)
        ttk.Button(frame, text="Browse...", command=self._browse_output).grid(row=1, column=2, padx=(8, 0), pady=4)

    def _add_file_section(self) -> None:
        frame = self._section("Files to plot")
        ttk.Label(frame, text="File type").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Combobox(frame, textvariable=self.file_mode_var, values=FILE_MODE_CHOICES, state="readonly", width=20).grid(row=0, column=1, sticky="w", pady=4)
        ttk.Checkbutton(frame, text="Search subfolders", variable=self.recursive_var).grid(row=0, column=2, sticky="w", padx=(16, 0), pady=4)

        ttk.Label(frame, text="N files (0 = all)").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.n_files_var, width=12).grid(row=1, column=1, sticky="w", pady=4)
        ttk.Checkbutton(frame, text="Random sample", variable=self.random_sample_var).grid(row=1, column=2, sticky="w", padx=(16, 0), pady=4)

        ttk.Label(frame, text="Random seed").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.random_seed_var, width=12).grid(row=2, column=1, sticky="w", pady=4)

    def _add_output_section(self) -> None:
        frame = self._section("Output")
        ttk.Label(frame, text="Output type").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Combobox(frame, textvariable=self.output_type_var, values=OUTPUT_TYPE_CHOICES, state="readonly", width=18).grid(row=0, column=1, sticky="w", pady=4)

        ttk.Label(frame, text="Output prefix").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.output_prefix_var).grid(row=1, column=1, sticky="we", pady=4)
        ttk.Checkbutton(frame, text="Add timestamp", variable=self.add_timestamp_var).grid(row=1, column=2, sticky="w", padx=(16, 0), pady=4)

        ttk.Checkbutton(frame, text="Put all files from this run in one new folder", variable=self.create_run_subfolder_var).grid(row=2, column=0, columnspan=3, sticky="w", pady=4)
        ttk.Checkbutton(frame, text="Also save individual PNG frames", variable=self.save_png_frames_var).grid(row=3, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Checkbutton(frame, text="Save contact sheet summary", variable=self.save_contact_sheet_var).grid(row=4, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Label(frame, text="Contact sheet max frames").grid(row=5, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.contact_sheet_max_var, width=12).grid(row=5, column=1, sticky="w", pady=4)
        ttk.Checkbutton(frame, text="Open output folder when done", variable=self.open_output_folder_var).grid(row=6, column=0, columnspan=2, sticky="w", pady=4)

    def _add_preprocess_section(self) -> None:
        frame = self._section("Preprocessing before spectrogram_core.py")
        ttk.Checkbutton(frame, text="Trim waveform before spectrogram", variable=self.trim_waveform_var).grid(row=0, column=0, columnspan=2, sticky="w", pady=4)
        self._add_labeled_entry(frame, 1, "Trim start (ms)", self.trim_start_ms_var)
        self._add_labeled_entry(frame, 2, "Trim end (ms; blank/0 = end)", self.trim_end_ms_var)
        ttk.Checkbutton(frame, text="Use trim start as plotted T0", variable=self.t0_from_trim_start_var).grid(row=3, column=0, columnspan=2, sticky="w", pady=4)
        self._add_labeled_entry(frame, 4, "Manual T0 if not using trim start (ms)", self.t0_ms_var)
        ttk.Checkbutton(frame, text="Remove mean/DC from waveform", variable=self.remove_dc_var).grid(row=5, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Label(
            frame,
            text="T0 only shifts the time axis. Trimming is what actually removes early passthrough samples.",
        ).grid(row=6, column=0, columnspan=3, sticky="w", pady=(4, 0))

    def _add_spectrogram_section(self) -> None:
        frame = self._section("Spectrogram settings")
        left = ttk.Frame(frame)
        right = ttk.Frame(frame)
        left.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=(0, 20))
        right.grid(row=0, column=2, sticky="nsew")
        left.columnconfigure(1, weight=1)
        right.columnconfigure(1, weight=1)

        self._add_labeled_entry(left, 0, "Sample rate for .npy (Hz)", self.fs_npy_var)
        ttk.Label(left, text="Scalar-byte .npy decode").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Combobox(left, textvariable=self.raw_npy_byte_dtype_var, values=RAW_NPY_BYTE_DTYPE_CHOICES, state="readonly", width=28).grid(row=1, column=1, sticky="we", pady=4)
        self._add_labeled_entry(left, 2, "Window length (samples)", self.window_length_var)
        self._add_labeled_entry(left, 3, "Overlap fraction", self.percent_overlap_var)
        self._add_labeled_entry(left, 4, "NFFT", self.nfft_var)
        self._add_labeled_entry(left, 5, "Fmin (Hz)", self.fmin_var)
        self._add_labeled_entry(left, 6, "Fmax (Hz)", self.fmax_var)

        self._add_labeled_entry(right, 0, "dB range", self.db_range_var)
        self._add_labeled_entry(right, 1, "Animation FPS", self.fps_var)
        self._add_labeled_entry(right, 2, "DPI", self.dpi_var)
        self._add_labeled_entry(right, 3, "Figure width", self.fig_width_var)
        self._add_labeled_entry(right, 4, "Figure height", self.fig_height_var)
        ttk.Checkbutton(right, text="Bare bones plot", variable=self.bare_bones_var).grid(row=5, column=0, columnspan=2, sticky="w", pady=4)

    def _add_run_section(self) -> None:
        frame = self._section("Run")
        self.run_button = ttk.Button(frame, text="Generate spectrogram plots", command=self._start_processing)
        self.run_button.grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.progress_var = tk.StringVar(value="Ready.")
        ttk.Label(frame, textvariable=self.progress_var).grid(row=0, column=1, sticky="w", padx=(12, 0), pady=(0, 8))
        self.progress_bar = ttk.Progressbar(frame, orient="horizontal", mode="determinate")
        self.progress_bar.grid(row=1, column=0, columnspan=3, sticky="we", pady=(0, 8))
        self.log_text = tk.Text(frame, height=14, wrap="word")
        self.log_text.grid(row=2, column=0, columnspan=3, sticky="nsew")
        frame.rowconfigure(2, weight=1)
        frame.columnconfigure(1, weight=1)

        if self.spectrogram_core_path_var.get():
            self._append_log(f"Auto-found spectrogram_core.py: {self.spectrogram_core_path_var.get()}")
        else:
            self._append_log("spectrogram_core.py was not auto-found. Browse to it before running.")
        if not SCIPY_WAV_AVAILABLE:
            self._append_log("scipy.io.wavfile not found; WAV loading will use Python's built-in PCM reader.")

    def _browse_core(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Choose spectrogram_core.py",
            filetypes=[("Python files", "*.py"), ("All files", "*.*")],
        )
        if file_path:
            self.spectrogram_core_path_var.set(file_path)

    def _browse_input(self) -> None:
        folder = filedialog.askdirectory(title="Choose folder containing .npy/.wav files")
        if folder:
            self.input_folder_var.set(folder)
            self.output_folder_var.set(str(Path(folder) / "Spectrogram_Plots"))
            self.output_prefix_var.set(safe_stem(Path(folder).name or "spectrogram_examples"))

    def _browse_output(self) -> None:
        folder = filedialog.askdirectory(title="Choose output folder")
        if folder:
            self.output_folder_var.set(folder)

    def _parse_config(self) -> RunConfig:
        def as_int(var: tk.StringVar, name: str) -> int:
            try:
                return int(var.get().strip())
            except Exception as exc:
                raise ValueError(f"{name} must be an integer") from exc

        def as_float(var: tk.StringVar, name: str) -> float:
            try:
                return float(var.get().strip())
            except Exception as exc:
                raise ValueError(f"{name} must be a number") from exc

        core_path = self.spectrogram_core_path_var.get().strip()
        if not core_path:
            raise ValueError("Choose spectrogram_core.py before running.")

        return RunConfig(
            spectrogram_core_path=core_path,
            input_folder=self.input_folder_var.get().strip(),
            output_folder=self.output_folder_var.get().strip(),
            recursive=bool(self.recursive_var.get()),
            file_mode=self.file_mode_var.get(),
            n_files=as_int(self.n_files_var, "N files"),
            random_sample=bool(self.random_sample_var.get()),
            random_seed=as_int(self.random_seed_var, "Random seed"),
            output_type=self.output_type_var.get(),
            save_png_frames=bool(self.save_png_frames_var.get()),
            save_contact_sheet=bool(self.save_contact_sheet_var.get()),
            contact_sheet_max=as_int(self.contact_sheet_max_var, "Contact sheet max frames"),
            output_prefix=self.output_prefix_var.get().strip(),
            add_timestamp=bool(self.add_timestamp_var.get()),
            create_run_subfolder=bool(self.create_run_subfolder_var.get()),
            fs_npy_hz=as_float(self.fs_npy_var, "Sample rate for .npy"),
            raw_npy_byte_dtype=self.raw_npy_byte_dtype_var.get(),
            remove_dc=bool(self.remove_dc_var.get()),
            trim_waveform=bool(self.trim_waveform_var.get()),
            trim_start_ms=as_float(self.trim_start_ms_var, "Trim start"),
            trim_end_ms_text=self.trim_end_ms_var.get().strip(),
            t0_from_trim_start=bool(self.t0_from_trim_start_var.get()),
            t0_ms=as_float(self.t0_ms_var, "Manual T0"),
            window_length=as_int(self.window_length_var, "Window length"),
            percent_overlap=as_float(self.percent_overlap_var, "Overlap fraction"),
            nfft=as_int(self.nfft_var, "NFFT"),
            fmin_hz=as_float(self.fmin_var, "Fmin"),
            fmax_hz=as_float(self.fmax_var, "Fmax"),
            db_range=as_float(self.db_range_var, "dB range"),
            fps=as_int(self.fps_var, "FPS"),
            dpi=as_int(self.dpi_var, "DPI"),
            fig_width=as_float(self.fig_width_var, "Figure width"),
            fig_height=as_float(self.fig_height_var, "Figure height"),
            bare_bones=bool(self.bare_bones_var.get()),
            open_output_folder=bool(self.open_output_folder_var.get()),
        )

    def _start_processing(self) -> None:
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("Still running", "A spectrogram export is already running.")
            return
        try:
            cfg = self._parse_config()
        except Exception as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return

        self.run_button.configure(state="disabled")
        self.progress_bar.configure(value=0, maximum=100)
        self.progress_var.set("Starting...")
        self._append_log("\n--- New run ---")
        self.worker_thread = threading.Thread(target=self._worker, args=(cfg,), daemon=True)
        self.worker_thread.start()

    def _worker(self, cfg: RunConfig) -> None:
        def log(msg: str) -> None:
            self.queue.put(("log", msg))

        def progress(done: int, total: int) -> None:
            self.queue.put(("progress", (done, total)))

        try:
            result = run_processing(cfg, log=log, progress=progress)
            self.queue.put(("done", result))
        except Exception:
            self.queue.put(("error", traceback.format_exc()))

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "log":
                    self._append_log(str(payload))
                elif kind == "progress":
                    done, total = payload  # type: ignore[misc]
                    percent = 100.0 * float(done) / max(float(total), 1.0)
                    self.progress_bar.configure(value=percent)
                    self.progress_var.set(f"Processed {done}/{total}")
                elif kind == "done":
                    self.run_button.configure(state="normal")
                    result: ProcessResult = payload  # type: ignore[assignment]
                    if result.failed_count:
                        self.progress_var.set(f"Done with {result.failed_count} failure(s).")
                        messagebox.showwarning(
                            "Done with failures",
                            f"Rendered {result.successful_count}/{result.total_files} files.\n\nFiles are in:\n{result.output_folder}\n\nCheck the failed-files CSV for details.",
                        )
                    else:
                        self.progress_var.set("Done.")
                        messagebox.showinfo("Done", f"Rendered {result.successful_count}/{result.total_files} files.\n\nFiles are in:\n{result.output_folder}")
                    self._append_log("Output files/folders:")
                    for path in result.output_files:
                        self._append_log(f"  {path}")
                elif kind == "error":
                    self.run_button.configure(state="normal")
                    self.progress_var.set("Error.")
                    err = str(payload)
                    self._append_log(err)
                    last_line = err.splitlines()[-1] if err else "Unknown error"
                    messagebox.showerror("Error", last_line)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _append_log(self, message: str) -> None:
        self.log_text.insert("end", message + "\n")
        self.log_text.see("end")


def main() -> None:
    app = SpectrogramGui()
    app.mainloop()


if __name__ == "__main__":
    main()
