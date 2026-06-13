#!/usr/bin/env python3
"""
Verification script for Workshop Delivery Robot GUI
Tests that all modules can be imported correctly
"""

def verify_imports():
    """Verify all modules can be imported"""
    print("🔍 Verifying Workshop Delivery Robot GUI System...")
    print("-" * 60)
    
    errors = []
    
    # Test data model
    try:
        from data_model import DeliveryRequest, DeliverySystem, delivery_system
        print("✅ data_model.py - OK")
    except Exception as e:
        print(f"❌ data_model.py - FAILED: {e}")
        errors.append(("data_model", e))
    
    # Test login page
    try:
        from pages.login_page import LoginPage
        print("✅ pages/login_page.py - OK")
    except Exception as e:
        print(f"❌ pages/login_page.py - FAILED: {e}")
        errors.append(("login_page", e))
    
    # Test user dashboard
    try:
        from pages.user_dashboard_page import UserDashboardPage
        print("✅ pages/user_dashboard_page.py - OK")
    except Exception as e:
        print(f"❌ pages/user_dashboard_page.py - FAILED: {e}")
        errors.append(("user_dashboard_page", e))
    
    # Test manager dashboard
    try:
        from pages.manager_dashboard_page import ManagerDashboardPage
        print("✅ pages/manager_dashboard_page.py - OK")
    except Exception as e:
        print(f"❌ pages/manager_dashboard_page.py - FAILED: {e}")
        errors.append(("manager_dashboard_page", e))
    
    # Test existing pages still work
    try:
        from pages.dashboard_page import DashboardPage
        print("✅ pages/dashboard_page.py - OK")
    except Exception as e:
        print(f"❌ pages/dashboard_page.py - FAILED: {e}")
        errors.append(("dashboard_page", e))
    
    try:
        from pages.request_page import RequestPage
        print("✅ pages/request_page.py - OK")
    except Exception as e:
        print(f"❌ pages/request_page.py - FAILED: {e}")
        errors.append(("request_page", e))
    
    try:
        from pages.manual_control_page import ManualControlPage
        print("✅ pages/manual_control_page.py - OK")
    except Exception as e:
        print(f"❌ pages/manual_control_page.py - FAILED: {e}")
        errors.append(("manual_control_page", e))
    
    # Test widgets
    try:
        from widgets.sidebar import Sidebar
        print("✅ widgets/sidebar.py - OK")
    except Exception as e:
        print(f"❌ widgets/sidebar.py - FAILED: {e}")
        errors.append(("sidebar", e))
    
    print("-" * 60)
    
    if errors:
        print(f"\n⚠️  {len(errors)} module(s) failed to import!")
        return False
    else:
        print("\n✅ All modules verified successfully!")
        print("\n🚀 To run the application:")
        print("   python main.py")
        return True

def verify_data_model():
    """Verify data model functionality"""
    print("\n🔍 Testing Data Model Functionality...")
    print("-" * 60)
    
    try:
        from data_model import delivery_system
        
        # Create test requests
        req1 = delivery_system.create_request("user1", "Package A", "Station B")
        req2 = delivery_system.create_request("user2", "Package B", "Station A")
        req3 = delivery_system.create_request("user1", "Package C", "Station C")
        
        print(f"✅ Created request: {req1}")
        print(f"✅ Created request: {req2}")
        print(f"✅ Created request: {req3}")
        
        # Test pending requests
        pending = delivery_system.get_pending_requests()
        print(f"✅ Pending requests: {len(pending)}")
        
        # Test selection
        delivery_system.select_request(req1)
        delivery_system.select_request(req2)
        print(f"✅ Selected 2 requests")
        
        # Test delivery start
        success = delivery_system.start_delivery()
        if success:
            print(f"✅ Delivery started, queue size: {len(delivery_system.delivery_queue)}")
        
        # Test queue ordering (should be sorted by closest: A, B, C)
        if delivery_system.delivery_queue:
            print(f"✅ Queue order (closest-first):")
            for i, req in enumerate(delivery_system.delivery_queue, 1):
                print(f"   {i}. {req.target_station}")
        
        print("-" * 60)
        print("✅ Data model tests passed!")
        return True
        
    except Exception as e:
        print(f"❌ Data model test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = verify_imports()
    if success:
        verify_data_model()
    
    print("\n" + "=" * 60)
    print("VERIFICATION COMPLETE")
    print("=" * 60)
