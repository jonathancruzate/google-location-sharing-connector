#!/usr/bin/env python3
"""Minimal local CONNECT forwarder.

Listens on 127.0.0.1:18080 and tunnels to the VM egress proxy, whose
hostname Chromium's resolver cannot handle from this sandbox. The
upstream connection is made by this process (system resolver, env
proxy address), so the browser only ever talks to localhost.
"""
import os
import select
import socket
import threading
from urllib.parse import urlparse

LISTEN = ("127.0.0.1", 18080)


def upstream_addr():
    raw = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    parsed = urlparse(raw)
    return (socket.gethostbyname(parsed.hostname), parsed.port or 3128)


UPSTREAM = upstream_addr()


def relay(a, b):
    try:
        while True:
            ready, _, _ = select.select([a, b], [], [], 60)
            if not ready:
                break
            for src in ready:
                data = src.recv(65536)
                if not data:
                    return
                (b if src is a else a).sendall(data)
    except OSError:
        pass
    finally:
        for sock in (a, b):
            try:
                sock.close()
            except OSError:
                pass


def handle(client):
    try:
        client.settimeout(30)
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = client.recv(4096)
            if not chunk:
                client.close()
                return
            buf += chunk
        head, _, rest = buf.partition(b"\r\n\r\n")
        first = head.split(b"\r\n")[0].decode(errors="replace")
        if not first.upper().startswith("CONNECT"):
            client.sendall(b"HTTP/1.1 405 Only CONNECT supported\r\n\r\n")
            client.close()
            return
        upstream = socket.create_connection(UPSTREAM, timeout=30)
        upstream.sendall(head + b"\r\n\r\n" + rest)
        # Read upstream response head
        ubuf = b""
        while b"\r\n\r\n" not in ubuf:
            chunk = upstream.recv(4096)
            if not chunk:
                client.close()
                upstream.close()
                return
            ubuf += chunk
        uhead, _, urest = ubuf.partition(b"\r\n\r\n")
        client.sendall(uhead + b"\r\n\r\n")
        if urest:
            client.sendall(urest)
        if b" 200 " not in uhead.split(b"\r\n")[0]:
            client.close()
            upstream.close()
            return
        relay(client, upstream)
    except OSError:
        try:
            client.close()
        except OSError:
            pass


def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(LISTEN)
    server.listen(64)
    print(f"local CONNECT forwarder on {LISTEN[0]}:{LISTEN[1]}", flush=True)
    while True:
        client, _ = server.accept()
        threading.Thread(target=handle, args=(client,), daemon=True).start()


if __name__ == "__main__":
    main()
