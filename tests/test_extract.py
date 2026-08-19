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
        """True / False / None, evaluated for the one platform we ship."""
        self.assertIs(eval_condition("BUILDFLAG(IS_WIN)"), True)
        self.assertIs(eval_condition("!BUILDFLAG(IS_WIN)"), False)
        # Another platform's flag is decidably false for us, not unknown.
        self.assertIs(eval_condition("BUILDFLAG(IS_ANDROID)"), False)
        self.assertIs(eval_condition("BUILDFLAG(IS_MAC) || BUILDFLAG(IS_WIN)"), True)
        self.assertIs(eval_condition("BUILDFLAG(IS_MAC) && BUILDFLAG(IS_WIN)"), False)
        # A non-platform buildflag cannot be decided here; None, never a guess.
        self.assertIsNone(eval_condition("BUILDFLAG(ENABLE_PLUGINS)"))

    def test_resolve_platform_state_picks_branch(self):
        block = """
#if BUILDFLAG(IS_WIN) || BUILDFLAG(IS_MAC)
             base::FEATURE_ENABLED_BY_DEFAULT
#else
             base::FEATURE_DISABLED_BY_DEFAULT
#endif
"""
        states = resolve_platform_state(block, base_features.STATE_RE)
        self.assertEqual(states, {"windows": "FEATURE_ENABLED_BY_DEFAULT"})


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

    def test_every_declaration_form_produces_the_same_attributes(self):
        """A missing attribute is indistinguishable from a changed one.

        `_meaningful` only compares keys that are present, so a form that omits
        one reports a phantom modification against a form that has it. That is
        what SCHEMA 4 was bumped for; the legacy form kept the bug three
        versions longer because nothing compared the shapes.
        """
        guard = "#if BUILDFLAG(IS_WIN)\n%s\n#endif\n"
        forms = {
            "macro2": guard % "BASE_FEATURE(kFoo, base::FEATURE_ENABLED_BY_DEFAULT);",
            "macro3": guard % ('BASE_FEATURE(kFoo, "Foo", '
                               "base::FEATURE_ENABLED_BY_DEFAULT);"),
            "legacy": guard % ('const base::Feature kFoo{"Foo", '
                               "base::FEATURE_ENABLED_BY_DEFAULT};"),
        }
        shapes = {}
        for label, source in forms.items():
            facts = base_features.extract(source, "content/features.cc")
            self.assertEqual(len(facts), 1, label)
            shapes[label] = set(facts[0].attrs)
        self.assertEqual(shapes["legacy"], shapes["macro2"])
        self.assertEqual(shapes["macro3"], shapes["macro2"])

    def test_the_same_feature_written_two_ways_is_not_a_change(self):
        from chromedrift.diff import diff_snapshots
        from chromedrift.model import Snapshot

        guard = "#if BUILDFLAG(IS_WIN)\n%s\n#endif\n"
        old = base_features.extract(
            guard % ('const base::Feature kFoo{"Foo", '
                     "base::FEATURE_ENABLED_BY_DEFAULT};"), "content/features.cc")
        new = base_features.extract(
            guard % "BASE_FEATURE(kFoo, base::FEATURE_ENABLED_BY_DEFAULT);",
            "content/features.cc")
        changes = diff_snapshots(Snapshot(ref="a", facts=old),
                                 Snapshot(ref="b", facts=new))
        self.assertEqual(changes, [])

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
        # Reading the global value would say "enabled"; the Windows branch is
        # what ships, and here the two happen to agree.
        self.assertEqual(fact.attrs["platform_state"], {"windows": "enabled"})

    def test_filename_convention_is_a_convention_not_a_rule(self):
        """Features are declared outside *_features.cc too.

        Measured at M151: the convention catches 201 of 201 declarations in
        content/public/common but only 1 of 24 in chrome/browser/ui/webui,
        where the rest sit in _fieldtrial.cc, _util.cc and _handler.cc.
        """
        for path in ("content/public/common/content_features.cc",
                     "components/x/composebox_fieldtrial.cc",
                     "chrome/browser/ui/webui/whats_new_util.cc",
                     "chrome/browser/x/on_device_ai_settings_handler.cc"):
            self.assertTrue(base_features.applies_to(path), path)

    def test_test_only_features_are_excluded(self):
        """A feature declared in a browsertest ships to nobody.

        Widening the filter pulled these in: 13 of the 23 declarations the old
        filter had missed were test-only, and counting them as product surface
        would be noise.
        """
        for path in ("chrome/browser/ui/webui/whats_new_fetcher_browsertest.cc",
                     "chrome/browser/x/whats_new_registrar_unittest.cc",
                     "components/y/features_test.cc",
                     "components/y/feature_test_util.cc"):
            self.assertFalse(base_features.applies_to(path), path)

    def test_unrelated_source_is_still_ignored(self):
        self.assertFalse(base_features.applies_to("chrome/browser/browser.cc"))
        self.assertFalse(base_features.applies_to("content/renderer/render_view.cc"))

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
    { name: "PerPlatform", status: {"Win": "stable", "Mac": "experimental"} },
    { name: "MacOnly", status: {"Mac": "stable"} },
    { name: "NoStatus" },
  ],
}
'''

    def setUp(self):
        self.facts = {f.key: f for f in blink_runtime.extract(
            self.SRC, "runtime_enabled_features.json5")}

    def test_simple_status_applies_everywhere(self):
        self.assertEqual(self.facts["SimpleStable"].attrs["windows_status"], "stable")

    def test_per_platform_status(self):
        attrs = self.facts["PerPlatform"].attrs
        self.assertEqual(attrs["platform_status"]["windows"], "stable")

    def test_missing_default_means_not_enabled(self):
        """Omitting "default" means unlisted platforms are OFF.

        Easy to get backwards, and getting it backwards would report a feature
        as shipping for us when it ships somewhere else entirely.
        """
        attrs = self.facts["MacOnly"].attrs
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

    def test_a_pref_bound_twice_yields_two_controls(self):
        """The preference alone is not a unique identity.

        A radio group and each of its buttons bind the same pref, and Chromium
        binds one pref from two pages in the same directory. Keyed on the pref
        alone, 142 of 881 controls at M148 were dropped as duplicates, and
        which one survived depended on directory walk order -- so a control
        type change could be reported that never happened.
        """
        source = """
          <settings-radio-group id="shortcutGroup"
              pref="{{prefs.omnibox.keyword_space_triggering_enabled}}">
            <controlled-radio-button id="spaceOption"
                pref="{{prefs.omnibox.keyword_space_triggering_enabled}}">
            </controlled-radio-button>
          </settings-radio-group>
        """
        facts = web_ui.extract(
            source, "chrome/browser/resources/settings/search_page/page.html")
        self.assertEqual(len(facts), 2)
        self.assertEqual(len({f.key for f in facts}), 2,
                         "both controls must survive dedupe")
        self.assertEqual({f.attrs["control"] for f in facts},
                         {"settings-radio-group", "controlled-radio-button"})

    def test_a_control_without_an_id_still_keys_on_its_pref(self):
        """Qualifying by id must not change identity where there is no id."""
        facts = web_ui.extract(
            '<settings-toggle-button pref="{{prefs.a.b}}">',
            "chrome/browser/resources/settings/x/page.html")
        self.assertEqual(facts[0].key, "settings/x/pref:a.b")

    def test_lit_line_numbers_point_at_the_real_file(self):
        """A line number nobody checks is a line number that quietly drifts.

        Slicing the TypeScript preamble off before scanning made every Lit
        control's line an offset into the template, so `path:line` in a report
        pointed at the wrong place in the file.
        """
        source = (
            "import {html} from 'lit';\n"          # 1
            "\n"                                    # 2
            "export function getHtml(this: X) {\n"  # 3
            "  return html`\n"                      # 4
            "    <cr-toggle id=\"first\"></cr-toggle>\n"   # 5
            "    <cr-button id=\"second\"></cr-button>\n"  # 6
            "  `;\n"
            "}\n"
        )
        facts = web_ui.extract(
            source, "chrome/browser/resources/downloads/item.html.ts")
        lines = {f.attrs["element_id"]: f.line for f in facts}
        self.assertEqual(lines, {"first": 5, "second": 6})

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


class TestPrefBindingForms(unittest.TestCase):
    """A control's link to a preference is written three ways, one of them new.

    Chromium began replacing `pref="{{prefs.a.b}}"` with `pref-key="a.b"`. At
    M151 twenty controls had moved and 125 had not, so reading one spelling
    makes a migrated control look like one that stopped writing a preference --
    which is what the captions settings page produced: four controls reported
    as repointed to nothing when the key had not changed at all.
    """

    PATH = "chrome/browser/resources/settings/a11y_page/captions_page.html"

    def _prefs(self, markup):
        from chromedrift.extract import webui_controls
        return {f.attrs["element_id"]: f.attrs["pref"]
                for f in webui_controls.extract(markup, self.PATH)}

    def test_the_new_pref_key_attribute_is_read(self):
        got = self._prefs('<settings-dropdown-menu id="a" '
                          'pref-key="accessibility.captions.text_color">')
        self.assertEqual(got["a"], "accessibility.captions.text_color")

    def test_the_polymer_binding_still_works(self):
        got = self._prefs('<settings-toggle-button id="b" '
                          'pref="{{prefs.download.prompt_for_download}}">')
        self.assertEqual(got["b"], "download.prompt_for_download")

    def test_a_component_property_is_not_a_preference(self):
        """`{{optedIn_}}` is a private JS member, not a pref key.

        The `prefs.` prefix is what separates them. Without requiring it, 27 of
        156 bindings at M151 recorded an ordinary property as a preference --
        each one inventing a dangling reference and giving the control an
        identity built on a JavaScript member.
        """
        got = self._prefs('<settings-toggle-button id="c" pref="{{optedIn_}}">'
                          '<settings-toggle-button id="d" pref="[[fakePref_]]">')
        self.assertEqual(got["c"], "")
        self.assertEqual(got["d"], "")

    def test_pref_key_wins_when_both_appear(self):
        got = self._prefs('<settings-toggle-button id="e" pref-key="a.b" '
                          'pref="{{prefs.c.d}}">')
        self.assertEqual(got["e"], "a.b")


class TestPrefFileConventions(unittest.TestCase):
    """Chromium names pref-declaring files two ways, and both carry keys.

    `*pref_names.{h,cc}` is the older, larger set. `*_prefs.{h,cc}` is what
    per-component keys use now, and at M151 it held 469 keys across 54 files --
    Memory Saver, Safety Hub, signin, enterprise connectors -- none of which
    were read while the extractor knew only the first spelling.
    """

    def test_both_conventions_are_recognised(self):
        from chromedrift.extract import constants
        for name in ("chrome/common/pref_names.h",
                     "components/bookmarks/common/bookmark_pref_names.h",
                     "chrome/browser/ui/safety_hub/safety_hub_prefs.h",
                     "components/performance_manager/public/user_tuning/prefs.h",
                     "chrome/browser/prefs/browser_prefs.cc"):
            self.assertTrue(constants.applies_to(name), name)

    def test_unrelated_files_are_not_claimed(self):
        from chromedrift.extract import constants
        for name in ("chrome/browser/foo.cc", "components/x/prefs_unittest.cc",
                     "chrome/browser/prefs_test.cc"):
            self.assertFalse(constants.applies_to(name), name)

    def test_a_real_declaration_is_extracted(self):
        from chromedrift.extract import constants
        facts = constants.extract(
            'inline constexpr char kMemorySaverModeEnabled[] =\n'
            '    "performance_tuning.high_efficiency_mode.enabled";',
            "components/performance_manager/public/user_tuning/prefs.h")
        self.assertEqual([f.key for f in facts],
                         ["performance_tuning.high_efficiency_mode.enabled"])
        self.assertEqual(facts[0].attrs["var"], "kMemorySaverModeEnabled")


if __name__ == "__main__":
    unittest.main(verbosity=2)
