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

## Cài đặt (Windows)

```bat
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
copy config\local.example.yaml config\local.yaml   & rem sửa đường dẫn exe
```

**chromedriver** phải cùng major version Chromium với bản build. Framework tự xử lý theo
thứ tự:

1. `browser.chromedriver` trong `config/local.yaml` (hoặc `--driver`, `SB_DRIVER`).
   **Khuyến nghị:** build target `chromedriver` từ chính source fork, khi đó version luôn khớp.
2. `drivers/<major>/chromedriver.exe` (dùng cho máy offline).
3. Tự phát hiện version Chromium của exe (qua DevTools `/json/version`, có cache) rồi
   tải driver bằng Selenium Manager.

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

- `report.html`, `junit.xml`
- `failures/<test>/` cho mỗi test fail: `page.png`, `dom.txt` (cây DOM xuyên shadow root),
  `screen.png` và `uia.txt` (cây UI native), `alert.txt`
- Trong console, mục *sbtest steps* cho biết test fail ở bước nào của test case.

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
| `sbtest/tools/` | `dom` (khám phá DOM), `uia_dump` (khám phá UI native), `coverage` |
| `testcases/<feature>/*.md` | test case dạng tài liệu, mỗi case có mã (BM-001…) |
| `tests/<feature>/` | script test, gắn `@pytest.mark.case("BM-001")` |
| `framework_tests/` | unit test của chính framework |
| `.claude/skills/` | `sbtest-author` (viết test từ test case), `sbtest-run` (chạy và phân loại lỗi) |

## Thêm test case mới (người hoặc agent)

1. Chuyển doc thành `testcases/<feature>/<file>.md` theo mẫu trong `testcases/README.md`,
   mỗi case một mã.
2. Đưa danh sách cho agent: *"Dùng skill sbtest-author, tự động hoá các case BM-020..BM-035
   trong testcases/bookmarks/…"*.
3. Agent khám phá UI (`python -m sbtest.tools.dom bookmarks --interactive`,
   `python -m sbtest.tools.uia_dump`), dùng hoặc mở rộng page object, viết test, chạy
   `python run.py --case ...` cho tới khi pass ổn định, rồi cập nhật dòng `Automated:` trong doc.

## Ghi chú

- Mỗi test chạy trên profile mới (`--browser-scope module|session` để dùng lại browser, nhanh
  hơn). Điều kiện ban đầu khai báo bằng `@pytest.mark.browser(bookmarks=..., prefs=...,
  extensions=[...])`.
- Nếu Samsung Internet dùng scheme khác `chrome://`, chỉ cần sửa `pages.scheme` trong config.
- Các test mẫu đã chạy thật trên Chromium 141 (Linux, headless). Selector của Samsung có
  thể khác: khi chạy lần đầu trên bản Samsung, sửa trong `sbtest/pages/` và `config/native_ui.yaml`.
  Phần native (pywinauto) chưa được chạy trên Windows thật.
