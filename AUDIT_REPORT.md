> **HISTORICAL — superseded (2026-10-09).**
> Pinned to the 2026-09-30 codebase (`~/workspace/desk`). Most "critical"
> items listed below were fixed in later builds; this file is a historical
> record and does not describe the current state of the code.

# AUDIT REPORT — WorkSlop Desktop (~/workspace/desk)

**Tanggal:** 2026-09-30
**Scope:** seluruh kode — `src/`, `main_app.py`, `workslop_cli.py`, `compile.py`, `tools/`, `src/sideload/ipaside_engine/`, `restore.py`, `restore_cache.py`
**Metode:** read-only, 4 auditor paralel, tiap klaim diverifikasi ke `file:line`. Tidak ada file yang diubah.
**Aturan verdict:**
- **CONFIRMED BUG** = terbukti di kode, bisa dijelasin kenapa rusak
- **SUSPICIOUS** = butuh iPhone nyata / build Windows / network buat buktiin
- **OK** = diverifikasi beneran jalan (bukan klaim)

**Kesimpulan 1 kalimat:** login Apple ID-nya kode beneran (bukan fake), engine restore-nya kerjaan serius — tapi build Windows yang di-release **gabisa login Apple ID sama sekali** (2 file native ketinggalan), tiap Apply **nimpa file preferensi live user**, dan ada beberapa tombol yang visual doang.

---

## KRITIS (crash / data-loss / security / fitur mati total)

### K1. Apple ID login MATI TOTAL di build Windows yang di-release — 2 file ketinggalan, bukan 1
- **File:** `compile.py` (committed), `src/sideload/ipaside_engine/tls.py:21`, `src/sideload/ipaside_engine/paths.py:18-27`
- **Kenapa:** Error user ("Failed to load the Unicorn dynamic library") cuma separuh cerita.
  1. `unicorn.dll` nggak ke-bundle karena baris `--collect-all=unicorn` di `compile.py` **cuma ada di working tree, belum pernah di-commit**. Build dari commit manapun (termasuk yang di-release) nggak punya fix ini.
  2. Kalaupun unicorn di-fix, login TETAP gagal: `tls.py:21` butuh `certs/apple_gsa_ca.pem`, dan `compile.py` nggak punya `--add-data` buat folder itu. PyInstaller nggak pernah copy `.pem`. Hasilnya `FileNotFoundError` di tiap HTTPS request ke Apple.
- **Dampak jujur:** di build Windows v1.0.0 yang baru di-upload, **setiap percobaan login Apple ID pasti gagal**. Bukan kadang-kadang. Pasti.

### K2. Tiap Apply nimpa file `.GlobalPreferences.plist` LIVE user dengan data kosong/parsial
- **File:** `src/devicemanagement/device_manager.py:1211-1216`
- **Kenapa:** kode nulis `plistlib.dumps({})` (plist kosong!) ke `/var/mobile/Library/Preferences/.GlobalPreferences.plist` **tanpa version gate, tanpa merge** — tiap kali apply, mau ada tweak GP atau nggak. Itu file preferensi live user (keyboard, locale, region, appearance), bukan overlay. Kalau ada tweak GP yang aktif, yang ditulis cuma key tweak-nya — tetap full replace, bukan merge. Klaim di AGENTS.md ("written verbatim from the bundled base plist") **salah** — nggak ada base plist di path ini.
- **Dampak jujur:** tiap pencet Apply berpotensi ngereset setting keyboard/bahasa/region iPhone user ke default.

### K3. Switch MobileGestalt/Eligibility di halaman Tweaks NGGAK NGAPA-NGAPAIN pas Apply
- **File:** `src/devicemanagement/device_manager.py:1085-1149`
- **Kenapa:** `_apply_tweak_pass` itu rantai `if/elif` per kelas tweak — dan **nggak ada cabang** buat `MobileGestaltTweak`, `MobileGestaltPickerTweak`, `MobileGestaltMultiTweak`, `MobileGestaltCacheDataTweak`. Nggak ada `else` juga. Jadi switch "Enable Apple Intelligence", "Spoof Hardware/CPU", dropdown spoof model di halaman Tweaks: user geser, pencet Apply, **nol yang kejadian, nol warning**. Satu-satunya jalan yang bener cuma tombol Apply di halaman MobileGestalt sendiri.
- **Dampak jujur:** ini definisi "fake gimmick" — UI yang keliatan kerja tapi nggak nyambung ke apa-apa.

### K4. zsign ke-bundle tapi frozen app nggak akan pernah nemu — signing sideload rusak di semua build
- **File:** `compile.py:148-154`, `src/sideload/ipaside_engine/signing.py:63-90`
- **Kenapa:** binary ditaruh di `_internal/zsign[.exe]` (bundle root), tapi `resolve_zsign()` cuma ngecek `_internal/ipaside_engine/vendor/`, folder exe (satu level di atas `_internal`), dan `vendor/` repo (cuma ada di source tree). Nggak ada yang cocok → jatuh ke PATH → `SigningError("zsign not found")`.
- **Dampak jujur:** sideload signing gagal di semua frozen build padahal file-nya ada di dalam package.

### K5. Zip-slip di import icon theme pack (CWE-22)
- **File:** `src/tweaks/icon_themes/icon_themes_tweak.py:169-170`
- **Kenapa:** `zf.extractall(tmp)` tanpa sanitasi nama member. File `.theme` jahat bisa nulis ke luar temp dir sebagai user yang jalanin app.
- **Dampak jujur:** ini bug security beneran, bukan teori. Satu-satunya yang bikin belum kritis-parah: attacker harus ngasih file theme jahat ke user.

### K6. Crash handler restart app TANPA SYARAT → infinite loop di CLI/worker
- **File:** `src/exceptions/crash_handler.py:337, 355-366`
- **Kenapa:** `_handle_crash` manggil `_restart_app()` yang `os.execv(sys.executable, sys.argv)` — argv yang sama. Di proses `-m`/CLI (`Nugget apply`), crash deterministik = respawn tanpa henti, makan CPU. Di GUI, exception di Qt slot = app mati + restart, state ilang. Klaim AGENTS.md soal tombol "Continue" yang "lets the session keep running" **salah** — tombolnya "Restart App" dan kode selalu restart.
- **Dampak jujur:** crash kecil jadi kehilangan semua progress + potensi loop.

### K7. Revert RdarFix ngapus key CustomResolution (saling timpa file yang sama)
- **File:** `src/tweaks/tweak_classes.py:205`
- **Kenapa:** revert nulis `other_tweaks[file_location] = {"nugget": 0}` — **replace, bukan merge** — di `FileLocation.resolution` yang juga dipake CustomResolution. Aktifin CustomResolution + revert RDAR dalam satu apply = key resolusi ilang.
- **Dampak jujur:** setting resolusi user bisa kehapus diam-diam.

### K8. Wallpaper ke-6..N diam-diam dibuang pas apply (tanpa warning)
- **File:** `src/devicemanagement/device_manager.py:34, 602`
- **Kenapa:** `MAX_TENDIES_PER_RESTORE = 5`, list dipotong `[:5]` tanpa warning ke user (padahal `verify_tendie` ngizinin 10).
- **Dampak jujur:** user apply 8 wallpaper, cuma 5 yang kepasang, nggak dikasih tau.

---

## MAJOR (rusak beneran, tapi nggak ngancurin data)

### M1. Pilih IPA yang ada app extensions → crash `tr()` (TypeError)
- **File:** `src/gui/ios/sideload.py:390-392`
- **Kenapa:** helper lokal `def tr(text: str)` cuma 1 parameter (line 35-36), tapi dipanggil `tr("Contains %n app extension(s)...", "", len(...))` — 3 argumen. Udah direproduksi: `TypeError`. IPA nggak kepilih.
- **Dampak jujur:** banyak IPA sideload umum (yang ada extensions) gabisa dipilih. Ini crash kedua di halaman sideload setelah yang kemarin.

### M2. "Sign Only" manual nge-freeze seluruh UI
- **File:** `src/gui/ios/sideload.py:579-583`
- **Kenapa:** `signing.sign_ipa(...)` dipanggil langsung di slot UI (satu-satunya engine call di halaman ini yang nggak dibungkus QThread). zsign di IPA gede = puluhan detik–menit freeze total, no progress, no cancel.
- **Dampak jujur:** app keliatan hang. User bakal kill paksa.

### M3. "New Folder" di App Data SELALU gagal (TypeError)
- **File:** `src/gui/ios/appdata.py:196`
- **Kenapa:** manggil `ha.makedirs(self.path, exist_ok=True)` tapi `AfcService.makedirs` di pymobiledevice3 10.7.1 **nggak punya** kwarg `exist_ok`. Selalu TypeError.
- **Dampak jujur:** tombol New Folder mati total.

### M4. Edit nilai Status Bar hilang diam-diam pas toggle dimatiin-dinyalain
- **File:** `src/gui/ios/statusbar.py:332, 352-356, 383`
- **Kenapa:** lambda toggle ngiket `current` versi lama; handler edit nggak refresh closure. Edit → toggle off → toggle on = nilai balik ke yang lama, tanpa warning.
- **Dampak jujur:** editan user lenyap misterius.

### M5. Thumbnail icon theme nggak pernah render (kondisi kebalik)
- **File:** `src/gui/ios/icon_themes.py:185-196`
- **Kenapa:** `get_icon_data()` return bytes PNG kalau file ada — persis kondisi di mana pixmap BISA dibikin — tapi kode cuma bikin pixmap kalau `data is None`. 100% repro: semua kartu nampilin "?".
- **Dampak jujur:** halaman Icon Themes keliatan rusak/kosong.

### M6. Export video PosterBoard di Linux SELALU diakhiri dialog error palsu
- **File:** `src/gui/ios/posterboard.py:561-568`
- **Kenapa:** abis export sukses, kode jalanin `open -R` (binary macOS) di Linux → `FileNotFoundError` → ketelen `except Exception` → dialog "Error!" padahal export-nya berhasil.
- **Dampak jujur:** user Linux dikibulin tiap export.

### M7. Reset cuma ada buat sebagian tweak — 5 keluarga NEMPEL permanen di device
- **File:** `src/devicemanagement/device_manager.py:~1360-1385`
- **Kenapa:** `_reset_tweaks` cuma handle StatusBar/Springboard/Daemons/InternalOptions. Nggak ada reset on-device buat: Feature Flags, Risky (OTA/resolusi), MobileGestalt (halamannya nggak punya tombol reset sama sekali), Eligibility, Templates, IconThemes ("Reset Icon Themes" cuma bersihin list lokal — `icon_themes.py:95-98` eksplisit bilang yang udah kepasang "not touched", jadi WebClip permanen).
- **Dampak jujur:** sekali apply, sebagian tweak gabisa di-undo dari app.

### M8. `DANGEROUS_DAEMONS`/`DANGEROUS_KEYS` = set kosong — "pengaman" yang nggak ngamanin apa-apa
- **File:** `src/tweaks/daemons_tweak.py`, `src/devicemanagement/device_manager.py:706-734`
- **Kenapa:** denylist-nya kosong "by design", jadi filter `never_enable` no-op. Satu-satunya guard beneran itu whitelist `INTERFACE_KEYS`. Lebih parah: `_apply_hotload_daemon_forcing` ngelakuin `allowed_keys.update(forced)` — rule hotload jahat bisa bypass whitelist dan disable daemon apa aja.
- **Dampak jujur:** nama variabelnya janjiin proteksi yang nggak ada (security theater).

### M9. `eval()` di `replace_region_code` + replace "US" global
- **File:** `src/tweaks/eligibility_tweak.py`
- **Kenapa:** region code di-substitusi ke `str(plist_data)` terus di-`eval()`. Praktis nggak exploitable (input dibatasi 2 char di GUI), tapi `str.replace("US", code)` ngerusak **semua** substring "US" di plist (URL, identifier, dsb).
- **Dampak jujur:** ganti region code bisa korup plist eligibility secara halus.

### M10. `packaging` di-import tapi nggak ada di requirements
- **File:** `src/gui/ios/statusbar.py:6`
- **Kenapa:** `from packaging.version import Version` — nggak ada di `requirements.txt` maupun `requirements-legacy.txt`. Jalan hari ini cuma karena ketiban transitif.
- **Dampak jujur:** install minimal = halaman Status Bar crash pas import.

### M11. ffmpeg nggak pernah di-bundle → video wallpaper rusak di semua frozen build
- **File:** `compile.py:131-135`, `src/controllers/video_handler.py:35-40`
- **Kenapa:** folder `ffmpeg/` nggak ada di repo; `convert_to_mov()` (dipanggil `posterboard_tweak.py:229`) butuh binary ffmpeg beneran.
- **Dampak jujur:** tendies video gagal di-convert di build release kecuali user kebetulan punya ffmpeg di PATH. (Warning "failed to include cv2!" yang lama juga masih relevan.)

### M12. Subcommand `Nugget restore` = ImportError tiap dipanggil
- **File:** `src/cli/main.py:89`, `restore.py:20-21`
- **Kenapa:** `from restore import main` — tapi `restore.py` nggak punya `main` di level modul.
- **Dampak jujur:** fitur CLI yang diiklankan di USAGE text mati.

### M13. Crash report kekirim ke repo upstream, bukan fork (rebrand bocor)
- **File:** `src/exceptions/crash_handler.py:42, ~48, 407`
- **Kenapa:** `ISSUES_URL` masih `github.com/awesomenull-dev/GoldenNugget`, fallback name "GoldenNugget", banner print "GoldenNugget 9.5.1".
- **Dampak jujur:** user WorkSlop yang klik "Report on GitHub" ngirim issue ke repo orang.

### M14. Terjemahan Indonesia ~60% bolong
- **File:** `Nugget_id.ts` (463 source vs ~760 string di kode)
- **Kenapa:** string UI baru (seluruh alur sideload, deskripsi tweak baru) belum diterjemahin. Qt fallback ke Inggris — nggak crash, tapi...
- **Dampak jujur:** user Indonesia liat campur aduk Inggris di banyak halaman.

---

## MINOR / SLOP (kode mati, dokumen ngaco, bau)

- `src/gui/ios/posterboard.py:17` — `TemplatePreviewCard` nggak pernah diinstantiate, nggak ada click handler. Fitur "preview" yang diiklankan docstring nggak ada.
- `src/gui/ios/settings.py:823` — handler reset backup-location dir udah ditulis tapi nggak disambung ke tombol manapun. Sekali set custom dir, gabisa balik ke default dari UI.
- `TweakID.DisableSolarium`, `TweakID.MetalForceHudEnabled` (`tweak_names.py`) — didefinisikan, nol referensi. `InvalidRegionCodeException` (`eligibility_tweak.py:16`) — didefinisikan, nggak pernah di-raise.
- `main_app.py:214` — referensi `nugget.ico` yang nggak ada di repo (kosmetik; icon beneran dari `workslop_icon.png`).
- `pb_config_manager.py:246` — wallpaper yang udah dihapus user bisa muncul lagi pas apply berikutnya (stale `saved_items`, ada TODO).
- `restore_cache.py --password` — password backup lewat argv → keliatan di `ps`/shell history.
- Dokumen vs kode: AGENTS.md "tombol Continue" (salah, tombolnya Restart), "base plist" (salah, liat K2), MEMORY.md flow iOS 27 "backup→wipe→restore" udah stale (default sekarang `merge_phases=True` = tanpa wipe; wipe klasik butuh `GOLDENNUGGET_NO_MERGE_PHASES=1`).
- Log kepencar 2 direktori (`.../Roaming/Logs` vs `.../Roaming/WorkSlopDesktop/Logs`) karena crash handler install sebelum app name di-set.
- `compile.py:133` — `--collect-all=pillow_heif` no-op diam-diam di Windows/macOS (package linux-only).

---

## SUSPICIOUS (nggak bisa dibuktiin tanpa iPhone / build Windows / network)

- **Payload diterima iOS atau nggak:** semua payload (MobileGestalt, eligibility sqlite, PosterBoard sqlite, status bar archive, Liquid Glass Tier 3/4/5 — 39 key ditandai "unverified on-device") **belum pernah dites di device**. Kode generate-nya bener, iOS nerima atau nggak = misteri. Terutama iOS 26.2+ (Apple nutup jalur restore) dan iOS 27.2 beta 2.
- `posterboard_tweak.py:359-366` — reset "PRB" nulis file 0-byte **di path direktori** (`/Library/Application Support/PRBPosterExtensionDataStore`). iOS bakal replace/merge/reject = butuh device.
- Anisette depend ke SATU host pihak ketiga (`anisette.dl.mikealmel.ooo`) buat download provisioning libs pas login pertama. Host mati = login pertama gagal (error message-nya jelas, tapi single point of failure di luar kontrol).
- Fix unicorn perlu build Windows beneran buat proof end-to-end (apakah `unicorn.dll` + 2 mingw DLL beneran ke-copy ke `_internal/unicorn/lib/`).
- Klasifikasi error: `is_device_locked_error` (`device_errors.py`) nganggep SEMUA "MBErrorDomain" = "device kekunci" — restore gagal karena payload ilang pun didiagnosa "unlock device". `NotEnoughDiskSpace` di-retry 18x (nggak akan sembuh dengan retry).
- Login thread bisa lebih panjang umur dari UI (tunggu 2FA sampe 300 detik, non-daemon) — tutup app pas nunggu = shutdown stall.

---

## YANG UDAH OK (diverifikasi beneran, bukan klaim)

- **Login Apple ID itu kode SRP+anisette BENERAN, bukan stub.** Ditelusur end-to-end: `sideload.py:299` → `sideload_worker.py:38` → `gsa.py:788` — SRP-6a parameter Apple, PBKDF2 s2k, AES-CBC/GCM, endpoint `gsa.apple.com` beneran, 2FA trusted-device + SMS beneran, provisioning `developerservices2.apple.com` beneran, keypair RSA-2048 beneran. Tiap failure raise typed error — nggak ada jalur fake-success.
- **Password nggak pernah nyentuh disk.** Cuma token (adsid, GsIdmsToken) yang disimpen; `_secure_write` 0o600 (no-op aman di Windows); email di-hash SHA-256 jadi nama file. (Batasan jujur: string Python immutable — wipe RAM nggak bisa dijamin sempurna.)
- **Mayoritas tweak generate payload beneran:** MobileGestalt port verbatim, eligibility (Config.plist di-skip dengan warning jujur karena butuh BookRestore), daemons whitelist, status bar struct serializer (C bitfield table didokumentasi), PosterBoard WAL/SHM 0-byte companion + sqlite_sequence fix — semuanya ketelusur sampe domain restore.
- **Alur iOS 27:** protective backup + `restore_cache.py` recovery tooling-nya kerjaan serius (prune, unlock-wait loop, AFC media re-push). Klasifikasi "payload-generated ≠ iOS-accepted" dipertahankan — nggak ada klaim palsu di kode soal ini.
- `py_compile`: 0 gagal di semua file. Qt resources 77/77 resolve. Page indices home.py bener semua. Preset save/load/export/import wired penuh. Nggak ada Qt type-error lain di scope GUI selain M1 (sweep `loadFromData`/`QPixmap`/`QImage` bersih).

---

## URUTAN FIX YANG DISARANKAN

1. **K1** — commit fix unicorn + tambah `--add-data` buat `certs/apple_gsa_ca.pem`, rebuild Windows, upload ulang ke release. (Tanpa ini, sideload = mati.)
2. **K4** — benerin `resolve_zsign()` ngecek `sys._MEIPASS/zsign[.exe]`.
3. **K2** — jangan pernah tulis `.GlobalPreferences.plist` kosong; merge atau skip kalau nggak ada tweak GP.
4. **K3** — tambah cabang MobileGestalt di `_apply_tweak_pass` ATAU disable switch-nya di halaman Tweaks dengan penjelasan.
5. **K5** — sanitasi nama member zip (tolak `..` dan absolute path).
6. **K6** — jangan `os.execv` dari konteks CLI/`-m`; pertimbangkan ulang policy restart.
7. **M1, M2, M3** — crash/freeze/fail yang user langsung rasain.
8. **K7, K8, M7** — correctness + reset story.
9. **M13** — rebrand crash handler ke repo fork.
10. Sisanya minor/slop.

**Catatan jujur penutup:** build v1.0.0 yang baru di-upload ke release **nggak boleh dipromosiin sebagai "udah jadi"** sebelum K1–K4 di-fix dan di-rebuild. Login Apple ID dan sideload signing — dua fitur headline — mati di build itu.
