import json

import yaml

from sbtest.browser.profile import Profile, expand_dotted
from sbtest.browser.version import parse_chromium_version
from sbtest.config import load_config
from sbtest.data import BookmarksSeed, Bm, Folder, files
from sbtest.data.loader import format_data


def test_config_layers(tmp_path, monkeypatch):
    (tmp_path / "default.yaml").write_text(yaml.safe_dump({"browser": {"exe": "", "headless": False},
                                                           "pages": {"scheme": "chrome", "history": "history"}}))
    (tmp_path / "local.yaml").write_text(yaml.safe_dump({"browser": {"exe": "C:/a.exe"}}))
    monkeypatch.setenv("SB_HEADLESS", "true")
    cfg = load_config({"browser.mode": "attach"}, config_dir=tmp_path)
    assert cfg.get("browser.exe") == "C:/a.exe"
    assert cfg.get("browser.headless") is True
    assert cfg.get("browser.mode") == "attach"
    assert cfg.page_url("history") == "chrome://history"
    assert cfg.page_url("internet://x") == "internet://x"


def test_parse_version():
    ua = "Mozilla/5.0 (Windows NT 10.0) AppleWebKit/537.36 Chrome/141.0.7390.37 SamsungBrowser/29.0 Safari/537.36"
    assert parse_chromium_version("SamsungInternet/29.0.1.2", ua) == "141.0.7390.37"
    assert parse_chromium_version("HeadlessChrome/120.0.1.2") == "120.0.1.2"
    assert parse_chromium_version("nothing") is None


def test_chromium_version_when_browser_field_holds_the_product_version():
    from sbtest.browser.version import chromium_version_from

    ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
          "SamsungBrowser/31.0 Chrome/{} Safari/537.36")
    # Samsung 31.0.0.55: Browser holds the full Chromium version, the UA a reduced one
    assert chromium_version_from({"Browser": "Chrome/148.0.7778.217",
                                  "User-Agent": ua.format("148.0.0.0")}) == "148.0.7778.217"
    # a Samsung 31.0.2 build on Chromium 157: Browser holds the product version
    assert chromium_version_from({"Browser": "Chrome/31.0.1.21",
                                  "User-Agent": ua.format("157.0.0.0")}) == "157.0.0.0"
    assert chromium_version_from({"Browser": "", "User-Agent": ua.format("157.0.0.0")}) == "157.0.0.0"


def test_download_uses_curl_then_urllib(monkeypatch):
    from sbtest.browser import driver_resolver as dr

    calls = []
    monkeypatch.setattr(dr, "curl_exe", lambda: "curl.exe")
    monkeypatch.setattr(dr, "_curl", lambda c, url, t: calls.append(("curl", url)) or b"zip")
    assert dr.fetch("https://x/a.zip") == b"zip" and calls == [("curl", "https://x/a.zip")]

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b"from urllib"

    def broken(*a):
        raise RuntimeError("curl exit 35")
    monkeypatch.setattr(dr, "_curl", broken)
    monkeypatch.setattr(dr, "_open", lambda url, t: Resp())
    assert dr.fetch("https://x/a.zip") == b"from urllib"
    monkeypatch.setattr(dr, "curl_exe", lambda: None)
    assert dr.fetch("https://x/a.zip") == b"from urllib"


def test_driver_major_checked_against_chromium(tmp_path, monkeypatch):
    import pytest

    from sbtest.browser import driver_resolver as dr

    local = tmp_path / "157" / dr.EXE_NAME
    local.parent.mkdir()
    local.write_text("")
    monkeypatch.setattr(dr, "driver_version", lambda p: "148.0.7778.97")
    with pytest.raises(RuntimeError, match="version 148.*Chromium 157.*chromedriver 157"):
        dr.resolve_chromedriver("", "157.0.0.0", drivers_dir=tmp_path)
    assert dr.resolve_chromedriver(str(local), "157.0.0.0") == str(local)   # configured: warning only
    monkeypatch.setattr(dr, "driver_version", lambda p: "157.0.7900.2")
    assert dr.resolve_chromedriver("", "157.0.0.0", drivers_dir=tmp_path) == str(local)


def test_bookmarks_seed_ids_unique():
    seed = BookmarksSeed().url("A", "http://a").folder("F", [Bm("B", "http://b"), Folder("E")])
    data = seed.to_json()
    ids = []

    def walk(n):
        ids.append(n["id"])
        for c in n.get("children", []):
            walk(c)

    for root in data["roots"].values():
        walk(root)
    assert len(ids) == len(set(ids))
    assert data["roots"]["bookmark_bar"]["children"][1]["children"][0]["url"] == "http://b"


def test_seed_from_dict_and_format():
    raw = {"bookmark_bar": [{"name": "A", "url": "{site}/a"}, {"name": "F", "children": [{"name": "B", "url": "{site}/b"}]}]}
    seed = BookmarksSeed.from_dict(format_data(raw, {"site": "http://h:1"}))
    j = seed.to_json()["roots"]["bookmark_bar"]["children"]
    assert j[0]["url"] == "http://h:1/a" and j[1]["children"][0]["url"] == "http://h:1/b"


def test_profile_prefs_merge(tmp_path):
    p = Profile(tmp_path, "t")
    p.prefs({"download.prompt_for_download": True}).prefs({"download.default_directory": "x"})
    prefs = json.loads((p.default / "Preferences").read_text())
    assert prefs["download"] == {"prompt_for_download": True, "default_directory": "x"}
    assert (p.dir / "First Run").exists()
    assert expand_dotted({"a.b.c": 1}) == {"a": {"b": {"c": 1}}}


def test_png_is_valid(tmp_path):
    f = files.png_file(tmp_path)
    assert f.read_bytes().startswith(b"\x89PNG")


def test_local_yaml_layers(tmp_path, monkeypatch):
    monkeypatch.delenv("SB_EXE", raising=False)
    (tmp_path / "default.yaml").write_text(yaml.safe_dump(
        {"pages": {"scheme": "chrome", "display_scheme": "internet", "history": "history"}, "browser": {"exe": ""}}))
    (tmp_path / "local.yaml").write_text(yaml.safe_dump({"browser": {"exe": "a.exe"}}))
    assert load_config(config_dir=tmp_path).get("browser.exe") == "a.exe"
    # older layout: targets.samsung section still applies
    (tmp_path / "local.yaml").write_text(yaml.safe_dump({"targets": {"samsung": {"browser": {"exe": "s.exe"}}}}))
    assert load_config(config_dir=tmp_path).get("browser.exe") == "s.exe"
    assert load_config({"browser.exe": "cli.exe"}, config_dir=tmp_path).get("browser.exe") == "cli.exe"


def test_pages_factory():
    from types import SimpleNamespace

    from sbtest.pages import ExtensionsPage, Pages
    web = SimpleNamespace(cfg=SimpleNamespace(get=lambda k, d=None: d))
    assert isinstance(Pages(web).extensions, ExtensionsPage)


def test_display_url_vs_navigation_url(tmp_path):
    (tmp_path / "default.yaml").write_text(yaml.safe_dump(
        {"pages": {"scheme": "chrome", "display_scheme": "internet", "history": "history"}}))
    cfg = load_config(config_dir=tmp_path)
    assert (cfg.page_url("history"), cfg.display_url("history")) == ("chrome://history", "internet://history")


def test_setup_saves_the_exe_keeping_local_yaml(tmp_path):
    import yaml

    from sbtest.tools.setup import save_exe

    example = tmp_path / "local.example.yaml"
    example.write_text("# comment kept\nbrowser:\n  exe: 'C:/build/SamsungInternet.exe'\n  # chromedriver: x\n"
                       "network:\n  # download_proxy: y\n", encoding="utf-8")
    local = tmp_path / "local.yaml"
    save_exe(r"D:\sb\SamsungInternet.exe", local)          # new file: starts from the example
    text = local.read_text(encoding="utf-8")
    assert "# comment kept" in text and "# chromedriver: x" in text
    assert yaml.safe_load(text)["browser"]["exe"] == r"D:\sb\SamsungInternet.exe"
    save_exe(r"E:\new\SamsungInternet.exe", local)         # existing file: only that line changes
    assert yaml.safe_load(local.read_text(encoding="utf-8"))["browser"]["exe"] == r"E:\new\SamsungInternet.exe"
    assert local.read_text(encoding="utf-8").count("exe:") == 1

    other = tmp_path / "other" / "local.yaml"
    other.parent.mkdir()
    other.write_text("network:\n  browser_proxy: http://p:8080\n", encoding="utf-8")
    save_exe(r"C:\x\SamsungInternet.exe", other)           # no browser: section -> appended
    data = yaml.safe_load(other.read_text(encoding="utf-8"))
    assert data == {"network": {"browser_proxy": "http://p:8080"}, "browser": {"exe": r"C:\x\SamsungInternet.exe"}}


def test_profiles_leave_a_deep_repo_folder(tmp_path):
    from pathlib import Path

    from sbtest.browser.profile import MAX_PROFILE_DIR, SHORT_ROOT, profiles_root

    short = Path("C:/sbtest/artifacts/test-results/profiles")
    assert profiles_root(short) == short                     # usual repo folders keep them
    deep = Path("C:/" + "deep/" * 30) / "artifacts" / "test-results" / "profiles"
    assert profiles_root(deep) == SHORT_ROOT                 # past the 260-character limit otherwise
    assert len(str(SHORT_ROOT)) + 38 <= MAX_PROFILE_DIR


def test_native_ui_map_uses_stable_criteria():
    """Views number their AutomationIds in creation order (``view_1023``): they change between
    builds, so the ui map must not use them. Each entry names a class, an id, or a control
    type plus its title - a title alone matches too much."""
    import re

    import yaml

    from sbtest.config import ROOT

    ONE_PER_WINDOW = {"Tab"}   # the frame has one tab strip
    ui = yaml.safe_load((ROOT / "config" / "native_ui.yaml").read_text(encoding="utf-8"))
    for key, crit in ui.items():
        if key in ("dialogs", "startup_bubbles") or not isinstance(crit, dict):
            continue
        assert not re.fullmatch(r"view_\d+", str(crit.get("auto_id", ""))), f"{key}: auto_id view_N changes per build"
        stable = {"class_name", "class_name_re", "auto_id"} & set(crit) or (
            "control_type" in crit and {"title", "title_re"} & set(crit)) or (
            crit.get("control_type") in ONE_PER_WINDOW and len(crit) == 1)
        assert stable, f"{key}: add class_name, auto_id or control_type + title ({crit})"


def test_devtools_port_file_read_while_the_browser_writes_it(tmp_path, monkeypatch):
    from pathlib import Path

    from sbtest.browser import version

    port_file = tmp_path / "DevToolsActivePort"
    port_file.write_text("51234\n/devtools/browser/x\n")
    real, calls = Path.read_text, []

    def locked_once(self, *a, **k):   # the browser holds the file on the first read
        calls.append(1)
        if len(calls) == 1:
            raise PermissionError(13, "Permission denied")
        return real(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", locked_once)
    monkeypatch.setattr(version.time, "sleep", lambda s: None)
    assert version.wait_devtools_port(tmp_path, timeout=5) == 51234 and len(calls) == 2
