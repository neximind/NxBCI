import serial
import threading
import time
from typing import List, Callable, Optional, Deque
from collections import deque
import logging
import numpy as np


class Serial_Receiver:
    """
    Thread-safe serial port receiver for continuous EMG data acquisition.

    This class serves as a hybrid driver:
    1. Legacy Mode: Supports `get_emg_data()` returning deque snapshots.
    2. Sync Mode: Supports `pop_new_data()` returning Numpy arrays for MultiSourceController.

    Protocol Constants:
        FRAME_HEAD = 0x0A
        FRAME_TAIL = 0x0D
        FRAME_SIZE = 48 (16 channels * 3 bytes)
    """

    # Protocol constants
    FRAME_HEAD = 0x0A
    FRAME_TAIL = 0x0D
    ESCAPE_BYTE = 0x1B
    ESCAPE_HEAD = 0x01
    ESCAPE_TAIL = 0x02
    ESCAPE_ESC = 0x03

    # Data configuration
    FRAME_SIZE = 48  
    LSB = 1.5 / (2 ** 23)
    READ_BLOCK_SIZE = 4096 

    def __init__(self, port: Optional[str] = None, baudrate: int = 4000000):
        """
        Initialize the Serial Receiver.

        Args:
            port: Serial port identifier (e.g., 'COM3').
            baudrate: Communication speed. Default is 4000000.
        """
        self.port = port
        self.baudrate = baudrate
        self.logger = logging.getLogger(f"Rx_{port if port else 'Unk'}")

        self.serial_port: Optional[serial.Serial] = None
        self.is_running = False
        self.read_thread: Optional[threading.Thread] = None

        # Internal Buffers
        self.buffer = bytearray()
        self.buffer_lock = threading.Lock()
        
        # Data Storage
        # maxlen is set to prevent memory overflow in Legacy Mode
        self.channel_queues: List[Deque[float]] = [deque(maxlen=4000) for _ in range(16)]
        
        # Legacy error callback support
        self.error_callback: Optional[Callable[[str], None]] = None

    def open(self) -> bool:
        """
        Open the serial port and start the acquisition thread.

        Returns:
            True if successful, False otherwise.
        """
        if not self.port:
            self.logger.error("Port name not set.")
            return False
            
        try:
            if self.serial_port and self.serial_port.is_open:
                self.close()
            
            self.serial_port = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.1, 
                xonxoff=False,
                rtscts=False,
                dsrdtr=False
            )
            self.serial_port.set_buffer_size(rx_size=65536, tx_size=65536)
            self.reset_internal_buffers()
            
            self.is_running = True
            self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self.read_thread.start()
            
            self.logger.info(f"Port {self.port} opened successfully.")
            return True
        except Exception as e:
            msg = f"Failed to open port {self.port}: {str(e)}"
            self.logger.error(msg)
            if self.error_callback: self.error_callback(msg)
            return False

    def close(self):
        """
        Close the serial port and stop the acquisition thread.
        """
        self.is_running = False
        if self.read_thread and self.read_thread.is_alive():
            self.read_thread.join(timeout=1.0)
        
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
        
        self.logger.info("Port closed.")

    def is_open(self) -> bool:
        """
        Check if the receiver is currently connected.
        """
        return self.serial_port is not None and self.serial_port.is_open

    def reset_internal_buffers(self):
        """
        Clear all internal byte buffers and data queues.
        """
        with self.buffer_lock:
            self.buffer.clear()
            if self.serial_port:
                self.serial_port.reset_input_buffer()
            for q in self.channel_queues:
                q.clear()

    # --------------------------------------------------------------------------
    #   Single Serial Mode
    # --------------------------------------------------------------------------
    def get_emg_data(self) -> List[Deque[float]]:
        """
        Get a snapshot of the current data buffers (Non-destructive).

        Returns:
            A list of 16 deques containing voltage samples.
        
        Note:
            This method is intended for the legacy single-port implementation.
            It returns a copy of the data without clearing the buffer.
        """
        with self.buffer_lock:
            return [q.copy() for q in self.channel_queues]

    # --------------------------------------------------------------------------
    #   Multi-Source Controller
    # --------------------------------------------------------------------------
    def pop_new_data(self) -> Optional[np.ndarray]:
        """
        Retrieve and clear all accumulated data (Destructive).

        Returns:
            np.ndarray: A (16, N) array containing new samples since last call.
            None: If no data is available.
            
        Note:
            This method is intended for MultiSourceController to prevent data duplication.
        """
        with self.buffer_lock:
            if not self.channel_queues[0]:
                return None
            
            data_batch = np.array([list(q) for q in self.channel_queues])
            
            for q in self.channel_queues:
                q.clear()
            
            return data_batch

    def _read_loop(self):
        local_buffer = bytearray()
        while self.is_running and self.serial_port:
            try:
                data = self.serial_port.read(self.READ_BLOCK_SIZE)
                if data:
                    local_buffer.extend(data)
                    if len(local_buffer) >= 1024:
                        with self.buffer_lock:
                            self.buffer.extend(local_buffer)
                            local_buffer.clear()
                            self._process_buffer()
                else:
                    time.sleep(0.001)
            except Exception as e:
                self.logger.error(f"Read loop exception: {str(e)}")
                break

    def _process_buffer(self):
        while len(self.buffer) >= self.FRAME_SIZE + 2:
            try:
                head_idx = self.buffer.index(self.FRAME_HEAD)
            except ValueError:
                self.buffer.clear()
                return

            if head_idx > 0:
                del self.buffer[:head_idx]

            try:
                tail_idx = self.buffer.index(self.FRAME_TAIL, 1)
            except ValueError:
                if len(self.buffer) > self.FRAME_SIZE * 2:
                     del self.buffer[0]
                return

            raw_payload = bytes(self.buffer[1:tail_idx])
            del self.buffer[:tail_idx + 1]

            unescaped = self._unescape_data(raw_payload)

            if len(unescaped) == self.FRAME_SIZE:
                self._parse_valid_frame(unescaped)
            else:
                self._append_dummy_frame()

    def _unescape_data(self, data: bytes) -> bytearray:
        res = bytearray()
        i = 0
        length = len(data)
        while i < length:
            if data[i] == self.ESCAPE_BYTE:
                if i + 1 < length:
                    nxt = data[i+1]
                    if nxt == self.ESCAPE_HEAD: res.append(self.FRAME_HEAD)
                    elif nxt == self.ESCAPE_TAIL: res.append(self.FRAME_TAIL)
                    elif nxt == self.ESCAPE_ESC: res.append(self.ESCAPE_BYTE)
                    else: res.append(self.ESCAPE_BYTE)
                    i += 2
                else:
                    i += 1
            else:
                res.append(data[i])
                i += 1
        return res

    def _parse_valid_frame(self, data: bytearray):
        arr = np.frombuffer(data, dtype=np.uint8).reshape(16, 3)
        u24 = (arr[:, 0].astype(np.int32) << 16) | (arr[:, 1].astype(np.int32) << 8) | arr[:, 2].astype(np.int32)
        
        mask = u24 >= 0x800000
        u24[mask] -= 0x1000000
        
        volts = u24 * self.LSB * 1000.0
        
        for i in range(16):
            self.channel_queues[i].append(volts[i])

    def _append_dummy_frame(self):
        for i in range(16):
            self.channel_queues[i].append(0.0)