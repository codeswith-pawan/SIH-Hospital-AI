#!/bin/sh
set -e

echo "==> Initializing SIH Hospital AI Database Schema..."

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f /docker-migrations/001_initial_postgresql_schema.sql
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f /docker-migrations/002_referral_workflow_and_notifications.sql
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f /docker-migrations/003_registration_system.sql

echo "==> Database Schema Successfully Initialized!"
