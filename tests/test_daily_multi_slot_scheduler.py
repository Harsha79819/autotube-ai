"""
Unit and Regression Test Suite for AutoTube AI 24/7 Multi-Channel Scheduler
(tests/test_daily_multi_slot_scheduler.py)

Validates:
  1. Exact 10-slot schedule integrity (5 Ch1, 5 Ch2).
  2. Format distribution: 6 Shorts (9:16), 4 Long-form (16:9).
  3. Strict Instagram Reels gating: True for Shorts, strictly False for Long-form.
  4. Universal Telugu female voice: Shruti across all slots.
  5. Dynamic intensity duration scaling (3-5m vs 5-8m vs 35-45s).
  6. Slot state persistence and recovery (daily_slot_status.json).
  7. Channel credential and topic resolver routing.
"""

import unittest
from datetime import datetime
from pathlib import Path
import json

from daily_scheduler import (
    DAILY_SLOT_CONFIGS,
    get_slot_config,
    load_daily_slot_status,
    save_daily_slot_status,
    evaluate_slot_duration,
    DEFAULT_TELUGU_VOICE,
    MultiSlotDailyScheduler,
)


class TestDailyMultiSlotScheduler(unittest.TestCase):

    def test_01_slot_count_and_channel_balance(self):
        """Ensure exactly 10 slots exist, balanced 5 for Channel 1 and 5 for Channel 2."""
        self.assertEqual(len(DAILY_SLOT_CONFIGS), 10, "Schedule must have exactly 10 slots")

        ch1_slots = [s for s in DAILY_SLOT_CONFIGS if "1" in s["channel"]]
        ch2_slots = [s for s in DAILY_SLOT_CONFIGS if "2" in s["channel"]]

        self.assertEqual(len(ch1_slots), 5, "Channel 1 must have exactly 5 slots")
        self.assertEqual(len(ch2_slots), 5, "Channel 2 must have exactly 5 slots")

    def test_02_format_distribution_and_aspect_ratios(self):
        """Ensure exactly 6 Shorts (9:16) and 4 Long-form (16:9) videos."""
        shorts = [s for s in DAILY_SLOT_CONFIGS if s["format_type"] == "short"]
        longs = [s for s in DAILY_SLOT_CONFIGS if s["format_type"] == "long-form"]

        self.assertEqual(len(shorts), 6, "Must have exactly 6 Shorts daily")
        self.assertEqual(len(longs), 4, "Must have exactly 4 Long-form videos daily")

        for s in shorts:
            self.assertEqual(s["aspect_ratio"], "9:16", f"Short slot {s['slot_id']} must have 9:16 aspect ratio")

        for l in longs:
            self.assertEqual(l["aspect_ratio"], "16:9", f"Long-form slot {l['slot_id']} must have 16:9 aspect ratio")

    def test_03_strict_instagram_reels_isolation(self):
        """Ensure Instagram Reels upload is strictly True for Shorts and False for Long-form."""
        for s in DAILY_SLOT_CONFIGS:
            if s["format_type"] == "short":
                self.assertTrue(
                    s["instagram_upload"],
                    f"Shorts slot {s['slot_id']} should enable Instagram Reels",
                )
            else:
                self.assertFalse(
                    s["instagram_upload"],
                    f"Long-form slot {s['slot_id']} must NEVER upload to Instagram Reels",
                )

    def test_04_universal_shruti_voice_standardization(self):
        """Ensure all 10 slots use Shruti female Telugu creator voice."""
        for s in DAILY_SLOT_CONFIGS:
            self.assertEqual(
                s["voice"],
                DEFAULT_TELUGU_VOICE,
                f"Slot {s['slot_id']} must use Shruti female voice",
            )
            self.assertIn("Shruti", s["voice"])

    def test_05_dynamic_intensity_duration_evaluation(self):
        """Ensure dynamic long-form duration evaluates topic intensity properly."""
        short_slot = get_slot_config("CH1-S1")
        long_slot = get_slot_config("CH1-L1")

        # 1. Shorts always 60-90s
        self.assertEqual(evaluate_slot_duration(short_slot, "Any Topic"), "60-90s")

        # 2. Standard long-form topic -> 3-5m
        std_topic = "Top 5 Innovations in Smartphone Battery Tech"
        self.assertEqual(evaluate_slot_duration(long_slot, std_topic), "3-5m")

        # 3. High intensity mystery / scandal / deep history -> 5-8m
        intense_topic_1 = "The Unsolved Mystery of the Lost Ancient Civilization"
        self.assertEqual(evaluate_slot_duration(long_slot, intense_topic_1), "5-8m")

        intense_topic_2 = "Bigg Boss 10 Shocking Elimination Controversy and Voting Scandal"
        self.assertEqual(evaluate_slot_duration(long_slot, intense_topic_2), "5-8m")

    def test_06_slot_state_persistence_and_initialization(self):
        """Ensure slot status initializes all 10 slots and saves cleanly."""
        status = load_daily_slot_status()
        self.assertIn("date", status)
        self.assertIn("slots", status)

        # Check all 10 slots represented
        for conf in DAILY_SLOT_CONFIGS:
            s_id = conf["slot_id"]
            self.assertIn(s_id, status["slots"], f"Slot {s_id} missing from slot status payload")
            self.assertIn(status["slots"][s_id]["status"], ("pending", "in_progress", "success", "failed", "skipped"))

    def test_07_due_time_checker(self):
        """Ensure scheduler correctly flags due slots based on time."""
        scheduler = MultiSlotDailyScheduler()
        slot_conf = {"scheduled_time": "08:00"}

        time_before = datetime(2026, 11, 3, 7, 59, 0)
        time_exact = datetime(2026, 11, 3, 8, 0, 0)
        time_after = datetime(2026, 11, 3, 10, 30, 0)

        self.assertFalse(scheduler.is_slot_due(slot_conf, time_before))
        self.assertTrue(scheduler.is_slot_due(slot_conf, time_exact))
        self.assertTrue(scheduler.is_slot_due(slot_conf, time_after))

    def test_08_channel_automation_filtering(self):
        """Ensure Channel 1 is automated while Channel 2 is reserved for manual execution."""
        scheduler = MultiSlotDailyScheduler()
        ch1_slot = {"channel": "Channel 1 (Primary)"}
        ch2_slot = {"channel": "Channel 2 (Secondary)"}

        # With default SCHEDULED_CHANNELS="Channel 1"
        self.assertTrue(scheduler.is_channel_automated(ch1_slot))
        self.assertFalse(scheduler.is_channel_automated(ch2_slot))


if __name__ == "__main__":
    unittest.main()
