# Heroku / Render deployment entrypoint
# Uses gunicorn as the production WSGI server
web: gunicorn accessable_india.wsgi:application --workers 3 --bind 0.0.0.0:$PORT
