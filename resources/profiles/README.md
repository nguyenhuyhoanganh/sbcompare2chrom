# Profile templates

A folder here (e.g. `resources/profiles/with_history/`) is copied into the fresh
user-data-dir before the browser starts when a test uses
`@pytest.mark.browser(profile="with_history")`.

Create one by running the browser with `--user-data-dir=<this folder>`, preparing the
state by hand, closing the browser, then deleting caches (`Default/Cache`,
`Default/Code Cache`, `GrShaderCache`, `ShaderCache`, crash dumps) to keep it small.
Prefer seeding in code (bookmarks/prefs) when possible: it is easier to review.
