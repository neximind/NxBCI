import asyncio
from bleak import BleakScanner, BleakClient
from typing import Optional, Callable, List, Tuple, Union, Dict
import json
import logging

logger = logging.getLogger()

class BluetoothController:

    """
    A Bluetooth Low Energy (BLE) controller for managing device connections and data exchange.
    
    Attributes:
        SERVICE_UUID: Base service UUID for the BLE device
        JSON_FILE_UUID: Characteristic UUID for JSON configuration data
        TF_CARD_UUID: Characteristic UUID for TF card storage information
        BATTERY_LEVEL_UUID: Characteristic UUID for battery level readings
        
    The controller handles device scanning, connection management, characteristic reading/writing,
    and notification handling for BLE devices.

    Example Usages:

        controller = BluetoothController(device_name="BLE_FOR_EEG")

        async def main():
            try:
                await controller.initialize()
                print("JSON File:", controller.json_data)
                print("Battery Power:", controller.battery_power)
                print("TF Card Storage:", controller.tf_card_storage)
                print("WiFi Name:", controller.wifi_name)
                print("Battery Power (float):", controller.battery_power_float)
                print("TF Card Storage (float):", controller.tf_card_storage_float)
                print("mqtt_uri:", controller.mqtt_uri)
                print("mqtt_port:", controller.mqtt_port)
                print("Gain:", controller.gain)
                print("DB:", controller.DB)
            except Exception as e:
                logger.error(f"Error during initialization: {e}")
            finally:
                await controller.close()

        if __name__ == "__main__":
            asyncio.run(main())
    """
     
    SERVICE_UUID = "1826"
    JSON_FILE_UUID = "FFF2"
    TF_CARD_UUID = "FFF1"
    BATTERY_LEVEL_UUID = "2A19"

    def __init__(self, device_name: str = "BLE_FOR_EEG"):
        """
        Initialize Bluetooth controller with device-specific parameters.
        
        Parameters:
            device_name: Name of the target BLE device to connect to
            
        Initializes connection parameters, device state tracking, and data storage fields
        for handling BLE communications.
        """

        # Device identification and connection management
        self.device_name = device_name
        self.device_address: str = ""
        self.client: Optional[BleakClient] = None

        # Callbacks for characteristic notifications
        self.notification_callbacks: Dict[str, Callable] = {}

        # Raw data storage from BLE characteristics
        self.json_data: bytes = b""
        self.battery_power: bytes = b""
        self.tf_card_storage: bytes = b""
        self.wifi_name: str = ""
        self.wifi_pwd: str = ""
        self.work_mode: str = ""
        self.gain:str = ""
        self.DB:str = ""
        self.mqtt_uri:str = ""
        self.mqtt_port:str = ""

        # Parsed device configuration parameters
        self.battery_power_float: float = 0.0
        self.tf_card_storage_float: float = 0.0
        self.updateJson = True

        # Connection retry parameters
        self.retry_count = 3  # Maximum retry attempts
        self.reconnect_delay = 5  # Seconds between retry attempts

        self.fullChargeVoltage = 4200.0#mv
        self.cutoffVoltage = 3000.0
    async def initialize(self) -> None:
        """
        Initialize BLE device connection with scanning and setup.
        """
        
        try:
            logger.info("[Bluetooth] Initializing Bluetooth Controller")

            count = 0
            while self.retry_count > count:

                logger.info(f"[Bluetooth] Start trying the {count+1} scan bluetooth Device.")
                devices = await self.scan_devices()

                if not devices:
                    count = count+1
                else:
                    break

            if not devices:
                logger.error(f"[Bluetooth] No device named '{self.device_name}' found.")
                return
            
            self.device_address = devices[0][1]

            if not await self.connect_device():
                logger.error("[Bluetooth] Failed to connect to the bluetooth.")
                return

            await self.update_data()

            logger.info("[Bluetooth] Initialization completed.")

        except Exception as e:
            logger.error(f"[Bluetooth] Initialization failed: {e}")

        self.updateJson = True

    async def scan_devices(self) -> List[Tuple[str, str]]:
       
        """
        Scan for available BLE devices matching the configured name.
        
        Returns:
            List of tuples containing (device_name, device_address) pairs
        """

        logger.info("[Bluetooth] Scanning for BLE devices...")
        devices = await BleakScanner.discover()
        matched_devices = [(d.name, d.address) for d in devices if d.name == self.device_name]
        
        if not matched_devices:

            logger.warning(f"[Bluetooth] No device named '{self.device_name}' found.")

        else:

            logger.info(f"[Bluetooth] Found {len(matched_devices)} devices matching '{self.device_name}':")

            for name, addr in matched_devices:
                logger.info(f"{name} ({addr})")
        
        return matched_devices

    async def connect_device(self) -> bool:
        """
        Establish connection to the identified BLE device.
        
        Returns:
            bool: True if connection successful, False otherwise
        """

        if not self.device_address:
            raise ValueError("[Bluetooth] Device address not set. Call scan_devices() first.")

        self.client = BleakClient(self.device_address)
        
        try:
            await self.client.connect()

            if self.client.is_connected:

                logger.info(f"[Bluetooth] Connected to {self.device_name} at {self.device_address}")
                return True
            
            else:

                logger.error("[Bluetooth] Failed to connect to the device.")
                return False
            
        except Exception as e:

            logger.error(f"[Bluetooth] Connection failed: {e}")
            return False

    async def update_data(self) -> None:

        """
        Update device state by reading latest values from all characteristics.
        """
        if not self.getState() or not self:
            return
        
        try:
           
            results = await asyncio.gather(
                self.read_characteristic(self.JSON_FILE_UUID),
                self.read_characteristic(self.BATTERY_LEVEL_UUID),
                self.read_characteristic(self.TF_CARD_UUID)
            )
            
            self.json_data, self.battery_power, self.tf_card_storage = results
            
            self.battery_power_float = int.from_bytes(self.battery_power, byteorder='little')
            self.tf_card_storage_float = int.from_bytes(self.tf_card_storage, byteorder='little')
            
            
            if self.updateJson == False:
                return
                
            json_str = self.json_data.decode('utf-8').rstrip('\x00')
            print(json_str)
            try:
                json_dict = json.loads(json_str)
                self.wifi_name = json_dict.get("wifi_id", "")
                self.wifi_pwd = json_dict.get("wifi_pwd", "")
                self.work_mode = json_dict.get("WM", "")
                self.gain = json_dict.get("Gain","")
                self.DB = json_dict.get("DB","")
                self.mqtt_uri = json_dict.get("mqtt_uri","")
                self.mqtt_port = json_dict.get("mqtt_port","")

                if self.mqtt_port != "":
                    self.updateJson = False

                logger.info("[Bluetooth] Received data from the device")

            except json.JSONDecodeError as e:
                logger.warning(f"[Bluetooth] Failed to parse JSON data: {e}")
            
        except Exception as e:
            logger.error(f"[Bluetooth] Failed to update data: {e}")
            raise
        
    async def read_characteristic(self, uuid: str) -> bytes:
        """
        Read value from a specified GATT characteristic.
        
        Parameters:
            uuid: Characteristic UUID to read from
            
        Returns:
            bytes: Raw characteristic value as bytes
        """
        if not self.client or not self.client.is_connected:

            logger.error("[Bluetooth] Not connected to a device.")

            return

        try:

            value = await self.client.read_gatt_char(uuid)
            logger.debug(f"[Bluetooth] Read from {uuid}: {value}")

            return value
        
        except Exception as e:

            logger.error(f"[Bluetooth] Failed to read from {uuid}: {e}")
            raise

    async def write_characteristic(self, uuid: str, data: bytes) -> None:
        """
        Write data to a specified GATT characteristic.
        
        Parameters:
            uuid: Characteristic UUID to write to
            data: Bytes data to write
        """
        if not self.client or not self.client.is_connected:
            logger.error("[Bluetooth] Not connected to a device.")
        try:
    
            await self.client.write_gatt_char(uuid, data,response=True)
            logger.info(f"[Bluetooth] Wrote to {uuid}: {data}")
        except Exception as e:
            logger.error(f"[Bluetooth] Failed to write to {uuid}: {e}")
            return

    def clear(self):

        """
        Reset all device configuration parameters to default values.
        """

        self.wifi_name: str = ""
        self.wifi_pwd: str = ""
        self.work_mode: str = ""
        self.gain:str = ""
        self.DB:str = ""
        self.mqtt_uri:str = ""
        self.mqtt_port:str = ""
        self.battery_power_float = 0
        self.tf_card_storage_float = 0
       

    async def writeData(self,data):

        """
        Write JSON configuration data to the device.
        
        Parameters:
            data: Dictionary containing configuration parameters
        """
        
        bytes_data = json.dumps(data).encode('utf-8')
        self.clear()
        self.updateJson = False

        try:
            logger.info("[Bluetooth] Prepareing to write information to Device")
            await self.write_characteristic(self.JSON_FILE_UUID,bytes_data)
            logger.info("[Bluetooth] Data written successfully")
            self.close()

        except Exception as e:

            logger.error(f"[Bluetooth] Error in writing data to device: {e}")
        self.updateJson = True   

    async def start_notification(self, uuid: str, callback: Callable[[int, bytes], None]) -> None:

        """
        Start receiving notifications from a characteristic.
        
        Parameters:
            uuid: Characteristic UUID to subscribe to
            callback: Function to handle incoming notifications
        """

        if not self.client or not self.client.is_connected:

            logger.error("[Bluetooth] Not connected to a device.")

            return

        try:

            self.notification_callbacks[uuid] = callback
            await self.client.start_notify(uuid, self._notification_handler)
            logger.info(f"[Bluetooth] Started notification on {uuid}")

        except Exception as e:

            logger.error(f"[Bluetooth] Failed to start notification on {uuid}: {e}")
            

    async def stop_notification(self, uuid: str) -> None:
        
        """
        Stop receiving notifications from a characteristic.
        
        Parameters:
            uuid: Characteristic UUID to unsubscribe from
        """

        if not self.client or not self.client.is_connected:

            logger.error("[Bluetooth] Not connected to a device.")

            return

        try:

            await self.client.stop_notify(uuid)
            logger.info(f"[Bluetooth] Stopped notification on {uuid}")

        except Exception as e:
            logger.error(f"[Bluetooth] Failed to stop notification on {uuid}: {e}")
    

    async def close(self) -> None:
       
        """
        Disconnect from the BLE device and clean up resources.
        """
        if self.client and self.client.is_connected:

            try:

                await self.client.disconnect()
                logger.info("[Bluetooth] Disconnected from device.")

            except Exception as e:

                logger.warning(f"[Bluetooth] Error during disconnection: {e}")

        self.client = None

    def _notification_handler(self, sender: int, data: bytes) -> None:
       
        """
        Internal handler for incoming characteristic notifications.
        
        Parameters:
            sender: Integer handle of the characteristic sending the notification
            data: Raw data bytes from the notification
        """
       
        if uuid := self._get_uuid_from_sender(sender):

            if callback := self.notification_callbacks.get(uuid):

                try:

                    callback(sender, data)

                except Exception as e:

                    logger.error(f"[Bluetooth] Error in notification callback: {e}")

    def _get_uuid_from_sender(self, sender: int) -> Optional[str]:
        return None
    
    def getState(self):
        """
        Check current connection status.
        
        Returns:
            bool: True if connected, False otherwise
        """
        state = True if self.client and self.client.is_connected else False

        return state
    
    

    def __del__(self):
       
        """
        Class destructor that ensures proper resource cleanup.
        """
        if self.client and self.client.is_connected:

            try:
                loop = asyncio.get_event_loop()

                if loop.is_running():

                    loop.create_task(self.close())

                else:

                    loop.run_until_complete(self.close())

            except Exception as e:

                logger.warning(f"[Bluetooth] Error during cleanup: {e}")

    async def bt_SetBluetoothTarget(self,target):
            """
            Set a new BLE device to connect.

            Parameters:
                target: the new BLE device name
            """
            logger.info(f"[Bluetooth] Set a new BLE Device:{target}")
            if self.device_name == target:
                return
            
            self.close()
            self.clear()
            self.device_name = target

            await self.initialize()

    async def bt_ReconnectBluetooth(self):
            """
            Reconnect to the BLE device.
            """

            if self.getState():
                logger.warning(f"[Bluetooth] The BLE device:{self.device_name} has been connected.")
                return

            try:
                logger.info(f"[Bluetooth] Trying to reconnect to BLE device:{self.device_name}")

                count = 0
                while self.retry_count > count:

                    logger.info(f"[Bluetooth] Start trying the {count+1} scan bluetooth Device.")
                    devices = await self.scan_devices()

                    if not devices:
                        count = count+1
                    else:
                        logger.info("[Bluetooth] The reconnecting of the BLE device was succe")
                        break

                if not devices:
                    logger.error(f"[Bluetooth] No device named '{self.device_name}' found.")
                    return
                
                self.device_address = devices[0][1]

                if not await self.connect_device():
                    logger.error("[Bluetooth] Failed to connect to the bluetooth.")
                    return
            except Exception as e:
                logger.error(f"[Bluetooth] A error occurred during the reconnection of the BLE device:{e}")
                

    def bt_GetConnectionStatus(self):
        """
        Get the BLE device connection status.
        
        Returns:
            bool: True if connected, False otherwise
        """
        return self.getState()

    def bt_GetDeviceName(self):
        """
        Get the current BLE device Name.
        
        Returns:
            str: The current BLE device Name.
        """
        return self.device_name

    def bt_GetDeviceAddress(self):
        """
        Get the current BLE device Mac address.
        
        Returns:
            str: The current BLE device Mac address.
        """
        return self.device_address

    def bt_GetBatteryLevel(self):
        """
        Get the current BLE device battery level .
        
        Returns:
            int: Battery percentage (0-100).
        """
        power = (self.fullChargeVoltage - self.battery_power_float)/(self.fullChargeVoltage-self.cutoffVoltage)

        power = 1.0 if power > 1.0 else power
        power = 0.0 if 0.0 > power else power
        
        return int(power*100.0) 

    async def bt_SetGain(self,gain):
        """
        Get the current BLE device battery level .
        
        Parameters:
                gain: the gain of the device(only 100 or 1000).
        """

        
        if gain == 100 or gain == 1000:
            gain_tag = 's' if gain == 100 else 'b'
        else:
            logger.error(f"The gain multiplier can only be 100 or 1000,your gain:{gain}")
            return
        
        new_data = {"wifi_id": self.wifi_name,
                        "wifi_pwd":self.wifi_pwd,
                        "WM":self.work_mode,
                        "Gain":gain_tag,
                        "DB":"l", # Deprecated
                        "mqtt_uri":self.mqtt_uri,
                        "mqtt_port":str(self.mqtt_port)}
        
        await self.writeData(data= new_data)

    def bt_GetGain(self):
        
        """
        Get the gain of the current device  .
        
        Returns:
            int: Battery percentage (0 is an error,100 or 1000).
        """
        gain = 0

        if self.gain == 's' or self.gain == 'b':
            gain = 100 if self.gain=='s' else 1000
        else:
            logger.error(f"[Bluetooth] Confirm that the BLE device is connected and wait for the device to return the gain configuration")
        
        return gain

    async def bt_SetTFcardStorageMode(self):
        """
        Set the workmode of the current device to TF card storage mode.
        """
        if self.getState():
            self.work_mode = "TF"

            new_data = {"wifi_id": self.wifi_name,
                        "wifi_pwd":self.wifi_pwd,
                        "WM":self.work_mode,
                        "Gain":self.gain,
                        "DB":"l", # Deprecated
                        "mqtt_uri":self.mqtt_uri,
                        "mqtt_port":str(self.mqtt_port)}
            
            await self.writeData(data= new_data)

        else:
            logger.error("[Bluetooth] The BLE device is not connected")

    async def bt_SetTCPMode(self,wifi_name,password):
        """
        Set the workmode of the current device to TCP transport mode.

        Parameters:
                wifi_name: the WIFI name of the device.
                password: the password of the device's WIFI.
        """
        if self.getState():
            self.work_mode = "TCP"
            self.wifi_name = wifi_name
            self.wifi_pwd = password
            new_data = {"wifi_id": self.wifi_name,
                        "wifi_pwd":self.wifi_pwd,
                        "WM":self.work_mode,
                        "Gain":self.gain,
                        "DB":"l", # Deprecated
                        "mqtt_uri":self.mqtt_uri,
                        "mqtt_port":str(self.mqtt_port)}
            
            await self.writeData(data= new_data)

        else:
            logger.error("[Bluetooth] The BLE device is not connected")
    
    async def bt_SetMQTTMode(self,MQTT_URI,port):
        """
        Set the workmode of the current device to MQTT transport mode.

        Parameters:
                wifi_name: the address of MQTT broker .
                password: the port of MQTT broker .
        """
        if self.getState():
            self.work_mode = "MQTT"
            self.mqtt_uri = MQTT_URI
            self.mqtt_port = port
            new_data = {"wifi_id": self.wifi_name,
                        "wifi_pwd":self.wifi_pwd,
                        "WM":self.work_mode,
                        "Gain":self.gain,
                        "DB":"l", # Deprecated
                        "mqtt_uri":self.mqtt_uri,
                        "mqtt_port":str(self.mqtt_port)}
            
            await self.writeData(data= new_data)

        else:
            logger.error("[Bluetooth] The BLE device is not connected")

"""
# just for test
controller = BluetoothController(device_name="BLE_FOR_EEG")

async def main():
    try:
        await controller.initialize()
        print("JSON File:", controller.json_data)
        print("Battery Power:", controller.battery_power)
        print("TF Card Storage:", controller.tf_card_storage)
        print("WiFi Name:", controller.wifi_name)
        print("Battery Power (float):", controller.battery_power_float)
        print("TF Card Storage (float):", controller.tf_card_storage_float)
        print("mqtt_uri:", controller.mqtt_uri)
        print("mqtt_port:", controller.mqtt_port)
        print("Gain:", controller.gain)
        print("DB:", controller.DB)

        await controller.bt_ReconnectBluetooth()
    except Exception as e:
        logger.error(f"Error during initialization: {e}")
    finally:
        await controller.close()

if __name__ == "__main__":
    asyncio.run(main())
"""
