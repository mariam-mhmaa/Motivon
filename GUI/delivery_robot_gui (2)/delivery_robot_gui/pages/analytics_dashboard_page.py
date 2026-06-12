"""Analytics dashboard page for viewing delivery statistics"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget,
    QTableWidgetItem, QScrollArea, QFrame, QComboBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QColor

from analytics import analytics
from database import db


class AnalyticsDashboardPage(QWidget):
    """Dashboard for viewing analytics and statistics"""
    
    logout_requested = Signal()
    
    def __init__(self):
        super().__init__()
        
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 30, 30, 30)
        root.setSpacing(20)
        
        # Header
        header_layout = QHBoxLayout()
        
        title = QLabel("Analytics Dashboard")
        title.setStyleSheet("font-size: 34px; font-weight: 800; color: #F4FBFF;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setMaximumWidth(120)
        refresh_btn.setStyleSheet(self.get_button_style("blue"))
        refresh_btn.clicked.connect(self.refresh_data)
        header_layout.addWidget(refresh_btn)
        
        logout_btn = QPushButton("Logout")
        logout_btn.setMaximumWidth(100)
        logout_btn.setStyleSheet(self.get_button_style("red"))
        logout_btn.clicked.connect(self.logout_requested.emit)
        header_layout.addWidget(logout_btn)
        
        root.addLayout(header_layout)
        
        subtitle = QLabel("View delivery statistics and analytics")
        subtitle.setStyleSheet("font-size: 13px; color: #8FCDF2;")
        root.addWidget(subtitle)
        
        # Create scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(20)
        
        # Overall Statistics Section
        scroll_layout.addWidget(self.create_overall_stats_section())
        
        # User Statistics Section
        scroll_layout.addWidget(self.create_user_stats_section())
        
        # Station Statistics Section
        scroll_layout.addWidget(self.create_station_stats_section())
        
        # Request History Section
        scroll_layout.addWidget(self.create_request_history_section())
        
        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        
        root.addWidget(scroll)
    
    def create_overall_stats_section(self):
        """Create overall statistics display"""
        widget = QFrame()
        widget.setStyleSheet("""
            QFrame {
                background-color: #1e2d47;
                border-radius: 8px;
                border: 1px solid #2d5a8c;
                padding: 15px;
            }
        """)
        
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        
        title = QLabel("📊 Overall Statistics")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #F4FBFF;")
        layout.addWidget(title)
        
        # Stats grid
        stats_layout = QHBoxLayout()
        
        total_count = db.get_request_count()
        completed_count = db.get_request_count("completed")
        pending_count = db.get_request_count("pending")
        cancelled_count = db.get_request_count("cancelled")
        
        stats = [
            ("Total Requests", str(total_count), "#87CEEB"),
            ("Completed", str(completed_count), "#90EE90"),
            ("Pending", str(pending_count), "#FFD700"),
            ("Cancelled", str(cancelled_count), "#FF6B6B"),
        ]
        
        for label, value, color in stats:
            stat_frame = QFrame()
            stat_frame.setStyleSheet(f"""
                QFrame {{
                    background-color: rgba(45, 90, 140, 0.5);
                    border-radius: 5px;
                    border: 1px solid {color};
                    padding: 10px;
                }}
            """)
            
            stat_layout = QVBoxLayout(stat_frame)
            
            label_widget = QLabel(label)
            label_widget.setStyleSheet(f"color: {color}; font-size: 12px;")
            stat_layout.addWidget(label_widget)
            
            value_widget = QLabel(value)
            value_widget.setStyleSheet(f"color: {color}; font-size: 24px; font-weight: bold;")
            stat_layout.addWidget(value_widget)
            
            stats_layout.addWidget(stat_frame)
        
        layout.addLayout(stats_layout)
        
        # Completion rate
        completion_rate = analytics.get_completion_rate()
        rate_label = QLabel(f"Completion Rate: {completion_rate:.1f}%")
        rate_label.setStyleSheet("color: #8FCDF2; font-size: 14px;")
        layout.addWidget(rate_label)
        
        return widget
    
    def create_user_stats_section(self):
        """Create user statistics table"""
        widget = QFrame()
        widget.setStyleSheet("""
            QFrame {
                background-color: #1e2d47;
                border-radius: 8px;
                border: 1px solid #2d5a8c;
                padding: 15px;
            }
        """)
        
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        
        title = QLabel("👥 User Statistics")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #F4FBFF;")
        layout.addWidget(title)
        
        # User stats table
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(["User", "Total", "Completed", "Pending", "Cancelled", "Delivering"])
        table.setStyleSheet("""
            QTableWidget {
                background-color: #0f1821;
                color: #F4FBFF;
                gridline-color: #2d5a8c;
            }
            QHeaderView::section {
                background-color: #2d5a8c;
                color: #F4FBFF;
                padding: 5px;
            }
        """)
        
        user_stats = analytics.get_user_statistics()
        table.setRowCount(len(user_stats))
        
        for row, (user, stats) in enumerate(sorted(user_stats.items())):
            table.setItem(row, 0, QTableWidgetItem(user))
            table.setItem(row, 1, QTableWidgetItem(str(stats['total'])))
            table.setItem(row, 2, QTableWidgetItem(str(stats['completed'])))
            table.setItem(row, 3, QTableWidgetItem(str(stats['pending'])))
            table.setItem(row, 4, QTableWidgetItem(str(stats['cancelled'])))
            table.setItem(row, 5, QTableWidgetItem(str(stats['delivering'])))
        
        table.resizeColumnsToContents()
        layout.addWidget(table)
        
        return widget
    
    def create_station_stats_section(self):
        """Create station statistics display"""
        widget = QFrame()
        widget.setStyleSheet("""
            QFrame {
                background-color: #1e2d47;
                border-radius: 8px;
                border: 1px solid #2d5a8c;
                padding: 15px;
            }
        """)
        
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        
        title = QLabel("🏢 Station Statistics")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #F4FBFF;")
        layout.addWidget(title)
        
        # Station stats
        station_stats = analytics.get_station_statistics()
        
        for station, count in sorted(station_stats.items()):
            station_layout = QHBoxLayout()
            
            station_label = QLabel(station)
            station_label.setStyleSheet("color: #87CEEB; font-size: 14px; font-weight: bold;")
            station_layout.addWidget(station_label)
            
            station_layout.addStretch()
            
            count_label = QLabel(str(count))
            count_label.setStyleSheet("color: #F4FBFF; font-size: 14px;")
            station_layout.addWidget(count_label)
            
            layout.addLayout(station_layout)
        
        return widget
    
    def create_request_history_section(self):
        """Create request history table"""
        widget = QFrame()
        widget.setStyleSheet("""
            QFrame {
                background-color: #1e2d47;
                border-radius: 8px;
                border: 1px solid #2d5a8c;
                padding: 15px;
            }
        """)
        
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        
        title = QLabel("📜 Request History")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #F4FBFF;")
        layout.addWidget(title)
        
        # History table
        table = QTableWidget()
        table.setColumnCount(6)
        table.setHorizontalHeaderLabels(["Request ID", "User", "Object", "Station", "Status", "Created"])
        table.setStyleSheet("""
            QTableWidget {
                background-color: #0f1821;
                color: #F4FBFF;
                gridline-color: #2d5a8c;
            }
            QHeaderView::section {
                background-color: #2d5a8c;
                color: #F4FBFF;
                padding: 5px;
            }
        """)
        
        # Get all requests, most recent first
        all_requests = db.get_all_requests()
        table.setRowCount(min(len(all_requests), 10))  # Show last 10
        
        for row, req in enumerate(all_requests[:10]):
            table.setItem(row, 0, QTableWidgetItem(req['request_id']))
            table.setItem(row, 1, QTableWidgetItem(req['user_name']))
            table.setItem(row, 2, QTableWidgetItem(req['object_requested']))
            table.setItem(row, 3, QTableWidgetItem(req['target_station']))
            
            status_item = QTableWidgetItem(req['status'].upper())
            if req['status'] == "completed":
                status_item.setForeground(QColor("#90EE90"))
            elif req['status'] == "delivering":
                status_item.setForeground(QColor("#FFD700"))
            elif req['status'] == "cancelled":
                status_item.setForeground(QColor("#FF6B6B"))
            else:
                status_item.setForeground(QColor("#87CEEB"))
            table.setItem(row, 4, status_item)
            
            created_time = req['created_at'].split('T')[0]
            table.setItem(row, 5, QTableWidgetItem(created_time))
        
        table.resizeColumnsToContents()
        layout.addWidget(table)
        
        return widget
    
    def refresh_data(self):
        """Refresh all statistics"""
        # Recreate all sections with fresh data
        self.setLayout(None)
        root = QVBoxLayout(self)
        root.setContentsMargins(30, 30, 30, 30)
        root.setSpacing(20)
        
        # Recreate header
        header_layout = QHBoxLayout()
        
        title = QLabel("Analytics Dashboard")
        title.setStyleSheet("font-size: 34px; font-weight: 800; color: #F4FBFF;")
        header_layout.addWidget(title)
        header_layout.addStretch()
        
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.setMaximumWidth(120)
        refresh_btn.setStyleSheet(self.get_button_style("blue"))
        refresh_btn.clicked.connect(self.refresh_data)
        header_layout.addWidget(refresh_btn)
        
        logout_btn = QPushButton("Logout")
        logout_btn.setMaximumWidth(100)
        logout_btn.setStyleSheet(self.get_button_style("red"))
        logout_btn.clicked.connect(self.logout_requested.emit)
        header_layout.addWidget(logout_btn)
        
        root.addLayout(header_layout)
        
        subtitle = QLabel("View delivery statistics and analytics")
        subtitle.setStyleSheet("font-size: 13px; color: #8FCDF2;")
        root.addWidget(subtitle)
        
        # Create scrollable content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background-color: transparent; }")
        
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(20)
        
        scroll_layout.addWidget(self.create_overall_stats_section())
        scroll_layout.addWidget(self.create_user_stats_section())
        scroll_layout.addWidget(self.create_station_stats_section())
        scroll_layout.addWidget(self.create_request_history_section())
        
        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        
        root.addWidget(scroll)
    
    @staticmethod
    def get_button_style(color_type):
        """Get button stylesheet"""
        colors = {
            "blue": "#2d5a8c",
            "red": "#8b3a3a",
        }
        
        return f"""
            QPushButton {{
                background-color: {colors.get(color_type, '#2d5a8c')};
                color: white;
                border: none;
                border-radius: 5px;
                padding: 8px 16px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: {colors.get(color_type, '#2d5a8c')}dd;
            }}
            QPushButton:pressed {{
                background-color: {colors.get(color_type, '#2d5a8c')}99;
            }}
        """
