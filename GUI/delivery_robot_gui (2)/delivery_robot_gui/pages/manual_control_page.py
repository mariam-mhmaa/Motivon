from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFrame
from widgets.joystick_widget import JoystickWidget


class ManualControlPage(QWidget):
    def __init__(self):
        super().__init__()

        self.direction_label = QLabel("Direction: Neutral")
        self.speed_label = QLabel("Speed: 0.00")
        self.xy_label = QLabel("X: 0.00 | Y: 0.00")

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

        estop = QPushButton("Emergency Stop")
        estop.setStyleSheet("""
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

        return_btn = QPushButton("Return to Base")
        return_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(26, 105, 182, 240),
                    stop:1 rgba(10, 62, 125, 240)
                );
                border: 1px solid rgba(130, 210, 255, 80);
                border-radius: 16px;
                padding: 14px;
                color: white;
                font-size: 14px;
                font-weight: 800;
            }
            QPushButton:hover { background: rgba(36, 122, 210, 240); }
        """)

        right_layout.addWidget(info_title)
        right_layout.addSpacing(8)
        right_layout.addWidget(self.direction_label)
        right_layout.addWidget(self.speed_label)
        right_layout.addWidget(self.xy_label)
        right_layout.addSpacing(22)
        right_layout.addWidget(estop)
        right_layout.addWidget(return_btn)
        right_layout.addStretch()

        content.addWidget(left, 2)
        content.addWidget(right, 1)

        root.addLayout(content)

    def update_joystick_info(self, x, y):
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