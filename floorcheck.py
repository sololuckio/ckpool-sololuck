#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read a port's difficulty floor from the pool itself. Python 3 stdlib only.

    python3 floorcheck.py stratum.sololuck.io 3335 <your-bitcoin-address>
    python3 floorcheck.py stratum.sololuck.io 3333 <your-bitcoin-address>
    python3 floorcheck.py stratum.sololuck.io 3334 <your-bitcoin-address> --tls
    python3 floorcheck.py stratum.sololuck.io 4334 <your-bitcoin-address>

WHY IT ASKS TWICE
    A bare subscribe tells you nothing about the floor: every port starts a
    connection at the pool's start difficulty (4000 on sololuck.io) unless the
    port's floor is higher. The floor only shows when a miner asks for LESS.
    And patch 0001 remembers the floor as the connection's suggested
    difficulty, so asking straight for 1 on a port whose floor is 1024 changes
    nothing and the pool sends nothing back.

    So this asks for 2048 first (above the Nano and Bitaxe floors), then for 1.
    The difficulty the pool sets after the second request is the floor:
        3335 -> 1          3333, 3334 -> 1,024
        4334 -> no change: the connection is already held at 1,048,576

WHAT IT DOES TO YOUR ACCOUNT
    It connects as a miner would and authorises as <address>.floorcheck, so a
    worker called "floorcheck" shows up on your own stats page. It submits no
    shares and disconnects after about fifteen seconds.
"""
import json
import socket
import ssl
import sys
import time


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 3:
        print(__doc__)
        return 2
    host, port, addr = args[0], int(args[1]), args[2]
    sock = socket.create_connection((host, port), timeout=15)
    if "--tls" in sys.argv:
        sock = ssl.create_default_context().wrap_socket(sock, server_hostname=host)
    sock.settimeout(0.25)
    buf = b""
    seen = []

    def send(obj):
        sock.sendall(json.dumps(obj).encode() + b"\n")

    def pump(seconds, want_id=None):
        nonlocal buf
        end = time.time() + seconds
        reply = None
        while time.time() < end:
            try:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                buf += chunk
            except (socket.timeout, ssl.SSLWantReadError):
                pass
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if msg.get("method") == "mining.set_difficulty":
                    seen.append(msg["params"][0])
                    print("  pool set difficulty %s" % format(msg["params"][0], ","))
                if want_id is not None and msg.get("id") == want_id:
                    reply = msg
            if reply is not None:
                return reply
        return reply

    send({"id": 1, "method": "mining.subscribe", "params": ["floorcheck/1.0"]})
    if not pump(10, want_id=1):
        print("no answer to mining.subscribe")
        return 1
    send({"id": 2, "method": "mining.authorize", "params": [addr + ".floorcheck", "x"]})
    auth = pump(10, want_id=2)
    if not auth or auth.get("result") is not True:
        print("not authorised (%s) -- is %s a valid address for this pool?" % (auth, addr))
        return 1
    pump(2)
    start = seen[-1] if seen else None
    print("  after subscribe + authorise: %s" % (format(start, ",") if start is not None else "no difficulty sent yet"))
    send({"id": 3, "method": "mining.suggest_difficulty", "params": [2048]})
    pump(5)
    before = len(seen)
    send({"id": 4, "method": "mining.suggest_difficulty", "params": [1]})
    pump(5)
    sock.close()
    if len(seen) > before:
        print("floor on port %d: %s" % (port, format(seen[-1], ",")))
    elif seen:
        print("floor on port %d: no change -- the connection is held at %s" % (port, format(seen[-1], ",")))
    else:
        print("the pool sent no difficulty at all")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
