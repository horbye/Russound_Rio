import asyncio
import logging

from async_timeout import timeout
from .russound import Russound
from .error import RussoundError
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import device_registry as dr
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.components.media_player.const import DOMAIN as MEDIA_PLAYER_DOMAIN
from .const import DOMAIN as RUSSOUND_DOMAIN, STATE_CONNECTED
from homeassistant.const import (
    CONF_NAME,
    CONF_HOST,
    EVENT_HOMEASSISTANT_STOP,
    CONF_PORT,
)
from homeassistant.exceptions import ConfigEntryNotReady

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Load a config entry."""
    hass.data.setdefault(RUSSOUND_DOMAIN, {})
    await hass.config_entries.async_forward_entry_setup(entry, MEDIA_PLAYER_DOMAIN)

    return True


# async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
#     """Load a config entry."""
#     hass.data.setdefault(RUSSOUND_DOMAIN, {})
#     controller = Russound(entry)
#     try:
#         await controller.connect()
#     except (RussoundError, ConnectionError) as err:
#         await controller.disconnect()
#         _LOGGER.debug("Unable to connect: %s", err)
#         raise ConfigEntryNotReady from err

#     async def disconnect(event: str):
#         await controller.disconnect()

#     entry.async_on_unload(
#         hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, disconnect)
#     )
#     hass.data[RUSSOUND_DOMAIN][entry.entry_id] = controller

#     await hass.config_entries.async_forward_entry_setup(entry, MEDIA_PLAYER_DOMAIN)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload config entry."""
    controller: Russound = hass.data[RUSSOUND_DOMAIN][entry.entry_id]
    await controller._connection.disconnect()
    await hass.config_entries.async_forward_entry_unload(entry, MEDIA_PLAYER_DOMAIN)
    del hass.data[RUSSOUND_DOMAIN][entry.entry_id]
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, ConfigEntry)
    await async_setup_entry(hass, ConfigEntry)
