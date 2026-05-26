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

<img width="2412" height="5702" alt="20260510_182647~2 jpg" src="https://github.com/user-attachments/assets/efdbc24e-190f-4068-8be7-b15e5dc4b1d5" />


---

## Final Hardware Assembly

<img width="3000" height="2079" alt="circuit_image" src="https://github.com/user-attachments/assets/7fd8de52-9a08-4279-87d6-c5713a338b36" />


---

# 📊 Randomness Visualization

## 1️⃣ Real-Time Bitstream

<img width="733" height="570" alt="bitstream" src="https://github.com/user-attachments/assets/b93a80e3-66b9-499c-bd74-d5becc2ed173" />


---

## 2️⃣ Random Bit Matrix

<img width="1373" height="917" alt="bit matrix" src="https://github.com/user-attachments/assets/7eaa071d-828b-46c3-9acf-86ad920070b9" />


---

## 3️⃣ Scatter Plot / Star Map

<img width="1920" height="1080" alt="star map" src="https://github.com/user-attachments/assets/de0d4d8b-a868-4c67-a3a9-b4ff58c0b1d7" />




---

## 4️⃣ Serial Plotter Output

<img width="1511" height="370" alt="plotter" src="https://github.com/user-attachments/assets/5db46b6f-87db-41e9-a51b-f8ee8edd4581" />


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
└──Hardware Photos┐
│                 └── Final_look.jpeg
│                 └── Components_req.jpeg
│
└──Esp32_tuning.ino
│
└──Python scripts for analysis plots┐
│                                   └── tuning.py
│                                   └── bit_matrix.py
│                                   └── scatter_plotter.py                               
└── README.md
