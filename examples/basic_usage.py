"""
Basic Grok usage: start a conversation and continue it.

Run from the project root:
    python examples/basic_usage.py
"""

from core import Grok

# --- Start a new conversation -------------------------------------------
# Optional: Grok("grok-3-fast", proxy="http://user:pass@ip:port")
grok = Grok()  # defaults to the "grok-3-auto" model

result = grok.start_convo("Hello, how are you today?")

print("Grok:", result["response"])
print("Images:", result["images"])

# --- Continue the same conversation --------------------------------------
# Pass extra_data back in to keep the chat context.
result2 = grok.start_convo(
    "That's nice! Glad to hear! What can you help me with?",
    extra_data=result["extra_data"],
)
print("Grok:", result2["response"])

# --- Streaming tokens ------------------------------------------------------
# result["stream_response"] holds the token-by-token stream as a list:
for token in result2["stream_response"]:
    print(token, end="", flush=True)
print()
