"""Data model for managing requests and system state"""
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime
from database import db


# Predefined users and credentials
PREDEFINED_USERS = {
    # Worker/Manager account
    "nour": "nour6",
    # Regular users
    "ainour": "ainour5",
    "mariam": "mariam6",
    "zeina": "zeina5",
}

# Role mapping
USER_ROLES = {
    "nour": "worker",
    "ainour": "user",
    "mariam": "user",
    "zeina": "user",
}


@dataclass
class DeliveryRequest:
    """Represents a delivery request"""
    request_id: str
    user_name: str
    object_requested: str
    target_station: str  # "Station A", "Station B", or "Station C"
    status: str = "pending"  # pending, selected, delivering, completed, cancelled
    created_at: datetime = field(default_factory=datetime.now)
    
    def __str__(self):
        return f"ID:{self.request_id} | User:{self.user_name} | Object:{self.object_requested} | Target:{self.target_station}"


class DeliverySystem:
    """Central system for managing delivery requests and state"""
    
    # Station positions (for closest-first sorting)
    STATIONS = {
        "Station A": {"position": 1},
        "Station B": {"position": 2},
        "Station C": {"position": 3},
    }
    
    def __init__(self):
        self.all_requests: List[DeliveryRequest] = []
        self.request_counter = 0
        self.current_user = None
        self.current_manager = None
        self.selected_requests: List[DeliveryRequest] = []
        self.delivery_queue: List[DeliveryRequest] = []
        self.current_delivery: Optional[DeliveryRequest] = None
        self.system_state = "idle"  # idle, loading, delivering, waiting_user, returning_home
        
        # Load requests from database
        self._load_requests_from_db()
        
    def create_request(self, user_name: str, object_requested: str, target_station: str) -> DeliveryRequest:
        """Create a new delivery request"""
        self.request_counter += 1
        request_id = f"REQ{self.request_counter:04d}"
        
        request = DeliveryRequest(
            request_id=request_id,
            user_name=user_name,
            object_requested=object_requested,
            target_station=target_station,
            status="pending"
        )
        
        self.all_requests.append(request)
        
        # Save to database
        db.create_request(request_id, user_name, object_requested, target_station, "pending")
        
        return request
    
    def get_pending_requests(self) -> List[DeliveryRequest]:
        """Get all pending requests"""
        return [r for r in self.all_requests if r.status == "pending"]
    
    def select_request(self, request: DeliveryRequest):
        """Select a request for delivery"""
        if request not in self.selected_requests:
            self.selected_requests.append(request)
            request.status = "selected"
            # Update in database
            db.update_request_status(request.request_id, "selected")
    
    def deselect_request(self, request: DeliveryRequest):
        """Deselect a request"""
        if request in self.selected_requests:
            self.selected_requests.remove(request)
            request.status = "pending"
    
    def start_delivery(self) -> bool:
        """Start delivery with selected requests (sorted by closest first)"""
        if not self.selected_requests:
            return False
        
        # Sort by closest position first
        sorted_requests = sorted(
            self.selected_requests,
            key=lambda r: self.STATIONS[r.target_station]["position"]
        )
        
        self.delivery_queue = sorted_requests.copy()
        
        # Set all selected to "delivering" and update in database
        for req in self.selected_requests:
            req.status = "delivering"
            db.update_request_status(req.request_id, "delivering")
        
        self.selected_requests.clear()
        self.system_state = "loading"
        return True
    
    def get_next_delivery(self) -> Optional[DeliveryRequest]:
        """Get the next delivery from queue"""
        if self.delivery_queue:
            self.current_delivery = self.delivery_queue.pop(0)
            self.system_state = "delivering"
            return self.current_delivery
        else:
            self.system_state = "returning_home"
            self.current_delivery = None
            return None
    
    def complete_current_delivery(self):
        """Mark current delivery as received by user"""
        if self.current_delivery:
            self.current_delivery.status = "completed"
            # Update in database
            db.update_request_status(self.current_delivery.request_id, "completed")
            self.current_delivery = None
    
    def cancel_delivery(self, request: DeliveryRequest):
        """Cancel a delivery request"""
        request.status = "cancelled"
        if request in self.selected_requests:
            self.selected_requests.remove(request)
        if request in self.delivery_queue:
            self.delivery_queue.remove(request)
        
        # Update in database
        db.update_request_status(request.request_id, "cancelled")
    
    def _load_requests_from_db(self):
        """Load all requests from database into memory"""
        db_requests = db.get_all_requests()
        
        for req_data in db_requests:
            # Parse datetime from ISO format string
            created_at = datetime.fromisoformat(req_data['created_at'])
            
            request = DeliveryRequest(
                request_id=req_data['request_id'],
                user_name=req_data['user_name'],
                object_requested=req_data['object_requested'],
                target_station=req_data['target_station'],
                status=req_data['status'],
                created_at=created_at
            )
            self.all_requests.append(request)
            
            # Update counter to ensure new requests get unique IDs
            request_num = int(req_data['request_id'].replace('REQ', ''))
            if request_num > self.request_counter:
                self.request_counter = request_num
    
    def reset_delivery_cycle(self):
        """Reset after delivery cycle completes"""
        self.delivery_queue.clear()
        self.current_delivery = None
        self.system_state = "idle"
    
    def get_delivery_statistics(self):
        """Get statistics about requests"""
        total = len(self.all_requests)
        pending = len(self.get_pending_requests())
        completed = len([r for r in self.all_requests if r.status == "completed"])
        cancelled = len([r for r in self.all_requests if r.status == "cancelled"])
        
        return {
            "total": total,
            "pending": pending,
            "completed": completed,
            "cancelled": cancelled,
        }


# Global instance
delivery_system = DeliverySystem()
