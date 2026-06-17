from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFrame, QMessageBox

from api_client import GuiBridgeClient
from widgets.joystick_widget import JoystickWidget


class ManualControlPage(QWidget):
    def __init__(self):
        super().__init__()
        self.current_manager = None
        self.current_x = 0.0
        self.current_y = 0.0
        self.current_yaw = 0.0
        self.manual_enabled = False
        self.bridge = GuiBridgeClient(parent=self)

        self.direction_label = QLabel("Direction: Neutral")
        self.speed_label = QLabel("Speed: 0.00")
        self.xy_label = QLabel("X: 0.00 | Y: 0.00")
        self.mode_label = QLabel("Mode: AUTO")

        self.command_timer = QTimer(self)
        self.command_timer.timeout.connect(self.publish_manual_command)
        self.command_timer.start(100)

        root = QVBoxLayout(self)
        root.setContentsMargins(30, 30, 30, 30)
        root.setSpacing(20)

        title = QLabel("Manual Control")
        title.setStyleSheet("font-size: 34px; font-weight: 800; color: #F4FBFF;")

        subtitle = QLabel("Analog joystick teleoperation panel")
        subtitle.setStyleSheet("font-size: 13px; color: #8FCDF2;")

        root.addWidget(title)
        root.addWidget(subtitle)

        content = QHBoxLayout()
        content.setSpacing(18)

        left = QFrame()
        left.setStyleSheet("""
            QFrame {
                background: rgba(8, 18, 32, 215);
                border: 1px solid rgba(90, 185, 255, 35);
                border-radius: 24px;
            }
        """)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(20, 20, 20, 20)

        joy_title = QLabel("Joystick")
        joy_title.setStyleSheet("font-size: 20px; font-weight: 700; color: #F4FBFF;")

        self.joystick = JoystickWidget()
        self.joystick.joystickMoved.connect(self.update_joystick_info)

        left_layout.addWidget(joy_title)
        left_layout.addSpacing(10)
        left_layout.addWidget(self.joystick, 1)

        right = QFrame()
        right.setStyleSheet("""
            QFrame {
                background: rgba(8, 18, 32, 215);
                border: 1px solid rgba(90, 185, 255, 35);
                border-radius: 24px;
            }
        """)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(22, 22, 22, 22)
        right_layout.setSpacing(14)

        info_title = QLabel("Control Data")
        info_title.setStyleSheet("font-size: 20px; font-weight: 700; color: #F4FBFF;")

        info_style = """
            font-size: 15px;
            font-weight: 600;
            color: #D9F2FF;
            background: rgba(16, 40, 63, 170);
            padding: 12px 14px;
            border-radius: 12px;
        """
        self.direction_label.setStyleSheet(info_style)
        self.speed_label.setStyleSheet(info_style)
        self.xy_label.setStyleSheet(info_style)
        self.mode_label.setStyleSheet(info_style)

        manual_btn = QPushButton("Turn Manual Mode On")
        manual_btn.setStyleSheet("""
            QPushButton {
                background: rgba(15, 150, 80, 210);
                border: 1px solid rgba(100, 255, 150, 80);
                border-radius: 16px;
                padding: 14px;
                color: white;
                font-size: 14px;
                font-weight: 800;
            }
            QPushButton:hover { background: rgba(20, 170, 100, 230); }
        """)
        manual_btn.clicked.connect(self.enable_manual_mode)

        auto_btn = QPushButton("Return to AUTO Mode")
        auto_btn.setStyleSheet("""
            QPushButton {
                background: rgba(26, 105, 182, 240);
                border: 1px solid rgba(130, 210, 255, 80);
                border-radius: 16px;
                padding: 14px;
                color: white;
                font-size: 14px;
                font-weight: 800;
            }
            QPushButton:hover { background: rgba(36, 122, 210, 240); }
        """)
        auto_btn.clicked.connect(self.enable_auto_mode)

        stop_btn = QPushButton("Stop Manual Command")
        stop_btn.setStyleSheet("""
            QPushButton {
                background: rgba(184, 48, 72, 240);
                border: 1px solid rgba(255, 155, 170, 95);
                border-radius: 16px;
                padding: 14px;
                color: white;
                font-size: 14px;
                font-weight: 800;
            }
            QPushButton:hover { background: rgba(205, 60, 85, 245); }
        """)
        stop_btn.clicked.connect(self.stop_manual_command)

        rotate_row = QHBoxLayout()
        rotate_left = QPushButton("Rotate Left")
        rotate_right = QPushButton("Rotate Right")
        for button in (rotate_left, rotate_right):
            button.setStyleSheet("""
                QPushButton {
                    background: rgba(15, 100, 180, 200);
                    border: 1px solid rgba(100, 195, 255, 80);
                    border-radius: 12px;
                    padding: 10px;
                    color: #E9F8FF;
                    font-weight: bold;
                }
                QPushButton:hover { background: rgba(20, 120, 200, 220); }
            """)
        rotate_left.pressed.connect(lambda: self.set_yaw(1.0))
        rotate_left.released.connect(lambda: self.set_yaw(0.0))
        rotate_right.pressed.connect(lambda: self.set_yaw(-1.0))
        rotate_right.released.connect(lambda: self.set_yaw(0.0))
        rotate_row.addWidget(rotate_left)
        rotate_row.addWidget(rotate_right)

        right_layout.addWidget(info_title)
        right_layout.addSpacing(8)
        right_layout.addWidget(self.mode_label)
        right_layout.addWidget(self.direction_label)
        right_layout.addWidget(self.speed_label)
        right_layout.addWidget(self.xy_label)
        right_layout.addSpacing(22)
        right_layout.addWidget(manual_btn)
        right_layout.addWidget(auto_btn)
        right_layout.addLayout(rotate_row)
        right_layout.addWidget(stop_btn)
        right_layout.addStretch()

        content.addWidget(left, 2)
        content.addWidget(right, 1)

        root.addLayout(content)

    def set_manager(self, username):
        self.current_manager = username

    def enable_manual_mode(self):
        response = self.bridge.set_mode("MANUAL")
        if response.get("success"):
            self.manual_enabled = True
            self.mode_label.setText("Mode: MANUAL")
            return
        QMessageBox.warning(
            self,
            "Manual Mode Failed",
            response.get("message", "Could not switch to manual mode."),
        )

    def enable_auto_mode(self):
        self.stop_manual_command()
        response = self.bridge.set_mode("AUTO")
        if response.get("success"):
            self.manual_enabled = False
            self.mode_label.setText("Mode: AUTO")
            return
        QMessageBox.warning(
            self,
            "AUTO Mode Failed",
            response.get("message", "Could not switch to AUTO mode."),
        )

    def set_yaw(self, yaw):
        self.current_yaw = float(yaw)

    def stop_manual_command(self):
        self.current_x = 0.0
        self.current_y = 0.0
        self.current_yaw = 0.0
        self.joystick.reset_knob()
        self.bridge.send_manual_command(0.0, 0.0, 0.0)
        self.update_joystick_info(0.0, 0.0)

    def publish_manual_command(self):
        if self.manual_enabled:
            self.bridge.send_manual_command(
                self.current_y,
                self.current_x,
                self.current_yaw,
            )

    def update_joystick_info(self, x, y):
        self.current_x = float(x)
        self.current_y = float(y)
        self.xy_label.setText(f"X: {x:.2f} | Y: {y:.2f}")
        speed = min((x**2 + y**2) ** 0.5, 1.0)
        self.speed_label.setText(f"Speed: {speed:.2f}")

        threshold = 0.2
        if abs(x) < threshold and abs(y) < threshold:
            direction = "Neutral"
        elif abs(y) >= abs(x):
            direction = "Forward" if y > 0 else "Backward"
        else:
            direction = "Right" if x > 0 else "Left"

        self.direction_label.setText(f"Direction: {direction}")
