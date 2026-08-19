# Bàn giao — việc cần chạy tại công ty

File này dành cho agent chạy trên máy có **source Samsung Browser** và **mạng nội bộ**. Mọi việc dưới đây tôi **không làm được từ bên ngoài** vì cần quyền truy cập đó.

Đánh dấu `[x]` khi xong. Mỗi việc có: mục tiêu → lệnh → kỳ vọng → nếu hỏng → **báo lại gì**.

---

## Bối cảnh 30 giây

`chromedrift` so hai phiên bản Chromium và trả lời "đội SB cần sửa gì". Nó chạy bằng Python thuần, không cần cài gì.

Có **hai phép so** khác nhau, đừng nhầm:

| | Ý nghĩa | Lệnh |
|---|---|---|
| **uprev** | Chromium M148 → M151, cùng một dòng upstream | `run A B --mode uprev` |
| **fork** | SB `main/dev` ↔ Chromium M148, cùng thời điểm | `run A B --mode fork` |
| **provenance** | SB so với **cả chuỗi** phiên bản đã merge | `provenance ...` |

Điểm mấu chốt cần hiểu trước khi chạy: **SB không ghi đè code Chromium**. Merge M148 về thì có đủ code M148, code Samsung nằm song song, bọc trong `#if defined(SBROWSER_...)`. Nên so giá trị sẽ báo "khớp M148 hoàn toàn" — đúng, nhưng cái chạy lại là nhánh kia. Chỉ **guard** mới lộ ra điều đó.

---

## Trạng thái hiện tại

### Đã xong và đã kiểm chứng

- [x] So hai bản Chromium (uprev) — đối chứng độc lập khớp 19/19
- [x] Phân biệt "cờ dọn sau khi ship" với "mất tính năng thật" — 45/45 trên M148→M151
- [x] Đọc trang/điều khiển WebUI của 8 màn hình `chrome://`
- [x] Gom mảnh vụn liên quan thành một câu chuyện — ca Local Network Access gom 7 mảnh
- [x] Chia vùng theo đội, in rõ phần chưa có chủ
- [x] Chế độ `fork` và `provenance`, cơ chế đã chạy trên dữ liệu giả lập
- [x] 94 test, chạy offline, đã kiểm trên macOS + Ubuntu + Debian

### Chưa từng chạy thật — đây là lý do có file này

- [ ] **Chưa từng chạy trên source SB**
- [ ] **Chưa từng đưa báo cáo thật cho agent đọc qua skill**
- [ ] **`must_fix` luôn bằng 0** vì chưa có hồ sơ SB thật
- [ ] Trọng số chấm điểm là tôi tự đặt, chưa ai xác nhận

---

## GIAI ĐOẠN 0 — Kiểm môi trường (~15 phút)

### 0.1 Lấy code và kiểm máy

- [ ] Chạy được

```bash
git clone https://github.com/nguyenhuyhoanganh/sbcompare2chrom.git
cd sbcompare2chrom
git checkout fork-comparison        # nhánh chứa phần so sánh fork

python3 -m chromedrift check
```

**Kỳ vọng**: mọi dòng `[OK]`, kết thúc bằng `ready`.

**Nếu hỏng**:
- `python3` không có → dùng `python3.9`+ bất kỳ, hoặc `py -3` trên Windows
- Host mạng `[FAIL]` → xem mục proxy trong `SETUP.md` §8
- `chromestatus` fail thì bỏ qua được bằng `--no-enrich`

**Báo lại**: dán nguyên output.

### 0.2 Chạy thử với Chromium thuần

- [ ] Chạy được

```bash
python3 -m chromedrift run 148.0.7778.217 151.0.7922.138 \
  --no-enrich --out out/smoke
```

**Kỳ vọng**: khoảng 90 giây, ~2.500 semantic changes, sinh 3 file trong `out/smoke/`.

**Báo lại**: số changes, thời gian chạy. Nếu lệch nhiều so với 2.500 thì báo ngay.

---

## GIAI ĐOẠN 1 — Thu thập thông tin tôi không đoán được (~30 phút)

Đây là phần quan trọng nhất. Không có ba thông tin này thì không chạy được trên SB.

### 1.0 Quét dấu vết của Samsung trong cây nguồn — **làm việc này trước**

- [ ] Đã chạy

```bash
python3 -m chromedrift discover --fork-src /đường/dẫn/sbrowser/src \
  --scan-content --out out/discover.json
```

Một lệnh này thay cho việc nhớ đường dẫn. SB đặt code của mình **bên trong cây
Chromium**, nên "file nào là của mình" không suy ra được từ cấu trúc Chromium.
Lệnh quét cả checkout và tìm ba loại dấu vết:

| Dấu vết | Ví dụ |
|---|---|
| Thư mục của vendor, ở bất kỳ độ sâu nào | `chrome/browser/resources/samsung/`, `ui/samsung/views/` |
| **Hậu tố `-si` trên biến thể của component upstream** | `.../settings/privacy_page/privacy_page-si.html` |
| Macro build bọc code trong file upstream | `#if defined(SBROWSER_CUSTOM_DOWNLOADS)` |

Hậu tố `-si` là loại quan trọng nhất và cũng khó thấy nhất: nó nằm **trong** thư
mục của Chromium và giữ nguyên tên component của Chromium, nên không tiền tố
đường dẫn nào chạm tới, cũng không có tiền tố ký hiệu nào của vendor.

**Kỳ vọng — ba khối output:**

1. Thống kê: bao nhiêu file là của Samsung, theo từng loại dấu vết
2. **FIXABLE** — thư mục của Samsung mà danh sách target **chưa bao giờ tải**.
   Đây là những bề mặt đang **vắng mặt hoàn toàn** khỏi mọi phép so, và không
   có gì khác báo điều đó. Mỗi dòng ở đây là một dòng cần thêm vào `targets.py`.
3. **OUT OF MODEL** — file của Samsung mà **không extractor nào đọc dù có tải**
   (native C++ UI, chuỗi `.grd`, file build). Thêm target **không giải quyết
   được gì**; những thứ này phải nêu ở mục giới hạn của báo cáo.

Cuối cùng lệnh in sẵn khối `vendor_markers` để dán vào hồ sơ.

**Báo lại**: cả ba khối, đầy đủ, kèm file `out/discover.json`.

### 1.1 Tên macro Samsung dùng để bọc code

- [ ] Đã lấy

Việc 1.0 với `--scan-content` đã cho danh sách này rồi. Nếu muốn đối chiếu độc
lập:

```bash
cd /đường/dẫn/sbrowser/src

grep -rhoE '#if[[:space:]]+defined\(([A-Z_]*(SBROWSER|SAMSUNG|SEC|TERRACE)[A-Z_]*)\)' \
  --include=*.cc --include=*.h . \
  | grep -oE '\(.*\)' | tr -d '()' | sort | uniq -c | sort -rn | head -50
```

**Kỳ vọng**: danh sách macro kèm số lần xuất hiện, ví dụ `12043 SBROWSER_CUSTOM_UI`.

**Nếu ra rỗng**: Samsung dùng cách bọc khác. Thử tiếp:

```bash
grep -rhoE '#if[[:space:]]+(defined|BUILDFLAG)\([A-Z_]{4,}\)' --include=*.cc . \
  | sort | uniq -c | sort -rn | head -60
```
rồi nhìn xem tên nào là của Samsung.

**Báo lại**: **toàn bộ danh sách 50 dòng đầu**. Đây là thứ điền vào `vendor_markers` trong hồ sơ.

### 1.2 Chuỗi phiên bản Chromium đã merge qua

- [ ] Đã lấy

```bash
cd /đường/dẫn/sbrowser/src
git log --oneline --merges main/dev | head -40
git tag | grep -iE 'm1[0-9][0-9]|chromium' | sort -V | tail -20
```

**Kỳ vọng**: nhận ra được dãy mốc, ví dụ `M120 → M131 → M139 → M148`.

**Báo lại**: dãy phiên bản đầy đủ, cũ nhất trước. Nếu không tra được thì báo "không xác định được" — vẫn chạy được nhưng phân biệt nợ/quyết định kém chính xác hơn.

### 1.3 Repo SB có chung lịch sử git với Chromium không

- [ ] Đã kiểm

```bash
cd /đường/dẫn/sbrowser/src
git merge-base main/dev 148.0.7778.217 2>&1 || echo "KHÔNG CHUNG LỊCH SỬ"
git remote -v
ls -d src content chrome third_party 2>/dev/null    # xem cây nằm ở đâu
```

**Kỳ vọng**: một trong hai
- **Ra commit hash** → có tổ tiên chung, dùng được `git diff` (đường tốt hơn)
- **"KHÔNG CHUNG LỊCH SỬ"** → là bản chép, dùng so cây (vẫn chạy được)

**Báo lại**: kết quả, và **đường dẫn tuyệt đối tới thư mục chứa `content/`, `chrome/`, `third_party/`**. Công cụ cần đúng thư mục đó, không phải thư mục cha.

---

## GIAI ĐOẠN 2 — Chạy lần đầu trên SB thật

### 2.1 Tạo hồ sơ SB

- [ ] Đã tạo

```bash
cp config/sb-profile.example.json5 config/sb-profile.json5
```

Sửa ba chỗ trong file đó:

```json5
{
  name: "Samsung Browser",
  platform: "windows",                    // giá trị khác sẽ bị từ chối khi nạp

  vendor_markers: {
    macros: [ /* điền từ việc 1.1 */ ],
    path_markers: ["samsung/", "sbrowser/"],
    filename_markers: ["-si"],
  },

  patch_dirs: [],                          // xoá dòng trỏ tới demo-patches
  git: { repo: "/đường/dẫn/sbrowser/src", upstream_ref: "148.0.7778.217" },
}
```

**Quan trọng**: xoá `patch_dirs: ["../examples/demo-patches"]` — đó là **dữ liệu bịa** để demo, để nguyên sẽ ra kết quả sai.

- [ ] Kiểm hồ sơ

```bash
python3 -m chromedrift profile config/sb-profile.json5
```

**Kỳ vọng**: `symbols` và `patched files` > 0.

**Nếu `symbols: 0`**: hồ sơ chưa lấy được bằng chứng nào → `must_fix` sẽ luôn bằng 0. Báo lại ngay.

### 2.2 Chụp snapshot SB

- [ ] Chạy được

```bash
cd /đường/dẫn/sbrowser/src && git checkout main/dev && cd -

python3 -m chromedrift snapshot sb-main-dev \
  --local-src /đường/dẫn/sbrowser/src
```

**Kỳ vọng**: khoảng 20.000+ facts, phân bố các loại gần giống Chromium thuần.

**Nếu facts rất ít (< 5.000)**: đường dẫn sai, hoặc Samsung đã đổi cấu trúc file khai báo.

**Báo lại**: bảng phân bố loại fact, và dòng `missing targets` nếu có.

### 2.3 So SB với Chromium M148

- [ ] Chạy được

```bash
python3 -m chromedrift run 148.0.7778.217 sb-main-dev --mode fork \
  --to-src /đường/dẫn/sbrowser/src \
  --profile config/sb-profile.json5 \
  --out out/sb-vs-m148
```

**Kỳ vọng**: có `fork_dropped`, `fork_added`, **`fork_default_override`** trong danh sách nhãn.

**Báo lại**: 4 con số bucket, và 10 nhãn xuất hiện nhiều nhất.

### 2.4 Phân tích nợ merge và vùng bị shadow

- [ ] Chạy được

```bash
python3 -m chromedrift provenance sb-main-dev \
  <dãy-phiên-bản-từ-việc-1.2> \
  --fork-src /đường/dẫn/sbrowser/src \
  --profile config/sb-profile.json5 \
  --out out/provenance.json
```

Ví dụ: `provenance sb-main-dev 120.0.x 131.0.x 139.0.x 148.0.7778.217 ...`

**Kỳ vọng**: hai bảng

1. Xuất xứ: `in_sync / stale / diverged / missing_new / missing_old / vendor_only`
2. Che phủ: `untouched / shadowed / modified / absent / vendor_only / orphaned`
   kèm **danh sách flag Samsung cover bao nhiêu mục**

**Đây là câu trả lời cho "đã nợ những gì"** — `stale` nêu đích danh phiên bản còn khớp.

Hai trạng thái cần đọc kỹ vì chúng dễ bị lẫn với nhau:

- `vendor_only` — chỉ ta có, **và** có dấu hiệu là của ta (macro `SBROWSER*`, tiền tố ký hiệu, hoặc đường dẫn của ta). Đây là quyết định.
- `orphaned` — chỉ ta có, nhưng **không có dấu hiệu nào** nói là của ta. Thường là upstream đã xoá và bản merge của ta giữ lại. Đây là nợ, không phải quyết định.

Trước đây cả hai đều bị gộp chung thành `vendor_only`, nên nợ bị xếp nhầm vào mục quyết định.

**Báo lại**: cả hai bảng, đầy đủ.

---

## GIAI ĐOẠN 3 — Kiểm chứng chất lượng

### 3.1 Đối chứng độc lập

- [ ] Đã làm

Lấy 10 mục ngẫu nhiên trong `out/sb-vs-m148/report.md`, mở source thật kiểm từng cái.

**Báo lại**: bao nhiêu mục đúng / sai, và mô tả cái sai.

### 3.2 Hỏi người thật về thứ tự ưu tiên

- [ ] Đã hỏi

Lấy 10 mục đầu bảng "Must fix" và "Needs review", đưa cho một kỹ sư trong đội hỏi: *"thứ tự ưu tiên này có đúng không?"*

**Nếu sai**: sửa `SIGNAL_SEVERITY` trong `chromedrift/diff.py` — là dữ liệu thuần, không phải logic.

**Báo lại**: nhận xét của kỹ sư, và mục nào bị xếp sai chỗ.

### 3.3 Kiểm phần chưa thuộc vùng nào

- [ ] Đã xem

```bash
python3 -m chromedrift report out/sb-vs-m148/report.json --list-areas
python3 -m chromedrift report out/sb-vs-m148/report.json --area _unassigned --out out/unassigned
```

**Báo lại**: số mục `_unassigned` và bao nhiêu trong đó điểm ≥ 60. Nếu > 30% thì định nghĩa vùng còn thô, cần bổ sung.

---

## GIAI ĐOẠN 4 — Kiểm chứng báo cáo như đầu vào cho agent (CHƯA TỪNG LÀM)

Công cụ **không tự phán xét**. Nó dừng ở bằng chứng và thứ hạng; phần diễn giải
nằm trong skill `skills/analyzing-chromium-uprevs/`, do agent đọc.

Nghĩa là câu hỏi chất lượng đã đổi. Không còn là "prompt có cho ra kết quả dùng
được không", mà là: **báo cáo có đủ để một người đọc chưa biết gì đi tới kết luận
đúng không.** Chưa ai kiểm việc này trên dữ liệu SB thật.

### 4.1 Đưa báo cáo cho agent

- [ ] Đã làm

Mở một phiên agent có nạp skill, đưa `out/sb-fork/report.md` (hoặc `report.json`
nếu agent đọc được JSON), rồi yêu cầu đúng những gì skill mô tả ở Bước 5: viết
báo cáo theo 6 mục, có nêu giới hạn.

**Kỳ vọng**: agent phân loại được từng finding theo thủ tục 5 câu hỏi mà **không
cần hỏi lại thông tin đã có sẵn trong báo cáo**.

### 4.2 Báo lại — quan trọng nhất trong cả file này

- [ ] Đã báo lại

1. **Agent phải hỏi thêm những gì?** Mỗi câu hỏi là một chỗ báo cáo còn thiếu dữ
   liệu, và đó là danh sách việc cần sửa trong `report/markdown.py`.
2. **Dán 5 kết luận đầu tiên nguyên văn.**
3. **Đánh giá thật: dùng được, chung chung, hay bịa?** Nếu bịa, nó bịa từ đâu —
   từ tên feature (thì báo cáo thiếu bằng chứng ở dòng đó), hay từ khoảng trống
   trong skill (thì sửa `SKILL.md`).

Không có phản hồi này thì tôi không có cơ sở nào để nói báo cáo đủ hay chưa.

---

## Những chỗ nhiều khả năng vỡ

Liệt kê trước để đỡ mất thời gian chẩn đoán:

| Triệu chứng | Nguyên nhân nhiều khả năng | Xử lý |
|---|---|---|
| facts rất ít | `--local-src` trỏ sai; phải là thư mục chứa `content/`, `chrome/` | sửa đường dẫn |
| `missing targets` nhiều | Samsung đổi cấu trúc file khai báo | báo lại danh sách thiếu, tôi sửa `targets.py` |
| 0 fact `webui_*` | SB không dùng layout `chrome/browser/resources/` | báo lại, cần đổi bộ đọc |
| `shadowed: 0` mà biết chắc có cover | `vendor_markers.macros` sai tên | quay lại việc 1.1 |
| `stale` gần bằng 0 | chuỗi phiên bản ở việc 1.2 sai | kiểm lại dãy merge |
| `must_fix: 0` | hồ sơ chưa có bằng chứng | quay lại việc 2.1 |
| chạy rất chậm | mạng chậm khi tải Chromium | thêm `--local-src` cho cả bên Chromium nếu có sẵn |

Bật log chi tiết khi cần: `CHROMEDRIFT_DEBUG=1` trước lệnh.

---

## Mẫu báo cáo lại

Gửi về theo dạng này, càng nguyên văn càng tốt:

```
GIAI ĐOẠN 0
  0.1 check        : [xong/hỏng]  <dán output>
  0.2 smoke        : [xong/hỏng]  N changes, T giây

GIAI ĐOẠN 1
  1.1 macro        : <dán 50 dòng>
  1.2 chuỗi ver    : <dãy, cũ nhất trước>
  1.3 git chung    : [có/không]   src path = <...>

GIAI ĐOẠN 2
  2.2 snapshot SB  : N facts, phân bố = <...>, missing = <...>
  2.3 fork diff    : must_fix/review/opportunity/fyi = ...
                     10 nhãn nhiều nhất = <...>
  2.4 provenance   : <dán cả hai bảng>

GIAI ĐOẠN 3
  3.1 đối chứng    : đúng ?/10, sai = <mô tả>
  3.2 kỹ sư nói    : <nguyên văn>
  3.3 unassigned   : N mục, M mục điểm >= 60

GIAI ĐOẠN 4
  4.2 agent đọc    : agent phải hỏi thêm = <liệt kê>
                     5 kết luận đầu = <dán nguyên văn>
                     ĐÁNH GIÁ: <dùng được / chung chung / bịa>

VỠ Ở ĐÂU: <mô tả + thông báo lỗi nguyên văn>
```

---

## Đọc thêm

- `README.md` — giải thích từ đầu công cụ làm gì và vì sao (tiếng Việt)
- `SETUP.md` — cài đặt A–Z, proxy, mạng cách ly, xử lý sự cố
- `skills/analyzing-chromium-uprevs/` — gói kiến thức cho agent, gồm 8 cái bẫy đã kiểm chứng

**Ưu tiên nếu không đủ thời gian**: việc **1.1** (tên macro) và **4.2** (agent đọc báo cáo thật). Hai cái đó chặn nhiều thứ nhất và tôi hoàn toàn không đoán được.
