"""
Timing_QC_GUI.py

A user-friendly timing quality-control tool for echo/GPS field data.

Purpose
-------
This script helps students quickly check whether echo filenames and GPS files
have timing problems before anyone tries to synchronize the data or train a
model. It is designed for the specific failure mode where a Raspberry Pi clock
resets after shutdown/restart, causing later files to reuse/overlap earlier
filename timestamps.

What it checks
--------------
Echo data:
    - parses timestamps from filenames like 20231122_052949990.npy
    - checks for duplicate timestamps
    - checks for backward jumps in timestamp order
    - checks for large recording gaps
    - detects blocks/sessions and whether their time ranges overlap
    - compares filename timestamps to filesystem modified times as a sanity check

GPS data:
    - parses GPX files without requiring gpxpy
    - extracts GPS point times from <trkpt><time>...</time></trkpt>
    - flags empty/unparseable GPX files
    - checks GPS point time coverage and gaps
    - estimates the GPS-to-filename clock offset using GPX filename timestamps
    - checks whether echo times fall inside the GPS time coverage after offset correction

How to run
----------
    python Timing_QC_GUI.py

Required packages:
    pip install numpy matplotlib

No TensorFlow, scipy, pandas, or project src/ folder is required.
"""

from __future__ import annotations

import csv
import json
import math
import os
import queue
import re
import subprocess
import sys
import threading
import traceback
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

SECONDS_PER_DAY = 86400.0


# -----------------------------
# Data classes
# -----------------------------

@dataclass
class QcConfig:
    echo_folder: str
    gps_folder: str
    output_folder: str
    recursive: bool
    echo_patterns: str
    order_mode: str
    large_gap_s: float
    backward_jump_s: float
    overlap_tolerance_s: float
    gps_offset_warn_s: float
    gps_offset_fail_s: float
    min_echo_inside_gps_percent: float
    create_run_subfolder: bool
    output_prefix: str
    add_timestamp: bool
    open_output_folder: bool


@dataclass
class EchoFileRow:
    index_order: int
    filename: str
    relative_path: str
    absolute_path: str
    folder: str
    suffix: str
    size_bytes: int
    timestamp_epoch: Optional[float]
    timestamp_text: str
    file_mtime_epoch: float
    file_mtime_text: str
    parse_ok: bool
    parse_error: str


@dataclass
class GpsFileRow:
    index_order: int
    filename: str
    relative_path: str
    absolute_path: str
    size_bytes: int
    filename_time_epoch: Optional[float]
    filename_time_text: str
    file_mtime_epoch: float
    file_mtime_text: str
    point_count: int
    first_gps_epoch: Optional[float]
    first_gps_text: str
    last_gps_epoch: Optional[float]
    last_gps_text: str
    duration_s: Optional[float]
    offset_last_gps_minus_filename_s: Optional[float]
    status: str
    parse_error: str


@dataclass
class EchoBlock:
    block_id: int
    start_order_index: int
    end_order_index: int
    n_files: int
    start_epoch: float
    end_epoch: float
    start_text: str
    end_text: str
    duration_s: float
    median_dt_s: Optional[float]
    max_gap_s: Optional[float]
    folder: str
    start_reason: str
    overlaps_previous: bool
    status: str


@dataclass
class Issue:
    severity: str   # INFO, WARN, FAIL
    category: str
    message: str


@dataclass
class QcResults:
    overall_status: str
    issues: list[Issue]
    echo_rows: list[EchoFileRow]
    gps_rows: list[GpsFileRow]
    echo_blocks: list[EchoBlock]
    echo_dt_by_order: list[float]
    gps_all_point_epochs: list[float]
    gps_scaled_range: Optional[tuple[float, float]]
    gps_median_offset_s: Optional[float]
    echo_inside_gps_percent: Optional[float]
    output_folder: str
    output_files: list[str]


# -----------------------------
# Time parsing helpers
# -----------------------------

TIMESTAMP_PATTERNS = [
    # Echo style: 20231122_052949990, 20231122-052949990, etc.
    re.compile(r"(?P<date>\d{8})[_-](?P<hms>\d{6})(?P<frac>\d{1,6})?(?!\d)"),
    # GPS style: gpx_20231122051309, or compact echo style.
    re.compile(r"(?P<date>\d{8})(?P<hms>\d{6})(?P<frac>\d{1,6})?(?!\d)"),
]


def safe_stem(text: str) -> str:
    text = (text or "timing_qc").strip()
    text = re.sub(r"[^A-Za-z0-9_.-]+", "_", text)
    return text.strip("_") or "timing_qc"


def epoch_to_dt(epoch_s: float) -> datetime:
    return datetime.fromtimestamp(float(epoch_s), tz=timezone.utc).replace(tzinfo=None)


def fmt_epoch(epoch_s: Optional[float], include_ms: bool = True) -> str:
    if epoch_s is None or not np.isfinite(epoch_s):
        return ""
    dt = epoch_to_dt(epoch_s)
    if include_ms:
        return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def datetime_to_epoch_utc(dt: datetime) -> float:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.timestamp()


def parse_filename_timestamp(path: Path) -> tuple[Optional[float], str]:
    """Parse common field-data timestamps from a filename stem."""
    stem = path.stem
    for pattern in TIMESTAMP_PATTERNS:
        for match in pattern.finditer(stem):
            date = match.group("date")
            hms = match.group("hms")
            frac = match.group("frac") or ""
            try:
                year = int(date[0:4])
                month = int(date[4:6])
                day = int(date[6:8])
                hour = int(hms[0:2])
                minute = int(hms[2:4])
                second = int(hms[4:6])
                microsecond = int(frac.ljust(6, "0")[:6]) if frac else 0
                dt = datetime(year, month, day, hour, minute, second, microsecond, tzinfo=timezone.utc)
                return dt.timestamp(), ""
            except Exception as exc:
                return None, f"Timestamp-like text found but could not parse: {exc}"
    return None, "No YYYYMMDD_HHMMSSmmm or YYYYMMDDHHMMSS timestamp found in filename"


def parse_iso_time_to_epoch(text: str) -> Optional[float]:
    """Parse GPX ISO timestamps such as 2023-11-22T05:13:09Z."""
    if not text:
        return None
    clean = text.strip()
    if clean.endswith("Z"):
        clean = clean[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(clean).astimezone(timezone.utc).timestamp()
    except Exception:
        # Small fallback for common GPX timestamps without fractional seconds.
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(text.strip().replace("Z", ""), fmt).replace(tzinfo=timezone.utc).timestamp()
            except Exception:
                pass
    return None


# -----------------------------
# File collection/parsing
# -----------------------------

def split_patterns(patterns_text: str) -> list[str]:
    parts = re.split(r"[;,\n]+", patterns_text)
    patterns = []
    for part in parts:
        p = part.strip()
        if not p:
            continue
        if not any(ch in p for ch in "*?[]"):
            p = f"*.{p.lstrip('.')}"
        patterns.append(p)
    return patterns or ["*.npy"]


def collect_files(folder: Path, patterns: list[str], recursive: bool) -> list[Path]:
    files: set[Path] = set()
    for pattern in patterns:
        iterator = folder.rglob(pattern) if recursive else folder.glob(pattern)
        files.update(p for p in iterator if p.is_file())
    return sorted(files)


def sort_echo_paths(paths: list[Path], order_mode: str) -> list[Path]:
    mode = order_mode.lower()
    if "modified" in mode:
        return sorted(paths, key=lambda p: (p.stat().st_mtime, str(p)))
    if "filename timestamp" in mode:
        def key_name_time(p: Path):
            t, _ = parse_filename_timestamp(p)
            return (float("inf") if t is None else t, str(p))
        return sorted(paths, key=key_name_time)
    return sorted(paths, key=lambda p: str(p))


def read_echo_rows(echo_folder: Path, cfg: QcConfig) -> list[EchoFileRow]:
    patterns = split_patterns(cfg.echo_patterns)
    paths = collect_files(echo_folder, patterns, cfg.recursive)
    paths = sort_echo_paths(paths, cfg.order_mode)
    rows: list[EchoFileRow] = []

    for i, path in enumerate(paths, start=1):
        st = path.stat()
        ts, err = parse_filename_timestamp(path)
        try:
            rel = str(path.relative_to(echo_folder))
        except ValueError:
            rel = path.name
        rows.append(EchoFileRow(
            index_order=i,
            filename=path.name,
            relative_path=rel,
            absolute_path=str(path.resolve()),
            folder=str(path.parent.resolve()),
            suffix=path.suffix.lower(),
            size_bytes=int(st.st_size),
            timestamp_epoch=ts,
            timestamp_text=fmt_epoch(ts),
            file_mtime_epoch=float(st.st_mtime),
            file_mtime_text=fmt_epoch(float(st.st_mtime)),
            parse_ok=ts is not None,
            parse_error="" if ts is not None else err,
        ))
    return rows


def strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def parse_gpx_point_times(path: Path) -> tuple[list[float], str]:
    """Extract GPX trackpoint times. Falls back to any <time> tags if no trackpoints exist."""
    try:
        tree = ET.parse(path)
    except Exception as exc:
        return [], f"GPX parse error: {exc}"

    root = tree.getroot()
    times: list[float] = []

    # Prefer trackpoint times.
    for elem in root.iter():
        if strip_ns(elem.tag) != "trkpt":
            continue
        for child in elem:
            if strip_ns(child.tag) == "time" and child.text:
                t = parse_iso_time_to_epoch(child.text)
                if t is not None:
                    times.append(t)

    # Fallback for GPX files that use route points or waypoints.
    if not times:
        for elem in root.iter():
            if strip_ns(elem.tag) == "time" and elem.text:
                t = parse_iso_time_to_epoch(elem.text)
                if t is not None:
                    times.append(t)

    if not times:
        return [], "No usable GPX <time> values found"
    return times, ""


def read_gps_rows(gps_folder: Optional[Path]) -> tuple[list[GpsFileRow], list[float]]:
    if gps_folder is None or not gps_folder.exists() or not gps_folder.is_dir():
        return [], []

    paths = sorted(gps_folder.rglob("*.gpx"))
    rows: list[GpsFileRow] = []
    all_point_times: list[float] = []

    for i, path in enumerate(paths, start=1):
        st = path.stat()
        filename_time, filename_err = parse_filename_timestamp(path)
        point_times: list[float] = []
        parse_error = ""
        status = "OK"

        if st.st_size == 0:
            status = "EMPTY_FILE"
            parse_error = "File size is 0 bytes"
        else:
            point_times, parse_error = parse_gpx_point_times(path)
            if parse_error:
                status = "NO_USABLE_POINTS"

        point_times_sorted = sorted(point_times)
        all_point_times.extend(point_times_sorted)
        first = point_times_sorted[0] if point_times_sorted else None
        last = point_times_sorted[-1] if point_times_sorted else None
        duration = (last - first) if first is not None and last is not None else None
        offset = (last - filename_time) if last is not None and filename_time is not None else None

        try:
            rel = str(path.relative_to(gps_folder))
        except ValueError:
            rel = path.name

        if filename_time is None:
            status = "BAD_FILENAME_TIME" if status == "OK" else status
            parse_error = (parse_error + "; " if parse_error else "") + filename_err

        rows.append(GpsFileRow(
            index_order=i,
            filename=path.name,
            relative_path=rel,
            absolute_path=str(path.resolve()),
            size_bytes=int(st.st_size),
            filename_time_epoch=filename_time,
            filename_time_text=fmt_epoch(filename_time),
            file_mtime_epoch=float(st.st_mtime),
            file_mtime_text=fmt_epoch(float(st.st_mtime)),
            point_count=len(point_times_sorted),
            first_gps_epoch=first,
            first_gps_text=fmt_epoch(first),
            last_gps_epoch=last,
            last_gps_text=fmt_epoch(last),
            duration_s=duration,
            offset_last_gps_minus_filename_s=offset,
            status=status,
            parse_error=parse_error,
        ))

    return rows, sorted(all_point_times)


# -----------------------------
# Analysis
# -----------------------------

def detect_echo_blocks(rows: list[EchoFileRow], cfg: QcConfig) -> tuple[list[EchoBlock], list[float]]:
    parsed = [r for r in rows if r.timestamp_epoch is not None]
    if not parsed:
        return [], []

    blocks_indices: list[tuple[int, int, str]] = []
    start = 0
    start_reason = "start_of_data"
    dt_by_order: list[float] = []

    for i in range(1, len(parsed)):
        prev = parsed[i - 1]
        cur = parsed[i]
        dt = float(cur.timestamp_epoch - prev.timestamp_epoch)  # type: ignore[operator]
        dt_by_order.append(dt)

        reason = ""
        if cur.folder != prev.folder:
            reason = "folder_changed"
        if dt < -abs(cfg.backward_jump_s):
            reason = "backward_timestamp_jump"
        elif dt > cfg.large_gap_s:
            reason = "large_gap"

        if reason:
            blocks_indices.append((start, i - 1, start_reason))
            start = i
            start_reason = reason

    blocks_indices.append((start, len(parsed) - 1, start_reason))

    blocks: list[EchoBlock] = []
    previous_ranges: list[tuple[float, float]] = []
    for block_id, (a, b, reason) in enumerate(blocks_indices, start=1):
        block_rows = parsed[a:b + 1]
        times = np.array([r.timestamp_epoch for r in block_rows], dtype=float)
        start_epoch = float(np.min(times))
        end_epoch = float(np.max(times))
        dts = np.diff(times)
        median_dt = float(np.median(dts)) if len(dts) else None
        max_gap = float(np.max(dts)) if len(dts) else None
        duration = end_epoch - start_epoch

        overlaps_previous = any(start_epoch < (prev_end - cfg.overlap_tolerance_s) for _, prev_end in previous_ranges)
        previous_ranges.append((start_epoch, end_epoch))

        if overlaps_previous:
            status = "FAIL_OVERLAPS_PREVIOUS_BLOCK"
        elif reason == "backward_timestamp_jump":
            status = "FAIL_BACKWARD_JUMP_STARTED_BLOCK"
        elif reason == "large_gap":
            status = "WARN_LARGE_GAP_STARTED_BLOCK"
        else:
            status = "OK"

        folder_names = sorted({Path(r.folder).name for r in block_rows})
        blocks.append(EchoBlock(
            block_id=block_id,
            start_order_index=block_rows[0].index_order,
            end_order_index=block_rows[-1].index_order,
            n_files=len(block_rows),
            start_epoch=start_epoch,
            end_epoch=end_epoch,
            start_text=fmt_epoch(start_epoch),
            end_text=fmt_epoch(end_epoch),
            duration_s=duration,
            median_dt_s=median_dt,
            max_gap_s=max_gap,
            folder=";".join(folder_names),
            start_reason=reason,
            overlaps_previous=overlaps_previous,
            status=status,
        ))

    return blocks, dt_by_order


def analyze_results(cfg: QcConfig) -> QcResults:
    echo_folder = Path(cfg.echo_folder).expanduser().resolve()
    gps_folder_text = cfg.gps_folder.strip()
    gps_folder = Path(gps_folder_text).expanduser().resolve() if gps_folder_text else None

    if not echo_folder.exists() or not echo_folder.is_dir():
        raise FileNotFoundError(f"Echo folder not found: {echo_folder}")

    output_parent = Path(cfg.output_folder).expanduser().resolve()
    prefix = safe_stem(cfg.output_prefix or echo_folder.name)
    if cfg.add_timestamp:
        prefix = f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_folder = output_parent / prefix if cfg.create_run_subfolder else output_parent
    output_folder = make_unique_path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    echo_rows = read_echo_rows(echo_folder, cfg)
    gps_rows, gps_all_points = read_gps_rows(gps_folder)
    echo_blocks, echo_dt_by_order = detect_echo_blocks(echo_rows, cfg)

    issues: list[Issue] = []
    if not echo_rows:
        issues.append(Issue("FAIL", "echo", "No echo files were found using the selected file patterns."))
    else:
        parsed_echo = [r for r in echo_rows if r.timestamp_epoch is not None]
        unparsed = len(echo_rows) - len(parsed_echo)
        if not parsed_echo:
            issues.append(Issue("FAIL", "echo", "No echo files had parseable timestamps in their filenames."))
        elif unparsed:
            issues.append(Issue("WARN", "echo", f"{unparsed} echo file(s) did not have parseable timestamps."))

        if parsed_echo:
            timestamps_rounded_ms = [round(float(r.timestamp_epoch) * 1000.0) for r in parsed_echo]
            duplicate_count = len(timestamps_rounded_ms) - len(set(timestamps_rounded_ms))
            if duplicate_count > 0:
                issues.append(Issue("FAIL", "echo", f"{duplicate_count} duplicate echo timestamp(s) found at millisecond precision."))

        negative_jumps = [dt for dt in echo_dt_by_order if dt < -1e-6]
        backward_jumps = [dt for dt in echo_dt_by_order if dt < -abs(cfg.backward_jump_s)]
        large_gaps = [dt for dt in echo_dt_by_order if dt > cfg.large_gap_s]
        if backward_jumps:
            issues.append(Issue("FAIL", "echo", f"{len(backward_jumps)} backward timestamp jump(s) detected in collection order. Worst jump = {min(backward_jumps):.3f} s."))
        elif negative_jumps:
            issues.append(Issue("WARN", "echo", f"{len(negative_jumps)} small negative timestamp step(s) detected. Worst step = {min(negative_jumps):.3f} s. If files were copied/reordered, try the Filename timestamp order mode."))
        if large_gaps:
            issues.append(Issue("WARN", "echo", f"{len(large_gaps)} large timestamp gap(s) > {cfg.large_gap_s:g} s detected. Largest gap = {max(large_gaps):.3f} s."))
        if len(echo_blocks) > 1:
            issues.append(Issue("INFO", "echo", f"Echo data split into {len(echo_blocks)} detected block(s)/session(s)."))
        overlap_blocks = [b for b in echo_blocks if b.overlaps_previous]
        if overlap_blocks:
            ids = ", ".join(str(b.block_id) for b in overlap_blocks)
            issues.append(Issue("FAIL", "echo", f"Echo block(s) {ids} overlap earlier echo timestamp ranges. This is the main Pi-clock-reset failure mode."))

    gps_median_offset = None
    gps_scaled_range = None
    echo_inside_gps_percent = None

    if gps_folder is not None and gps_folder_text:
        if not gps_folder.exists() or not gps_folder.is_dir():
            issues.append(Issue("FAIL", "gps", f"GPS folder not found: {gps_folder}"))
        elif not gps_rows:
            issues.append(Issue("WARN", "gps", "No .gpx files were found in the GPS folder."))
        else:
            empty = [r for r in gps_rows if r.size_bytes == 0]
            bad = [r for r in gps_rows if r.status != "OK"]
            if empty:
                issues.append(Issue("WARN", "gps", f"{len(empty)} empty GPX file(s) found."))
            if bad:
                issues.append(Issue("WARN", "gps", f"{len(bad)} GPX file(s) had warnings/errors. Check GPS_File_Summary.csv."))
            if not gps_all_points:
                issues.append(Issue("FAIL", "gps", "No usable GPS point times were found in the GPX files."))
            else:
                gps_diffs = np.diff(np.array(sorted(gps_all_points), dtype=float))
                if len(gps_diffs):
                    gps_backward = int(np.sum(gps_diffs < -1e-6))
                    gps_large_gaps = gps_diffs[gps_diffs > cfg.large_gap_s]
                    if gps_backward:
                        issues.append(Issue("FAIL", "gps", f"GPS point times had {gps_backward} backward jump(s)."))
                    if len(gps_large_gaps):
                        issues.append(Issue("WARN", "gps", f"GPS point times had {len(gps_large_gaps)} gap(s) > {cfg.large_gap_s:g} s. Largest = {float(np.max(gps_large_gaps)):.3f} s."))

            offsets = np.array([r.offset_last_gps_minus_filename_s for r in gps_rows if r.offset_last_gps_minus_filename_s is not None], dtype=float)
            if len(offsets):
                gps_median_offset = float(np.median(offsets))
                offset_range = float(np.max(offsets) - np.min(offsets)) if len(offsets) > 1 else 0.0
                if offset_range > cfg.gps_offset_fail_s:
                    issues.append(Issue("FAIL", "gps", f"GPS-to-filename offset varies by {offset_range:.3f} s, above fail threshold {cfg.gps_offset_fail_s:g} s."))
                elif offset_range > cfg.gps_offset_warn_s:
                    issues.append(Issue("WARN", "gps", f"GPS-to-filename offset varies by {offset_range:.3f} s, above warning threshold {cfg.gps_offset_warn_s:g} s."))

            if gps_all_points and gps_median_offset is not None:
                gps_scaled_range = (min(gps_all_points) - gps_median_offset, max(gps_all_points) - gps_median_offset)
                echo_times = np.array([r.timestamp_epoch for r in echo_rows if r.timestamp_epoch is not None], dtype=float)
                if len(echo_times):
                    inside = (echo_times >= gps_scaled_range[0]) & (echo_times <= gps_scaled_range[1])
                    echo_inside_gps_percent = 100.0 * float(np.mean(inside))
                    if echo_inside_gps_percent < cfg.min_echo_inside_gps_percent:
                        issues.append(Issue("FAIL", "sync", f"Only {echo_inside_gps_percent:.1f}% of echo timestamps fall inside scaled GPS coverage. Minimum requested = {cfg.min_echo_inside_gps_percent:g}%."))

    fail_count = sum(1 for i in issues if i.severity == "FAIL")
    warn_count = sum(1 for i in issues if i.severity == "WARN")
    if fail_count:
        overall = "FAIL"
    elif warn_count:
        overall = "PASS_WITH_WARNINGS"
    else:
        overall = "PASS"

    results = QcResults(
        overall_status=overall,
        issues=issues,
        echo_rows=echo_rows,
        gps_rows=gps_rows,
        echo_blocks=echo_blocks,
        echo_dt_by_order=echo_dt_by_order,
        gps_all_point_epochs=gps_all_points,
        gps_scaled_range=gps_scaled_range,
        gps_median_offset_s=gps_median_offset,
        echo_inside_gps_percent=echo_inside_gps_percent,
        output_folder=str(output_folder),
        output_files=[],
    )

    save_outputs(results, cfg, output_folder, prefix)
    if cfg.open_output_folder:
        open_folder(output_folder)
    return results


def make_unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for i in range(2, 1000):
        candidate = path.parent / f"{path.name}_{i:02d}"
        if not candidate.exists():
            return candidate
    return path.parent / f"{path.name}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"


# -----------------------------
# Output writers
# -----------------------------

def write_dataclass_csv(path: Path, rows: Iterable[object]) -> None:
    rows = list(rows)
    with path.open("w", newline="", encoding="utf-8") as f:
        if not rows:
            f.write("empty\n")
            return
        fieldnames = list(asdict(rows[0]).keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def write_issues_csv(path: Path, issues: list[Issue]) -> None:
    write_dataclass_csv(path, issues)


def write_report(path: Path, results: QcResults, cfg: QcConfig) -> None:
    fail_count = sum(1 for i in results.issues if i.severity == "FAIL")
    warn_count = sum(1 for i in results.issues if i.severity == "WARN")
    info_count = sum(1 for i in results.issues if i.severity == "INFO")

    parsed_echo_count = sum(1 for r in results.echo_rows if r.timestamp_epoch is not None)
    parsed_gps_files = sum(1 for r in results.gps_rows if r.point_count > 0)

    lines: list[str] = []
    lines.append("==== TIMING QC REPORT ====\n")
    lines.append(f"Overall status: {results.overall_status}")
    lines.append(f"Failures: {fail_count} | Warnings: {warn_count} | Info: {info_count}\n")

    lines.append("---- Echo Summary ----")
    lines.append(f"Echo files found: {len(results.echo_rows)}")
    lines.append(f"Echo files with parsed timestamps: {parsed_echo_count}")
    lines.append(f"Detected echo blocks/sessions: {len(results.echo_blocks)}")
    if results.echo_blocks:
        for b in results.echo_blocks:
            lines.append(
                f"  Block {b.block_id}: {b.n_files} files | {b.start_text} -> {b.end_text} "
                f"| duration {b.duration_s:.3f} s | status {b.status}"
            )
    if results.echo_dt_by_order:
        dt = np.array(results.echo_dt_by_order, dtype=float)
        lines.append(
            f"Echo adjacent dt: median={np.median(dt):.3f} s, "
            f"min={np.min(dt):.3f} s, max={np.max(dt):.3f} s"
        )

    lines.append("\n---- GPS Summary ----")
    lines.append(f"GPX files found: {len(results.gps_rows)}")
    lines.append(f"GPX files with usable points: {parsed_gps_files}")
    lines.append(f"Total GPS point times: {len(results.gps_all_point_epochs)}")
    if results.gps_all_point_epochs:
        lines.append(f"Raw GPS point coverage: {fmt_epoch(min(results.gps_all_point_epochs))} -> {fmt_epoch(max(results.gps_all_point_epochs))}")
    if results.gps_median_offset_s is not None:
        lines.append(f"Median GPS-to-filename offset: {results.gps_median_offset_s:.3f} s")
    if results.gps_scaled_range is not None:
        lines.append(f"Scaled GPS coverage in echo filename clock: {fmt_epoch(results.gps_scaled_range[0])} -> {fmt_epoch(results.gps_scaled_range[1])}")
    if results.echo_inside_gps_percent is not None:
        lines.append(f"Echo timestamps inside scaled GPS coverage: {results.echo_inside_gps_percent:.1f}%")

    lines.append("\n---- Issues ----")
    if results.issues:
        for issue in results.issues:
            lines.append(f"[{issue.severity}] {issue.category}: {issue.message}")
    else:
        lines.append("No issues detected using the selected thresholds.")

    lines.append("\n---- How to interpret the biggest red flags ----")
    lines.append("FAIL: backward echo timestamp jump = likely Pi clock reset or files not ordered by true collection order.")
    lines.append("FAIL: overlapping echo blocks = two different recording sessions may reuse the same timestamp range.")
    lines.append("FAIL/WARN: GPS-to-filename offset changes = one global GPS/echo time correction may not be valid.")
    lines.append("FAIL: low echo-inside-GPS percentage = many echoes cannot be synchronized to GPS using the estimated offset.")

    lines.append("\n---- Settings ----")
    for k, v in asdict(cfg).items():
        lines.append(f"{k}: {v}")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def save_outputs(results: QcResults, cfg: QcConfig, out: Path, prefix: str) -> None:
    files: list[Path] = []

    settings_path = out / f"{prefix}_settings.json"
    settings_path.write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")
    files.append(settings_path)

    report_path = out / f"{prefix}_Timing_QC_Report.txt"
    write_report(report_path, results, cfg)
    files.append(report_path)

    echo_csv = out / f"{prefix}_Echo_File_Summary.csv"
    write_dataclass_csv(echo_csv, results.echo_rows)
    files.append(echo_csv)

    blocks_csv = out / f"{prefix}_Echo_Blocks.csv"
    write_dataclass_csv(blocks_csv, results.echo_blocks)
    files.append(blocks_csv)

    gps_csv = out / f"{prefix}_GPS_File_Summary.csv"
    write_dataclass_csv(gps_csv, results.gps_rows)
    files.append(gps_csv)

    issues_csv = out / f"{prefix}_Issues.csv"
    write_issues_csv(issues_csv, results.issues)
    files.append(issues_csv)

    summary_json = out / f"{prefix}_summary.json"
    summary_json.write_text(json.dumps({
        "overall_status": results.overall_status,
        "n_echo_files": len(results.echo_rows),
        "n_echo_parsed": sum(1 for r in results.echo_rows if r.timestamp_epoch is not None),
        "n_echo_blocks": len(results.echo_blocks),
        "n_gpx_files": len(results.gps_rows),
        "n_gps_point_times": len(results.gps_all_point_epochs),
        "gps_median_offset_s": results.gps_median_offset_s,
        "echo_inside_gps_percent": results.echo_inside_gps_percent,
        "issues": [asdict(i) for i in results.issues],
    }, indent=2), encoding="utf-8")
    files.append(summary_json)

    plot_paths = make_plots(results, out, prefix)
    files.extend(plot_paths)

    results.output_files = [str(p) for p in files]


def save_fig(fig: plt.Figure, path: Path) -> Path:
    fig.savefig(path, dpi=200, bbox_inches="tight")
    plt.close(fig)
    return path


def make_plots(results: QcResults, out: Path, prefix: str) -> list[Path]:
    saved: list[Path] = []
    parsed_echo = [r for r in results.echo_rows if r.timestamp_epoch is not None]

    if parsed_echo:
        x = np.arange(1, len(parsed_echo) + 1)
        y_dt = [epoch_to_dt(float(r.timestamp_epoch)) for r in parsed_echo]
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(x, y_dt, marker=".", linewidth=1)
        ax.set_xlabel("File order used for QC")
        ax.set_ylabel("Echo timestamp from filename")
        ax.set_title("Echo filename timestamp by file order")
        ax.grid(True, alpha=0.3)
        ax.yaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M:%S"))
        fig.autofmt_xdate()
        saved.append(save_fig(fig, out / f"{prefix}_Echo_Timestamp_By_Order.png"))

        # Filesystem modified time vs filename time.
        fig, ax = plt.subplots(figsize=(8, 8))
        ax.scatter([epoch_to_dt(r.file_mtime_epoch) for r in parsed_echo], y_dt, s=12)
        ax.set_xlabel("Filesystem modified time")
        ax.set_ylabel("Timestamp parsed from filename")
        ax.set_title("Filename time vs filesystem modified time")
        ax.grid(True, alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d\n%H:%M"))
        ax.yaxis.set_major_formatter(mdates.DateFormatter("%m-%d\n%H:%M"))
        saved.append(save_fig(fig, out / f"{prefix}_Filename_Time_vs_File_Modified_Time.png"))

    if results.echo_dt_by_order:
        dt = np.array(results.echo_dt_by_order, dtype=float)
        x = np.arange(2, len(dt) + 2)
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.plot(x, dt, marker=".", linewidth=1)
        ax.axhline(0, linestyle="--", linewidth=1)
        ax.set_xlabel("File order")
        ax.set_ylabel("Adjacent echo timestamp difference (s)")
        ax.set_title("Raw adjacent echo timestamp differences")
        ax.grid(True, alpha=0.3)
        saved.append(save_fig(fig, out / f"{prefix}_Echo_Adjacent_Differences_RAW.png"))

        finite = dt[np.isfinite(dt)]
        if finite.size:
            q1, q99 = np.percentile(finite, [1, 99])
            median = float(np.median(finite))
            spread = max(abs(q99 - q1), 1.0)
            ymin = max(min(q1 - 0.25 * spread, median - 5 * spread), -10.0)
            ymax = max(q99 + 0.25 * spread, median + 5 * spread, 1.0)
            fig, ax = plt.subplots(figsize=(12, 5))
            ax.plot(x, dt, marker=".", linewidth=1)
            ax.axhline(0, linestyle="--", linewidth=1)
            ax.set_ylim(ymin, ymax)
            ax.set_xlabel("File order")
            ax.set_ylabel("Adjacent echo timestamp difference (s)")
            ax.set_title("Zoomed adjacent echo timestamp differences")
            ax.grid(True, alpha=0.3)
            saved.append(save_fig(fig, out / f"{prefix}_Echo_Adjacent_Differences_ZOOMED.png"))

        fig, ax = plt.subplots(figsize=(8, 5))
        ax.hist(dt[np.isfinite(dt)], bins=60)
        ax.set_xlabel("Adjacent echo timestamp difference (s)")
        ax.set_ylabel("Count")
        ax.set_title("Histogram of adjacent echo timestamp differences")
        ax.grid(True, alpha=0.3)
        saved.append(save_fig(fig, out / f"{prefix}_Echo_Adjacent_Differences_Histogram.png"))

    if results.echo_blocks or results.gps_all_point_epochs:
        fig, ax = plt.subplots(figsize=(12, 5))
        y = 10
        yticks: list[float] = []
        ylabels: list[str] = []

        for block in results.echo_blocks:
            start_num = mdates.date2num(epoch_to_dt(block.start_epoch))
            width = max((block.end_epoch - block.start_epoch) / SECONDS_PER_DAY, 1.0 / SECONDS_PER_DAY)
            ax.broken_barh([(start_num, width)], (y - 3, 6))
            ax.text(start_num, y + 4, f"Echo block {block.block_id}", fontsize=8, rotation=30)
            y += 10

        if results.gps_all_point_epochs:
            gps_start = min(results.gps_all_point_epochs)
            gps_end = max(results.gps_all_point_epochs)
            start_num = mdates.date2num(epoch_to_dt(gps_start))
            width = max((gps_end - gps_start) / SECONDS_PER_DAY, 1.0 / SECONDS_PER_DAY)
            ax.broken_barh([(start_num, width)], (y - 3, 6))
            yticks.append(y); ylabels.append("Raw GPS")
            y += 10

        if results.gps_scaled_range is not None:
            start, end = results.gps_scaled_range
            start_num = mdates.date2num(epoch_to_dt(start))
            width = max((end - start) / SECONDS_PER_DAY, 1.0 / SECONDS_PER_DAY)
            ax.broken_barh([(start_num, width)], (y - 3, 6))
            yticks.append(y); ylabels.append("GPS scaled to echo clock")
            y += 10

        # Place echo block labels in y-axis too.
        yticks = [10 + 10 * i for i in range(len(results.echo_blocks))] + yticks
        ylabels = [f"Echo block {b.block_id}" for b in results.echo_blocks] + ylabels
        ax.set_yticks(yticks)
        ax.set_yticklabels(ylabels)
        ax.set_xlabel("Time")
        ax.set_title("Echo and GPS time coverage")
        ax.grid(True, axis="x", alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M:%S"))
        fig.autofmt_xdate()
        saved.append(save_fig(fig, out / f"{prefix}_Echo_vs_GPS_Coverage.png"))

    offsets = [r.offset_last_gps_minus_filename_s for r in results.gps_rows if r.offset_last_gps_minus_filename_s is not None]
    if offsets:
        x = np.arange(1, len(offsets) + 1)
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.plot(x, offsets, marker="o", linewidth=1)
        ax.set_xlabel("GPX file index")
        ax.set_ylabel("last GPS point time - GPX filename time (s)")
        ax.set_title("GPS-to-filename clock offset per GPX file")
        ax.grid(True, alpha=0.3)
        saved.append(save_fig(fig, out / f"{prefix}_GPS_Offset_Per_File.png"))

    good_gps = [r for r in results.gps_rows if r.first_gps_epoch is not None and r.last_gps_epoch is not None]
    if good_gps:
        fig, ax = plt.subplots(figsize=(12, 5))
        for i, row in enumerate(good_gps, start=1):
            start = float(row.first_gps_epoch)
            end = float(row.last_gps_epoch)
            start_num = mdates.date2num(epoch_to_dt(start))
            width = max((end - start) / SECONDS_PER_DAY, 1.0 / SECONDS_PER_DAY)
            ax.broken_barh([(start_num, width)], (i - 0.4, 0.8))
        ax.set_xlabel("GPS point time")
        ax.set_ylabel("GPX file index")
        ax.set_title("GPS point time span for each GPX file")
        ax.grid(True, axis="x", alpha=0.3)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M:%S"))
        fig.autofmt_xdate()
        saved.append(save_fig(fig, out / f"{prefix}_GPS_File_Time_Spans.png"))

    return saved


def open_folder(path: Path) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception:
        pass


# -----------------------------
# GUI
# -----------------------------

class TimingQcGui(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Echo/GPS Timing QC")
        self.geometry("920x760")
        self.minsize(840, 660)
        self.queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.worker: Optional[threading.Thread] = None
        self._build_vars()
        self._build_layout()
        self.after(100, self._poll_queue)

    def _build_vars(self) -> None:
        cwd = Path.cwd()
        self.echo_folder_var = tk.StringVar(value=str(cwd))
        self.gps_folder_var = tk.StringVar(value="")
        self.output_folder_var = tk.StringVar(value=str(cwd / "Timing_QC_Outputs"))
        self.recursive_var = tk.BooleanVar(value=True)
        self.echo_patterns_var = tk.StringVar(value="*.npy;*.wav")
        self.order_mode_var = tk.StringVar(value="Filesystem modified time (recommended)")
        self.large_gap_var = tk.StringVar(value="30")
        self.backward_jump_var = tk.StringVar(value="0.1")
        self.overlap_tolerance_var = tk.StringVar(value="1")
        self.gps_offset_warn_var = tk.StringVar(value="2")
        self.gps_offset_fail_var = tk.StringVar(value="10")
        self.min_inside_gps_var = tk.StringVar(value="95")
        self.create_run_subfolder_var = tk.BooleanVar(value=True)
        self.output_prefix_var = tk.StringVar(value="timing_qc")
        self.add_timestamp_var = tk.BooleanVar(value=True)
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

        self._folders_section()
        self._settings_section()
        self._run_section()

    def _section(self, title: str) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(self.content, text=title, padding=10)
        frame.pack(fill="x", expand=True, pady=(0, 10))
        frame.columnconfigure(1, weight=1)
        return frame

    def _folders_section(self) -> None:
        frame = self._section("Folders")

        ttk.Label(frame, text="Echo data folder").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.echo_folder_var).grid(row=0, column=1, sticky="we", pady=4)
        ttk.Button(frame, text="Browse...", command=self._browse_echo).grid(row=0, column=2, padx=(8, 0), pady=4)

        ttk.Label(frame, text="GPS data folder (optional)").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.gps_folder_var).grid(row=1, column=1, sticky="we", pady=4)
        ttk.Button(frame, text="Browse...", command=self._browse_gps).grid(row=1, column=2, padx=(8, 0), pady=4)
        ttk.Button(frame, text="Clear", command=lambda: self.gps_folder_var.set("")).grid(row=1, column=3, padx=(8, 0), pady=4)

        ttk.Label(frame, text="Output folder").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.output_folder_var).grid(row=2, column=1, sticky="we", pady=4)
        ttk.Button(frame, text="Browse...", command=self._browse_output).grid(row=2, column=2, padx=(8, 0), pady=4)

    def _settings_section(self) -> None:
        frame = self._section("Timing QC settings")
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, weight=1)

        ttk.Label(frame, text="Echo file patterns").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.echo_patterns_var).grid(row=0, column=1, sticky="we", pady=4)
        ttk.Checkbutton(frame, text="Search subfolders", variable=self.recursive_var).grid(row=0, column=2, columnspan=2, sticky="w", padx=(16, 0), pady=4)

        ttk.Label(frame, text="File order for QC").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Combobox(
            frame,
            textvariable=self.order_mode_var,
            values=[
                "Filesystem modified time (recommended)",
                "Filename timestamp",
                "Full path/name",
            ],
            state="readonly",
            width=34,
        ).grid(row=1, column=1, sticky="w", pady=4)

        self._entry(frame, 2, 0, "Large gap threshold (s)", self.large_gap_var)
        self._entry(frame, 2, 2, "Backward jump threshold (s)", self.backward_jump_var)
        self._entry(frame, 3, 0, "Block overlap tolerance (s)", self.overlap_tolerance_var)
        self._entry(frame, 3, 2, "Min echo inside GPS (%)", self.min_inside_gps_var)
        self._entry(frame, 4, 0, "GPS offset warn (s)", self.gps_offset_warn_var)
        self._entry(frame, 4, 2, "GPS offset fail (s)", self.gps_offset_fail_var)

        ttk.Label(frame, text="Output prefix").grid(row=5, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(frame, textvariable=self.output_prefix_var).grid(row=5, column=1, sticky="we", pady=4)
        ttk.Checkbutton(frame, text="Add timestamp", variable=self.add_timestamp_var).grid(row=5, column=2, sticky="w", padx=(16, 0), pady=4)

        ttk.Checkbutton(frame, text="Put all outputs in one new run folder", variable=self.create_run_subfolder_var).grid(row=6, column=0, columnspan=3, sticky="w", pady=4)
        ttk.Checkbutton(frame, text="Open output folder when done", variable=self.open_output_folder_var).grid(row=7, column=0, columnspan=3, sticky="w", pady=4)

    def _entry(self, parent: ttk.LabelFrame, row: int, col: int, label: str, var: tk.StringVar) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=col, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(parent, textvariable=var, width=12).grid(row=row, column=col + 1, sticky="w", pady=4)

    def _run_section(self) -> None:
        frame = self._section("Run")
        self.run_button = ttk.Button(frame, text="Analyze timing", command=self._start)
        self.run_button.grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.progress_var = tk.StringVar(value="Ready.")
        ttk.Label(frame, textvariable=self.progress_var).grid(row=0, column=1, sticky="w", padx=(12, 0), pady=(0, 8))
        self.log = tk.Text(frame, height=18, wrap="word")
        self.log.grid(row=1, column=0, columnspan=3, sticky="nsew")
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(1, weight=1)
        self._append_log("Choose an echo folder, optionally choose a GPS folder, then click Analyze timing.")

    def _browse_echo(self) -> None:
        folder = filedialog.askdirectory(title="Choose Echo_Data folder")
        if folder:
            self.echo_folder_var.set(folder)
            self.output_folder_var.set(str(Path(folder) / "Timing_QC_Outputs"))
            self.output_prefix_var.set(safe_stem(Path(folder).name or "timing_qc"))

    def _browse_gps(self) -> None:
        folder = filedialog.askdirectory(title="Choose GPS_Data folder")
        if folder:
            self.gps_folder_var.set(folder)

    def _browse_output(self) -> None:
        folder = filedialog.askdirectory(title="Choose output folder")
        if folder:
            self.output_folder_var.set(folder)

    def _parse_float(self, var: tk.StringVar, name: str) -> float:
        try:
            return float(var.get().strip())
        except Exception as exc:
            raise ValueError(f"{name} must be a number") from exc

    def _config(self) -> QcConfig:
        return QcConfig(
            echo_folder=self.echo_folder_var.get().strip(),
            gps_folder=self.gps_folder_var.get().strip(),
            output_folder=self.output_folder_var.get().strip(),
            recursive=bool(self.recursive_var.get()),
            echo_patterns=self.echo_patterns_var.get().strip(),
            order_mode=self.order_mode_var.get(),
            large_gap_s=self._parse_float(self.large_gap_var, "Large gap threshold"),
            backward_jump_s=self._parse_float(self.backward_jump_var, "Backward jump threshold"),
            overlap_tolerance_s=self._parse_float(self.overlap_tolerance_var, "Block overlap tolerance"),
            gps_offset_warn_s=self._parse_float(self.gps_offset_warn_var, "GPS offset warn"),
            gps_offset_fail_s=self._parse_float(self.gps_offset_fail_var, "GPS offset fail"),
            min_echo_inside_gps_percent=self._parse_float(self.min_inside_gps_var, "Min echo inside GPS"),
            create_run_subfolder=bool(self.create_run_subfolder_var.get()),
            output_prefix=self.output_prefix_var.get().strip(),
            add_timestamp=bool(self.add_timestamp_var.get()),
            open_output_folder=bool(self.open_output_folder_var.get()),
        )

    def _start(self) -> None:
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("Still running", "Timing QC is already running.")
            return
        try:
            cfg = self._config()
        except Exception as exc:
            messagebox.showerror("Invalid settings", str(exc))
            return
        self.run_button.configure(state="disabled")
        self.progress_var.set("Running...")
        self._append_log("\n--- New timing QC run ---")
        self.worker = threading.Thread(target=self._worker, args=(cfg,), daemon=True)
        self.worker.start()

    def _worker(self, cfg: QcConfig) -> None:
        try:
            results = analyze_results(cfg)
            self.queue.put(("done", results))
        except Exception:
            self.queue.put(("error", traceback.format_exc()))

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "done":
                    results: QcResults = payload  # type: ignore[assignment]
                    self.run_button.configure(state="normal")
                    self.progress_var.set(results.overall_status)
                    self._append_log(f"Overall status: {results.overall_status}")
                    self._append_log(f"Output folder: {results.output_folder}")
                    for issue in results.issues:
                        self._append_log(f"[{issue.severity}] {issue.category}: {issue.message}")
                    messagebox.showinfo(
                        "Timing QC finished",
                        f"Overall status: {results.overall_status}\n\nFiles are in:\n{results.output_folder}",
                    )
                elif kind == "error":
                    self.run_button.configure(state="normal")
                    self.progress_var.set("Error")
                    err = str(payload)
                    self._append_log(err)
                    messagebox.showerror("Timing QC error", err.splitlines()[-1] if err else "Unknown error")
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _append_log(self, msg: str) -> None:
        self.log.insert("end", msg + "\n")
        self.log.see("end")


def main() -> None:
    app = TimingQcGui()
    app.mainloop()


if __name__ == "__main__":
    main()
