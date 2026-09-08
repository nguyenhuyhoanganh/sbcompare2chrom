---
name: analyzing-chromium-upgrades
description: Compares two Chromium versions with the chromiumdiff scripts and explains what changed, what it affects and what to verify or update, scoped to the product areas the user names, then publishes the result to Confluence or hands it back as a document. Use when analyzing a Chromium upgrade or version bump, interpreting a chromiumdiff report.json or review directory, or reviewing one area such as Settings, WebUI, Mojo or feature flags across two milestones. Use investigating-chromium-root-causes instead to trace one identifier or one reported symptom back to its cause.
---

# Phân tích một đợt nâng version Chromium

Script đọc các khai báo ra từ hai version Chromium rồi liệt kê khác biệt. Bạn
là người tìm ra mỗi khác biệt đó có nghĩa gì, ảnh hưởng tới đâu, và user phải
kiểm hay sửa gì. Bucket, score, signal và cluster chỉ nói cho bạn biết nên xem
cái gì trước. Chúng không bao giờ là câu trả lời.

## Luồng công việc

Chép checklist này vào câu trả lời của bạn, xong bước nào thì tick dòng đó:

```
Chromium upgrade review:
- [ ] 1 Lấy số phiên bản và phạm vi -- đọc reference/scoping.md trước
- [ ] 2 Tạo hoặc mở lần so sánh
- [ ] 3 Kiểm kê toàn bộ index
- [ ] 4 Lấy bằng chứng cho phạm vi -- đọc reference/focus.md trước
- [ ] 5 Đọc bằng chứng -- đọc reference/traps.md trước
- [ ] 6 Gom thành event và ghi quyết định -- đọc reference/investigation.md trước
- [ ] 7 Lặp 4 tới 6 cho tới khi xong phạm vi
- [ ] 8 Render bản review
- [ ] 9 Đưa kết quả cho user
```

Mỗi bước kết thúc bằng một **Checkpoint**: một điều phải đúng, và phải làm gì
khi nó chưa đúng. Chưa xong checkpoint của bước trước thì không bắt đầu bước
sau. Chưa tự kiểm checkpoint thì không tick dòng đó.

Đọc hết reference được nêu ở một bước, trước khi bắt đầu bước đó. Nếu trong
lần chạy này bạn đã đọc rồi thì không cần mở lại. Còn ba reference nữa đọc
trong bước 5, khi gặp đúng chủ đề của chúng:
[signals.md](reference/signals.md) để biết các nhãn của bộ phân loại nghĩa là
gì, [settings-screen.md](reference/settings-screen.md) cho route, control của
WebUI và điều kiện chúng hiện ra, và [history.md](reference/history.md) cho CL
và bug, và trước khi bạn nói vì sao một thay đổi được làm, hoặc nói nó bị
tách, bị revert hay được merge.

`MUST` nghĩa là bắt buộc phải làm. Chạy mọi lệnh từ thư mục gốc của project;
`python3 -m chromiumdiff` hỏng ở chỗ khác. Đọc file này, chép một lệnh trong
đó ra, hay chỉ đọc `report.md` — đều chưa đủ để qua bất kỳ checkpoint nào.

## Từ vựng

- **Fact**: một khai báo đọc ra từ một version; nó có thể không đổi.
  `--fact-kind` lọc theo loại của nó.
- **Finding**: một khác biệt giữa các fact đã đọc, đặt tên bằng `kind:key`.
- **Source delta**: một khác biệt trong nội dung file, gồm cả code không
  parser nào hiểu. **Hunk** là một đoạn của diff một file.
- **Event**: một thay đổi bạn giải thích trong báo cáo cuối. Nó có thể gồm một
  finding hoặc nhiều finding, nằm ở nhiều file và nhiều commit.
- **Consumer**: code hoặc hệ thống bên ngoài gọi một API, đọc một giá trị,
  hiện thực một interface, hoặc phụ thuộc kiểu khác vào hành vi đã đổi.
- **Gate**: một điều kiện quyết định code hay API có dùng được hay không.
  **Rollout** là chuyện nó có thật sự dùng được trong sản phẩm đã phát hành
  hay không. Cái này có thể khác với giá trị mặc định viết trong source.
- **Scope**: các khu vực và quyết định user đưa cho bạn ở bước 1.
  **Acquisition** là chuyện khác: script tải và đọc bao nhiêu phần Chromium,
  đặt bằng `--target-set` và `--partition` ở bước 2.

## Bước 1 — Lấy số phiên bản và phạm vi

MUST hỏi mọi thứ còn thiếu trước khi chạy so sánh hay phân tích finding. Hỏi
hết trong một lượt, bằng ngôn ngữ của user:

> 1. So sánh hai phiên bản nào? Tốt nhất là số phiên bản đầy đủ, ví dụ
>    `148.0.7778.217` và `151.0.7922.138`. Chỉ ghi milestone như `148` cũng
>    được: nó sẽ thành bản stable Windows mới nhất của milestone đó tại đúng
>    lúc tôi chạy, nên cùng một yêu cầu chạy lại sau có thể ra bản khác.
> 2. Tôi nên review khu vực nào: Settings, History, Bookmarks, Extensions,
>    Downloads, khu vực khác bạn nêu tên, hay so sánh diện rộng? Chọn nhiều
>    cũng được.
> 3. Loại khai báo nào quan trọng với bạn: feature flag, preference, switch
>    dòng lệnh, Mojo interface, Web IDL, WebUI control và route — hay tất cả?
>    Chưa chắc thì trả lời "tất cả".
> 4. Điều gì quan trọng nhất: thay đổi người dùng sẽ thấy, năng lực mới, hay
>    thay đổi mà sản phẩm của bạn phải thích ứng?

Các khu vực trên là ví dụ, không phải danh sách để đi tìm. Câu 3 chỉ thu hẹp
phần được đánh dấu là user yêu cầu; một loại bạn không chọn vẫn xuất hiện khi
nó giải thích cho loại bạn đã chọn, nên trả lời "tất cả" không mất gì. Đừng
bắt user phân loại code: trả lời bằng ngôn ngữ sản phẩm là đủ.

MUST chờ khi còn thiếu bất kỳ mục nào. Không tự chọn phiên bản, khu vực hay
loại khai báo, và không quay sang lấy N dòng đầu hoặc score cao nhất. Nếu user
đã trả lời rõ thì dùng luôn, không hỏi lại; khi làm tiếp, giữ nguyên những gì
đã ghi trừ khi user đổi.

So sánh diện rộng là một câu trả lời hợp lệ, gồm năng lực mới, thay đổi hành
vi, thay đổi API, migration và việc đã lên lịch, không chỉ vấn đề tương thích.

[reference/scoping.md](reference/scoping.md) liệt kê các trường cần ghi vào
`review/request.md`, và cách chọn acquisition mà không bỏ rơi những phụ thuộc
mà khu vực đã chọn cần tới.

**Checkpoint 1.** Đã biết cả hai phiên bản, và `review/request.md` tồn tại,
trả lời đủ mọi trường scoping.md liệt kê. Nếu bạn đoán một phiên bản, một khu
vực hay một loại khai báo, hoặc tự chọn, thì chưa đạt: dừng lại và hỏi user.

## Bước 2 — Tạo hoặc mở lần so sánh

Python 3.9 trở lên là đủ. Không cài gì thêm. Script chỉ so bản Windows và
không có tuỳ chọn nào đổi được điều đó. Ghi lại đúng `from_ref` và `to_ref`
mà report trả về, vì một số milestone trần có thể trỏ vào bản khác ở lần chạy
sau.

Với một lần so sánh mới:

```bash
cache_dir=.chromiumdiff-cache
python3 -m chromiumdiff check
python3 -m chromiumdiff run FROM TO --cache "$cache_dir" --out out/upgrade
python3 -m chromiumdiff review init out/upgrade --directory out/upgrade/review --cache "$cache_dir"
```

Thay FROM/TO và các đường dẫn bằng phiên bản user yêu cầu. Một lần chạy tải
khoảng 315 MB mỗi version và đọc mọi file mà target của nó phủ. Nó vẫn không
đọc hết Chromium, và nó không hiểu mọi loại code nó tải về. `--target-set
smoke` chỉ đọc ba file; dùng nó để kiểm công cụ có chạy không, đừng bao giờ
dùng để so hai version. `--partition` tải ít hơn, và chỉ dùng sau khi user
đồng ý đọc ít hơn.

Nếu đã có report mà chưa có review, chạy `review init` với đúng cache của
report đó. Nếu đã có review rồi thì sang bước 3. Chỉ chạy `review init` lại
khi đầu vào của nó đã đổi, và đọc
[reference/investigation.md](reference/investigation.md) trước: một lần refresh
phải dùng lại cache và nguồn Git đã lưu.

Nếu user có sẵn checkout Git Chromium ở máy, thêm
`--source-repo /path/to/chromium/src` vào `review init`. Khi đó nó lấy được
danh sách đầy đủ các file đã đổi ở cả hai version. Nó đọc object Git và không
làm gì tới checkout. Không có nó thì lần so sánh chỉ thấy các file đã có trong
cache, và một file thiếu trong cache nghĩa là bạn không biết trong đó có gì,
chứ không phải Chromium đã xoá.

Lần chạy ghi ra:

- `report.md`, một bản tóm tắt. Bảng của nó có thể bỏ sót dòng.
- `report.json`, mọi finding. Hãy truy vấn nó. Đừng nạp cả file, và một lần
  tìm chuỗi trên nó không phải là đã review.
- `review-index.json`, các thiết lập lần chạy đã dùng, cộng với các finding,
  các fact không đổi, các liên kết giữa chúng và diff của từng file.
- `review.json`, các event và bằng chứng của bạn, cùng một quyết định cho mọi
  item. Bước 8 biến nó thành `review.md`.

**Checkpoint 2.** `review init` thoát mã 0 và thư mục review có
`review-index.json` cùng `review.json`. Nếu hỏng thì sửa đầu vào rồi chạy lại.
Chỉ làm việc trên `report.md` thì chưa đạt.

## Bước 3 — Kiểm kê toàn bộ index

```bash
python3 -m chromiumdiff review check out/upgrade/review
python3 -m chromiumdiff review overview out/upgrade/review
python3 -m chromiumdiff review overview out/upgrade/review --group-by path --path-depth 3
```

`check` thoát mã 1 khi còn việc chưa xong. Ở đây như vậy là bình thường. Đọc
JSON nó in ra. `overview` đếm toàn bộ index đã lưu ngay trong script và chỉ in
ra con số, không in dòng dữ liệu hay diff. Hãy chọn truy vấn tiếp theo từ
những con số đó, để không phải kéo hàng nghìn dòng vào context chỉ để biết
trong đó có gì.

Con số này phủ mọi thứ, kể cả score thấp, finding không có signal, diff của
file và milestone summary. Muốn bỏ một thứ ra ngoài thì cần một lý do đến từ
phạm vi user đã nêu. "Từ khoá của tôi không khớp" và "đường dẫn của tôi không
khớp" không phải lý do. scoping.md liệt kê các bộ lọc `--path-prefix`,
`--item-kind`, `--fact-kind` và nói từng cái bỏ sót những gì.

**Checkpoint 3.** Bạn đã đọc JSON của `check` và `overview`, đã biết
`index_total`, và các truy vấn của bạn lấy ra từ những con số đó. Chọn truy
vấn từ bảng trong `report.md` thì chưa đạt.

## Bước 4 — Lấy bằng chứng cho phạm vi

MUST làm theo [reference/focus.md](reference/focus.md) trước khi bạn coi một
bộ lọc đường dẫn là toàn bộ bằng chứng. Lọc theo đường dẫn bỏ sót những thứ
khai báo ở chỗ khác, ví dụ một Mojo interface mà file Settings gọi tới nhưng
lại nằm trong `services/`.

```bash
python3 -m chromiumdiff review focus out/upgrade/review \
  --path-prefix PREFIX --output out/upgrade/review/area-focus.json
python3 -m chromiumdiff review focus-read out/upgrade/review --file out/upgrade/review/area-focus.json
```

Lấy PREFIX từ những gì bước 3 in ra. focus.md giải thích các tuỳ chọn còn lại,
các phần của gói bằng chứng, và cách đọc hết từng phần.

Dùng thêm `review related`. Nó cho thấy các liên kết mà parser đã ghi nhận, ở
cả hai version, kể cả những khai báo không đổi. Hai item dùng chung một flag,
một tiền tố đường dẫn, một màn hình, một interface hay một CL là lý do để xem,
không phải bằng chứng chúng là một event. Gói này chỉ là bằng chứng bạn thu
thập: đọc nó không đánh dấu gì là đã review và không loại trừ gì cả.

**Checkpoint 4.** File gói bằng chứng đã tồn tại, và với mọi phần bạn chọn,
bạn đã đọc tiếp cho tới khi `next_cursor` trả về null, kể cả `unresolved`. Nếu
bạn dừng một phần giữa chừng thì bạn chưa đọc chỗ bằng chứng đó.

## Bước 5 — Đọc bằng chứng

Đọc [reference/traps.md](reference/traps.md) trước khi bạn kết luận bất cứ
điều gì từ source, từ việc một thứ có dùng được hay không, hay từ việc một thứ
biến mất.

Đọc source trước và sau, và cả code dùng tới nó. Với file nằm trong phạm vi,
xem mọi hunk thay đổi, kể cả hunk đã có finding rồi. Với file dùng chung nằm
ngoài phạm vi, bắt đầu từ những khai báo mà gói bằng chứng trỏ tới rồi lần
theo các hunk quanh đó, như focus.md mô tả; đừng đánh dấu cả file là đã review
khi còn hunk trong đó chưa đọc. Lần theo những identifier mà parser không phân
giải được. Một thay đổi không có finding vẫn phải xem.

Trường `change` của một finding chứa `before`, `after`, `deltas`, `paths`,
`locations` và `signals`. `unconfirmed` nghĩa là lần chạy chưa đọc đủ để chắc
rằng thứ đó thật sự mất. Đọc các con số coverage và các lý do trước khi bạn
nói một khai báo đã bị gỡ.

Từng loại bằng chứng nói được gì và không nói được gì:

- Flag và API: đối chiếu trạng thái Windows đã ghi nhận, cộng với mọi điều
  kiện build và runtime quanh nó. Một giá trị mặc định viết trong source không
  chứng minh được cái gì đã tới tay người dùng.
- Khai báo bị gỡ: tìm khai báo thay thế, và xem code từng dùng nó, trước khi
  bạn nói tính năng đó đã mất.
- Chữ ký API hoặc IPC: cái này chỉ nói một khai báo đã đổi. Hãy tìm ra code
  nào dùng nó, và cặp version nào mới quan trọng, trước khi bạn nói build hay
  lúc chạy sẽ hỏng.
- Pref, switch và parameter: tìm code đọc nó, code ghi nó, migration nếu có,
  và bất cứ thứ gì ngoài binary có thể ghi đè nó. Nếu không thấy gate nào thì
  điều đó không có nghĩa là code luôn chạy.
- Hai version của source chỉ nói cho bạn khác biệt giữa đúng hai version đó.
  Muốn nói một thứ bị tách ra, bị revert, hay được merge về sau, bạn cần lịch
  sử commit cho việc đó.

Đọc [signals.md](reference/signals.md) trước khi bạn suy ra bất cứ điều gì từ
các nhãn của bộ phân loại. Đọc
[settings-screen.md](reference/settings-screen.md) khi bạn lần theo route,
control của WebUI và các điều kiện làm chúng hiện hay ẩn. Đọc
[history.md](reference/history.md) khi bạn không biết vì sao một thay đổi được
làm, hoặc thứ tự các việc ra sao; nó nói cả cách tra CL từ một finding, và
cách đọc thẳng lịch sử file khi `why.py` không tìm ra dòng nào. Đối chiếu
milestone summary với đúng hai version: chỉ riêng ngày tháng của nó không nói
được tính năng đó đã có ở version nào.

Các lệnh `index`, `inspect`, `related` và `source` được giải thích ở cuối file
này.

**Checkpoint 5.** Với mọi ứng viên trong đợt, bạn đã đọc source trước và sau,
và bạn biết các điều kiện quanh nó. Mọi item bạn chưa trả lời được đều ghi rõ
bước kiểm tiếp theo. Một preview có `truncated` không tính là đã đọc: mở nó
bằng `review inspect` trước.

## Bước 6 — Gom thành event và ghi quyết định

Đọc [reference/investigation.md](reference/investigation.md) trước. Nó cho
định dạng của một quyết định, các trạng thái một item có thể ở, và cách làm
hết danh sách pending.

Chỉ xếp các item vào cùng một event khi bằng chứng nói chúng là một thay đổi,
và nói rõ từng item đóng góp gì. Giữ các thay đổi không liên quan tách riêng,
kể cả khi công cụ đã gom chúng lại. Nói tách bạch ba thứ: bạn thấy gì trong
source, bạn nghĩ nó nhằm mục đích gì, và nó có nghĩa gì với sản phẩm này.

```bash
python3 -m chromiumdiff review record out/upgrade/review --file /path/to/decisions.json
python3 -m chromiumdiff review check out/upgrade/review
```

Lưu event và các câu hỏi chưa trả lời trong từng đợt. Đọc danh sách event đã
lưu và đối chiếu bằng chứng mới với quyết định trước, sửa lại một nhóm khi bằng
chứng nói nó nên được gộp hoặc tách. Đừng tách một event thành hai chỉ vì bạn
tình cờ xem các phần của nó ở hai đợt khác nhau.

**Checkpoint 6.** `review record` đã nhận đợt đó, và lần `review check` bạn
chạy sau nó cho thấy số pending giảm đúng bằng số item bạn đã quyết. Nếu không
giảm thì đọc kết quả `record` trả về. Đi ghi một nhóm item khác thay vào đó
thì chưa đạt.

## Bước 7 — Lặp 4 tới 6 cho tới khi xong phạm vi

```bash
python3 -m chromiumdiff review index out/upgrade/review --status pending --limit 30
```

Giữ nguyên bộ lọc đường dẫn và loại của phạm vi mỗi lần chạy truy vấn đó. Xem
riêng phần source hỗ trợ và các phụ thuộc nằm ngoài bộ lọc. investigation.md
cho các quy tắc con trỏ giúp một danh sách pending đang co lại không nhảy cóc
mất item.

Bạn chỉ được dừng trước khi cả index được quyết vì đúng một lý do: phạm vi user
đưa cho bạn đã xong. Những dòng trông thú vị, một ngưỡng score và một số trang
đều không phải lý do để dừng. Một đợt nhỏ giới hạn lượng thông tin bạn giữ
trong context tại một lúc; nó không giới hạn phần phạm vi bạn phải review. Nên
đừng dừng sau trang đầu, và đừng định trước sẽ tìm ra bao nhiêu event. Với
những identifier bạn chưa gặp bao giờ cũng làm y như vậy: các ví dụ trong
reference và tên signal không phải danh sách những thứ cần đi tìm.

Một truy vấn có lọc mà không trả về gì không có nghĩa là hết việc. `review
unresolved` liệt kê các tham chiếu parser không phân giải được, khác với những
quyết định bạn chưa làm; cái sau dùng `index --status unresolved`. Quay lại
các event bạn đánh dấu provisional. Kiểm lại danh sách pending sau khi bạn sửa
một event hoặc refresh review, vì cả hai đều có thể đưa item về lại pending.

**Checkpoint 7.** `index --status pending` kèm bộ lọc của phạm vi không trả về
dòng nào, bạn đã quay lại các event provisional, và bạn đã đọc `review check`
để lấy con số toàn index. Chỉ một truy vấn có lọc trả về rỗng thì chưa đạt: có
thể bộ lọc sai chứ không phải việc đã xong.

## Bước 8 — Render bản review

```bash
python3 -m chromiumdiff review render out/upgrade/review
```

Chỉ thêm `--require-complete` khi bạn đã review toàn bộ index. Nó thoát mã 1
và không ghi gì khi còn item hay event chưa xong. Một bản review giới hạn ở
một phạm vi không bao giờ tới trạng thái đó, vì các item ngoài phạm vi vẫn ở
pending, nên chạy không kèm tuỳ chọn này và để báo cáo ghi PARTIAL. Nếu bạn
phải dừng sớm vì hết ngân sách hoặc vì thiếu bằng chứng, nói rõ là cái nào
trong hai, kèm các con số và việc cần kiểm tiếp. Đừng bao giờ vượt qua một lần
check thất bại bằng cách đổi các item bạn chưa xem thành `explained` hay
`out_of_scope`.

`review.md` là bản ghi của chính công cụ: trước hết là các giới hạn coverage
nó đo được, rồi mỗi event một mục kèm bằng chứng. Bước 9 dựng từ nó, và
`render` ghi đè file này, nên đừng bao giờ sửa tay.

Có quyết định cho mọi item không có nghĩa là bạn đã tìm ra mọi thay đổi quan
trọng. Source trong cache có thể chưa đủ, và parser chỉ hiểu một số loại code.
Cấu hình bên ngoài binary, patch riêng của sản phẩm này, và UI như nó hiện ra
— tất cả đều cần bằng chứng riêng. `review check` không phải phê duyệt phát
hành.

**Checkpoint 8.** `review render` thoát mã 0 và `review.md` có đủ mỗi event
bạn đã ghi một mục. Nếu bạn chưa đọc file đó thì chưa đạt.

## Bước 9 — Đưa kết quả cho user

Hỏi kết quả nên đi đâu:

> Bạn muốn đưa cái này lên Confluence, hay nhận một tài liệu ở đây? Nếu lên
> Confluence, tôi cần biết trang: tạo trang mới nằm dưới một trang có sẵn, hay
> thay nội dung của một trang có sẵn. Cho tôi tên trang hoặc URL của nó.

Nếu chọn Confluence, dùng skill `managing-confluence` và đưa nó đúng trang user
đã nêu. Nếu skill đó không có trong lần chạy này, nói rõ ra rồi viết tài liệu
thay thế. Đừng đăng bằng cách nào khác, và đừng đoán một trang mà user chưa
nêu tên.

Nếu không, viết tài liệu vào `out/upgrade/review/delivery.md` rồi cho user
biết nó nằm ở đâu. `render` không đụng tới file này.

Cả trang Confluence lẫn tài liệu đều gồm đúng ba phần, theo thứ tự này.

**1. Lần chạy này đã xem những gì.** Đúng `from_ref` và `to_ref`, platform,
các khu vực và loại khai báo user đã yêu cầu, và đường dẫn tới thư mục review.
Nếu người đọc không biết hai bản nào được đem so, phần còn lại của trang vô
dụng với họ.

**2. Các thay đổi.** Mỗi event một dòng. Đưa những dòng user nói là quan trọng
nhất lên đầu; đừng sắp theo score.

| Thay đổi | Nghĩa là gì | Bằng chứng | Verify |
|---|---|---|---|
| Feature flag X bật mặc định | Người dùng Windows có X mà không cần bật flag | `base_feature:X`, `chrome/browser/x/features.cc:42` | Not verified |

`Thay đổi` nói việc gì đã xảy ra. Đừng để mỗi bucket, score hay identifier ở
đó. `Nghĩa là gì` nói người ta sẽ thấy gì, hoặc sản phẩm này phải sửa gì, viết
bằng ngôn ngữ của user. `Bằng chứng` liệt kê ID finding cùng file và dòng
source ở từng version, để người đọc mở ra xem được. `Verify` khởi đầu là
`Not verified` ở mọi dòng. Cột đó để một con người điền vào sau khi họ kiểm
dòng đó: trên Confluence dùng status marker màu xám, để những dòng chưa ai
kiểm dễ nhận ra; tài liệu thường không có màu, nên chỉ ghi đúng chữ đó. Bạn
MUST NOT đổi một dòng thành đã verify. Chỉ con người mới làm được việc kiểm
đó. Công cụ không làm được, và bạn cũng không.

**3. Lần chạy này chưa xem những gì.** Đặt phần này dưới một heading riêng,
trên cùng trang hoặc trong cùng tài liệu, không nhét thành một dòng chú thích
ở cuối. Chép sang từ `review.md` những gì lần chạy đã đo: mỗi bên đọc được bao
nhiêu file khai báo, những thư mục nó đọc được ít nhất, và những file không
target nào đọc tới. Rồi thêm những gì cách làm này vốn không làm được. Nó so
khai báo, không so việc code làm gì. Một file không parser nào hiểu thì không
bao giờ xuất hiện trong finding, dù nó có đổi hay không. Finch, cấu hình ngoài
binary, patch riêng của sản phẩm này và UI như nó hiện ra — tất cả đều cần
bằng chứng riêng. Nói rõ có bao nhiêu item bị bỏ ngoài phạm vi user yêu cầu.
Người đọc phải biết được việc một thứ **không có** trong bảng nghĩa là gì.

**Checkpoint 9.** Trang hoặc tài liệu đã tồn tại, có đủ ba phần, và mọi dòng
của bảng đều ghi `Not verified`. Một cái bảng thiếu phần 1 hoặc thiếu phần 3
thì chưa đạt: người đọc không biết các dòng đó nói về cái gì, và không biết
việc một thứ vắng mặt nghĩa là gì.

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
`--limit` và `--max-chars`. Cái cuối đếm ký tự, không đếm token. Đọc tiếp các
trang cho tới khi `next_cursor` là null. Với `index`, dùng `--after
NEXT_AFTER` khi quyết định của bạn thay đổi giữa các trang: danh sách pending
co lại mỗi khi bạn quyết một item, và một offset dạng số trên danh sách đang
co lại sẽ nhảy cóc mất item. Cách quyết hết cả đợt rồi chạy lại truy vấn từ
cursor 0 cũng được.

`inspect` trả tên trường theo đường dẫn JSON-pointer. Chuỗi dài có offset và
có thể trải qua nhiều trang. `events` trả một danh sách ngắn; inspect một event
ID để đọc toàn bộ phân tích đã lưu của nó mà không phải nạp cả review.

`related` trả các chuỗi liên kết, mỗi liên kết có kiểu. Nó không nói cho bạn
biết cái này gây ra cái kia, và tự nó không lần theo một tham chiếu mơ hồ hay
một CL khớp yếu. Nếu một node có quá nhiều liên kết, truy vấn nó bằng
`--hops 1` rồi đọc từng trang.

`source` trả đúng ref, nguồn gốc file, và hash SHA-256. `next_line` của nó là
thứ khác với `next_cursor`: đọc hết các trang của một khoảng dòng rồi mới sang
khoảng tiếp theo. Dùng `--side from` hoặc `--side to` khi bạn cần số dòng của
source, vì số dòng trong diff không phải số dòng trong file. Nếu một file
thiếu, `source --fetch` lấy nó về ở đúng ref. Nếu lệnh đó hỏng thì nói là
thiếu bằng chứng. Đừng bao giờ lấy file đó ở version khác dùng thay.

Một lần tìm theo từ khoá MUST NOT được dùng làm bằng chứng về việc code làm
gì, hay về mức độ đã phủ. Để tìm code dùng tới một thứ, đọc đúng giá trị
`inputs.source_roots` từ index, rồi:

```bash
rg -n -F -- 'IDENTIFIER' EXACT_VERSION_ROOT
```

Kết quả tìm kiếm là những chỗ cần tới xem. Chúng không chứng minh code có
chạy. Ở chế độ Git, dùng các bước `git grep` trong `reference/history.md`,
vốn ghim đúng ref, vì cây làm việc đang checkout có thể là version khác.
