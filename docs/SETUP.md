# Cài đặt sbtest trên một máy Windows mới

Làm một lần cho mỗi máy, mất khoảng 15 phút. Sau đó mỗi lần có bản build mới chỉ cần
trỏ `config\local.yaml` sang exe mới rồi chạy test (mục 6).

## 1. Máy cần có

| Thứ | Yêu cầu | Ghi chú |
|---|---|---|
| Windows | 10 (1809+) hoặc 11, x64 hoặc ARM64 | Samsung Internet chỉ có bản Windows |
| Python | 3.10 trở lên | Cài từ python.org, **tích "Add python.exe to PATH"**. Đã chạy thật với 3.14 |
| Git | bản bất kỳ | để clone repo |
| Samsung Internet / Samsung Browser | bản build cần test | build nội bộ (thư mục `out\Release`) hoặc bản cài từ browser.samsung.com |
| Mạng | lần đầu cần ra internet (qua proxy công ty cũng được) | để tải gói Python và chromedriver. Sau đó test chạy offline, trừ case cài add-on từ Web Store |
| Màn hình | desktop Windows đang mở, không khoá | test native điều khiển chuột/bàn phím thật |

Không cần quyền admin, trừ khi phải cài Samsung Browser bản public.

## 2. Lấy code và cài môi trường

```bat
git clone https://github.com/nguyenhuyhoanganh/sbcompare2chrom.git
cd sbcompare2chrom
git checkout blank
rem chỉ khi đi qua proxy công ty:
set HTTPS_PROXY=http://proxy.company.com:8080
setup.bat
```

`setup.bat` sẽ:
- tự tìm Python thật (`py -3`, sau đó tới `python`),
- tạo `.venv`, cài `requirements.txt`,
- tạo `config\local.yaml` từ `config\local.example.yaml`.

Báo `Python 3.10+ not found`? Cài Python từ python.org. Nếu đã cài mà vẫn báo, tắt alias
`python.exe` của Microsoft Store: Settings > Apps > Advanced app settings > App execution aliases.

## 3. Khai báo bản build cần test

Mở `config\local.yaml` (file này chỉ ở trên máy, không commit) và sửa đường dẫn exe:

```yaml
browser:
  exe: 'C:\build\out\Release\SamsungInternet.exe'
  # bản public: 'C:\Program Files\Samsung\Internet\Application\samsunginternet.exe'
network:
  # download_proxy: http://proxy.company.com:8080   # nếu không dùng biến HTTPS_PROXY
```

Không cần chỉnh gì thêm:
- **chromedriver**: framework tự đọc version Chromium của exe rồi tải chromedriver khớp
  version vào `drivers\<major>\` (qua proxy nếu có). Máy không ra mạng được thì chép sẵn
  `drivers\<major>\chromedriver.exe` từ một máy khác vào. Nếu chromedriver của Google không
  nhận bản fork, build `chromedriver` từ source fork rồi khai báo `browser.chromedriver`.
- Cấu hình sẵn chế độ `attach` và điều hướng `chrome://` (thanh địa chỉ vẫn hiển thị
  `internet://`), xem `config\default.yaml`.
- `config\local.yaml` theo mẫu cũ (`targets: samsung: browser: exe: ...`) vẫn dùng được.

## 4. Chuẩn bị Windows trước khi chạy

| Việc | Vì sao |
|---|---|
| **Tắt bộ gõ tiếng Việt** (UniKey, EVKey, OpenKey... chuyển sang chế độ English) và để bàn phím English (US) | test gõ đường dẫn, tên bằng bàn phím thật; Telex/VNI sẽ biến đổi chữ được gõ |
| Không đụng chuột/bàn phím, không để cửa sổ khác nhảy lên trước trong lúc chạy | cửa sổ khác nhận phím gõ, làm fail các bước có dialog (đã gặp thật) |
| Tắt màn hình khoá / sleep trong thời gian chạy | máy khoá thì UI Automation không thấy cửa sổ |
| Không chạy qua RDP đang thu nhỏ | cửa sổ RDP thu nhỏ = desktop không vẽ, test native fail |
| Tắt Focus Assist / Do not disturb | case thông báo web cần thấy toast |
| Đóng các cửa sổ Samsung Browser đang mở bằng tay | tránh lẫn với browser của test (test dùng profile riêng nên không mất dữ liệu của bạn) |

## 5. Kiểm tra máy

```bat
.venv\Scripts\python -m sbtest.tools.doctor
```

Phải đạt **0 failure**. Mỗi dòng `[FAIL]`/`[WARN]` có kèm cách sửa, và ảnh chụp lưu ở
`artifacts\doctor\`. Doctor kiểm tra:
- gói Python và bàn phím/bộ gõ,
- exe, version Chromium, chromedriver,
- khởi động browser, các trang nội bộ,
- UI native của browser.

Một số cảnh báo thường gặp:

| Cảnh báo | Sửa |
|---|---|
| `input method: UniKey running` | tắt UniKey (hoặc chuyển English) trước khi chạy |
| `browser exe ... not found` | sửa đường dẫn ở mục 3 |
| `browser start: ReadTimeoutError` | browser không cho chromedriver kết nối: kiểm tra `browser.mode: attach` (mặc định), đóng hết Samsung đang mở |
| `page chrome://...` WARN | bản build không mở được trang qua WebDriver: xem `pages.scheme` |
| `native ui_map ...: not found` | giao diện bản build khác bản đã kiểm chứng: báo cho agent (skill `sbtest-explore`) cập nhật `config\native_ui.yaml` |

## 6. Chạy và lấy báo cáo

```bat
.venv\Scripts\activate
python run.py --sanity                         & rem lượt nhanh (case đánh dấu sanity)
python run.py --all                            & rem toàn bộ test của Samsung
python run.py --feature addons                 & rem chỉ một phần: addons | bookmarks | downloads | history
python run.py --case BM-113,DL-104             & rem vài case
```

Kết thúc mỗi lần chạy, màn hình in ra đường dẫn báo cáo:
`artifacts\test-results\report\index.html`. Thư mục `artifacts\test-results\` chỉ chứa lần chạy
mới nhất: lần chạy sau làm trống nó trước (cần giữ thì chép đi chỗ khác). Báo cáo gồm:
- kết luận **BUILD PASSED / FAILED**, thông tin bản build và máy chạy,
- mỗi case một dòng: các bước, kết quả mong đợi, kết quả thực tế, ảnh chụp.

Nén thư mục `report\` lại là gửi đi được. Thư mục `confluence\` cạnh đó là cùng báo cáo
dạng trang Confluence. Sinh lại báo cáo: `python -m sbtest.tools.report --open`.

Thời gian tham khảo: khoảng 8-9 phút cho 4 phần add-ons, bookmarks, downloads, history.

## 7. Dùng với agent (Claude Code hoặc agent khác)

Mở agent trong thư mục repo trên chính máy này.
- Claude Code tự nạp skill từ `.claude\skills\` và quy tắc từ `CLAUDE.md`.
- Cline nạp skill từ `.claude\skills\` và quy tắc từ `AGENTS.md`; gọi skill bằng `/` (ví dụ
  `/sbtest`).
- Agent khác theo chuẩn Agent Skills đọc `.agents\skills\` và `AGENTS.md`. Agent không tự nạp
  skill thì bảo nó đọc `AGENTS.md` trước.
- Sửa skill thì chỉ sửa trong `.agents\skills\`, rồi chạy `python -m sbtest.tools.sync_skills`
  để cập nhật bản sao cho Claude Code.

Ví dụ:
- `/sbtest`: agent hỏi phần cần test, đường dẫn exe, chỗ đăng Confluence, rồi tự
  chạy doctor, chạy test, phân loại lỗi và (sau khi bạn xác nhận) tạo trang Confluence bằng skill
  `managing-jira-confluence`.
- "Chạy sanity cho bản build mới và đẩy báo cáo lên Confluence" (skill `sbtest-run`).
- "Viết test: mở add-on X từ toolbar, popup phải hiện Y" (skill `sbtest-explore`).
- "Đọc test case ở <link Confluence> và tự động hoá" (skill `sbtest-intake`, rồi `sbtest-explore`).

Để đẩy lên Confluence, agent cần skill/connector Confluence của bạn, cùng space hoặc trang
cha nơi đặt báo cáo.

## 8. Khi Samsung merge Chromium mới (141 -> 143 -> 151 ...)

Không phải cập nhật chromedriver bằng tay. Mỗi lần chạy, framework làm như sau:
1. đọc version Chromium thật của exe (khởi động exe một lần, đọc `/json/version`). Kết quả
   được cache theo đường dẫn + kích thước + thời gian sửa của exe, nên exe mới (kể cả cùng
   đường dẫn) luôn được dò lại. Thường lấy trường `Browser` (vd. `Chrome/148.0.7778.217`);
   một số bản Samsung lại ghi version sản phẩm vào đó (vd. `Chrome/31.0.1.21` trên bản
   Chromium 157), khi đó lấy số Chromium trong `User-Agent` (`Chrome/157.0.0.0`);
2. dùng `drivers\<major>\chromedriver.exe` nếu đã có, nếu chưa thì tải bản khớp major từ
   Chrome for Testing (có đủ mọi milestone, kể cả bản beta/canary). Chỉ cần khớp **major**
   (vd. driver 148.0.7778.178 chạy tốt với Samsung 148.0.7778.217).
   Framework tự so major của driver với Chromium và báo rõ khi lệch; bước kiểm tra riêng của
   chromedriver được tắt (`--disable-build-check`) vì nó đọc nhầm trường `Browser` ở trên.

Chỉ phải động tay khi:
- trong `config\local.yaml` có ghim `browser.chromedriver` hoặc `browser.chromium_version`:
  cập nhật hoặc xoá hai dòng đó;
- máy không ra được mạng: chép `drivers\<major mới>\chromedriver.exe` từ một máy khác vào;
- chromedriver của Google không nhận bản fork (doctor báo lỗi ở bước `browser start`):
  build `chromedriver` từ source fork rồi khai báo `browser.chromedriver`.

Sau mỗi lần merge: chạy `doctor` để kiểm tra, rồi `python run.py --all`. Test fail vì UI
đổi (đổi nhãn, đổi DOM) thì là việc của page object / ui map, không phải của driver; agent
xử lý theo skill `sbtest-run` (phân loại lỗi) và `sbtest-explore`.

## 9. Cập nhật

```bat
git pull
setup.bat                                      & rem cài thêm gói mới nếu requirements.txt đổi
.venv\Scripts\python -m sbtest.tools.doctor
```
