"""Publishes UPS status to MQTT using Home Assistant's MQTT discovery format.

When MQTT_HOST is set, entities show up in Home Assistant automatically -
no YAML configuration needed. When it's unset, this is a no-op and the
Flask JSON endpoint (/monitor) is the only way to get data out.

Doesn't poll on its own - register publish() as a sink on poller.Poller so
there's exactly one thread talking to the serial port.
"""
import json
import logging
import os
import threading
import time

import paho.mqtt.client as mqtt

from reader import PowerViewError, read_model

logger = logging.getLogger("sms_powerview.mqtt")

MQTT_HOST = os.environ.get("MQTT_HOST", "")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_USERNAME = os.environ.get("MQTT_USERNAME", "")
MQTT_PASSWORD = os.environ.get("MQTT_PASSWORD", "")
MQTT_DISCOVERY_PREFIX = os.environ.get("MQTT_DISCOVERY_PREFIX", "homeassistant")
MQTT_BASE_TOPIC = os.environ.get("MQTT_BASE_TOPIC", "sms_powerview")
DEVICE_NAME = os.environ.get("DEVICE_NAME", "SMS Nobreak")
DEVICE_ID = os.environ.get("DEVICE_ID", "sms_powerview_ups")

STATUS_SENSORS = {
    "input_voltage": {"name": "Input Voltage", "unit": "V", "device_class": "voltage"},
    "output_voltage": {"name": "Output Voltage", "unit": "V", "device_class": "voltage"},
    "output_frequency": {"name": "Output Frequency", "unit": "Hz", "device_class": "frequency"},
    "battery_charge": {"name": "Battery Charge", "unit": "%", "device_class": "battery"},
    "temperature": {"name": "Temperature", "unit": "°C", "device_class": "temperature"},
    "output_power": {"name": "Output Power", "unit": "W", "device_class": "power"},
}

# battery_in_use and self_test_active are confirmed against real hardware
# tests (a software test command and a real AC unplug/replug - see
# reader.py's comment on _parse_medidores_estado). The rest are still
# untested best-effort guesses; device_class choices are conservative
# accordingly.
BINARY_INFO_SENSORS = {
    "battery_in_use": {"name": "Running On Battery", "device_class": None},  # confirmed
    "battery_connected": {"name": "Battery Connected", "device_class": None},
    "battery_low": {"name": "Battery Low", "device_class": "battery"},
    "self_test_active": {"name": "Self-test Active", "device_class": None},  # confirmed
    "ups_ok": {"name": "UPS OK", "device_class": None},
    "status_bit_5": {"name": "Status Bit 5 (unknown)", "device_class": None},
    "shutdown_active": {"name": "Shutdown Active", "device_class": "problem"},
}


class MqttPublisher:
    def __init__(self):
        self.enabled = bool(MQTT_HOST)
        self._client = None
        self._discovered = False
        self._connected = False
        self._lock = threading.Lock()
        self._last_published = {}  # topic -> {"value": ..., "at": epoch}
        self._device_info = {
            "identifiers": [DEVICE_ID],
            "name": DEVICE_NAME,
            "manufacturer": "SMS",
        }

    def start(self):
        if not self.enabled:
            logger.info("MQTT_HOST not set, MQTT publishing disabled")
            return

        try:
            self._device_info["model"] = read_model()
        except PowerViewError as exc:
            logger.warning("could not read nobreak model/firmware string: %s", exc)

        self._client = mqtt.Client(client_id=f"{DEVICE_ID}-publisher")
        if MQTT_USERNAME:
            self._client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        self._client.will_set(f"{MQTT_BASE_TOPIC}/availability", "offline", retain=True)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)
        self._client.loop_start()

    def stop(self):
        if self._client:
            self._client.publish(f"{MQTT_BASE_TOPIC}/availability", "offline", retain=True)
            self._client.loop_stop()
            self._client.disconnect()

    def _on_connect(self, client, userdata, flags, rc):
        self._connected = rc == 0
        if self._connected:
            logger.info("connected to MQTT broker %s:%s", MQTT_HOST, MQTT_PORT)
        else:
            logger.warning("MQTT connect failed, rc=%s", rc)

    def _on_disconnect(self, client, userdata, rc):
        self._connected = False

    def publish(self, data: dict) -> None:
        """Sink callback for poller.Poller - publishes one reading."""
        if not self.enabled or not self._client:
            return
        if not self._discovered:
            self._publish_discovery()
            self._discovered = True
        self._publish_state(data)

    def status(self) -> dict:
        """Read-only snapshot for the UI's integration page."""
        with self._lock:
            last_published = dict(self._last_published)
        return {
            "enabled": self.enabled,
            "connected": self._connected if self.enabled else None,
            "host": MQTT_HOST or None,
            "port": MQTT_PORT,
            "discovery_prefix": MQTT_DISCOVERY_PREFIX,
            "base_topic": MQTT_BASE_TOPIC,
            "device_id": DEVICE_ID,
            "device_name": DEVICE_NAME,
            "last_published": last_published,
        }

    def _publish_discovery(self):
        for key, meta in STATUS_SENSORS.items():
            self._publish_sensor_config("sensor", key, meta, f"status/{key}")
        for key, meta in BINARY_INFO_SENSORS.items():
            self._publish_sensor_config("binary_sensor", key, meta, f"info/{key}", binary=True)

    def _publish_sensor_config(self, component, key, meta, state_suffix, binary=False):
        object_id = f"{DEVICE_ID}_{key}"
        config_topic = f"{MQTT_DISCOVERY_PREFIX}/{component}/{DEVICE_ID}/{key}/config"
        state_topic = f"{MQTT_BASE_TOPIC}/{state_suffix}"

        payload = {
            "name": meta["name"],
            "unique_id": object_id,
            "state_topic": state_topic,
            "device": self._device_info,
            "availability_topic": f"{MQTT_BASE_TOPIC}/availability",
        }
        if meta.get("unit"):
            payload["unit_of_measurement"] = meta["unit"]
        if meta.get("device_class"):
            payload["device_class"] = meta["device_class"]
        if binary:
            payload["payload_on"] = "On"
            payload["payload_off"] = "Off"

        self._client.publish(config_topic, json.dumps(payload), retain=True)

    def _record(self, topic: str, value) -> None:
        with self._lock:
            self._last_published[topic] = {"value": value, "at": time.time()}

    def _publish_state(self, data):
        status = data.get("status", {})
        info = data.get("info", {})

        for key in STATUS_SENSORS:
            if key in status:
                topic = f"{MQTT_BASE_TOPIC}/status/{key}"
                value = status[key]["current"]
                self._client.publish(topic, value, retain=True)
                self._record(topic, value)

        for key in BINARY_INFO_SENSORS:
            if key in info:
                topic = f"{MQTT_BASE_TOPIC}/info/{key}"
                value = info[key]
                self._client.publish(topic, value, retain=True)
                self._record(topic, value)

        avail_topic = f"{MQTT_BASE_TOPIC}/availability"
        self._client.publish(avail_topic, "online", retain=True)
        self._record(avail_topic, "online")
