# 7. Truy nguyên CL và issue — vì sao một thay đổi xảy ra

Sáu tài liệu trước trả lời câu hỏi **cái gì đã đổi**. Tài liệu này trả lời câu hỏi còn lại, và là câu hỏi người triage hỏi ngay sau đó: **ai đã đổi nó, và họ đang sửa cái gì.**

Đây là chặng duy nhất trong công cụ hỏi một thứ mà hai cây source không chứa. Nó được tách thành một lệnh riêng — `chromiumdiff serve` — vì nó cần mạng, và vì một báo cáo vẫn đáng đọc khi không có nó.

## Trả lời ngắn

Hai cây source nói được rằng một feature flag chuyển từ `disabled` sang `enabled`. Chúng **không thể** nói ai làm việc đó. Thông tin đó nằm ở nơi khác: trên Gerrit, review server của chính Chromium, nơi mọi thay đổi phải đi qua trước khi vào cây.

ChromiumDiff đi tới đó bằng bốn bước tra cứu, không bước nào là phỏng đoán:

```text
một Fact  →  file khai báo nó
          →  mọi CL đã merge chạm vào file đó trong khoảng giữa hai version
          →  những CL mà diff của chính nó nhắc tới identifier này
          →  footer `Bug:` của các CL đó, và mọi CL khác cite cùng issue
```

Bước thứ ba là toàn bộ giá trị. Ba bước còn lại đều rẻ và đều hiển nhiên; bước ba là bước biến một danh sách vô dụng thành một câu trả lời.

Kết quả trên một dòng báo cáo trông như sau:

```text
Why it changed (1 of 62 merged CLs touched this file):
  CL 7885356  2026-05-12  exact
  android: Enable AndroidCaptureKeyEvents by default
  → issue 41494401
```

Đó chính là finding — `AndroidCaptureKeyEvents` chuyển từ disabled sang enabled — được viết lại bằng lời của người đã làm ra nó.

## Vì sao chỉ biết file là chưa đủ

File khai báo là **tài sản chung**. Đo trên khoảng giữa hai điểm nhánh M148 và M151:

| File khai báo | Số CL đã merge chạm vào nó |
|---|---|
| `chrome/browser/about_flags.cc` | 500 |
| `third_party/blink/.../runtime_enabled_features.json5` | 337 |
| `content/public/common/content_features.cc` | 62 |

Đưa cho người đọc 500 CL cho một cái flag còn tệ hơn không đưa gì — nó biến một câu trả lời thành một việc phải làm. Vì vậy file **chỉ sinh ra ứng viên**, và ứng viên sau đó bị lọc bằng câu hỏi: *diff của chính CL đó, trên chính file đó, có nhắc tới identifier này không?*

Với `AndroidCaptureKeyEvents`: 62 ứng viên, sống sót đúng một.

Panel in cả mẫu số cùng với CL, vì `1 of 62` mới là thứ làm cho con số 1 có ý nghĩa. Một CL trong 62 là một trích dẫn; một CL trong 1 có thể chỉ là file đó vắng người.

## Toàn bộ luồng, nhìn từ trên xuống

```text
Finding (đã có score, đã có locations)
       │
       ▼
window_for(from_ref, to_ref)  — cửa sổ thời gian, lấy từ tag
   điểm nhánh tag cũ  →  điểm nhánh tag mới   (truy vấn ghim main)
                       →  ngày tag mới      (chỉ cho merge-back)
       │
       ▼
tokens_for(change) + container_for(change) + delta_tokens(change)
   identifier cần tìm, struct bao quanh nó, và giá trị mà Fact chuyển sang
       │
       ▼
tìm ứng viên trên Gerrit, theo file
   1. file:"<path>" branch:main
   2. nếu rỗng → cùng file, bỏ ghim branch      (merge-back)
   3. nếu vẫn rỗng → commit message toàn cửa sổ  (không ghim file)
       │
       ├── trả về đúng 500 dòng → chưa chứng minh được → chẻ đôi cửa sổ, hỏi lại
       │
       ▼
đọc diff của từng (CL, file)   — có ngân sách, chi theo thứ tự file rẻ trước
       │
       ▼
_match()  — so từng dòng đã đổi với token, container và delta
       │
       ▼
verdict: introduced / exact / moved / declares / described / crowded / touched
       │
       ▼
_prune()  — bỏ trùng, xếp hạng, cắt còn tối đa 12, sắp cũ trước
       │
       ▼
bugs_in(message)   — footer Bug:/Fixed:, miễn phí trong kết quả tìm kiếm
       │
       ▼
finding.enrichment["gerrit"]  →  panel trong HTML, và các dòng trong report.md

       ╌╌ tới đây là hết một lượt tra dòng ╌╌

người đọc bấm chip issue trên một CL
       │
       ▼
issue_meta()  →  issue_history()
   tiêu đề + có mở được không   các CL khác cùng cite issue đó
```

Các mục dưới đây đi qua từng chặng.

## Bước 1 — Cửa sổ thời gian lấy từ tag, không ước lượng

Muốn hỏi "CL nào đã merge giữa hai version" thì phải có hai mốc ngày. Lấy ngày của hai tag là sai, và sai theo hướng nguy hiểm nhất: **bỏ sót**.

Một release branch được cắt ra khỏi `main` từ rất sớm, rồi mới được đóng tag nhiều tuần sau đó. Tag của Chromium ghi lại chính xác chỗ nó rời `main`, trong dòng `Cr-Branched-From:` của commit message. ChromiumDiff đọc dòng đó.

Đo trên M148: điểm nhánh là **2026-04-06**, tức **bảy tuần** trước ngày ghi trên chính cái tag. Bảy tuần CL sẽ biến mất nếu lấy ngày tag.

Cận trên thì có **hai** giá trị, vì hai truy vấn đang hỏi hai câu khác nhau.

Truy vấn ghim `branch:main` phải dừng ở **điểm nhánh của tag mới**. Một CL land lên main sau khi release branch đã cắt thì không nằm trong cây đã phát hành, nên nó không thể là nguyên nhân của bất cứ thứ gì. Và nó không phải ứng viên vô hại: nó vẫn có thể mang identifier, vẫn ăn verdict `exact`, và vẫn xếp trên CL thật sự gây ra thay đổi.

Đo trên 105 row đã resolve khi cận trên còn là ngày tag: **38 trong 160 CL được trích dẫn đã land sau khi M151 tách nhánh, 11 row xếp một trong số đó lên đầu, 9 row không trích gì khác.** Năm flag Autofill khác nhau cùng bị gán cho một CL dọn dẹp mà M151 không hề chứa. Sửa cận trên đưa cả ba con số về 0, và pool ứng viên giảm khoảng một nửa.

Truy vấn **bỏ ghim branch** thì vẫn chạy tới ngày tag mới, vì merge-back còn land lên release branch nhiều tuần sau khi cắt và những commit đó **nằm trong cây đang được so**. M151 tách ngày 2026-06-29 và tag ngày 2026-08-10 — sáu tuần đó thuộc về câu hỏi này, và không thuộc về câu hỏi nào khác.

## Bước 2 — Danh sách ứng viên, và chỗ Gerrit im lặng

Truy vấn ứng viên là một câu hỏi theo file, giới hạn trong cửa sổ, chỉ lấy CL đã merge.

Ở đây có một cái bẫy phải biết: **Gerrit dừng ở 500 dòng cho truy vấn ẩn danh và không nói gì cả.** Hỏi `start=500` thì nó trả về một trang rỗng, không có dấu hiệu `_more_changes` nào — tức là **không phân biệt được** với việc đã đọc hết.

Nên một truy vấn trả về đúng ở mức trần là một truy vấn **chưa được chứng minh**. ChromiumDiff chẻ đôi cửa sổ và hỏi lại cho tới khi xác lập được con số. Đo trên `about_flags.cc`: hỏi nguyên khối trả về 500; chẻ ba trả về 130 + 196 + 174 = 500. Cái đó đúng là 500 thật — nhưng **phép chẻ mới là thứ chứng minh điều đó**, và nếu không chẻ thì con số 500 và con số 1.500 sẽ trông y hệt nhau.

Khi danh sách vẫn bị cắt, panel in **cả hai số**. `chrome/browser/flag-metadata.json` bị **662** CL chạm vào trên cặp này, và chỉ 500 cái mới nhất được đọc — nên một dòng khai báo trong đó hiện `3 of 662 merged CLs touched this file · 500 of them read`. Tìm thấy và đã đọc là hai khẳng định khác nhau, và khoảng cách giữa chúng chính là chỗ một CL bị thiếu sẽ nằm.

## Bước 3 — Lọc ứng viên bằng chính diff của CL

Đây là chặng tốn tiền và cũng là chặng quyết định. Mỗi cặp `(CL, file)` là một request HTTP.

### Các mức bằng chứng, không bao giờ trộn thành một điểm số

Mỗi CL mang theo một **verdict** nói rõ nó được tìm ra bằng cách nào. Các verdict **không** cộng lại thành score, vì chúng trả lời những câu hỏi khác nhau và một người đọc phải phân biệt được chúng:

| Verdict | Nó khẳng định điều gì | Chi phí thêm |
|---|---|---|
| `introduced` | trong chính declaration này, CL **thêm** giá trị mà Fact kết thúc ở đó, **hoặc xoá** giá trị nó bắt đầu từ đó — CL này *là* thay đổi | không |
| `exact` | một dòng CL đã sửa có mang identifier này | một request/CL |
| `moved` | file bị đổi tên và Fact đi theo; không dòng nào thay đổi | không |
| `declares` | CL sửa **thân** declaration, không phải dòng đặt tên nó | một request/CL |
| `described` | tiêu đề hoặc mô tả của chính CL nhắc tên nó; không đọc diff nào | không |
| `crowded` | quá bốn CL cùng sửa declaration này, nên không cái nào chỉ ra được cái nào | không |
| `touched` | không gì khớp identifier; đây chỉ là các CL mới nhất đã chạm file | không |

**Các verdict phía trên gọi tên được Fact. Hai cái cuối thì không** — và ranh giới đó được vẽ rõ trong code bằng một hằng số (`CITES`), chứ không để cho màu badge tự gánh.

Chúng **không thừa nhau, và cũng không được dùng ngang nhau**. Đo trên top 150 finding của một lần chạy M148 → M151 thật: **145 dòng được trả lời chỉ bằng diff, 2 dòng bằng cả diff lẫn lời tác giả, và không dòng nào chỉ bằng lời tác giả.**

`described` giữ chỗ của nó nhờ **hình dạng mà không phép tìm diff nào với tới được** — một CL xoá đúng cái declaration mang tên nó thì identifier không còn nằm trong dòng nào sống sót — chứ không nhờ tần suất.

### `introduced` — verdict duy nhất mà câu trả lời *là* thay đổi

Có một lớp finding mà tên của nó là **cấu trúc do công cụ dựng lên**, không phải chuỗi ký tự tồn tại trong file. Ví dụ kinh điển là `blink.mojom.TokenError.url`. Một file `.mojom` viết như sau:

```text
struct TokenError {
  url.mojom.Url? url;
};
```

Nó không bao giờ viết chuỗi `blink.mojom.TokenError.url`, còn `url` thì quá ngắn để tìm. Hệ quả trước khi có verdict này: 10 diff được đọc để tìm một chuỗi **không thể xuất hiện trong bất kỳ diff nào**, và kết quả được báo là *"không CL nào sửa dòng mang identifier này"* — đúng về mặt kỹ thuật, và sai lệch nghiêm trọng về mặt ý nghĩa.

Câu trả lời vốn đã nằm sẵn trong báo cáo và chưa bao giờ được tiêu. Một `Change` không chỉ gọi tên declaration — nó ghi lại **hai trạng thái** của declaration đó:

```json
{"type": ["array<url.mojom.Url>", "array<network.mojom.LinkHeader>"]}
```

Và CL đã làm ra thay đổi đó, theo định nghĩa, là CL có diff **thêm vào** một dòng chứa `array<network.mojom.LinkHeader>`, nằm bên trong declaration đó — hoặc **xoá đi** dòng chứa `array<url.mojom.Url>`. Cả hai phía đều tính, vì cả hai đều *là* thay đổi đang diễn ra: một phép đổi tên làm trong một CL thì thêm và xoá cùng lúc, làm trong hai CL thì không. `blink.mojom.AIManagerCreateClientError` đi từ `kUnsupportedPerformancePreference` sang `kIncompatiblePreferenceOptions` qua **hai CL cách nhau hai ngày**, và CL đầu chỉ xoá tên cũ — không dòng nào ở đâu mang giá trị cuối cho tới CL thứ hai. Chỉ hỏi về dòng thêm thì CL đầu bị gọi là hàng xóm, mà nó không phải. Mọi verdict khác hỏi *"CL này có chạm vào thứ đó không"* — câu mà bất kỳ CL nào reformat file cũng thoả mãn. `introduced` hỏi *"CL này có đặt giá trị mới vào đó không"*.

Ba điều kiện làm cho nó không sinh ra kết quả rác:

- **Chỉ tìm phần khác nhau giữa hai trạng thái.** Một giá trị có ở cả hai phía thì không hề đổi, và nó sẽ khớp với mọi CL từng chạm declaration đó vì bất cứ lý do gì.
- **Chỉ tìm thứ trông giống code.** Phải có chữ hoa ở giữa, dấu gạch dưới, dấu chấm, hoặc đơn giản là dài. `kPreinstalledExtensions`, `IS_ANDROID`, `array<network.mojom.LinkHeader>` nhận diện được một thay đổi; `enabled`, `stable`, `109` xuất hiện trong mọi declaration khác của cùng file và không nhận diện gì.
- **So với văn bản của phía kia, không phải tập token của nó.** `Vector2d` sẽ đọc ra thành "đã mất đi" khi type đổi thành `Vector2dF`, tức là biến chính CL làm ra thay đổi thành bằng chứng cho điều ngược lại.

Đo trên top 150 finding của một lần chạy M148 → M151 thật: **37 CL đạt `introduced`, trải trên 33 dòng**, và **29 trong 33 dòng đó quy về đúng một CL**.

`TokenError.url` giờ đọc ra CL 7982397, *"[FedCM] Modernize TokenError::url from string to url.mojom.Url"* — dù **không một CL nào trong 10 ứng viên mang cái tên đó**.

### `declares` — và bài học "không có bán kính nào đúng"

Một Mojo method mọc thêm tham số thì dòng mang **tên** nó không hề đổi; phép sửa nằm ở phần thân bên dưới. Nếu chỉ tìm dòng mang tên, cả lớp finding này trả về rỗng.

Hai bán kính cố định đã được thử, và cả hai sai theo cùng một kiểu, theo hai hướng ngược nhau:

| Cách thử | Kết quả |
|---|---|
| Đối xứng, rộng 25 dòng | Trên một file toàn declaration thì mọi phép sửa đều gần mọi declaration. `AIManager.CreateLanguageModel` kéo về **4 CL không liên quan**, `DevToolsSession.DispatchProtocolCommand` kéo **5** |
| Chỉ tiến, rộng 3 dòng | Sửa được hai ca trên — cả hai còn **đúng một CL**, và là CL đúng — nhưng một danh sách tham số dài không nằm gọn trong ba dòng, nên `OnScriptLoadStarted` khi mọc tham số thứ bảy **không khớp gì cả** |

Kết luận: **không có bán kính nào đúng**, vì bài toán không phải là khoảng cách. Declaration kết thúc ở dấu đóng của **chính nó**, và đó là thứ được quét:

| Dạng khai báo | Vùng quét |
|---|---|
| `struct Bar {` | tới `}` khớp với nó |
| `Foo(` | tới `);` đóng danh sách tham số |
| `Type name;` | đúng một dòng |
| không có gì đóng cả | block **trong cùng bao quanh** cái tên |

Trường hợp cuối là `runtime_enabled_features.json5`: nó đặt tên feature bên trong một record `{ … },` và không có gì phía sau kết thúc bằng `;`. Riêng quy tắc đó chọn ra **1 trong 337 CL** chạm file đó, và đó là CL 7895296, *"Return empty styles for getComputedStyle() outside flat tree"*.

Vùng quét bị chặn ở 60 dòng, để một file mà scanner không hiểu cú pháp không thể làm bước này thành bậc hai. Một declaration dài hơn thế thì cũng không phải thứ quy trách nhiệm được.

Có một cái bẫy nhỏ trong bản quét tiến, đáng nhắc vì nó im lặng: bản quét phải học cách **không tin một thay đổi mà nó đi ngang qua** trên đường xác định xem vùng có đóng lại hay không. Trả `True` ngay khi gặp sẽ báo phép sửa của *record kế tiếp* thành phép sửa của record này — và nó sai đúng trên loại cú pháp làm bản quét thất bại ngay từ đầu.

### Hai verdict yếu — để một dòng luôn có câu trả lời

Con số "150 trên 150 dòng đều có CL" là phép đo của **một lát cắt của một lần chạy**, không phải một tính chất của công cụ. Câu hỏi nó mời gọi — *một dòng có luôn được trả lời không* — có năm câu trả lời "không" riêng biệt:

1. tên ngắn dưới bốn ký tự thì không tìm được, nên tập token rỗng và vòng lặp diff bỏ qua finding;
2. file bị ngân sách diff từ chối thì chỉ còn giữ lại phần mô tả;
3. quá bốn CL cùng sửa một declaration thì **trước đây bị bỏ hết**;
4. diff đọc rồi mà không khớp gì thì không khớp gì;
5. một Fact mà tên là cấu trúc của ta thì rơi về container của nó, và container cũng có thể trượt.

Bốn trong năm trường hợp đó **vốn đã cầm sẵn các CL ứng viên**. Chỉ thiếu cách trình bày — và `crowded` với `touched` chính là cách trình bày đó.

Đánh đổi ở đây được nói thẳng, vì nó là một quyết định có thể tranh luận. `crowded` trước đây **bị bỏ**: 11 CL cùng sửa `ai_manager.mojom` và không cái nào chỉ ra được `AIManager.CreateLanguageModel`, nên bốn câu trả lời sai đầy tự tin tệ hơn không có câu nào. Lập luận đó **vẫn đúng**, và vẫn là lý do badge không phải `declares`. Cái nó *kết luận* sai là: nó đáp lại một người vừa bấm vào dòng bằng sự im lặng, về một declaration mà 11 CL đã sửa thật. Đưa ra 11 CL đó và nói rõ chúng là gì thì nhiều hơn hẳn việc không đưa gì — **miễn là không có gì ở chúng đọc ra như một trích dẫn**.

Nên có **ba lớp** giữ cho manh mối không bị nhầm thành trích dẫn, vì một lớp là không đủ cho thứ người ta lướt qua:

- dòng có **state riêng** (`weak`), và bộ lọc "Has a CL" **loại nó ra** — con số "đã hiểu được bao nhiêu" không thể bị thổi phồng bởi những dòng chỉ liệt kê review;
- badge **màu xám**, không mượn màu của verdict thật;
- danh sách in dưới một **câu chữ** nói rõ đây là manh mối, không phải trích dẫn.

Hai verdict yếu **không dùng chung câu đó**, vì chúng không phải cùng một khẳng định:

| | `touched` | `crowded` |
|---|---|---|
| Nói gì | các CL này chạm file, không gì buộc chúng vào identifier | mọi CL đã sửa **chính declaration này** |
| Là gì | manh mối | **lịch sử** của declaration đó |
| Trình bày | mới nhất trước, tối đa 3 | **cũ trước**, tiêu đề *"How it got here"* |

`touched` đọc ứng viên từ **danh sách tìm kiếm** chứ không từ diff, và đó chính là ý nghĩa của nó: file không sinh ra gì khác là file chưa ai đọc.

Và có một trường hợp riêng phải tách ra: **một dòng bị ngân sách diff từ chối không phải là một dòng đã được tìm.** Đổ manh mối vào đó làm nó *đọc ra* như đã tìm hết, đồng thời lấy luôn lối thoát của nó — vì câu gợi ý khắc phục và nút tra cứu đều nằm trong nhánh chỉ chạy khi không có CL nào cả. Kết quả là đúng cái dòng còn trả lời được lại thành cái dòng không hỏi được nữa. Giờ nó nói `Not looked up — 147 CLs touched this file, more than the run's diff budget would read` và **giữ lại cái nút**.

### Kết quả đo được của cả bước 3

Trên top 150 finding của một lần chạy M148 → M151 thật:

| | Số dòng |
|---|---|
| Có ít nhất một CL | **150 / 150** |
| Trong đó được một verdict **gọi tên** | **147** |
| Chỉ có manh mối | 3 |
| `exact` | 94 |
| `declares` | 60 |
| `introduced` | 37 |
| `touched` | 7 |
| `moved` | 6 |
| `described` | 2 |
| Tổng số CL được trích dẫn | 206 |

Phiên bản chạy được đầu tiên của chặng này đạt 115 trên 150. Ba lần cải tiến — quét tới dấu đóng, rơi về container, và `introduced` — là chỗ 35 dòng còn lại đến từ.

## Bước 4 — Issue, và lịch sử sửa lỗi đứng sau nó

Một CL Chromium ghi issue của nó trong footer commit message, dạng `Bug:` hoặc `Fixed:`. Hai cái này **được hiển thị tách nhau**, vì đóng một issue và tham chiếu một issue là hai khẳng định khác nhau — đo trên một mẫu thật, Chromium viết **575 dòng `Bug:` so với 34 dòng `Fixed:`**.

Từ issue, ChromiumDiff hỏi ngược lại: *còn CL nào khác cite cùng issue này?* Đó chính là **lịch sử sửa lỗi** của bug đứng sau thay đổi — và nó đến gần như miễn phí, vì nó là một truy vấn thay vì một loạt diff.

`revert_of` và `cherry_pick_of_change` đến sẵn trong cùng response và cũng được in ra: **23 trong 534 CL của một mẫu thật là revert**, và chúng là thứ làm cho lịch sử launch–revert–reland của một flag đọc được mà không phải so tiêu đề bằng mắt.

### Issue chỉ tải khi bạn bấm vào nó

Mỗi CL trên dòng đã mang sẵn footer `Bug:` của nó — thứ này đến **miễn phí** trong kết quả tìm kiếm, nên dòng gọi tên được mọi issue mà không cần hỏi tracker câu nào.

Phần còn lại của issue — tiêu đề, có mở được không, và các CL khác cùng cite nó — chỉ được tải **khi bạn bấm vào chip issue trên một CL cụ thể**. Đó chính là cú bấm nói lên bạn cho rằng CL nào mới là CL đúng. Trước đây một dòng cite sáu issue tiêu mười hai request trước khi người đọc kịp quyết định CL nào đáng quan tâm.

Mỗi issue mở ra trong khối riêng, thụt vào dưới đúng CL của nó, và **bấm cái thứ hai không đóng cái thứ nhất** — người đọc đang *so sánh* hai issue chứ không phải bật qua bật lại. Bấm lại đúng chip đó thì chỉ đóng riêng nó.

Mở file từ đĩa thì không có gì để hỏi, nên chip quay về đúng cái link tracker như cũ.

### Hơn bốn trong mười link issue không mở được

Đo trên 97 issue phân biệt mà top 150 finding của một lần chạy M148 → M151 thật liên kết tới: **44 cái trả HTTP 403** — bị hạn chế cho tài khoản Google, vì chúng nằm trong component security, abuse, hoặc nội bộ.

Một link chết không được đánh dấu đọc ra như một **công cụ hỏng**, chứ không phải như một **cánh cửa đóng**. Nên mọi issue được liên kết đều bị thăm dò một lần và cái bị hạn chế được đánh dấu `RESTRICTED` ngay tại chỗ. Link vẫn **được giữ lại**, vì người đọc báo cáo có thể chính là người mở được nó.

Điều quan trọng cần nói với người triage: **CL vẫn đọc được dù issue không mở.** CL nằm trên Gerrit, chúng công khai, và tiêu đề của chúng mang theo phần lớn nội dung mà issue nói tới.

### Issue mở được thì nói luôn nó nói về cái gì

Phép thăm dò là một GET chứ không phải HEAD, chính vì lý do đó: HEAD không tốn gì hơn và chỉ cho biết cửa mở, trong khi cùng một request đó **cũng mang theo dòng tóm tắt**.

`issues.chromium.org` trả về JSON đánh địa chỉ bằng chỉ số, không có tên trường. Tiêu đề vì vậy được tìm bằng **mốc duy nhất không phải chỉ số** — cái mảng có phần tử thứ hai là số issue — và được đối chiếu với 8 issue thật, **đúng cả 8**.

Trong cùng response còn có đường dẫn component, và nó **cố ý không được hiển thị**: cùng phép duyệt đó cho ra `Blink>AI` cho một vụ hồi quy bộ nhớ trên MacOS. Một trường sai một trên tám thì giá trị của nó là **âm** — nó không làm người đọc thiếu thông tin, nó làm người đọc tin nhầm.

Kết quả cuối, đọc được từ đầu đến cuối:

```text
ViewTransitionElement.border_offset   Vector2d → Vector2dF
  CL 7757059  "VT: Avoid transform rounding in style tracker"
  issue 500417362  "Snapshot positioning pixel rounding error?"
```

## Ba câu hỏi trước khi trả lời "không có CL"

Đây là phần quan trọng nhất về mặt **nhận thức luận**, và nó đáng đọc kể cả với người không quan tâm chi tiết kỹ thuật.

Panel trước đây nói: *"không CL nào chạm file này giữa hai version, nên không có gì để trích dẫn"*. Đó là một khẳng định **về Chromium**, và là khẳng định chặng này không có quyền đưa ra.

**Hai cây source khác nhau, nghĩa là đã có gì đó land.** Không tồn tại thay đổi mà không có CL. Mọi dòng trống là một phát biểu về *cuộc tìm kiếm này*, không phải về Chromium — và diễn đạt nó như một sự vắng mặt sẽ mời người đọc kết luận rằng một declaration tự nó thay đổi, điều không thể xảy ra.

Nên file được hỏi **ba cách** trước khi câu trả lời là "không":

| # | Câu hỏi | Vì sao cần |
|---|---|---|
| 1 | `file:"<path>" branch:main` | Câu hỏi chính, và là nền của mọi thứ ở trên |
| 2 | Cùng file, **bỏ ghim branch** | Merge-back land lên release branch suốt nhiều tuần sau khi branch được cắt, và những commit đó nằm trong cây đang được so. Cận trên của cửa sổ vốn đã chấp nhận các ngày đó — chính `branch:main` là thứ duy nhất che chúng đi |
| 3 | **Commit message của toàn bộ cửa sổ**, không ghim file, không ghim branch | Chỉ tới bước này khi *không gì* chạm file — vì tới lúc đó, câu hỏi về file là câu hỏi sai |

Câu hỏi thứ ba tồn tại vì có bốn cách một declaration đổi mà file **không hề** bị chạm dưới cái tên ta đang cầm: nó được sinh ra từ template; Gerrit ghi nó dưới một path khác; nó bị đổi tên trong một CL chỉ được index theo tên mới; hoặc nó được roll vào từ third-party.

Thứ trả về từ câu hỏi ba là verdict `described` — CL gọi tên identifier, và không diff nào được đọc để khẳng định thêm — và nó được đếm như **một lời giải**, không phải một manh mối. Đúng một request không giới hạn phạm vi, và chỉ dành cho finding mà file của nó không sinh ra ứng viên nào; đó là thứ khiến nó đủ rẻ để làm.

Một dòng được trả lời theo cách đó nói *"found by commit message — nothing touched this file in the window"*, chứ không mượn mẫu số của cuộc tìm theo file — mẫu số đó không hề đếm nó.

Và khi cả ba đều trượt, panel nói ra **kết luận mà người đọc hành động được**, chứ không nói ra một sự vắng mặt:

> This lookup found nothing. Nothing touched this file on any branch in the window, and no commit message in it names this identifier — so the CL that made this change is recorded under something other than the name or the path held here.

Số lần xảy ra được đếm trong summary (`findings_by_message`, `files_found_off_main`), để một cặp version hay gặp chuyện này thì **nhìn ra được** chứ không bị hấp thụ vào im lặng.

## Một dòng giữ cả chuỗi CL, không giữ cái tốt nhất

Một feature flag hiếm khi có một CL. Nó có một câu chuyện: thêm flag, bật mặc định, launch, revert, reland, revert, reland, gỡ bỏ. **40 trong 150 dòng của một lần chạy thật mang nhiều hơn một CL.**

Hai quy tắc từng cắt danh sách đó mà không nói, và chúng sai theo hai hướng ngược nhau:

- **Một hit mạnh xoá sạch mọi `declares` bên cạnh nó**, theo lập luận rằng `exact` làm chúng thừa. Nó không thừa: một CL sửa thân declaration mà không chạm dòng đặt tên là một CL **khác** làm việc **khác**, không phải bản sao yếu hơn của cùng câu trả lời. Quy tắc này vứt đi **40 CL trên 18 finding**.
- **Giới hạn lấy 8 CL mới nhất** — đúng cho một trích dẫn và **ngược hoàn toàn** cho một chuỗi, nơi khởi nguồn nằm ở đầu **cũ**. `NtpComposebox` mất *"[ntp-composebox] Add feature flag"*, tức là CL mà câu chuyện bắt đầu, trong khi giữ lại **năm cái revert** của chính nó.

Ba thay đổi:

- giới hạn là **12**, khớp với giới hạn mà khối issue vốn đã dùng;
- thứ bị cắt được **in ra** — `15 of 19 merged CLs touched this file, newest 12 shown` — thay vì gộp vào số pool;
- một dòng có nhiều hơn một CL đọc theo thứ tự **cũ trước**.

Sau đó `NtpComposebox` đọc trọn câu chuyện xuôi chiều, và số dòng mang cả một chuỗi tăng từ 28 lên **40 trên 150**.

Cần lưu ý: con số 40 là phép đo của **một lần chạy ở một mức ngân sách**, không phải một tính chất của công cụ. `--click-budget` nhỏ hơn thì đọc ít diff hơn và tìm ra ít chuỗi hơn.

### Một dòng đếm một con số ba lần

Cùng chỗ này từng có một lỗi trình bày đáng ghi lại, vì nó là loại lỗi khó thấy nhất — con số nào cũng đúng, chỉ có việc ghép chúng lại là sai. Ba khẳng định khác nhau:

1. bao nhiêu CL chạm file;
2. bao nhiêu trong số đó được một diff buộc vào Fact này;
3. bao nhiêu cái được in ra.

Panel in **cái thứ ba đối chiếu cái thứ nhất, như thể nó là cái thứ hai**. `runtime_enabled_features.json5` hiện `1 of <toàn bộ>` trên một cuộc tìm chỉ mở phần mới nhất; `NtpComposebox` hiện `8 of 19` trên một dòng mà 15 cái khớp và 7 cái bị cắt, không có gì nói rằng danh sách đã bị cắt.

Khối issue nằm ngay dưới một panel đã làm đúng chuyện này ngay từ đầu — *"11 CLs cite it, newest 8 shown"*.

## Một tra cứu tự thuật lại chính nó

Ba thứ có thể làm cho câu trả lời của một dòng **kém chắc chắn hơn**: một request thất bại, một danh sách ứng viên Gerrit trả về ở mức trần trang, và một ngân sách diff đã từ chối file.

Không thứ nào làm dòng đó **sai**, và cả ba làm nó **chưa hoàn tất**. Đó là hai trạng thái rất khác nhau và người đọc phải phân biệt được.

Có ba nguyên tắc ở đây, và cả ba đều đến từ việc sửa một lỗi thật:

- **Cảnh báo nằm phía trên câu trả lời, không nằm trong một nhánh của nó.** Cảnh báo từng được viết vào nhánh trong cùng của panel rỗng — mà đó lại là hình dạng **duy nhất mà một thất bại một phần không thể tạo ra**, vì sàn `touched` luôn đưa manh mối cho bất kỳ dòng nào có ứng viên. Nên ba hình dạng mà một thất bại một phần **thực sự** tạo ra lại là ba hình dạng không nói gì. Một qualifier là thuộc tính **của cuộc tra cứu**, không phải của cách cuộc tra cứu kết thúc.
- **Cuộc tra cứu tự ghi lại, không để người gọi ghi hộ.** Vì lời cảnh báo thuộc về **câu trả lời**, không thuộc về người đi hỏi. Trước đây `serve` đọc bản tóm tắt của cả lần chạy để lấy nó — mà một lời gọi cho *một dòng* thì bản tóm tắt đó không ghi gì cả, nên đúng cái dòng mất request lại là cái dòng không nói gì về việc đó.
- **Request thất bại được ghi kèm file đã mất nó, không chỉ đếm.** Một con số đếm thì chỉ tới được summary; một dòng cần biết **chính nó** đã mất gì.

Một cái tinh vi đáng nêu riêng, vì nó là trường hợp duy nhất mà mất một request làm **đổi kết luận** chứ không chỉ làm mỏng bằng chứng: hai fetch đứng sau một phép đổi tên từng đi ra **nặc danh**, nên thất bại ở một trong hai không đánh dấu dòng nào. Verdict `moved` được cấp từ chính hai fetch đó. Mất chúng thì Fact đọc ra thành **"đã bị xoá ở path cũ"** — đúng cái câu trả lời mà verdict `moved` tồn tại để ngăn — trong khi dòng báo cáo một cuộc tìm đã hoàn tất.

Và cảnh báo mất request phải mang số của **dòng**, không phải của **lần chạy**: một dòng mất hai request mà in ra tổng của cả lần chạy thì nó đang nói với người đọc rằng nó mất mọi thứ cả lần chạy đã mất.

## Vì sao phải chạy một server

Báo cáo là **một file HTML tự chứa**. Đó là lý do nó gửi qua mail được và chạy được trên máy không nối mạng. Đó cũng là giới hạn cứng của nó.

Mở từ đĩa thì trang nằm trên origin `file://`, và `chromium-review.googlesource.com` **không gửi header `Access-Control-Allow-Origin`**. Trình duyệt chặn request trước cả khi nó được gửi đi. Mọi đường vòng đã được thử và đều đóng:

| Cách thử | Kết quả |
|---|---|
| `Origin: null` (trang `file://`) | không có `Access-Control-Allow-Origin` |
| Một origin `https://` thật | cũng không có |
| Preflight `OPTIONS` | HTTP 400 |
| JSONP (`?callback=`) | bị bỏ qua; JSON có tiền tố XSSI trả về nguyên vẹn, nên thẻ `<script>` chỉ nhận được syntax error |
| Dùng gitiles thay Gerrit | không có header, và `+log` theo path cùng `+blame` trả 401 |

Cách giải **không phải là đánh bại quy tắc origin, mà là rời khỏi nó.** Phục vụ trang qua `http://127.0.0.1` thì trang có một origin nói chuyện được với một thứ, và thứ đó là chính process Python này — vốn đã biết cách hỏi Gerrit:

```text
trước:   trình duyệt ──✗──→ chromium-review

serve:   trình duyệt ──✓──→ 127.0.0.1     (cùng origin; quy tắc không áp dụng)
                                │
                                └──✓──→ chromium-review   (Python, không phải trình duyệt)
```

Điểm cần hiểu: **serve qua HTTP không làm quy tắc biến mất**. Cùng trang đó phục vụ qua HTTP vẫn bị chặn y hệt nếu nó tự gọi Gerrit. Thứ thay đổi là **ai đi hỏi**. Quy tắc same-origin tồn tại **bên trong trình duyệt** để bảo vệ cookie của người dùng; `curl` và `urllib` chưa bao giờ chịu nó.

### Trả tiền cho những dòng bạn mở

Việc để một cú click kích hoạt tra cứu đổi mô hình chi phí một cách căn bản, và đây là lý do thiết kế chứ không phải hệ quả phụ.

Hoá đơn được quyết định bởi **file khai báo bận đến đâu**, không phải bởi có bao nhiêu finding: một request cho mỗi cặp `(CL, file)`. Top 150 finding của một lần chạy thật chạm 56 file; top 300 chạm 60 file. Hình dạng đắt nhất là một file bận trả lời đúng một dòng — `extension_features.cc` tiêu 44 request cho một dòng, trong khi `autofill_features.cc` tiêu 8 request mỗi lần cho mười sáu dòng.

| Con số | Giá trị |
|---|---|
| Một báo cáo 3.022 finding, chưa mở dòng nào | **0 request** |
| Một dòng điểm 45, cache lạnh | **5,7 giây** |
| File trung vị, mẫu 183 dòng đủ 16 loại | 8 CL ứng viên |
| Ba file bận nhất | 662 · 500 · 337 CL |
| Trần mặc định mỗi cú click | 600 diff |

Trần 600 được đặt hào phóng có chủ ý. Ngân sách của một lần chạy được rải lên hàng trăm dòng chưa ai hỏi; một cú click là **một dòng có người hỏi**, nên từ chối nó để người đọc không còn chỗ nào đi — bấm lại chỉ nhận đúng lời từ chối đó.

Mọi thứ được cache **vĩnh viễn**, vì một CL đã merge thì không đổi nữa. Dòng thứ hai trong cùng file là tức thì, và dòng cũ mở lại ngày mai cũng vậy.

**Câu trả lời cũ được hỏi lại, không phục vụ lại.** Không tra lại chính là thứ làm cú bấm thứ hai vào một dòng trở nên tức thì — và cái giá của nó là một report sống lâu hơn cái bug nó được sinh ra dưới. Hai lỗi đã biết đều **nhìn thấy được ngay trong dữ liệu đã lưu**, nên không cần cờ hay số phiên bản: một CL không có dấu thời gian submit là CL từng bị sắp theo ngày, và một CL có ngày sau khi bản đích tách nhánh thì không nằm trong cây đó.

**Phép kiểm chạy lúc bạn mở dòng ra.** Một dòng đã có CL thì không hiện nút tra cứu, nên nếu không kiểm ở đây thì không có gì trên trang gọi được server về nó nữa — câu trả lời sai sẽ được phục vụ mãi. Mở dòng là một round trip tới localhost; server trả lại đúng cái nó đang giữ nếu còn tốt, không tốn request Gerrit nào. Dòng **chưa** tra thì không tự hỏi: tra một dòng tốn request thật, và đó là việc của cái nút.

Đo trên một report thật: **16 trong 60 dòng đã tra** đang trích loại thứ hai. `blink.mojom.TokenError.url` — chính ví dụ chủ lực của tài liệu này — đang đứng đầu bằng một CL dọn dẹp land **ba ngày** *sau* khi M151 tách nhánh; sau khi hỏi lại, nó còn 2 CL và đứng đầu bằng CL 7982397 với verdict `introduced`.

Kết quả tra cứu được **ghi ngược lại `report.json`**, ghi nguyên tử qua một file tạm cùng thư mục. Trang được render từ bản báo cáo mà process này đang giữ, chứ không đọc lại từ đĩa, nên reload thấy đúng những gì các cú click đã tìm ra và restart cũng vậy. Một buổi triage không mất vì đóng terminal. `--no-save` để tắt.

## Dùng như thế nào

```bash
python3 -m chromiumdiff run 148.0.7778.217 151.0.7922.138 --out out/M148_to_M151
python3 -m chromiumdiff serve out/M148_to_M151
# → http://127.0.0.1:8787/

# sau khi dừng serve, đưa những gì đã tra vào hai file trên đĩa
python3 -m chromiumdiff report out/M148_to_M151/report.json \
  --format both --out out/M148_to_M151/report
```

Lệnh thứ ba không bỏ được. `serve` ghi kết quả tra cứu vào `report.json` và **chỉ** vào đó; `report.md` với `report.html` trên đĩa vẫn là bản `run` viết ra lúc đầu, tức **không có một link CL nào** dù `report.json` đã đầy. Ai đọc file mà không ngồi cạnh bàn phím sẽ đọc bản cũ.

`--out` cũng không bỏ được: thiếu nó, `report` in ra stdout, tức là đổ cả bản báo cáo ra terminal và để nguyên hai file cũ.

Lệnh `run` không đổi và **không hề chạm mạng Gerrit** — chặng này hoàn toàn nằm ngoài nó. Sau khi `run` xong, nó in ra dòng nhắc `serve`.

| Tuỳ chọn | Mặc định | Ý nghĩa |
|---|---|---|
| `--port` | 8787 | Cổng localhost |
| `--click-budget N` | 600 | Đọc tối đa N diff cho mỗi dòng được mở (0 = không trần) |
| `--no-save` | tắt | Không ghi kết quả ngược vào `report.json` |
| `--cache DIR` | `.chromiumdiff-cache` | Thư mục cache dùng chung với `run` |

Server chỉ bind vào `127.0.0.1`, chỉ phục vụ đúng ba file của báo cáo, và xử lý một request tra cứu tại một thời điểm (công việc **bên trong** một request vẫn chạy song song, và đó mới là chỗ tốn thời gian).

Lệnh `check` giờ cũng thăm dò `chromium-review`, vì đó là host duy nhất mà một cú tra cứu cần và cả `run` lẫn `snapshot` đều không chạm — nếu không, một máy pass `check` rồi không trả lời được cú click sẽ không hề được cảnh báo trước.

### Cùng một file `report.html`, hai chế độ

Trang gọi `/api/ping` **đúng một lần lúc load** và chỉ bật đường live nếu có ai trả lời. Cùng file đó mở thẳng từ đĩa, hoặc gửi cho đồng nghiệp, hoặc mở trên máy air-gapped, hành xử **y hệt như trước**: bảng vẫn lọc, vẫn sắp xếp, vẫn bung dòng. Chỉ có nút tra cứu là không xuất hiện.

Đây cũng là cái bẫy hay gặp nhất với người dùng mới, kể cả AI agent: mở `report.html` bằng cách bấm đúp vào file, thấy tra cứu không hoạt động, rồi báo cáo rằng tính năng bị hỏng. Nó không hỏng — nó đang ở đúng chế độ mà origin `file://` cho phép.

## Một CL nối các dòng lại với nhau

Đây là thứ mà việc tra CL cho không, ngoài câu trả lời cho từng dòng.

Một thay đổi của Chromium thường land qua **nhiều khai báo cùng lúc**, và report hiện ra thành nhiều dòng rời. Người đọc mở từng dòng, đọc từng lần, rồi mới nhận ra đó là **một** chuyện.

```
CL 7957918  "[sub apps] change web api"
   mojo_method:blink.mojom.SubAppsService.Add        80 điểm
   mojo_method:blink.mojom.SubAppsService.List       80
   idl_interface:SubAppsAddParams                    70
   idl_member:SubAppsAddParams.installURL            70
   ...  7 dòng, 3 loại fact
```

### Vì sao luật cũ không thấy được

`cluster.py` vốn đã gom nhóm, nhưng chỉ theo **liên kết Chromium tự khai báo trong source**: một `webui_gate` nhắc tên một `base_feature`, một `feature_param` nhắc feature cha, một control nhắc trang nó thuộc về. Comment trong code nói thẳng nguyên tắc — *chỉ nối theo liên kết Chromium thật sự khai báo; suy từ tên giống nhau là đoán mò*.

Nguyên tắc đó **đúng**, nhưng nó giới hạn việc gom vào bề mặt WebUI. Giữa một file `.mojom` và một file `.idl`, **Chromium không viết ra liên kết nào cả**.

Hậu quả đo được trên M148 → M151: luật cũ gom được 183 trong 3.022 dòng, mà **143 nhóm trong đó là feature + param của nó** — tức là đáy bảng xếp hạng. Trong 150 dòng điểm cao nhất, nó với tới **6**.

### CL là cùng loại bằng chứng, ghi ở chỗ khác

Tác giả viết **một** thay đổi, nó land qua nhiều khai báo, và **số CL là chính Chromium nói vậy**. Không phải đoán theo tên giống nhau — đúng chuẩn mà luật cũ tự đặt ra cho mình, chỉ là ở một nguồn nó chưa được nối vào.

| | Luật cũ | Thêm luật CL |
|---|---:|---:|
| Trong 150 dòng điểm cao nhất | 6 | **84** |
| Toàn report | 183 | **261** |

Và nó quan trọng nhất **đúng chỗ người đọc đang nhìn**: trong **20 dòng đầu bảng, 9 dòng** là bản kể lại của một thay đổi đã có trên màn hình. Một CL đưa vào một mixin chiếm **14 dòng**.

### Ba ràng buộc, mỗi cái có lý do đo được

- **Chỉ CL, không dùng issue.** Một issue trong lần chạy này mang 24 CL trải khắp các bề mặt không liên quan — gom theo issue sẽ ra một cụm không ai đọc nổi.
- **Chỉ verdict gọi tên fact**, không dùng `crowded`/`touched`. Chúng gọi tên **file**; riêng `about_flags.cc` sẽ nhét 500 finding vào một cụm.
- **Trần 20 dòng một nhóm** — và đây là *hàng rào phòng xa, không phải số đo*. Dữ liệu không cần nó: nhóm chạy 2–7 dòng và đúng một nhóm 14. Thứ tạo nhóm sai to nhất — một CL reformat khớp hàng chục khai báo — đã bị chặn ở tầng trên, vì Gerrit đánh dấu reformat là `common: true` và tool không tính nó là dòng đã đổi.

### Nó chạy lúc nào

**Lúc bạn bấm tra một dòng.** `run` không hỏi Gerrit câu nào, nên trên một report chưa tra gì thì luật CL im lặng hoàn toàn và bốn luật cũ là tất cả. Nhóm **lớn dần** theo lúc bạn khám phá:

```
tra dòng 1  → (chưa có nhóm)
tra dòng 2  → 2 findings in all
tra dòng 3  → 3 findings in all. The heaviest scores 80, read that one first.
```

Nó **không lấy gì thêm** — chỉ đọc CL mà dòng đó đã có. Chi phí 2 ms cho cả 3.022 dòng.

### Nhìn thấy ở đâu

- **Bảng HTML** — mở một dòng ra, panel nói ngay trên phần bằng chứng: *"Part of a larger change — [sub apps] change web api, 3 findings in all. The heaviest of them scores 80, so read that one first."* Nhãn lấy từ **tiêu đề CL chung**, vì tác giả đã đặt tên sẵn.
- **`report.md`** — mục *"Related changes, grouped"* ở đầu, **và** một dòng trong mục của từng finding. Dòng thứ hai mới quan trọng: bản Markdown là bản đi vào ticket, mà người ta paste một mục chứ không paste cái bảng.

Cả hai chỗ trên chỉ có sau khi render lại: panel HTML là do process đang chạy dựng nên nên thấy ngay, còn hai file trên đĩa thì phải chạy lệnh `report` ở mục trên.

Bảng **không gộp dòng, không giấu dòng, không đổi thứ tự** — mỗi finding vẫn một dòng, vẫn sắp theo điểm. Gom nhóm chỉ thêm một câu vào panel.

## Đọc panel và các bộ lọc

### Bộ lọc thứ năm trong bảng HTML

Một dòng có CL và một dòng không có CL **trông giống hệt nhau** trong bảng. Vì vậy bảng có thêm một bộ lọc, và năm trạng thái của nó **tách bạch** — gộp chúng lại chính là sai lầm mà cả chặng này tồn tại để tránh:

| Trạng thái | Nghĩa |
|---|---|
| **Has a CL** | tìm được thứ gì đó gọi tên Fact này |
| **A diff proved it** | mọi CL hiển thị đều được một dòng đã đổi buộc vào identifier (`introduced` hoặc `exact`) |
| **Leads only, nothing names it** | có liệt kê CL, không cái nào gọi tên Fact này |
| **Scanned, nothing found** | diff đã được đọc, không cái nào khớp |
| **Not looked up** | chưa ai nhìn |

Một vạch 3px trên ô điểm nói cùng điều đó trong khi cuộn. Bộ lọc này **ẩn** trên một báo cáo chưa tra cứu gì và tự hiện ra ngay khi server trả lời hoặc lượt tra cứu đầu tiên land — nó không chiếm chỗ trên một báo cáo mà nó chưa có gì để nói.

Mỗi CL trên dòng **gọi tên được issue của nó** — footer `Bug:` đến miễn phí trong kết quả tìm kiếm — nên một flag từng launch, revert và reland hiện đủ cả ba issue nó cite, chứ không phải một cái tình cờ sắp cao nhất. Còn *lịch sử* của một issue thì chỉ tải khi bạn bấm vào chip của đúng CL bạn tin, như mục trên đã nói.

### Trong `report.md`

Bản Markdown là bản **đi vào ticket**, và nó không có màu badge, không có row state, không có panel để đặt lời cảnh báo. Dòng người đọc copy ra là **toàn bộ thứ đi xa**.

Vì vậy ở đây chính **tiêu đề** thay đổi theo bản chất của câu trả lời:

| Tiêu đề trong `report.md` | Khi nào |
|---|---|
| `Why it changed (…)` | có ít nhất một verdict gọi tên Fact |
| `How it got here, oldest first (…)` | toàn bộ là `crowded` — đây là lịch sử declaration |
| `Leads only, no CL names this (…)` | toàn bộ là manh mối |

Mẫu số, số đã đọc và số bị cắt đều nằm trong dấu ngoặc, vì chúng là **một phần của trích dẫn**, không phải trang trí.

## Sáu cách chặng này từng nói sai, và đã sửa

Mỗi cái đều tạo ra một **câu trả lời sai đầy tự tin** thay vì một lỗi — loại khuyết tật duy nhất thực sự quan trọng ở đây, vì nó không để lại dấu vết. Bốn cái đầu được tìm ra bằng cách lấy một finding trả về rỗng rồi đi săn CL của nó bằng tay.

| Lỗi | Nó gây ra cái gì |
|---|---|
| **Không xử lý block `{"skip": N}`** | Gerrit đáp một request diff cho path **cũ** của file đã đổi tên bằng `change_type: MODIFIED` và cả file gói trong một block `skip` — không 404, không dấu hiệu rename. Parser thấy một file rỗng, nên sáu IDL member bị xoá đọc ra thành "không quy được trách nhiệm", trong khi một CL giải thích rõ cả sáu |
| **Đếm reindent thành edit** | Block gắn `{"a": […], "b": […], "common": true}` là Gerrit nói *các dòng này cùng nội dung, chỉ khác bên trong dòng*. Đếm thành thay đổi thì một CL reformat file trở thành `exact` match cho **mọi** declaration trong file đó. 49 block như vậy trong mẫu 2.329 diff |
| **`diffs_read` chỉ ghi trên dòng đã có CL** | Một dòng chưa ai nhìn trông y hệt một dòng đã quét và thật sự không khớp gì. Giờ nó được ghi trên **mọi** dòng được hỏi tới, và panel nói rõ dòng nào là dòng nào |
| **Mẫu số đếm một path, hit đến từ hai** | Dòng có declaration ở hai file in ra `3 of 2 merged CLs`. 60 trong 3.022 finding được khai báo ở hai file; cả hai được tìm, cả hai đóng góp, và mỗi CL giờ nói rõ nó được tìm thấy ở file nào |
| **Key có qualifier bị coi là văn bản** | Chính là ca `TokenError.url`. Container giờ được giữ ở **ô riêng** chứ không trộn vào tập token — vì một dòng đã đổi có nhắc `TokenError` **không phải** một dòng đã đổi khai báo `TokenError.url`; trộn vào thì nó đòi `exact` trên hai CL chỉ dọn dẹp struct, và đẩy văng CL đúng ra ngoài |
| **Server giữ bản sao riêng của danh sách trường** | Khi `issue` đổi thành `issues` ở phía renderer, server vẫn lọc theo `issue`, nên mọi lượt tra cứu trả về các CL và **âm thầm bỏ mất toàn bộ lịch sử issue**. Giờ chỉ còn một danh sách, nằm ở renderer |

Ngoài ra, hai thứ về mạng được xử lý riêng vì chúng có cùng một hậu quả:

- **HTTP 429 có thang lùi riêng** (5 giây, 20 giây, 60 giây). Thang lùi chung của công cụ là 1,5 / 3 / 6 giây — quá ngắn cho một rate limiter đếm theo phút. Một 429 bị retry quá nhanh trở thành **một fetch âm thầm trả về không có gì**, và "không có gì" ở điểm sử dụng thì **không phân biệt được** với "CL này không nhắc identifier".
- **Fetch thất bại được đếm và công bố, không bao giờ bị hấp thụ.** Biến một cú vấp mạng thành một câu *"không tìm thấy CL"* đầy tự tin là điều duy nhất chặng này không được phép làm.

## Có thể tin tới đâu, và không nên tin điều gì

### Những điểm khiến kết quả kiểm toán được

- Mỗi CL mang một verdict nói rõ **bằng chứng thuộc loại nào**, và các verdict không bị trộn thành điểm số.
- Ranh giới giữa "trích dẫn" và "manh mối" là một hằng số trong code, không phải một quy ước về màu sắc.
- Mẫu số luôn đi kèm tử số: `1 of 62` kiểm tra được, `1` thì không.
- Ba con số — chạm file, khớp Fact, được in ra — được giữ tách nhau và in tách nhau.
- Một danh sách bị cắt **nói rằng nó bị cắt**.
- Một cuộc tìm mất request, gặp trần trang, hoặc bị ngân sách từ chối đều nói ra điều đó, ở phía trên câu trả lời.
- Mọi CL đều mở được trên Gerrit bằng số của nó; người đọc kiểm tra lại được toàn bộ chuỗi lập luận.
- Kết quả tra cứu được lưu vào `report.json`, nên hai người chạy lại cùng báo cáo nhìn thấy cùng một thứ.

### Những điều một CL không chứng minh

- **Rằng CL đó gây ra finding này.** `serve` xác lập rằng một CL đã sửa một dòng mang identifier, bên trong cửa sổ — **không phải** rằng phép sửa đó chính là phép sửa mà finding nói tới. Một file bị chạm bởi một phép đổi tên, một phép reformat và thay đổi thật sẽ báo cả ba là `exact`. Người đọc vẫn phải mở CL ra.
- **Rằng danh sách CL là đầy đủ.** Trần 500 dòng của Gerrit, ngân sách diff, và giới hạn 12 CL mỗi dòng đều cắt bớt — cả ba đều nói ra, nhưng chúng vẫn cắt.
- **Rằng `crowded` hay `touched` là nguyên nhân.** Chúng không gọi tên Fact. Đừng bao giờ trích chúng như nguyên nhân; hãy nói đúng chúng là gì.
- **Rằng một dòng trống nghĩa là không có CL.** Nó nghĩa là ba câu hỏi đều trượt, và CL được ghi dưới một cái tên hoặc một path khác với cái báo cáo đang cầm.
- **Rằng issue mở được thì nội dung của nó đã được đọc.** Công cụ chỉ lấy tiêu đề, và chỉ tiêu đề.

### Ba câu nên dùng khi viết kết luận

| Tình huống | Câu nên viết |
|---|---|
| Có `introduced` hoặc `exact`, một CL | *"CL 7885356 đã bật flag này mặc định; đây là 1 trong 62 CL chạm file, và là CL duy nhất có diff nhắc tới tên flag."* |
| Chỉ có manh mối | *"Chưa có CL nào được buộc vào khai báo này. 11 CL đã chạm file, liệt kê để tham khảo."* |
| Cả ba câu hỏi đều trượt | *"Không tra được CL: không gì chạm file này trên bất kỳ branch nào trong cửa sổ, và không commit message nào gọi tên nó. Thay đổi này có thể đến từ file sinh tự động hoặc một bản roll third-party."* |
