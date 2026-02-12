import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.core.management import call_command

print("Creating migrations...")
call_command('makemigrations', 'ibkr')
print("\nRunning migrations...")
call_command('migrate')
print("\nDone!")
