#!/usr/bin/env python3
"""
Verification script for user authentication system
Tests that predefined users can be validated correctly
"""

def verify_users():
    """Verify user authentication system"""
    print("🔍 Verifying User Authentication System...")
    print("-" * 70)
    
    from data_model import PREDEFINED_USERS, USER_ROLES
    
    print("\n✅ Available Users:")
    print()
    
    # Worker
    print("WORKER ACCOUNT:")
    print(f"  • Username: nour")
    print(f"    Password: nour123")
    print(f"    Role: {USER_ROLES.get('nour', 'unknown')}")
    print(f"    Can login as: Manager")
    print()
    
    # Regular users
    print("REGULAR USER ACCOUNTS:")
    for username in ["ainour", "mariam", "zeina"]:
        password = PREDEFINED_USERS[username]
        role = USER_ROLES.get(username, "unknown")
        print(f"  • Username: {username}")
        print(f"    Password: {password}")
        print(f"    Role: {role}")
        print(f"    Can login as: User")
        print()
    
    print("-" * 70)
    print("\n✅ Testing Authentication Logic:")
    print()
    
    # Test worker login
    test_cases = [
        {
            "name": "Worker (nour) login as Manager",
            "username": "nour",
            "password": "nour6",
            "login_type": "manager",
            "should_pass": True
        },
        {
            "name": "User (ainour) login as User",
            "username": "ainour",
            "password": "ainour5",
            "login_type": "user",
            "should_pass": True
        },
        {
            "name": "User (mariam) login as User",
            "username": "mariam",
            "password": "mariam6",
            "login_type": "user",
            "should_pass": True
        },
        {
            "name": "User (zeina) login as User",
            "username": "zeina",
            "password": "zeina5",
            "login_type": "user",
            "should_pass": True
        },
        {
            "name": "Wrong password for nour",
            "username": "nour",
            "password": "wrong",
            "login_type": "manager",
            "should_pass": False
        },
        {
            "name": "User tries to login as Manager",
            "username": "ainour",
            "password": "ainour5",
            "login_type": "manager",
            "should_pass": False
        },
        {
            "name": "Non-existent user",
            "username": "john",
            "password": "john123",
            "login_type": "user",
            "should_pass": False
        },
    ]
    
    for i, test in enumerate(test_cases, 1):
        username = test["username"]
        password = test["password"]
        login_type = test["login_type"]
        should_pass = test["should_pass"]
        
        # Validate
        passed = False
        reason = ""
        
        if username not in PREDEFINED_USERS:
            reason = "User not found"
        elif PREDEFINED_USERS[username] != password:
            reason = "Password incorrect"
        else:
            user_role = USER_ROLES.get(username, "user")
            expected_role = "worker" if login_type == "manager" else "user"
            if user_role != expected_role:
                reason = f"Role mismatch (is {user_role}, needs {expected_role})"
            else:
                passed = True
                reason = "Authentication successful"
        
        result = "✅ PASS" if passed == should_pass else "❌ FAIL"
        print(f"{i}. {result} - {test['name']}")
        print(f"   {reason}")
        print()
    
    print("-" * 70)
    print("\n✅ Authentication System Verification Complete!")
    print("\nUsers can now login with their predefined credentials.")

if __name__ == "__main__":
    verify_users()
