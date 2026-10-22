"""Approximate host power outages from Home Assistant activity gaps."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_NOTIFY_ENTITY,
    CONF_REPORT_TIME,
    DEFAULT_REPORT_TIME,
    DOMAIN,
    HEARTBEAT_SECONDS,
)
from .model import add_gap, empty_state, period_keys, previous_week_key, week_key

_LOGGER = logging.getLogger(__name__)
PLATFORMS = ["sensor"]


class ActivityMonitor:
    """Persist heartbeats and outage statistics for one HA host."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.store = Store(hass, 1, f"{DOMAIN}_{entry.entry_id}")
        self.state: dict = {}
        self.listeners: set = set()
        self._heartbeat_lock = asyncio.Lock()

    @property
    def zone(self) -> ZoneInfo:
        return ZoneInfo(self.hass.config.time_zone)

    @property
    def settings(self) -> dict:
        return {**self.entry.data, **self.entry.options}

    async def async_start(self) -> None:
        now = dt_util.utcnow()
        stored = await self.store.async_load()
        if stored is None:
            self.state = empty_state(now.astimezone(self.zone))
        else:
            self.state = stored
            try:
                last = datetime.fromisoformat(stored["last_seen"])
                if last.tzinfo is None:
                    raise ValueError("naive last_seen")
            except (KeyError, ValueError, TypeError):
                _LOGGER.warning("Stored heartbeat is invalid; starting from the current time")
                last = now
            add_gap(self.state, last, now, self.zone)

        self.state["last_seen"] = now.isoformat()
        await self.store.async_save(self.state)
        await self._send_pending()
        await self._send_weekly_if_due(now)

    async def async_heartbeat(self, _now: datetime | None = None) -> None:
        async with self._heartbeat_lock:
            now = dt_util.utcnow()
            try:
                last = datetime.fromisoformat(self.state["last_seen"])
                add_gap(self.state, last, now, self.zone)
                self.state["last_seen"] = now.isoformat()
                await self.store.async_save(self.state)
                self._notify_listeners()
                await self._send_pending()
                await self._send_weekly_if_due(now)
            except Exception:
                _LOGGER.exception("Power activity heartbeat failed")

    @callback
    def subscribe(self, listener):
        self.listeners.add(listener)

        @callback
        def unsubscribe():
            self.listeners.discard(listener)

        return unsubscribe

    @callback
    def _notify_listeners(self) -> None:
        for listener in self.listeners:
            listener()

    async def _send_message(self, message: str) -> bool:
        target = self.settings.get(CONF_NOTIFY_ENTITY)
        if not target:
            return False
        try:
            await self.hass.services.async_call(
                "notify",
                "send_message",
                {"message": message},
                target={"entity_id": target},
                blocking=True,
            )
        except Exception:
            _LOGGER.exception("Could not send power activity notification to %s", target)
            return False
        return True

    async def _send_pending(self) -> None:
        while self.state["pending_gaps"]:
            pending = self.state["pending_gaps"][0]
            start, end = (datetime.fromisoformat(value) for value in pending)
            duration = (end - start).total_seconds() / 60
            message = (
                "Монитор электропитания: зарегистрирован простой Home Assistant.\n"
                f"Последняя активность: {start.astimezone(self.zone):%d.%m.%Y %H:%M}.\n"
                f"Активность возобновилась: {end.astimezone(self.zone):%d.%m.%Y %H:%M}.\n"
                f"Приблизительная длительность: {duration:.0f} мин."
            )
            if not await self._send_message(message):
                return
            self.state["pending_gaps"].pop(0)
            await self.store.async_save(self.state)

    async def _send_weekly_if_due(self, now: datetime) -> None:
        target = self.settings.get(CONF_NOTIFY_ENTITY)
        if not target:
            return
        local = now.astimezone(self.zone)
        monday = local.date() - timedelta(days=local.weekday())
        configured = self.settings.get(CONF_REPORT_TIME, DEFAULT_REPORT_TIME)
        try:
            report_time = configured if isinstance(configured, time) else time.fromisoformat(configured)
        except (TypeError, ValueError):
            report_time = time(9)
        due = datetime.combine(monday, report_time, self.zone)
        if local < due:
            return
        previous = previous_week_key(local)
        if self.state.get("last_report_week") == previous:
            return
        seconds = self.state["weeks"].get(previous, 0)
        message = (
            f"Монитор электропитания: отчёт за неделю {previous}.\n"
            f"Приблизительное время простоя: {seconds / 3600:.2f} ч.\n"
            f"Отключений, начавшихся за неделю: "
            f"{self.state['week_counts'].get(previous, 0)}."
        )
        if await self._send_message(message):
            self.state["last_report_week"] = previous
            await self.store.async_save(self.state)

    def period_seconds(self, period: str) -> float:
        keys = period_keys(dt_util.utcnow().astimezone(self.zone))
        index = {"weeks": 0, "months": 1, "years": 2}[period]
        return self.state[period].get(keys[index], 0)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    monitor = ActivityMonitor(hass, entry)
    await monitor.async_start()
    entry.runtime_data = monitor
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(
        async_track_time_interval(
            hass, monitor.async_heartbeat, timedelta(seconds=HEARTBEAT_SECONDS)
        )
    )
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
