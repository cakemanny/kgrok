# TODO: rename module IPC?
from dataclasses import dataclass
import io

import trio.abc


# A text version of our messages for debugability during development
class Text:

    @staticmethod
    def new_connection(conn_id) -> bytes:
        return f'NC:{conn_id:08x}\n'.encode()

    @staticmethod
    def connection_closed(conn_id) -> bytes:
        return f'CC:{conn_id:08x}\n'.encode()

    @staticmethod
    def data_received(conn_id, data: bytes) -> bytes:
        b = io.BytesIO()
        b.write(f'DR:{conn_id:08x}:{len(data):08x}:'.encode())
        b.write(data)
        b.write(b'\n')
        return b.getvalue()

    _cc_message_length = len(connection_closed(0))

    @staticmethod
    async def read_ipc_message(stream: trio.abc.ReceiveStream):
        def extract_conn_id(prefix):
            return int(prefix[3:11], 16)

        prefix = await stream.receive_some(Text._cc_message_length)
        if prefix == b'':
            return None
        if prefix.startswith(b'NC:'):
            conn_id = extract_conn_id(prefix)
            return NewConnection(conn_id)
        if prefix.startswith(b'CC:'):
            conn_id = extract_conn_id(prefix)
            return ConnectionClosed(conn_id)
        if prefix.startswith(b'DR:'):
            conn_id = extract_conn_id(prefix)
            length = await stream.receive_some(9)
            assert length[-1:] == b':', f"{length=}"
            length = int(length[:8], 16)
            data = await stream.receive_some(length + 1)
            assert data[-1:] == b'\n', f'{data=}'
            data = data[:-1]
            return DataReceived(conn_id, data)
        raise Exception(f'Unknown message with {prefix=}')

    @staticmethod
    def can_encode(msg) -> bool:
        return isinstance(msg, (DataReceived, ConnectionClosed, NewConnection))

    type Message = DataReceived | ConnectionClosed | NewConnection

    @classmethod
    def encode(cls, msg: Message) -> bytes:
        match msg:
            case DataReceived(conn_id, data):
                return cls.data_received(conn_id, data)
            case ConnectionClosed(conn_id):
                return cls.connection_closed(conn_id)
            case NewConnection(conn_id):
                return cls.new_connection(conn_id)
        raise TypeError(f'cannot encode {msg.__class.__.__name__}')


@dataclass
class DataReceived:
    conn_id: int
    data: bytes


@dataclass
class ConnectionClosed:
    conn_id: int


@dataclass
class NewConnection:
    conn_id: int
