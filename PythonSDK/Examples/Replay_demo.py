import sys
import os
import asyncio

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from NxBCI.Replay import Replay
import logging
import matplotlib.pyplot as plt
import numpy as np
import time

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
filepath = os.path.join(os.getcwd(), "Examples", "EMGDATA_500Hz_mixdata.bin")

try:
    with Replay(FilePath=filepath, sample_rate=500,isLoop=True) as replay:
        # 启动后台回放
        replay.load_all_data()

        print("--- Starting playback from the beginning ---")
        replay.restart_playback()
        time.sleep(2) # 播放2秒

        CHANNELS = replay.channels
        MAX_POINTS = replay.data_queues[0].maxlen # 从实例中获取配置
        OFFSET = 200
        
        plt.ion()
        fig, ax = plt.subplots(figsize=(12, 8))
        lines = [ax.plot([], [])[0] for _ in range(CHANNELS)]
        ax.set_title(f"{CHANNELS}-Channel Replay Data Plot")
        ax.set_xlabel("Time Points")
        ax.set_ylabel("Voltage (Channels separated by offset)")
        ax.set_xlim(0, MAX_POINTS)
        ax.set_ylim(-OFFSET, CHANNELS * OFFSET)
        ax.grid(True, linestyle='--', alpha=0.6)
        ax.set_yticks([]) 
        fig.tight_layout()

        x_data_full = np.arange(MAX_POINTS)
        print("Starting plot... Press Ctrl+C or close the window to stop.")

        # 绘图循环完全不变
        while plt.fignum_exists(fig.number):
            data = replay.get_data()
            if not data or not data[0]:
                plt.pause(0.1)
                continue
            
                    # 更新每一条线的数据
            for i in range(CHANNELS):
                y_points = list(data[i])
                current_len = len(y_points)
                
                # 只有在有数据点时才更新
                if current_len > 0:
                    y_data = np.array(y_points) + i * OFFSET
                    # 使用预先创建的 x_data 的切片，确保 x 和 y 长度一致
                    lines[i].set_data(x_data_full[:current_len], y_data)
                
            fig.canvas.draw()
            fig.canvas.flush_events()
            plt.pause(0.01)

except FileNotFoundError as e:
    logging.error(e)
except KeyboardInterrupt:
    print("\nPlotting stopped by user.")
finally:
    # 'with' 语句会自动调用 receiver.stop() 和关闭文件
    print("Cleanup complete.")