import socket
import threading
import base64
import sys
import os
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common import Message, MessageType
from PyQt6.QtCore import QObject, pyqtSignal

class NetworkClient(QObject):
    connected = pyqtSignal()
    disconnected = pyqtSignal()
    message_received = pyqtSignal(Message)
    error_occurred = pyqtSignal(str)
    user_list_updated = pyqtSignal(list)
    
    def __init__(self):
        super().__init__()
        self.socket = None
        self.running = False
        self.receive_thread = None
        self.buffer = b''
        self.client_id = None
    
    def connect_to_server(self, host: str, port: int):
        try:
            self.socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            self.socket.connect((host, port))
            self.running = True
            self.client_id = f"{self.socket.getsockname()[0]}:{self.socket.getsockname()[1]}"
            
            self.receive_thread = threading.Thread(target=self._receive_loop)
            self.receive_thread.daemon = True
            self.receive_thread.start()
            
            self.connected.emit()
            return True
        except Exception as e:
            self.error_occurred.emit(f"连接失败: {str(e)}")
            return False
    
    def disconnect(self):
        self.running = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
        self.disconnected.emit()
    
    def send_message(self, msg: Message):
        if self.socket and self.running:
            try:
                self.socket.send(msg.serialize())
                return True
            except Exception as e:
                self.error_occurred.emit(f"发送失败: {str(e)}")
                self.disconnect()
        return False
    
    def send_screen_frame(self, frame_data: bytes, target_id: str):
        encoded_frame = base64.b64encode(frame_data).decode('utf-8')
        msg = Message(MessageType.SCREEN_FRAME, {
            'frame': encoded_frame,
            'target': target_id
        })
        self.send_message(msg)
    
    def send_mouse_event(self, x: int, y: int, button: str, pressed: bool, target_id: str):
        msg = Message(MessageType.MOUSE_EVENT, {
            'x': x,
            'y': y,
            'button': button,
            'pressed': pressed,
            'target': target_id
        })
        self.send_message(msg)
    
    def send_keyboard_event(self, key: str, pressed: bool, target_id: str):
        msg = Message(MessageType.KEYBOARD_EVENT, {
            'key': key,
            'pressed': pressed,
            'target': target_id
        })
        self.send_message(msg)
    
    def join_group(self, group_name: str, username: str):
        msg = Message(MessageType.JOIN_GROUP, {
            'group': group_name,
            'username': username
        })
        self.send_message(msg)
    
    def leave_group(self):
        msg = Message(MessageType.LEAVE_GROUP, {})
        self.send_message(msg)
    
    def _receive_loop(self):
        while self.running:
            try:
                data = self.socket.recv(65536)
                if not data:
                    break
                self.buffer += data
                
                while len(self.buffer) >= Message.get_header_size():
                    msg_type, payload_len = Message.parse_header(self.buffer)
                    
                    if len(self.buffer) < Message.get_header_size() + payload_len:
                        break
                    
                    msg = Message.deserialize(self.buffer[:Message.get_header_size() + payload_len])
                    self.buffer = self.buffer[Message.get_header_size() + payload_len:]
                    
                    if msg.msg_type == MessageType.USER_LIST:
                        self.user_list_updated.emit(msg.data.get('users', []))
                    else:
                        self.message_received.emit(msg)
            
            except Exception as e:
                if self.running:
                    self.error_occurred.emit(f"接收错误: {str(e)}")
                break
        
        self.disconnect()
