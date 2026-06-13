from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, 
    QFrame, QMessageBox, QStackedWidget
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QIcon
from data_model import PREDEFINED_USERS, USER_ROLES


class LoginPage(QWidget):
    """Login page for the delivery robot system"""
    
    login_successful = Signal(str)  # Emits username when login successful
    
    def __init__(self):
        super().__init__()
        
        self.login_type = None  # "user" or "manager"
        
        # Create stacked widget to switch between role selection and login
        self.stacked = QStackedWidget()
        
        # Role selection page
        self.role_page = self.create_role_selection_page()
        # Login page
        self.login_page = self.create_login_page()
        
        self.stacked.addWidget(self.role_page)
        self.stacked.addWidget(self.login_page)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.stacked)
        
    def create_role_selection_page(self):
        """Create the page where user selects their role"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(30)
        
        # Add stretch at top
        layout.addStretch()
        
        # Title
        title = QLabel("Delivery Robot System")
        title.setFont(QFont("Segoe UI", 38, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #F4FBFF;")
        layout.addWidget(title)
        
        # Subtitle
        subtitle = QLabel("Select your role to continue")
        subtitle.setFont(QFont("Segoe UI", 16))
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet("color: #8FCDF2;")
        layout.addWidget(subtitle)
        
        # Buttons container
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(40)
        buttons_layout.addStretch()
        
        # User button
        user_btn = self.create_role_button("User", "📦 User\nRequest Delivery", "user")
        buttons_layout.addWidget(user_btn)
        
        # Manager button
        manager_btn = self.create_role_button("Manager", "🔧 Manager\nManage Deliveries", "manager")
        buttons_layout.addWidget(manager_btn)
        
        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)
        
        layout.addStretch()
        
        return page
    
    def create_role_button(self, role, label, role_type):
        """Create a role selection button"""
        btn = QPushButton()
        btn.setMinimumSize(200, 200)
        btn.setMaximumSize(250, 250)
        btn.setText(label)
        btn.setFont(QFont("Segoe UI", 14, QFont.Bold))
        btn.setCursor(Qt.PointingHandCursor)
        
        btn.setStyleSheet("""
            QPushButton {
                background: rgba(9, 22, 38, 200);
                border: 2px solid rgba(90, 185, 255, 38);
                border-radius: 15px;
                color: #E9F8FF;
                padding: 20px;
                text-align: center;
                white-space: pre-wrap;
            }
            QPushButton:hover {
                background: rgba(15, 35, 60, 220);
                border: 2px solid rgba(150, 220, 255, 80);
            }
            QPushButton:pressed {
                background: rgba(20, 45, 75, 240);
            }
        """)
        
        btn.clicked.connect(lambda: self.select_role(role_type))
        return btn
    
    def select_role(self, role_type):
        """Handle role selection"""
        self.login_type = role_type
        self.reset_login_form()
        self.stacked.setCurrentWidget(self.login_page)
    
    def create_login_page(self):
        """Create the login form page"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 40, 40, 40)
        layout.setSpacing(20)
        
        layout.addStretch()
        
        # Title
        self.login_title = QLabel("User Login")
        self.login_title.setFont(QFont("Segoe UI", 32, QFont.Bold))
        self.login_title.setAlignment(Qt.AlignCenter)
        self.login_title.setStyleSheet("color: #F4FBFF;")
        layout.addWidget(self.login_title)
        
        # Form
        form_layout = QVBoxLayout()
        form_layout.setSpacing(15)
        
        # Username field
        username_label = QLabel("Username:")
        username_label.setStyleSheet("color: #8FCDF2; font-size: 13px;")
        form_layout.addWidget(username_label)
        
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter your username")
        self.username_input.setMinimumHeight(40)
        self.username_input.setStyleSheet("""
            QLineEdit {
                background: rgba(20, 40, 60, 180);
                border: 1px solid rgba(90, 185, 255, 50);
                border-radius: 8px;
                color: #E9F8FF;
                padding: 8px 12px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 2px solid rgba(150, 220, 255, 100);
                background: rgba(25, 50, 75, 200);
            }
        """)
        form_layout.addWidget(self.username_input)
        
        # Password field
        password_label = QLabel("Password:")
        password_label.setStyleSheet("color: #8FCDF2; font-size: 13px;")
        form_layout.addWidget(password_label)
        
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Enter your password")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setMinimumHeight(40)
        self.password_input.setStyleSheet("""
            QLineEdit {
                background: rgba(20, 40, 60, 180);
                border: 1px solid rgba(90, 185, 255, 50);
                border-radius: 8px;
                color: #E9F8FF;
                padding: 8px 12px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 2px solid rgba(150, 220, 255, 100);
                background: rgba(25, 50, 75, 200);
            }
        """)
        form_layout.addWidget(self.password_input)
        
        # Add form to layout with max width
        form_widget = QWidget()
        form_widget.setLayout(form_layout)
        form_widget.setMaximumWidth(400)
        
        center_layout = QHBoxLayout()
        center_layout.addStretch()
        center_layout.addWidget(form_widget)
        center_layout.addStretch()
        
        layout.addLayout(center_layout)
        
        # Buttons
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(20)
        buttons_layout.addStretch()
        
        # Back button
        back_btn = QPushButton("Back")
        back_btn.setMinimumWidth(120)
        back_btn.setMinimumHeight(40)
        back_btn.setStyleSheet("""
            QPushButton {
                background: rgba(40, 60, 80, 180);
                border: 1px solid rgba(90, 185, 255, 50);
                border-radius: 8px;
                color: #E9F8FF;
                font-weight: bold;
            }
            QPushButton:hover {
                background: rgba(50, 75, 100, 200);
                border: 1px solid rgba(150, 220, 255, 80);
            }
        """)
        back_btn.clicked.connect(self.go_back)
        buttons_layout.addWidget(back_btn)
        
        # Login button
        login_btn = QPushButton("Login")
        login_btn.setMinimumWidth(120)
        login_btn.setMinimumHeight(40)
        login_btn.setStyleSheet("""
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
        login_btn.clicked.connect(self.perform_login)
        buttons_layout.addWidget(login_btn)
        
        buttons_layout.addStretch()
        layout.addLayout(buttons_layout)
        
        layout.addStretch()
        
        return page
    
    def go_back(self):
        """Go back to role selection"""
        self.stacked.setCurrentWidget(self.role_page)
        self.reset_login_form()
    
    def reset_login_form(self):
        """Clear login form"""
        self.username_input.clear()
        self.password_input.clear()
        
        if self.login_type == "user":
            self.login_title.setText("User Login")
        else:
            self.login_title.setText("Manager Login")
    
    def perform_login(self):
        """Handle login"""
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        
        if not username:
            QMessageBox.warning(self, "Login Failed", "Please enter a username.")
            return
        
        if not password:
            QMessageBox.warning(self, "Login Failed", "Please enter a password.")
            return
        
        # Validate against predefined users
        if username not in PREDEFINED_USERS:
            QMessageBox.warning(self, "Login Failed", f"User '{username}' not found.\n\nAvailable users:\n• nour (worker)\n• ainour\n• mariam\n• zeina")
            return
        
        # Check password
        if PREDEFINED_USERS[username] != password:
            QMessageBox.warning(self, "Login Failed", "Incorrect password.")
            return
        
        # Check if user role matches login type
        user_role = USER_ROLES.get(username, "user")
        expected_role = "worker" if self.login_type == "manager" else "user"
        
        if self.login_type == "manager" and user_role != "worker":
            QMessageBox.warning(self, "Login Failed", f"User '{username}' does not have manager/worker privileges.")
            return
        
        if self.login_type == "user" and user_role != "user":
            QMessageBox.warning(self, "Login Failed", f"User '{username}' can only login as manager.")
            return
        
        # Login successful
        self.login_successful.emit(username)
