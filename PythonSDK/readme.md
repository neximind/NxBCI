# NxBCI
This interface module is designed for customers who have purchased our equipment. It enables seamless data acquisition from the devices and provides control over operational parameters and device status monitoring.

---

## 🚀 Getting Started

This guide will help you successfully install and run NxBCI on your local machine for development and testing.

### Prerequisites

For Python environment and dependency management, we recommend [Anaconda](https://www.anaconda.com/download).

---

## ⚙️ Installation

Please follow these steps to set up your local development environment.

### 1. Clone the Repository

First, clone this repository to your local computer:

```bash
git clone https://github.com/neximind/NxBCI.git
cd NxBCI
```
### 2. Create and Activate the Conda Environment

Use the `environment.yml` file to create and activate your Conda environment.

```bash
# 根据 yml 文件创建环境
conda env create -f environment.yml

# 激活新创建的环境
conda activate NxBCI
```
### 3. Install Additional Dependencies
Please use pip to install the additional dependencies included in the `requirements.txt` file.
```bash
pip install -r requirements.txt
```
### 4. Install NxBCI
Install NxBCI into your project in editable mode.
```bash
pip install -e .
```
## ▶️ Usage


You can run demos of various NxBCI features within the `Examples` folder. For instance, see how to replay scripts saved by the acquisition device to a file:
```bash
python Examples/Replay_demo.py
```
## 🤝 Contributing

We welcome contributions of all kinds! You can help us improve this project by submitting Pull Requests or reporting Issues.

---

## 📄 License

This project is licensed under th [MIT](LICENSE) License.