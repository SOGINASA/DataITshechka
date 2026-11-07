#!/bin/sh
set -e
flask --app app:create_app db upgrade
flask --app app:create_app seed-checklist
exec gunicorn --workers 2 --threads 4 --bind 0.0.0.0:6767 --timeout 360 'app:create_app()'
