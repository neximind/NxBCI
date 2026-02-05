import time
import logging
import os
import sys
import numpy as np
import matplotlib.pyplot as plt
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from NxBCI.MultiSourceController import MultiSourceController

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

if __name__ == "__main__":

    current_script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(current_script_dir, "data", "my_experiment_data.csv")
    print(f"Data will be saved to: {csv_path}")
    
    # 示例端口列表
    TARGET_PORTS = ['COM3'] # 根据实际情况修改端口列表,你可以通过设备管理器查看端口号或使用 list_ports 列出可用端口
    
    # 实例化控制器，开启 CSV 保存功能
    controller = MultiSourceController(
        ports=TARGET_PORTS, 
        save_csv=True, 
        csv_filename=csv_path
    )
    
    # 绘图配置
    TOTAL_CHANNELS = 16 * len(TARGET_PORTS)
    MAX_DISPLAY = 1000*4
    OFFSET = 200
    
    plt.ion()
    fig, ax = plt.subplots(figsize=(15, 9))

    lines = [ax.plot([], [], lw=0.8)[0] for _ in range(TOTAL_CHANNELS)]
    ax.set_title(f"Multi-Source Real-Time Data Plot ({len(TARGET_PORTS)} Devices, {TOTAL_CHANNELS} Channels)")
    ax.set_xlabel("Time Points")
    ax.set_ylabel("Channel Data (Offset Applied)")
    ax.set_xlim(0, MAX_DISPLAY)
    ax.set_ylim(-OFFSET, TOTAL_CHANNELS * OFFSET + OFFSET/2)

    y_ticks_pos = [i * OFFSET for i in range(TOTAL_CHANNELS)]
    y_ticks_labels = [f"ch{i}" for i in range(TOTAL_CHANNELS)]
    ax.set_yticks(y_ticks_pos)
    ax.set_yticklabels(y_ticks_labels, fontsize=8)

    ax.grid(True, linestyle='--', alpha=0.6)
    
    fig.tight_layout()

    plot_buffer = np.zeros((TOTAL_CHANNELS, MAX_DISPLAY))
    x_idxs = np.arange(MAX_DISPLAY)
    
    try:
        controller.start()
        print("System Running... Press Ctrl+C to stop.")
        
        while plt.fignum_exists(fig.number):
            data = controller.get_aligned_data()
            
            if data is not None:
                n = data.shape[1]

                if n >= MAX_DISPLAY:
                    plot_buffer = data[:, -MAX_DISPLAY:]
                else:
                    plot_buffer[:, :-n] = plot_buffer[:, n:]
                    plot_buffer[:, -n:] = data

                for i in range(TOTAL_CHANNELS):
                    lines[i].set_data(x_idxs, plot_buffer[i] + i * OFFSET)
                fig.canvas.draw()
                fig.canvas.flush_events()
            else:
                time.sleep(0.005)
                fig.canvas.flush_events()
                
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        controller.stop()
        print(f"Done. Check '{csv_path}'.")
        plt.ioff()
        plt.show()