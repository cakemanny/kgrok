import pytest
import trio.testing

from kgrok.messages import ConnectionClosed, DataReceived, NewConnection, Text


class TestText:

    @pytest.mark.parametrize('data,expected_message', [
        (Text.connection_closed(1), ConnectionClosed(1)),
        (Text.data_received(1, b'test'), DataReceived(1, b'test')),
        (Text.new_connection(1), NewConnection(1)),
    ])
    async def test_read_ipc_message(self, data, expected_message):
        stream = trio.testing.MemoryReceiveStream()
        stream.put_data(data)

        message = await Text.read_ipc_message(stream)

        assert message == expected_message

    async def test_multiple_messages(self):
        stream = trio.testing.MemoryReceiveStream()
        stream.put_data(Text.data_received(1, b'xxxx'))
        stream.put_data(Text.data_received(1, b'yyyy'))

        m1 = await Text.read_ipc_message(stream)
        m2 = await Text.read_ipc_message(stream)

        assert [m1, m2] == [
            DataReceived(1, b'xxxx'),
            DataReceived(1, b'yyyy'),
        ]
