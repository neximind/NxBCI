# NxBCI Python SDK

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9](https://img.shields.io/badge/python-3.9-blue.svg)](https://www.python.org/downloads/)
[![Lang: En](https://img.shields.io/badge/Lang-English-blue.svg)](Readme.md)

**NxBCI** SDK 用于与 Neximind 采集设备进行通信。本文档旨在帮助开发者在 **Windows** 或 **macOS** 系统上搭建开发环境并运行示例代码。

---

### 🌐 [English Documentation](Readme.md)

---

## 💻 系统要求

* **操作系统**: 支持 Windows 10/11 或 macOS (10.15+)。
* **Python 版本**: Python 3.9 及以上。
* **硬件接口**: USB 串口或蓝牙适配器。

## 🛠️ 环境搭建指南

您可以使用 **Conda** 或 Python 原生的 **Pip** (venv) 来管理依赖环境。

### 1. 克隆代码仓库

```bash
git clone https://github.com/neximind/NxBCI.git
cd NxBCI
```

### 2. 安装依赖库

#### 方案 A: 使用 Conda (推荐)

如果您习惯使用 Anaconda/Miniconda：

```bash
conda env create -f environment.yml
conda activate NxBCI
```
#### 方案 B: 使用原生 Pip (venv)

1. **创建虚拟环境:**

   ```bash
   # Windows 系统
   python -m venv venv
   .\venv\Scripts\activate

   # macOS / Linux 系统
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **安装依赖:**

   ```bash
   pip install -r requirements.txt
   ```

### 3. 安装 SDK 模块

以“编辑模式”安装 SDK，以便在开发过程中随时修改代码：

```bash
pip install -e .
```

## ▶️ 运行示例

环境配置完成后，您可以运行 `Examples` 目录下的脚本来验证安装。

### 示例 1: 数据回放 (Replay Demo)
该脚本通过读取录制文件模拟数据采集过程，无需连接硬件：

```bash
python Examples/Replay_demo.py
```

### 示例 2: 硬件采集
若要通过串口连接设备，请先确认您的串口名称(您可以运行Examples/list_port.py查看自己电脑当前的串口)：
* **Windows**: 通常为 `COM3`, `COM4` 等。
* **macOS**: 通常为 `/dev/tty.usbserial-XXXX` 或 `/dev/tty.usbmodemXXXX`。

请在Examples/MultiSerial_Ports_Demo.py代码中修改为您实际的端口号。

## 🔧 常见问题

* **权限被拒绝 (macOS)**: 如果无法打开串口，请检查是否已安装 CH340/CP210x 驱动，或尝试检查 USB 设备权限。
* **找不到模块**: 运行代码前，请务必确认已激活虚拟环境 (`conda activate NxBCI` 或 `source venv/bin/activate`)。

## 📄 许可证

本项目遵循 [MIT 许可证](LICENSE)。