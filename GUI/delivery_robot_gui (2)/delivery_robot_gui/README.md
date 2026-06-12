# Workshop Delivery Robot GUI System

## Overview
A comprehensive delivery management system for autonomous robots with dual-role authentication (User & Manager), request tracking, and automated delivery coordination with vision-based verification.

## System Architecture

### Core Components

#### 1. **Login System** (`pages/login_page.py`)
- Dual-role authentication: User and Manager
- Simple username/password interface
- Role selection page for clarity

#### 2. **User Dashboard** (`pages/user_dashboard_page.py`)
- **Create Delivery Requests**:
  - Enter object description
  - Select target station (Station A, B, or C)
  - View confirmation with Request ID
  
- **Request History**:
  - View all submitted requests
  - Track request status (pending, delivering, completed, cancelled)
  - Sort by newest requests first
  - Status color coding

#### 3. **Manager Dashboard** (`pages/manager_dashboard_page.py`)
- **Pending Requests View**:
  - List all unprocessed requests
  - Select multiple requests via checkboxes
  - View request details (user, object, target)

- **Manager Verification Phase**:
  - "Open Lid" button triggers vision verification
  - System simulates facial recognition for manager
  - Upon verification: lid opens for item loading

- **Delivery Control**:
  - "Close Lid / Start Delivery" button initiates journey
  - System automatically sorts requests by closest station first
  - Real-time delivery status display

- **Delivery Tracking**:
  - Shows current delivery target
  - Displays expected user
  - Simulates vision verification at each location
  - "User Received" button for simulated user confirmation
  - Automatic progression to next delivery

- **Delivery Completion**:
  - Returns robot to HOME when all deliveries complete
  - Success notification
  - Option to cancel at any time

#### 4. **Data Model** (`data_model.py`)
- **DeliveryRequest Class**:
  - Unique request ID (REQ0001, REQ0002, etc.)
  - User name, object, target station
  - Status tracking
  - Timestamp tracking

- **DeliverySystem Class**:
  - Central management of all requests
  - Request creation and tracking
  - Selection and queuing
  - Closest-first routing algorithm
  - System state management

## Workflow

### Complete Delivery Workflow

#### **User Side**
```
1. User logs into GUI
   └─ Username/Password authentication
   
2. User creates delivery request
   └─ Select object
   └─ Select target station
   └─ Submit (generates Request ID)
   
3. User receives confirmation
   └─ View in request history
```

#### **Manager Side**
```
1. Manager logs into GUI
   └─ Username/Password authentication
   
2. Manager views pending requests
   └─ List shows all unprocessed orders
   
3. Manager selects requests
   └─ Checkbox selection for multiple requests
   └─ "Refresh" updates list
   
4. Manager presses "Open Lid (Manager Verification)"
   └─ Vision system activates at HOME
   └─ Facial recognition verification dialog
   └─ Upon verification: lid opens
   
5. Manager loads items into robot
   └─ Lid is open
   
6. Manager presses "Close Lid / Start Delivery"
   └─ System sorts requests by closest station first
   └─ Robot begins delivery journey
   
7. For each delivery:
   a. Robot navigates to target station
   b. Upon arrival: vision activates
   c. Expected user must stand in front
   d. Facial recognition verifies user identity
   e. Lid opens automatically
   f. User takes item
   g. User presses "User Confirmed Receipt" (in GUI simulation)
   h. Lid closes
   
8. Progression:
   └─ If more deliveries: go to next target
   └─ If no more deliveries: return to HOME
   
9. Mission completes
   └─ Success message
   └─ Ready for new requests
```

## Key Features

### Request Management
- ✅ Unique request ID generation
- ✅ Request status lifecycle tracking
- ✅ Timestamp recording
- ✅ Multi-request batch handling

### Routing Intelligence
- ✅ Closest-first station selection
- ✅ Automatic queue optimization
- ✅ Multi-delivery journey support

### Vision Integration (Simulated)
- ✅ Manager verification at HOME
- ✅ User verification at delivery stations
- ✅ Automatic lid control
- ✅ Dialog-based verification feedback

### User Experience
- ✅ Intuitive dual-role interface
- ✅ Real-time status updates
- ✅ Clear visual feedback
- ✅ Request history with status colors
- ✅ Smooth page transitions
- ✅ Logout functionality

## File Structure

```
delivery_robot_gui/
├── main.py                          # Main application entry point
├── data_model.py                    # Data models and system logic
├── pages/
│   ├── login_page.py               # Login and role selection
│   ├── user_dashboard_page.py      # User request creation
│   ├── manager_dashboard_page.py   # Manager delivery control
│   ├── dashboard_page.py           # Original dashboard (optional)
│   ├── request_page.py             # Original request page (optional)
│   └── manual_control_page.py      # Original manual control (optional)
├── widgets/
│   └── sidebar.py                  # Navigation sidebar
├── assets/
│   └── workshop_bg.jpg             # Background image (optional)
└── README.md                        # This file
```

## Running the Application

### Prerequisites
```bash
pip install PySide6
```

### Launch
```bash
python main.py
```

### Demo Workflow

1. **First Login as User**:
   - Click "User" button
   - Enter username: `john_user`
   - Enter password: `password`
   - Create a request for "Package A" to "Station B"
   - View in request history

2. **Login as Manager**:
   - Logout from user dashboard
   - Click "Manager" button
   - Enter username: `alice_manager`
   - Enter password: `password`
   - View pending requests
   - Select requests and start delivery
   - Follow verification flow

## Vision System (Simulated)

The application simulates vision-based verification with popup dialogs:

### Manager Verification (at HOME)
```
🔍 Vision System Activated
Manager Verification in Progress...
✅ Manager Verified Successfully!
```

### User Verification (at Target Station)
```
🔍 Vision System Verification
User Verified Successfully!
```

## Status Colors

In Request History:
- 🟢 Green: Completed
- 🟡 Yellow: Delivering
- 🔴 Red: Cancelled
- 🔵 Blue: Pending

## System State Management

States shown in Manager Dashboard:
- **LOADING**: Manager is loading items (lid open)
- **DELIVERING**: Robot en route to target
- **WAITING FOR USER VERIFICATION**: At target, waiting for user
- **RETURNING HOME**: All deliveries complete, heading home
- **IDLE**: System ready for new requests

## Future Enhancements

- Integration with actual ROS robot
- Real camera feed from robot
- Actual facial recognition API
- Database persistence
- Route optimization algorithm
- Real-time GPS tracking
- SMS/Email notifications
- Request priority levels
- Multiple delivery zones
- Robot maintenance scheduling

## Notes

- Application uses simulated vision verification for demonstration
- All requests are stored in memory (not persistent)
- Station positions: A=1, B=2, C=3 (for routing priority)
- Username/password authentication is simplified (accepts any non-empty input)
