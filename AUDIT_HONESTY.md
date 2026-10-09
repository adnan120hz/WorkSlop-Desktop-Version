> **HISTORICAL — superseded (2026-10-09).**
> Pinned to the 2026-09-30 codebase (`~/workspace/desk`, branch `main` @
> `d28570e`). Most findings listed as open criticals below were fixed in
> later builds; this file is a historical record and does not describe
> the current state of the code.

# AUDIT KEJUJURAN KODE — WorkSlop Desktop

Repo: `~/workspace/desk`, branch `main` @ `d28570e`. Tanggal: 2026-09-30.
Sifat: **read-only**, 5 tim auditor paralel, semua vonis wajib bukti `file:line`.
Bukan audit tweak-per-tweak (itu `AUDIT_TWEAKS_DETAIL.md`, tim lain).

## Cara baca vonis

- **REAL** — kode ada + wiring lengkap sampai ke endpoint/lib nyata.
- **STUB** — kerangka ada, belum implementasi.
- **FAKE** — pura-pura jalan (sukses palsu, klaim vs kode beda).
- **DEAD** — tidak dipakai / tidak terjangkau.
- **GIMMICK** — visual-only.
- **UNVERIFIED** — tidak bisa diverifikasi statis, butuh device/runtime. Bukan tebakan.

## Ringkasan eksekutif

| Area | Vonis keseluruhan |
|---|---|
| 1. Sideloading engine | **REAL** — SRP-6a, anisette, provisioning Xcode, zsign, install AFC semuanya kode nyata, 0 stub/TODO. Tapi ada **1 bug wiring yang mematikan seluruh fitur device di halaman Sideload GUI**. |
| 2. Restore/apply pipeline | **REAL** — sparse restore, Apply, backup, iOS 27 flow semuanya genuine. Dua koreksi: flow iOS 27 default-nya merged tanpa wipe; `.GlobalPreferences.plist` ditulis replace tanpa merge. |
| 3. GUI wiring | **Mayoritas REAL** — hampir semua tombol nyambung ke backend. 3 dead code + 1 bug kritis (sama dengan area 1). |
| 4. Utilitas pendukung | **REAL** — anisette, TLS, bundling, ffmpeg jalan. Tapi: crash report + hotload kill-switch **masih menunjuk ke repo upstream** (sisa rebrand), crash handler restart tanpa syarat (risiko loop). |
| 5. Pola AI slop | **Ditemukan** — komentar proteksi bohong (daemon list kosong), 1 gate terbalik, 1 docstring bohong, 8 fungsi mati, ~46+ key Solarium tanpa sumber (UNVERIFIED) ditulis ke device user. |

Kabar baiknya: **tidak ditemukan** pola try/except → return sukses palsu, tidak ada progress bar animasi-palsu, tidak ada data hardcode yang diklaim dari Apple. Engine-nya jujur; masalahnya di wiring, sisa rebrand, dan key tanpa sumber.

---

## Area 1 — Sideloading engine (`src/sideload/ipaside_engine/`)

### Ringkasan
Login Apple ID = kode SRP-6a + anisette + 2FA **beneran**, endpoint Apple asli, provisioning pakai private API Xcode beneran, signing pakai binary zsign beneran, install via AFC + InstallationProxy beneran. Ini bukan mock. Yang rusak: **satu baris di GUI** bikin semua fitur device di halaman Sideload mati total.

### Mekanisme
1. **Login**: `_authenticate_once()` (`gsa.py:349`) → SRP-6a varian Apple (`rfc5054_enable()` + `no_username_in_x()`, `gsa.py:46-48`) → handshake init/complete ke `https://gsa.apple.com/grandslam/GsService2` → dekripsi `spd` pakai AES-CBC (`gsa.py:333`) → tukar ke app-token Xcode (`o=apptokens`, `gsa.py:515`). Password tidak disimpan; cuma token sesi di file 0600 (`gsa.py:70-80`).
2. **2FA**: trigger ke `/auth/verify/trusteddevice` (`gsa.py:405`) atau SMS (`/auth/verify/phone`, `gsa.py:458`) → submit kode → login ulang SRP (`complete_2fa`, `gsa.py:789`). GUI: `LoginThread` → sinyal `twofa_required` → `QInputDialog` → `submit_2fa()` (`sideload_worker.py:9-76`, `sideload.py:530-556`).
3. **Anisette**: `get_headers()` (`anisette.py:264`) pakai package `anisette` 1.2.4; library provisioning Apple diunduh dari `https://anisette.dl.mikealmel.ooo/libs?arch=arm64-v8a` (`anisette.py:47`), state di-cache per-mesin (anti re-provision = anti-abuse Apple). Tidak ada server anisette remote — semua in-process.
4. **Provisioning**: `developer.py:28` manggil `listTeams.action`, `ios/addDevice.action`, `ios/submitDevelopmentCSR.action`, `ios/downloadTeamProvisioningProfile.action` di `developerservices2.apple.com/services/QH65B2/` dengan header `X-Apple-GS-Token` dari login GSA. CSR RSA-2048 digenerate lokal (`signing.py:36`), device diregistrasi (`provision.py:236-343`).
5. **Signing**: `signing.sign_ipa()` (`signing.py:103`) menjalankan binary zsign via subprocess (`-k -p -m -z -o`, `signing.py:147-172`). Fallback berlapis: env `WORKSLOP_ZSIGN` → bundled → repo vendor → PATH; kalau tidak ada → error jelas, bukan sukses palsu.
6. **Install**: `apps.install()` (`apps.py:123`) upload IPA via AFC chunk 4MB dengan progress byte-level, lalu perintah `Install` dengan `PackageType: "Developer"` ke installd via InstallationProxy, streaming `PercentComplete`/`Status` (`apps.py:206-238`). Lockdown via pymobiledevice3 usbmux (`lockdown.py:58-95`).
7. **Refresh**: `refresh.py` (`record()`/`due()`/`refresh_record()`, `sideload.py:622`) re-sign + reinstall — infra nyata, tapi **tidak ada tombol di GUI dan tidak ada scheduler otomatis** (docstring "scheduled background task" belum ada implementasi).

### Tabel temuan

| ID | file:line | Vonis | Bukti | Potensi berhasil |
|---|---|---|---|---|
| SL-01 | `gsa.py:349-398` | REAL | SRP-6a varian Apple, handshake ke `gsa.apple.com/grandslam/GsService2`, dekripsi spd AES-CBC | Masuk akal; UNVERIFIED tanpa Apple ID nyata |
| SL-02 | `gsa.py:405-509` | REAL | 2FA trusted-device + SMS, re-login SRP setelah kode; GUI wire via `LoginThread` | REAL |
| SL-03 | `anisette.py:47,264` | REAL | Libs dari `anisette.dl.mikealmel.ooo`, provision in-process, state di-cache | Bergantung host pihak ketiga up |
| SL-04 | `developer.py:28,61-227` | REAL | Endpoint Xcode privat (listTeams/addDevice/submitDevelopmentCSR/...) + `X-Apple-GS-Token` | Pola AltStore/Sideloadly; UNVERIFIED tanpa Apple ID nyata |
| SL-05 | `signing.py:103-172` | REAL | Subprocess zsign nyata; error diteruskan, bukan ditelan | Binary wajib ada (CI `build.yml:64`, bundle `compile.py:146`) |
| SL-06 | `apps.py:123-238` | REAL | Upload AFC chunked + `Install` `PackageType: "Developer"` | REAL; UNVERIFIED tanpa iPhone |
| SL-07 | `sideload.py:411-416` | **BUG** | `_device_udid()` baca `self.window.dev` — atribut ini **tidak ada** di seluruh `src/` (grep: 0 assignment); `except` → selalu `None` | **Sideload, Installed Apps, Uninstall di GUI selalu "No iPhone connected"**. Fix sebaris: `device_manager.get_current_device_udid()` (`device_manager.py:317`) |
| SL-08 | `refresh.py:1-115` | REAL/DEAD | Infra nyata + CLI `refresh` (`__main__.py:675`); GUI tidak ada tombolnya | "Auto-refresh" cuma manual via CLI |
| SL-09 | `sideload.py:148-166` | REAL/DEAD | Profil LiveContainer nyata, tapi `SideloadThread` tidak terima parameter `profile` → tidak terjangkau dari GUI | DEAD dari GUI |

---

## Area 2 — Restore/apply pipeline (`src/restore/`, `src/devicemanagement/`, `src/controllers/`)

### Ringkasan
Pipeline-nya genuine: bukan "protocol sparse restore" terpisah — tweak dikemas jadi **synthetic minimal backup** lalu dikirim lewat `Mobilebackup2Service.restore()` milik pymobiledevice3. Rantai Apply lengkap tanpa stub. Tapi ada dua hal yang perlu diluruskan dari klaim lama.

### Mekanisme
1. **Pack**: `Backup.write_to_directory()` (`src/restore/backup.py:106-131`) nulis `Status.plist`, `Manifest.db` (iOS 27+) atau `Manifest.mbdb` (iOS 26) + payload `<aa>/<fileID>` dengan fileID = `sha1("<domain>-<path>")`.
2. **Kirim**: `perform_restore()` (`src/restore/__init__.py:27-53`) manggil `Mobilebackup2Service.restore(backup_dir, system=True, reboot=False, ...)`. pymobiledevice3==10.7.1 ter-pin (`requirements.txt:1`).
3. **Apply**: klik Apply (`gui/ios/backup.py:163-164`) → `_on_apply_tweaks` → `apply_tweaks_clicked` (`main_window_mixins.py:640`) → `apply_changes` (`:807`) → `ApplyThread` (`thread_workers/apply_worker.py:47`) → `device_manager._apply_changes` (`:603`): Phase 0 protective backup (iOS 27+) → PosterBoard targeted backup (iOS 26) → tweak pass (`FileToRestore`) → `start_restore` → `restore_files` (`restore.py:961`) → merge/registrasi AppDomain via InstallationProxy.
4. **Full backup**: `mb.backup(full=True, ..., filter_callback=...)` (`protective.py:774`) — progress **real** (passthrough device-driven), tapi scope-nya **protective/selective by design** (cuma HomeDomain prefixes + CameraRoll/Media/Messages + SystemPreferences + Keychain; sisanya di-drain, tidak ke disk).
5. **iOS 27 flow**: `_restore_ios27` (`restore.py:424-967`) beneran 6 fase. **TAPI** `merge_phases=True` adalah default (`restore.py:961`) dan tidak pernah di-override → Phase 2 `reboot=False`: **tidak reboot, tidak wipe**. Flow klasik wipe cuma via `GOLDENNUGGET_NO_MERGE_PHASES=1` atau fallback self-reboot. Klaim dok "backup → wipe → restore" = kode ada, perilaku default beda.

### Tabel temuan

| ID | file:line | Vonis | Bukti | Potensi berhasil |
|---|---|---|---|---|
| RP-01 | `src/restore/__init__.py:27-53` | REAL | `perform_restore` → `mb.restore(..., system=True)` via pymobiledevice3 | Masuk akal; UNVERIFIED di device |
| RP-02 | `src/restore/backup.py:106-131` | REAL | Manifest.db/MBDB + payload `<aa>/<fileID>`, fileID=sha1(domain-path) | Konsisten format backup Apple |
| RP-03 | `restore.py:961-1168` | REAL | `restore_files`: merge_duplicates, AppDomain registration via InstallationProxy | Tidak ada stub |
| RP-04 | `restore.py:424-967,961` | REAL (non-default) | 6 fase iOS 27 lengkap; default `merge_phases=True` = no-wipe | Gap dokumentasi |
| RP-05 | `protective.py:774-775` | REAL | `mb.backup(full=True, filter_callback=...)`, progress real | Scope selektif by design, kode jujur |
| RP-06 | `device_manager.py:1270-1279` | REAL (risky) | `.GlobalPreferences.plist` ditulis **verbatim dari dict tweak, tanpa merge plist live**; komentar kode sendiri: *"SAFETY (K2): this write REPLACES the live file"* | Mitigasi cuma gating (GP tweak on + iOS 27+); risiko locale/keyboard hilang UNVERIFIED |
| RP-07 | `device_manager.py:603-747` | REAL | `_apply_changes` rantai penuh | Lengkap |

---

## Area 3 — GUI wiring (`src/gui/`)

### Ringkasan
Mayoritas REAL — sidebar, Backup, Tweaks, MobileGestalt, Eligibility, Risky, Daemons, Sideload (login/sign), App Data, Settings, Themes, PosterBoard semuanya nyambung ke backend. Tidak ditemukan handler kosong, stub "not implemented", atau progress palsu. Temuannya: 1 bug kritis (SL-07, sama) + 3 dead code.

### Tabel temuan

| ID | file:line | Vonis | Bukti |
|---|---|---|---|
| GW-01 | `src/gui/ios/sideload.py:410-416` | **BUG** | Sama dengan SL-07: `_device_udid()` baca `self.window.dev` yang tidak ada → Sideload/Refresh/Uninstall selalu "No iPhone connected" |
| GW-02 | `src/gui/ios/settings.py:823` | DEAD | `_on_backup_location_reset()` tidak pernah di-connect ke widget apa pun |
| GW-03 | `src/gui/ios/apply.py` + `main_window_mixins.py:601-602` | DEAD | `IOSApplyPage` unreachable — tombol sidebar klasik di-`hide()` (`main_window.py:324`); sesuai desain "Apply hanya di Backup" |
| GW-04 | `src/gui/interface_picker.py:27` | DEAD | `InterfacePickerDialog` tidak pernah diinstansiasi |
| GW-05 | `src/gui/ios/appdata.py:322-323` | STUB (kosmetik) | `_retheme` isinya `pass` — ganti tema tidak me-restyle tree browser |

Wiring yang diverifikasi REAL (rantai lengkap): sidebar 9 menu (`sidebar.py:66` → `main_window_mixins.py:449`); Apply (`backup.py:163` → `mixins:807` → `ApplyThread`); switch Tweaks (`tweaks.py:199` → `tweak.set_enabled` → dibaca jalur Apply); MobileGestalt/Eligibility/Risky/Daemons; Sign In/Out/IPA/Sign Only; App Data house_arrest; Settings preset/pairing reset.

---

## Area 4 — Utilitas & klaim pendukung

### Ringkasan
Utilitasnya jalan beneran: anisette, TLS, bundling, ffmpeg. Dua sisa rebrand yang kritis: crash report dan hotload kill-switch masih menunjuk ke repo upstream. Crash handler restart tanpa syarat (risiko loop).

### Tabel temuan

| ID | file:line | Vonis | Bukti | Potensi/risiko |
|---|---|---|---|---|
| UT-01 | `anisette.py:55-57,96-113` | REAL | Libs diunduh (bukan dibundle, alasan lisensi), cek magic archive, state di-cache per-mesin | Host mati → login Apple ID gagal total |
| UT-02 | `compile.py:65-66,70` | REAL | `--collect-all=unicorn`, `--collect-data=anisette`, `--add-data=.../certs` unconditional; cocok dengan resolver frozen `paths.py:18-28` | Tanpa ini frozen app mati saat login |
| UT-03 | `compile.py:152-159,136-143` | CONDITIONAL | zsign/ffmpeg/idevice cuma dibundle kalau file-nya ada (warning saja kalau tidak) | Frozen tanpa zsign → signing error jelas (bukan sukses palsu) |
| UT-04 | `crash_handler.py:441-450` | REAL (risky) | `_handle_crash` → `_restart_app()` via `os.execv` **tanpa syarat** | Crash-loop: crash deterministik → dialog → dismiss → execv → crash lagi (user-mediated, bukan full-otomatis) |
| UT-05 | `crash_handler.py:45` | REAL (salah alamat) | `ISSUES_URL = "https://github.com/awesomenull-dev/GoldenNugget/issues/new"` — report crash user WorkSlop mendarat di tracker upstream | Sisa rebrand, bug |
| UT-06 | `crash_handler.py:1-24` vs `:316-330` | FAKE (klaim doc) | Docstring: "dismiss it and keep working"; kode: satu-satunya tombol "Restart App" → `_restart_app()` | Tidak ada jalur lanjut tanpa restart |
| UT-07 | `hotload.py:24-25`, `main_app.py:281-286,340-372` | REAL (risky) | `RULES_URL = raw.githubusercontent.com/awesomenull-dev/GoldenNugget/...`; `kill_app` → app nolak start / `os._exit(1)` tiap 5 detik | **Remote kill switch dikendalikan maintainer upstream**, bukan pemilik fork. Bukan RCE (JSON cuma di-parse, tidak di-exec) |
| UT-08 | `tls.py:25-33` | REAL | `ca_bundle()` = certifi + `apple_gsa_ca.pem`; dipakai `verify=` di `gsa.py:164`, `developer.py:74` | Sertifikat terverifikasi Apple asli via openssl |
| UT-09 | `daemons_tweak.py:3-8` | REAL wiring, EMPTY | `DANGEROUS_DAEMONS = set()` kosong by design (jujur di komentar) → guard no-op | Validasi nol hari ini |
| UT-10 | `video_handler.py:35-40`, `requirements.txt` | REAL | `ffmpeg-python`, `convert_to_mov` dipakai PosterBoard | Tanpa binary → gagal tanpa fallback |

---

## Area 5 — Pola "AI slop"

### Ringkasan
Ditemukan pola slop nyata, tapi juga banyak yang **terverifikasi bukan slop** (keluarga `_ff` 13 feature flag = verbatim 1:1 dari upstream Nugget, dicek melawan GitHub raw). Tidak ditemukan pola try/except → sukses palsu.

### Tabel temuan

| ID | file:line | Pola | Bukti |
|---|---|---|---|
| SP-01 | `daemons_tweak.py:8-9,169-171` | Komentar klaim proteksi yang tidak ada | Header *"Daemons that must never be disabled — disabling them bootloops the device"* + *"filled below"* — tapi `DANGEROUS_DAEMONS`/`DANGEROUS_KEYS` **kosong di kedua tempat**. Dulu berisi `{Daemon.VoiceControl}` (commit `ee1e57a`), dikosongkan (`3943122`), dan `VoiceControl` sekarang **bisa di-toggle user** (`:92`, `:197`) |
| SP-02 | `registry.py:578`, `compat.py:26-27` | Gate terbalik vs deskripsi | `WatchOSCompatibility` pakai `ipad_only=True`, deskripsi: pair Apple Watch dengan **iPhone**. Apple Watch cuma pair ke iPhone → tweak disembunyikan tepat di satu-satunya device yang bisa memakainya. Gate buatan fork (`a9cbfa5`), upstream tidak punya |
| SP-03 | `apply_worker.py:515-518` vs `device_manager.py:430` | Docstring bohong | Docstring: *"Runs `device_manager.apply_gestalt_tweaks` … never on iOS 26.2+"*. Fakta: manggil `self.manager._apply_gestalt_tweaks` (private); wrapper publik **tidak pernah dipanggil siapa pun**. Klaim versi juga bertentangan dengan keputusan fork (26.2 beta 1) |
| SP-04 | 8 fungsi | Fungsi meyakinkan, 0 pemanggil produksi | `tendie_preview.py:253` `render_tendie_preview`; `passcode_theme.py:227` `stage_passthm`; `wallpaper_api.py:157,257` `get_source`/`download_file`; `nugget_logger.py:141` `log_banner`; `constants.py:52` `is_version_ios27`; `web_request_handler.py:9` `is_update_available`; `statusbar_archive.py:181,201` (cuma dipakai test) |
| SP-05 | `registry.py:89-105` + 46 spec | Key tanpa sumber | ~46 key `UISolarium*` di-derive mekanis `"UISolarium" + TweakID.name`, ditulis ke `.GlobalPreferences` device nyata; sebagian deskripsi asertif, sebagian jujur *"unverified on-device"* → **UNVERIFIED**, bukan SLOP terbukti |
| SP-06 | `registry.py` Tier 1/2 | Key tanpa sumber | `SBDisableSpecularEverywhereUsingLSSAssertion`, `SBDisallowGlassTime`, `SBDisableGlassDock`, `Calistoga*` — deskripsi asertif, tanpa komentar sumber, tanpa jejak publik → **UNVERIFIED** |
| SP-07 | `registry.py:74-87` | Magic value warisan | UUID `CD97EEB8-…`, `AdvertisingIdentifierSeed`, `maxPairingCompatibilityVersion: 37` — **terverifikasi verbatim dari upstream** `leminlimez/Nugget` `load_springboard()`, termasuk komentar ketidakpastian author asli → REAL (ketidakpastian diwariskan, dilabeli jujur) |

---

## 10 masalah paling kritis (urut prioritas)

1. **`_device_udid()` baca atribut yang tidak ada** (`sideload.py:411-416`) — seluruh fitur device halaman Sideload (Sideload, Installed Apps, Uninstall) mati total, selalu "No iPhone connected". Fix sebaris, backend-only, tanpa ubah UI.
2. **Hotload kill-switch menunjuk ke upstream** (`hotload.py:24-25`) — `raw.githubusercontent.com/awesomenull-dev/GoldenNugget/...`; maintainer upstream bisa mematikan semua instalasi WorkSlop Desktop. Sisa rebrand.
3. **Crash report menunjuk ke upstream** (`crash_handler.py:45`) — issue user nyasar ke repo `awesomenull-dev/GoldenNugget`. Sisa rebrand.
4. **Crash handler restart tanpa syarat** (`crash_handler.py:441-450`) — `os.execv` tiap crash; risiko crash-loop. Docstring bohong soal "dismiss and keep working" (`:1-24` vs `:316-330`).
5. **`.GlobalPreferences.plist` = replace tanpa merge** (`device_manager.py:1270-1279`) — nulis verbatim dari dict tweak; risiko locale/keyboard/region user hilang. UNVERIFIED di device.
6. **~46+ key Solarium tanpa sumber ditulis ke device user** (`registry.py:89-105` + Tier 1/2) — UNVERIFIED; key asing di `.GlobalPreferences` device nyata.
7. **Flow iOS 27 default merged tanpa wipe** (`restore.py:961`) — klaim "backup → wipe → restore" tidak sesuai perilaku default; gap dokumentasi vs ekspektasi keamanan user.
8. **`WatchOSCompatibility` gate terbalik** (`registry.py:578`) — `ipad_only=True` menyembunyikan tweak tepat di iPhone, satu-satunya device yang bisa pair Apple Watch.
9. **`DANGEROUS_DAEMONS` kosong + VoiceControl bisa di-toggle** (`daemons_tweak.py:8-9,92,197`) — komentar janji proteksi bootloop yang tidak ada; daemon berisiko bisa dimatikan user.
10. **Refresh sideload tanpa GUI/scheduler** (`refresh.py`, `__main__.py:675`) — infra nyata tapi cuma via CLI; docstring "scheduled background task" belum ada implementasi; profil 7 hari Apple kedaluwarsa tanpa pengingat.

## Yang tetap UNVERIFIED (jujur, bukan vonis)

- Login Apple ID / provisioning / install: kode genuine, tapi **belum pernah dites** dengan Apple ID nyata, IPA nyata, iPhone nyata, dan frozen build Windows.
- Sparse restore di iOS 26/27: builder konsisten format Apple, tapi penerimaan device belum terbukti.
- Semua key `UISolarium*` / `SBDisable*` / `Calistoga*`: tidak bisa dibuktikan palsu statis, tidak bisa dibuktikan jalan tanpa device.
- Efek `.GlobalPreferences.plist` replace terhadap setting live user.

## Catatan untuk parent

- Semua fix yang diusulkan temuan di atas adalah **backend-only** — tidak ada yang butuh perubahan UI (UI frozen dihormati).
- Tidak ada file yang diubah selama audit ini (murni read-only).
- `AUDIT_TWEAKS_DETAIL.md` tidak disentuh (milik tim lain).
