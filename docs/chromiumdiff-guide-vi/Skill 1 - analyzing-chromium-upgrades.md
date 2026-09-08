---
name: analyzing-chromium-upgrades
description: So sánh hai version Chromium và giải thích các thay đổi có liên quan, dựa trên finding của báo cáo, source đúng version và lịch sử commit. Dùng khi phân tích một đợt nâng version Chromium, khi diễn giải báo cáo chromiumdiff, kèm tác động, việc cần làm và giới hạn coverage nêu rõ.
---

# Phân tích một đợt nâng version Chromium

Giải thích cái gì đã đổi giữa hai version Chromium, các thay đổi liên quan
với nhau ra sao, và user cần kiểm tra hoặc cập nhật cái gì.

Phân chia công việc: script trích xuất khai báo và so sánh chúng; agent quyết
định các khác biệt đó có nghĩa gì. Bucket, score, signal và cluster là kết quả
phân loại của script, không phải kết luận cuối cùng.

Tài liệu này là bản tiếng Việt của skill `analyzing-chromium-upgrades`. Bản
tiếng Anh trong `skills/analyzing-chromium-upgrades/` là bản chuẩn; khi hai bản
lệch nhau thì lấy bản tiếng Anh.

## Từ vựng

Dùng các từ dưới đây nhất quán trong toàn bộ quá trình phân tích.

| Từ | Nghĩa |
|---|---|
| **fact** | Một khai báo được trích xuất từ một version. Một fact có thể không hề đổi. |
| **finding** | Một khác biệt giữa các fact, định danh bằng `kind:key`. |
| **source delta** | Một khác biệt trong nội dung file, kể cả phần code mà parser không hiểu. |
| **hunk** | Một đoạn trong bản diff của một file. |
| **event** | Một thay đổi có liên quan, được giải thích thành một mục trong báo cáo cuối. Một event có thể gồm nhiều finding, nhiều file và nhiều commit, hoặc chỉ một finding. |
| **consumer** | Code hoặc hệ thống bên ngoài gọi một API, đọc một giá trị, hiện thực một interface, hoặc phụ thuộc theo cách khác vào hành vi đã đổi. |
| **gate** | Một điều kiện quyết định code hay API có sẵn dùng hay không. |
| **rollout** | Mức độ sẵn dùng thật sự trong sản phẩm đã triển khai. Nó có thể khác với giá trị mặc định khai báo trong source. |

Các từ dưới đây là của báo cáo, không phải của quá trình phân tích.

- **signal** — nhãn do code so sánh gán cho một finding, mô tả thay đổi được
  ghi nhận hoặc cách classifier diễn giải nó. Nằm ở `change.signals`. Một
  finding có thể mang nhiều signal, hoặc không mang signal nào. Ở lần chạy
  M148 → M151 với bộ `default`, 981 trong 3.022 finding không mang signal nào,
  và chúng vẫn cần phân tích như mọi finding khác.
- **severity và score** — severity là mức của loại thay đổi, do signal quyết
  định. score là severity sau hai khoản trừ: khai báo không có trong bản build
  Windows ở cả hai phía → 0; xoá chưa được xác nhận → −15. Không có gì làm tăng
  score. Score là thứ tự ưu tiên công việc, không phải xác suất hay mức độ tin
  cậy. Mỗi khoản trừ đều kèm một câu trong `reasons`; trích câu đó.
- **bucket** — nhóm chuyện đã xảy ra, suy ra từ signal quyết định. Có đúng năm
  bucket và mỗi finding thuộc đúng một. Bucket dùng để sắp xếp báo cáo thô,
  không dùng làm tiêu đề cho báo cáo cuối.

| Bucket | Dùng nó để làm gì trong lúc phân tích |
|---|---|
| **Compatibility break** | Kiểm tra các contract có thể đã đổi, và xác định consumer nào thật sự bị ảnh hưởng |
| **Behaviour change** | Xác định khai báo đã đổi có làm đổi hành vi trong điều kiện liên quan hay không |
| **New declarations** | Kiểm tra khả năng có capability mới và điều kiện của nó; một khai báo không tự chứng minh là nó đã sẵn dùng |
| **Scheduled** | Kiểm tra công việc tương lai ghi trong metadata; phân biệt kế hoạch với việc đã làm |
| **Upstream cleanup** | Xác minh thay đổi là không đổi hành vi, là bị loại khỏi platform, hay là do bằng chứng vắng mặt không đủ |

- **unconfirmed** — một boolean trên finding, bật khi lần chạy chưa đọc đủ
  source để xác nhận sự vắng mặt mà finding đó dựa vào. Nó không phải bucket
  thứ sáu: cùng một thay đổi sẽ mang cờ này ở bộ `default` và không mang ở bộ
  `wide`. Ở M148 → M151 với bộ `default`, `summary.unconfirmed` là 303, trong
  đó 120 nằm ở Compatibility break; lần chạy `wide` không có dòng nào.
  Chạy rộng hơn cải thiện coverage theo file, không chứng minh parser đã đọc
  hết ngữ pháp hay đã phủ hết hành vi.

## Hai nhóm khai báo

Mười sáu `kind` chia thành hai nhóm, khác nhau ở chỗ có gì đứng chắn giữa một
thay đổi trong code và người dùng hay không. Nhóm quyết định câu hỏi phải hỏi.

| Nhóm | `change.kind` | Đứng chắn giữa code và người dùng |
|---|---|---|
| **1 — có gate** | `base_feature`, `blink_runtime_feature`, `flag_entry`, `webui_route`, `webui_control`, `webui_gate` | giá trị mặc định của flag, theo từng platform |
| **2 — không có gate** | `mojo_interface`, `mojo_method`, `mojo_struct`, `mojo_field`, `mojo_enum`, `pref`, `switch`, `feature_param` | không có gì |
| **1 hoặc 2** | `idl_interface`, `idl_member` | `[RuntimeEnabled]` trên member hoặc trên interface chứa nó, nếu có. Không có `[RuntimeEnabled]` thì đọc như nhóm 2 |

**Nhóm 1.** Code thường đi qua ba giai đoạn cách nhau vài milestone: merge vào
Chromium khi flag đang tắt, bật flag, rồi xoá flag. Chỉ giai đoạn giữa mới đổi
hành vi. Đọc `platform_state.windows` ở cả hai phía trước khi kết luận. Đọc
sai ở nhóm này cho ra kết quả: báo một thay đổi mà người dùng không hề thấy.

**Nhóm 2.** Không có giai đoạn nào. Khai báo chính là contract, và nó đổi ngay
khi version mới được nhận vào:

- hai đầu của một Mojo interface sinh ra từ cùng một cây source, nên một
  signature đã đổi không làm hỏng build của chính Chromium
- Chromium bỏ qua một command-line switch không nhận ra và không báo gì
- một feature param bị xoá thì Finch config vẫn set nó, chỉ là không còn tác dụng

Đọc sai ở nhóm này cho ra kết quả: kết luận không có gì xảy ra, trong khi có
thứ đã hỏng mà không có gì báo lỗi.

**Đọc Compatibility break thì mặc định hỏi câu của nhóm 2.** Mọi signal
`ipc_*`, `pref_*`, `switch_*` và `param_*` chỉ phát sinh từ khai báo nhóm 2.
Số cụ thể đổi theo từng cặp version. Ở M148 → M151 với bộ `default`: 181 trong
276 dòng Compatibility break là nhóm 2, 93 dòng là Web IDL (tuỳ vào
`[RuntimeEnabled]`), 2 dòng thuộc nhóm 1.

## Bắt đầu hoặc tiếp tục một lần so sánh

Dùng version và phạm vi mà user đưa. Thiếu version thì hỏi. Phạm vi không rõ
thì nêu một mặc định hợp lý. Một yêu cầu rà soát rộng bao gồm capability mới,
thay đổi hành vi, thay đổi API, migration và công việc đã lên lịch; không thu
hẹp nó thành riêng các vấn đề tương thích.

Chạy mọi lệnh **từ thư mục gốc của repo**: `python3 -m chromiumdiff` cần import
được package, đứng ở thư mục khác nó báo `No module named chromiumdiff`. Mọi
đường dẫn dưới đây tương đối so với gốc repo. Chỉ cần stdlib Python 3.9+.

Script so sánh theo điều kiện của Windows và không có tuỳ chọn CLI nào đổi
được điều đó. Ghi lại `from_ref` và `to_ref` chính xác mà báo cáo trả về: số
milestone trần có thể giải ra bản khác ở lần chạy sau.

Với một lần so sánh mới:

```bash
cache_dir=.chromiumdiff-cache
python3 -m chromiumdiff check
python3 -m chromiumdiff run FROM TO --target-set wide --cache "$cache_dir" --out out/upgrade
python3 -m chromiumdiff review init out/upgrade --directory out/upgrade/review --cache "$cache_dir"
```

Thay FROM/TO và đường dẫn output bằng lần so sánh được yêu cầu.

| `--target-set` | Tải mỗi version | Đọc được gì |
|---|---:|---|
| `minimal` | ~1 MB | 3 file. Chỉ để kiểm tra công cụ chạy được, không trả lời câu hỏi nội dung nào |
| `default` | ~40 MB | chưa tới một nửa số file, hơn một nửa số flag |
| `wide` | ~337 MB | gần như toàn bộ cây source. Đọc nhiều file được hỗ trợ hơn, không phải toàn bộ code hay toàn bộ ngữ pháp |

`--partition` thu hẹp phạm vi xuống các đường dẫn đã liệt kê sẵn cho một tính
năng (`settings`, `downloads`, `bookmarks`, `history`, `extensions`,
`passwords`, `printing`, `newtab`, `webplatform`, `network`, `media`). Đúng khi
đang soi một tính năng, sai khi dùng làm cổng chặn release: Chromium không tổ
chức source theo tính năng, nên một thay đổi ảnh hưởng tới downloads có thể nằm
trong `content/` và không khớp partition nào.

**Đã có báo cáo nhưng chưa có review:** chạy `review init` với đúng cache của
báo cáo đó. **Đã có review:** tiếp tục bằng `index`, `events` và `check`; đừng
init lại trừ khi input đã đổi.

**Có repo Git Chromium ở máy** thì thêm `--source-repo /path/to/chromium/src`
vào lần `review init` đầu tiên. Nó cho danh sách đầy đủ mọi đường dẫn đã đổi
giữa hai ref, đọc thẳng từ Git object và không đụng vào checkout. Không có Git
thì phần so sánh source chỉ phủ các file đã có trong cache, và một file thiếu
trong cache nghĩa là **chưa biết nội dung**, không phải Chromium đã xoá.

Đọc [reference/investigation.md](analyzing-chromium-upgrades/reference/investigation.md)
trước khi ghi quyết định hoặc refresh một review đã có.

## Các artifact và cách đọc chúng

| File | Chứa gì |
|---|---|
| `report.md` | Bản tổng quan cho người đọc. Các bảng trong đó có thể bị cắt bớt |
| `report.json` | Toàn bộ finding. Truy vấn bằng chương trình; không nạp cả file vào context, và không coi một lần tìm chuỗi là đã rà soát xong |
| `report.html` | Bảng đầy đủ, lọc được, mở bằng trình duyệt |
| `review-index.json` | Cấu hình input, finding, các fact không đổi, quan hệ khai báo, và source delta |
| `review.json` | Event, bằng chứng, và quyết định cho từng item đã index |
| `review.md` | Báo cáo render ra từ `review.json` |

`change` của một finding chứa `before`, `after`, `deltas`, `paths`, `locations`
và `signals`. `unconfirmed` nghĩa là bằng chứng vắng mặt không đủ; đọc coverage
và `reasons` trước khi nói một khai báo đã bị xoá.

**Chỉ một trong ba file của `run` lọt được vào context.** Đo trên lần chạy
M148 → M151 với bộ `default` trong repo này; ước lượng token là số ký tự chia 4:

| Artifact | Dung lượng | ≈ token | Đọc thế nào |
|---|---:|---:|---|
| `report.md` | 173 KB | ~44k | đọc trọn, từ trên xuống |
| `report.html` | 1,47 MB | ~384k | mở bằng browser, không đưa vào context |
| `report.json` | 4,52 MB | ~1.185k | chỉ qua chương trình |

Chạy Python trên `report.json` và chỉ in ra câu trả lời:

```python
import json, collections
R = json.load(open("out/M148_to_M151/report.json"))
F = R["findings"]
print(collections.Counter(f["bucket"] for f in F))
print([f["change"]["name"] for f in F
       if "pref_left_scan" in f["change"]["signals"]][:20])
```

`grep` trên file này không dùng được: nó ghi trên một dòng, nên mọi match trả
về nguyên 4,5 MB.

**Thứ tự đọc `report.md`.** Các mục đầu là phần dùng để định hướng:

| Đọc | ≈ token | Cho biết |
|---|---:|---|
| Header, *What kind of change*, *What happened* | 2k | các con số đếm và mọi nhóm signal |
| *Related changes, grouped* | 1k | các cụm ứng viên mà `cluster.py` gom sẵn |
| *What changed on each screen* | 2k | thay đổi theo từng màn hình |
| *Compatibility break*, *Behaviour change* | ~25k | các dòng cần đọc kỹ |

*What Chromium says shipped in this window* nằm giữa đường đọc đó và không
thuộc về nó: đấy là bản tóm tắt milestone của chính Chromium, một nguồn độc
lập. Dùng nó để **kiểm chứng** một thay đổi đã có người hỏi, không dùng để
**phát hiện** thay đổi, và xác minh nó với đúng cặp version đang so.

*How this was produced* là chỗ lấy phần giới hạn cho báo cáo cuối: nó mang con
số coverage của cả hai ref, target set và version chính xác.

## Quy trình phân tích

```
- [ ] 1. Đọc metadata và tổng quan; liệt kê mọi item đã index, ghi một quyết định cho từng cái
- [ ] 2. Tìm các thay đổi có thể liên quan bằng `related`
- [ ] 3. Đọc source before/after và các consumer liên quan; đọc mọi hunk đã đổi
- [ ] 4. Khi nguyên nhân, thứ tự hay ý định chưa rõ thì tra lịch sử
- [ ] 5. Chỉ gom item khi bằng chứng cho thấy chúng là một thay đổi liên quan
- [ ] 6. Sau mỗi đợt, lưu event và câu hỏi còn treo; đối chiếu với quyết định cũ
- [ ] 7. Trước khi giao, kiểm tra phần còn treo rồi chạy `review check` và `review render`
```

1. **Đọc metadata và tổng quan báo cáo.** Liệt kê mọi item đã index theo từng
   trang, gồm cả dòng điểm thấp, finding không mang signal, source delta và
   bản tóm tắt milestone. Ghi một quyết định cho từng item. Chỉ loại một item
   khi nêu được lý do phù hợp với phạm vi user đưa.
2. **Tìm các thay đổi có thể liên quan.** Dùng `related` để xem quan hệ khai
   báo ở cả hai version, kể cả những khai báo không đổi. Một flag, tiền tố,
   màn hình, interface hay CL dùng chung là **lý do để điều tra**, không phải
   bằng chứng rằng các item đó là một event.
3. **Đọc source before/after và các consumer liên quan.** Đọc mọi hunk đã đổi
   của một file, kể cả khi vài hunk đã có finding mô tả. Lần theo các
   identifier mà graph không giải được. Thay đổi không có finding vẫn cần
   phân tích.
4. **Khi nguyên nhân, thứ tự hay ý định chưa rõ**, dùng
   [reference/history.md](analyzing-chromium-upgrades/reference/history.md).
   Nó bao gồm cả cách tra theo finding lẫn cách đọc thẳng lịch sử file khi
   `why.py` không tìm được dòng nào. Bản tóm tắt milestone phải được kiểm
   chứng với đúng cặp version: riêng ngày tháng không chứng minh tính năng đã
   có ở version nào.
5. **Chỉ gom item khi bằng chứng cho thấy chúng là một thay đổi liên quan.**
   Nêu rõ mỗi item đóng góp gì. Tách các thay đổi không liên quan ngay cả khi
   công cụ gom chúng lại. Nói riêng phần quan sát được từ source, phần suy ra
   về ý định, và phần hậu quả phụ thuộc vào sản phẩm cụ thể.
6. **Sau mỗi đợt, lưu event và câu hỏi chưa trả lời.** Đọc lại danh sách event
   đã lưu và đối chiếu bằng chứng mới với quyết định trước. Sửa lại cách gom
   khi bằng chứng cho thấy cần gộp hoặc cần tách.
7. **Trước khi giao**, kiểm tra các item còn `pending`, các câu hỏi
   `unresolved` và các event còn `provisional`. Chạy `review check` và
   `review render`. Còn phần việc đáng kể thì giao báo cáo một phần và liệt kê
   các câu hỏi còn lại.

Quy trình này áp dụng cho cả những identifier chưa từng gặp. Ví dụ trong các
reference và tên signal không phải danh sách tính năng cần đi tìm. Score có thể
ảnh hưởng thứ tự làm việc, nhưng không được quyết định bằng chứng nào được xem
hay event nào tồn tại.

## Truy vấn theo từng phần nhỏ

```bash
python3 -m chromiumdiff review index out/upgrade/review --limit 30
python3 -m chromiumdiff review events out/upgrade/review --limit 30
python3 -m chromiumdiff review inspect out/upgrade/review 'KIND:KEY'
python3 -m chromiumdiff review related out/upgrade/review 'KIND:KEY' --hops 2
python3 -m chromiumdiff review unresolved out/upgrade/review
python3 -m chromiumdiff review source out/upgrade/review path/to/file.cc --side diff --start 1 --end 120
```

Dùng ID và đường dẫn lấy từ index thật. Mọi lệnh truy vấn đều nhận `--cursor`,
`--limit` và `--max-chars`. Giới hạn đó tính bằng ký tự, không phải token của
model. Đọc tiếp các trang cho tới khi `next_cursor` là null.

Với `index`, dùng `--after NEXT_AFTER` nếu quyết định thay đổi giữa các trang:
offset dạng số trên một danh sách `--status pending` đang co lại sẽ nhảy cóc
qua item.

- `inspect` trả về các trường dưới dạng JSON pointer. Chuỗi dài có offset và
  có thể trải nhiều trang.
- `events` trả về danh sách ngắn; `inspect` một event ID để đọc toàn bộ phần
  phân tích đã lưu của nó mà không phải nạp cả review.
- `related` trả về chuỗi tham chiếu có kiểu, không phải kết luận nhân quả. Nó
  không tự mở rộng các tham chiếu mơ hồ hay các CL khớp yếu. Một node có quá
  nhiều liên kết thì truy vấn riêng node đó với `--hops 1`.
- `source` trả về ref chính xác, nguồn gốc source và hash SHA-256. `next_line`
  của nó tách biệt với `next_cursor`: đọc hết các trang của khoảng dòng đang
  hỏi rồi mới sang khoảng tiếp theo. Dùng `--side from` hoặc `--side to` để lấy
  **số dòng của source**; số dòng trong output diff không phải số dòng source.

File thiếu trong cache thì `source --fetch` tải đúng đường dẫn đó ở đúng ref.
Tải thất bại hoặc không tải được thì nêu rõ bằng chứng còn thiếu. **Không thay
thế bằng file của một version khác trong cache.**

Để tìm consumer trong source đã cache, đọc `inputs.source_roots` chính xác từ
index rồi dùng:

```bash
rg -n -F -- 'IDENTIFIER' EXACT_VERSION_ROOT
```

Kết quả tìm kiếm là các vị trí cần xem, không phải bằng chứng code có chạy. Ở
chế độ Git, dùng thủ tục `git grep` theo đúng ref trong `reference/history.md`;
checkout hiện tại có thể đang ở version khác.

## Ghi quyết định vào review

Mỗi item đã index cần một quyết định:

| Trạng thái | Nghĩa |
|---|---|
| `event` | Item thuộc về một event. Event khác vẫn có thể trích nó làm bằng chứng phụ mà không gán nó hai lần |
| `explained` | Đã xem, nhưng không cần một event riêng. Phải nêu lý do và vị trí trong source; nhãn kiểu "cleanup" không phải một lời giải thích |
| `out_of_scope` | Bị loại theo phạm vi user đưa, kèm lý do cụ thể |
| `unresolved` | Còn một câu hỏi cần bằng chứng. Phải nêu bước kiểm tiếp theo |
| `pending` | Chưa có quyết định |

Các trạng thái này theo dõi tiến độ phân tích. Chúng không phải phân loại cho
báo cáo cuối.

Một item `file:` đại diện cho **toàn bộ** bản diff của file đó. Đọc từng hunk,
kể cả hunk không có finding nào mô tả. Ghi lại event nào giải thích hunk nào,
hoặc vì sao một hunk không có hậu quả đáng báo cáo. Một file có thể phục vụ
nhiều event; gán nó cho một event không giải thích các hunk còn lại.

Tạo file JSON quyết định rồi ghi vào review:

```bash
python3 -m chromiumdiff review record out/upgrade/review --file /path/to/decisions.json
python3 -m chromiumdiff review check out/upgrade/review
python3 -m chromiumdiff review render out/upgrade/review
```

Cấu trúc file, các trường bắt buộc của một event, và dạng của một mục bằng
chứng (`item`, `url`, hoặc `source` có kiểm hash) nằm trong
[reference/investigation.md](analyzing-chromium-upgrades/reference/investigation.md).
Những điểm cần nhớ:

- `record` kiểm tra cấu trúc và tham chiếu trước khi ghi. Mọi thành viên của
  một event đều cần một câu giải thích bằng chứng. ID lạ, gán trùng thành viên
  chính, và quyết định trỏ tới event không tồn tại đều bị từ chối. Nó kiểm
  **cấu trúc**, không kiểm kết luận có đúng hay không.
- `confirmed` nghĩa là kết luận được bằng chứng chống đỡ **trong phạm vi đã
  nêu**. `provisional` nghĩa là còn một câu hỏi có thể làm đổi kết luận. Không
  biết trạng thái rollout vẫn có thể là một giới hạn đã nêu của một thay đổi
  `confirmed` ở mức source; nó không cho phép kết luận tính năng đã tới người dùng.
- ID của event mặc định là hash của danh sách item đã sắp xếp, không phụ thuộc
  câu chữ hay score. Sửa một event thì đưa lại `id` của nó. Tách hoặc gộp thì
  đưa `remove_events` cùng các event thay thế trong **một** patch. Item bị gỡ
  khỏi event sẽ quay về `pending` nếu không được gán lại.
- `check` trả mã khác 0 khi còn item `pending`/`unresolved`, còn event
  `provisional`, bản ghi không hợp lệ, hoặc input đã đổi. Mã 0 chỉ nghĩa là
  mọi item đã index đều có quyết định hợp lệ. **Nó không chứng minh phân tích
  đã đầy đủ về mặt ngữ nghĩa và không phải một cổng duyệt release.**

## Refresh sau khi lưu bằng chứng mới

`why.py --save` ghi thêm vào `report.json`, nên phải refresh review trước khi
làm tiếp. Đây là chỗ dễ sai: `review init --refresh` rơi về cache mặc định khi
không truyền `--cache`, và bỏ hẳn `--source-repo` khi không truyền lại. Refresh
kiểu đó sẽ re-index bằng cache khác và mất source scope kiểu Git.

`reference/investigation.md` có sẵn đoạn script đọc cấu hình đã lưu trong
`review-index.json` rồi dựng lại đúng câu lệnh. Dùng nó thay vì tự nhớ tham số.

Đọc phần warning của kết quả refresh:

- Bằng chứng giống hệt thì quyết định cũ được giữ. Riêng thứ hạng hay thứ tự
  input đổi thì không làm mất hiệu lực quyết định.
- Thay đổi chỉ ở phần ngữ cảnh sẽ lưu trữ bản quyết định cũ, đánh dấu các event
  liên quan thành `provisional` và các quyết định không phải event thành
  `unresolved`. Phần không liên quan được giữ; item mới là `pending`. Việc này
  có thể mở lại nhiều event nằm dưới một điều kiện chung; **điều đó không có
  nghĩa các event đó nên gộp làm một.**
- Thay đổi ở source, snapshot hay phạm vi sẽ lưu trữ và reset các quyết định.
  Nếu thay đổi đó ngoài ý muốn, kiểm tra lại cấu hình trước khi phân tích tiếp.
- File tải thêm bằng `review source --fetch` nằm ở cache riêng và **không** mở
  rộng phạm vi quét gốc.

## Diễn giải bằng chứng

Nguyên tắc chung:

- **Flag và API:** so trạng thái Windows được ghi nhận cùng toàn bộ điều kiện
  build và runtime liên quan. Một giá trị mặc định trong source không phải
  rollout đã đo được.
- **Khai báo bị xoá:** xem khai báo thay thế và các consumer trước khi kết luận
  capability đã mất.
- **Signature của API hay IPC:** mới chỉ là một khai báo đã đổi. Xác định
  consumer bị ảnh hưởng và các tổ hợp version trước khi nói build hỏng hay
  runtime hỏng.
- **Pref, switch và param:** tìm bên đọc, bên ghi, migration và override từ bên
  ngoài. Không ghi nhận gate nào không chứng minh code chạy vô điều kiện.
- **Hai version source chỉ xác lập khác biệt ròng giữa chúng.** Mọi khẳng định
  về một lần tách, một lần revert hay một lần merge sau đó đều cần lịch sử tương ứng.

Câu hỏi theo từng loại khai báo:

**Mojo** — `mojo_interface`, `mojo_method`, `mojo_struct`, `mojo_field`, `mojo_enum`

1. Đọc `platform_state.windows`. `not_compiled` thì score đã bằng 0;
   `conditional` là **chưa xác định**, không phải mặc định là của mình.
2. Ai ở đầu bên kia? Cả hai đầu biên dịch từ cùng một cây source, nên đây là
   lỗi build cho code ngoài cây trước khi nó là lỗi lúc chạy. Mục 10 của
   `reference/traps.md` liệt kê các trường hợp nó là lỗi lúc chạy.
3. Với enum, xem `[Extensible]` và `[Default]` trước khi mô tả cách xử lý giá
   trị lạ. Không mặc định rằng mọi peer đều từ chối giá trị không biết.

**Web platform** — `idl_interface`, `idl_member`, `blink_runtime_feature`

1. Một trang web có với tới được không? `web_api_added_live` nghĩa là
   classifier **không tìm thấy** gate đóng nào trong các điều kiện nó xét — nó
   không chứng minh API sẵn dùng ở mọi nơi. `web_api_added_gated` mô tả một hạn
   chế mặc định được ghi nhận — nó không chứng minh mọi ngữ cảnh override hay
   origin trial đều không dùng được.
2. Điều kiện có thể nằm trên **interface** chứ không nằm trên member. Một
   member không mang `[RuntimeEnabled]` riêng không vì thế mà với tới được.
3. `web_api_removed` so với `web_api_removed_gated`: cái sau là khai báo bị xoá
   trong khi gate ghi nhận trước đó đã đóng.

**Flag, pref và switch** — `base_feature`, `feature_param`, `pref`, `switch`, `flag_entry`

1. Trạng thái flag có đổi trên Windows không? Xem `platform_state`.
   `disabled → enabled` hoặc ngược lại là thay đổi hành vi thật.
2. Flag có biến mất không? `flag_retired_on` / `flag_retired_off` chỉ phân loại
   giá trị mặc định **cuối cùng quan sát được**. Chúng không cho biết phần hiện
   thực được giữ lại, bị xoá, hay bị thay thế — phải đọc consumer.
3. Sự biến mất đã được xác nhận chưa? `pref_left_scan` / `switch_left_scan`
   nghĩa là "không có trong những file lần chạy này đọc". Tìm key trong source
   đủ đầy đủ, hoặc chạy lại `wide`, trước khi kết luận theo bất kỳ hướng nào.
4. Với pref biến mất, tìm key đã lưu, chỗ đăng ký, bên đọc, bên ghi và code
   migration. Dữ liệu có thể vẫn nằm trên đĩa dù code mới không đọc key nữa.
   Không suy ra mất dữ liệu hay reset chỉ từ nhãn bucket.

**Trang chrome://** — `webui_route`, `webui_control`, `webui_gate`

1. Lần theo điều kiện của route hoặc control ra tới giá trị mà handler C++ cung
   cấp. Một control hay một trang biến mất thường là đã chuyển ra sau một điều
   kiện khác, và thay đổi mà người dùng thấy đã xảy ra lúc flag đó lật.
2. Cả UI cũ lẫn UI mới có thể cùng tồn tại trong source trong lúc migration mà
   không phải cả hai đều hiển thị. Mục 6 của `reference/traps.md`.
3. `ui_control_relabelled` chỉ nói key của label đổi. Nó không chứng minh chữ
   người dùng nhìn thấy đã đổi — phải đọc string resource thật.

**Thay đổi cần sửa ở ngoài repository.** Nhánh này theo signal chứ không theo
`kind`. Các signal dưới đây đều biên dịch bình thường rồi ngừng có tác dụng
ngoài thực địa, và chỗ phải sửa là Finch config, script khởi chạy hoặc
automation:

`feature_string_renamed`, `switch_renamed`, `param_removed`, `param_rewired`,
`flag_retired_on`, `flag_retired_off`, `killswitch_retired`, `flag_expiring`,
`flag_expiry_moved`

Ba signal flag bị gỡ nằm trong Upstream cleanup, là bucket duy nhất không có
bảng trong `report.md`. Ở M148 → M151 với bộ `default` chúng là 175 dòng, và
phần lớn tên đó không xuất hiện ở đâu trong `report.md`. Truy vấn ra trước khi
viết báo cáo:

```python
RETIRED = {"flag_retired_on", "flag_retired_off", "killswitch_retired"}
[f["change"]["name"] for f in F if set(f["change"]["signals"]) & RETIRED]
```

Không cái nào trong đó tự nó đổi hành vi, nên báo cáo một cái như tính năng bị
mất là sai. Nhưng mỗi cái đều làm một override đặt từ bên ngoài mất tác dụng mà
không có gì báo. Đây là danh sách cần kiểm tra, không phải danh sách đã hỏng.

## Truy nguyên lịch sử

Dùng lịch sử khi khác biệt trong source không giải thích được ý định, sự thay
thế, thứ tự, hoặc một mâu thuẫn. Thủ tục đầy đủ nằm trong
[reference/history.md](analyzing-chromium-upgrades/reference/history.md).
Tóm tắt các đường có thể đi:

| Tình huống | Cách làm |
|---|---|
| Finding có trong `report.json` | `why.py` với UID của finding và đúng `--cache` đã lưu |
| Có repo Git ở máy | `git log`/`git show`/`git grep` theo đúng hai ref, không đổi checkout |
| Không có repo Git | Mở file ở Gitiles theo đúng ref rồi xem history; Gerrit tìm theo đường dẫn hoặc identifier |
| Đã xác định được CL | `cl.py` với số CL và `--cache` |

Ba điểm hay sai:

1. **Một lần tìm không ra kết quả là kết quả của lần tìm đó, không phải kết
   luận về Chromium.** Giới hạn request, lỗi mạng hay danh sách ứng viên không
   đầy đủ đều không chứng minh không có commit liên quan. Ghi lại phần chưa xem
   được. Các trường chẩn đoán nằm ở
   [reference/no-row.md](investigating-chromium-root-causes/reference/no-row.md).
2. **`introduced`, `exact` và `declares` mô tả các kiểu khớp khác nhau trong
   diff của một CL** — phải đọc diff để biết nó có giải thích được chuyển biến
   đang xét hay không. `described` chỉ khớp commit message; `touched` và
   `crowded` là khớp theo file, yếu hơn. Không cái nào tự nó xác lập nhân quả.
3. **Một CL có thể chứa nhiều sửa đổi không liên quan, và một sự việc có thể
   trải nhiều CL.** Cùng một bug hay cùng một tiêu đề không đủ để gộp hai sự
   việc làm một.

Issue bị hạn chế truy cập là chuyện bình thường: nhiều issue nằm trong các
component security, abuse hoặc nội bộ và trả về HTTP 403. Ghi đó là bằng chứng
còn thiếu; các CL vẫn công khai và đọc được.

**Với người đọc là người thật**, `python3 -m chromiumdiff serve out/upgrade`
mở giao diện tra cứu ở `http://127.0.0.1:8787/`, bấm vào một dòng thì nó tra CL
của dòng đó. `--click-budget N` giới hạn số diff đọc mỗi lần bấm (mặc định
600), `--no-save` thì không ghi ngược vào `report.json`. Mở thẳng file
`report.html` thì phần tra cứu không chạy, vì trang trên `file://` không được
phép gọi `chromium-review.googlesource.com`; đó là giới hạn của trình duyệt,
không phải lỗi.

Kết quả tra cứu được ghi vào `report.json` nhưng chỉ vào tới `report.md` và
`report.html` sau khi render lại:

```bash
python3 -m chromiumdiff report out/upgrade/report.json --format both --out out/upgrade/report
```

## Viết báo cáo cuối

Mỗi event là một mục được đánh số, đặt tiêu đề theo **thay đổi**, không đặt
theo bucket, score hay riêng một identifier.

Mỗi mục phải có:

- **before / after** — trạng thái quan sát được ở version cũ và version mới
- **lý do gom** — vì sao các item này thuộc về một thay đổi
- **consumer bị ảnh hưởng**
- **điều kiện** — build, runtime và triển khai
- **bằng chứng** — finding, đường dẫn source kèm số dòng, CL
- **việc cần làm** — kiểm tra hay cập nhật cụ thể, kèm vị trí consumer
- **phần chưa chắc** — câu hỏi vẫn còn cần bằng chứng

Viết câu trực tiếp và định nghĩa các thuật ngữ kỹ thuật lạ. Viết bằng ngôn ngữ
của user; giữ nguyên identifier trong source và tên lệnh.

Nêu version chính xác, platform và phạm vi. Tách phần được source xác lập ra
khỏi phần hậu quả phụ thuộc vào build hoặc cấu hình của user. Báo cáo dài thì
kèm một bản tóm tắt ngắn và link tới review đầy đủ.

Hai ví dụ **sai**:

- *"`LocalNetworkAccessChecksSplitPermissions` đã bị xoá ở M151."* — một mảnh
  của một thay đổi lớn hơn, và đọc lên thành mất tính năng.
- *"12 thay đổi ở chrome:// pages, 3 cái Compatibility break."* — một con số
  đếm không phải một chuyện đã xảy ra.

**Dừng ở chỗ bằng chứng cho phép.** Viết cái gì đã đổi và phải kiểm gì; đừng
viết rằng cái đó là bug. Công cụ chỉ có hai version Chromium và không biết sản
phẩm này đang patch hay ship cái gì.

## Tài liệu tham chiếu

Đường dẫn dưới đây tính từ thư mục của skill, tức
`skills/analyzing-chromium-upgrades/`.

- **`reference/investigation.md`** — cách đọc cấu hình đã lưu trong
  `review-index.json`, cách ghi quyết định, cấu trúc file record, và thủ tục
  refresh giữ nguyên cache cùng repo Git.
- **`reference/history.md`** — cách tìm commit và giải thích lịch sử: đường
  `why.py` khi có finding, và đường đọc thẳng `git log`/Gitiles khi không có.
- **`reference/signals.md`** — mỗi signal ghi nhận thay đổi gì, và cần thêm
  bằng chứng gì trước khi kết luận từ nó.
- **`reference/traps.md`** — mười ba giới hạn của kết luận rút từ source: vắng
  mặt, điều kiện platform, tính sẵn dùng của API, và tương thích.
- **`reference/settings-screen.md`** — vị trí source của WebUI, cách lần theo
  điều kiện hiển thị, và cách chọn phạm vi cho một event về UI.
- **`skills/investigating-chromium-root-causes/reference/no-row.md`** — các
  trường chẩn đoán khi một lần tra cứu không trả về kết quả.

## Những gì công cụ không nhìn thấy

Nêu những điều này trong mọi báo cáo. Việc mọi item đã index đều có quyết định
không chứng minh đã phát hiện hết mọi thay đổi đáng kể.

- **Thay đổi chỉ nằm trong phần hiện thực.** Công cụ đọc khai báo. Hành vi đổi
  bên trong thân một hàm thì nó không tạo ra finding nào.
- **Các loại khai báo mà parser không biến thành fact**, ngay trong những file
  nó đọc đầy đủ. Coverage theo file và coverage theo ngữ pháp là hai chuyện.
- **Bất cứ thứ gì ngoài repository** — Finch config, script khởi chạy, test
  automation, enterprise policy, metadata trên store.
- **Bản vá của chính sản phẩm.** Công cụ so Chromium với Chromium. Tìm
  identifier trong cây source của mình mới trả lời được câu "cái này có ảnh
  hưởng tới mình không".
- **IDL của Chrome Extensions và MIDL.** Chỉ `.idl` của riêng Blink được đọc.
- **Hành vi của trang và giao diện đã render.** Chỉ phần khai báo của một
  screen WebUI được đọc, không phải toàn bộ TypeScript, và không có ảnh chụp
  màn hình.

Dùng khai báo để **phát hiện**, đọc source có chủ đích để **giải thích**, ảnh
chụp màn hình chỉ để **xác nhận** một danh sách ngắn.
