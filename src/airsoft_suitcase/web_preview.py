import contextlib
import functools
import http.server
import os
import socket
import socketserver
import webbrowser

from .game_utils import PROJECT_ROOT, is_truthy

WEB_ROOT = PROJECT_ROOT / "web"


def _find_open_port(preferred_port: int) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", preferred_port))
            return preferred_port
        except OSError:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, _format: str, *_args: object) -> None:
        return


def main() -> None:
    preferred_port = int(os.getenv("AIRSOFT_WEB_PORT", "4311"))
    port = _find_open_port(preferred_port)

    handler = functools.partial(QuietHandler, directory=str(WEB_ROOT))
    with socketserver.TCPServer(("127.0.0.1", port), handler) as server:
        url = f"http://127.0.0.1:{port}/"
        print(f"[WEB] Serving Raspberry Pi UI preview at {url}")
        print("[WEB] Press Ctrl+C to stop")

        if not is_truthy(os.getenv("AIRSOFT_NO_BROWSER")):
            with contextlib.suppress(Exception):
                webbrowser.open(url)

        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\n[WEB] Stopped")


if __name__ == "__main__":
    main()
