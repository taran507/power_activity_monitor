"""Checks for manual corrections to the current downtime periods."""

from datetime import datetime
import importlib.util
from pathlib import Path
import unittest
from zoneinfo import ZoneInfo


MODEL_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "power_activity_monitor"
    / "model.py"
)
spec = importlib.util.spec_from_file_location("power_activity_model_adjustment", MODEL_PATH)
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)


class AdjustTimeTests(unittest.TestCase):
    def setUp(self):
        self.zone = ZoneInfo("UTC")
        self.now = datetime(2026, 10, 22, 12, tzinfo=self.zone)
        self.state = model.empty_state(self.now)

    def test_add_then_subtract_updates_current_periods_and_total(self):
        model.adjust_time(self.state, self.now, self.zone, 5400)
        model.adjust_time(self.state, self.now, self.zone, -1800)

        self.assertEqual(self.state["total_seconds"], 3600)
        for bucket, key in zip(("weeks", "months", "years"), model.period_keys(self.now)):
            self.assertEqual(self.state[bucket][key], 3600)
        self.assertEqual(self.state["outage_count"], 0)
        self.assertIsNone(self.state["last_gap_seconds"])
        self.assertEqual(self.state["pending_gaps"], [])

    def test_excessive_subtraction_changes_nothing(self):
        self.state["total_seconds"] = 7200
        before = {bucket: values.copy() for bucket, values in self.state.items() if isinstance(values, dict)}

        with self.assertRaises(ValueError):
            model.adjust_time(self.state, self.now, self.zone, -3600)

        self.assertEqual(self.state["total_seconds"], 7200)
        for bucket, values in before.items():
            self.assertEqual(self.state[bucket], values)

    def test_adjustment_uses_current_calendar_keys(self):
        previous = datetime(2026, 12, 31, 23, tzinfo=self.zone)
        current = datetime(2027, 1, 1, 1, tzinfo=self.zone)
        model.adjust_time(self.state, previous, self.zone, 3600)
        model.adjust_time(self.state, current, self.zone, 1800)

        self.assertEqual(self.state["years"], {"2026": 3600, "2027": 1800})
        self.assertEqual(self.state["total_seconds"], 5400)

    def test_non_finite_or_zero_adjustment_is_rejected(self):
        for seconds in (0, float("nan"), float("inf")):
            with self.subTest(seconds=seconds), self.assertRaises(ValueError):
                model.adjust_time(self.state, self.now, self.zone, seconds)


if __name__ == "__main__":
    unittest.main()
