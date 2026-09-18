"""A minimal GEECS UDP/TCP client — plays Master Control's side of the protocol.

Deliberately independent of :mod:`picoscope_driver.geecs_server` (it does not
import it) so that using this client against a running
:class:`~picoscope_driver.geecs_server.GeecsDeviceServer` exercises the wire
format end-to-end, not just two halves of the same code agreeing with each
other. Used by the test suite (``tests/test_geecs_server.py``) and by the
``scripts/hardware_protocol_demo.py`` lab demo — anywhere something needs to
talk to this driver the way Master Control does, without pulling in the
server or device code.
"""

from __future__ import annotations

import asyncio
import struct
from typing import Any

from . import wire


class GeecsCommandError(RuntimeError):
    """Raised when a get/set command is rejected or fails on the device."""


class GeecsClient:
    """Sends get/set commands and reads ``Wait>>`` subscriptions against a server."""

    def __init__(self, host: str, port: int) -> None:
        self._host = host
        self._port = port
        self._cmd_transport: asyncio.DatagramTransport | None = None
        self._exe_transport: asyncio.DatagramTransport | None = None
        self._cmd_queue: "asyncio.Queue[bytes] | None" = None
        self._exe_queue: "asyncio.Queue[bytes] | None" = None

    async def connect(self) -> None:
        """Bind the command and exe sockets used for every exchange."""
        loop = asyncio.get_running_loop()
        self._cmd_queue = asyncio.Queue()
        self._exe_queue = asyncio.Queue()

        cmd_transport, _ = await loop.create_datagram_endpoint(
            lambda: _QueueProtocol(self._cmd_queue), local_addr=("0.0.0.0", 0)
        )
        cmd_port = cmd_transport.get_extra_info("sockname")[1]
        exe_transport, _ = await loop.create_datagram_endpoint(
            lambda: _QueueProtocol(self._exe_queue), local_addr=("0.0.0.0", cmd_port + 1)
        )
        self._cmd_transport = cmd_transport
        self._exe_transport = exe_transport

    async def close(self) -> None:
        """Release both sockets."""
        if self._cmd_transport is not None:
            self._cmd_transport.close()
        if self._exe_transport is not None:
            self._exe_transport.close()

    async def __aenter__(self) -> "GeecsClient":
        await self.connect()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def get(self, variable: str, timeout: float = 5.0) -> Any:
        """Send ``get{variable}>>`` and return the parsed value."""
        return await self._exchange(f"get{variable}>>", variable, timeout)

    async def set(self, variable: str, value: Any, timeout: float = 5.0) -> Any:
        """Send ``set{variable}>>{value}`` and return the confirmed value."""
        return await self._exchange(f"set{variable}>>{value}", variable, timeout)

    async def _exchange(self, command: str, variable: str, timeout: float) -> Any:
        assert self._cmd_transport is not None, "call connect() first"
        self._cmd_transport.sendto(command.encode("ascii"), (self._host, self._port))

        try:
            ack = await asyncio.wait_for(self._cmd_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            raise GeecsCommandError(f"no ACK from {self._host}:{self._port} for {command!r}")
        if not wire.is_ack(ack.decode("ascii")):
            raise GeecsCommandError(f"unexpected ACK: {ack!r}")

        try:
            exe = await asyncio.wait_for(self._exe_queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            raise GeecsCommandError(f"no exe response for {command!r} within {timeout}s")

        parts = exe.decode("ascii").split(">>")
        if len(parts) != 4:
            raise GeecsCommandError(f"malformed exe reply: {exe!r}")
        _device, echoed_variable, value_text, status = parts
        if echoed_variable != variable:
            raise GeecsCommandError(
                f"exe reply named {echoed_variable!r}, expected {variable!r}"
            )
        if status.startswith("error"):
            raise GeecsCommandError(status)
        return wire.coerce_scalar(value_text)

    async def subscribe(self, variables: list[str]) -> "SubscriptionReader":
        """Open a ``Wait>>`` TCP subscription for *variables*."""
        reader, writer = await asyncio.open_connection(self._host, self._port)
        writer.write(wire.pack_frame("Wait>>" + ",".join(variables)))
        await writer.drain()
        return SubscriptionReader(reader, writer)


class SubscriptionReader:
    """Reads successive pushed frames from an open subscription."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._reader = reader
        self._writer = writer

    async def read_one(self, timeout: float = 5.0) -> str:
        """Read and decode the next pushed message."""
        header = await asyncio.wait_for(
            self._reader.readexactly(wire.FRAME_HEADER_SIZE), timeout=timeout
        )
        length = wire.unpack_frame_header(header)
        payload = await asyncio.wait_for(self._reader.readexactly(length), timeout=timeout)
        return payload.decode("ascii")

    async def close(self) -> None:
        """Close the subscription connection."""
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
