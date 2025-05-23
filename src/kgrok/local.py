import os
from contextlib import AsyncExitStack
import functools
import logging
import subprocess
import typing

from lightkube import AsyncClient
from lightkube.config.kubeconfig import KubeConfig, SingleConfig
from lightkube.models.core_v1 import ServicePort, ServiceSpec
from lightkube.models.meta_v1 import ObjectMeta
from lightkube.resources.core_v1 import Service
from trio.abc import SendStream, SendChannel, ReceiveChannel
import lightkube
import click
import trio

from kgrok.messages import (
    ConnectionClosed, DataReceived, NewConnection, Text as encoding,
)


log = logging.getLogger(__name__)


async def handle_connection(
    conn_id: int,
    local_svc_addr: tuple[str, int],
    response_channel: SendChannel,
    recv: ReceiveChannel,
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
                    case _:
                        raise TypeError(type(message))

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
            await remote_stdin.send_all(encoding.encode(message))


async def accept_connections(
    nursery: trio.Nursery,
    remote_stdio: trio.StapledStream,
    local_svc_addr: tuple[str, int]
):

    response_channel: SendChannel = await nursery.start(
        write_responses, remote_stdio.send_stream,
    )

    connections: dict[int, SendChannel] = {}

    try:
        while True:
            message = await encoding.read_ipc_message(remote_stdio)
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
                        log.warning(f'dropped data for {conn_id=}')
                case ConnectionClosed(conn_id):
                    conn = connections.get(conn_id)
                    if conn:
                        await conn.send(message)
                        await conn.aclose()
                        del connections[conn_id]
                    else:
                        log.warning(f'unknown connection {conn_id=}')
                case None:
                    break
    finally:
        async with AsyncExitStack() as stack:
            for chan in connections.values():
                stack.push_async_exit(chan)

###
### Startup
###

def run_remote(port):

    return functools.partial(
        trio.run_process,
        [".venv/bin/kgrok-remote", "--port", str(port)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        env={'PYTHONUNBUFFERED': "1"}
    )


def prepare_labels(labels: dict[str, str]) -> str:
    return ','.join(
        '='.join((k, v)) for k,v in labels.items()
    )


def run_kubectl_run(port, labels, namespace):

    default_image = "ghcr.io/cakemanny/kgrok-remote"
    image = os.getenv("KGROK_REMOTE_IMAGE", default_image)

    extra_args = []
    # For now this is something of a good indicator for a locally loaded
    # dev image
    if '/' not in image:  # locally loaded dev image
        extra_args.append("--image-pull-policy=Never")

    if namespace and namespace != 'default':
        extra_args.append(f"--namespace={namespace}")

    return functools.partial(
        trio.run_process,
        [
            # The --rm doesn't seem to work without --tty
            # so, we have to call kubectl delete
            "kubectl", "run", "-i", "--rm", "kgrok-remote",
            f"--image={image}",
            "--port", str(port),
            "--restart=Never",
            "--labels=" + prepare_labels(labels),  # shell vuln?
            *extra_args,
            "--",
            "--port", str(port),
        ],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        # capture stderr?
    )


type TargetSpec = tuple[dict[str, str], int]


def target_spec_from_service(svc: Service) -> TargetSpec:
    assert svc.metadata is not None, f'svc.metadata is None: {svc=}'
    assert svc.spec is not None, f'svc.spec is None: {svc=}'
    name = svc.metadata.name

    # I checked the api spec for this one
    selector = typing.cast(dict[str,str], svc.spec.selector)

    ports = svc.spec.ports or []
    if len(ports) < 1:
        raise ValueError(f'service {name} has no ports')
    if len(ports) > 1:
        log.warning(f'service {name} has more than one port, using first')

    # Future: we could exclude udp ports
    # Future: we could prefer http appProtocol over other options...

    port = ports[0].targetPort or ports[0].port
    if isinstance(port, str):
        # Future: look up selected pods and work out what the name
        # refers to
        raise ValueError(f'service {name} has a named port, named ports not supported')

    return selector, port


async def setup_service(
    name: str, namespace: str, port: int, exit_stack: AsyncExitStack,
) -> TargetSpec:

    config: SingleConfig | None = KubeConfig.from_env().get()
    assert config is not None
    client = AsyncClient(config=config)

    try:
        svc = await client.get(Service, name, namespace=namespace)
        assert isinstance(svc, Service)
        return target_spec_from_service(svc)
    except lightkube.ApiError as e:
        if e.status.reason == "NotFound":
            labels = {'app': name}
            service = Service(
                metadata=ObjectMeta(
                    name=name, namespace=namespace, labels=labels,
                ),
                spec=ServiceSpec(
                    ports=[ServicePort(port=port)], selector=labels,
                )
            )
            await client.create(service, name)
            exit_stack.push_async_callback(
                client.delete, Service, name, namespace=namespace,
            )
            return labels, port
        else:
            raise


async def async_main(service_name: str, host: str, port: int, namespace: str):

    async with AsyncExitStack() as exit_stack:
        labels, remote_port = await setup_service(
            service_name, namespace, port, exit_stack)

        try:
            async with trio.open_nursery() as nursery:
                process = await nursery.start(
                    run_kubectl_run(remote_port, labels, namespace)
                )
                nursery.start_soon(
                    accept_connections, nursery, process.stdio, (host, port),
                )
        except subprocess.CalledProcessError as cpe:
            log.warning(f'calledprocesserror {cpe=}')
            raise
        finally:
            try:
                await trio.run_process(["kubectl", "delete", "pod", "kgrok-remote"])
            except Exception as e:
                log.warning("failed to delete pod", repr(e))


@click.command()
@click.argument('service-name')
@click.argument('host-port')
@click.option('-n', '--namespace', default="default" , help='the kubernetes namespace')
def main(service_name, host_port, namespace):
    host = 'localhost'
    if ':' in host_port:
        host, port = host_port.split(':')
        port = int(port)
    else:
        port = int(host_port)

    logging.basicConfig(
        level=logging.INFO,
    )

    trio.run(async_main, service_name, host, port, namespace)


if __name__ == '__main__':
    main()
