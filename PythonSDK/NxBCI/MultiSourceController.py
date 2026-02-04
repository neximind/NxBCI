
import time
import logging
import numpy as np
from typing import List, Optional
from collections import deque
from NxBCI.AsyncCSVLogger import AsyncCSVLogger
from NxBCI.Serial_Receiver import Serial_Receiver

class MultiSourceController:
    """
    Controller for synchronized multi-device data acquisition and logging.

    This class manages multiple `Serial_Receiver` instances, aligns their data streams
    based on frame count, and optionally streams the data to a CSV file.

    Features:
        - Auto-synchronization reset.
        - Data alignment (intersection of available frames).
        - Asynchronous CSV logging (saving raw data with 4 decimal precision).
    """

    def __init__(self, ports: List[str], save_csv: bool = False, csv_filename: str = "emg_data.csv"):
        """
        Initialize the Controller.

        Args:
            ports: List of COM port names (e.g., ['COM3', 'COM4']).
            save_csv: If True, enables automatic logging to CSV.
            csv_filename: File path for the CSV output.
        """
        self.logger = logging.getLogger("SyncCtrl")
        self.receivers = [Serial_Receiver(port) for port in ports]
        self.num_devs = len(ports)
        
        # Alignment Buffers
        self.local_buffers = [deque() for _ in range(self.num_devs)]
        
        # CSV Logging Setup
        self.save_csv = save_csv
        self.csv_logger: Optional[AsyncCSVLogger] = None
        
        if save_csv:
            total_channels = 16 * self.num_devs
            self.csv_logger = AsyncCSVLogger(csv_filename, total_channels)

    def start(self):
        """
        Open all ports, reset synchronization, and start logging (if enabled).
        """
        for rx in self.receivers:
            rx.open()
        
        time.sleep(0.5)
        self.logger.info("Performing Sync Reset...")
        for rx in self.receivers:
            rx.reset_internal_buffers()
        
        if self.csv_logger:
            self.csv_logger.start()
            
        self.logger.info("Multi-source acquisition started.")

    def stop(self):
        """
        Stop all ports and finalize the CSV file.
        """
        for rx in self.receivers:
            rx.close()
        
        if self.csv_logger:
            self.csv_logger.stop()
            
        self.logger.info("Multi-source acquisition stopped.")

    def get_aligned_data(self) -> Optional[np.ndarray]:
        """
        Retrieve a chunk of aligned data from all devices.

        This method automatically pushes the aligned data to the CSV logger
        if `save_csv` was enabled during initialization.

        Returns:
            np.ndarray: A matrix of shape (Total_Channels, Aligned_Length).
                        Returns None if not enough data is available for alignment.
        """
        for i, rx in enumerate(self.receivers):
            new_chunk = rx.pop_new_data() 
            if new_chunk is not None:
                self.local_buffers[i].append(new_chunk)

        flat_buffers = []
        for i in range(self.num_devs):
            if len(self.local_buffers[i]) > 0:
                merged = np.concatenate(self.local_buffers[i], axis=1) 
                flat_buffers.append(merged)
                self.local_buffers[i].clear() 
            else:
                flat_buffers.append(np.empty((16, 0)))

        lengths = [b.shape[1] for b in flat_buffers]
        min_len = min(lengths)

        if min_len == 0:
            for i, buf in enumerate(flat_buffers):
                if buf.shape[1] > 0:
                    self.local_buffers[i].append(buf)
            return None

        output_chunks = []
        for i in range(self.num_devs):
            valid_part = flat_buffers[i][:, :min_len] 
            output_chunks.append(valid_part)
            
            leftover = flat_buffers[i][:, min_len:]
            if leftover.shape[1] > 0:
                self.local_buffers[i].append(leftover)

        final_matrix = np.vstack(output_chunks)

        if self.csv_logger:
            self.csv_logger.push_data(final_matrix)

        return final_matrix