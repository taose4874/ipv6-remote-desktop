#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import socket
import threading
import json
import os
import time
from datetime import datetime
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                             QTextEdit, QGroupBox, QFormLayout, QSpinBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QColor


def get_config_path(filename):
    # 获取程序所在目录
    if getattr(sys, 'frozen', False):
        # 打包后的exe程序
        program_dir = Path(sys.executable).parent
    else:
        # 开发环境下的脚本文件
        program_dir = Path(__file__).parent
    return str(program_dir / filename)


CONFIG_FILE = get_config_path('config_client.json')
BUFFER_SIZE = 4096

DEFAULT_CONFIG = {
    "server_addr": "",
    "server_port": 7000,
    "local_port": 25565
}


def get_timestamp():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


class LogEmitter(QObject):
    log_signal = pyqtSignal(str, str)
    port_allocated = pyqtSignal(int)


class ClientThread(QThread):
    def __init__(self, config, log_emitter):
        super().__init__()
        self.config = config
        self.log_emitter = log_emitter
        self.running = False
        self.control_socket = None
        self.public_port = None
        
    def log(self, message, level="info"):
        self.log_emitter.log_signal.emit(message, level)
        
    def forward_data(self, src, dst, name):
        try:
            src.settimeout(2.0)
            while self.running:
                try:
                    data = src.recv(BUFFER_SIZE)
                    if not data:
                        break
                    dst.sendall(data)
                except socket.timeout:
                    continue
        except Exception as e:
            pass
        finally:
            try:
                src.close()
            except:
                pass
            try:
                dst.close()
            except:
                pass
                
    def handle_tunnel(self, tunnel_socket, local_port):
        try:
            local_socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            local_socket.settimeout(5.0)
            local_socket.connect(('::1', local_port))
            self.log(f'连接本地端口: {local_port}', 'info')
            
            thread1 = threading.Thread(target=self.forward_data, args=(tunnel_socket, local_socket, f'tunnel->{local_port}'))
            thread2 = threading.Thread(target=self.forward_data, args=(local_socket, tunnel_socket, f'{local_port}->tunnel'))
            
            thread1.daemon = True
            thread2.daemon = True
            thread1.start()
            thread2.start()
            
            while self.running and (thread1.is_alive() or thread2.is_alive()):
                time.sleep(0.1)
            
        except Exception as e:
            self.log(f'连接本地端口失败: {e}', 'error')
            try:
                tunnel_socket.close()
            except:
                pass
                
    def create_tunnel(self, proxy_port, local_port):
        try:
            server_addr = self.config['server_addr']
            server_port = self.config['server_port']
            
            tunnel_socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
            tunnel_socket.settimeout(5.0)
            tunnel_socket.connect((server_addr, server_port))
            
            ready_msg = {'type': 'TUNNEL_READY', 'proxy_port': proxy_port}
            tunnel_socket.sendall((json.dumps(ready_msg) + '\n').encode('utf-8'))
            
            tunnel_thread = threading.Thread(
                target=self.handle_tunnel,
                args=(tunnel_socket, local_port)
            )
            tunnel_thread.daemon = True
            tunnel_thread.start()
            
        except Exception as e:
            self.log(f'创建隧道失败: {e}', 'error')
                
    def connect_to_server(self):
        server_addr = self.config['server_addr']
        server_port = self.config['server_port']
        local_port = self.config.get('local_port', 25565)
        
        while self.running:
            try:
                self.control_socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                self.log(f'正在连接服务器: {server_addr}:{server_port}', 'info')
                self.control_socket.connect((server_addr, server_port))
                self.log('连接服务器成功！', 'success')
                
                self.log(f'请求端口分配，本地端口: {local_port}', 'info')
                req_msg = {'type': 'REQUEST_PORT', 'local_port': local_port}
                self.control_socket.sendall((json.dumps(req_msg) + '\n').encode('utf-8'))
                
                buffer = ''
                while self.running:
                    try:
                        data = self.control_socket.recv(BUFFER_SIZE)
                        if not data:
                            break
                        
                        buffer += data.decode('utf-8', errors='ignore')
                        
                        while '\n' in buffer:
                            line, buffer = buffer.split('\n', 1)
                            line = line.strip()
                            
                            try:
                                msg = json.loads(line)
                                
                                if msg.get('type') == 'PORT_ALLOCATED':
                                    self.public_port = msg.get('public_port')
                                    self.log(f'端口分配成功！公网端口: {self.public_port}', 'success')
                                    self.log_emitter.port_allocated.emit(self.public_port)
                                    
                                elif msg.get('type') == 'PORT_ERROR':
                                    self.log(f'端口分配失败: {msg.get("message", "")}', 'error')
                                    
                                elif msg.get('type') == 'NEW_CONNECTION':
                                    proxy_port = msg.get('proxy_port')
                                    if proxy_port == self.public_port:
                                        tunnel_thread = threading.Thread(
                                            target=self.create_tunnel,
                                            args=(proxy_port, local_port)
                                        )
                                        tunnel_thread.daemon = True
                                        tunnel_thread.start()
                                        
                            except Exception as e:
                                self.log(f'处理消息错误: {e}', 'error')
                    except socket.timeout:
                        continue
                    
            except Exception as e:
                self.log(f'连接服务器失败: {e}', 'error')
                self.log('5秒后重试...', 'warning')
                for i in range(50):
                    if not self.running:
                        break
                    time.sleep(0.1)
                continue
            
            try:
                if self.control_socket:
                    self.control_socket.close()
                    self.control_socket = None
            except:
                pass
            
    def run(self):
        self.running = True
        self.connect_to_server()
        
    def stop(self):
        self.running = False
        try:
            if self.control_socket:
                self.control_socket.close()
        except:
            pass
        self.wait()


class ClientWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.client_thread = None
        self.log_emitter = LogEmitter()
        self.log_emitter.log_signal.connect(self.append_log)
        self.log_emitter.port_allocated.connect(self.on_port_allocated)
        self.server_addr = ""
        self.public_port = None
        self.init_ui()
        self.load_config()
        
    def init_ui(self):
        self.setWindowTitle('IPv6 内网穿透 - 客户端')
        self.setMinimumSize(600, 500)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        
        # 配置区域
        config_group = QGroupBox('配置')
        config_layout = QFormLayout()
        
        self.server_addr_input = QLineEdit()
        self.server_addr_input.setPlaceholderText('例如: 2001:db8::1')
        config_layout.addRow('服务器地址:', self.server_addr_input)
        
        self.server_port_input = QSpinBox()
        self.server_port_input.setRange(1, 65535)
        self.server_port_input.setValue(7000)
        config_layout.addRow('服务器端口:', self.server_port_input)
        
        self.local_port_input = QSpinBox()
        self.local_port_input.setRange(1, 65535)
        self.local_port_input.setValue(25565)
        config_layout.addRow('本地游戏端口:', self.local_port_input)
        
        config_group.setLayout(config_layout)
        main_layout.addWidget(config_group)
        
        # 公网链接显示
        link_group = QGroupBox('公网连接地址')
        link_layout = QHBoxLayout()
        
        self.link_label = QLabel('未连接')
        self.link_label.setStyleSheet('font-size: 18px; font-weight: bold; color: #666;')
        link_layout.addWidget(self.link_label)
        
        self.copy_link_btn = QPushButton('复制链接')
        self.copy_link_btn.clicked.connect(self.copy_link)
        self.copy_link_btn.setEnabled(False)
        link_layout.addWidget(self.copy_link_btn)
        
        link_group.setLayout(link_layout)
        main_layout.addWidget(link_group)
        
        # 控制按钮
        button_layout = QHBoxLayout()
        
        self.connect_button = QPushButton('连接服务器')
        self.connect_button.setStyleSheet('''
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-size: 16px;
                font-weight: bold;
                padding: 15px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        ''')
        self.connect_button.clicked.connect(self.toggle_connection)
        button_layout.addWidget(self.connect_button)
        
        main_layout.addLayout(button_layout)
        
        # 日志区域
        log_group = QGroupBox('日志')
        log_layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont('Consolas', 10))
        log_layout.addWidget(self.log_text)
        
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)
        
        # 状态标签
        self.status_label = QLabel('状态: 未连接')
        self.status_label.setStyleSheet('font-size: 12px; color: #666;')
        main_layout.addWidget(self.status_label)
        
    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                self.server_addr_input.setText(config.get('server_addr', ''))
                self.server_port_input.setValue(config.get('server_port', 7000))
                self.local_port_input.setValue(config.get('local_port', 25565))
            except Exception as e:
                self.append_log(f'配置加载失败: {e}', 'error')
                
    def save_config(self):
        config = {
            "server_addr": self.server_addr_input.text(),
            "server_port": self.server_port_input.value(),
            "local_port": self.local_port_input.value()
        }
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.append_log(f'配置保存失败: {e}', 'error')
            
    def toggle_connection(self):
        if self.client_thread is None:
            self.start_connection()
        else:
            self.stop_connection()
            
    def start_connection(self):
        self.save_config()
        
        self.server_addr = self.server_addr_input.text().strip()
        if not self.server_addr:
            self.append_log('请填写服务器地址', 'error')
            return
        
        config = {
            "server_addr": self.server_addr,
            "server_port": self.server_port_input.value(),
            "local_port": self.local_port_input.value()
        }
        self.client_thread = ClientThread(config, self.log_emitter)
        self.client_thread.start()
        
        self.connect_button.setText('断开服务器')
        self.connect_button.setStyleSheet('''
            QPushButton {
                background-color: #f44336;
                color: white;
                font-size: 16px;
                font-weight: bold;
                padding: 15px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
        ''')
        
        self.server_addr_input.setEnabled(False)
        self.server_port_input.setEnabled(False)
        self.local_port_input.setEnabled(False)
        self.status_label.setText('状态: 连接中...')
        self.status_label.setStyleSheet('font-size: 12px; color: #FF9800; font-weight: bold;')
        
    def stop_connection(self):
        if self.client_thread:
            self.client_thread.stop()
            self.client_thread = None
            
        self.connect_button.setText('连接服务器')
        self.connect_button.setStyleSheet('''
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-size: 16px;
                font-weight: bold;
                padding: 15px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        ''')
        
        self.server_addr_input.setEnabled(True)
        self.server_port_input.setEnabled(True)
        self.local_port_input.setEnabled(True)
        self.status_label.setText('状态: 已断开')
        self.status_label.setStyleSheet('font-size: 12px; color: #666;')
        self.link_label.setText('未连接')
        self.link_label.setStyleSheet('font-size: 18px; font-weight: bold; color: #666;')
        self.copy_link_btn.setEnabled(False)
        self.append_log('连接已断开', 'warning')
        
    def on_port_allocated(self, port):
        self.public_port = port
        
        if ':' in self.server_addr and self.server_addr.startswith('['):
            link = f'{self.server_addr}:{port}'
        elif ':' in self.server_addr:
            link = f'[{self.server_addr}]:{port}'
        else:
            link = f'{self.server_addr}:{port}'
        
        self.link_label.setText(link)
        self.link_label.setStyleSheet('font-size: 18px; font-weight: bold; color: #4CAF50;')
        self.copy_link_btn.setEnabled(True)
        self.status_label.setText('状态: 已连接')
        self.status_label.setStyleSheet('font-size: 12px; color: #4CAF50; font-weight: bold;')
        
    def copy_link(self):
        if not self.server_addr or not self.public_port:
            return
        
        if ':' in self.server_addr and self.server_addr.startswith('['):
            link = f'{self.server_addr}:{self.public_port}'
        elif ':' in self.server_addr:
            link = f'[{self.server_addr}]:{self.public_port}'
        else:
            link = f'{self.server_addr}:{self.public_port}'
        
        clipboard = QApplication.clipboard()
        clipboard.setText(link)
        self.append_log(f'已复制链接: {link}', 'success')
        
    def append_log(self, message, level="info"):
        timestamp = get_timestamp()
        color_map = {
            "info": "#333333",
            "success": "#4CAF50",
            "warning": "#FF9800",
            "error": "#f44336"
        }
        color = color_map.get(level, "#333333")
        
        html = f'<span style="color:#999;">[{timestamp}]</span> <span style="color:{color};">{message}</span>'
        self.log_text.append(html)


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    window = ClientWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
