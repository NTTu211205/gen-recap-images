# Verify bounded scheduling, stable ordering and cleanup without network calls.

import unittest
from threading import Event, Lock

from src.core.concurrency import ordered_parallel_map


class OrderedParallelMapTests(unittest.TestCase):
    def test_overlaps_calls_but_returns_input_order_with_bounded_buffer(self):
        second_done = Event()
        lock = Lock()
        called = []

        def work(value):
            with lock:
                called.append(value)
            if value == 0:
                self.assertTrue(second_done.wait(2))
            if value == 1:
                second_done.set()
            return value

        with ordered_parallel_map(work, range(5), 2) as results:
            self.assertEqual(next(results), 0)
            self.assertEqual(sorted(called), [0, 1])
            self.assertEqual(list(results), [1, 2, 3, 4])

    def test_failure_does_not_schedule_rest_or_retry(self):
        second_done = Event()
        called = []

        def work(value):
            called.append(value)
            if value == 0:
                self.assertTrue(second_done.wait(2))
                raise TimeoutError("upstream")
            second_done.set()
            return value

        with self.assertRaises(TimeoutError):
            with ordered_parallel_map(work, range(10), 2) as results:
                list(results)
        self.assertEqual(sorted(called), [0, 1])

    def test_caller_failure_stops_scheduling(self):
        called = []

        def work(value):
            called.append(value)
            return value

        with self.assertRaises(ValueError):
            with ordered_parallel_map(work, range(10), 2) as results:
                next(results)
                raise ValueError("cutout failed")
        self.assertEqual(called.count(0), 1)
        self.assertTrue(set(called) <= {0, 1})

    def test_serial_mode_stops_immediately_on_failure(self):
        called = []

        def work(value):
            called.append(value)
            raise TimeoutError()

        with self.assertRaises(TimeoutError):
            with ordered_parallel_map(work, range(5), 1) as results:
                list(results)
        self.assertEqual(called, [0])
