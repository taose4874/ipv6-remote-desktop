#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import socket
import threading
import json
import os
from datetime import datetime

CONFIG_FILE = 'config_server.json'
BUFFER_SIZE = 4096

DEFAULT_CONFIG = {
    "control_port": 7000,
    "listen_port": 25565
}

lock = threading.Lock()
client_control_socket = None
client_connected = False
pending_connection = None


def get_timestamp():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def log(message):
    print(f'[{get_timestamp()}] {message}')


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            log(f'配置加载成功: {CONFIG_FILE}')
            return config
        except Exception as e:
            log(f'配置加载失败: {e}')
    else:
        log(f'创建默认配置: {CONFIG_FILE}')
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
    return DEFAULT_CONFIG


def forward_data(src, dst, name):
    try:
        while True:
            data = src.recv(BUFFER_SIZE)
            if not data:
                break
            dst.sendall(data)
    except Exception as e:
        log(f'转发错误 [{name}]: {e}')
    finally:
        try:
            src.close()
        except:
            pass
        try:
            dst.close()
        except:
            pass


def handle_tunnel_connection(tunnel_socket, addr):
    global pending_connection
    
    log(f'隧道连接来自: {addr[0]}:{addr[1]}')
    
    with lock:
        if pending_connection is None:
            log('没有待处理的连接，关闭隧道')
            tunnel_socket.close()
            return
        
        game_socket = pending_connection
        pending_connection = None
    
    try:
        thread1 = threading.Thread(target=forward_data, args=(game_socket, tunnel_socket, 'game->tunnel'))
        thread2 = threading.Thread(target=forward_data, args=(tunnel_socket, game_socket, 'tunnel->game'))
        
        thread1.daemon = True
        thread2.daemon = True
        thread1.start()
        thread2.start()
        
        thread1.join()
        thread2.join()
        
    except Exception as e:
        log(f'处理隧道连接错误: {e}')


def handle_game_connection(game_socket, addr):
    global pending_connection, client_connected, client_control_socket
    
    log(f'游戏连接来自: {addr[0]}:{addr[1]}')
    
    with lock:
        if not client_connected or client_control_socket is None:
            log('客户端未连接，拒绝游戏连接')
            game_socket.close()
            return
        
        pending_connection = game_socket
    
    try:
        req_msg = {'type': 'NEW_CONNECTION'}
        client_control_socket.sendall((json.dumps(req_msg) + '\n').encode('utf-8'))
        
    except Exception as e:
        log(f'发送连接请求错误: {e}')
        game_socket.close()
        with lock:
            pending_connection = None


def start_game_listener(listen_port):
    listen_socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        listen_socket.bind(('::', listen_port))
        listen_socket.listen(128)
        
        log(f'游戏端口监听: [::]:{listen_port}')
        
        while True:
            try:
                game_socket, addr = listen_socket.accept()
                game_thread = threading.Thread(
                    target=handle_game_connection,
                    args=(game_socket, addr)
                )
                game_thread.daemon = True
                game_thread.start()
            except Exception as e:
                log(f'接受游戏连接错误: {e}')
                
    except Exception as e:
        log(f'游戏端口监听失败: {e}')
    finally:
        listen_socket.close()


def handle_client_control(conn, addr):
    global client_control_socket, client_connected
    
    client_ip = addr[0]
    log(f'客户端连接: {client_ip}:{addr[1]}')
    
    with lock:
        client_control_socket = conn
        client_connected = True
    
    try:
        while True:
            data = conn.recv(BUFFER_SIZE)
            if not data:
                break
                
    except Exception as e:
        log(f'客户端连接错误: {e}')
    finally:
        with lock:
            client_control_socket = None
            client_connected = False
        
        try:
            conn.close()
        except:
            pass
        
        log(f'客户端断开: {client_ip}')


def start_control_listener(control_port):
    server_socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server_socket.bind(('::', control_port))
        server_socket.listen(128)
        
        log(f'控制端口监听: [::]:{control_port}')
        
        while True:
            try:
                conn, addr = server_socket.accept()
                
                if not client_connected:
                    client_thread = threading.Thread(
                        target=handle_client_control,
                        args=(conn, addr)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                else:
                    tunnel_thread = threading.Thread(
                        target=handle_tunnel_connection,
                        args=(conn, addr)
                    )
                    tunnel_thread.daemon = True
                    tunnel_thread.start()
                
            except Exception as e:
                log(f'接受控制连接错误: {e}')
                
    except Exception as e:
        log(f'控制端口监听失败: {e}')
    finally:
        server_socket.close()


def start_server():
    config = load_config()
    control_port = config.get('control_port', 7000)
    listen_port = config.get('listen_port', 25565)
    
    print('=' * 60)
    print('IPv6 内网穿透 - 服务器端')
    print('=' * 60)
    print(f'控制端口: {control_port}')
    print(f'游戏端口: [::]:{listen_port}')
    print('=' * 60)
    print('服务器启动中...')
    print()
    
    control_thread = threading.Thread(target=start_control_listener, args=(control_port,))
    control_thread.daemon = True
    control_thread.start()
    
    game_thread = threading.Thread(target=start_game_listener, args=(listen_port,))
    game_thread.daemon = True
    game_thread.start()
    
    import time
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print('\n服务器关闭')


if __name__ == '__main__':
    start_server()
