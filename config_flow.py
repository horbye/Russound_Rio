"""Config flow for Rio integration."""

import logging
import asyncio
from .russound import Russound
import voluptuous as vol
from async_timeout import timeout
from homeassistant import config_entries
from homeassistant.const import CONF_NAME, CONF_HOST, CONF_PORT

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


DEFAULT_NAME = "Russound"
DEFAULT_HOST = "192.168.16.250"
DEFAULT_PORT = 9621

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
        vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
    }
)


class RussoundConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Russound configuration flow."""

    VERSION = 1

    def __init__(self) -> None:
        """Init discovery flow."""
        self._domain = DOMAIN

    async def async_step_user(self, user_input=None):
        errors = {}
        _LOGGER.debug("Handle the confirmation step.")
        if user_input is not None:
            try:
                r, w = await asyncio.open_connection(
                    user_input["host"], user_input["port"]
                )
                _LOGGER.info("Success connecting to Russound")
                w.close()
                await w.wait_closed()
                await self.async_set_unique_id(self._domain, raise_on_progress=False)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input["name"], data=user_input
                )
            except Exception as e:
                errors["base"] = "Failed connecting to Russound"
        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )
