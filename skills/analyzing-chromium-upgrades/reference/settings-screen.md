# Analyzing WebUI changes

Use this reference for route declarations, controls, preferences and visibility
conditions. The objective is to explain a change in the UI or its behaviour,
not to list each changed HTML element or feature flag separately.

## Source locations

For desktop settings, start with the files below if they exist at the compared
refs. Other WebUI screens can use different handlers and route structures.

| Source | What to inspect |
|---|---|
| `chrome/browser/resources/settings/route.ts` | Route names, paths, parents and surrounding conditions |
| Templates and TypeScript under `chrome/browser/resources/settings/` | Controls, preference bindings, event handlers and visibility logic |
| C++ under `chrome/browser/ui/webui/settings/` | Values supplied to `loadTimeData` and their full expressions |
| `chrome/browser/resources/settings/page_visibility.ts`, when present | Additional page visibility conditions |
| Preference declarations, registrations and consumers | Key identity, default, stored values and migration behaviour |
| String resources referenced by the templates | Actual displayed text and translations, not only the resource key |

A path in this table is a starting location, not a guarantee that it was
fetched or parsed. Use the index's exact-version roots or `review source`.
If the cache lacks a required file, fetch that path at the correct ref or
record the missing evidence.

## Determine visibility and behaviour

Follow each relevant reference:

```text
route or control
  -> condition or loadTimeData key
  -> handler expression
  -> feature/configuration values and affected implementation
```

Read all terms of an expression. A feature default does not determine a
condition that also depends on profile state, platform or another value.
Compare both versions; some of these declarations may be unchanged while
their consumers change.

For a control with a preference binding, inspect the key's readers and
writers. The same binding can help identify a moved control, but several
controls may use one preference. Confirm the relationship rather than merging
all controls that share a key.

Inspect event handlers and other implementation code when the question is
about what the UI does. Template presence alone does not establish behaviour
or rendered visibility. For platform-specific files, verify build scope
rather than assuming every finding is relevant to Windows.

## Choose an event's scope

| Observed change | What establishes a useful report item |
|---|---|
| One control changed type, value or label | Explain its before/after interaction and affected setting |
| A route appeared, disappeared or moved | Explain navigation, conditions and replacement if one exists |
| Several pages, controls and consumers changed together | Explain the shared capability change and evidence connecting the parts |

Group by the supported change, not by screen name, prefix, common flag or
score. A screen can contain unrelated changes. A single related change can
involve several screens and files. Changes without a feature flag also need
analysis.

For a proposed migration, identify the old behaviour, new behaviour and
source or history connecting them. Two endpoint versions do not establish
when users first saw the new UI. State that date only with relevant history
or deployment evidence.

## Coverage and verification

The WebUI extractors read supported route, control and handler declarations
in the files selected by the run. This is not a complete TypeScript analysis
or a rendered UI test. Use actual report coverage; do not assume that a
previous run's screen count or file list applies.

`cluster.py` produces candidate groups. The review index also records declared
relationships through unchanged facts. Both help retrieve evidence; the
agent still verifies which items belong to one event.

Before concluding that a page or control was removed, check alternative
locations, full visibility conditions and consumers. If those checks are
incomplete, report the observed source change and the unresolved question.
