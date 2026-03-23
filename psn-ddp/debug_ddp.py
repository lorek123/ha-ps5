"""Minimal DDP debug script — shows exactly what port we bind, what we send, and what we receive."""
from __future__ import annotations

import asyncio
import socket
import sys

DDP_PORT = 9302
DDP_SRCH_PORT = 987
BROADCAST = "255.255.255.255"

SRCH_PACKET = b"SRCH * HTTP/1.1\ndevice-discovery-protocol-version:00030010\n\n"


async def debug_discover(target: str = BROADCAST, src_port: int = DDP_SRCH_PORT, timeout: float = 3.0) -> None:
    loop = asyncio.get_event_loop()

    received: list[tuple[bytes, tuple]] = []

    class DebugProtocol(asyncio.DatagramProtocol):
        def connection_made(self, transport):
            sock: socket.socket = transport.get_extra_info("socket")
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            bound = sock.getsockname()
            print(f"[+] Socket bound to {bound[0]}:{bound[1]}")
            print(f"[+] Sending SRCH to {target}:{DDP_PORT}")
            transport.sendto(SRCH_PACKET, (target, DDP_PORT))
            print(f"[+] Sent {len(SRCH_PACKET)} bytes: {SRCH_PACKET!r}")

        def datagram_received(self, data, addr):
            print(f"[+] Response from {addr}: {data!r}")
            received.append((data, addr))

        def error_received(self, exc):
            print(f"[!] Socket error: {exc}")

        def connection_lost(self, exc):
            pass

    transport, _ = await loop.create_datagram_endpoint(
        DebugProtocol,
        local_addr=("0.0.0.0", src_port),
        family=socket.AF_INET,
    )
    print(f"[+] Waiting {timeout}s for responses…")
    await asyncio.sleep(timeout)
    transport.close()

    if not received:
        print("[-] No responses received.")
    else:
        print(f"[+] {len(received)} response(s) received.")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else BROADCAST
    src_port = int(sys.argv[2]) if len(sys.argv) > 2 else DDP_SRCH_PORT
    print(f"Target: {target}, src_port: {src_port}")
    asyncio.run(debug_discover(target, src_port))
