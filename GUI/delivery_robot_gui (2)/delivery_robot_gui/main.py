import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QLabel, QPushButton
)
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QPoint, QParallelAnimationGroup
from PySide6.QtGui import QPixmap

from pages.login_page import LoginPage
from pages.user_dashboard_page import UserDashboardPage
from pages.manager_dashboard_page import ManagerDashboardPage
from pages.analytics_dashboard_page import AnalyticsDashboardPage
from pages.dashboard_page import DashboardPage
from pages.request_page import RequestPage
from pages.manual_control_page import ManualControlPage
from widgets.sidebar import Sidebar
from data_model import delivery_system

# Global list to track all open windows
open_windows = []


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Workshop Delivery Robot")
        self.resize(1400, 820)

        self.bg_original = None
        self.current_user_type = None  # "user" or "manager"
        self.current_user = None

        self.background_label = QLabel(self)
        self.background_label.setScaledContents(True)
        self.background_label.lower()
        self.set_background_image("assets/workshop_bg.jpg")

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)

        outer_layout = QVBoxLayout(root)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Create main stack widget for different "modes"
        self.main_stack = QStackedWidget()
        
        # Create login page
        self.login_page = LoginPage()
        self.login_page.login_successful.connect(self.on_login_successful)
        
        # Create main content area (with topbar, sidebar, pages)
        self.main_content = QWidget()
        content_layout = QVBoxLayout(self.main_content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        self.topbar = self.create_topbar()
        content_layout.addWidget(self.topbar)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self.sidebar = Sidebar()
        self.pages = QStackedWidget()
        self.pages.setObjectName("pagesArea")

        # Create all pages
        self.dashboard_page = DashboardPage()
        self.user_dashboard = UserDashboardPage()
        self.manager_dashboard = ManagerDashboardPage()
        self.analytics_dashboard = AnalyticsDashboardPage()
        self.request_page = RequestPage()
        self.manual_control_page = ManualControlPage()

        self.pages.addWidget(self.dashboard_page)       # 0
        self.pages.addWidget(self.user_dashboard)       # 1
        self.pages.addWidget(self.manager_dashboard)    # 2
        self.pages.addWidget(self.analytics_dashboard)  # 3
        self.pages.addWidget(self.request_page)         # 4
        self.pages.addWidget(self.manual_control_page)  # 5

        body_layout.addWidget(self.sidebar)
        body_layout.addWidget(self.pages, 1)

        content_layout.addWidget(body, 1)
        
        # Add main content to stack
        self.main_stack.addWidget(self.login_page)
        self.main_stack.addWidget(self.main_content)
        
        # Show login page initially
        self.main_stack.setCurrentWidget(self.login_page)
        
        outer_layout.addWidget(self.main_stack)

        # Connect sidebar buttons
        self.sidebar.dashboard_btn.clicked.connect(lambda: self.switch_page(0))
        self.sidebar.request_btn.clicked.connect(lambda: self.switch_page(1))
        self.sidebar.manual_btn.clicked.connect(lambda: self.switch_page(2))

        self.sidebar.set_active_button(self.sidebar.dashboard_btn)
        
        # Connect logout signals
        self.user_dashboard.logout_requested.connect(self.logout)
        self.manager_dashboard.logout_requested.connect(self.logout)

        self.setStyleSheet("""
            QMainWindow, QWidget {
                color: #F2FAFF;
                font-family: 'Segoe UI';
                font-size: 14px;
                background: transparent;
            }

            #root {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 rgba(2, 8, 16, 170),
                    stop:1 rgba(4, 18, 32, 145)
                );
            }

            #topbar {
                background: rgba(5, 16, 28, 220);
                border-bottom: 1px solid rgba(100, 195, 255, 35);
            }

            #topTitle {
                font-size: 23px;
                font-weight: 800;
                color: #F4FBFF;
            }

            #topSubtitle {
                font-size: 12px;
                color: #89C7EC;
            }

            #statusPill {
                background: rgba(13, 47, 78, 200);
                border: 1px solid rgba(105, 195, 255, 80);
                border-radius: 13px;
                padding: 8px 14px;
                color: #E9F8FF;
                font-weight: 700;
            }

            #pagesArea {
                background: transparent;
            }
        """)
    
    def on_login_successful(self, username):
        """Handle successful login"""
        self.current_user = username
        self.current_user_type = self.login_page.login_type
        
        # Show main content
        self.main_stack.setCurrentWidget(self.main_content)
        
        # Update topbar
        if self.current_user_type == "user":
            self.user_pill.setText(f"User: {username}")
        else:
            self.user_pill.setText(f"Manager: {username}")
        
        # Route to appropriate dashboard
        if self.current_user_type == "user":
            self.user_dashboard.set_user(username)
            self.switch_page_direct(1)  # User dashboard
        else:  # manager
            self.manager_dashboard.set_manager(username)
            self.switch_page_direct(2)  # Manager dashboard
    
    def logout(self):
        """Handle logout"""
        self.current_user = None
        self.current_user_type = None
        self.main_stack.setCurrentWidget(self.login_page)
    
    def open_new_session(self):
        """Open a new session window"""
        new_window = MainWindow()
        new_window.setGeometry(self.x() + 50, self.y() + 50, 1400, 820)
        new_window.show()
        open_windows.append(new_window)
    
    def switch_page_direct(self, index):
        """Switch page directly without animation"""
        self.pages.setCurrentIndex(index)

    def create_topbar(self):
        topbar = QWidget()
        topbar.setObjectName("topbar")
        topbar.setFixedHeight(78)

        layout = QHBoxLayout(topbar)
        layout.setContentsMargins(24, 12, 24, 12)

        left = QVBoxLayout()
        title = QLabel("Workshop Delivery Robot")
        title.setObjectName("topTitle")

        subtitle = QLabel("Industrial blue control interface")
        subtitle.setObjectName("topSubtitle")
        self.topbar_subtitle = subtitle  # Store reference for updating

        left.addWidget(title)
        left.addWidget(subtitle)

        layout.addLayout(left)
        layout.addStretch()
        
        # New Session button
        new_session_btn = QPushButton("+ New Session")
        new_session_btn.setMaximumWidth(140)
        new_session_btn.setStyleSheet("""
            QPushButton {
                background: rgba(20, 100, 50, 180);
                border: 1px solid rgba(100, 255, 150, 80);
                border-radius: 8px;
                color: #E9F8FF;
                padding: 6px 12px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background: rgba(25, 120, 60, 220);
            }
        """)
        new_session_btn.clicked.connect(self.open_new_session)
        layout.addWidget(new_session_btn)
        
        # User info pill
        self.user_pill = QLabel("Not logged in")
        self.user_pill.setObjectName("statusPill")
        self.user_pill.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.user_pill)

        for text in ["Robot Online", "Battery 87%"]:
            pill = QLabel(text)
            pill.setObjectName("statusPill")
            pill.setAlignment(Qt.AlignCenter)
            layout.addWidget(pill)

        return topbar
    
    def update_topbar_subtitle(self, text):
        """Update topbar subtitle"""
        self.topbar_subtitle.setText(text)

    def set_background_image(self, path):
        pixmap = QPixmap(path)
        if pixmap.isNull():
            print("⚠️ Background image not found:", path)
            return
        self.bg_original = pixmap
        self.update_background()

    def update_background(self):
        if self.bg_original:
            scaled = self.bg_original.scaled(
                self.size(),
                Qt.IgnoreAspectRatio,
                Qt.SmoothTransformation
            )
            self.background_label.setPixmap(scaled)
            self.background_label.setGeometry(0, 0, self.width(), self.height())

    def resizeEvent(self, event):
        self.update_background()
        super().resizeEvent(event)

    def switch_page(self, index):
        current_index = self.pages.currentIndex()
        if current_index == index:
            return

        current_widget = self.pages.currentWidget()
        next_widget = self.pages.widget(index)

        width = self.pages.width()
        direction = 1 if index > current_index else -1

        next_widget.move(direction * width, 0)
        next_widget.show()

        anim_group = QParallelAnimationGroup(self)

        anim_out = QPropertyAnimation(current_widget, b"pos")
        anim_out.setDuration(320)
        anim_out.setEndValue(QPoint(-direction * width, 0))
        anim_out.setEasingCurve(QEasingCurve.OutCubic)

        anim_in = QPropertyAnimation(next_widget, b"pos")
        anim_in.setDuration(320)
        anim_in.setStartValue(QPoint(direction * width, 0))
        anim_in.setEndValue(QPoint(0, 0))
        anim_in.setEasingCurve(QEasingCurve.OutCubic)

        anim_group.addAnimation(anim_out)
        anim_group.addAnimation(anim_in)

        def finish():
            self.pages.setCurrentIndex(index)
            current_widget.move(0, 0)

        anim_group.finished.connect(finish)
        self.anim_group = anim_group
        anim_group.start()

        if index == 0:
            self.sidebar.set_active_button(self.sidebar.dashboard_btn)
        elif index == 1:
            self.sidebar.set_active_button(self.sidebar.request_btn)
        elif index == 2:
            self.sidebar.set_active_button(self.sidebar.manual_btn)
    
    def closeEvent(self, event):
        """Handle window close to remove from open_windows list"""
        if self in open_windows:
            open_windows.remove(self)
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    open_windows.append(window)
    window.show()
    sys.exit(app.exec())