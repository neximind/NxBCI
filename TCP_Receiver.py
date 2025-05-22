import socket
import struct
import numpy as np
from collections import deque
from Receiver_base import Receiver
import time
import threading
import logging

logger = logging.getLogger()


class TCP_Receiver(Receiver):

    """
    A TCP receiver class for handling voltage data acquisition from the EEG/EMG acquisition device.
    
    Attributes:
        channels (int): Number of data channels to handle simultaneously
        sample_rate (int): Sampling frequency in Hz
        duration (int): Duration in seconds for data storage in queues
        Ip (str): IP address of the EEG/EMG acquisition device.
        port (int): Port number of the EEG/EMG acquisition device.
    
    Example Usage:

        tcp_receiver = TCP_Receiver()

        while not tcp_receiver.isConnected:
            tcp_receiver.connect()

        tcp_receiver.start()

        tcp_receiver.pose_Config(50)

        while True:
            time.sleep(1)
            data = tcp_receiver.get_data()
            print(data)
        
    """
    
    def __init__(self, channels=16, sample_rate=500, duration=4, Ip="192.168.4.1", port=8080):

        """
        Initialize TCP receiver with configurable parameters and system constants.
        
        Parameters:
            channels (int): Number of data channels to handle simultaneously
            sample_rate (int): Sampling frequency in Hz
            duration (int): Duration in seconds for data storage in queues
            Ip (str): IP address of the EEG/EMG acquisition device.
            port (int): Port number of the EEG/EMG acquisition device.
        """
        
        # Initialize data queues with calculated maximum lengths
        self.data_queues = [deque(maxlen=sample_rate * duration) for _ in range(channels)]
        self.num_channels = channels
        self.duration = duration
        self.sample_rate = sample_rate

        # Voltage reference constants
        self.V_REF = 2.5  # 参考电压
        self.VCC = 5.0
        self.LSB = 1.5 / (2 ** 23)  # 分辨率
        self.ACCE_LSB = 4 / (2 ** 15)#加速度数据分辨率
        self.GYPO_LSB = 1000 / (2 ** 15)#角速度数据分辨率
        self.mpu_data_queues = [deque(maxlen=sample_rate * duration) for _ in range(7)]
        self.mpu_sample_rate = 500
        self.pose_data_queues = [deque(maxlen=self.mpu_sample_rate * duration) for _ in range(7)]

        # Connection parameters
        self.address = Ip
        self.port = port

        # Thread control and socket initialization
        self.stop_event = threading.Event()
        self.client_socket = None
        self.receive_thread = None
        self.tcp_thread = threading.Thread(target=self.tcp_prepare)
        self.tcp_stop_event = threading.Event()
        self.tcp_thread.start()

        # Create TCP socket and configure server address
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_address = (self.address, self.port)
        self.isConnected = False
        self.isReceiving = False
        self.isRelay = False


    def tcp_prepare(self):

        while not self.tcp_stop_event.is_set():
            
            self.connect()

            if self.isConnected:
                self.tcp_stop_event.set()
            else:
                time.sleep(3)
        
        self.start()
        self.tcp_stop_event.clear()

        while not self.tcp_stop_event.is_set():
            time.sleep(5)

            if self.isReceiving or self.isConnected:
                continue

            if self.receive_thread.is_alive():
                continue
            
            self.restart()



    def connect(self):
        """
        Establish connection to the configured EEG/EMG acquisition device.
        """
        logger.info(f"[TCP_Receiver] Start connect to IP:{self.address}:{self.port}")
        self.stop_event.clear()
        self.isConnected = False
        try:
            if not self.is_connected():
                self.client_socket.connect((self.address, self.port))
            self.isConnected = True
            logger.info(f"[TCP_Receiver] The connection to the IP:{self.address} was established.")

        except ConnectionRefusedError:

            logger.error(f"[TCP_Receiver] The connection to the IP:{self.address} was refused:{ConnectionRefusedError}")

        except Exception as e:

            logger.error(f"[TCP_Receiver] An unknown error occurred during the establishing of the TCP connection:{e}")


    def is_connected(self):

        try:
            self.client_socket.getpeername()
            self.isConnected = True
            return True
        
        except Exception as e:

            logger.info(f"[TCP_Receiver] Connect state:{e}")
            return False
    
    def start(self):
        """
        Start data reception thread if connection is established.
        """
        if self.isConnected:

            self.receive_thread = threading.Thread(target=self.receive_data)
            self.receive_thread.start()

        else:

            logger.error(f"[TCP_Receiver] The TCP connection was not established")

    def extract_voltage(self, uint24_value):

        """
        Convert 24-bit raw value to voltage measurement.
        
        Parameters:
            uint24_value (int): 24-bit unsigned integer value from sensor
            
        Returns:
            float: Calculated voltage value in millivolts
        """

        raw_value = uint24_value

        if raw_value & (1 << 23):
            raw_value -= (1 << 24)

        voltage = raw_value * self.LSB * 1000

        return voltage
    
    def receive_data(self):
        """
        Continuously receive and process TCP data packets.
        """
         
        while not self.stop_event.is_set():
            buffer = b''

            while len(buffer) < 64:
                data = self.client_socket.recv(64 - len(buffer))
                if not data:
                    logger.error("[TCP_Receiver] client socket timeout because not receivied data")
                    self.stop_event.set()
                    self.isReceiving = False
                    break
                buffer += data

            try:
                
                if len(buffer) == 64:

                    uint24_values = []
                    for i in range(16):

                        offset = i*3
                        bytes_24 = buffer[offset:offset+3]
                        padded_bytes = b'\x00' + bytes_24
                        uint32_values, = struct.unpack('>I',padded_bytes)
                        uint24_values.append(uint32_values)

                        #检查分隔符
                    separator = struct.unpack(">H", buffer[48:50])[0]
                    if separator == 0xFFFF:
                        #解析后14字节
                        uint16_values = struct.unpack(">7H", buffer[50:64])
                    elif separator == 0x0000:
                        uint16_values = []
                    else:
                        logger.error(f"[TCP_Receiver] Invalid separator:{separator:#06x}")

                    voltages = [self.extract_voltage(val) for val in uint24_values]
                    
                    if self.isRelay:
                        self.relay.relay_data(voltages)

                    for i in range(16):
                        self.data_queues[i].append(voltages[i])
                    
                    if separator == 0xFFFF:
                        def mpu6500_convert_data(uint16_value):
                            if uint16_value & (1 << 15):
                                uint16_value -= (1 << 16)
                            return uint16_value

                        converted_values = [mpu6500_convert_data(mpudata) for mpudata in uint16_values]
                
                        mpu6500data = [
                        converted_values[0] * (self.ACCE_LSB),
                        converted_values[1] * (self.ACCE_LSB),
                        converted_values[2] * (self.ACCE_LSB),
                        (converted_values[3] / 333.87 ) + 21,
                        converted_values[4] * (self.GYPO_LSB),
                        converted_values[5] * (self.GYPO_LSB),
                        converted_values[6] * (self.GYPO_LSB)
                        ]
                        #存储mpu6500数据到队列
                        for i in range(7):
                            self.mpu_data_queues[i].append(mpu6500data[i])

                    self.isReceiving = True


                else :
                    logger.error(f"[TCP_Receiver] Received invalid TCP data length: {len(buffer)}")
                    self.stop_event.set()
                    self.isReceiving = False


            except BlockingIOError:
                # 无数据可读，继续循环
                continue
            except Exception as e:

                logger.error(f"[TCP_Receiver] Error in receive_data: {e}")
                self.isReceiving = False
                self.stop_event.set()

        
        if self.client_socket:
            self.client_socket.close()
            self.isConnected = False
            logger.info("[TCP_Receiver] client socket was closed")


    def stop(self):
        """
        Stop data reception and clean up resources.
        """

        super().stop()
        self.stop_event.set()
        self.tcp_stop_event.set()

        if self.receive_thread and self.receive_thread.is_alive():
            self.receive_thread.join(timeout=1)

    def restart(self):
        """
        Restart the TCP connection and data reception.
        """
        logger.info("[TCP_Receiver] try to restart the TCP service")
        self.client_socket.close()

        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        while not self.tcp_stop_event.is_set():
            
            self.connect()
            
            if self.isConnected:
                self.tcp_stop_event.set()
            else:
                time.sleep(3)
        self.isConnected = True
        self.tcp_stop_event.clear()
        self.start()
       
    def setRelay(self,relay):
        """
        Relay current data to the cloud EMQX server.
        """
        self.relay = relay
        self.isRelay = True

    def get_data(self):
        """
        Retrieve current data queues with collected measurements.
        
        Returns:
            list: List of deques containing voltage data per channel
        """

        return self.data_queues
    
    def eeg_Get_data(self):
        """
        Retrieve current data queues with collected measurements.
        
        Returns:
            list: List of deques containing voltage data per channel
        """
        return self.data_queues
    
    def eeg_Stop(self):
        """
        Shut down the TCP receiver.
        """
        self.stop()
        self.close()

    def pose_Config(self,Sample_rate):
        """
        Set the sampling rate for pose and temperature
        Parameters:
            Sample_rate (float): The sampling rate for pose and temperature
        """
    
        if self.sample_rate // Sample_rate != self.sample_rate / Sample_rate:
            logger.error(f"Please enter a sample rate that is divisible by {self.sample_rate}")
            return
        
        if self.mpu_sample_rate != Sample_rate:
            self.mpu_sample_rate = Sample_rate
            self.pose_data_queues = [deque(maxlen=self.mpu_sample_rate * self.duration) for _ in range(7)]
    
    def pose_GetData(self):
        """
        Retrieves the latest pose and temperature information
        Returns:
            A "deque" containing:
            - T  : Temperature in degrees Celsius.
            - X_a  : Acceleration along the x-axis.
            - Y_a  : Acceleration along the y-axis.
            - Z_a  : Acceleration along the z-axis.
            - ω_x  : Angular velocity along the x-axis.
            - ω_y  : Angular velocity along the y-axis.
            - ω_z  : Angular velocity along the z-axis.
        """
        if not self.isConnected:
            logger.error("[TCP_Receiver] The TCP connection is not established")

        sampleNum = self.mpu_sample_rate * self.duration
        n = int(self.sample_rate /self.mpu_sample_rate)

        if sampleNum > len(self.mpu_data_queues[0]):
            logger.error("[TCP_Receiver] The MPU buffer is not filled")
            return
        
        X_a_List = list(self.mpu_data_queues[0])
        Y_a_List = list(self.mpu_data_queues[1])
        Z_a_List = list(self.mpu_data_queues[2])
        T_List   = list(self.mpu_data_queues[3])
        ω_x_List = list(self.mpu_data_queues[4])
        ω_y_List = list(self.mpu_data_queues[5])
        ω_z_List = list(self.mpu_data_queues[6])

        for i in range(self.mpu_sample_rate*self.duration):
            index = n*i
            X_a = np.mean(X_a_List[index:index+n])
            Y_a = np.mean(Y_a_List[index:index+n])
            Z_a = np.mean(Z_a_List[index:index+n])
            T = np.mean(T_List[index:index+n])
            ω_x = np.mean(ω_x_List[index:index+n])
            ω_y = np.mean(ω_y_List[index:index+n])
            ω_z = np.mean(ω_z_List[index:index+n])
            self.pose_data_queues[0].append(X_a)
            self.pose_data_queues[1].append(Y_a)
            self.pose_data_queues[2].append(Z_a)
            self.pose_data_queues[3].append(T)
            self.pose_data_queues[4].append(ω_x)
            self.pose_data_queues[4].append(ω_y)
            self.pose_data_queues[4].append(ω_z)

        return self.pose_data_queues


    def close(self):
        """
        Close TCP socket connection safely.
        """
        self.tcp_stop_event.set()
        if self.client_socket:

            self.client_socket.close()
            self.client_socket = None

    def __del__(self):
        self.close()

"""
# just for test
import time
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s : %(message)s',
    handlers={
        logging.StreamHandler()
    }
)
tcp_receiver = TCP_Receiver()
while True:
    time.sleep(1)
    data = tcp_receiver.get_data()
    print(data[0])
"""