# NxBCI Python SDK

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9](https://img.shields.io/badge/python-3.9-blue.svg)](https://www.python.org/downloads/)
[![Lang: Zh](https://img.shields.io/badge/语言-中文-red.svg)](README_zh.md)

The **NxBCI** SDK enables developers to communicate with Neximind acquisition devices. This guide focuses on setting up the development environment and running demos on **Windows** and **macOS**.

---

### 🌐 [中文说明 (Chinese Documentation)](README_zh.md)

---

## 💻 System Requirements

* **Operating System**: Windows 10/11 or macOS (10.15+).
* **Python Version**: Python 3.9 or newer.
* **Hardware Interface**: USB Serial Port or Bluetooth Adapter.

## 🛠️ Environment Setup

You can set up the environment using either **Conda** (recommended for isolation) or standard **Pip** (venv).

### 1. Clone the Repository

```bash
git clone [https://github.com/neximind/NxBCI.git](https://github.com/neximind/NxBCI.git)
cd NxBCI
```

### 2. Install Dependencies

#### Option A: Using Conda (Cross-Platform)

If you have `environment.yml`:

```bash
conda env create -f environment.yml
conda activate NxBCI
```

#### Option B: Using Standard Pip (venv)

1. **Create a virtual environment:**

   ```bash
   # Windows
   python -m venv venv
   .\venv\Scripts\activate

   # macOS / Linux
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Install requirements:**

   ```bash
   pip install -r requirements.txt
   ```

### 3. Install the SDK Package

Install the SDK in editable mode to allow for development:

```bash
pip install -e .
```

## ▶️ Running Demos

Once the environment is ready, you can verify the installation by running the examples.

### Example: Replay Demo
This script simulates data acquisition by replaying a recorded file.

```bash
python Examples/Replay_demo.py
```

### Example: Hardware Acquisition
To run with a device, check your serial port name first(You can run the "list_port.py" to list all serial ports):
* **Windows**: `COM3`, `COM4`, etc.
* **macOS**: `/dev/tty.usbserial-XXXX` or `/dev/tty.usbmodemXXXX`.

Update the port in "Examples/MultiSerial_Ports_Demo.py" script accordingly.

## 🔧 Troubleshooting

* **Permission Denied (macOS)**: If you cannot open the serial port, you may need to install the CH340/CP210x driver or run the script with necessary permissions.
* **Module Not Found**: Ensure you have activated your virtual environment (`conda activate NxBCI` or `source venv/bin/activate`) before running scripts.

## 📄 License

This project is licensed under the [MIT License](LICENSE).