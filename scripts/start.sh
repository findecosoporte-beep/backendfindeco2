#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

# Railway: forzar producción (evita DisallowedHost si el panel deja development)
if [[ -n "${RAILWAY_ENVIRONMENT:-}" ]]; then
  export DJANGO_ENV=production
  export DJANGO_DEBUG=false
  export DJANGO_SECURE_SSL_REDIRECT=false
  _domain="${RAILWAY_PUBLIC_DOMAIN:-}"
  if [[ -n "$_domain" ]]; then
    export ALLOWED_HOSTS="${_domain},.up.railway.app"
  else
    export ALLOWED_HOSTS=".up.railway.app"
  fi
fi

python manage.py migrate --noinput

exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT:-8080}" \
  --workers "${GUNICORN_WORKERS:-2}" \
  --timeout "${GUNICORN_TIMEOUT:-120}" \
  --access-logfile - \
  --error-logfile -
