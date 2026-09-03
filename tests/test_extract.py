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

from chromiumdiff import jsonc
from chromiumdiff.model import Fact
from chromiumdiff.extract import base_features, blink_runtime, constants, mojom, web_idl
from chromiumdiff.extract import webui_controls as web_ui
from chromiumdiff.extract import _stamp_platform_dirs
from chromiumdiff.extract._cpp import (
    PLATFORM,
    balanced_args,
    eval_condition,
    eval_mojom_condition,
    mask_comments,
    mojom_platform_state,
    other_platform_dir,
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
        from chromiumdiff.diff import diff_snapshots
        from chromiumdiff.model import Snapshot

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


class TestMojomDataTypes(unittest.TestCase):
    """The other 74% of the Mojo surface.

    Only `interface` was read, which is 1,581 of the 5,911 declarations in the
    M151 tree. A struct field changing type breaks deserialization on the far
    side of the process boundary exactly the way a moved method parameter does,
    and it breaks the build no more than that one does.
    """

    SRC = '''
module blink.mojom;

struct Payload {
  bool flag;
  network.mojom.IPEndPoint? endpoint;
  [MinVersion=1] url.mojom.Url source@0;
  int32 retries = 5;
  map<string, array<uint8>> blobs;
};

union Either {
  string text;
  array<uint8> bytes;
};

interface Holder {
  enum WaitMode { kWait, kNoWait = 3 };
  Acquire(WaitMode mode) => (bool ok);
};

enum TopLevel { kA, kB = 2, };
'''

    def setUp(self):
        self.by_key = {f.key: f for f in mojom.extract(self.SRC, "a.mojom")}

    def test_structs_unions_and_enums_are_facts(self):
        self.assertEqual(self.by_key["blink.mojom.Payload"].attrs["mojo_kind"],
                         "struct")
        self.assertEqual(self.by_key["blink.mojom.Either"].attrs["mojo_kind"],
                         "union")
        self.assertIn("blink.mojom.TopLevel", self.by_key)

    def test_a_field_carries_the_type_that_is_the_wire_format(self):
        f = self.by_key["blink.mojom.Payload.endpoint"]
        self.assertEqual(f.attrs["type"], "network.mojom.IPEndPoint?")
        self.assertEqual(f.attrs["struct"], "blink.mojom.Payload")

    def test_generic_types_survive_intact(self):
        self.assertEqual(self.by_key["blink.mojom.Payload.blobs"].attrs["type"],
                         "map<string, array<uint8>>")

    def test_ordinal_and_version_annotation_are_read(self):
        f = self.by_key["blink.mojom.Payload.source"]
        self.assertEqual(f.attrs["type"], "url.mojom.Url")
        self.assertEqual(f.attrs["ordinal"], "0")
        self.assertEqual(f.attrs["attrs"], "MinVersion=1")

    def test_a_default_is_not_swallowed_into_the_name(self):
        """`int32 retries = 5` came out as a field named `5`.

        The attribute block and the default both contain an `=`, and the type
        has to stay greedy so `array<uint8>? data` keeps its whole type. Both
        are peeled off before the field pattern runs.
        """
        f = self.by_key["blink.mojom.Payload.retries"]
        self.assertEqual(f.attrs["type"], "int32")
        self.assertEqual(f.attrs["default"], "5")
        self.assertNotIn("blink.mojom.Payload.5", self.by_key)

    def test_a_nested_enum_is_named_the_way_mojo_names_it(self):
        self.assertIn("blink.mojom.Holder.WaitMode", self.by_key)

    def test_a_nested_declaration_is_not_read_as_its_parents_content(self):
        """357 enums at M151 are declared inside the type that uses them."""
        holder = self.by_key["blink.mojom.Holder"]
        self.assertEqual(holder.attrs["methods"], ["Acquire"])
        self.assertNotIn("blink.mojom.Holder.kWait", self.by_key)

    def test_an_enum_carries_its_members_as_one_list(self):
        """Members alone are 17,061 declarations; a fact each buries the report.

        A `values` delta says in one row what 17,000 add/remove rows would say,
        which is the shape `web_idl` already uses for an IDL enum.
        """
        self.assertEqual(self.by_key["blink.mojom.TopLevel"].attrs["values"],
                         ["kA", "kB = 2"])
        self.assertEqual(
            self.by_key["blink.mojom.Holder.WaitMode"].attrs["values"],
            ["kWait", "kNoWait = 3"])

    def test_a_struct_does_not_compare_its_own_field_list(self):
        """The same reason an interface does not compare its method list.

        Every field is already a fact, so comparing the list would report one
        ABI change twice, once vaguely and once precisely.
        """
        from chromiumdiff.diff import MEANINGFUL_ATTRS
        from chromiumdiff.model import KIND_MOJO_STRUCT
        self.assertNotIn("fields", MEANINGFUL_ATTRS[KIND_MOJO_STRUCT])

    def test_a_field_type_change_is_an_abi_break(self):
        from chromiumdiff.diff import diff_snapshots
        from chromiumdiff.model import Snapshot
        old = Snapshot(ref="a", facts=mojom.extract(self.SRC, "a.mojom"),
                       meta={"target_set": "default"})
        new = Snapshot(ref="b", meta={"target_set": "default"},
                       facts=mojom.extract(
                           self.SRC.replace("bool flag;", "int32 flag;"),
                           "a.mojom"))
        change = {c.key: c for c in diff_snapshots(old, new)}["blink.mojom.Payload.flag"]
        self.assertIn("ipc_shape_changed", change.signals)
        self.assertGreaterEqual(change.severity, 80)

    def test_an_enum_member_change_is_reported_once(self):
        from chromiumdiff.diff import diff_snapshots
        from chromiumdiff.model import Snapshot
        old = Snapshot(ref="a", facts=mojom.extract(self.SRC, "a.mojom"),
                       meta={"target_set": "default"})
        new = Snapshot(ref="b", meta={"target_set": "default"},
                       facts=mojom.extract(
                           self.SRC.replace("kA, kB = 2,", "kA, kB = 2, kC = 3,"),
                           "a.mojom"))
        changes = diff_snapshots(old, new)
        self.assertEqual([c.key for c in changes], ["blink.mojom.TopLevel"])
        self.assertIn("ipc_enum_changed", changes[0].signals)


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
        """Qualifying by id must not change identity where there is no id.

        The declaring file is in the key as well as the directory, because two
        dialogs in one folder bind the same thing -- so the tail is
        `<surface>/<directory>/<file>/<ident>`.
        """
        facts = web_ui.extract(
            '<settings-toggle-button pref="{{prefs.a.b}}">',
            "chrome/browser/resources/settings/x/page.html")
        self.assertEqual(facts[0].key, "settings/x/page/pref:a.b")

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
        from chromiumdiff.extract import webui_controls
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
        from chromiumdiff.extract import constants
        for name in ("chrome/common/pref_names.h",
                     "components/bookmarks/common/bookmark_pref_names.h",
                     "chrome/browser/ui/safety_hub/safety_hub_prefs.h",
                     "components/performance_manager/public/user_tuning/prefs.h",
                     "chrome/browser/prefs/browser_prefs.cc"):
            self.assertTrue(constants.applies_to(name), name)

    def test_unrelated_files_are_not_claimed(self):
        from chromiumdiff.extract import constants
        for name in ("chrome/browser/foo.cc", "components/x/prefs_unittest.cc",
                     "chrome/browser/prefs_test.cc"):
            self.assertFalse(constants.applies_to(name), name)

    def test_a_real_declaration_is_extracted(self):
        from chromiumdiff.extract import constants
        facts = constants.extract(
            'inline constexpr char kMemorySaverModeEnabled[] =\n'
            '    "performance_tuning.high_efficiency_mode.enabled";',
            "components/performance_manager/public/user_tuning/prefs.h")
        self.assertEqual([f.key for f in facts],
                         ["performance_tuning.high_efficiency_mode.enabled"])
        self.assertEqual(facts[0].attrs["var"], "kMemorySaverModeEnabled")


class TestPlatformSkipHasOneException(unittest.TestCase):
    """ChromeOS code is skipped -- except its string constants.

    A pref key is identified by its string, and Chromium is splitting
    chrome/common/pref_names.h apart. A key that moves out of it into a
    ChromeOS file looks, to a reader that cannot see the destination, exactly
    like a key that was deleted -- and for a pref, "deleted" means every
    existing user's stored value is orphaned. Measured M148 -> M151, of 141
    keys that vanished, 100 had simply moved into a ChromeOS pref file.

    So string constants are read wherever they live, and nothing else is.
    """

    def _kinds(self, tree):
        import os
        import tempfile

        from chromiumdiff.extract import run_on_tree

        with tempfile.TemporaryDirectory() as tmp:
            for rel, text in tree.items():
                path = os.path.join(tmp, rel)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path, "w") as fh:
                    fh.write(text)
            facts, _ = run_on_tree(tmp)
        return {f.kind for f in facts}

    PREF = 'inline constexpr char kFoo[] = "ash.foo";'
    FEATURE = 'BASE_FEATURE(kBar, base::FEATURE_ENABLED_BY_DEFAULT);'

    def test_a_chromeos_pref_is_read(self):
        kinds = self._kinds({"chrome/browser/ash/x/pref_names.h": self.PREF})
        self.assertIn("pref", kinds)

    def test_a_chromeos_feature_is_not_read(self):
        kinds = self._kinds({"chrome/browser/ash/x/x_features.cc": self.FEATURE})
        self.assertEqual(kinds, set())

    def test_the_same_file_on_our_platform_is_read_in_full(self):
        kinds = self._kinds({"components/x/x_features.cc": self.FEATURE})
        self.assertIn("base_feature", kinds)

    def test_test_code_is_still_skipped_everywhere(self):
        """The platform exception must not become a hole for test files."""
        self.assertEqual(
            self._kinds({"components/x/test/pref_names.h": self.PREF}), set())
        self.assertEqual(
            self._kinds({"chrome/browser/ash/test/pref_names.h": self.PREF}), set())


class TestDeclarationHintsComeInPairs(unittest.TestCase):
    """A `.cc` hint without its `.h` loses whatever the header declares.

    It has happened twice: `_feature_list.h` and then `_field_trial.h`, each
    found only because a coverage measurement named the files it could not
    reach. Both were fetched and then not read, which is the quietest way to
    lose a declaration -- the file is on disk, so nothing looks missing.
    """

    def test_every_cc_hint_has_an_h_hint(self):
        from chromiumdiff.extract.base_features import FILE_HINTS

        # These have no header form in Chromium: the definitions live in the
        # .cc and the header, if any, declares nothing this extractor reads.
        no_header = {"media_switches.cc", "gpu_finch_features.cc",
                     "_util.cc", "_handler.cc", "_manager.cc"}
        for hint in FILE_HINTS:
            if not hint.endswith(".cc") or hint in no_header:
                continue
            self.assertIn(hint[:-3] + ".h", FILE_HINTS,
                          f"{hint} is read but its header is not")

    def test_the_wide_filter_and_the_hints_agree(self):
        """Fetching a suffix nobody reads is waste; the reverse loses data."""
        from chromiumdiff.extract import REGISTRY
        from chromiumdiff.targets import READABLE_SUFFIXES

        for suffix in READABLE_SUFFIXES:
            if not suffix.endswith((".cc", ".h")) or suffix.startswith("."):
                continue
            probe = f"components/x/y_{suffix}"
            self.assertTrue(any(applies(probe) for _, applies, _ in REGISTRY),
                            f"{suffix} is fetched but nothing reads {probe}")

    def test_a_bare_filename_is_read_as_well_as_a_prefixed_one(self):
        """Chromium writes both `content_switches.cc` and plain `switches.cc`.

        The hints were spelled `_switches.`, with the underscore required, so
        the bare form was fetched and never read. At M151 that was 44 files --
        `components/embedder_support/switches.cc` declares `--headless` and
        `--disable-popup-blocking`, `extensions/common/switches.cc` declares
        35 more -- inside a target set reporting full coverage.
        """
        from chromiumdiff.extract import REGISTRY
        from chromiumdiff.targets import READABLE_SUFFIXES

        for suffix in READABLE_SUFFIXES:
            if not suffix.endswith((".cc", ".h")) or suffix.startswith("."):
                continue
            probe = f"components/x/{suffix}"
            self.assertTrue(any(applies(probe) for _, applies, _ in REGISTRY),
                            f"{suffix} is fetched but nothing reads {probe}")

    def test_every_convention_the_candidate_rule_names_is_readable(self):
        """Coverage must not count a file no extractor would read.

        The candidate rule and the extractors are two lists of filename
        conventions, and they had drifted apart in both directions: coverage
        did not count `*flags.{cc,h}` although the extractors read them, and
        the extractors did not read a bare `switches.cc` although coverage
        counted it. A denominator that disagrees with what is read makes the
        percentage describe nothing.
        """
        from chromiumdiff.extract import REGISTRY
        from chromiumdiff.targets import could_declare

        conventions = ("features", "switches", "feature_list", "field_trial",
                       "fieldtrial", "flags", "pref_names", "prefs")
        for convention in conventions:
            for ext in (".cc", ".h"):
                for stem in (convention, "foo_" + convention):
                    path = f"components/x/{stem}{ext}"
                    self.assertTrue(could_declare(path),
                                    f"coverage does not count {path}")
                    self.assertTrue(
                        any(applies(path) for _, applies, _ in REGISTRY),
                        f"coverage counts {path} but nothing reads it")

    def test_a_bare_switches_file_yields_its_switches(self):
        from chromiumdiff.extract import constants

        source = """
        namespace switches {
        // Enable headless mode.
        const char kHeadless[] = "headless";
        }  // namespace switches
        """
        path = "components/embedder_support/switches.cc"
        self.assertTrue(constants.applies_to(path))
        facts = constants.extract(source, path)
        self.assertEqual([f.key for f in facts], ["headless"])


class TestMojomBuildConditions(unittest.TestCase):
    """Mojom's `[EnableIf]` is the third dialect of one question.

    `platform_state` existed on four of the sixteen kinds and none of them were
    Mojo, so the scoring stage could not zero an Android-only declaration --
    and Mojo carries the highest severities the tool produces. 256 declarations
    in the M151 tree are `EnableIf=is_android`.
    """

    def test_platform_names_resolve_for_windows(self):
        self.assertIs(eval_mojom_condition("EnableIf=is_win"), True)
        self.assertIs(eval_mojom_condition("EnableIf=is_android"), False)
        self.assertIs(eval_mojom_condition("EnableIfNot=is_win"), False)
        self.assertIs(eval_mojom_condition("EnableIfNot=is_android|is_ios"), True)
        self.assertIs(eval_mojom_condition("EnableIf=is_chromeos|is_linux"), False)

    def test_a_non_platform_build_flag_stays_undecided(self):
        """Guessing here would be the same mistake in a new place.

        40 of the 68 distinct attributes in the M151 tree are build flags
        rather than platforms -- `enable_print_preview`, `use_ozone`.
        """
        self.assertIsNone(eval_mojom_condition("EnableIf=enable_print_preview"))
        self.assertEqual(mojom_platform_state(["EnableIf=use_ozone"]), "conditional")

    def test_an_or_is_settled_by_the_half_it_can_decide(self):
        """`is_win|enable_pdf` is true on Windows whatever `enable_pdf` is."""
        self.assertIs(eval_mojom_condition("EnableIf=is_win|enable_pdf"), True)

    def test_an_attribute_that_is_not_a_condition_decides_nothing(self):
        self.assertIsNone(eval_mojom_condition("Sync"))
        self.assertIsNone(eval_mojom_condition("MinVersion=3"))
        self.assertEqual(mojom_platform_state([]), None)

    def test_conditions_are_inherited_from_the_enclosing_declaration(self):
        """An enum inside an Android-only struct is not in our binary either.

        The same chain `_qualified` walks. Reading only a declaration's own
        attributes would report the enum as ours.
        """
        facts = mojom.extract("""
module test.mojom;

[EnableIf=is_android]
struct Phone {
  int32 imei;
  enum Radio { kLte, kNr };
};

[EnableIf=is_win]
interface Desktop {
  Ping();
  [EnableIf=is_android] Never();
};
""", "test.mojom")
        state = {f.key: f.attrs.get("platform_state", {}).get("windows")
                 for f in facts}
        self.assertEqual(state["test.mojom.Phone"], "not_compiled")
        self.assertEqual(state["test.mojom.Phone.imei"], "not_compiled")
        self.assertEqual(state["test.mojom.Phone.Radio"], "not_compiled")
        self.assertEqual(state["test.mojom.Desktop"], "compiled")
        self.assertEqual(state["test.mojom.Desktop.Ping"], "compiled")
        # Windows interface, Android method: the guards are ANDed, so it is in
        # neither build rather than in ours.
        self.assertEqual(state["test.mojom.Desktop.Never"], "not_compiled")

    def test_an_unconditional_declaration_carries_no_platform_state(self):
        """Absent, not "compiled", so it compares equal to how it always was."""
        facts = mojom.extract(
            "module test.mojom;\n\nstruct Plain { int32 a; };\n", "test.mojom")
        for fact in facts:
            self.assertNotIn("platform_state", fact.attrs)


class TestPlatformDirectories(unittest.TestCase):
    """A directory Chromium excludes in BUILD.gn leaves no guard to read.

    Nothing inside `chrome/browser/ash/` carries `#if BUILDFLAG(IS_CHROMEOS)`,
    because the whole directory is outside the build on every other platform.
    The path is the only evidence, and it decides the same thing a guard does.
    """

    def test_the_rule_matches_directories_and_not_words_containing_them(self):
        self.assertTrue(other_platform_dir("ash/constants/ash_features.cc"))
        self.assertTrue(other_platform_dir("chrome/browser/ash/login/prefs.h"))
        self.assertTrue(other_platform_dir("chrome/browser/flags/android/x.cc"))
        self.assertFalse(other_platform_dir("chrome/common/pref_names.h"))
        # `hash` and `studios` end in the platform names, and start no
        # directory called one.
        self.assertFalse(other_platform_dir("components/hash/hash.cc"))
        self.assertFalse(other_platform_dir("media/studios/x.cc"))

    def test_one_definition_serves_every_stage_that_asks(self):
        """There were two, and they disagreed about `android/`.

        `targets.py` decided what to fetch and what the coverage denominator
        is; `extract/` decided which extractors run. Nothing asked when
        scoring, so 164 findings on a wide M148 -> M151 run were declared
        under a platform we do not build and none of them scored zero.
        """
        from chromiumdiff.extract._cpp import PLATFORM_DIR_RE
        from chromiumdiff.targets import _OTHER_PLATFORM_RE
        self.assertIs(_OTHER_PLATFORM_RE, PLATFORM_DIR_RE)

    def test_a_declaration_under_a_platform_directory_is_not_in_our_build(self):
        facts = _stamp_platform_dirs([
            Fact(kind="base_feature", key="AndroidOnly", name="AndroidOnly",
                 path="chrome/browser/flags/android/chrome_feature_list.cc",
                 attrs={"var": "kAndroidOnly"}),
            Fact(kind="base_feature", key="Ours", name="Ours",
                 path="content/public/common/content_features.cc",
                 attrs={"var": "kOurs"}),
        ], ours_somewhere=set())
        state = {f.key: f.attrs.get("platform_state") for f in facts}
        self.assertEqual(state["AndroidOnly"], {PLATFORM: "not_compiled"})
        self.assertIsNone(state["Ours"])

    def test_a_key_declared_in_both_places_keeps_its_build(self):
        """Five keys at M151 are, and dedupe keeps the ChromeOS copy.

        `pref:id`, `pref:name`, `pref:system` and two more are declared under
        a platform directory and outside one. Marking them from the copy we do
        not build would take a real preference out of the report.
        """
        facts = _stamp_platform_dirs([
            Fact(kind="pref", key="system", name="system",
                 path="chrome/browser/ash/x.h", attrs={"var": "kSystem"}),
        ], ours_somewhere={"pref:system"})
        self.assertNotIn("platform_state", facts[0].attrs)


class TestFactsAnOutsideReviewFoundMissing(unittest.TestCase):
    """Five things the tool had the evidence for and did not use.

    Every one was invisible to a self-consistency test: the extractor and the
    documents agreed with each other about a number that was wrong, because
    neither counted what neither read. They are held individually here.
    """

    def test_the_guard_around_a_feature_reaches_its_platform_state(self):
        """441 features at M151 sat under a Windows-excluding `#if`.

        The guard was collected into `conditions` and never applied, so
        `score._not_in_build` could not fire and an Android-only feature
        turning on scored 75 on a Windows report.
        """
        facts = {f.key: f for f in base_features.extract("""
#if BUILDFLAG(IS_ANDROID)
BASE_FEATURE(kAndroidOnly, base::FEATURE_ENABLED_BY_DEFAULT);
#endif
BASE_FEATURE(kOurs, base::FEATURE_ENABLED_BY_DEFAULT);
#if BUILDFLAG(ENABLE_PDF)
BASE_FEATURE(kMaybe, base::FEATURE_ENABLED_BY_DEFAULT);
#endif
""", "x/features.cc")}
        state = lambda k: facts[k].attrs["platform_state"][PLATFORM]
        self.assertEqual(state("AndroidOnly"), "not_compiled")
        self.assertEqual(state("Ours"), "enabled")
        # A non-platform build flag is undecidable, not ours-by-default.
        self.assertEqual(state("Maybe"), "conditional")

    def test_a_mojo_method_pinned_to_an_ordinal_is_still_a_method(self):
        """269 declarations across 23 files at M151 produced nothing.

        `_parse_method` required `(` straight after the name, so `Foo@0(...)`
        matched nothing and was skipped without an error -- on the surface
        this tool ranks highest.
        """
        facts = {f.key: f for f in mojom.extract(
            "module t;\ninterface I {\n  Foo@0(int32 a);\n  Bar(int32 b);\n"
            "  [Sync] Baz@7(string s) => (bool ok);\n};\n", "t.mojom")}
        self.assertIn("t.I.Foo", facts)
        self.assertEqual(facts["t.I.Foo"].attrs["ordinal"], "0")
        self.assertEqual(facts["t.I.Baz"].attrs["ordinal"], "7")
        # The ordinal is part of the wire contract, so it is compared; a
        # method that never had one carries no key at all.
        self.assertNotIn("ordinal", facts["t.I.Bar"].attrs)

    def test_mac_and_linux_are_platform_directories_too(self):
        """79 Mojo facts at M151 live in exact `/mac/` and `/linux/` dirs."""
        self.assertTrue(other_platform_dir("chrome/common/mac/app_shim.mojom"))
        self.assertTrue(other_platform_dir("chrome/browser/linux/x.cc"))

    def test_a_hyphenated_idl_attribute_keeps_its_whole_name(self):
        """`\\w` does not match a hyphen, so `margin-top` was named `top`.

        Its neighbour is genuinely called `top`, so the two collided on one
        uid and deduplication dropped one. 138 member uids at M151.
        """
        facts = [f.key for f in web_idl.extract(
            "interface X { attribute CSSOMString margin-top; "
            "attribute CSSOMString top; };",
            "third_party/blink/renderer/x.idl") if f.kind == "idl_member"]
        self.assertEqual(sorted(facts), ["X.margin-top", "X.top"])

    def test_test_and_fuzzer_declarations_never_reach_a_product_report(self):
        """151 facts at M151 came from files that ship to nobody."""
        from chromiumdiff.extract import _skip
        for path in ("services/network/public/mojom/network_service_test.mojom",
                     "mojo/public/tools/fuzzers/fuzz.mojom",
                     "content/browser/indexed_db_control_test.mojom"):
            self.assertTrue(_skip(path), path)
        self.assertFalse(_skip("third_party/blink/public/mojom/frame/frame.mojom"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
