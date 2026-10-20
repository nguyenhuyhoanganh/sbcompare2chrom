# Add-ons - sanity pass after a Chromium merge (Samsung Browser for Windows)

Flows as the Samsung UI does them (verified on Samsung Browser 31.0.0.55 / Chromium 148).
Install flows and basics are in addons.md (ADD-001..ADD-022). Store installs use free,
widely used extensions only (test_data/addons.yaml: Dark Reader).

## ADD-101 Card shows name, version, description and source
- Priority: High
- Type: web
- Precondition: "SB Sample Addon" 1.0.0 installed (unpacked)
- Steps:
  1. Open Add-ons
  2. Turn on Developer mode
- Expected:
  - The card shows "SB Sample Addon", the manifest description, Details and Remove; the switch is on
  - With Developer mode on the card also shows the version "1.0.0"
- Automated: tests/features/addons/test_addons_sanity.py::test_card_details

## ADD-102 Developer mode shows the developer tools
- Priority: High
- Type: web
- Steps:
  1. Open Add-ons, turn on "Developer mode" in the side bar
  2. Turn it off again
- Expected:
  - On: the toolbar shows Load Unpacked, Pack add-on, Update
  - Off: they are hidden
- Automated: tests/features/addons/test_addons_sanity.py::test_developer_mode_toolbar

## ADD-103 Search add-ons
- Priority: Low
- Type: web
- Precondition: "SB Sample Addon" installed
- Steps:
  1. Type "Sample" in the search box, then "zzz"
- Expected:
  - "Sample" lists the add-on; "zzz" lists nothing
- Automated: tests/features/addons/test_addons_sanity.py::test_search

## ADD-104 Disabled state is kept after restart
- Priority: High
- Type: web
- Precondition: "SB Sample Addon" installed
- Steps:
  1. Turn the add-on off
  2. Close and reopen the browser on the same profile, open Add-ons
- Expected:
  - The add-on is still off and does not run on pages
- Automated: tests/features/addons/test_addons_sanity.py::test_disabled_survives_restart

## ADD-105 Cancel removal keeps the add-on
- Priority: Medium
- Type: native
- Precondition: "SB Sample Addon" installed
- Steps:
  1. Click Remove on the card
  2. In "Delete SB Sample Addon?" click Cancel
- Expected:
  - The add-on is still installed and enabled
- Automated: tests/features/addons/test_addons_sanity.py::test_cancel_remove

## ADD-106 Open Add-ons from the app menu
- Priority: Medium
- Type: native
- Steps:
  1. Open the app menu (⋮ "Samsung Browser"), click "Add-ons"
- Expected:
  - The Add-ons page opens
- Automated: tests/features/addons/test_addons_sanity.py::test_open_from_app_menu
