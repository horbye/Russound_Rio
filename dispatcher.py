"""Classes for dispatching events"""

from __future__ import annotations

import asyncio
import functools
import logging
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any


_LOGGER = logging.getLogger(__name__)


class Signal:
    """Container for a named target function that receives events"""

    def __init__(self, dispatcher: Dispatcher, name: str, target: Callable):
        """Initialize signal."""
        self.dispatcher = dispatcher
        self.name = name
        self.target = target

    def disconnect(self) -> None:
        """Removes signal from the dispatcher."""
        self.dispatcher.disconnect(self)


class Dispatcher:
    """Handles event dispatching."""

    def __init__(self):
        """Initialize dispatcher."""
        self._signals: dict[str, list[Signal]] = defaultdict(list)
        self._loop = asyncio.get_event_loop()
        self._cmd_queue = asyncio.Queue()
        self._disconnects = []

    def connect(self, name: str, target: Callable) -> Signal:
        """Returns a new named signal that runs target function."""
        signal = Signal(self, name, target)
        self._signals[name].append(signal)
        return signal

    def send(self, name: str, *args: Any) -> None:
        """Calls named signal's target function with args."""
        if name in self._signals:
            for signal in self._signals[name]:
                self._call_target(signal.target, *args)
            if len(self._signals[name]) > 0:
                _LOGGER.debug(
                    "Dispatched signal '%s' to %s listener%s with %s",
                    name,
                    len(self._signals[name]),
                    "s" if len(self._signals[name]) > 1 else "",
                    args,
                )

    def disconnect(self, signal: Signal):
        """Removes signal."""
        try:
            self._signals[signal.name].remove(signal)
        except ValueError:
            pass

    def disconnect_all(self) -> None:
        """Disconnect all signals."""
        self._signals.clear()

    def _call_target(self, target: Callable, *args) -> Awaitable:
        check_target = target
        while isinstance(check_target, functools.partial):
            check_target = check_target.func
        if asyncio.iscoroutinefunction(check_target):
            return self._loop.create_task(target(*args))
        return self._loop.run_in_executor(None, target, *args)
