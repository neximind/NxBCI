import socket
import struct
import threading
import time
import logging
from collections import deque
from typing import List, Optional, Deque

class TCP_Receiver:
    """
    A thread-safe TCP receiver for continuously acquiring data streams from a device.

    This class utilizes a single worker thread model to automatically handle
    connection, data reception, and auto-reconnection upon disconnection.
    All public methods are designed to be thread-safe.

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
                    # Safely get a copy of the data queues
                    latest_data_queues = receiver.get_data()
                    if latest_data_queues and latest_data_queues[0]:
                        # Access the latest value from the first channel's queue
                        print(f"Connection is ON. Channel 0 latest value: {list(latest_data_queues[0])[-1]}")
                    else:
                        print("Connection is ON, but no data has been received yet.")
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
    PACKET_SIZE = 48  # Expected size of each TCP packet in bytes
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
        self.data_queues: List[Deque[float]] = [deque(maxlen=sample_rate * duration) for _ in range(channels)]
        
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

        The worker thread handles connection, data reception, and reconnection.
        This method is thread-safe and idempotent (calling it multiple times
        has no harmful effect).
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
        Stops the background worker thread and cleans up resources (e.g., closes the socket).
        This method is thread-safe.
        """
        self.logger.info("[TCP_Receiver] Stopping receiver service...")
        self._stop_event.set()
        
        # Closing the socket will interrupt a blocking recv() call in the worker thread
        with self._socket_lock:
            if self._client_socket:
                self._client_socket.close()
        
        if self._worker_thread and self._worker_thread.is_alive():
            # Wait for the thread to finish gracefully
            self._worker_thread.join(timeout=2.0)
            if self._worker_thread.is_alive():
                self.logger.warning("[TCP_Receiver] Worker thread did not terminate in time.")
        
        self.logger.info("[TCP_Receiver] Receiver service stopped.")

    def _worker_loop(self):
        """
        The main loop for the single worker thread.

        It manages a lifecycle of connecting, receiving data, and then
        cleaning up and reconnecting on disconnection.
        """
        while not self._stop_event.is_set():
            try:
                # --- Phase 1: Connect ---
                self.logger.info(f"[TCP_Receiver] Attempting to connect to {self.server_address}...")
                with self._socket_lock:
                    # Create a new socket for each connection attempt
                    self._client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self._client_socket.settimeout(5.0)  # Set a timeout for the connect operation
                    self._client_socket.connect(self.server_address)
                
                # Update connection status thread-safely
                with self._state_lock:
                    self._is_connected = True
                self.logger.info("[TCP_Receiver] Connection established successfully.")

                # --- Phase 2: Receive Data ---
                self._receive_data_loop()

            except (socket.timeout, socket.error) as e:
                self.logger.error(f"[TCP_Receiver] A connection or communication error occurred: {e}. Will retry...")
            except Exception as e:
                self.logger.error(f"[TCP_Receiver] An unexpected error occurred in the worker loop: {e}", exc_info=True)
            finally:
                # --- Phase 3: Cleanup ---
                # Ensure connection resources are cleaned up regardless of what happened
                self._cleanup_connection()
            
            # --- Phase 4: Wait before Reconnecting ---
            if not self._stop_event.is_set():
                self.logger.info(f"[TCP_Receiver] Waiting {self.RECONNECT_DELAY} seconds before reconnecting.")
                # wait() is used instead of time.sleep() so it can be interrupted by the stop_event
                self._stop_event.wait(self.RECONNECT_DELAY)
        
        self.logger.info("[TCP_Receiver] Worker loop has terminated.")
    
    def _receive_data_loop(self):
        """
        Continuously receives and processes data on an established connection.
        This loop will exit if the connection is lost.
        """
        buffer = b''
        while not self._stop_event.is_set():
            try:
                # The recv() call is blocking, so it must be outside the lock
                with self._socket_lock:
                    if not self._client_socket:
                        break  # Socket was closed by another thread (e.g., stop())
                    
                    # Read only the bytes needed to complete the next packet
                    read_size = self.PACKET_SIZE - len(buffer)
                    data = self._client_socket.recv(read_size)

                if not data:
                    # An empty byte string from recv() means the peer has closed the connection gracefully
                    self.logger.warning("[TCP_Receiver] Connection closed by the peer.")
                    break  # Exit the receive loop to trigger reconnection logic

                buffer += data

                if len(buffer) >= self.PACKET_SIZE:
                    # Process one full packet and keep the rest of the buffer
                    packet = buffer[:self.PACKET_SIZE]
                    buffer = buffer[self.PACKET_SIZE:]
                    self._process_packet(packet)
                    with self._state_lock:
                        self._is_receiving = True

            except socket.timeout:
                 self.logger.warning("[TCP_Receiver] Socket recv() timed out. No data received in the timeout period.")
                 continue # Continue waiting for data
            except socket.error as e:
                # Any other socket error (e.g., connection reset) indicates a broken connection
                self.logger.error(f"[TCP_Receiver] Socket error during data reception: {e}")
                break # Exit the receive loop to trigger reconnection

    def _process_packet(self, packet: bytes):
        """Parses a 64-byte packet into 16 channel voltage values and appends them to the queues."""
        try:
            voltages = []
            for i in range(self.num_channels):
                offset = i * 3
                # Unpack 3 bytes into a 24-bit unsigned integer (big-endian)
                bytes_24 = packet[offset:offset+3]
                uint24_val = int.from_bytes(bytes_24, 'big', signed=False)
                voltages.append(self._extract_voltage(uint24_val))
            
            for i in range(self.num_channels):
                self.data_queues[i].append(voltages[i])
        except Exception as e:
            self.logger.error(f"[TCP_Receiver] Failed to process packet: {e}")

    def _extract_voltage(self, uint24_value: int) -> float:
        """Converts a 24-bit raw value to a voltage value in millivolts (mV)."""
        if uint24_value & (1 << 23):  # Check if the sign bit (24th bit) is set
            raw_value = uint24_value - (1 << 24)
        else:
            raw_value = uint24_value
        
        return raw_value * self.LSB * 1000  # Convert to millivolts

    def _cleanup_connection(self):
        """Safely closes the current socket and resets the status flags."""
        with self._socket_lock:
            if self._client_socket:
                try:
                    self._client_socket.close()
                except Exception as e:
                    self.logger.warning(f"[TCP_Receiver] An error occurred while closing the socket: {e}")
                finally:
                    self._client_socket = None
        
        with self._state_lock:
            self._is_connected = False
            self._is_receiving = False
        self.logger.info("[TCP_Receiver] Connection resources have been cleaned up.")

    def is_connected(self) -> bool:
        """
        Checks if the client is currently connected to the server.
        
        Returns:
            bool: True if connected, False otherwise.
        """
        with self._state_lock:
            return self._is_connected

    def get_data(self) -> List[Deque[float]]:
        """
        Returns a shallow copy of all channel data queues.

        Returning a copy prevents potential issues if the queues are modified
        by the background thread while iterating over them.
        
        Returns:
            list[deque]: A list where each element is a deque containing
                         the data for one channel.
        """
        return [q.copy() for q in self.data_queues]
    