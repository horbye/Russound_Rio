import asyncio
import logging
from .connection import Connection, ZoneID, PresetID, CommandException, UncachedVariable
from .dispatcher import Dispatcher
from .const import (
    DEFAULT_TIMEOUT,
    STATE_DISCONNECTED,
    STATE_CONNECTED,
    STATE_RECONNECTING,
    DEFAULT_RECONNECT_DELAY,
    EVENT_CONNECTION_CONNECTED,
    EVENT_CONNECTION_DISCONNECTED,
    SIGNAL_CONTROLLER_EVENT,
    EVENT_CONTROLLER_CONNECTED,
    EVENT_CONTROLLER_DISCONNECTED,
    SIGNAL_CONNECTION_EVENT,
    DOMAIN as RUSSOUND_DOMAIN,
)
from dataclasses import dataclass
from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from .russound_entity import RussoundEntity

from typing import TYPE_CHECKING, TypeVar, cast
from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
)

# from homeassistant.components.media_player.const import MEDIA_TYPE_MUSIC
# from homeassistant.const import STATE_OFF, STATE_ON

RUSSOUND_FEATURES = (
    MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.TURN_ON
    | MediaPlayerEntityFeature.TURN_OFF
    | MediaPlayerEntityFeature.SELECT_SOURCE
)

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

_LOGGER = logging.getLogger(__name__)


class Russound(RussoundEntity):
    """Manages the RIO connection to a Russound device."""

    _attr_icon = "mdi:speaker"
    _attr_name = None
    _attr_device_class = MediaPlayerDeviceClass.SPEAKER
    _attr_supported_features = RUSSOUND_FEATURES

    def __init__(self, entry: ConfigEntry, reconnect: bool = True):
        """
        Initialize the Russound object using the event loop, host and port
        provided.
        """
        super().__init__(entry)
        # self._model = self.get_amplifier_model()
        self._reconnect_enabled = reconnect
        self._reconnect_delay: float = DEFAULT_RECONNECT_DELAY
        self._timeout: float = DEFAULT_TIMEOUT
        self._state: str = STATE_DISCONNECTED
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._dispatcher = Dispatcher()
        self._connection = Connection(self._dispatcher, CONF_HOST, CONF_PORT)

    async def connect(self) -> None:
        if self.is_connected:
            return

        self._signals = [
            self.dispatcher.connect(SIGNAL_CONNECTION_EVENT, self._handle_event)
        ]

        await self._connection.connect(
            host=self._host,
            port=self._port,
            timeout=self._timeout,
            auto_reconnect=self._reconnect_enabled,
            reconnect_delay=self._reconnect_delay,
        )

        _LOGGER.debug(
            "Connected to server %s",
            self._host,
        )

    async def disconnect(self) -> None:
        """Disconnect from hardware."""
        if not self.is_connected:
            return

        await self._connection.disconnect()

        try:
            for signal in self._signals:
                signal.disconnect()
        finally:
            self._signals.clear()

    async def _handle_event(self, event: str, *args) -> None:
        """Handles updates to the system."""
        if event == EVENT_CONNECTION_CONNECTED:
            # Skip refresh until initial load of devices is complete. Preventing any
            # race conditions.
            self._dispatcher.send(SIGNAL_CONTROLLER_EVENT, EVENT_CONTROLLER_CONNECTED)

        elif event == EVENT_CONNECTION_DISCONNECTED:
            self._dispatcher.send(
                SIGNAL_CONTROLLER_EVENT, EVENT_CONTROLLER_DISCONNECTED
            )

    async def get_friendly_system_name(self) -> str:
        """Return friendly system name."""
        return cast(self._name)

    @property
    def should_poll(self):
        """No polling needed."""
        return False

    @property
    def dispatcher(self) -> Dispatcher:
        """Returns dispatcher instance."""
        return self._dispatcher

    @property
    def connection(self) -> Connection:
        """Returns connection instance."""
        return self._connection

    @property
    def is_connected(self) -> bool:
        """Returns whether connection is currently connected."""
        return self._connection._state == STATE_CONNECTED

    @property
    def is_reconnecting(self) -> bool:
        """Returns whether connection is currently reconnecting."""
        return self._connection._state == STATE_RECONNECTING

    @property
    def available(self) -> bool:
        """Returns if device is available."""
        return self._connection.is_connected()

    async def get_amplifier_model(self):
        """Get amplifier model name"""
        return await self._connection._send_cmd("GET C[%d].%s" % (1, "type"))

    async def set_zone_variable(self, zone_id, variable, value):
        """
        Set a zone variable to a new value.
        """
        return await self._connection._send_cmd(
            'SET %s.%s="%s"' % (zone_id.device_str(), variable, value)
        )

    async def get_zone_variable(self, zone_id, variable):
        """Retrieve the current value of a zone variable.  If the variable is
        not found in the local cache then the value is requested from the
        controller."""

        try:
            return await self._retrieve_cached_zone_variable(zone_id, variable)
        except UncachedVariable:
            return await self._connection._send_cmd(
                "GET %s.%s" % (zone_id.device_str(), variable)
            )

    def get_cached_zone_variable(self, zone_id, variable, default=None):
        """Retrieve the current value of a zone variable from the cache or
        return the default value if the variable is not present."""

        try:
            return self._retrieve_cached_zone_variable(zone_id, variable)
        except UncachedVariable:
            return default

    async def watch_zone(self, zone_id):
        """Add a zone to the watchlist.
        Zones on the watchlist will push all
        state changes (and those of the source they are currently connected to)
        back to the client"""
        r = await self._connection._send_cmd("WATCH %s ON" % (zone_id.device_str(),))
        self._connection._watched_zones.add(zone_id)
        return r

    async def unwatch_zone(self, zone_id):
        """Remove a zone from the watchlist."""
        self._connection._watched_zones.remove(zone_id)
        return await self._connection._send_cmd(
            "WATCH %s OFF" % (zone_id.device_str(),)
        )

    async def send_zone_event(self, zone_id, event_name, *args):
        """Send an event to a zone."""
        cmd = "EVENT %s!%s %s" % (
            zone_id.device_str(),
            event_name,
            " ".join(str(x) for x in args),
        )
        return await self._connection._send_cmd(cmd)

    async def enumerate_zones(self):
        """Return a list of (zone_id, zone_name) tuples"""
        zones = []
        for controller in range(1, 8):
            for zone in range(1, 17):
                zone_id = ZoneID(zone, controller)
                try:
                    name = await self.get_zone_variable(zone_id, "name")
                    if name:
                        zones.append((zone_id, name))
                except CommandException:
                    break
        return zones

    async def set_source_variable(self, source_id, variable, value):
        """Change the value of a source variable."""
        source_id = int(source_id)
        return self._connection._send_cmd(
            'SET S[%d].%s="%s"' % (source_id, variable, value)
        )

    async def get_source_variable(self, source_id, variable):
        """Get the current value of a source variable. If the variable is not
        in the cache it will be retrieved from the controller."""

        source_id = int(source_id)
        try:
            return self._retrieve_cached_source_variable(source_id, variable)
        except UncachedVariable:
            return await self._connection._send_cmd(
                "GET S[%d].%s" % (source_id, variable)
            )

    def get_cached_source_variable(self, source_id, variable, default=None):
        """Get the cached value of a source variable. If the variable is not
        cached return the default value."""

        source_id = int(source_id)
        try:
            return self._retrieve_cached_source_variable(source_id, variable)
        except UncachedVariable:
            return default

    async def watch_source(self, source_id):
        """Add a souce to the watchlist."""
        source_id = int(source_id)
        r = await self._connection._send_cmd("WATCH S[%d] ON" % (source_id,))
        self._connection._watched_sources.add(source_id)
        return r

    async def unwatch_source(self, source_id):
        """Remove a souce from the watchlist."""
        source_id = int(source_id)
        self._connection._watched_sources.remove(source_id)
        return await self._connection._send_cmd("WATCH S[%d] OFF" % (source_id,))

    async def get_preset_variable(self, preset_id, variable):
        """Retrieve the current value of a preset variable.  If the variable is
        not found in the local cache then the value is requested from the
        controller."""

        try:
            return self._retrieve_cached_preset_variable(preset_id, variable)
        except UncachedVariable:
            return await self._connection._send_cmd(
                "GET %s.%s" % (preset_id.device_str(), variable)
            )

    async def calc_preset_index(self, bank_id, preset_id):
        """
        Calculates the index of a preset.
        """
        return ((bank_id - 1) * 2) + preset_id

    async def enumerate_sources(self):
        """Return a list of (source_id, source_name, source_type) tuples"""
        sources = []
        for source_id in range(1, 17):
            try:
                source_name = await self.get_source_variable(source_id, "name")
                source_type = await self.get_source_variable(source_id, "type")
                if source_name and source_type:
                    sources.append((source_id, source_name, source_type))
            except CommandException:
                break
        return sources

    async def enumerate_presets(self):
        """Return a list of (source_id, bank_id, preset_id, index_id, preset_name) tuples"""
        banks = []
        for source_id in range(1, 17):
            try:
                source_name = await self.get_source_variable(source_id, "name")
                source_type = await self.get_source_variable(source_id, "type")
                if source_name and source_type:
                    if source_type == "RNET AM/FM Tuner (Internal)":
                        for bank_id in range(1, 7):
                            for preset_id in range(1, 7):
                                var_preset_id = PresetID(source_id, bank_id, preset_id)
                                preset_name = await self.get_preset_variable(
                                    var_preset_id, "name"
                                )
                                preset_valid = await self.get_preset_variable(
                                    var_preset_id, "valid"
                                )
                                if str(preset_valid) == "TRUE":
                                    index_id = await self.calc_preset_index(
                                        bank_id, preset_id
                                    )
                                    banks.append(
                                        (
                                            source_id,
                                            bank_id,
                                            preset_id,
                                            index_id,
                                            preset_name,
                                        )
                                    )
            except CommandException:
                break
        return banks

    def _retrieve_cached_zone_variable(self, zone_id, name):
        """
        Retrieves the cache state of the named variable for a particular
        zone. If the variable has not been cached then the UncachedVariable
        exception is raised.
        """
        try:
            s = self._connection._zone_state[zone_id][name.lower()]
            _LOGGER.debug(
                "Zone Cache retrieve %s.%s = %s", zone_id.device_str(), name, s
            )
            return s
        except KeyError:
            raise UncachedVariable

    def _retrieve_cached_source_variable(self, source_id, name):
        """
        Retrieves the cache state of the named variable for a particular
        source. If the variable has not been cached then the UncachedVariable
        exception is raised.
        """
        try:
            s = self._connection._source_state[source_id][name.lower()]
            _LOGGER.debug("Source Cache retrieve S[%d].%s = %s", source_id, name, s)
            return s
        except KeyError:
            raise UncachedVariable

    def _retrieve_cached_preset_variable(self, preset_id, name):
        """
        Retrieves the cache state of the named variable for a particular
        preset. If the variable has not been cached then the UncachedVariable
        exception is raised.
        """
        try:
            s = self._connection._preset_state[preset_id][name.lower()]
            _LOGGER.debug(
                "Preset Cache retrieve: %s.%s = %s", preset_id.device_str(), name, s
            )
            return s
        except KeyError:
            raise UncachedVariable

    def add_zone_callback(self, callback):
        """
        Registers a callback to be called whenever a zone variable changes.
        The callback will be passed three arguments: the zone_id, the variable
        name and the variable value.
        """
        self._connection._zone_callbacks.append(callback)

    def remove_zone_callback(self, callback):
        """
        Removes a previously registered zone callback.
        """
        self._connection._zone_callbacks.remove(callback)

    def add_source_callback(self, callback):
        """
        Registers a callback to be called whenever a source variable changes.
        The callback will be passed three arguments: the source_id, the
        variable name and the variable value.
        """
        self._connection._source_callbacks.append(callback)

    def remove_source_callback(self, source_id, callback):
        """
        Removes a previously registered source callback.
        """
        self._connection._source_callbacks.remove(callback)

    def add_preset_callback(self, callback):
        """
        Registers a callback to be called whenever a preset variable changes.
        The callback will be passed three arguments: the preset_id, the variable
        name and the variable value.
        """
        self._connection._preset_callbacks.append(callback)

    def remove_preset_callback(self, callback):
        """
        Removes a previously registered preset callback.
        """
        self._connection._preset_callbacks.remove(callback)
