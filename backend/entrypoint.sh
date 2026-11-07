#!/bin/sh
set -e
flask --app app:create_app db upgrade
exec gunicorn --workers 2 --threads 4 --bind 0.0.0.0:5000 --timeout 60 'app:create_app()'
