"""Support for Russound multizone controllers using RIO Protocol."""

from .russound import Russound
from .russound_zone import RussoundMediaPlayer
from .error import RussoundError

import logging
import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import entity_platform
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import device_registry as dr
from .const import (
    DOMAIN as RUSSOUND_DOMAIN,
    SIGNAL_CONNECTION_EVENT,
)
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STOP,
)

_LOGGER = logging.getLogger(__name__)


logging.basicConfig(level=logging.DEBUG)
# PYTHONASYNCIODEBUG=1


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
):
    """Set up the platform from a config entry."""
    platform = entity_platform.async_get_current_platform()
    controller = Russound(entry)
    hass.data[RUSSOUND_DOMAIN][entry.entry_id] = controller
    try:
        await controller.connect()
        if controller.is_connected:
            async_add_entities(new_entities=[controller])
            sources = await controller.enumerate_sources()
            presets = await controller.enumerate_presets()
            valid_zones = await controller.enumerate_zones()

            for source_id, source_name, source_type in sources:
                await controller.watch_source(source_id)

            for zone_id, name in valid_zones:
                await controller.watch_zone(zone_id)
                _LOGGER.info("Opretter %s:%s", zone_id, name)
                async_add_entities(
                    new_entities=[
                        RussoundMediaPlayer(
                            entry, controller, zone_id, name, sources, presets
                        )
                    ]
                )
    except (RussoundError, ConnectionError) as err:
        await controller._connection.disconnect()
        _LOGGER.error("Unable to connect: %s", err)
        raise ConfigEntryNotReady from err

    async def async_create_entities(self) -> None:
        """Handles reconnecting entities."""
        for zone_id, name in valid_zones:
            await controller.watch_zone(zone_id)

        for source_id, source_name, source_type in sources:
            await controller.watch_source(source_id)

    controller._signals = [
        controller.dispatcher.connect(SIGNAL_CONNECTION_EVENT, async_create_entities)
    ]

    @callback
    def on_stop(event):
        """Shutdown cleanly when hass stops."""
        hass.loop.create_task(controller.disconnect())

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, on_stop)
