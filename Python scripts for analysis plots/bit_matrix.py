# ==========================================
# REAL-TIME QRNG BIT MATRIX VISUALIZER
#
# Shows incoming random bits as a live matrix
# White  = 1
# Black  = 0
#
# Install:
# pip install pyserial matplotlib numpy
# ==========================================

import serial
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

# =========================
# SETTINGS
# =========================
SERIAL_PORT = 'COM12'
BAUD_RATE = 115200

ROWS = 64
COLS = 64

# =========================
# SERIAL
# =========================
ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)

# =========================
# MATRIX
# =========================
matrix = np.zeros((ROWS, COLS))

# Current write position
index = 0

# =========================
# PLOT
# =========================
fig, ax = plt.subplots(figsize=(7, 7))

img = ax.imshow(
    matrix,
    cmap='gray',
    vmin=0,
    vmax=1,
    interpolation='nearest'
)

ax.set_title("Real-Time QRNG Bit Matrix")
ax.axis('off')

# =========================
# UPDATE FUNCTION
# =========================
def update(frame):

    global index
    global matrix

    updated = False

    while ser.in_waiting:

        try:
            value = ser.readline().decode().strip()

            if value in ['0', '1']:

                bit = int(value)

                row = index // COLS
                col = index % COLS

                matrix[row, col] = bit

                index += 1
                updated = True

                # Restart matrix when full
                if index >= ROWS * COLS:
                    index = 0

        except:
            pass

    if updated:
        img.set_array(matrix)

    return [img]

# =========================
# ANIMATION
# =========================
ani = FuncAnimation(
    fig,
    update,
    interval=30,
    blit=True
)

plt.tight_layout()
plt.show()

ser.close()
