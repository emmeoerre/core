"""The AVE ws integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .web_server import AveWebServer

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR]
_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the AVE ws integration."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up AVE ws from a config entry."""
    # Forward the entry to the binary sensor platform

    WS = AveWebServer(entry.data["ip_address"])
    if not await WS.authenticate():
        _LOGGER.error("AVEWS: Cannot connect to the web server")

    entry.runtime_data = WS
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Disconnect the WebSocket server
    web_server: AveWebServer = hass.data[DOMAIN].pop(entry.entry_id)
    await web_server.disconnect()

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
