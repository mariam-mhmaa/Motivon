from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QComboBox, QFrame


class RequestPage(QWidget):
    def __init__(self):
        super().__init__()

        root = QVBoxLayout(self)
        root.setContentsMargins(30, 30, 30, 30)
        root.setSpacing(20)

        title = QLabel("Request Tools")
        title.setStyleSheet("font-size: 34px; font-weight: 800; color: #F4FBFF;")

        subtitle = QLabel("Create a delivery mission for a workshop stop")
        subtitle.setStyleSheet("font-size: 13px; color: #8FCDF2;")

        root.addWidget(title)
        root.addWidget(subtitle)

        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background: rgba(8, 18, 32, 215);
                border: 1px solid rgba(90, 185, 255, 35);
                border-radius: 24px;
            }
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        label_style = "color: #D9F2FF; font-size: 14px; font-weight: 700;"
        combo_style = """
            QComboBox {
                background: rgba(14, 36, 58, 235);
                border: 1px solid rgba(110, 200, 255, 60);
                border-radius: 14px;
                padding: 12px;
                color: #F4FBFF;
                font-size: 14px;
            }
            QComboBox:hover {
                border: 1px solid rgba(130, 215, 255, 95);
            }
            QComboBox::drop-down { border: none; }
        """
        btn_style = """
            QPushButton {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 rgba(28, 118, 201, 245),
                    stop:1 rgba(8, 69, 138, 245)
                );
                border: 1px solid rgba(140, 220, 255, 100);
                border-radius: 16px;
                padding: 14px;
                color: white;
                font-size: 14px;
                font-weight: 800;
            }
            QPushButton:hover {
                background: rgba(35, 132, 224, 245);
            }
            QPushButton:pressed {
                background: rgba(16, 82, 155, 245);
            }
        """

        stop = QComboBox()
        stop.addItems(["Stop 1", "Stop 2", "Stop 3"])
        stop.setStyleSheet(combo_style)

        tools = QComboBox()
        tools.addItems(["Wrench Set", "Screwdriver Set", "Pliers", "Measuring Tools", "Fastener Kit"])
        tools.setStyleSheet(combo_style)

        submit = QPushButton("Submit Request")
        submit.setStyleSheet(btn_style)

        stop_label = QLabel("Destination Stop")
        stop_label.setStyleSheet(label_style)

        tool_label = QLabel("Requested Tool Set")
        tool_label.setStyleSheet(label_style)

        layout.addWidget(stop_label)
        layout.addWidget(stop)
        layout.addWidget(tool_label)
        layout.addWidget(tools)
        layout.addSpacing(8)
        layout.addWidget(submit)

        root.addWidget(card)
        root.addStretch()