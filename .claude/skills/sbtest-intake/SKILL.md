---
name: sbtest-intake
description: Read test cases from a Confluence page or Jira issue link (company Server/Data Center) and turn them into normalized testcases/<feature>/*.md files with IDs, ready for automation with sbtest. Use when the user pastes a Confluence or Jira link, a JQL query, or says "read the test cases from ..." for Samsung Internet sanity testing.
---

# Intake: Confluence / Jira link -> testcases/*.md

## 1. Fetch

Token: the user sets a Personal Access Token in env var `SB_ATLASSIAN_TOKEN` (never ask
them to paste it in chat, never write it to a file). Base URLs are in `config/local.yaml`
(`atlassian.confluence_url`, `atlassian.jira_url`).

```
python -m sbtest.tools.atlassian_read <confluence page url>                 # one page
python -m sbtest.tools.atlassian_read <url> --children --attachments        # + child pages, images
python -m sbtest.tools.atlassian_read https://jira.company.com/browse/SIB-123
python -m sbtest.tools.atlassian_read --jql "project = SIB AND labels = sanity"
python -m sbtest.tools.atlassian_read <url> --out -                          # print only
```

Output: `testcases/_inbox/<title>.md` (raw, converted to Markdown; tables kept) plus an
attachments folder. Supported links: `viewpage.action?pageId=`, `/display/SPACE/Title`,
`/spaces/SPACE/pages/<id>/...`, `/x/<tiny>`, `/browse/KEY-1`.

Errors: HTTP 401/403 -> token missing/expired or no permission; SSL errors -> set
`atlassian.verify_ssl` to the company CA `.pem`; connection errors -> proxy (`HTTPS_PROXY`,
or add the host to `NO_PROXY` when Confluence is internal).

## 2. Normalize (you write this, the tool does not guess)

Read the inbox file and write `testcases/<feature>/<area>.md` in the format of
`testcases/README.md`:

- Feature folder from the content: bookmarks, history, downloads, settings, addons, general
  (new area -> new folder + prefix, tell the user).
- **Keep the source IDs** if the doc has them (e.g. `SI-ADD-012`) - put them in the heading;
  if it has none, assign the feature prefix + next free number and add
  `- Source: <url> (row/section)` so a human can trace it back.
- Steps: numbered, one action each, the author's wording; split compound steps only when
  the expected result belongs to a sub-step.
- Expected: one bullet per checkable outcome.
- `Type:` web / native / mixed, from the step -> layer table in the `sbtest-author` skill.
- Preconditions that are data (existing bookmarks, installed add-on, setting value) are
  written as data, e.g. "Bookmarks bar contains 'Static page 1'".
- Mark cases that cannot be automated (real Samsung account, hardware, external apps)
  with `- Automated: no (<reason>)`.
- Keep `testcases/_inbox/` as the raw copy; it is not read by tests.

Then run `python -m sbtest.tools.coverage --feature <feature>` and hand over to the
`sbtest-author` skill for automation. Report: number of cases read, written per feature,
ambiguities you resolved (list them), cases marked not automatable.
