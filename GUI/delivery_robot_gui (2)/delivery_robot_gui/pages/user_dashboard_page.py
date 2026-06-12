from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QLineEdit, QFrame, QTableWidget, QTableWidgetItem, QMessageBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor

from data_model import delivery_system


class UserDashboardPage(QWidget):
    """User dashboard for creating delivery requests"""
    
    logout_requested = Signal()
    
    def __init__(self):
        super().__init__()
        self.current_user = None
        
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 30, 30, 30)
        root.setSpacing(20)
        
        # Header
        header_layout = QHBoxLayout()
        
        title = QLabel("User Dashboard")
        title.setStyleSheet("font-size: 34px; font-weight: 800; color: #F4FBFF;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        
        logout_btn = QPushButton("Logout")
        logout_btn.setMaximumWidth(100)
        logout_btn.setStyleSheet("""
            QPushButton {
                background: rgba(150, 50, 50, 180);
                border: 1px solid rgba(255, 100, 100, 80);
                border-radius: 8px;
                color: #F0F0F0;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(180, 60, 60, 220);
            }
        """)
        logout_btn.clicked.connect(self.logout_requested.emit)
        header_layout.addWidget(logout_btn)
        
        root.addLayout(header_layout)
        
        # Subtitle
        subtitle = QLabel("Create a new delivery request or view your history")
        subtitle.setStyleSheet("font-size: 13px; color: #8FCDF2;")
        root.addWidget(subtitle)
        
        # Create Request Section
        root.addWidget(self.create_section_label("📋 Create New Request"))
        
        request_frame = QFrame()
        request_frame.setStyleSheet("""
            QFrame {
                background: rgba(9, 22, 38, 180);
                border: 1px solid rgba(90, 185, 255, 38);
                border-radius: 12px;
                padding: 20px;
            }
        """)
        request_layout = QVBoxLayout(request_frame)
        request_layout.setSpacing(15)
        
        # Object input
        obj_label = QLabel("Object to Request:")
        obj_label.setStyleSheet("color: #8FCDF2; font-weight: bold;")
        request_layout.addWidget(obj_label)
        
        self.object_input = QLineEdit()
        self.object_input.setPlaceholderText("e.g., Package, Document, Part #123")
        self.object_input.setMinimumHeight(35)
        self.object_input.setStyleSheet(self.get_input_style())
        request_layout.addWidget(self.object_input)
        
        # Target station dropdown
        target_label = QLabel("Target Station:")
        target_label.setStyleSheet("color: #8FCDF2; font-weight: bold;")
        request_layout.addWidget(target_label)
        
        self.station_combo = QComboBox()
        self.station_combo.addItems(["Station A", "Station B", "Station C"])
        self.station_combo.setMinimumHeight(35)
        self.station_combo.setStyleSheet(self.get_combo_style())
        request_layout.addWidget(self.station_combo)
        
        # Submit button
        submit_btn = QPushButton("Submit Request")
        submit_btn.setMinimumHeight(40)
        submit_btn.setFont(QFont("Segoe UI", 12, QFont.Bold))
        submit_btn.setStyleSheet("""
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
        """)
        submit_btn.clicked.connect(self.submit_request)
        request_layout.addWidget(submit_btn)
        
        root.addWidget(request_frame)
        
        # Request History Section
        root.addWidget(self.create_section_label("📊 Your Request History"))
        
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(5)
        self.history_table.setHorizontalHeaderLabels([
            "Request ID", "Object", "Target", "Status", "Created"
        ])
        self.history_table.setStyleSheet("""
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
        self.history_table.setMinimumHeight(200)
        self.history_table.resizeColumnsToContents()
        root.addWidget(self.history_table)
        
        root.addStretch()
    
    def create_section_label(self, text):
        """Create a section label"""
        label = QLabel(text)
        label.setStyleSheet("font-size: 16px; font-weight: 700; color: #A8D8FF; margin-top: 10px;")
        return label
    
    def get_input_style(self):
        """Get input field style"""
        return """
            QLineEdit {
                background: rgba(20, 40, 60, 180);
                border: 1px solid rgba(90, 185, 255, 50);
                border-radius: 6px;
                color: #E9F8FF;
                padding: 8px 12px;
                font-size: 13px;
            }
            QLineEdit:focus {
                border: 2px solid rgba(150, 220, 255, 100);
                background: rgba(25, 50, 75, 200);
            }
        """
    
    def get_combo_style(self):
        """Get combo box style"""
        return """
            QComboBox {
                background: rgba(20, 40, 60, 180);
                border: 1px solid rgba(90, 185, 255, 50);
                border-radius: 6px;
                color: #E9F8FF;
                padding: 6px 12px;
                font-size: 13px;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 20px;
                border-left: 1px solid rgba(90, 185, 255, 50);
            }
            QComboBox::down-arrow {
                image: none;
            }
            QComboBox:focus {
                border: 2px solid rgba(150, 220, 255, 100);
            }
        """
    
    def set_user(self, username):
        """Set the current user"""
        self.current_user = username
        self.refresh_history()
    
    def submit_request(self):
        """Submit a new delivery request"""
        object_name = self.object_input.text().strip()
        target_station = self.station_combo.currentText()
        
        if not object_name:
            QMessageBox.warning(self, "Input Error", "Please enter the object name.")
            return
        
        if not self.current_user:
            QMessageBox.warning(self, "Error", "User not logged in.")
            return
        
        # Create request in the system
        request = delivery_system.create_request(
            user_name=self.current_user,
            object_requested=object_name,
            target_station=target_station
        )
        
        QMessageBox.information(
            self, 
            "Request Created", 
            f"Your delivery request has been created!\n\nRequest ID: {request.request_id}\nObject: {object_name}\nTarget: {target_station}"
        )
        
        # Clear form
        self.object_input.clear()
        self.station_combo.setCurrentIndex(0)
        
        # Refresh history
        self.refresh_history()
    
    def refresh_history(self):
        """Refresh the request history table"""
        if not self.current_user:
            return
        
        # Get user's requests
        user_requests = [r for r in delivery_system.all_requests if r.user_name == self.current_user]
        
        self.history_table.setRowCount(len(user_requests))
        
        for row, request in enumerate(reversed(user_requests)):  # Show newest first
            self.history_table.setItem(row, 0, QTableWidgetItem(request.request_id))
            self.history_table.setItem(row, 1, QTableWidgetItem(request.object_requested))
            self.history_table.setItem(row, 2, QTableWidgetItem(request.target_station))
            
            status_item = QTableWidgetItem(request.status.upper())
            # Color code by status
            if request.status == "completed":
                status_item.setForeground(QColor("#90EE90"))
            elif request.status == "delivering":
                status_item.setForeground(QColor("#FFD700"))
            elif request.status == "cancelled":
                status_item.setForeground(QColor("#FF6B6B"))
            else:
                status_item.setForeground(QColor("#87CEEB"))
            
            self.history_table.setItem(row, 3, status_item)
            
            created_time = request.created_at.strftime("%Y-%m-%d %H:%M")
            self.history_table.setItem(row, 4, QTableWidgetItem(created_time))
