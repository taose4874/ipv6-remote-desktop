#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import socket
import threading
import json
import os
import time
from datetime import datetime

CONFIG_FILE = 'config_client.json'
BUFFER_SIZE = 4096

DEFAULT_CONFIG = {
    "server_addr": "your_server_ipv6",
    "server_port": 7000,
    "local_port": 25565
}


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


def handle_tunnel(tunnel_socket, local_port):
    try:
        local_socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        local_socket.connect(('::1', local_port))
        log(f'连接本地端口: {local_port}')
        
        thread1 = threading.Thread(target=forward_data, args=(tunnel_socket, local_socket, 'tunnel->local'))
        thread2 = threading.Thread(target=forward_data, args=(local_socket, tunnel_socket, 'local->tunnel'))
        
        thread1.daemon = True
        thread2.daemon = True
        thread1.start()
        thread2.start()
        
        thread1.join()
        thread2.join()
        
    except Exception as e:
        log(f'处理隧道错误: {e}')
        try:
            tunnel_socket.close()
        except:
            pass


def connect_to_server(config):
    server_addr = config['server_addr']
    server_port = config['server_port']
    local_port = config['local_port']
    
    print('=' * 60)
    print('IPv6 内网穿透 - 客户端')
    print('=' * 60)
    print(f'服务器地址: {server_addr}:{server_port}')
    print(f'本地端口: {local_port}')
    print('=' * 60)
    print('连接服务器中...')
    print()
    
    while True:
        try:
            control_socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            log(f'正在连接服务器: {server_addr}:{server_port}')
            control_socket.connect((server_addr, server_port))
            log('连接服务器成功！')
            
            buffer = ''
            while True:
                data = control_socket.recv(BUFFER_SIZE)
                if not data:
                    break
                
                buffer += data.decode('utf-8', errors='ignore')
                
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    line = line.strip()
                    
                    try:
                        msg = json.loads(line)
                        
                        if msg.get('type') == 'NEW_CONNECTION':
                            log('收到新连接请求！')
                            
                            tunnel_socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                            tunnel_socket.connect((server_addr, server_port))
                            
                            tunnel_thread = threading.Thread(
                                target=handle_tunnel,
                                args=(tunnel_socket, local_port)
                            )
                            tunnel_thread.daemon = True
                            tunnel_thread.start()
                            
                    except Exception as e:
                        log(f'处理消息错误: {e}')
                        
        except Exception as e:
            log(f'连接服务器失败: {e}')
            log('5秒后重试...')
            time.sleep(5)
            continue


if __name__ == '__main__':
    config = load_config()
    connect_to_server(config)
