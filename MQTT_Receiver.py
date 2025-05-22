import struct
import logging
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from collections import deque
from Receiver_base import Receiver

logger = logging.getLogger()

class MQTT_Receiver(Receiver):

    """
    A class to receive and process EEG data via MQTT.

    This class extends the `Receiver` base class and provides functionality to connect
    to an MQTT broker, subscribe to a topic, and process incoming EEG data.

    Attributes:
        data_queues (list): List of deques to store EEG data for each channel.
        num_channels (int): Number of EEG channels.
        duration (int): Duration of data to store in seconds.
        sample_rate (int): Sampling rate of the EEG data.
        V_REF (float): Reference voltage for voltage conversion.
        VCC (float): Supply voltage for voltage conversion.
        LSB (float): Least significant bit value for voltage conversion.
        MQTT_BROKER (str): IP address of the MQTT broker.
        MQTT_PORT (int): Port of the MQTT broker.
        MQTT_TOPIC (str): MQTT topic to subscribe to.
        isReceiving (bool): Flag indicating whether data is being received.
        client (mqtt.Client): MQTT client instance.
    """

    def __init__(self,channels = 16,sample_rate =500,duration = 4,Ip = "192.168.4.2",port = 1883,topic = "esp32-pub-message" ):
        """
        Initialize the MQTT_Receiver object.

        Args:
            channels (int, optional): Number of EEG channels. Defaults to 16.
            sample_rate (int, optional): Sampling rate of the EEG data. Defaults to 500.
            duration (int, optional): Duration of data to store in seconds. Defaults to 4.
            Ip (str, optional): IP address of the MQTT broker. Defaults to "192.168.4.2".
            port (int, optional): Port of the MQTT broker. Defaults to 1883.
            topic (str, optional): MQTT topic to subscribe to. Defaults to "esp32-pub-message".
        """

        self.data_queues = [deque(maxlen=sample_rate*duration) for _ in range(channels)]
        self.num_channels = channels
        self.duration = duration
        self.sample_rate = sample_rate

        self.V_REF = 2.5  
        self.VCC = 5.0
        self.LSB = 1.5 / (2 ** 23)

        self.MQTT_BROKER = Ip
        self.MQTT_PORT = port
        self.MQTT_TOPIC = topic
        self.isReceiving = False
        self.isRelay = False
        
        try:
            self.client = mqtt.Client(
            client_id="my_client",
            callback_api_version=CallbackAPIVersion.VERSION1  # 强制使用旧版API，新版的会崩
            )
            self.client.on_connect = self.on_connect
            self.client.on_message = self.on_message
            self.client.connect(self.MQTT_BROKER, self.MQTT_PORT, 60)
            self.client.subscribe(self.MQTT_TOPIC)

            self.client.loop_start()
            
        except ConnectionRefusedError as e:
            logger.error(f"[MQTT_Receiver] The connection was refused by the MQTT Broker:{e}")

        except Exception as e:
            logger.error(f"[MQTT_Receiver] An unknown error occurred during the initialization of the local MQTT connection{e} ")

        finally:
            logger.info("[MQTT_Receiver] The local MQTT service is initialized successfully")
        

    def get_data(self):

        """
        Get the current EEG data.

        Returns:
            list: List of deques containing EEG data for each channel.
        """

        return self.data_queues

    def setRelay(self,relay):
        """
        Relay current data to the cloud EMQX server.
        """
        self.relay = relay
        self.isRelay = True
   
    def on_message(self,client, userdata, msg):

        """
        Callback function for handling incoming MQTT messages.

        Args:
            client (mqtt.Client): The MQTT client instance.
            userdata: User-defined data passed to the callback.
            msg (mqtt.MQTTMessage): The received MQTT message.
        """

        msg_payload = msg.payload
        
        if len(msg_payload) == 64:
            self.isReceiving = True
            buffer = msg_payload[:64]
            uint24_values = []
            for i in range(16):

                offset = i*3
                bytes_24 = buffer[offset:offset+3]
                padded_bytes = b'\x00' + bytes_24
                uint32_values, = struct.unpack('>I',padded_bytes)
                uint24_values.append(uint32_values)
        else:
            self.isReceiving = False
            logger.error(f"[MQTT_Receiver] Received invalid payload length:{len(msg_payload)}")

        def extract_voltage(uint32_value):
            
            raw_value = uint32_value

            if raw_value & (1 << 23):
                raw_value -= (1 << 24)
               
            voltage = raw_value * self.LSB * 1000
            return voltage
        
        
        voltages = [extract_voltage(val) for val in uint24_values]

        if self.isRelay:
            self.relay.relay_data(voltages)
                        
        for i in range(self.num_channels):
            self.data_queues[i].append(voltages[i])

    def on_connect(self,client, userdata, flags, rc):
        """
        Callback function for handling MQTT connection events.

        Args:
            client (mqtt.Client): The MQTT client instance.
            userdata: User-defined data passed to the callback.
            flags: Connection flags.
            rc (int): Connection result code.
        """
        logger.info(f"[MQTT_Receiver] Connected with result code:{rc}")
        
        
    
    def stop(self):
        """
        Stop the MQTT client from receiving messages.
        """
        self.client.loop_stop()  
        logger.info(f"[MQTT_Receiver] MQTT client stopped receiving messages.")

    def eeg_Get_data(self):
        """
        Return the latest duration seconds of n-channel raw EEG data
        """
        return self.data_queues
    
    def eeg_Stop(self):
        """
        Stop the MQTT client from receiving messages.
        """
        self.stop()

    def pose_Config(self,Sample_rate):
        """
        Set the sampling rate for pose and temperature
        Parameters:
            Sample_rate (float): The sampling rate for pose and temperature
        """

        pass
    
    def pose_GetData(self):
        """
        Retrieves the latest pose and temperature information
        Returns:
            A "Tuple" containing:
            - T  : Temperature in degrees Celsius.
            - X_a  : Acceleration along the x-axis.
            - Y_a  : Acceleration along the y-axis.
            - Z_a  : Acceleration along the z-axis.
            - ω_x  : Angular velocity along the x-axis.
            - ω_y  : Angular velocity along the y-axis.
            - ω_z  : Angular velocity along the z-axis.
        """
        pass

