import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'catering_site.settings')
django.setup()

from django.test import Client
c = Client()
res = c.post('/admin-panel/login/', {'username': 'CB-ADMIN', 'password': 'password123'})
print("Login status:", res.status_code)
if res.status_code == 302:
    dashboard_res = c.get(res.url)
    print("Dashboard status:", dashboard_res.status_code)
    if dashboard_res.status_code == 500:
        print(dashboard_res.content.decode()[:1000])
