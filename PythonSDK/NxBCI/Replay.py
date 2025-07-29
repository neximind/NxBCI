import mmap
import struct
import os
import logging
import threading
import time
from collections import deque
from typing import List, Deque, Optional, Tuple

class Replay:
    """
    A thread-safe class to replay data from a binary file, simulating a live feed.

    This class offers two modes of operation:
    1.  **Load Mode**: Reads the entire data file into memory for quick access,
        analysis, and seeking specific segments.
    2.  **Playback Mode**: Starts a background thread that "plays" data samples
        at the specified sample rate into a deque, perfectly simulating a live
        data source like a TCP or MQTT receiver.

    This class is designed as a context manager to ensure resources are properly closed.

    Example (Playback Mode):
        with Replay(FilePath='EEGDATA.BIN', sample_rate=500) as replayer:
            replayer.start_playback()
            for _ in range(10):
                time.sleep(1)
                data = replayer.get_data() # Gets the last ~4 seconds of played data
                if data and data[0]:
                    print(f"Playback running. Channel 0 has {len(data[0])} points.")

    Example (Load Mode):
        with Replay(FilePath='EEGDATA.BIN') as replayer:
            replayer.load_all_data()
            print(f"File loaded. Total samples: {replayer.get_total_samples()}")
            full_dataset = replayer.get_full_dataset()
            segment = replayer.get_segment(start_sample=500, end_sample=1000)
    """

    # --- Constants ---
    LSB = 1.5 / (2 ** 23)
    ACCE_LSB = 4 / (2**15)
    GYPO_LSB = 1000 / (2**15)
    DATA_CHANNELS = 16
    DATA_SIZE = 3 # 24-bit sample = 3 bytes
    DATA_PACKET_BYTES = DATA_CHANNELS * DATA_SIZE # 16 * 3 = 48 bytes

    SEPARATOR_BYTES = 2
    MPU_CHANNELS = 7
    MPU_DATA_BYTES = MPU_CHANNELS * 2
    FULL_PACKET_SIZE = DATA_PACKET_BYTES + SEPARATOR_BYTES + MPU_DATA_BYTES # 48 + 2 + 14 = 64


    def __init__(self, FilePath: str, channels: int = 16, sample_rate: int = 500, duration: int = 4, isLoop: bool = False):
        """
        Initializes the Replay.

        This method is lightweight and does not perform any file I/O.

        Args:
            FilePath (str): Path to the binary data file.
            channels (int): Number of data channels in the file.
            sample_rate (int): The desired playback sample rate in Hz.
            duration (int): Duration of data to store in the playback deque in seconds.
            isLoop (bool): Whether to loop playback continuously.
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        
        if not os.path.exists(FilePath) or not os.path.isfile(FilePath):
            raise FileNotFoundError(f"[Replay] The specified file does not exist: {FilePath}")

        self.file_path = FilePath
        self.channels = channels
        self.sample_rate = sample_rate
        self.playback_interval = 1.0 / sample_rate if sample_rate > 0 else 0
        self.isLoop = isLoop

        # --- Playback Data Queues (public interface) ---
        self.data_queues: List[Deque[float]] = [deque(maxlen=sample_rate * duration) for _ in range(channels)]
        self.mpu_sample_rate = 100
        self.mpu_data_queues: List[Deque[float]] = [deque(maxlen=100) for _ in range(self.MPU_CHANNELS)]

        # --- Internal State ---
        self._file = None
        self._mmapped_file = None
        self._full_data_cache: List[List[float]] = []
        self._full_mpu_data_cache:List[List[float]] = []
        self._total_samples = 0
        
        self._state_lock = threading.Lock()
        self._playback_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._is_running = False

    # --- Context Manager for resource safety ---
    def __enter__(self):
        self.logger.info(f"[Replay] Opening replay file: {self.file_path}")
        self._file = open(self.file_path, 'rb')
        self._mmapped_file = mmap.mmap(self._file.fileno(), 0, access=mmap.ACCESS_READ)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logger.info("[Replay] Closing replay file and stopping all activities.")
        self.stop()
        if self._mmapped_file:
            self._mmapped_file.close()
        if self._file:
            self._file.close()

    # --- Core Functionality ---

    def start_playback(self):
        """
        Starts replaying the data from the beginning.
        This is now an alias for restart_playback().
        """
        self.restart_playback()

    def stop(self):
        """Stops the background playback thread if it is running."""
        with self._state_lock:
            if not self._is_running:
                return
            self._is_running = False

        self.logger.info("[Replay] Stopping playback thread...")
        self._stop_event.set()
        if self._playback_thread and self._playback_thread.is_alive():
            self._playback_thread.join(timeout=1)
        self.logger.info("[Replay] Playback stopped.")
        
    def restart_playback(self):
        """
        Restarts playback from the very beginning of the file (sample 0).
        If playback is already running, it will be stopped and restarted.
        """
        self.logger.info("[Replay] Restarting playback from beginning.")
        # Load data if not already loaded
        if not self._full_data_cache:
            self.load_all_data()
        self._start_playback_thread(start_sample=0, end_sample=self._total_samples)

    def play_from(self, start_sample: int):
        """
        Starts playback from a specific sample index until the end of the file.

        Args:
            start_sample (int): The sample index to start playing from.
        """
        # Load data if not already loaded
        if not self._full_data_cache:
            self.load_all_data()
            
        if not (0 <= start_sample < self._total_samples):
            self.logger.error(f"[Replay] Invalid start sample: {start_sample}. Must be between 0 and {self._total_samples - 1}.")
            return
        
        self.logger.info(f"[Replay] Starting playback from sample {start_sample}.")
        self._start_playback_thread(start_sample=start_sample, end_sample=self._total_samples)

    def play_segment(self, start_sample: int, end_sample: int):
        """
        Plays only a specific segment of the data file, then stops.

        Args:
            start_sample (int): The starting sample index of the segment.
            end_sample (int): The ending sample index of the segment (exclusive).
        """
        # Load data if not already loaded
        if not self._full_data_cache:
            self.load_all_data()
            
        if not (0 <= start_sample < end_sample <= self._total_samples):
            self.logger.error(f"[Replay] Invalid segment range: {start_sample}-{end_sample}. Max samples: {self._total_samples}")
            return
        
        self.logger.info(f"[Replay] Playing segment from sample {start_sample} to {end_sample}.")
        self._start_playback_thread(start_sample=start_sample, end_sample=end_sample)

    def load_all_data(self):
        """
        Loads the entire file into memory for immediate access.

        This is a blocking operation. After it completes, you can use methods like
        get_full_dataset() and get_total_samples().
        """
        with self._state_lock:
            if self._full_data_cache:
                self.logger.info("Data has already been loaded.")
                return
            self._load_data_from_map()
        self.logger.info(f"[Replay] Successfully loaded {self._total_samples} samples for {self.channels} channels.")

    # --- Private Helper Methods ---

    def _start_playback_thread(self, start_sample: int, end_sample: int):
        """
        A centralized, private method to safely start the playback thread.
        
        This method handles stopping any existing thread, loading data if needed,
        and launching the new playback thread with the specified range.
        """
        with self._state_lock:
            if self._is_running:
                self.stop() # Stop any current playback first

            if not self._full_data_cache:
                self.logger.info("[Replay] Data not pre-loaded, loading now before playback...")
                self._load_data_from_map()
                if not self._full_data_cache:
                    self.logger.error("[Replay] Failed to load data, cannot start playback.")
                    return

            self._stop_event.clear()
            self._is_running = True
            
            # The target now passes arguments to the loop
            self._playback_thread = threading.Thread(
                target=self._playback_loop, 
                args=(start_sample, end_sample),
                daemon=True
            )
            self._playback_thread.start()
    
    def _playback_loop(self, start_index: int, end_index: int):
        """
        The background thread loop that simulates real-time data.
        It now accepts a start and end index to control the playback range.
        
        Args:
            start_index (int): The starting sample index for this playback session.
            end_index (int): The loop will stop when the index reaches this value.
        """
        self.logger.info(f"[Replay] Playback loop started. Range: {start_index} -> {end_index}. Loop: {self.isLoop}")
        current_index = start_index
        start_time = time.monotonic()

        # The loop condition now checks for the stop event
        # If looping is enabled, we don't check the end condition
        while not self._stop_event.is_set():
            # Check if we've reached the end and handle accordingly
            if current_index >= end_index:
                if self.isLoop:
                    # Reset to start for continuous looping
                    current_index = start_index
                    self.logger.info(f"[Replay] Looping: Reset to start_index {start_index}")
                else:
                    # Exit loop if not looping
                    break
            
            # Get the sample for the current index
            sample_data = self._get_sample_from_cache(current_index)
            mpu_sample_data = self._get_mpu_sample_from_cache(current_index)
            # Append data to public queues (this is thread-safe)
            for i in range(self.channels):
                self.data_queues[i].append(sample_data[i])
            
            for i in range(7):
                self.mpu_data_queues[i].append(mpu_sample_data[i])
                
            next_sample_target_time = start_time + (current_index - start_index + 1) * self.playback_interval
            current_time = time.monotonic()
            sleep_duration = next_sample_target_time - current_time
            if sleep_duration > 0:
                time.sleep(sleep_duration)

            current_index += 1
            
        
        reason = "Stopped by user" if self._stop_event.is_set() else "End of segment"
        self.logger.info(f"[Replay] Playback loop finished. Reason: {reason}")
        with self._state_lock:
            self._is_running = False

    def _load_data_from_map(self):
        """Internal method to parse the entire memory-mapped file into a list."""
        if self._mmapped_file is None:
            raise RuntimeError("[Replay] File is not open. Use this class with a 'with' statement.")

        self._full_data_cache = [[] for _ in range(self.channels)]
        self._full_mpu_data_cache = [[] for _ in range(self.MPU_CHANNELS)]
        offset = 0
        while offset + self.FULL_PACKET_SIZE <= len(self._mmapped_file):
            packet = self._mmapped_file[offset : offset + self.FULL_PACKET_SIZE]
            eeg_data, mpu_data = self._parse_packet(packet)

            for i in range(self.channels):
                self._full_data_cache[i].append(eeg_data[i])

            for i in range(self.MPU_CHANNELS):
                self._full_mpu_data_cache[i].append(mpu_data[i])

            offset += self.FULL_PACKET_SIZE
        
        if self._full_data_cache and self._full_data_cache[0]:
            self._total_samples = len(self._full_data_cache[0])

    def _parse_packet(self, packet: bytes) -> List[float]:
        """Parses a single 48-byte packet into 16 voltage values."""
        voltages = []
        for i in range(self.channels):
            start = i * self.DATA_SIZE
            raw_value = int.from_bytes(packet[start : start + self.DATA_SIZE], 'big', signed=True)
            voltages.append(raw_value * self.LSB * 1000)

        separator = struct.unpack(">H", packet[self.DATA_PACKET_BYTES:self.DATA_PACKET_BYTES+self.SEPARATOR_BYTES])[0]
        mpu_data = [0.0] * self.MPU_CHANNELS  # Default to zeros

        if separator == 0xFFFF:
            mpu_bytes = struct.unpack(">7h",packet[self.DATA_PACKET_BYTES+self.SEPARATOR_BYTES:self.FULL_PACKET_SIZE])
            mpu_data = [
                mpu_bytes[0]*self.ACCE_LSB,
                mpu_bytes[1]*self.ACCE_LSB,
                mpu_bytes[2]*self.ACCE_LSB,
                (mpu_bytes[3] / 333.87) + 21,
                mpu_bytes[4]*self.GYPO_LSB,
                mpu_bytes[5]*self.GYPO_LSB,
                mpu_bytes[6]*self.GYPO_LSB
            ]
        elif separator != 0x0000:
            self.logger.error(f"[Replay] Unexpected separator:{separator:#06x}")
                
        return voltages,mpu_data
    
    def _get_sample_from_cache(self, index: int) -> List[float]:
        """Retrieves a single time sample for all channels from the cache."""
        return [self._full_data_cache[ch][index] for ch in range(self.channels)]

    def _get_mpu_sample_from_cache(self, index: int) -> List[float]:
        """Retrieves a single time sample for all channels from the cache."""
        return [self._full_mpu_data_cache[ch][index] for ch in range(self.MPU_CHANNELS)]
    
    # --- Public API for Data Retrieval ---

    def get_data(self) -> List[Deque[float]]:
        """
        Returns a copy of the playback data deques. 
        
        This is the primary way to get data during real-time playback simulation.
        """
        return [q.copy() for q in self.data_queues]

    def get_full_dataset(self) -> List[List[float]]:
        """
        Returns the entire dataset after it has been loaded.
        
        Requires load_all_data() to be called first.
        """
        if not self._full_data_cache:
            self.logger.warning("[Replay] Data not loaded. Call load_all_data() first. Returning empty list.")
        return self._full_data_cache

    def get_segment(self, start_sample: int, end_sample: int) -> List[List[float]]:
        """
        Returns a specific segment of the data.
        
        Requires load_all_data() to be called first.
        """
        if not self._full_data_cache:
            self.logger.warning("[Replay] Data not loaded. Call load_all_data() first. Returning empty list.")
            return []
        if not (0 <= start_sample < end_sample <= self._total_samples):
            self.logger.error(f"[Replay] Invalid sample range: {start_sample}-{end_sample}. Max samples: {self._total_samples}")
            return []
        
        return [ch_data[start_sample:end_sample] for ch_data in self._full_data_cache]
    
    def pose_GetData(self):
        """
        Retrieves the latest pose and temperature information
        Returns:
            A "deque" containing:
            
            - X_a  : Acceleration along the x-axis.
            - Y_a  : Acceleration along the y-axis.
            - Z_a  : Acceleration along the z-axis.
            - T    : Temperature in degrees Celsius.
            - ω_x  : Angular velocity along the x-axis.
            - ω_y  : Angular velocity along the y-axis.
            - ω_z  : Angular velocity along the z-axis.
        """
        if not self.is_running():
            self.logger.error("[Replay] The playback thread is not running")
            return None


        if not self.mpu_data_queues or not self.mpu_data_queues[0]:
            self.logger.error("[Replay] The MPU buffer is empty.")
            return None
        
        return [q.copy() for q in self.mpu_data_queues]
    

    def get_total_samples(self) -> int:
        """Returns the total number of samples in the file."""
        if not self._full_data_cache:
             self.logger.warning("[Replay] Data not loaded. Call load_all_data() first. Returning 0.")
             return 0
        return self._total_samples

    def is_running(self) -> bool:
        """Checks if the playback thread is currently active."""
        with self._state_lock:
            return self._is_running