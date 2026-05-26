import serial
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
import numpy as np

# ==========================================
# SETTINGS
# ==========================================
SERIAL_PORT = 'COM12'
BAUD_RATE = 115200

MAX_POINTS = 4000

# ==========================================
# SERIAL CONNECTION
# ==========================================
try:
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=1)
    print(f"Connected to {SERIAL_PORT}")
except Exception as e:
    print("Serial Error:", e)
    exit()

# ==========================================
# BIT BUFFER
# ==========================================
bit_buffer = ""

# ==========================================
# STAR STORAGE
# ==========================================
x_data = []
y_data = []
colors = []

# ==========================================
# PLOT SETUP
# ==========================================
plt.style.use("dark_background")

fig, ax = plt.subplots(figsize=(8, 8))

ax.set_xlim(0, 255)
ax.set_ylim(0, 255)

ax.set_facecolor("black")

ax.set_title(
    "Quantum Random Star Map",
    fontsize=16
)

ax.set_xlabel("X Byte")
ax.set_ylabel("Y Byte")

# Initial scatter
scatter = ax.scatter(
    [],
    [],
    s=[],
    alpha=0.8
)

# ==========================================
# BYTE GENERATOR
# ==========================================
def get_byte():
    global bit_buffer

    while len(bit_buffer) < 8:

        if ser.in_waiting:

            chunk = ser.read(ser.in_waiting).decode(errors='ignore')

            # Keep only 0 and 1
            chunk = ''.join(c for c in chunk if c in '01')

            bit_buffer += chunk

    byte = bit_buffer[:8]
    bit_buffer = bit_buffer[8:]

    return int(byte, 2)

# ==========================================
# UPDATE FUNCTION
# ==========================================
def update(frame):

    global x_data, y_data, colors

    try:

        # Generate multiple stars per frame
        for _ in range(25):

            x = get_byte()
            y = get_byte()

            x_data.append(x)
            y_data.append(y)

            # Random brightness
            colors.append(np.random.uniform(0.5, 1.0))

        # Limit total stars
        if len(x_data) > MAX_POINTS:

            x_data = x_data[-MAX_POINTS:]
            y_data = y_data[-MAX_POINTS:]
            colors = colors[-MAX_POINTS:]

        # Random star sizes
        sizes = np.random.uniform(2, 12, len(x_data))

        scatter.set_offsets(
            np.column_stack((x_data, y_data))
        )

        scatter.set_sizes(sizes)

        scatter.set_array(np.array(colors))

    except:
        pass

    return scatter,

# ==========================================
# ANIMATION
# ==========================================
ani = FuncAnimation(
    fig,
    update,
    interval=30,
    blit=True,
    cache_frame_data=False
)

plt.tight_layout()
plt.show()

ser.close()
