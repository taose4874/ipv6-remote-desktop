#!/usr/bin/env python3
import sys
import os
import base64
from io import BytesIO

if os.path.exists(os.path.join(os.path.dirname(__file__), 'common')):
    sys.path.insert(0, os.path.dirname(__file__))

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QSpinBox, QComboBox, QSplitter,
    QListWidget, QListWidgetItem, QGroupBox, QSlider, QMessageBox,
    QStatusBar, QFrame
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QPixmap, QImage, QPainter, QColor, QFont, QIcon

from screen_capture import ScreenCapture
from network import NetworkClient
from remote_control import RemoteController
from common import Message, MessageType

class ModernButton(QPushButton):
    def __init__(self, text, color="#3b82f6"):
        super().__init__(text)
        self.color = color
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 8px;
                font-size: 14px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: #2563eb;
            }}
            QPushButton:pressed {{
                background-color: #1d4ed8;
            }}
            QPushButton:disabled {{
                background-color: #9ca3af;
            }}
        """)

class ScreenDisplay(QLabel):
    mouse_event = pyqtSignal(int, int, str, bool)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(640, 480)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("""
            QLabel {
                background-color: #1f2937;
                border: 2px solid #374151;
                border-radius: 8px;
            }
        """)
        self.setMouseTracking(True)
        self.original_pixmap = None
        self.last_pos = None

    def set_frame(self, frame_data: bytes):
        try:
            image = QImage.fromData(frame_data)
            if not image.isNull():
                self.original_pixmap = QPixmap.fromImage(image)
                self.update_display()
        except:
            pass

    def update_display(self):
        if self.original_pixmap:
            scaled = self.original_pixmap.scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.setPixmap(scaled)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_display()

    def mousePressEvent(self, event):
        if self.original_pixmap:
            pos = self.map_to_original(event.position().x(), event.position().y())
            btn = 'left' if event.button() == Qt.MouseButton.LeftButton else 'right'
            self.mouse_event.emit(int(pos.x()), int(pos.y()), btn, True)

    def mouseReleaseEvent(self, event):
        if self.original_pixmap:
            pos = self.map_to_original(event.position().x(), event.position().y())
            btn = 'left' if event.button() == Qt.MouseButton.LeftButton else 'right'
            self.mouse_event.emit(int(pos.x()), int(pos.y()), btn, False)

    def mouseMoveEvent(self, event):
        if self.original_pixmap and event.buttons() == Qt.MouseButton.LeftButton:
            pos = self.map_to_original(event.position().x(), event.position().y())
            self.mouse_event.emit(int(pos.x()), int(pos.y()), 'move', True)

    def map_to_original(self, x: float, y: float):
        if not self.original_pixmap or not self.pixmap():
            return x, y

        scaled = self.pixmap()
        scale_x = self.original_pixmap.width() / scaled.width()
        scale_y = self.original_pixmap.height() / scaled.height()

        offset_x = (self.width() - scaled.width()) / 2
        offset_y = (self.height() - scaled.height()) / 2

        return (x - offset_x) * scale_x, (y - offset_y) * scale_y

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("IPv6 远程桌面控制")
        self.setMinimumSize(1200, 800)

        self.network = NetworkClient()
        self.screen_capture = ScreenCapture()
        self.remote_controller = RemoteController()

        self.current_group = "default"
        self.username = ""
        self.connected_users = []
        self.selected_user = None
        self.is_sharing = False
        self.is_controlling = False

        self.setup_ui()
        self.setup_connections()

    def setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(20)

        left_panel = self.create_left_panel()
        right_panel = self.create_right_panel()

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)

        main_layout.addWidget(splitter)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("未连接")

        self.apply_dark_theme()

    def create_left_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)

        title = QLabel("控制面板")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        connect_group = QGroupBox("服务器连接")
        connect_layout = QVBoxLayout()

        server_layout = QHBoxLayout()
        server_layout.addWidget(QLabel("地址:"))
        self.server_host = QLineEdit("::1")
        server_layout.addWidget(self.server_host)
        connect_layout.addLayout(server_layout)

        port_layout = QHBoxLayout()
        port_layout.addWidget(QLabel("端口:"))
        self.server_port = QSpinBox()
        self.server_port.setRange(1, 65535)
        self.server_port.setValue(8888)
        port_layout.addWidget(self.server_port)
        connect_layout.addLayout(port_layout)

        self.connect_btn = ModernButton("连接")
        self.disconnect_btn = ModernButton("断开", "#ef4444")
        self.disconnect_btn.setEnabled(False)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.connect_btn)
        btn_layout.addWidget(self.disconnect_btn)
        connect_layout.addLayout(btn_layout)

        connect_group.setLayout(connect_layout)
        layout.addWidget(connect_group)

        user_group = QGroupBox("用户信息")
        user_layout = QVBoxLayout()

        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("用户名:"))
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("输入用户名")
        name_layout.addWidget(self.username_input)
        user_layout.addLayout(name_layout)

        group_layout = QHBoxLayout()
        group_layout.addWidget(QLabel("群组:"))
        self.group_input = QLineEdit("default")
        group_layout.addWidget(self.group_input)
        user_layout.addLayout(group_layout)

        self.join_group_btn = ModernButton("加入群组")
        self.join_group_btn.setEnabled(False)
        user_layout.addWidget(self.join_group_btn)

        user_group.setLayout(user_layout)
        layout.addWidget(user_group)

        users_group = QGroupBox("在线用户")
        users_layout = QVBoxLayout()
        self.users_list = QListWidget()
        users_layout.addWidget(self.users_list)
        users_group.setLayout(users_layout)
        layout.addWidget(users_group)

        control_group = QGroupBox("控制")
        control_layout = QVBoxLayout()

        self.share_btn = ModernButton("分享屏幕", "#10b981")
        self.share_btn.setEnabled(False)
        self.stop_share_btn = ModernButton("停止分享", "#f59e0b")
        self.stop_share_btn.setEnabled(False)
        self.control_btn = ModernButton("远程控制", "#3b82f6")
        self.control_btn.setEnabled(False)
        self.stop_control_btn = ModernButton("停止控制", "#ef4444")
        self.stop_control_btn.setEnabled(False)

        control_layout.addWidget(self.share_btn)
        control_layout.addWidget(self.stop_share_btn)
        control_layout.addWidget(self.control_btn)
        control_layout.addWidget(self.stop_control_btn)

        control_group.setLayout(control_layout)
        layout.addWidget(control_group)

        settings_group = QGroupBox("设置")
        settings_layout = QVBoxLayout()

        quality_layout = QHBoxLayout()
        quality_layout.addWidget(QLabel("画质:"))
        self.quality_slider = QSlider(Qt.Orientation.Horizontal)
        self.quality_slider.setRange(10, 100)
        self.quality_slider.setValue(50)
        quality_layout.addWidget(self.quality_slider)
        settings_layout.addLayout(quality_layout)

        fps_layout = QHBoxLayout()
        fps_layout.addWidget(QLabel("FPS:"))
        self.fps_slider = QSlider(Qt.Orientation.Horizontal)
        self.fps_slider.setRange(1, 60)
        self.fps_slider.setValue(15)
        fps_layout.addWidget(self.fps_slider)
        settings_layout.addLayout(fps_layout)

        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)

        layout.addStretch()

        return panel

    def create_right_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)

        title = QLabel("远程桌面")
        title.setFont(QFont("Arial", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        self.screen_display = ScreenDisplay()
        layout.addWidget(self.screen_display)

        info_layout = QHBoxLayout()
        self.status_label = QLabel("等待连接...")
        self.status_label.setStyleSheet("color: #9ca3af;")
        info_layout.addWidget(self.status_label)
        info_layout.addStretch()
        layout.addLayout(info_layout)

        return panel

    def setup_connections(self):
        self.connect_btn.clicked.connect(self.connect_to_server)
        self.disconnect_btn.clicked.connect(self.disconnect_from_server)
        self.join_group_btn.clicked.connect(self.join_group)

        self.share_btn.clicked.connect(self.start_sharing)
        self.stop_share_btn.clicked.connect(self.stop_sharing)
        self.control_btn.clicked.connect(self.start_control)
        self.stop_control_btn.clicked.connect(self.stop_control)

        self.quality_slider.valueChanged.connect(
            lambda v: self.screen_capture.set_quality(v)
        )
        self.fps_slider.valueChanged.connect(
            lambda v: self.screen_capture.set_fps(v)
        )

        self.network.connected.connect(self.on_connected)
        self.network.disconnected.connect(self.on_disconnected)
        self.network.error_occurred.connect(self.on_error)
        self.network.message_received.connect(self.on_message)
        self.network.user_list_updated.connect(self.on_user_list)

        self.screen_capture.frame_ready.connect(self.on_screen_frame)
        self.screen_display.mouse_event.connect(self.on_mouse_event)

        self.users_list.itemClicked.connect(self.on_user_selected)

    def connect_to_server(self):
        host = self.server_host.text()
        port = self.server_port.value()
        if self.network.connect_to_server(host, port):
            self.status_bar.showMessage(f"已连接到 [{host}]:{port}")

    def disconnect_from_server(self):
        self.network.disconnect()

    def join_group(self):
        username = self.username_input.text() or "Anonymous"
        group = self.group_input.text() or "default"
        self.username = username
        self.current_group = group
        self.network.join_group(group, username)

    def start_sharing(self):
        if self.selected_user:
            self.is_sharing = True
            self.screen_capture.start()
            self.share_btn.setEnabled(False)
            self.stop_share_btn.setEnabled(True)
            self.status_label.setText(f"正在分享屏幕给 {self.selected_user['username']}")

    def stop_sharing(self):
        self.is_sharing = False
        self.screen_capture.stop()
        self.share_btn.setEnabled(True)
        self.stop_share_btn.setEnabled(False)
        self.status_label.setText("已停止分享")

    def start_control(self):
        if self.selected_user:
            self.is_controlling = True
            self.control_btn.setEnabled(False)
            self.stop_control_btn.setEnabled(True)
            self.status_label.setText(f"正在控制 {self.selected_user['username']}")

    def stop_control(self):
        self.is_controlling = False
        self.control_btn.setEnabled(True)
        self.stop_control_btn.setEnabled(False)
        self.status_label.setText("已停止控制")

    def on_connected(self):
        self.connect_btn.setEnabled(False)
        self.disconnect_btn.setEnabled(True)
        self.join_group_btn.setEnabled(True)
        self.status_bar.showMessage("已连接")

    def on_disconnected(self):
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)
        self.join_group_btn.setEnabled(False)
        self.share_btn.setEnabled(False)
        self.stop_share_btn.setEnabled(False)
        self.control_btn.setEnabled(False)
        self.stop_control_btn.setEnabled(False)
        self.is_sharing = False
        self.is_controlling = False
        self.screen_capture.stop()
        self.status_bar.showMessage("已断开")
        self.status_label.setText("等待连接...")

    def on_error(self, error_msg: str):
        QMessageBox.critical(self, "错误", error_msg)
        self.status_bar.showMessage(error_msg)

    def on_message(self, msg: Message):
        if msg.msg_type == MessageType.SCREEN_FRAME:
            frame_data = base64.b64decode(msg.data['frame'])
            self.screen_display.set_frame(frame_data)
        elif msg.msg_type == MessageType.MOUSE_EVENT:
            self.remote_controller.handle_mouse_event(
                msg.data['x'], msg.data['y'],
                msg.data['button'], msg.data['pressed']
            )
        elif msg.msg_type == MessageType.KEYBOARD_EVENT:
            self.remote_controller.handle_keyboard_event(
                msg.data['key'], msg.data['pressed']
            )

    def on_user_list(self, users: list):
        self.connected_users = users
        self.users_list.clear()
        for user in users:
            item_text = f"{user['username']} ({user['id']})"
            if user['group']:
                item_text += f" - {user['group']}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.ItemDataRole.UserRole, user)
            self.users_list.addItem(item)

    def on_screen_frame(self, frame_data: bytes):
        if self.is_sharing and self.selected_user:
            self.network.send_screen_frame(frame_data, self.selected_user['id'])

    def on_mouse_event(self, x: int, y: int, button: str, pressed: bool):
        if self.is_controlling and self.selected_user:
            if button != 'move':
                self.network.send_mouse_event(x, y, button, pressed, self.selected_user['id'])

    def on_user_selected(self, item):
        self.selected_user = item.data(Qt.ItemDataRole.UserRole)
        self.share_btn.setEnabled(True)
        self.control_btn.setEnabled(True)
        self.status_label.setText(f"已选择: {self.selected_user['username']}")

    def apply_dark_theme(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #111827;
            }
            QWidget {
                color: #f3f4f6;
                font-family: Arial, sans-serif;
            }
            QGroupBox {
                border: 2px solid #374151;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 12px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
            }
            QLineEdit, QSpinBox {
                background-color: #1f2937;
                border: 2px solid #374151;
                border-radius: 6px;
                padding: 8px;
                color: #f3f4f6;
            }
            QLineEdit:focus, QSpinBox:focus {
                border: 2px solid #3b82f6;
            }
            QListWidget {
                background-color: #1f2937;
                border: 2px solid #374151;
                border-radius: 6px;
                padding: 6px;
            }
            QListWidget::item {
                padding: 8px;
                border-radius: 4px;
            }
            QListWidget::item:selected {
                background-color: #3b82f6;
            }
            QStatusBar {
                background-color: #1f2937;
                border-top: 1px solid #374151;
            }
            QSlider::groove:horizontal {
                height: 8px;
                background: #374151;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                width: 20px;
                height: 20px;
                background: #3b82f6;
                border-radius: 10px;
                margin: -6px 0;
            }
        """)

    def closeEvent(self, event):
        self.screen_capture.stop()
        self.network.disconnect()
        event.accept()

def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')

    window = MainWindow()
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
