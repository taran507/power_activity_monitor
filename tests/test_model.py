"""Focused accounting checks for manual outage corrections."""

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
spec = importlib.util.spec_from_file_location("power_activity_model", MODEL_PATH)
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)


class ManualIntervalTests(unittest.TestCase):
    def setUp(self):
        self.zone = ZoneInfo("UTC")
        self.data = model.empty_state(datetime(2026, 10, 22, tzinfo=self.zone))

    def test_add_and_remove_across_week_and_month(self):
        start = datetime(2026, 8, 31, 23, 30, tzinfo=self.zone)
        end = datetime(2026, 9, 1, 0, 30, tzinfo=self.zone)

        self.assertTrue(model.add_gap(self.data, start, end, self.zone, manual=True))
        self.assertEqual(self.data["total_seconds"], 3600)
        self.assertEqual(self.data["outage_count"], 1)
        self.assertEqual(self.data["months"], {"2026-08": 1800, "2026-09": 1800})
        self.assertEqual(self.data["week_counts"], {"2026-W36": 1})
        self.assertEqual(self.data["pending_gaps"], [])

        self.assertTrue(model.remove_gap(self.data, self.data["gaps"][0]["id"], self.zone))
        self.assertEqual(self.data["total_seconds"], 0)
        self.assertEqual(self.data["outage_count"], 0)
        self.assertEqual(self.data["months"], {})
        self.assertEqual(self.data["weeks"], {})
        self.assertEqual(self.data["week_counts"], {})

    def test_overlap_is_rejected_without_changing_totals(self):
        start = datetime(2026, 10, 20, 12, tzinfo=self.zone)
        end = datetime(2026, 10, 20, 13, tzinfo=self.zone)
        self.assertTrue(model.add_gap(self.data, start, end, self.zone, manual=True))

        self.assertFalse(
            model.add_gap(
                self.data,
                datetime(2026, 10, 20, 12, 30, tzinfo=self.zone),
                datetime(2026, 10, 20, 13, 30, tzinfo=self.zone),
                self.zone,
                manual=True,
            )
        )
        self.assertEqual(self.data["total_seconds"], 3600)
        self.assertEqual(len(self.data["gaps"]), 1)

    def test_automatic_gap_keeps_pending_notification_until_excluded(self):
        start = datetime(2026, 10, 20, 12, tzinfo=self.zone)
        end = datetime(2026, 10, 20, 13, tzinfo=self.zone)
        self.assertTrue(model.add_gap(self.data, start, end, self.zone))
        self.assertEqual(self.data["pending_gaps"], [[start.isoformat(), end.isoformat()]])

        self.assertTrue(model.remove_gap(self.data, self.data["gaps"][0]["id"], self.zone))
        self.assertEqual(self.data["pending_gaps"], [])

    def test_legacy_totals_survive_removal_of_new_interval(self):
        self.data["total_seconds"] = 7200
        self.data["outage_count"] = 2
        self.data["last_gap_seconds"] = 3600
        self.data["legacy_last_gap_seconds"] = 3600
        self.data["legacy_last_seen"] = "2026-10-20T10:00:00+00:00"
        start = datetime(2026, 10, 21, 12, tzinfo=self.zone)
        end = datetime(2026, 10, 21, 12, 30, tzinfo=self.zone)

        self.assertTrue(model.add_gap(self.data, start, end, self.zone, manual=True))
        self.assertEqual(self.data["last_gap_seconds"], 1800)
        self.assertTrue(model.remove_gap(self.data, self.data["gaps"][0]["id"], self.zone))
        self.assertEqual(self.data["total_seconds"], 7200)
        self.assertEqual(self.data["outage_count"], 2)
        self.assertEqual(self.data["last_gap_seconds"], 3600)

    def test_daylight_saving_interval_uses_elapsed_time(self):
        zone = ZoneInfo("Europe/Berlin")
        start = datetime(2026, 10, 25, 1, 30, tzinfo=zone)
        end = datetime(2026, 10, 25, 3, 30, tzinfo=zone)

        self.assertTrue(model.add_gap(self.data, start, end, zone, manual=True))
        self.assertEqual(self.data["total_seconds"], 10800)
        self.assertEqual(self.data["last_gap_seconds"], 10800)


if __name__ == "__main__":
    unittest.main()
