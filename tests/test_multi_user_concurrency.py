"""
Unit & Concurrency Tests for Multi-User Pipeline Locking (run_lock.py)
"""
import os
import json
import time
import threading
import unittest
from pathlib import Path

from run_lock import PipelineLock, LOCK_FILE


class TestMultiUserConcurrency(unittest.TestCase):
    def setUp(self):
        PipelineLock.force_unlock()

    def tearDown(self):
        PipelineLock.force_unlock()

    def test_single_thread_acquire_and_release(self):
        lock = PipelineLock(source="test", topic="Test Topic")
        acquired, reason = lock.acquire()
        self.assertTrue(acquired)
        self.assertIsNone(reason)
        self.assertTrue(LOCK_FILE.exists())

        lock.release()
        self.assertFalse(LOCK_FILE.exists())

    def test_reentrancy_same_thread(self):
        # Same thread acquiring twice should succeed (re-entrant)
        lock1 = PipelineLock(source="dashboard", topic="First")
        acq1, _ = lock1.acquire()
        self.assertTrue(acq1)

        lock2 = PipelineLock(source="pipeline", topic="First")
        acq2, _ = lock2.acquire()
        self.assertTrue(acq2)

        lock1.release()

    def test_multi_user_concurrent_rejection(self):
        # Simulates User A and User B clicking Generate at the same time in Streamlit
        lock_a = PipelineLock(source="user_a", topic="Topic A")
        acquired_a, _ = lock_a.acquire()
        self.assertTrue(acquired_a)

        results = []

        def _user_b_worker():
            lock_b = PipelineLock(source="user_b", topic="Topic B")
            acq_b, reason = lock_b.acquire()
            results.append((acq_b, reason))

        t = threading.Thread(target=_user_b_worker)
        t.start()
        t.join()

        self.assertEqual(len(results), 1)
        acq_b, reason_b = results[0]
        self.assertFalse(acq_b)
        self.assertIn("Generation already in progress", reason_b)

        # Release User A, then User B should be able to acquire
        lock_a.release()

        results_retry = []
        def _user_b_retry():
            lock_b2 = PipelineLock(source="user_b", topic="Topic B")
            acq_b2, reason2 = lock_b2.acquire()
            results_retry.append((acq_b2, reason2))
            lock_b2.release()

        t2 = threading.Thread(target=_user_b_retry)
        t2.start()
        t2.join()

        self.assertEqual(len(results_retry), 1)
        self.assertTrue(results_retry[0][0])

    def test_pipeline_lock_decorator_mutual_exclusion(self):
        from pipeline import with_pipeline_lock

        executed = []

        @with_pipeline_lock
        def dummy_pipeline_task(topic, duration=0.1):
            time.sleep(duration)
            executed.append(topic)
            return f"done: {topic}"

        # Thread 1 starts dummy pipeline
        thread_started = threading.Event()
        thread_finished = threading.Event()

        def _worker_1():
            thread_started.set()
            dummy_pipeline_task("Worker Topic 1", duration=0.2)
            thread_finished.set()

        t1 = threading.Thread(target=_worker_1)
        t1.start()
        thread_started.wait()
        time.sleep(0.05)  # Ensure t1 acquired lock

        # Thread 2 tries to run while Thread 1 is holding the lock
        collision_detected = False
        try:
            dummy_pipeline_task("Worker Topic 2")
        except RuntimeError as e:
            if "Pipeline execution blocked" in str(e):
                collision_detected = True

        self.assertTrue(collision_detected, "Thread 2 should have been blocked by Thread 1's lock")

        t1.join()
        thread_finished.wait()

        # After Thread 1 finishes, Thread 2 should succeed
        res = dummy_pipeline_task("Worker Topic 2 Post", duration=0.01)
        self.assertEqual(res, "done: Worker Topic 2 Post")

    def test_sqlite_concurrent_access_stress(self):
        """Stress tests SQLite WAL mode and busy_timeout across 10 concurrent threads."""
        from data.asset_ledger import record_asset, generate_description_credits, clear_ledger_for_video
        from data.negative_ledger import get_negative_ledger

        clear_ledger_for_video("test_concurrent")
        neg_ledger = get_negative_ledger()
        errors = []

        def _db_worker(thread_num):
            try:
                for i in range(10):
                    record_asset(
                        video_id="test_concurrent",
                        beat_id=i,
                        asset_path=f"assets/{thread_num}_{i}.jpg",
                        tier="TIER_A",
                        license_name="Unsplash",
                        credit_text=f"Photo by Creator {thread_num}"
                    )
                    neg_ledger.ban_url(f"https://badsite-{thread_num}-{i}.com", f"Corrupt image {thread_num}")
                    _ = neg_ledger.is_url_banned(f"https://badsite-{thread_num}-{i}.com")
                    _ = generate_description_credits("test_concurrent")
            except Exception as ex:
                errors.append(ex)

        threads = [threading.Thread(target=_db_worker, args=(t,)) for t in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"SQLite concurrency produced errors: {errors}")


if __name__ == '__main__':
    unittest.main()