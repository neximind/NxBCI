import struct
import logging
import threading
import time
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from collections import deque
from typing import List, Deque,Dict ,Optional

class MQTT_Receiver:
    """
    A thread-safe class to receive and process data via MQTT.

    This class provides robust functionality to connect to an MQTT broker,
    subscribe to a topic, and process incoming data in a thread-safe manner.
    It manages the connection lifecycle explicitly with start() and stop() methods.

    Example Usage:
        
        # Configure logging in your main script
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

        # Initialize the receiver
        receiver = MQTT_Receiver(Ip="192.168.176.254", port=1883, topic="esp32-pub-message")

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
        if len(payload) != 66:
            self.logger.warning(f"[MQTT_Receiver]  Received message with invalid payload length. "
                              f"Expected {66}, got {len(payload)}.")
            with self._state_lock:
                self._is_receiving = False
            return
        
        with self._state_lock:
            self._is_receiving = True

        try:
            # --- 1. Process first 48 bytes for EMG data ---
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
            # --- 2. Process GPS Data (bytes 48-58) if valid ---
            if payload[48] == 0x59:
                lat_val_raw = struct.unpack('>f', payload[49:53])[0]
                lon_val_raw = struct.unpack('>f', payload[54:58])[0]

                latitude,longitude = self._Parse_GPS(lat_raw =lat_val_raw,lon_raw=lon_val_raw)
                lat_dir = ' '
                lon_dir = ' '

                if payload[53:54] in {b'N', b'S'}:
                    lat_dir = payload[53:54].decode('ascii')

                if payload[58:59] in {b'E', b'W'}:
                    lon_dir = payload[58:59].decode('ascii')
                
                self.gps_data['latitude'].append(str(latitude)+"°"+lat_dir)
                self.gps_data['longitude'].append(str(longitude)+"°"+lon_dir)

            # --- 3. Process Gyroscope Data (bytes 59-65) if valid ---
            if payload[59] == 0x59:
                roll_raw = int.from_bytes(payload[60:62], 'little', signed=True)
                pitch_raw = int.from_bytes(payload[62:64], 'little', signed=True)
                yaw_raw = int.from_bytes(payload[64:66], 'little', signed=True)

                roll = roll_raw / 32768.0 * 180.0
                pitch = pitch_raw / 32768.0 * 180.0
                yaw = yaw_raw / 32768.0 * 180.0

                self.gyro_data['roll'].append(roll)
                self.gyro_data['pitch'].append(pitch)
                self.gyro_data['yaw'].append(yaw)

        except Exception as e:
            self.logger.error(f"[MQTT_Receiver] Error processing message payload: {e}", exc_info=True)

    def _Parse_GPS(self, lat_raw,lon_raw):
        
        def to_decimal(raw_data):
            degrees = raw_data // 100
            minutes = raw_data % 100
            decimal_degrees = degrees + (minutes / 60.0)
            return decimal_degrees
        lat = to_decimal(lat_raw)
        lon = to_decimal(lon_raw)
        return lat,lon
    # --- Public API Methods ---

    def is_connected(self) -> bool:
        """
        Checks if the client is currently connected to the MQTT broker.
        
        Returns:
            bool: True if connected, False otherwise.
        """
        with self._state_lock:
            return self._is_connected

    def pose_GetData(self):
        """
        [Deprecated] Retrieves the latest pose data.
        NOTE: The current 66-byte packet format does not populate this data.
        This method is preserved for API compatibility and will return None.
        """
        self.logger.error(f"[MQTT_Receiver] pose_GetData() is deprecated and not supported in the current packet format.")
        
        return None
    
    def get_data(self) -> List[Deque[float]]:
        """Returns a shallow copy of all channel EMG data queues (for backward compatibility)."""
        return self.get_emg_data()
    
    def get_emg_data(self) -> List[Deque[float]]:
        """Returns a shallow copy of all channel EMG data queues."""
        with self._state_lock:
            return [q.copy() for q in self.data_queues]
    
    def get_gps_data(self) -> Dict[str, Deque[float]]:
        """Returns a shallow copy of the GPS data queues."""
        with self._state_lock:
            return {key: q.copy() for key, q in self.gps_data.items()}

    def get_gyro_data(self) -> Dict[str, Deque[float]]:
        """Returns a shallow copy of the Gyroscope data queues."""
        with self._state_lock:
            return {key: q.copy() for key, q in self.gyro_data.items()}
        
