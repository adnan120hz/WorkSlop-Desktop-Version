# Riset: hapus efek corner + refleksi di pinggiran ikon (iOS 26 Liquid Glass)

Tanggal: 2026-09-30. Status: **TWEAK SUDAH ADA — tidak perlu key baru.**

## Temuan

Tweak yang diminta user ("pinggiran sisi icon ada efek corner dan refleksi yang
ganggu") **sudah ada** di WorkSlop Desktop, di-port verbatim dari
leminlimez/Nugget `load_featureflags()`:

- **ID:** `TweakID.SolariumFFIconServices`
- **Judul UI:** "Disable Solarium (Liquid Glass) — Icon Services"
- **Section:** Feature Flags (`src/tweaks/registry.py:150`)
- **Mekanisme:** `FeatureFlagTweak` → tulis ke
  `/var/preferences/FeatureFlags/Global.plist` saat Apply:
  ```json
  {"IconServices": {"EnhancedGlass": {"Enabled": false},
                    "SolariumCornerRadius": {"Enabled": false}}}
  ```
- `IconServices` = service sistem yang me-render ikon Home Screen;
  `EnhancedGlass` = efek kaca/refleksi, `SolariumCornerRadius` = corner
  treatment ikon.

Payload di atas diverifikasi via `spec.factory().apply_tweak({})` (bukan karangan).

## Kenapa ini jawaban yang benar (bukan key tebakan)

- Komunitas (gist klutzyT, arsip) men-disable Liquid Glass via FeatureFlags
  `Global.plist` — dan gist-nya sendiri bilang "USE NUGGET 7.2's (or later)
  FEATURE FLAG OPTION INSTEAD", yang mana fork ini sudah punya.
- `UIDesignRequiresCompatibility` (Info.plist per-app) BUKAN solusi: itu
  opt-out per aplikasi, deprecated dan dihapus di iOS 27.
- "Reduce Transparency" (Accessibility) hanya melemahkan efek, tidak
  menghilangkan edge shine di ikon (Macworld).

## Batasan jujur

- Flag-flag ini dari penemuan komunitas (via Nugget), bukan dokumentasi Apple.
- **UNVERIFIED di device** — perlu tes iPhone iOS 26: nyalakan tweak →
  Apply → reboot → lihat ikon Home Screen.
- Tidak ada perubahan UI yang dibutuhkan; tweak sudah tampil di section
  Feature Flags dan ikut jalur Apply yang ada.
