#!/usr/bin/env bash

set -e

PROJECT_BASE_PATH='/usr/local/apps/profiles-rest-api'
ENV_PATH="$PROJECT_BASE_PATH/env"

echo "Changing directory to project path..."
cd $PROJECT_BASE_PATH

echo "Fetching latest changes from Git..."
git fetch
git pull

echo "Applying database migrations..."
$ENV_PATH/bin/python manage.py migrate

echo "Collecting static files..."
$ENV_PATH/bin/python manage.py collectstatic --noinput

echo "Restarting Supervisor process..."
supervisorctl restart profiles_api

echo "UPDATE COMPLETE! ✅"
