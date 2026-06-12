"""Report generation and export functionality"""
import csv
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from database import db
from analytics import analytics


class ReportGenerator:
    """Generate and export delivery reports"""
    
    def __init__(self, output_dir: str = "reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
    
    def generate_csv_export(self, filename: str = None) -> str:
        """Export all requests to CSV file"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"delivery_requests_{timestamp}.csv"
        
        filepath = self.output_dir / filename
        
        all_requests = db.get_all_requests()
        
        if not all_requests:
            return str(filepath)  # Return path even if empty
        
        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['request_id', 'user_name', 'object_requested', 'target_station', 
                         'status', 'created_at', 'updated_at']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for req in all_requests:
                writer.writerow(req)
        
        return str(filepath)
    
    def generate_text_report(self, filename: str = None) -> str:
        """Generate a text summary report"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"delivery_report_{timestamp}.txt"
        
        filepath = self.output_dir / filename
        
        report_text = analytics.export_summary_report()
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report_text)
        
        return str(filepath)
    
    def generate_user_report(self, filename: str = None) -> str:
        """Generate per-user detailed report"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"user_report_{timestamp}.txt"
        
        filepath = self.output_dir / filename
        
        report_lines = []
        report_lines.append("=" * 70)
        report_lines.append("USER DELIVERY REPORT")
        report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append("=" * 70)
        
        user_stats = analytics.get_user_statistics()
        
        for user in sorted(user_stats.keys()):
            report_lines.append(f"\n📦 USER: {user}")
            report_lines.append("-" * 70)
            
            stats = user_stats[user]
            report_lines.append(f"  Total Requests: {stats['total']}")
            report_lines.append(f"  Completed: {stats['completed']}")
            report_lines.append(f"  Pending: {stats['pending']}")
            report_lines.append(f"  Cancelled: {stats['cancelled']}")
            report_lines.append(f"  Delivering: {stats['delivering']}")
            
            if stats['total'] > 0:
                completion_rate = (stats['completed'] / stats['total']) * 100
                report_lines.append(f"  Completion Rate: {completion_rate:.1f}%")
            
            # Get user's requests
            user_reqs = db.get_requests_by_user(user)
            report_lines.append(f"\n  Recent Requests:")
            for req in user_reqs[:5]:  # Last 5
                report_lines.append(f"    - {req['request_id']}: {req['object_requested']} → "
                                  f"{req['target_station']} ({req['status']})")
        
        report_lines.append("\n" + "=" * 70)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("\n".join(report_lines))
        
        return str(filepath)
    
    def generate_daily_report(self, filename: str = None) -> str:
        """Generate daily statistics report"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"daily_report_{timestamp}.txt"
        
        filepath = self.output_dir / filename
        
        report_lines = []
        report_lines.append("=" * 70)
        report_lines.append("DAILY DELIVERY STATISTICS")
        report_lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append("=" * 70)
        
        daily_stats = analytics.get_daily_statistics(days_back=30)
        
        for date in sorted(daily_stats.keys(), reverse=True):
            stats = daily_stats[date]
            report_lines.append(f"\n📅 {date}")
            report_lines.append(f"  Total: {stats['total']} | "
                              f"Completed: {stats['completed']} | "
                              f"Pending: {stats['pending']} | "
                              f"Cancelled: {stats['cancelled']}")
        
        report_lines.append("\n" + "=" * 70)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("\n".join(report_lines))
        
        return str(filepath)
    
    def generate_html_report(self, filename: str = None) -> str:
        """Generate an HTML report for browser viewing"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"delivery_report_{timestamp}.html"
        
        filepath = self.output_dir / filename
        
        total_count = db.get_request_count()
        completed_count = db.get_request_count("completed")
        pending_count = db.get_request_count("pending")
        cancelled_count = db.get_request_count("cancelled")
        
        completion_rate = analytics.get_completion_rate()
        user_stats = analytics.get_user_statistics()
        station_stats = analytics.get_station_statistics()
        
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Delivery System Report</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            background-color: #f5f5f5;
            margin: 0;
            padding: 20px;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #2d5a8c;
            padding-bottom: 10px;
        }}
        .timestamp {{
            color: #666;
            font-size: 14px;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 15px;
            margin: 20px 0;
        }}
        .stat-box {{
            background-color: #f9f9f9;
            border-left: 4px solid #2d5a8c;
            padding: 15px;
            border-radius: 4px;
        }}
        .stat-value {{
            font-size: 28px;
            font-weight: bold;
            color: #2d5a8c;
        }}
        .stat-label {{
            font-size: 14px;
            color: #666;
            margin-top: 5px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }}
        th {{
            background-color: #2d5a8c;
            color: white;
            padding: 10px;
            text-align: left;
        }}
        td {{
            padding: 10px;
            border-bottom: 1px solid #ddd;
        }}
        tr:hover {{
            background-color: #f5f5f5;
        }}
        h2 {{
            color: #333;
            margin-top: 30px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Delivery System Report</h1>
        <p class="timestamp">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        
        <h2>📊 Overall Statistics</h2>
        <div class="stats-grid">
            <div class="stat-box">
                <div class="stat-value">{total_count}</div>
                <div class="stat-label">Total Requests</div>
            </div>
            <div class="stat-box">
                <div class="stat-value">{completed_count}</div>
                <div class="stat-label">Completed</div>
            </div>
            <div class="stat-box">
                <div class="stat-value">{pending_count}</div>
                <div class="stat-label">Pending</div>
            </div>
            <div class="stat-box">
                <div class="stat-value">{cancelled_count}</div>
                <div class="stat-label">Cancelled</div>
            </div>
        </div>
        
        <p><strong>Completion Rate:</strong> {completion_rate:.1f}%</p>
        
        <h2>👥 User Statistics</h2>
        <table>
            <tr>
                <th>User</th>
                <th>Total</th>
                <th>Completed</th>
                <th>Pending</th>
                <th>Cancelled</th>
            </tr>
"""
        
        for user in sorted(user_stats.keys()):
            stats = user_stats[user]
            html_content += f"""
            <tr>
                <td>{user}</td>
                <td>{stats['total']}</td>
                <td>{stats['completed']}</td>
                <td>{stats['pending']}</td>
                <td>{stats['cancelled']}</td>
            </tr>
"""
        
        html_content += """
        </table>
        
        <h2>🏢 Station Statistics</h2>
        <table>
            <tr>
                <th>Station</th>
                <th>Requests</th>
            </tr>
"""
        
        for station in sorted(station_stats.keys()):
            html_content += f"""
            <tr>
                <td>{station}</td>
                <td>{station_stats[station]}</td>
            </tr>
"""
        
        html_content += """
        </table>
    </div>
</body>
</html>
"""
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        return str(filepath)
    
    def list_reports(self) -> List[str]:
        """List all generated reports"""
        if not self.output_dir.exists():
            return []
        
        return [str(f) for f in self.output_dir.glob("*") if f.is_file()]


# Global report generator instance
report_generator = ReportGenerator()
