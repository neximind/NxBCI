from paho.mqtt import client as mqtt_client
from paho.mqtt.enums import CallbackAPIVersion
import logging

logger = logging.getLogger()

class Relay:
    """
    A class to relay data to a cloud MQTT broker.

    This class provides functionality to connect to a cloud MQTT broker, publish data
    to a specified topic, and handle connection events.

    Attributes:
        isConnected (bool): Flag indicating whether the connection to the MQTT broker is active.
        cloud_broker_address (str): IP address or hostname of the cloud MQTT broker.
        cloud_port (int): Port of the cloud MQTT broker.
        cloud_topic (str): MQTT topic to publish data to.
        client_id (str): Client ID for the MQTT connection.
        username (str): Username for MQTT authentication.
        password (str): Password for MQTT authentication.
        client (mqtt_client.Client): MQTT client instance.
    """

    def __init__(self, cloud_broker_address='', cloud_port=1883, cloud_topic='', client_id='', username='', password=''):
        """
        Initialize the Relay object.

        Args:
            cloud_broker_address (str, optional): IP address or hostname of the cloud MQTT broker. Defaults to ''.
            cloud_port (int, optional): Port of the cloud MQTT broker. Defaults to 1883.
            cloud_topic (str, optional): MQTT topic to publish data to. Defaults to ''.
            client_id (str, optional): Client ID for the MQTT connection. Defaults to ''.
            username (str, optional): Username for MQTT authentication. Defaults to ''.
            password (str, optional): Password for MQTT authentication. Defaults to ''.
        """
        self.isConnected = False
        self.cloud_broker_address = cloud_broker_address
        self.cloud_port = cloud_port
        self.cloud_topic = cloud_topic
        self.client_id = client_id
        self.username = username
        self.password = password

        try:
            self.client = mqtt_client.Client(client_id=self.client_id, callback_api_version=CallbackAPIVersion.VERSION1)
            self.client.username_pw_set(self.username, self.password)
            if self.cloud_port == 8883:  # The MQTT 8883 port of the Alibaba Cloud server must support TLS/SSL
                self.client.tls_set(tls_version=mqtt_client.ssl.PROTOCOL_TLS)

            self.client.on_connect = self.on_connect
            self.client.connect(self.cloud_broker_address, self.cloud_port)
            self.client.loop_start()
        except ConnectionRefusedError as e:
            logger.error(f"[Relay] The connection to the EMQX cloud server was refused:{e}")
        except Exception as e:
            logger.error(f"[Relay] An error occurred during the initialization:{e}")
        finally:
            logger.info("[Relay] The relay function to EMQX ECS has been successfully initialized")

    def on_connect(self, client, userdata, flags, rc):
        """
        Callback function for handling MQTT connection events.

        Args:
            client (mqtt_client.Client): The MQTT client instance.
            userdata: User-defined data passed to the callback.
            flags: Connection flags.
            rc (int): Connection result code.
        """
        if rc == 0:
            logger.info("[Relay] Connected to MQTT Broker!")
            self.isConnected = True
        else:
            logger.error(f"[Relay] Failed to connect, return code:{rc}")
            self.isConnected = False

    def relay_data(self, data):
        """
        Relay data to the cloud MQTT broker.

        Args:
            data (str or bytes): Data to be published to the MQTT topic.

        Raises:
            Exception: If the data fails to be published.
        """
        result = self.client.publish(self.cloud_topic, str(data))
        status = result[0]

        if status == 0:
            pass
        else:
            logger.error(f"Failed to send message to topic {self.cloud_topic}")
