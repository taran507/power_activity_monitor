"""Sensors exposed by the power activity monitor."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfTime
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

DESCRIPTIONS = (
    SensorEntityDescription(
        key="current_week",
        translation_key="current_week",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="current_month",
        translation_key="current_month",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="current_year",
        translation_key="current_year",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="all_time",
        translation_key="all_time",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SensorEntityDescription(
        key="last_activity",
        translation_key="last_activity",
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    SensorEntityDescription(
        key="last_gap",
        translation_key="last_gap",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        key="outage_count",
        translation_key="outage_count",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
)


async def async_setup_entry(hass, entry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities(
        PowerActivitySensor(entry.runtime_data, description) for description in DESCRIPTIONS
    )


class PowerActivitySensor(SensorEntity):
    """One statistic for the host activity monitor."""

    _attr_has_entity_name = True
    _attr_suggested_display_precision = 3

    def __init__(self, monitor, description: SensorEntityDescription) -> None:
        self.monitor = monitor
        self.entity_description = description
        self._attr_unique_id = f"{monitor.entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, "host_power_activity")},
            name="Монитор электропитания",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.monitor.subscribe(self._update))

    @callback
    def _update(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self):
        state = self.monitor.state
        key = self.entity_description.key
        if key == "last_activity":
            return datetime.fromisoformat(state["last_seen"])
        if key == "outage_count":
            return state["outage_count"]
        if key == "last_gap":
            seconds = state.get("last_gap_seconds")
            return None if seconds is None else round(seconds / 3600, 3)
        if key == "all_time":
            return round(state["total_seconds"] / 3600, 3)
        period = {
            "current_week": "weeks",
            "current_month": "months",
            "current_year": "years",
        }[key]
        return round(self.monitor.period_seconds(period) / 3600, 3)
