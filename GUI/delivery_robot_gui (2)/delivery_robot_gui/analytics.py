"""Analytics module for delivery statistics and insights"""
from datetime import datetime, timedelta
from typing import Dict, List, Any
from database import db


class DeliveryAnalytics:
    """Generate analytics and reports for delivery system"""
    
    def __init__(self):
        self.db = db
    
    def get_daily_statistics(self, days_back: int = 30) -> Dict[str, Any]:
        """Get statistics for the last N days"""
        all_requests = self.db.get_all_requests()
        cutoff_date = datetime.now() - timedelta(days=days_back)
        
        daily_stats = {}
        
        for req in all_requests:
            created_at = datetime.fromisoformat(req['created_at'])
            
            if created_at >= cutoff_date:
                date_key = created_at.strftime("%Y-%m-%d")
                
                if date_key not in daily_stats:
                    daily_stats[date_key] = {
                        'total': 0,
                        'completed': 0,
                        'pending': 0,
                        'cancelled': 0,
                        'delivering': 0,
                    }
                
                daily_stats[date_key]['total'] += 1
                daily_stats[date_key][req['status']] += 1
        
        return daily_stats
    
    def get_user_statistics(self) -> Dict[str, Dict[str, int]]:
        """Get request statistics per user"""
        all_requests = self.db.get_all_requests()
        user_stats = {}
        
        for req in all_requests:
            user = req['user_name']
            
            if user not in user_stats:
                user_stats[user] = {
                    'total': 0,
                    'completed': 0,
                    'pending': 0,
                    'cancelled': 0,
                    'delivering': 0,
                }
            
            user_stats[user]['total'] += 1
            user_stats[user][req['status']] += 1
        
        return user_stats
    
    def get_station_statistics(self) -> Dict[str, int]:
        """Get request statistics per station"""
        all_requests = self.db.get_all_requests()
        station_stats = {}
        
        for req in all_requests:
            station = req['target_station']
            
            if station not in station_stats:
                station_stats[station] = 0
            
            station_stats[station] += 1
        
        return dict(sorted(station_stats.items()))
    
    def get_completion_rate(self) -> float:
        """Get percentage of completed requests"""
        all_requests = self.db.get_all_requests()
        
        if not all_requests:
            return 0.0
        
        completed = len([r for r in all_requests if r['status'] == 'completed'])
        return (completed / len(all_requests)) * 100
    
    def get_average_completion_time(self) -> Dict[str, Any]:
        """Get average time from creation to completion"""
        all_requests = self.db.get_all_requests()
        completed_requests = [r for r in all_requests if r['status'] == 'completed']
        
        if not completed_requests:
            return {
                'average_hours': 0,
                'average_minutes': 0,
                'requests_analyzed': 0,
            }
        
        total_time = timedelta()
        
        for req in completed_requests:
            created = datetime.fromisoformat(req['created_at'])
            updated = datetime.fromisoformat(req['updated_at'])
            total_time += (updated - created)
        
        avg_time = total_time / len(completed_requests)
        
        return {
            'average_hours': int(avg_time.total_seconds() / 3600),
            'average_minutes': int((avg_time.total_seconds() % 3600) / 60),
            'requests_analyzed': len(completed_requests),
        }
    
    def get_peak_station(self) -> str:
        """Get the station with most requests"""
        station_stats = self.get_station_statistics()
        
        if not station_stats:
            return "N/A"
        
        return max(station_stats, key=station_stats.get)
    
    def get_busiest_user(self) -> str:
        """Get the user with most requests"""
        user_stats = self.get_user_statistics()
        
        if not user_stats:
            return "N/A"
        
        return max(user_stats, key=lambda u: user_stats[u]['total'])
    
    def export_summary_report(self) -> str:
        """Generate a text summary report"""
        user_stats = self.get_user_statistics()
        station_stats = self.get_station_statistics()
        completion_rate = self.get_completion_rate()
        avg_time = self.get_average_completion_time()
        total_count = self.db.get_request_count()
        
        report = []
        report.append("=" * 60)
        report.append("DELIVERY SYSTEM ANALYTICS REPORT")
        report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append("=" * 60)
        
        report.append("\n📊 OVERALL STATISTICS")
        report.append(f"Total Requests: {total_count}")
        report.append(f"Completed: {self.db.get_request_count('completed')}")
        report.append(f"Pending: {self.db.get_request_count('pending')}")
        report.append(f"Cancelled: {self.db.get_request_count('cancelled')}")
        report.append(f"Completion Rate: {completion_rate:.1f}%")
        
        report.append("\n👥 USER STATISTICS")
        for user, stats in sorted(user_stats.items()):
            report.append(f"  {user}: {stats['total']} requests ({stats['completed']} completed)")
        
        report.append("\n🏢 STATION STATISTICS")
        for station, count in sorted(station_stats.items()):
            report.append(f"  {station}: {count} requests")
        
        if avg_time['requests_analyzed'] > 0:
            report.append("\n⏱️  PERFORMANCE METRICS")
            report.append(f"Average Completion Time: {avg_time['average_hours']}h {avg_time['average_minutes']}m")
            report.append(f"Requests Analyzed: {avg_time['requests_analyzed']}")
        
        report.append("\n" + "=" * 60)
        
        return "\n".join(report)
    
    def get_request_history(self, user_name: str = None, status: str = None) -> List[Dict[str, Any]]:
        """Get filtered request history"""
        if user_name:
            requests = self.db.get_requests_by_user(user_name)
        elif status:
            requests = self.db.get_requests_by_status(status)
        else:
            requests = self.db.get_all_requests()
        
        return requests


# Global analytics instance
analytics = DeliveryAnalytics()
