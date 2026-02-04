import threading
import queue
import logging
import os
import numpy as np
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class AsyncCSVLogger:
    """
    Thread-safe asynchronous CSV logger implementing the Producer-Consumer pattern.

    This class handles file I/O operations in a dedicated background thread to ensure
    that high-frequency data acquisition is not blocked by disk write latency.

    Attributes:
        filename (str): Path to the output CSV file.
        total_channels (int): Total number of data channels.
    """

    def __init__(self, filename: str, total_channels: int):
        """
        Initialize the AsyncCSVLogger.

        Args:
            filename: Target file path (e.g., 'data/record.csv').
                      Directories will be created automatically if they don't exist.
            total_channels: The total number of columns (excluding Index) to write.
        """
        self.logger = logging.getLogger("CSV_Logger")
        self.filename = filename
        self.total_channels = total_channels
        
        self.queue = queue.Queue()
        self.stop_event = threading.Event()
        self.write_thread: Optional[threading.Thread] = None
        self.sample_index = 0

    def start(self):
        """
        Start the background logging thread and initialize the CSV file.

        Creates the file and writes the header row: "Index,ch0,ch1,..."
        """
        folder = os.path.dirname(self.filename)
        if folder and not os.path.exists(folder):
            os.makedirs(folder)
            
        with open(self.filename, 'w', newline='') as f:
            header = ["Index"] + [f"ch{i}" for i in range(self.total_channels)]
            f.write(",".join(header) + "\n")
            
        self.stop_event.clear()
        self.write_thread = threading.Thread(target=self._write_loop, daemon=True)
        self.write_thread.start()
        self.logger.info(f"Recording started: {self.filename}")

    def stop(self):
        """
        Stop the logging thread safely.

        Waits for the background thread to finish processing remaining queue items
        (with a timeout) before returning.
        """
        self.stop_event.set()
        if self.write_thread and self.write_thread.is_alive():
            self.write_thread.join(timeout=2.0)
        self.logger.info("Recording stopped.")

    def push_data(self, data_matrix: np.ndarray):
        """
        Push a batch of data into the write queue.

        Args:
            data_matrix: A numpy array of shape (channels, samples).
                         The method automatically transposes it for row-wise writing.
        
        Note:
            This method is non-blocking and returns immediately.
        """
        if data_matrix.size > 0:
            self.queue.put(data_matrix.T)

    def _write_loop(self):
        """
        Internal loop running in the background thread.
        Consumes data chunks from the queue and writes formatted lines to disk.
        """
        while not self.stop_event.is_set() or not self.queue.empty():
            try:
                chunk = self.queue.get(timeout=0.1)
                
                with open(self.filename, 'a', newline='') as f:
                    lines = []
                    for row in chunk:
                        vals = ",".join([f"{x:.4f}" for x in row])
                        lines.append(f"{self.sample_index},{vals}\n")
                        self.sample_index += 1
                    
                    f.writelines(lines)
                    
            except queue.Empty:
                continue
            except Exception as e:
                self.logger.error(f"Write error: {str(e)}")