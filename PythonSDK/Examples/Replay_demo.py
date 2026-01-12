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

filepath = os.path.join(current_dir, "EMGDATA_500Hz_mixdata.bin")

try:
    with Replay(FilePath=filepath, sample_rate=500,isLoop=True) as replay:
        
        replay.load_all_data()

        print("--- Starting playback from the beginning ---")
        replay.restart_playback()
        time.sleep(2) 

        CHANNELS = replay.num_channels
        MAX_POINTS = replay.emg_data_queues[0].maxlen 
        OFFSET = 200
        emg_data = replay.get_emg_data() 
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

        while plt.fignum_exists(fig.number):
            data = replay.get_data()
            if not data or not data[0]:
                plt.pause(0.1)
                continue
            
            for i in range(CHANNELS):
                y_points = list(data[i])
                current_len = len(y_points)
                
                if current_len > 0:
                    y_data = np.array(y_points) + i * OFFSET
                    lines[i].set_data(x_data_full[:current_len], y_data)
                
            fig.canvas.draw()
            fig.canvas.flush_events()
            plt.pause(0.01)

except FileNotFoundError as e:
    logging.error(e)
except KeyboardInterrupt:
    print("\nPlotting stopped by user.")
finally:
    print("Cleanup complete.")