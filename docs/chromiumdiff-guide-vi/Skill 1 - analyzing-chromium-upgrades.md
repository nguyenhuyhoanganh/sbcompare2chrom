---
name: analyzing-chromium-upgrades
description: So sánh hai version Chromium — feature flag, Web API, pref, switch, Mojo interface, các surface WebUI chrome:// (route, control, gate hiển thị) — tách thay đổi hành vi thật ra khỏi việc dọn dẹp, và tạo ra một báo cáo có xếp hạng về những gì đã dịch chuyển, định tuyến tới team sẽ phải sửa từng mục. Dùng khi lên kế hoạch hoặc rà soát một đợt nâng version Chromium, ví dụ M148 lên M151; khi được hỏi cái gì mới, cái gì bị bỏ, cái gì đã đổi giữa hai milestone Chromium; khi được hỏi một thay đổi của Chromium có làm hỏng gì không; khi cần diễn giải một bản diff Chromium thô; hoặc khi quyết định một đợt rebase đòi hỏi những việc gì.
---

# Phân tích một đợt nâng version Chromium

Chạy `chromiumdiff` trên hai version Chromium, rồi phân loại những gì nó tìm được và báo cáo đúng phần user cần. Công cụ lo phần xếp hạng; còn quyết định một thay đổi có nghĩa gì với một sản phẩm cụ thể là việc mà skill này mô tả.

**Một khai báo đã đổi không có nghĩa là một hành vi đã đổi.** Công cụ chỉ đọc khai báo, nên thứ nó gán cho mỗi dòng là *phân loại dựa trên những gì lần chạy đó đọc được*, không phải kết luận đã chắc về thực tế.

Việc của skill này là kiểm lại phân loại đó bằng ngữ cảnh mà công cụ không có. Nó sai theo hai chiều ngược nhau: **báo một thay đổi mà người dùng không hề thấy**, và **bỏ qua một dòng trông vô hại, trong khi nó làm hỏng thứ gì đó mà không có gì báo lỗi**.

## Từ vựng

Những từ dưới đây xuất hiện khắp phần còn lại của skill và trong `report.json`.

- **finding và change** — `finding` là một dòng của báo cáo, một phần tử của mảng `findings` trong `report.json`. Bên trong nó, `change` giữ phần mô tả khai báo đã đổi: `kind`, `signals`, `locations`, `before`, `after`.
- **signal** — nhãn mô tả vì sao thay đổi này quan trọng, kèm một mức nghiêm trọng sàn. Một finding có thể mang nhiều signal; signal có sàn cao nhất là signal quyết định, và báo cáo vừa gom nhóm vừa đặt tiêu đề cho finding theo chính nó. Nằm ở `change.signals`. Nghĩa của từng signal: **[reference/signals.md](reference/signals.md)**.
- **severity và score** — severity là cái giá của loại thay đổi đó, do signal quyết định. score là severity sau hai khoản trừ: không có trong bản build Windows ở cả hai phía → 0; xoá chưa được xác nhận → −15. Không có gì làm tăng score, nên score thấp hơn severity luôn kèm một câu trong `reasons` — trích câu đó, đừng trích con số.
- **bucket** — loại chuyện đã xảy ra, suy ra từ signal quyết định. Có đúng năm bucket và mỗi finding thuộc đúng một:

| Bucket | Nghĩa là |
|---|---|
| **Compatibility break** | Một contract bên ngoài binary không còn giữ nguyên, và không có gì ở khâu build cảnh báo: dữ liệu người dùng đã lưu, script khởi chạy, Finch config, website đang chạy thật, process ở đầu bên kia |
| **Behaviour change** | Bản build Windows chạy khác đi sau thay đổi này. Có người nhìn thấy được sự khác biệt |
| **New declarations** | Có khai báo ở version mới mà version cũ không có. Bản thân nó không tự bật cái gì lên |
| **Scheduled** | Một cái ngày, không phải một sự kiện. Chromium đã lên lịch xoá hoặc dời lịch. Chưa có gì xảy ra |
| **Upstream cleanup** | Chromium dọn thứ đã ngã ngũ, hoặc khai báo không nằm trong build Windows ở cả hai phía. Không có gì quan sát được đã dịch chuyển |

- **unconfirmed** — một boolean trên finding, bật khi lần chạy này chưa đọc đủ cây source để xác nhận sự vắng mặt mà dòng đó dựa vào. Không phải bucket: cùng một thay đổi sẽ mang cờ này ở bộ `default` và không mang ở bộ `wide`. Những dòng mang cờ nằm trong Upstream cleanup vì **thiếu bằng chứng**, *không* phải vì nhẹ — trên một lần chạy `wide` chúng là Compatibility break và cao hơn 15 điểm. `summary.unconfirmed` đếm chúng: 31 ở M148 → M151 với bộ `default`, 0 với bộ `wide`.

## Hai nhóm khai báo

Mười sáu `kind` của công cụ chia thành hai nhóm, khác nhau ở chỗ **có gì đứng chắn giữa một thay đổi trong code và người dùng hay không**. Nhóm nào quyết định câu hỏi phải hỏi. Hỏi nhầm câu thì ra kết luận sai.

Đọc `change.kind` của finding rồi tra bảng này trước khi phân tích nó.

| Nhóm | `change.kind` | Đứng chắn giữa code và người dùng |
|---|---|---|
| **1 — có flag chắn** | `base_feature`, `blink_runtime_feature`, `flag_entry`, `webui_route`, `webui_control`, `webui_gate` | giá trị mặc định của flag, theo từng platform |
| **2 — không có flag chắn** | `mojo_interface`, `mojo_method`, `mojo_struct`, `mojo_field`, `mojo_enum`, `pref`, `switch`, `feature_param` | không có gì |
| **1 hoặc 2** | `idl_interface`, `idl_member` | `[RuntimeEnabled]` trên member hoặc trên interface của nó, nếu có. Không có `[RuntimeEnabled]` thì đọc như nhóm 2 |

### Nhóm 1, có flag chắn — một thay đổi trong diff thường không phải thay đổi

Code đi qua ba giai đoạn, thường cách nhau vài milestone:

1. code mới được merge vào Chromium, flag đang tắt — người dùng không thấy gì
2. flag được bật lên — **đây mới là thay đổi**
3. flag bị xoá — người dùng không thấy gì

Một bản diff phần lớn cho thấy giai đoạn 1 và 3, tức là hai giai đoạn không ai thấy gì.

**Phải làm: đọc `platform_state.windows` trước đã.** Chưa đọc trạng thái flag thì chưa được viết "X đã đổi".

Đọc sai ở nhóm này ra kết quả: báo một thay đổi mà người dùng không hề thấy.

### Nhóm 2, không có flag chắn — một thay đổi trong diff luôn là thay đổi

Không có giai đoạn nào. Khai báo là contract, và nó đổi ngay lúc version mới được nhận vào mà không có gì báo:

- hai đầu của một Mojo interface đều sinh ra từ cùng một file, nên một signature đã đổi không bao giờ làm hỏng build
- Chromium bỏ qua một command-line switch không nhận ra và không báo gì cả
- một feature param bị xoá thì Finch config vẫn set nó như cũ, chỉ là không còn tác dụng nữa

**Phải làm: đừng đi tìm flag nào cả. Khai báo đã đổi nghĩa là đã hỏng rồi.**

Đọc sai ở nhóm này ra kết quả: kết luận không có gì xảy ra, trong khi có thứ đã hỏng mà không ai được báo.

### Đọc Compatibility break thì mặc định hỏi câu của nhóm 2

Đây là tính chất của bảng signal, không phải của một lần chạy: mọi signal `ipc_*`, `pref_*`, `switch_*` và `param_*` — phần lớn những signal đưa một finding vào Compatibility break — chỉ phát sinh từ khai báo nhóm 2. Nhóm 1 chỉ vào được Compatibility break trong vài trường hợp hiếm, ví dụ một `base::Feature` bị đổi tên hoặc một `webui_control` trỏ sang pref khác, chứ không phải qua việc một flag lật.

Số cụ thể đổi theo từng cặp version, nên đừng mang con số của cặp này sang cặp khác. Ở M148 → M151 chẳng hạn: 181 trong 276 dòng Compatibility break là nhóm 2, 94 dòng Web IDL tuỳ vào `[RuntimeEnabled]`, 1 dòng thuộc nhóm 1. **Thứ không đổi là mặc định: đọc Compatibility break thì hỏi câu của nhóm 2 trước.**

## Quy trình

```
- [ ] 1. Hỏi user: so hai version nào, cần đọc kỹ tới mức nào
- [ ] 2. Chạy chromiumdiff
- [ ] 3. Đọc báo cáo theo đúng thứ tự
- [ ] 4. Hỏi vì sao một dòng lại đổi — khi có người hỏi; render lại sau đó
- [ ] 5. Đọc từng finding bằng câu hỏi của đúng loại khai báo
- [ ] 6. Viết báo cáo theo đúng thứ user quan tâm, kèm phần giới hạn
```

### Bước 1: Hỏi user, rồi mới chạy

**Hỏi user ba câu dưới đây trước khi chạy bất cứ thứ gì.**

**Câu 1 — so hai version nào?** Đưa số milestone trần cũng chạy được: công cụ tự giải `151` thành bản stable mới nhất của milestone đó tính đến hôm nay. Nhưng như vậy cùng một câu lệnh chạy hai ngày khác nhau có thể ra hai kết quả khác nhau — `ServiceWorkerAutoPreload` là ENABLED ở 143.0.7499.40 và DISABLED ở 143.0.7499.194, hai bản stable của cùng milestone 143. Version thật sự được dùng nằm ở `from_ref` và `to_ref` trong `report.json`; trích báo cáo từ đó, đừng trích lại con số user đưa vào.

**Câu 2 — cần đọc kỹ tới mức nào?** User thường không biết "target set" là gì, nên hỏi bằng thứ họ nhận được chứ đừng hỏi bằng tên tuỳ chọn:

| User cần gì | Dùng | Đánh đổi |
|---|---|---|
| Xem nhanh đợt này có gì đổi | `default` — mặc định của công cụ | Đọc chưa tới một nửa số file. Một khai báo "biến mất" có thể chỉ là nằm trong file lần chạy này không mở |
| Quyết định đợt nâng version này có ship được không | `wide` | Đọc gần như toàn bộ cây source. Tải nặng hơn và lâu hơn nhiều, đổi lại kết luận "đã bị xoá" mới đáng tin |
| Chỉ muốn biết công cụ có chạy được không | `minimal` | Đọc 3 file. Không dùng để trả lời bất kỳ câu hỏi nào về nội dung |

Chi phí cụ thể của từng mức ở bảng trong Bước 2.

**Câu 3 — user muốn xem phần nào?** Không đọc hết được: một cặp version cho ra vài nghìn dòng. Hỏi user quan tâm cái gì rồi lọc theo đúng cái đó, đừng mặc định đổ cả báo cáo ra.

Hỏi bằng thứ user nói được, rồi ánh xạ sang một trong ba trục mà báo cáo lọc được:

| User nói | Lọc theo |
|---|---|
| "chỉ quan tâm cái gì hỏng" | bucket `contract` (**Compatibility break**) |
| "phần Mojo / IPC", "web API", "trang settings" | `change.kind` |
| "cái gì bật tắt hành vi", "contract với bên ngoài" | nhóm kind — mục *What happened* của `report.md` |

Nếu người đọc là người thật, **đưa thẳng trang `serve` cho họ**: nó có tối đa năm ô lọc chọn nhiều giá trị cùng lúc — bucket, surface, consequences, coverage, evidence — cộng một ô nhập từ khoá cần loại bỏ. Ô coverage chỉ hiện khi có dòng `unconfirmed`, ô evidence chỉ hiện sau khi đã tra CL. Họ tự chọn nhanh hơn mọi cách hỏi.

**Platform luôn là Windows.** Công cụ luôn so cho Windows và không tuỳ chọn nào đổi được điều đó — `meta.platform` trong `report.json` ghi lại là `windows`. Trạng thái của một flag nằm ở `change.before.platform_state.windows` và `change.after.platform_state.windows`. Ngay cạnh chúng có `default_state`: đó là mặc định chung của Chromium, không phải của Windows, và đọc nhầm sang nó là lỗi hay gặp nhất ở bước này.

**Còn thiếu gì khác thì hỏi user, đừng tự điền.**

### Bước 2: Chạy

Chạy mọi lệnh **từ thư mục gốc của repo `chromiumdiff`**: `python3 -m chromiumdiff` cần import được package, đứng ở thư mục khác nó báo `No module named chromiumdiff`. Mọi đường dẫn dưới đây đều tương đối so với gốc repo.

```bash
python3 -m chromiumdiff check          # kiểm tra máy, mạng, cache

python3 -m chromiumdiff run 148.0.7778.217 151.0.7922.138 \
  --out out/M148_to_M151
```

Thuần stdlib Python 3.9+, không cần cài gì, không cần checkout Chromium. Khoảng ba phút rưỡi cho một cặp khi chạy nguội; nửa giây khi đã có cache.

| `--target-set` | Tải mỗi version | Số file đọc |
|---|---:|---|
| `minimal` | ~1 MB | 3 |
| `default` | ~40 MB | chưa tới một nửa số file, hơn một nửa số flag |
| `wide` | ~337 MB | **gần như toàn bộ cây source** |

Lần chạy ghi ba file vào đúng thư mục `--out` vừa đưa:

```
out/M148_to_M151/report.md      dán vào ticket
out/M148_to_M151/report.html    mở bằng trình duyệt, lọc được
out/M148_to_M151/report.json    dữ liệu để viết script
```

Mọi lệnh sau đó — `serve`, `report`, `why.py` — nhận **thư mục đó hoặc chính file `report.json`**, không nhận thư mục cha. `serve out` sẽ báo `no report.json in out`.

Ba file mang ba thứ khác nhau, và **id của signal chỉ có trong `report.json`**:

| Cần gì | `report.md` | `report.html` | `report.json` |
|---|---|---|---|
| id signal (`pref_left_scan`, `ipc_shape_changed`…) | không có — chỉ in nhãn chữ, ví dụ *Mojo data shape changed (ABI)* | chỉ nằm trong ô lọc | `change.signals` |
| bucket của từng dòng | ngầm theo tên mục | có | `bucket` |
| lần chạy có xác nhận được sự vắng mặt không | mục *Unconfirmed* riêng | badge trên dòng, ô lọc `All coverage` | `unconfirmed`, và `summary.unconfirmed` |
| `platform_state`, score, severity, `path:line` | có | có | có |

**Lọc hay rẽ nhánh theo signal thì phải đọc `report.json`.** `report.md` là bản cho người đọc, `report.html` cộng `serve` là bản cho người bấm chuột.

Source Chromium tải về nằm trong `.chromiumdiff-cache/` ở gốc repo, đổi được bằng `--cache` hoặc biến môi trường `CHROMIUMDIFF_CACHE`. Nó tái tạo được — xoá đi chỉ làm lần chạy sau chậm lại. `check` in ra thư mục cache, chỗ trống còn lại và ước lượng dung lượng một cặp version cần.

Mỗi finding đều dẫn `path:line` trong `change.locations` — trích nguyên văn, đừng bao giờ diễn đạt lại tên file.

**Chỉ mình `report.html` trả lời được *cái gì* đã đổi, không bao giờ trả lời *vì sao*.** Mở như một file, nó là một bảng đầy đủ, chạy offline; nhưng phần tra cứu "vì sao dòng này đổi" của từng dòng không chạy được ở đó, vì một trang trên `file://` không được phép gọi `chromium-review.googlesource.com` và trình duyệt chặn ngay trước khi request kịp gửi đi. Serve thư mục đó lên sẽ đổi người đi hỏi — trang gọi về localhost, và Python mới là bên hỏi Gerrit:

```
python3 -m chromiumdiff serve out/M148_to_M151     # in ra http://127.0.0.1:8787/
```

Hãy đề xuất cách này mỗi khi có người hỏi vì sao một dòng đổi, một flag để làm gì, hoặc nên đọc review nào. Bạn có thể tự khởi động nó rồi đưa URL cho họ. Mở thẳng `report.html` rồi kết luận phần tra cứu bị hỏng là sai: nó không chạy vì `file://`, không phải vì lỗi.

**Công cụ không kết luận thay bạn.** Nó dừng ở bằng chứng trích được và một thứ hạng tất định. Nó không biết gì về việc ai patch, ai ship hay ai override cái gì: một dòng **Compatibility break** nói rằng một contract đã dịch chuyển, chứ không nói rằng có ai đang dựa vào contract đó.

**Mỗi lần chạy đều in ra coverage đạt được.** Trích con số đó vào báo cáo; đừng bao giờ trích một con số từ chính file này.

```
coverage: reads N of M files in this tree that could declare (P% of files)
```

**Coverage làm đổi câu trả lời, chứ không chỉ đổi độ tin cậy.** Một mục bị xoá là suy luận từ sự vắng mặt, nên khi đọc thiếu nó bị trừ 15 điểm, bị xếp vào Upstream cleanup thay vì Compatibility break, và mang cờ `unconfirmed`. Đo trên M148 → M151: `default` tìm được 139 dòng `pref_left_scan`, `wide` tìm được 171 — nhưng chỉ 30 trong số đó có trong bản build Windows, và đúng 30 dòng ấy chuyển từ Upstream cleanup 20 điểm sang Compatibility break 35 điểm khi chạy `wide`. Số còn lại về 0 điểm ở cả hai lần chạy. **`Compatibility break: 0` trên một lần chạy `default` không có nghĩa là không có gì hỏng** — đọc `summary.unconfirmed` trước khi nói vậy.

**Hai thông báo lỗi, cùng một nguyên nhân.** `cannot diff snapshots built from different target sets` và `cannot diff: X holds N facts against Y's M` đều nói rằng một bên chỉ đọc được một phần nhỏ so với bên kia. Cả hai đều không phải lỗi cần lách: kiểm tra xem `--local-src` / `--from-src` / `--to-src` có trỏ vào một thư mục `src/` Chromium đầy đủ hay không.

`--partition settings` (lặp lại được: `downloads`, `bookmarks`, `history`, `extensions`, `passwords`, `printing`, `newtab`, `webplatform`, `network`, `media`) chỉ tải và quét những đường dẫn source đã liệt kê sẵn cho một tính năng. Đúng khi đang soi một tính năng, sai khi dùng làm cổng chặn release — Chromium không tổ chức source theo tính năng, nên một thay đổi ảnh hưởng tới downloads có thể nằm trong `content/` và không khớp partition nào.

Hai lệnh phụ: `chromiumdiff catalog <ref>` đo xem target set đang bỏ sót những gì; `chromiumdiff figures <report.json>` ghi ra các con số mà chính tài liệu của project trích dẫn, và đó là cách chúng luôn đúng. Lệnh render lại báo cáo nằm ở Bước 4, chỗ nói vì sao cần nó.

### Bước 3: Đọc báo cáo theo đúng thứ tự

Báo cáo đã xếp sẵn theo điểm, cao nhất trước. **Đó không phải thứ tự đọc, và cũng không phải chỗ để cắt.** Một dòng Compatibility break mà lần chạy không xác nhận được sẽ bị trừ 15 điểm và tụt xuống dưới hàng nghìn dòng ít hậu quả hơn. Đo ở M148 → M151: đọc 100 dòng điểm cao nhất bỏ sót 232 trong 276 dòng Compatibility break; đọc 500 dòng vẫn bỏ sót 55. Điểm để xếp thứ tự bên trong một bucket, không để quyết định đọc tới đâu.

Danh sách dài thì **gom theo signal**, đừng cắt bớt: ở cặp version đó, bốn bucket trên Upstream cleanup là 2.287 dòng nhưng chỉ 39 leading signal khác nhau. Xem mỗi nhóm signal một lần là đã phủ hết.

Đọc theo bucket, theo đúng thứ tự dưới đây.

1. **Cái gì đã đổi** — bảng đếm theo bucket, ở đầu `report.md`. Bắt đầu từ đây; nó cho biết mỗi danh sách dài bao nhiêu.
2. **Chuyện gì đã xảy ra** — mọi finding được gom theo signal đã quyết định mức nghiêm trọng của nó, nên một báo cáo vài nghìn dòng gom lại chỉ còn vài chục nhóm.
3. **Compatibility break**, rồi **Behaviour change**, rồi **New declarations**. Mỗi bucket có một bảng riêng trong `report.md`.
4. **Scheduled** — cũng có bảng. Đọc như danh sách của milestone sau, không phải của milestone này: chưa có gì trong đó xảy ra. Đây cũng không phải bucket "điểm thấp": ở M148 → M151 nó lên tới 45 điểm, cao hơn mọi dòng trong New declarations, vì `flag_expiring` là một cái xoá Chromium đã cam kết.
5. **Unconfirmed** — có mục riêng trong `report.md`, và ô lọc `All coverage` trong `report.html`. Đây là những mục bị xoá mà lần chạy này không xác nhận được. Phần lớn giữ nguyên bucket và chỉ mất 15 điểm; riêng `pref_left_scan` và `switch_left_scan` còn bị chuyển sang Upstream cleanup — nằm ở đó vì **thiếu bằng chứng**, *không* phải vì nhẹ. Bước 5, nhánh *Flag, pref và switch*, nói phải làm gì với chúng. 303 dòng ở M148 → M151 với bộ `default`, 120 trong số đó ở Compatibility break; một lần chạy `wide` không có dòng nào.
6. **Upstream cleanup**: bỏ qua. Nó cố ý không có bảng — đây là bucket lớn nhất trong mọi báo cáo, và khi Scheduled với Unconfirmed đã tách ra thì phần còn lại không cần làm gì. Ở M148 → M151 nó chỉ lên tới 35 điểm.

Flag bị gỡ nằm ở Upstream cleanup, và đó là cố ý: ở M148 → M151 có 132 flag như vậy, 72 flag đã từng ship và 60 flag bị bỏ, không cái nào người dùng thấy được. Báo cáo một trong số đó như một tính năng bị mất là sai — đọc [reference/traps.md](reference/traps.md) trước khi kết luận.

### Bước 4: Hỏi vì sao một dòng lại đổi

Mở rộng một dòng trong trang được serve sẽ tra cứu review đã tạo ra thay đổi đó. Nó đọc các CL đã chạm vào file chứa khai báo trong khoảng giữa hai milestone, rồi giữ lại những CL mà một bản diff buộc được vào *chính* identifier này — một file khai báo là của chung, và đã có 500 CL được merge chạm vào `about_flags.cc` giữa M148 và M151, nên chỉ riêng cái tên file thì không trả lời được gì.

Thứ trả về là một CL, issue mà CL đó dẫn, và những CL khác cũng dẫn cùng issue ấy — đó là lịch sử sửa lỗi của bug đứng sau thay đổi này. Mỗi CL mang theo verdict đã đưa nó vào danh sách, và các verdict không bao giờ bị gộp lại thành một điểm số:

| Verdict | Nó khẳng định điều gì |
|---|---|
| `introduced` | **ngay bên trong khai báo này**, một dòng đã nhận giá trị mà khai báo kết thúc bằng, hoặc mất đi giá trị mà khai báo bắt đầu bằng — CL này *chính là* thay đổi |
| `exact` | một dòng mà CL này sửa có chứa identifier |
| `moved` | file bị đổi tên và khai báo đi theo; không dòng nào đổi |
| `declares` | CL sửa phần thân của khai báo, không phải dòng đặt tên cho nó |
| `described` | tiêu đề hoặc mô tả của chính CL có gọi tên nó; không đọc diff nào |
| `crowded` | nhiều CL cùng sửa khai báo này nên không CL nào tách riêng ra được — đọc như lịch sử của khai báo đó, cũ nhất trước |
| `touched` | không có gì khớp identifier; những CL này chỉ đơn giản là có chạm vào file |

Hai loại cuối không chỉ đích danh khai báo nào. Đừng bao giờ trích chúng như nguyên nhân; hãy nói đúng bản chất của chúng.

Kết quả tra cứu được ghi ngược vào `report.json`, nên chúng vẫn còn sau khi khởi động lại. Chúng chỉ vào tới `report.md` và `report.html` khi render lại, và `serve` không tự làm việc đó cho bạn — nó in ra câu lệnh khi bạn dừng nó:

```bash
python3 -m chromiumdiff report out/M148_to_M151/report.json --format both --out out/M148_to_M151/report
```

Hãy làm việc đó trước khi trích báo cáo cho bất kỳ ai: những gì bạn tìm được bằng cách bấm chuột nằm trong JSON, còn hai file trên đĩa vẫn là hai file mà lần chạy đã ghi ra.

`--click-budget N` giới hạn số diff đọc cho mỗi dòng (mặc định 600), `--no-save` thì không đụng vào file. Lịch sử của một issue không được tải về cùng với dòng: bấm vào issue trên CL mà bạn tin, nó sẽ mở ra ngay dưới CL đó.

**Một issue bị hạn chế truy cập là chuyện bình thường, không phải một thất bại.** Khoảng bốn trong mười issue được dẫn trả về HTTP 403 — chúng nằm trong các component security, abuse hoặc nội bộ Google của tracker. Panel nói rõ điều đó và vẫn giữ link, vì người đọc có thể chính là người duy nhất mở được. **Dù thế nào thì các CL vẫn đọc được**: chúng nằm trên Gerrit, chúng công khai, và tiêu đề của chúng cho biết issue nói về cái gì. Hãy báo cáo lịch sử sửa lỗi, đừng chỉ báo cáo là không mở được issue.

**Không tìm thấy CL nào chỉ có nghĩa là lần tìm này không thấy, không có nghĩa là Chromium không đổi.** Hai cây source khác nhau, nghĩa là đã có gì đó vào cây. File được hỏi theo ba cách — trên nhánh main, rồi ngoài main để bắt các bản merge-back, rồi toàn bộ commit message trong khoảng thời gian đó — và nếu cả ba đều trượt thì CL được ghi dưới một cái tên hoặc một đường dẫn mà báo cáo này không giữ. Hãy nói đúng như vậy; đừng báo cáo rằng một khai báo tự nó đổi.

### Bước 5: Đọc từng finding bằng câu hỏi của đúng loại khai báo

Đọc `change.kind` của finding, rẽ nhánh theo bảng dưới, rồi hỏi đúng câu của nhánh đó.

**Mojo** — `mojo_interface`, `mojo_method`, `mojo_struct`, `mojo_field`, `mojo_enum`

1. `platform_state.windows` — `not_compiled` thì đã có điểm bằng không; `conditional` là chưa xác định, không phải mặc định là của mình. Một khai báo nằm dưới `android/`, `ash/`, `chromeos/` hay `ios/` thì hoàn toàn không có guard nào.
2. **Ai ở đầu bên kia?** Cả hai đầu đều biên dịch từ cùng một cây source, nên đây là lỗi build cho code nằm ngoài cây trước khi nó là lỗi lúc chạy. Bẫy 10 trong [reference/traps.md](reference/traps.md) liệt kê những trường hợp nó là lỗi lúc chạy. Hãy nói rõ trường hợp nào đang áp dụng.
3. `ipc_shape_changed` và `ipc_signature_change` làm hỏng deserialization mà không báo lỗi. `ipc_enum_changed` nhẹ hơn: một giá trị lạ bị từ chối chứ không bị đọc sai.

**Web platform** — `idl_interface`, `idl_member`, `blink_runtime_feature`

1. **Một trang web có với tới được không?** `web_api_added_live` so với `web_api_added_gated`. `web_api_added` nghĩa là flag chắn nó nằm ngoài phạm vi lần chạy này đọc — kiểm tra trước khi kết luận theo bất kỳ hướng nào.
2. `web_api_removed` làm hỏng các site đang chạy thật; `web_api_removed_gated` thì chưa tới người dùng nào.
3. `web_api_shipped` là thời điểm người dùng thật sự nhận được nó.

**Flag, pref và switch** — `base_feature`, `feature_param`, `pref`, `switch`, `flag_entry`

1. **Trạng thái của flag có đổi trên platform của mình không?** Xem `platform_state`. `disabled → enabled` hoặc ngược lại là một thay đổi hành vi thật. Dừng ở đó.
2. **Flag có biến mất không?** Đọc trạng thái nó giữ *trước đó*. `flag_retired_on` / `flag_retired_off` nghĩa là hành vi ở đây không đổi.
3. **Sự biến mất đó đã được xác nhận chưa?** `pref_left_scan` / `switch_left_scan` nghĩa là "không có trong những file mà lần chạy này đọc". Tìm key đó trong cây source, hoặc chạy lại với `wide`, trước khi báo cáo theo bất kỳ hướng nào.

**Trang chrome://** — `webui_route`, `webui_control`, `webui_gate`

1. **Lần theo guard để ra flag của nó.** Một control hay một trang biến mất thường là đã chuyển ra sau một guard khác, và thay đổi mà người dùng thấy đã xảy ra vào lúc flag đó lật. Bẫy 2 và 6 trong [reference/traps.md](reference/traps.md).

**Sửa ở ngoài repository** — nhánh này không theo `kind` mà theo signal. Chín signal dưới đây đều biên dịch bình thường rồi ngừng hoạt động ngoài thực địa, và chỗ phải sửa là Finch config, script khởi chạy hoặc automation chứ không phải file khai báo:

`feature_string_renamed`, `switch_renamed`, `param_removed`, `param_rewired`, `flag_retired_on`, `flag_retired_off`, `killswitch_retired`, `flag_expiring`, `flag_expiry_moved`

1. **Luôn có việc phải làm nếu cái tên cũ còn xuất hiện ở đâu đó.** Bốn signal đầu làm chết thứ đang set giá trị từ bên ngoài. Ba signal tiếp theo là flag bị gỡ, làm mọi override đặt từ bên ngoài mất tác dụng mà không có gì báo. Hai signal cuối là lịch xoá: một flag có ngày hết hạn nghĩa là override đặt lên nó cũng có hạn.
2. Công cụ không nhìn thấy bất kỳ nơi nào trong số đó. Đây là danh sách những thứ cần kiểm tra, không phải danh sách những thứ đã hỏng.

Ý nghĩa từng signal: **[reference/signals.md](reference/signals.md)**.

### Bước 6: Viết báo cáo theo đúng thứ user quan tâm

Bố cục do Câu 3 quyết định — gom theo đúng thứ user đã nêu, và ghi rõ đã lọc theo cái gì. Mẫu dưới đây là mặc định khi user không nêu gì: gom theo nhánh của Bước 5.

```markdown
## Overall risk
[Một câu về mức rủi ro, và nhánh nào chiếm phần lớn rủi ro đó.]

## Mojo — N to look at
## Web platform — N
## Flags, prefs and switches — N
## chrome:// pages — N
[Bỏ qua mục không có gì trong Compatibility break hay Behaviour change, và nói rõ là đã bỏ.]

## Fixed outside the repository — N
[Luôn có mặt, luôn ở cuối, kể cả khi đã lọc: một tên flag hay switch bị đổi làm chết override của bất kỳ ai đặt nó, không riêng ai.]

## New capability
[Chỉ `web_api_added_live`. Đây là đầu vào cho sản phẩm, không phải thứ chặn release.]

## Limits
[Con số coverage mà lần chạy đã in ra, target set, partition, version chính xác.]
```

Mỗi finding cần ba phần: **cái gì đã dịch chuyển**, **người dùng có thấy khác đi không**, **ai đó phải làm gì**. Phần ở giữa quyết định độ ưu tiên, và một bản diff thô không cung cấp được nó.

Sai: *"`LocalNetworkAccessChecksSplitPermissions` đã bị xoá ở M151."*

Đúng: *"Local Network Access đã chuyển sang cơ chế split permissions. Flag này đã ENABLED từ M148, nên người dùng đã thấy điều này từ trước bản nền hiện tại của chúng ta; M151 chỉ cho flag nghỉ hưu. Không có thay đổi hành vi. Việc cần làm: cập nhật mọi chỗ còn tham chiếu tới `kLocalNetworkAccessChecksSplitPermissions` hoặc route `/localNetworkAccess`."*

## Tài liệu tham chiếu

- **[reference/traps.md](reference/traps.md)** — những con đường dẫn tới kết luận sai, mỗi con đường đều được đo trên dữ liệu Chromium thật. Đọc trước khi diễn giải bất kỳ mục bị xoá nào; các bẫy về sau nói về Mojo, web API và switch.
- **[reference/signals.md](reference/signals.md)** — mỗi signal nghĩa là gì.
- **[reference/settings-surface.md](reference/settings-surface.md)** — chuỗi ba chặng từ một trang settings tới flag đứng sau nó, và cách ước lượng quy mô của một "feature".

## Những gì công cụ không nhìn thấy

Nêu những điều này trong mọi báo cáo. Một báo cáo sạch không có nghĩa là một đợt nâng version sạch.

- **Liệu có phần nào trong đó chạm tới một sản phẩm cụ thể hay không.** Công cụ so Chromium với Chromium. Tìm identifier mà một finding dẫn ra trong cây source của chính mình mới là bước trả lời câu "cái này có ảnh hưởng tới mình không".
- **Thay đổi chỉ nằm ở phần cài đặt.** Nó đọc khai báo. Hành vi đổi bên trong thân một hàm thì nó không thấy.
- **Năm loại khai báo mà nó không biến thành fact**, ngay trong những file mà nó vẫn đọc đầy đủ. Đo ở M151: 85 định nghĩa `callback` của Web IDL, 144 `typedef`, 200 quan hệ `Interface includes Mixin`, 18 khối `feature` của Mojo và 311 hằng số Mojo. Ví dụ thật không tạo ra dòng nào: `typedef LanguageModelMessageValue` đổi union nền của nó ở M143 → M147, và hằng số Mojo `kWebNNDirectML` biến mất ở M151. **"Đọc 99% số file" là phát biểu về file, không phải về ngữ pháp.**
- **Bất cứ thứ gì nằm ngoài repository** — config Finch, script khởi chạy, test automation, enterprise policy, metadata trên store.
- **IDL của Chrome Extensions và MIDL.** Chỉ có `.idl` của riêng Blink được đọc.
- **Hành vi của trang.** Chỉ các phần khai báo của một surface WebUI: bảng route và các template HTML, không phải TypeScript.
- **Giao diện đã render.** Không ảnh chụp màn hình, không layout, không lỗi hiển thị.

Dùng flag và khai báo để *phát hiện*, đọc code có chủ đích để *giải thích*, ảnh chụp màn hình chỉ để *xác nhận* một danh sách ngắn. Đừng dùng ảnh chụp màn hình để phát hiện thay đổi.
