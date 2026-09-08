---
name: analyzing-chromium-upgrades
description: Hỏi khu vực Chromium nào và quyết định nào là quan trọng, rồi so sánh hai version bằng script chromiumdiff, các reference bắt buộc và bằng chứng đúng version. Dùng khi phân tích một đợt nâng version Chromium và khi diễn giải báo cáo, kèm tác động, việc cần làm và giới hạn coverage nêu rõ.
---

# Phân tích một đợt nâng version Chromium

Giải thích cái gì đã đổi giữa hai version Chromium, các thay đổi liên quan với
nhau ra sao, và user cần kiểm tra hay cập nhật cái gì. Script trích xuất khai
báo rồi so sánh chúng. Agent xác định các khác biệt đó có nghĩa gì. Không dùng
bucket, score, signal hay cluster làm kết luận cuối cùng.

## Bước bắt buộc trước khi phân tích

`MUST` đánh dấu một bước bắt buộc, không phải gợi ý. Các yêu cầu này áp dụng
cho việc phân tích nâng version, không áp dụng cho việc chỉ giải thích một
câu lệnh làm gì.

1. **MUST xác định phạm vi của user trước khi chạy so sánh hoặc phân tích
   finding.** Hỏi khu vực nào là quan trọng và báo cáo cần hỗ trợ quyết định
   gì. Đề xuất Settings, History, Bookmarks, Extensions, Downloads, một khu
   vực khác do user tự nêu, hoặc một lần review rộng. Được chọn nhiều khu vực;
   đây không phải danh sách khám phá cố định. Chỉ đề xuất các kind khai báo kỹ
   thuật như một lựa chọn tinh chỉnh thêm. Không bắt user phải biết thuật ngữ
   của parser.
2. **MUST chờ user trả lời khi còn thiếu.** Không tự chọn `wide`, tất cả khu
   vực, một mẫu top-N hay các score cao nhất. Nếu user đã cung cấp phạm vi và
   ưu tiên rõ ràng, dùng chính các câu trả lời đó, không hỏi lại. Khi tiếp tục
   một review cũ, giữ phạm vi đã ghi trừ khi user thay đổi nó.
3. **MUST đọc các reference bắt buộc dưới đây trước phần việc tương ứng.** Đọc
   trọn vẹn từng reference đã chọn, không chỉ đọc heading hay các đoạn khớp
   khi tìm kiếm. Một reference đã đọc trong lần chạy này thì không cần nạp lại.
4. **MUST chạy các script được ghi trong tài liệu và đọc kết quả thực tế của
   chúng.** Đọc SKILL.md, chép lệnh ví dụ, hay chỉ đọc `report.md` đều không
   hoàn thành một lần phân tích. Nếu một script hay reference bắt buộc không
   dùng được, nêu rõ chỗ bị chặn và không tuyên bố phần việc phụ thuộc vào nó
   đã xong.

Một câu hỏi mở đầu ngắn, chuyển sang ngôn ngữ của user:

> Bạn muốn tôi review khu vực nào: Settings, History, Bookmarks, Extensions,
> Downloads, khu vực khác bạn tự nêu, hay một lần so sánh rộng? Điều gì quan
> trọng nhất: thay đổi user sẽ thấy, capability mới, hay thay đổi mà sản phẩm
> của bạn phải thích ứng theo? Bạn có thể chọn nhiều mục và mô tả ưu tiên
> riêng của mình.

Hỏi luôn các version còn thiếu trong cùng lượt trao đổi đó. Xem
[reference/scoping.md](reference/scoping.md) để biết cách ghi lại câu trả lời,
chọn phạm vi thu thập và truy vấn có giới hạn mà không bỏ sót phụ thuộc.

| Trước phần việc này | Reference MUST đọc |
|---|---|
| Chọn phạm vi thu thập/truy vấn hoặc bắt đầu phân tích chi tiết | [scoping.md](reference/scoping.md) |
| Dựng hoặc đọc bằng chứng cho một khu vực sản phẩm đã chọn | [focus.md](reference/focus.md) |
| Bắt đầu hoặc tiếp tục một review, lưu quyết định hoặc refresh input | [investigation.md](reference/investigation.md) |
| Kết luận từ source, từ tính khả dụng hoặc từ sự vắng mặt | [traps.md](reference/traps.md) |
| Diễn giải signal, bucket hay score của bộ phân loại | [signals.md](reference/signals.md) |
| Phân tích control, route, pref hay điều kiện hiển thị WebUI | [settings-screen.md](reference/settings-screen.md) |
| Tra CL/bug hoặc khẳng định nguyên nhân, ý định, tách, revert hay merge | [history.md](reference/history.md) |

Các script MUST được dùng ở những giai đoạn sau:

- So sánh mới: `check`, `run`, rồi `review init` với các input đã chọn.
- Đã có báo cáo: chỉ chạy `review init` nếu chưa có review; không tạo lại một
  báo cáo không đổi. Sau đó chạy `review check` và `review overview`.
- Phân tích bằng chứng: dùng `review index`, `inspect`, `related` và `source`
  khi cần, để xem finding và source đúng version. Một lần tìm theo từ khoá
  MUST NOT được coi là bằng chứng về hành vi hay về coverage đầy đủ.
- Lưu và giao kết quả: `review record`, `review check`, rồi `review render
  --require-complete` khi phần kế toán đã xong. Một báo cáo còn dở MUST giữ
  nguyên trạng thái và các con số chưa hoàn tất của nó. Không vượt qua một lần
  `check` thất bại bằng cách đổi các item chưa giải thích thành `explained`
  hay `out_of_scope`.

Dùng các thuật ngữ này một cách nhất quán:

- **Fact**: một khai báo được trích ra từ một version; nó có thể không đổi.
- **Finding**: một khác biệt giữa các fact đã trích, định danh bằng `kind:key`.
- **Source delta**: một khác biệt về nội dung file, bao gồm cả code mà parser
  không hiểu. Một **hunk** là một đoạn trong bản diff của file.
- **Event**: một thay đổi có liên quan được giải thích trong báo cáo cuối. Nó
  có thể gồm nhiều finding, file và commit, hoặc chỉ một finding.
- **Consumer**: code hoặc hệ thống bên ngoài gọi một API, đọc một giá trị,
  hiện thực một interface, hoặc phụ thuộc theo cách khác vào hành vi đã đổi.
- **Gate**: một điều kiện quyết định code hay API có khả dụng hay không.
  **Rollout** nghĩa là tính khả dụng thực tế trong một sản phẩm đã triển khai,
  có thể khác với giá trị mặc định khai báo trong source.

## Bắt đầu hoặc tiếp tục một lần so sánh

Dùng phạm vi và version đã được xác nhận. Một câu hỏi phạm vi chưa được trả
lời không phải là sự cho phép bắt đầu. Một lần review rộng bao gồm capability
mới, thay đổi hành vi, thay đổi API, migration và việc đã lên lịch; không thu
hẹp nó về riêng các vấn đề tương thích. Giữ câu trả lời của user trong
`review/request.md` như mô tả ở `reference/scoping.md`.

Chạy lệnh từ thư mục gốc của project. Thư viện chuẩn Python 3.9+ là đủ. Script
so sánh theo điều kiện Windows; không có tuỳ chọn CLI cho platform. Ghi lại
đúng `from_ref` và `to_ref` mà báo cáo trả về. Số milestone trần có thể phân
giải khác đi ở những lần chạy sau.

Với một lần so sánh mới sau khi đã xác nhận phạm vi (ví dụ dùng thu thập rộng):

```bash
cache_dir=.chromiumdiff-cache
python3 -m chromiumdiff check
python3 -m chromiumdiff run FROM TO --target-set wide --cache "$cache_dir" --out out/upgrade
python3 -m chromiumdiff review init out/upgrade --directory out/upgrade/review --cache "$cache_dir"
```

Thay FROM/TO và các đường dẫn đầu ra bằng lần so sánh được yêu cầu. `wide`
quét nhiều file được hỗ trợ hơn `default`; nó không phủ hết mọi code hay cú
pháp của Chromium. `minimal` dành cho các lần kiểm tra cơ bản. `--partition`
thu hẹp phạm vi.

Với một báo cáo đã có mà chưa có review, chạy `review init` với đúng cache của
nó. Với một review đã có, tiếp tục bằng `index`, `events` và `check`; không
khởi tạo lại trừ khi input của nó đã đổi.

Một repository Git Chromium ở máy có thể cung cấp danh sách mọi đường dẫn đã
đổi giữa hai ref: thêm `--source-repo /path/to/chromium/src` vào lần
`review init` đầu tiên. Lệnh này đọc object Git mà không đổi checkout. Không
có Git thì việc so sánh source chỉ phủ các file trong cache. Một file thiếu
trong cache nghĩa là nội dung của nó chưa biết, không phải Chromium đã xoá nó.

Đọc [reference/investigation.md](reference/investigation.md) trước khi ghi
quyết định hoặc refresh một review đã có. Nó giải thích cách đọc cấu hình đã
lưu, giữ nguyên cache/nguồn Git và lưu tiến độ.

## Đọc báo cáo và source

- `report.md` cho một cái nhìn tổng quan. Các bảng hiển thị của nó có thể
  không đầy đủ.
- `report.json` chứa toàn bộ finding. Dùng truy vấn có cấu trúc; không nạp cả
  file vào context và không coi một lần tìm văn bản là một lần review đầy đủ.
- `review-index.json` chứa cấu hình input, các finding, các fact không đổi,
  các quan hệ đã khai báo và các source delta.
- `review.json` lưu event, bằng chứng chống đỡ và quyết định cho mọi item đã
  lập chỉ mục. `review.md` là báo cáo dựng ra từ các quyết định đó.

Trường `change` của một finding chứa `before`, `after`, `deltas`, `paths`,
`locations` và `signals`. `unconfirmed` cho biết bằng chứng chưa đủ để khẳng
định sự vắng mặt. Đọc phần coverage và các lý do trước khi nói một khai báo đã
bị xoá.

## Phân tích các thay đổi

1. Đọc metadata của lần so sánh và chạy `review overview` trước các truy vấn
   chi tiết. Dùng các con số trên toàn chỉ mục của nó để chọn truy vấn cho
   phạm vi đã xác nhận; không nạp hàng nghìn dòng thô vào context. Kế toán cho
   toàn bộ kho item, gồm cả score thấp, finding không có signal, source delta
   và bản tóm tắt milestone. Một lần loại trừ cần lý do gắn với phạm vi của
   user, không phải chỉ vì một từ khoá hay đường dẫn không khớp. Làm theo
   `reference/scoping.md`.
2. Xác định các thay đổi có thể liên quan. Dùng `related` để xem các quan hệ
   đã khai báo trên cả hai version, kể cả những khai báo không đổi. Chung một
   flag, tiền tố, màn hình, interface hay CL là lý do để điều tra, không phải
   bằng chứng rằng các item đó tạo thành một event.
   Với một lần so sánh tập trung vào một khu vực, MUST dùng quy trình trong
   [reference/focus.md](reference/focus.md) để lấy các ứng viên có source
   chống đỡ, trước khi coi một bộ lọc đường dẫn là toàn bộ tập bằng chứng.
3. Đọc source trước/sau và các consumer liên quan. Xem mọi hunk đã đổi của các
   file nằm trong phạm vi đã xác nhận, kể cả khi một số hunk đã có finding.
   Với các file phụ thuộc dùng chung, theo các phần được tham chiếu và các hunk
   liên quan như mô tả ở `reference/focus.md`; không đánh dấu cả file là đã
   xem khi còn hunk chưa đọc. Lần theo các identifier mà graph không giải
   được. Thay đổi không có finding vẫn cần được phân tích.
4. Khi nguyên nhân, trình tự hay ý định chưa rõ, dùng
   [reference/history.md](reference/history.md). Nó bao gồm cả cách tra theo
   finding lẫn cách xem lịch sử file trực tiếp khi `why.py` không tìm ra dòng
   nào. Đối chiếu các bản tóm tắt milestone với đúng lần so sánh đang xét;
   riêng ngày tháng của chúng không xác lập tính khả dụng ở version nào.
5. Chỉ gom các item lại khi bằng chứng của chúng chống đỡ cho một thay đổi có
   liên quan. Giải thích mỗi item đóng góp gì. Tách các thay đổi không liên
   quan ngay cả khi công cụ gom chúng lại. Nêu các quan sát từ source tách
   riêng khỏi ý định được suy ra và khỏi hệ quả riêng của sản phẩm.
6. Sau mỗi đợt, lưu các event và các câu hỏi chưa trả lời. Đọc danh sách event
   đã lưu và đối chiếu bằng chứng mới với các quyết định trước đó. Sửa lại các
   nhóm khi bằng chứng cho thấy chúng nên được gộp hoặc tách.
7. Trước khi giao kết quả, kiểm tra các item còn pending, các câu hỏi chưa
   giải và các event provisional. Chạy `review check` và `review render
   --require-complete`. Nếu còn việc và các bước kiểm tra được phép vẫn còn
   dùng được, tiếp tục đợt kế tiếp. Nếu một giới hạn tài nguyên thật sự hoặc
   bằng chứng thiếu ngăn việc hoàn tất, lưu tiến độ và giao một báo cáo còn dở
   kèm các con số và các bước kiểm tra tiếp theo.

Áp dụng quy trình này cho cả những identifier không quen. Các ví dụ trong
reference và tên signal không phải là danh sách tính năng cần đi tìm. Score có
thể ảnh hưởng thứ tự làm việc, nhưng không được quyết định bằng chứng nào được
xem xét hay event nào tồn tại. Không đặt trước một số lượng event cần tìm. Một
đợt nhỏ giới hạn lượng thông tin có mặt trong context tại một thời điểm, không
giới hạn phần so sánh cần review. Làm theo quy trình lặp lại cho item pending
trong `reference/investigation.md`; không dừng lại sau trang đầu tiên hay sau
một nhóm ví dụ thú vị.

## Truy vấn theo từng phần nhỏ

```bash
python3 -m chromiumdiff review check out/upgrade/review
python3 -m chromiumdiff review overview out/upgrade/review
python3 -m chromiumdiff review index out/upgrade/review --status pending --limit 30
python3 -m chromiumdiff review events out/upgrade/review --limit 30
python3 -m chromiumdiff review inspect out/upgrade/review 'KIND:KEY'
python3 -m chromiumdiff review related out/upgrade/review 'KIND:KEY' --hops 2
python3 -m chromiumdiff review unresolved out/upgrade/review
python3 -m chromiumdiff review source out/upgrade/review path/to/file.cc --side diff --start 1 --end 120
```

Dùng ID và đường dẫn lấy từ chỉ mục thật. Mọi truy vấn đều hỗ trợ `--cursor`,
`--limit` và `--max-chars`. Giới hạn đầu ra tính bằng ký tự, không phải token
của model. Đọc hết các trang còn lại cho tới khi `next_cursor` là null. Với
`index`, dùng `--after NEXT_AFTER` nếu các quyết định thay đổi giữa các trang:
offset dạng số trên một danh sách `--status pending` đang co lại có thể bỏ sót
item. Cách khác: quyết định cho mọi item trả về trong đợt pending hiện tại,
lưu lại, rồi lặp lại `index --status pending` từ cursor 0. Kiểm tra toàn bộ
review trước khi dừng: một lần tìm có lọc mà rỗng không có nghĩa là hết việc.
`review unresolved` liệt kê các tham chiếu graph chưa giải được, không phải
các quyết định review chưa xong; dùng `index --status unresolved` cho việc đó.

`inspect` trả về các trường dưới dạng đường dẫn JSON-pointer. Chuỗi dài có
offset và có thể trải qua nhiều trang. `events` trả về một danh sách ngắn; xem
một event ID để đọc trọn phần phân tích đã lưu của nó mà không phải nạp cả
review.

`related` trả về chuỗi các tham chiếu có kiểu, không phải kết luận nhân quả.
Nó không tự mở rộng các tham chiếu mơ hồ hay các CL khớp yếu. Nếu một node có
quá nhiều liên kết, truy vấn riêng node đó với `--hops 1` rồi đọc từng trang.

`source` trả về đúng ref, nguồn gốc source và hash SHA-256. `next_line` của nó
tách biệt với `next_cursor`: đọc hết các trang cho khoảng dòng đã yêu cầu, rồi
mới chuyển sang khoảng tiếp theo. Dùng `--side from` hoặc `--side to` để lấy
số dòng của source; số dòng trong diff không phải số dòng trong source.

Với một file bị thiếu, `source --fetch` lấy đường dẫn được yêu cầu tại đúng
ref. Nếu việc lấy thất bại hoặc không dùng được, nêu rõ phần bằng chứng còn
thiếu. Không thay thế bằng file từ một version khác trong cache. Để tìm
consumer trong source đã cache, đọc đúng `inputs.source_roots` từ chỉ mục rồi
dùng:

```bash
rg -n -F -- 'IDENTIFIER' EXACT_VERSION_ROOT
```

Đặt identifier và root theo giá trị quan sát được. Kết quả tìm kiếm là các vị
trí cần xem, không phải bằng chứng rằng code có chạy. Ở chế độ Git, dùng quy
trình `git grep` theo đúng ref trong `reference/history.md`; checkout đang làm
việc có thể khác.

## Diễn giải bằng chứng

- Flag và API: so sánh trạng thái Windows đã ghi và mọi điều kiện build lẫn
  runtime liên quan. Một giá trị mặc định trong source không phải là rollout
  đã đo được của sản phẩm.
- Khai báo bị xoá: xem các khai báo thay thế và các consumer trước khi kết
  luận rằng capability đó đã bị bỏ.
- Chữ ký API hoặc IPC: một khai báo đã đổi. Xác định các consumer bị ảnh hưởng
  và các tổ hợp version trước khi khẳng định có lỗi build hay lỗi runtime.
- Pref, switch và parameter: tìm nơi đọc, nơi ghi, các migration và các
  override từ bên ngoài. Không ghi nhận được gate nào không chứng minh rằng
  nó được dùng vô điều kiện.
- Hai version source xác lập khác biệt ròng giữa chúng. Các khẳng định về một
  lần tách, revert hay merge về sau đòi hỏi phần lịch sử tương ứng.

Đọc [reference/signals.md](reference/signals.md) để diễn giải nhãn của bộ phân
loại, [reference/traps.md](reference/traps.md) cho các giới hạn thường gặp của
bằng chứng từ source, và
[reference/settings-screen.md](reference/settings-screen.md) khi lần theo
route, control và điều kiện hiển thị WebUI.

## Viết báo cáo cuối

Mỗi event là một mục được đánh số, đặt tiêu đề theo chính thay đổi đó chứ
không theo riêng bucket, score hay identifier. Giải thích trước/sau, lý do gom
nhóm, các consumer bị ảnh hưởng, các điều kiện, bằng chứng, việc cần làm và
phần chưa chắc chắn. Dùng câu trực tiếp và định nghĩa các thuật ngữ kỹ thuật
xa lạ. Viết bằng ngôn ngữ của user; giữ nguyên chính xác các identifier trong
source và tên lệnh.

Ghi rõ version chính xác, platform và phạm vi. Phân biệt các thay đổi được
xác lập bởi source với các hệ quả phụ thuộc vào bản build hay cấu hình của
user. Kèm một bản tóm tắt ngắn và link tới bản review đầy đủ khi nó dài. Bản
review đầy đủ phải giữ lại mọi event có bằng chứng chống đỡ, kể cả khi bản
tóm tắt chỉ nêu một vài. Báo cáo `check.total`, các con số quyết định,
`by_kind` và số event provisional; số finding và số file chồng lấn nhau và
không phải số event. Không gọi các item chưa xem là `explained` hay
`out_of_scope` để kết thúc sớm hơn.

Kế toán đủ cho mọi item đã lập chỉ mục không chứng minh rằng mọi thay đổi có
ý nghĩa đã được phát hiện. Source trong cache có thể không đầy đủ; parser chỉ
phủ một phần cú pháp được chọn. Cấu hình bên ngoài, bản vá của sản phẩm và
giao diện đã render cần bằng chứng riêng. Không trình bày `review check` như
một sự phê duyệt phát hành.
