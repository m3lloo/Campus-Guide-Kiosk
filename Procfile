web: gunicorn --workers 1 --worker-class sync --bind 0.0.0.0:$PORT --timeout 180 --max-requests 100 --max-requests-jitter 10 app:app
