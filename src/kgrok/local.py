import trio
import click


async def async_main(service_name, host, port):

    async with trio.open_nursery() as nursery:
        nursery.start
        # do the nursery.start to start our 'remote' process
        pass


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

    trio.run(async_main, service_name, host, port)

if __name__ == '__main__':
    main()
