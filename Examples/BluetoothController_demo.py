import sys
import os
import asyncio

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from NxBCI.BluetoothController import BluetoothController
import logging
logging.basicConfig(level=logging.INFO,format='%(levelname)s : %(message)s',handlers=[logging.StreamHandler()])


controller = BluetoothController(device_name="BLE_FOR_EEG")

async def main():
    try:
        async with controller: # 自动调用 initialize 和 close
            if not controller.getState():
                print("Failed to initialize controller.")
                return
        
            while controller.getState():
               
                print("JSON File:", controller.json_data)
                print("Battery Power:", controller.battery_power)
                print("TF Card Storage:", controller.tf_card_remain_storage)
                print("WiFi Name:", controller.wifi_name)
                print("Battery Power (float):", controller.battery_power_float)
                print("TF Card Storage (float):", controller.tf_card_remain_storage_float)
                print("mqtt_uri:", controller.mqtt_uri)
                print("mqtt_port:", controller.mqtt_port)
                print("Gain:", controller.gain)
               
                pose_data = controller.pose_GetData() # Pose data will not be received until the TCP connection is established.
                if pose_data is not None:
                    print(f"accelerometer:({pose_data[0][99]},{pose_data[1][99]},{pose_data[2][99]})")
                    print(f"thermometer:{pose_data[3][99]}")
                    print(f"gyroscope:({pose_data[4][99]},{pose_data[5][99]},{pose_data[6][99]})")
                await asyncio.sleep(1)
            
    except Exception as e:
        print(f"Error during initialization: {e}")
    finally:
        await controller.close()

if __name__ == "__main__":
    asyncio.run(main())