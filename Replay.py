import mmap
import struct
import os
import logging
import threading
import time
from Receiver_base import Receiver
from collections import deque

logger = logging.getLogger()

class Replay(Receiver):
    """
    A class to replay and process raw data from a file.

    This class extends the `Receiver` base class and provides functionality to read,
    parse, and manipulate raw data stored in a file. It supports operations such as
    reading data, extracting voltage values, and seeking specific segments of the data.

    Attributes:
        channel (int): Number of data channels.
        sample_rate (int): Sampling rate of the data.
        duration (int): Duration of the data in seconds.
        filePath (str): Path to the file containing raw data.
        chunkSize (int): Size of data chunks to read at a time.
        bufferSize (int): Size of the buffer for parsing data.
        V_REF (float): Reference voltage for voltage conversion.
        VCC (float): Supply voltage for voltage conversion.
        LSB (float): Least significant bit value for voltage conversion.
        rawData (list): List of lists containing raw data for each channel.
        length (int): Length of the raw data.
        file (file object): File object for reading the data file.
        mmapped_file (mmap object): Memory-mapped file object for efficient data access.
        all_datas (list): List of lists containing all parsed data for each channel.
    
    Examples:
        file_path = 'EEGDATA.BIN'
        replay = Replay(FilePath=file_path)
        print(replay.tf_getDataLength())
    """

    def __init__(self, channels=16, sample_rate=500, duration=4, FilePath=""):
        """
        Initialize the Replay object.

        Args:
            channels (int, optional): Number of data channels. Defaults to 16.
            sample_rate (int, optional): Sampling rate of the data. Defaults to 500.
            duration (int, optional): Duration of the data in seconds. Defaults to 4.
            FilePath (str, optional): Path to the file containing raw data. Defaults to "".
        """
        super().__init__(channels, sample_rate, duration)
        self.channel = channels
        self.sample_rate = sample_rate
        self.duration = duration
        self.filePath = FilePath
        self.chunkSize = 1024 * 1024
        self.bufferSize = 64
        self.V_REF = 2.5  # Reference voltage
        self.VCC = 5.0
        self.LSB = 1.5 / (2 ** 23)  # Resolution
        self.rawData = []
        self.length = 0
        self.readRawData(self.filePath)

    def __del__(self):
        """
        Clean up resources when the object is deleted.

        Closes the file and memory-mapped file objects.
        """
        self.file.close()
        self.mmapped_file.close()
        return super().__del__()

    def readRawData(self, FilePath):
        """
        Read raw data from the specified file.

        Args:
            FilePath (str): Path to the file containing raw data.

        Raises:
            FileNotFoundError: If the file does not exist.
            IOError: If the file cannot be opened or mapped.
        """
        self.filePath = FilePath

        if not os.path.exists(self.filePath):  # Check if the path exists
            logger.error(f"[Replay] The file path:{self.filePath} does not exist.")
            return

        if not os.path.isfile(self.filePath):  # Check if the path is a file
            logger.error(f"[Replay] The file:{self.filePath} does not exist")
            return

        logger.info(f"[Replay] Start parsing the file:{self.filePath}")
        try:
            self.file = open(self.filePath, 'r+b')
            self.mmapped_file = mmap.mmap(self.file.fileno(), 0, access=mmap.ACCESS_READ)
            self.all_datas = [[] for _ in range(self.channel)]
            self.thread = threading.Thread(target=self.readData)
            self.thread.start()
        except Exception as e:
            logger.error(f"[Replay] Unable to map file:{e}")
            return

    def readData(self):
        """
        Read and parse data from the memory-mapped file.

        This method processes the file in chunks and extracts data for each channel.
        """
        if not self.mmapped_file:
            self.readRawData(self.filePath)

        offset = 0
        while offset < len(self.mmapped_file):
            end_offset = min(offset + self.chunkSize, len(self.mmapped_file))
            chunk = self.mmapped_file[offset:end_offset]

            start = 0
            while start + self.bufferSize <= len(chunk):
                buffer = chunk[start:start + self.bufferSize]
                data = self.parseMessage(buffer=buffer)

                if len(data) == 16:
                    for i in range(16):
                        self.all_datas[i].append(data[i])

                start = start + self.bufferSize
            offset = end_offset
        self.length = len(self.all_datas[0])
        self.rawData = self.all_datas

    def extract_voltage(self, uint24_value):
        """
        Convert a 24-bit raw value to a voltage measurement.

        Args:
            uint24_value (int): 24-bit unsigned integer value from the sensor.

        Returns:
            float: Calculated voltage value in millivolts.
        """
        raw_value = uint24_value

        if raw_value & (1 << 23):
            raw_value -= (1 << 24)

        voltage = raw_value * self.LSB * 1000

        return voltage

    def parseMessage(self, buffer):
        """
        Parse a buffer of raw data into voltage values.

        Args:
            buffer (bytes): Buffer containing raw data.

        Returns:
            list: List of voltage values for each channel.
        """
        if len(buffer) == 64:
            uint24_values = []
            for i in range(16):
                offset = i * 3
                bytes_24 = buffer[offset:offset + 3]
                padded_bytes = b'\x00' + bytes_24
                uint32_values, = struct.unpack('>I', padded_bytes)
                uint24_values.append(uint32_values)

            voltages = [self.extract_voltage(val) for val in uint24_values]
            return voltages
        else:
            logger.error(f"[Replay] Invalid data length: {len(buffer)}")
            return []

    def tf_ReadRawData(self, file_path):
        """
        Read raw data from a new file and replace the current data.

        Args:
            file_path (str): Path to the new file containing raw data.
        """
        if self.filePath != file_path:
            self.filePath = file_path
            logger.info("[Replay] The previous data will be cleared and new data will be read.")
            self.readRawData(self.filePath)

        logger.info(f"[Replay] The file:{file_path} was read in memory")

    def wait_for_loading(self):
        logger.info("[Replay] waiting for loading data from file,please be patient")
        while self.thread.is_alive():
            time.sleep(1)

    def tf_GetRawData(self):
        """
        Get the current raw data.

        Returns:
            list: List of lists containing raw data for each channel.
        """
        self.wait_for_loading()
        return self.rawData

    def tf_Seek(self, file_path, pos):
        """
        Seek to a specific position in the data.

        Args:
            file_path (str): Path to the file containing raw data.
            pos (int): Position to seek to.

        Raises:
            ValueError: If the position is invalid.
        """
        if self.filePath != file_path:
            self.filePath = file_path
            self.readRawData()

        self.wait_for_loading()
        if pos < 0 or pos > self.length:
            logger.error(f"[Replay] The location you entered is invalid:{pos}")
            return

        for i in range(self.channel):
            self.rawData[i] = self.all_datas[i][pos:]

    def tf_SeekSpecifiedSegment(self, start_index, end_index):
        """
        Seek to a specified segment of the data.

        Args:
            start_index (int): Start index of the segment.
            end_index (int): End index of the segment.

        Raises:
            ValueError: If the indices are invalid.
        """
        self.wait_for_loading()

        if not self.rawData:
            logger.error(f"[Replay] Please load a playback file first")
            return

        if start_index < 0 or end_index > self.length:
            logger.error(f"[Replay] The start index, or the end index, you entered is invalid")
            return

        for i in range(self.channel):
            self.rawData[i] = self.all_datas[i][start_index:end_index]

    def tf_PlayBack(self, file_path):
        """
        Start playback of the data from the specified file.

        Args:
            file_path (str): Path to the file containing raw data.
        """
        self.wait_for_loading()
        if self.filePath == file_path:
            self.rawData = self.all_datas
        else:
            self.filePath = file_path
            self.readRawData(self.filePath)

    def tf_Stop(self):
        """
        Stop playback of the data.
        """
        pass

    def tf_getChannelsState(self):
        """
        Get the state of the channels.

        Returns:
            list: List of channel states.
        """
        pass

    def tf_getDataLength(self):
        """
        Get the length of the current raw data.

        Returns:
            int: Length of the raw data.
        """
        self.wait_for_loading()
        if not self.rawData:
            logger.error("[Replay] Please load a playback file first")
            return 0
        return len(self.rawData[0])

