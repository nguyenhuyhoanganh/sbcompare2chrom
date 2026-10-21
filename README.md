# sbtest: Auto test sanity cho Samsung Internet (Windows)

Mỗi lần merge một bản Chromium mới vào Samsung Internet, bộ test này chạy lại các sanity
test cơ bản theo từng feature: add-ons, bookmarks, downloads, history, duyệt web chung.

- **Lớp web (Selenium):** điều khiển nội dung trang, kể cả các trang nội bộ `internet://`.
- **Lớp native (pywinauto):** điều khiển phần không phải web: toolbar, menu, bubble/prompt,
  dialog Open/Save As/chọn thư mục, File Explorer, print, toast của Windows, phím tắt, chuột thật.
- **Skill cho agent** (`.claude/skills/`) để agent tự viết, chạy và báo cáo test.

## Cấu trúc

```
run.py                       chạy test (feature, case, sanity)
setup.bat                    cài đặt lần đầu trên Windows
config/
  default.yaml               cấu hình (attach mode, điều hướng chrome:// - thanh địa chỉ hiện internet://)
  native_ui.yaml             tên logic -> tiêu chí UIA của UI Samsung (toolbar, menu, bubble, dialog)
  local.yaml                 cấu hình riêng của máy (đường dẫn exe, proxy), không đưa lên git
sbtest/                      framework
  browser/                   khởi động browser, profile, version Chromium, chromedriver
  web/                       lớp web: locator (xuyên Shadow DOM), wait, action, đọc nội dung, tab, iframe
  native/                    lớp native: UI của browser, dialog Windows, Explorer, toast
  pages/                     page object các trang internet:// (bookmarks, history, downloads, add-ons)
  data/  server/             dữ liệu mẫu, web server local
  reporting/                 bằng chứng lỗi, results.json, báo cáo, thư mục cho Confluence
  tools/                     doctor, dom, uia_dump, explore, coverage, case_overview, report
tests/features/              test, mỗi feature một thư mục
  addons/  bookmarks/  downloads/  history/  general/
testcases/<feature>/*.md     test case dạng tài liệu, mỗi case có mã (ADD-101...)
test_site/  test_data/       trang web test local, add-on mẫu (.crx + unpacked), dữ liệu
framework_tests/             unit test của framework
```

## Cài đặt (Windows)

Hướng dẫn đầy đủ cho máy mới (yêu cầu, proxy, bộ gõ, kiểm tra, chạy, báo cáo): **[SETUP.md](SETUP.md)**. Tóm tắt:

```bat
setup.bat
notepad config\local.yaml        & rem browser.exe = <thư mục build>\SamsungInternet.exe
.venv\Scripts\activate
python -m sbtest.tools.doctor    & rem kiểm tra từng bước, ảnh chụp lưu ở artifacts\doctor\
```

Về chromedriver: framework tự dò version Chromium của exe rồi tải driver của Google qua proxy
(biến `HTTPS_PROXY`). Nếu driver của Google không nhận bản Samsung (lỗi `unrecognized Chrome
version`), hãy build `chromedriver` từ source fork rồi khai báo `browser.chromedriver`.

## Chạy

```bat
python run.py --all                               & rem toàn bộ tests\features
python run.py --feature addons                    & rem chỉ một phần: addons | bookmarks | downloads | history ...
python run.py --feature addons,bookmarks
python run.py --case ADD-001,DL-004
python run.py --sanity --reruns 1
python run.py --all --screenshot-steps            & rem chụp ảnh sau mỗi bước
python run.py --list                              & rem case nào đã được tự động hoá
```

Kết quả nằm ở `artifacts\runs\<thời gian>\`:

| | |
|---|---|
| `report\index.html` | **báo cáo sanity của bản build**: kết luận BUILD PASSED / FAILED, thông tin build (phiên bản Samsung, Chromium, máy, thời gian, phần được chạy), mỗi case một dòng: ID, tên + mô tả, các bước, kết quả mong đợi, kết quả (bước fail + lỗi nếu fail), ảnh chụp lúc kết thúc. Nén cả thư mục `report\` để gửi |
| `report\report.md` | cùng báo cáo dạng Markdown |
| `confluence\` | cùng báo cáo dạng trang Confluence (`page.storage.html` + `attachments\`), agent dùng skill Confluence để tạo trang và upload |
| `report.html` | report gốc của pytest |
| `failures\<test>\failure.txt` | case, bước fail, kết quả mong đợi, lỗi, phần tử đang thao tác |
| `failures\<test>\page.png` | ảnh tab, **phần tử lỗi được khoanh đỏ** |
| `failures\<test>\screen.png` | **toàn màn hình Windows**, thấy được cả dialog native |
| `failures\<test>\dom.txt`, `uia.txt` | cây DOM và cây UI native lúc fail |
| `steps\<test>\` | ảnh từng bước (khi chạy với `--screenshot-steps`) |
| `results.json`, `junit.xml` | kết quả dạng máy đọc |

Sinh lại báo cáo của một lần chạy (ví dụ sau khi sửa mô tả case): `python -m sbtest.tools.report [thư mục run] --open`.
Bảng tổng hợp mọi case kèm kết quả gần nhất: `python -m sbtest.tools.case_overview` -> `testcases\TESTCASES.md`.

Test native cần desktop Windows đang mở và không bị khoá. Đừng chạy qua RDP đang thu nhỏ.

## Làm việc với agent (Claude Code chạy trên máy Windows có bản build)

- *"Đọc test case add-ons ở <link Confluence> và tự động hoá"*:
  - `sbtest-intake` đọc link qua skill Confluence và chuẩn hoá thành `testcases\addons\*.md`.
  - `sbtest-author` tự mở browser, khám phá UI, sửa page object Samsung, viết test vào
    `tests\features\addons\` rồi chạy cho tới khi pass ổn định.
- *"Viết test: mở add-on X từ toolbar, popup phải hiện thông tin Y"*: `sbtest-explore` khám phá UI
  thật (ảnh + dump), tra bảng action (`.claude\skills\sbtest-explore\references\action-catalog.md`),
  viết case + script, chạy tới khi ổn định.
- *"Chạy sanity cho bản build mới và đẩy report lên Confluence"*: `sbtest-run` chạy test,
  phân loại lỗi rồi tạo trang Confluence từ thư mục `confluence\`.

## Ghi chú

- Đã chạy thật trên Windows 11 (arm64) với **Samsung Browser 31.0.0.55 (Chromium 148)** bản
  public (browser.samsung.com): 74 case, tất cả pass. Bảng đầy đủ: `testcases\TESTCASES.md`.
- Settings chưa có test (các case cũ chưa kiểm chứng trên Samsung nên đã bỏ). Muốn thêm, dùng
  skill `sbtest-explore` để viết từ đầu trên Samsung.
- Case chia theo feature và theo khu vực: `testcases\<feature>\<khu vực>.md` (trang quản lý,
  `sanity.md`, `toolbar.md` cho icon/popup trên toolbar), test tương ứng
  `tests\features\<feature>\test_<feature>_<khu vực>.py` - chạy riêng một phần bằng `--feature`.
- Test native điều khiển chuột/bàn phím thật: đừng dùng máy trong lúc chạy (một cửa sổ khác nhảy
  lên trước sẽ nhận phím gõ và làm fail các bước dialog).
- Khác biệt Samsung cần biết (chi tiết trong `.claude\skills\sbtest-author\references\feature-notes.md`):
  - WebDriver phải mở `chrome://...`, thanh địa chỉ hiển thị `internet://...`.
  - chromedriver không tự khởi chạy được Samsung, nên framework dùng `browser.mode: attach`.
  - Profile mới hiện bubble "Samsung Browser has been updated."; framework tự đóng nó ngay khi mở browser.
