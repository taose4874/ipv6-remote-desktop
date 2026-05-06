#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import socket
import threading
import json
import os
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                             QTextEdit, QGroupBox, QFormLayout, QSpinBox,
                             QMessageBox, QSplitter)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QTextCharFormat, QColor


CONFIG_FILE = 'config_server.json'
BUFFER_SIZE = 4096

DEFAULT_CONFIG = {
    "control_port": 7000,
    "listen_port": 25565
}


def get_timestamp():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


class LogEmitter(QObject):
    log_signal = pyqtSignal(str, str)


class ServerThread(QThread):
    def __init__(self, config, log_emitter):
        super().__init__()
        self.config = config
        self.log_emitter = log_emitter
        self.running = False
        self.client_control_socket = None
        self.client_connected = False
        self.pending_connection = None
        self.lock = threading.Lock()
        
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
                
    def handle_tunnel_connection(self, tunnel_socket, addr):
        with self.lock:
            if self.pending_connection is None:
                self.log('没有待处理的连接，关闭隧道', "warning")
                tunnel_socket.close()
                return
            game_socket = self.pending_connection
            self.pending_connection = None
            
        try:
            thread1 = threading.Thread(target=self.forward_data, args=(game_socket, tunnel_socket, 'game->tunnel'))
            thread2 = threading.Thread(target=self.forward_data, args=(tunnel_socket, game_socket, 'tunnel->game'))
            
            thread1.daemon = True
            thread2.daemon = True
            thread1.start()
            thread2.start()
            
            thread1.join()
            thread2.join()
            
        except Exception as e:
            self.log(f'处理隧道连接错误: {e}', "error")
            
    def handle_game_connection(self, game_socket, addr):
        self.log(f'游戏连接来自: {addr[0]}:{addr[1]}', "info")
        
        with self.lock:
            if not self.client_connected or self.client_control_socket is None:
                self.log('客户端未连接，拒绝游戏连接', "warning")
                game_socket.close()
                return
            self.pending_connection = game_socket
            
        try:
            req_msg = {'type': 'NEW_CONNECTION'}
            self.client_control_socket.sendall((json.dumps(req_msg) + '\n').encode('utf-8'))
            
        except Exception as e:
            self.log(f'发送连接请求错误: {e}', "error")
            game_socket.close()
            with self.lock:
                self.pending_connection = None
                
    def handle_client_control(self, conn, addr):
        self.log(f'客户端连接: {addr[0]}:{addr[1]}', "success")
        
        with self.lock:
            self.client_control_socket = conn
            self.client_connected = True
            
        try:
            while self.running:
                data = conn.recv(BUFFER_SIZE)
                if not data:
                    break
                    
        except Exception as e:
            self.log(f'客户端连接错误: {e}', "error")
        finally:
            with self.lock:
                self.client_control_socket = None
                self.client_connected = False
            
            try:
                conn.close()
            except:
                pass
            
            self.log(f'客户端断开: {addr[0]}', "warning")
            
    def start_game_listener(self, listen_port):
        listen_socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        listen_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            listen_socket.bind(('::', listen_port))
            listen_socket.listen(128)
            
            self.log(f'游戏端口监听: [::]:{listen_port}', "info")
            
            while self.running:
                try:
                    listen_socket.settimeout(1.0)
                    try:
                        game_socket, addr = listen_socket.accept()
                        game_thread = threading.Thread(
                            target=self.handle_game_connection,
                            args=(game_socket, addr)
                        )
                        game_thread.daemon = True
                        game_thread.start()
                    except socket.timeout:
                        continue
                    
                except Exception as e:
                    self.log(f'接受游戏连接错误: {e}', "error")
                    
        except Exception as e:
            self.log(f'游戏端口监听失败: {e}', "error")
        finally:
            listen_socket.close()
            
    def start_control_listener(self, control_port):
        server_socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            server_socket.bind(('::', control_port))
            server_socket.listen(128)
            
            self.log(f'控制端口监听: [::]:{control_port}', "info")
            
            while self.running:
                try:
                    server_socket.settimeout(1.0)
                    try:
                        conn, addr = server_socket.accept()
                        
                        with self.lock:
                            if not self.client_connected:
                                client_thread = threading.Thread(
                                    target=self.handle_client_control,
                                    args=(conn, addr)
                                )
                                client_thread.daemon = True
                                client_thread.start()
                            else:
                                tunnel_thread = threading.Thread(
                                    target=self.handle_tunnel_connection,
                                    args=(conn, addr)
                                )
                                tunnel_thread.daemon = True
                                tunnel_thread.start()
                    except socket.timeout:
                        continue
                        
                except Exception as e:
                    self.log(f'接受控制连接错误: {e}', "error")
                    
        except Exception as e:
            self.log(f'控制端口监听失败: {e}', "error")
        finally:
            server_socket.close()
            
    def run(self):
        self.running = True
        control_port = self.config.get('control_port', 7000)
        listen_port = self.config.get('listen_port', 25565)
        
        control_thread = threading.Thread(target=self.start_control_listener, args=(control_port,))
        control_thread.daemon = True
        control_thread.start()
        
        game_thread = threading.Thread(target=self.start_game_listener, args=(listen_port,))
        game_thread.daemon = True
        game_thread.start()
        
        while self.running:
            self.msleep(100)
            
    def stop(self):
        self.running = False
        self.wait()


class ServerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.server_thread = None
        self.log_emitter = LogEmitter()
        self.log_emitter.log_signal.connect(self.append_log)
        self.init_ui()
        self.load_config()
        
    def init_ui(self):
        self.setWindowTitle('IPv6 内网穿透 - 服务器端')
        self.setMinimumSize(800, 600)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        
        # 配置区域
        config_group = QGroupBox('配置')
        config_layout = QFormLayout()
        
        self.control_port_input = QSpinBox()
        self.control_port_input.setRange(1, 65535)
        self.control_port_input.setValue(7000)
        config_layout.addRow('控制端口:', self.control_port_input)
        
        self.listen_port_input = QSpinBox()
        self.listen_port_input.setRange(1, 65535)
        self.listen_port_input.setValue(25565)
        config_layout.addRow('游戏端口:', self.listen_port_input)
        
        config_group.setLayout(config_layout)
        main_layout.addWidget(config_group)
        
        # 控制按钮
        button_layout = QHBoxLayout()
        
        self.start_button = QPushButton('启动服务')
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
        self.start_button.clicked.connect(self.start_server)
        button_layout.addWidget(self.start_button)
        
        self.stop_button = QPushButton('停止服务')
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
        self.stop_button.clicked.connect(self.stop_server)
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
        self.status_label = QLabel('状态: 未启动')
        self.status_label.setStyleSheet('font-size: 12px; color: #666;')
        main_layout.addWidget(self.status_label)
        
    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                self.control_port_input.setValue(config.get('control_port', 7000))
                self.listen_port_input.setValue(config.get('listen_port', 25565))
            except Exception as e:
                self.append_log(f'配置加载失败: {e}', "error")
                
    def save_config(self):
        config = {
            "control_port": self.control_port_input.value(),
            "listen_port": self.listen_port_input.value()
        }
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            self.append_log('配置已保存', "success")
        except Exception as e:
            self.append_log(f'配置保存失败: {e}', "error")
            
    def start_server(self):
        config = {
            "control_port": self.control_port_input.value(),
            "listen_port": self.listen_port_input.value()
        }
        self.server_thread = ServerThread(config, self.log_emitter)
        self.server_thread.start()
        
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.control_port_input.setEnabled(False)
        self.listen_port_input.setEnabled(False)
        self.status_label.setText('状态: 运行中')
        self.status_label.setStyleSheet('font-size: 12px; color: #4CAF50; font-weight: bold;')
        
    def stop_server(self):
        if self.server_thread:
            self.server_thread.stop()
            self.server_thread = None
            
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.control_port_input.setEnabled(True)
        self.listen_port_input.setEnabled(True)
        self.status_label.setText('状态: 已停止')
        self.status_label.setStyleSheet('font-size: 12px; color: #666;')
        self.append_log('服务已停止', "warning")
        
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
    
    window = ServerWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
