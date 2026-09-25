# Examples

All examples run from the project root. Install dependencies first:

```bash
pip install -r requirements.txt
```

## 1. `basic_usage.py` — Start & continue a conversation

The minimal flow: create a `Grok` client, send a message, pass `extra_data`
back in to continue the same conversation.

```bash
python examples/basic_usage.py
```

## 2. `advanced_usage.py` — Multi-turn chat loop

A 5-turn conversation with per-turn timing, automatic retries on
anti-bot/heavy-usage errors, and an optional proxy (edit `PROXY`).

```bash
python examples/advanced_usage.py
```

## 3. `api_client.py` — Use the FastAPI server

Starts `api_server.py` for you (or reuses one that's already running),
then hits `/ask` twice to show conversation continuity over HTTP.

```bash
python examples/api_client.py
```

### Notes

- `extra_data` carries cookies, keys and conversation IDs between calls —
  keep it if you want chat context, drop it to start fresh.
- If Grok flags your IP (`rejected by anti-bot rules`), set a proxy
  (formats: `http://ip:port`, `http://user:pass@ip:port`, or `ip:port`).
- The first run of the day fetches Grok's JS chunks to rebuild signature
  mappings; later runs reuse the cached mappings in `core/mappings/`.
