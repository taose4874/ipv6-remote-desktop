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
                             QTextEdit, QGroupBox, QFormLayout, QSpinBox,
                             QTableWidget, QTableWidgetItem, QHeaderView)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject
from PyQt6.QtGui import QFont, QColor


def get_config_path(filename):
    # 获取程序所在目录
    if getattr(sys, 'frozen', False):
        program_dir = Path(sys.executable).parent
    else:
        program_dir = Path(__file__).parent
    return str(program_dir / filename)


CONFIG_FILE = get_config_path('config_server.json')
BUFFER_SIZE = 4096

DEFAULT_CONFIG = {
    "control_port": 7000,
    "port_start": 25565,
    "port_end": 65535
}


def get_timestamp():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


class LogEmitter(QObject):
    log_signal = pyqtSignal(str, str)
    port_added = pyqtSignal(int, str, str)
    port_removed = pyqtSignal(int)
    server_addr_found = pyqtSignal(str)


class ClientSession:
    def __init__(self, conn, addr, session_id):
        self.conn = conn
        self.addr = addr
        self.session_id = session_id
        self.public_port = None
        self.local_port = None
        self.tunnel_socket = None
        self.running = False


class ServerThread(QThread):
    def __init__(self, config, log_emitter):
        super().__init__()
        self.config = config
        self.log_emitter = log_emitter
        self.running = False
        self.lock = threading.Lock()
        self.clients = {}
        self.client_counter = 0
        self.available_ports = []
        self.proxy_listeners = {}
        self.pending_connections = {}
        
    def log(self, message, level="info"):
        self.log_emitter.log_signal.emit(message, level)
        
    def init_ports(self):
        port_start = self.config.get('port_start', 25565)
        port_end = self.config.get('port_end', 65535)
        self.available_ports = list(range(port_start, port_end + 1))
        import random
        random.shuffle(self.available_ports)
        self.log(f'可用端口范围: {port_start} - {port_end}, 共 {len(self.available_ports)} 个端口', 'info')
        
    def allocate_port(self):
        with self.lock:
            if not self.available_ports:
                return None
            port = self.available_ports.pop(0)
            return port
            
    def release_port(self, port):
        import random
        with self.lock:
            if port:
                self.available_ports.append(port)
                random.shuffle(self.available_ports)
                self.log_emitter.port_removed.emit(port)
                
    def get_local_ipv6(self):
        try:
            hostname = socket.gethostname()
            addrs = socket.getaddrinfo(hostname, None, socket.AF_INET6)
            for addr in addrs:
                ip = addr[4][0]
                if not ip.startswith('::1') and not ip.startswith('fe80:'):
                    return ip
        except Exception as e:
            pass
        
        try:
            s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
            s.connect(('2001:4860:4860::8888', 80))
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith('::1') and not ip.startswith('fe80:'):
                return ip
        except Exception as e:
            pass
        
        return None
                
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
                
    def handle_tunnel_connection(self, tunnel_socket, addr, session_id):
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
                tunnel_socket.close()
                return
            
            with self.lock:
                if proxy_port not in self.pending_connections or not self.pending_connections[proxy_port]:
                    tunnel_socket.close()
                    return
                game_socket = self.pending_connections[proxy_port].pop(0)
            
            thread1 = threading.Thread(target=self.forward_data, args=(game_socket, tunnel_socket, f'game->{proxy_port}'))
            thread2 = threading.Thread(target=self.forward_data, args=(tunnel_socket, game_socket, f'{proxy_port}->game'))
            
            thread1.daemon = True
            thread2.daemon = True
            thread1.start()
            thread2.start()
            
            while self.running and (thread1.is_alive() or thread2.is_alive()):
                time.sleep(0.1)
            
        except Exception as e:
            pass
            
    def handle_proxy_connection(self, game_socket, addr, proxy_port):
        with self.lock:
            if proxy_port not in self.pending_connections:
                self.pending_connections[proxy_port] = []
            self.pending_connections[proxy_port].append(game_socket)
            
        try:
            # 通知所有相关的客户端有新连接
            with self.lock:
                for session_id, client in self.clients.items():
                    if client.public_port == proxy_port:
                        try:
                            req_msg = {'type': 'NEW_CONNECTION', 'proxy_port': proxy_port}
                            client.conn.sendall((json.dumps(req_msg) + '\n').encode('utf-8'))
                            break
                        except:
                            pass
            
        except Exception as e:
            game_socket.close()
            with self.lock:
                if proxy_port in self.pending_connections and game_socket in self.pending_connections[proxy_port]:
                    self.pending_connections[proxy_port].remove(game_socket)
                
    def handle_client_control(self, conn, addr):
        with self.lock:
            self.client_counter += 1
            session_id = self.client_counter
            
        client = ClientSession(conn, addr, session_id)
        
        with self.lock:
            self.clients[session_id] = client
            
        client_addr = addr[0]
        self.log(f'客户端连接: {client_addr}', 'success')
        
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
                            if msg.get('type') == 'REQUEST_PORT':
                                local_port = msg.get('local_port')
                                
                                public_port = self.allocate_port()
                                if public_port:
                                    client.public_port = public_port
                                    client.local_port = local_port
                                    client.running = True
                                    
                                    self.log(f'分配端口 {public_port} -> {client_addr}', 'success')
                                    self.log_emitter.port_added.emit(public_port, '已分配', client_addr)
                                    
                                    resp_msg = {'type': 'PORT_ALLOCATED', 'public_port': public_port}
                                    conn.sendall((json.dumps(resp_msg) + '\n').encode('utf-8'))
                                    
                                    self.start_proxy_listener(public_port)
                                else:
                                    self.log(f'{client_addr} 端口分配失败', 'error')
                                    resp_msg = {'type': 'PORT_ERROR', 'message': '没有可用端口'}
                                    conn.sendall((json.dumps(resp_msg) + '\n').encode('utf-8'))
                                    
                        except Exception as e:
                            self.log(f'处理消息错误: {e}', 'error')
                except socket.timeout:
                    continue
                    
        except Exception as e:
            self.log(f'{client_addr} 连接错误: {e}', 'error')
        finally:
            with self.lock:
                if session_id in self.clients:
                    del self.clients[session_id]
            
            # 释放端口
            if client.public_port:
                self.stop_proxy_listener(client.public_port)
                self.release_port(client.public_port)
            
            try:
                conn.close()
            except:
                pass
            
            self.log(f'客户端断开: {client_addr}', 'warning')
            
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
                        break
                    
            thread = threading.Thread(target=listen_thread)
            thread.daemon = True
            thread.start()
            
        except Exception as e:
            self.log(f'监听端口 {proxy_port} 失败: {e}', 'error')
            self.release_port(proxy_port)
            
    def stop_proxy_listener(self, proxy_port):
        if proxy_port in self.proxy_listeners:
            try:
                self.proxy_listeners[proxy_port].close()
            except:
                pass
            del self.proxy_listeners[proxy_port]
            
    def start_control_listener(self, control_port):
        server_socket = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.settimeout(1.0)
        
        try:
            server_socket.bind(('::', control_port))
            server_socket.listen(128)
            
            ipv6 = self.get_local_ipv6()
            if ipv6:
                self.log_emitter.server_addr_found.emit(ipv6)
                self.log(f'服务端IPv6: {ipv6}', 'info')
            
            self.log(f'控制端口监听: [::]:{control_port}', 'info')
            
            while self.running:
                try:
                    try:
                        conn, addr = server_socket.accept()
                        
                        # 新连接都作为客户端控制连接处理
                        client_thread = threading.Thread(
                            target=self.handle_client_control,
                            args=(conn, addr)
                        )
                        client_thread.daemon = True
                        client_thread.start()
                        
                    except socket.timeout:
                        continue
                        
                except Exception as e:
                    self.log(f'接受连接错误: {e}', 'error')
                    
        except Exception as e:
            self.log(f'控制端口监听失败: {e}', 'error')
        finally:
            try:
                server_socket.close()
            except:
                pass
            
    def run(self):
        self.running = True
        self.init_ports()
        control_port = self.config.get('control_port', 7000)
        
        control_thread = threading.Thread(target=self.start_control_listener, args=(control_port,))
        control_thread.daemon = True
        control_thread.start()
        
        while self.running:
            self.msleep(100)
            
    def stop(self):
        self.running = False
        for port in list(self.proxy_listeners.keys()):
            self.stop_proxy_listener(port)
        self.wait()


class ServerWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.server_thread = None
        self.log_emitter = LogEmitter()
        self.log_emitter.log_signal.connect(self.append_log)
        self.log_emitter.port_added.connect(self.add_port_to_table)
        self.log_emitter.port_removed.connect(self.remove_port_from_table)
        self.log_emitter.server_addr_found.connect(self.on_server_addr_found)
        self.server_addr = ""
        self.init_ui()
        self.load_config()
        
    def init_ui(self):
        self.setWindowTitle('IPv6 内网穿透 - 服务端')
        self.setMinimumSize(700, 550)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        
        config_group = QGroupBox('配置')
        config_layout = QFormLayout()
        
        self.control_port_input = QSpinBox()
        self.control_port_input.setRange(1, 65535)
        self.control_port_input.setValue(7000)
        config_layout.addRow('控制端口:', self.control_port_input)
        
        self.port_start_input = QSpinBox()
        self.port_start_input.setRange(1, 65535)
        self.port_start_input.setValue(25565)
        self.port_start_input.setMinimumWidth(100)
        config_layout.addRow('端口起始:', self.port_start_input)
        
        self.port_end_input = QSpinBox()
        self.port_end_input.setRange(1, 65535)
        self.port_end_input.setValue(65535)
        self.port_end_input.setMinimumWidth(100)
        config_layout.addRow('端口结束:', self.port_end_input)
        
        config_group.setLayout(config_layout)
        main_layout.addWidget(config_group)
        
        addr_group = QGroupBox('服务端地址')
        addr_layout = QHBoxLayout()
        
        self.server_addr_label = QLabel('启动后显示')
        self.server_addr_label.setStyleSheet('font-size: 12px; color: #666;')
        addr_layout.addWidget(self.server_addr_label)
        
        self.copy_addr_btn = QPushButton('复制地址')
        self.copy_addr_btn.clicked.connect(self.copy_server_addr)
        self.copy_addr_btn.setEnabled(False)
        addr_layout.addWidget(self.copy_addr_btn)
        
        addr_group.setLayout(addr_layout)
        main_layout.addWidget(addr_group)
        
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
        
        port_group = QGroupBox('已分配端口')
        port_layout = QVBoxLayout()
        
        self.port_table = QTableWidget()
        self.port_table.setColumnCount(3)
        self.port_table.setHorizontalHeaderLabels(['公网端口', '客户端地址', '状态'])
        self.port_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.port_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.port_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        port_layout.addWidget(self.port_table)
        
        port_group.setLayout(port_layout)
        main_layout.addWidget(port_group)
        
        log_group = QGroupBox('日志')
        log_layout = QVBoxLayout()
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont('Consolas', 10))
        log_layout.addWidget(self.log_text)
        
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)
        
        self.status_label = QLabel('状态: 未启动')
        self.status_label.setStyleSheet('font-size: 12px; color: #666;')
        main_layout.addWidget(self.status_label)
        
    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                self.control_port_input.setValue(config.get('control_port', 7000))
                self.port_start_input.setValue(config.get('port_start', 25565))
                self.port_end_input.setValue(config.get('port_end', 65535))
            except Exception as e:
                self.append_log(f'配置加载失败: {e}', 'error')
                
    def save_config(self):
        config = {
            "control_port": self.control_port_input.value(),
            "port_start": self.port_start_input.value(),
            "port_end": self.port_end_input.value()
        }
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            self.append_log('配置已保存', 'success')
        except Exception as e:
            self.append_log(f'配置保存失败: {e}', 'error')
            
    def on_server_addr_found(self, addr):
        self.server_addr = addr
        if ':' in addr and not addr.startswith('['):
            display_addr = f'[{addr}]'
        else:
            display_addr = addr
        self.server_addr_label.setText(display_addr)
        self.server_addr_label.setStyleSheet('font-size: 12px; color: #4CAF50; font-weight: bold;')
        self.copy_addr_btn.setEnabled(True)
        
    def copy_server_addr(self):
        if not self.server_addr:
            return
        clipboard = QApplication.clipboard()
        clipboard.setText(self.server_addr)
        self.append_log(f'已复制服务器地址: {self.server_addr}', 'success')
            
    def start_server(self):
        if self.port_start_input.value() >= self.port_end_input.value():
            self.append_log('端口范围设置错误', 'error')
            return
            
        config = {
            "control_port": self.control_port_input.value(),
            "port_start": self.port_start_input.value(),
            "port_end": self.port_end_input.value()
        }
        self.server_thread = ServerThread(config, self.log_emitter)
        self.server_thread.start()
        
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.control_port_input.setEnabled(False)
        self.port_start_input.setEnabled(False)
        self.port_end_input.setEnabled(False)
        self.status_label.setText('状态: 运行中')
        self.status_label.setStyleSheet('font-size: 12px; color: #4CAF50; font-weight: bold;')
        
    def stop_server(self):
        if self.server_thread:
            self.server_thread.stop()
            self.server_thread = None
            
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.control_port_input.setEnabled(True)
        self.port_start_input.setEnabled(True)
        self.port_end_input.setEnabled(True)
        self.status_label.setText('状态: 已停止')
        self.status_label.setStyleSheet('font-size: 12px; color: #666;')
        self.server_addr_label.setText('启动后显示')
        self.server_addr_label.setStyleSheet('font-size: 12px; color: #666;')
        self.copy_addr_btn.setEnabled(False)
        self.port_table.setRowCount(0)
        self.append_log('服务已停止', 'warning')
        
    def add_port_to_table(self, public_port, status, client_addr):
        row = self.port_table.rowCount()
        self.port_table.insertRow(row)
        self.port_table.setItem(row, 0, QTableWidgetItem(str(public_port)))
        self.port_table.setItem(row, 1, QTableWidgetItem(client_addr))
        self.port_table.setItem(row, 2, QTableWidgetItem(status))
        
    def remove_port_from_table(self, public_port):
        for row in range(self.port_table.rowCount()):
            if self.port_table.item(row, 0).text() == str(public_port):
                self.port_table.removeRow(row)
                break
        
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
    
    window = ServerWindow()
    window.show()
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
