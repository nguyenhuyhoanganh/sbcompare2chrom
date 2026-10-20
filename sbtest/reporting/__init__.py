"""Run outputs.

    evidence.py           failure evidence (failure.txt, page.png with the element outlined,
                          screen.png, dom.txt, page.html, uia.txt, alert.txt) + per-step screenshots
    results.py            results.json: one record per test (outcome, case ids, steps, evidence)
    confluence_export.py  results.json -> a folder ready to become a Confluence page
                          (page body + attachments), uploaded with the Confluence skill
"""
