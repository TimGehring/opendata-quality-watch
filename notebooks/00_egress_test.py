# Databricks notebook source
# MAGIC %md
# MAGIC # 00 Egress-Test (Ticket 1.2)
# MAGIC Prüft, ob der Databricks-Cluster (Free Edition, Serverless) ausgehende HTTPS-Anfragen
# MAGIC an die CKAN-API von datenregister.berlin.de stellen darf.

# COMMAND ----------

import requests

API_URL = "https://datenregister.berlin.de/api/3/action/package_search?rows=0"

try:
    response = requests.get(API_URL, timeout=15)
    print(f"HTTP-Status: {response.status_code}")
    response.raise_for_status()
    payload = response.json()
    print(f"success: {payload.get('success')}")
    print(f"count (Datensätze im Portal): {payload['result']['count']}")
except requests.Timeout:
    print("FEHLER: Zeitüberschreitung nach 15 s - Egress vermutlich blockiert.")
except requests.ConnectionError as error:
    print(f"FEHLER: Keine Verbindung (DNS/Firewall/Egress-Richtlinie): {error}")
except requests.HTTPError as error:
    print(f"FEHLER: HTTP-Fehler: {error}")
except (ValueError, KeyError) as error:
    print(f"FEHLER: Unerwartete Antwort (kein gültiges CKAN-JSON): {error}")
