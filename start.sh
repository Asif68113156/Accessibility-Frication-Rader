#!/usr/bin/env bash
# run migrations at runtime to establish ownership and create SQL tables dynamically
python manage.py migrate

# boot up the web server
gunicorn accessable_india.wsgi:application --workers 3 --bind 0.0.0.0:$PORT
