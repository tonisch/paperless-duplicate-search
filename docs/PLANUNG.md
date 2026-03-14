# Planungsboard: Paperless-Duplikate-App

**Ziel:** Eine übersichtliche App, mit der Duplikate **schnell erkannt** und **sicher gelöscht** werden können.

---

## 1. Nutzerziele (User Stories)

| Priorität | Als Nutzer … |
|-----------|----------------|
| P0 | … will ich sofort sehen, **wie viele** Duplikate es gibt und ob es sich lohnt, Zeit zu investieren. |
| P0 | … will ich pro Paar **auf einen Blick** erkennen: gleicher Inhalt? Welches behalten? |
| P0 | … will ich mit **wenigen Klicks** entscheiden (behalten/löschen) ohne versehentlich das Falsche zu löschen. |
| P1 | … will ich **schnell durch viele Paare** gehen können (Tastatur, klare Aktionen). |
| P1 | … will ich **100 %-Duplikate** in einem Schritt bereinigen können, wenn ich der Erkennung vertraue. |
| P2 | … will ich bei unsicheren Fällen **Vorschau** sehen (Dokumente vergleichen). |

---

## 2. Aktueller Stand (kurz)

- **Laden:** Paperless-API → Duplikate nach Checksum + ähnlichem Titel/Inhalt. Polling, Fortschritt + Log.
- **Ansicht:** Liste großer Karten, je Paar: Ähnlichkeit, zwei Spalten (Titel, Vorschau), Checkbox „Paar auswählen“, Radio „Linkes/Rechtes behalten“, Buttons „Rechtes löschen“ / „Linkes löschen“ / „Überspringen“.
- **Aktionen:** Einzeln löschen, „Ausgewählte löschen“ (pro Paar ein Dokument), „Alle 100 %-Duplikate bereinigen“.

**Stärken:** Vorschau, klare Zuordnung behalten/löschen, Filter nach Ähnlichkeit.  
**Schwächen:** Viel Scrollen, viele Klicks pro Paar, keine Tastaturbedienung, keine kompakte Übersicht.

---

### Bereits umgesetzt (UX-Verbesserungen)

- **Unterschiede sichtbar:** Pro Paar ein Block „Unterschiede in Paperless“ – Titel, Korrespondent, Tags links vs. rechts; abweichende Werte farblich hervorgehoben (amber).
- **Ähnlichkeit als Entscheidungshilfe:** Großer farbiger Badge (100 % = grün, 95–99 % = amber, darunter = orange) mit Tooltip „Je höher, desto sicherer die Duplikat-Erkennung“.
- **PDF-Vorschau für Entscheidung:** Label „Vorschau für Entscheidung (PDF)“ über den beiden Previews; Iframes unverändert.
- **Fortschritt beim Löschen:** Beim „Ausgewählte löschen“ Einzellöschung nacheinander mit Fortschrittsbalken am unteren Rand („Lösche Dokument 2 von 5…“, Balken, „2/5“).

---

## 3. Ideen für bessere UX

### 3.1 Erster Eindruck: Zusammenfassung

- **Nach dem Laden:** Eine **Summary-Karte** oben:
  - „X Duplikat-Paare gefunden (Y mit 100 %, Z mit 95–99 %).“
  - Optional: „[Nur 100 % anzeigen]“, „[Alle anzeigen]“, „[Alle 100 % auf einmal bereinigen]“.
- Nutzer entscheidet sofort: „Will ich durchgehen?“ oder „Erst nur 100 %?“.

### 3.2 Zwei Modi: „Schnell durchgehen“ vs „Vergleichen“

| Modus | Ziel | Darstellung |
|-------|------|--------------|
| **Schnell (Wizard)** | Viele Paare nacheinander abarbeiten. | Ein Paar pro Bildschirm, große Buttons: **Behalten links** / **Behalten rechts** / **Überspringen**. Fortschritt „Paar 3 von 12“. Optional Tastatur: ← / → / Leer. |
| **Vergleichen (Liste)** | Bei unsicheren Fällen nebeneinander prüfen. | Kompakte Zeilen (Titel links | Ähnlichkeit | Titel rechts) + auf Klick/Expand große Vorschau. Pro Zeile: „Links behalten“ / „Rechts behalten“ / „Überspringen“. |

- Umschaltbar z. B. über „Modus: Schnell / Vergleichen“ oder Tabs.
- Standard könnte **Schnell** sein (Wizard), Liste für „alle auf einmal sichten“.

### 3.3 Kompakte Listen-Ansicht

- Statt nur großer Karten: **Tabelle/Liste** mit einer Zeile pro Paar:
  - Spalten: **Titel links** (gekürzt), **Ähnlichkeit**, **Titel rechts**, **Aktionen** (Links behalten | Rechts behalten | Skip).
  - Vorschau **nur on demand**: Zeile aufklappen oder „Vorschau“-Button → dann zwei Previews.
- Vorteil: 20+ Paare auf einen Blick, schnelles Scannen.

### 3.4 Weniger Klicks pro Paar

- **Eine klare Standard-Entscheidung:** z. B. „Immer **älteres** behalten“ oder „**Linkes** behalten“ als Voreinstellung, dann nur ein Klick: „So löschen“ (das andere wird gelöscht).
- Oder: Zwei große Buttons pro Paar: **„Links behalten“** (rechts löschen) und **„Rechts behalten“** (links löschen) – ohne extra Checkbox/Radio.
- Bulk: „Alle ausgewählten Paare: **jeweils rechtes** löschen“ – eine Bestätigung, fertig.

### 3.5 Tastatur & Fokus

- Im Wizard: **←** = Links behalten, **→** = Rechts behalten, **Leer** = Überspringen (oder umgekehrt).
- Fokus immer auf den Aktions-Buttons, kein Herumklicken nötig.

### 3.6 Sicherheit & Vertrauen

- Immer klar beschriften: **„Behalten: …“** und **„Wird gelöscht: …“** (z. B. mit ID/Titel).
- Optional: Kurze Bestätigung vor dem ersten Löschen („Von jetzt an: Ein Klick = Löschen?“) oder pro Paar nur ein Klick ohne zweites Popup, wenn die Buttons eindeutig sind.
- „Alle 100 % bereinigen“ weiterhin mit expliziter Bestätigung und klarer Erklärung („Es bleibt jeweils ein Dokument pro Gruppe.“).

### 3.7 Technik / Performance

- **Vorschau lazy:** Iframes/Previews erst laden, wenn Zeile aufgeklappt oder Paar im Wizard sichtbar ist.
- **Statistik/Chart** optional ein- und ausklappbar (bereits umgesetzt).
- Optional: Letztes Ergebnis **cachen** (z. B. 5 Min), „Aus Cache anzeigen“ während „Im Hintergrund aktualisieren“.

---

## 4. Vorschlag: Priorisierte Umsetzung

### Phase 1 – Schnell gewinnen (ohne große Strukturänderung)

1. **Summary oben** nach dem Laden: eine Karte „X Paare, Y mit 100 %“ + schnelle Links „Nur 100 %“ / „Alle“.
2. **Pro Paar:** Checkbox/Radio entfernen oder stark vereinfachen: nur zwei Hauptbuttons **„Links behalten“** und **„Rechts behalten“** (jeweils mit klarem „… wird gelöscht“). Optional „Überspringen“.
3. **Kompakte Zeilen-Ansicht** als Option: Liste/Table mit Titel | Ähnlichkeit | Titel | Aktionen, Vorschau auf Expand.

### Phase 2 – Wizard für Speed

4. **Modus „Schnell“:** Ein Paar pro Bildschirm, zwei große Buttons + Überspringen, Fortschrittsanzeige.
5. **Tastatur:** ← / → (oder 1/2) für „Links behalten“ / „Rechts behalten“, Leer für Skip.

### Phase 3 – Feinschliff

6. **Lazy Vorschau** für Liste (nur sichtbare/aufgeklappte Paare laden).
7. Optional: **Standard „älteres behalten“** pro Paar voreingestellt, dann „Alle so anwenden“ + eine Bestätigung.

---

## 5. Offene Punkte

- Soll **„Älteres behalten“** als globaler Default angeboten werden (z. B. Radiobutton „Standard: älteres Dokument behalten“)?
- Soll die **Statistik** (Balkendiagramm) auf der Startseite bleiben oder nur in einem „Details“-Bereich?
- **Sprache:** Weiter DE/EN per Umschalter, oder nur Browser-Sprache?

---

## 6. Nächste Schritte

- [ ] Entscheiden: Zuerst **Phase 1** (Summary + vereinfachte Buttons + kompakte Liste) umsetzen?
- [ ] Oder zuerst **Wizard (Phase 2)** für maximale Geschwindigkeit?
- [ ] Danach: konkrete Tickets/Issues aus diesem Dokument ableiten und abarbeiten.

---

*Stand: Planungsboard, kann jederzeit ergänzt oder umpriorisiert werden.*
