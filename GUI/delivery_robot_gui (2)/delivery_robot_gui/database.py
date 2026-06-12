"""Database module for persistent data storage using SQLite"""
import sqlite3
import os
from datetime import datetime
from typing import List, Optional, Dict, Any

DB_PATH = "delivery_robot.db"


class Database:
    """Handles all database operations for the delivery system"""
    
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.init_database()
    
    def get_connection(self):
        """Get database connection"""
        return sqlite3.connect(self.db_path)
    
    def init_database(self):
        """Initialize database tables if they don't exist"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Create requests table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS delivery_requests (
                request_id TEXT PRIMARY KEY,
                user_name TEXT NOT NULL,
                object_requested TEXT NOT NULL,
                target_station TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        ''')
        
        # Create index for faster queries
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_status ON delivery_requests(status)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_user_name ON delivery_requests(user_name)
        ''')
        
        conn.commit()
        conn.close()
    
    def create_request(self, request_id: str, user_name: str, object_requested: str, 
                      target_station: str, status: str = "pending") -> bool:
        """Create a new delivery request"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            cursor.execute('''
                INSERT INTO delivery_requests 
                (request_id, user_name, object_requested, target_station, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (request_id, user_name, object_requested, target_station, status, now, now))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error creating request: {e}")
            return False
    
    def get_all_requests(self) -> List[Dict[str, Any]]:
        """Get all requests from database"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM delivery_requests ORDER BY created_at DESC')
            columns = [description[0] for description in cursor.description]
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            print(f"Error fetching all requests: {e}")
            return []
    
    def get_requests_by_status(self, status: str) -> List[Dict[str, Any]]:
        """Get requests filtered by status"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM delivery_requests 
                WHERE status = ? 
                ORDER BY created_at DESC
            ''', (status,))
            
            columns = [description[0] for description in cursor.description]
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            print(f"Error fetching requests by status: {e}")
            return []
    
    def get_requests_by_user(self, user_name: str) -> List[Dict[str, Any]]:
        """Get requests created by a specific user"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM delivery_requests 
                WHERE user_name = ? 
                ORDER BY created_at DESC
            ''', (user_name,))
            
            columns = [description[0] for description in cursor.description]
            rows = cursor.fetchall()
            conn.close()
            
            return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            print(f"Error fetching requests by user: {e}")
            return []
    
    def update_request_status(self, request_id: str, status: str) -> bool:
        """Update request status"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            now = datetime.now().isoformat()
            
            cursor.execute('''
                UPDATE delivery_requests 
                SET status = ?, updated_at = ?
                WHERE request_id = ?
            ''', (status, now, request_id))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error updating request status: {e}")
            return False
    
    def get_request_by_id(self, request_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific request by ID"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM delivery_requests WHERE request_id = ?', (request_id,))
            columns = [description[0] for description in cursor.description]
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return dict(zip(columns, row))
            return None
        except Exception as e:
            print(f"Error fetching request by ID: {e}")
            return None
    
    def delete_request(self, request_id: str) -> bool:
        """Delete a request"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM delivery_requests WHERE request_id = ?', (request_id,))
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error deleting request: {e}")
            return False
    
    def clear_all_requests(self) -> bool:
        """Clear all requests (for testing/reset)"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM delivery_requests')
            
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"Error clearing requests: {e}")
            return False
    
    def get_request_count(self, status: Optional[str] = None) -> int:
        """Get count of requests, optionally filtered by status"""
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            
            if status:
                cursor.execute('SELECT COUNT(*) FROM delivery_requests WHERE status = ?', (status,))
            else:
                cursor.execute('SELECT COUNT(*) FROM delivery_requests')
            
            count = cursor.fetchone()[0]
            conn.close()
            return count
        except Exception as e:
            print(f"Error getting request count: {e}")
            return 0


# Create global database instance
db = Database()
