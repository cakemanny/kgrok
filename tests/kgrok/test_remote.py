import pytest
import trio
import trio.testing
from kgrok.messages import DataReceived

from kgrok.remote import dispatch_stdin


@pytest.mark.skip("flaky")
async def test_dispatch_stdin():
    with trio.fail_after(1):
        # We use buffered channels to avoid blocking forever and getting stuck
        from_decode, to_dispatch  = trio.open_memory_channel(1)
        nc_from_handler, nc_to_dispatch = trio.open_memory_channel(1)
        reply_send, reply_recv = trio.open_memory_channel(1)

        # a new connection
        await nc_from_handler.send((1,reply_send,))
        # ...
        # local is told about the new connection
        # ...
        # a reply
        await from_decode.send(DataReceived(1, b'xxx'))
        await from_decode.aclose()

        await dispatch_stdin(to_dispatch, new_channels=nc_to_dispatch)

        assert await reply_recv.receive() == DataReceived(conn_id=1, data=b'xxx')
