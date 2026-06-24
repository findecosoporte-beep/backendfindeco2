#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

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

: "${DJANGO_SUPERUSER_PASSWORD:?Define DJANGO_SUPERUSER_PASSWORD en Variables de Railway}"

export DJANGO_SUPERUSER_USERNAME="${DJANGO_SUPERUSER_USERNAME:-admin}"
export DJANGO_SUPERUSER_EMAIL="${DJANGO_SUPERUSER_EMAIL:-admin@findeco.local}"
export DJANGO_SUPERUSER_PASSWORD

python manage.py createsuperuser --noinput
echo "Superusuario listo: ${DJANGO_SUPERUSER_USERNAME} (${DJANGO_SUPERUSER_EMAIL})"
