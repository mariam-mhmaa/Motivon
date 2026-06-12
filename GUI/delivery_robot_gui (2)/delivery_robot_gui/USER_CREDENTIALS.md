# User Credentials - Delivery Robot GUI

## Predefined Users

The system now includes predefined user accounts with specific roles and credentials:

### Worker/Manager Account
- **Username**: `nour`
- **Password**: `nour123`
- **Role**: Worker (can login as Manager)
- **Permissions**: View all pending requests, manage deliveries, coordinate with users

### Regular Users
These users can create delivery requests and receive items:

| Username | Password | Role |
|----------|----------|------|
| ainour | ainour123 | User |
| mariam | mariam123 | User |
| zeina | zeina123 | User |

## How to Use

### For Users (ainour, mariam, zeina):
1. Launch the application: `python main.py`
2. Click "User" button
3. Enter your username and password
4. Create a delivery request (object + target station)
5. View your request history

**Example:**
- Username: `ainour`
- Password: `ainour123`

### For Manager/Worker (nour):
1. Launch the application: `python main.py`
2. Click "Manager" button (or "Worker" if available)
3. Enter credentials:
   - Username: `nour`
   - Password: `nour123`
4. View pending requests from all users
5. Select and process deliveries
6. Coordinate deliveries to stations

## User Roles Mapping

```
Worker: nour
  ↓
Can login as Manager/Worker
  ↓
Can view all requests
Can manage delivery coordination
Can verify users at delivery stations

Regular Users: ainour, mariam, zeina
  ↓
Can login as User
  ↓
Can create requests
Can view their own request history
Can receive items at stations
```

## Authentication Validation

The login system now validates:
1. ✅ Username exists in system
2. ✅ Password matches credentials
3. ✅ User role matches login type (Worker can only login as Manager, Users can only login as User)

If authentication fails, you'll see an error message with available users listed.

## Note

- The worker account (nour) can only login via the "Manager" option
- User accounts (ainour, mariam, zeina) can only login via the "User" option
- Passwords are case-sensitive
- All credentials are stored in `data_model.py` for demo purposes
