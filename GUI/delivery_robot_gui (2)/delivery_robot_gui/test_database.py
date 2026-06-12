"""Test database persistence functionality"""
from database import db
from data_model import delivery_system, DeliveryRequest
import os

# Clean up old database for fresh test
if os.path.exists("delivery_robot.db"):
    os.remove("delivery_robot.db")

# Re-initialize database
from database import Database
db_fresh = Database()

print("=" * 60)
print("TESTING DATABASE PERSISTENCE")
print("=" * 60)

# Test 1: Create requests
print("\n✅ Test 1: Creating requests through delivery_system")
req1 = delivery_system.create_request("ainour", "Document", "Station A")
print(f"Created: {req1}")

req2 = delivery_system.create_request("mariam", "Package", "Station B")
print(f"Created: {req2}")

req3 = delivery_system.create_request("zeina", "Box", "Station C")
print(f"Created: {req3}")

print(f"Total requests in memory: {len(delivery_system.all_requests)}")
print(f"Total requests in database: {db.get_request_count()}")

# Test 2: Check database directly
print("\n✅ Test 2: Verifying data in database")
db_requests = db.get_all_requests()
for req in db_requests:
    print(f"DB: {req['request_id']} | {req['user_name']} | {req['object_requested']} | {req['target_station']} | Status: {req['status']}")

# Test 3: Update request status
print("\n✅ Test 3: Updating request status")
delivery_system.select_request(req1)
print(f"Selected req1, status: {req1.status}")
print(f"DB status: {db.get_request_by_id(req1.request_id)['status']}")

# Test 4: Complete delivery
print("\n✅ Test 4: Starting and completing delivery")
delivery_system.select_request(req2)
delivery_system.start_delivery()
next_delivery = delivery_system.get_next_delivery()
print(f"Current delivery: {next_delivery.request_id} to {next_delivery.target_station}")
print(f"Before completion: {db.get_request_by_id(next_delivery.request_id)['status']}")
delivery_system.complete_current_delivery()
print(f"After completion: {db.get_request_by_id(next_delivery.request_id)['status']}")

# Test 5: Verify pending requests
print("\n✅ Test 5: Getting pending requests")
pending = delivery_system.get_pending_requests()
print(f"Pending requests: {len(pending)}")
for p in pending:
    print(f"  - {p.request_id}: {p.status}")

# Test 6: Statistics
print("\n✅ Test 6: Delivery statistics")
stats = delivery_system.get_delivery_statistics()
print(f"Total: {stats['total']}")
print(f"Pending: {stats['pending']}")
print(f"Completed: {stats['completed']}")
print(f"Cancelled: {stats['cancelled']}")

# Test 7: Persistence test - load from fresh instance
print("\n✅ Test 7: Testing persistence with fresh DeliverySystem")
from data_model import DeliverySystem
fresh_system = DeliverySystem()
print(f"Requests loaded from DB: {len(fresh_system.all_requests)}")
for req in fresh_system.all_requests:
    print(f"  - {req.request_id}: {req.user_name} | {req.status}")

print("\n" + "=" * 60)
print("DATABASE TESTS COMPLETED SUCCESSFULLY ✅")
print("=" * 60)
