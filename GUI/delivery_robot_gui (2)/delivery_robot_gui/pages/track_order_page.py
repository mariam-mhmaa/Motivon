from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from api_client import GuiBridgeClient
from data_model import delivery_system
from mission_display import destination_text


class TrackOrderPage(QWidget):
    logout_requested = Signal()

    def __init__(self):
        super().__init__()
        self.current_user = None
        self.latest_mission = {}

        self.bridge = GuiBridgeClient(parent=self)
        self.bridge.status_received.connect(self.on_bridge_status)
        self.bridge.start_status_stream()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_orders)
        self.refresh_timer.start(1500)

        root = QVBoxLayout(self)
        root.setContentsMargins(30, 30, 30, 30)
        root.setSpacing(18)

        header = QHBoxLayout()
        title = QLabel("Track Order")
        title.setStyleSheet("font-size: 34px; font-weight: 800; color: #F4FBFF;")
        header.addWidget(title)
        header.addStretch()
        root.addLayout(header)

        subtitle = QLabel("Live mission destination and status for your orders")
        subtitle.setStyleSheet("font-size: 13px; color: #8FCDF2;")
        root.addWidget(subtitle)

        self.empty_label = QLabel("None of your orders are currently being delivered.")
        self.empty_label.setStyleSheet(
            "color: #D9F2FF; font-size: 18px; font-weight: 700; "
            "background: rgba(9, 22, 38, 180); border: 1px solid rgba(90, 185, 255, 38); "
            "border-radius: 8px; padding: 22px;"
        )
        self.empty_label.setWordWrap(True)
        root.addWidget(self.empty_label)

        self.active_panel = QWidget()
        active_layout = QVBoxLayout(self.active_panel)
        active_layout.setContentsMargins(0, 0, 0, 0)
        active_layout.setSpacing(14)

        self.destination_card = self.create_big_card("Destination", "Home")
        active_layout.addWidget(self.destination_card)

        self.status_table = QTableWidget()
        self.status_table.setColumnCount(4)
        self.status_table.setHorizontalHeaderLabels(
            ["Request ID", "Object", "Station", "Status"]
        )
        self.status_table.setMinimumHeight(180)
        self.status_table.setStyleSheet(self.table_style())
        active_layout.addWidget(self.status_table)

        self.confirm_receipt_btn = QPushButton("Confirm Order Received")
        self.confirm_receipt_btn.setMinimumHeight(42)
        self.confirm_receipt_btn.setStyleSheet(self.button_style("green"))
        self.confirm_receipt_btn.clicked.connect(self.confirm_receipt)
        active_layout.addWidget(self.confirm_receipt_btn)

        root.addWidget(self.active_panel)
        root.addStretch()
        self.active_panel.hide()

    def set_user(self, username):
        self.current_user = username
        self.refresh_orders()

    def create_big_card(self, label, value):
        frame = QFrame()
        frame.setStyleSheet(self.frame_style())
        layout = QVBoxLayout(frame)
        layout.setSpacing(6)
        title = QLabel(label)
        title.setStyleSheet("color: #8FCDF2; font-size: 13px; font-weight: 800;")
        value_label = QLabel(value)
        value_label.setObjectName("value")
        value_label.setStyleSheet(
            "color: #F4FBFF; font-size: 30px; font-weight: 850;"
        )
        value_label.setWordWrap(True)
        frame.value_label = value_label
        layout.addWidget(title)
        layout.addWidget(value_label)
        return frame

    def on_bridge_status(self, status):
        self.latest_mission = status.get("mission", {})
        self.refresh_orders()

    def user_active_requests(self):
        if not self.current_user:
            return []
        return [
            request
            for request in delivery_system.all_requests
            if request.user_name == self.current_user
            and request.status in ("selected", "delivering")
        ]

    def refresh_orders(self):
        active_requests = self.user_active_requests()
        mission_active = bool(self.latest_mission.get("mission_active"))
        show_active = bool(active_requests and mission_active)

        self.empty_label.setVisible(not show_active)
        self.active_panel.setVisible(show_active)
        if not show_active:
            return

        self.destination_card.value_label.setText(destination_text(self.latest_mission))
        self.status_table.setRowCount(len(active_requests))
        for row, request in enumerate(active_requests):
            self.status_table.setItem(row, 0, QTableWidgetItem(request.request_id))
            self.status_table.setItem(row, 1, QTableWidgetItem(request.object_requested))
            self.status_table.setItem(row, 2, QTableWidgetItem(request.target_station))
            label = "DELIVERING" if request.status in ("selected", "delivering") else "DELIVERED"
            self.status_table.setItem(row, 3, QTableWidgetItem(label))

        can_confirm = bool(self.latest_mission.get("can_confirm_user_received"))
        active_user = self.latest_mission.get("active_user", "")
        self.confirm_receipt_btn.setVisible(can_confirm and active_user == self.current_user)

    def confirm_receipt(self):
        response = self.bridge.confirm_user_received()
        if response.get("success"):
            request_id = self.latest_mission.get("active_request_id", "")
            if request_id:
                delivery_system.update_request_status(request_id, "completed")
            self.refresh_orders()
            return
        QMessageBox.warning(
            self,
            "Receipt Failed",
            response.get("message", "Could not confirm receipt."),
        )

    @staticmethod
    def frame_style():
        return """
            QFrame {
                background: rgba(9, 22, 38, 185);
                border: 1px solid rgba(90, 185, 255, 50);
                border-radius: 8px;
                padding: 16px;
            }
        """

    @staticmethod
    def table_style():
        return """
            QTableWidget {
                background: rgba(9, 22, 38, 180);
                border: 1px solid rgba(90, 185, 255, 38);
                border-radius: 8px;
                gridline-color: rgba(90, 185, 255, 30);
                color: #E9F8FF;
            }
            QHeaderView::section {
                background: rgba(15, 35, 60, 220);
                color: #A8D8FF;
                padding: 8px;
                border: none;
                font-weight: bold;
            }
        """

    @staticmethod
    def button_style(color_type="blue"):
        if color_type == "green":
            return """
                QPushButton {
                    background: rgba(15, 150, 80, 200);
                    border: 1px solid rgba(100, 255, 150, 80);
                    border-radius: 8px;
                    color: #E9F8FF;
                    font-weight: bold;
                }
                QPushButton:hover { background: rgba(20, 170, 100, 220); }
            """
        return """
            QPushButton {
                background: rgba(15, 100, 180, 200);
                border: 1px solid rgba(100, 195, 255, 80);
                border-radius: 8px;
                color: #E9F8FF;
                font-weight: bold;
            }
        """
