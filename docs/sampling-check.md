# Stichprobe (Ticket 3.4)

Fünf Datensätze, im Portal von Hand gegen unsere Werte prüfen. Pro Datensatz das Ergebnis eintragen: ✅ stimmt / ❌ stimmt nicht + Notiz. Ein Screenshot pro Fall in `Material/Stichprobe/` ist gut für die Präsentation.

| # | Datensatz | Warum ausgewählt | Unser Wert | Im Portal prüfen | Ergebnis |
| --- | --- | --- | --- | --- | --- |
| 1 | [Standardeinspeisprofil BHKW 2013](https://daten.berlin.de/datensaetze/standardeinspeisprofil-bhkw-2013-berlin) | Stromnetz, toter Link | Score 75, „1 toter Link“ | Download-Link anklicken → wirklich 404? | ✅ (Tim, 16.11.) |
| 2 | [ALKIS Berlin Gebäude – WMS](https://daten.berlin.de/datensaetze/alkis-berlin-gebaude-wms-986ea575) | High-Value-Datensatz, nur Kartenbild | Score 55, „nur Kartenbild, Format fehlt, kurze Beschreibung“ | Gibt es nur WMS? **Gibt es einen eigenen ALKIS-Gebäude-WFS-Datensatz?** (Portal-Suche „ALKIS Gebäude“) | ⚠️ Nur WMS im Datensatz stimmt, **aber es gibt den Zwilling `alkis-berlin-gebaude-wfs-728b368a` mit WFS** → Befund umformuliert, siehe unten |
| 3 | [Los_5_2024](https://daten.berlin.de/datensaetze/los_5_2024-berlin) | „Aktualisiert vor Veröffentlichung“ | veröffentlicht 16.04.2024, aktualisiert 01.01.2024 | **Wie heißen die beiden Datumsfelder auf der Portalseite genau?** | ✅ Portal zeigt „Veröffentlicht: 16.04.2024“ und „Aktualisiert: 01.01.2024“ → Regel bleibt, Formulierung angepasst |
| 4 | [Haushaltsplan 2020/2021](https://daten.berlin.de/datensaetze/haushaltsplan-2020-2021) | kein Datum, nicht maschinenlesbar | Score 55 | Fehlt das Aktualisierungsdatum wirklich? Welches Format hat die Ressource (PDF?) | ✅ (Tim, 16.11.) |
| 5 | [Liste der häufigen Vornamen 2018](https://daten.berlin.de/datensaetze/liste-der-h-ufigen-vornamen-2018) | Gegenprobe: Score 100 | 14 Ressourcen, alle maschinenlesbar | Gehen 2–3 der CSV-Links? | ✅ (Tim, 16.11.) |

## Verdacht zu Fall 3 (vor der Prüfung)

Wir wissen aus dem Datenprofil, dass `date_updated` eher der **Datenstand** ist (Werte bis 1910). Dann ist „Datenstand vor Veröffentlichung“ **normal und kein Widerspruch**: Daten von 2007 werden 2015 veröffentlicht. Damit wäre die Regel „Aktualisiert vor Veröffentlichung“ (205 Fälle, davon 164 FIS-Broker) ein Fehlschluss wie bei `temporal_granularity`.

→ Falls das Portal das Feld als Datenstand bzw. „Stand der Daten“ bezeichnet: **Regel aus Q2 und aus dem Score streichen** (Prompt 08). Wenn es eindeutig „zuletzt aktualisiert“ heißt, bleibt sie.

## Ergebnis der Stichprobe (16.11.)

**Fall 3:** Das Portal zeigt den Nutzern wörtlich „Veröffentlicht 16.04.2024 · Aktualisiert 01.01.2024“. Für jemanden, der die Seite liest, ist das ein Widerspruch. Vermutlich tragen manche Bereitsteller in „Aktualisiert“ den Datenstand ein und andere das Datum der letzten Aktualisierung. → **Die Regel bleibt**, aber sie heißt jetzt „Angezeigtes Aktualisierungsdatum liegt vor der Veröffentlichung“. In der Präsentation sagen wir dazu: Das Feld wird uneinheitlich genutzt (Datenstand vs. Aktualisierung), und darin liegt der eigentliche Qualitätsmangel.

**Fall 2 – wichtige Korrektur:** Der FIS-Broker legt WMS und WFS oft als **zwei getrennte Datensätze** an (621 solcher Paare). Pro Datensatz stimmt „nur Kartenbild“, aber die Daten gibt es häufig im Zwilling als WFS. Auf Ebene der **Angebote** (WMS- und WFS-Eintrag zusammengefasst):

| Gruppe | Angebote | mit maschinenlesbarer Variante |
| --- | --- | --- |
| High-Value-Datensätze | 208 | 113 (54,3 %) |
| übrige | 1764 | 1492 (84,6 %) |
| FIS-Broker | 982 | 664 (67,6 %) |
| alle | 1972 | 1605 (81,4 %) |

→ **Der HVD-Befund hält auch auf Angebotsebene, der Abstand ist sogar größer:** Fast jedes zweite HVD-Angebot (95 von 208) hat keine maschinenlesbare Variante, bei den übrigen nur etwa jedes siebte.
→ **„59 % der Geodaten nur als Kartenbild“ ist so nicht haltbar.** Richtig ist: Bei 32 % der FIS-Broker-Angebote (318 von 982) gibt es keine maschinenlesbare Variante, auch keinen WFS-Zwilling.
→ Neuer Nebenbefund: Die WMS/WFS-Doppelung bläht den Katalog auf (621 Paare), und Nutzer müssen den Zwilling selbst finden.

Zwilling erkannt über den Namen ohne `-wms-/-wfs-<hex>`. Das ist eine Heuristik, Zwillinge mit anderem Namen werden nicht erkannt. Die Zahlen sind also eher eine Untergrenze.
