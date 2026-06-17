from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from api_client import GuiBridgeClient
from data_model import delivery_system
from system_launcher import (
    start_laptop_ros_stack,
    start_pi_camera_stream,
    start_windows_vision_preview,
)


class ManagerDashboardPage(QWidget):
    """Manager dashboard for real robot mission control."""

    logout_requested = Signal()

    def __init__(self):
        super().__init__()
        self.current_manager = None
        self.active_mission_request_ids = set()
        self.completed_event_ids = set()
        self.pending_selected_request_ids = set()
        self.last_event_key = None
        self.latest_status = {}
        self.terminal_reset_pending = False
        self.ros_process = None
        self.camera_process = None
        self.preview_process = None

        self.bridge = GuiBridgeClient(parent=self)
        self.bridge.status_received.connect(self.on_bridge_status)
        self.bridge.connection_changed.connect(self.on_bridge_connection)
        self.bridge.start_status_stream()

        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_pending_requests)
        self.refresh_timer.start(2000)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setStyleSheet(
            """
            QScrollArea {
                background: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background: rgba(7, 18, 32, 160);
                width: 12px;
                margin: 0;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background: rgba(90, 185, 255, 120);
                min-height: 30px;
                border-radius: 6px;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {
                height: 0;
            }
            """
        )

        content = QWidget()
        scroll_area.setWidget(content)
        outer_layout.addWidget(scroll_area)

        root = QVBoxLayout(content)
        root.setContentsMargins(30, 30, 30, 30)
        root.setSpacing(18)

        header_layout = QHBoxLayout()
        title = QLabel("Manager Dashboard")
        title.setStyleSheet(
            "font-size: 34px; font-weight: 800; color: #F4FBFF;"
        )
        header_layout.addWidget(title)
        header_layout.addStretch()

        logout_btn = QPushButton("Logout")
        logout_btn.setMaximumWidth(100)
        logout_btn.setStyleSheet(self.get_button_style("red"))
        logout_btn.clicked.connect(self.logout_requested.emit)
        header_layout.addWidget(logout_btn)
        root.addLayout(header_layout)

        subtitle = QLabel("Manage delivery requests and monitor robot operations")
        subtitle.setStyleSheet("font-size: 13px; color: #8FCDF2;")
        root.addWidget(subtitle)

        root.addWidget(self.create_system_launcher_section())

        self.pending_section = self.create_pending_requests_section()
        self.delivery_section = self.create_delivery_control_section()
        self.delivery_section.hide()

        root.addWidget(self.pending_section)
        root.addWidget(self.delivery_section)
        root.addStretch()

    def create_system_launcher_section(self):
        frame = QFrame()
        frame.setStyleSheet(self.get_frame_style())
        layout = QHBoxLayout(frame)
        layout.setSpacing(12)

        self.system_launch_label = QLabel(
            "Start system launches Pi camera + local ROS vision test stack."
        )
        self.system_launch_label.setStyleSheet("color: #A8D8FF;")
        self.system_launch_label.setWordWrap(True)
        layout.addWidget(self.system_launch_label, 1)

        self.start_system_btn = QPushButton("Start System")
        self.start_system_btn.setMinimumWidth(150)
        self.start_system_btn.setMinimumHeight(36)
        self.start_system_btn.setStyleSheet(self.get_button_style("blue"))
        self.start_system_btn.clicked.connect(self.start_system_stack)
        layout.addWidget(self.start_system_btn)

        return frame

    def start_system_stack(self):
        messages = []

        try:
            if self.camera_process is None or self.camera_process.poll() is not None:
                self.camera_process = start_pi_camera_stream()
                messages.append(
                    "Pi camera SSH window started. Enter the Pi password "
                    "there if prompted, and leave it open."
                )
            else:
                messages.append("Pi camera process already started from this GUI.")
        except Exception as error:
            messages.append(f"Pi camera was not started automatically: {error}")

        try:
            if self.ros_process is None or self.ros_process.poll() is not None:
                self.ros_process = start_laptop_ros_stack()
                messages.append("WSL ROS/vision launch window started.")
            else:
                messages.append("ROS/vision process already started from this GUI.")
        except Exception as error:
            messages.append(f"ROS/vision was not started: {error}")

        try:
            if self.preview_process is None or self.preview_process.poll() is not None:
                self.preview_process = start_windows_vision_preview()
                messages.append("Windows vision preview window started.")
            else:
                messages.append("Vision preview process already started from this GUI.")
        except Exception as error:
            messages.append(f"Vision preview was not started: {error}")

        message = "\n".join(messages)
        self.system_launch_label.setText(message)
        QMessageBox.information(self, "System Launch", message)

    def create_pending_requests_section(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(14)

        layout.addWidget(self.create_section_label("Pending Requests"))

        self.pending_table = QTableWidget()
        self.pending_table.setColumnCount(6)
        self.pending_table.setHorizontalHeaderLabels(
            ["Select", "Request ID", "User", "Object", "Target Station", "Created"]
        )
        self.pending_table.setMinimumHeight(250)
        self.pending_table.setStyleSheet(self.get_table_style())
        self.pending_table.itemChanged.connect(self.on_pending_item_changed)
        layout.addWidget(self.pending_table)

        button_layout = QHBoxLayout()
        button_layout.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setMinimumWidth(100)
        refresh_btn.setStyleSheet(self.get_button_style("blue"))
        refresh_btn.clicked.connect(self.refresh_pending_requests)
        button_layout.addWidget(refresh_btn)

        self.start_delivery_btn = QPushButton("Open Lid")
        self.start_delivery_btn.setMinimumWidth(220)
        self.start_delivery_btn.setMinimumHeight(40)
        self.start_delivery_btn.setFont(QFont("Segoe UI", 12, QFont.Bold))
        self.start_delivery_btn.setStyleSheet(self.get_button_style("green"))
        self.start_delivery_btn.clicked.connect(self.open_lid_for_manager)
        self.start_delivery_btn.setEnabled(False)
        button_layout.addWidget(self.start_delivery_btn)

        button_layout.addStretch()
        layout.addLayout(button_layout)
        return widget

    def create_delivery_control_section(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(14)

        layout.addWidget(self.create_section_label("Active Delivery"))

        status_frame = QFrame()
        status_frame.setStyleSheet(self.get_frame_style())
        status_layout = QVBoxLayout(status_frame)
        status_layout.setSpacing(10)

        self.state_display = QLabel("IDLE")
        self.state_display.setStyleSheet(
            "color: #FFD700; font-weight: bold; font-size: 16px;"
        )
        self.step_display = QLabel("-")
        self.step_display.setStyleSheet("color: #87CEEB;")
        self.queue_display = QLabel("0 delivery request(s) selected")
        self.queue_display.setStyleSheet("color: #87CEEB;")

        status_layout.addWidget(self.label_row("System State:", self.state_display))
        status_layout.addWidget(self.label_row("Current Step:", self.step_display))
        status_layout.addWidget(self.label_row("Queue:", self.queue_display))
        layout.addWidget(status_frame)

        control_frame = QFrame()
        control_frame.setStyleSheet(self.get_frame_style())
        control_layout = QVBoxLayout(control_frame)
        control_layout.setSpacing(12)

        self.delivery_status_label = QLabel("Waiting for mission status...")
        self.delivery_status_label.setStyleSheet("color: #D9F2FF;")
        self.delivery_status_label.setWordWrap(True)
        control_layout.addWidget(self.delivery_status_label)

        self.lid_open_indicator = QLabel("LID OPEN - Manager loading items")
        self.lid_open_indicator.setStyleSheet(
            "color: #90EE90; font-weight: bold; font-size: 13px;"
        )
        self.lid_open_indicator.hide()
        control_layout.addWidget(self.lid_open_indicator)

        action_layout = QHBoxLayout()
        action_layout.addStretch()

        self.manager_verified_btn = QPushButton("Manager Verified")
        self.manager_verified_btn.setMinimumWidth(190)
        self.manager_verified_btn.setMinimumHeight(40)
        self.manager_verified_btn.setStyleSheet(self.get_button_style("blue"))
        self.manager_verified_btn.clicked.connect(self.manager_verified)
        self.manager_verified_btn.hide()
        action_layout.addWidget(self.manager_verified_btn)

        self.close_start_btn = QPushButton("Start Mission")
        self.close_start_btn.setMinimumWidth(190)
        self.close_start_btn.setMinimumHeight(40)
        self.close_start_btn.setStyleSheet(self.get_button_style("green"))
        self.close_start_btn.clicked.connect(self.close_lid_and_start)
        self.close_start_btn.hide()
        action_layout.addWidget(self.close_start_btn)

        self.user_verified_btn = QPushButton("User Verified")
        self.user_verified_btn.setMinimumWidth(170)
        self.user_verified_btn.setMinimumHeight(40)
        self.user_verified_btn.setStyleSheet(self.get_button_style("blue"))
        self.user_verified_btn.clicked.connect(self.user_verified)
        self.user_verified_btn.hide()
        action_layout.addWidget(self.user_verified_btn)

        self.user_received_btn = QPushButton("Confirm Receipt")
        self.user_received_btn.setMinimumWidth(170)
        self.user_received_btn.setMinimumHeight(40)
        self.user_received_btn.setStyleSheet(self.get_button_style("green"))
        self.user_received_btn.clicked.connect(self.user_received_item)
        self.user_received_btn.hide()
        action_layout.addWidget(self.user_received_btn)

        cancel_btn = QPushButton("Cancel Delivery")
        cancel_btn.setMinimumWidth(150)
        cancel_btn.setMinimumHeight(40)
        cancel_btn.setStyleSheet(self.get_button_style("red"))
        cancel_btn.clicked.connect(self.cancel_delivery)
        action_layout.addWidget(cancel_btn)

        action_layout.addStretch()
        control_layout.addLayout(action_layout)
        layout.addWidget(control_frame)
        return widget

    def label_row(self, title, value_widget):
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(title)
        label.setStyleSheet("color: #8FCDF2; font-weight: bold;")
        layout.addWidget(label)
        layout.addWidget(value_widget)
        layout.addStretch()
        return row

    def create_section_label(self, text):
        label = QLabel(text)
        label.setStyleSheet(
            "font-size: 16px; font-weight: 700; color: #A8D8FF;"
        )
        return label

    def get_table_style(self):
        return """
            QTableWidget {
                background: rgba(9, 22, 38, 180);
                border: 1px solid rgba(90, 185, 255, 38);
                border-radius: 8px;
                gridline-color: rgba(90, 185, 255, 30);
            }
            QTableWidget::item {
                padding: 8px;
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

    def get_frame_style(self):
        return """
            QFrame {
                background: rgba(9, 22, 38, 180);
                border: 1px solid rgba(90, 185, 255, 38);
                border-radius: 12px;
                padding: 16px;
            }
        """

    def get_button_style(self, color_type="blue"):
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
                QPushButton:disabled {
                    background: rgba(50, 50, 50, 100);
                    color: rgba(200, 200, 200, 150);
                }
            """
        if color_type == "red":
            return """
                QPushButton {
                    background: rgba(150, 50, 50, 180);
                    border: 1px solid rgba(255, 100, 100, 80);
                    border-radius: 8px;
                    color: #F0F0F0;
                    font-weight: bold;
                }
                QPushButton:hover { background: rgba(180, 60, 60, 220); }
            """
        return """
            QPushButton {
                background: rgba(15, 100, 180, 200);
                border: 1px solid rgba(100, 195, 255, 80);
                border-radius: 8px;
                color: #E9F8FF;
                font-weight: bold;
            }
            QPushButton:hover { background: rgba(20, 120, 200, 220); }
            QPushButton:disabled {
                background: rgba(50, 50, 50, 100);
                color: rgba(200, 200, 200, 150);
            }
        """

    def set_manager(self, username):
        self.current_manager = username
        self.refresh_pending_requests()

    def refresh_pending_requests(self):
        if self.delivery_section.isVisible():
            return

        self.capture_pending_selection()
        pending = delivery_system.get_pending_requests()
        pending_ids = {request.request_id for request in pending}
        self.pending_selected_request_ids.intersection_update(pending_ids)

        self.pending_table.blockSignals(True)
        self.pending_table.setRowCount(len(pending) if pending else 1)

        if not pending:
            item = QTableWidgetItem("No pending requests yet.")
            item.setForeground(QColor("#9AA6B2"))
            self.pending_table.setItem(0, 0, item)
            for col in range(1, 6):
                self.pending_table.setItem(0, col, QTableWidgetItem(""))
        else:
            for row, request in enumerate(pending):
                checkbox = QTableWidgetItem()
                checkbox.setCheckState(
                    Qt.Checked
                    if request.request_id in self.pending_selected_request_ids
                    else Qt.Unchecked
                )
                self.pending_table.setItem(row, 0, checkbox)
                self.pending_table.setItem(row, 1, QTableWidgetItem(request.request_id))
                self.pending_table.setItem(row, 2, QTableWidgetItem(request.user_name))
                self.pending_table.setItem(row, 3, QTableWidgetItem(request.object_requested))
                self.pending_table.setItem(row, 4, QTableWidgetItem(request.target_station))
                created_time = request.created_at.strftime("%Y-%m-%d %H:%M")
                self.pending_table.setItem(row, 5, QTableWidgetItem(created_time))

        self.pending_table.blockSignals(False)
        self.update_start_button_state()

    def capture_pending_selection(self):
        if not hasattr(self, "pending_table"):
            return
        for row in range(self.pending_table.rowCount()):
            checkbox_item = self.pending_table.item(row, 0)
            id_item = self.pending_table.item(row, 1)
            if not checkbox_item or not id_item:
                continue
            request_id = id_item.text()
            if checkbox_item.checkState() == Qt.Checked:
                self.pending_selected_request_ids.add(request_id)
            else:
                self.pending_selected_request_ids.discard(request_id)

    def on_pending_item_changed(self, item):
        if item.column() != 0:
            return
        id_item = self.pending_table.item(item.row(), 1)
        if not id_item:
            return
        request_id = id_item.text()
        if item.checkState() == Qt.Checked:
            self.pending_selected_request_ids.add(request_id)
        else:
            self.pending_selected_request_ids.discard(request_id)
        self.update_start_button_state()

    def update_start_button_state(self):
        self.start_delivery_btn.setEnabled(bool(self.pending_selected_request_ids))

    def get_selected_requests(self):
        self.capture_pending_selection()
        selected = []
        for request_id in self.pending_selected_request_ids:
            request = next(
                (
                    r
                    for r in delivery_system.all_requests
                    if r.request_id == request_id
                ),
                None,
            )
            if request and request.status == "pending":
                selected.append(request)
        return selected

    def open_lid_for_manager(self):
        selected = self.get_selected_requests()
        if not selected:
            QMessageBox.warning(
                self,
                "No Selection",
                "Please select at least one request to deliver.",
            )
            return

        response = self.bridge.start_mission(selected)
        if not response.get("success"):
            QMessageBox.warning(
                self,
                "Mission Start Failed",
                response.get("message", "Could not start mission."),
            )
            return

        for request in selected:
            delivery_system.select_request(request)
        self.active_mission_request_ids = {r.request_id for r in selected}
        self.pending_selected_request_ids.clear()
        self.completed_event_ids.clear()
        self.terminal_reset_pending = False
        self.pending_section.hide()
        self.delivery_section.show()
        self.manager_verified_btn.show()
        self.update_delivery_display()

    def manager_verified(self):
        response = self.bridge.confirm_manager_verified()
        if not response.get("success"):
            QMessageBox.warning(
                self,
                "Verification Failed",
                response.get("message", "Could not confirm manager."),
            )

    def close_lid_and_start(self):
        response = self.bridge.confirm_manager_loaded()
        if response.get("success"):
            for request_id in self.active_mission_request_ids:
                delivery_system.update_request_status(request_id, "delivering")
        else:
            QMessageBox.warning(
                self,
                "Start Mission Failed",
                response.get("message", "Could not start route."),
            )

    def user_verified(self):
        response = self.bridge.confirm_user_verified()
        if not response.get("success"):
            QMessageBox.warning(
                self,
                "User Verification Failed",
                response.get("message", "Could not confirm user."),
            )

    def user_received_item(self):
        response = self.bridge.confirm_user_received()
        if not response.get("success"):
            QMessageBox.warning(
                self,
                "Receipt Failed",
                response.get("message", "Could not confirm receipt."),
            )

    def cancel_delivery(self):
        reply = QMessageBox.question(
            self,
            "Cancel Delivery",
            "Are you sure you want to cancel the current delivery cycle?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            response = self.bridge.cancel_mission()
            if not response.get("success"):
                QMessageBox.warning(
                    self,
                    "Cancel Failed",
                    response.get("message", "Could not cancel mission."),
                )

    def complete_delivery_cycle(self):
        delivery_system.reset_delivery_cycle()
        self.active_mission_request_ids.clear()
        self.pending_section.show()
        self.delivery_section.hide()
        self.manager_verified_btn.hide()
        self.close_start_btn.hide()
        self.user_verified_btn.hide()
        self.user_received_btn.hide()
        self.lid_open_indicator.hide()
        self.terminal_reset_pending = False
        self.refresh_pending_requests()

    def update_delivery_display(self):
        count = len(self.active_mission_request_ids)
        self.queue_display.setText(f"{count} delivery request(s) selected")

    def on_bridge_connection(self, connected, message):
        self.step_display.setText("Bridge connected" if connected else message)

    def on_bridge_status(self, status):
        self.latest_status = status
        mission = status.get("mission", {})
        if mission:
            self.apply_mission_status(mission)
        event = status.get("last_event", {})
        if event:
            self.apply_mission_event(event)

    def apply_mission_status(self, mission):
        state = mission.get("state", "-")
        detail = mission.get("detail", "")
        self.state_display.setText(state)
        self.step_display.setText(detail or "-")
        self.delivery_status_label.setText(self.format_mission_detail(mission))

        self.manager_verified_btn.setVisible(
            bool(mission.get("can_confirm_manager_verified"))
        )
        self.close_start_btn.setVisible(
            bool(mission.get("can_confirm_manager_loaded"))
        )
        self.lid_open_indicator.setVisible(state == "WAITING_FOR_MANAGER_LOAD")
        self.user_verified_btn.setVisible(
            bool(mission.get("can_confirm_user_verified"))
        )
        self.user_received_btn.setVisible(
            bool(mission.get("can_confirm_user_received"))
        )

        if (
            state in ("COMPLETE", "ABORTED", "FAULTED")
            and not self.terminal_reset_pending
        ):
            self.reconcile_terminal_mission(mission)
            self.terminal_reset_pending = True
            QTimer.singleShot(600, self.complete_delivery_cycle)

    def reconcile_terminal_mission(self, mission):
        if not self.active_mission_request_ids:
            return

        state = mission.get("state", "-")
        completed_count = int(mission.get("completed_count", 0) or 0)
        total_count = int(mission.get("total_count", 0) or 0)

        if state == "COMPLETE" and completed_count >= total_count:
            for request_id in list(self.active_mission_request_ids):
                delivery_system.update_request_status(request_id, "completed")
            self.active_mission_request_ids.clear()
            return

        unfinished = [
            request_id
            for request_id in self.active_mission_request_ids
            if request_id not in self.completed_event_ids
        ]
        delivery_system.return_requests_to_pending(unfinished)
        self.pending_selected_request_ids.update(unfinished)
        self.active_mission_request_ids.difference_update(unfinished)

    @staticmethod
    def format_mission_detail(mission):
        lines = [mission.get("detail", "")]
        station = mission.get("current_station", "")
        target = mission.get("current_target", "")
        request_id = mission.get("active_request_id", "")
        user = mission.get("active_user", "")
        item = mission.get("active_item", "")
        if station or target:
            lines.append(f"Station: {station or '-'} | Target: {target or '-'}")
        if request_id:
            lines.append(f"Request: {request_id} | User: {user} | Item: {item}")
        completed = mission.get("completed_count", 0)
        total = mission.get("total_count", 0)
        lines.append(f"Progress: {completed}/{total}")
        if mission.get("safety_paused"):
            lines.append("Safety stop active")
        return "\n".join(line for line in lines if line)

    def apply_mission_event(self, event):
        key = (
            event.get("event_type"),
            event.get("request_id"),
            event.get("message"),
        )
        if key == self.last_event_key:
            return
        self.last_event_key = key

        event_type = event.get("event_type")
        request_id = event.get("request_id")
        if event_type == "REQUEST_COMPLETED" and request_id:
            delivery_system.update_request_status(request_id, "completed")
            self.completed_event_ids.add(request_id)
            self.active_mission_request_ids.discard(request_id)
            self.update_delivery_display()
        elif event_type == "REQUEST_SKIPPED_UNVERIFIED" and request_id:
            delivery_system.update_request_status(request_id, "pending")
            self.pending_selected_request_ids.add(request_id)
            self.active_mission_request_ids.discard(request_id)
            self.update_delivery_display()
        elif event_type in ("MISSION_CANCELLED", "MISSION_FAULTED"):
            self.pending_selected_request_ids.update(self.active_mission_request_ids)
            delivery_system.return_requests_to_pending(
                list(self.active_mission_request_ids)
            )
            self.active_mission_request_ids.clear()
            self.update_delivery_display()
