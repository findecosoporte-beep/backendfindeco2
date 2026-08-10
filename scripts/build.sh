#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/.."

python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py collectstatic --noinput
