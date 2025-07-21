import struct
import logging
import threading
import time
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from collections import deque
from typing import List, Deque, Optional

class MQTT_Receiver:
    """
    A thread-safe class to receive and process data via MQTT.

    This class provides robust functionality to connect to an MQTT broker,
    subscribe to a topic, and process incoming data in a thread-safe manner.
    It manages the connection lifecycle explicitly with start() and stop() methods.

    Example Usage:
        
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

        # Initialize the receiver (does not connect yet)
        receiver = MQTT_Receiver(Ip="127.0.0.1", port=1883, topic="esp32-pub-message")
        
        # Start the connection and background network loop
        receiver.start()

        try:
            while True:
                time.sleep(2)
                if receiver.is_connected():
                    # Safely get a copy of the data
                    data = receiver.get_data()
                    if data and data[0]:
                        print(f"MQTT Connected. Last value on Ch0: {list(data[0])[-1]}")
                    else:
                        print("MQTT Connected, but no data received yet.")
                else:
                    print("MQTT Disconnected. Paho-MQTT will attempt to reconnect automatically.")

        except KeyboardInterrupt:
            print("Program interrupted.")
        finally:
            print("Stopping MQTT receiver...")
            receiver.stop()
            print("Receiver stopped.")
    """

    # Voltage conversion constants
    LSB = 1.5 / (2 ** 23)
    ACCE_LSB = 4 / (2**15)
    GYPO_LSB = 1000 / (2**15)

    def __init__(self, channels: int = 16, sample_rate: int = 500, duration: int = 4, Ip: str = "127.0.0.1", port: int = 1883, topic: str = "esp32-pub-message"):
        """
        Initializes the MQTT_Receiver object.

        This method only sets up the configuration and does not initiate any network connections.
        Call the start() method to connect and begin receiving data.
        
        Args:
            channels (int): Number of data channels.
            sample_rate (int): Sampling rate of the data in Hz.
            duration (int): Duration of data to store in seconds.
            Ip (str): IP address of the MQTT broker.
            port (int): Port of the MQTT broker.
            topic (str): MQTT topic to subscribe to.
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Data storage and configuration
        self.data_queues: List[Deque[float]] = [deque(maxlen=sample_rate * duration) for _ in range(channels)]
        self.num_channels = channels
        self.mpu_data_queues: List[Deque[float]] = [deque(maxlen=100) for _ in range(7)]
        
        # MQTT configuration
        self._broker_address = Ip
        self._broker_port = port
        self._topic = topic
        
        # Thread safety locks
        self._state_lock = threading.Lock()

        # Thread-safe state flags
        self._is_connected = False
        self._is_receiving = False

        # Configure the MQTT client
        try:
            # Using VERSION1 as specified in original code. If you switch to paho-mqtt v2.x,
            # you might need to update callback signatures.
            self.client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION1)
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.on_message = self._on_message

            self.logger.info("[MQTT_Receiver] MQTT client configured successfully. Call start() to connect.")
            
        except Exception as e:
            self.logger.error(f"[MQTT_Receiver] Failed to initialize MQTT client: {e}", exc_info=True)
            # Re-raise or handle more gracefully if initialization failure is critical
            raise

    def start(self):
        """
        Connects to the MQTT broker and starts the background network loop.
        This method is safe to call even if the client is already started.
        """
        if self.is_connected():
            self.logger.warning("[MQTT_Receiver] start() called but client is already connected.")
            return

        try:
            self.logger.info(f"[MQTT_Receiver] Connecting to MQTT broker at {self._broker_address}:{self._broker_port}...")
            # connect() is non-blocking and will initiate the connection in the background.
            self.client.connect(self._broker_address, self._broker_port, 60)
            
            # loop_start() starts a new thread to process network traffic, dispatch callbacks,
            # and handle reconnecting automatically.
            self.client.loop_start()
            self.logger.info("[MQTT_Receiver] MQTT network loop started. Waiting for connection...")

        except (ConnectionRefusedError, OSError) as e:
            self.logger.error(f"[MQTT_Receiver] Failed to initiate connection to MQTT Broker: {e}")
        except Exception as e:
            self.logger.error(f"[MQTT_Receiver] An unexpected error occurred during start(): {e}", exc_info=True)

    def stop(self):
        """
        Stops the network loop and disconnects gracefully from the MQTT broker.
        """
        self.logger.info("[MQTT_Receiver]  Stopping MQTT client...")
        
        # Stops the background thread.
        self.client.loop_stop()
        
        # Politely disconnect from the broker.
        self.client.disconnect()
        self.logger.info("[MQTT_Receiver]  MQTT client has been stopped.")

    def _on_connect(self, client: mqtt.Client, userdata, flags: dict, rc: int):
        """Callback for when the client connects to the broker."""
        if rc == 0:
            self.logger.info(f"[MQTT_Receiver]  Successfully connected to MQTT Broker. Subscribing to topic: '{self._topic}'")
            with self._state_lock:
                self._is_connected = True
            try:
                client.subscribe(self._topic)
            except Exception as e:
                self.logger.error(f"[MQTT_Receiver]  Failed to subscribe to topic '{self._topic}': {e}")
        else:
            self.logger.error(f"[MQTT_Receiver]  Failed to connect to MQTT Broker, return code {rc}\n"
                              "Common codes: 1 (protocol), 2 (client ID), 3 (server unavailable), "
                              "4 (bad user/pass), 5 (not authorized)")
            with self._state_lock:
                self._is_connected = False

    def _on_disconnect(self, client: mqtt.Client, userdata, rc: int):
        """Callback for when the client disconnects from the broker."""
        self.logger.warning(f"[MQTT_Receiver]  Disconnected from MQTT Broker with result code: {rc}. "
                            "Paho-MQTT will attempt to reconnect automatically.")
        with self._state_lock:
            self._is_connected = False
            self._is_receiving = False

    def _on_message(self, client: mqtt.Client, userdata, msg: mqtt.MQTTMessage):
        """Callback for when a message is received from the broker."""
        if msg.topic != self._topic:
            return

        payload = msg.payload
        if len(payload) != 48 and len(payload) != 62:
            self.logger.warning(f"[MQTT_Receiver]  Received message with invalid payload length. "
                              f"Expected {48} or {62}, got {len(payload)}.")
            with self._state_lock:
                self._is_receiving = False
            return
        
        with self._state_lock:
            self._is_receiving = True

        try:
            voltages = []
            for i in range(self.num_channels):
                offset = i * 3
                bytes_24 = payload[offset:offset+3]
                raw_value = int.from_bytes(bytes_24, 'big', signed=True)
                voltage = raw_value * self.LSB * 1000
                voltages.append(voltage)

            # deque.append is atomic, so it's safe to call from the callback thread.
            for i in range(self.num_channels):
                self.data_queues[i].append(voltages[i])

            if len(payload) == 62:
                mpu_bytes = struct.unpack(">7h",payload[48:62])
                mpu6500data = [
                    mpu_bytes[0]*self.ACCE_LSB,
                    mpu_bytes[1]*self.ACCE_LSB,
                    mpu_bytes[2]*self.ACCE_LSB,
                    (mpu_bytes[3] / 333.87) + 21,
                    mpu_bytes[4]*self.GYPO_LSB,
                    mpu_bytes[5]*self.GYPO_LSB,
                    mpu_bytes[6]*self.GYPO_LSB
                ]
                
                for i in range(7):
                    self.mpu_data_queues[i].append(mpu6500data[i])
                    

        except Exception as e:
            self.logger.error(f"[MQTT_Receiver] Error processing message payload: {e}", exc_info=True)

    # --- Public API Methods ---

    def is_connected(self) -> bool:
        """
        Checks if the client is currently connected to the MQTT broker.
        
        Returns:
            bool: True if connected, False otherwise.
        """
        with self._state_lock:
            return self._is_connected

    def get_data(self) -> List[Deque[float]]:
        """
        Returns a shallow copy of all channel data queues.

        Returning a copy prevents potential race conditions if the main thread
        iterates over the queues while the network thread is modifying them.
        
        Returns:
            list[deque]: A list where each element is a deque containing
                         the data for one channel.
        """
        # deque.copy() is an atomic and thread-safe operation.
        return [q.copy() for q in self.data_queues]
    
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
        if not self.is_connected():
            self.logger.error("[MQTT_Receiver] The playback thread is not running")
            return None


        if not self.mpu_data_queues or not self.mpu_data_queues[0]:
            self.logger.error("[MQTT_Receiver] The MPU buffer is empty.")
            return None
        
        return [q.copy() for q in self.mpu_data_queues]