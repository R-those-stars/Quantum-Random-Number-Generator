# Quantum-Random-Number-Generator

> A hardware-based Quantum Random Number Generator (QRNG) using Zener diode noise as an entropy source for cryptographic and scientific applications.

---

## 📌 Overview

This project generates **true random numbers** using the intrinsic noise characteristics of a **Zener diode**.  
The analog entropy is amplified, conditioned, and converted into digital random bits using comparator circuitry and an ESP32.

The generated random bitstream is transmitted to a computer for:
- Real-time visualization
- Statistical analysis
- Cryptographic applications
- Randomness testing

---

# 📷 Project Preview
<img width="1688" height="2252" alt="20260510_175829(1) jpg" src="https://github.com/user-attachments/assets/33657007-f73a-4865-af65-cc6952a5aa58" />

![Project Banner](assets/project_banner_placeholder.png)

> Replace this with a clean image of your final setup or project render.

---

# ⚡ Working Principle

1. Zener diode generates electrical noise.
2. Analog circuitry amplifies weak entropy signals.
3. Comparator converts noise into digital HIGH/LOW states.
4. ESP32 samples the digital signal.
5. Random bits are sent via Serial Communication.
6. Python/MATLAB visualizes the randomness.

---

# 🛠️ Hardware Components

| Component | Purpose |
|---|---|
| ESP32 | Bit acquisition & serial transmission |
| LM393 Comparator | Analog-to-digital conversion |
| 4.7V Zener Diode | Entropy source |
| Potentiometer | Threshold tuning |
| Capacitors | Noise filtering & coupling |
| Resistors | Biasing & amplification |
| Breadboard | Prototyping |

---

# 🔌 Circuit Diagram

![Circuit Diagram](assets/circuit_diagram_placeholder.png)

> Add your final schematic here.

---

# 📸 Hardware Setup

## Breadboard Prototype

![Breadboard Setup](assets/breadboard_placeholder.jpg)

---

## Final Hardware Assembly

![Final Hardware](assets/final_hardware_placeholder.jpg)

---

# 📊 Randomness Visualization

## 1️⃣ Real-Time Bitstream

![Bitstream Plot](assets/bitstream_plot_placeholder.png)

---

## 2️⃣ Random Bit Matrix

![Bit Matrix](assets/bit_matrix_placeholder.png)

---

## 3️⃣ Scatter Plot / Star Map

![Scatter Plot](assets/scatter_plot_placeholder.png)

---

## 4️⃣ Serial Plotter Output

![Serial Plotter](assets/serial_plotter_placeholder.png)

---

# 💻 Software Stack

- Python
- ESP32 Arduino Framework
- PySerial
- Matplotlib
- MATLAB (Optional)

---

# 🚀 Features

- True hardware-generated randomness
- Real-time data visualization
- Adjustable comparator threshold
- Lightweight hardware design
- Serial data streaming
- Cryptography-oriented entropy generation

---

# 📂 Project Structure

```bash
Quantum-Random-Number-Generator/
│
├── Arduino_Code/
│   └── qrng_esp32.ino
│
├── Python/
│   └── realtime_visualizer.py
│
├── MATLAB/
│   └── qrng_analysis.m
│
├── assets/
│   ├── project_banner_placeholder.png
│   ├── circuit_diagram_placeholder.png
│   ├── breadboard_placeholder.jpg
│   ├── final_hardware_placeholder.jpg
│   ├── bitstream_plot_placeholder.png
│   ├── bit_matrix_placeholder.png
│   ├── scatter_plot_placeholder.png
│   └── serial_plotter_placeholder.png
│
└── README.md
