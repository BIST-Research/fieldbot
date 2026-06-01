from __future__ import annotations
from pathlib import Path
import os
import subprocess
import imageio.v2 as imageio

# ===== EDIT THESE =====
FOLDER = Path(r"C:\Users\adamh\Desktop\Phase_Space\Plots\Example_Spectrograms")  # folder containing .gif files
OUT_SUBFOLDER = "slower"   # outputs go into FOLDER\slower
NEW_FPS = 4                # lower = slower (e.g. 2, 3, 4, 6)
# ======================

out_dir = (FOLDER / OUT_SUBFOLDER).resolve()
out_dir.mkdir(parents=True, exist_ok=True)

gifs = sorted(FOLDER.glob("*.gif"))
if not gifs:
    raise SystemExit(f"No .gif files found in: {FOLDER}")

first_out = None

for gif in gifs:
    reader = imageio.get_reader(gif)
    frames = [frame for frame in reader]
    reader.close()

    out_path = out_dir / gif.name
    if first_out is None:
        first_out = out_path

    imageio.mimsave(out_path, frames, fps=NEW_FPS)
    print(f"Saved: {out_path}")

print(f"\nDone. Output folder: {out_dir}")

# --- Open File Explorer to the output folder (Windows) ---
try:
    # Open folder
    os.startfile(str(out_dir))

    # Also select the first output file (optional, nicer UX)
    if first_out is not None and first_out.exists():
        subprocess.run(["explorer", "/select,", str(first_out)], check=False)
except Exception as e:
    print(f"(Could not open File Explorer automatically: {e})")