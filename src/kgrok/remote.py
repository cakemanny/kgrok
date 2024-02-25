from itertools import count
from typing import Any
import os
import sys

import click
import trio

from kgrok.messages import (
    ConnectionClosed, DataReceived, Text as msg,
)


CONNECTION_COUNTER = count()


class Handler:
    def __init__(self) -> None:
        self.stdout = trio.wrap_file(sys.stdout.buffer)
        self.recv_channels = {}

    async def __call__(self, stream: trio.SocketStream) -> Any:
        conn_id = next(CONNECTION_COUNTER)

        async with trio.open_nursery() as nursery:
            nursery.start_soon(self._handle_recv, conn_id, stream)
            await nursery.start(self._handle_resp, conn_id, stream)

    async def _handle_resp(self, conn_id: int, stream: trio.SocketStream,
                           *, task_status=trio.TASK_STATUS_IGNORED):

        send, recv = trio.open_memory_channel(80)

        # yuk - TODO: work out how we can share send the channel to the
        # stdin reader better
        self.recv_channels[conn_id] = send
        task_status.started()

        async with recv:
            async for value in recv:
                match value:
                    case DataReceived(conn_id, data):
                        await stream.send_all(data)
                    case ConnectionClosed(conn_id):
                        await stream.send_eof()

    async def _handle_recv(self, conn_id: int, stream: trio.SocketStream):
        # we must've got a connection
        await self.stdout.write(msg.new_connection(conn_id))
        try:
            async for data in stream:
                await self.stdout.write(msg.data_received(conn_id, data))
        finally:
            await self.stdout.write(msg.connection_closed(conn_id))


async def read_stdin(channels: dict[int, trio.MemorySendChannel]):
    # WARN: Absolutely no other use of stdin is allowed
    stdin = trio.lowlevel.FdStream(os.dup(sys.stdin.fileno()))
    try:
        while True:
            message = await msg.read_ipc_message(stdin)
            channel = channels.get(message.conn_id)
            if channel is not None:
                await channel.send(message)
                if isinstance(message, ConnectionClosed):
                    await channel.aclose()
                    del channels[message.conn_id]
            else:
                print(f'dropped message for {message.conn_id=}',
                      file=sys.stderr)
    finally:
        await stdin.aclose()


async def listen(port: int):
    handler = Handler()

    async with trio.open_nursery() as nursery:
        nursery.start_soon(read_stdin, handler.recv_channels)
        nursery.start_soon(trio.serve_tcp, handler, port)


@click.command()
@click.option('--port', required=True, type=int)
def main(port: int):
    trio.run(listen, port)


if __name__ == '__main__':
    main()
