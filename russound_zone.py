import logging
from .russound import Russound
from .russound_zone_entity import RussoundZoneEntity
from homeassistant.components.media_player import MediaPlayerEntity
from .const import DOMAIN as RUSSOUND_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo

_LOGGER = logging.getLogger(__name__)

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
)

from homeassistant.components.media_player.const import MEDIA_TYPE_MUSIC
from homeassistant.const import STATE_OFF, STATE_ON

RUSSOUND_FEATURES = (
    MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.TURN_OFF
    | MediaPlayerEntityFeature.SELECT_SOURCE
)


# RUSSOUND_FEATURES = (
#     MediaPlayerEntityFeature.PAUSE
#     | MediaPlayerEntityFeature.SEEK
#     | MediaPlayerEntityFeature.VOLUME_SET
#     | MediaPlayerEntityFeature.VOLUME_MUTE
#     | MediaPlayerEntityFeature.PREVIOUS_TRACK
#     | MediaPlayerEntityFeature.NEXT_TRACK
#     | MediaPlayerEntityFeature.PLAY_MEDIA
#     | MediaPlayerEntityFeature.SELECT_SOURCE
#     | MediaPlayerEntityFeature.STOP
#     | MediaPlayerEntityFeature.CLEAR_PLAYLIST
#     | MediaPlayerEntityFeature.PLAY
#     | MediaPlayerEntityFeature.BROWSE_MEDIA
#     | MediaPlayerEntityFeature.TURN_ON
#     | MediaPlayerEntityFeature.TURN_OFF
# )


from homeassistant.components.media_player import (
    ATTR_MEDIA_EXTRA,
    BrowseMedia,
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
    async_process_play_media_url,
)


class RussoundMediaPlayer(RussoundZoneEntity, MediaPlayerEntity):
    """Representation of a Russound Zone."""

    _attr_icon = "mdi:speaker"
    _attr_name = None
    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_supported_features = RUSSOUND_FEATURES

    def __init__(
        self, entry: ConfigEntry, russ: Russound, zone_id, name, sources, presets
    ):
        """Initialize the zone device."""
        super().__init__(entry, russ, zone_id, name)
        compliled_sources = []
        for source_id, source_name, source_type in sources:
            compliled_sources.append((source_id, source_name, None))
            if source_type == "RNET AM/FM Tuner (Internal)":
                for (
                    preset_source_id,
                    bank_id,
                    preset_id,
                    index_id,
                    preset_name,
                ) in presets:
                    if preset_source_id == source_id:
                        compliled_sources.append(
                            (source_id, source_name + ": " + preset_name, index_id)
                        )

        self._sources = compliled_sources
        self._presets = presets

    def _zone_var(self, name, default=None):
        return self._russ.get_cached_zone_variable(self._zone_id, name, default)

    def _source_var(self, name, default=None):
        current = int(self._zone_var("currentsource", 0))
        if current:
            return self._russ.get_cached_source_variable(current, name, default)
        return default

    def _source_na_var(self, name):
        """Will replace invalid values with None."""
        current = int(self._zone_var("currentsource", 0))
        if current:
            value = self._russ.get_cached_source_variable(current, name, None)
            if value in (None, "", "------"):
                return None
            return value
        return None

    def _zone_callback_handler(self, zone_id, *args):
        if zone_id == self._zone_id:
            self.schedule_update_ha_state()

    def _source_callback_handler(self, source_id, *args):
        current = int(self._zone_var("currentsource", 0))
        if source_id == current:
            self.schedule_update_ha_state()

    async def async_added_to_hass(self):
        """Register callback handlers."""
        self._russ.add_zone_callback(self._zone_callback_handler)
        self._russ.add_source_callback(self._source_callback_handler)

    @property
    def should_poll(self):
        """No polling needed."""
        return False

    #
    #
    #
    #
    #
    #
    #
    @property
    def state(self):
        """Return the state of the device."""
        status = self._zone_var("status", "OFF")
        if status == "ON":
            return STATE_ON
        if status == "OFF":
            return STATE_OFF

    #
    #
    #
    #
    #
    #
    # @property
    # def name(self):
    #     """Return the name of the zone."""
    #     return self._zone_var("name", self._name)

    # @property
    # def state(self):
    #     """Return the state of the device."""
    #     status = self._zone_var("status", "OFF")
    #     if status == "ON":
    #         return MediaPlayerEntityFeature.TURN_ON
    #     if status == "OFF":
    #         return MediaPlayerEntityFeature.TURN_OFF

    # @property
    # def supported_features(self):
    #     """Flag media player features that are supported."""
    #     return RUSSOUND_FEATURES

    #
    #
    #
    #
    #
    #

    @property
    def source(self):
        """Get the currently selected source."""
        return self._source_na_var("name")

    @property
    def source_list(self):
        """Return a list of available input sources."""
        return [x[1] for x in self._sources]

    @property
    def media_content_type(self):
        """Content type of current playing media."""
        return MEDIA_TYPE_MUSIC

    @property
    def media_title(self):
        """Title of current playing media."""
        if self._source_na_var("songname") != None:
            return self._source_na_var("songname")
        elif self._source_na_var("programservicename") != None:
            return self._source_na_var("programservicename")
        else:
            return self._source_na_var("name")

    @property
    def media_artist(self):
        """Artist of current playing media, music track only."""
        if self._source_na_var("artistname") != None:
            return self._source_na_var("artistname")
        elif self._source_na_var("radiotext") != None:
            return self._source_na_var("radiotext")
        else:
            return None

    @property
    def media_album_name(self):
        """Album name of current playing media, music track only."""
        if self._source_na_var("albumname") != None:
            return self._source_na_var("albumname")
        elif self._source_na_var("channel") != None:
            return self._source_na_var("channel")
        else:
            return None

    @property
    def media_image_url(self):
        """Image url of current playing media."""
        return self._source_na_var("coverarturl")

    @property
    def volume_level(self):
        """Volume level of the media player (0..1).
        Value is returned based on a range (0..50).
        Therefore float divide by 50 to get to the required range.
        """
        return float(self._zone_var("volume", 0)) / 50.0

    @property
    def is_volume_muted(self) -> bool | None:
        """Return true if volume is muted."""
        if self._zone_var("mute") == "ON":
            return True
        return False

    async def async_turn_off(self):
        """Turn off the zone."""
        await self._russ.send_zone_event(self._zone_id, "ZoneOff")

    async def async_turn_on(self):
        """Turn on the zone."""
        await self._russ.send_zone_event(self._zone_id, "ZoneOn")

    # self._russ.speaker.muted

    #
    # @property
    # def volume_mute(self):
    #     """Volume level of the media player (0..1).
    #     Value is returned based on a range (0..50).
    #     Therefore float divide by 50 to get to the required range.
    #     """
    #     return float(self._zone_var("volume", 0)) / 50.0

    # def mute_volume(self, mute: bool) -> None:
    #     """Mute (true) or unmute (false) media player."""
    #     if self._russ.get_zone_variable(self._zone_id, "Mute") == "On":
    #         self._russ.send_zone_event(self._zone_id, "Mute", "Off")
    #     self._russ.send_zone_event(self._zone_id, "Mute", "On")

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute the zone."""
        mute = int(13)
        # if mute:
        #     # await self._russ.set_zone_variable(self._zone_id, "mute", "ON")
        #     await self._russ._connection._send_cmd("EVENT C[1].Z[7]!KeyCode 13")
        # else:
        await self._russ.send_zone_event(self._zone_id, "KeyCode", mute)

    #
    #
    #
    #

    async def async_set_volume_level(self, volume):
        """Set the volume level."""
        rvol = int(volume * 50.0)
        await self._russ.send_zone_event(self._zone_id, "KeyPress", "Volume", rvol)

    async def async_select_source(self, source):
        """Select the source input for this zone."""
        for source_id, source_name, preset_id in self._sources:
            if source_name.lower() != source.lower():
                continue
            if preset_id == None:
                await self._russ.send_zone_event(
                    self._zone_id, "SelectSource", source_id
                )
                break
            else:
                await self._russ.send_zone_event(
                    self._zone_id, "SelectSource", source_id
                )
                await self._russ.send_zone_event(
                    self._zone_id, "RestorePreset", preset_id
                )
                break

    async def async_media_next_track(self):
        """Next Track."""
        """_LOGGER.warning("trying to execute next track")"""
        await self._russ.send_zone_event(self._zone_id, "KeyRelease", "Next")

    async def async_media_previous_track(self):
        """Previous Track."""
        """_LOGGER.warning("trying to execute previous track")"""
        await self._russ.send_zone_event(self._zone_id, "KeyRelease", "Previous")  #
