"""A minimal GEECS UDP/TCP client, for testing our server implementation.

This plays Master Control's side of the protocol described in
``picoscope_driver.wire`` — deliberately independent of
``picoscope_driver.geecs_server`` so the tests exercise the wire format, not
just two halves of the same code agreeing with each other.
"""

from __future__ import annotations

import asyncio
import struct
from typing import Any

from picoscope_driver import wire


class GeecsTestClient:
    """Sends get/set commands and reads Wait>> subscriptions against a server."""

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._cmd_transport: asyncio.DatagramTransport | None = None
        self._exe_transport: asyncio.DatagramTransport | None = None
        self._cmd_queue: asyncio.Queue[bytes] | None = None
        self._exe_queue: asyncio.Queue[bytes] | None = None

    async def connect(self) -> None:
        loop = asyncio.get_running_loop()
        self._cmd_queue = asyncio.Queue()
        self._exe_queue = asyncio.Queue()

        cmd_transport, _ = await loop.create_datagram_endpoint(
            lambda: _QueueProtocol(self._cmd_queue), local_addr=("127.0.0.1", 0)
        )
        cmd_port = cmd_transport.get_extra_info("sockname")[1]
        exe_transport, _ = await loop.create_datagram_endpoint(
            lambda: _QueueProtocol(self._exe_queue), local_addr=("127.0.0.1", cmd_port + 1)
        )
        self._cmd_transport = cmd_transport
        self._exe_transport = exe_transport

    async def close(self) -> None:
        if self._cmd_transport is not None:
            self._cmd_transport.close()
        if self._exe_transport is not None:
            self._exe_transport.close()

    async def get(self, variable: str, timeout: float = 2.0) -> Any:
        return await self._exchange(f"get{variable}>>", variable, timeout)

    async def set(self, variable: str, value: Any, timeout: float = 2.0) -> Any:
        return await self._exchange(f"set{variable}>>{value}", variable, timeout)

    async def _exchange(self, command: str, variable: str, timeout: float) -> Any:
        assert self._cmd_transport is not None
        self._cmd_transport.sendto(command.encode("ascii"), (self._host, self._port))

        ack = await asyncio.wait_for(self._cmd_queue.get(), timeout=timeout)
        if not wire.is_ack(ack.decode("ascii")):
            raise AssertionError(f"unexpected ACK: {ack!r}")

        exe = await asyncio.wait_for(self._exe_queue.get(), timeout=timeout)
        parts = exe.decode("ascii").split(">>")
        assert len(parts) == 4, f"malformed exe reply: {exe!r}"
        _device, echoed_variable, value_text, status = parts
        assert echoed_variable == variable, (echoed_variable, variable)
        if status.startswith("error"):
            raise AssertionError(status)
        return wire.coerce_scalar(value_text)

    async def subscribe(self, variables: list[str]) -> "SubscriptionReader":
        reader, writer = await asyncio.open_connection(self._host, self._port)
        writer.write(wire.pack_frame("Wait>>" + ",".join(variables)))
        await writer.drain()
        return SubscriptionReader(reader, writer)


class SubscriptionReader:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._reader = reader
        self._writer = writer

    async def read_one(self, timeout: float = 2.0) -> str:
        header = await asyncio.wait_for(self._reader.readexactly(4), timeout=timeout)
        (length,) = struct.unpack(">i", header)
        payload = await asyncio.wait_for(self._reader.readexactly(length), timeout=timeout)
        return payload.decode("ascii")

    async def close(self) -> None:
        self._writer.close()
        try:
            await self._writer.wait_closed()
        except Exception:
            pass


class _QueueProtocol(asyncio.DatagramProtocol):
    def __init__(self, queue: "asyncio.Queue[bytes]") -> None:
        self._queue = queue

    def datagram_received(self, data: bytes, _addr: object) -> None:
        self._queue.put_nowait(data)
