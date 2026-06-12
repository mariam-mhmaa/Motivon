from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QGridLayout, QHBoxLayout


class DashboardPage(QWidget):
    def __init__(self):
        super().__init__()

        root = QVBoxLayout(self)
        root.setContentsMargins(30, 30, 30, 30)
        root.setSpacing(20)

        title = QLabel("Dashboard")
        title.setStyleSheet("font-size: 34px; font-weight: 800; color: #F4FBFF;")

        subtitle = QLabel("Live robot overview and workshop status")
        subtitle.setStyleSheet("font-size: 13px; color: #8FCDF2;")

        root.addWidget(title)
        root.addWidget(subtitle)

        grid = QGridLayout()
        grid.setSpacing(18)

        grid.addWidget(self.card("Robot Status", "Idle"), 0, 0)
        grid.addWidget(self.card("Current Stop", "Base"), 0, 1)
        grid.addWidget(self.card("Battery", "87%"), 0, 2)
        grid.addWidget(self.card("Lid Status", "Locked"), 0, 3)

        root.addLayout(grid)

        lower = QHBoxLayout()
        lower.setSpacing(18)

        lower.addWidget(self.large_panel("Camera Feed", "Live stream will appear here"), 2)
        lower.addWidget(self.large_panel("System Alerts", "No warnings detected"), 1)

        root.addLayout(lower)
        root.addStretch()

    def card(self, heading, value):
        frame = QFrame()
        frame.setMinimumHeight(155)
        frame.setStyleSheet("""
            QFrame {
                background: rgba(9, 22, 38, 210);
                border: 1px solid rgba(90, 185, 255, 38);
                border-radius: 22px;
            }
            QFrame:hover {
                border: 1px solid rgba(120, 210, 255, 75);
            }
        """)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(20, 18, 20, 18)

        head = QLabel(heading)
        head.setStyleSheet("color: #8FCDF2; font-size: 13px; font-weight: 700;")

        val = QLabel(value)
        val.setStyleSheet("color: #F6FCFF; font-size: 30px; font-weight: 800;")

        hint = QLabel("System telemetry")
        hint.setStyleSheet("color: #6E9FBE; font-size: 12px;")

        layout.addWidget(head)
        layout.addSpacing(14)
        layout.addWidget(val)
        layout.addSpacing(6)
        layout.addWidget(hint)
        layout.addStretch()
        return frame

    def large_panel(self, heading, body):
        frame = QFrame()
        frame.setMinimumHeight(330)
        frame.setStyleSheet("""
            QFrame {
                background: rgba(8, 18, 32, 215);
                border: 1px solid rgba(90, 185, 255, 35);
                border-radius: 24px;
            }
        """)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(22, 20, 22, 20)

        head = QLabel(heading)
        head.setStyleSheet("color: #F4FBFF; font-size: 20px; font-weight: 700;")

        body_lbl = QLabel(body)
        body_lbl.setStyleSheet("color: #89B9D6; font-size: 14px;")

        placeholder = QLabel("●  Monitoring channel ready")
        placeholder.setStyleSheet("""
            color: #7ED0FF;
            font-size: 13px;
            padding: 12px 14px;
            background: rgba(18, 45, 70, 180);
            border-radius: 12px;
        """)

        layout.addWidget(head)
        layout.addSpacing(16)
        layout.addWidget(body_lbl)
        layout.addSpacing(12)
        layout.addWidget(placeholder)
        layout.addStretch()
        return frame