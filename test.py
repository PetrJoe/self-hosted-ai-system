import sys
import requests

# Usage:
#   python3 test.py                      # no proxy, message "Hello, Grok!"
#   python3 test.py "Hi there"           # no proxy, custom message
#   python3 test.py --proxy http://user:pass@host:port
#   python3 test.py "Hi there" --proxy http://user:pass@host:port

args = sys.argv[1:]
proxy = None

if "--proxy" in args:
    i = args.index("--proxy")
    if i + 1 >= len(args):
        print('Usage: python3 test.py [message] [--proxy "http://user:pass@host:port"]')
        sys.exit(1)
    proxy = args[i + 1]
    del args[i:i + 2]

message = args[0] if args else "Hello, Grok!"

payload = {
    "message": message,
    "model": "grok-3-fast",
    "extra_data": None
}
if proxy:
    payload["proxy"] = proxy

response = requests.post("http://localhost:6969/ask", json=payload)
print(response.json())
