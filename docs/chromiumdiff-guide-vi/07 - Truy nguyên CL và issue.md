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

Bước thứ ba là bước quyết định: ba bước còn lại đều rẻ và hiển nhiên, còn bước ba biến một danh sách dài thành một câu trả lời.

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

Đưa cho người đọc 500 CL cho một cái flag còn tệ hơn không đưa gì. Vì vậy file **chỉ sinh ra ứng viên**, và ứng viên sau đó bị lọc bằng câu hỏi: *diff của chính CL đó, trên chính file đó, có nhắc tới identifier này không?*

Với `AndroidCaptureKeyEvents`: 62 ứng viên, sống sót đúng một.

Panel in cả mẫu số cùng với CL, vì `1 of 62` mới là thứ làm cho con số 1 có ý nghĩa. Một CL trong 62 là một trích dẫn; một CL trong 1 có thể chỉ vì gần như không ai chạm vào file đó.

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

Nếu lấy ngày tag làm cận trên, các CL như vậy sẽ lọt vào kết quả. Đo trên 105 row đã resolve: **38 trong 160 CL được trích dẫn land sau khi M151 tách nhánh, 11 row xếp một CL như vậy lên đầu, và 9 row chỉ trích toàn CL như vậy**. Năm flag Autofill khác nhau bị gán cho cùng một CL dọn dẹp mà M151 không hề chứa. Lấy điểm nhánh làm cận trên thì các trường hợp này không còn, và pool ứng viên giảm khoảng một nửa.

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

Nó không bao giờ viết chuỗi `blink.mojom.TokenError.url`, còn `url` thì quá ngắn để tìm. Nếu chỉ tìm theo tên, công cụ sẽ đọc 10 diff để tìm một chuỗi **không thể xuất hiện trong diff nào**, rồi báo *"không CL nào sửa dòng mang identifier này"*. Câu đó đúng về mặt kỹ thuật nhưng dễ khiến người đọc hiểu sai.

Câu trả lời nằm sẵn trong báo cáo. Một `Change` không chỉ gọi tên declaration — nó ghi lại **hai trạng thái** của declaration đó:

```json
{"type": ["array<url.mojom.Url>", "array<network.mojom.LinkHeader>"]}
```

Và CL đã làm ra thay đổi đó, theo định nghĩa, là CL có diff **thêm vào** một dòng chứa `array<network.mojom.LinkHeader>`, nằm bên trong declaration đó — hoặc **xoá đi** dòng chứa `array<url.mojom.Url>`. Cả hai phía đều tính, vì cả hai đều *là* thay đổi đang diễn ra: một phép đổi tên làm trong một CL thì thêm và xoá cùng lúc, làm trong hai CL thì không. `blink.mojom.AIManagerCreateClientError` đi từ `kUnsupportedPerformancePreference` sang `kIncompatiblePreferenceOptions` qua **hai CL cách nhau hai ngày**, và CL đầu chỉ xoá tên cũ — không dòng nào ở đâu mang giá trị cuối cho tới CL thứ hai. Chỉ hỏi về dòng thêm thì CL đầu bị coi là không liên quan, trong khi nó có liên quan. Mọi verdict khác hỏi *"CL này có chạm vào thứ đó không"* — câu mà bất kỳ CL nào reformat file cũng thoả mãn. `introduced` hỏi *"CL này có đặt giá trị mới vào đó không"*.

Ba điều kiện làm cho nó không sinh ra kết quả rác:

- **Chỉ tìm phần khác nhau giữa hai trạng thái.** Một giá trị có ở cả hai phía thì không hề đổi, và nó sẽ khớp với mọi CL từng chạm declaration đó vì bất cứ lý do gì.
- **Chỉ tìm thứ trông giống code.** Phải có chữ hoa ở giữa, dấu gạch dưới, dấu chấm, hoặc đơn giản là dài. `kPreinstalledExtensions`, `IS_ANDROID`, `array<network.mojom.LinkHeader>` nhận diện được một thay đổi; `enabled`, `stable`, `109` xuất hiện trong mọi declaration khác của cùng file và không nhận diện gì.
- **So với văn bản của phía kia, không phải tập token của nó.** `Vector2d` sẽ đọc ra thành "đã mất đi" khi type đổi thành `Vector2dF`, tức là biến chính CL làm ra thay đổi thành bằng chứng cho điều ngược lại.

Đo trên top 150 finding của một lần chạy M148 → M151 thật: **37 CL đạt `introduced`, trải trên 33 dòng**, và **29 trong 33 dòng đó quy về đúng một CL**.

Với verdict này, `TokenError.url` được gán cho CL 7982397, *"[FedCM] Modernize TokenError::url from string to url.mojom.Url"* — dù **không một CL nào trong 10 ứng viên mang cái tên đó**.

### `declares` — quét tới dấu đóng của declaration

Một Mojo method mọc thêm tham số thì dòng mang **tên** nó không hề đổi; phép sửa nằm ở phần thân bên dưới. Nếu chỉ tìm dòng mang tên, cả lớp finding này trả về rỗng.

Nếu chỉ quét một số dòng cố định quanh dòng tên, công cụ không tìm được phép sửa này một cách ổn định:

| Cách quét | Kết quả |
|---|---|
| Đối xứng, rộng 25 dòng | Trên một file toàn declaration, mọi phép sửa đều gần mọi declaration: `AIManager.CreateLanguageModel` kéo về **4 CL không liên quan**, `DevToolsSession.DispatchProtocolCommand` kéo **5** |
| Chỉ tiến, rộng 3 dòng | Hai ca trên còn **đúng một CL**, và là CL đúng; nhưng một danh sách tham số dài không nằm gọn trong ba dòng, nên `OnScriptLoadStarted` khi mọc tham số thứ bảy **không khớp gì** |

Vì vậy công cụ không quét theo số dòng cố định mà quét tới dấu đóng của **chính declaration** đó:

| Dạng khai báo | Vùng quét |
|---|---|
| `struct Bar {` | tới `}` khớp với nó |
| `Foo(` | tới `);` đóng danh sách tham số |
| `Type name;` | đúng một dòng |
| không có gì đóng cả | block **trong cùng bao quanh** cái tên |

Trường hợp cuối là `runtime_enabled_features.json5`: nó đặt tên feature bên trong một record `{ … },` và không có gì phía sau kết thúc bằng `;`. Riêng quy tắc đó chọn ra **1 trong 337 CL** chạm file đó, và đó là CL 7895296, *"Return empty styles for getComputedStyle() outside flat tree"*.

Vùng quét bị chặn ở 60 dòng, để một file mà scanner không hiểu cú pháp không thể làm bước này thành bậc hai. Một declaration dài hơn thế thì cũng không phải thứ quy trách nhiệm được.

Trong lúc dò xem vùng quét kết thúc ở đâu, bản quét tiến **không tính những thay đổi mà nó đi qua**. Nếu trả `True` ngay khi gặp một thay đổi, phép sửa ở *record kế tiếp* sẽ bị tính nhầm cho record đang xét.

### Hai verdict yếu — để một dòng luôn có câu trả lời

Con số "150 trên 150 dòng đều có CL" chỉ là kết quả đo trên **một phần của một lần chạy**, không phải đặc tính của công cụ. Có năm trường hợp một dòng không có verdict nào gọi tên Fact:

1. tên ngắn dưới bốn ký tự thì không tìm được, nên tập token rỗng và vòng lặp diff bỏ qua finding;
2. file bị ngân sách diff từ chối thì chỉ còn giữ lại phần mô tả;
3. có hơn bốn CL cùng sửa một declaration, nên không CL nào chỉ rõ được declaration đó;
4. diff đã đọc nhưng không khớp gì;
5. Fact có tên do công cụ tự ghép (ví dụ `blink.mojom.TokenError.url`) phải tìm theo container của nó, và container cũng có thể không khớp.

Ở bốn trong năm trường hợp này, công cụ đã có sẵn danh sách CL ứng viên. `crowded` và `touched` là hai cách hiển thị danh sách đó.

Đây là một đánh đổi. 11 CL cùng sửa `ai_manager.mojom` nhưng không CL nào chỉ rõ `AIManager.CreateLanguageModel`, nên không CL nào được trích với verdict `declares`: đưa ra bốn câu trả lời sai mà trông chắc chắn còn tệ hơn không đưa gì. Nhưng hiển thị 11 CL đó dưới dạng `crowded`, kèm một câu giải thích chúng là gì, vẫn có ích cho người đọc hơn là để trống, **miễn là không có gì khiến chúng trông giống một trích dẫn**.

Có **ba lớp** giữ cho manh mối không bị nhầm thành trích dẫn:

- dòng có **state riêng** (`weak`), và bộ lọc "Has a CL" **loại nó ra** — con số "đã hiểu được bao nhiêu" không thể bị thổi phồng bởi những dòng chỉ liệt kê review;
- badge **màu xám**, không mượn màu của verdict thật;
- danh sách in dưới một **câu chữ** nói rõ đây là manh mối, không phải trích dẫn.

Hai verdict yếu **không dùng chung câu đó**, vì chúng không phải cùng một khẳng định:

| | `touched` | `crowded` |
|---|---|---|
| Nói gì | các CL này chạm file, không gì buộc chúng vào identifier | mọi CL đã sửa **chính declaration này** |
| Là gì | manh mối | **lịch sử** của declaration đó |
| Trình bày | mới nhất trước, tối đa 3 | **cũ trước**, tiêu đề *"How it got here"* |

`touched` đọc ứng viên từ **danh sách tìm kiếm** chứ không từ diff, và đó chính là ý nghĩa của nó: một file không sinh ra verdict nào khác là file chưa có diff nào được đọc.

Có một trường hợp cần tách riêng: **dòng bị ngân sách diff từ chối không phải là dòng đã được tìm.** Diff của dòng đó chưa được đọc, nên các verdict gọi tên Fact chưa hề được thử. Khi dòng đó chỉ có manh mối `touched`, panel ghi thêm `Nothing here was read — 147 CLs touched this file, more than the run's diff budget would open` và **vẫn hiện nút tra cứu**, vì dòng này vẫn có thể được trả lời. Không có ghi chú đó, dòng này sẽ trông như đã được tìm hết.

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

## Bước 4 — Issue, và lịch sử sửa lỗi đứng sau nó

Một CL Chromium ghi issue của nó trong footer commit message, dạng `Bug:` hoặc `Fixed:`. Hai cái này **được hiển thị tách nhau**, vì đóng một issue và tham chiếu một issue là hai khẳng định khác nhau — đo trên một mẫu thật, Chromium viết **575 dòng `Bug:` so với 34 dòng `Fixed:`**.

Từ issue, ChromiumDiff hỏi ngược lại: *còn CL nào khác cite cùng issue này?* Đó chính là **lịch sử sửa lỗi** của bug đứng sau thay đổi — và nó đến gần như miễn phí, vì nó là một truy vấn thay vì một loạt diff.

`revert_of` và `cherry_pick_of_change` đến sẵn trong cùng response và cũng được in ra: **23 trong 534 CL của một mẫu thật là revert**, và chúng là thứ làm cho lịch sử launch–revert–reland của một flag đọc được mà không phải so tiêu đề bằng mắt.

### Issue chỉ tải khi bạn bấm vào nó

Mỗi CL trên dòng đã mang sẵn footer `Bug:` của nó — thứ này đến **miễn phí** trong kết quả tìm kiếm, nên dòng gọi tên được mọi issue mà không cần hỏi tracker câu nào.

Phần còn lại của issue — tiêu đề, có mở được không, và các CL khác cùng cite nó — chỉ được tải **khi bạn bấm vào chip issue trên một CL cụ thể**. Người đọc chỉ bấm vào issue của CL mà họ cho là đúng, nên chỉ issue đó cần được tải.

Mỗi issue mở ra trong khối riêng, thụt vào dưới đúng CL của nó, và **bấm cái thứ hai không đóng cái thứ nhất** — người đọc đang *so sánh* hai issue chứ không phải bật qua bật lại. Bấm lại đúng chip đó thì chỉ đóng riêng nó.

Khi mở file từ đĩa, chip là link tracker thông thường.

### Gần một nửa link issue không mở được

Đo trên 97 issue phân biệt mà top 150 finding của một lần chạy M148 → M151 liên kết tới: **44 cái trả HTTP 403** — bị hạn chế cho tài khoản Google, vì chúng nằm trong component security, abuse, hoặc nội bộ.

Một link chết không được đánh dấu sẽ bị đọc thành **công cụ hỏng**, thay vì thành một issue bị hạn chế. Nên mọi issue được liên kết đều bị thăm dò một lần và cái bị hạn chế được đánh dấu `RESTRICTED` ngay tại chỗ. Link vẫn **được giữ lại**, vì người đọc báo cáo có thể có quyền truy cập.

Điều quan trọng cần nói với người triage: **CL vẫn đọc được dù issue không mở.** CL nằm trên Gerrit, chúng công khai, và tiêu đề của chúng mang theo phần lớn nội dung mà issue nói tới.

### Issue mở được thì nói luôn nó nói về cái gì

Phép thăm dò là một GET chứ không phải HEAD, vì cùng một request **trả về cả dòng tóm tắt**.

`issues.chromium.org` trả về JSON đánh địa chỉ bằng chỉ số, không có tên trường. Tiêu đề vì vậy được tìm bằng **mốc duy nhất không phải chỉ số** — cái mảng có phần tử thứ hai là số issue — và được đối chiếu với 8 issue thật, **đúng cả 8**.

Response còn chứa đường dẫn component, nhưng công cụ **không hiển thị** trường này: cùng cách đọc đó trả về `Blink>AI` cho một lỗi hồi quy bộ nhớ trên MacOS, tức là sai ở một trong tám issue đã kiểm tra.

Kết quả cuối, đọc được từ đầu đến cuối:

```text
ViewTransitionElement.border_offset   Vector2d → Vector2dF
  CL 7757059  "VT: Avoid transform rounding in style tracker"
  issue 500417362  "Snapshot positioning pixel rounding error?"
```

## Ba câu hỏi trước khi trả lời "không có CL"

Phần này quy định panel được phép kết luận gì khi không tìm thấy CL.

Panel không nói *"không CL nào chạm file này giữa hai version, nên không có gì để trích dẫn"*: đó là một khẳng định **về Chromium**, và bước tra cứu không có căn cứ để đưa ra khẳng định đó.

**Hai cây source khác nhau, nghĩa là đã có gì đó land.** Không tồn tại thay đổi mà không có CL. Mọi dòng trống là một phát biểu về *cuộc tìm kiếm này*, không phải về Chromium — và diễn đạt nó như một sự vắng mặt sẽ khiến người đọc kết luận rằng một declaration tự nó thay đổi, điều không thể xảy ra.

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

Số lần xảy ra được đếm trong summary (`findings_by_message`, `files_found_off_main`), để một cặp version hay gặp trường hợp này thì **nhìn ra được**.

## Một dòng giữ cả chuỗi CL, không giữ cái tốt nhất

Một feature flag hiếm khi chỉ có một CL, mà thường có cả một chuỗi: thêm flag, bật mặc định, launch, revert, reland, revert, reland, gỡ bỏ. **40 trong 150 dòng của một lần chạy thật mang nhiều hơn một CL.**

Hai quy tắc giúp giữ lại chuỗi đó:

- **Khi có hit mạnh, các CL `declares` đi kèm vẫn được giữ.** Một CL sửa phần thân declaration mà không chạm dòng chứa tên là một CL **khác**, làm một việc **khác**, không phải phiên bản yếu hơn của cùng một câu trả lời. Giới hạn của `declares` vẫn áp dụng: nếu có hơn bốn CL `declares`, không CL nào trong số đó chỉ rõ được declaration.
- **Danh sách giữ tối đa 12 CL và hiển thị CL cũ trước.** 12 CL được chọn theo verdict mạnh trước, rồi tới CL mới hơn. Khi hiển thị, CL cũ nhất đứng đầu, vì trong một chuỗi, CL đầu tiên là điểm khởi đầu. Giới hạn 12 giống giới hạn của khối issue, và số CL bị cắt được **in ra** — `15 of 19 merged CLs touched this file, newest 12 shown` — chứ không gộp vào con số pool.

Cần lưu ý: con số 40 là phép đo của **một lần chạy ở một mức ngân sách**, không phải một tính chất của công cụ. `--click-budget` nhỏ hơn thì đọc ít diff hơn và tìm ra ít chuỗi hơn.

### Ba con số trên một dòng

Panel hiển thị riêng ba con số khác nhau:

1. bao nhiêu CL chạm file;
2. bao nhiêu trong số đó được một diff buộc vào Fact này;
3. bao nhiêu CL được in ra.

Khi số CL khớp nhiều hơn số CL được in, panel ghi rõ là danh sách đã bị cắt, giống cách khối issue ghi: *"11 CLs cite it, newest 8 shown"*.

## Một tra cứu tự thuật lại chính nó

Ba thứ có thể làm cho câu trả lời của một dòng **kém chắc chắn hơn**: một request thất bại, một danh sách ứng viên Gerrit trả về ở mức trần trang, và một ngân sách diff đã từ chối file.

Không thứ nào làm dòng đó **sai**, và cả ba làm nó **chưa hoàn tất**. Đó là hai trạng thái rất khác nhau và người đọc phải phân biệt được.

Có ba nguyên tắc:

- **Cảnh báo luôn nằm phía trên câu trả lời**, dù panel ở dạng nào. Cảnh báo là thông tin **về lượt tra cứu**, không phụ thuộc vào việc lượt tra cứu kết thúc ra sao.
- **Lượt tra cứu tự ghi cảnh báo của mình**, không để nơi gọi ghi hộ, vì cảnh báo là một phần của **câu trả lời**: bản tóm tắt của lần chạy không có thông tin gì về lượt tra một dòng.
- **Request thất bại được ghi kèm file đã mất nó, không chỉ đếm.** Một con số đếm thì chỉ tới được summary; một dòng cần biết **chính nó** đã mất gì.

Có một trường hợp cần nêu riêng, vì ở đó mất request làm **thay đổi kết luận**, không chỉ làm bằng chứng yếu đi: verdict `moved` dựa vào các fetch lần theo một phép đổi tên file. Nếu mất các fetch này, Fact sẽ bị hiểu thành **"đã bị xoá ở path cũ"**. Vì vậy các fetch này được ghi theo path mà dòng đang lần theo, và khi chúng thất bại, dòng đó được đánh dấu.

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

Cách giải là **đổi bên đi hỏi**, chứ không tìm cách vượt qua quy tắc origin. Phục vụ trang qua `http://127.0.0.1` thì trang có một origin nói chuyện được với một thứ, và thứ đó là chính process Python này — vốn đã biết cách hỏi Gerrit:

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
| Một báo cáo chưa mở dòng nào | **0 request** |
| Một dòng điểm 45, cache lạnh | **5,7 giây** |
| File trung vị, mẫu 183 dòng đủ 16 loại | 8 CL ứng viên |
| Ba file bận nhất | 662 · 500 · 337 CL |
| Trần mặc định mỗi cú click | 600 diff |

Trần 600 được đặt rộng có chủ ý. Ngân sách của một lần chạy được rải lên hàng trăm dòng chưa ai hỏi; một cú click là **một dòng có người hỏi**, nên từ chối nó sẽ khiến người đọc không còn cách nào khác: bấm lại cũng chỉ nhận đúng lời từ chối đó.

Mọi thứ được cache **vĩnh viễn**, vì một CL đã merge thì không đổi nữa. Dòng thứ hai trong cùng file là tức thì, và dòng cũ mở lại ngày mai cũng vậy.

**Có ba trường hợp câu trả lời đã lưu bị tra lại thay vì dùng lại.** Nhờ lưu câu trả lời, lần bấm thứ hai vào một dòng có kết quả ngay; vì vậy việc kiểm tra dựa hoàn toàn vào dữ liệu đã lưu, không cần cờ hay số phiên bản. Ba trường hợp đó là: lượt tra trước đã mất request; có CL không có thời điểm submit, nên danh sách chỉ được sắp theo ngày; hoặc có CL mang ngày sau thời điểm bản đích tách nhánh, tức là CL đó không nằm trong cây đang so.

**Phép kiểm chạy lúc bạn mở dòng ra.** Một dòng đã có CL thì không hiện nút tra cứu, nên nếu không kiểm ở đây thì không có gì trên trang gọi được server về nó nữa — câu trả lời sai sẽ được phục vụ mãi. Mở dòng là một round trip tới localhost; server trả lại đúng cái nó đang giữ nếu còn tốt, không tốn request Gerrit nào. Dòng **chưa** tra thì không tự hỏi: tra một dòng tốn request thật, và đó là việc của cái nút.

Đo trên một report thật: **16 trong 60 dòng đã tra** có trích một CL land sau khi M151 tách nhánh. Sau khi tra lại, `blink.mojom.TokenError.url` còn 2 CL, đứng đầu là CL 7982397 với verdict `introduced`.

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

Lệnh `check` cũng thăm dò `chromium-review`, vì đó là host duy nhất mà một cú tra cứu cần và cả `run` lẫn `snapshot` đều không chạm — nếu không, một máy pass `check` rồi không trả lời được cú click sẽ không hề được cảnh báo trước.

### Cùng một file `report.html`, hai chế độ

Trang gọi `/api/ping` **đúng một lần lúc load** và chỉ bật đường live nếu có ai trả lời. Cùng file đó mở thẳng từ đĩa, hoặc gửi cho đồng nghiệp, hoặc mở trên máy air-gapped, vẫn hoạt động như một báo cáo tĩnh: bảng vẫn lọc, vẫn sắp xếp, vẫn bung dòng. Chỉ có nút tra cứu là không xuất hiện.

Đây cũng là cái bẫy hay gặp nhất với người dùng mới, kể cả AI agent: mở `report.html` bằng cách bấm đúp vào file, thấy tra cứu không hoạt động, rồi báo cáo rằng tính năng bị hỏng. Nó không hỏng — nó đang ở đúng chế độ mà origin `file://` cho phép.

## Một CL nối các dòng lại với nhau

Ngoài câu trả lời cho từng dòng, việc tra CL còn cho thêm một thứ nữa.

Một thay đổi của Chromium thường land qua **nhiều khai báo cùng lúc**, và report hiện ra thành nhiều dòng rời. Người đọc mở từng dòng, đọc từng lần, rồi mới nhận ra đó là **một** chuyện.

```
CL 7957918  "[sub apps] change web api"
   mojo_method:blink.mojom.SubAppsService.Add        80 điểm
   mojo_method:blink.mojom.SubAppsService.List       80
   idl_interface:SubAppsAddParams                    70
   idl_member:SubAppsAddParams.installURL            70
   ...  7 dòng, 3 loại fact
```

### Vì sao luật theo liên kết khai báo không đủ

`cluster.py` gom nhóm theo **liên kết Chromium tự khai báo trong source**: một `webui_gate` nhắc tên một `base_feature`, một `feature_param` nhắc feature cha, một control nhắc trang nó thuộc về. Comment trong code nói thẳng nguyên tắc — *chỉ nối theo liên kết Chromium thật sự khai báo; suy từ tên giống nhau là đoán mò*.

Nguyên tắc đó **đúng**, nhưng nó giới hạn việc gom vào các màn hình WebUI. Giữa một file `.mojom` và một file `.idl`, **Chromium không viết ra liên kết nào cả**.

Đo trên một report M148 → M151 có 3.022 dòng: luật theo liên kết khai báo gom được 183 dòng, mà **143 nhóm trong đó là feature + param của nó** — tức là đáy bảng xếp hạng. Trong 150 dòng điểm cao nhất, nó với tới **6**.

### CL là cùng loại bằng chứng, ghi ở chỗ khác

Tác giả viết **một** thay đổi, nó land qua nhiều khai báo, và **số CL là chính Chromium nói vậy**. Không phải đoán theo tên giống nhau — đúng chuẩn mà luật theo liên kết khai báo đặt ra, chỉ ở một nguồn khác.

| | Chỉ luật liên kết khai báo | Thêm luật CL |
|---|---:|---:|
| Trong 150 dòng điểm cao nhất | 6 | **84** |
| Toàn report | 183 | **261** |

Và nó quan trọng nhất **đúng chỗ người đọc đang nhìn**: trong **20 dòng đầu bảng, 9 dòng** là một thay đổi đã có trên màn hình, xuất hiện lại. Một CL đưa vào một mixin chiếm **14 dòng**.

### Ba ràng buộc, mỗi cái có lý do đo được

- **Chỉ CL, không dùng issue.** Một issue trong lần chạy này mang 24 CL trải khắp các bề mặt không liên quan — gom theo issue sẽ ra một cụm không ai đọc nổi.
- **Chỉ verdict gọi tên fact**, không dùng `crowded`/`touched`. Chúng gọi tên **file**; riêng `about_flags.cc` sẽ nhét 500 finding vào một cụm.
- **Trần 20 dòng một nhóm** — và đây là *hàng rào phòng xa, không phải số đo*. Dữ liệu không cần nó: nhóm chạy 2–7 dòng và đúng một nhóm 14. Thứ tạo nhóm sai to nhất — một CL reformat khớp hàng chục khai báo — đã bị chặn ở tầng trên, vì Gerrit đánh dấu reformat là `common: true` và tool không tính nó là dòng đã đổi.

### Nó chạy lúc nào

**Lúc bạn bấm tra một dòng.** `run` không hỏi Gerrit câu nào, nên trên một report chưa tra gì thì luật CL không gom gì, và bốn luật theo liên kết khai báo là tất cả. Nhóm **lớn dần** theo lúc bạn khám phá:

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

Một dòng có CL và một dòng không có CL **trông giống hệt nhau** trong bảng. Vì vậy bảng có thêm một bộ lọc, và năm trạng thái của nó **tách bạch** — gộp chúng lại chính là lỗi mà cả chặng này được viết ra để tránh:

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

Bản Markdown là bản **đi vào ticket**, và nó không có màu badge, không có row state, không có panel để đặt lời cảnh báo. Dòng người đọc copy ra là tất cả những gì đi tiếp.

Vì vậy ở đây chính **tiêu đề** thay đổi theo bản chất của câu trả lời:

| Tiêu đề trong `report.md` | Khi nào |
|---|---|
| `Why it changed (…)` | có ít nhất một verdict gọi tên Fact |
| `How it got here, oldest first (…)` | toàn bộ là `crowded` — đây là lịch sử declaration |
| `Leads only, no CL names this (…)` | toàn bộ là manh mối |

Mẫu số, số đã đọc và số bị cắt đều nằm trong dấu ngoặc, vì chúng là **một phần của trích dẫn**, không phải trang trí.

## Những phản hồi của Gerrit cần xử lý riêng

Nếu không được xử lý riêng, mỗi trường hợp dưới đây sẽ cho ra một **câu trả lời sai nhưng trông chắc chắn**, thay vì báo lỗi.

| Trường hợp | Cách xử lý |
|---|---|
| **Block `{"skip": N}` của file đã đổi tên** | Gerrit đáp request diff cho path **cũ** của file đã đổi tên bằng `change_type: MODIFIED` và cả file gói trong một block `skip`, không 404, không dấu hiệu rename. Parser đọc block `skip` thành N dòng không đổi; diff không có dòng nào đổi thì công cụ hỏi CL đó đã chuyển file sang đâu, và Fact được lần theo tới path mới với verdict `moved` |
| **Reindent** | Block gắn `{"a": […], "b": […], "common": true}` là các dòng cùng nội dung, chỉ khác bên trong dòng. Công cụ không tính chúng là dòng đã đổi, nên một CL reformat file không trở thành `exact` cho mọi declaration trong file đó. Mẫu 2.329 diff có 49 block như vậy |
| **Dòng bị ngân sách diff từ chối** | `diffs_read` được ghi trên **mọi** dòng đã được tra, và chỉ là `true` khi mọi path của dòng đều đã được đọc. Nhờ vậy có thể phân biệt dòng chưa được đọc với dòng đã quét nhưng không khớp gì |
| **Declaration ở hai file** | Declaration đã chuyển file được tìm ở cả hai file, và mỗi CL ghi rõ nó được tìm thấy ở file nào |
| **Key có qualifier** | Ca `TokenError.url`: container được giữ **tách khỏi** tập token, vì một dòng đã đổi có nhắc `TokenError` **không phải** một dòng khai báo `TokenError.url`; container chỉ có thể nhận verdict `declares`, không bao giờ nhận `exact` |
| **Danh sách trường của payload** | Server tạo payload bằng chính hàm render dòng của trang và chỉ giữ các key trong `PROVENANCE_KEYS` của renderer, nên danh sách trường chỉ tồn tại ở một nơi |

Ngoài ra, hai thứ về mạng được xử lý riêng vì chúng có cùng một hậu quả:

- **HTTP 429 có thang lùi riêng** (5 giây, 20 giây, 60 giây). Thang lùi chung của công cụ là 1,5 / 3 / 6 giây — quá ngắn cho một rate limiter đếm theo phút. Một 429 bị retry quá nhanh trở thành **một fetch âm thầm trả về không có gì**, và "không có gì" ở điểm sử dụng thì **không phân biệt được** với "CL này không nhắc identifier".
- **Fetch thất bại luôn được đếm và báo ra, không bao giờ bị bỏ qua.** Một lỗi mạng không bao giờ được báo thành *"không tìm thấy CL"*.

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
