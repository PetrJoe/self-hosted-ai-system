"""
API server example: spins up the FastAPI server (if not already running)
and sends requests to /ask for both new and continued conversations.

Run from the project root:
    python examples/api_client.py
"""

from subprocess import Popen
from sys import executable
from time import sleep

import requests

BASE_URL = "http://127.0.0.1:6969/ask"


def ask(message: str, model: str = "grok-3-auto", extra_data: dict = None, proxy: str = None) -> dict:
    response = requests.post(
        BASE_URL,
        json={
            "proxy": proxy,
            "message": message,
            "model": model,
            "extra_data": extra_data,
        },
        timeout=300,
    )
    response.raise_for_status()
    return response.json()


def main() -> None:
    # Start the server unless something is already listening.
    server = None
    try:
        requests.post(BASE_URL, json={"message": "ping"}, timeout=2)
        print("Server already running.")
    except requests.exceptions.ConnectionError:
        print("Starting api_server.py ...")
        server = Popen([executable, "api_server.py"])

    try:
        # Wait for the server to come up.
        for _ in range(60):
            try:
                requests.post(BASE_URL, json={"message": "ping"}, timeout=2)
                break
            except requests.exceptions.ConnectionError:
                sleep(1)
        else:
            raise RuntimeError("Server did not start in time.")

        # --- New conversation -------------------------------------------
        r1 = ask("Hello, Grok! Who are you in one sentence?")
        print("Grok:", r1.get("response", r1))

        # --- Continue it --------------------------------------------------
        r2 = ask("Summarize what you just said in five words.", extra_data=r1.get("extra_data"))
        print("Grok:", r2.get("response", r2))

    finally:
        if server:
            server.terminate()
            print("Server stopped.")


if __name__ == "__main__":
    main()
