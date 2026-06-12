from PySide6.QtWidgets import QWidget, QVBoxLayout, QPushButton, QLabel
from PySide6.QtCore import Qt


class Sidebar(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedWidth(270)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 22, 18, 22)
        layout.setSpacing(14)

        title = QLabel("CONTROL PANEL")
        title.setStyleSheet("""
            color: #79C8FF;
            font-size: 12px;
            font-weight: 800;
            letter-spacing: 2px;
            padding-left: 6px;
        """)

        self.dashboard_btn = QPushButton("Dashboard")
        self.request_btn = QPushButton("Request Tools")
        self.manual_btn = QPushButton("Manual Control")

        self.buttons = [self.dashboard_btn, self.request_btn, self.manual_btn]

        for btn in self.buttons:
            btn.setMinimumHeight(58)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(self.default_style())

        self.setStyleSheet("""
            QWidget {
                background: rgba(6, 16, 28, 225);
                border-right: 1px solid rgba(95, 185, 255, 40);
            }
        """)

        layout.addWidget(title)
        layout.addSpacing(8)
        layout.addWidget(self.dashboard_btn)
        layout.addWidget(self.request_btn)
        layout.addWidget(self.manual_btn)
        layout.addStretch()

    def default_style(self):
        return """
            QPushButton {
                background: rgba(13, 31, 51, 230);
                border: 1px solid rgba(105, 190, 255, 28);
                border-radius: 18px;
                padding: 15px 18px;
                text-align: left;
                color: #EAF7FF;
                font-size: 15px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: rgba(20, 45, 72, 240);
                border: 1px solid rgba(105, 190, 255, 90);
            }
            QPushButton:pressed {
                background: rgba(26, 58, 90, 245);
            }
        """

    def active_style(self):
        return """
            QPushButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(24, 95, 170, 245),
                    stop:1 rgba(10, 52, 105, 245)
                );
                border: 1px solid rgba(130, 210, 255, 145);
                border-radius: 18px;
                padding: 15px 18px;
                text-align: left;
                color: white;
                font-size: 15px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: rgba(28, 108, 188, 245);
            }
        """

    def set_active_button(self, active_button):
        for btn in self.buttons:
            btn.setStyleSheet(self.default_style())
        active_button.setStyleSheet(self.active_style())