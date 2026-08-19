# Luồng so sánh hai bản Chromium, từ đầu đến cuối

Tài liệu này đi theo **một thay đổi có thật**, từ lúc gõ lệnh tới lúc nó xuất hiện
trong báo cáo. Ở mỗi chặng nói rõ ba điều: **máy móc bên trong làm gì**, tại sao
làm thế, và điều gì hỏng nếu làm cách khác.

Mọi đoạn output dưới đây là **chạy thật**, không phải minh hoạ.

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
[Finding]                ->  [Finding+]  cluster.py, enrich/
[Finding]                ->  báo cáo     report/
```

Mỗi chặng đọc và ghi JSON, nên chạy lại được từng chặng riêng. Điều đó không phải
để cho đẹp: chặng đắt (mạng) và chặng phải chỉnh đi chỉnh lại (chấm điểm,
báo cáo) có chi phí khác hẳn nhau.

---

## Bước 1. Từ "151" thành một ref cụ thể

**Code:** `acquire.resolve_ref()`

Ba dạng đầu vào, ba đường xử lý:

| Anh gõ | Cơ chế | Kết quả |
|---|---|---|
| `151.0.7922.138` | regex `^\d+\.\d+\.\d+\.\d+$` khớp → dùng thẳng | `refs/tags/151.0.7922.138` |
| `151` | regex `^\d{2,3}$` khớp → gọi chromiumdash | ref của bản stable mới nhất |
| `main/dev` | không khớp gì → chuyển nguyên | `main/dev` |

Với dạng thứ hai, cụ thể là:

```
GET https://chromiumdash.appspot.com/fetch_releases
      ?channel=Stable&platform=Windows&milestone=151&num=25
```

rồi lấy `max()` theo tuple `(major, minor, build, patch)` — so số chứ không so
chuỗi, vì `"7922" < "800"` theo thứ tự chuỗi.

### Tại sao nên tránh gõ số milestone trần

`151` giải ra bản stable mới nhất **tại thời điểm chạy**, và nó trôi. Ví dụ thật:
`ServiceWorkerAutoPreload` **BẬT** ở `143.0.7499.40` nhưng **TẮT** ở
`143.0.7499.194` — cùng milestone, khác bản vá, vì bị revert.

Hai lần chạy cách nhau vài tuần cho hai kết luận khác nhau, và **cả hai đều
đúng**. Với thứ ghi vào ticket, luôn ghim phiên bản đầy đủ.

Ref đã giải xong cũng là **khoá cache**. Tag đã phát hành thì nội dung không bao
giờ đổi, nên snapshot của nó cache được vĩnh viễn.

---

## Bước 2. Lấy về vài nghìn file, không phải cả Chromium

**Code:** `targets.py`, `acquire.GitilesSource`

`fetch chromium && gclient sync` là ~100 GB và vài giờ mỗi phiên bản. Ta chỉ cần
các file **khai báo**, nên dùng hai endpoint của Gitiles:

```
# cả một thư mục, dạng tar.gz
GET .../+archive/refs/tags/<tag>/<dir>.tar.gz

# một file đơn, trả về base64
GET .../+/refs/tags/<tag>/<path>?format=TEXT
```

`materialize()` đổ chúng ra đĩa thành **một bản checkout rất từng phần**: cùng
cấu trúc thư mục như `src/`, nhưng chỉ có các file ta cần. Nhờ vậy mọi extractor
phía sau chỉ cần biết đường dẫn tương đối, không cần biết nguồn từ đâu — và
`LocalSource` (đọc từ checkout thật của SB) thay thế được mà không đổi gì phía sau.

Ví dụ của ta nằm trong `chrome/common/chrome_features.cc`, tải về 92.615 byte.

### Cơ chế cache: một file marker cho mỗi target

Mỗi target có một file `.state` trong `.chromedrift/`:

```
<tên đường dẫn đã escape>.<hash 8 ký tự của bộ lọc đuôi>.state
   nội dung: "ok"  hoặc  "missing"
```

Ba chi tiết trong tên và nội dung này, mỗi cái vá một lỗi có thật:

**Nội dung ghi *kết quả gì*, không chỉ "đã xong".** File 404 vẫn được cache để
khỏi tải lại mỗi lần — file có thể chưa tồn tại ở milestone cũ, đó là *dữ liệu*
chứ không phải lỗi. Nhưng nếu marker chỉ ghi "xong", một lần chạy mà **mọi**
target đều 404 (gõ nhầm tag, hoặc proxy công ty trả 404 thay vì chặn) sẽ báo lỗi
lần đầu, rồi **lần chạy thứ hai y hệt lại thành công** và ghi ra snapshot 0 fact.
Đem diff với bản thật thì toàn bộ bề mặt tính năng trông như biến mất, không có
gì báo động.

**Hash của bộ lọc đuôi nằm trong tên.** Một cây tải với bộ lọc hẹp không phải cùng
một thứ với cây đó tải bằng bộ lọc rộng hơn. Khoá marker chỉ theo đường dẫn từng
khiến việc thêm `.html.ts` (Lit) **không thay đổi gì cả**: snapshot dựng lại, số
fact đứng im, không lỗi.

**Giải nén chặn path traversal.** `_extract_tar_gz` tính `os.path.abspath` của
từng thành viên và bỏ qua bất kỳ cái nào không nằm dưới thư mục đích.

Mọi request HTTP đều retry 4 lần với backoff `1,5 × 2^n`, và **kiểm tra body
không rỗng** — Gitiles thỉnh thoảng đóng kết nối giữa chừng và trả về 0 byte cho
một URL vừa mới hoạt động.

---

## Bước 3. Đọc file thành "fact"

**Code:** `extract/` — 9 extractor, mỗi cái là hai hàm thuần
`applies_to(path) -> bool` và `extract(text, path) -> [Fact]`

`run_on_tree()` duyệt cây, với mỗi file hỏi từng extractor "có nhận không", rồi
gọi cái nào nhận. Một extractor ném lỗi thì file đó bị bỏ qua và đếm vào
`_errors`, **không làm hỏng cả snapshot**.

### Tại sao lex chứ không parse

Không có compiler, không có `compile_commands.json`, chỉ có một phần cây nguồn.
Nhưng các khai báo ta cần đều là **macro và hằng số viết theo house style ổn định
nhiều năm**, nên lex cẩn thận thắng parse thật.

Cái duy nhất bắt buộc phải đúng là **ngữ cảnh preprocessor**. Đây là cơ chế đó,
chạy thật trên đoạn mã sau:

```cpp
// Copyright 2025
#if BUILDFLAG(IS_WIN)
BASE_FEATURE(kFoo,   // ghi chú có dấu ( lạc
#if BUILDFLAG(ENABLE_PLUGINS)
             base::FEATURE_ENABLED_BY_DEFAULT
#else
             base::FEATURE_DISABLED_BY_DEFAULT
#endif
);
#endif
```

**(a) `mask_comments` — che comment nhưng giữ nguyên độ dài:**

```
len gốc=231  len sau=231  bằng nhau=True
dòng 3 sau khi che: 'BASE_FEATURE(kFoo,                          '
→ line_of(offset) vẫn đúng: BASE_FEATURE ở dòng 3
```

Thay comment bằng dấu cách **cùng số ký tự** nghĩa là mọi offset tính trên văn
bản đã che vẫn ánh xạ đúng sang văn bản gốc, nên số dòng báo cáo ra vẫn chuẩn.
Chuỗi trong `"..."` được giữ nguyên vì **tên feature nằm trong đó**. Dấu `(` lạc
trong comment biến mất, nên không phá phép đếm ngoặc.

**(b) `conditional_spans` — mỗi khối `#if` thành một khoảng offset:**

```
[ 115, 161)  BUILDFLAG(ENABLE_PLUGINS)
[ 167, 214)  !(BUILDFLAG(ENABLE_PLUGINS))     ← nhánh #else thành phủ định
[  40, 224)  BUILDFLAG(IS_WIN)
enclosing_conditions(offset 40) = ['BUILDFLAG(IS_WIN)']
```

Dùng khoảng offset thay vì phân tích lồng nhau vì **guard thường bọc cả khai báo
chứ không nằm bên trong nó**. Người gọi cần hỏi "những điều kiện nào *bao quanh*
vị trí này", không phải "trong đoạn này có điều kiện gì".

**(c) `balanced_args` — lấy phần trong ngoặc, bỏ qua ngoặc trong chuỗi:**

Đếm độ sâu, nhưng khi gặp `"` hoặc `'` thì nhảy tới hết chuỗi, có xử lý `\`
escape. Nếu ngoặc không đóng (file cắt cụt, tải hỏng) thì ném `ValueError` và
khai báo đó bị bỏ, thay vì nuốt phần còn lại của file.

**(d) `conditional_values` — mỗi giá trị kèm ngữ cảnh `#if` của chính nó:**

```
FEATURE_ENABLED_BY_DEFAULT       <- [('BUILDFLAG(ENABLE_PLUGINS)', True)]
FEATURE_DISABLED_BY_DEFAULT      <- [('BUILDFLAG(ENABLE_PLUGINS)', False)]
```

Duy trì một stack: `#if` đẩy vào, `#elif` biến các nhánh trước thành `False` rồi
thêm nhánh mới, `#else` lật tất cả thành `False`, `#endif` pop ra.

**(e) `eval_condition` — bộ đánh giá ba trạng thái:**

```
BUILDFLAG(IS_WIN)                              -> True
BUILDFLAG(IS_ANDROID)                          -> False   ← nền tảng khác, chắc chắn không phải ta
BUILDFLAG(ENABLE_PLUGINS)                      -> None    ← không phải cờ nền tảng, không đoán
BUILDFLAG(IS_WIN) || BUILDFLAG(IS_MAC)         -> True
!BUILDFLAG(IS_ANDROID)                         -> True
BUILDFLAG(IS_WIN) && BUILDFLAG(ENABLE_PLUGINS) -> None    ← None lan truyền
```

Đây là một parser đệ quy xuống nhỏ (`parse_or` → `parse_and` → `parse_unary` →
`parse_atom`) trên logic ba trị: `True || None = True`, nhưng `True && None =
None`. **`None` lan truyền**, nên khi không quyết được thì trả lời "không xác
định" thay vì đoán.

**(f) `resolve_platform_state` — ráp lại:**

```
{'windows': 'conditional'}
```

Với mỗi nền tảng, duyệt các cặp (ngữ cảnh, giá trị) theo thứ tự, lấy giá trị đầu
tiên có ngữ cảnh đánh giá ra `True`. Nếu gặp `None` giữa chừng thì đánh dấu
`unknown`. Kết quả có ba khả năng: giá trị cụ thể, `"conditional"` (có nhánh
không quyết được), hoặc `"not_compiled"` (mọi nhánh đều `False`).

### Vì sao ngữ cảnh này đáng công đến thế

| Guard bọc quanh khai báo | Đọc thô | Giá trị thực trên Windows |
|---|---|---|
| `IS_WIN \|\| IS_MAC \|\| IS_LINUX` | `enabled` | `enabled` — trùng nhau |
| `IS_ANDROID` … `#else` | `enabled` | **`disabled`** — đọc thô cho kết luận **ngược** |
| `ENABLE_PLUGINS` … `#else` | `enabled` | `conditional` — không đoán |

Chỉ trong `content_features.cc`, **14/187 cờ** có mặc định khác nhau theo nền
tảng. Đọc nhầm không phải sai số nhỏ, mà đảo ngược kết luận.

### Khoá phải bền qua thay đổi cú pháp

Đây là điều làm cả thiết kế đứng vững. Giữa M139 và M143, macro `BASE_FEATURE`
bỏ tham số tên chuỗi:

```cpp
BASE_FEATURE(kBackForwardCache, "BackForwardCache", ENABLED);  // <= M141
BASE_FEATURE(kBackForwardCache, ENABLED);                      // >= M142
```

Trong `content_features.cc`, M139 có 170/170 khai báo dạng cũ, M143 có 12/187.
**Một parser khoá theo văn bản nguồn sẽ báo cả file bị viết lại.**

Cơ chế chống lại: `feature_name_from_var()` bỏ tiền tố `k` — `kBackForwardCache`
→ `"BackForwardCache"` — đúng quy ước Chromium dùng khi tự suy tên. Dạng ba tham
số thì lấy chuỗi tường minh, dạng hai tham số thì suy ra. Cả hai về cùng một khoá.

Sau chuẩn hoá, delta thật là 152 giữ nguyên, 18 bỏ, 35 thêm.

Ví dụ của ta ra một fact:

```json
{ "kind": "base_feature", "key": "GlicActorUiMagicCursor",
  "path": "chrome/common/chrome_features.cc",
  "attrs": { "var": "kGlicActorUiMagicCursor",
             "default_state": "enabled",
             "platform_state": { "windows": "enabled" },
             "declared_form": "macro2", "conditions": [] } }
```

### Chống trùng và phạm vi

`dedupe_facts()` khoá theo `uid = kind:key`, giữ cái xuất hiện đầu, rồi **sắp xếp
ổn định** theo `(kind, key)`. Chromium khai báo vài feature ở nhiều nơi; không có
bước này thì diff thấy "modification ma" mà chiều của nó phụ thuộc thứ tự duyệt
thư mục.

Phạm vi trích xuất bám theo **target đã khai**, không theo "có gì trên đĩa". Cache
cây nguồn dùng chung theo ref, nên nếu để nó tự lấy phạm vi từ đĩa thì chạy
`--target-set minimal` trong thư mục mà lần chạy `default` trước đã đổ đầy sẽ cho
ra snapshot "minimal" chứa **đủ 21.595 fact** — đem diff với minimal thật thì bịa
ra khoảng 20.000 addition, không lỗi, không cảnh báo, và trông rất hợp lý.

---

## Bước 4. So sánh hai snapshot

**Code:** `diff.py`

### Cơ chế: ba lượt trên hai dict

`Snapshot.index()` dựng `{uid: Fact}` với `uid = f"{kind}:{key}"`:

```
uid cũ : ['base_feature:Flipped', 'base_feature:Gone', 'base_feature:Kept']
uid mới: ['base_feature:Flipped', 'base_feature:Kept', 'base_feature:New']
```

Rồi:

1. Duyệt `new_index` — không có trong cũ → **added**
2. Duyệt `new_index` — có trong cũ → so thuộc tính có nghĩa → có lệch thì **modified**
3. Duyệt `old_index` — không có trong mới → **removed**

Việc so là `dict != dict` trên tập thuộc tính đã lọc, nên độ phức tạp tuyến tính
và không phụ thuộc thứ tự.

### Quy tắc 1 — chỉ so thuộc tính có nghĩa

`MEANINGFUL_ATTRS` liệt kê, cho từng loại fact, những thuộc tính mà thay đổi của
chúng có ý nghĩa với hạ nguồn. Với `base_feature` là `default_state`,
`platform_state`, `conditions`.

`declared_form` **không** nằm trong đó. Chạy thật, cùng một feature viết bằng hai
dạng macro khác nhau, giá trị y nguyên:

```
attrs thô khác nhau : True
meaningful khác nhau: False
số change           : 0
```

Nếu `declared_form` được so, đợt đổi macro M139→M143 sẽ sinh ra hàng nghìn
"modification" chẳng nói lên gì.

`conditions` thì **có** trong danh sách, vì một fork thường không sửa code
upstream mà **bọc cờ build quanh nó**: guard xuất hiện hay biến mất chính *là*
thay đổi, trong khi giá trị đứng im.

Ví dụ của ta:

```
deltas = { default_state:  ["disabled", "enabled"],
           platform_state: [{windows: "disabled"}, {windows: "enabled"}] }
```

### Quy tắc 2 — signal, không phải chỉ "đã đổi"

Mỗi change nhận các **signal**: nhãn đọc được kèm mức nghiêm trọng sàn. Điểm cuối
là `max(BASE_SEVERITY[kind, type], max(sàn của các signal))`.

Chạy thật, ba tình huống:

```
modified Flipped  severity= 75  signals=['enabled_by_default', 'default_flip_on']
added    New      severity= 55  signals=['new_feature_on_by_default']
removed  Gone     severity= 35  signals=['flag_retired_on']
```

Vì sao tách `default_flip_on` (60) và `enabled_by_default` (75)?
Cái đầu nói **Chromium viết gì**; cái sau nói **người dùng của ta nhận gì**.
Chúng thường xuyên khác nhau, và chỉ cái sau mới đáng gọi là thay đổi hành vi —
nên nó có sàn cao hơn.

### Vì sao "biến mất" hầu như không phải "mất tính năng"

Chromium cho mọi tính năng đi qua **ba giai đoạn, cách nhau nhiều milestone**:

| Giai đoạn | Code | Người dùng thấy |
|---|---|---|
| A | Code mới về, cờ mặc định TẮT | không gì |
| B | Cờ lật thành BẬT | **chính là thay đổi** |
| C | Xoá nhánh cũ và xoá cờ | không gì |

Nên diff giữa hai phiên bản **chủ yếu thấy A và C**. Cơ chế phân biệt: khi một cờ
biến mất, đọc **trạng thái nó giữ ngay trước khi bị xoá**.

```python
prior = platform_state["windows"] của bản CŨ
if prior == "enabled":  → flag_retired_on   (sàn 35)
if prior == "disabled": → flag_retired_off  (sàn 30)
ngược lại:              → feature_deleted   (sàn 65)
```

Đo thật M148 → M151 trên Windows: **90 cờ bị xoá, chia đúng 45/45**. Gán cả 90 là
"tính năng bị xoá" thì một nửa danh sách là báo động giả.

Với Blink còn rõ hơn: M139 → M143 có 202 runtime feature biến mất, **170 cái
trước đó đang `stable`** — rút kill-switch sau khi đã ship, không phải mất API.
Xếp chúng thành "API bị xoá" là 170 báo động giả nằm đầu báo cáo. API bị xoá thật
được phát hiện từ diff của IDL, là nguồn đúng cho câu hỏi đó.

### Phát hiện đổi tên: cơ chế ghép theo biến C++

Với `pref`, `switch`, `base_feature`, **danh tính là một chuỗi**, còn biến C++
thì bền. Nên một lần đổi tên đi vào diff dưới dạng một removal và một addition
chẳng liên quan gì nhau — hậu quả thật nằm lọt giữa hai dòng đó.

`_detect_renames()` gom các change theo `(kind, attrs["var"])`. Nhóm nào có
**đúng một** addition và **đúng một** removal thì gộp thành một change duy nhất.
Yêu cầu "đúng một" là có chủ ý: nhiều hơn thì không còn là đổi tên rõ ràng, và
đoán bừa còn tệ hơn để rời.

Chạy thật trên ca có thật:

```
modified FedCmIdPregistration -> FedCmIdPRegistration
  signals=['feature_string_renamed'] severity=75
  deltas={'value': ['FedCmIdPregistration', 'FedCmIdPRegistration']}
```

M139 khai báo `BASE_FEATURE(kFedCmIdPRegistration, "FedCmIdPregistration", ...)`
— chữ `r` thường. M143 dùng macro hai tham số, tự suy tên từ biến → thành
`"FedCmIdPRegistration"`, chữ `R` hoa. **Không ai sửa tên; đợt đổi macro đã đổi
nó.** Mọi field trial phía server và mọi `--enable-features` gõ theo cách cũ từ
đó im lặng không có tác dụng. Không compiler nào cảnh báo.

Ở chế độ `--mode fork` bước ghép này **bị tắt**: qua một fork, removal + addition
cùng biến nghĩa là vendor thay cái này bằng cái kia — đó là **hai quyết định**,
không phải một lần đổi tên, và gộp lại là giấu mất một cái.

---

## Bước 5. Chấm điểm: "có đổi" so với "có ảnh hưởng tới **ta**"

**Code:** `sbprofile.py` (bằng chứng), `impact.py` (chấm điểm)

`diff.py` trả lời "cái này thường quan trọng cỡ nào". Bước này trả lời câu đội
ngũ thật sự hỏi: **có ảnh hưởng đến ta không.**

### Cơ chế đảo chiều quét

Thay vì grep Chromium tìm tên của Samsung, `build_vocabulary()` lấy **từ vựng của
snapshot** — mọi tên feature, switch, pref mà Chromium khai báo — rồi tìm các
token đó trong mã nguồn của fork, **một lượt duy nhất**.

Chạy thật:

```
token : ['BackForwardCache', 'Navigator', 'kBackForwardCache', 'kDownloadDir']
chuỗi : ['download.default_directory']
```

Chú ý cái **không** có: `before` — tên member trần của IDL bị loại có chủ ý. Web
IDL đầy member tên `before`, `after`, `has`, `values`, `close`; khớp chúng với văn
xuôi trong comment của patch từng tạo ra một dương tính giả rất tự tin ("ta có
tham chiếu `before`") từ đúng chữ "before" trong một câu tiếng Anh. Member chỉ có
nghĩa khi kèm interface, mà tên interface (`Navigator`) đã có trong từ vựng rồi.

Việc này biến bài toán "quét nhiều lượt trên cây khổng lồ" thành **một lượt trên
cây nhỏ**, và bắt được thứ danh sách patch bỏ lọt: code *đọc* một feature mà
không hề vá file khai báo nó.

Từ vựng dựng từ **cả hai** snapshot. Nếu chỉ dùng bản mới, một ký hiệu chỉ tồn
tại ở bản cũ sẽ bị lọc mất — mà đó chính là ca đáng giá nhất: thứ ta phụ thuộc và
upstream vừa xoá.

### Cơ chế cộng điểm

Chạy thật, cùng một change (`ServiceWorkerAutoPreload` lật BẬT, severity 75), bốn
mức bằng chứng:

```
không bằng chứng   score= 75  review
có vá file         score= 87  review
     +12 we patch 1 of the declaring file(s): content/features.cc
có nhắc ký hiệu    score=100  must_fix
     +30 our source references kServiceWorkerAutoPreload
cả hai + vùng      score=100  must_fix
     +12 we patch 1 of the declaring file(s)
     +30 our source references kServiceWorkerAutoPreload
     +15 owned area 'Network' (weight 75)
```

**Bằng chứng cấp ký hiệu (+30) nặng hơn cấp đường dẫn (+12) là có chủ ý.** Vá
`content_features.cc` gần như không nói gì — file đó khai báo gần 200 cờ. Nhắc
đúng định danh của cờ thì nói rất nhiều.

Điểm bị kẹp về `[0, 100]`, và có hai khoản trừ: `−45` nếu
`platform_state.windows == "not_compiled"`, `−45` nếu đường dẫn nằm trong
`ignore_paths`.

### Cơ chế xếp nhóm

```python
evidence      = có matched_symbols          # chỉ ký hiệu mới tính
weak_evidence = có matched_paths
breaking      = signal ∈ BREAKING_SIGNALS
opportunity   = signal ∈ OPPORTUNITY_SIGNALS  hoặc  change_type == added

evidence và (breaking hoặc score>=60)  -> must_fix
(evidence hoặc weak) và score>=35      -> review
opportunity và không breaking          -> opportunity
score>=65                              -> review
ngược lại                              -> fyi
```

Thứ tự kiểm quan trọng. Một API web lên `stable` có điểm cao vì nó **quan trọng**
— nhưng nó là "đây là thứ người dùng của bạn vừa có", không phải "đây là thứ có
thể vỡ". Để 150 mục như thế trôi vào danh sách review là cách một công cụ triage
biến thành thứ không ai mở nữa. Nên nhánh `opportunity` được kiểm **trước** nhánh
"điểm cao thì review".

Ví dụ của ta không có bằng chứng nào (`sb-profile.example.json5` là hồ sơ mẫu),
nên dừng ở `score 75, bucket review`. Nếu hồ sơ thật của SB có nhắc
`kGlicActorUiMagicCursor`, nó thành 100 và *must_fix*.

Mọi điều chỉnh điểm đều **ghi lại lý do đọc được**. Một bảng xếp hạng không cãi
lại được là bảng xếp hạng bị bỏ qua ngay lần đầu nó sai — và ở đây điểm số còn
quyết định người đọc tiêu công sức vào đâu, nên điểm không giải thích được sẽ
lan thành khuyến nghị không giải thích được.

---

## Bước 6. Gom mảnh rời thành một câu chuyện

**Code:** `cluster.py`

Một thay đổi upstream đi vào báo cáo dưới dạng nhiều mảnh trên nhiều bề mặt. Đợt
di trú Local Network Access giữa M148 và M151 sinh ra **7 finding riêng** — đọc
rời thì chúng **mâu thuẫn nhau**: dòng này bảo mất một trang, dòng kia bảo có
thêm trang.

### Cơ chế: union-find trên các cạnh dữ liệu tự khai

Không dùng độ giống tên. Chỉ đi theo liên kết mà **chính dữ liệu khai báo**:

```
webui_route  --guards-->       webui_gate
webui_gate   --features-->     base_feature
blink_runtime --base_feature--> base_feature
feature_param --feature-->     base_feature
webui_control --label--------> webui_route   (sau chuẩn hoá)
```

Cạnh cuối cần chuẩn hoá vì hai bên viết theo hai quy ước:

```
_norm('SITE_SETTINGS_LOCAL_NETWORK') = 'sitesettingslocalnetwork'
_norm('siteSettingsLocalNetwork')    = 'sitesettingslocalnetwork'
```

Chạy thật:

```
cụm 'LocalNetworkAccessChecks' — 4 mảnh:
    webui_route, webui_gate, base_feature, webui_control
đứng riêng: ['SomethingElse']
```

`SomethingElse` cũng là `base_feature` nhưng **không có cạnh nào nối tới**, nên
không bị kéo vào — đó chính là điều một quy tắc "tên giống nhau" sẽ làm sai.

Các cạnh được đọc trên **cả hai phía** của change. `SITE_SETTINGS_LOCAL_NETWORK`
được gác bởi `enableLocalNetworkAccessSplitPermissions` ở M148 và
`enableLocalNetworkAccessSetting` ở M151; chỉ đọc phía mới thì một cuộc di trú bị
tách thành hai cụm không liên quan.

Với Blink, chỉ nối khi Chromium **tự khai** liên kết: nhiều cờ Blink mang
`base_feature: "none"`, nghĩa là không có feature C++ nào để nối — bịa ra một cái
từ độ giống tên là đoán.

Đọc thành một cụm, 7 mảnh nói một điều đơn giản và đúng: trang chuyển sang split
permissions, người dùng đã thấy từ M148, và việc phải làm duy nhất là cập nhật
một tham chiếu route đã cũ.

---

## Bước 7. Bổ sung ngữ cảnh do người viết

**Code:** `enrich/chromestatus.py`

Extractor nói **cái gì** đổi; chromestatus.com nói **tại sao**, bằng văn xuôi do
người viết: tóm tắt, link spec, milestone ship.

Ghép từng mục thì tỉ lệ trúng rất thấp (~2%) vì tên bên đó là văn xuôi còn tên
trong mã là định danh. Nên thay vì cố ghép, công cụ ghi **cả danh sách "Chromium
đã ship gì trong khoảng này"** vào báo cáo như phần nền — khoảng 100 mục, ~8k
token, và bỏ hẳn được phép ghép mong manh.

Danh sách này từng chỉ tồn tại bên trong prompt gửi cho model. Khi chặng phán xét
bị bỏ đi, nó phải chuyển vào báo cáo: đó là nguồn duy nhất nói *upstream định ship
cái gì*, và tải về rồi vứt đi thì mất trắng. Nó nằm trong `report.json` dưới
`summary.milestone_brief`, và trong `report.md` dưới một khối `<details>` — có
nhãn rõ là **nền**, không phải là ý kiến thứ hai về bất kỳ dòng nào.

---

## Bước 8. Dừng ở đây — công cụ không phán xét

Luồng kết thúc ở bằng chứng và thứ hạng. Không có chặng nào kết luận "cái này có
nghĩa gì với sản phẩm của chúng ta".

Đó là chủ ý, không phải thiếu sót. Phần ấy cần suy xét, và nó thuộc về người đọc
báo cáo — hoặc về một agent chạy skill
[`analyzing-chromium-uprevs`](skills/analyzing-chromium-uprevs/SKILL.md), vốn là
nơi chứa quy trình phân loại, các bẫy đã biết, và giới hạn phải nêu trong mọi báo
cáo.

Hệ quả với thiết kế của các bước trước: **báo cáo chính là đầu vào**, nên nó phải
trích dẫn được. Đó là lý do mỗi finding luôn mang theo lý do chấm điểm, đường dẫn
khai báo, và bằng chứng phía fork — chứ không phải một con số đã tóm tắt mất dấu
vết. Toàn bộ 1.226 finding không-FYI của M148 → M151 gói lại ≈ 105k token, vừa
một lượt đọc.

Một hệ quả nữa: **không có chặng nào hỏng trong im lặng**. Bản trước có cột
verdict do model điền; khi request lỗi thì cột ấy rỗng, và một phân tích không
chạy trông y hệt một kết quả sạch — phải có một dòng cảnh báo riêng ở đầu báo cáo
mới phân biệt được. Giờ mọi thứ trong báo cáo đều là thứ đã trích ra được từ mã
nguồn, nên không còn khoảng trống nào để hiểu nhầm.

---

## Bước 9. Báo cáo

**Code:** `report/markdown.py`, `report/html.py`

Ba dạng ra:

- `report.md` — dán thẳng vào ticket
- `report.html` — bảng lọc/sắp xếp được, **tự chứa hoàn toàn**, không tải tài
  nguyên ngoài, nên mở được trong mạng cách ly và gửi kèm mail được
- `report.json` — cho script và so sánh giữa các kỳ

Thứ tự trình bày theo thứ tự người đọc cần: phân loại → việc phải làm → bằng chứng.
Mỗi finding hiện **lý do chấm điểm** để người đọc cãi lại được.

Lọc theo vùng xảy ra **lúc render, không bao giờ trước khi phân tích**: JSON luôn
giữ mọi finding, nên cắt lát theo đội không tốn gì và không giấu được gì.

```bash
python3 -m chromedrift report out/report.json --list-areas
python3 -m chromedrift report out/report.json --area downloads
```

Báo cáo cũng luôn in **số finding không thuộc vùng nào**. Đó không phải chú thích
bên lề: đo trên M148 → M151, tập không-vùng chứa 281 mục điểm ≥ 60, gồm **cả mười
mục nghiêm trọng nhất** — vốn là các thay đổi signature Mojo không thuộc sản phẩm
nào.

Tiêu đề và ý nghĩa từng nhóm đổi theo `--mode`: một báo cáo so fork được đặt tên
*"Fork divergence from upstream"* và nói rõ chiều so sánh, vì cùng một bảng mang
hai nghĩa hoàn toàn khác nhau tuỳ phép so nào đã chạy.

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
chỉnh chấm điểm và cách trình bày trở nên khả thi.

---

## Tự dựng lại các đoạn output ở trên

Mọi output trong tài liệu này chạy lại được. Ví dụ, cơ chế ngữ cảnh preprocessor:

```python
from chromedrift.extract._cpp import (mask_comments, conditional_spans,
    enclosing_conditions, eval_condition, resolve_platform_state)

SRC = open("chrome/common/chrome_features.cc").read()
masked = mask_comments(SRC)
spans  = conditional_spans(masked)
print(enclosing_conditions(spans, masked.index("kSomeFeature")))
print(eval_condition("BUILDFLAG(IS_WIN) && BUILDFLAG(ENABLE_PLUGINS)"))
```

---

## Đọc tiếp

- [COVERAGE.md](COVERAGE.md) — "tính năng" gồm những gì, và phủ được bao nhiêu
- [README.md](README.md) — giải thích từng nhóm code, chi tiết hơn
- [SETUP.md](SETUP.md) — cài đặt trên máy mới, xử lý sự cố
- [skills/analyzing-chromium-uprevs/](skills/analyzing-chromium-uprevs/) — quy
  trình dạng skill cho agent, kèm bẫy đã gặp và bảng tra signal
