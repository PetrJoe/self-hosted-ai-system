"""
Full example: multi-turn chat loop with per-turn timing, retries,
and an optional proxy.

Run from the project root:
    python examples/advanced_usage.py
"""

from time import time

from core import Grok, Log

PROXY = None  # e.g. "http://user:pass@ip:port"

grok = Grok("grok-3-auto", proxy=PROXY, max_retries=3)
extra_data = None  # None starts a new conversation

for turn in range(1, 6):
    message = f"Turn {turn}: In one short sentence, tell me a fun fact about number {turn}."
    Log.Info(f"USER: {message}")

    start = time()
    result = grok.start_convo(message, extra_data=extra_data)
    elapsed = time() - start

    if "error" in result:
        Log.Error(f"Request failed: {result['error']}")
        break

    Log.Info(f"GROK ({elapsed:.2f}s): {result['response']}")

    # Carry the conversation forward.
    extra_data = result["extra_data"]

Log.Success("Done.")
