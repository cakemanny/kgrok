from contextlib import AsyncExitStack
import functools
import logging
import subprocess
import sys

from trio.abc import SendStream
import click
import trio

from kgrok.messages import (
    ConnectionClosed, DataReceived, NewConnection, Text as msg,
)


async def handle_connection(
    conn_id: int,
    local_svc_addr: tuple[str, int],
    response_channel: trio.MemorySendChannel,
    recv: trio.MemoryReceiveChannel,
):
    host, port = local_svc_addr
    local_stream = await trio.open_tcp_stream(host, port)

    async def remote_to_local(recv):
        async with recv:  # not sure if it's our job to close this or not...
            async for message in recv:
                match message:
                    case DataReceived(_, data):
                        await local_stream.send_all(data)
                    case ConnectionClosed():
                        await local_stream.send_eof()

    async def local_to_remote(response_channel):
        async for data in local_stream:
            await response_channel.send(DataReceived(conn_id, data))
        await response_channel.send(ConnectionClosed(conn_id))

    async with local_stream, trio.open_nursery() as nursery:
        nursery.start_soon(remote_to_local, recv)
        nursery.start_soon(local_to_remote, response_channel)


async def write_responses(remote_stdin: SendStream, *,
                          task_status=trio.TASK_STATUS_IGNORED):
    send, recv = trio.open_memory_channel(0)
    task_status.started(send)

    async with recv:
        async for message in recv:
            match message:
                # TODO: we ought to define some sort of encoder interface
                case DataReceived(conn_id, data):
                    await remote_stdin.send_all(msg.data_received(conn_id, data))
                case ConnectionClosed(conn_id):
                    await remote_stdin.send_all(msg.connection_closed(conn_id))
                case other:
                    print(f'unexpected: {other=}', file=sys.stderr)


async def accept_connections(
    nursery: trio.Nursery,
    remote_stdio: trio.StapledStream,
    local_svc_addr: tuple[str, int]
):

    response_channel: trio.MemorySendChannel = await nursery.start(
        write_responses, remote_stdio.send_stream,
    )

    connections: dict[int, trio.MemorySendChannel] = {}

    try:
        while True:
            message = await msg.read_ipc_message(remote_stdio)
            match message:
                case NewConnection(conn_id):
                    send, recv = trio.open_memory_channel(80)
                    connections[conn_id] = send
                    nursery.start_soon(
                        handle_connection,
                        conn_id, local_svc_addr, response_channel, recv,
                    )
                case DataReceived(conn_id, _):
                    conn = connections.get(conn_id)
                    if conn:
                        await conn.send(message)
                    else:
                        print(f'dropped data for {conn_id=}', file=sys.stderr)
                case ConnectionClosed(conn_id):
                    conn = connections.get(conn_id)
                    if conn:
                        await conn.send(message)
                        await conn.aclose()
                        del connections[conn_id]
                    else:
                        print(f'unknown connection {conn_id=}', file=sys.stderr)
                case None:
                    break
    finally:
        async with AsyncExitStack() as stack:
            for chan in connections.values():
                stack.push_async_exit(chan)



def run_remote(port):

    return functools.partial(
        trio.run_process,
        [".venv/bin/kgrok-remote", "--port", str(port)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        env={'PYTHONUNBUFFERED': "1"}
    )


def run_kubectl_run(port):
    # Currently doing this to load into kind cluster:
    #
    #   docker build . -t kgrok-remote
    #   kind load docker-image kgrok-remote
    #

    return functools.partial(
        trio.run_process,
        [
            # The --rm doesn't seem to work without --tty
            # so, we have to call kubectl delete
            "kubectl", "run", "-i", "--rm", "kgrok-remote",
            "--image=kgrok-remote",
            "--port", str(port),
            "--image-pull-policy=Never",
            "--restart=Never",
            "--",
            "--port", str(port),
        ],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        # capture stderr?
    )


async def async_main(service_name, host, port):

    try:
        async with trio.open_nursery() as nursery:
            process = await nursery.start(run_kubectl_run(port))
            nursery.start_soon(
                accept_connections, nursery, process.stdio, (host, port),
            )
    except subprocess.CalledProcessError as cpe:
        print(f'calledprocesserror {cpe=}', file=sys.stderr)
        raise
    finally:
        try:
            await trio.run_process(["kubectl", "delete", "pod", "kgrok-remote"])
        except Exception as e:
            print("failed to delete pod", repr(e))


@click.command()
@click.argument('service-name')
@click.argument('host-port')
def main(service_name, host_port):
    host = 'localhost'
    if ':' in host_port:
        host, port = host_port.split(':')
        port = int(port)
    else:
        port = int(host_port)

    logging.basicConfig(
        level=logging.INFO,
    )

    trio.run(async_main, service_name, host, port)


if __name__ == '__main__':
    main()
