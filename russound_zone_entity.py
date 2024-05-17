"""Entity representing a Bang & Olufsen device."""

from __future__ import annotations

from typing import cast
from .russound import Russound
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN as RUSSOUND_DOMAIN
from homeassistant.const import CONF_HOST


class RussoundZoneBase:
    """Base class for BangOlufsen Home Assistant objects."""

    def __init__(self, entry: ConfigEntry, russ: Russound, zone_id, name) -> None:
        """Initialize the object."""
        self._russ = russ
        self.entry: ConfigEntry = entry
        self._host: str = self.entry.data[CONF_HOST]
        self._name = name
        self._zone_id = zone_id
        self._unique_id = self.entry.unique_id + " - Zone:" + str(self._zone_id)

        # Objects that get directly updated by notifications.
        # self._playback_metadata: PlaybackContentMetadata = PlaybackContentMetadata()
        # self._playback_progress: PlaybackProgress = PlaybackProgress(total_duration=0)
        # self._playback_source: Source = Source()
        # self._playback_state: RenderingState = RenderingState()
        # self._source_change: Source = Source()
        # self._volume: VolumeState = VolumeState(
        #     level=VolumeLevel(level=0), muted=VolumeMute(muted=False)
        # )


class RussoundZoneEntity(Entity, RussoundZoneBase):
    """Base Entity for BangOlufsen entities."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, client: Russound, zone_id, name) -> None:
        """Initialize the object."""
        super().__init__(entry, client, zone_id, name)

        self._attr_device_info = DeviceInfo(
            configuration_url=f"http://{self._host}/#/",
            identifiers={(RUSSOUND_DOMAIN, self._unique_id)},
            manufacturer="Russound",
            model="Zone",
            name=self._name,
            suggested_area=self._name,
        )
        self._attr_unique_id = self._unique_id

    async def _update_connection_state(self, connection_state: bool) -> None:
        """Update entity connection state."""
        self._attr_available = connection_state

        self.async_write_ha_state()
