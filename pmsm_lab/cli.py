"""Terminal entry point, with optional opening of the local browser UI."""
from __future__ import annotations

import argparse
import threading
import time
import webbrowser


def port_number(text: str) -> int:
    try:
        port = int(text)
    except ValueError as error:
        raise argparse.ArgumentTypeError('Порт должен быть целым числом от 1 до 65535.') from error
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError('Порт должен быть от 1 до 65535.')
    return port


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='PMSM Drive Lab — локальная модель двигателя с FOC')
    parser.add_argument('--host', default='127.0.0.1', help='Адрес сервера (по умолчанию: только этот компьютер)')
    parser.add_argument('--port', default=8000, type=port_number, help='Порт интерфейса (по умолчанию: 8000)')
    parser.add_argument('--no-browser', action='store_true', help='Не открывать браузер автоматически')
    return parser


def main() -> None:
    args = build_parser().parse_args()
    import uvicorn

    host = '127.0.0.1' if args.host in ('0.0.0.0', '::') else args.host
    if ':' in host:
        host = f'[{host}]'
    url = f'http://{host}:{args.port}'
    server = uvicorn.Server(uvicorn.Config('pmsm_lab.app:app', host=args.host, port=args.port))
    stop = threading.Event()

    def on_ready():
        deadline = time.monotonic() + 60
        while not stop.wait(.1):
            if server.started:
                print(f'\nPMSM Drive Lab: {url}\nОстановка — Ctrl+C в этом терминале.\n', flush=True)
                if not args.no_browser:
                    try:
                        opened = webbrowser.open(url, new=2)
                    except webbrowser.Error:
                        opened = False
                    if not opened:
                        print(f'Откройте браузер и перейдите по адресу {url}', flush=True)
                return
            if server.should_exit or time.monotonic() >= deadline:
                return

    threading.Thread(target=on_ready, daemon=True).start()
    try:
        server.run()
    finally:
        stop.set()
