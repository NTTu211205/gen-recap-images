# Bound concurrent I/O while preserving input order and caller-owned cleanup.

from collections import deque
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from itertools import islice
from typing import TypeVar

Input = TypeVar("Input")
Output = TypeVar("Output")


@contextmanager
def ordered_parallel_map(
    function: Callable[[Input], Output], items: Iterable[Input], workers: int,
) -> Iterator[Iterator[Output]]:
    """Keep at most workers pending results; stop scheduling on failure."""
    if not 1 <= workers <= 8:
        raise ValueError("workers must be between 1 and 8")
    if workers == 1:
        yield map(function, items)
        return
    iterator = iter(items)
    executor = ThreadPoolExecutor(max_workers=workers)
    pending = deque()

    def results() -> Iterator[Output]:
        for item in islice(iterator, workers):
            pending.append(executor.submit(function, item))
        while pending:
            yield pending.popleft().result()
            for item in islice(iterator, 1):
                pending.append(executor.submit(function, item))

    try:
        yield results()
    finally:
        # Running HTTP calls finish within their configured timeout.
        executor.shutdown(wait=True, cancel_futures=True)
