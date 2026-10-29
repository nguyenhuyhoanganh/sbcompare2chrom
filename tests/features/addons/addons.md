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
- Automated: tests/features/addons/test_addons.py::test_addon_listed_and_active

## ADD-002 Disable an add-on
- Priority: High
- Type: web
- Steps:
  1. Turn off "SB Sample Addon" on the extensions page
  2. Open a local test page
- Expected:
  - The add-on state is DISABLED; the page is not marked
- Automated: tests/features/addons/test_addons.py::test_disable_addon

## ADD-003 Details page
- Priority: Low
- Type: web
- Steps:
  1. Click Details on "SB Sample Addon"
- Expected:
  - The details view shows the description and version 1.0.0
- Automated: tests/features/addons/test_addons.py::test_details_page

## ADD-004 Remove an add-on (native confirmation)
- Priority: High
- Type: native
- Steps:
  1. Click Remove on "SB Sample Addon", confirm in the dialog
- Expected:
  - The add-on is gone from the list
- Automated: tests/features/addons/test_addons.py::test_remove_addon_native_confirm

## ADD-005 Install an add-on with "Load unpacked"
- Priority: High
- Type: native
- Steps:
  1. Open the add-ons page, turn on Developer mode
  2. Click "Load unpacked", choose the folder resources/extensions/sample_addon
- Expected:
  - "SB Sample Addon" is listed and enabled
- Automated: tests/features/addons/test_addon_install.py::test_load_unpacked

## ADD-006 Install an add-on from Chrome Web Store
- Priority: High
- Type: native
- Precondition: internet through the company proxy; extension id in resources/data/addons.yaml
- Steps:
  1. Open the store page of the extension, click "Add to ..."
  2. Confirm "Add extension" in the prompt
- Expected:
  - The store shows the remove button; the add-on is listed on the add-ons page
- Automated: tests/features/addons/test_addon_install.py::test_install_from_web_store
