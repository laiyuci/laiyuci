import argparse
import json
import ssl
import sys
import time
import threading
from typing import Any, Dict

import certifi
from websocket import create_connection, WebSocketTimeoutException


BASE_URL = "wss://twcg-stage.hg66sdt65nfx64.com/api/websocket?token="
DEFAULT_TOKENS_FILE = "tokens.txt"


def build_sslopt(insecure: bool) -> Dict[str, Any]:
    if insecure:
        return {"cert_reqs": ssl.CERT_NONE}
    return {"cert_reqs": ssl.CERT_REQUIRED, "ca_certs": certifi.where()}


def connection_worker(name: str, url: str, payload: Dict[str, Any], interval: float, count: int, insecure: bool, timeout: int) -> None:
    sent = 0
    while True:
        try:
            ws = create_connection(url, timeout=timeout, sslopt=build_sslopt(insecure))
            print(f"[{name}] connected")
            try:
                try:
                    ws.settimeout(1.0)
                except Exception:
                    pass

                while True:
                    try:
                        ws.send(json.dumps(payload))
                        sent += 1
                        print(f"[{name}] sent {sent}: {payload}")
                    except Exception as send_err:
                        print(f"[{name}] send error: {send_err}")
                        break

                    # Drain incoming messages quickly
                    while True:
                        try:
                            message = ws.recv()
                            print(f"[{name}] recv: {message}")
                        except WebSocketTimeoutException:
                            break
                        except Exception as recv_err:
                            print(f"[{name}] recv error: {recv_err}")
                            break

                    if count and sent >= count:
                        return

                    time.sleep(max(0.0, interval))
            finally:
                try:
                    ws.close()
                finally:
                    print(f"[{name}] closed")
        except KeyboardInterrupt:
            return
        except Exception as conn_err:
            print(f"[{name}] connect error: {conn_err}")
            time.sleep(2.0)


def main() -> None:
    parser = argparse.ArgumentParser(description="WebSocket sender (fixed base URL, tokens from file)")
    parser.add_argument(
        "--tokens-file",
        default=DEFAULT_TOKENS_FILE,
        help="Path to file with tokens (value after token=), one per line",
    )
    parser.add_argument(
        "--message",
        default=json.dumps({
            "type": "send_public_message",
            "data": {"message_type": 1, "content": ""}
        }),
        help="JSON string to send",
    )
    parser.add_argument("--timeout", type=int, default=15, help="Connect timeout seconds")
    parser.add_argument("--interval", type=float, default=5.0, help="Seconds between messages")
    parser.add_argument("--count", type=int, default=0, help="Times to send per connection (0=infinite)")
    parser.add_argument("--insecure", action="store_true", help="Disable TLS verification (testing only)")
    args = parser.parse_args()

    try:
        payload = json.loads(args.message)
    except json.JSONDecodeError as e:
        print(f"[arg error] --message must be valid JSON: {e}")
        sys.exit(2)

    # Load tokens
    try:
        with open(args.tokens_file, "r", encoding="utf-8") as f:
            tokens = [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"[arg error] failed to read --tokens-file: {e}")
        sys.exit(2)

    if not tokens:
        print("[arg error] tokens file is empty")
        sys.exit(2)

    # Build URLs from fixed base
    urls = [BASE_URL + t for t in tokens]

    # Start threads
    threads: list[threading.Thread] = []
    for idx, u in enumerate(urls, start=1):
        name = f"conn-{idx}"
        th = threading.Thread(
            target=connection_worker,
            args=(name, u, payload, args.interval, args.count, args.insecure, args.timeout),
            daemon=True,
        )
        th.start()
        threads.append(th)

    try:
        if args.count:
            for th in threads:
                th.join()
        else:
            while True:
                time.sleep(1.0)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()


