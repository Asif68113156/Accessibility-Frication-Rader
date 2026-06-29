import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "accessable_india.settings")
django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()

try:
    admin = User.objects.get(username='admin')
    admin.set_password('admin123')
    admin.role = 'superadmin'
    admin.is_staff = True
    admin.is_superuser = True
    admin.save()
    print("Existing admin password updated.")
except User.DoesNotExist:
    admin = User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
    admin.role = 'superadmin'
    admin.save()
    print("New admin created.")
