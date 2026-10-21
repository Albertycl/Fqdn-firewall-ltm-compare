"""Trigger the daily config update.

Targets the loopback address by default so the script is host-independent;
override with DAILY_UPDATE_URL (or API_HOST / API_PORT) when the API runs
elsewhere.
"""
import os
import requests

host = os.getenv('API_HOST', '127.0.0.1')
port = os.getenv('API_PORT', '5432')
url = os.getenv('DAILY_UPDATE_URL', f'http://{host}:{port}/api/download/daily')

response = requests.get(url, params={'auto_parse': 'true'}, timeout=600)

print(response.text)
