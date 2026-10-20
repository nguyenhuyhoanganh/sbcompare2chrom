# sbtest: Auto test sanity cho Samsung Internet (Windows)

Mỗi lần merge một bản Chromium mới vào Samsung Internet, bộ test này chạy lại các sanity
test cơ bản theo từng feature: add-ons, bookmarks, downloads, history, settings, duyệt web chung.

- **Lớp web (Selenium):** điều khiển nội dung trang, kể cả các trang nội bộ `internet://`.
- **Lớp native (pywinauto):** điều khiển phần không phải web: toolbar, menu, bubble/prompt,
  dialog Open/Save As/chọn thư mục, File Explorer, print, toast của Windows, phím tắt, chuột thật.
- **Hai target:** `samsung` là sản phẩm cần test. `chrome` (Chrome for Testing, cùng nền
  Chromium) dùng làm bản tham chiếu, đã kiểm chứng.
- **Skill cho agent** (`.claude/skills/`) để agent tự viết, chạy và báo cáo test.

## Cấu trúc

```
run.py                       chạy test (target, suite, feature, case)
setup.bat                    cài đặt lần đầu trên Windows
config/
  default.yaml               cấu hình chung
  targets/samsung.yaml       internet://, page object Samsung, map UI native Samsung
  targets/chrome.yaml        chrome://, page object Chromium, map UI native Chrome
  native_ui/*.yaml           tên logic -> tiêu chí UIA (toolbar, dialog, prompt...)
  local.yaml                 cấu hình riêng của máy (đường dẫn exe, proxy), không đưa lên git
sbtest/                      framework
  browser/                   khởi động browser, profile, version Chromium, chromedriver
  web/                       lớp web: locator (xuyên Shadow DOM), wait, action, đọc nội dung, tab, iframe
  native/                    lớp native: UI của browser, dialog Windows, Explorer, toast
  pages/chromium/            page object các trang chrome:// (tham chiếu, đã kiểm chứng)
  pages/samsung/             page object các trang internet:// (kế thừa chromium, sửa phần khác)
  data/  server/             dữ liệu mẫu, web server local
  reporting/                 bằng chứng lỗi, results.json, thư mục report cho Confluence
  tools/                     doctor, dom, uia_dump, coverage, get_chrome, confluence_export
tests/
  features/                  test sản phẩm, mỗi feature một thư mục
    addons/  bookmarks/  downloads/  history/  settings/  general/
  reference/                 bộ thao tác mẫu trên Chrome (xem tests/reference/README.md)
    web/                     điều hướng, tab, input, chuột, phím, drag-drop, JS dialog, iframe, upload/download
    files/                   hộp Open, Save As, chọn thư mục, kéo file từ Explorer, Show in folder
    native/                  thanh địa chỉ, nút toolbar, menu, phím tắt, đăng nhập HTTP, quyền, print, toast
testcases/<feature>/*.md     test case dạng tài liệu, mỗi case có mã (ADD-001...)
test_site/  test_data/       trang web test local, add-on mẫu (.crx + unpacked), dữ liệu
framework_tests/             unit test của framework
```

## Cài đặt (Windows)

```bat
setup.bat
notepad config\local.yaml        & rem targets.samsung.browser.exe = <thư mục build>\SamsungInternet.exe
.venv\Scripts\activate
python -m sbtest.tools.doctor    & rem kiểm tra từng bước, ảnh chụp lưu ở artifacts\doctor\
```

Bản tham chiếu Chrome dùng `python -m sbtest.tools.get_chrome`. Lệnh này tải Chrome for
Testing cùng major Chromium với bản Samsung, kèm chromedriver khớp version, rồi
`python -m sbtest.tools.doctor --target chrome`.

Về chromedriver: framework tự dò version Chromium của exe rồi tải driver của Google qua proxy
(biến `HTTPS_PROXY`). Nếu driver của Google không nhận bản Samsung (lỗi `unrecognized Chrome
version`), hãy build `chromedriver` từ source fork rồi khai báo `browser.chromedriver`.

## Chạy

```bat
python run.py --all                               & rem Samsung, toàn bộ tests\features
python run.py --feature addons,bookmarks
python run.py --case ADD-001,DL-004
python run.py --sanity --reruns 1
python run.py --all --screenshot-steps            & rem chụp ảnh sau mỗi bước
python run.py --target chrome --suite reference   & rem bộ thao tác mẫu trên Chrome
python run.py --list                              & rem case nào đã được tự động hoá
```

Kết quả nằm ở `artifacts\runs\<thời gian>\`:

| | |
|---|---|
| `report.html` | report HTML, có nhúng ảnh lỗi |
| `failures\<test>\failure.txt` | case, bước fail, kết quả mong đợi, lỗi, phần tử đang thao tác |
| `failures\<test>\page.png` | ảnh tab, **phần tử lỗi được khoanh đỏ** |
| `failures\<test>\screen.png` | **toàn màn hình Windows**, thấy được cả dialog native |
| `failures\<test>\dom.txt`, `uia.txt` | cây DOM và cây UI native lúc fail |
| `steps\<test>\` | ảnh từng bước (khi chạy với `--screenshot-steps`) |
| `results.json`, `junit.xml` | kết quả dạng máy đọc |
| `confluence\` | trang report đã soạn sẵn (`page.storage.html`/`page.md` + `attachments\`), dùng skill Confluence để tạo trang và upload |

Test native cần desktop Windows đang mở và không bị khoá. Đừng chạy qua RDP đang thu nhỏ.

## Làm việc với agent (Claude Code chạy trên máy Windows có bản build)

- *"Đọc test case add-ons ở <link Confluence> và tự động hoá"*:
  - `sbtest-intake` đọc link qua skill Confluence và chuẩn hoá thành `testcases\addons\*.md`.
  - `sbtest-author` tự mở browser, khám phá UI, sửa page object Samsung, viết test vào
    `tests\features\addons\` rồi chạy cho tới khi pass ổn định.
- *"Chạy sanity cho bản build mới và đẩy report lên Confluence"*: `sbtest-run` chạy test,
  phân loại lỗi rồi tạo trang Confluence từ thư mục `confluence\`.

## Ghi chú

- Page object Samsung hiện **kế thừa nguyên bản Chromium và chưa được kiểm chứng**. Agent sửa
  từng trang khi viết test cho trang đó.
- Đã chạy thật trên Chromium 141 (Linux): test feature và phần web của bộ tham chiếu.
  Các test native/files (Windows) đã viết sẵn nhưng chưa được chạy trên Windows thật.
