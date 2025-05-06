"""WebSocket connection to the AVE web server."""

import asyncio
import logging
from typing import Any

import aiohttp

from .binary_sensor import MotionBinarySensor

_LOGGER = logging.getLogger(__name__)


class AveWebServer:
    """AVE web server class."""

    def __init__(self, host: str) -> None:
        """Initialize."""
        self.host = host
        self.ws_conn = None
        self._connected = False
        self.device_list: list[Any] = []
        self.wstask: asyncio.Task
        self.started = False
        self.closed = False
        self.binary_sensors: dict[
            str, MotionBinarySensor
        ] = {}  # Track binary sensors by unique ID
        self.binary_sensor_async_add_entities = None

    async def set_binary_sensor_async_add_entities(self, async_add_entities) -> None:
        """Set the async_add_entities method for binary sensors."""
        self.binary_sensor_async_add_entities = async_add_entities

    async def is_connected(self) -> bool:
        """Return if the web server is connected."""
        return self._connected

    async def authenticate(self) -> bool:
        """Test if we can authenticate with the host."""
        self.wstask = asyncio.create_task(self.connect())
        return True

    async def start(self) -> None:
        """Start the WebSocket connection."""
        if self.ws_conn is None or self.ws_conn.closed:
            await self.connect()

        self.started = True
        await self.on_connect_actions()

    async def disconnect(self) -> None:
        """Disconnect from the web server."""
        self.closed = True
        if self.ws_conn:
            await self.ws_conn.close()
            self.ws_conn = None
            self._connected = False
            _LOGGER.info("WebSocket disconnected!", extra={"host": self.host})

    async def connect(self):
        """Connect to the web server."""
        session = aiohttp.ClientSession()
        try:
            self.ws_conn = await session.ws_connect(
                f"ws://{self.host}:14001",
                protocols=["binary"],
            )
            self._connected = True
            _LOGGER.info("WebSocket connected!", extra={"host": self.host})

            if self.started:
                await self.on_connect_actions()

            async for msg in self.ws_conn:
                if msg.type == aiohttp.WSMsgType.BINARY:
                    await self.on_message(msg.data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    _LOGGER.error("WebSocket error", extra={"error": msg.data})
                    break

        except aiohttp.ClientError as e:
            _LOGGER.error("WebSocket connection failed", exc_info=e)
        finally:
            self._connected = False
            if self.closed:
                _LOGGER.info("WebSocket connection closed by user")
            else:
                _LOGGER.warning("WebSocket closed. Reconnecting in 5 seconds")
                await asyncio.sleep(5)
                await self.connect()

    async def on_connect_actions(self):
        """Actions to perform after connecting to the web server."""

        # Get status by family type 1 (lights)
        await self.send_ws_command("GSF", "1")

        # Get status by family type 12 (motion detection areas)
        await self.send_ws_command("GSF", ["12"])

        # potentially replaces GSF command for type 12
        await self.send_ws_command("WSF", "12")

        await self.send_ws_command("SU3")  # Start streaming updates (most of them)
        # await self.send_ws_command("SU2") # Starts streaming updates (UPD for TLO and XU , NET and CLD messages)

    def value_to_hex(self, value):
        """Return the herawstringalue of a number."""
        return hex(value)[2:].upper()

    def build_crc(self, rawstring):
        """Build CRC for the given string."""
        crc = 0
        for char in rawstring:
            crc ^= ord(char)
        crc = 0xFF - crc
        msb = self.value_to_hex(crc >> 4)
        lsb = self.value_to_hex(crc & 0xF)
        return msb + lsb

    async def on_message(self, message):
        """Handle incoming messages from the web server."""
        # _LOGGER.debug("Received message: %s", message)
        try:
            # Ensure the message is decoded if it's in bytes
            if isinstance(message, bytes):
                message = message.decode("utf-8")  # Decode bytes to string using UTF-8
            # log_with_timestamp(message)
            messages = message.split(chr(0x04))
            for msg in messages:
                if len(msg) < 3:
                    continue
                str_msg = msg[1:-3]
                cmd_params, *records_data = str_msg.split(chr(0x1E))
                command, *parameters = cmd_params.split(chr(0x1D))
                records = [record.split(chr(0x1D)) for record in records_data]
                await self.manage_commands(command, parameters, records)
        except Exception as e:  # noqa: BLE001
            _LOGGER.error("Error processing message", exc_info=e)

    async def send_ws_command(self, command, parameters=None):
        """Send a command to the web server."""
        message = chr(0x02) + command
        if parameters:
            message += chr(0x1D) + chr(0x1D).join(parameters)
        message += chr(0x03)
        crc = self.build_crc(message)
        full_message = message + crc + chr(0x04)
        if self.ws_conn and not self.ws_conn.closed:
            await self.ws_conn.send_str(full_message)
            # _LOGGER.debug("Sent command: %s", full_message)
        else:
            _LOGGER.error("WebSocket is not connected")

    async def manage_commands(self, command, parameters, records):
        """Manage commands received from the web server."""
        if command == "pong":
            pass
        elif command == "ack":
            _LOGGER.debug("Received ACK for command:", extra={"command": parameters[0]})
        elif command == "ping":
            await self.send_ws_command("PONG")
        elif command == "gsf":
            self.manage_gsf(parameters, records)
        elif command == "upd":
            self.manage_upd(parameters, records)
        elif command == "cld":
            # cloud commands received from SU2
            pass
        elif command == "net":
            # IOT commands received from SU2
            pass
        else:
            _LOGGER.error(
                "Unknown command",
                extra={
                    "command": command,
                    "parameters": parameters,
                    "records": records,
                },
            )

    def manage_upd(self, parameters, records):
        """Manage UPD commands received from the web server."""
        _LOGGER.debug(
            "Received UPD command. Parameters: %s Records: %s", parameters, records
        )
        if parameters[0] == "WS":
            pass
            # Async device updates. Will replace the polling approach
            # Devices with ID > 2000000 must be scenarios or something...

            # device_type = int(parameters[1])
            # device_id = int(parameters[2])
            # device_status = int(parameters[3])
            # if device_type in [12, 13]:
            #     log_with_timestamp(f"Received async Antitheft status update. Device ID: {device_id}, Device Type: {device_type}, Status: {device_status}")
            # else:
            #     log_with_timestamp(f"Received async status update. Device ID: {device_id}, Device Type: {device_type}, Status: {device_status}")
            #     if device_type in [1, 2, 22, 9, 3, 16, 19, 6]:  # Limited to [Lighting / Energy / Shutters / Scenarios] for security reasons --- VER228 WANDA
            #         for device in DOMINAPLUS_MANAGER_deviceList:
            #             if "id" in device and "type" in device and int(device["id"]) == device_id and int(device["type"]) == device_type:
            #                 device["currentVal"] = device_status
        elif parameters[0] == "X" and parameters[1] == "A":  # ANTITHEFT AREA
            # parameters[2] is the area ID. all other parameters are == 0 when triggered, parameters[6] == 1 when cleared
            # really sensitive, better use a polling approach for now

            area_progressive = int(parameters[2])
            # area_engaged = int(parameters[3])
            # area_in_alarm = int(parameters[5])
            area_clear = int(parameters[6])
            status = 1
            if area_clear > 0:
                status = 0
            self.update_binary_sensors(12, area_progressive, status)
            # log_with_timestamp(f"{ANTITHEFT_PREFIX} XA - areaID: {area_progressive} - engaged: {area_engaged} - clear: {area_clear} - alarm: {area_in_alarm}")
        elif parameters[0] == "X" and parameters[1] == "S":  # ANTITHEFT SENSOR
            self.update_binary_sensors(1007, int(parameters[2]), int(parameters[4]))
        elif parameters[0] == "X" and parameters[1] == "U":
            # ANTITHEFT UNIT (requires SU2)
            _LOGGER.debug("XU Antitheft Unit - engaged", extra={"id": parameters[2]})
        elif parameters[0] == "WT":
            if parameters[1] == "O":  # THERMOSTAT OFFSET  # noqa: SIM114
                pass
            elif parameters[1] == "S":  # THERMOSTAT SEASON # noqa: SIM114
                pass
            elif parameters[1] == "T":  # THERMOSTAT TEMPERATURE # noqa: SIM114
                pass
            elif parameters[1] == "L":  # DAIKIN FAN LEVEL # noqa: SIM114
                pass
            elif parameters[1] == "Z":  # DAIKIN LOCALOFF
                pass
        elif (
            parameters[0] == "TT" or parameters[0] == "TP" or parameters[0] == "TR"
        ):  # THERMOSTAT TEMPERATURE
            pass
        elif (
            parameters[0] == "TLO" or parameters[0] == "D"
        ):  # THERMOSTAT LOCAL OFF (requires SU2)
            pass
        elif parameters[0] == "GUI":
            # Reload gui
            pass
        else:
            _LOGGER.warning("Not yet handled UPD", extra={"parameters": parameters})

    def manage_gsf(self, parameters, records):
        """Manage GSF Get Status by Family commands received from the web server."""
        _LOGGER.debug(
            "Received GSF command for family %s",
            parameters[0],
            extra={"parameters": parameters, "records": records},
        )
        if parameters[0] in ["7", "12"]:  # Motion detection types
            for record in records:
                device_id, device_status = int(record[0]), int(record[1])
                self.update_binary_sensors(int(parameters[0]), device_id, device_status)

        if parameters[0] == "1":
            for record in records:
                device_id, device_status = int(record[0]), int(record[1])
                # send_mqtt_message(device_id, device_status)

    def update_binary_sensors(self, family, device_id, device_status):
        """Update binary sensors based on the family and device status."""

        if family not in [12, 1007]:
            _LOGGER.debug(
                " Not updating binary sensor for family %s, device_id %s",
                family,
                device_id,
            )
            return
        _LOGGER.debug(
            " Updating binary sensor for family %s, device_id %s", family, device_id
        )

        unique_id = f"ave_motion_{family}_{device_id}"  # Unique ID for the sensor

        # Check if the sensor already exists
        if unique_id in self.binary_sensors:
            # Update the existing sensor's state
            sensor = self.binary_sensors[unique_id]
            sensor.update_state(device_status)
        else:
            # Create a new motion detection sensor
            sensor = MotionBinarySensor(
                unique_id=unique_id,
                is_motion_detected=device_status > 0,
                family=family,
                device_id=device_id,
            )
            self.binary_sensors[unique_id] = sensor
            self.binary_sensor_async_add_entities(
                [sensor]
            )  # Add the new sensor to Home Assistant
