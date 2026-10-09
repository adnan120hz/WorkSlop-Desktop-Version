# FROZEN — Custom Icons / Icon Themes menu

**Frozen by user order, 2026-10-09.**

The Custom Icons (Icon Themes) menu is **device-proven**: on
2026-10-09 the user applied iOS 18 icons from this menu on their own
phone (iPhone14,7, iOS 26.6.1) and the iOS 18-styled icons landed on
the home screen. The menu works as shipped in the v14 round
(commit `2cd8317`) and must keep working through any future WorkSlop
overhaul — so its code and data are pinned.

## Frozen files

Pinned by SHA-256 in `tools/test_icon_themes_frozen.py`
(104 files total):

| File(s) | What it is |
|---|---|
| `src/gui/ios/icon_themes.py` | The Icon Themes page: themes list, bundled iOS 18 table (per-row Add + Add All), "Import Icon Pack (.zip)..." |
| `src/tweaks/icon_themes/icon_themes_tweak.py` | The model: `IconThemesTweak`, WebClip builder (`WorkSlop_<bundleID>,<displayName>` folders), hash-matched ZIP pack import (`import_pack_zip_matched`, `build_pack_hash_index`) |
| `src/gui/dialogs/icon_pack_downloader.py` | The "Download Icon Packs" dialog the page opens and imports through |
| `files/ios18_icons/Light/*.png` (51) | Bundled catwithabaloon catalog, Light artwork |
| `files/ios18_icons/Dark/*.png` (50) | Bundled catwithabaloon catalog, Dark artwork |

The two main modules also carry a `# FROZEN 2026-10-09 (user order)`
header comment.

## Rules

1. **Do not change the behavior of these files** — no edits, renames,
   moves, additions or removals — without an **explicit order from the
   user**. This includes "harmless" refactors and cleanups during a
   larger overhaul.
2. The guard is `tools/test_icon_themes_frozen.py`. It fails hard and
   names the offending file(s) if anything in the manifest changed,
   went missing, or if an icon was added/removed/renamed. Run it after
   touching anything near this menu.
3. **If the user does order a change** to this menu, update
   `EXPECTED_SHA256` in `tools/test_icon_themes_frozen.py` in the
   **same commit** as the change (re-hash the touched files), so the
   guard keeps passing and the freeze stays meaningful.

Related coverage that must stay green:
`tools/test_icon_pack_zip_import.py` (51-app hash import against the
real pack) and `tools/test_audit_gui_pages.py`.

Credit: the bundled artwork is the
[iOS-18-icon-pack by catwithabaloon](https://github.com/catwithabaloon/iOS-18-icon-pack);
attribution also lives in the app's About dialog and the README.
