#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import socket
import threading
import json
import time
from datetime import datetime

# 服务器配置
PORT = 3003
MAX_ROOMS = 100
MAX_PLAYERS_PER_ROOM = 10
BUFFER_SIZE = 4096

# 全局数据
rooms = {}  # room_id -> {players: {player_id: {socket, name}}, name, created_at}
clients = {}  # client_socket -> {player_id, room_id, name}
lock = threading.Lock()


def get_timestamp():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def log(message):
    print(f'[{get_timestamp()}] {message}')


def send_message(client_socket, message_type, data=None):
    try:
        message = {'type': message_type}
        if data is not None:
            message['data'] = data
        message_json = json.dumps(message, ensure_ascii=False) + '\n'
        client_socket.send(message_json.encode('utf-8'))
    except Exception as e:
        log(f'发送消息失败: {e}')


def broadcast_to_room(room_id, message_type, data, exclude_player_id=None):
    with lock:
        if room_id not in rooms:
            return
        players = rooms[room_id]['players']
        for player_id, player_info in players.items():
            if player_id == exclude_player_id:
                continue
            try:
                send_message(player_info['socket'], message_type, data)
            except Exception as e:
                log(f'广播消息失败: {e}')


def handle_create_room(client_socket, room_id, room_name):
    with lock:
        if len(rooms) >= MAX_ROOMS:
            send_message(client_socket, 'ERROR', {'message': '房间数量已达上限'})
            return
        
        if room_id in rooms:
            send_message(client_socket, 'ERROR', {'message': '房间ID已存在'})
            return
        
        rooms[room_id] = {
            'name': room_name,
            'players': {},
            'created_at': get_timestamp()
        }
        
        send_message(client_socket, 'ROOM_CREATED', {
            'room_id': room_id,
            'room_name': room_name
        })
        
        log(f'房间 {room_id} ({room_name}) 创建成功')


def handle_join_room(client_socket, room_id, player_id, player_name):
    with lock:
        if room_id not in rooms:
            send_message(client_socket, 'ERROR', {'message': '房间不存在'})
            return
        
        room = rooms[room_id]
        if len(room['players']) >= MAX_PLAYERS_PER_ROOM:
            send_message(client_socket, 'ERROR', {'message': '房间已满'})
            return
        
        if player_id in room['players']:
            send_message(client_socket, 'ERROR', {'message': '玩家ID已存在'})
            return
        
        room['players'][player_id] = {
            'socket': client_socket,
            'name': player_name
        }
        
        clients[client_socket] = {
            'player_id': player_id,
            'room_id': room_id,
            'name': player_name
        }
        
        send_message(client_socket, 'JOINED', {
            'room_id': room_id,
            'room_name': room['name'],
            'players': [{'id': pid, 'name': pinfo['name']} for pid, pinfo in room['players'].items()]
        })
        
        broadcast_to_room(room_id, 'PLAYER_JOINED', {
            'player_id': player_id,
            'player_name': player_name
        }, exclude_player_id=player_id)
        
        log(f'玩家 {player_name} ({player_id}) 加入房间 {room_id}')


def handle_leave_room(client_socket, room_id, player_id):
    with lock:
        if room_id not in rooms:
            return
        
        room = rooms[room_id]
        if player_id not in room['players']:
            return
        
        del room['players'][player_id]
        
        if client_socket in clients:
            del clients[client_socket]
        
        broadcast_to_room(room_id, 'PLAYER_LEFT', {
            'player_id': player_id
        })
        
        if len(room['players']) == 0:
            del rooms[room_id]
            log(f'房间 {room_id} 已解散')
        else:
            log(f'玩家 {player_id} 离开房间 {room_id}')


def handle_send_data(client_socket, room_id, player_id, data):
    with lock:
        if room_id not in rooms:
            return
        
        broadcast_to_room(room_id, 'DATA', {
            'player_id': player_id,
            'data': data
        }, exclude_player_id=player_id)


def handle_broadcast(client_socket, room_id, player_id, message):
    with lock:
        if room_id not in rooms:
            return
        
        broadcast_to_room(room_id, 'BROADCAST', {
            'player_id': player_id,
            'message': message
        })


def handle_list_rooms(client_socket):
    with lock:
        room_list = []
        for room_id, room_info in rooms.items():
            room_list.append({
                'id': room_id,
                'name': room_info['name'],
                'player_count': len(room_info['players']),
                'max_players': MAX_PLAYERS_PER_ROOM,
                'created_at': room_info['created_at']
            })
        
        send_message(client_socket, 'ROOM_LIST', {'rooms': room_list})


def handle_client(client_socket, client_address):
    client_ip = client_address[0]
    log(f'新连接来自 {client_ip}:{client_address[1]}')
    
    try:
        buffer = ''
        while True:
            data = client_socket.recv(BUFFER_SIZE)
            if not data:
                break
            
            buffer += data.decode('utf-8')
            
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                line = line.strip()
                if not line:
                    continue
                
                try:
                    message = json.loads(line)
                    message_type = message.get('type')
                    
                    if message_type == 'CREATE_ROOM':
                        room_id = message.get('room_id')
                        room_name = message.get('room_name', '未命名房间')
                        handle_create_room(client_socket, room_id, room_name)
                    
                    elif message_type == 'JOIN_ROOM':
                        room_id = message.get('room_id')
                        player_id = message.get('player_id')
                        player_name = message.get('player_name', '匿名玩家')
                        handle_join_room(client_socket, room_id, player_id, player_name)
                    
                    elif message_type == 'LEAVE_ROOM':
                        room_id = message.get('room_id')
                        player_id = message.get('player_id')
                        handle_leave_room(client_socket, room_id, player_id)
                    
                    elif message_type == 'SEND_DATA':
                        room_id = message.get('room_id')
                        player_id = message.get('player_id')
                        data = message.get('data')
                        handle_send_data(client_socket, room_id, player_id, data)
                    
                    elif message_type == 'BROADCAST':
                        room_id = message.get('room_id')
                        player_id = message.get('player_id')
                        msg = message.get('message')
                        handle_broadcast(client_socket, room_id, player_id, msg)
                    
                    elif message_type == 'LIST_ROOMS':
                        handle_list_rooms(client_socket)
                    
                    elif message_type == 'PING':
                        send_message(client_socket, 'PONG')
                    
                    else:
                        send_message(client_socket, 'ERROR', {'message': f'未知消息类型: {message_type}'})
                
                except json.JSONDecodeError:
                    send_message(client_socket, 'ERROR', {'message': 'JSON解析失败'})
                except Exception as e:
                    log(f'处理消息错误: {e}')
                    send_message(client_socket, 'ERROR', {'message': str(e)})
    
    except ConnectionResetError:
        log(f'客户端 {client_ip} 连接已重置')
    except Exception as e:
        log(f'客户端错误: {e}')
    finally:
        if client_socket in clients:
            client_info = clients[client_socket]
            handle_leave_room(client_socket, client_info['room_id'], client_info['player_id'])
        
        client_socket.close()
        log(f'客户端 {client_ip} 已断开')


def start_server():
    server_socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server_socket.bind(('::', PORT))
        server_socket.listen(128)
        
        print('=' * 60)
        print('IPv6 游戏联机中继服务器')
        print('=' * 60)
        print(f'服务器地址: [::]:{PORT}')
        print(f'最大房间数: {MAX_ROOMS}')
        print(f'每房最大人数: {MAX_PLAYERS_PER_ROOM}')
        print('=' * 60)
        print('服务器已启动，等待连接...')
        print()
        
        while True:
            try:
                client_socket, client_address = server_socket.accept()
                client_thread = threading.Thread(
                    target=handle_client,
                    args=(client_socket, client_address)
                )
                client_thread.daemon = True
                client_thread.start()
            except Exception as e:
                log(f'接受连接错误: {e}')
    
    except Exception as e:
        print(f'服务器启动失败: {e}')
    finally:
        server_socket.close()
        print('服务器已关闭')


if __name__ == '__main__':
    start_server()
