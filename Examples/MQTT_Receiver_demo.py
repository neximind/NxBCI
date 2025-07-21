import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

import matplotlib.pyplot as plt
import numpy as np
import logging
from NxBCI.MQTT_Receiver import MQTT_Receiver

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

BROKER_IP = "192.168.177.22"
BROKER_PORT = 1883
TOPIC = "esp32-pub-message"
CHANNELS = 16
SAMPLE_RATE = 500
DURATION = 4 
MAX_POINTS = SAMPLE_RATE * DURATION 
OFFSET = 200 

receiver = MQTT_Receiver(
    Ip=BROKER_IP, 
    port=BROKER_PORT,
    topic=TOPIC,
    channels=CHANNELS,
    sample_rate=SAMPLE_RATE,
    duration=DURATION
)
receiver.start()

plt.ion() 
fig, ax = plt.subplots(figsize=(15, 9)) # 窗口大一点更清晰

# 为每一条线创建一个空的 Line2D 对象
lines = [ax.plot([], [])[0] for _ in range(CHANNELS)]

# 设置坐标轴和标题 (一次性完成)
ax.set_title(f"{CHANNELS}-Channel Real-Time Data Plot")
ax.set_xlabel("Time Points")
ax.set_ylabel("Voltage (Channels separated by offset)")
ax.set_xlim(0, MAX_POINTS)
ax.set_ylim(-OFFSET, CHANNELS * OFFSET)
ax.grid(True, linestyle='--', alpha=0.6)

# 移除 Y 轴刻度，因为偏移量使得刻度没有意义
ax.set_yticks([]) 
fig.tight_layout()

# --- 4. 预先创建 X 轴数据 (性能关键点) ---
x_data_full = np.arange(MAX_POINTS)

print("Starting plot... Press Ctrl+C in the terminal or close the plot window to stop.")

try:
    # 循环条件：只要绘图窗口存在就继续
    while plt.fignum_exists(fig.number):
        
        # 从接收器安全地获取数据副本
        all_channels_data = receiver.get_data()

        # 检查是否收到了有效数据
        if not all_channels_data or not all_channels_data[0]:
            plt.pause(0.1) # 如果没数据，稍微多等一下
            continue

        # 更新每一条线的数据
        for i in range(CHANNELS):
            y_points = list(all_channels_data[i])
            current_len = len(y_points)
            
            # 只有在有数据点时才更新
            if current_len > 0:
                y_data = np.array(y_points) + i * OFFSET
                # 使用预先创建的 x_data 的切片，确保 x 和 y 长度一致
                lines[i].set_data(x_data_full[:current_len], y_data)
        
        # 高效地重绘图形
        fig.canvas.draw()
        fig.canvas.flush_events()
        
        # 短暂暂停，让 GUI 响应
        plt.pause(0.01)

except KeyboardInterrupt:
    print("\nPlotting stopped by user.")
finally:
    print("Cleaning up resources...")
    receiver.stop()
    print("MQTT Receiver stopped.")
    plt.ioff() # 关闭交互模式
    print("Plot display finished.")