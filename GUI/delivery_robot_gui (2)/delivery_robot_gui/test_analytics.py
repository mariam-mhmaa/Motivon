"""Test analytics and reporting functionality"""
from analytics import analytics
from reports import report_generator
from data_model import delivery_system
import os

print("=" * 70)
print("TESTING ANALYTICS AND REPORTING")
print("=" * 70)

# Test 1: Create test data
print("\n✅ Test 1: Creating test data")
test_users = ["ainour", "mariam", "zeina"]
test_stations = ["Station A", "Station B", "Station C"]

for i, user in enumerate(test_users):
    for j, station in enumerate(test_stations):
        req = delivery_system.create_request(user, f"Object-{i*3+j}", station)
        print(f"Created: {req.request_id} for {user}")

# Test 2: Analytics queries
print("\n✅ Test 2: Analytics queries")

print("\n  📊 User Statistics:")
user_stats = analytics.get_user_statistics()
for user, stats in user_stats.items():
    print(f"    {user}: {stats['total']} requests")

print("\n  🏢 Station Statistics:")
station_stats = analytics.get_station_statistics()
for station, count in station_stats.items():
    print(f"    {station}: {count} requests")

print(f"\n  📈 Completion Rate: {analytics.get_completion_rate():.1f}%")
print(f"  🔝 Busiest User: {analytics.get_busiest_user()}")
print(f"  🏆 Peak Station: {analytics.get_peak_station()}")

# Test 3: Summary Report
print("\n✅ Test 3: Summary report")
report_text = analytics.export_summary_report()
print(report_text)

# Test 4: CSV Export
print("\n✅ Test 4: CSV Export")
csv_file = report_generator.generate_csv_export()
print(f"CSV exported to: {csv_file}")

# Verify CSV content
with open(csv_file, 'r') as f:
    lines = f.readlines()
    print(f"CSV lines: {len(lines)} (header + {len(lines)-1} data rows)")

# Test 5: Text Report Export
print("\n✅ Test 5: Text Report Export")
text_file = report_generator.generate_text_report()
print(f"Text report exported to: {text_file}")

# Test 6: HTML Report Export
print("\n✅ Test 6: HTML Report Export")
html_file = report_generator.generate_html_report()
print(f"HTML report exported to: {html_file}")

# Test 7: User Report Export
print("\n✅ Test 7: User Report Export")
user_file = report_generator.generate_user_report()
print(f"User report exported to: {user_file}")

# Test 8: Daily Report Export
print("\n✅ Test 8: Daily Report Export")
daily_file = report_generator.generate_daily_report()
print(f"Daily report exported to: {daily_file}")

# Test 9: List Reports
print("\n✅ Test 9: List Reports")
reports = report_generator.list_reports()
print(f"Generated {len(reports)} reports:")
for report in reports:
    size_kb = os.path.getsize(report) / 1024
    print(f"  - {os.path.basename(report)} ({size_kb:.1f} KB)")

# Test 10: Request History Query
print("\n✅ Test 10: Request History Query")
history = analytics.get_request_history(user_name="ainour")
print(f"Ainour's requests: {len(history)}")
for req in history:
    print(f"  - {req['request_id']}: {req['object_requested']} → {req['target_station']}")

print("\n" + "=" * 70)
print("ANALYTICS AND REPORTING TESTS COMPLETED ✅")
print("=" * 70)
