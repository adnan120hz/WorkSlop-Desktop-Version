# Changelog

Release history of WorkSlop Desktop. Versions marked *pre-release* were
development builds published for testing; **v11.5** is the current public
release.

## v12 — 2026-10-05 (pre-release, Windows)

- Liquid Glass Disable (Beta 1) now has a dedicated full-backup delivery
  route on iOS 26.6.1 (builds 23G82 and 23G83): when G1 and/or G2 is
  applied, WorkSlop takes a complete device backup, writes the verified
  payload into it, re-verifies the injected backup with hard gates
  (complete backup, every payload accounted for, payload bytes intact,
  G1 keeps 100% of the device's original keys), and only then restores.
  An encrypted backup is refused honestly; any failure cancels the
  apply before the device is changed. Rollback uses the same route.
  Other iOS versions keep the previous delivery exactly as before.
- Home now has two separate Liquid Glass Disable tiles (G2 Managed
  Overlay and G1 Device File Merge). A tile opens the Liquid Glass
  Disable page focused on that route; it never enables a tweak by
  itself.
- Fixes: the Liquid Glass Disable page no longer crashes when showing
  the saved-original status or a rollback confirmation; the
  saved-original store is written atomically and its status survives a
  missing metadata file; an empty duplicate restore record no longer
  fails the verification gate when a valid record exists.
- No changes to any existing tweak payload (the Liquid Glass v4 set
  and the Nugget set are untouched).
- Post-release audit fixes (same day): a crash that killed every G1
  apply/rollback on the full-backup route before it could start; the
  G2 overlay is now merged onto the device's own managed file from the
  apply backup (pre-existing managed keys survive, and that file is
  the rollback source); LGD full backups live in their own retained
  pool instead of the iOS 27 protective-backup pool; the encrypted
  backup refusal now fires before any backup analysis.

## v11.5 — 2026-10-03

- Fixed the developer-beta warning naming the wrong iOS version: it now
  names the detected major version (an iOS 27 beta device reads "iOS 27
  beta", not "iOS 26 beta"). The warning text and the set of devices that
  trigger it are unchanged.
- The warning is now shown non-modally, once per app session per device.
  It no longer closes the app on Linux/Wayland (previously, clicking OK in
  the modal warning could break the Wayland session and terminate the
  app) and no longer blocks the tweak menus.
- No tweak or payload changes.

## v11.0.1 — 2026-10-03

- Removed the fixed "Backup Location" panel from the Backup page. The backup
  folder is now chosen in the system file picker when a Full Backup or a
  Protective Backup starts; the folder is created automatically if needed,
  the choice is remembered, and the automatic protective backup before an
  apply uses the same folder.
- Added a live progress strip at the bottom of the Backup page (current step,
  percentage, progress bar) while a backup or restore runs.
- Themes and classic Apply pages are color-matched to the Nugget interface;
  the Themes page is fully dark in that interface.
- The Apply progress log is now shown in all three interfaces.
- No tweak or payload changes.

## v11.0 — 2026-10-03

- Three selectable interfaces — **WorkSlop (Main)**, **WorkSlop 2** and
  **Nugget** (Settings → Appearance), with a stacked interface picker using
  the new names; the OS window title bar follows the active interface.
- Liquid Glass section rebuilt: the WorkSlop set restored verbatim to its v4
  implementation (payload-identical, including restored entries) plus a Blurr
  Motion toggle; a separate "Liquid Glass Tweaks (Nugget)" set, 100% from
  Nugget v7.4.1, appears in the Nugget-based interfaces.
- Eligibility options (EU Enabler, AI Eligibility, folder creation) are
  locked fail-closed on iOS 26.2 beta 2 (build `23C5035e`) and newer —
  the same boundary as MobileGestalt — and remain available up to `23C5027f`.
- Backup stall watchdog active on every backup path (protective backup,
  PosterBoard backups, app-domain backup, apply-time backups).
- New WorkSlop brand icon across the app; Backup entry added to the classic
  sidebars; beta tester team (Charlie, rfrz1d_, Davy) credited on the Home
  page next to the license attribution.

## v10.0 — 2026-10-03 *(initially pre-release)*

- Modern interface rebuild with a device-first detection flow: identity-first
  detection, a rewritten Refresh, and a faster device handshake.
- Fixed backups stalling at 84% (stall watchdog, bounded retries); research
  tweaks that passed a structural audit became available as normal toggles.
- MobileGestalt support boundary clarified: open up to iOS 26.2 beta 1
  (`23C5027f`), locked from `23C5035e` onward.
- PosterBoard rebuilt on the Nugget v7.4 descriptor system; new Disable
  Thermal tweak; application is English-only.

## v4.0-pre — 2026-10-02 *(pre-release, developer only)*

- "Pre-Beta (Developer Only)" build of the Sky-interface era; the Liquid
  Glass tweak set that later became the reference implementation originates
  from this line.

## v3.6-pre — 2026-10-02 *(pre-release)*

- Published 71 twice-audited tweak candidates as a developer-only pre-beta
  for device testing.

## v3.5-dev — 2026-10-01 *(pre-release)*

- Development iteration of the v3 line.

## v3.4 — 2026-10-01 *(pre-release)*

- "Zero code change" rule in effect: changes limited to feature exposure,
  gating and read-only behavior; tweak payloads untouched.
- Sideloading menu removed.

## v3.0 — 2026-09-30

- First tagged release of this repository.
- MobileGestalt module ported from Nugget; update checker points at this
  repository.
