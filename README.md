# sbtest: Auto test sanity cho Samsung Internet (Windows, fork Chromium)

Tool chạy lại các sanity test cơ bản (bookmarks, history, downloads, settings, add-ons,
duyệt web chung) mỗi lần merge một bản Chromium mới. Đầu vào là `SamsungInternet.exe`.
Có thể chạy toàn bộ, theo từng feature, hoặc theo từng mã test case.

- **Selenium + chromedriver** điều khiển nội dung web, kể cả các trang nội bộ chrome://
  (bookmarks, history...). Các trang này dựng bằng Shadow DOM, framework xử lý sẵn.
- **pywinauto (UI Automation)** điều khiển phần native: toolbar, omnibox, menu,
  bubble/prompt của trình duyệt, dialog Save As/Open/Print, toast của Windows, phím tắt
  (Ctrl+D, Ctrl+H...), chuột thật cho drag & drop.
- **Skill cho agent** (`.claude/skills/`): agent nhận danh sách test case, tự khám phá UI
  và tự viết script test.

## Cài đặt (Windows, chỉ chạy trên Windows)

```bat
setup.bat                                   & rem tạo .venv, cài thư viện, tạo config\local.yaml
notepad config\local.yaml                   & rem browser.exe = <thư mục build>\SamsungInternet.exe
.venv\Scripts\activate
python -m sbtest.tools.doctor               & rem kiểm tra từng bước, chụp ảnh vào artifacts\doctor\
```

Sau proxy công ty thì đặt `HTTPS_PROXY` trước khi chạy `setup.bat`. Nếu cần, đặt thêm
`network.download_proxy` trong `config/local.yaml`. Kết nối tới localhost (chromedriver,
web server local) tự động không đi qua proxy.

**chromedriver** phải cùng major version Chromium với bản build. Framework tự xử lý theo
thứ tự:

1. `browser.chromedriver` trong `config/local.yaml` (hoặc `--driver`).
2. `drivers/<major>/chromedriver.exe` (dùng cho máy offline).
3. Tự phát hiện version Chromium của exe (qua DevTools `/json/version`), rồi tải driver của
   Google (Chrome for Testing) cùng build, qua proxy.

Nếu chromedriver của Google báo `unrecognized Chrome version`, nghĩa là bản fork không
khai báo mình là "Chrome". Khi đó build target `chromedriver` từ chính source fork rồi trỏ
`browser.chromedriver` vào file đó.

Các trang nội bộ dùng `internet://` (cấu hình `pages.scheme`).

## Chạy

```bat
python run.py --exe "C:\SI\SamsungInternet.exe" --all
python run.py --exe ... --feature bookmarks,history
python run.py --exe ... --case BM-001,DL-004
python run.py --exe ... --sanity             & rem chỉ chạy bộ nhanh
python run.py --exe ... --all --reruns 1     & rem chạy lại test fail 1 lần để tách lỗi flaky
python run.py --exe ... --no-native          & rem bỏ các test cần UI native (máy không có desktop)
python run.py --list                         & rem case nào đã được tự động hoá
```

Kết quả nằm ở `artifacts/runs/<thời gian>/`:

- `report.html`: ảnh chụp lỗi nhúng thẳng trong report.
- `junit.xml`, `results.json`.
- `failures/<test>/` cho mỗi test fail:
  - `failure.txt`: case, bước fail, kết quả mong đợi, lỗi, phần tử cuối cùng được thao tác.
  - `page.png`: ảnh tab, phần tử đang thao tác được **khoanh đỏ**.
  - `screen.png`: **toàn màn hình Windows**, thấy được cả dialog/bubble native.
  - `dom.txt`, `page.html`, `uia.txt`, `alert.txt`.
- `--screenshot-steps`: chụp thêm ảnh sau **mỗi bước** vào `steps/<test>/`.
- `--publish`: tạo **một trang Confluence mới** cho lần chạy, gồm bảng theo feature/mã case
  và ảnh lỗi đính kèm. Cần `SB_ATLASSIAN_TOKEN` (Personal Access Token) và mục `atlassian`
  trong `config/local.yaml`. Xem trước bằng
  `python -m sbtest.tools.confluence_report artifacts\runs\<ts> --dry-run`.

Test native cần desktop Windows đang mở và không bị khoá. Đừng chạy qua RDP đang thu nhỏ.

## Cấu trúc

| Đường dẫn | Nội dung |
|-----------|----------|
| `run.py` | CLI chạy test |
| `config/default.yaml` | mọi cấu hình: args, prefs, timeout, URL các trang nội bộ (`pages`) |
| `config/native_ui.yaml` | tên logic → tiêu chí UIA của toolbar, dialog… (sửa ở đây khi Samsung đổi tên) |
| `sbtest/browser/` | khởi động/attach browser, profile riêng cho mỗi test, dò version, resolve chromedriver |
| `sbtest/core/` | lớp web: locator (CSS, XPath, `>>>` xuyên shadow, `text=`, `aria=`), wait, action, đọc nội dung, tab, JS dialog |
| `sbtest/native/` | lớp native: phím tắt, toolbar, menu, context menu, bubble, file dialog, toast, chuột thật, dump UIA |
| `sbtest/pages/` | page object: bookmarks, history, downloads, settings, extensions |
| `sbtest/data/`, `test_data/` | dữ liệu mẫu: seed bookmarks, prefs, add-on mẫu, sinh file |
| `sbtest/server/`, `test_site/` | web server local: trang form, dialog, drag-drop, popup, download (không cần internet) |
| `sbtest/tools/` | `doctor` (kiểm tra máy), `dom` (khám phá DOM), `uia_dump` (khám phá UI native), `coverage`, `atlassian_read` (đọc link Confluence/Jira), `confluence_report` (đẩy report) |
| `sbtest/atlassian.py` | client Confluence/Jira Server/DC, xác thực bằng PAT |
| `testcases/<feature>/*.md` | test case dạng tài liệu, mỗi case có mã (BM-001…) |
| `tests/<feature>/` | script test, gắn `@pytest.mark.case("BM-001")` |
| `framework_tests/` | unit test của chính framework |
| `.claude/skills/` | `sbtest-intake` (link Confluence/Jira → test case), `sbtest-author` (test case → script), `sbtest-run` (chạy, phân loại lỗi, report) |

## Quy trình với agent (chạy Claude Code trên máy Windows có bản build)

1. Đặt token: `set SB_ATLASSIAN_TOKEN=<PAT>`.
2. Đưa link cho agent: *"Đọc test case add-ons ở <link Confluence> và tự động hoá"*.
   - Skill `sbtest-intake` đọc link, chuẩn hoá nội dung thành `testcases/addons/*.md`, mỗi case có mã.
   - Skill `sbtest-author` tự mở browser, khám phá UI (`sbtest.tools.dom`, `uia_dump`), sửa
     page object theo trang thật của Samsung, viết test, rồi chạy `python run.py --case ...`
     cho tới khi pass ổn định.
3. Chạy bộ test sau mỗi lần merge Chromium: `python run.py --all --publish` (skill `sbtest-run`).

## Ghi chú

- Mỗi test chạy trên profile mới. Điều kiện ban đầu khai báo bằng
  `@pytest.mark.browser(bookmarks=..., prefs=..., extensions=[...])`.
- Add-ons có ba luồng cài dựng sẵn: Load unpacked (hộp chọn thư mục của Windows), kéo thả
  `.crx` từ File Explorer (chuột thật), và Chrome Web Store (qua proxy, xác nhận bằng prompt native).
- **Page object hiện được viết theo Chromium gốc.** Samsung đã viết lại nhiều trang, nên
  agent phải kiểm tra lại và sửa selector trên bản build thật. Phần lõi (locator, wait,
  action, native, report) không phụ thuộc vào cấu trúc trang.
- Đã chạy thật trên Chromium 141 (Linux). Phần pywinauto/Windows chưa được chạy trên
  Windows thật, `python -m sbtest.tools.doctor` sẽ cho thấy chỗ nào cần chỉnh.
