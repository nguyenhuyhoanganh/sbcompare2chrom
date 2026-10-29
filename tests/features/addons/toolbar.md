# Add-ons - browser toolbar (Samsung Browser for Windows)

Add-ons from the browser's own UI: app menu entry, toolbar "Add-ons" (puzzle) menu, pinned
add-on icon and its popup. All native (Windows). Verified on Samsung Browser 31.0.0.55.
The popup and options pages belong to the sample add-on (resources/extensions/sample_addon).

## ADD-110 Open Add-ons from the app menu
- Priority: Medium
- Type: native
- Steps:
  1. Open the app menu (⋮ "Samsung Browser"), click "Add-ons"
- Expected:
  - The Add-ons page opens
- Automated: tests/features/addons/test_addons_toolbar.py::test_open_from_app_menu

## ADD-111 Pin and unpin an add-on from the toolbar Add-ons menu
- Priority: High
- Type: native
- Precondition: "SB Sample Addon" installed
- Steps:
  1. Click the toolbar "Add-ons" (puzzle) button
  2. Click "Pin" next to "SB Sample Addon"
  3. Open the menu again, click "Unpin"
- Expected:
  - The menu lists the add-on with Pin and "More options"
  - After Pin the add-on icon is in the toolbar; after Unpin it is gone
- Automated: tests/features/addons/test_addons_toolbar.py::test_pin_from_addons_menu

## ADD-112 Open the add-on popup from its toolbar icon
- Priority: High
- Type: native
- Precondition: "SB Sample Addon" installed and pinned
- Steps:
  1. Click the add-on icon in the toolbar
  2. Click the "Clicked 0" button in the popup
- Expected:
  - The popup opens with "SB Sample Addon" and "Clicked 0"
  - The button turns into "Clicked 1" (the popup's script runs)
- Automated: tests/features/addons/test_addons_toolbar.py::test_popup_from_toolbar_icon

## ADD-113 Add-on "More options" menu opens the options page
- Priority: Medium
- Type: native
- Precondition: "SB Sample Addon" installed
- Steps:
  1. Toolbar "Add-ons" > "More options" of the add-on
  2. Click "Options"
- Expected:
  - The menu offers Options, Remove from Samsung Browser, Manage add-on
  - A tab "SB options" opens with "SB Sample Addon options"
- Automated: tests/features/addons/test_addons_toolbar.py::test_more_options_opens_options_page
