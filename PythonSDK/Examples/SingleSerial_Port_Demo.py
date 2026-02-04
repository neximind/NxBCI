import sys
import os

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

import matplotlib.pyplot as plt
import numpy as np
import logging
from NxBCI.Serial_Receiver import Serial_Receiver

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
receiver = Serial_Receiver(port='COM3')
receiver.open()

CHANNELS = 16
MAX_POINTS = 1000*4
OFFSET = 200

plt.ion() 
fig, ax = plt.subplots(figsize=(15, 9))

lines = [ax.plot([], [])[0] for _ in range(CHANNELS)]

ax.set_title(f"{CHANNELS}-Channel Real-Time Data Plot")
ax.set_xlabel("Time Points")
ax.set_ylabel("Voltage (Channels separated by offset)")
ax.set_xlim(0, MAX_POINTS)
ax.set_ylim(-OFFSET, CHANNELS * OFFSET)
ax.grid(True, linestyle='--', alpha=0.6)

ax.set_yticks([]) 
fig.tight_layout()
x_data_full = np.arange(MAX_POINTS)

print("Starting plot... Press Ctrl+C in the terminal or close the plot window to stop.")

try:
   
    while plt.fignum_exists(fig.number):

        all_channels_data = receiver.get_emg_data()

        if not all_channels_data or not all_channels_data[0]:
            plt.pause(0.1)
            continue

        for i in range(CHANNELS):
            y_points = list(all_channels_data[i])
            current_len = len(y_points)
            
            if current_len > 0:
                y_data = np.array(y_points) + i * OFFSET
                lines[i].set_data(x_data_full[:current_len], y_data)
        
        fig.canvas.draw()
        fig.canvas.flush_events()
        plt.pause(0.01)

except KeyboardInterrupt:
    print("\nPlotting stopped by user.")
finally:
    print("Cleaning up resources...")
    receiver.close()
    print("Serial Receiver stopped.")
    plt.ioff() # 关闭交互模式
    print("Plot display finished.")