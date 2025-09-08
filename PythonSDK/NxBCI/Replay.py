import mmap
import struct
import os
import logging
import threading
import time
from collections import deque
from typing import List, Deque, Optional, Dict

class Replay:
    """
    A thread-safe class to replay data from a binary file, simulating a live data stream.

    This class has been refactored to use a TCP-like streaming architecture internally.
    It reads a binary file packet-by-packet in a background thread, mimicking a real-time device.
    It parses 66-byte packets containing EMG, GPS, and Gyroscope data.

    All original API methods, including load_all_data(), get_full_dataset(), and get_segment(),
    have been preserved for backward compatibility. The class now supports two primary use cases:
    
    1.  **Playback Mode**: Simulates a live data feed by streaming data into queues at a
        specific sample rate. Use start() or start_playback() to begin.
    2.  **Load Mode**: Pre-loads the entire file into memory for offline analysis. Use
        load_all_data() for this purpose.

    Example (Playback Mode):

        with Replay(FilePath='YOUR_DATA.BIN', sample_rate=500) as replayer:
            replayer.start() # or replayer.start_playback()
            time.sleep(5)
            emg_data = replayer.get_emg_data() # New, explicit API
            gps_data = replayer.get_gps_data()
            print(f"EMG Queue 0 has {len(emg_data[0])} points. Latest GPS: {list(gps_data['latitude'])[-1]}")
            replayer.stop()

    Example (Load Mode):

        with Replay(FilePath='YOUR_DATA.BIN') as replayer:
            replayer.load_all_data()
            print(f"File loaded. Total samples: {replayer.get_total_samples()}")
            full_emg_dataset = replayer.get_full_dataset()
            emg_segment = replayer.get_segment(start_sample=100, end_sample=200)
    """

    # --- Class Constants ---
    PACKET_SIZE = 66
    LSB = 1.5 / (2 ** 23)

    def __init__(self, FilePath: str, channels: int = 16, sample_rate: int = 500, duration: int = 4, isLoop: bool = False):
        """
        Initializes the Replay class.

        Args:
            FilePath (str): Path to the binary data file.
            channels (int): Number of EMG channels in the file.
            sample_rate (int): The desired playback sample rate in Hz.
            duration (int): Duration of data to store in the playback deques, in seconds.
            isLoop (bool): If True, playback will loop continuously.
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        
        if not os.path.exists(FilePath) or not os.path.isfile(FilePath):
            raise FileNotFoundError(f"[Replay] The specified file does not exist: {FilePath}")

        # --- Configuration ---
        self.file_path = FilePath
        self.num_channels = channels
        self.sample_rate = sample_rate
        self.playback_interval = 1.0 / sample_rate if sample_rate > 0 else 0
        self.isLoop = isLoop
        
        # --- Data Storage for Playback Mode ---
        queue_len = sample_rate * duration
        self.emg_data_queues: List[Deque[float]] = [deque(maxlen=queue_len) for _ in range(self.num_channels)]
        self.gps_data: Dict[str, Deque[str]] = {'latitude': deque(maxlen=10), 'longitude': deque(maxlen=10)}
        self.gyro_data: Dict[str, Deque[float]] = {'roll': deque(maxlen=queue_len), 'pitch': deque(maxlen=queue_len), 'yaw': deque(maxlen=queue_len)}
        # Preserving original API, though not populated by 66-byte packet format
        self.pose_data_queues: List[Deque[float]] = [deque(maxlen=queue_len) for _ in range(7)] 

        # --- Data Storage for Load Mode ---
        self._full_emg_data_cache: List[List[float]] = []
        self._full_gps_data_cache: Dict[str, List[str]] = {}
        self._full_gyro_data_cache: Dict[str, List[float]] = {}
        self._is_data_loaded = False

        # --- File and State Management ---
        self._file = None
        self._mmapped_file = None
        self._total_samples = 0
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._state_lock = threading.Lock()
        self._is_running = False
        self._start_sample = 0
        self._end_sample = -1

    # --- Context Manager ---
    def __enter__(self):
        self.logger.info(f"[Replay] Opening file: {self.file_path}")
        try:
            self._file = open(self.file_path, 'rb')
            self._mmapped_file = mmap.mmap(self._file.fileno(), 0, access=mmap.ACCESS_READ)
            self._total_samples = len(self._mmapped_file) // self.PACKET_SIZE
            if self._end_sample == -1: self._end_sample = self._total_samples
            self.logger.info(f"[Replay] File loaded. Contains {self._total_samples} total samples.")
        except Exception as e:
            self.logger.error(f"[Replay] Failed to open or map file: {e}")
            if self._file: self._file.close()
            raise
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.logger.info("[Replay] Closing file and stopping all activities.")
        self.stop()
        if self._mmapped_file: self._mmapped_file.close()
        if self._file: self._file.close()

    # --- New & Original Combined Playback Control API ---

    def start(self):
        """Starts the background worker thread to stream data from the file."""
        with self._state_lock:
            if self._is_running:
                self.logger.warning("[Replay] Playback service is already running.")
                return
            if self._mmapped_file is None:
                raise RuntimeError("[Replay] File is not open. Use this class within a 'with' statement.")

            self.logger.info("[Replay] Starting playback service...")
            self._stop_event.clear()
            self._is_running = True
            self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self._worker_thread.start()

    def start_playback(self):
        """Alias for start() for backward compatibility."""
        self.start()

    def stop(self):
        """Stops the background worker thread."""
        with self._state_lock:
            if not self._is_running: return
        
        self.logger.info("[Replay] Stopping playback service...")
        self._stop_event.set()
        
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)
        
        self._is_running = False
        self.logger.info("[Replay] Playback service stopped.")

    def restart_playback(self):
        """Stops any current playback and restarts from the beginning of the file."""
        self.logger.info("[Replay] Restarting playback from the beginning.")
        self.stop()
        self._start_sample = 0
        self._end_sample = self._total_samples
        self.start()

    def play_from(self, start_sample: int):
        """Starts playback from a specific sample index to the end."""
        if not (0 <= start_sample < self._total_samples):
            self.logger.error(f"[Replay] Invalid start sample: {start_sample}. Must be between 0 and {self._total_samples - 1}.")
            return
        
        self.logger.info(f"[Replay] Setting playback to start from sample {start_sample}.")
        self.stop()
        self._start_sample = start_sample
        self._end_sample = self._total_samples
        self.start()

    def play_segment(self, start_sample: int, end_sample: int):
        """Plays only a specific segment of the file, then stops."""
        if not (0 <= start_sample < end_sample <= self._total_samples):
            self.logger.error(f"[Replay] Invalid segment range: {start_sample}-{end_sample}. Max samples: {self._total_samples}")
            return
            
        self.logger.info(f"[Replay] Setting playback for segment from sample {start_sample} to {end_sample}.")
        self.stop()
        self._start_sample = start_sample
        self._end_sample = end_sample
        self.start()

    # --- Original Data Loading API ---
    
    def load_all_data(self):
        """
        Loads the entire file into memory for immediate access (Load Mode).
        This is a blocking operation and is separate from the real-time playback.
        """
        with self._state_lock:
            if self._is_data_loaded:
                self.logger.info("[Replay] Data has already been loaded.")
                return
            
            if self._mmapped_file is None:
                raise RuntimeError("[Replay] File not open. Use this class with a 'with' statement.")

            self.logger.info("[Replay] Loading all data from file into memory cache...")
            # Initialize caches
            self._full_emg_data_cache = [[] for _ in range(self.num_channels)]
            self._full_gps_data_cache = {'latitude': [], 'longitude': []}
            self._full_gyro_data_cache = {'roll': [], 'pitch': [], 'yaw': []}

            offset = 0
            while offset + self.PACKET_SIZE <= len(self._mmapped_file):
                packet = self._mmapped_file[offset : offset + self.PACKET_SIZE]
                self._process_packet_for_cache(packet)
                offset += self.PACKET_SIZE
            
            self._is_data_loaded = True
            self.logger.info(f"[Replay] Successfully loaded {self._total_samples} samples into cache.")

    # --- Worker Thread and Data Processing ---

    def _worker_loop(self):
        """The main loop for the worker thread for real-time playback."""
        try:
            self.logger.info(f"[Replay] Worker started. Playing samples from {self._start_sample} to {self._end_sample}.")
            self._receive_data_loop()
        except Exception as e:
            self.logger.error(f"[Replay] An unexpected error occurred in the worker loop: {e}", exc_info=True)
        finally:
            with self._state_lock:
                self._is_running = False
            self.logger.info("[Replay] Worker loop has terminated.")

    def _receive_data_loop(self):
        """Continuously reads and processes data from the file for playback."""
        current_offset = self._start_sample * self.PACKET_SIZE
        end_offset = self._end_sample * self.PACKET_SIZE
        start_time = time.monotonic()
        packet_count = 0

        while not self._stop_event.is_set():
            if current_offset >= end_offset:
                if self.isLoop:
                    self.logger.info("[Replay] Reached end of segment, looping.")
                    current_offset = self._start_sample * self.PACKET_SIZE
                    packet_count = 0
                    start_time = time.monotonic()
                else:
                    self.logger.info("[Replay] Reached end of playback segment.")
                    break

            # In this simulation, we can read one full packet at a time
            if current_offset + self.PACKET_SIZE > len(self._mmapped_file):
                break # End of file

            packet = self._mmapped_file[current_offset : current_offset + self.PACKET_SIZE]
            current_offset += self.PACKET_SIZE
            self._process_packet_for_playback(packet)
            packet_count += 1

            # Timing logic to simulate sample rate
            next_packet_target_time = start_time + packet_count * self.playback_interval
            sleep_duration = next_packet_target_time - time.monotonic()
            if sleep_duration > 0:
                time.sleep(sleep_duration)

    def _process_packet_for_playback(self, packet: bytes):
        """Parses a packet and appends data to the real-time queues."""
        self._parse_and_append(packet, self.emg_data_queues, self.gps_data, self.gyro_data, is_queue=True)

    def _process_packet_for_cache(self, packet: bytes):
        """Parses a packet and appends data to the full data caches."""
        self._parse_and_append(packet, self._full_emg_data_cache, self._full_gps_data_cache, self._full_gyro_data_cache, is_queue=False)

    def _parse_and_append(self, packet, emg_dest, gps_dest, gyro_dest, is_queue):
        """Generic packet parser that appends to either queues or lists."""
        try:
            # EMG Data
            for i in range(self.num_channels):
                offset = i * 3
                uint24_val = int.from_bytes(packet[offset:offset+3], 'big', signed=False)
                voltage = self._extract_voltage(uint24_val)
                emg_dest[i].append(voltage)
            
            # GPS Data (if valid)
            if packet[48] == 0x59:
                lat, lon, lat_dir, lon_dir = self._parse_gps_from_packet(packet)
                gps_dest['latitude'].append(f"{lat}°{lat_dir}")
                gps_dest['longitude'].append(f"{lon}°{lon_dir}")
            elif not is_queue: # For caching, add placeholder if invalid
                gps_dest['latitude'].append(None)
                gps_dest['longitude'].append(None)

            # Gyroscope Data (if valid)
            if packet[59] == 0x59:
                roll, pitch, yaw = self._parse_gyro_from_packet(packet)
                gyro_dest['roll'].append(roll)
                gyro_dest['pitch'].append(pitch)
                gyro_dest['yaw'].append(yaw)
            elif not is_queue: # For caching, add placeholder if invalid
                gyro_dest['roll'].append(None)
                gyro_dest['pitch'].append(None)
                gyro_dest['yaw'].append(None)
        except Exception as e:
            self.logger.error(f"[Replay] Failed to process packet: {e}", exc_info=True)
    
    # --- Private Helper Methods ---

    def _parse_gps_from_packet(self, packet: bytes):
        lat_val_raw = struct.unpack('>f', packet[49:53])[0]
        lon_val_raw = struct.unpack('>f', packet[54:58])[0]
        lat_dir = packet[53:54].decode('ascii') if packet[53:54] in {b'N', b'S'} else ' '
        lon_dir = packet[58:59].decode('ascii') if packet[58:59] in {b'E', b'W'} else ' '
        lat, lon = self._convert_gps_to_decimal(lat_val_raw, lon_val_raw)
        return lat, lon, lat_dir, lon_dir

    def _parse_gyro_from_packet(self, packet: bytes):
        roll_raw = int.from_bytes(packet[60:62], 'little', signed=True)
        pitch_raw = int.from_bytes(packet[62:64], 'little', signed=True)
        yaw_raw = int.from_bytes(packet[64:66], 'little', signed=True)
        roll = roll_raw / 32768.0 * 180.0
        pitch = pitch_raw / 32768.0 * 180.0
        yaw = yaw_raw / 32768.0 * 180.0
        return roll, pitch, yaw
        
    def _convert_gps_to_decimal(self, lat_raw: float, lon_raw: float):
        """Converts raw DDMM.MMMM format to decimal degrees."""
        lat = int(lat_raw / 100) + (lat_raw % 100) / 60.0
        lon = int(lon_raw / 100) + (lon_raw % 100) / 60.0
        return lat, lon
        
    def _extract_voltage(self, uint24_value: int) -> float:
        """Converts a 24-bit raw value to a voltage value in millivolts (mV)."""
        if uint24_value & (1 << 23):
            raw_value = uint24_value - (1 << 24)
        else:
            raw_value = uint24_value
        return raw_value * self.LSB * 1000

    # --- Public API for Status and Data Retrieval ---

    def is_running(self) -> bool:
        """Checks if the playback thread is currently active."""
        with self._state_lock:
            return self._is_running

    def get_total_samples(self) -> int:
        """Returns the total number of samples detected in the file."""
        return self._total_samples
    
    # --- New, Explicit Data Getters ---

    def get_emg_data(self) -> List[Deque[float]]:
        """Returns a copy of the playback EMG data deques."""
        with self._state_lock:
            return [q.copy() for q in self.emg_data_queues]
    
    def get_gps_data(self) -> Dict[str, Deque[str]]:
        """Returns a copy of the playback GPS data deques."""
        with self._state_lock:
            return {key: q.copy() for key, q in self.gps_data.items()}

    def get_gyro_data(self) -> Dict[str, Deque[float]]:
        """Returns a copy of the playback Gyroscope data deques."""
        with self._state_lock:
            return {key: q.copy() for key, q in self.gyro_data.items()}

    # --- Original Data Retrieval API (Preserved) ---
    
    def get_data(self) -> List[Deque[float]]:
        """
        [Backward Compatibility] Returns a copy of the playback EMG data deques.
        This is an alias for get_emg_data().
        """
        return self.get_emg_data()
    
    def get_full_dataset(self) -> List[List[float]]:
        """
        [Load Mode] Returns the entire EMG dataset after it has been loaded.
        Requires load_all_data() to have been called first.
        """
        if not self._is_data_loaded:
            self.logger.warning("[Replay] Data not loaded. Call load_all_data() first. Returning empty list.")
            return []
        return self._full_emg_data_cache

    def get_segment(self, start_sample: int, end_sample: int) -> List[List[float]]:
        """
        [Load Mode] Returns a specific segment of the EMG data.
        Requires load_all_data() to have been called first.
        """
        if not self._is_data_loaded:
            self.logger.warning("[Replay] Data not loaded. Call load_all_data() first. Returning empty list.")
            return []
        if not (0 <= start_sample < end_sample <= self._total_samples):
            self.logger.error(f"[Replay] Invalid sample range: {start_sample}-{end_sample}. Max samples: {self._total_samples}")
            return []
        
        return [ch_data[start_sample:end_sample] for ch_data in self._full_emg_data_cache]
    
    def pose_GetData(self) -> List[Deque[float]]:
        """
        [Deprecated] Retrieves the latest pose data.
        NOTE: The current 66-byte packet format does not populate this data.
        This method is preserved for API compatibility and will return empty deques.
        """
        return [q.copy() for q in self.pose_data_queues]