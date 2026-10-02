#!/usr/bin/env python3
"""Offline tests for the Wave 10 update checker (mocked GitHub API).

Pins buildspec R6 §4: channel selection (stable excludes prereleases —
including tags that parse as prereleases when GitHub's flag is wrong),
exact-one-``v`` tag stripping, invalid-tag accounting, the build rule,
error taxonomy (``unknown`` never becomes an update), per-channel
caching, and the dialog's exact ``html_url`` contract.

Run: python tools/test_update_checker.py
(GUI dialog check needs PySide6; it skips cleanly without it.)
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

PASS = 0


def check(name, cond, extra=""):
    global PASS
    assert cond, f"FAILED: {name} {extra}"
    PASS += 1
    print(f"  ok: {name}" + (f"  [{extra}]" if extra else ""))


import requests  # noqa: E402

import src.controllers.web_request_handler as wrh  # noqa: E402


class FakeResponse:
    def __init__(self, payload=None, status=200, headers=None, bad_json=False):
        self._payload = payload
        self.status_code = status
        self.headers = headers or {}
        self._bad_json = bad_json

    def json(self):
        if self._bad_json:
            raise ValueError("no json")
        return self._payload


def rel(tag, prerelease=False, draft=False, published="2026-01-01T00:00:00Z",
        version_flag=None):
    return {
        "tag_name": tag,
        "name": f"Release {tag}",
        "html_url": f"https://github.com/adnan120hz/"
                    f"WorkSlop-Desktop-Version/releases/tag/{tag}",
        "prerelease": prerelease if version_flag is None else version_flag,
        "draft": draft,
        "published_at": published,
        "assets": [],
    }


class Fetcher:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = 0

    def __call__(self, url, params=None, headers=None, timeout=None):
        self.calls += 1
        item = self.responses[min(self.calls - 1, len(self.responses) - 1)]
        if isinstance(item, Exception):
            raise item
        return item


def run(fetcher, *args, **kwargs):
    wrh._release_cache.clear()
    wrh.requests.get = fetcher
    return wrh.check_for_update(*args, **kwargs)


def test_channels():
    print("\nchannel selection")
    payload = [rel("v10.0-pre", prerelease=True,
                   published="2026-09-01T00:00:00Z"),
               rel("v9.0", published="2026-08-01T00:00:00Z")]
    r = run(Fetcher(FakeResponse(payload)), "4.0", 0, "stable")
    check("stable picks final over prerelease",
          r.latest and r.latest.tag_name == "v9.0", str(r.latest))
    check("stable: 9.0 > 4.0 is an update", r.outcome == "update_available")
    r = run(Fetcher(FakeResponse(payload)), "4.0", 0, "beta")
    check("beta picks highest incl. prerelease",
          r.latest and r.latest.tag_name == "v10.0-pre")
    check("beta result carries html_url",
          r.latest.html_url.endswith("/v10.0-pre"))
    check("beta result flagged prerelease", r.latest.prerelease is True)


def test_version_compare():
    print("\nversion comparison")
    r = run(Fetcher(FakeResponse([rel("v10.0")])), "4.0", 0, "stable")
    check("4.0 -> 10.0 update", r.outcome == "update_available")
    r = run(Fetcher(FakeResponse([rel("v10.0")])), "10.0", 0, "stable")
    check("10.0 == 10.0 up to date", r.outcome == "up_to_date")
    r = run(Fetcher(FakeResponse([rel("v9.0")])), "10.0", 0, "stable")
    check("older release not an update", r.outcome == "up_to_date")


def test_build_rule():
    print("\nbuild rule")
    r = run(Fetcher(FakeResponse([rel("v10.0")])), "10.0", 3, "beta")
    check("build>0 + same final version -> update",
          r.outcome == "update_available")
    r = run(Fetcher(FakeResponse([rel("v10.0-pre", prerelease=True)])),
            "10.0", 3, "beta")
    check("build rule does not fire for prerelease",
          r.outcome == "up_to_date")


def test_tag_validation():
    print("\ntag validation")
    payload = [rel("vv10.0"), rel("version-10.0"), {"name": "no tag"},
               rel("v8.0")]
    r = run(Fetcher(FakeResponse(payload)), "4.0", 0, "stable")
    check("invalid tags skipped, valid one selected",
          r.latest and r.latest.tag_name == "v8.0")
    check("exactly one v stripped", r.latest.version == "8.0")
    r = run(Fetcher(FakeResponse([rel("vv10.0"), rel("version-10.0")])),
            "4.0", 0, "stable")
    check("all tags invalid -> up_to_date/no_valid_tags",
          r.outcome == "up_to_date" and r.error_kind == "no_valid_tags",
          str(r.error_kind))
    r = run(Fetcher(FakeResponse([])), "4.0", 0, "stable")
    check("no releases -> up_to_date/no_releases",
          r.outcome == "up_to_date" and r.error_kind == "no_releases")


def test_drafts_and_flag_lies():
    print("\ndrafts + lying prerelease flags")
    payload = [rel("v11.0", draft=True),
               rel("v10.0-rc1", version_flag=False)]  # tag says prerelease
    r = run(Fetcher(FakeResponse(payload)), "4.0", 0, "stable")
    check("draft never selected; prerelease tag excluded from stable",
          r.outcome == "up_to_date" and r.error_kind == "no_releases")
    r = run(Fetcher(FakeResponse(payload)), "4.0", 0, "beta")
    check("beta still sees the prerelease tag",
          r.latest and r.latest.tag_name == "v10.0-rc1"
          and r.latest.prerelease is True)


def test_tie_break():
    print("\ntie break")
    payload = [rel("v10.0", published="2026-01-01T00:00:00Z"),
               rel("v9.0", published="2026-12-01T00:00:00Z"),
               rel("v10.0", published="2026-06-01T00:00:00Z")]
    r = run(Fetcher(FakeResponse(payload)), "4.0", 0, "stable")
    check("highest version wins over list order",
          r.latest.tag_name == "v10.0"
          and r.latest.published_at == "2026-06-01T00:00:00Z")


def test_errors():
    print("\nerror taxonomy")
    r = run(Fetcher(FakeResponse(status=404)), "4.0", 0, "stable")
    check("404 -> unknown/http_404",
          r.outcome == "unknown" and r.error_kind == "http_404")
    r = run(Fetcher(FakeResponse(status=500)), "4.0", 0, "stable")
    check("500 -> unknown/http_500",
          r.outcome == "unknown" and r.error_kind == "http_500")
    r = run(Fetcher(requests.Timeout("slow")), "4.0", 0, "stable")
    check("timeout -> unknown/timeout",
          r.outcome == "unknown" and r.error_kind == "timeout")
    r = run(Fetcher(requests.ConnectionError("down")), "4.0", 0, "stable")
    check("conn error -> unknown/network",
          r.outcome == "unknown" and r.error_kind == "network")
    r = run(Fetcher(FakeResponse(bad_json=True)), "4.0", 0, "stable")
    check("bad json -> unknown/invalid_json",
          r.outcome == "unknown" and r.error_kind == "invalid_json")
    r = run(Fetcher(FakeResponse(status=403, headers={
        "X-RateLimit-Remaining": "0"})), "4.0", 0, "stable")
    check("403 rate-limited -> unknown/rate_limited",
          r.outcome == "unknown" and r.error_kind == "rate_limited")
    f = Fetcher(FakeResponse([rel("v10.0")]))
    r = run(f, "not-a-version", 0, "stable")
    check("invalid local version -> unknown, no HTTP",
          r.outcome == "unknown"
          and r.error_kind == "local_version_invalid" and f.calls == 0)


def test_cache():
    print("\ncache")
    f = Fetcher(FakeResponse([rel("v10.0")]))
    wrh._release_cache.clear()
    wrh.requests.get = f
    wrh.check_for_update("4.0", 0, "stable")
    wrh.check_for_update("4.0", 0, "stable")
    check("second check served from cache", f.calls == 1, str(f.calls))
    wrh.check_for_update("4.0", 0, "stable", force=True)
    check("force bypasses cache", f.calls == 2)
    wrh.check_for_update("4.0", 0, "beta")
    check("cache is per-channel", f.calls == 3)
    f2 = Fetcher(FakeResponse(status=500), FakeResponse([rel("v10.0")]))
    wrh._release_cache.clear()
    wrh.requests.get = f2
    r1 = wrh.check_for_update("4.0", 0, "stable")
    r2 = wrh.check_for_update("4.0", 0, "stable")
    check("unknown is not cached",
          r1.outcome == "unknown" and r2.outcome == "update_available"
          and f2.calls == 2)


def test_wrappers_and_channels():
    print("\nwrappers + channel defaults")
    wrh._release_cache.clear()
    wrh.requests.get = Fetcher(FakeResponse([rel("v10.0")]))
    check("is_update_available wrapper", wrh.is_update_available("4.0", 0))
    check("wrapper false when current", not wrh.is_update_available("10.0", 0))
    check("default channel: release install -> stable",
          wrh.default_channel("4.0", 0) == "stable")
    check("default channel: build>0 -> beta",
          wrh.default_channel("4.0", 2) == "beta")
    check("default channel: prerelease version -> beta",
          wrh.default_channel("10.0-pre", 0) == "beta")
    check("repo constant is canonical",
          wrh.WORKSLOP_REPO == "adnan120hz/WorkSlop-Desktop-Version")
    check("deprecated alias follows canonical repo",
          wrh.Nugget_Repo.startswith("adnan120hz/WorkSlop-Desktop-Version"))


def test_dialog_html_url():
    print("\ndialog contract")
    try:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        import src.gui.dialogs.dialogs as dialogs_mod
    except Exception as e:
        print(f"  skipped: {type(e).__name__}: {e}")
        return
    app = QApplication.instance() or QApplication([])
    result = run(Fetcher(FakeResponse(
        [rel("v10.0-pre", prerelease=True)])), "4.0", 0, "beta")
    opened = []
    real_open = dialogs_mod.open_new_tab
    dialogs_mod.open_new_tab = opened.append
    try:
        dlg = dialogs_mod.UpdateAppDialog(result)
        dlg.accept()
    finally:
        dialogs_mod.open_new_tab = real_open
    check("accept opens the exact release html_url",
          opened == [result.latest.html_url], str(opened))


test_channels()
test_version_compare()
test_build_rule()
test_tag_validation()
test_drafts_and_flag_lies()
test_tie_break()
test_errors()
test_cache()
test_wrappers_and_channels()
test_dialog_html_url()

print(f"\nALL {PASS} CHECKS PASSED")
