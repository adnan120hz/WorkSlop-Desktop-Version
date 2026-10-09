#!/usr/bin/env python3
"""Frozen-file guard for the Custom Icons / Icon Themes menu.

The Icon Themes menu (page + iOS 18 icon table + ZIP pack import) was
proven working on the user's own phone on 2026-10-09 (iOS 18 icons live
on the home screen after the v14 round). By explicit user order the
menu is FROZEN: a future WorkSlop overhaul must not silently change
its behavior.

This test pins the SHA-256 of every file that implements the menu:

* ``src/gui/ios/icon_themes.py`` — the page (themes list, the iOS 18
  two side-by-side tables (Light/Dark) with
  per-row Add + one Add All per table, "Import Icon Pack (.zip)...").
* ``src/tweaks/icon_themes/icon_themes_tweak.py`` — the model, the
  WebClip builder (``WorkSlop_<bundleID>,<name>``) and the hash-matched
  pack importer.
* ``src/gui/dialogs/icon_pack_downloader.py`` — the online pack
  downloader dialog the page opens ("Download Icon Packs"); frozen
  because the page launches it and imports through it.
* ``files/ios18_icons/Light/*.png`` (51) and
  ``files/ios18_icons/Dark/*.png`` (50) — the bundled catwithabaloon
  catalog the table and the ZIP hash-matcher both resolve against.

Adding, removing, renaming or editing any of these trips the guard.
That is the point: if the user explicitly orders a change, update the
manifest below in the SAME commit (see FROZEN_ICON_THEMES.md at the
repo root). Any other red run of this test means an un-ordered change
reached a frozen menu.

No Qt needed — hashing only, runs anywhere.

Run: python tools/test_icon_themes_frozen.py
"""
import hashlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PASS = 0
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

FREEZE_MARKER = "FROZEN 2026-10-09 (user order)"
MARKED_FILES = (
    "src/gui/ios/icon_themes.py",
    "src/tweaks/icon_themes/icon_themes_tweak.py",
)
ICON_DIRS = ("files/ios18_icons/Light", "files/ios18_icons/Dark")

# SHA-256 manifest of the frozen files, paths relative to the repo
# root. Regenerate ONLY on an explicit user order, in the same commit
# as the change itself (see FROZEN_ICON_THEMES.md).
#
# Ordered exceptions on record: Fix Audit 4 + 88 (explicit fix order)
# changed ONLY the zip-caller block of ``src/gui/ios/icon_themes.py``
# and the download/import caller of
# ``src/gui/dialogs/icon_pack_downloader.py``; their two hashes were
# regenerated in the same change. The frozen tweak model and the icon
# catalog are byte-identical to the original freeze.
EXPECTED_SHA256 = {
    "files/ios18_icons/Dark/app-store.png": "045c187857ef476ecf26c92557841dd7ad3c4930c1964062c0f521ca1bd9f6fe",
    "files/ios18_icons/Dark/apple-sports.png": "7efc01408618b76f74f85f6bfdc9737ca7252b44bf4590671ccfd8dd3a155d66",
    "files/ios18_icons/Dark/apple-store.png": "37ba6504058b30be7180d3126477ce0be6e9346be3724de2b4a5f7bc8453c682",
    "files/ios18_icons/Dark/apple-tv-remote.png": "e6f5e59ef13b56b3e2abc20594fd1482aa22a50aed7078c1d4b1ec9edc415b2c",
    "files/ios18_icons/Dark/books.png": "3f740c69927c1962fa794b215f3b3b38b79ec8d3d5b86fad1361f9a7259d87f5",
    "files/ios18_icons/Dark/calculator.png": "6988ad1abb07ccf14362860c19f3d037dcd8dd7df68e995b434dfb98ad4e9169",
    "files/ios18_icons/Dark/calendar.png": "166387ba46efecf2536f0d59cf25fa7a1e7834d1edd4a0ed58ba83c4788c5e1c",
    "files/ios18_icons/Dark/camera.png": "476e8ff8f722c7b81fc6a181a554f1f04bfcffae58fa3c6651deae9ad27f42b8",
    "files/ios18_icons/Dark/clips.png": "a0a6643b5d3a9e105659c0ae1928f46ef33db70b5bb3ac6785e877afa644ed9c",
    "files/ios18_icons/Dark/clock.png": "ab1f7eec86c7e98d9bd1cae9a157ab10b0fd9cc208ec8a30c13bd4511c560454",
    "files/ios18_icons/Dark/compass.png": "bc468cebe201fcaf70340372d13bb1b0092cf71313157e1d449c8d75c11315b5",
    "files/ios18_icons/Dark/contacts.png": "05ecbc939ee8e779586ffa2af56968eab586dbafcd15b1c27c6d50e8a76841e8",
    "files/ios18_icons/Dark/facetime.png": "91960d59868c57f8f5ca865f2122a16e92fb278641183154cfe12a12e9162837",
    "files/ios18_icons/Dark/files.png": "107cc2c6a504fc12922778eafd0caa74e1b0c1bcdf923710e55ba2477cb9b7ae",
    "files/ios18_icons/Dark/find-my.png": "a9402f46a00cbd8ebdc4bbaa6608071026a764193fadbbfd535db1d39965f7d9",
    "files/ios18_icons/Dark/fitness.png": "a1890ee05bdb8ef1271574e1ab8c5b4ee41232e720bcc62358dbc09f16191fd1",
    "files/ios18_icons/Dark/garageband.png": "dc93139eaa0b649350407217b11dfa05bb6b53034306f838b56abb772dc89bf4",
    "files/ios18_icons/Dark/health.png": "1dd474050d005972a7b1749407e950ad173894503ba9b7671fdcf3b7a9c67ef6",
    "files/ios18_icons/Dark/home.png": "1923ca1fce463dd042b551c7b0285585cf417441fb45e9aec48f2a6bde038d92",
    "files/ios18_icons/Dark/imovie.png": "7470016d54d2ce27aee95c7c9b6979915c01c7838b3fcbecbd16da2c06a81476",
    "files/ios18_icons/Dark/keynote.png": "efc9a528347aba93822ae0b5ba5338d8ac4670dabb5f414a44ecc3f7f0c6b3bd",
    "files/ios18_icons/Dark/magnifier.png": "3438ecddbcd287e3db482b199a16a20343ed60a9353fdfe02605c1833e617f30",
    "files/ios18_icons/Dark/mail.png": "1f8698adec538d6e238f6fe78f790c604620f3775914d61d89a69059d479fcbb",
    "files/ios18_icons/Dark/maps.png": "074a7e04d2943c2d92f422a0e0f8fdd3779a0caac0a88eb0761a4dfe2f2ee36e",
    "files/ios18_icons/Dark/measure.png": "e67ad2e84e0a6f6402552ed726bc4988df1940c158b98897b3df52211463a58a",
    "files/ios18_icons/Dark/messages.png": "f606175466517aff50ba563d62b0ede40dd8f86bd7e0959690411fb1f713ba3d",
    "files/ios18_icons/Dark/music-classical.png": "ccfa5d8c4f8348008f5a78c80406394de86a17e5275755e14e8790e650f3f558",
    "files/ios18_icons/Dark/music.png": "8d0593d7b80559be90fd67142164c9ae932c88196be5e0881e9f77d91d1e2350",
    "files/ios18_icons/Dark/news.png": "6763bb8e725ef1df24dfde75666583183f53c398d0dec60f89bc7f640d674046",
    "files/ios18_icons/Dark/notes.png": "13759bf52a355a5794bf61e3d085c4a443b1275a257b3d131d0c5d850194870c",
    "files/ios18_icons/Dark/numbers.png": "47ccd18b7a51b9d7bf1618834afca98a2fcb1248c2a935a54f1b42c584fd0ed1",
    "files/ios18_icons/Dark/pages.png": "887356780cbc5c1c8a512c2d3f5a2ba3fc8c451d29b2fbfa1a9f81fc403ab12c",
    "files/ios18_icons/Dark/passwords.png": "e47b10acc67e96d1cbbe5f03cb98af088d765a706760b8755a6fac585daf1d88",
    "files/ios18_icons/Dark/phone.png": "2c3a4591ac535228d5069cb89de8fe5d403272d45f6075c4b9c4957af17b4949",
    "files/ios18_icons/Dark/photos.png": "aa8ce7f31c162bd4cb922176d4c2cafa8d66b7700a0602fdf97a24c73663558f",
    "files/ios18_icons/Dark/podcasts.png": "1274aa35a6d5b509f40590c839598ee0f70bb1849892d3f1eee0cc00092d841b",
    "files/ios18_icons/Dark/reminders.png": "3b9bea68c42f7e8896008347b8c1bcdead3db3d38f1b54f52b422c4003a448c6",
    "files/ios18_icons/Dark/safari.png": "5b710c514fefe25583b33fcfe5ac760edf729230b442391625a3041f5fc76d47",
    "files/ios18_icons/Dark/settings.png": "d67b6929faca27425ea9db0eadf4e0bc9d4dfc7a9d5ff9a8bda7f21a3b16f48b",
    "files/ios18_icons/Dark/shazam.png": "2c44d85c47d7db417bda4b65eca43c855399420ab7b432d1cca1e86497c7ec8e",
    "files/ios18_icons/Dark/stocks.png": "bf30468b67f6730aea68b7f64a7463f8fc2c8d773c16b0d48f0e09c90b3fcc04",
    "files/ios18_icons/Dark/swift-playgrounds.png": "ad01a02a407347efe6e611c75dedca1c09dfe5d736d0406d96ad2a53ea70eb44",
    "files/ios18_icons/Dark/testflight.png": "4a5ff9751953296daf5780c9ecdb2d51983b6cf92393f5fb08fc76e82bacff3c",
    "files/ios18_icons/Dark/tips.png": "f3a4f5f39815ac46fc2e413ad200ae363dcf6945c2ccaf055a24361033fc1f05",
    "files/ios18_icons/Dark/translate.png": "260ff73b42c66ae92656d0576ef3e6d4f3e33c2311936a521b0ec156e027efc5",
    "files/ios18_icons/Dark/tv.png": "737ef9ddd7004b3aa0950d7fc8f33396b09c01e3fbcbaa98288dba68ca6111dc",
    "files/ios18_icons/Dark/voice-memos.png": "f26b832f1241a1aaa384d81d7627594d29f09e49cb4b7cc2523dc9a2fe74904d",
    "files/ios18_icons/Dark/wallet.png": "b298913f272555bb70218c10b1cc0ce0655f7413baf702a4f3e0f339247862a7",
    "files/ios18_icons/Dark/watch.png": "c7bc40e969cef802ac51c4f0618ede887f55b0524b3e03307054eb341663780e",
    "files/ios18_icons/Dark/weather.png": "8b08684d242e36b7b6614b50b422e6c7388146c0b5bcf2b1cc6af3d305454792",
    "files/ios18_icons/Light/app-store.png": "c6005a5c27b3c7d89a542290161ec91fe2495650727662190eda21c31000b6cb",
    "files/ios18_icons/Light/apple-sports.png": "81d10ec2efc8cfbb7af80e4d545fb281830141a0006041bad040bac8be832003",
    "files/ios18_icons/Light/apple-store.png": "c1e52f7c61493b299797a9ec3241a616c7c3295a514a785be667db52e60e0c19",
    "files/ios18_icons/Light/apple-tv-remote.png": "e6f5e59ef13b56b3e2abc20594fd1482aa22a50aed7078c1d4b1ec9edc415b2c",
    "files/ios18_icons/Light/books.png": "788ddc36892d0c4507f9d7f76d8f0d7b1df3349a9f7c84206a4299aed6f68201",
    "files/ios18_icons/Light/calculator.png": "8ec311c3c1e64a435f1d7c9394b98e3e71bcea86f667021d6b1a24bb10a8bb46",
    "files/ios18_icons/Light/calendar.png": "9164ff64b6c5ca5f938a20ed850af064823224f1d177b2088a433babd031df97",
    "files/ios18_icons/Light/camera.png": "0aefe4a166a4fdb7548bc1ec7a871c31a617f46e68c4c50f4bbecaaa3779fd29",
    "files/ios18_icons/Light/clips.png": "a0a6643b5d3a9e105659c0ae1928f46ef33db70b5bb3ac6785e877afa644ed9c",
    "files/ios18_icons/Light/clock.png": "dad4c388fbc74430c2da6c38e0dcdc3c5ca76808b588550d8893aef148f8edb5",
    "files/ios18_icons/Light/compass.png": "bc468cebe201fcaf70340372d13bb1b0092cf71313157e1d449c8d75c11315b5",
    "files/ios18_icons/Light/contacts.png": "3b0ab82a363fbacb05eaa1ced54cd8f0176001f8f3e18769fe474026f27de5d1",
    "files/ios18_icons/Light/facetime.png": "b69b40b623a06efc990b5f433cd9d222529cfce30ac0f2376af9719c3d30410a",
    "files/ios18_icons/Light/files.png": "849e0cd8c26f7183dbab3427866c90320128467e6b86d928e55bbb744be54c93",
    "files/ios18_icons/Light/find-my.png": "29b50354b6d60dc2e750ddb6595c882d67590675001aeb69ce96e68c79a4fff3",
    "files/ios18_icons/Light/fitness.png": "a1890ee05bdb8ef1271574e1ab8c5b4ee41232e720bcc62358dbc09f16191fd1",
    "files/ios18_icons/Light/garageband.png": "495ad201144f699fbaa347570e0758461dff72d7b7641579a3529a00b22da12a",
    "files/ios18_icons/Light/health.png": "d055305a7843d3401108b5dce7d5dcfdf4239e4fbdf5da55f284f9803c7f8dbe",
    "files/ios18_icons/Light/home.png": "3e5aa4f562dfa89a9b07d6d04509ff974e28f5ed467f15385d53bf517d53ffd7",
    "files/ios18_icons/Light/imovie.png": "2c05cb46f395cf45e83ae8cdeca57a04e6d33b6212bf5a3aff13acea27fa4b9e",
    "files/ios18_icons/Light/keynote.png": "bee897592823d8314e8f9477dee550d07c069c597909d232e3c6ef1ae9e30280",
    "files/ios18_icons/Light/magnifier.png": "3438ecddbcd287e3db482b199a16a20343ed60a9353fdfe02605c1833e617f30",
    "files/ios18_icons/Light/mail.png": "ecb9ffdb25d8c2a4a72fbd7842a005dcb70256d8815362eb7091b57c19b884e5",
    "files/ios18_icons/Light/maps.png": "72346881bcdbf97be03a8eae0a49c5e215c9a70a82e2ffcac6ac47a8a224784a",
    "files/ios18_icons/Light/measure.png": "e67ad2e84e0a6f6402552ed726bc4988df1940c158b98897b3df52211463a58a",
    "files/ios18_icons/Light/messages.png": "07811de1ce37fa4f7095e7115cca335122f2503be0dff65940cf288df7cc991d",
    "files/ios18_icons/Light/music-classical.png": "041ec21b776d9fa0c17fa117cd5198cb1c6e37aeddc6ee562cd3eeac06dfc872",
    "files/ios18_icons/Light/music.png": "e72f04ce77d0e13913818650e33eb9c135a97594c115b025291218e3761241e4",
    "files/ios18_icons/Light/news.png": "b08186922ce3c9b3f4b15b5f1865e5eb116e1748970d1a97e1b3fe3917361bc4",
    "files/ios18_icons/Light/notes.png": "dfb34b92d602f1676194f17236d2f33ffc6e7737c1058f605f2ae2cda4f270c1",
    "files/ios18_icons/Light/numbers.png": "6c3f5dbef8510bf97670f7f232ba6d921a0cf4215f317975a8e6547af71a1d3a",
    "files/ios18_icons/Light/pages.png": "7cb6dc3e729d98aa25a78c048c56eb1414f11060d1fbf01696e3fdc46b2b2d54",
    "files/ios18_icons/Light/passwords.png": "7daf1882cd38b80dd15519c63903b7cf73d8084f99958db3512aca3c2ad14a16",
    "files/ios18_icons/Light/phone.png": "84d67463ff5ba89861d05870b568ad4161cf704a5660b3ff32d916b1278e7e62",
    "files/ios18_icons/Light/photos.png": "2c2b324fba0b20b3895c19d98442356819694f38d19370bda38b816b561fb558",
    "files/ios18_icons/Light/podcasts.png": "9cc80a0d34d8b2320e0ddb3888d3e9f1afd4e371ff9ae8783e3ea6cc989c7074",
    "files/ios18_icons/Light/reminders.png": "fd3ae4b877a171bfe73c65542bb7b9be51840140efd9765a54bc0a524bd85860",
    "files/ios18_icons/Light/safari.png": "5c806d04b21f3a11f288af8faea8a496caab918a5023a2a48e985a9d6713c8e8",
    "files/ios18_icons/Light/settings.png": "ae4f659cce86c980a2d1e753e1c45855478d599375f209349f3a02121b7c48a8",
    "files/ios18_icons/Light/shazam.png": "59d7dad3dcfad5155b81691f90207887bdf163aded61b4532ee735124a43d2d2",
    "files/ios18_icons/Light/shortcuts.png": "6247c6724fd8f7bfa51b7f9f09109e6981afd387348c14fa400d240312bdf49f",
    "files/ios18_icons/Light/stocks.png": "bf30468b67f6730aea68b7f64a7463f8fc2c8d773c16b0d48f0e09c90b3fcc04",
    "files/ios18_icons/Light/swift-playgrounds.png": "20a4a3f6547b49f7e4a791be7972332af96183609b42efa6c425977164b1115d",
    "files/ios18_icons/Light/testflight.png": "4a5ff9751953296daf5780c9ecdb2d51983b6cf92393f5fb08fc76e82bacff3c",
    "files/ios18_icons/Light/tips.png": "3ac6727335ed3600f85bb5800f6c9b701655350b991a9cc89315437affaebeda",
    "files/ios18_icons/Light/translate.png": "260ff73b42c66ae92656d0576ef3e6d4f3e33c2311936a521b0ec156e027efc5",
    "files/ios18_icons/Light/tv.png": "737ef9ddd7004b3aa0950d7fc8f33396b09c01e3fbcbaa98288dba68ca6111dc",
    "files/ios18_icons/Light/voice-memos.png": "f26b832f1241a1aaa384d81d7627594d29f09e49cb4b7cc2523dc9a2fe74904d",
    "files/ios18_icons/Light/wallet.png": "b298913f272555bb70218c10b1cc0ce0655f7413baf702a4f3e0f339247862a7",
    "files/ios18_icons/Light/watch.png": "c7bc40e969cef802ac51c4f0618ede887f55b0524b3e03307054eb341663780e",
    "files/ios18_icons/Light/weather.png": "f46be82e7592687241321a0cb7e043f0d147eb2819eec03d858bec125d4ab4a9",
    "src/gui/dialogs/icon_pack_downloader.py": "0406c608892b97e3c21161e2617283d763aa09cab70d218c879f85e895d5acc8",
    "src/gui/ios/icon_themes.py": "c64532ef4680c56704af2bb8b8d5c30d7909edd9532fa7a66ad2e874ef047109",
    "src/tweaks/icon_themes/icon_themes_tweak.py": "3f344d6336be0c7a44aab3eef3c012fc7e7391c7f2ce144584ee111ebe0a3860",
}


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    print(f"frozen manifest: {len(EXPECTED_SHA256)} files pinned")

    print("\nevery frozen file present + byte-identical (sha256)")
    missing, changed = [], []
    for rel, want in sorted(EXPECTED_SHA256.items()):
        path = os.path.join(ROOT, *rel.split("/"))
        if not os.path.isfile(path):
            missing.append(rel)
            print(f"  MISSING FROZEN FILE: {rel}")
            continue
        got = sha256_of(path)
        if got != want:
            changed.append(rel)
            print(f"  FROZEN FILE CHANGED: {rel}")
            print(f"    expected sha256: {want}")
            print(f"    actual   sha256: {got}")
    check(f"all {len(EXPECTED_SHA256)} frozen files present",
          not missing, "; ".join(missing))
    check("frozen manifest intact — the Icon Themes menu is FROZEN by "
          "user order (2026-10-09); changing any of these files needs "
          "an explicit user order AND a manifest update in the same "
          "commit (see FROZEN_ICON_THEMES.md)",
          not changed, "; ".join(changed))

    print("\nno icon added, removed or renamed in the frozen catalog")
    for icon_dir in ICON_DIRS:
        prefix = icon_dir + "/"
        pinned = sorted(rel for rel in EXPECTED_SHA256
                        if rel.startswith(prefix))
        actual = sorted(
            prefix + name
            for name in os.listdir(os.path.join(ROOT, *icon_dir.split("/")))
            if name.endswith(".png"))
        check(f"{icon_dir}: {len(pinned)} icons pinned, none added/"
              f"removed/renamed", actual == pinned,
              f"on disk: {len(actual)}")

    print("\nfreeze marker still on the two main modules")
    for rel in MARKED_FILES:
        with open(os.path.join(ROOT, *rel.split("/")),
                  encoding="utf-8") as f:
            head = "".join(f.readline() for _ in range(4))
        check(f"marker present in {rel}", FREEZE_MARKER in head)

    print(f"\nALL {PASS} CHECKS PASSED")


main()
