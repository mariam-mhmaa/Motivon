#!/usr/bin/env python3
"""
Test script to verify requests persist across logins
"""

def test_request_persistence():
    """Test that requests created by one user are visible to the manager"""
    from data_model import delivery_system, PREDEFINED_USERS
    
    print("🔍 Testing Request Persistence Across Logins...")
    print("-" * 70)
    
    # Clear any existing requests for clean test
    delivery_system.all_requests.clear()
    print(f"✅ Cleared existing requests")
    print()
    
    # Simulate User (ainour) creating a request
    print("1️⃣ User 'ainour' creates a request...")
    request1 = delivery_system.create_request(
        user_name="ainour",
        object_requested="Test Package",
        target_station="Station A"
    )
    print(f"   ✅ Request created: {request1}")
    print(f"   Status: {request1.status}")
    print()
    
    # Check pending requests (as user)
    print("2️⃣ Check pending requests (User view)...")
    pending = delivery_system.get_pending_requests()
    print(f"   Pending requests: {len(pending)}")
    for req in pending:
        print(f"   - {req}")
    print()
    
    # Simulate another user creating a request
    print("3️⃣ User 'mariam' creates another request...")
    request2 = delivery_system.create_request(
        user_name="mariam",
        object_requested="Another Package",
        target_station="Station B"
    )
    print(f"   ✅ Request created: {request2}")
    print()
    
    # Check all requests in system
    print("4️⃣ Check all requests in system...")
    print(f"   Total requests: {len(delivery_system.all_requests)}")
    for req in delivery_system.all_requests:
        print(f"   - {req.request_id}: {req.user_name} -> {req.object_requested}")
    print()
    
    # Check pending requests (as manager should see)
    print("5️⃣ Manager 'nour' checks pending requests...")
    pending = delivery_system.get_pending_requests()
    print(f"   Pending requests found: {len(pending)}")
    if len(pending) == 2:
        print(f"   ✅ SUCCESS: Both requests are visible!")
        for req in pending:
            print(f"   - {req.request_id}: {req.user_name} -> {req.object_requested}")
    else:
        print(f"   ❌ FAIL: Expected 2 pending requests, got {len(pending)}")
        if len(pending) > 0:
            for req in pending:
                print(f"   - {req}")
    print()
    
    print("-" * 70)

if __name__ == "__main__":
    test_request_persistence()
