"""Run ONE tick of scheduler.task_archiver against the live server.

The real archiver loop sleeps `interval` at the TOP of each iteration and
sleep(0) between archive batches. A naive side_effect mock (one CancelledError)
gets consumed by the batch sleep(0) — this harness only cancels on the SECOND
top-of-loop sleep, letting a full tick (all batches) complete.

Usage: python3 run_archiver_tick.py
"""

import asyncio
import contextlib
from unittest.mock import patch

import scheduler

_loop_sleeps = 0


async def fake_sleep(interval: float):
    global _loop_sleeps
    if interval == 0:
        return None  # inter-batch yield — never cancel here
    _loop_sleeps += 1
    if _loop_sleeps > 1:
        raise asyncio.CancelledError()


async def main():
    with (
        patch.object(scheduler.asyncio, "sleep", new=fake_sleep),
        contextlib.suppress(asyncio.CancelledError),
    ):
        await scheduler.task_archiver(1)
    print("archiver tick done")


if __name__ == "__main__":
    asyncio.run(main())
