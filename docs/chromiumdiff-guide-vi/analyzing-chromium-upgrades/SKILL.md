---
name: analyzing-chromium-upgrades
description: Compares two Chromium versions with the chromiumdiff scripts and explains what changed, what it affects and what to verify or update, scoped to the product areas the user names. Use when analyzing a Chromium upgrade or version bump, interpreting a chromiumdiff report.json or review directory, or reviewing one area such as Settings, WebUI, Mojo or feature flags across two milestones. Use investigating-chromium-root-causes instead to trace one identifier or one reported symptom back to its cause.
---

# Phân tích một đợt nâng version Chromium

Script trích xuất các khai báo rồi so sánh chúng. Agent là bên xác định những
khác biệt đó có nghĩa gì, ảnh hưởng tới đâu, và user phải kiểm hay sửa gì.
Bucket, score, signal và cluster chỉ dùng để xếp thứ tự công việc, không bao
giờ là kết luận.

## Luồng công việc

Chép checklist này vào câu trả lời của bạn, xong bước nào thì tick dòng đó:

```
Chromium upgrade review:
- [ ] 1 Xác nhận phạm vi -- đọc reference/scoping.md trước
- [ ] 2 Tạo hoặc mở lần so sánh
- [ ] 3 Kiểm kê toàn bộ index
- [ ] 4 Lấy bằng chứng cho phạm vi -- đọc reference/focus.md trước
- [ ] 5 Đọc bằng chứng -- đọc reference/traps.md trước
- [ ] 6 Gom thành event và ghi quyết định -- đọc reference/investigation.md trước
- [ ] 7 Lặp 4 tới 6 cho tới khi phạm vi được kế toán xong
- [ ] 8 Render và giao kết quả
```

Mỗi bước kết thúc bằng một **Checkpoint**: một điều kiện, kèm việc phải làm
khi nó chưa đạt. Không bắt đầu một bước khi checkpoint của bước trước chưa
đạt, và không tick một dòng mà bạn chưa kiểm checkpoint của nó.

Đọc trọn vẹn reference được nêu trước bước của nó; reference đã đọc trong lần
chạy này thì không cần nạp lại. Ba reference nữa được đọc bên trong bước 5 khi
gặp chủ đề của chúng: [signals.md](reference/signals.md) cho nhãn của bộ phân
loại, [settings-screen.md](reference/settings-screen.md) cho route, control và
điều kiện hiển thị của WebUI, và [history.md](reference/history.md) cho CL,
bug và mọi khẳng định về nguyên nhân, ý định, split, revert hay merge.

`MUST` đánh dấu một hành động bắt buộc. Chạy mọi lệnh từ thư mục gốc của
project; `python3 -m chromiumdiff` hỏng ở chỗ khác. Đọc file này, chép một
lệnh ví dụ, hay chỉ đọc `report.md` đều không qua được checkpoint nào.

## Từ vựng

- **Fact**: một khai báo trích từ một version; nó có thể không đổi.
  `--fact-kind` lọc theo loại của nó.
- **Finding**: một khác biệt giữa các fact đã trích, định danh bằng `kind:key`.
- **Source delta**: một khác biệt trong nội dung file, gồm cả code không parser
  nào hiểu. **Hunk** là một đoạn của diff một file.
- **Event**: một thay đổi có liên quan được giải thích trong báo cáo cuối, phủ
  một hoặc nhiều finding, file và commit.
- **Consumer**: code hoặc hệ thống bên ngoài gọi một API, đọc một giá trị,
  hiện thực một interface, hoặc phụ thuộc theo cách khác vào hành vi đã đổi.
- **Gate**: điều kiện quyết định code hay API có sẵn dùng hay không.
  **Rollout** là mức sẵn dùng thực tế trong sản phẩm đã phát hành, có thể khác
  với giá trị mặc định khai báo trong source.
- **Scope**: các khu vực và quyết định user xác nhận ở bước 1.
  **Acquisition** là chuyện khác: script tải và parse bao nhiêu phần Chromium,
  đặt bằng `--target-set` và `--partition` ở bước 2.

## Bước 1 — Xác nhận phạm vi

MUST xác lập phạm vi trước khi chạy so sánh hay phân tích finding. Hỏi khu vực
nào quan trọng và báo cáo cần phục vụ quyết định nào:

> Tôi nên review khu vực nào: Settings, History, Bookmarks, Extensions,
> Downloads, khu vực khác bạn nêu tên, hay so sánh diện rộng? Điều gì quan
> trọng nhất: thay đổi người dùng sẽ thấy, năng lực mới, hay thay đổi mà sản
> phẩm của bạn phải thích ứng? Bạn có thể chọn nhiều và mô tả ưu tiên riêng.

Chuyển câu hỏi sang ngôn ngữ của user, và hỏi luôn version còn thiếu trong
cùng lượt. Các khu vực trên là ví dụ, không phải danh sách để đi tìm. Chỉ nêu
loại khai báo như một lựa chọn tinh chỉnh; đừng bắt user phân loại code.

MUST chờ khi chưa có câu trả lời. Không tự chọn khu vực, không lấy N dòng đầu
và không làm lần lượt theo score để thay thế. Nếu user đã nêu rõ phạm vi và ưu
tiên thì dùng luôn, không hỏi lại; khi làm tiếp, giữ nguyên phạm vi đã ghi trừ
khi user đổi.

So sánh diện rộng là một câu trả lời hợp lệ, phủ năng lực mới, thay đổi hành
vi, thay đổi API, migration và việc đã lên lịch, không chỉ vấn đề tương thích.

[reference/scoping.md](reference/scoping.md) liệt kê các trường cần ghi vào
`review/request.md` và cách chọn acquisition mà không bỏ rơi những phụ thuộc
mà khu vực đã chọn cần tới.

**Checkpoint 1.** `review/request.md` tồn tại và trả lời đủ mọi trường
scoping.md liệt kê. Phạm vi phỏng đoán thì không đạt, phạm vi do bạn tự chọn
cũng không: dừng lại và hỏi.

## Bước 2 — Tạo hoặc mở lần so sánh

Thư viện chuẩn Python 3.9+ là đủ; không cài gì thêm. Script so sánh theo điều
kiện Windows và không có tuỳ chọn platform. Ghi lại đúng `from_ref` và `to_ref`
mà report trả về, vì số milestone trần có thể phân giải khác ở lần chạy sau.

Với một lần so sánh mới:

```bash
cache_dir=.chromiumdiff-cache
python3 -m chromiumdiff check
python3 -m chromiumdiff run FROM TO --cache "$cache_dir" --out out/upgrade
python3 -m chromiumdiff review init out/upgrade --directory out/upgrade/review --cache "$cache_dir"
```

Thay FROM/TO và các đường dẫn bằng lần so sánh được yêu cầu. Một lần chạy đọc
mọi file mà target của nó phủ, khoảng 315 MB mỗi version, và vẫn không phủ hết
code lẫn cú pháp của Chromium. Thêm `--target-set smoke` để đọc ba file và kiểm
xem công cụ có chạy được không; nó đọc quá ít để so sánh hai version.
`--partition` thu hẹp phần được tải về các đường dẫn được hỗ trợ, và chỉ dùng
sau khi user chấp nhận đầu vào hẹp hơn đó.

Với report đã có nhưng chưa có review, chạy `review init` với đúng cache của
report đó. Với review đã có, sang bước 3; chỉ init lại nếu đầu vào của nó đã
đổi, và đọc [reference/investigation.md](reference/investigation.md) trước, vì
một lần refresh phải mang theo cache và nguồn Git đã lưu.

Thêm `--source-repo /path/to/chromium/src` vào `review init` sẽ lấy được mọi
đường dẫn thay đổi tại hai ref từ một repo Git Chromium cục bộ, đọc object Git
mà không đụng tới checkout. Không có nó, so sánh source chỉ phủ các file trong
cache, và một file thiếu trong cache nghĩa là chưa biết nội dung, không phải
Chromium đã xoá.

Lần chạy ghi ra:

- `report.md`, bản tổng quan mà các bảng hiển thị có thể chưa đủ.
- `report.json`, toàn bộ finding. Hãy truy vấn nó; đừng nạp cả file, và đừng
  coi một lần tìm chuỗi trên nó là đã review.
- `review-index.json`, cấu hình đầu vào, các finding, các fact không đổi, quan
  hệ khai báo và source delta.
- `review.json`, các event, bằng chứng và quyết định cho mọi item đã index.
  `review.md` được render từ nó ở bước 8.

**Checkpoint 2.** `review init` thoát mã 0 và thư mục review có
`review-index.json` cùng `review.json`. Nếu hỏng thì sửa đầu vào rồi chạy lại;
phân tích riêng `report.md` không qua được checkpoint này.

## Bước 3 — Kiểm kê toàn bộ index

```bash
python3 -m chromiumdiff review check out/upgrade/review
python3 -m chromiumdiff review overview out/upgrade/review
python3 -m chromiumdiff review overview out/upgrade/review --group-by path --path-depth 3
```

`check` thoát mã 1 khi còn việc, ở đây là đúng như vậy; hãy đọc JSON của nó.
`overview` gộp index đã lưu ngay trong tiến trình script và chỉ xuất ra con số,
không bao giờ xuất dòng dữ liệu hay nội dung diff, nên hãy chọn truy vấn cho
phạm vi từ các con số đó thay vì kéo dòng thô vào context.

Bản kiểm kê gồm cả score thấp, finding không signal, source delta và milestone
summary. Một lần loại trừ cần lý do gắn với phạm vi, không phải vì trượt một
từ khoá hay một đường dẫn. scoping.md nêu các bộ lọc `--path-prefix`,
`--item-kind`, `--fact-kind` và từng cái **không** chọn những gì.

**Checkpoint 3.** JSON của `check` và `overview` đã được đọc, đã biết
`index_total`, và các truy vấn cho phạm vi lấy ra từ những con số đó. Chọn
truy vấn từ bảng trong `report.md` thì không đạt.

## Bước 4 — Lấy bằng chứng cho phạm vi

MUST làm theo [reference/focus.md](reference/focus.md) trước khi coi một bộ
lọc đường dẫn là toàn bộ tập bằng chứng. Lọc theo đường dẫn bỏ sót các phụ
thuộc khai báo ở nơi khác, gồm cả interface Mojo mà những file consumer không
đổi vẫn gọi.

```bash
python3 -m chromiumdiff review focus out/upgrade/review \
  --path-prefix PREFIX --output out/upgrade/review/area-focus.json
python3 -m chromiumdiff review focus-read out/upgrade/review --file out/upgrade/review/area-focus.json
```

Lấy PREFIX từ kết quả bước 3. focus.md nêu các tuỳ chọn còn lại, các phần của
gói bằng chứng và cách đọc hết từng phần.

Dùng thêm `review related` để đọc quan hệ khai báo ở cả hai version, kể cả
những khai báo không đổi. Cùng một flag, prefix, màn hình, interface hay CL là
lý do để điều tra, không phải bằng chứng của một event. Gói này là bằng chứng
truy vấn: đọc nó không đánh dấu gì là đã review và không loại trừ gì.

**Checkpoint 4.** Gói bằng chứng tồn tại và mọi phần bạn chọn đã đọc tiếp cho
tới khi `next_cursor` trả về null, kể cả `unresolved`. Một phần dừng giữa
chừng là bằng chứng chưa đọc.

## Bước 5 — Đọc bằng chứng

Đọc [reference/traps.md](reference/traps.md) trước khi rút ra bất kỳ kết luận
nào từ source, từ mức sẵn dùng hay từ sự vắng mặt.

Đọc source trước/sau và các consumer liên quan. Xem mọi hunk thay đổi của một
file nằm trong phạm vi, kể cả khi hunk đó đã có finding. Với file phụ thuộc
dùng chung nằm ngoài phạm vi, lần theo các khai báo được tham chiếu và các hunk
liên quan như focus.md mô tả, và đừng đánh dấu cả file đã review khi còn hunk
chưa đọc. Lần theo các identifier mà graph không phân giải được. Một thay đổi
không có finding vẫn cần phân tích.

Trường `change` của một finding chứa `before`, `after`, `deltas`, `paths`,
`locations` và `signals`. `unconfirmed` nghĩa là bằng chứng cho sự vắng mặt
chưa đủ: đọc phần coverage và các lý do trước khi nói một khai báo đã bị gỡ.

Từng loại bằng chứng chứng minh được gì và không chứng minh được gì:

- Flag và API: đối chiếu trạng thái Windows đã ghi nhận cùng mọi điều kiện
  build và runtime liên quan. Mặc định trong source không phải rollout đo được.
- Khai báo bị gỡ: xem khai báo thay thế và các consumer trước khi kết luận
  năng lực đó đã mất.
- Chữ ký API hoặc IPC: một khai báo đã đổi. Xác định consumer bị ảnh hưởng và
  các tổ hợp version trước khi nói build hay runtime sẽ hỏng.
- Pref, switch và parameter: tìm nơi đọc, nơi ghi, migration và các override
  bên ngoài. Không thấy gate nào không chứng minh là dùng vô điều kiện.
- Hai version source chỉ xác lập khác biệt ròng giữa chúng. Split, revert hay
  merge về sau là khẳng định về lịch sử và cần lịch sử.

Đọc [signals.md](reference/signals.md) trước khi diễn giải nhãn của bộ phân
loại, [settings-screen.md](reference/settings-screen.md) khi lần theo route,
control và điều kiện hiển thị của WebUI, và [history.md](reference/history.md)
khi nguyên nhân, trình tự hay ý định chưa rõ. history.md phủ cả cách tra theo
finding lẫn cách tra lịch sử file trực tiếp khi `why.py` không tìm ra dòng nào.
Đối chiếu milestone summary với đúng lần so sánh; ngày tháng của nó không xác
lập mức sẵn dùng ở version nào cả.

Cơ chế truy vấn cho `index`, `inspect`, `related` và `source` nằm ở cuối file
này.

**Checkpoint 5.** Mọi ứng viên trong đợt đều đã đọc source trước/sau và đã xác
định điều kiện của nó, và mọi item thiếu bằng chứng đều mang một bước kiểm tra
tiếp theo có tên cụ thể. Một preview có `truncated` không phải bằng chứng đã
đọc: mở đầy đủ bằng `review inspect` trước.

## Bước 6 — Gom thành event và ghi quyết định

Đọc [reference/investigation.md](reference/investigation.md) trước, để biết
định dạng quyết định, các trạng thái disposition và quy trình xử lý item
pending.

Chỉ gom các item khi bằng chứng của chúng ủng hộ một thay đổi liên quan, và
nói rõ từng item đóng góp gì. Tách các thay đổi không liên quan kể cả khi công
cụ gom chúng lại. Giữ quan sát từ source, ý định suy ra và hệ quả riêng của
sản phẩm thành những phát biểu tách bạch.

```bash
python3 -m chromiumdiff review record out/upgrade/review --file /path/to/decisions.json
python3 -m chromiumdiff review check out/upgrade/review
```

Lưu event và các câu hỏi chưa trả lời trong từng đợt. Đọc danh sách event đã
lưu và đối chiếu bằng chứng mới với quyết định trước, sửa lại một nhóm khi bằng
chứng nói nó nên được gộp hoặc tách. Ranh giới của đợt làm việc không được trở
thành ranh giới của event.

**Checkpoint 6.** `review record` đã nhận đợt đó, và lần `review check` chạy
sau nó cho thấy số pending giảm đúng bằng số item đã quyết. Nếu không giảm thì
đọc kết quả của record; đi ghi một mẫu khác thay vào đó không qua được
checkpoint này.

## Bước 7 — Lặp 4 tới 6 cho tới khi phạm vi được kế toán xong

```bash
python3 -m chromiumdiff review index out/upgrade/review --status pending --limit 30
```

Giữ nguyên bộ lọc đường dẫn và loại của phạm vi khi tiếp tục truy vấn đó, và
xem source hỗ trợ cùng các phụ thuộc nằm ngoài bộ lọc một cách riêng biệt.
investigation.md nêu các quy tắc con trỏ giúp một danh sách pending đang co lại
không nhảy cóc mất item.

Phạm vi đã xác nhận là ranh giới duy nhất kết thúc công việc trước khi kế toán
hết index. Những dòng trông thú vị, một ngưỡng score và một số trang đều không
phải ranh giới. Một đợt nhỏ giới hạn lượng thông tin có mặt trong context tại
một thời điểm, không giới hạn phần phạm vi cần review: đừng dừng sau trang đầu
và đừng đặt trước số event cần tìm. Áp dụng đúng quy trình này cho cả những
identifier không quen, vì các ví dụ trong reference và tên signal không phải
danh sách tính năng cần đi tìm.

Một truy vấn có lọc mà rỗng không có nghĩa là hết việc. `review unresolved`
liệt kê các tham chiếu khai báo chưa phân giải, đó không phải quyết định còn
dở; dùng `index --status unresolved` cho loại đó. Xem lại các event
provisional, và kiểm lại item pending sau khi sửa event hoặc sau refresh, vì
cả hai đều có thể đưa item về lại pending.

**Checkpoint 7.** `index --status pending` kèm bộ lọc của phạm vi không trả về
dòng nào, các event provisional đã được xem lại, và `review check` đã được đọc
để lấy con số toàn index. Chỉ một truy vấn có lọc rỗng thì không đạt: có thể
bộ lọc sai chứ không phải công việc đã xong.

## Bước 8 — Render và giao kết quả

```bash
python3 -m chromiumdiff review render out/upgrade/review
```

Thêm `--require-complete` khi đã review toàn bộ index; nó thoát mã 1 và không
ghi `review.md` khi còn item hay event chưa xong. Một review theo phạm vi hẹp
không bao giờ tới trạng thái đó, vì các item ngoài phạm vi vẫn ở pending, nên
render không kèm tuỳ chọn này và giữ nguyên trạng thái PARTIAL. `render` ghi đè
`review.md`, nên phạm vi đã xác nhận phải nằm trong bản tóm tắt giao đi, lấy từ
`review/request.md`, kèm các con số chưa đụng tới. Nếu giới hạn tài nguyên hoặc
bằng chứng thiếu làm dừng việc sớm hơn, nói rõ là cái nào trong hai và đưa các
con số cùng các bước kiểm tiếp theo. Không xoá một lần check thất bại bằng cách
đổi các item chưa xem thành `explained` hay `out_of_scope`.

Viết mỗi event một mục có số thứ tự, tiêu đề nói về thay đổi chứ không phải
bucket, score hay identifier. Nêu trước và sau, lý do gom nhóm, consumer bị ảnh
hưởng, điều kiện, bằng chứng, hành động và phần chưa chắc. Viết bằng ngôn ngữ
của user và giữ nguyên chính xác identifier trong source cùng tên lệnh.

Ghi đúng version, platform và phạm vi đã xác nhận, và tách phần source xác lập
được ra khỏi phần phụ thuộc vào build hay cấu hình của user. Báo cáo dài thì
kèm một bản tóm tắt ngắn và link tới bản đầy đủ, bản đầy đủ giữ mọi event có
bằng chứng. Báo `check.total`, số quyết định theo trạng thái, `by_kind` và số
event provisional; số finding và số file chồng lấn nhau và không phải số event.

Kế toán đủ mọi item đã index không chứng minh đã tìm ra mọi thay đổi có ý
nghĩa: source trong cache có thể chưa đủ và parser chỉ phủ một phần cú pháp.
Cấu hình bên ngoài, patch riêng của sản phẩm và UI đã render cần bằng chứng
riêng. `review check` không phải phê duyệt phát hành.

**Checkpoint 8.** `review render` đã ghi `review.md`, và bản tóm tắt giao đi có
nêu phạm vi đã xác nhận, các con số và các giới hạn. Một bản tóm tắt chỉ nêu
event mà thiếu những thứ đó thì không đạt.

## Cơ chế truy vấn

```bash
python3 -m chromiumdiff review index out/upgrade/review --status pending --limit 30
python3 -m chromiumdiff review events out/upgrade/review --limit 30
python3 -m chromiumdiff review inspect out/upgrade/review 'KIND:KEY'
python3 -m chromiumdiff review related out/upgrade/review 'KIND:KEY' --hops 2
python3 -m chromiumdiff review unresolved out/upgrade/review
python3 -m chromiumdiff review source out/upgrade/review path/to/file.cc --side diff --start 1 --end 120
```

Dùng ID và đường dẫn lấy từ index thật. Mọi truy vấn nhận `--cursor`,
`--limit` và `--max-chars`, và giới hạn đó đếm ký tự chứ không đếm token. Đọc
hết các trang cho tới khi `next_cursor` là null. Với `index`, dùng
`--after NEXT_AFTER` khi quyết định thay đổi giữa các trang, vì offset dạng số
trên một danh sách `--status pending` đang co lại sẽ nhảy cóc mất item; cách
quyết hết đợt vừa trả về rồi lặp lại truy vấn từ cursor 0 cũng được.

`inspect` trả các trường theo đường dẫn JSON-pointer, và chuỗi dài có offset,
có thể trải qua nhiều trang. `events` trả một danh sách ngắn; inspect một
event ID để đọc toàn bộ phân tích đã lưu của nó mà không phải nạp cả review.

`related` trả các chuỗi tham chiếu có kiểu, không phải kết luận nhân quả, và
tự nó không mở rộng tham chiếu mơ hồ hay CL khớp yếu. Với một node quá nhiều
liên kết, truy vấn node đó bằng `--hops 1` rồi đọc từng trang.

`source` trả đúng ref, nguồn gốc và hash SHA-256. `next_line` của nó tách biệt
với `next_cursor`: đọc hết các trang của một khoảng dòng rồi mới sang khoảng
tiếp theo. Dùng `--side from` hoặc `--side to` để lấy số dòng của source, vì số
dòng trong diff không phải số dòng trong source. Với file thiếu,
`source --fetch` lấy đường dẫn đó tại đúng ref; nếu hỏng thì báo là thiếu bằng
chứng chứ đừng thay bằng file của version khác.

Một lần tìm theo từ khoá MUST NOT được coi là bằng chứng về hành vi hay về độ
phủ. Để tìm consumer trong source đã cache, đọc đúng `inputs.source_roots` từ
index, rồi:

```bash
rg -n -F -- 'IDENTIFIER' EXACT_VERSION_ROOT
```

Kết quả tìm kiếm là các vị trí cần xem, không phải bằng chứng code có chạy.
Ở chế độ Git, dùng quy trình `git grep` theo đúng ref trong
`reference/history.md`, vì checkout đang làm việc có thể khác.
