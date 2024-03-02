from itertools import count
import logging
import os
import signal
import sys

from trio.abc import SendChannel, ReceiveChannel
import click
import trio

from kgrok.messages import (
    ConnectionClosed, DataReceived, Text as encoding,
)

log = logging.getLogger(__name__)

CONNECTION_COUNTER = count()


class Handler:
    def __init__(self, new_connections: SendChannel[tuple[int, SendChannel]]) -> None:
        self.stdout = trio.wrap_file(sys.stdout.buffer)
        self.new_connections = new_connections

    async def __call__(self, stream: trio.SocketStream):
        conn_id = next(CONNECTION_COUNTER)

        async with trio.open_nursery() as nursery:
            nursery.start_soon(self._handle_recv, conn_id, stream)
            nursery.start_soon(self._handle_resp, conn_id, stream)

    async def _handle_resp(self, conn_id: int, stream: trio.SocketStream):
        # The thought with the 80 here is that, configuring it to be 0
        # would mean that all connections would block if this client stops
        # reading ...
        # The correct thing to do would be to
        #  - a: timeout the sends and
        #  - b: stop reading in recv if sends are not working.
        send, recv = trio.open_memory_channel(80)
        await self.new_connections.send((conn_id, send,))

        async with recv:
            async for value in recv:
                match value:
                    case DataReceived(conn_id, data):
                        await stream.send_all(data)
                    case ConnectionClosed(conn_id):
                        await stream.send_eof()
                    case _:
                        raise TypeError(type(value))

    async def _handle_recv(self, conn_id: int, stream: trio.SocketStream):
        # we must've got a connection
        await self.stdout.write(encoding.new_connection(conn_id))
        try:
            async for data in stream:
                await self.stdout.write(encoding.data_received(conn_id, data))
        finally:
            await self.stdout.write(encoding.connection_closed(conn_id))


async def combine[L, R](
    left: ReceiveChannel[L],
    right: ReceiveChannel[R],
    *,
    task_status=trio.TASK_STATUS_IGNORED,
):
    out: SendChannel[tuple[L, None] | tuple[None, R]]
    out, recv = trio.open_memory_channel(0)
    task_status.started(recv)

    async def read_left(cancel_scope):
        async for value in left:
            await out.send((value, None))
        log.debug('cancel left')
        cancel_scope.cancel()

    async def read_right(cancel_scope):
        async for value in right:
            await out.send((None, value))
        log.debug('cancel right')
        cancel_scope.cancel()

    async with out, trio.open_nursery() as nursery:
        nursery.start_soon(read_left, nursery.cancel_scope)
        nursery.start_soon(read_right, nursery.cancel_scope)


async def dispatch_stdin(
    from_decode: ReceiveChannel,
    new_channels: ReceiveChannel[tuple[int, SendChannel]]
):
    channels: dict[int, SendChannel] = {}

    async with trio.open_nursery() as nursery:
        messages_or_new_connections = await nursery.start(
            combine, from_decode, new_channels)

        async for (message, new_channel) in messages_or_new_connections:
            if new_channel is not None:
                conn_id, send = new_channel
                channels[conn_id] = send
            else:
                assert message is not None
                channel = channels.get(message.conn_id)
                if channel is not None:
                    # Idea: one option might be to close the connection
                    # if the client stops reading.
                    await channel.send(message)
                    if isinstance(message, ConnectionClosed):
                        await channel.aclose()
                        del channels[message.conn_id]
                else:
                    # This really happened once in testing and the client
                    # hung... so maybe we have a problem after all.
                    # I think we have to switch back to the dict
                    log.warning(
                        f'dropped message for {message.conn_id=}',
                    )
        await messages_or_new_connections.aclose()


async def decode_stdin(decoded: SendChannel):
    # WARN: Absolutely no other use of stdin is allowed
    async with decoded, trio.lowlevel.FdStream(os.dup(sys.stdin.fileno())) as stdin:
        while True:
            message = await encoding.read_ipc_message(stdin)
            if message is None:
                break
            await decoded.send(message)


async def handle_sigterm(cancel_scope: trio.CancelScope):
    with trio.open_signal_receiver(signal.SIGTERM) as signal_aiter:
        async for signum in signal_aiter:
            assert signum == signal.SIGTERM
            log.info('SIGTERM. cancelling')
            cancel_scope.cancel()


async def listen(port: int):
    async with trio.open_nursery() as nursery:
        from_decode, to_dispatch = trio.open_memory_channel(0)
        nursery.start_soon(decode_stdin, from_decode)
        # nc = new channels/connections
        nc_from_handler, nc_to_dispatch = trio.open_memory_channel(0)
        nursery.start_soon(dispatch_stdin, to_dispatch, nc_to_dispatch)

        handler = Handler(nc_from_handler)
        nursery.start_soon(trio.serve_tcp, handler, port)
        nursery.start_soon(handle_sigterm, nursery.cancel_scope)


@click.command()
@click.option('--port', required=True, type=int)
def main(port: int):
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s:%(asctime)s:%(name)s:%(message)s'
    )
    log.info('listening on port %d', port)
    try:
        trio.run(listen, port)
    finally:
        log.info('exiting')


if __name__ == '__main__':
    main()
