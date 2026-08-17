# Luồng so sánh hai bản Chromium, từ đầu đến cuối

Tài liệu này đi theo **một thay đổi có thật**, từ lúc anh gõ lệnh cho tới lúc nó
xuất hiện trong báo cáo, giải thích ở mỗi chặng: code làm gì, tại sao làm thế, và
điều gì sẽ hỏng nếu làm cách khác.

Ví dụ dùng xuyên suốt là một finding thật của lần chạy M148 → M151:

```
GlicActorUiMagicCursor    disabled → enabled    severity 75
```

Lệnh:

```bash
python3 -m chromedrift run 148.0.7778.217 151.0.7922.138 \
  --profile config/sb-profile.json5 --out out/M148_to_M151
```

Toàn bộ luồng là một đường thẳng gồm các phép biến đổi dữ liệu thuần:

```
Snapshot(ref)            ->  [Fact]      extract/
(Snapshot, Snapshot)     ->  [Change]    diff.py
([Change], TouchSet)     ->  [Finding]   impact.py
[Finding]                ->  [Finding+]  cluster.py, enrich/, ai/
[Finding]                ->  báo cáo     report/
```

Mỗi chặng đọc và ghi JSON, nên chạy lại được từng chặng riêng. Điều đó không phải
để cho đẹp: chặng đắt (mạng) và chặng anh chỉnh đi chỉnh lại (chấm điểm, prompt,
báo cáo) có chi phí khác hẳn nhau.

---

## Bước 1. Từ "151" thành một ref cụ thể

**Code:** `acquire.resolve_ref()`

Anh có thể đưa vào ba dạng, và chúng được xử lý khác nhau:

| Anh gõ | Xảy ra gì |
|---|---|
| `151.0.7922.138` | Dùng thẳng → `refs/tags/151.0.7922.138` |
| `151` | Hỏi chromiumdash bản **stable mới nhất** của milestone đó |
| `main/dev` | Coi là git ref, chuyển nguyên |

### Tại sao nên tránh gõ số milestone trần

`151` giải ra bản stable mới nhất **tại thời điểm chạy**, và nó trôi. Ví dụ thật:
`ServiceWorkerAutoPreload` **BẬT** ở `143.0.7499.40` nhưng **TẮT** ở
`143.0.7499.194` — cùng milestone, khác bản vá, vì bị revert.

Hai lần chạy cách nhau vài tuần cho hai kết luận khác nhau, và **cả hai đều
đúng**. Với thứ ghi vào ticket, luôn ghim phiên bản đầy đủ.

Ref đã giải xong cũng là **khoá cache**. Tag đã phát hành thì nội dung không bao
giờ đổi, nên snapshot của nó cache được vĩnh viễn.

---

## Bước 2. Lấy về đúng vài nghìn file, không phải cả Chromium

**Code:** `targets.py`, `acquire.GitilesSource`

`fetch chromium && gclient sync` là ~100 GB và vài giờ, mỗi phiên bản. Ta chỉ cần
các file **khai báo**, nên kéo thẳng tarball theo thư mục từ Gitiles:

```
https://chromium.googlesource.com/chromium/src/+archive/refs/tags/<tag>/<dir>.tar.gz
```

`targets.py` là danh sách khai báo lấy gì, mỗi mục kèm lý do. Ba nhóm:

- **File cờ** — `chrome/common/chrome_features.cc` (247 cờ ở M151),
  `content/public/common/`, `net/base/features.cc`, …
- **Cây có lọc đuôi** — `third_party/blink/renderer/modules` chỉ lấy `.idl`;
  `chrome/browser/resources/settings` chỉ lấy template và bảng route
- **Manifest** — `runtime_enabled_features.json5`, `flag-metadata.json`

Ví dụ của ta nằm trong `chrome/common/chrome_features.cc`, tải về 92.615 byte.

### Ba chi tiết nhỏ nhưng từng gây lỗi thật

**Marker cache ghi *kết quả gì*, không chỉ "đã xong".** File 404 vẫn được cache
để khỏi tải lại mỗi lần — nhưng nếu marker chỉ ghi "xong", thì một lần chạy mà
**mọi** target đều 404 (gõ nhầm tag, hoặc proxy trả 404) sẽ báo lỗi lần đầu, rồi
**lần chạy thứ hai y hệt lại thành công** và ghi ra snapshot 0 fact. Đem diff với
bản thật thì toàn bộ bề mặt tính năng trông như biến mất.

**Marker gắn hash của bộ lọc đuôi file.** Một cây tải với bộ lọc hẹp không phải
cùng một thứ với cây đó tải bằng bộ lọc rộng hơn. Khoá marker chỉ theo đường dẫn
từng khiến việc thêm `.html.ts` (Lit) **không thay đổi gì cả**: snapshot dựng
lại, số fact đứng im, không có gì báo lỗi.

**Giải nén có chặn path traversal** — tarball hỏng hoặc độc không được ghi ra
ngoài thư mục đích.

---

## Bước 3. Đọc file thành "fact"

**Code:** `extract/` — 9 extractor, mỗi cái là hai hàm thuần
`applies_to(path)` và `extract(text, path)`

### Tại sao lex chứ không parse

Không có compiler, không có `compile_commands.json`, và chỉ có một phần cây
nguồn. Nhưng các khai báo ta cần đều là **macro và hằng số viết theo một house
style ổn định nhiều năm**, nên lex cẩn thận thắng parse thật.

Cái duy nhất bắt buộc phải đúng là **ngữ cảnh**:

```cpp
BASE_FEATURE(kAudioServiceOutOfProcess,
#if BUILDFLAG(IS_WIN) || BUILDFLAG(IS_MAC) || BUILDFLAG(IS_LINUX)
             base::FEATURE_ENABLED_BY_DEFAULT
#else
             base::FEATURE_DISABLED_BY_DEFAULT
#endif
);
```

Đọc thô lấy giá trị đầu tiên. Với guard này thì tình cờ đúng. Nhưng đảo lại —
Windows nằm ở nhánh `#else` — thì đọc thô cho **kết luận ngược**. Chỉ trong một
file, 14/187 cờ có mặc định khác nhau theo nền tảng.

Nên `_cpp.py` có bộ đánh giá điều kiện **ba trạng thái**. Kết quả thật:

| Guard | Đọc thô | Giá trị thực trên Windows |
|---|---|---|
| `IS_WIN \|\| IS_MAC \|\| IS_LINUX` | `enabled` | `enabled` |
| `IS_ANDROID` … `#else` | `enabled` | **`disabled`** |
| `ENABLE_PLUGINS` … `#else` | `enabled` | `conditional` |

Dòng ba quan trọng ngang dòng hai: khi điều kiện phụ thuộc một buildflag không
phải nền tảng, công cụ trả lời **"không xác định"** thay vì đoán.

### Khoá phải bền qua thay đổi cú pháp

Đây là điều làm cả thiết kế đứng vững. Giữa M139 và M143, macro `BASE_FEATURE`
bỏ tham số tên chuỗi:

```cpp
BASE_FEATURE(kBackForwardCache, "BackForwardCache", ENABLED);  // <= M141
BASE_FEATURE(kBackForwardCache, ENABLED);                      // >= M142
```

Trong `content_features.cc`, M139 có 170/170 khai báo dạng cũ, M143 có 12/187.
**Một parser khoá theo văn bản nguồn sẽ báo cả file bị viết lại.** Sau khi chuẩn
hoá `kFoo` → `"Foo"`, delta thật là 152 giữ nguyên, 18 bỏ, 35 thêm.

Ví dụ của ta ra một fact như sau:

```json
{ "kind": "base_feature", "key": "GlicActorUiMagicCursor",
  "path": "chrome/common/chrome_features.cc",
  "attrs": { "var": "kGlicActorUiMagicCursor",
             "default_state": "enabled",
             "platform_state": { "windows": "enabled" },
             "declared_form": "macro2", "conditions": [] } }
```

### Phạm vi trích xuất bám theo target đã khai, không theo đĩa

Cache cây nguồn dùng chung theo ref. Nếu để việc trích xuất tự lấy phạm vi từ
"có gì trên đĩa", thì chạy `--target-set minimal` trong thư mục mà lần chạy
`default` trước đã đổ đầy sẽ cho ra snapshot "minimal" chứa **đủ 21.595 fact** —
đem diff với minimal thật thì bịa ra khoảng 20.000 addition, không lỗi, không
cảnh báo, và trông rất hợp lý.

---

## Bước 4. So sánh hai snapshot

**Code:** `diff.py`

### Quy tắc 1 — chỉ so thuộc tính có nghĩa

`MEANINGFUL_ATTRS` liệt kê, cho từng loại fact, những thuộc tính mà thay đổi của
chúng có ý nghĩa với hạ nguồn. Với `base_feature` là `default_state`,
`platform_state`, `conditions`.

`declared_form` **không** nằm trong đó — nếu có, đợt đổi macro M139→M143 sẽ sinh
ra hàng nghìn "modification" chẳng nói lên gì.

`conditions` thì có, vì một fork thường không sửa code upstream mà **bọc cờ build
quanh nó**: guard xuất hiện hay biến mất chính *là* thay đổi, trong khi giá trị
đứng im.

Ví dụ của ta:

```
deltas = { default_state:  ["disabled", "enabled"],
           platform_state: [{windows: "disabled"}, {windows: "enabled"}] }
```

### Quy tắc 2 — signal, không phải chỉ "đã đổi"

Mỗi change nhận các **signal**: nhãn đọc được kèm mức nghiêm trọng sàn.

Ví dụ của ta nhận `enabled_by_default` (75) và `default_flip_on` (60). Điểm cuối
là 75 — cao nhất trong các sàn.

Vì sao tách hai signal? `default_flip_on` nói **Chromium viết gì**;
`enabled_by_default` nói **người dùng của ta nhận gì**. Chúng thường xuyên khác
nhau, và chỉ cái thứ hai mới đáng gọi là thay đổi hành vi.

### Vì sao "biến mất" hầu như không phải "mất tính năng"

Chromium cho mọi tính năng đi qua **ba giai đoạn, cách nhau nhiều milestone**:

| Giai đoạn | Code | Người dùng thấy |
|---|---|---|
| A | Code mới về, cờ mặc định TẮT | không gì |
| B | Cờ lật thành BẬT | **chính là thay đổi** |
| C | Xoá nhánh cũ và xoá cờ | không gì |

Nên diff giữa hai phiên bản **chủ yếu thấy A và C**. Một cờ biến mất thường là
Chromium dọn dẹp sau khi kết quả đã ngã ngũ — và **trạng thái nó giữ ngay trước
khi bị xoá** cho biết ngã ngũ theo hướng nào.

Đo thật M148 → M151 trên Windows: **90 cờ bị xoá, chia đúng 45/45** giữa
"đã ship rồi mới rút cờ" và "chưa từng ship, xoá luôn". Gán cả 90 là "tính năng
bị xoá" thì một nửa danh sách là báo động giả. Nên có hai signal riêng:
`flag_retired_on` và `flag_retired_off`.

Với Blink còn rõ hơn: M139 → M143 có 202 runtime feature biến mất, **170 cái
trước đó đang `stable`** — tức là rút kill-switch sau khi đã ship, không phải mất
API. Xếp chúng thành "API bị xoá" là 170 báo động giả nằm đầu báo cáo.

### Phát hiện đổi tên: lỗi im lặng đắt nhất

Với `pref`, `switch`, `base_feature`, **danh tính là một chuỗi**, còn biến C++
thì bền. Nên một lần đổi tên đi vào diff dưới dạng "một cái mất, một cái thêm"
chẳng liên quan gì nhau — và hậu quả thật nằm lọt giữa hai dòng đó.

`_detect_renames()` ghép removal với addition **dùng chung tên biến C++**.

Đây không phải giả thuyết. M139 khai báo
`BASE_FEATURE(kFedCmIdPRegistration, "FedCmIdPregistration", ...)` — chữ `r`
thường. M143 dùng macro hai tham số, tự suy tên từ biến → thành
`"FedCmIdPRegistration"`, chữ `R` hoa. **Không ai sửa tên; đợt đổi macro đã đổi
nó.** Mọi field trial phía server và mọi `--enable-features` gõ theo cách cũ từ
đó im lặng không có tác dụng. Không compiler nào cảnh báo.

---

## Bước 5. Chấm điểm: "có đổi" so với "có ảnh hưởng tới **ta**"

**Code:** `sbprofile.py` (bằng chứng), `impact.py` (chấm điểm)

`diff.py` trả lời "cái này thường quan trọng cỡ nào". Bước này trả lời câu đội
ngũ thật sự hỏi: **có ảnh hưởng đến ta không.**

### Bằng chứng đến từ đâu

`sbprofile.load_profile()` gom `TouchSet` từ bất cứ thứ gì đội có:

- thư mục file `.patch` — hình dạng thường thấy của một fork
- `git diff --name-only <upstream_tag>` trong cây fork
- danh sách đường dẫn tự duy trì
- **quét mã nguồn riêng của fork** tìm tham chiếu tới tên Chromium

### Chiều quét bị đảo ngược, có chủ ý

Thay vì grep Chromium tìm tên của Samsung, công cụ lấy **từ vựng của snapshot**
(mọi tên feature, switch, pref mà Chromium khai báo) rồi tìm các token đó trong
mã nguồn của fork.

Việc này biến bài toán "quét nhiều lượt trên cây khổng lồ" thành **một lượt trên
cây nhỏ**, và bắt được thứ danh sách patch bỏ lọt: code *đọc* một feature mà
không hề vá file khai báo nó.

Từ vựng dựng từ **cả hai** snapshot. Nếu chỉ dùng bản mới, một ký hiệu chỉ tồn
tại ở bản cũ sẽ bị lọc mất — mà đó chính là ca đáng giá nhất: thứ ta phụ thuộc và
upstream vừa xoá.

### Bằng chứng cấp ký hiệu mạnh hơn cấp đường dẫn, rất nhiều

```
+12  ta có vá file khai báo nó
+30  mã nguồn của ta có nhắc tên nó
```

Vá `content_features.cc` gần như không nói gì — file đó khai báo gần 200 cờ.
Nhắc đúng định danh của cờ thì nói rất nhiều. Nên **chỉ bằng chứng cấp ký hiệu**
mới đẩy được một mục lên *Must fix*.

Ví dụ của ta không có bằng chứng nào (`config/sb-profile.example.json5` là hồ sơ
mẫu), nên nó dừng ở:

```
score 75, bucket "review"
lý do: base severity 75 (modified base_feature)
```

Nếu hồ sơ thật của SB có nhắc `kGlicActorUiMagicCursor`, nó sẽ thành 100 và
*Must fix*.

### Bốn nhóm, và vì sao "New opportunity" tách riêng

| Nhóm | Nghĩa |
|---|---|
| Must fix | Ta tham chiếu tới nó VÀ nó đã đổi |
| Needs review | Ta động tới vùng đó, hoặc đủ nghiêm trọng để cần xác nhận |
| New opportunity | Năng lực mới có thể lấy về |
| FYI | Ghi nhận cho đủ |

Một API web lên `stable` có điểm cao vì nó **quan trọng** — nhưng nó là "đây là
thứ người dùng của bạn vừa có", không phải "đây là thứ có thể vỡ". Để 150 mục
như thế trôi vào danh sách review là cách một công cụ triage biến thành thứ
không ai mở nữa.

Mọi điều chỉnh điểm đều **ghi lại lý do đọc được**. Một bảng xếp hạng không cãi
lại được là bảng xếp hạng bị bỏ qua ngay lần đầu nó sai — và ở đây điểm số còn
quyết định AI tiêu ngân sách ngữ cảnh vào đâu.

---

## Bước 6. Gom mảnh rời thành một câu chuyện

**Code:** `cluster.py`

Một thay đổi upstream đi vào báo cáo dưới dạng nhiều mảnh trên nhiều bề mặt. Đợt
di trú Local Network Access giữa M148 và M151 sinh ra **7 finding riêng**:

```
webui_route    SITE_SETTINGS_LOCAL_NETWORK_ACCESS   bị xoá
webui_route    SITE_SETTINGS_LOCAL_NETWORK          đổi cờ gác
webui_gate     enableLocalNetworkAccessSplitPermissions  bị xoá
webui_gate     enableLocalNetworkAccessSetting      đổi biểu thức
webui_control  label:siteSettingsLocalNetworkAccess bị xoá
base_feature   LocalNetworkAccessChecksSplitPermissions  rút cờ
blink_runtime  LocalNetworkAccessSplitPermissions   bị bỏ
```

Đọc rời 7 dòng thì chúng **mâu thuẫn nhau** — dòng này bảo mất một trang, dòng
kia bảo có thêm trang. Đọc thành một cụm thì nó nói một điều đơn giản và đúng:
trang chuyển sang split permissions, người dùng đã thấy từ M148, và việc phải làm
duy nhất là cập nhật một tham chiếu route đã cũ.

Gom cụm dùng **liên kết mà dữ liệu tự khai** — route gọi tên guard của nó, guard
gọi tên feature, feature trùng tên với cờ Blink — chứ không phải độ giống tên.
Vì thế cụm là **chính xác**, không phải phỏng đoán.

---

## Bước 7. Bổ sung ngữ cảnh do người viết

**Code:** `enrich/chromestatus.py`

Extractor nói **cái gì** đổi; chromestatus.com nói **tại sao**, bằng văn xuôi do
người viết: tóm tắt, link spec, milestone ship.

Ghép từng mục thì tỉ lệ trúng rất thấp (~2%) vì tên bên đó là văn xuôi còn tên
trong mã là định danh. Nên thay vì cố ghép, công cụ đưa **cả danh sách "Chromium
đã ship gì trong khoảng này" làm ngữ cảnh dùng chung** cho mọi request — khoảng
100 mục, ~8k token, không đáng kể trong cửa sổ 200k.

---

## Bước 8. AI phán xét, không phát hiện

**Code:** `ai/budget.py`, `ai/prompts.py`, `ai/analyze.py`

Hai nguyên tắc chi phối thiết kế.

**Model phán xét, không khám phá.** Mọi bản ghi đưa sang đã được chuẩn hoá, chấm
điểm và gắn bằng chứng bởi các chặng tất định. Việc của model là phần thật sự cần
suy xét — *cái này có nghĩa gì với sản phẩm của chúng ta, ai phải làm gì* — chứ
không phải tính lại một cái diff mà nó không nhìn thấy.

**Phải làm việc bịa đặt trở nên kém hấp dẫn.** Tên feature của Chromium gợi ý đủ
mạnh để một model sẵn sàng kể `PwaNavigationCapturing` làm gì chỉ từ cái tên. Nên
bản ghi mang theo bằng chứng thật, hướng dẫn bắt buộc trích dẫn bằng chứng đó, và
`unknown` là một verdict **hạng nhất**. Một câu trả lời sai đầy tự tin tốn của
người review nhiều thời gian hơn là không trả lời.

### Ngân sách

Một bản ghi change là vài trăm token thay vì vài nghìn dòng. Đo thật trên
M148 → M151: toàn bộ 1.226 finding không-FYI ≈ 105k token, **vừa một request**
cửa sổ 200k.

Vì thế mặc định `--top` là **0 = không giới hạn**. Bản trước cắt còn 150 mục,
tức vứt 93% phân tích để tiết kiệm một chi phí **không tồn tại**.

Gom theo vùng sở hữu để mỗi batch đọc như một tiểu hệ thống, rồi **trộn cả nhóm
lại** khi còn vừa. Gom mà không trộn là cái bẫy: mỗi nhóm vài nghìn token thì
một-request-một-nhóm tốn 5 request để gửi 4k token.

### Khi AI hỏng

Một phân tích thất bại hiển thị thành các ô verdict trống — **trông y hệt một kết
quả sạch**. Nên `ai_status_note()` in một dòng không thể bỏ qua ngay đầu báo cáo,
trước mọi finding.

---

## Bước 9. Báo cáo

**Code:** `report/markdown.py`, `report/html.py`

Ba dạng ra:

- `report.md` — dán thẳng vào ticket
- `report.html` — bảng lọc/sắp xếp được, **tự chứa hoàn toàn**, không tải tài
  nguyên ngoài, nên mở được trong mạng cách ly và gửi kèm mail được
- `report.json` — cho script và so sánh giữa các kỳ

Thứ tự trình bày theo thứ tự người đọc cần: verdict → việc phải làm → bằng chứng.
Mỗi finding hiện **lý do chấm điểm** để người đọc cãi lại được.

Lọc theo vùng xảy ra **lúc render, không bao giờ trước khi phân tích**: JSON luôn
giữ mọi finding, nên cắt lát theo đội không tốn gì và không giấu được gì.

```bash
python3 -m chromedrift report out/report.json --list-areas
python3 -m chromedrift report out/report.json --area downloads
```

Báo cáo cũng luôn in **số finding không thuộc vùng nào**. Đó không phải chú thích
bên lề: đo trên M148 → M151, tập không-vùng chứa 281 mục điểm ≥ 60, gồm **cả
mười mục nghiêm trọng nhất** — vốn là các thay đổi signature Mojo không thuộc sản
phẩm nào.

---

## Vì sao cách này hoạt động

Gộp lại thành bốn ý.

**1. So sánh khai báo, không so sánh văn bản.** Chromium tự mô tả mình bằng máy
đọc được: macro cờ, JSON5 manifest, IDL, mojom, bảng route. Đó là những chỗ hành
vi được *quyết định*. Diff văn bản của bốn milestone là hàng triệu dòng; diff
khai báo là vài nghìn sự kiện có nghĩa.

**2. Khoá theo ngữ nghĩa, không theo cú pháp.** Cú pháp đổi thường xuyên hơn ngữ
nghĩa rất nhiều. Chuẩn hoá về tên feature khiến đợt đổi macro M139→M143 — vốn
viết lại toàn bộ file — trở thành **không thay đổi gì**, đúng như thực tế.

**3. Biết vòng đời ba giai đoạn.** Không có nó, mọi lần dọn dẹp của Chromium đọc
thành mất tính năng: 170 báo động giả chỉ riêng Blink ở M139→M143, 45 chỉ riêng
`base::Feature` ở M148→M151.

**4. Join với bằng chứng hạ nguồn.** "Chromium đổi X" là dữ liệu. "Chúng ta có
nhắc X" mới là tín hiệu. Không có vế thứ hai thì không có thứ tự ưu tiên, và một
danh sách không thứ tự ưu tiên thì không ai đọc.

---

## Chi phí thật

Đo trên máy thật, cache lạnh:

| Phạm vi | Thời gian | Cache | Fact |
|---|---:|---:|---:|
| Toàn bộ | ~120 s | 126 MB | 24.646 |
| `--partition settings` | 24 s | 37 MB | 4.467 |
| `--partition downloads` | 17 s | 2,6 MB | 2.692 |

Cache ấm thì mọi chặng sau snapshot chạy trong vài giây — đó là điều khiến việc
chỉnh chấm điểm và prompt trở nên khả thi.

---

## Đọc tiếp

- [COVERAGE.md](COVERAGE.md) — "tính năng" gồm những gì, và phủ được bao nhiêu
- [README.md](README.md) — giải thích từng nhóm code, chi tiết hơn
- [SETUP.md](SETUP.md) — cài đặt trên máy mới, xử lý sự cố
- [skills/analyzing-chromium-uprevs/](skills/analyzing-chromium-uprevs/) — quy
  trình dạng skill cho agent, kèm bẫy đã gặp và bảng tra signal
