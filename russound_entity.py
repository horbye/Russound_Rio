"""Entity representing a Bang & Olufsen device."""

from __future__ import annotations
from typing import cast
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_NAME
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN as RUSSOUND_DOMAIN


class RussoundBase:
    """Base class for BangOlufsen Home Assistant objects."""

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the object."""
        self.entry: ConfigEntry = entry
        self._host: str = self.entry.data[CONF_HOST]
        self._port: str = self.entry.data[CONF_PORT]
        self._name = entry.data[CONF_NAME] + " Amp"
        self._unique_id = self.entry.unique_id + " - Amp" + str(0)


class RussoundEntity(Entity, RussoundBase):
    """Base Entity for BangOlufsen entities."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry) -> None:
        """Initialize the object."""
        super().__init__(entry)

        self._attr_device_info = DeviceInfo(
            configuration_url=f"http://{self._host}/#/",
            identifiers={(RUSSOUND_DOMAIN, self._unique_id)},
            manufacturer="Russound",
            model="MCA-C5",
            name=self._name,
            suggested_area=f"Rack",
        )
        self._attr_unique_id = self._unique_id

    async def _update_connection_state(self, connection_state: bool) -> None:
        """Update entity connection state."""
        self._attr_available = connection_state
        self.async_write_ha_state()
