#!/usr/bin/env bash

set -e

PROJECT_BASE_PATH='/usr/local/apps/profiles-rest-api'
ENV_PATH="$PROJECT_BASE_PATH/env"

echo "Changing directory to project path..."
cd $PROJECT_BASE_PATH

echo "Force resetting to latest code from Git..."
git fetch origin
git reset --hard origin/upgrade-python-django
git clean -fd

echo "Applying database migrations..."
$ENV_PATH/bin/python manage.py migrate

echo "Collecting static files..."
$ENV_PATH/bin/python manage.py collectstatic --noinput

echo "Restarting Supervisor process..."
supervisorctl restart profiles_api

