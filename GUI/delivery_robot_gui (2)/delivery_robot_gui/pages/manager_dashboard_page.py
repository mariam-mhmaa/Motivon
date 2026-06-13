from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QMessageBox, QDialog, QCheckBox, QFrame, QComboBox
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont

from data_model import delivery_system


class ManagerDashboardPage(QWidget):
    """Manager dashboard for managing deliveries"""
    
    logout_requested = Signal()
    
    def __init__(self):
        super().__init__()
        self.current_manager = None
        self.current_delivery_step = None
        self.vision_simulation_timer = None
        
        # Auto-refresh timer for pending requests
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_pending_requests)
        self.refresh_timer.start(2000)  # Refresh every 2 seconds
        
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 30, 30, 30)
        root.setSpacing(20)
        
        # Header
        header_layout = QHBoxLayout()
        
        title = QLabel("Manager Dashboard")
        title.setStyleSheet("font-size: 34px; font-weight: 800; color: #F4FBFF;")
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
        
        # Tab-like sections using a stack-like layout
        self.main_stack_layout = QVBoxLayout()
        self.main_stack_layout.setSpacing(20)
        
        # Pending Requests Section (initial view)
        self.pending_section = self.create_pending_requests_section()
        # Delivery Control Section (visible during delivery)
        self.delivery_section = self.create_delivery_control_section()
        
        self.main_stack_layout.addWidget(self.pending_section)
        self.main_stack_layout.addWidget(self.delivery_section)
        
        # Hide delivery section initially
        self.delivery_section.hide()
        
        root.addLayout(self.main_stack_layout)
        root.addStretch()
    
    def create_pending_requests_section(self):
        """Create section for viewing pending requests"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(15)
        
        layout.addWidget(self.create_section_label("📋 Pending Requests"))
        
        # Requests table
        self.pending_table = QTableWidget()
        self.pending_table.setColumnCount(6)
        self.pending_table.setHorizontalHeaderLabels([
            "Select", "Request ID", "User", "Object", "Target Station", "Created"
        ])
        self.pending_table.setMinimumHeight(250)
        self.pending_table.setStyleSheet("""
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
        """)
        
        layout.addWidget(self.pending_table)
        
        # Control buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        button_layout.addStretch()
        
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setMinimumWidth(100)
        refresh_btn.setStyleSheet(self.get_button_style("blue"))
        refresh_btn.clicked.connect(self.refresh_pending_requests)
        button_layout.addWidget(refresh_btn)
        
        self.start_delivery_btn = QPushButton("Open Lid (Manager Verification)")
        self.start_delivery_btn.setMinimumWidth(250)
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
        """Create section for controlling active delivery"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(15)
        
        layout.addWidget(self.create_section_label("🚀 Active Delivery"))
        
        # Status frame
        status_frame = QFrame()
        status_frame.setStyleSheet("""
            QFrame {
                background: rgba(9, 22, 38, 180);
                border: 1px solid rgba(90, 185, 255, 38);
                border-radius: 12px;
                padding: 20px;
            }
        """)
        status_layout = QVBoxLayout(status_frame)
        status_layout.setSpacing(10)
        
        # System state
        state_layout = QHBoxLayout()
        state_label = QLabel("System State:")
        state_label.setStyleSheet("color: #8FCDF2; font-weight: bold;")
        self.state_display = QLabel("LOADING (Manager verification)")
        self.state_display.setStyleSheet("color: #FFD700; font-weight: bold;")
        state_layout.addWidget(state_label)
        state_layout.addWidget(self.state_display)
        state_layout.addStretch()
        status_layout.addLayout(state_layout)
        
        # Current step
        step_layout = QHBoxLayout()
        step_label = QLabel("Current Step:")
        step_label.setStyleSheet("color: #8FCDF2; font-weight: bold;")
        self.step_display = QLabel("-")
        self.step_display.setStyleSheet("color: #87CEEB;")
        step_layout.addWidget(step_label)
        step_layout.addWidget(self.step_display)
        step_layout.addStretch()
        status_layout.addLayout(step_layout)
        
        # Queue info
        queue_layout = QHBoxLayout()
        queue_label = QLabel("Queue:")
        queue_label.setStyleSheet("color: #8FCDF2; font-weight: bold;")
        self.queue_display = QLabel("0 deliveries pending")
        self.queue_display.setStyleSheet("color: #87CEEB;")
        queue_layout.addWidget(queue_label)
        queue_layout.addWidget(self.queue_display)
        queue_layout.addStretch()
        status_layout.addLayout(queue_layout)
        
        layout.addWidget(status_frame)
        
        # Control buttons
        control_layout = QVBoxLayout()
        control_layout.setSpacing(10)
        
        # Manager loading phase
        manager_layout = QHBoxLayout()
        manager_layout.addStretch()
        
        self.lid_open_indicator = QLabel("🔓 LID OPEN - Manager loading items...")
        self.lid_open_indicator.setStyleSheet("color: #90EE90; font-weight: bold; font-size: 13px;")
        manager_layout.addWidget(self.lid_open_indicator)
        manager_layout.addStretch()
        
        control_layout.addLayout(manager_layout)
        
        # Close lid and start button
        close_start_layout = QHBoxLayout()
        close_start_layout.addStretch()
        
        self.close_start_btn = QPushButton("Close Lid / Start Delivery")
        self.close_start_btn.setMinimumWidth(300)
        self.close_start_btn.setMinimumHeight(45)
        self.close_start_btn.setFont(QFont("Segoe UI", 13, QFont.Bold))
        self.close_start_btn.setStyleSheet(self.get_button_style("green"))
        self.close_start_btn.clicked.connect(self.close_lid_and_start)
        close_start_layout.addWidget(self.close_start_btn)
        
        close_start_layout.addStretch()
        control_layout.addLayout(close_start_layout)
        
        # Delivery status section (hidden initially)
        self.delivery_status_frame = QFrame()
        self.delivery_status_frame.setStyleSheet("""
            QFrame {
                background: rgba(9, 22, 38, 180);
                border: 1px solid rgba(90, 185, 255, 38);
                border-radius: 12px;
                padding: 20px;
            }
        """)
        delivery_status_layout = QVBoxLayout(self.delivery_status_frame)
        delivery_status_layout.setSpacing(10)
        
        status_title = QLabel("Delivery Status:")
        status_title.setStyleSheet("color: #8FCDF2; font-weight: bold; font-size: 14px;")
        delivery_status_layout.addWidget(status_title)
        
        self.delivery_status_label = QLabel("Waiting for first delivery target...")
        self.delivery_status_label.setStyleSheet("color: #87CEEB;")
        self.delivery_status_label.setWordWrap(True)
        delivery_status_layout.addWidget(self.delivery_status_label)
        
        # User received button
        user_button_layout = QHBoxLayout()
        user_button_layout.addStretch()
        
        self.user_received_btn = QPushButton("User Confirmed Receipt (Simulated Vision Verification)")
        self.user_received_btn.setMinimumWidth(350)
        self.user_received_btn.setMinimumHeight(40)
        self.user_received_btn.setStyleSheet(self.get_button_style("blue"))
        self.user_received_btn.clicked.connect(self.user_received_item)
        self.user_received_btn.hide()
        
        user_button_layout.addWidget(self.user_received_btn)
        user_button_layout.addStretch()
        
        delivery_status_layout.addLayout(user_button_layout)
        
        self.delivery_status_frame.hide()
        control_layout.addWidget(self.delivery_status_frame)
        
        # Cancel delivery button
        cancel_layout = QHBoxLayout()
        cancel_layout.addStretch()
        
        cancel_btn = QPushButton("Cancel Delivery")
        cancel_btn.setMinimumWidth(150)
        cancel_btn.setStyleSheet(self.get_button_style("red"))
        cancel_btn.clicked.connect(self.cancel_delivery)
        cancel_layout.addWidget(cancel_btn)
        
        cancel_layout.addStretch()
        control_layout.addLayout(cancel_layout)
        
        layout.addLayout(control_layout)
        
        return widget
    
    def create_section_label(self, text):
        """Create section label"""
        label = QLabel(text)
        label.setStyleSheet("font-size: 16px; font-weight: 700; color: #A8D8FF;")
        return label
    
    def get_button_style(self, color_type="blue"):
        """Get button style"""
        if color_type == "blue":
            return """
                QPushButton {
                    background: rgba(15, 100, 180, 200);
                    border: 1px solid rgba(100, 195, 255, 80);
                    border-radius: 8px;
                    color: #E9F8FF;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: rgba(20, 120, 200, 220);
                }
                QPushButton:pressed {
                    background: rgba(10, 80, 160, 240);
                }
                QPushButton:disabled {
                    background: rgba(50, 50, 50, 100);
                    color: rgba(200, 200, 200, 150);
                }
            """
        elif color_type == "green":
            return """
                QPushButton {
                    background: rgba(15, 150, 80, 200);
                    border: 1px solid rgba(100, 255, 150, 80);
                    border-radius: 8px;
                    color: #E9F8FF;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: rgba(20, 170, 100, 220);
                }
                QPushButton:pressed {
                    background: rgba(10, 130, 70, 240);
                }
            """
        elif color_type == "red":
            return """
                QPushButton {
                    background: rgba(150, 50, 50, 180);
                    border: 1px solid rgba(255, 100, 100, 80);
                    border-radius: 8px;
                    color: #F0F0F0;
                    font-weight: bold;
                }
                QPushButton:hover {
                    background: rgba(180, 60, 60, 220);
                }
                QPushButton:pressed {
                    background: rgba(120, 40, 40, 240);
                }
            """
    
    def set_manager(self, username):
        """Set the current manager"""
        self.current_manager = username
        self.refresh_pending_requests()
    
    def refresh_pending_requests(self):
        """Refresh the pending requests table"""
        pending = delivery_system.get_pending_requests()
        
        self.pending_table.setRowCount(len(pending))
        
        if len(pending) == 0:
            # Show empty message
            self.pending_table.setRowCount(1)
            empty_item = QTableWidgetItem("No pending requests yet. Waiting for user requests...")
            empty_item.setForeground(Qt.gray)
            self.pending_table.setItem(0, 0, empty_item)
            # Disable columns for empty state
            for col in range(1, 6):
                span_item = QTableWidgetItem("")
                self.pending_table.setItem(0, col, span_item)
        else:
            for row, request in enumerate(pending):
                # Checkbox for selection
                checkbox = QTableWidgetItem()
                checkbox.setCheckState(Qt.Unchecked)
                self.pending_table.setItem(row, 0, checkbox)
                
                self.pending_table.setItem(row, 1, QTableWidgetItem(request.request_id))
                self.pending_table.setItem(row, 2, QTableWidgetItem(request.user_name))
                self.pending_table.setItem(row, 3, QTableWidgetItem(request.object_requested))
                self.pending_table.setItem(row, 4, QTableWidgetItem(request.target_station))
                
                created_time = request.created_at.strftime("%Y-%m-%d %H:%M")
                self.pending_table.setItem(row, 5, QTableWidgetItem(created_time))
        
        
        # Update button state
        self.start_delivery_btn.setEnabled(len(pending) > 0)
    
    def get_selected_requests(self):
        """Get currently selected requests from table"""
        selected = []
        for row in range(self.pending_table.rowCount()):
            checkbox_item = self.pending_table.item(row, 0)
            if checkbox_item and checkbox_item.checkState() == Qt.Checked:
                request_id = self.pending_table.item(row, 1).text()
                request = next((r for r in delivery_system.all_requests if r.request_id == request_id), None)
                if request:
                    selected.append(request)
        return selected
    
    def open_lid_for_manager(self):
        """Open lid for manager to load items"""
        selected = self.get_selected_requests()
        
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select at least one request to deliver.")
            return
        
        # Select requests in system
        for request in selected:
            delivery_system.select_request(request)
        
        # ✅ Manager verified (no vision verification needed right now)
        print(f"✅ Manager {self.current_manager} verified")
        print(f"📦 Selected {len(selected)} request(s) for delivery")
        
        # Switch to delivery control view
        self.pending_section.hide()
        self.delivery_section.show()
        
        # Update display
        self.update_delivery_display()
    
    def close_lid_and_start(self):
        """Close lid and start the delivery journey"""
        if not delivery_system.start_delivery():
            QMessageBox.warning(self, "Error", "Failed to start delivery.")
            return
        
        # Hide manager loading phase
        self.lid_open_indicator.hide()
        self.close_start_btn.hide()
        
        # Show delivery status
        self.delivery_status_frame.show()
        
        # Start first delivery
        self.proceed_to_next_delivery()
    
    def proceed_to_next_delivery(self):
        """Get next delivery from queue"""
        next_delivery = delivery_system.get_next_delivery()
        
        if next_delivery:
            # Update status
            self.state_display.setText("DELIVERING")
            self.state_display.setStyleSheet("color: #FFD700; font-weight: bold;")
            
            self.current_delivery_step = next_delivery
            self.delivery_status_label.setText(
                f"🤖 Robot navigating to {next_delivery.target_station}...\n"
                f"Destination: {next_delivery.target_station}\n"
                f"User: {next_delivery.user_name}\n"
                f"Item: {next_delivery.object_requested}\n\n"
                f"Vision system will activate upon arrival for user verification."
            )
            
            # Simulate robot arrival at target
            self.simulate_robot_arrival()
        else:
            # No more deliveries, return home
            self.state_display.setText("RETURNING HOME")
            self.state_display.setStyleSheet("color: #87CEEB; font-weight: bold;")
            
            self.delivery_status_label.setText(
                "✅ All deliveries completed!\n\n"
                "Robot returning to HOME position..."
            )
            
            self.user_received_btn.hide()
            
            # After delay, reset
            QTimer.singleShot(2000, self.complete_delivery_cycle)
    
    def simulate_robot_arrival(self):
        """Simulate robot arriving at target"""
        QTimer.singleShot(1500, self.activate_user_verification)
    
    def activate_user_verification(self):
        """Ready for user to receive item (no vision verification needed right now)"""
        if self.current_delivery_step:
            self.state_display.setText("WAITING FOR USER CONFIRMATION")
            self.state_display.setStyleSheet("color: #FFD700; font-weight: bold;")
            
            self.delivery_status_label.setText(
                f"📍 Robot arrived at {self.current_delivery_step.target_station}\n\n"
                f"Waiting for: {self.current_delivery_step.user_name}\n"
                f"Item: {self.current_delivery_step.object_requested}\n\n"
                f"Click 'Confirm Receipt' to complete delivery."
            )
            
            self.user_received_btn.setText("✅ Confirm Receipt")
            self.user_received_btn.show()
    
    def user_received_item(self):
        """Handle user receiving item"""
        if not self.current_delivery_step:
            return
        
        # ✅ User confirmed receipt (no vision verification needed right now)
        print(f"✅ {self.current_delivery_step.user_name} confirmed receipt")
        
        # Complete this delivery
        delivery_system.complete_current_delivery()
        
        self.delivery_status_label.setText(
            f"✅ Item received by {self.current_delivery_step.user_name}\n"
            f"Lid closing...\n\n"
            f"Proceeding to next delivery..."
        )
        
        self.user_received_btn.hide()
        
        # Proceed to next
        QTimer.singleShot(1500, self.proceed_to_next_delivery)
    
    def complete_delivery_cycle(self):
        """Complete entire delivery cycle"""
        delivery_system.reset_delivery_cycle()
        
        QMessageBox.information(
            self,
            "Delivery Complete",
            "✅ All deliveries completed successfully!\n\n"
            "Robot returned to HOME position.\n\n"
            "Ready for new delivery requests."
        )
        
        # Return to pending requests view
        self.pending_section.show()
        self.delivery_section.hide()
        
        # Reset controls
        self.lid_open_indicator.show()
        self.close_start_btn.show()
        self.delivery_status_frame.hide()
        self.user_received_btn.hide()
        
        self.refresh_pending_requests()
    
    def cancel_delivery(self):
        """Cancel the current delivery cycle"""
        reply = QMessageBox.question(
            self,
            "Cancel Delivery",
            "Are you sure you want to cancel the current delivery cycle?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            delivery_system.reset_delivery_cycle()
            
            # Return to pending requests view
            self.pending_section.show()
            self.delivery_section.hide()
            
            # Reset controls
            self.lid_open_indicator.show()
            self.close_start_btn.show()
            self.delivery_status_frame.hide()
            self.user_received_btn.hide()
            
            self.refresh_pending_requests()
    
    def update_delivery_display(self):
        """Update delivery display"""
        queue_size = len(delivery_system.selected_requests)
        self.queue_display.setText(f"{queue_size} delivery request(s) selected")
