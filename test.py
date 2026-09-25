import sys
import requests

if len(sys.argv) < 2:
    print('Usage: python3 test.py "http://user:pass@host:port"')
    sys.exit(1)

response = requests.post(
    "http://localhost:6969/ask",
    json={
        "proxy": sys.argv[1],
        "message": "Hello, Grok!",
        "model": "grok-3-fast",
        "extra_data": None
    }
)
print(response.json())
