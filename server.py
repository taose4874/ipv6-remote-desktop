#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import socket
import threading
import json
import os
from datetime import datetime
from pathlib import Path
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QLabel, QLineEdit, QPushButton, 
                             QTextEdit, QGroupBox, QFormLayout, QSpinBox,
                             QMessageBox, QTableWidget, QTableWidgetItem, QHeaderView)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QColor


def get_config_path(filename):
    if sys.platform == 'win32':
        config_dir = Path(os.environ.get('APPDATA', Path.home() / 'AppData' / 'Roaming'))
    else:
        config_dir = Path.home() / '.config'
    app_dir = config_dir / 'IPv6Proxy'
    app_dir.mkdir(parents=True, exist_ok=True)
    return str(app_dir / filename)


CONFIG_FILE = get_config_path('config_server.json')
BUFFER_SIZE = 4096

DEFAULT_CONFIG = {
    "control_port": 7000,
    "proxy_ports": [25565]
}


def get_timestamp():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


class LogEmitter(QObject):
    log_signal = pyqtSignal(str, str)
    proxy_added = pyqtSignal(int, int)
    proxy_removed = pyqtSignal(int)


class ServerThread(QThread):
    def __init__(self, config, log_emitter):
        super().__init__()
        self.config = config
        self.log_emitter = log_emitter
        self.running = False
        self.client_control_socket = None
        self.client_connected = False
        self.lock = threading.Lock()
        self.proxy_listeners = {}
        self.pending_connections = {}
        self.pending_tunnels = {}
        
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
        try:
            tunnel_socket.settimeout(5.0)
            buffer = ''
            proxy_port = None
            
            while self.running:
                try:
                    data = tunnel_socket.recv(BUFFER_SIZE)
                    if not data:
                        break
                    
                    buffer += data.decode('utf-8', errors='ignore')
                    if '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        try:
                            msg = json.loads(line)
                            if msg.get('type') == 'TUNNEL_READY':
                                proxy_port = msg.get('proxy_port')
                                break
                        except:
                            pass
                except socket.timeout:
                    break
            
            if proxy_port is None:
                self.log('隧道连接未收到proxy_port，关闭', "warning")
                tunnel_socket.close()
                return
            
            with self.lock:
                if proxy_port not in self.pending_connections or not self.pending_connections[proxy_port]:
                    self.log(f'没有待处理的连接，关闭隧道 (端口: {proxy_port})', "warning")
                    tunnel_socket.close()
                    return
                game_socket = self.pending_connections[proxy_port].pop(0)
            
            self.log(f'建立隧道连接，端口: {proxy_port}', "info")
            
            thread1 = threading.Thread(target=self.forward_data, args=(game_socket, tunnel_socket, f'game->{proxy_port}'))
            thread2 = threading.Thread(target=self.forward_data, args=(tunnel_socket, game_socket, f'{proxy_port}->game'))
            
            thread1.daemon = True
            thread2.daemon = True
            thread1.start()
            thread2.start()
            
            while self.running and (thread1.is_alive() or thread2.is_alive()):
                time.sleep(0.1)
            
        except Exception as e:
            self.log(f'处理隧道连接错误: {e}', "error")
            
    def handle_proxy_connection(self, game_socket, addr, proxy_port):
        self.log(f'端口 {proxy_port} 收到连接: {addr[0]}:{addr[1]}', "info")
        
        with self.lock:
            if not self.client_connected or self.client_control_socket is None:
                self.log(f'客户端未连接，拒绝连接 (端口: {proxy_port})', "warning")
                game_socket.close()
                return
            
            if proxy_port not in self.pending_connections:
                self.pending_connections[proxy_port] = []
            self.pending_connections[proxy_port].append(game_socket)
            
        try:
            req_msg = {'type': 'NEW_CONNECTION', 'proxy_port': proxy_port}
            self.client_control_socket.sendall((json.dumps(req_msg) + '\n').encode('utf-8'))
            
        except Exception as e:
            self.log(f'发送连接请求错误: {e}', "error")
            game_socket.close()
            with self.lock:
                if proxy_port in self.pending_connections and game_socket in self.pending_connections[proxy_port]:
                    self.pending_connections[proxy_port].remove(game_socket)
                
    def handle_client_control(self, conn, addr):
        self.log(f'客户端连接: {addr[0]}:{addr[1]}', "success")
        
        with self.lock:
            self.client_control_socket = conn
            self.client_connected = True
            
        try:
            conn.settimeout(2.0)
            buffer = ''
            while self.running:
                try:
                    data = conn.recv(BUFFER_SIZE)
                    if not data:
                        break
                        
                    buffer += data.decode('utf-8', errors='ignore')
                        
                    while '\n' in buffer:
                        line, buffer = buffer.split('\n', 1)
                        line = line.strip()
                        if not line:
                            continue
                            
                        try:
                            msg = json.loads(line)
                            if msg.get('type') == 'REGISTER_PROXIES':
                                proxy_ports = msg.get('proxy_ports', [])
                                self.log(f'客户端注册端口: {proxy_ports}', "info")
                                self.start_proxy_listeners(proxy_ports)
                        except Exception as e:
                            self.log(f'处理消息错误: {e}', "error")
                except socket.timeout:
                    continue
                    
        except Exception as e:
            self.log(f'客户端连接错误: {e}', "error")
        finally:
            with self.lock:
                self.client_control_socket = None
                self.client_connected = False
                self.stop_all_proxy_listeners()
            
            try:
                conn.close()
            except:
                pass
            
            self.log(f'客户端断开: {addr[0]}', "warning")
            
    def start_proxy_listener(self, proxy_port):
        if proxy_port in self.proxy_listeners:
            return
            
        listener_socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        listener_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener_socket.settimeout(1.0)
        
        try:
            listener_socket.bind(('::', proxy_port))
            listener_socket.listen(128)
            self.proxy_listeners[proxy_port] = listener_socket
            self.log(f'开始监听端口: {proxy_port}', "info")
            self.log_emitter.proxy_added.emit(proxy_port, proxy_port)
            
            def listen_thread():
                while self.running and proxy_port in self.proxy_listeners:
                    try:
                        try:
                            game_socket, addr = listener_socket.accept()
                            thread = threading.Thread(
                                target=self.handle_proxy_connection,
                                args=(game_socket, addr, proxy_port)
                            )
                            thread.daemon = True
                            thread.start()
                        except socket.timeout:
                            continue
                    except Exception as e:
                        self.log(f'端口 {proxy_port} 监听错误: {e}', "error")
                        break
                        
                try:
                    listener_socket.close()
                except:
                    pass
                    
            thread = threading.Thread(target=listen_thread)
            thread.daemon = True
            thread.start()
            
        except Exception as e:
            self.log(f'监听端口 {proxy_port} 失败: {e}', "error")
            
    def start_proxy_listeners(self, proxy_ports):
        for port in proxy_ports:
            self.start_proxy_listener(port)
            
    def stop_all_proxy_listeners(self):
        for port in list(self.proxy_listeners.keys()):
            try:
                self.proxy_listeners[port].close()
            except:
                pass
            self.log_emitter.proxy_removed.emit(port)
        self.proxy_listeners.clear()
            
    def start_control_listener(self, control_port):
        server_socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.settimeout(1.0)
        
        try:
            server_socket.bind(('::', control_port))
            server_socket.listen(128)
            
            self.log(f'控制端口监听: [::]:{control_port}', "info")
            
            while self.running:
                try:
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
            try:
                server_socket.close()
            except:
                pass
            
    def run(self):
        self.running = True
        control_port = self.config.get('control_port', 7000)
        
        control_thread = threading.Thread(target=self.start_control_listener, args=(control_port,))
        control_thread.daemon = True
        control_thread.start()
        
        while self.running:
            self.msleep(100)
            
    def stop(self):
        self.running = False
        self.stop_all_proxy_listeners()
        self.wait()


class ServerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.server_thread = None
        self.log_emitter = LogEmitter()
        self.log_emitter.log_signal.connect(self.append_log)
        self.log_emitter.proxy_added.connect(self.add_proxy_to_table)
        self.log_emitter.proxy_removed.connect(self.remove_proxy_from_table)
        self.init_ui()
        self.load_config()
        
    def init_ui(self):
        self.setWindowTitle('IPv6 内网穿透 - 服务器端 (类似FRP)')
        self.setMinimumSize(900, 600)
        
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
        
        # 代理端口表格
        proxy_group = QGroupBox('代理端口')
        proxy_layout = QVBoxLayout()
        
        self.proxy_table = QTableWidget()
        self.proxy_table.setColumnCount(2)
        self.proxy_table.setHorizontalHeaderLabels(['公网端口', '状态'])
        self.proxy_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.proxy_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        proxy_layout.addWidget(self.proxy_table)
        
        proxy_group.setLayout(proxy_layout)
        main_layout.addWidget(proxy_group)
        
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
            except Exception as e:
                self.append_log(f'配置加载失败: {e}', "error")
                
    def save_config(self):
        config = {
            "control_port": self.control_port_input.value(),
            "proxy_ports": []
        }
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            self.append_log('配置已保存', "success")
        except Exception as e:
            self.append_log(f'配置保存失败: {e}', "error")
            
    def start_server(self):
        config = {
            "control_port": self.control_port_input.value()
        }
        self.server_thread = ServerThread(config, self.log_emitter)
        self.server_thread.start()
        
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.control_port_input.setEnabled(False)
        self.status_label.setText('状态: 运行中')
        self.status_label.setStyleSheet('font-size: 12px; color: #4CAF50; font-weight: bold;')
        
    def stop_server(self):
        if self.server_thread:
            self.server_thread.stop()
            self.server_thread = None
            
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.control_port_input.setEnabled(True)
        self.status_label.setText('状态: 已停止')
        self.status_label.setStyleSheet('font-size: 12px; color: #666;')
        self.proxy_table.setRowCount(0)
        self.append_log('服务已停止', "warning")
        
    def add_proxy_to_table(self, public_port, local_port):
        row = self.proxy_table.rowCount()
        self.proxy_table.insertRow(row)
        self.proxy_table.setItem(row, 0, QTableWidgetItem(str(public_port)))
        self.proxy_table.setItem(row, 1, QTableWidgetItem('监听中'))
        
    def remove_proxy_from_table(self, public_port):
        for row in range(self.proxy_table.rowCount()):
            if self.proxy_table.item(row, 0).text() == str(public_port):
                self.proxy_table.removeRow(row)
                break
        
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
    import time
    main()
