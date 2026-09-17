"""Asyncio server implementing the GEECS Master Control device wire protocol.

This is the Python-native counterpart of a LabVIEW ``BaseDriver.lvclass``
device: it listens on one UDP port and one TCP port (same port number) and
answers Master Control's get/set commands and variable subscriptions. It is
generic over any :class:`VariableStore` — the PicoScope-specific behaviour
lives in :mod:`picoscope_driver.device`, not here, so this module can be
unit-tested and reused independently of the oscilloscope hardware.

See :mod:`picoscope_driver.wire` for the wire-format details.
"""

from __future__ import annotations

import asyncio
import errno
import logging
import struct
from typing import Any, Protocol

from . import wire

logger = logging.getLogger(__name__)

DEFAULT_PUSH_HZ = 5.0


class VariableStore(Protocol):
    """The device-side interface the GEECS protocol server calls into."""

    def try_set(self, variable: str, value: Any) -> str | None:
        """Attempt to set *variable*; return an error detail, or ``None`` on success."""
        ...

    def try_get(self, variable: str) -> tuple[Any, str | None]:
        """Return ``(value, error)`` for *variable*; ``error`` is ``None`` on success."""
        ...

    def snapshot(self, variables: list[str]) -> tuple[int, dict[str, Any]]:
        """Return ``(shot_number, {variable: value})`` for a subscription push."""
        ...


class _GeecsUdpProtocol(asyncio.DatagramProtocol):
    """Handles incoming UDP get/set commands and sends ACK + exe responses."""

    def __init__(self, device_name: str, store: VariableStore) -> None:
        self._device_name = device_name
        self._store = store
        self._transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:  # type: ignore[override]
        self._transport = transport

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        client_ip, client_cmd_port = addr
        client_exe_port = client_cmd_port + 1

        try:
            message = data.decode("ascii").strip()
        except UnicodeDecodeError:
            logger.warning("received non-ASCII UDP datagram from %s", addr)
            return

        logger.debug("UDP rx from %s:%s -> %r", client_ip, client_cmd_port, message)

        try:
            op, variable, raw_value = wire.parse_command(message)
        except ValueError:
            logger.warning("malformed UDP command: %r", message)
            return

        if op == "set":
            value = wire.coerce_scalar(raw_value)
            error = self._store.try_set(variable, value)
            reported_value = value if error is None else None
        else:
            reported_value, error = self._store.try_get(variable)

        assert self._transport is not None
        self._transport.sendto(wire.ACK_OK.encode("ascii"), (client_ip, client_cmd_port))

        exe_message = wire.build_exe_response(
            self._device_name, variable, reported_value, error
        )
        self._transport.sendto(exe_message.encode("ascii"), (client_ip, client_exe_port))
        logger.debug("UDP tx exe -> %s:%s %r", client_ip, client_exe_port, exe_message)

    def error_received(self, exc: Exception) -> None:
        logger.error("UDP error: %s", exc)


class _TcpSubscriptionHandler:
    """Manages one TCP ``Wait>>`` subscription connection."""

    def __init__(
        self,
        device_name: str,
        store: VariableStore,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        push_interval: float,
    ) -> None:
        self._device_name = device_name
        self._store = store
        self._reader = reader
        self._writer = writer
        self._push_interval = push_interval

    async def run(self) -> None:
        try:
            header = await self._reader.readexactly(wire.FRAME_HEADER_SIZE)
            message_length = wire.unpack_frame_header(header)
            payload = await self._reader.readexactly(message_length)
            command = payload.decode("ascii")
        except (asyncio.IncompleteReadError, ConnectionResetError):
            return

        try:
            variables = wire.parse_wait_command(command)
        except ValueError:
            logger.warning("TCP: unexpected subscription command %r", command)
            return

        logger.debug("TCP subscription for vars: %s", variables)
        try:
            while True:
                shot, values = self._store.snapshot(variables)
                message = wire.build_subscription_payload(self._device_name, shot, values)
                frame = wire.pack_frame(message)
                try:
                    self._writer.write(frame)
                    await self._writer.drain()
                except (ConnectionResetError, BrokenPipeError):
                    break
                await asyncio.sleep(self._push_interval)
        finally:
            await _close_writer(self._writer)


async def _close_writer(writer: asyncio.StreamWriter, timeout: float = 1.0) -> None:
    writer.close()
    try:
        await asyncio.wait_for(writer.wait_closed(), timeout=timeout)
    except Exception:
        transport = getattr(writer, "transport", None) or getattr(writer, "_transport", None)
        if transport is not None:
            transport.abort()


class GeecsDeviceServer:
    """Serves the GEECS UDP/TCP wire protocol for one device.

    Typical usage::

        server = GeecsDeviceServer("U_Picoscope3000A", store, host="0.0.0.0", port=4030)
        async with server:
            await asyncio.Event().wait()  # run forever
    """

    def __init__(
        self,
        device_name: str,
        store: VariableStore,
        host: str = "0.0.0.0",
        port: int = 0,
        push_hz: float = DEFAULT_PUSH_HZ,
    ) -> None:
        self.device_name = device_name
        self._store = store
        self.host = host
        self.port = port
        self._push_interval = 1.0 / push_hz
        self._udp_transport: asyncio.DatagramTransport | None = None
        self._tcp_server: asyncio.Server | None = None
        self._tcp_writers: set[asyncio.StreamWriter] = set()
        self._tcp_handler_tasks: set[asyncio.Task[Any]] = set()

    async def start(self) -> None:
        """Bind the UDP and TCP listeners on the same port number."""
        loop = asyncio.get_running_loop()
        bind_attempts = 10 if self.port == 0 else 1
        last_error: OSError | None = None

        for _attempt in range(bind_attempts):
            udp_transport: asyncio.BaseTransport | None = None
            try:
                udp_transport, _ = await loop.create_datagram_endpoint(
                    lambda: _GeecsUdpProtocol(self.device_name, self._store),
                    local_addr=(self.host, self.port),
                )
                bound_port = udp_transport.get_extra_info("sockname")[1]
                self._tcp_server = await asyncio.start_server(
                    self._handle_tcp, host=self.host, port=bound_port
                )
                self._udp_transport = udp_transport  # type: ignore[assignment]
                self.port = bound_port
                break
            except OSError as exc:
                if udp_transport is not None:
                    udp_transport.close()
                if self.port != 0 or exc.errno != errno.EADDRINUSE:
                    raise
                last_error = exc
                await asyncio.sleep(0)
        else:
            assert last_error is not None
            raise last_error

        logger.info(
            "GeecsDeviceServer '%s' listening on %s:%s (UDP+TCP)",
            self.device_name,
            self.host,
            self.port,
        )

    async def stop(self) -> None:
        """Shut down listeners and any active subscriptions."""
        if self._tcp_server is not None:
            self._tcp_server.close()
            await self._tcp_server.wait_closed()
            self._tcp_server = None

        writers = list(self._tcp_writers)
        self._tcp_writers.clear()
        if writers:
            await asyncio.gather(
                *(_close_writer(writer) for writer in writers), return_exceptions=True
            )

        handler_tasks = [
            task
            for task in self._tcp_handler_tasks
            if task is not asyncio.current_task() and not task.done()
        ]
        if handler_tasks:
            await asyncio.gather(*handler_tasks, return_exceptions=True)

        if self._udp_transport is not None:
            self._udp_transport.close()
            self._udp_transport = None

    async def _handle_tcp(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        task = asyncio.current_task()
        if task is not None:
            self._tcp_handler_tasks.add(task)
        self._tcp_writers.add(writer)
        try:
            handler = _TcpSubscriptionHandler(
                self.device_name, self._store, reader, writer, self._push_interval
            )
            await handler.run()
        finally:
            self._tcp_writers.discard(writer)
            if task is not None:
                self._tcp_handler_tasks.discard(task)

    async def __aenter__(self) -> "GeecsDeviceServer":
        await self.start()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.stop()
