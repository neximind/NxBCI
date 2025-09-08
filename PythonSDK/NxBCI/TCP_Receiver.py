import socket
import struct
import threading
import time
import logging
from collections import deque
from typing import List, Optional, Deque, Dict, Union

class TCP_Receiver:
    """
    A thread-safe TCP receiver for continuously acquiring data streams from a device.

    This class utilizes a single worker thread model to automatically handle
    connection, data reception, and auto-reconnection upon disconnection.
    All public methods are designed to be thread-safe.

    Updated to support 66-byte data packets which include EMG, GPS, and Gyroscope data.
    
    WARNING: This version only stores GPS and Gyroscope data when it is marked as valid.
    This will lead to data desynchronization between EMG, GPS, and Gyroscope streams
    if some packets contain invalid data. Use with caution.

    Example Usage:

        # Configure logging in your main script
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        
        # Initialize the receiver
        receiver = TCP_Receiver(channels=16, sample_rate=500, Ip="192.168.4.1", port=8080)
        
        # Start the background worker thread
        receiver.start()

        try:
            while True:
                time.sleep(2)
                if receiver.is_connected():
                    print("\n--- Connection is ON ---")
                    # Safely get a copy of the data queues
                    emg_data = receiver.get_emg_data()
                    gps_data = receiver.get_gps_data()
                    gyro_data = receiver.get_gyro_data()

                    print(f"Queue lengths: EMG={len(emg_data[0]) if emg_data else 0}, GPS={len(gps_data['latitude']) if gps_data else 0}, Gyro={len(gyro_data['roll']) if gyro_data else 0}")

                    if gps_data and gps_data['latitude']:
                        print(f"Latest GPS Data: Latitude={list(gps_data['latitude'])[-1]}, Longitude={list(gps_data['longitude'])[-1]}")
                    else:
                        print("No valid GPS data received yet.")

                    if gyro_data and gyro_data['roll']:
                        print(f"Latest GYRO Data: Roll={list(gyro_data['roll'])[-1]}°, Pitch={list(gyro_data['pitch'])[-1]}°,Yaw={list(gyro_data['yaw'])[-1]}°")
                    else:
                        print("No valid GYRO data received yet.")
                else:
                    print("Connection is OFF. Waiting for the receiver to reconnect...")

        except KeyboardInterrupt:
            print("Program interrupted by user.")
        finally:
            print("Stopping receiver service...")
            # Ensure the thread and resources are cleaned up on exit
            receiver.stop()
            print("Receiver service stopped.")
    """

    # --- Class Constants ---
    PACKET_SIZE = 66  # Expected size of each TCP packet in bytes (48 EMG + 18 GPS/Gyro)
    RECONNECT_DELAY = 3  # Delay in seconds before attempting to reconnect

    def __init__(self, channels: int = 16, sample_rate: int = 500, duration: int = 4, Ip: str = "192.168.4.1", port: int = 8080):
        """
        Initializes the TCP receiver.

        Note: This method only sets up the object's state and does not
        initiate any network activity or threads. Call the start() method
        after object creation to begin operations.
        """
        # Set up a logger specific to this class instance
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Data storage and configuration
        self.num_channels = channels
        queue_len = sample_rate * duration

        # EMG data queues
        self.emg_data_queues: List[Deque[float]] = [deque(maxlen=queue_len) for _ in range(channels)]
        
        # GPS data storage
        
        self.gps_data: Dict[str, Deque[str]] = {
            'latitude': deque(maxlen=10),
            'longitude': deque(maxlen=10)
        }
        
        # Gyroscope data storage
        self.gyro_data: Dict[str, Deque[float]] = {
            'roll': deque(maxlen=2000),
            'pitch': deque(maxlen=2000),
            'yaw': deque(maxlen=2000)
        }
        
        # Voltage conversion constants
        self.LSB = 1.5 / (2 ** 23)  # Least Significant Bit resolution for voltage conversion

        # Connection parameters
        self.server_address = (Ip, port)

        # Thread and state management
        self._worker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._client_socket: Optional[socket.socket] = None
        
        # Thread-safe locks for shared resources
        self._socket_lock = threading.Lock()
        self._state_lock = threading.Lock()

        # Thread-safe status flags, protected by _state_lock
        self._is_connected = False
        self._is_receiving = False

        self.logger.info(f"[TCP_Receiver] initialized for {Ip}:{port}. Call start() to begin.")

    def start(self):
        """
        Starts the background worker thread.
        """
        with self._state_lock:
            if self._worker_thread and self._worker_thread.is_alive():
                self.logger.warning("[TCP_Receiver] Receiver service is already running.")
                return

            self.logger.info("[TCP_Receiver] Starting receiver service...")
            self._stop_event.clear()
            self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self._worker_thread.start()

    def stop(self):
        """
        Stops the background worker thread and cleans up resources.
        """
        self.logger.info("[TCP_Receiver] Stopping receiver service...")
        self._stop_event.set()
        
        with self._socket_lock:
            if self._client_socket:
                self._client_socket.close()
        
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)
        
        self.logger.info("[TCP_Receiver] Receiver service stopped.")

    def _worker_loop(self):
        """
        The main loop for the single worker thread.
        """
        while not self._stop_event.is_set():
            try:
                self.logger.info(f"[TCP_Receiver] Attempting to connect to {self.server_address}...")
                with self._socket_lock:
                    self._client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self._client_socket.settimeout(5.0)
                    self._client_socket.connect(self.server_address)
                
                with self._state_lock:
                    self._is_connected = True
                self.logger.info("[TCP_Receiver] Connection established successfully.")

                self._receive_data_loop()

            except (socket.timeout, socket.error) as e:
                self.logger.error(f"[TCP_Receiver] A connection or communication error occurred: {e}. Will retry...")
            finally:
                self._cleanup_connection()
            
            if not self._stop_event.is_set():
                self._stop_event.wait(self.RECONNECT_DELAY)
        
        self.logger.info("[TCP_Receiver] Worker loop has terminated.")
    
    def _receive_data_loop(self):
        """
        Continuously receives and processes data on an established connection.
        """
        buffer = b''
        while not self._stop_event.is_set():
            try:
                with self._socket_lock:
                    if not self._client_socket: break
                    read_size = self.PACKET_SIZE - len(buffer)
                    data = self._client_socket.recv(read_size)

                if not data:
                    self.logger.warning("[TCP_Receiver] Connection closed by the peer.")
                    break

                buffer += data

                if len(buffer) >= self.PACKET_SIZE:
                    packet = buffer[:self.PACKET_SIZE]
                    buffer = buffer[self.PACKET_SIZE:]
                    self._process_packet(packet)
                    with self._state_lock:
                        self._is_receiving = True

            except socket.error as e:
                self.logger.error(f"[TCP_Receiver] Socket error during data reception: {e}")
                break

    def _process_packet(self, packet: bytes):
        """Parses a 66-byte packet and appends the data to the respective queues."""
        try:
            # --- 1. Process first 48 bytes for EMG data ---
            voltages = []
            for i in range(self.num_channels):
                offset = i * 3
                bytes_24 = packet[offset:offset+3]
                uint24_val = int.from_bytes(bytes_24, 'big', signed=False)
                voltages.append(self._extract_voltage(uint24_val))
            
            for i in range(self.num_channels):
                self.emg_data_queues[i].append(voltages[i])
            
            # --- 2. Process GPS Data (bytes 48-58) if valid ---
            if packet[48] == 0x59:
                lat_val_raw = struct.unpack('>f', packet[49:53])[0]
                lon_val_raw = struct.unpack('>f', packet[54:58])[0]

                latitude,longitude = self._Parse_GPS(lat_raw =lat_val_raw,lon_raw=lon_val_raw)
                lat_dir = ' '
                lon_dir = ' '

                if packet[53:54] in {b'N', b'S'}:
                    lat_dir = packet[53:54].decode('ascii')

                if packet[58:59] in {b'E', b'W'}:
                    lon_dir = packet[58:59].decode('ascii')
                
                self.gps_data['latitude'].append(str(latitude)+"°"+lat_dir)
                self.gps_data['longitude'].append(str(longitude)+"°"+lon_dir)
            
            # --- 3. Process Gyroscope Data (bytes 59-65) if valid ---
            if packet[59] == 0x59:
                roll_raw = int.from_bytes(packet[60:62], 'little', signed=True)
                pitch_raw = int.from_bytes(packet[62:64], 'little', signed=True)
                yaw_raw = int.from_bytes(packet[64:66], 'little', signed=True)

                roll = roll_raw / 32768.0 * 180.0
                pitch = pitch_raw / 32768.0 * 180.0
                yaw = yaw_raw / 32768.0 * 180.0

                self.gyro_data['roll'].append(roll)
                self.gyro_data['pitch'].append(pitch)
                self.gyro_data['yaw'].append(yaw)

        except Exception as e:
            self.logger.error(f"[TCP_Receiver] Failed to process packet: {e}", exc_info=True)

    def _Parse_GPS(self, lat_raw,lon_raw):
        
        def to_decimal(raw_data):
            degrees = raw_data // 100
            minutes = raw_data % 100
            decimal_degrees = degrees + (minutes / 60.0)
            return decimal_degrees
        lat = to_decimal(lat_raw)
        lon = to_decimal(lon_raw)
        return lat,lon
        
    def _extract_voltage(self, uint24_value: int) -> float:
        """Converts a 24-bit raw value to a voltage value in millivolts (mV)."""
        if uint24_value & (1 << 23):
            raw_value = uint24_value - (1 << 24)
        else:
            raw_value = uint24_value
        return raw_value * self.LSB * 1000

    def _cleanup_connection(self):
        """Safely closes the current socket and resets the status flags."""
        with self._socket_lock:
            if self._client_socket:
                try: self._client_socket.close()
                except Exception: pass
                finally: self._client_socket = None
        with self._state_lock:
            self._is_connected = False
            self._is_receiving = False
        self.logger.info("[TCP_Receiver] Connection resources have been cleaned up.")

    def is_connected(self) -> bool:
        """Checks if the client is currently connected to the server."""
        with self._state_lock:
            return self._is_connected

    def get_data(self) -> List[Deque[float]]:
        """Returns a shallow copy of all channel EMG data queues (for backward compatibility)."""
        return self.get_emg_data()
    
    def get_emg_data(self) -> List[Deque[float]]:
        """Returns a shallow copy of all channel EMG data queues."""
        with self._state_lock:
            return [q.copy() for q in self.emg_data_queues]
    
    def get_gps_data(self) -> Dict[str, Deque[float]]:
        """Returns a shallow copy of the GPS data queues."""
        with self._state_lock:
            return {key: q.copy() for key, q in self.gps_data.items()}

    def get_gyro_data(self) -> Dict[str, Deque[float]]:
        """Returns a shallow copy of the Gyroscope data queues."""
        with self._state_lock:
            return {key: q.copy() for key, q in self.gyro_data.items()}
        