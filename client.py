#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import socket
import threading
import json
import os
import time
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                             QTextEdit, QGroupBox, QFormLayout, QSpinBox,
                             QMessageBox, QSplitter)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QTextCharFormat, QColor


CONFIG_FILE = 'config_client.json'
BUFFER_SIZE = 4096

DEFAULT_CONFIG = {
    "server_addr": "你的公网IPv6地址",
    "server_port": 7000,
    "local_port": 25565
}


def get_timestamp():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


class LogEmitter(QObject):
    log_signal = pyqtSignal(str, str)


class ClientThread(QThread):
    def __init__(self, config, log_emitter):
        super().__init__()
        self.config = config
        self.log_emitter = log_emitter
        self.running = False
        
    def log(self, message, level="info"):
        self.log_emitter.log_signal.emit(message, level)
        
    def forward_data(self, src, dst, name):
        try:
            while self.running:
                data = src.recv(BUFFER_SIZE)
                if not data:
                    break
                dst.sendall(data)
        except Exception as e:
            self.log(f'转发错误 [{name}]: {e}', "error")
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
            local_socket.connect(('::1', local_port))
            self.log(f'连接本地端口: {local_port}', "info")
            
            thread1 = threading.Thread(target=self.forward_data, args=(tunnel_socket, local_socket, 'tunnel->local'))
            thread2 = threading.Thread(target=self.forward_data, args=(local_socket, tunnel_socket, 'local->tunnel'))
            
            thread1.daemon = True
            thread2.daemon = True
            thread1.start()
            thread2.start()
            
            thread1.join()
            thread2.join()
            
        except Exception as e:
            self.log(f'处理隧道错误: {e}', "error")
            try:
                tunnel_socket.close()
            except:
                pass
                
    def connect_to_server(self):
        server_addr = self.config['server_addr']
        server_port = self.config['server_port']
        local_port = self.config['local_port']
        
        while self.running:
            try:
                control_socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                self.log(f'正在连接服务器: {server_addr}:{server_port}', "info")
                control_socket.connect((server_addr, server_port))
                self.log('连接服务器成功！', "success")
                
                buffer = ''
                while self.running:
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
                                self.log('收到新连接请求！', "info")
                                    
                                tunnel_socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
                                tunnel_socket.connect((server_addr, server_port))
                                    
                                tunnel_thread = threading.Thread(
                                    target=self.handle_tunnel,
                                    args=(tunnel_socket, local_port)
                                )
                                tunnel_thread.daemon = True
                                tunnel_thread.start()
                                    
                        except Exception as e:
                            self.log(f'处理消息错误: {e}', "error")
                            
            except Exception as e:
                self.log(f'连接服务器失败: {e}', "error")
                self.log('5秒后重试...', "warning")
                if self.running:
                    time.sleep(5)
                continue
            
    def run(self):
        self.running = True
        self.connect_to_server()
        
    def stop(self):
        self.running = False
        self.wait()


class ClientWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.client_thread = None
        self.log_emitter = LogEmitter()
        self.log_emitter.log_signal.connect(self.append_log)
        self.init_ui()
        self.load_config()
        
    def init_ui(self):
        self.setWindowTitle('IPv6 内网穿透 - 客户端')
        self.setMinimumSize(800, 600)
        
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
        config_layout.addRow('本地端口:', self.local_port_input)
        
        config_group.setLayout(config_layout)
        main_layout.addWidget(config_group)
        
        # 控制按钮
        button_layout = QHBoxLayout()
        
        self.start_button = QPushButton('连接服务器')
        self.start_button.setStyleSheet('''
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-size: 14px;
                font-weight: bold;
                padding: 10px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
        ''')
        self.start_button.clicked.connect(self.start_client)
        button_layout.addWidget(self.start_button)
        
        self.stop_button = QPushButton('断开连接')
        self.stop_button.setStyleSheet('''
            QPushButton {
                background-color: #f44336;
                color: white;
                font-size: 14px;
                font-weight: bold;
                padding: 10px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #da190b;
            }
        ''')
        self.stop_button.clicked.connect(self.stop_client)
        self.stop_button.setEnabled(False)
        button_layout.addWidget(self.stop_button)
        
        self.save_config_button = QPushButton('保存配置')
        self.save_config_button.setStyleSheet('''
            QPushButton {
                background-color: #2196F3;
                color: white;
                font-size: 14px;
                font-weight: bold;
                padding: 10px;
                border-radius: 5px;
            }
            QPushButton:hover {
                background-color: #0b7dda;
            }
        ''')
        self.save_config_button.clicked.connect(self.save_config)
        button_layout.addWidget(self.save_config_button)
        
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
                self.server_addr_input.setText(config.get('server_addr', '你的公网IPv6地址'))
                self.server_port_input.setValue(config.get('server_port', 7000))
                self.local_port_input.setValue(config.get('local_port', 25565))
            except Exception as e:
                self.append_log(f'配置加载失败: {e}', "error")
                
    def save_config(self):
        config = {
            "server_addr": self.server_addr_input.text(),
            "server_port": self.server_port_input.value(),
            "local_port": self.local_port_input.value()
        }
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            self.append_log('配置已保存', "success")
        except Exception as e:
            self.append_log(f'配置保存失败: {e}', "error")
            
    def start_client(self):
        config = {
            "server_addr": self.server_addr_input.text(),
            "server_port": self.server_port_input.value(),
            "local_port": self.local_port_input.value()
        }
        self.client_thread = ClientThread(config, self.log_emitter)
        self.client_thread.start()
        
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.server_addr_input.setEnabled(False)
        self.server_port_input.setEnabled(False)
        self.local_port_input.setEnabled(False)
        self.status_label.setText('状态: 连接中...')
        self.status_label.setStyleSheet('font-size: 12px; color: #FF9800; font-weight: bold;')
        
    def stop_client(self):
        if self.client_thread:
            self.client_thread.stop()
            self.client_thread = None
            
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.server_addr_input.setEnabled(True)
        self.server_port_input.setEnabled(True)
        self.local_port_input.setEnabled(True)
        self.status_label.setText('状态: 已断开')
        self.status_label.setStyleSheet('font-size: 12px; color: #666;')
        self.append_log('连接已断开', "warning")
        
    def append_log(self, message, level="info"):
        timestamp = get_timestamp()
        color_map = {
            "info": "#333333",
            "success": "#4CAF50",
            "warning": "#FF9800",
            "error": "#F44336"
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
