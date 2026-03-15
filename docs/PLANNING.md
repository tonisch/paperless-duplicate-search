# Planning: Paperless Duplicate App

**Goal:** A clear app to **detect duplicates quickly** and **delete them safely**.

---

## 1. User stories

| Priority | As a user I want to … |
|----------|------------------------|
| P0 | … see **how many** duplicates there are and whether it’s worth spending time. |
| P0 | … see **at a glance** per pair: same content? Which to keep? |
| P0 | … decide with **few clicks** (keep/delete) without deleting the wrong one. |
| P1 | … move **quickly through many pairs** (keyboard, clear actions). |
| P1 | … **clean all 100% duplicates** in one step when I trust the detection. |
| P2 | … see **preview** in uncertain cases (compare documents). |

---

## 2. Current status

- **Load:** Paperless API → duplicates by checksum + similar title/content. Polling, progress + log.
- **View:** List of large cards; per pair: similarity, two columns (title, preview), “select pair” checkbox, “keep left/right” radio, “delete right” / “delete left” / “skip” buttons.
- **Actions:** Delete single, “Delete selected” (one doc per pair), “Clean all 100% duplicates”.

**Strengths:** Preview, clear keep/delete mapping, filter by similarity.  
**Gaps:** Lots of scrolling, many clicks per pair, no keyboard support, no compact overview.

---

## 3. Ideas for better UX

- **Summary card** after load: “X pairs (Y at 100%, Z at 95–99%)” and quick links “Only 100%” / “All”.
- **Two modes:** “Quick” (wizard: one pair per screen, big buttons) vs “Compare” (list with expandable preview).
- **Compact list:** Table row per pair (title | similarity | title | actions), preview on expand.
- **Fewer clicks:** Two main buttons “Keep left” / “Keep right” per pair; optional “Skip”.
- **Keyboard:** ← / → for keep left/right, Space for skip (in wizard).
- **Safety:** Clear labels “Keep: …” and “Will be deleted: …”; optional one-time confirmation.

---

## 4. Phases (suggested)

**Phase 1:** Summary card + simplified buttons + compact list option.  
**Phase 2:** Wizard mode + keyboard.  
**Phase 3:** Lazy preview, optional “keep older” default.

---

*Planning board; can be updated or reprioritised anytime.*
