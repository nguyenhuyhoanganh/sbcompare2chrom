# sbtest: Auto test sanity cho Samsung Internet (Windows)

Mỗi lần merge một bản Chromium mới vào Samsung Internet, bộ test này chạy lại các sanity
test cơ bản theo từng feature: add-ons, bookmarks, downloads, history, duyệt web chung.

- **Lớp web (Selenium):** điều khiển nội dung trang, kể cả các trang nội bộ `internet://`.
- **Lớp native (pywinauto):** điều khiển phần không phải web: toolbar, menu, bubble/prompt,
  dialog Open/Save As/chọn thư mục, File Explorer, print, toast của Windows, phím tắt, chuột thật.
- **Skill cho agent** (`.agents/skills/`, chuẩn Agent Skills) để agent tự viết, chạy và báo cáo test.
  Quy tắc chung cho mọi agent ở `AGENTS.md`.

## Cấu trúc

```
config/                      cấu hình
  default.yaml               attach mode, điều hướng chrome:// (thanh địa chỉ hiện internet://), timeout, paths, report, proxy
  native_ui.yaml             tên logic -> tiêu chí UIA của UI Samsung (toolbar, menu, toast, dialog)
  local.yaml                 cấu hình riêng của máy (đường dẫn exe, proxy), không đưa lên git
sbtest/                      framework (package Python)
  browser/                   khởi động browser, profile, version Chromium, chromedriver
  web/                       lớp web: locator (xuyên Shadow DOM), wait, action, đọc nội dung, tab, iframe
  native/                    lớp native: UI của browser, dialog Windows, Explorer, toast
  pages/                     page object các trang internet:// (bookmarks, history, downloads, add-ons)
  data/  server/             đọc/sinh dữ liệu test, web server cục bộ
  reporting/                 bằng chứng lỗi, results.json, báo cáo, thư mục cho Confluence
  tools/                     doctor, dom, uia_dump, explore, coverage, case_overview, report
tests/
  features/                  test sản phẩm, mỗi feature một thư mục: addons/ bookmarks/ downloads/ history/ general/
  framework/                 unit test của framework (không cần browser)
cases/                       test case dạng tài liệu, mỗi feature một thư mục + TESTCASES.md (bảng tổng hợp) + _inbox/
resources/                   tài nguyên test
  data/                      bookmarks.yaml, addons.yaml (seed bookmark, add-on mẫu, id Web Store)
  extensions/                add-on mẫu (unpacked)
  profiles/                  profile mẫu (tuỳ chọn)
  site/                      trang web test cục bộ (download, form, dialog...)
docs/SETUP.md                cài đặt máy Windows mới, xử lý khi Samsung merge Chromium mới
drivers/                     chromedriver cho máy offline (git-ignored, framework tự tải)
.agents/skills/              skill cho agent: intake, explore, author, run (bản gốc, chỉ sửa ở đây)
.claude/skills/              bản sao cho Claude Code, sinh bằng python -m sbtest.tools.sync_skills
AGENTS.md  CLAUDE.md         quy tắc cho agent (CLAUDE.md chỉ import AGENTS.md)
run.py  setup.bat            chạy test / cài đặt lần đầu
```

## Cài đặt (Windows)

Hướng dẫn đầy đủ cho máy mới (yêu cầu, proxy, bộ gõ, kiểm tra, chạy, báo cáo): **[docs/SETUP.md](docs/SETUP.md)**. Tóm tắt:

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

Kết quả nằm ở `artifacts\runs\<thời gian>\`. Chỉ giữ lần chạy mới nhất: mỗi lần chạy, `run.py` xoá
các lần trước (kèm log chromedriver và profile còn sót). Muốn giữ nhiều hơn: `--keep-runs N`
hoặc `report.keep_runs` trong `config\local.yaml` (0 = giữ tất cả).

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
Bảng tổng hợp mọi case kèm kết quả gần nhất: `python -m sbtest.tools.case_overview` -> `cases\TESTCASES.md`.

Test native cần desktop Windows đang mở và không bị khoá. Đừng chạy qua RDP đang thu nhỏ.

## Làm việc với agent (Claude Code chạy trên máy Windows có bản build)

- *"Đọc test case add-ons ở <link Confluence> và tự động hoá"*:
  - `sbtest-intake` đọc link qua skill Confluence và chuẩn hoá thành `cases\addons\*.md`.
  - `sbtest-author` tự mở browser, khám phá UI, sửa page object Samsung, viết test vào
    `tests\features\addons\` rồi chạy cho tới khi pass ổn định.
- *"Viết test: mở add-on X từ toolbar, popup phải hiện thông tin Y"*: `sbtest-explore` khám phá UI
  thật (ảnh + dump), tra bảng action (`.agents\skills\sbtest-explore\references\action-catalog.md`),
  viết case + script, chạy tới khi ổn định.
- *"Chạy sanity cho bản build mới và đẩy report lên Confluence"*: `sbtest-run` chạy test,
  phân loại lỗi rồi tạo trang Confluence từ thư mục `confluence\`.

## Ghi chú

- Đã chạy thật trên Windows 11 (arm64) với **Samsung Browser 31.0.0.55 (Chromium 148)** bản
  public (browser.samsung.com): 73 case, tất cả pass. Bảng đầy đủ: `cases\TESTCASES.md`.
- Bản build 155: BM-113/114/116 (sao bookmark thành `PageActionView`, chỉ hiện khi omnibox không
  focus) và DL-003 (bubble Downloads che nút Clear all) đã sửa theo, chưa chạy lại trên 155.
- Settings chưa có test (các case cũ chưa kiểm chứng trên Samsung nên đã bỏ). Muốn thêm, dùng
  skill `sbtest-explore` để viết từ đầu trên Samsung.
- Case chia theo feature và theo khu vực: `cases\<feature>\<khu vực>.md` (trang quản lý,
  `sanity.md`, `toolbar.md` cho icon/popup trên toolbar), test tương ứng
  `tests\features\<feature>\test_<feature>_<khu vực>.py` - chạy riêng một phần bằng `--feature`.
- Test native điều khiển chuột/bàn phím thật: đừng dùng máy trong lúc chạy (một cửa sổ khác nhảy
  lên trước sẽ nhận phím gõ và làm fail các bước dialog).
- Khác biệt Samsung cần biết (chi tiết trong `.agents\skills\sbtest-author\references\feature-notes.md`):
  - WebDriver phải mở `chrome://...`, thanh địa chỉ hiển thị `internet://...`.
  - chromedriver không tự khởi chạy được Samsung, nên framework dùng `browser.mode: attach`.
  - Profile mới hiện bubble "Samsung Browser has been updated."; framework tự đóng nó ngay khi mở browser.
