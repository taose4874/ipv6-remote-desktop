#!/usr/bin/env python3
import socket
import threading
import sys
import os
import json

if os.path.exists(os.path.join(os.path.dirname(__file__), 'common')):
    sys.path.insert(0, os.path.dirname(__file__))

from common import Message, MessageType

class RemoteDesktopServer:
    def __init__(self, host='::', port=8888):
        self.host = host
        self.port = port
        self.clients = {}
        self.groups = {}
        self.running = False
        self.socket = None
        self.lock = threading.Lock()

    def start(self):
        self.socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.host, self.port))
        self.socket.listen(10)
        self.running = True
        print(f"服务器启动成功，监听 [{self.host}]:{self.port}")

        try:
            while self.running:
                client_socket, client_address = self.socket.accept()
                print(f"新客户端连接: {client_address}")
                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, client_address)
                )
                client_thread.daemon = True
                client_thread.start()
        except KeyboardInterrupt:
            print("\n服务器正在关闭...")
            self.stop()

    def stop(self):
        self.running = False
        with self.lock:
            for client_id in list(self.clients.keys()):
                try:
                    self.clients[client_id]['socket'].close()
                except:
                    pass
            self.clients.clear()
        if self.socket:
            self.socket.close()
        print("服务器已关闭")

    def handle_client(self, client_socket, client_address):
        client_id = f"{client_address[0]}:{client_address[1]}"
        try:
            with self.lock:
                self.clients[client_id] = {
                    'socket': client_socket,
                    'address': client_address,
                    'username': f"User_{len(self.clients) + 1}",
                    'group': None
                }

            self.broadcast_user_list()

            buffer = b''
            while self.running:
                data = client_socket.recv(65536)
                if not data:
                    break
                buffer += data

                while len(buffer) >= Message.get_header_size():
                    msg_type, payload_len = Message.parse_header(buffer)

                    if len(buffer) < Message.get_header_size() + payload_len:
                        break

                    msg = Message.deserialize(buffer[:Message.get_header_size() + payload_len])
                    buffer = buffer[Message.get_header_size() + payload_len:]

                    self.process_message(client_id, msg)

        except Exception as e:
            print(f"客户端 {client_id} 错误: {e}")
        finally:
            self.remove_client(client_id)

    def process_message(self, client_id: str, msg: Message):
        with self.lock:
            client = self.clients.get(client_id)
            if not client:
                return

        if msg.msg_type == MessageType.JOIN_GROUP:
            group_name = msg.data.get('group', 'default')
            username = msg.data.get('username')
            with self.lock:
                if username:
                    client['username'] = username
                client['group'] = group_name
                if group_name not in self.groups:
                    self.groups[group_name] = []
                if client_id not in self.groups[group_name]:
                    self.groups[group_name].append(client_id)
            self.broadcast_user_list()

        elif msg.msg_type == MessageType.LEAVE_GROUP:
            group_name = client.get('group')
            with self.lock:
                if group_name and group_name in self.groups:
                    if client_id in self.groups[group_name]:
                        self.groups[group_name].remove(client_id)
                client['group'] = None
            self.broadcast_user_list()

        elif msg.msg_type == MessageType.SCREEN_FRAME:
            target_id = msg.data.get('target')
            if target_id and target_id in self.clients:
                try:
                    self.clients[target_id]['socket'].send(msg.serialize())
                except:
                    pass

        elif msg.msg_type in (MessageType.MOUSE_EVENT, MessageType.KEYBOARD_EVENT):
            target_id = msg.data.get('target')
            if target_id and target_id in self.clients:
                try:
                    self.clients[target_id]['socket'].send(msg.serialize())
                except:
                    pass

        elif msg.msg_type == MessageType.HEARTBEAT:
            try:
                client_socket.send(msg.serialize())
            except:
                pass

    def broadcast_user_list(self):
        with self.lock:
            user_list = []
            for cid, info in self.clients.items():
                user_list.append({
                    'id': cid,
                    'username': info['username'],
                    'group': info['group']
                })

        msg = Message(MessageType.USER_LIST, {'users': user_list})
        with self.lock:
            for client_id in list(self.clients.keys()):
                try:
                    self.clients[client_id]['socket'].send(msg.serialize())
                except:
                    self.remove_client(client_id)

    def remove_client(self, client_id: str):
        with self.lock:
            if client_id in self.clients:
                client = self.clients[client_id]
                group_name = client.get('group')
                if group_name and group_name in self.groups:
                    if client_id in self.groups[group_name]:
                        self.groups[group_name].remove(client_id)
                try:
                    client['socket'].close()
                except:
                    pass
                del self.clients[client_id]
        self.broadcast_user_list()

def main():
    server = RemoteDesktopServer()
    try:
        server.start()
    except Exception as e:
        print(f"服务器启动失败: {e}")

if __name__ == "__main__":
    main()
