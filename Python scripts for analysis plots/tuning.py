# ==========================================
# REAL-TIME QRNG BIAS MONITOR
# Shows:
# 1. Live ratio of 0s and 1s
# 2. Percentage balance
# 3. Real-time graph
#
# Install first:
# pip install pyserial matplotlib
# ==========================================

import serial
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from collections import deque

# =========================
# SETTINGS
# =========================
SERIAL_PORT = 'COM12'     # Change if needed
BAUD_RATE = 115200
WINDOW_SIZE = 1000        # Number of recent bits to analyze

# =========================
# SERIAL SETUP
# =========================
ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)

# =========================
# DATA STORAGE
# =========================
bits = deque(maxlen=WINDOW_SIZE)

zeros_history = deque(maxlen=200)
ones_history = deque(maxlen=200)

# =========================
# PLOT SETUP
# =========================
plt.style.use('dark_background')

fig, ax = plt.subplots(figsize=(10, 5))

line0, = ax.plot([], [], label='0 Ratio')
line1, = ax.plot([], [], label='1 Ratio')

ax.set_ylim(0, 100)
ax.set_xlim(0, 200)

ax.set_ylabel('Percentage (%)')
ax.set_xlabel('Time')
ax.set_title('Real-Time QRNG Bias Monitor')

ax.legend()

text_box = ax.text(
    0.02,
    0.95,
    '',
    transform=ax.transAxes,
    fontsize=12,
    verticalalignment='top'
)

# =========================
# UPDATE FUNCTION
# =========================
def update(frame):

    # Read serial data
    while ser.in_waiting:
        try:
            value = ser.readline().decode().strip()

            if value in ['0', '1']:
                bits.append(int(value))

        except:
            pass

    if len(bits) == 0:
        return line0, line1

    # Count
    zeros = bits.count(0)
    ones = bits.count(1)

    total = zeros + ones

    zero_ratio = (zeros / total) * 100
    one_ratio = (ones / total) * 100

    zeros_history.append(zero_ratio)
    ones_history.append(one_ratio)

    # Update graph
    x = range(len(zeros_history))

    line0.set_data(x, zeros_history)
    line1.set_data(x, ones_history)

    ax.set_xlim(0, max(200, len(zeros_history)))

    # Display text
    text_box.set_text(
        f'0s: {zeros} ({zero_ratio:.2f}%)\n'
        f'1s: {ones} ({one_ratio:.2f}%)\n'
        f'Total Bits: {total}\n\n'
        f'Adjust potentiometer until both are near 50%'
    )

    return line0, line1, text_box

# =========================
# ANIMATION
# =========================
ani = FuncAnimation(
    fig,
    update,
    interval=50,
    blit=False
)

plt.tight_layout()
plt.show()

ser.close()
