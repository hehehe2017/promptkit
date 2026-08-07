#!/usr/bin/env python3
"""Async prompts: await confirm/select/checkbox from within an asyncio event loop.

The a* variants (aconfirm, aselect, acheckbox) run the same UI as their sync
counterparts but yield to the event loop while waiting for input — so other
coroutines keep making progress instead of blocking on stdin.

To make that visible without corrupting the TUI, the background task here does
NOT print to the terminal (that would tear the prompt's rendering). It just
counts ticks and 'refreshes a quota' in shared state. After the wizard finishes
we print what the background task accomplished while the user was answering.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from promptkit import aconfirm, aselect, acheckbox  # noqa: E402


async def background_worker(state: dict, stop: asyncio.Event) -> None:
    """Silent background work — counts seconds and refreshes a fake quota every 3s.

    Never touches stdout: printing from here would smear ANSI escapes across the
    prompt UI. Everything is stashed in ``state`` and reported after the prompt.
    """
    ticks = 0
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=1.0)
        except asyncio.TimeoutError:
            ticks += 1
            state["ticks"] = ticks
            if ticks % 3 == 0:
                state["quota"] = 1000 - ticks * 10


async def wizard() -> tuple[str, list[str], bool]:
    env = await aselect(
        message="Deploy to which environment?",
        choices=["staging", "production"],
        border=True,
    )

    features = await acheckbox(
        message="Enable which features?",
        choices=["metrics", "tracing", "cache", "beta-ui"],
        default=["metrics"],
        border=True,
    )

    go = await aconfirm(
        message=f"Deploy to {env} with {len(features)} feature(s)?",
        default=False,
    )
    return env, features, go


async def main() -> None:
    state: dict = {"ticks": 0, "quota": None}
    stop = asyncio.Event()
    bg = asyncio.create_task(background_worker(state, stop))
    try:
        env, features, go = await wizard()
    finally:
        stop.set()
        await bg

    print(f"\nenv={env}  features={features}  confirmed={go}")
    print(
        f"While you were answering, the background task ran for "
        f"{state['ticks']}s and last-refreshed quota = {state['quota']}."
    )


if __name__ == "__main__":
    asyncio.run(main())
