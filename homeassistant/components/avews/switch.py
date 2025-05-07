"""Binary sensor platform for AVEWS integration."""

import logging
from typing import Any

from homeassistant.components.switch import SwitchDeviceClass, SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .web_server import AveWebServer

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant | None,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up AVEWS binary sensors.

    Args:
        hass: Home Assistant instance.
        entry: Config entry for the integration.
        async_add_entities: Callback to add entities to Home Assistant.

    """
    webserver: AveWebServer = entry.runtime_data
    if not webserver:
        _LOGGER.error("AVEWS: Web server not initialized")
        raise ConfigEntryNotReady("Can't reach webserver")

    await webserver.set_async_add_sw_entities(async_add_entities)
    await webserver.set_update_switch(update_switch)


def set_sensor_uid(family, device_id):
    """Set the unique ID for the sensor."""
    return f"ave_switch_{family}_{device_id}"  # Unique ID for the sensor


def update_switch(server: AveWebServer, family, device_id, device_status, name=None):
    """Update switch based on the family and device status."""

    if family not in [1]:
        _LOGGER.debug(
            " Not updating switch for family %s, device_id %s",
            family,
            device_id,
        )
        return
    _LOGGER.debug(" Updating switch for family %s, device_id %s", family, device_id)

    unique_id = set_sensor_uid(family, device_id)
    already_exists = unique_id in server.switches
    if already_exists:
        # Update the existing sensor's state
        switch: LightSwitch = server.switches[unique_id]
        if device_status >= 0:
            switch.update_state(device_status)
        if name is not None and server.settings.get_entity_names:
            switch.set_name(name)
    else:
        # Create a new motion detection sensor
        switch = LightSwitch(
            unique_id=unique_id,
            is_on=device_status,
            family=family,
            device_id=device_id,
            webserver=server,
        )
        if name is not None and server.settings.get_entity_names:
            switch.set_name(name)
        _LOGGER.info("Creating new switch entity %s", name)
        server.switches[unique_id] = switch
        server.async_add_sw_entities([switch])  # Add the new sensor to Home Assistant


class LightSwitch(SwitchEntity):
    """Representation of a light switch."""

    def __init__(
        self,
        unique_id: str,
        family: int,
        device_id: int,
        is_on: int,
        name=None,
        webserver: AveWebServer | None = None,
    ) -> None:
        """Initialize the motion detection sensor."""
        self._unique_id = unique_id
        self._is_on = is_on
        self.device_id = device_id
        self.family = family
        self._webserver = webserver
        if is_on >= 0:
            self._attr_is_on = bool(is_on)  # Initialize the state
        if name is None:
            self._name = self.build_name()
        else:
            self._name = name

    async def async_toggle(self, **kwargs: Any) -> None:
        """Toggle the switch."""
        if self._webserver:
            await self._webserver.switch_toggle(self.device_id)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        if self._webserver:
            await self._webserver.switch_turn_on(self.device_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        if self._webserver:
            await self._webserver.switch_turn_off(self.device_id)

    @property
    def unique_id(self) -> str:
        """Return the unique ID of the sensor."""
        return self._unique_id

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return self._name

    @property
    def device_class(self) -> SwitchDeviceClass | None:
        """Return the device class of the sensor."""
        return SwitchDeviceClass.SWITCH

    def update_state(self, is_on: int):
        """Update the state of the switch."""
        if is_on < 0:
            return
        self._attr_is_on = bool(is_on)  # Set the state to True (on) or False (off)
        self.async_write_ha_state()  # Notify Home Assistant of the state change

    def set_name(self, name: str):
        """Set the name of the sensor."""
        self._name = name

    def build_name(self) -> str:
        """Build the name of the sensor based on its family and device ID."""
        suffix = "sensor type " + str(self.family)
        if self.family == 1:
            suffix = "light"
        elif self.family == 6:
            suffix = "sccenario"
        return f"AVE {suffix} {self.device_id}"
