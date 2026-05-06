import struct
import json
from enum import Enum

class MessageType(Enum):
    SCREEN_FRAME = 1
    MOUSE_EVENT = 2
    KEYBOARD_EVENT = 3
    JOIN_GROUP = 4
    LEAVE_GROUP = 5
    USER_LIST = 6
    HEARTBEAT = 7
    REQUEST_CONTROL = 8
    GRANT_CONTROL = 9
    RELEASE_CONTROL = 10
    DISCONNECT = 11

class Message:
    def __init__(self, msg_type: MessageType, data=None):
        self.msg_type = msg_type
        self.data = data or {}
    
    def serialize(self) -> bytes:
        payload = json.dumps(self.data).encode('utf-8')
        header = struct.pack('!II', self.msg_type.value, len(payload))
        return header + payload
    
    @classmethod
    def deserialize(cls, data: bytes) -> 'Message':
        msg_type_value, payload_len = struct.unpack('!II', data[:8])
        payload = json.loads(data[8:8+payload_len].decode('utf-8'))
        return cls(MessageType(msg_type_value), payload)
    
    @classmethod
    def get_header_size(cls) -> int:
        return struct.calcsize('!II')
    
    @classmethod
    def parse_header(cls, data: bytes) -> tuple:
        msg_type_value, payload_len = struct.unpack('!II', data[:8])
        return MessageType(msg_type_value), payload_len
