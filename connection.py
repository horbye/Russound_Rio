"""Class handling network connection to Russound device."""

import asyncio
import re
import logging
import time
from .error import RussoundError, MessageParseError, format_error
from .const import (
    DEFAULT_TIMEOUT,
    DEFAULT_RECONNECT_DELAY,
    STATE_DISCONNECTED,
    STATE_CONNECTED,
    STATE_RECONNECTING,
    DEFAULT_RECONNECT_DELAY,
    EVENT_CONNECTION_CONNECTED,
    EVENT_CONNECTION_RECONNECTING,
    EVENT_CONNECTION_DISCONNECTED,
    EVENT_CONNECTION_MESSAGE,
    SIGNAL_CONNECTION_EVENT,
)
from homeassistant.const import (
    CONF_ID,
    CONF_HOST,
    CONF_PORT,
    EVENT_HOMEASSISTANT_STOP,
    STATE_OFF,
    STATE_ON,
)

# from .rio import ZoneID, PresetID
# r"^VERSION\=(?P<version>(\"\d\d\.\d\d\.\d\d\"))|"
_re_response = re.compile(
    r"(?:"
    r"(?:S\[(?P<preset_source>\d+)\].B\[(?P<preset_bank>\d+)\].P\[(?P<preset>\d+)\])|"
    r"(?:S\[(?P<source>\d+)\])|"
    r"(?:C\[(?P<controller>\d+)\].Z\[(?P<zone>\d+)\]))"
    r"\.(?P<variable>\S+)=\"(?P<value>.*)\""
)


# _re_response = re.compile(
#     r"(?:"
#     r"(?:S\[(?P<preset_source>\d+)\].B\[(?P<preset_bank>\d+)\].P\[(?P<preset>\d+)\])|"
#     r"VERSION\=(?P<version>(\"\d\d\.\d\d\.\d\d\"))|"
#     r"(?:S\[(?P<source>\d+)\])|"
#     r"(?:C\[(?P<controller>\d+)\].Z\[(?P<zone>\d+)\]))|"
#     r"\.(?P<variable>\S+)=\"(?P<value>.*)\""
# )

# Maintain compat with various 3.x async changes
if hasattr(asyncio, "ensure_future"):
    ensure_future = asyncio.ensure_future
else:
    ensure_future = getattr(asyncio, "async")


class CommandException(Exception):
    """A command sent to the controller caused an error."""

    pass


class UncachedVariable(Exception):
    """A variable was not found in the cache."""

    pass


from . import const
from .error import RussoundError, MessageParseError, format_error

from .dispatcher import Dispatcher

_LOGGER = logging.getLogger(__name__)


class ZoneID:
    """Uniquely identifies a zone

    Russound controllers can be linked together to expand the total zone count.
    Zones are identified by their zone index (1-N) within the controller they
    belong to and the controller index (1-N) within the entire system.
    """

    def __init__(self, zone, controller=1):
        self.zone = int(zone)
        self.controller = int(controller)

    def __str__(self):
        return "%d:%d" % (self.controller, self.zone)

    def __eq__(self, other):
        return (
            hasattr(other, "zone")
            and hasattr(other, "controller")
            and other.zone == self.zone
            and other.controller == self.controller
        )

    def __hash__(self):
        return hash(str(self))

    def device_str(self):
        """
        Generate a string that can be used to reference this zone in a RIO
        command
        """
        return "C[%d].Z[%d]" % (self.controller, self.zone)


class PresetID:
    """Uniquely identifies a preset
    Russound presets can be found as part of a source's bank.
    Presets are identified by their preset index [1-6]  within a bank [1-6] on the source they
    belong to.
    """

    def __init__(self, source, bank, preset):
        self.source = int(source)
        self.bank = int(bank)
        self.preset = int(preset)

    def __str__(self):
        return "%d:%d:%d" % (self.source, self.bank, self.preset)

    def __eq__(self, other):
        return (
            hasattr(other, "source")
            and hasattr(other, "bank")
            and hasattr(other, "preset")
            and other.source == self.source
            and other.bank == self.bank
            and other.preset == self.preset
        )

    def __hash__(self):
        return hash(str(self))

    def device_str(self):
        """
        Generate a string that can be used to reference this preset in a RIO
        command
        """
        return "S[%d].B[%d].P[%d]" % (self.source, self.bank, self.preset)


class Connection:
    """Class handling network connection to hardware device."""

    def __init__(self, dispatcher: Dispatcher, host, port) -> None:
        """Initializes connection."""
        self._dispatcher = dispatcher
        self._host = host
        self._port = port
        self._timeout: float = DEFAULT_TIMEOUT
        self._state: str = STATE_DISCONNECTED
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._response_handler_task: asyncio.Task | None = None
        self._reconnect_delay: float | None = None
        self._reconnect_task: asyncio.Task | None = None
        self._auto_reconnect: bool = False
        self._cmd_queue = asyncio.Queue()
        self._source_state = {}
        self._zone_state = {}
        self._preset_state = {}
        self._watched_zones = set()
        self._watched_sources = set()
        self._zone_callbacks = []
        self._source_callbacks = []
        self._preset_callbacks = []
        self._first_run = True

    async def connect(
        self,
        host: str,
        port: int = None,
        *,
        timeout: float = None,
        auto_reconnect: bool = False,
        reconnect_delay: float = DEFAULT_RECONNECT_DELAY,
    ) -> None:
        """Connects to the hardware device."""
        if self._state == const.STATE_CONNECTED:
            return

        self._host = host
        self._port = port
        self._timeout = timeout if timeout else DEFAULT_TIMEOUT
        self._auto_reconnect = auto_reconnect
        self._reconnect_delay = reconnect_delay
        await self._connect()
        _LOGGER.debug("Connected to %s", self._host)

    async def _connect(self) -> None:
        """Connect to server."""
        try:
            connection = asyncio.open_connection(self._host, self._port)
            self._reader, self._writer = await asyncio.wait_for(
                connection, self._timeout
            )
        except ConnectionError:
            # Don't allow subclasses of ConnectionError to be cast as OSErrors below
            asyncio.create_task(self._handle_connection_error(err))
            # raise
        except (OSError, asyncio.TimeoutError) as err:
            # Generalize connection errors
            # if self._state == STATE_DISCONNECTED:
            #     await self._reconnect()
            asyncio.create_task(self._handle_connection_error(err))
            # raise ConnectionError(format_error(err)) from err

        self._response_handler_task = asyncio.create_task(self._response_handler())
        self._dispatcher.send(SIGNAL_CONNECTION_EVENT, EVENT_CONNECTION_CONNECTED)
        self._state = STATE_CONNECTED
        # self._dispatcher.send(STATE_CONNECTED)

    async def _reconnect(self):
        """Reconnect to server."""
        try:
            while self._state != STATE_CONNECTED:
                try:
                    await self._connect()
                except ConnectionError as err:
                    _LOGGER.debug("Failed reconnect to %s with '%s'", self._host, err)
                    await self._disconnect()
                    await asyncio.sleep(self._reconnect_delay)
                else:
                    self._reconnect_task = None
                    self._dispatcher.send(
                        SIGNAL_CONNECTION_EVENT, EVENT_CONNECTION_RECONNECTING
                    )
                    _LOGGER.debug("Reconnected to %s", self._host)
        except Exception as err:  # pylint: disable=broad-except
            _LOGGER.debug("Unhandled exception %s('%s')", type(err).__name__, err)
            raise

    async def disconnect(self):
        """Disconnect from server."""
        if self._state == STATE_DISCONNECTED:
            return
        # Cancel pending reconnect task
        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except:  # pylint: disable=bare-except
                # Ensure completes
                pass
            self._reconnect_task = None

        await self._disconnect()
        self._state = STATE_DISCONNECTED

        _LOGGER.debug("Disconnected from %s", self._host)
        self._dispatcher.send(SIGNAL_CONNECTION_EVENT, EVENT_CONNECTION_DISCONNECTED)

    async def _disconnect(self):
        """Disconnect from server."""
        if self._response_handler_task:
            self._response_handler_task.cancel()
            try:
                await self._response_handler_task
            except:  # pylint: disable=bare-except
                # Ensure completes
                pass
            self._response_handler_task = None

        if self._writer:
            self._writer.close()
            self._writer = None

        self._reader = None
        # self._pending_requests.clear()

    def is_connected(self) -> bool:
        """Checks how long ago reading while loop, was active."""
        if self._state == STATE_CONNECTED:
            return True
        else:
            return False

    async def _handle_connection_error(self, err: Exception):
        """Handle connection failures and schedule reconnect."""
        await self._disconnect()
        self._state = STATE_RECONNECTING
        self._reconnect_task = asyncio.create_task(self._reconnect())
        _LOGGER.debug(
            "Disconnected from %s %s('%s')", self._host, type(err).__name__, err
        )

    def _store_cached_zone_variable(self, zone_id, name, value):
        """
        Stores the current known value of a zone variable into the cache.
        Calls any zone callbacks.
        """
        zone_state = self._zone_state.setdefault(zone_id, {})
        name = name.lower()
        zone_state[name] = value
        _LOGGER.debug("Zone Cache store %s.%s = %s", zone_id.device_str(), name, value)
        for callback in self._zone_callbacks:
            callback(zone_id, name, value)

    def _store_cached_source_variable(self, source_id, name, value):
        """
        Stores the current known value of a source variable into the cache.
        Calls any source callbacks.
        """
        source_state = self._source_state.setdefault(source_id, {})
        name = name.lower()
        source_state[name] = value
        _LOGGER.debug("Source Cache store S[%d].%s = %s", source_id, name, value)
        for callback in self._source_callbacks:
            callback(source_id, name, value)

    def _store_cached_preset_variable(self, preset_id, name, value):
        """
        Stores the current known value of a zone variable into the cache.
        Calls any zone callbacks.
        """
        preset_state = self._preset_state.setdefault(preset_id, {})
        name = name.lower()
        preset_state[name] = value
        _LOGGER.debug(
            "Preset Cache store %s.%s = %s", preset_id.device_str(), name, value
        )
        for callback in self._preset_callbacks:
            callback(preset_id, name, value)

    def _process_response(self, res):
        s = str(res, "utf-8").strip()
        ty, payload = s[0], s[2:]
        if ty == "E":
            _LOGGER.debug("Device responded with error: %s", payload)
            raise CommandException(payload)

        m = _re_response.match(payload)
        if not m:
            return ty, None
        _LOGGER.debug(m)
        p = m.groupdict()
        if p["source"]:
            source_id = int(p["source"])
            self._store_cached_source_variable(source_id, p["variable"], p["value"])
        elif p["zone"]:
            zone_id = ZoneID(controller=p["controller"], zone=p["zone"])
            self._store_cached_zone_variable(zone_id, p["variable"], p["value"])
        elif p["preset_source"]:
            preset_id = PresetID(p["preset_source"], p["preset_bank"], p["preset"])
            self._store_cached_preset_variable(preset_id, p["variable"], p["value"])
        return ty, p["value"]

    async def _send_cmd(self, cmd):
        #######################################################
        # logger.info("CMD %s", cmd)
        # logger.info("CMD-IsConnected %s", await self.is_connected())
        #######################################################
        future = asyncio.Future()
        await self._cmd_queue.put((cmd, future))
        r = await future
        return r

    async def _response_handler(self) -> None:
        # self._ioloop_future = ensure_future(self._ioloop())
        queue_future = ensure_future(self._cmd_queue.get())
        net_future = ensure_future(self._reader.readline())
        try:
            _LOGGER.debug("Starting IO loop")
            while True:
                #######################################################
                # _LOGGER.info("While loop: %s", self._cmd_queue.get())
                #######################################################
                done, pending = await asyncio.wait(
                    [queue_future, net_future], return_when=asyncio.FIRST_COMPLETED
                )

                if net_future in done:
                    response = net_future.result()
                    try:
                        self._process_response(response)
                    except CommandException:
                        pass
                    net_future = ensure_future(self._reader.readline())

                if queue_future in done:
                    cmd, future = queue_future.result()
                    cmd += "\r"
                    self._writer.write(bytearray(cmd, "utf-8"))
                    await self._writer.drain()

                    queue_future = ensure_future(self._cmd_queue.get())

                    while True:
                        response = await net_future
                        net_future = ensure_future(self._reader.readline())
                        try:
                            ty, value = self._process_response(response)
                            if ty == "S":
                                future.set_result(value)
                                break
                        except CommandException as e:
                            future.set_exception(e)
                            break
            _LOGGER.debug("IO loop exited")
        except asyncio.CancelledError as err:
            _LOGGER.debug("IO loop cancelled")
            self._writer.close()
            queue_future.cancel()
            net_future.cancel()
            # self.close()
            asyncio.create_task(self._handle_connection_error(err))
            return
        except IndexError as err:
            _LOGGER.debug("Index error")
            self._writer.close()
            queue_future.cancel()
            net_future.cancel()
            # self.close()
            asyncio.create_task(self._handle_connection_error(err))
            return
        except Exception as err:
            _LOGGER.debug(err)
            self._writer.close()
            queue_future.cancel()
            net_future.cancel()
            # self.close()
            asyncio.create_task(self._handle_connection_error(err))
            return
