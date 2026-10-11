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
* ``files/ios18_icons/Tinted/*.png`` (51) — monochrome duotone
  variants generated from the Light PNGs (iOS 18 tinted style),
  added by explicit user order 2026-10-11 for the new "Tinted"
  table, replacing the removed Rounded tables. Like the originals,
  pinned against silent change.

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
ICON_DIRS = ("files/ios18_icons/Light", "files/ios18_icons/Dark",
             "files/ios18_icons/Tinted")

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
#
# 2026-10-11 (explicit user order): "Light Rounded"/"Dark Rounded"
# tables added. 101 new circle-masked PNGs in
# ``files/ios18_icons/Rounded-{Light,Dark}/`` pinned; the Light/Dark
# originals are byte-identical; ``src/gui/ios/icon_themes.py`` hash
# regenerated in the same change.
#
# 2026-10-11 (explicit user order, revision): the Rounded tables were
# removed (user judged the result ugly) and replaced with a single
# "Tinted" table — 51 monochrome duotone PNGs in
# ``files/ios18_icons/Tinted/`` generated from the Light pack;
# ``src/gui/ios/icon_themes.py`` hash regenerated in the same change.
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
    "files/ios18_icons/Tinted/app-store.png": "8ef3582d0b2bb69e97b74788de51448208fc7f5c2811295454954d0eec1d3a79",
    "files/ios18_icons/Tinted/apple-sports.png": "10194217d812603c1ae77e46b9406090e187a61904bd1a8cc944f15e6824150b",
    "files/ios18_icons/Tinted/apple-store.png": "187c826fa3b87ce5d9df5ad599d8261c4db148b52c8842602f8b42431db82a4e",
    "files/ios18_icons/Tinted/apple-tv-remote.png": "e012377bd617cefaeb8ab61c88de7509ec538598b3a4789d59b86a8118090f89",
    "files/ios18_icons/Tinted/books.png": "ecdce07e5e5e5bd5c2427af66c035938a0fe840d79d686a5c42e41dd9066ba6c",
    "files/ios18_icons/Tinted/calculator.png": "53aaffc3f6ca1e2c388280bea418e6d4741dc942f555e17c300ad9a2df82f6bd",
    "files/ios18_icons/Tinted/calendar.png": "e385f5670096b80af3dc2103c06337067e6ffbf8bb57a2598daf6b1e8ae39a77",
    "files/ios18_icons/Tinted/camera.png": "8192baf85524490da8b9bdafa8c42dafe6f8b5f08e301e22e5f58a0742aaba4d",
    "files/ios18_icons/Tinted/clips.png": "358f22267112f4fc9379b2d5e92cc8e4a366ee71b7b86e2481456aa8bbd80c55",
    "files/ios18_icons/Tinted/clock.png": "5d60a366614d38c11197cba2a7d8f6845f92dc5e2a7217aea296860f6070b971",
    "files/ios18_icons/Tinted/compass.png": "b089a10f00178bfc36b584b34740c6c68036f419e83d73157024ce8fd8f1cf4c",
    "files/ios18_icons/Tinted/contacts.png": "68ac49f198e182f974d81808aef7aa011dc2768a8574fbe46d345bb1a623421d",
    "files/ios18_icons/Tinted/facetime.png": "5a8c9df2bbabd41213925d68ba4f154573dc514e6c764ebb4ea2e070be4f39f5",
    "files/ios18_icons/Tinted/files.png": "6e6206f140f4407f30cee4e95be751df2998a3c05e0aeec2698e409e37f42bc2",
    "files/ios18_icons/Tinted/find-my.png": "c201fd9f78c100aefec87303ecee2147c076a3ae51db21c7f311dc83f6de1ddb",
    "files/ios18_icons/Tinted/fitness.png": "a355042f7686d71593b29d826005516d9e432c22c54f5622ef60f0c49a18f42a",
    "files/ios18_icons/Tinted/garageband.png": "7864c49d5cc0b825a518f470b03887e06da94221019f7965d773272b4233a087",
    "files/ios18_icons/Tinted/health.png": "c6225fd1be018e61f584378d61b065eae5692c5d0d38d10a672217ad44dc5911",
    "files/ios18_icons/Tinted/home.png": "84faafba05432e0310d3982fe11b15ced89c091c3bf5dc15ad9bca5ddbd01d25",
    "files/ios18_icons/Tinted/imovie.png": "48e0a608515ed6b1a6375b222d718035bf87a77104100340683da53d02bc5e7e",
    "files/ios18_icons/Tinted/keynote.png": "8b82a4a0941ee42023e62331b7a0b1f3989016e7bb2bb11c2939f0d8f8c85e42",
    "files/ios18_icons/Tinted/magnifier.png": "c622ad8aeda8eb92e52f25a8527748123157d5e401159478889ca66fc4301e1d",
    "files/ios18_icons/Tinted/mail.png": "953fe7fbe27fc551ec75abd0f67e64fec9fc9fa5063ce47d5e1acb9e161f4ade",
    "files/ios18_icons/Tinted/maps.png": "b899e8eae221c8397bd534a357eecedf1d6b6f486cbde6d3ed8a8017e0c20df6",
    "files/ios18_icons/Tinted/measure.png": "9656bf1bb773fed4d3a876859d87ef95eef15dfc28b543c6e6f888d15cf63fee",
    "files/ios18_icons/Tinted/messages.png": "215330b33e40eb631510d547dadf01e80bd39a4983228c96ae1a7205e642ea7d",
    "files/ios18_icons/Tinted/music-classical.png": "e6e5709c1256bf9428177b09164f62866ccaf5d752ed621bf6a2d014bf81148a",
    "files/ios18_icons/Tinted/music.png": "44a29a515a0a2cdc90c7b66854c4300bd7ce4e4b7bee27ef9b7b53c2d3cd31b1",
    "files/ios18_icons/Tinted/news.png": "24ebbcdd1857d3419a08a3eb290bea088b2704e1d9d1d9dbf618ab578889740e",
    "files/ios18_icons/Tinted/notes.png": "60013a026c9e93ed1c6cf3f05eb93b25b9fac06685f20afd9541832b29e6261d",
    "files/ios18_icons/Tinted/numbers.png": "dfd2946d028baa7f38b5896bc6961a74aa7caef369721ba53be59f1caf08e076",
    "files/ios18_icons/Tinted/pages.png": "529c477c9bdade0bd5891dc98cfe8c1087de5d85de96bed2bab326063a59acdf",
    "files/ios18_icons/Tinted/passwords.png": "69a64da06974fd464d56ee5d5b7cd4d3a7657ae039423e07cae0dc03e90f6b58",
    "files/ios18_icons/Tinted/phone.png": "fb3f630d7c426023ff8f25d523151d6608b840212caa02cd22a59a905abb2605",
    "files/ios18_icons/Tinted/photos.png": "833713f609a3d3719438495eef07187005c1cbcf93135f2c4e9ecac8640d3f1f",
    "files/ios18_icons/Tinted/podcasts.png": "aeafe53c4ec0155a0843be66e5057508e6118dee758de33238d3a6ab4f1db1ac",
    "files/ios18_icons/Tinted/reminders.png": "df3ce68b5ec34971f383eeb63af747859009eae4307e8c3761202c60950c11fe",
    "files/ios18_icons/Tinted/safari.png": "8c9ef14ed194cd5fcaa5868c9a60ad7c89288b34892c2d5203a32c7a735b21e1",
    "files/ios18_icons/Tinted/settings.png": "227e078a43d9083296b747fd4af02970a942f8d265e0148939cdc23ccdd53116",
    "files/ios18_icons/Tinted/shazam.png": "2d418f44595bc8b617aba95dd0c4442dff856fb33ed667a5875c5962a49b12d2",
    "files/ios18_icons/Tinted/shortcuts.png": "923c98144c301674a5c61f8e0aa9e0f338c480ac6be9748ef14e24c729231e3a",
    "files/ios18_icons/Tinted/stocks.png": "a6f2be31c1c88a740f289548ce8d9cb5f7b0b868a81961be4c931cef6cc18afa",
    "files/ios18_icons/Tinted/swift-playgrounds.png": "913f26039ff913be9cd45a57333be94ca5492cd82e75d38be524056b4a00dbd4",
    "files/ios18_icons/Tinted/testflight.png": "fe96f6a6566a9b304aebd67295e9d666746d7e59356a07cc53b4f69673c63fad",
    "files/ios18_icons/Tinted/tips.png": "4552ec0c110fc94902b55bab0c6fa453fa14718f00ba9a7c55e27759777ffaca",
    "files/ios18_icons/Tinted/translate.png": "e564afb9f2f0c592f9e2a01ddafc124fdc40c29cad1e86f0732b6b08b6247603",
    "files/ios18_icons/Tinted/tv.png": "00b4c362c53424ed48cfde2f1f4898a35becf889c84b13aa71958ed51dfe3c18",
    "files/ios18_icons/Tinted/voice-memos.png": "598c20f58982fdbb99d9266ff78f7bf4efd17974d847c57a2efd0f04cdfa7bc1",
    "files/ios18_icons/Tinted/wallet.png": "1d0518299d4b94053fa2ca19525d04633f01dda6c9b6abf97d70e708bdb9444b",
    "files/ios18_icons/Tinted/watch.png": "935f5a41d82ab2b94feb281d4bed7bca76b1e4673d58f45cb21d09aed67e9fd1",
    "files/ios18_icons/Tinted/weather.png": "d85b7364b84d768f6d511d41987e76da5ed8e98b7a097d51bdea57d76c2ffe73",
    "src/gui/dialogs/icon_pack_downloader.py": "0406c608892b97e3c21161e2617283d763aa09cab70d218c879f85e895d5acc8",
    "src/gui/ios/icon_themes.py": "70d79953a23bc51429bb650337be29edec9d23ab080a25eb796481ba425721bd",
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
