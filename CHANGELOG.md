# Changelog

Release history of WorkSlop Desktop. Versions marked *pre-release* were
development builds published for testing; **v11.5** is the current public
release.

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
