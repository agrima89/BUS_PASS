# Project plan

## Done

| Phase | Scope | Status |
|---|---|---|
| 1 | Flask app, SQLite, dark admin dashboard, basic student management | ✅ Done |
| 2 | Admin login, photo uploads, live preview, Pillow card, online/offline QR, verify page | ✅ Done |
| 3 | Single and four-per-A4 printing, PDF export, camera scanner, backups, deployment guide | ✅ Done |
| 4A | Buggy-pass registration fields, pickup points, pass-issue rules, privacy tests | ✅ Done, approved 2026-11-05 |
| 4B | Two-sided HTML/CSS buggy pass, Card Settings, duplex printing, two-sided live preview | ✅ Done, approved 2026-11-05 (official assets pending) |

The Phase 2–3 card is a generic **placeholder design**. It is replaced by the buggy pass below.

---

## Phase 4: Buggy pass, two-sided

Reference: two photos of the current university buggy pass (front and back), supplied 2026-11-05.
They are layout references only. No logo, seal or contact number is copied from them.

### 4A. Student registration ✅ done

What was built (decisions made where the plan offered a choice):
- **UID:** the existing `roll_number` column, now labelled **UID** everywhere (form, lists, card, verify page, scanner).
  A separate column can still be added if roll number and UID turn out to differ.
- **Class/Branch:** `program` is now labelled *Class / Program* and `department` *Branch / Department*. On the card
  they will fill the two Class/Branch lines.
- **S/O:** `guardian_relation` (S/O, D/O, W/O, C/O, chosen per student) plus `guardian_name`.
- **Pickup point:** chosen from a new admin-managed **Pickup Points** page. Spelling is tidied and duplicates are
  rejected regardless of case. A point in use can only be hidden, not deleted.
- **Emergency contact** (validated phone) and **address** (up to 4 lines, 300 characters).
- **Pass-issue rules:** `REQUIRED_FOR_PASS` in `.env`. By default a pass needs a photo, guardian name, pickup point,
  emergency contact, address and valid-until date. Incomplete students show **⚠ Incomplete** with the missing fields listed.
- **Pass number:** `PASS_NUMBER_STYLE=random` (default) or `sequential` (`DU-2026-00001` …).
- **Privacy:** guardian name, emergency contact and address never reach the verify page, the scan API or offline QR
  codes. A test checks this.
- Server-side length limits on all text fields (previously enforced only by the browser).
- Existing databases are upgraded in place. A test upgrades a Phase 1 database.

Original requirements table, for reference:

| Card field | Current app | Change needed |
|---|---|---|
| Name | `full_name` | none |
| Photograph | `photo_path` | Photo box on the card is roughly square, so re-check the 3:4 crop (see open questions) |
| S/O | missing | Add `guardian_name`, plus a relation label (S/O, D/O, W/O, C/O) chosen on the form, so the card isn't fixed to "S/O" |
| Class/Branch | `program` + `department` | Map them, or add one `class_branch` field. The card has two lines for this |
| UID | `roll_number` | Rename the label to **UID** in the UI, or add a separate `uid` if roll number and UID differ |
| Pickup Point | missing | Add `pickup_point`, ideally chosen from an admin-managed list (new `pickup_points` table) so spelling stays consistent |
| Valid Upto | `valid_until` | none (shown as DD-MM-YYYY on the card) |
| Emergency Contact No. | missing | Add `emergency_contact` (validated phone) |
| Address | missing | Add `address` (multi-line, length-limited) |
| Buggy Pass No. | `pass_code` | Make the format configurable (e.g. `PASS_PREFIX` + sequence) to match the university's numbering |

Also in 4A:
- Make these fields optional or required through config, so the admin can decide what must be filled before a pass is issued.
- Additive database migration (as in Phase 2), with no data loss.
- Treat sensitive fields as such. Guardian name, emergency contact and address are **never** shown on the public
  verify page, never put in offline QR codes, and never sent by the scan API. They appear only on the printed card and admin pages.
- Tests for validation, the migration and the privacy rules above.

### 4B. Two-sided card as editable HTML/CSS ✅ done with placeholders

What was built:
- `templates/cards/_buggy.html` (front and back macros) + `static/css/card.css`: real text positioned in mm on an
  85.6 × 54 mm card, traced from the reference photos. The same template is used for the live preview, the pass page and printing.
- **Card Settings** page (`/settings`): every label and all official text are editable, and logo and seal upload slots
  (images re-encoded to PNG, admin-only). Defaults: the reference's field labels, with **all official text blank**.
  Blank lines are left off the card.
- Square photo box (the stored 3:4 photo is cover-cropped toward the face). Valid Upto is shown as DD-MM-YYYY.
- QR on the **back** as vector SVG (sharp at any printer resolution). The front has no QR, like the reference.
- `static/js/cardfit.js`: long text shrinks to fit its fixed box (down to 50%), so the layout never moves.
- Printing: single card = front page + back page at 85.6 × 54 mm. A4 = fronts sheet, then backs sheet,
  backs mirrored for long-edge duplex (toggle available), with crop marks. PDF via the browser's Save as PDF.
- Printing is refused for revoked passes or students missing the required fields.
- The previous one-sided design is still available as "classic" (print, PNG, PDF) until this design is signed off.

Original specification, for reference:

**Approach:** card faces become Jinja templates styled in real millimetres (`mm`), not Pillow images:
- `templates/cards/buggy_front.html`: logo slot, university name and tagline slot, "Buggy Pass No." and its value,
  bordered photo box on the left, label/underline rows on the right (Name, S/O, Class/Branch across two lines, UID, Pickup Point), blank lower area kept as on the original.
- `templates/cards/buggy_back.html`: thin inner border, Valid Upto (bold value), Emergency Contact No., Address,
  return instructions, Transport Dept. block, Contact No., Transport Helpline, a round **seal placeholder** at top right
  (empty dashed circle unless an official seal image is uploaded), and the note at the bottom.
- Text stays real, selectable text. Data fills the underlined rows, and long values shrink or wrap within a fixed box so the layout never moves.
- **Size:** CR80, 85.6 × 54 mm, landscape, rounded corners (about 3 mm). Measure the physical card to confirm before building (see open questions).

**Configurable branding and wording**, edited in the admin UI (new Settings page, stored in the database) with defaults from `.env`:
- University name, tagline, logo file, seal file (uploads; empty until official assets are given)
- Card title (e.g. "Buggy Pass No."), every field label, the return-to text, department name, address lines,
  contact and helpline numbers, the note lines
- **Defaults stay blank or neutral placeholders.** The real wording is entered by the university, not by the app.

**Printing:**
- Single card: front page + back page, each 85.6 × 54 mm (`@page` size), for duplex ID-card printers.
- A4 duplex: 4 fronts on page 1, 4 backs on page 2, with the **back sheet mirrored left↔right** so each back lines up
  behind its front on long-edge duplex. Crop marks as in Phase 3. A simplex option prints fronts and backs on separate pages.
- The live preview on the student form shows both faces (with a front/back toggle) using the **same template** as printing.

**PDF export** (needs a decision, see below): HTML/CSS layouts can't go through the current Pillow PDF route.

**QR code:** the reference card has none. Proposed: a small QR in the blank lower-right area of the front, with a config
switch to move it to the back or turn it off.

**Retire or keep:** the old Pillow card stays available as a fallback design until the buggy pass is approved.

---

## Decisions for 4B (answered 2026-11-05)

- **Card size:** CR80, 85.6 × 54 mm, landscape.
- **Photo box:** square, like the reference. Uploads get a square crop for this card.
- **QR code:** on the **back** side. The front stays as on the reference.
- **PDF:** browser "Save as PDF" from the print view. No new dependency.

## Open questions (needed before or during 4B) — still open: 1 and 2 (3–6 decided above; 7 settled in 4A: relation chosen per student)

1. **Branding rights and assets.** Please provide the official logo and seal files, the exact wording, and contact and
   helpline numbers, through the university. The app will not draw or recreate them.
2. **Wording in the reference that may be typos.** The app will print exactly what is configured, so please confirm the intended text:
   - "Buggle Pass No." on the front vs. "buggy" on the back
   - "Discover Leam, Empower." (Learn?)
   - "Pass is not Transfersine." (Transferable?)
   - "Unvented rides" (meaning unclear)
   - The address line "University, Gharuan, Mohali, Punjab" is printed twice
3. **Exact card size:** please measure the physical card. CR80 (85.6 × 54 mm) is assumed; the photo's
   perspective makes the ratio hard to read.
4. **Photo box shape:** on the reference it is close to square. Should it be a square crop, or stay 3:4 portrait?
5. **QR placement:** front lower-right, back, or none?
6. **PDF engine** (choose one):
   - *Browser "Save as PDF"* from the print view. No new dependencies, exact match to printing, but manual.
   - *Playwright (headless Chromium)*. One-click server-side PDF, adds a large dependency (~150 MB).
   - *WeasyPrint*. Pure Python, but awkward to install on Windows (needs GTK).
7. **S/O wording:** fixed "S/O", or choose S/O / D/O / C/O per student?

## Order of work

1. ~~4A student registration fields, migration, privacy rules, tests~~ ✅ done, approved
2. Answers to the open questions plus official assets
3. 4B card templates, settings page, preview, printing, PDF → **review and approval**
