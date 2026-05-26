"""
QRNG Visualizer — Real-Time Quantum Randomness Dashboard
=========================================================
Performance architecture
  • PIL/ImageDraw pixel rendering for Bitstream, Scatter, Poincaré, ByteDist
    — one PhotoImage canvas item instead of thousands of ovals/rectangles
  • Only the ACTIVE tab is redrawn each tick (hidden tabs are skipped)
  • Dirty flag: redraws are skipped entirely if no new bytes arrived
  • Rates tuned to Arduino hardware: ~625 bytes/s (8 reads × 200 µs)
  • Serial thread reads raw binary (Serial.write) — no ASCII parsing
  • Numpy used for byte stats when available; pure-Python fallback otherwise

Port / baud: change COM_PORT / BAUD_RATE below
"""

import tkinter as tk
from tkinter import ttk
import threading
import collections
import math
import time
import random

try:
    import serial
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

try:
    from PIL import Image, ImageDraw
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

# ── User config ───────────────────────────────────────────────────────────────
COM_PORT   = "COM10"
BAUD_RATE  = 115200

# Seconds of timestamped data kept in scatter / poincare plots
WINDOW_SEC = 20.0

# Master redraw interval (ms). At 625 bytes/s new data arrives every ~1.6 ms
# so 100 ms gives ~60 new bytes per frame — plenty of visual change.
# Raise to 200+ on slow machines.
REDRAW_MS  = 120

# Tab names that use PIL pixel rendering (fast) vs Tk item rendering (light)
PIL_TABS   = {"bitstream", "scatter", "poincare", "bytedist"}

MAX_BYTES  = 20_000   # ring-buffer depth — ~32 s at 625 bytes/s
MAX_BITS   = MAX_BYTES * 8

# ── Palette ───────────────────────────────────────────────────────────────────
BG        = "#0a0a0f"
PANEL     = "#111118"
BORDER    = "#1e1e2e"
ACCENT    = "#00ffcc"
ACCENT2   = "#7c3aed"
ACCENT3   = "#f97316"
TEXT      = "#e2e8f0"
SUBTEXT   = "#64748b"
GRID      = "#1a1a2a"
FONT_MONO = ("Courier New", 10)
FONT_UI   = ("Segoe UI", 10)
FONT_H    = ("Segoe UI", 12, "bold")
FONT_BIG  = ("Courier New", 22, "bold")


# ── Timestamped data store ────────────────────────────────────────────────────
class DataStore:
    """
    Thread-safe ring buffer.
    bytes_ stores (timestamp, value) tuples so plots can age-filter.
    bits  stores raw 0/1 for fast bit-level analysis.
    dirty counts total bytes ever pushed — drawers compare against their last
    seen value and skip the redraw if nothing new arrived.
    """
    def __init__(self, max_bytes=MAX_BYTES):
        self.max_bytes = max_bytes
        self._bytes: collections.deque = collections.deque()
        self._bits:  collections.deque = collections.deque()
        self.lock    = threading.Lock()
        self.total   = 0   # all-time bits received
        self.ones    = 0
        self.dirty   = 0   # increments with every push_many call

    def push_many(self, data: bytes):
        ts = time.monotonic()
        with self.lock:
            for val in data:
                self._bytes.append((ts, val))
                for i in range(8):
                    b = (val >> i) & 1
                    self._bits.append(b)
                    self.total += 1
                    if b:
                        self.ones += 1
            trim_b = max(0, len(self._bytes) - self.max_bytes)
            for _ in range(trim_b):
                self._bytes.popleft()
            trim_bits = max(0, len(self._bits) - MAX_BITS)
            for _ in range(trim_bits):
                self._bits.popleft()
            self.dirty += 1

    def snapshot_all(self):
        with self.lock:
            bl  = list(self._bits)
            bvl = [v for _, v in self._bytes]
            tsl = [t for t, _ in self._bytes]
            return bl, bvl, tsl, self.total, self.ones

    def snapshot_window(self, seconds: float):
        now = time.monotonic()
        cutoff = now - seconds
        with self.lock:
            pairs = [(t, v) for t, v in self._bytes if t >= cutoff]
        if pairs:
            ts, vals = zip(*pairs)
            return list(vals), list(ts)
        return [], []

    def snapshot_bits(self, n=None):
        with self.lock:
            bl = list(self._bits)
        return bl if n is None else bl[-n:]


# ── Serial / Demo reader ──────────────────────────────────────────────────────
class SerialReader(threading.Thread):
    def __init__(self, store: DataStore, port=COM_PORT, baud=BAUD_RATE):
        super().__init__(daemon=True, name="SerialReader")
        self.store   = store
        self.port    = port
        self.baud    = baud
        self.running = True
        self.status  = "Connecting…"
        self.error   = None
        self.live    = False

    def run(self):
        if not SERIAL_AVAILABLE:
            self.status = "DEMO MODE  (pyserial not installed)"
            self._demo()
            return
        try:
            # Arduino uses Serial.write(value) → raw binary, one byte per sample.
            # We read the bytes directly — no ASCII decoding, no bit-string parsing.
            ser = serial.Serial(self.port, self.baud, timeout=0.05)
            # Flush any boot garbage (Arduino bootloader noise)
            time.sleep(0.1)
            ser.reset_input_buffer()
            self.status = f"Connected  {self.port}  @{self.baud}  [binary mode]"
            self.live = True

            # Expected throughput:
            #   8 digitalRead × 200 µs delay = 1.6 ms/byte ≈ 625 bytes/s ≈ 5 kbit/s
            # We read whatever is waiting and push it in one batch.
            while self.running:
                waiting = ser.in_waiting
                if waiting:
                    raw = ser.read(waiting)   # raw bytes — already fully assembled
                    self.store.push_many(raw)
                else:
                    time.sleep(0.001)
        except Exception as e:
            self.error  = str(e)
            self.status = f"Serial error: {e}  →  Demo mode"
            self._demo()

    def _demo(self):
        """
        Mimics the Arduino firmware rate:
          8 digitalRead x 200 us = 1.6 ms/byte -> ~625 bytes/s ~ 5 kbit/s.
        Sends small bursts every ~16 ms (~10 bytes/burst) to match that pace.
        """
        while self.running:
            burst = bytes(random.getrandbits(8) for _ in range(random.randint(8, 12)))
            self.store.push_many(burst)
            time.sleep(0.016)

    def stop(self):
        self.running = False


# ── Canvas helpers ────────────────────────────────────────────────────────────
def canvas_wh(canvas: tk.Canvas):
    canvas.update_idletasks()
    w = canvas.winfo_width()
    h = canvas.winfo_height()
    return max(w, 100), max(h, 100)

def clear_canvas(canvas: tk.Canvas):
    w, h = canvas_wh(canvas)
    canvas.delete("all")
    canvas.create_rectangle(0, 0, w, h, fill=PANEL, outline="")
    return w, h

def draw_grid_tk(canvas, w, h, nx=8, ny=6):
    for i in range(1, nx):
        canvas.create_line(i*w/nx, 0, i*w/nx, h, fill=GRID)
    for j in range(1, ny):
        canvas.create_line(0, j*h/ny, w, j*h/ny, fill=GRID)

def hex_to_rgb(h: str):
    return int(h[1:3],16), int(h[3:5],16), int(h[5:7],16)

PANEL_RGB  = hex_to_rgb(PANEL)
ACCENT_RGB = hex_to_rgb(ACCENT)   # (0,255,204)
ACCENT2_RGB= hex_to_rgb(ACCENT2)
ACCENT3_RGB= hex_to_rgb(ACCENT3)
GRID_RGB   = hex_to_rgb(GRID)


def make_pil_image(w, h):
    """Return a blank PIL image filled with PANEL colour."""
    img = Image.new("RGB", (w, h), PANEL_RGB)
    return img, ImageDraw.Draw(img)


def pil_to_photo(canvas, img, photo_attr):
    """
    Convert PIL image to Tk PhotoImage and display as single canvas item.
    Stores the PhotoImage on `canvas` under `photo_attr` to prevent GC.
    Returns the PhotoImage.
    """
    from PIL import ImageTk
    photo = ImageTk.PhotoImage(img)
    setattr(canvas, photo_attr, photo)   # keep reference
    canvas.delete("all")
    canvas.create_image(0, 0, anchor="nw", image=photo)
    return photo


# ── Individual tab drawers ────────────────────────────────────────────────────
class TabDrawer:
    """
    Base class.
    _last_dirty tracks the store.dirty value at last draw so we can skip
    frames where no new data arrived.
    """
    def __init__(self, canvas: tk.Canvas, store: DataStore, app):
        self.canvas      = canvas
        self.store       = store
        self.app         = app
        self._last_dirty = -1

    def has_new_data(self):
        d = self.store.dirty
        if d == self._last_dirty:
            return False
        self._last_dirty = d
        return True

    def draw(self):
        raise NotImplementedError


# ─── Bitstream — PIL pixel grid ───────────────────────────────────────────────
class BitstreamDrawer(TabDrawer):
    """Each bit = one pixel block. Drawn entirely in PIL — single canvas item."""

    ONE_NEW  = (0, 255, 204)    # ACCENT
    ONE_OLD  = (0,  64,  46)
    ZERO_NEW = (30,  58,  95)
    ZERO_OLD = (10,  10,  15)

    def _lerp(self, a, b, t):
        return tuple(int(a[i] + (b[i]-a[i])*t) for i in range(3))

    def draw(self):
        if not self.has_new_data():
            return
        c = self.canvas
        w, h = canvas_wh(c)
        bits = self.store.snapshot_bits()
        if not bits:
            clear_canvas(c)
            c.create_text(w//2, h//2, text="Waiting for data…",
                          fill=SUBTEXT, font=("Segoe UI", 11))
            return

        cell = max(3, min(12, w // 100))
        cols = max(1, w // cell)
        rows = max(1, h // cell)
        show = bits[-(cols * rows):]

        if not PIL_AVAILABLE:
            # Fallback: plain Tk rects (slow but works without Pillow)
            c.delete("all")
            c.create_rectangle(0, 0, w, h, fill=PANEL, outline="")
            for idx, b in enumerate(show):
                ci, ri = idx % cols, idx // cols
                age = ri / max(rows-1, 1)
                col = "#00ffcc" if (b and age < 0.5) else ("#004433" if b else ("#1e3a5f" if age < 0.5 else "#0a0a0f"))
                c.create_rectangle(ci*cell, ri*cell, ci*cell+cell-1, ri*cell+cell-1, fill=col, outline="")
            return

        img = Image.new("RGB", (w, h), PANEL_RGB)
        pix = img.load()
        for idx, b in enumerate(show):
            ci, ri = idx % cols, idx // cols
            age = ri / max(rows-1, 1)
            color = self._lerp(self.ONE_NEW, self.ONE_OLD, age) if b \
                    else self._lerp(self.ZERO_NEW, self.ZERO_OLD, age)
            x0, y0 = ci*cell, ri*cell
            for dy in range(cell-1):
                for dx in range(cell-1):
                    if x0+dx < w and y0+dy < h:
                        pix[x0+dx, y0+dy] = color

        pil_to_photo(c, img, "_bs_photo")

        # Overlay text labels via Tk (cheap — just 3 items)
        ones  = sum(show)
        zeros = len(show) - ones
        c.create_text(8, h-6, anchor="sw",
                      text=f"1s:{ones}  0s:{zeros}  showing {len(show)} bits",
                      fill=SUBTEXT, font=("Courier New", 9))


# ─── Histogram — lightweight Tk (only 2 bars) ─────────────────────────────────
class HistogramDrawer(TabDrawer):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._smooth = [0.0, 0.0]

    def draw(self):
        if not self.has_new_data():
            return
        c = self.canvas
        w, h = clear_canvas(c)
        _, _, _, total, ones = self.store.snapshot_all()
        zeros = total - ones
        mx    = max(ones, zeros, 1)

        alpha = 0.18
        self._smooth[0] += alpha * (zeros/mx - self._smooth[0])
        self._smooth[1] += alpha * (ones /mx - self._smooth[1])

        draw_grid_tk(c, w, h, 2, 8)
        pad_l = max(60, w//10); pad_b = 40; gap = 20
        bw = max(40, (w - 2*pad_l - gap) // 2)
        uh = h - pad_b - 30

        for val, count, sh, color, label in [
            (0, zeros, self._smooth[0], ACCENT2, "Bit '0'"),
            (1, ones,  self._smooth[1], ACCENT,  "Bit '1'"),
        ]:
            x0 = pad_l + val*(bw+gap)
            bh = int(sh * uh)
            y0 = h - pad_b - bh
            c.create_rectangle(x0+4, y0+4, x0+bw+4, h-pad_b+4, fill="#000", outline="")
            c.create_rectangle(x0, y0, x0+bw, h-pad_b, fill=color, outline="")
            c.create_text(x0+bw//2, max(14, y0-16),
                          text=f"{count:,}", fill=TEXT, font=("Courier New", 12, "bold"))
            if bh > 30:
                pct = count/total*100 if total else 0
                c.create_text(x0+bw//2, y0+18,
                              text=f"{pct:.2f}%", fill=BG, font=("Courier New", 11, "bold"))
            c.create_text(x0+bw//2, h-pad_b+16, text=label, fill=SUBTEXT, font=("Segoe UI", 10))

        iy = h - pad_b - int(0.5*uh)
        c.create_line(pad_l-10, iy, pad_l+2*bw+gap+10, iy, fill=ACCENT3, dash=(6,4))
        c.create_text(w-8, iy-9, text="ideal 50%", fill=ACCENT3, font=("Segoe UI", 8), anchor="e")
        for frac in [0, 0.25, 0.5, 0.75, 1.0]:
            yy = h-pad_b-int(frac*uh)
            c.create_text(pad_l-6, yy, text=f"{int(frac*mx):,}",
                          fill=SUBTEXT, font=("Segoe UI", 8), anchor="e")


# ─── Byte Distribution — PIL pixel columns ────────────────────────────────────
class ByteDistDrawer(TabDrawer):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._smooth = [0.0] * 256

    def draw(self):
        if not self.has_new_data():
            return
        c = self.canvas
        w, h = canvas_wh(c)
        bytes_vals, _ = self.store.snapshot_window(WINDOW_SEC)
        if len(bytes_vals) < 4:
            clear_canvas(c)
            c.create_text(w//2, h//2, text="Collecting data…", fill=SUBTEXT, font=("Segoe UI", 11))
            return

        freq = [0]*256
        for b in bytes_vals:
            freq[b] += 1
        mx = max(freq) or 1
        alpha = 0.14
        for i in range(256):
            self._smooth[i] += alpha * (freq[i]/mx - self._smooth[i])

        pad_l = 24; pad_b = 28
        uw = w - pad_l - 8
        uh = h - pad_b - 10

        if not PIL_AVAILABLE:
            c.delete("all"); c.create_rectangle(0, 0, w, h, fill=PANEL, outline="")
            bw = uw/256
            for i, sh in enumerate(self._smooth):
                bh = max(1, int(sh*uh))
                x0 = pad_l + i*bw
                r  = int(i*0.6); g = max(0,min(255,80+i)); bc = max(0,min(255,200-i//2))
                c.create_rectangle(x0, h-pad_b-bh, x0+bw, h-pad_b, fill=f"#{r:02x}{g:02x}{bc:02x}", outline="")
            return

        img, draw = make_pil_image(w, h)
        bw = uw / 256
        for i, sh in enumerate(self._smooth):
            bh = max(1, int(sh * uh))
            x0 = int(pad_l + i*bw); x1 = int(pad_l + (i+1)*bw)
            y0 = h - pad_b - bh;    y1 = h - pad_b
            r  = int(i*0.6); g = max(0,min(255,80+i)); bc = max(0,min(255,200-i//2))
            draw.rectangle([x0, y0, x1, y1], fill=(r, g, bc))

        # Grid lines on top
        for j in range(1, 6):
            y = int(j * h / 6)
            draw.line([(0,y),(w,y)], fill=GRID_RGB)
        for i in range(1, 8):
            x = int(i * w / 8)
            draw.line([(x,0),(x,h)], fill=GRID_RGB)

        pil_to_photo(c, img, "_bd_photo")

        # Axis labels via Tk
        for v in [0, 64, 128, 192, 255]:
            x = int(pad_l + v*bw)
            c.create_text(x, h-12, text=str(v), fill=SUBTEXT, font=("Segoe UI", 8))
        c.create_text(8, 8, anchor="nw",
                      text=f"n={len(bytes_vals)} bytes  window={WINDOW_SEC:.0f}s",
                      fill=SUBTEXT, font=("Segoe UI", 8))


# ─── Poincaré — PIL pixel dots ────────────────────────────────────────────────
class PoincareDrawer(TabDrawer):
    def draw(self):
        if not self.has_new_data():
            return
        c = self.canvas
        w, h = canvas_wh(c)
        bytes_vals, ts_list = self.store.snapshot_window(WINDOW_SEC)
        if len(bytes_vals) < 4:
            clear_canvas(c)
            c.create_text(w//2, h//2, text="Collecting data…", fill=SUBTEXT, font=("Segoe UI", 11))
            return

        pad = 24
        pw  = w - 2*pad; ph = h - 2*pad
        sx  = pw / 255.0; sy = ph / 255.0
        now = time.monotonic()
        n   = len(bytes_vals)

        if not PIL_AVAILABLE:
            clear_canvas(c); draw_grid_tk(c, w, h)
            for i in range(n-1):
                t   = 1.0 - (now - ts_list[i]) / WINDOW_SEC
                t   = max(0.0, min(1.0, t))
                x   = pad + bytes_vals[i]*sx
                y   = h - pad - bytes_vals[i+1]*sy
                g   = int(60+t*195); b2 = int(60+t*100)
                c.create_oval(x-1,y-1,x+1,y+1, fill=f"#00{g:02x}{b2:02x}", outline="")
            return

        img = Image.new("RGB", (w, h), PANEL_RGB)
        pix = img.load()
        for i in range(n-1):
            t  = 1.0 - (now - ts_list[i]) / WINDOW_SEC
            t  = max(0.0, min(1.0, t))
            px = int(pad + bytes_vals[i]   * sx)
            py = int(h - pad - bytes_vals[i+1] * sy)
            g  = int(60 + t*195); b2 = int(60 + t*100)
            for dy in range(-1, 2):
                for dx in range(-1, 2):
                    nx2 = px+dx; ny2 = py+dy
                    if 0 <= nx2 < w and 0 <= ny2 < h:
                        pix[nx2, ny2] = (0, g, b2)

        pil_to_photo(c, img, "_pc_photo")
        c.create_text(w//2, h-6,  text="x(n)",    fill=SUBTEXT, font=("Segoe UI", 8))
        c.create_text(10,   h//2, text="x(n+1)",  fill=SUBTEXT, font=("Segoe UI", 8), angle=90)
        c.create_text(w-6, 8, anchor="ne",
                      text=f"n={n}  {WINDOW_SEC:.0f}s window",
                      fill=SUBTEXT, font=("Segoe UI", 8))


# ─── Scatter — PIL pixel dots ─────────────────────────────────────────────────
class ScatterDrawer(TabDrawer):
    def draw(self):
        if not self.has_new_data():
            return
        c = self.canvas
        w, h = canvas_wh(c)
        bytes_vals, ts_list = self.store.snapshot_window(WINDOW_SEC)
        if len(bytes_vals) < 4:
            clear_canvas(c)
            c.create_text(w//2, h//2, text="Collecting data…", fill=SUBTEXT, font=("Segoe UI", 11))
            return

        pad = 24
        pw  = w - 2*pad; ph = h - 2*pad
        sx  = pw / 255.0; sy = ph / 255.0
        now = time.monotonic()
        n_pairs = len(bytes_vals) // 2

        if not PIL_AVAILABLE:
            clear_canvas(c); draw_grid_tk(c, w, h)
            for i in range(n_pairs):
                bx  = bytes_vals[i*2]; by = bytes_vals[i*2+1]
                t   = 1.0-(now-ts_list[i*2])/WINDOW_SEC; t = max(0,min(1,t))
                x   = pad+bx*sx; y = h-pad-by*sy
                g   = min(255,int(80+t*175)); b2 = min(255,int(60+t*140))
                c.create_oval(x-1,y-1,x+1,y+1, fill=f"#00{g:02x}{b2:02x}", outline="")
            return

        img = Image.new("RGB", (w, h), PANEL_RGB)
        pix = img.load()
        for i in range(n_pairs):
            bx  = bytes_vals[i*2]; by = bytes_vals[i*2+1]
            t   = 1.0 - (now - ts_list[i*2]) / WINDOW_SEC
            t   = max(0.0, min(1.0, t))
            px  = int(pad + bx * sx)
            py  = int(h - pad - by * sy)
            rv  = int((1-t)*20); gv = min(255,int(80+t*175)); bv = min(255,int(60+t*140))
            for dy in range(-1, 2):
                for dx in range(-1, 2):
                    nx2 = px+dx; ny2 = py+dy
                    if 0 <= nx2 < w and 0 <= ny2 < h:
                        pix[nx2, ny2] = (rv, gv, bv)

        pil_to_photo(c, img, "_sc_photo")
        c.create_text(w//2, h-6,  text="byte[2n]",   fill=SUBTEXT, font=("Segoe UI", 8))
        c.create_text(10,   h//2, text="byte[2n+1]", fill=SUBTEXT, font=("Segoe UI", 8), angle=90)


# ─── Runs — lightweight Tk (20 bars) ──────────────────────────────────────────
class RunsDrawer(TabDrawer):
    def draw(self):
        if not self.has_new_data():
            return
        c = self.canvas
        w, h = clear_canvas(c)
        bits = self.store.snapshot_bits(4000)   # 4k bits is plenty for runs
        if len(bits) < 10:
            c.create_text(w//2, h//2, text="Collecting data…", fill=SUBTEXT, font=("Segoe UI", 11))
            return

        runs = []; cur_val = bits[0]; cur_len = 1
        for b in bits[1:]:
            if b == cur_val: cur_len += 1
            else: runs.append(cur_len); cur_val = b; cur_len = 1
        runs.append(cur_len)

        MAX_SHOW = 20
        freq = [0]*(MAX_SHOW+1)
        for r in runs:
            if r <= MAX_SHOW: freq[r] += 1

        draw_grid_tk(c, w, h)
        pad_l = 50; pad_b = 36; pad_t = 20
        uh = h-pad_b-pad_t; mx = max(freq[1:], default=1)
        bw = (w-pad_l-20)/MAX_SHOW

        for length in range(1, MAX_SHOW+1):
            cnt = freq[length]
            bh  = int((cnt/mx)*uh) if mx else 0
            x0  = pad_l+(length-1)*bw; y0 = h-pad_b-bh
            col = ACCENT if length%2==0 else ACCENT2
            c.create_rectangle(x0+2, y0, x0+bw-2, h-pad_b, fill=col, outline="")
            c.create_text(x0+bw/2, h-pad_b+14, text=str(length), fill=SUBTEXT, font=("Segoe UI", 8))
            if cnt > 0 and bh > 12:
                c.create_text(x0+bw/2, y0+8, text=str(cnt), fill=BG, font=("Courier New", 7, "bold"))

        lpts = []
        for length in range(1, MAX_SHOW+1):
            exp = len(runs)*(0.5**length)
            bh  = int((exp/mx)*uh)
            lpts.extend([pad_l+(length-0.5)*bw, h-pad_b-bh])
        if len(lpts) >= 4:
            c.create_line(lpts, fill=ACCENT3, width=2, smooth=True)
        c.create_text(w-8, pad_t, text="— expected geometric p=0.5",
                      fill=ACCENT3, font=("Segoe UI", 8), anchor="e")
        avg = sum(runs)/len(runs) if runs else 0
        self.app.lbl_runs_stats.config(
            text=f"  Runs: {len(runs):,}   Mean: {avg:.3f}   Max: {max(runs)}   Expected mean: 2.000")


# ─── Entropy — lightweight Tk (line chart) ────────────────────────────────────
class EntropyDrawer(TabDrawer):
    WINDOW = 512
    HIST   = 400

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.history: collections.deque = collections.deque(maxlen=self.HIST)

    def update(self):
        bits = self.store.snapshot_bits(self.WINDOW)
        if len(bits) < 8: return
        p1 = sum(bits)/len(bits); p0 = 1.0-p1
        ent = 0.0
        if p1 > 0: ent -= p1*math.log2(p1)
        if p0 > 0: ent -= p0*math.log2(p0)
        self.history.append(ent)

    def draw(self):
        # Entropy always redraws (history changes even without new raw bytes)
        c = self.canvas
        w, h = clear_canvas(c)
        hist = list(self.history)
        if not hist:
            c.create_text(w//2, h//2, text="Collecting data…", fill=SUBTEXT, font=("Segoe UI", 11))
            return

        draw_grid_tk(c, w, h, 8, 5)
        pl=42; pb=28; pt=20; pr=10
        uw=w-pl-pr; uh=h-pb-pt

        def ey(e): return h-pb-e*uh

        if len(hist) >= 2:
            sx = uw/max(len(hist)-1, 1)
            area = [pl, h-pb]
            for i, e in enumerate(hist): area.extend([pl+i*sx, ey(e)])
            area.extend([pl+(len(hist)-1)*sx, h-pb])
            c.create_polygon(area, fill="#00ffcc15", outline="")
            line = []
            for i, e in enumerate(hist): line.extend([pl+i*sx, ey(e)])
            if len(line) >= 4: c.create_line(line, fill=ACCENT, width=2, smooth=True)
        elif hist:
            e = hist[0]
            c.create_oval(pl-3, ey(e)-3, pl+3, ey(e)+3, fill=ACCENT, outline="")

        cur = hist[-1]
        quality = "✓ ideal" if cur > 0.99 else ("~ good" if cur > 0.95 else "⚠ low")
        c.create_text(w-pr, pt, anchor="ne",
                      text=f"H = {cur:.5f} b/b  {quality}",
                      fill=ACCENT, font=("Courier New", 13, "bold"))
        iy = h-pb-uh
        c.create_line(pl, iy, w-pr, iy, fill=ACCENT3, dash=(6,3))
        c.create_text(w-pr-4, iy-10, text="H=1.0 ideal",
                      fill=ACCENT3, font=("Segoe UI", 8), anchor="e")
        for frac in [0, 0.25, 0.5, 0.75, 1.0]:
            yy = h-pb-int(frac*uh)
            c.create_text(pl-4, yy, text=f"{frac:.2f}", fill=SUBTEXT, font=("Segoe UI", 8), anchor="e")


# ── Main App ──────────────────────────────────────────────────────────────────
class QRNGApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("QRNG  ·  Real-Time Quantum Randomness Visualizer")
        self.configure(bg=BG)
        self.minsize(1100, 700)
        self.geometry("1280x820")

        self.store      = DataStore()
        self.reader     = SerialReader(self.store)
        self._start_ts  = time.monotonic()

        self._build_header()
        self._build_notebook()
        self._build_statusbar()

        # Drawers
        self.drawers: dict[str, TabDrawer] = {}
        self._init_drawers()

        self.reader.start()

        # Schedule per-tab redraws + global status update
        self._schedule_all()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Header ────────────────────────────────────────────────────────────────
    def _build_header(self):
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill="x", padx=24, pady=(16, 0))
        tk.Label(bar, text="QRNG", font=("Courier New", 26, "bold"),
                 fg=ACCENT, bg=BG).pack(side="left")
        tk.Label(bar, text="  Real-Time Quantum Randomness Dashboard",
                 font=("Segoe UI", 13), fg=SUBTEXT, bg=BG).pack(side="left", pady=4)

        right = tk.Frame(bar, bg=BG)
        right.pack(side="right")
        self.lbl_rate  = tk.Label(right, text="rate: —",  font=FONT_MONO, fg=SUBTEXT,  bg=BG)
        self.lbl_rate.pack(side="right", padx=12)
        self.lbl_bias  = tk.Label(right, text="bias: —",  font=FONT_MONO, fg=ACCENT3, bg=BG)
        self.lbl_bias.pack(side="right", padx=12)
        self.lbl_total = tk.Label(right, text="bits: 0",  font=FONT_MONO, fg=ACCENT2, bg=BG)
        self.lbl_total.pack(side="right", padx=12)

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", pady=(12, 0))

    # ── Notebook ──────────────────────────────────────────────────────────────
    def _build_notebook(self):
        style = ttk.Style(self)
        style.theme_use("default")
        style.configure("Q.TNotebook",     background=BG, borderwidth=0)
        style.configure("Q.TNotebook.Tab",
                        background=PANEL, foreground=SUBTEXT,
                        padding=[20, 8], font=("Segoe UI", 10), borderwidth=0)
        style.map("Q.TNotebook.Tab",
                  background=[("selected", BG)],
                  foreground=[("selected", ACCENT)])

        self.nb = ttk.Notebook(self, style="Q.TNotebook")
        self.nb.pack(fill="both", expand=True)

        self.canvases: dict[str, tk.Canvas] = {}
        tabs = [
            ("  Bitstream  ",  "bitstream", self._build_tab_bitstream),
            ("  Histogram  ",  "histogram", self._build_tab_histogram),
            ("  Byte Dist  ",  "bytedist",  self._build_tab_bytedist),
            ("  Poincaré   ",  "poincare",  self._build_tab_poincare),
            ("  Scatter    ",  "scatter",   self._build_tab_scatter),
            ("  Runs Test  ",  "runs",      self._build_tab_runs),
            ("  Entropy    ",  "entropy",   self._build_tab_entropy),
            ("  Statistics ",  "stats",     self._build_tab_stats),
        ]
        for name, key, builder in tabs:
            frame = tk.Frame(self.nb, bg=BG)
            self.nb.add(frame, text=name)
            builder(frame, key)

    def _make_canvas(self, parent, key):
        c = tk.Canvas(parent, bg=PANEL, bd=0, highlightthickness=0)
        c.pack(fill="both", expand=True, pady=(8, 0))
        self.canvases[key] = c
        return c

    def _tab_header(self, parent, title, sub):
        tk.Label(parent, text=title, font=FONT_H, fg=TEXT, bg=BG).pack(anchor="w")
        tk.Label(parent, text=sub, font=("Segoe UI", 9), fg=SUBTEXT, bg=BG).pack(anchor="w")

    def _build_tab_bitstream(self, parent, key):
        f = tk.Frame(parent, bg=BG)
        f.pack(fill="both", expand=True, padx=20, pady=14)
        self._tab_header(f, "Live Bit Stream",
                         f"Scrolling — newest bits brightest  ·  window {WINDOW_SEC:.0f}s")
        self._make_canvas(f, key)
        row = tk.Frame(f, bg=BG)
        row.pack(fill="x", pady=(8, 0))
        self.lbl_ones  = tk.Label(row, text="1s: 0",    font=FONT_BIG, fg=ACCENT,  bg=BG)
        self.lbl_zeros = tk.Label(row, text="0s: 0",    font=FONT_BIG, fg=ACCENT2, bg=BG)
        self.lbl_ratio = tk.Label(row, text="ratio: —", font=FONT_BIG, fg=ACCENT3, bg=BG)
        self.lbl_ones.pack(side="left", padx=14)
        self.lbl_zeros.pack(side="left", padx=14)
        self.lbl_ratio.pack(side="left", padx=14)

    def _build_tab_histogram(self, parent, key):
        f = tk.Frame(parent, bg=BG)
        f.pack(fill="both", expand=True, padx=20, pady=14)
        self._tab_header(f, "Bit Frequency Histogram (all-time)",
                         "Expected 50 / 50 for ideal QRNG  ·  bars animate to target")
        self._make_canvas(f, key)

    def _build_tab_bytedist(self, parent, key):
        f = tk.Frame(parent, bg=BG)
        f.pack(fill="both", expand=True, padx=20, pady=14)
        self._tab_header(f, f"Byte Value Distribution — last {WINDOW_SEC:.0f}s  (0–255)",
                         "Flat distribution = ideal randomness  ·  bars animate to target")
        self._make_canvas(f, key)

    def _build_tab_poincare(self, parent, key):
        f = tk.Frame(parent, bg=BG)
        f.pack(fill="both", expand=True, padx=20, pady=14)
        self._tab_header(f, "Poincaré / Return Map",
                         f"x(n) vs x(n+1)  ·  last {WINDOW_SEC:.0f}s  ·  new=bright, old=dark")
        self._make_canvas(f, key)

    def _build_tab_scatter(self, parent, key):
        f = tk.Frame(parent, bg=BG)
        f.pack(fill="both", expand=True, padx=20, pady=14)
        self._tab_header(f, "2D Scatter — Sequential Byte Pairs",
                         f"last {WINDOW_SEC:.0f}s  ·  new=bright/large, old=dark/small")
        self._make_canvas(f, key)

    def _build_tab_runs(self, parent, key):
        f = tk.Frame(parent, bg=BG)
        f.pack(fill="both", expand=True, padx=20, pady=14)
        self._tab_header(f, "Runs Length Analysis",
                         "Distribution of consecutive identical bit runs vs geometric expectation")
        self._make_canvas(f, key)
        self.lbl_runs_stats = tk.Label(f, text="", font=FONT_MONO,
                                       fg=ACCENT, bg=BG, justify="left")
        self.lbl_runs_stats.pack(anchor="w", pady=(6, 0))

    def _build_tab_entropy(self, parent, key):
        f = tk.Frame(parent, bg=BG)
        f.pack(fill="both", expand=True, padx=20, pady=14)
        self._tab_header(f, "Shannon Entropy over Time",
                         "Rolling 512-bit window  ·  recalculated every tick  ·  ideal = 1.000 b/b")
        self._make_canvas(f, key)

    def _build_tab_stats(self, parent, key):
        f = tk.Frame(parent, bg=BG)
        f.pack(fill="both", expand=True, padx=20, pady=14)
        tk.Label(f, text="Statistical Summary", font=FONT_H, fg=TEXT, bg=BG).pack(anchor="w")
        tk.Label(f, text=f"All-time counters + rolling {WINDOW_SEC:.0f}s window stats",
                 font=("Segoe UI", 9), fg=SUBTEXT, bg=BG).pack(anchor="w")

        grid = tk.Frame(f, bg=BG)
        grid.pack(fill="both", expand=True, pady=12)
        self.stat_vars: dict[str, tk.StringVar] = {}
        items = [
            ("Total bits",        "total_bits",  ACCENT),
            ("Total bytes",       "total_bytes", ACCENT),
            ("Ones (all-time)",   "ones",        ACCENT),
            ("Zeros (all-time)",  "zeros",       ACCENT2),
            ("P(1)",              "p1",          ACCENT3),
            ("P(0)",              "p0",          ACCENT3),
            ("Bias from 0.5",     "bias_err",    ACCENT3),
            ("Shannon entropy",   "entropy",     ACCENT),
            ("Mean byte (window)","mean_byte",   TEXT),
            ("Std dev byte",      "std_byte",    TEXT),
            ("Min byte",          "min_byte",    TEXT),
            ("Max byte",          "max_byte",    TEXT),
            ("χ² (df=1)",         "chi2",        ACCENT2),
            ("Data rate",         "rate",        SUBTEXT),
        ]
        for idx, (label, key2, color) in enumerate(items):
            col_i, row_i = idx % 2, idx // 2
            cell = tk.Frame(grid, bg=PANEL, padx=14, pady=10)
            cell.grid(row=row_i, column=col_i, padx=5, pady=4, sticky="nsew")
            grid.columnconfigure(col_i, weight=1)
            tk.Label(cell, text=label, font=("Segoe UI", 9),
                     fg=SUBTEXT, bg=PANEL).pack(anchor="w")
            var = tk.StringVar(value="—")
            self.stat_vars[key2] = var
            tk.Label(cell, textvariable=var, font=("Courier New", 16, "bold"),
                     fg=color, bg=PANEL).pack(anchor="w", pady=(2, 0))

    # ── Status bar ────────────────────────────────────────────────────────────
    def _build_statusbar(self):
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")
        row = tk.Frame(self, bg="#0d0d14")
        row.pack(fill="x")
        self.lbl_status = tk.Label(row, text="", font=("Segoe UI", 9),
                                   fg=SUBTEXT, bg="#0d0d14", pady=5)
        self.lbl_status.pack(side="left", padx=16)
        self.lbl_mode = tk.Label(row, text="", font=("Courier New", 9),
                                 fg=ACCENT, bg="#0d0d14", pady=5)
        self.lbl_mode.pack(side="right", padx=16)

    # ── Drawers ───────────────────────────────────────────────────────────────
    def _init_drawers(self):
        self.drawers["bitstream"] = BitstreamDrawer(self.canvases["bitstream"], self.store, self)
        self.drawers["histogram"] = HistogramDrawer(self.canvases["histogram"], self.store, self)
        self.drawers["bytedist"]  = ByteDistDrawer (self.canvases["bytedist"],  self.store, self)
        self.drawers["poincare"]  = PoincareDrawer (self.canvases["poincare"],  self.store, self)
        self.drawers["scatter"]   = ScatterDrawer  (self.canvases["scatter"],   self.store, self)
        self.drawers["runs"]      = RunsDrawer     (self.canvases["runs"],      self.store, self)
        self.entropy_drawer       = EntropyDrawer  (self.canvases["entropy"],   self.store, self)
        self.drawers["entropy"]   = self.entropy_drawer

        # Map notebook tab index → key (built from the tab order in _build_notebook)
        self._tab_keys = ["bitstream", "histogram", "bytedist",
                          "poincare",  "scatter",   "runs", "entropy", "stats"]

    # ── Single unified tick ───────────────────────────────────────────────────
    def _schedule_all(self):
        self.update_idletasks()
        self.after(REDRAW_MS,  self._tick_draw)    # active-tab redraw
        self.after(150,        self._tick_entropy)  # entropy history (always)
        self.after(500,        self._tick_stats)    # stats tab (cheap labels)
        self.after(200,        self._tick_header)   # header / status bar

    def _active_key(self):
        idx = self.nb.index(self.nb.select())
        return self._tab_keys[idx] if idx < len(self._tab_keys) else None

    def _tick_draw(self):
        """Draw ONLY the currently visible tab."""
        key = self._active_key()
        if key and key != "stats" and key in self.drawers:
            self.drawers[key].draw()
        self.after(REDRAW_MS, self._tick_draw)

    def _tick_entropy(self):
        """Update entropy history unconditionally — keeps graph live even when hidden."""
        self.entropy_drawer.update()
        self.after(150, self._tick_entropy)

    def _tick_stats(self):
        if self._active_key() == "stats":
            self._update_stats()
        self.after(500, self._tick_stats)

    def _tick_header(self):
        _, _, _, total, ones = self.store.snapshot_all()
        self.lbl_total.config(text=f"bits: {total:,}")
        p1 = ones / total if total else 0
        self.lbl_bias.config(text=f"P(1): {p1:.4f}")
        elapsed = time.monotonic() - self._start_ts
        rate    = total / elapsed if elapsed > 0 else 0
        self.lbl_rate.config(text=f"~{rate:,.0f} b/s")
        if total:
            self.lbl_ones.config(text=f"1s: {ones:,}")
            self.lbl_zeros.config(text=f"0s: {total-ones:,}")
            r = ones / max(total-ones, 1)
            self.lbl_ratio.config(text=f"ratio: {r:.4f}")
        mode = "DEMO" if (not SERIAL_AVAILABLE or self.reader.error) else "LIVE"
        self.lbl_status.config(text=f"  {self.reader.status}")
        self.lbl_mode.config(text=f"● {mode}",
                             fg=ACCENT3 if mode == "DEMO" else ACCENT)
        self.after(200, self._tick_header)

    # ── Stats tab ─────────────────────────────────────────────────────────────
    def _update_stats(self):
        bits, bytes_, _, total, ones = self.store.snapshot_all()
        zeros = total - ones
        p1    = ones / total if total else 0
        p0    = 1.0 - p1
        bias  = abs(p1 - 0.5)

        window = self.store.snapshot_bits(512)
        p1w = sum(window) / len(window) if window else 0
        p0w = 1.0 - p1w
        ent = 0.0
        if p1w > 0: ent -= p1w * math.log2(p1w)
        if p0w > 0: ent -= p0w * math.log2(p0w)

        bv_win, _ = self.store.snapshot_window(WINDOW_SEC)
        if bv_win:
            mean_b = sum(bv_win) / len(bv_win)
            if NUMPY_AVAILABLE:
                std_b = float(np.std(bv_win))
            else:
                std_b = math.sqrt(sum((x-mean_b)**2 for x in bv_win)/len(bv_win))
            min_b, max_b = min(bv_win), max(bv_win)
        else:
            mean_b = std_b = min_b = max_b = 0

        exp  = total / 2
        chi2 = ((ones-exp)**2 + (zeros-exp)**2) / exp if exp > 0 else 0
        elapsed = time.monotonic() - self._start_ts
        rate    = total / elapsed if elapsed > 0 else 0

        def s(k, v):
            if k in self.stat_vars: self.stat_vars[k].set(v)

        s("total_bits",  f"{total:,}")
        s("total_bytes", f"{len(bytes_):,}")
        s("ones",        f"{ones:,}")
        s("zeros",       f"{zeros:,}")
        s("p1",          f"{p1:.6f}")
        s("p0",          f"{p0:.6f}")
        s("bias_err",    f"{bias:.6f}  ({'✓ ok' if bias < 0.005 else '⚠ biased'})")
        s("entropy",     f"{ent:.6f} b/b")
        s("mean_byte",   f"{mean_b:.3f}  (ideal 127.5)")
        s("std_byte",    f"{std_b:.3f}  (ideal 73.61)")
        s("min_byte",    f"{min_b}")
        s("max_byte",    f"{max_b}")
        s("chi2",        f"{chi2:.4f}  (crit 3.841)")
        s("rate",        f"~{rate:,.0f}  bit/s")

    # ── Close ─────────────────────────────────────────────────────────────────
    def _on_close(self):
        self.reader.stop()
        self.destroy()


# ── Entry ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    if not SERIAL_AVAILABLE:
        print("[WARN] pyserial not installed — running in DEMO mode")
        print("       pip install pyserial")
    if not NUMPY_AVAILABLE:
        print("[INFO] numpy optional — pip install numpy  (for accurate std dev)")
    if not PIL_AVAILABLE:
        print("[WARN] Pillow not installed — pixel tabs use slower Tk fallback")
        print("       pip install Pillow")
    QRNGApp().mainloop()
