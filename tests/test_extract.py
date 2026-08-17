"""Extractor tests.

The fixtures are shortened but syntactically faithful excerpts of real
Chromium files, including the awkward shapes that broke earlier versions of
these parsers: the two-argument BASE_FEATURE macro, preprocessor-conditional
defaults, and per-platform status dictionaries.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from chromedrift import jsonc
from chromedrift.extract import base_features, blink_runtime, constants, mojom, web_idl
from chromedrift.extract import webui_controls as web_ui
from chromedrift.extract._cpp import (
    balanced_args,
    eval_condition,
    mask_comments,
    resolve_platform_state,
    split_top_level,
)


class TestJson5(unittest.TestCase):
    def test_comments_and_trailing_commas(self):
        doc = jsonc.loads("""
        {
          // line comment
          name: 'single quoted',
          /* block */
          list: [1, 2, 3,],
          nested: { a: 1, },
        }
        """)
        self.assertEqual(doc["name"], "single quoted")
        self.assertEqual(doc["list"], [1, 2, 3])
        self.assertEqual(doc["nested"], {"a": 1})

    def test_numbers_and_literals(self):
        doc = jsonc.loads("{a: 0x10, b: -1.5e2, c: true, d: null}")
        self.assertEqual(doc["a"], 16)
        self.assertEqual(doc["b"], -150.0)
        self.assertIs(doc["c"], True)
        self.assertIsNone(doc["d"])

    def test_url_in_comment_is_not_a_comment_start(self):
        doc = jsonc.loads('{ url: "https://example.com/a//b" }')
        self.assertEqual(doc["url"], "https://example.com/a//b")

    def test_unterminated_raises(self):
        with self.assertRaises(jsonc.Json5Error):
            jsonc.loads("{a: 1")


class TestCppLexing(unittest.TestCase):
    def test_mask_preserves_offsets(self):
        src = 'int a; // comment\nint b;'
        masked = mask_comments(src)
        self.assertEqual(len(masked), len(src))
        self.assertNotIn("comment", masked)
        self.assertIn("int b;", masked)

    def test_mask_keeps_string_literals(self):
        masked = mask_comments('const char* s = "http://x//y"; // gone')
        self.assertIn('"http://x//y"', masked)
        self.assertNotIn("gone", masked)

    def test_balanced_args_skips_strings(self):
        src = 'F(a, "b)c", d)'
        inner, end = balanced_args(src, 1)
        self.assertEqual(inner, 'a, "b)c", d')
        self.assertEqual(end, len(src))

    def test_split_top_level_respects_nesting(self):
        parts = split_top_level('a, F(b, c), base::FeatureParam<int, long>, "x,y"')
        self.assertEqual(parts, ['a', 'F(b, c)', 'base::FeatureParam<int, long>', '"x,y"'])

    def test_eval_condition_three_valued(self):
        self.assertIs(eval_condition("BUILDFLAG(IS_ANDROID)", "android"), True)
        self.assertIs(eval_condition("BUILDFLAG(IS_ANDROID)", "windows"), False)
        self.assertIs(eval_condition("!BUILDFLAG(IS_ANDROID)", "windows"), True)
        self.assertIs(eval_condition("BUILDFLAG(IS_WIN) || BUILDFLAG(IS_MAC)", "mac"), True)
        # A non-platform buildflag cannot be decided here.
        self.assertIsNone(eval_condition("BUILDFLAG(ENABLE_PLUGINS)", "android"))

    def test_resolve_platform_state_picks_branch(self):
        block = """
#if BUILDFLAG(IS_WIN) || BUILDFLAG(IS_MAC)
             base::FEATURE_ENABLED_BY_DEFAULT
#else
             base::FEATURE_DISABLED_BY_DEFAULT
#endif
"""
        states = resolve_platform_state(block, base_features.STATE_RE)
        self.assertEqual(states["windows"], "FEATURE_ENABLED_BY_DEFAULT")
        self.assertEqual(states["android"], "FEATURE_DISABLED_BY_DEFAULT")


class TestBaseFeatures(unittest.TestCase):
    THREE_ARG = '''
// M139-era declaration.
BASE_FEATURE(kBackForwardCache,
             "BackForwardCache",
             base::FEATURE_ENABLED_BY_DEFAULT);
'''

    TWO_ARG = '''
// M143-era declaration: the string is derived from the variable.
BASE_FEATURE(kBackForwardCache, base::FEATURE_ENABLED_BY_DEFAULT);
'''

    def _one(self, src):
        facts = [f for f in base_features.extract(src, "p/features.cc")
                 if f.kind == "base_feature"]
        self.assertEqual(len(facts), 1, facts)
        return facts[0]

    def test_identity_survives_macro_migration(self):
        """The regression this whole design turns on.

        Between M139 and M143 the macro dropped its string argument. Keying on
        syntax makes every feature look removed and re-added.
        """
        old = self._one(self.THREE_ARG)
        new = self._one(self.TWO_ARG)
        self.assertEqual(old.key, "BackForwardCache")
        self.assertEqual(new.key, "BackForwardCache")
        self.assertEqual(old.uid, new.uid)
        self.assertEqual(old.attrs["declared_form"], "macro3")
        self.assertEqual(new.attrs["declared_form"], "macro2")

    def test_explicit_string_wins_over_derived_name(self):
        # A real M139 case: the author typed the 'k' prefix into the string.
        fact = self._one('BASE_FEATURE(kFoo, "kFoo", base::FEATURE_DISABLED_BY_DEFAULT);')
        self.assertEqual(fact.key, "kFoo")
        self.assertEqual(fact.attrs["var"], "kFoo")

    def test_legacy_brace_form(self):
        fact = self._one(
            'const base::Feature kOld{"OldFeature", '
            'base::FEATURE_DISABLED_BY_DEFAULT};')
        self.assertEqual(fact.key, "OldFeature")
        self.assertEqual(fact.attrs["declared_form"], "legacy")

    def test_platform_conditional_default(self):
        src = '''
BASE_FEATURE(kAudioServiceOutOfProcess,
#if BUILDFLAG(IS_WIN) || BUILDFLAG(IS_MAC) || BUILDFLAG(IS_LINUX)
             base::FEATURE_ENABLED_BY_DEFAULT
#else
             base::FEATURE_DISABLED_BY_DEFAULT
#endif
);
'''
        fact = self._one(src)
        self.assertEqual(fact.attrs["platform_state"]["android"], "disabled")
        self.assertEqual(fact.attrs["platform_state"]["windows"], "enabled")

    def test_feature_params(self):
        src = '''
BASE_FEATURE(kSpare, base::FEATURE_DISABLED_BY_DEFAULT);
const base::FeatureParam<int> kSpareTimeout{
    &kSpare, "timeout_seconds", 30};
'''
        params = [f for f in base_features.extract(src, "p/features.cc")
                  if f.kind == "feature_param"]
        self.assertEqual(len(params), 1)
        self.assertEqual(params[0].key, "Spare/timeout_seconds")
        self.assertEqual(params[0].attrs["default"], "30")
        self.assertEqual(params[0].attrs["feature"], "Spare")


class TestBlinkRuntime(unittest.TestCase):
    SRC = '''
{
  data: [
    { name: "SimpleStable", status: "stable" },
    { name: "PerPlatform", status: {"Android": "stable", "Win": "experimental"} },
    { name: "AndroidOnly", status: {"Android": "stable"} },
    { name: "NoStatus" },
  ],
}
'''

    def setUp(self):
        self.facts = {f.key: f for f in blink_runtime.extract(
            self.SRC, "runtime_enabled_features.json5")}

    def test_simple_status_applies_everywhere(self):
        self.assertEqual(self.facts["SimpleStable"].attrs["android_status"], "stable")

    def test_per_platform_status(self):
        attrs = self.facts["PerPlatform"].attrs
        self.assertEqual(attrs["platform_status"]["android"], "stable")
        self.assertEqual(attrs["platform_status"]["windows"], "experimental")

    def test_missing_default_means_not_enabled(self):
        """Omitting "default" means unlisted platforms are OFF.

        Easy to get backwards, and getting it backwards would report a
        feature as shipping everywhere when it ships on one platform.
        """
        attrs = self.facts["AndroidOnly"].attrs
        self.assertEqual(attrs["platform_status"]["android"], "stable")
        self.assertEqual(attrs["platform_status"]["windows"], "")

    def test_status_ranking(self):
        self.assertGreater(blink_runtime.status_rank("stable"),
                           blink_runtime.status_rank("experimental"))
        self.assertGreater(blink_runtime.status_rank("experimental"),
                           blink_runtime.status_rank("test"))
        self.assertEqual(blink_runtime.status_rank(""), 0)


class TestWebIdl(unittest.TestCase):
    SRC = '''
// A trimmed but structurally real interface.
[
    Exposed=Window,
    SecureContext
] interface Gamepad {
    readonly attribute DOMString id;
    [RuntimeEnabled=GamepadButtonAxisEvents] readonly attribute double timestamp;
    undefined vibrate(double duration, optional GamepadEffectParameters params);
    const unsigned short MAX_BUTTONS = 32;
};

partial interface Navigator {
    sequence<Gamepad?> getGamepads();
};

enum GamepadHand { "", "left", "right" };
'''

    def setUp(self):
        self.facts = web_idl.extract(self.SRC, "modules/gamepad/gamepad.idl")
        self.by_key = {f.key: f for f in self.facts}

    def test_interface_and_ext_attrs(self):
        iface = self.by_key["Gamepad"]
        self.assertEqual(iface.kind, "idl_interface")
        self.assertEqual(iface.attrs["ext"]["Exposed"], "Window")
        self.assertIs(iface.attrs["ext"]["SecureContext"], True)

    def test_members_classified(self):
        self.assertEqual(self.by_key["Gamepad.id"].attrs["member_type"], "attribute")
        self.assertEqual(self.by_key["Gamepad.vibrate"].attrs["member_type"], "operation")
        self.assertEqual(self.by_key["Gamepad.MAX_BUTTONS"].attrs["member_type"], "const")

    def test_runtime_enabled_links_to_blink_flag(self):
        member = self.by_key["Gamepad.timestamp"]
        self.assertEqual(member.attrs["runtime_enabled"], "GamepadButtonAxisEvents")

    def test_partial_members_attach_to_base_interface(self):
        self.assertIn("Navigator.getGamepads", self.by_key)
        # A partial does not redeclare the interface itself.
        self.assertNotIn("Navigator", self.by_key)

    def test_enum_values_captured(self):
        self.assertEqual(self.by_key["GamepadHand"].attrs["values"],
                         ["", "left", "right"])


class TestMojom(unittest.TestCase):
    SRC = '''
module blink.mojom;

interface WidgetHost {
  SetCursor(Cursor cursor);
  [Sync]
  GetFrameSinkId() => (FrameSinkId id);
};
'''

    def setUp(self):
        self.by_key = {f.key: f for f in mojom.extract(self.SRC, "a.mojom")}

    def test_qualified_names(self):
        self.assertIn("blink.mojom.WidgetHost", self.by_key)
        self.assertIn("blink.mojom.WidgetHost.SetCursor", self.by_key)

    def test_signature_includes_params_and_response(self):
        method = self.by_key["blink.mojom.WidgetHost.GetFrameSinkId"]
        self.assertEqual(method.attrs["signature"],
                         "GetFrameSinkId() => (FrameSinkId id)")
        self.assertIn("Sync", method.attrs["attrs"])

    def test_param_change_alters_signature(self):
        changed = mojom.extract(
            self.SRC.replace("SetCursor(Cursor cursor)",
                             "SetCursor(Cursor cursor, bool force)"), "a.mojom")
        sig = {f.key: f for f in changed}["blink.mojom.WidgetHost.SetCursor"]
        self.assertEqual(sig.attrs["signature"], "SetCursor(Cursor cursor, bool force)")


class TestWebUiControls(unittest.TestCase):
    """Chromium ships two template dialects; reading one leaves gaps.

    Measured at M151: settings is still 243 Polymer .html to 6 Lit .html.ts,
    but extensions is 2 to 33 and print_preview 2 to 32. Reading only .html
    left 23% of templates unread and nearly all of the surfaces a browser team
    cares about -- extensions, history, bookmarks, downloads.
    """

    POLYMER = '''
    <settings-section page-title="$i18n{downloadsPageTitle}">
      <settings-toggle-button
          pref="{{prefs.download.prompt_for_download}}"
          label="$i18n{promptForDownload}">
      </settings-toggle-button>
      <controlled-button id="changeDownloadsPath"
          pref="[[prefs.download.default_directory]]">
      </controlled-button>
    </settings-section>
    '''

    LIT = '''
    import {html} from '//resources/lit/v3_0/lit.rollup.js';
    export function getHtml(this: DownloadsItemElement) {
      return html`<!--_html_template_start_-->
    <cr-toggle id="deepScan" ?checked="${this.isChecked_}"
        @change="${this.onToggle_}"></cr-toggle>
    <settings-toggle-button .pref="${this.prefs.download.bubble_enabled}"
        label="$i18n{showBubble}"></settings-toggle-button>
    `;
    }
    '''

    def _by_control(self, text, path):
        return {f.attrs["control"]: f for f in web_ui.extract(text, path)}

    def test_polymer_template(self):
        facts = self._by_control(
            self.POLYMER, "chrome/browser/resources/settings/downloads_page/x.html")
        self.assertEqual(facts["settings-toggle-button"].attrs["pref"],
                         "download.prompt_for_download")
        self.assertEqual(facts["controlled-button"].attrs["pref"],
                         "download.default_directory")

    def test_lit_template_is_read_at_all(self):
        facts = self._by_control(
            self.LIT, "chrome/browser/resources/downloads/item.html.ts")
        self.assertIn("cr-toggle", facts)
        self.assertIn("settings-toggle-button", facts)

    def test_lit_pref_binding(self):
        """Lit writes .pref="${this.prefs.x}" where Polymer writes {{prefs.x}}."""
        facts = self._by_control(
            self.LIT, "chrome/browser/resources/downloads/item.html.ts")
        self.assertEqual(facts["settings-toggle-button"].attrs["pref"],
                         "download.bubble_enabled")

    def test_lit_sigil_attributes_are_read(self):
        """?bool, .property and @event names must survive the sigil."""
        facts = self._by_control(
            self.LIT, "chrome/browser/resources/downloads/item.html.ts")
        self.assertEqual(facts["cr-toggle"].attrs["element_id"], "deepScan")

    def test_both_dialects_are_claimed(self):
        self.assertTrue(web_ui.applies_to(
            "chrome/browser/resources/settings/a/b.html"))
        self.assertTrue(web_ui.applies_to(
            "chrome/browser/resources/downloads/item.html.ts"))
        # Plain TypeScript is behaviour, not a template.
        self.assertFalse(web_ui.applies_to(
            "chrome/browser/resources/downloads/item.ts"))

    def test_page_name_strips_both_extensions(self):
        self.assertEqual(
            web_ui.page_of("chrome/browser/resources/downloads/item.html.ts"),
            "item")
        self.assertEqual(
            web_ui.surface_of("chrome/browser/resources/downloads/item.html.ts"),
            "downloads")


class TestConstants(unittest.TestCase):
    def test_switches(self):
        facts = constants.extract(
            'const char kDisableGpu[] = "disable-gpu";', "content_switches.cc")
        self.assertEqual(facts[0].kind, "switch")
        self.assertEqual(facts[0].key, "disable-gpu")
        self.assertEqual(facts[0].attrs["var"], "kDisableGpu")

    def test_prefs(self):
        facts = constants.extract(
            'inline constexpr char kHomePage[] = "homepage";', "pref_names.h")
        self.assertEqual(facts[0].kind, "pref")
        self.assertEqual(facts[0].key, "homepage")

    def test_applies_to_only_relevant_files(self):
        self.assertTrue(constants.applies_to("content/content_switches.cc"))
        self.assertTrue(constants.applies_to("chrome/common/pref_names.h"))
        self.assertFalse(constants.applies_to("chrome/browser/foo.cc"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
