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
#
# 2026-10-11 (explicit user order, revision 2): the ENTIRE catalog was
# replaced with the official catwithabaloon 2.0 pack release asset
# (iOS.18.App.Icons.by.catwithabaloon.zip, sent by the user): 68 Light
# ("App Icon-1..68"), 68 Dark ("App Icon-69..136", 18 byte-identical to
# their Light twin), 67 Tinted ("App Icon-137..203"; app #68 has no
# Tinted artwork in the pack). The self-generated duotone Tinted set
# was deleted. 17 new apps added as table rows (68 rows Light/Dark,
# 67 rows Tinted). Also fixed: Dark/phone.png and Dark/passwords.png
# were swapped with each other in the old catalog. Every PNG is
# byte-identical from the pack — nothing generated. Manifest
# regenerated in the same change; ``src/gui/ios/icon_themes.py`` hash
# regenerated in the same change.
EXPECTED_SHA256 = {
    "files/ios18_icons/Dark/app-store.png": "045c187857ef476ecf26c92557841dd7ad3c4930c1964062c0f521ca1bd9f6fe",
    "files/ios18_icons/Dark/apple-account.png": "b7b5528cd2e7068d945a339c049ac304317ced06fb76ecbdc0c0351f30df3f26",
    "files/ios18_icons/Dark/apple-sports.png": "7efc01408618b76f74f85f6bfdc9737ca7252b44bf4590671ccfd8dd3a155d66",
    "files/ios18_icons/Dark/apple-store.png": "37ba6504058b30be7180d3126477ce0be6e9346be3724de2b4a5f7bc8453c682",
    "files/ios18_icons/Dark/apple-tv-remote.png": "e6f5e59ef13b56b3e2abc20594fd1482aa22a50aed7078c1d4b1ec9edc415b2c",
    "files/ios18_icons/Dark/battery.png": "98850c266d4ebf0b73c2411fe6e562fe835fea68a08ef81cdef592064cfbb3aa",
    "files/ios18_icons/Dark/blank.png": "dbec3403f3992c79813ef765d34c29667a365fe30e429d4d71d37b327217cdff",
    "files/ios18_icons/Dark/bloom.png": "a5959681fd6e6d454bf57bb42e63460c4ec38b9313234c7d5f1ae7da609b4398",
    "files/ios18_icons/Dark/books.png": "3f740c69927c1962fa794b215f3b3b38b79ec8d3d5b86fad1361f9a7259d87f5",
    "files/ios18_icons/Dark/calculator.png": "6988ad1abb07ccf14362860c19f3d037dcd8dd7df68e995b434dfb98ad4e9169",
    "files/ios18_icons/Dark/calendar.png": "166387ba46efecf2536f0d59cf25fa7a1e7834d1edd4a0ed58ba83c4788c5e1c",
    "files/ios18_icons/Dark/camera.png": "476e8ff8f722c7b81fc6a181a554f1f04bfcffae58fa3c6651deae9ad27f42b8",
    "files/ios18_icons/Dark/clips.png": "a0a6643b5d3a9e105659c0ae1928f46ef33db70b5bb3ac6785e877afa644ed9c",
    "files/ios18_icons/Dark/clock.png": "ab1f7eec86c7e98d9bd1cae9a157ab10b0fd9cc208ec8a30c13bd4511c560454",
    "files/ios18_icons/Dark/compass.png": "bc468cebe201fcaf70340372d13bb1b0092cf71313157e1d449c8d75c11315b5",
    "files/ios18_icons/Dark/contacts.png": "05ecbc939ee8e779586ffa2af56968eab586dbafcd15b1c27c6d50e8a76841e8",
    "files/ios18_icons/Dark/facetime.png": "91960d59868c57f8f5ca865f2122a16e92fb278641183154cfe12a12e9162837",
    "files/ios18_icons/Dark/feedback.png": "c1e20dac7904a81a941da94036d1c56b088f5befa254cff77e21a8ba603b364a",
    "files/ios18_icons/Dark/files.png": "107cc2c6a504fc12922778eafd0caa74e1b0c1bcdf923710e55ba2477cb9b7ae",
    "files/ios18_icons/Dark/final-cut-camera.png": "d49d656cab1af884c549e8d131764bffbfb2398e3f7d95633bad1ef9dc4bcd81",
    "files/ios18_icons/Dark/find-my.png": "a9402f46a00cbd8ebdc4bbaa6608071026a764193fadbbfd535db1d39965f7d9",
    "files/ios18_icons/Dark/fitness.png": "a1890ee05bdb8ef1271574e1ab8c5b4ee41232e720bcc62358dbc09f16191fd1",
    "files/ios18_icons/Dark/freeform.png": "a2bd3512939251f9e28d1513c57d722254dbedbdccf933622db0b86ab930ca1f",
    "files/ios18_icons/Dark/game-center.png": "bdcb1238ccca81fdd8e010069905cecac538f6a7c8f837736c7f746f5c6a3a3b",
    "files/ios18_icons/Dark/garageband.png": "dc93139eaa0b649350407217b11dfa05bb6b53034306f838b56abb772dc89bf4",
    "files/ios18_icons/Dark/health.png": "1dd474050d005972a7b1749407e950ad173894503ba9b7671fdcf3b7a9c67ef6",
    "files/ios18_icons/Dark/home.png": "1923ca1fce463dd042b551c7b0285585cf417441fb45e9aec48f2a6bde038d92",
    "files/ios18_icons/Dark/icloud.png": "142611adec28808dbaca00bae329c76ff2d7a9545fc77ea643dd82957eeb5d9b",
    "files/ios18_icons/Dark/image-playground.png": "051bea51fe7b1e7fb728cf4aa14ce0d450e430680f8f08b5633fc2145a443b67",
    "files/ios18_icons/Dark/imovie.png": "7470016d54d2ce27aee95c7c9b6979915c01c7838b3fcbecbd16da2c06a81476",
    "files/ios18_icons/Dark/infinity.png": "bb65b87644616c01afda878ec52afb84aa7f50a4baf35345cc35cccb8721d4e3",
    "files/ios18_icons/Dark/ios-18.png": "a0e11c5f130cb3313dd29afa91a994cbff48739c6f782493072d62f001b6e2be",
    "files/ios18_icons/Dark/journal.png": "7afd9c7bcb07df043b5f52dc31965cf710bff6dff11b34127e094d965830a73c",
    "files/ios18_icons/Dark/keynote.png": "efc9a528347aba93822ae0b5ba5338d8ac4670dabb5f414a44ecc3f7f0c6b3bd",
    "files/ios18_icons/Dark/magnifier.png": "3438ecddbcd287e3db482b199a16a20343ed60a9353fdfe02605c1833e617f30",
    "files/ios18_icons/Dark/mail.png": "1f8698adec538d6e238f6fe78f790c604620f3775914d61d89a69059d479fcbb",
    "files/ios18_icons/Dark/maps-navigation.png": "9812f360a03342c90713e85cc3e5a637d1d21f4b4df77acef26cc717fdf88e76",
    "files/ios18_icons/Dark/maps.png": "074a7e04d2943c2d92f422a0e0f8fdd3779a0caac0a88eb0761a4dfe2f2ee36e",
    "files/ios18_icons/Dark/measure.png": "e67ad2e84e0a6f6402552ed726bc4988df1940c158b98897b3df52211463a58a",
    "files/ios18_icons/Dark/messages.png": "f606175466517aff50ba563d62b0ede40dd8f86bd7e0959690411fb1f713ba3d",
    "files/ios18_icons/Dark/music-classical.png": "ccfa5d8c4f8348008f5a78c80406394de86a17e5275755e14e8790e650f3f558",
    "files/ios18_icons/Dark/music.png": "8d0593d7b80559be90fd67142164c9ae932c88196be5e0881e9f77d91d1e2350",
    "files/ios18_icons/Dark/news.png": "6763bb8e725ef1df24dfde75666583183f53c398d0dec60f89bc7f640d674046",
    "files/ios18_icons/Dark/notes.png": "13759bf52a355a5794bf61e3d085c4a443b1275a257b3d131d0c5d850194870c",
    "files/ios18_icons/Dark/numbers.png": "47ccd18b7a51b9d7bf1618834afca98a2fcb1248c2a935a54f1b42c584fd0ed1",
    "files/ios18_icons/Dark/pages.png": "887356780cbc5c1c8a512c2d3f5a2ba3fc8c451d29b2fbfa1a9f81fc403ab12c",
    "files/ios18_icons/Dark/passwords.png": "2c3a4591ac535228d5069cb89de8fe5d403272d45f6075c4b9c4957af17b4949",
    "files/ios18_icons/Dark/phone.png": "e47b10acc67e96d1cbbe5f03cb98af088d765a706760b8755a6fac585daf1d88",
    "files/ios18_icons/Dark/photos.png": "aa8ce7f31c162bd4cb922176d4c2cafa8d66b7700a0602fdf97a24c73663558f",
    "files/ios18_icons/Dark/podcasts.png": "1274aa35a6d5b509f40590c839598ee0f70bb1849892d3f1eee0cc00092d841b",
    "files/ios18_icons/Dark/reminders.png": "3b9bea68c42f7e8896008347b8c1bcdead3db3d38f1b54f52b422c4003a448c6",
    "files/ios18_icons/Dark/safari.png": "5b710c514fefe25583b33fcfe5ac760edf729230b442391625a3041f5fc76d47",
    "files/ios18_icons/Dark/screen-time-widget.png": "b257a5b7b15f7045fee4dc4e1eb0ab933ab12c9edea597b5f909fb095c489643",
    "files/ios18_icons/Dark/screen-time.png": "2d4af47e127adfe211293362e5a5051716ab324e36c4366e739d82cce6b37277",
    "files/ios18_icons/Dark/settings.png": "d67b6929faca27425ea9db0eadf4e0bc9d4dfc7a9d5ff9a8bda7f21a3b16f48b",
    "files/ios18_icons/Dark/shazam.png": "2c44d85c47d7db417bda4b65eca43c855399420ab7b432d1cca1e86497c7ec8e",
    "files/ios18_icons/Dark/shortcuts.png": "93a199042ec710533b8aa9054919aada62929b7ffcf0c69b6167707fd2130d60",
    "files/ios18_icons/Dark/sleep.png": "9feb294f8ad7bdf7b991d5acba1e5449148967370f8f7e95d42d918ada3dd1c2",
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
    "files/ios18_icons/Light/apple-account.png": "b7b5528cd2e7068d945a339c049ac304317ced06fb76ecbdc0c0351f30df3f26",
    "files/ios18_icons/Light/apple-sports.png": "81d10ec2efc8cfbb7af80e4d545fb281830141a0006041bad040bac8be832003",
    "files/ios18_icons/Light/apple-store.png": "c1e52f7c61493b299797a9ec3241a616c7c3295a514a785be667db52e60e0c19",
    "files/ios18_icons/Light/apple-tv-remote.png": "e6f5e59ef13b56b3e2abc20594fd1482aa22a50aed7078c1d4b1ec9edc415b2c",
    "files/ios18_icons/Light/battery.png": "00593ded7c2bd7f5cc946e5a0949e14be492e6459410482274209979732f0a74",
    "files/ios18_icons/Light/blank.png": "c4eed5b0f815681420a0b07e1a3c270485b15cfc75c16c9bd37d27d2b157ccf9",
    "files/ios18_icons/Light/bloom.png": "0fa6b0f0b8c4becfedb5534af87ebf54391c68bac15e2272545392239a680404",
    "files/ios18_icons/Light/books.png": "788ddc36892d0c4507f9d7f76d8f0d7b1df3349a9f7c84206a4299aed6f68201",
    "files/ios18_icons/Light/calculator.png": "8ec311c3c1e64a435f1d7c9394b98e3e71bcea86f667021d6b1a24bb10a8bb46",
    "files/ios18_icons/Light/calendar.png": "9164ff64b6c5ca5f938a20ed850af064823224f1d177b2088a433babd031df97",
    "files/ios18_icons/Light/camera.png": "0aefe4a166a4fdb7548bc1ec7a871c31a617f46e68c4c50f4bbecaaa3779fd29",
    "files/ios18_icons/Light/clips.png": "a0a6643b5d3a9e105659c0ae1928f46ef33db70b5bb3ac6785e877afa644ed9c",
    "files/ios18_icons/Light/clock.png": "dad4c388fbc74430c2da6c38e0dcdc3c5ca76808b588550d8893aef148f8edb5",
    "files/ios18_icons/Light/compass.png": "bc468cebe201fcaf70340372d13bb1b0092cf71313157e1d449c8d75c11315b5",
    "files/ios18_icons/Light/contacts.png": "3b0ab82a363fbacb05eaa1ced54cd8f0176001f8f3e18769fe474026f27de5d1",
    "files/ios18_icons/Light/facetime.png": "b69b40b623a06efc990b5f433cd9d222529cfce30ac0f2376af9719c3d30410a",
    "files/ios18_icons/Light/feedback.png": "3f60ccfcd03f32d6d55df889fde2231cd53bdae328ed13960622a596fad3781a",
    "files/ios18_icons/Light/files.png": "849e0cd8c26f7183dbab3427866c90320128467e6b86d928e55bbb744be54c93",
    "files/ios18_icons/Light/final-cut-camera.png": "d49d656cab1af884c549e8d131764bffbfb2398e3f7d95633bad1ef9dc4bcd81",
    "files/ios18_icons/Light/find-my.png": "29b50354b6d60dc2e750ddb6595c882d67590675001aeb69ce96e68c79a4fff3",
    "files/ios18_icons/Light/fitness.png": "a1890ee05bdb8ef1271574e1ab8c5b4ee41232e720bcc62358dbc09f16191fd1",
    "files/ios18_icons/Light/freeform.png": "32434e34e49cb10f0dbee4029e0a8bb37ce94cd9221d9b9d4b3333957716f8fa",
    "files/ios18_icons/Light/game-center.png": "47d7be099f180ee1af265c6c9818af29648fedac0d26f787199519128058fb6d",
    "files/ios18_icons/Light/garageband.png": "495ad201144f699fbaa347570e0758461dff72d7b7641579a3529a00b22da12a",
    "files/ios18_icons/Light/health.png": "d055305a7843d3401108b5dce7d5dcfdf4239e4fbdf5da55f284f9803c7f8dbe",
    "files/ios18_icons/Light/home.png": "3e5aa4f562dfa89a9b07d6d04509ff974e28f5ed467f15385d53bf517d53ffd7",
    "files/ios18_icons/Light/icloud.png": "5e4bb578ace137641d74e212d66483eaff0e80989f1b8bd7571dcce1325ca59e",
    "files/ios18_icons/Light/image-playground.png": "051bea51fe7b1e7fb728cf4aa14ce0d450e430680f8f08b5633fc2145a443b67",
    "files/ios18_icons/Light/imovie.png": "2c05cb46f395cf45e83ae8cdeca57a04e6d33b6212bf5a3aff13acea27fa4b9e",
    "files/ios18_icons/Light/infinity.png": "3fe06338d1f9b1bc28f289e5b1ed3902d4fcaa71635c0432fa054a7d446d692d",
    "files/ios18_icons/Light/ios-18.png": "a0e11c5f130cb3313dd29afa91a994cbff48739c6f782493072d62f001b6e2be",
    "files/ios18_icons/Light/journal.png": "490b44ab1cf2f14e922343ecc58413e8421d2222dabb9a6809bd2e0e458622e5",
    "files/ios18_icons/Light/keynote.png": "bee897592823d8314e8f9477dee550d07c069c597909d232e3c6ef1ae9e30280",
    "files/ios18_icons/Light/magnifier.png": "3438ecddbcd287e3db482b199a16a20343ed60a9353fdfe02605c1833e617f30",
    "files/ios18_icons/Light/mail.png": "ecb9ffdb25d8c2a4a72fbd7842a005dcb70256d8815362eb7091b57c19b884e5",
    "files/ios18_icons/Light/maps-navigation.png": "d1d20c46a349e982aa051b5eceebc418f3361792f6d2307764ef69155c655f11",
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
    "files/ios18_icons/Light/screen-time-widget.png": "05b2ecb4566ccf41a82628e4d82cf3a50377a15784ff9309fe306da2788f0c00",
    "files/ios18_icons/Light/screen-time.png": "3229b8c58b5d9039edbd32da3d291bf437e93c7a8b2405b849f07a615aa9f0b7",
    "files/ios18_icons/Light/settings.png": "ae4f659cce86c980a2d1e753e1c45855478d599375f209349f3a02121b7c48a8",
    "files/ios18_icons/Light/shazam.png": "59d7dad3dcfad5155b81691f90207887bdf163aded61b4532ee735124a43d2d2",
    "files/ios18_icons/Light/shortcuts.png": "93a199042ec710533b8aa9054919aada62929b7ffcf0c69b6167707fd2130d60",
    "files/ios18_icons/Light/sleep.png": "dc7932786aa4c80968ec9d4f58367fc51d5203f55494f0fd84b56e50e0ebb6df",
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
    "files/ios18_icons/Tinted/app-store.png": "e636a40ecd108c356737d438e3bcfe8fc341a7806978c8e15390c073ddbb4673",
    "files/ios18_icons/Tinted/apple-account.png": "75f05e42b7b66e6121f177ecfac5a6b007d479d39adcb6381ff6d302764ace15",
    "files/ios18_icons/Tinted/apple-sports.png": "7b06858a63a9725862491c5dee2dd28572b618e2df9532a243cdfd063959db2c",
    "files/ios18_icons/Tinted/apple-store.png": "0154d3f9da6e33a154b8d1bc3ffbd5d01d5d5ada6e2ab7ceb4830dd03a8f04c0",
    "files/ios18_icons/Tinted/apple-tv-remote.png": "5096834ed03cb57a076ce0a149fea287c7a36759e923ca9974f5cf27d8a6409f",
    "files/ios18_icons/Tinted/battery.png": "3c6c594cd7fa7de5ced1793381e613911dfd1585a9242200101bbf900e75c8a6",
    "files/ios18_icons/Tinted/blank.png": "3f3aca92d16211097b0c32d925d7979a285530b0c6530e6c71bfbdb771a9cfaa",
    "files/ios18_icons/Tinted/bloom.png": "63ac7b5e41cf74c7593309a6612818bf69eeb88b638234cc9c043633aa7f50c9",
    "files/ios18_icons/Tinted/books.png": "8eb10aac7b53c712ae68b8b645a84ae3ccd375ac4395e2d94d6b118bb58d929b",
    "files/ios18_icons/Tinted/calculator.png": "9a384930f812f0bf7125b2780f67789892ce4a71d666ff64e72ae2e491c85e38",
    "files/ios18_icons/Tinted/calendar.png": "8e35b1c3a500adfd167c192d6f323e825e484b5c98e3232ac4af6974d142cd0c",
    "files/ios18_icons/Tinted/camera.png": "b84aa521ce8bc81347481453dd1c04cdc3b7cf4a3075a3fe993d70abd5c44263",
    "files/ios18_icons/Tinted/clips.png": "c8693ce3c273f69750c9502a795c6687d936b56e696b0b67d29055640bd09e83",
    "files/ios18_icons/Tinted/clock.png": "d9180a2aba725a10c38dd677f97883a2361de64861f3030c23922d479682a2b1",
    "files/ios18_icons/Tinted/compass.png": "6a44787373dd05ed2218382b56cf73de0da831870561550e6af41fc2018b717b",
    "files/ios18_icons/Tinted/contacts.png": "7067d43b1f78410a5831bfa30185e5ed1cc20acc3d9198d761320a48bfc06639",
    "files/ios18_icons/Tinted/facetime.png": "9b63db6dd8a25751381d4edf648a12e2d678d1368c7cc6babd90a50bcc547bb3",
    "files/ios18_icons/Tinted/feedback.png": "4bf161b4804d08afcda0d414a195e611031f3b6ce99ad14a5229131b513faa09",
    "files/ios18_icons/Tinted/files.png": "1450da1cd7953d0531cedf980f240770f1ce78e20351d6e6b6664a5608a974ad",
    "files/ios18_icons/Tinted/final-cut-camera.png": "d602fe152213e14427a4ca88444f9da3a8c30ce182e3392e09dac97b1785e471",
    "files/ios18_icons/Tinted/find-my.png": "ce8d27c1fc8ca0d3817b84017a0bc49e153567327a0eb4eaab6f0f2ef2fcd5b3",
    "files/ios18_icons/Tinted/fitness.png": "c3124fa734de69b919bd1c58b729742862a489e1934b25fb9cf810b98d4575c3",
    "files/ios18_icons/Tinted/freeform.png": "bccce0c8680db8f08f9dabf89f104e74b26d1041a2257b29c289621030387148",
    "files/ios18_icons/Tinted/game-center.png": "704a1dc027af9d40273dfa576ef2130c740d3c01beb16951412d83aa3766edad",
    "files/ios18_icons/Tinted/garageband.png": "9f82319bbf524c27f5d3174ad486a4e394932f53cc6deba08924dfdb821c1fd3",
    "files/ios18_icons/Tinted/health.png": "09b11baa2d9cc30ba38a8601dd2b728f203b79fe58e45007e60cbaf612586110",
    "files/ios18_icons/Tinted/home.png": "981f8bbd731caa518796f2556548ccc49fc169b85846bb48e3aca8fd9b9e1630",
    "files/ios18_icons/Tinted/icloud.png": "104b4a6bfce7d04dc708850fd85f8a0dee313055cf05b17a03679956b1322ebe",
    "files/ios18_icons/Tinted/image-playground.png": "1d0b01934641402d5b35a6e3a6af13a07d459b26e40d30b773afad60906e365e",
    "files/ios18_icons/Tinted/imovie.png": "8e82a19525feb04c17626938600dba2ea9a3e9ad44002d417531cf316c72fbfe",
    "files/ios18_icons/Tinted/infinity.png": "f5c5bc0aa0295e57894a8abae9a3d30a4554c269ff3341cda837d0e435c42d83",
    "files/ios18_icons/Tinted/journal.png": "0a4ce873c97c0b1b528e52a58bfa6c1ed499142e98d293e9e2e5784642b90aef",
    "files/ios18_icons/Tinted/keynote.png": "d17f2725d1e481f1c09c188d219fe230e9a0bf0b575faa616f43b66063017084",
    "files/ios18_icons/Tinted/magnifier.png": "1af6425be028098195ec6bc6553e69747a2463c34d8b87ec99b9a6d024ae1ed4",
    "files/ios18_icons/Tinted/mail.png": "93bf4e83a9b6f3c99dbbd785a245a0d8a14b5b52fa7ab40ffaec915628f39b74",
    "files/ios18_icons/Tinted/maps-navigation.png": "8cc028b7c89baeb0a9ee5ed186c799a8058542ebfe42d95493d91da0e82a72e9",
    "files/ios18_icons/Tinted/maps.png": "6680f5cf446879ae0fc72acaf29b77573cb3134ab88c761d57f95468a3680ed9",
    "files/ios18_icons/Tinted/measure.png": "ad6f4e7a71296bbf1807695262d13cc44c65985d8e60ba6815f63269419dd137",
    "files/ios18_icons/Tinted/messages.png": "28458f658b482e93019daa4a09d4b6599ec6c06e3800e5e8dbbcb6928a400555",
    "files/ios18_icons/Tinted/music-classical.png": "ffbb5b638b51426ff841f6a1be3123fc268e5d0e1255549ed78d033d0c4e4552",
    "files/ios18_icons/Tinted/music.png": "f37e4f5dd519b2326939f0a5b536bddf33f674a6421de176c7b7f65b2d54fa35",
    "files/ios18_icons/Tinted/news.png": "9c5b12c117c100cd7f62a29d63cf69d966e5267dbf53e55f3f567faed9c7ba99",
    "files/ios18_icons/Tinted/notes.png": "8a7e6343f8b31ff89f396f430e074ebd3fd986c3d63da9049637ac6b1905b97e",
    "files/ios18_icons/Tinted/numbers.png": "d5c8dea6c07921f0c8b74a57c2ebf61b88ea3b69701b6a1006028be2a50e42b4",
    "files/ios18_icons/Tinted/pages.png": "d71f3e26a6defbedd5089f93b63986eae61d1d3aa5e2275d0bc66ea071caf22d",
    "files/ios18_icons/Tinted/passwords.png": "c397b021f4ca4931cd0b05f040ba7cb30ba9c51519b9ef3151cd67d1a71dfd7d",
    "files/ios18_icons/Tinted/phone.png": "fa22bfcfc6fd6d06c5c3bae0ca9fd55644cbf31ab321591d7532d086ce5b804b",
    "files/ios18_icons/Tinted/photos.png": "e68e6601cb06404979132e814e8d131a467f296d36fafb5e38d377f8a28e1613",
    "files/ios18_icons/Tinted/podcasts.png": "f8798e303a91967130352d9b362df96e460e68b0639768bba9a69fc2d299a4ed",
    "files/ios18_icons/Tinted/reminders.png": "5a5458e10e45dbc6713a1b7873588b32b14a40970f5bae8dbbfbf503070fe23f",
    "files/ios18_icons/Tinted/safari.png": "ddfa979fd9510ba8fd901f5c6154b85a949b9f03da2d773af24690f6d8cdc439",
    "files/ios18_icons/Tinted/screen-time-widget.png": "b9672a8b73be6a8e319902af72cec699de8fbb09b7701cbb8da41197a82126c1",
    "files/ios18_icons/Tinted/screen-time.png": "4f13a9c48adb67e9506e9d5415eadbd2aa09642500567d00c12d763e9540789a",
    "files/ios18_icons/Tinted/settings.png": "bb138c3911aed4badd68da194922398f52f15f4965a18c971aad0567a88ada29",
    "files/ios18_icons/Tinted/shazam.png": "10c436f32247ef2be7b1c4f49b97cbf83f1b7f6b3d263ece5acbfc0296e75272",
    "files/ios18_icons/Tinted/shortcuts.png": "2dbcc225111fec0337bb6693b3e07bbc3ede84d63ac1a169e50cfdd7ecf3e699",
    "files/ios18_icons/Tinted/sleep.png": "c2ba8b902c430d3910a73a5765275839cd0911793c3577543080a363bb833119",
    "files/ios18_icons/Tinted/stocks.png": "b3da15f1903bcb45a72d425ac54933f48426a09b4c77892094f1baf3fb7eda8e",
    "files/ios18_icons/Tinted/swift-playgrounds.png": "392a902f9074aa10115a5895a8614371ae3b27c474a29046330536ca766c8f4e",
    "files/ios18_icons/Tinted/testflight.png": "46896b864a5c5d89edd2776dbbe73a0550164c224d67ddb720509314cc971462",
    "files/ios18_icons/Tinted/tips.png": "85250fc9271610bb7ab2c7ddfbccb297e8289217d424006ddf986c3f6df04cab",
    "files/ios18_icons/Tinted/translate.png": "2576094e9964e93bd7aa6d1f954da7c91c2505c527ae7ef4f671d072c5200ef3",
    "files/ios18_icons/Tinted/tv.png": "8b682961994366cd864695a71afb62db5ffbcd7ca44b2837d4f8115f65194d0a",
    "files/ios18_icons/Tinted/voice-memos.png": "0fc6325231072ba4eb5ffec109a5bd1ae6b83b2eaec23e9fa8336239ee5575ed",
    "files/ios18_icons/Tinted/wallet.png": "708ed3a39c0df6c3de4659bc4cc2faf3ac65afea846c9778295f7736ca4a8388",
    "files/ios18_icons/Tinted/watch.png": "5188d75d4f0529832b16c4afd6561c1415b6891e98dfe3003a3bfa9c1b08a9c7",
    "files/ios18_icons/Tinted/weather.png": "459d3ef4b42e6f6d8bd2c3d5c0fa75d4689ef70c3b8cab30d1e7a751ca40a5ae",
    "src/gui/dialogs/icon_pack_downloader.py": "0406c608892b97e3c21161e2617283d763aa09cab70d218c879f85e895d5acc8",
    "src/gui/ios/icon_themes.py": "76e4e36c3450244b6e2ebb7c4f071e3668d350210c5fbcccb625774ec419aee5",
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
