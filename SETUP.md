# Hướng dẫn cài đặt & vận hành A–Z

Từ máy trắng đến báo cáo đầu tiên. Mọi số liệu dưới đây đo trên lần chạy thật (macOS, Python 3.14, mạng công ty bình thường).

---

## 0. Hệ điều hành nào chạy được

| Nền tảng | Trạng thái | Đã kiểm chứng thế nào |
|---|---|---|
| **macOS** | Chạy đầy đủ | Toàn bộ pipeline, Python 3.14.6 |
| **Linux / Ubuntu** | Chạy đầy đủ | Ubuntu 24.04 + Python 3.12 và Debian + Python 3.9 trong Docker: 58/58 test, `check`, và một lần `run` thật ra **kết quả trùng khớp macOS từng con số** |
| **Windows** | Chạy được | Không chạy trực tiếp được ở đây; đã kiểm định từng cơ chế Windows gây vỡ bằng dữ liệu thật — xem bên dưới |

### Về Windows — đã kiểm những gì

Không có mã phụ thuộc POSIX (không `fork`, không quyền file, không symlink, không `os.uname`). Các điểm Windows thường làm vỡ công cụ Python đã được kiểm riêng:

- **Encoding console** — đây là lỗi thật đã tìm ra và sửa. Windows chỉ dùng UTF-8 cho console thật; hễ output bị chuyển hướng ra file/pipe là rơi về cp1252, mà báo cáo chứa `→` và `·`. Trước khi sửa, `chromedrift report ... > report.md` chết với `'charmap' codec can't encode character '\u2192'`, và cả `chromedrift check` cũng chết vì chính output của nó có dấu `—`. Nay CLI ép stdout/stderr về UTF-8 khi khởi động, và có test hồi quy chạy CLI dưới `PYTHONIOENCODING=cp1252`.
- **Đọc file UTF-8** — mọi `open()` trong mã đều khai `encoding=` tường minh, nên không rơi về cp1252 khi đọc mã nguồn Chromium.
- **Ngữ nghĩa đường dẫn** — chạy trực tiếp qua module `ntpath` (module Windows dùng): `basename` xử lý đúng dấu `/`, chuẩn hoá `relpath` đúng, và chốt chặn path-traversal khi giải nén tarball vẫn chặn được `../../../etc/passwd` → `C:\etc\passwd`.
- **Giới hạn 260 ký tự (MAX_PATH)** — đường dẫn tương đối dài nhất trong 5.310 file cache đo được là **142 ký tự**, còn dư ~118 ký tự cho thư mục gốc. Đủ thoải mái, nhưng đừng đặt dự án ở chỗ quá sâu; nếu gặp lỗi, xem §9.
- **Tên file cấm / đụng độ hoa-thường / ký tự cấm** — quét toàn bộ 5.310 file: **không có** tên `CON`/`PRN`/`AUX`/`NUL`/`COM*`/`LPT*`, không có cặp file chỉ khác nhau hoa-thường, không có ký tự `: * ? " < > |`.

Trên Windows dùng `py -3` hoặc `python` thay cho `python3`:

```powershell
py -3 -m chromedrift check
```

Nếu tổ chức bạn triển khai Windows rộng rãi, cách chắc chắn nhất vẫn là chạy thử `py -3 -m chromedrift check` rồi `python3 -m unittest discover -s tests` trên đúng máy đó — mất 10 giây và cho câu trả lời dứt khoát.

---

## 1. Cần gì để chạy

| Hạng mục | Yêu cầu | Ghi chú |
|---|---|---|
| Python | **3.9 trở lên** | Không dùng cú pháp 3.10+ (không `match`, không `X \| Y` runtime). Đã chạy trên 3.14.6. |
| Thư viện ngoài | **Không có** | Chỉ stdlib. Không cần `pip install`, không cần venv, không cần quyền admin. |
| Đĩa trống | **~50 MB** cho 2 phiên bản | Cache thật đo được: 43 MB (26 MB source + 17 MB snapshot JSON). |
| RAM | ~500 MB lúc cao điểm | Snapshot 21.000 facts giữ trong bộ nhớ. |
| Mạng | 3 host HTTPS (xem §2) | Hoặc bỏ hẳn mạng nếu dùng checkout nội bộ, xem §8. |
| Chromium checkout | **Không cần** | Có thì tốt hơn (`--local-src`), không có vẫn chạy đủ. |

Tuỳ chọn: nếu môi trường có sẵn `tiktoken` thì công cụ tự dùng để đếm token chính xác; không có thì dùng ước lượng nội bộ. Không cần cài.

### Các host cần mở

| Host | Dùng để làm gì | Bắt buộc? |
|---|---|---|
| `chromium.googlesource.com` | Tải mã nguồn Chromium theo tag | **Có** |
| `chromiumdash.appspot.com` | Phân giải `143` → `143.0.7499.194` | Không, nếu bạn luôn ghi phiên bản đầy đủ |
| `chromestatus.com` | Tóm tắt tính năng + link spec | Không, bỏ bằng `--no-enrich` |
| Endpoint AI nội bộ của bạn | Tầng phân tích | Không, bỏ bằng `--no-ai` |

---

## 2. Cài đặt

Không có bước build. Chỉ cần chép thư mục sang máy đích:

```bash
# Từ máy này
tar czf chromedrift.tgz chromedrift/ config/ examples/ tests/ README.md SETUP.md

# Trên máy đích
tar xzf chromedrift.tgz
cd <thư-mục-vừa-giải-nén>
python3 -m chromedrift --version      # kỳ vọng: 0.1.0
```

Nếu công ty có Git nội bộ thì `git clone` rồi chạy luôn, không có bước cài đặt nào.

---

## 3. Kiểm tra máy trước khi chạy

Đây là bước nên làm đầu tiên trên mọi máy mới. Nó kiểm tra tất cả những thứ thường hỏng, một lượt, thay vì để bạn phát hiện từng cái một sau 2 phút chạy:

```bash
python3 -m chromedrift check
```

Kết quả mong đợi:

```
python
  [OK  ] version 3.14.6
cache directory
  [OK  ] /path/.chromedrift-cache writable — 68 GB free
network
  [OK  ] gitiles (source) — HTTP 200
  [OK  ] chromiumdash (version resolution) — HTTP 200
  [OK  ] chromestatus (enrichment, optional) — HTTP 200

ready
```

Kiểm luôn cả hồ sơ và endpoint AI (lệnh sẽ **gọi thử một request thật** tới model):

```bash
python3 -m chromedrift check \
  --profile config/sb-profile.example.json5 \
  --llm config/llm.example.json5
```

Thoát code `0` = sẵn sàng, `1` = có dòng FAIL cần xử lý. Dùng được trong CI làm bước tiền kiểm.

---

## 4. Chạy lần đầu

### 4a. Chạy nhanh để xác nhận đường ống (~10 giây)

```bash
python3 -m chromedrift run 139.0.7258.155 143.0.7499.194 \
  --target-set minimal --no-ai --no-enrich
```

`minimal` chỉ tải 3 file (~300 KB) — đủ để xác nhận đường ống thông suốt.

### 4b. Chạy đầy đủ (~2 phút lần đầu, ~5 giây các lần sau)

```bash
python3 -m chromedrift run 139.0.7258.155 143.0.7499.194 \
  --profile config/sb-profile.example.json5 \
  --no-ai
```

Đo thật trên lần chạy nguội: **1 phút 59 giây**, tải 43 MB, trích 21.595 facts từ 2.513 file, sinh 3.120 thay đổi ngữ nghĩa.

Lần chạy sau với cùng cặp tag là **cache hit**, gần như tức thì. Tag đã phát hành thì nội dung không bao giờ đổi, nên cache giữ vĩnh viễn — an toàn.

Kết quả nằm trong `out/`:

| File | Kích thước | Dùng khi nào |
|---|---|---|
| `report.md` | ~46 KB | Dán vào Jira/Confluence/MR |
| `report.html` | ~1.9 MB | Mở bằng browser, lọc & sắp xếp được, tự chứa hoàn toàn |
| `report.json` | ~2.8 MB | Đưa vào script, dashboard, hoặc so sánh giữa các kỳ |

`report.html` **không tải bất kỳ tài nguyên ngoài nào** — mở được trong mạng cách ly, gửi kèm mail được.

### Ghim phiên bản — quan trọng

`139` và `143` là phân giải **động** sang bản stable mới nhất *tại thời điểm chạy*. Điều này gây khác biệt thật:

```
143.0.7499.40   → ServiceWorkerAutoPreload = ENABLED
143.0.7499.194  → ServiceWorkerAutoPreload = DISABLED   (bị revert trong bản vá)
```

Cùng một lệnh `run 139 143` chạy cách nhau vài tuần có thể cho kết luận khác nhau, và cả hai đều đúng. **Với báo cáo chính thức, luôn ghi phiên bản đầy đủ** (`139.0.7258.155`) và lưu lại trong ticket. Dùng số milestone trần chỉ khi thăm dò.

---

## 5. Cấu hình hồ sơ downstream — phần quan trọng nhất

Đây là việc duy nhất bắt buộc phải làm nghiêm túc. Chất lượng cột **Must fix** tỉ lệ thuận trực tiếp với file này. Không có nó, công cụ chỉ biết "Chromium đổi gì", không biết "đổi đó có đụng tới ta không".

```bash
cp config/sb-profile.example.json5 config/sb-profile.json5
```

Chọn nguồn bằng chứng phù hợp với cách đội bạn quản lý fork (kết hợp được nhiều nguồn):

### Cách A — có thư mục patch (phổ biến nhất với vendor fork)

```json5
{
  patch_dirs: ["/work/sbrowser/patches"],
}
```

Đọc mọi `.patch`/`.diff`, lấy **cả đường dẫn lẫn identifier trong thân hunk**. Identifier mới là bằng chứng có giá trị: `content_features.cc` khai báo gần 200 feature, nên biết bạn vá *file* đó gần như vô nghĩa; biết bạn động vào `kServiceWorkerAutoPreload` thì rất có nghĩa.

### Cách B — fork toàn bộ source trong git

```json5
{
  git: { repo: "/work/sbrowser/src", upstream_ref: "139.0.7258.155" },
}
```

Chạy `git diff --name-only <upstream_ref>`. Cần `git` trong PATH và `upstream_ref` phải tồn tại trong repo đó.

### Cách C — quét mã riêng của bạn (bắt được thứ patch bỏ sót)

```json5
{
  source_roots: ["/work/sbrowser/sbrowser_chrome", "/work/sbrowser/sbrowser_java"],
}
```

Quét mã của bạn tìm tham chiếu tới tên feature/switch/pref của Chromium. Bắt được code *đọc* một feature mà không hề vá file khai báo nó — trường hợp cách A và B đều bỏ lọt.

### Cách D — danh sách tự duy trì

```json5
{
  modified_paths: [
    "content/browser/renderer_host/render_widget_host_view_aura.cc",
    "media/base/win/",              // dấu / cuối = khớp theo tiền tố
  ],
  symbols: ["BackForwardCache", "kBackForwardCache"],
}
```

### Khai báo `areas`

Đây là thứ khiến finding **tự định tuyến về đúng đội**. `weight` (0–100) vào thẳng điểm số; `owner` hiện trong báo cáo:

```json5
areas: [
  { id: "media", title: "Video & media", weight: 90, owner: "media-team",
    paths: ["media/", "content/browser/media/"],
    symbols: ["Media", "Video", "Codec"] },
]
```

`symbols` ở đây là **khớp chuỗi con**, không phải khớp chính xác — `"Audio"` sẽ bắt `RestrictOwnAudio`. Cố ý như vậy để phân loại theo chủ đề, nhưng đừng đặt từ quá ngắn hoặc quá chung.

### Kiểm tra hồ sơ trước khi chạy thật

```bash
python3 -m chromedrift profile config/sb-profile.json5 --ref 143.0.7499.194
```

```
profile: Samsung Browser (platform windows)
  areas:            7
  patched files:    3
  symbols:          11
    symbols_from_patches: 7
```

Nếu `symbols: 0` thì **không mục nào lên được Must fix** — công cụ sẽ cảnh báo. Xem §9 để xử lý.

---

## 6. Cấu hình AI nội bộ

```bash
cp config/llm.example.json5 config/llm.json5
```

```json5
{
  provider: "openai",                        // endpoint tương thích OpenAI
  base_url: "http://ai-gateway.noi-bo/v1",   // KHÔNG kèm /chat/completions
  model: "ten-model-cua-ban",
  api_key_env: "CHROMEDRIFT_LLM_KEY",
  context_window: 200000,
  max_output_tokens: 8000,
  max_requests: 40,
}
```

```bash
export CHROMEDRIFT_LLM_KEY="..."       # không bao giờ ghi key vào file config
python3 -m chromedrift check --llm config/llm.json5      # gọi thử 1 request
```

Ba provider:

- `openai` — mọi endpoint `/chat/completions` tương thích: vLLM, TGI, Ollama, gateway nội bộ
- `anthropic` — Messages API
- `echo` — **không chạm mạng**, trả stub tất định. Dùng để phát triển/demo offline

`context_window` phải khớp model thật. Khai quá lớn → request bị từ chối vì quá dài. Khai quá nhỏ → tốn nhiều request không cần thiết. Với 200k, 150 findings + 100 mục ngữ cảnh chromestatus gói trong **1 request ~26k token**.

`max_requests: 40` là chốt chặn cứng để cấu hình sai không lặng lẽ biến thành hàng trăm request. Chạy bình thường chỉ tốn 2.

Response được cache theo `hash(model + prompt)` trong `.chromedrift-cache/ai/`. Sửa prompt rồi chạy lại **không tốn thêm request nào** cho phần không đổi.

---

## 7. Đọc kết quả

```
must fix:      4     ← ta có bằng chứng phụ thuộc VÀ nó đã đổi. Coi như có việc.
needs review: 432    ← hoặc ta có đụng, hoặc mức độ đủ nghiêm trọng để xác nhận
opportunity: 1399    ← năng lực mới có thể lấy về
fyi:        1285     ← ghi nhận cho đủ
```

Đọc theo thứ tự: **Must fix → Needs review → Opportunity**. `fyi` chỉ tra khi cần.

Mọi điểm số đều có lý do đọc được, và bạn nên cãi lại khi thấy sai:

```
base severity 75 (modified base_feature)
  | +12 we patch 1 of the declaring file(s): content/public/common/content_features.cc
  | +30 our source references ServiceWorkerAutoPreload, kServiceWorkerAutoPreload
  | +16 owned area 'Video & media playback' (weight 80)
```

Muốn chỉnh mức độ ưu tiên thì sửa `weight` trong `areas`, hoặc sửa bảng `BASE_SEVERITY` / `SIGNAL_SEVERITY` trong `chromedrift/diff.py`. Cả hai đều là dữ liệu thuần, không phải logic.

### Nếu tầng AI hỏng

Báo cáo sẽ nói thẳng ngay dòng đầu:

> **The AI stage did not run.** 1 request(s) failed against provider `openai`… Every verdict below is empty for that reason, not because nothing needs attention.

Cột verdict rỗng vì AI không chạy trông **y hệt** kết quả sạch. Nên tình trạng này luôn được ghi rõ trước mọi finding. Phần diff và chấm điểm vẫn đầy đủ giá trị mà không cần AI.

---

## 8. Môi trường đặc biệt

### Sau proxy công ty

`urllib` tự đọc biến môi trường:

```bash
export HTTPS_PROXY=http://proxy.noi-bo:8080
export NO_PROXY=localhost,127.0.0.1,.noi-bo
python3 -m chromedrift check          # sẽ in ra proxy đang dùng
```

### Proxy có chặn/giải mã TLS

Nếu gặp lỗi `CERTIFICATE_VERIFY_FAILED`, trỏ Python tới CA nội bộ:

```bash
export SSL_CERT_FILE=/etc/ssl/certs/ca-noi-bo.pem
export REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-noi-bo.pem
```

### Mạng cách ly hoàn toàn (không ra được internet)

Hai lựa chọn:

**1. Dùng checkout/mirror nội bộ** — không cần mạng ngoài chút nào:

```bash
python3 -m chromedrift run 139.0.7258.155 143.0.7499.194 \
  --local-src /mirror/chromium-139/src --no-enrich --no-ai
```

Lưu ý: `--local-src` áp cho **cả hai** ref, nên cách đúng là tạo snapshot từng bản riêng rồi mới diff:

```bash
python3 -m chromedrift snapshot 139.0.7258.155 --local-src /mirror/chromium-139/src
python3 -m chromedrift snapshot 143.0.7499.194 --local-src /mirror/chromium-143/src
python3 -m chromedrift run 139.0.7258.155 143.0.7499.194 --no-enrich   # dùng cache
```

**2. Chuyển cache từ máy có mạng sang.** Snapshot là JSON thuần, chép được:

```bash
# máy có mạng
python3 -m chromedrift snapshot 143.0.7499.194
# chép .chromedrift-cache/snapshots/*.json sang máy cách ly
```

---

## 9. Xử lý sự cố

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `error: could not resolve milestone 143` | Không vào được chromiumdash | Ghi phiên bản đầy đủ: `143.0.7499.194`. Tra ở chromiumdash.appspot.com/branches |
| `error: 404 …` khi snapshot | Tag không tồn tại | Kiểm tra tag có thật. Chỉ tag đã phát hành mới có |
| `GET failed after 4 attempts` | Mạng chập chờn / rate limit | Chạy lại — cache giữ phần đã tải xong. Nếu lặp lại, xem proxy ở §8 |
| `every target missing for <ref>` | Ref sai hoàn toàn | So lại chuỗi ref; `refs/tags/` được thêm tự động |
| `snapshot: N facts` với N rất nhỏ | `--local-src` trỏ sai chỗ | Phải trỏ vào thư mục **`src/`** của Chromium, nơi có `content/`, `third_party/` |
| `missing targets: 1` | File không tồn tại ở milestone đó | Bình thường, không phải lỗi. Chromium di chuyển file giữa các bản |
| `cannot diff snapshots built from different target sets` | Hai snapshot tạo bằng `--target-set` khác nhau | Chạy lại với cùng một target set, hoặc thêm `--refresh`. Công cụ từ chối thay vì so sánh nhầm — một bên thiếu hẳn nhiều loại fact thì mọi fact bên kia sẽ bị đọc thành "mới thêm" |
| `snapshot cache stale (schema N != M)` | Cache tạo bởi bản cũ hơn | Bình thường, tự dựng lại. Ý nghĩa của snapshot đã đổi nên bản cũ bị loại bỏ có chủ đích |
| **`must fix: 0`** | Hồ sơ chưa có bằng chứng | Chạy `chromedrift profile …`. Nếu `symbols: 0`, xem ô dưới |
| `symbols: 0` trong profile | `patch_dirs` sai, hoặc patch không chứa identifier Chromium | Kiểm tra thư mục có `.patch`/`.diff` thật. Token trong patch được lọc theo từ vựng Chromium, nên chỉ tên feature/switch/pref thật mới được giữ |
| `nodename nor servname provided` | `base_url` sai hoặc DNS không phân giải | Kiểm bằng `curl <base_url>/models`. Không kèm `/chat/completions` vào `base_url` |
| `HTTP 401` từ LLM | Chưa export key | `export CHROMEDRIFT_LLM_KEY=…`, tên biến khớp `api_key_env` |
| `HTTP 400: … maximum context length` | `context_window` khai lớn hơn model thật | Giảm `context_window` cho khớp |
| `could not parse response as JSON` | Model không trả JSON thuần | Đã tự gỡ code fence và bóc JSON trong văn xuôi. Nếu vẫn lỗi, hạ `temperature` về 0 |
| `request cap reached` | Chạm `max_requests` | Giảm `--top`, hoặc tăng `max_requests` nếu thật sự cần |
| Báo cáo quá nhiều mục "review" | `areas.symbols` đặt từ quá chung | Từ như `"Api"`, `"Data"` khớp mọi thứ. Dùng từ đặc trưng hơn |
| Kết quả khác lần chạy trước | Dùng số milestone trần | Xem §4 — luôn ghim phiên bản đầy đủ cho báo cáo chính thức |
| **(Windows)** `[Errno 2]` hoặc `FileNotFoundError` khi giải nén | Chạm giới hạn 260 ký tự | Đặt dự án ở đường dẫn ngắn (`C:\cd`), hoặc trỏ cache ra chỗ ngắn: `set CHROMEDRIFT_CACHE=C:\cdcache`. Hoặc bật long path: `New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" -Name LongPathsEnabled -Value 1 -PropertyType DWORD -Force` |
| **(Windows)** `'charmap' codec can't encode` | Bản cũ trước khi ép UTF-8 | Đã sửa trong 0.1.0. Nếu vẫn gặp ở chỗ khác: `set PYTHONUTF8=1` |
| **(Windows)** `python3` không phải là lệnh | Windows dùng tên khác | Dùng `py -3` hoặc `python` |

### Bật log chi tiết

```bash
CHROMEDRIFT_DEBUG=1 python3 -m chromedrift run …    # in nguyên traceback
```

### Xoá cache khi nghi ngờ dữ liệu hỏng

```bash
python3 -m chromedrift run … --refresh     # bỏ qua cache, tải lại
rm -rf .chromedrift-cache                  # hoặc xoá sạch
```

Đặt cache ở nơi khác (ví dụ ổ chung, dùng lại giữa các job CI):

```bash
export CHROMEDRIFT_CACHE=/shared/chromedrift-cache
```

---

## 10. Chạy định kỳ trong CI

```bash
#!/bin/bash
set -euo pipefail

export CHROMEDRIFT_CACHE=/shared/chromedrift-cache
export CHROMEDRIFT_LLM_KEY="${VAULT_LLM_KEY}"

FROM="139.0.7258.155"        # ghim, đừng dùng số milestone trần
TO="143.0.7499.194"

python3 -m chromedrift check --profile config/sb-profile.json5 --llm config/llm.json5

python3 -m chromedrift run "$FROM" "$TO" \
  --profile config/sb-profile.json5 \
  --llm config/llm.json5 \
  --out "reports/${FROM}_to_${TO}"

# Chặn merge nếu có mục Must fix chưa xử lý
MUST=$(python3 -c "import json,sys; \
  print(json.load(open(sys.argv[1]))['bucket_counts']['must_fix'])" \
  "reports/${FROM}_to_${TO}/report.json")
echo "must_fix=$MUST"
[ "$MUST" -eq 0 ] || { echo "Còn $MUST mục phải xử lý trước khi uprev"; exit 1; }
```

Cache dùng chung khiến các job sau gần như tức thì. Snapshot của tag đã phát hành không bao giờ đổi nên chia sẻ được thoải mái giữa các job và các đội.

---

## 11. Kiểm thử

```bash
python3 -m unittest discover -s tests -v
```

58 test, chạy trong ~60 ms, **không cần mạng**. Nên chạy sau mỗi lần sửa `diff.py` hoặc `impact.py` — đó là hai chỗ chứa các quyết định phân loại, và các test ghim lại đúng những ca dễ làm sai (danh tính qua đợt đổi macro, kill-switch bị dọn, default theo platform, đổi tên Finch).

---

## 12. Mở rộng

**Thêm nguồn sự thật mới** (ví dụ enterprise policy): viết một extractor với hai hàm thuần `applies_to(path)` và `extract(text, path)`, đăng ký một dòng trong `chromedrift/extract/__init__.py`, khai file cần tải trong `chromedrift/targets.py`. Không đụng tới phần còn lại.

**Chỉnh cách chấm điểm**: `BASE_SEVERITY` và `SIGNAL_SEVERITY` trong `diff.py`, các hằng `*_BONUS` và hàm `_bucket` trong `impact.py`. Đều là dữ liệu thuần.

**Chỉnh prompt**: `chromedrift/ai/prompts.py`. Cache theo hash prompt nên thử nghiệm rẻ — chỉ phần prompt đổi mới tốn request.
