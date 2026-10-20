# Add-ons / extensions (sample cases)

## ADD-001 Installed add-on is listed and active
- Priority: High
- Type: web
- Precondition: "SB Sample Addon" installed (unpacked)
- Steps:
  1. Open the extensions page
  2. Open a local test page
- Expected:
  - "SB Sample Addon" is listed and enabled
  - The page is marked by the add-on content script
- Automated: tests/addons/test_addons.py::test_addon_listed_and_active

## ADD-002 Disable an add-on
- Priority: High
- Type: web
- Steps:
  1. Turn off "SB Sample Addon" on the extensions page
  2. Open a local test page
- Expected:
  - The add-on state is DISABLED; the page is not marked
- Automated: tests/addons/test_addons.py::test_disable_addon

## ADD-003 Details page
- Priority: Low
- Type: web
- Steps:
  1. Click Details on "SB Sample Addon"
- Expected:
  - The details view shows the description and version 1.0.0
- Automated: tests/addons/test_addons.py::test_details_page

## ADD-010 Remove an add-on (native confirmation)
- Priority: High
- Type: native
- Steps:
  1. Click Remove on "SB Sample Addon", confirm in the dialog
- Expected:
  - The add-on is gone from the list
- Automated: tests/addons/test_addons.py::test_remove_addon_native_confirm
