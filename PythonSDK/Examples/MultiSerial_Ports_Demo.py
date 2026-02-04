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
    TARGET_PORTS = ['COM3','COM4'] # 根据实际情况修改端口列表,你可以通过设备管理器查看端口号或使用 list_ports 列出可用端口
    
    # 实例化控制器，开启 CSV 保存功能
    controller = MultiSourceController(
        ports=TARGET_PORTS, 
        save_csv=True, 
        csv_filename="my_experiment_data.csv"
    )
    
    # 绘图配置
    TOTAL_CHANNELS = 16 * len(TARGET_PORTS)
    MAX_DISPLAY = 1000
    OFFSET = 200
    
    plt.ion()
    fig, ax = plt.subplots(figsize=(10, 6))

    lines = [ax.plot([], [], lw=0.5)[0] for _ in range(TOTAL_CHANNELS)]
    ax.set_ylim(-OFFSET, TOTAL_CHANNELS * OFFSET + OFFSET)
    ax.set_xlim(0, MAX_DISPLAY)
    
    plot_buffer = np.zeros((TOTAL_CHANNELS, MAX_DISPLAY))
    x_idxs = np.arange(MAX_DISPLAY)
    
    try:
        controller.start()
        print("System Running... Press Ctrl+C to stop.")
        
        while True:
            # 获取对齐的数据 (内部已自动保存到CSV)
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
                
                ax.draw_artist(ax.patch)
                for line in lines: ax.draw_artist(line)
                fig.canvas.flush_events()
            else:
                time.sleep(0.005)
                
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        controller.stop()
        print("Done. Check 'my_experiment_data.csv'.")  