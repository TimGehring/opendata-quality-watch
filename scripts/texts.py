# Gemeinsame Texte für Dashboard und Ergebnisseite aus site/texts.json.
# Platzhalter {schluessel|format} werden mit Werten aus site/data/findings.json gefüllt
# (erzeugt von scripts/export_results.py). site/app.js macht dasselbe im Browser.
# Formate: int (1.234), dec1 (21,9), pct0 / pct1 (Anteil 0..1 als 32 % bzw. 15,4 %).
# **fett** bleibt Markdown (Dashboard); die Seite wandelt es in <strong> um.
import json, re
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXTS_FILE = ROOT / "site" / "texts.json"
FINDINGS_FILE = ROOT / "site" / "data" / "findings.json"
NBSP = " "
PLACEHOLDER = re.compile(r"\{(\w+)\|(int|dec1|pct0|pct1)\}")


def de(value, places=0):
    """Wie Intl.NumberFormat('de-DE') mit fester Nachkommastellenzahl."""
    q = Decimal(str(value)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    s = f"{q:,.{places}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def fmt(value, kind):
    if kind == "int":
        return de(value, 0)
    if kind == "dec1":
        return de(value, 1)
    return de(value * 100, int(kind[-1])) + NBSP + "%"


def render(template, values):
    return PLACEHOLDER.sub(lambda m: fmt(values[m[1]], m[2]), template)


def placeholders(template):
    """[(schluessel, format), ...] in der Reihenfolge im Text."""
    return PLACEHOLDER.findall(template)


def load_texts():
    return json.loads(TEXTS_FILE.read_text(encoding="utf-8"))


def load_findings():
    return json.loads(FINDINGS_FILE.read_text(encoding="utf-8"))
