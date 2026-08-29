# ChromeDrift: bản trình bày kỹ thuật cho kế hoạch nâng phiên bản Chromium nền của Samsung Browser trên Windows

## Cách đọc tài liệu này

Đây là tài liệu tổng quan đầy đủ, dùng khi cần trình bày toàn bộ project trong một buổi họp hoặc khi cần tra cứu một chi tiết cụ thể. Nó dài, nên đừng đọc tuần tự từ đầu tới cuối nếu chỉ cần một phần.

| Muốn biết | Đọc phần |
|---|---|
| Vấn đề là gì và công cụ giải quyết được tới đâu | 1, 2 |
| Dữ liệu chảy qua hệ thống như thế nào | 3 |
| Mã nguồn được lấy từ đâu và lấy bao nhiêu | 4, 5, 6, 7 |
| Cấu trúc dữ liệu bên trong công cụ | 8, 9, 10 |
| Vì sao một thay đổi được điểm cao hay điểm thấp | 11, 12, 13, 14, 15 |
| Độ tin cậy của kết quả | 16, 23 |
| Báo cáo có những gì và đọc ra sao | 17, 18, 19 |
| Ai làm gì trong quy trình | 20, 22, 26 |
| Số liệu từ một lần chạy thật | 21 |
| Giới hạn của công cụ | 24, 25 |
| Chuẩn bị demo hoặc trả lời câu hỏi khi review | 27, 28 |
| Checklist vận hành và kết luận | 29, 30, 31 |

Các phần cần tra cứu riêng đã được tách thành một bộ tài liệu ngắn hơn:

- [Thuật ngữ dùng trong ChromeDrift](<01 - Thuật ngữ ChromeDrift.md>)
- [Cách lấy source tree, thư mục và file](<02 - Cách lấy source Chromium.md>)
- [9 nhóm nguồn khai báo và các bộ lọc](<03 - Chín nhóm file và bộ lọc.md>)
- [Fact và ví dụ đầu vào → JSON cho đủ 16 loại](<04 - Fact và cách trích xuất.md>)
- [So sánh, chấm điểm, bucket và owner](<05 - Cách so sánh, chấm điểm và phân loại.md>)
- [Skill, agent và nội dung dành cho từng team](<06 - Skill và cách hỗ trợ từng nhóm.md>)

**Về thuật ngữ:** nhiều từ trong tài liệu này được giữ nguyên tiếng Anh vì chúng là tên của một khái niệm kỹ thuật hoặc một chuỗi xuất hiện thật trong công cụ — `Fact`, `signal`, `bucket`, `coverage`, `uprev`. Mỗi từ như vậy đều có giải thích ngắn ở lần dùng đầu tiên, và toàn bộ định nghĩa được gom trong [phần 1 của bộ tài liệu ngắn](<01 - Thuật ngữ ChromeDrift.md>).

## 1. Bài toán cần giải quyết

Samsung Browser được phát triển từ mã nguồn Chromium. Mỗi lần chuyển sang một phiên bản Chromium mới — việc này gọi là một đợt `uprev` — team không chỉ phải merge một lượng code rất lớn, mà còn phải trả lời sớm những câu hỏi khó hơn nhiều:

- Hành vi nào của Chromium đã đổi mặc định trên Windows?
- API, IPC contract hoặc cấu trúc dữ liệu nào mà Samsung code có thể đang phụ thuộc đã đổi, nhưng compiler không hề cảnh báo?
- Những cái tên dùng để điều khiển browser **từ bên ngoài mã nguồn** có bị đổi hoặc mất không — pref key, command-line switch, feature name, hoặc `FeatureParam` mà server dùng để chạy thử nghiệm?
- Web API nào vừa được đưa vào sử dụng, bị rút lại, hoặc đổi cách gọi?
- Mojo interface, method hoặc data type nào đổi trên đường IPC giữa các process?
- Trang WebUI `chrome://` nào đổi route, đổi control, đổi pref phía sau, hoặc đổi điều kiện hiển thị?
- Thay đổi nào thực ra chỉ là Chromium dọn feature flag sau khi chức năng đã được bật từ trước, chứ không phải một hành vi mới?
- Mục thay đổi nào thuộc Browser C++, WebUI, Web Platform hay IPC; mục nào phải kiểm tra ở cấu hình nằm ngoài repository?

Một Git diff thô không trả lời tốt các câu hỏi này, vì nó trộn thay đổi cú pháp, refactor, chuyển file, dọn code và thay đổi contract thật vào cùng một danh sách dài.

ChromeDrift làm khác: nó đọc các khai báo quan trọng, chuyển mỗi khai báo thành một object chuẩn hoá gọi là `Fact`, so sánh các `Fact` giữa hai phiên bản, rồi xếp thứ tự để team biết nên điều tra gì trước.

### Giá trị thật nằm ở đâu

Giá trị của công cụ không phải là "nó biết mọi thứ". Giá trị là nó tạo ra một luồng thu hẹp dần mà ai cũng kiểm tra lại được:

```text
Toàn bộ thay đổi giữa hai Chromium tag
        ↓
Những khai báo có ý nghĩa đối với việc tích hợp browser
        ↓
Những thay đổi thực sự về hành vi hoặc contract
        ↓
Breaking / Behaviour change / New surface / Housekeeping
        ↓
Giao cho đúng owner: IPC / Web Platform / Browser C++ / WebUI / Config
        ↓
Đối chiếu tên liên quan trong Samsung source và cấu hình ngoài repository
        ↓
Danh sách việc thật cho đợt nâng phiên bản
```

Điểm thuyết phục nhất là **thời điểm**: ChromeDrift đưa việc phát hiện lên trước lúc merge. Ba ví dụ về những thứ bình thường chỉ lộ ra rất muộn:

- một C++ symbol đổi tên, vốn chỉ lộ khi build;
- một thay đổi trong Mojo IPC contract, có thể chỉ lộ khi chạy;
- một feature bị đổi tên, khiến server không còn bật đúng feature đó cho người dùng — và không có gì báo lỗi cả.

ChromeDrift biến các trường hợp này thành từng finding, kèm vị trí `path:line`, giá trị trước và sau, cùng lý do vì sao cần xem sớm.

## 2. Tool trả lời gì, và không trả lời gì

Phần này nên đọc kỹ trước khi trình bày công cụ cho người khác, vì đây là ranh giới dễ bị nói quá nhất.

### 2.1. Tool trả lời được

ChromeDrift so sánh **mã nguồn Chromium gốc ở hai phiên bản** và trả lời:

- Khai báo nào được thêm, bị bỏ, hoặc thay đổi về mặt ý nghĩa?
- Thay đổi đó thuộc nhóm nào: feature, Web API, Mojo, pref, hay WebUI?
- Bản build Windows có chứa khai báo đó ở cả phiên bản cũ lẫn phiên bản mới không?
- Loại thay đổi này thường có hậu quả gì?
- Bằng chứng của chính lần chạy này có đủ để tin một kết luận "đã biến mất" không?
- Owner nào phù hợp nhất để kiểm tra trước?
- File nào, dòng nào là bằng chứng cho finding?

### 2.2. Tool chưa thể tự trả lời

ChromeDrift không biết:

- Samsung Browser có đang dùng symbol, pref, switch hoặc Mojo API đó hay không.
- Samsung có sửa riêng phần implementation liên quan hay không.
- Các hệ thống nằm ngoài mã nguồn đang dùng tên nào — server chạy thử nghiệm, policy doanh nghiệp, script khởi động, automation.
- Một thay đổi sẽ tốn 2 giờ hay 2 tuần.
- Giao diện sau khi render có lệch layout, lệch visual hay lỗi tương tác không.
- Toàn bộ build graph trong `BUILD.gn` đã đổi ra sao.

### Cách phát biểu đúng

Vì vậy, câu **sai** là: *"276 Breaking nghĩa là Samsung có 276 bug."*

Câu **đúng** là:

> "Chromium gốc có 276 thay đổi về API, IPC hoặc cấu trúc dữ liệu cần đối chiếu với Samsung Browser. ChromeDrift đã phân loại, xếp thứ tự và chỉ ra vị trí khai báo; bước tiếp theo là tìm nơi Samsung đang sử dụng và giao cho owner xác nhận ảnh hưởng."

## 3. Luồng end-to-end

Công cụ được chạy bằng `python3 -m chromedrift`. Nhìn theo đường đi của dữ liệu, toàn bộ luồng gồm chín chặng:

```text
Đầu vào
  from_ref, to_ref
  target_set, partitions, complete
  Gitiles từ xa hoặc checkout có sẵn trên máy
        │
        ▼
1. Chuẩn hoá phiên bản
  milestone / version đầy đủ / git ref → một ref cụ thể
        │
        ▼
2. Lập danh sách file và đo coverage
  lấy cây file của đúng phiên bản
  xác định file nào có thể chứa loại khai báo mà tool hiểu
  đo tỷ lệ file thực sự đọc được trong từng nhóm
        │
        ▼
3. Tạo cây source rút gọn trên máy
  tải các file hoặc thư mục con cần thiết vào cache
        │
        ▼
4. Trích xuất thông tin
  9 bộ đọc chuyên biệt → 16 loại Fact
  xác định Fact có thuộc Windows build hay không, và loại bản ghi trùng
        │
        ├── Snapshot FROM
        └── Snapshot TO
                 │
                 ▼
5. So sánh hai phiên bản
  ghép Fact cũ và mới theo Fact.uid
  chỉ so những thuộc tính ảnh hưởng đến hành vi hoặc contract
  phát hiện đổi tên, hoặc WebUI control chuyển sang pref khác
  tạo Change, signal và severity
                 │
                 ▼
6. Chấm điểm ưu tiên
  severity → điều chỉnh theo Windows và coverage → điểm cuối
  xếp vào bucket và chọn owner
                 │
                 ▼
7. Bổ sung ngữ cảnh
  gom các finding có liên quan thành một nhóm
  bổ sung thông tin từ Chromestatus nếu được bật
                 │
                 ▼
8. Đầu ra
  report.json + report.md + report.html
                 │
                 ▼
9. Xác nhận ảnh hưởng lên Samsung Browser
  engineer hoặc coding agent làm theo skill
  tìm trong Samsung source/config, xác nhận ảnh hưởng và tạo đầu việc
```

Cần chú ý ranh giới: **pipeline kết thúc ở bước 8, tức là ở báo cáo.** Code hiện tại không có bước nào để AI tự quyết định thay đổi nào chắc chắn làm Samsung Browser lỗi. Bước 9 là việc của con người và của agent được cấp quyền truy cập source Samsung.

## 4. Version đến từ đâu?

### 4.1. Ba loại đầu vào được hỗ trợ

| Dạng đầu vào | Cách xử lý | Ví dụ |
|---|---|---|
| Version đầy đủ | Đổi thẳng thành Git tag, không thay đổi gì thêm | `151.0.7922.138` → `refs/tags/151.0.7922.138` |
| Chỉ có milestone | Hỏi ChromiumDash và lấy bản Stable Windows mới nhất **tại thời điểm chạy** | `151` → bản vá Stable mới nhất của M151 |
| Git ref | Giữ nguyên branch, tag hoặc SHA mà người dùng đưa vào | `refs/heads/main`, một SHA, một custom ref |

Một quyết định thiết kế đáng chú ý: **công cụ luôn phân tích cho Windows, và CLI không có option `--platform`.** Nhờ vậy, một báo cáo dành cho Android hoặc macOS không thể bị dùng nhầm cho Samsung Browser trên Windows.

### 4.2. Tại sao ticket phải ghi version đầy đủ?

Một milestone có nhiều bản vá. Trong cùng M143, một feature có thể được bật ở bản vá đầu rồi bị hoàn tác ở bản sau.

Hệ quả rất cụ thể: nếu ticket chỉ ghi `143`, cùng một lệnh chạy ở hai thời điểm khác nhau có thể lấy về hai Git tag khác nhau, và hai người sẽ tranh luận về hai bộ dữ liệu khác nhau mà không ai biết.

Quy tắc vận hành nên là:

- Chỉ dùng milestone để kiểm tra nhanh.
- Dùng version đầy đủ bốn phần cho báo cáo chính thức, cho kết quả lưu từ CI, và cho mọi quyết định lập kế hoạch.
- Luôn ghi cả version Chromium hiện tại lẫn version mục tiêu.

### 4.3. Hai nguồn code

**Gitiles — nguồn mặc định**

- Công cụ có thể tải từng file, hoặc tải cả một thư mục dưới dạng archive `.tar.gz`.
- Trước khi tải nội dung, công cụ lấy danh sách toàn bộ đường dẫn bằng Gitiles JSON, để đo coverage.
- Khi dùng một Git tag chính thức, nội dung không bao giờ thay đổi, nên kết quả có thể chạy lại và kiểm chứng.

**Source có sẵn trên máy, hoặc mirror nội bộ**

- Ba option `--local-src`, `--from-src`, `--to-src` cho phép đọc source từ ổ đĩa thay vì tải qua mạng.
- Sau bước lấy source, các bước trích xuất và so sánh hoàn toàn giống nhau.
- Cách này phù hợp với môi trường không có Internet, hoặc nơi đã có sẵn mirror Chromium nội bộ.

**Một giới hạn quan trọng cần nói rõ:** `LocalSource` không tự chuyển Git checkout sang commit cần phân tích, và cũng không kiểm tra xem thư mục đó có đúng commit được ghi trong báo cáo hay không. Người chạy phải tự chuẩn bị đúng source cho từng phiên bản.

Tình huống xấu nhất rất dễ xảy ra: nếu vô tình dùng cùng một thư mục cho cả bản cũ lẫn bản mới, công cụ sẽ so hai bản giống hệt nhau và báo cáo gần như không tìm thấy thay đổi nào — một kết quả trông rất yên tâm nhưng hoàn toàn vô nghĩa.

## 5. Tool kéo code gì, kéo như thế nào và làm sao biết đã kéo đúng?

### 5.1. Không tải toàn bộ Chromium

Một bộ source Chromium đầy đủ gồm repository chính cộng rất nhiều dependency. Trong quy trình Chromium thông thường, `gclient sync` là lệnh dùng để đồng bộ lượng dữ liệu này — và vì vậy việc tải có thể rất lớn và mất nhiều thời gian.

ChromeDrift không build Chromium. Nó chỉ đọc những file chứa các khai báo mà nó biết cách phân tích: feature flag, pref, Web API, Mojo interface. Vì vậy nó chỉ tải phần source cần thiết.

Các file đã tải vẫn được đặt đúng vị trí tương đối như trong repository Chromium. Ví dụ, file nằm ở `chrome/browser/...` trên Chromium cũng nằm ở `chrome/browser/...` trong cache. Việc giữ nguyên đường dẫn không phải để cho gọn — nó giúp các bộ đọc xác định đúng loại file và đúng component.

Hiện tại target set (bộ file mà một lần chạy cam kết đọc) có cấu trúc:

| Bộ file | Số mục được cấu hình | Thành phần | Mục đích |
|---|---:|---|---|
| `minimal` | 3 file | Blink manifest, file khai báo feature và file khai báo switch | Kiểm tra nhanh xem pipeline có hoạt động không |
| `default` | 49 mục: 36 file + 13 thư mục | Các file thường chứa nhiều thông tin, Blink IDL, Blink Mojo và 8 nhóm WebUI | Phân tích nhanh hằng ngày |
| `wide` | 81 mục: 36 file + 45 thư mục | `default` cộng thêm các thư mục subsystem lớn; trong mỗi thư mục vẫn chỉ giữ loại file mà tool đọc được | Lập kế hoạch chính thức với phạm vi rộng nhất |

Số liệu đã đo trong project là khoảng **40 MB** cho mỗi version với `default`, và khoảng **337 MB** với `wide`. Dung lượng thực tế phụ thuộc từng Git tag; khi trình bày, hãy dùng số của chính lần chạy đó chứ đừng dùng số trong tài liệu.

### 5.2. Tải một thư mục không có nghĩa giữ mọi file trong đó

Khi giải nén archive của một thư mục con, công cụ dùng danh sách `READABLE_SUFFIXES` để chỉ giữ những file có mẫu tên hoặc đuôi mà pipeline có khả năng cần. Danh sách này hiện có 27 cách viết, trong đó có:

- File feature/switch C++: `features.cc/.h`, `switches.cc/.h`, `feature_list`, `field_trial`, `flags`, một số `*_handler.cc`, `*_util.cc`, `*_manager.cc`.
- File preference: `pref_names.cc/.h`, `prefs.cc/.h`.
- `.mojom`, Blink `.idl`, `.json5`.
- Route và template WebUI: `route.ts`, `routes.ts`, `.html`, `.html.ts`.
- `flag-metadata.json`.

Đây mới chỉ là bộ lọc thô, mục đích là giảm dữ liệu trên ổ đĩa. Sau đó từng extractor còn kiểm tra đường dẫn bằng `applies_to`; chỉ file vượt qua bước này mới thật sự được phân tích. **Vì vậy một file được giữ lại sau khi giải nén chưa chắc tạo ra `Fact`.**

Bộ lọc cũng không khẳng định các file bị bỏ là "không quan trọng". Nó chỉ nói rằng ChromeDrift hiện chưa có parser đủ tin cậy cho chúng. Ví dụ: giữ toàn bộ implementation TypeScript trong khi không có parser tương ứng chỉ làm tăng dung lượng mà không tạo thêm finding nào.

### 5.3. Làm sao biết quá trình tải không bị sai hoặc thiếu?

Bảy lớp bảo vệ chính:

- Nếu request HTTP lỗi tạm thời, công cụ thử lại với khoảng chờ tăng dần.
- Công cụ kiểm tra response để phân biệt file rỗng thật với dữ liệu bị tải thiếu.
- HTTP 404 được ghi rõ là `missing`; còn lỗi mạng thì làm cả lần chạy thất bại, chứ không bị ghi nhầm thành "file không tồn tại".
- File nhỏ được tải song song tối đa tám luồng; archive của thư mục được xử lý tuần tự.
- Khi giải nén, công cụ chặn mọi đường dẫn có thể ghi file ra ngoài thư mục cache.
- Cache ghi lại Git ref, bộ file, partition, chế độ `complete` và bộ lọc đuôi file. Khi bất kỳ giá trị nào trong số này đổi, artifact cũ không thể bị dùng nhầm.
- Schema version `40` buộc snapshot và báo cáo cũ phải được tạo lại khi cấu trúc hoặc ý nghĩa của `Fact` thay đổi.

### 5.4. Cache layout và ý nghĩa

```text
.chromedrift-cache/
  listings/      # danh sách đường dẫn của từng Git ref
  trees/         # các file source đã tải
  snapshots/     # các Fact đã chuẩn hoá
  chromestatus/  # thông tin bổ sung theo milestone, nếu được bật
```

Thư mục `trees/` được dùng chung giữa các bộ file. Điều này tạo ra một rủi ro, và công cụ có cách chặn:

Bước trích xuất **không** đọc tất cả những gì đang có trong cache. Nó chỉ đọc những đường dẫn mà bộ file hiện tại cho phép. Cơ chế này ngăn các file còn sót lại từ một lần chạy `wide` lọt vào kết quả `minimal` hoặc `default` rồi tạo ra hàng nghìn thay đổi giả.

### 5.5. Cây thư mục được lấy như thế nào?

Có hai bước khác nhau, và không nên nhầm chúng với nhau:

1. **Lấy danh sách để đo coverage.** Gitiles trả về toàn bộ đường dẫn dưới các thư mục gốc cần khảo sát. Bước này chỉ lấy tên file, chưa tải nội dung.
2. **Tải file để phân tích.** Bộ file `minimal`, `default` hoặc `wide` quyết định file và thư mục con nào được tải vào cache.

Các thư mục gốc bao gồm những vùng như `chrome`, `components`, `content`, `extensions`, `services`, Blink, `base`, `device`, `cc`, `sandbox`, `storage` và `mojo`.

Mỗi extractor tự khai báo đường dẫn nào nó có thể đọc. Nhờ vậy, công cụ vừa lập được danh sách file ứng viên, vừa tính được coverage bằng **đúng tiêu chí** mà bước trích xuất sử dụng — chứ không phải bằng một danh sách viết tay có thể lệch theo thời gian.

## 6. Bộ lọc file hoạt động theo nhiều lớp

Một file chỉ tạo ra `Fact` khi vượt qua **tất cả** năm lớp lọc sau. Mỗi lớp trả lời một câu hỏi khác nhau.

### Lớp 1 — Có thuộc sản phẩm browser không?

Các nhóm sau bị loại:

- File test, fuzzer và mock, nhận diện bằng component và mẫu tên file cụ thể.
- File sinh tự động, cùng các thư mục `.git`, `out` và cache.
- Chương trình khác không phải browser chính: content shell, headless shell, updater, remote desktop, Windows service.
- Source bên thứ ba dùng cú pháp khác với loại mà extractor hỗ trợ.

Một chi tiết quan trọng về cách viết rule: rule xét **component và mẫu tên file cụ thể**, chứ không loại chỉ vì đường dẫn chứa một đoạn chữ chung. Ví dụ, `hit_test_opaqueness.mojom` là source của sản phẩm; chuỗi `_test_` nằm giữa tên không được phép làm file này bị loại nhầm.

### Lớp 2 — Có liên quan đến Windows không?

Các đường dẫn chỉ dành cho Android, ash/ChromeOS, iOS, Fuchsia, macOS hoặc Linux bị loại khỏi phân tích cho Windows.

Có một ngoại lệ có chủ đích: bộ đọc pref và switch vẫn được nhìn sang thư mục của nền tảng khác, để biết một key đã **được chuyển đi** chứ không thực sự bị xoá. Ngoại lệ này an toàn vì `platform_state` vẫn quyết định thay đổi đó có ảnh hưởng đến Windows hay không, và được chấm bao nhiêu điểm.

### Lớp 3 — Có nằm trong bộ file đã chọn không?

File phải được chỉ định trực tiếp, hoặc nằm trong một thư mục đã chọn và có đuôi file phù hợp. Nếu nhiều thư mục cha cùng khớp, công cụ kiểm tra tất cả thay vì dừng ở thư mục đầu tiên.

### Lớp 4 — Có extractor nào hiểu loại file này không?

Mỗi extractor định nghĩa chính xác đường dẫn nào nó có thể đọc:

- `.idl` chỉ được Web IDL extractor nhận nếu nằm dưới `third_party/blink/renderer/`.
- `.mojom` được Mojo extractor nhận.
- WebUI control chỉ nhận `.html`/`.html.ts` dưới `chrome/browser/resources/`.
- Bộ đọc C++ constants chỉ nhận các file có quy ước đặt tên dành cho switch hoặc pref.

### Lớp 5 — Cú pháp bên trong có đúng dạng extractor hỗ trợ không?

Ngay cả khi file đã được mở, extractor chỉ tạo `Fact` cho những mẫu khai báo mà parser của nó hỗ trợ.

Hệ quả cần nhớ: **đọc được 99% số file ứng viên không có nghĩa công cụ hiểu 99% mọi cú pháp nằm trong các file đó.** Đây là khác biệt giữa coverage theo file và coverage theo cú pháp, và nó quay lại nhiều lần trong tài liệu này.

## 7. Tool đọc những loại file nào, và mỗi loại dùng để làm gì?

ChromeDrift không chọn file chỉ vì đuôi file "có vẻ quan trọng". Mỗi loại file được chọn vì nó là **nơi Chromium khai báo một thông tin có thể so sánh giữa hai version**: feature nào tồn tại, API có hình dạng gì, IPC truyền dữ liệu ra sao, pref dùng key nào, hoặc WebUI control phụ thuộc feature nào.

### 7.1. Hai lớp quyết định một file có thực sự được phân tích hay không

Cần phân biệt hai bước:

1. `READABLE_SUFFIXES` là bộ lọc **thô**, chạy khi giải nén archive. Nó giúp bỏ sớm các file chắc chắn công cụ không dùng.
2. `applies_to(path)` của từng extractor là điều kiện **chính xác**. Chỉ khi điều kiện này đúng, extractor mới mở file và có thể tạo `Fact`.

Vì vậy, **file được giữ trong cây source rút gọn chưa chắc đã tạo `Fact`**. Ba ví dụ:

- Bộ lọc archive giữ file `.idl`, nhưng Web IDL extractor chỉ nhận `.idl` dưới `third_party/blink/renderer/`.
- Bộ lọc giữ `.html` và `.html.ts`, nhưng WebUI control extractor chỉ nhận chúng dưới `chrome/browser/resources/`.
- Bộ lọc giữ `.json5`, nhưng Blink runtime extractor chỉ đọc file có tên chính xác là `runtime_enabled_features.json5`.

Danh sách `READABLE_SUFFIXES` có 27 cách viết, nhưng đó **không phải** 27 loại dữ liệu độc lập. Nhiều cách viết cùng thuộc một nhóm — chẳng hạn `features.cc`, `features.h`, `feature_list.cc`, `field_trial.cc` và `flags.cc` đều có thể chứa khai báo feature.

### 7.2. Bảng tổng quan

| File hoặc mẫu tên | Nội dung Chromium khai báo trong đó | Extractor và `Fact` tạo ra | Câu hỏi mà report trả lời |
|---|---|---|---|
| `*features.cc/.h`, `*feature_list.cc/.h`, `*field_trial.cc/.h`, `*flags.cc/.h`, một số `*_handler.cc`, `*_util.cc`, `*_manager.cc` | `base::Feature`, trạng thái bật/tắt mặc định và `FeatureParam` | `base_features` → `base_feature`, `feature_param` | Feature nào đổi mặc định trên Windows? Param nào đổi type hoặc giá trị? C++ symbol nào đổi tên? |
| `*switches.cc/.h` | String constant dùng làm command-line switch; file cũng có thể chứa khai báo feature | `constants` → `switch`; `base_features` cũng đọc feature nếu có | Script test, automation hoặc shortcut có còn truyền đúng switch không? |
| `*pref_names.cc/.h`, `*_prefs.cc/.h`, `prefs.cc/.h` | String constant dùng làm key lưu setting trong user profile | `constants` → `pref` | Dữ liệu cũ trong profile có còn được đọc? Samsung code có còn dùng đúng C++ symbol không? |
| `runtime_enabled_features.json5` | Danh sách Blink runtime feature và trạng thái `test`, `experimental`, `stable` theo platform | `blink_runtime` → `blink_runtime_feature` | Web API nào bắt đầu được expose trên Windows, bị tắt, hoặc đổi gate? |
| `.idl` dưới `third_party/blink/renderer/` | Hình dạng Web API cung cấp cho JavaScript | `web_idl` → `idl_interface`, `idl_member` | Interface, method, property, signature hoặc runtime gate nào đổi? |
| `.mojom` | IPC interface và dữ liệu trao đổi giữa các process | `mojom` → interface, method, struct, field, enum | Method signature, field type, ordinal hoặc `MinVersion` nào đổi qua process boundary? |
| `flag-metadata.json` | Metadata của entry trong `chrome://flags`, đặc biệt là milestone hết hạn | `flags_metadata` → `flag_entry` | Flag nào sắp phải dọn? Đây là lịch công việc hay thay đổi hành vi thật? |
| `route.ts`, `routes.ts` dưới `chrome/browser/resources/` | Route, path, quan hệ cha-con và điều kiện hiển thị của WebUI page | `webui_routes` → `webui_route` | Page nội bộ nào đổi URL, đổi parent, bị thêm/xoá, hoặc đổi guard? |
| `.html`, `.html.ts` dưới `chrome/browser/resources/` | WebUI control trong Polymer hoặc Lit template | `webui_controls` → `webui_control` | Toggle/dropdown/button nào đổi loại, đổi pref, đổi label hoặc đổi điều kiện build? |
| `.cc` dưới `chrome/browser/ui/webui/` | C++ handler đưa dữ liệu và feature state vào WebUI qua `loadTimeData` | `webui_gates` → `webui_gate` | Boolean nào điều khiển page/control, và nó phụ thuộc `base::Feature` nào? |

### 7.3. C++ feature files

**File được nhận diện thế nào?**

Tên file phải kết thúc bằng một trong các mẫu như `features.cc`, `features.h`, `switches.cc`, `feature_list.cc`, `field_trial.cc`, `fieldtrial.cc`, `flags.cc`, `_handler.cc`, `_util.cc` hoặc `_manager.cc`. File test như `*_unittest.cc` và `*_browsertest.cc` bị loại.

**Tool đọc gì?**

Công cụ tìm các dạng khai báo `BASE_FEATURE`, `const base::Feature`, `BASE_FEATURE_PARAM` và `base::FeatureParam<T>`. Nó giữ lại: feature name, biến C++, trạng thái mặc định, type và giá trị của param, cùng điều kiện `#if` để xác định trạng thái trên Windows.

Ví dụ:

```cpp
BASE_FEATURE(kNewDownloadUI, base::FEATURE_ENABLED_BY_DEFAULT);
```

`Fact` tương ứng cho biết feature có tên `NewDownloadUI`, C++ symbol là `kNewDownloadUI`, và mặc định đang bật. Nếu version cũ là `DISABLED` còn version mới là `ENABLED`, đây là thay đổi hành vi mà Samsung Browser sẽ nhận sau khi merge — trừ khi Samsung có override riêng.

**Tại sao quan trọng?**

- Trạng thái mặc định đổi thường là thời điểm feature bắt đầu áp dụng rộng rãi.
- `FeatureParam` đổi có thể làm cùng một feature chạy theo cách khác, trong khi feature name không hề đổi.
- C++ symbol đổi tên có thể làm Samsung source lỗi build.
- Điều kiện `#if` đổi có thể đưa feature vào hoặc ra khỏi Windows build.

**Không đọc gì?**

Extractor không phân tích logic bên trong function. Một hành vi thay đổi hoàn toàn trong implementation nhưng giữ nguyên khai báo feature sẽ **không** xuất hiện ở nhóm này.

### 7.4. Command-line switch và pref files

Hai nhóm này đều dùng C++ string constant, nhưng phục vụ hai contract khác nhau.

**Command-line switch**

File thường có tên `switches.cc/.h`, hoặc có tiền tố như `content_switches.cc`. Công cụ đọc hai dạng:

```cpp
const char kEnableFoo[] = "enable-foo";
inline constexpr std::string_view kEnableFoo = "enable-foo";
```

Ở đây `enable-foo` là tên được truyền vào browser dưới dạng `--enable-foo`; còn `kEnableFoo` là symbol C++. Hai thứ này hỏng theo hai cách khác nhau:

- Nếu **string** đổi, script, automation hoặc shortcut dùng tên cũ có thể âm thầm mất tác dụng.
- Nếu chỉ **C++ symbol** đổi, script bên ngoài vẫn an toàn, nhưng Samsung source dùng symbol cũ có thể lỗi build.

**Preference**

File thường theo hai quy ước: dạng cũ `*pref_names.cc/.h` và dạng mới `*_prefs.cc/.h`; `prefs.cc/.h` cũng được nhận. Ví dụ:

```cpp
const char kPromptForDownload[] = "download.prompt_for_download";
```

`download.prompt_for_download` là pref key lưu trong user profile; `kPromptForDownload` là symbol C++. Cũng hai cách hỏng khác nhau:

- Nếu **pref key** đổi, browser mới có thể không đọc được giá trị đã lưu bằng key cũ, và setting quay về mặc định.
- Nếu chỉ **C++ symbol** đổi, dữ liệu người dùng giữ nguyên, nhưng Samsung source có thể phải sửa.

**Giới hạn**

Extractor chỉ nhận string literal trong file có mẫu tên nói trên. Key được tạo động, hoặc được khai báo trong file có tên ngoài quy ước, sẽ không được đọc.

Vì vậy coverage của nhóm pref/switch phải được xem **trước** khi tin bất kỳ kết luận "đã xoá" nào ở nhóm này.

### 7.5. Blink runtime manifest

File `third_party/blink/renderer/platform/runtime_enabled_features.json5` là danh sách tập trung các runtime feature của Blink. Mỗi entry có thể ghi trạng thái chung, hoặc ghi riêng theo từng platform:

```text
name: "ExampleFeature"
status: {"Win": "stable", "Mac": "experimental"}
```

Công cụ lấy trạng thái trên Windows, feature C++ đứng sau nó, các dependency, và thông tin Origin Trial nếu có. Ba chuyển dịch đáng chú ý:

- `experimental → stable`: API có thể bắt đầu được cung cấp mặc định cho website trên Windows.
- `stable → experimental/disabled`: website hoặc feature của Samsung đang dùng API có thể mất khả năng truy cập.
- Backing feature đổi: cần lần sang `base::Feature` mới để hiểu gate thật là gì.

File này cho biết **khả năng API được expose**; nó không mô tả đầy đủ signature của API. Signature nằm trong Web IDL.

### 7.6. Blink Web IDL

Công cụ chỉ đọc `.idl` dưới `third_party/blink/renderer/`, chủ yếu trong `core`, `modules` và `platform`. Đây là nguồn khai báo Web API mà Blink cung cấp cho JavaScript.

Ví dụ rút gọn:

```webidl
interface Example {
  Promise<Result> run(DOMString input);
};
```

Công cụ tạo `Fact` cho interface và cho từng member, giữ lại quan hệ kế thừa, signature, overload, extended attribute và runtime gate. Nhờ đó báo cáo phát hiện được:

- interface hoặc method bị thêm hoặc bị xoá;
- parameter, return type hoặc overload thay đổi;
- API chuyển sang một runtime gate khác;
- giá trị enum thay đổi.

Hai giới hạn: Chrome Extensions IDL và Windows MIDL cũng có đuôi `.idl` nhưng không thuộc Blink Web IDL nên bị loại; và công cụ hiện cũng chưa tạo `Fact` cho mọi callback, typedef hoặc quan hệ mixin.

### 7.7. Mojo `.mojom`

Chromium tách browser thành nhiều process. File `.mojom` khai báo contract IPC giữa các process đó. Công cụ đọc mọi `.mojom` nằm trong phạm vi source đã chọn và tạo `Fact` cho:

- interface;
- method cùng signature request/response;
- struct hoặc union;
- field cùng type, ordinal, giá trị mặc định và `MinVersion`;
- enum cùng tên và giá trị của từng member.

Ví dụ:

```mojom
interface DownloadObserver {
  OnChanged(DownloadState state);
};
```

Nếu `DownloadState` đổi type, hoặc method thêm parameter, code được sinh lại từ Chromium **có thể** vẫn build bình thường khi cả hai đầu cùng được cập nhật. Nhưng nếu Samsung tự triển khai hoặc tự gọi một đầu của interface, phần đó phải được kiểm tra.

Đó là lý do `.mojom` là nhóm ưu tiên cao đối với một fork, dù diff của nó thường rất nhỏ.

Công cụ hiện chưa tạo `Fact` cho Mojo `feature` block và constant. Và một finding Mojo cũng không tự chứng minh runtime sẽ lỗi; nó chỉ chỉ ra IPC contract đã đổi, cùng nơi Samsung cần đi tìm.

### 7.8. `chrome://flags` metadata

File `chrome/browser/flag-metadata.json` chứa tên entry, owner upstream và `expiry_milestone` của các mục trong `chrome://flags`.

Thông tin quan trọng nhất là milestone hết hạn, vì nó giúp dự đoán flag nào Chromium dự định dọn trong các version tới. Nhưng phải đọc kèm ba lưu ý:

- entry bị xoá **không** đồng nghĩa feature bị xoá;
- feature có thể đã bật mặc định từ trước, và Chromium chỉ đang dọn nút thử nghiệm;
- đổi `expiry_milestone` thường chỉ là đổi lịch, không phải đổi hành vi.

Vì vậy finding từ file này chủ yếu phục vụ việc lập kế hoạch và nằm ở nhóm Housekeeping — trừ khi có thêm signal từ chính khai báo feature.

### 7.9. Ba loại file của WebUI

WebUI cần đọc **ba lớp cùng nhau**. Đọc thiếu một lớp là nguồn gốc của phần lớn kết luận sai về giao diện.

**Lớp 1 — Route: `route.ts` và `routes.ts`**

Chỉ các file có đúng tên này, nằm dưới `chrome/browser/resources/`, mới được đọc. Công cụ lấy hằng route, URL path, quan hệ cha-con, và khoá `loadTimeData` dùng làm guard.

Một route bị xoá chưa chắc nghĩa là page biến mất; có thể page đã chuyển route hoặc chỉ đổi guard.

**Lớp 2 — Template: `.html` và `.html.ts`**

Đây là template Polymer và Lit. Công cụ lấy loại control, pref binding, element id, label và điều kiện GRIT. Nhờ đó nó phát hiện được các trường hợp như toggle đổi thành dropdown, hoặc control chuyển sang pref khác.

Công cụ không đánh giá CSS, layout, screenshot, hay toàn bộ hành vi TypeScript.

**Lớp 3 — C++ WebUI handler: `.cc` dưới `chrome/browser/ui/webui/`**

Đây là ngoại lệ duy nhất không dựa vào mẫu tên file: **mọi** `.cc` trong thư mục handler đều được xem xét. Công cụ tìm các lệnh `AddBoolean`, `AddString`, `AddInteger`, `AddDouble` và các phép kiểm tra `base::Feature`.

Nhờ đó nó nối được hai chuỗi:

```text
route guard → loadTimeData key → C++ handler → base::Feature
control → pref key
```

Nếu chỉ đọc template mà không đọc handler, báo cáo sẽ biết một page bị gate, nhưng không biết feature nào đứng sau gate đó — và đó chính là thông tin cần để quyết định.

### 7.10. Những file cố tình chưa đọc

Bảng này quan trọng khi trình bày, vì nó cho thấy các khoảng trống đã được biết trước chứ không phải bị bỏ sót:

| Nhóm file | Vì sao chưa đọc | Hậu quả đối với report |
|---|---|---|
| C++ `.cc/.h` thông thường | Chưa có parser cho phần thân function | Thay đổi logic bên trong function có thể bị bỏ sót |
| `BUILD.gn` | Chưa parse toàn bộ build graph | Một số build flag chỉ được ghi là `conditional`; không thể thay build để xác nhận |
| TypeScript/JavaScript thông thường | Chỉ route và template WebUI được hỗ trợ | Thay đổi về event handling hoặc business logic có thể không xuất hiện |
| CSS, image, string resource `.grd/.grdp` | Không tạo ra contract mà schema hiện tại so sánh | Report không đánh giá layout, visual hay thay đổi câu chữ |
| Output sinh tự động | Dễ tạo nhiễu và có thể tái sinh từ source | Công cụ ưu tiên khai báo gốc trong source |
| Test, fuzzer, mock | Không ship trong sản phẩm browser | Không đưa feature chỉ phục vụ test vào report sản phẩm |
| Source chỉ dành cho Android, ChromeOS, iOS, macOS, Linux hoặc Fuchsia | Project đang phân tích Samsung Browser trên Windows | Không để finding của nền tảng khác chiếm ưu tiên; riêng một số pref/switch vẫn được nhìn để nhận ra file move |
| Third-party được vendor sẵn, ngoài Blink | Extractor không được viết cho dialect của các project đó | Không tạo finding với độ tin cậy giả |

### 7.11. Cách tự kiểm tra một loại file có được cover đúng không

Khi reviewer hoặc owner nghi ngờ một finding bị thiếu, có thể kiểm tra theo năm câu hỏi:

1. File đó có chứa loại khai báo mà một trong chín extractor hỗ trợ không?
2. `applies_to(path)` của extractor có nhận đúng đường dẫn và tên file không?
3. Bộ file đang chạy là `default` hay `wide`, và đường dẫn có nằm trong phạm vi được tải không?
4. File có bị loại vì là test, vì thuộc binary khác, vì là third-party, hoặc vì thuộc nền tảng ngoài Windows không?
5. Coverage của đúng nhóm file ở version đó là bao nhiêu, và report có ghi nhận file mục tiêu bị thiếu hoặc lỗi parser nào không?

Nếu có bất kỳ câu trả lời nào là "không", báo cáo **không** được dùng để kết luận rằng đối tượng chắc chắn không tồn tại hoặc đã bị xoá.

Đây chính là lý do lần lập kế hoạch chính thức nên dùng `wide`, và luôn đọc coverage theo từng nhóm chứ không chỉ nhìn con số tổng.

## 8. Chín bộ trích xuất và mười sáu loại Fact

Mỗi extractor là một parser nhỏ, chuyên đọc một nhóm file và chỉ lấy ra những thuộc tính cần cho việc so sánh phiên bản. Công cụ hiện có chín extractor.

### 8.1. `base_features`

Đọc các file C++ khai báo feature và tạo hai loại `Fact`:

- `base_feature`: tên feature, biến C++, trạng thái mặc định, trạng thái trên Windows, và điều kiện `#if` bao quanh.
- `feature_param`: feature sở hữu param, tên param, kiểu C++, biến C++, và giá trị mặc định.

Chromium đã dùng ba cách viết khác nhau cho cùng một feature: macro `BASE_FEATURE` có ba đối số, macro mới có hai đối số, và dạng cũ `const base::Feature`. Extractor hiểu cả ba và đưa chúng về cùng một cấu trúc.

Điều đáng theo dõi nhất trong nhóm này là **trạng thái mặc định đổi từ tắt sang bật**, vì đó thường là lúc hành vi mới bắt đầu áp dụng rộng rãi.

### 8.2. `blink_runtime`

Đọc đúng file `runtime_enabled_features.json5` và tạo `blink_runtime_feature`, gồm:

- trạng thái chung, trạng thái theo từng nền tảng, và riêng `windows_status`;
- feature C++ đứng phía sau runtime flag này;
- dependency, Origin Trial, và cách API được expose.

Khi trạng thái chuyển từ `experimental` sang `stable`, Web API có thể bắt đầu được cung cấp mặc định cho website. Điều này khác hẳn với việc một flag mới chỉ được khai báo trong source nhưng chưa được bật.

### 8.3. `web_idl`

Chỉ đọc Blink IDL dưới `third_party/blink/renderer/`, tạo hai loại `Fact`:

- `idl_interface`: interface, dictionary, namespace hoặc enum; kèm quan hệ kế thừa và các thuộc tính mở rộng.
- `idl_member`: method hoặc property thuộc interface nào, kiểu dữ liệu, signature đã chuẩn hoá, và runtime gate.

Chrome Extensions IDL và Windows MIDL cũng dùng đuôi `.idl`, nhưng cú pháp và mục đích khác Blink Web IDL nên bị loại. Nguyên tắc ở đây: nếu cố đọc sai loại IDL, công cụ sẽ tạo ra finding sai — mà ghi rõ "chưa hỗ trợ" thì an toàn hơn nhiều.

Một Web IDL method có thể có nhiều overload. Công cụ gộp các overload cùng tên vào một `Fact`, nhưng vẫn giữ toàn bộ signature và vị trí source của từng overload. Nhờ vậy, việc bỏ đi một overload không bị che mất bởi các overload còn lại.

### 8.4. `mojom`

Đọc `.mojom` và tạo năm loại `Fact`:

- `mojo_interface`
- `mojo_method`
- `mojo_struct`
- `mojo_field`
- `mojo_enum`

Các `Fact` này giữ lại:

- tên đầy đủ, gồm cả module và type;
- signature của method, tham số request và response;
- ordinal được khai báo trực tiếp;
- vị trí của member trong interface có đánh dấu `[Stable]`;
- dữ liệu là struct hay union;
- kiểu, giá trị mặc định và `MinVersion` của field;
- các phần tử enum và điều kiện build.

Nhắc lại để tránh nhầm: Mojo là IPC framework nối các process của Chromium — browser, renderer, GPU, network. `Interface` ở đây là contract để hai đầu giao tiếp với nhau, **không phải giao diện người dùng**.

Nếu cả hai đầu đều được sinh lại từ cùng source Chromium, một thay đổi có thể vẫn build bình thường. Nhưng nếu Samsung tự triển khai hoặc sửa riêng một đầu, method hoặc data type mới có thể không còn khớp với đầu còn lại.

### 8.5. `constants`

Đọc các C++ string constant dùng làm command-line switch hoặc pref key, tạo hai loại `Fact`:

- `switch`: key là tên đứng sau dấu `--`, ví dụ `enable-features`; ngoài ra giữ biến C++ và trạng thái trên Windows.
- `pref`: key là tên dùng để lưu setting trong user profile; ngoài ra giữ biến C++ và trạng thái trên Windows.

Extractor hiểu cả dạng `char kFoo[]` và `std::string_view kFoo`.

Cần phân biệt rành mạch **ba cái tên** trong nhóm này: switch name là tên mà script truyền vào khi mở browser; pref key là tên dùng để lưu và đọc setting trong user profile; còn biến C++ là symbol mà source code gọi trực tiếp.

### 8.6. `flags_metadata`

Đọc `chrome/browser/flag-metadata.json`, tạo `flag_entry` với:

- tên entry;
- `expiry_milestone`;
- owner upstream, để tham khảo.

Đây là nguồn duy nhất trong cả pipeline nói trực tiếp về công việc **tương lai**: flag nào sắp hết hạn.

### 8.7. `webui_routes`

Đọc `route.ts` và `routes.ts`, tạo `webui_route` gồm:

- WebUI page chứa route, tên và path của route, quan hệ cha-con;
- các điều kiện `loadTimeData.getBoolean(...)` quyết định route có xuất hiện hay không.

Một route có mặt trong source chưa chắc nghĩa là người dùng nhìn thấy page đó — điều kiện guard có thể đang ẩn nó. Vì vậy công cụ phải giữ cả route lẫn điều kiện hiển thị.

### 8.8. `webui_controls`

Đọc Polymer `.html` và Lit `.html.ts`, tạo `webui_control` gồm:

- WebUI page và file chứa control;
- loại control: toggle, dropdown, radio hay button;
- pref mà control đọc/ghi, lấy từ `prefs.x.y` hoặc `pref-key`;
- khoá label i18n, element id, và điều kiện GRIT quyết định control có nằm trong Windows build hay không.

Công cụ không chỉ dựa vào một danh sách tag viết tay. Một element được coi là control khi nó bind với pref, có vai trò tương tác rõ ràng, hoặc có `id`/label đủ ổn định để theo dõi qua các phiên bản.

Cách làm này hỗ trợ được cả những control mới, mà không phụ thuộc vào vị trí của element trong file — vốn là thứ rất dễ thay đổi mỗi khi UI được refactor.

### 8.9. `webui_gates`

Đọc các C++ handler dưới `chrome/browser/ui/webui/`, tạo `webui_gate` gồm:

- khoá `loadTimeData` và C++ handler đã tạo ra khoá đó;
- kiểu dữ liệu được thêm bằng `AddBoolean`, `AddString`, `AddInteger` hoặc `AddDouble`;
- biểu thức đã rút gọn, cùng những `base::Feature` được kiểm tra bằng `IsEnabled`.

Mối liên hệ chính trong WebUI, viết gọn lại:

```text
route.ts --guard--> loadTimeData key --handler expression--> base::Feature
template control ----------------------pref binding--------> preference key
```

## 9. Fact là gì?

`Fact` không phải một dòng source được chép sang JSON. Nó là một object đại diện cho **một khai báo**, với khoá ổn định và đúng những thuộc tính cần thiết để so sánh hai phiên bản.

Data model chung:

```json
{
  "kind": "base_feature",
  "key": "AAPMBlocksWebGPU",
  "name": "AAPMBlocksWebGPU",
  "path": "gpu/config/gpu_finch_features.cc",
  "line": 291,
  "attrs": {
    "var": "kAAPMBlocksWebGPU",
    "default_state": "enabled",
    "platform_state": {"windows": "enabled"},
    "declared_form": "macro2",
    "conditions": []
  }
}
```

Định danh dùng khi so sánh được ghép từ hai trường đầu:

```text
uid = kind + ":" + key
```

Vai trò của các trường còn lại: `name` để hiển thị; `path` và `line` chỉ về đúng chỗ trong source; `attrs` chứa các thuộc tính kỹ thuật của khai báo.

### 9.1. Tại sao Fact có những thuộc tính này?

Một thuộc tính được giữ lại vì **ít nhất một** trong năm lý do sau:

- Giúp nhận ra cùng một khai báo ở hai phiên bản.
- Cho biết hành vi hoặc contract có thực sự thay đổi không.
- Cho biết khai báo có nằm trong Windows build không.
- Cho phép nối với một `Fact` liên quan — ví dụ WebUI gate nối tới feature.
- Giúp report giải thích finding và chỉ về source.

Nhưng **không phải thuộc tính nào cũng được dùng để tạo ra thay đổi.** Ví dụ, `declared_form: macro2/macro3/legacy` cho biết feature được viết bằng dạng macro nào. Thông tin này hữu ích khi kiểm tra source, nhưng đổi cách viết macro không đổi hành vi — nên nó không nằm trong `MEANINGFUL_ATTRS`, tức danh sách thuộc tính được phép sinh ra finding.

### 9.2. Key của từng loại fact

Cột bên phải quan trọng hơn vẻ ngoài của nó: nó giải thích vì sao khoá được chọn như vậy, và đó là lý do công cụ ghép đúng hai phiên bản với nhau.

| Loại Fact | Key dùng để ghép hai phiên bản | Vì sao chọn key đó |
|---|---|---|
| `base_feature` | Tên nhận diện feature | Server và tùy chọn `--enable-features` dùng tên này để xác định đúng tính năng cần bật hoặc tắt |
| `feature_param` | `owner/name`, nếu thiếu owner thì dùng `path:name` | Cùng một tên param có thể thuộc nhiều feature khác nhau |
| `blink_runtime_feature` | Tên feature trong manifest | Dùng để nối runtime gate với feature C++ và với Chromestatus |
| `idl_interface` | Tên interface | Đại diện ổn định cho một Web API |
| `idl_member` | `Interface.member` | Các overload cùng tên được gộp trong một `Fact` |
| `mojo_interface` | `module.Interface` | Phân biệt các interface trùng tên ở module khác nhau |
| `mojo_method` | `module.Interface.Method` | Signature là thuộc tính cần so sánh, không phải một identity mới |
| `mojo_struct` | Tên đầy đủ của type | Phân biệt type theo module chứa nó |
| `mojo_field` | `QualifiedType.field` | Kiểu và ordinal của field là thuộc tính cần so sánh |
| `mojo_enum` | Tên đầy đủ của enum | Danh sách phần tử được giữ trong `attrs` |
| `switch` | Tên tùy chọn khởi động | Script truyền tên này vào browser dưới dạng `--tên-tùy-chọn` |
| `pref` | Chuỗi định danh preference | Tên dùng để lưu và đọc lại thiết lập trong hồ sơ người dùng |
| `flag_entry` | Tên entry trong metadata của `chrome://flags` | Theo dõi đúng entry và milestone hết hạn của nó |
| `webui_route` | `surface/ROUTE_CONST` | Cùng một route constant có thể xuất hiện ở WebUI page khác |
| `webui_control` | `surface/page/file/stable-ident` | Tránh trùng tên giữa các page và giữ identity khi migrate Polymer → Lit |
| `webui_gate` | `handler/data_key` | Cùng một data key có thể được tạo bởi nhiều handler |

### 9.3. Chuẩn hoá thành Fact diễn ra thế nào?

Bốn ví dụ quan trọng nhất:

**Migrate macro**

```text
BASE_FEATURE(kFoo, "Foo", ENABLED)
BASE_FEATURE(kFoo, ENABLED)
```

Cả hai đều tạo ra `key = Foo`. Nếu khoá phụ thuộc vào cách viết nguyên văn, việc Chromium đổi dạng macro sẽ làm hàng loạt feature bị báo nhầm là **xoá rồi thêm lại** — và cả một release sẽ ngập trong finding giả.

**Khoảng trắng trong signature**

Công cụ chuẩn hoá khoảng trắng trong signature của Web IDL và Mojo, nhưng vẫn giữ nguyên nội dung string literal. Kết quả: chỉ format lại code thì không tạo finding, nhưng đổi một giá trị mặc định thì vẫn được phát hiện.

**Trạng thái trên Windows**

C++ `#if`, GRIT `<if expr>` và Mojo `[EnableIf]` đều được quy về ba trạng thái chung:

- `compiled` — có trong Windows build;
- `not_compiled` — không có trong Windows build;
- `conditional` — còn phụ thuộc vào một build flag khác mà công cụ chưa thể kết luận.

**Overload**

Nhiều khai báo Web IDL có cùng tên member được gộp thành một nhóm overload. Công cụ vẫn giữ từng signature riêng, nên việc thêm hoặc bỏ một overload không bị bước loại trùng che mất.

### 9.4. Dedupe

Chromium có thể chứa nhiều khai báo cùng tạo ra một UID. Với hầu hết các loại `Fact`, công cụ chọn khai báo có `(path, line)` đứng trước theo thứ tự chữ cái.

Cần đọc rule này cho đúng: đây **không** phải khẳng định rằng khai báo được chọn là bản "chính". Mục đích duy nhất là để hai máy khác nhau, hoặc hai lần chạy khác nhau, luôn chọn cùng một bản.

Riêng `idl_member` có xử lý đặc biệt: các overload được gộp **trước** khi chọn `Fact` đại diện, và `overload_locations` vẫn giữ vị trí của mọi khai báo liên quan để người đọc mở đúng source.

## 10. Snapshot chứa gì?

Mỗi version tạo ra một `Snapshot`:

```text
Snapshot
  schema
  ref, milestone, created
  facts[]
  counts by fact kind
  meta
    target_set / partitions / complete
    platform
    coverage overall + by_surface
    uncovered_files
    fetch_stats / fetch_seconds
    missing_targets
    extract_stats / parser errors
    milestone_info
```

Tạo `Snapshot` là bước tốn thời gian nhất, vì phải tải và đọc source. Vì vậy kết quả được lưu trong cache.

Lợi ích rất cụ thể: sau khi đã có snapshot, có thể sửa logic so sánh, sửa cách chấm điểm hoặc sửa report rồi chạy lại rất nhanh, mà không cần tải source lần nào nữa.

## 11. So sánh Fact đi sâu

### 11.1. Các điều kiện kiểm tra trước khi so sánh

Công cụ **từ chối** so sánh trong ba trường hợp:

- Hai snapshot được tạo từ bộ file, partition hoặc chế độ `complete` khác nhau.
- Với lần chạy có từ 500 `Fact` trở lên, một phía có ít hơn một nửa số `Fact` của phía kia.
- Một phía rỗng trong khi phía kia có dữ liệu.

Cả ba đều là dấu hiệu của lỗi chuẩn bị dữ liệu, không phải của thay đổi thật trong Chromium.

Ngoài ra, lệnh `run` còn kiểm tra thêm ba thứ:

- Có `Fact` nào đến từ file nằm ngoài phạm vi đã khai báo không.
- Có file hoặc thư mục mục tiêu nào tải thiếu không.
- Có liên kết giữa các `Fact` trỏ tới đối tượng không tồn tại không.

### 11.2. Pairing

Hai snapshot được lập chỉ mục theo `Fact.uid`, rồi ghép theo ba trường hợp:

- Chỉ có ở TO → `added`.
- Chỉ có ở FROM → `removed`.
- Có ở cả hai → so sánh các thuộc tính có ý nghĩa.

### 11.3. Chỉ so những thuộc tính có thể làm thay đổi ý nghĩa

| Kind | Thuộc tính được compare |
|---|---|
| Base feature | Windows/default state, conditions, C++ var |
| Feature param | Default, type, owner feature, var, platform state |
| Blink runtime | Status, backing feature, dependency, origin-trial/exposure fields |
| IDL interface/member | Kind, inheritance, enum values, signature/overload set, extended attributes, runtime gate |
| Mojo method | Signature, params, response, attrs, ordinal, stable position, platform state |
| Mojo data | Type/ordinal/default/MinVersion, struct-vs-union, enum values, stability/platform state |
| Pref/switch | C++ variable, platform state |
| WebUI | Route/parent/guards, control type/pref/label/build conditions, gate expression/features |

Hai rule bổ sung đáng chú ý:

**Khai báo chuyển file.** Nếu đường dẫn đổi nhưng các thuộc tính khác giữ nguyên, công cụ tạo delta cho `path` và gắn signal `declaration_moved`.

**Vị trí trong Mojo.** Thuộc tính `position` chỉ được so khi nó có mặt ở **cả hai phía**, và chỉ áp dụng cho khai báo Mojo có `[Stable]`. Nhờ rule này, khi `[Stable]` bị bỏ khỏi cả một interface, công cụ không biến một thay đổi ở mức interface thành hàng trăm thay đổi ordinal giả ở từng member.

### 11.4. Rename và identity move

Sau lượt ghép chính, công cụ tìm thêm các cặp "bị xoá" và "được thêm" có khả năng thực ra là cùng một đối tượng đã đổi tên:

- Pref, switch hoặc base feature có cùng biến C++ nhưng khác string key → **rename**.
- WebUI control cùng surface/page/id-hoặc-label nhưng khác pref phía sau → **repoint**.

Đây là bước quan trọng, vì chính cái khoá dùng để nhận diện đối tượng đã thay đổi. Nếu không ghép lại, một pref đổi tên sẽ xuất hiện thành hai dòng trông không liên quan gì tới nhau: một dòng bị xoá và một dòng được thêm.

Report khi đó sẽ che mất hậu quả thật, vốn là: browser có thể không còn đọc được giá trị cũ trong user profile, và setting của người dùng quay về mặc định.

### 11.5. Change object

Một ví dụ thật, từ M148 → M151:

```json
{
  "change_type": "modified",
  "kind": "mojo_field",
  "key": "blink.mojom.CommitNavigationParams.early_hints_preloaded_resources",
  "deltas": {
    "type": [
      "array<url.mojom.Url>",
      "array<network.mojom.LinkHeader>"
    ]
  },
  "locations": [
    "third_party/blink/public/mojom/navigation/navigation_params.mojom:571",
    "third_party/blink/public/mojom/navigation/navigation_params.mojom:575"
  ],
  "signals": ["ipc_shape_changed"],
  "severity": 80
}
```

Object này trả lời đủ ba câu hỏi mà một người review cần: **đối tượng nào đổi**, **giá trị cũ và mới là gì**, và **cần mở file nào để kiểm tra**.

## 12. Từ delta đến signal

`Signal` là kết luận cụ thể mà bộ so sánh suy ra từ ba thứ: loại `Fact`, hướng thay đổi, và phần giá trị khác nhau. Một số ví dụ:

- `enabled_by_default`
- `flag_retired_on`
- `feature_symbol_renamed`
- `pref_renamed`
- `web_api_shipped`
- `web_api_overload_removed`
- `ipc_signature_change`
- `ipc_shape_changed`
- `ui_page_regated`
- `ui_control_repointed`
- `flag_expiring`

Một thay đổi có thể tạo ra nhiều signal cùng lúc. **Leading signal** là signal có severity cao nhất; nếu bằng điểm, công cụ chọn theo tên để kết quả luôn ổn định.

Leading signal quyết định ba việc:

1. Đặt severity.
2. Chọn bucket.
3. Có thể chuyển finding sang owner khác, nếu nơi cần sửa không phải nơi khai báo nằm.

Nếu không suy ra được signal cụ thể nào, công cụ dùng mức điểm nền từ `BASE_SEVERITY[(kind, direction)]`. Điểm nền này chỉ là phương án dự phòng, và **không** được phép ghi đè severity của một signal rõ ràng hơn.

## 13. Bucket nói gì?

| Bucket | Ý nghĩa phía upstream | Cách team Samsung nên đọc |
|---|---|---|
| Breaking | API, IPC hoặc key bên ngoài binary có thể không còn tương thích | Tìm nơi Samsung sử dụng; chỉ trở thành blocker khi có sử dụng thật |
| Behaviour change | Hành vi mặc định trên Windows đã đổi | Xác nhận patch, test hoặc hành vi sản phẩm nào đang phụ thuộc hành vi cũ |
| New surface | Có API, feature hoặc control mới xuất hiện | Có thể là cơ hội sản phẩm hoặc vùng cần test thêm; không mặc định là blocker |
| Housekeeping | Dọn code, cập nhật lịch, hoặc bằng chứng chưa đủ mạnh | Không cần đọc từng dòng; nhưng nên lọc riêng flag sắp hết hạn và config cũ cần dọn |

Nhắc lại điều dễ bị nói quá nhất: `Breaking` mô tả **loại thay đổi trong Chromium gốc**, không có nghĩa Samsung Browser chắc chắn bị lỗi. Chỉ sau khi tìm thấy nơi Samsung đang dùng contract đó mới có thể kết luận về ảnh hưởng.

## 14. Owner routing

| Owner key | Label trong report | Surface | Câu hỏi tiếp theo |
|---|---|---|---|
| `ipc` | Process boundaries | Mojo interface/method/data | Samsung có custom caller/implementation/peer nào không? |
| `webplatform` | Web platform | Blink runtime + Web IDL | API có reachable không, site hoặc feature Samsung có dùng không? |
| `native` | Browser C++ | Features, prefs, switches | Fork có reference symbol, override default, hoặc persist key không? |
| `webui` | WebUI front-end | Route/control/gate | Samsung có patch, custom screen, custom control hoặc backing pref không? |
| `config` | Outside the repository | Tên feature và giá trị mà server dùng để bật/tắt thử nghiệm, script khởi động, lịch hết hạn | Tìm trong config/automation/policy ngoài source tree |

Loại `Fact` quyết định owner mặc định. Nhưng một số signal sẽ **chuyển owner**, vì nơi cần sửa khác với nơi khai báo nằm.

Ví dụ rõ nhất: feature name được khai báo trong C++, nhưng khi tên đó đổi, hệ thống phía server đang dùng tên cũ cũng phải cập nhật. Vì vậy finding này được giao cho owner `config`, chứ không chỉ cho team C++.

## 15. Severity và score khác nhau như thế nào?

### 15.1. Severity

Severity trả lời:

> "Nếu Samsung đang phụ thuộc vào phần này, bản chất thay đổi nghiêm trọng đến đâu?"

Ví dụ:

- Kiểu hoặc ordinal của Mojo field đổi, hay method signature đổi: 80.
- Web API bị xoá: 70.
- Feature chuyển sang bật mặc định trên Windows: 75.
- Loại WebUI control thay đổi: 45.
- Chỉ dời ngày hết hạn của flag: 10.

Severity không phải số ngày công, và cũng không phải xác suất xảy ra lỗi.

### 15.2. Score

Score trả lời một câu khác:

> "Với bằng chứng của **chính lần chạy này**, finding nên được ưu tiên ở mức nào?"

Công thức rút gọn:

```text
severity = severity của leading signal
           hoặc base prior nếu không có signal

score = 0
        nếu declaration không được compile vào Windows ở cả FROM và TO

score = clamp(severity - 15, 0, 100)
        nếu conclusion dựa trên absence mà run chưa confirm được

score = severity
        trong các trường hợp còn lại
```

Hai tính chất đi cùng nhau: công cụ **không bao giờ cộng điểm vượt quá severity**, và mọi lần trừ điểm đều phải có lý do ghi trong `reasons`. Nghĩa là score luôn bằng hoặc thấp hơn severity, và khoảng chênh lệch luôn giải thích được.

### 15.3. "Không nằm trong Windows build"

Score chỉ bằng 0 khi khai báo có trạng thái `not_compiled` ở **tất cả các phiên bản mà nó tồn tại**. Ba trường hợp:

- Chỉ dành cho Android ở cả bản cũ lẫn bản mới → score 0, bucket Housekeeping.
- Có trong Windows build ở bản cũ nhưng bị loại ở bản mới → giữ nguyên severity, vì chính việc bị loại là thay đổi cần xem.
- Bắt đầu được đưa vào Windows build ở bản mới → cũng giữ nguyên severity.

### 15.4. Khi chưa đủ bằng chứng để kết luận một khai báo đã biến mất

Công cụ đánh dấu `removed` khi thấy một `Fact` ở bản cũ nhưng không thấy ở bản mới. Nhưng nếu lần chạy chỉ đọc một phần source, đối tượng có thể đã chuyển sang một file chưa được tải, chứ chưa chắc bị xoá.

Vì vậy coverage được xét riêng cho **từng nhóm file**. Hai con số dưới đây cho thấy sự chênh lệch lớn đến mức nào, và vì sao không thể dùng một con số tổng:

- Với Web IDL, bộ `default` đọc **2.166 trên 2.170** file ứng viên ở M151. Mức này gần như đủ để tin rằng một API thực sự đã biến mất.
- Với pref và switch, bộ `default` chỉ đọc **9 trên 529** file ứng viên. Mức này hoàn toàn không đủ để kết luận một key đã bị xoá.

Ngưỡng xác nhận hiện là **95%**. Nếu coverage thấp hơn ngưỡng, finding dựa trên việc "không còn thấy" bị trừ 15 điểm. Riêng pref và switch chưa xác nhận được sẽ bị đưa về Housekeeping, vì kết luận an toàn lúc này chỉ là *"đã xoá, hoặc đã chuyển sang nơi chưa đọc"*.

Chiều ngược lại thì khác: một khai báo nhìn thấy rõ ở bản mới **không** bị trừ điểm chỉ vì coverage ở bản cũ thấp. Công cụ chỉ hạ độ tin cậy khi bản cũ có lỗi chắc chắn — thiếu file mục tiêu, hoặc parser thất bại — vì khi đó nó không thể chứng minh khai báo này thực sự mới.

### 15.5. Ba ví dụ

**Mojo data shape đổi**

```text
severity 80: ipc_shape_changed
Windows: có trong build
delta nhìn thấy ở cả hai phía, không dựa trên absence
score = 80, bucket = Breaking
```

**Feature flag LNA bị remove trong default run**

```text
prior Windows state = enabled
signal = flag_retired_on, severity 35
feature-file coverage tại TO ≈ 12%
removal chưa confirm → -15
score = 20, bucket vẫn Housekeeping
```

Với bộ `wide`, gần như toàn bộ file feature đều được đọc. Nếu không có lỗi tải hoặc lỗi parser, khoản trừ do thiếu coverage sẽ được bỏ đi.

**Android-only declaration đổi**

```text
platform_state.windows = not_compiled ở cả hai phía
score = 0, bucket = Housekeeping
```

## 16. Coverage được đo ra sao?

Trước hết, hai điều coverage **không** phải: nó không phải số file đã tải về, và cũng không phải một con số viết cố định trong code.

Công cụ tính lại coverage cho từng version, theo năm bước:

1. Lấy toàn bộ danh sách đường dẫn của đúng Git ref.
2. Hỏi từng extractor xem nó có thể đọc file nào.
3. Loại các file không thuộc sản phẩm browser hoặc không liên quan Windows.
4. Chia các file ứng viên theo nhóm: Mojo, Web IDL, pref/switch, WebUI...
5. Đối chiếu với bộ `default` hoặc `wide` để tính số file đã đọc và số file chưa đọc.

Kết quả được lưu trong snapshot và trong report, chứ không chỉ in ra log.

### 16.1. Số liệu M151 hiện có

| Surface denominator | Default read | Wide read | Candidate files |
|---|---:|---:|---:|
| Feature flags | 363 | 2,971 | 3,011 |
| Prefs and switches | 9 | 526 | 529 |
| Mojo | 367 | 1,439 | 1,463 |
| Blink Web IDL | 2,166 | 2,166 | 2,170 |
| WebUI controls | 434 | 1,031 | 1,031 |
| WebUI gates | 537 | 537 | 537 |
| WebUI routes manifest | 1 | 1 | 1 |
| Blink runtime manifest | 1 | 1 | 1 |
| Flag metadata | 1 | 1 | 1 |

Tổng thể:

- `default`: 3,677 / 8,366 file ứng viên, tức 43,95%.
- `wide`: 8,295 / 8,366 file ứng viên, tức 99,15%.

**Một điểm rất dễ hiểu sai về bảng trên:** số file không phản ánh trực tiếp số khai báo lấy được.

Bộ `default` được thiết kế để ưu tiên các file lớn chứa nhiều feature. Vì vậy, dù chỉ đọc khoảng 12% số file feature, nó vẫn lấy được gần một nửa số `base::Feature` mà bộ `wide` tìm thấy ở M151.

Đó là lý do coverage chỉ được dùng để **hạ độ tin cậy khi kết luận "đã biến mất"**. Nó không được coi là xác suất finding đúng.

### 16.2. Reference closure

Sau khi tạo snapshot, công cụ kiểm tra xem các liên kết giữa các `Fact` có tìm được đầu còn lại hay không:

- Route guard → WebUI gate.
- Gate → base feature.
- Control → preference.
- Blink flag → base feature.
- Feature param → owner feature.

Ở M151:

- `default` còn 180 liên kết chưa tìm được đầu kia.
- `wide` còn 89 liên kết chưa tìm được đầu kia.

Một liên kết chưa tìm thấy đầu còn lại **không** tự động có nghĩa là parser sai. Đối tượng đích có thể nằm ngoài bộ file, có thể dùng cú pháp chưa được hỗ trợ, hoặc chỉ tồn tại trong một cấu hình khác.

Report ghi rõ con số này để người đọc biết phần ngữ cảnh nào còn thiếu, thay vì âm thầm bỏ qua.

## 17. Gom các finding liên quan thành một câu chuyện

Một thay đổi chức năng trong Chromium thường tạo ra nhiều finding nằm rải rác ở các nhóm khác nhau. Module `cluster.py` gom chúng lại, dựa trên các liên kết rõ ràng mà extractor đã tìm thấy:

- Route dùng một guard cụ thể.
- Guard kiểm tra một feature cụ thể.
- `FeatureParam` thuộc một feature cụ thể.
- Blink runtime flag trỏ tới feature C++ đứng sau nó.
- WebUI control và route có cùng tên hoặc cùng `id` sau khi chuẩn hoá.

Ba điều bước này **không** làm: nó không dùng AI, không dựa trên độ giống nhau mơ hồ của câu chữ, và không đổi score hay bucket. Nó chỉ giúp người đọc mở các finding liên quan cùng nhau.

### Ví dụ Local Network Access

Từ M148 đến M151, công cụ gom được bảy finding liên quan tới Local Network Access, qua route, control, gate và feature:

- Route cũ `SITE_SETTINGS_LOCAL_NETWORK_ACCESS` bị xoá.
- Route `SITE_SETTINGS_LOCAL_NETWORK` đổi guard.
- Biểu thức quyết định hiển thị đổi.
- Gate cho split permissions bị xoá.
- Control cũ biến mất.
- `LocalNetworkAccessChecksSplitPermissions` được dọn bỏ sau khi hành vi mới đã bật mặc định.

Đây là ví dụ điển hình cho việc đọc từng dòng sẽ dẫn tới kết luận sai. Nếu chỉ nhìn dòng "route bị xoá", người đọc rất dễ kết luận rằng page đã bị mất.

Nhưng khi đọc cả nhóm cùng với trạng thái cũ của feature flag, bức tranh thật hiện ra: chức năng đã chuyển sang cơ chế split permissions **từ trước**, và M151 chủ yếu chỉ dọn flag cùng route cũ.

Đây chính là lý do report cần nối các thay đổi liên quan lại với nhau, thay vì chỉ liệt kê từng dòng diff.

## 18. Thông tin bổ sung từ Chromestatus

Bước này **không bắt buộc** và **không ảnh hưởng đến score**.

- Công cụ lấy thông tin về Web Platform feature theo milestone, và cache trong file `mNNN.json`.
- Thông tin giữ lại gồm: mô tả ngắn, spec URL, category, và trạng thái phát hành nếu có.
- Việc ghép Chromestatus với từng finding chỉ dùng tên trùng khớp chính xác. Cách ghép này có giới hạn rõ ràng, vì Chromestatus dùng tên dành cho người đọc, còn source thường dùng identifier.
- Vì vậy thông tin Chromestatus chỉ là **bối cảnh tham khảo**, không phải bằng chứng quyết định cho bất kỳ finding nào.

Khi chạy offline hoặc dùng `--no-enrich`, report vẫn có đầy đủ `Fact`, thay đổi và score; chỉ thiếu phần bối cảnh từ Chromestatus.

## 19. Report gồm những gì?

Cùng một dữ liệu được xuất ra ba định dạng, cho ba mục đích khác nhau.

### 19.1. `report.json`: dữ liệu đầy đủ cho automation

Cấu trúc ở mức trên cùng:

```text
schema
from_ref, to_ref
summary
meta
bucket_counts
findings[]
```

Phần `summary` chứa:

- Tổng số thay đổi, và số lượng theo từng loại `Fact` cùng hướng thay đổi.
- Số lượng theo bucket, theo owner, theo nhóm hậu quả, và theo leading signal.
- Số finding không nằm trong Windows build.
- Tóm tắt các nhóm finding liên quan.
- Thông tin Chromestatus theo milestone, nếu được bật.

Phần `meta` chứa:

- Nền tảng, thời gian tạo, và version của công cụ.
- Bộ file, partition và cờ `complete`.
- Số `Fact` của bản cũ và bản mới.
- Coverage tổng và coverage của từng nhóm, ở cả hai phía.
- File chưa đọc, file mục tiêu bị thiếu, và các liên kết chưa tìm thấy đầu còn lại.
- Những `Fact` bị phát hiện nằm ngoài phạm vi đã khai báo.

Mỗi `finding` có dạng:

```text
change
  change_type, kind, key, name
  before, after
  deltas
  paths, locations
  signals, severity
score
bucket
reasons[]
enrichment
```

**Một giới hạn hiện tại cần biết:** phần tổng hợp đã có số lượng theo owner, và bản HTML/Markdown cũng hiển thị owner — nhưng từng finding trong `report.json` chưa chứa trực tiếp trường này.

Hệ quả thực tế: một script đọc JSON muốn lọc theo owner phải dùng lại hàm mapping của project. Roadmap nên bổ sung `owner` vào từng finding, để JSON tự đủ thông tin mà không cần gọi ngược vào code.

### 19.2. `report.md`: bản đọc nhanh để đưa vào ticket hoặc wiki

Bản Markdown được sắp xếp theo đúng thứ tự nên đọc:

1. Số lượng và ý nghĩa của bốn bucket.
2. Owner nào có việc cần kiểm tra.
3. Loại thay đổi nào đã xảy ra, nhóm theo leading signal.
4. WebUI page nào có thay đổi.
5. Các finding có liên quan với nhau.
6. Chi tiết theo thứ tự Breaking → Behaviour change → New surface.
7. Lý do chấm điểm.
8. Nguồn dữ liệu, coverage và các file bị thiếu.

Markdown **không** in toàn bộ bảng Housekeeping, vì đây thường là nhóm lớn nhất và ít cần đọc từng dòng. Dữ liệu đầy đủ vẫn nằm trong JSON và HTML.

### 19.3. `report.html`: dashboard để triage

Mỗi dòng trong bảng hiển thị sáu thứ:

- Score.
- Bucket.
- Đối tượng nào thay đổi.
- Thay đổi gì đã xảy ra, lấy từ leading signal.
- WebUI page hoặc thư mục source liên quan.
- Loại `Fact` và nhóm hậu quả.

Khi mở một dòng ra, người đọc thấy thêm:

- Tất cả các nhãn signal.
- Vị trí source dạng `path:line`.
- Các delta.
- Tóm tắt Chromestatus, nếu có.
- Lý do chấm score.

### 19.4. Filter HTML hoạt động thế nào?

Bốn dropdown lọc theo giá trị chính xác và kết hợp với nhau bằng điều kiện **AND**:

- Bucket.
- Surface hoặc fact kind.
- Nhóm hậu quả.
- Owner.

Ô tìm kiếm không phân biệt chữ hoa chữ thường, và kiểm tra bảy trường:

- Name và key.
- Kind.
- Câu mô tả `what`.
- Screen hoặc directory `where`.
- Nhãn signal hoặc story.
- Đường dẫn source.
- Tóm tắt Chromestatus.

Hai chi tiết về hành vi của dashboard: khi bấm vào thẻ tổng hợp của một bucket, dashboard xoá các lựa chọn cũ rồi lọc theo bucket đó. Và bảng chỉ render 100 dòng mỗi lần, để một report vài nghìn finding vẫn phản hồi nhanh; có thể sort theo từng cột.

### 19.5. Ví dụ filter theo team

**Owner WebUI**

```text
Owner = WebUI front-end
Surface = WebUI page/control/gate
Search = settings hoặc downloads
Bucket = Behaviour change / Breaking
```

Cách đọc: xem route guard, biểu thức của gate, loại control và pref binding **cùng nhau**. Không kết luận chỉ từ một dòng route.

**Owner Browser C++**

```text
Owner = Browser C++
Bucket = Breaking hoặc Behaviour change
Search symbol/pref/switch đang patch trong Samsung
```

Cách đọc: luôn phân biệt hai trường hợp — tên feature dùng bên ngoài bị đổi, hay chỉ C++ symbol bị đổi; pref key bị đổi, hay chỉ C++ constant bị đổi.

**Owner IPC**

```text
Owner = Process boundaries
Bucket = Breaking
Sort score descending
```

Cách đọc: ưu tiên thay đổi về type, ordinal và signature. Sau đó tìm trong Samsung source xem có code riêng nào gọi, triển khai, hoặc trao đổi dữ liệu qua IPC contract đó không.

## 20. Ai làm gì? Tool, skill, agent và con người

### 20.1. Phần tool chạy theo quy tắc cố định

Python code trong `chromedrift/` chịu trách nhiệm sáu việc:

- Xác định chính xác version.
- Lấy danh sách file và tải source.
- Lọc file, trích xuất và chuẩn hoá `Fact`.
- Loại bản ghi trùng.
- So sánh, tạo signal, và tính severity/score.
- Gom nhóm finding, bổ sung ngữ cảnh, và tạo report.

**Không bước nào trong số này gọi LLM.** Với cùng một snapshot và cùng một version code của ChromeDrift, kết quả report là như nhau.

### 20.2. Skill `analyzing-chromium-uprevs`

Skill là checklist hướng dẫn engineer hoặc coding agent **đọc và xử lý** report. Nó không tham gia vào việc trích xuất dữ liệu. Nội dung chính:

- Chốt version chính xác và chọn bộ file phù hợp.
- Đọc report theo owner và bucket.
- Không nhầm việc dọn flag thành việc xoá feature.
- Lần từ WebUI guard tới feature flag đứng sau nó.
- Kiểm tra một Web API có thật sự tiếp cận được không.
- Kiểm tra nơi Samsung source hoặc cấu hình ngoài repository đang sử dụng tên đó.
- Ghi kết luận theo owner, và nêu rõ giới hạn của bằng chứng.

Nói gọn lại thành một câu:

> **Tool tạo bằng chứng; skill hướng dẫn cách điều tra; owner của Samsung xác nhận ảnh hưởng thật lên sản phẩm.**

### 20.3. RACI đề xuất

| Bước | Responsible | Accountable/Reviewer |
|---|---|---|
| Chốt chính xác phiên bản FROM/TO | Người phụ trách nâng Chromium | Tech lead |
| Chạy `wide`, lưu các file kết quả | Người phụ trách công cụ hoặc nâng Chromium | Tech lead |
| IPC triage | Mojo/integration owner | Browser architecture owner |
| Web platform triage | Blink/Web Platform owner | Compatibility lead |
| Browser C++ triage | Native migration owner | Tech lead |
| WebUI triage | WebUI owner | Product/UI lead, nếu hành vi người dùng thấy được |
| Cách server bật/tắt feature cho từng nhóm người dùng, cùng script khởi động và policy | Nhóm Config/Release/QA | Release lead |
| Tìm nơi Samsung sử dụng và ước lượng công sức | Từng owner | Tech lead |
| Quyết định build/test/merge | Team tích hợp upstream | Tech lead hoặc release gate hiện có |

Agent có thể hỗ trợ tìm kiếm và tóm tắt, nhưng owner kỹ thuật vẫn phải là người xác nhận hành vi và khối lượng công việc.

## 21. Số liệu chạy thật M148 → M151

Lệnh đã kiểm chứng:

```bash
python3 -m chromedrift run \
  148.0.7778.217 151.0.7922.138 \
  --out out/M148_to_M151 \
  --no-enrich
```

Snapshot và report ở bộ `default`:

| Metric | Kết quả |
|---|---:|
| Facts FROM | 28,507 |
| Facts TO | 29,138 |
| Semantic changes | 3,022 |
| Breaking | 276 |
| Behaviour change | 469 |
| New surface | 1,240 |
| Housekeeping | 1,037 |
| Not in Windows build | 187 |
| Clusters | 72, cluster lớn nhất 7 finding |

Số lượng theo owner:

| Owner | Total | Breaking |
|---|---:|---:|
| Process boundaries | 339 | 126 |
| Web platform | 719 | 94 |
| Browser C++ | 1,157 | 2 |
| WebUI front-end | 277 | 1 |
| Outside repository | 530 | 53 |

**Bảng thứ hai là lập luận mạnh nhất cho việc phải lọc theo owner và bucket.** Browser C++ có nhiều finding nhất — 1.157 — nhưng chỉ có 2 finding Breaking. Ngược lại, IPC chỉ có 339 finding, nhưng 126 trong số đó là Breaking.

Nếu chỉ nhìn tổng số dòng, hoặc nhìn kích thước Git diff, team sẽ dồn công sức vào đúng khu vực ít rủi ro nhất.

### Một finding C++ dễ hiểu

Tên dùng để lưu thiết lập `default_apps` giữ nguyên, nhưng C++ constant mà source code dùng đã đổi:

```text
kPreinstalledApps → kPreinstalledExtensions
signal: pref_symbol_renamed
severity/score: 55
bucket: Breaking
```

Đọc finding này: dữ liệu người dùng **không** mất, vì pref key `default_apps` vẫn giữ nguyên. Nhưng nếu Samsung code còn dùng symbol `prefs::kPreinstalledApps`, nó sẽ lỗi build sau khi merge Chromium mới.

Đây đúng là loại việc mà công cụ giúp phát hiện trước — tìm symbol cũ và chuẩn bị sửa **trước** khi merge, thay vì phát hiện lúc build đỏ.

### Một finding IPC điển hình

```text
blink.mojom.CommitNavigationParams.early_hints_preloaded_resources
array<url.mojom.Url>
    → array<network.mojom.LinkHeader>
signal: ipc_shape_changed
score: 80
```

Cần đọc thận trọng: **không phải cứ thấy finding này là phải sửa gì đó.** Team cần tìm trong Samsung source xem có code riêng nào tạo ra, nhận vào, hoặc giả định cấu trúc dữ liệu của field này hay không. Nếu không có, thay đổi này có thể không tạo thêm việc nào cho Samsung.

## 22. Từ report thành dự đoán công việc Samsung

Report của ChromeDrift mới chỉ mô tả thay đổi từ Chromium gốc. Muốn dự đoán công việc thật của Samsung, cần nối report với bằng chứng từ source và config của Samsung, theo quy trình năm bước sau.

### Bước 1 — Chạy `wide` trên hai version đầy đủ

Khi đánh giá toàn bộ một đợt nâng phiên bản, đừng giới hạn công cụ vào một subsystem nhỏ. Lưu cả ba định dạng JSON, Markdown và HTML cùng với tài liệu lập kế hoạch.

```bash
python3 -m chromedrift run \
  148.0.7778.217 151.0.7922.138 \
  --target-set wide \
  --out out/M148_to_M151_wide
```

### Bước 2 — Phân loại theo owner, không theo file

Thứ tự ưu tiên:

1. Breaking thuộc IPC.
2. Breaking thuộc Web Platform.
3. Breaking thuộc Config.
4. Behaviour change trên Windows.
5. New surface có liên quan tới roadmap sản phẩm.
6. Housekeeping — chỉ lọc phần hết hạn và phần override cần dọn.

### Bước 3 — Tìm nơi Samsung đang sử dụng

Với từng finding:

- Tìm `change.key`, biến C++ cũ và mới, cùng chuỗi pref/switch cũ và mới.
- Tìm theo đường dẫn, nếu Samsung có patch trong cùng file đó.
- Với Mojo, tìm tên đầy đủ của interface, method hoặc type, ở **cả phía gửi lẫn phía nhận**.
- Với WebUI, tìm route, khoá `loadTimeData`, element id và pref key.
- Với feature do server điều khiển, tìm tên feature và các giá trị đi kèm trong hệ thống thử nghiệm của Samsung. Nếu có script khởi động browser bằng cờ `--...`, tìm cả tên cũ lẫn tên mới trong các script đó.

### Bước 4 — Ghi trạng thái sau khi đối chiếu với Samsung

Mỗi finding nên được gắn một trong các trạng thái sau, ở lớp dữ liệu bổ sung hoặc trong hệ thống quản lý công việc:

```text
not_referenced
referenced_unmodified
patched_same_file
custom_implementation
external_config_match
needs_manual_validation
```

### Bước 5 — Chỉ ước lượng effort sau khi tìm thấy nơi sử dụng

Một finding chỉ trở thành đầu việc khi có **ít nhất một** bằng chứng cụ thể:

- Samsung source đang dùng symbol hoặc chuỗi đó.
- Samsung có patch trong cùng khu vực chức năng.
- Samsung có code riêng ở một đầu của Mojo interface.
- Hành vi hoặc test của sản phẩm phụ thuộc vào giá trị mặc định cũ.
- Config ngoài source đang dùng feature name hoặc param cũ.
- Sản phẩm có kế hoạch sử dụng API hoặc UI mới.

Chỉ sau đó team mới ước lượng phần sửa build, sửa code, phạm vi QA, chuyển config hoặc công việc phía sản phẩm. **Score của ChromeDrift không thay thế bước ước lượng này.**

## 23. Làm sao tin report đúng?

Không có một con số duy nhất chứng minh report đúng. Độ tin cậy đến từ việc từng bước đều để lại dữ liệu có thể kiểm tra lại. Bảy nhóm bằng chứng dưới đây là những gì có thể mang ra đối chất.

### 23.1. Source identity

- Version đầy đủ được đổi thành Git tag cố định khi tải qua Gitiles.
- Git ref được ghi trong cả snapshot lẫn report.
- Mỗi `Fact` và mỗi thay đổi đều giữ vị trí file và số dòng.

### 23.2. Scope identity

- Bộ file, partition và chế độ `complete` là một phần của khoá cache.
- Hai snapshot được tạo với phạm vi khác nhau không được phép đem so sánh.
- `Fact` nằm ngoài phạm vi đã khai báo được phát hiện và ghi vào report.
- Hai snapshot có số `Fact` chênh lệch bất thường bị từ chối, để tránh báo sai hàng loạt.

### 23.3. Coverage evidence

- Tổng số file ứng viên được tính từ cây thư mục thật của từng version.
- Tiêu chí "file nào đọc được" lấy từ chính các extractor, không phải từ một danh sách viết tay.
- Coverage tổng và coverage của từng nhóm đều được lưu trong report.
- File bị thiếu, lỗi parser, và liên kết chưa tìm thấy đầu còn lại đều được ghi rõ.

### 23.4. Determinism

- Danh sách thư mục và file luôn được sắp xếp trước khi đọc.
- Khi có bản ghi trùng, công cụ chọn theo `(path, line)` thay vì giữ file được đọc đầu tiên.
- Nếu hai signal có cùng severity, cách chọn leading signal vẫn cố định.
- JSON được ghi ra file tạm rồi mới thay thế file đích, tránh để lại artifact dở dang.
- Khi schema đổi, cache cũ bị vô hiệu hoá.

### 23.5. Semantic normalization

- Đổi cách viết macro không bị coi là đổi hành vi.
- Khoảng trắng và comment không làm khoá thay đổi.
- Công cụ đọc điều kiện build để xác định trạng thái trên Windows, chứ không chỉ dùng giá trị chung.
- Các trường hợp đổi tên và WebUI control chuyển pref đều được ghép lại.
- Các overload được giữ đầy đủ trước khi loại bản ghi trùng.

### 23.6. Explainability

Mỗi finding cần xử lý đều đi kèm bảy thông tin:

- Giá trị trước và sau.
- Phần giá trị thực sự thay đổi.
- Signal mô tả ý nghĩa của thay đổi.
- Severity.
- Lý do chấm score.
- Bucket.
- Vị trí trong source.

Nhờ đó người đọc có thể mở đúng source và kiểm tra từng rule. Không ai bị buộc phải tin một kết luận mà không nhìn thấy logic phía sau nó.

### 23.7. Test evidence

Toàn bộ test chạy được không cần mạng. Test suite kiểm tra:

- Từng extractor và các hàm parser dùng chung.
- Điều kiện build của C++, GRIT và Mojo.
- Phạm vi của từng bộ file, cache cũ, và chế độ partition/`complete`.
- Cách tính coverage và cách hạ độ tin cậy khi kết luận một đối tượng đã biến mất.
- So sánh `Fact`, đổi tên, overload, Mojo ordinal và data type.
- Cách tính score, chọn bucket và chọn owner.
- Gom nhóm finding, kiểm tra liên kết, và từ chối snapshot chênh lệch bất thường.
- Render Markdown/HTML, hiệu năng DOM và các ranh giới XSS.
- Documentation figures và source map.

Cần phát biểu đúng phạm vi của con số này: test chứng minh code đang tuân theo 368 trường hợp đã được mô tả trong test suite. Nó **không** chứng minh parser hiểu mọi cú pháp Chromium, và cũng không cho biết Samsung đang dùng finding nào.

## 24. Những giới hạn phải nói thẳng

Phần này nên được trình bày chủ động, không nên chờ người khác hỏi. Một công cụ nói rõ giới hạn của mình thì đáng tin hơn một công cụ hứa hẹn quá nhiều.

### 24.1. Tool đọc khai báo, không hiểu toàn bộ chương trình như compiler

Các extractor là những parser nhỏ, viết cho những mẫu cú pháp cụ thể. Chúng không thay thế Clang, Blink bindings generator hay Mojo compiler.

Đây là một đánh đổi có chủ ý: nhờ vậy công cụ chạy được trên một phần source mà không cần build Chromium. Đổi lại, cú pháp nằm ngoài các mẫu đã hỗ trợ có thể bị bỏ qua.

### 24.2. File coverage không phải grammar coverage

Một số loại khai báo hiện chưa được chuyển thành `Fact`:

- Web IDL callback, typedef, và quan hệ `Interface includes Mixin`.
- Mojo `feature` block và constant.
- Một số trường hợp cú pháp hiếm, cùng các quan hệ lồng nhau hoặc kế thừa phức tạp.

Vì vậy, dù bộ `wide` đọc 99% file ứng viên, điều đó **không** có nghĩa parser hiểu 99% mọi khai báo trong các file đó.

### 24.3. Không đọc implementation body

Nếu Chromium chỉ đổi logic bên trong một function mà giữ nguyên khai báo, ChromeDrift sẽ không phát hiện được.

### 24.4. Không parse BUILD.gn

Đường dẫn theo nền tảng và các điều kiện `#if` cho bằng chứng hữu ích, nhưng chúng không thay thế được toàn bộ dependency graph trong `BUILD.gn`.

Hệ quả: nếu một khai báo phụ thuộc vào build flag mà công cụ chưa hiểu, trạng thái của nó chỉ được ghi là `conditional`.

### 24.5. WebUI chỉ đọc phần được khai báo rõ trong source

Công cụ đọc route, template, và đoạn C++ đưa dữ liệu vào `loadTimeData`.

Nó **không** phân tích toàn bộ logic TypeScript, không đọc `page_visibility.ts`, không đọc file string `.grd`, không đánh giá layout, và không xem ảnh chụp UI.

### 24.6. Chưa biết Samsung đang sử dụng phần nào

Đây là giới hạn lớn nhất, và nên được nói ra đầu tiên khi có ai hỏi về giá trị của công cụ.

Project chưa đọc Samsung source, chưa đọc user profile, chưa đọc config riêng của Samsung. Vì vậy score chỉ xếp ưu tiên các thay đổi **từ Chromium gốc**; nó chưa phải điểm ảnh hưởng lên Samsung Browser.

### 24.7. Không phải mọi lỗi parser đều được ghi nhận

`run_on_tree` ghi vào `_errors` khi một extractor phát sinh exception. Tuy nhiên có hai lỗ hổng:

- hai extractor đọc JSON5 hiện có thể bắt `Json5Error` bên trong rồi trả về danh sách rỗng, và lỗi đó chưa làm `_errors` tăng lên;
- một mẫu cú pháp mà lexer không nhận ra cũng không tạo ra exception nào.

Vì vậy, "0 parser errors" chỉ có nghĩa là **không thấy lỗi nào được báo ra**, chứ không có nghĩa mọi khai báo đều đã được đọc.

### 24.8. Độ tin cậy của source có sẵn trên máy

Cache hiện dựa trên tên Git ref và policy, chứ chưa dựa trên commit hoặc hash nội dung của thư mục local.

Khi dùng Git tag chính thức qua Gitiles, rủi ro này rất nhỏ. Nhưng khi dùng một branch còn đang thay đổi, hoặc dùng source trên máy, người chạy phải tự kiểm tra commit và dùng `--refresh` khi cần.

### 24.9. Nhóm finding chỉ giúp điều hướng

Một cluster giúp xem các finding liên quan trong cùng ngữ cảnh, nhưng nó **không** chứng minh rằng tất cả chúng thuộc cùng một thay đổi logic trong Chromium. Người review vẫn phải kiểm tra từng liên kết và từng vị trí source.

## 25. Mức sử dụng an toàn

Bảng này trả lời trực tiếp câu hỏi "dùng công cụ tới đâu thì hợp lý":

| Cách sử dụng | Có nên dùng? | Điều kiện |
|---|---|---|
| Phát hiện sớm trước khi nâng phiên bản | Rất phù hợp | Version chính xác, có report và biết rõ phạm vi đã đọc |
| Chia triage theo owner | Rất phù hợp | Dùng bộ lọc owner và bucket |
| Tạo danh sách symbol/config cần tìm | Rất phù hợp | Giữ key và `path:line` làm bằng chứng |
| Dự báo vùng build/test có rủi ro | Phù hợp | Phải bổ sung thông tin về nơi Samsung đang sử dụng |
| Tự động ước lượng effort | Chưa đủ | Cần dữ liệu về patch, reference và config của Samsung |
| Dùng làm release gate duy nhất | Không | Vẫn cần merge, build, test và kiểm tra sản phẩm |
| Khẳng định "không có impact" từ một lần chạy `default` sạch | Không | Coverage của `default` chênh lệch rất lớn giữa các surface |

## 26. Đề xuất đưa vào quy trình nâng phiên bản Chromium

### Giai đoạn 1 — Dùng ngay

- Ghi version Chromium hiện tại và version mục tiêu bằng đầy đủ bốn phần trong ticket.
- Chạy `wide` một lần cho mỗi cặp version chính thức.
- Lưu `report.json`, `report.md`, `report.html` và cả lệnh đã chạy.
- Tạo checklist cho từng owner, từ hai bucket Breaking và Behaviour change.
- Dùng key và symbol trong report làm đầu vào cho `rg` khi tìm trong Samsung source và config.

### Giai đoạn 2 — Thêm bằng chứng từ phía Samsung

- Viết một bộ quét Samsung source, ghi lại: symbol nào khớp, file nào Samsung đã patch, và team nào sở hữu patch đó.
- Chuẩn bị đầu vào riêng cho repository hoặc file mà server Samsung dùng để quyết định feature nào được bật cho nhóm người dùng nào, cùng các script và automation liên quan.
- Ghi trực tiếp `owner` vào từng finding trong JSON.
- Thêm trạng thái sau khi đối chiếu với Samsung, và thêm trường effort — tách riêng khỏi score của Chromium gốc.

### Giai đoạn 3 — Hardening

- Ghi lại commit hoặc hash nội dung của source, đặc biệt khi dùng branch hoặc source local.
- Đo số khai báo mà parser đọc được, theo từng loại cú pháp.
- Đưa lỗi parse JSON5 vào `_errors` chung của lần chạy.
- Thêm mẫu đối chiếu từ các đợt nâng phiên bản đã hoàn thành: mục phát hiện nào thật sự tạo ra đầu việc, và tốn bao nhiêu công sức.
- Dùng lịch sử đó để hiệu chỉnh việc lập kế hoạch — nhưng không dùng severity như một con số thay thế cho effort.

## 27. Demo nên trình bày thế nào?

### Kịch bản 15–20 phút

**Phút 0–2: bài toán**

> "Mỗi lần nâng Chromium, chúng ta phải xử lý một Git diff rất lớn. Điều cần biết sớm là API hoặc IPC contract nào đổi, hành vi mặc định nào đổi, và Samsung có đang phụ thuộc vào phần đó không."

**Phút 2–5: pipeline**

Trình bày sơ đồ: version → source → `Fact` → so sánh → score → owner/report. Nhấn mạnh hai điểm: source được lấy từ Git tag chính xác, và bước trích xuất không dùng AI.

**Phút 5–9: một fact và một diff**

Mở một object `base_feature` để giải thích cách chuẩn hoá. Sau đó mở ví dụ Mojo field đổi kiểu dữ liệu, kèm vị trí source ở cả hai phiên bản.

**Phút 9–12: nhiều finding của cùng một thay đổi**

Trình bày nhóm Local Network Access. Ví dụ này cho thấy nếu chỉ nhìn dòng route bị xoá thì sẽ kết luận sai; phải đọc cùng feature flag và gate liên quan.

**Phút 12–15: thu hẹp report theo owner**

Trình bày số liệu M148 → M151: IPC có 339 finding nhưng 126 Breaking, trong khi Browser C++ có 1.157 finding nhưng chỉ 2 Breaking.

**Phút 15–18: độ tin cậy và giới hạn**

So sánh coverage của `default` và `wide`, và mở vị trí source của một finding. Nói rõ đây là lớp cảnh báo sớm, không thay thế release gate.

**Phút 18–20: đề xuất thử nghiệm**

Đề nghị thử trên một đợt nâng phiên bản thật: chạy `wide`, xem trước các danh sách quan trọng của từng nhóm, rồi đo xem bao nhiêu mục khớp với mã nguồn Samsung và bao nhiêu mục trở thành đầu việc.

### Ba câu nên tránh

- "Tool biết chính xác Samsung sẽ lỗi ở đâu."
- "99% coverage nghĩa là không thể bỏ sót thay đổi."
- "Score 80 chắc chắn là 80% có bug."

### Ba câu nên dùng

- "Tool biến thay đổi từ Chromium gốc thành từng finding có key, giá trị trước/sau và vị trí source."
- "Score chỉ xếp thứ tự điều tra; nơi Samsung đang sử dụng mới quyết định ảnh hưởng thật."
- "Chúng ta có thể đo trường hợp báo thừa hoặc bỏ sót qua một lần thử, rồi cải thiện bằng dữ liệu nâng phiên bản thật."

## 28. Bộ câu hỏi thường gặp khi review

### "Khác gì `git diff` hoặc release notes?"

Git diff cho biết dòng text nào đổi, nhưng không phân biệt được refactor với thay đổi contract. Release notes chỉ chọn một số thay đổi đáng chú ý cho người dùng cuối.

ChromeDrift tập trung vào các khai báo kỹ thuật: nó chuẩn hoá khác biệt cú pháp, xác định trạng thái trên Windows, phát hiện đổi tên, và giữ vị trí source để kiểm tra lại.

### "Version lấy từ đâu?"

Version đầy đủ được đổi thành Git tag chính thức. Nếu chỉ nhập milestone, công cụ hỏi ChromiumDash để lấy bản Stable Windows mới nhất tại thời điểm chạy.

Report chính thức phải dùng version đầy đủ, để lần chạy sau không tự chuyển sang một bản vá khác.

### "Có checkout toàn bộ Chromium không?"

Không. Công cụ lấy danh sách file từ Gitiles rồi chỉ tải các file hoặc thư mục con cần thiết. Ngay cả bộ `wide` cũng chỉ giữ những loại file mà extractor biết cách đọc.

### "Làm sao chắc file thuộc đúng version?"

Khi dùng version đầy đủ qua Gitiles, công cụ đọc từ Git tag `refs/tags/...` — vốn không thay đổi — và ghi tag đó vào snapshot cùng report.

Khi dùng source có sẵn trên máy, người chạy phải tự kiểm tra commit, vì công cụ hiện chưa xác nhận thư mục local có đúng commit hay không.

### "Tại sao không kéo tất cả file?"

Vì công cụ không build Chromium, và chưa phân tích thân function hay TypeScript thông thường. Tải các file đó sẽ tăng dung lượng nhưng không tạo thêm `Fact` nào.

Bộ `wide` vì vậy chỉ mở rộng tối đa **trong phạm vi những loại file mà parser hiện hỗ trợ**.

### "Tại sao chỉ các đuôi file đó?"

Vì đây là nơi Chromium khai báo feature flag, API, IPC data type, pref, WebUI control và thời hạn của flag.

Mỗi loại file muốn được đọc thì phải có một extractor và một cấu trúc `Fact` tương ứng; file không có extractor thì không thể so sánh một cách đáng tin.

### "C++ được đọc những gì?"

Công cụ đọc `base::Feature`, `FeatureParam`, các string constant dùng làm pref/switch, và các C++ handler đưa dữ liệu vào WebUI qua `loadTimeData`. Nó cũng đọc điều kiện `#if` xung quanh, để biết khai báo có nằm trong Windows build không.

### "Blink và Web IDL là gì?"

Blink là rendering engine của Chromium, chạy chủ yếu trong renderer process. Nó đọc HTML/CSS, xây DOM, tính layout, và cung cấp các Web Platform API cho JavaScript.

Web IDL là ngôn ngữ dùng để khai báo phần API mà JavaScript nhìn thấy. Ví dụ, một Web IDL interface có thể cung cấp method `navigator.foo()`. Nếu interface bị xoá, method đổi signature, hoặc runtime gate đổi trạng thái, website hay feature của Samsung dùng API đó có thể bị ảnh hưởng.

Công cụ chỉ phát hiện thay đổi trong khai báo; nó không chạy website để tự kết luận về khả năng tương thích.

### "Mojo và Mojo interface là gì? Có phải UI không?"

Không, hoàn toàn không liên quan tới UI. Mojo là IPC framework của Chromium.

Browser được tách thành nhiều process; Mojo quy định cách browser process, renderer process, GPU process, network process và các service gọi method hoặc gửi dữ liệu cho nhau.

File `.mojom` đóng vai trò như IDL cho IPC: một Mojo interface chứa các method; method nhận request và có thể trả response; còn struct, union và enum mô tả dữ liệu đi qua ranh giới process.

Nếu Chromium đổi signature của method hoặc đổi kiểu của một field, thì code Samsung tự triển khai hoặc tự sử dụng một đầu của interface đó có thể phải cập nhật cùng lúc.

### "WebUI là gì?"

WebUI là framework mà Chromium dùng cho các page nội bộ như `chrome://settings` và `chrome://downloads`. Phần hiển thị dùng HTML/TypeScript, còn dữ liệu và điều kiện bật feature thường đến từ C++ handler trong browser process.

Trong report, bốn từ này có nghĩa cụ thể: `route` xác định page; `control` là toggle, dropdown hoặc button; `backing pref` là nơi lưu setting; `gate` quyết định page hoặc feature có được hiển thị hay không.

Công cụ phát hiện thay đổi ở các phần này, nhưng không render UI và không đánh giá layout bằng ảnh chụp màn hình.

### "Finch là gì và tại sao nằm trong báo cáo?"

Hiểu đơn giản, Finch là hệ thống thử nghiệm của Chrome. Thay vì bật một tính năng giống nhau cho tất cả mọi người ngay trong mã nguồn, Chrome có thể để server quyết định:

- bật hoặc tắt tính năng nào;
- áp dụng cho nhóm người dùng nào;
- dùng giá trị nào cho tính năng đó.

Ví dụ: source có feature tên `NewDownloadUI` và param `button_style=compact`. Server có thể chỉ bật feature này cho 10% người dùng. Browser nhận quyết định đó lúc chạy, nên Chrome có thể thử nghiệm hoặc thu hồi tính năng mà không cần phát hành bản cài đặt mới.

**Vì sao điều này nguy hiểm khi uprev:** nếu Chromium đổi tên `NewDownloadUI` hoặc bỏ param `button_style`, source vẫn build bình thường, trong khi server vẫn gửi tên cũ. Browser không tìm thấy feature tương ứng và âm thầm dùng trạng thái mặc định — không có lỗi nào được báo.

Vì config trên server không nằm trong source Chromium, report giao các finding này cho nhóm `Outside the repository`.

Samsung Browser có thể không dùng Finch trực tiếp. Khi đó, đừng đi tìm một hệ thống có đúng tên "Finch"; hãy tìm **nơi Samsung đang quyết định bật/tắt feature cho từng nhóm người dùng**. Nơi đó có thể là hệ thống thử nghiệm A/B, file cấu hình trên server, policy, automation, hoặc script thêm cờ `--...` khi khởi động browser.

### "Cờ `--...` thêm lúc khởi động browser là gì?"

Đây là option được truyền ngay trong lệnh mở browser. Ví dụ:

```text
browser.exe --enable-features=NewDownloadUI
```

Lệnh trên yêu cầu browser bật feature `NewDownloadUI` trong lần chạy đó. Script test, automation hoặc shortcut nội bộ có thể đang dùng tên này.

Nếu Chromium đổi tên feature mà script vẫn truyền tên cũ, browser vẫn mở bình thường — nhưng yêu cầu bật feature không còn tác dụng nữa.

### "Preference hay `pref` trong tài liệu là gì?"

Pref là một setting được browser lưu trong user profile, ví dụ "có hỏi trước khi tải file hay không".

Chuỗi `download.prompt_for_download` là key dùng để lưu và đọc setting; còn C++ constant như `prefs::k...` là symbol mà source code dùng để truy cập key đó.

Hai kiểu hỏng khác nhau: nếu pref key đổi, giá trị cũ vẫn nằm trên ổ đĩa nhưng browser không còn đọc bằng key cũ, nên setting có thể quay về mặc định. Nếu chỉ C++ constant đổi mà pref key giữ nguyên, dữ liệu người dùng không đổi, nhưng Samsung source dùng symbol C++ cũ có thể lỗi build.

### "Fact có phải raw AST không?"

Không. `Fact` là một object rút gọn, dành riêng cho việc so sánh phiên bản. Nó chỉ giữ key, các thuộc tính quan trọng, đường dẫn và số dòng.

`Fact` ít chi tiết hơn AST, nhưng ổn định hơn nhiều khi source chỉ đổi cách format hoặc đổi cách viết macro.

### "Key có collision không?"

Có thể, vì Chromium đôi khi có nhiều khai báo cùng tạo ra một key. Công cụ xử lý bằng một quy tắc loại trùng cố định.

Riêng Web IDL overload được gộp thành một `Fact` nhưng vẫn giữ từng signature. Những trường hợp đổi tên, hoặc WebUI control đổi pref, được ghép lại ở một bước sau.

### "Tại sao attr này compare, attr kia không?"

`MEANINGFUL_ATTRS` là danh sách các thuộc tính được phép tạo ra finding. Một thuộc tính chỉ được vào danh sách khi thay đổi của nó có thể đổi hành vi, đổi contract, hoặc đổi khả năng được sử dụng.

Thuộc tính chỉ mô tả **cách source được viết** — như dạng macro — vẫn được giữ trong `Fact`, nhưng không tạo ra finding.

### "File move có thành remove/add không?"

Nếu UID giữ nguyên, công cụ coi đây là cùng một khai báo đã chuyển file, và tạo signal `declaration_moved`.

Nếu key cũng đổi, công cụ chỉ ghép hai phía lại khi có bằng chứng ổn định — cùng biến C++, hoặc cùng id/label của WebUI control.

### "Removal có chắc là delete?"

Không. `Removed` trước hết chỉ có nghĩa là công cụ thấy đối tượng ở bản cũ nhưng không thấy ở bản mới.

Công cụ kiểm tra coverage của đúng nhóm file, cùng các lỗi tải và lỗi parser, trước khi coi đó là xoá thật. Với pref và switch, bộ `default` đọc quá ít file nên **không** được dùng để xác nhận việc xoá.

### "Breaking có chắc Samsung break không?"

Không. `Breaking` chỉ nói rằng Chromium gốc đã thay đổi một contract có khả năng ảnh hưởng tới code bên ngoài.

Chỉ khi tìm thấy Samsung source hoặc config đang dùng contract đó, mới có thể coi đây là blocker của Samsung.

### "Score có phải xác suất?"

Không. Severity và score chỉ tạo ra thứ tự ưu tiên điều tra. Score 80 không có nghĩa 80% khả năng lỗi, và cũng không có nghĩa 80 đơn vị effort.

### "Score 0 nghĩa là bỏ luôn?"

Nghĩa là khai báo đó không được đưa vào Windows build ở cả hai phiên bản, theo bằng chứng hiện có.

Vẫn có thể xem nó trong nhóm Housekeeping nếu cần phân tích đa nền tảng, nhưng nó không nên chiếm ưu tiên của một đợt nâng phiên bản cho Windows.

### "Tại sao score chỉ trừ mà không cộng theo Samsung patch?"

Vì project hiện chưa đọc Samsung source. Nếu tự cộng điểm cho "ảnh hưởng Samsung" mà không biết Samsung có dùng phần đó hay không, con số sẽ tạo ra cảm giác chính xác giả.

Hướng đúng là bổ sung kết quả tìm kiếm trong Samsung source và config, rồi mới tạo một điểm số riêng cho sản phẩm.

### "Owner được quyết định thế nào?"

Loại `Fact` quyết định owner mặc định. Nếu nơi cần sửa khác với nơi khai báo nằm, leading signal sẽ chuyển finding sang owner phù hợp.

Ví dụ: feature name nằm trong C++, nhưng server đang dùng chính tên đó để bật thử nghiệm — nên team quản lý server config cũng phải kiểm tra.

### "WebUI được filter ra sao?"

Dashboard có bộ lọc riêng cho bucket, loại `Fact`, nhóm hậu quả và owner. Các bộ lọc kết hợp bằng AND. Ô tìm kiếm kiểm tra tên, mô tả, đường dẫn source, signal và tên WebUI page.

### "Một toggle đổi thành dropdown được phát hiện thế nào?"

Công cụ nhận diện cùng một control qua pref, id, label và file. Loại element được lưu trong thuộc tính `control`.

Nếu identity giữ nguyên nhưng element đổi từ toggle sang dropdown, công cụ tạo signal `ui_control_type_changed`.

### "Control đổi backing pref thì sao?"

Ở lần ghép đầu tiên, công cụ có thể thấy control cũ bị xoá và control mới được thêm, vì pref là một phần của khoá.

Bước ghép bổ sung sẽ nhận ra chúng có cùng page và cùng id/label, rồi tạo một finding `ui_control_repointed` để thể hiện đúng bản chất: control chuyển sang pref khác.

### "Route bị remove có nghĩa page biến mất?"

Chưa chắc. Route có thể bị thay thế, đổi guard, hoặc được dọn đi sau khi feature mới đã bật. Cần đọc cùng gate, feature flag và các finding liên quan.

Local Network Access là ví dụ điển hình: route cũ bị xoá, nhưng chức năng đã chuyển sang cơ chế mới từ trước đó.

### "Mojo change có luôn là runtime break?"

Không. Nếu cả hai đầu IPC đều được sinh lại từ cùng source Chromium, chúng cùng thay đổi và vẫn tương thích với nhau.

Rủi ro nằm ở code Samsung tự triển khai, tự gọi, hoặc giữ giả định riêng về một đầu của interface — đó là nơi cần tìm trước tiên.

### "Web API mới có dùng được ngay không?"

Công cụ phân biệt API mới đã có thể dùng (`web_api_added_live`) với API còn bị chặn bởi runtime flag (`web_api_added_gated`).

Nếu chính runtime flag đó nằm ngoài snapshot, report ghi là chưa đủ thông tin thay vì đoán.

### "Chromestatus có quyết định score không?"

Không. Chromestatus chỉ bổ sung bối cảnh về vòng đời của một Web Platform feature. Việc trích xuất, so sánh và chấm điểm vẫn chạy được hoàn toàn offline.

### "Default và wide khác nhau thế nào?"

`default` tối ưu cho tốc độ, và ưu tiên các file chứa nhiều khai báo. `wide` đọc gần như toàn bộ file mà extractor hiểu.

Lập kế hoạch cho cả một đợt nâng phiên bản thì nên dùng `wide`; `default` phù hợp để kiểm tra nhanh hằng ngày.

### "Partition dùng khi nào?"

Dùng partition khi đang phát triển, hoặc khi cần kiểm tra nhanh một khu vực nhỏ.

Không dùng kết quả partition để kết luận cho cả đợt nâng phiên bản, vì một thay đổi của Downloads hoàn toàn có thể nằm ở `content/`, ở Mojo, hoặc ở một file feature dùng chung nằm ngoài partition đó.

### "`--complete` có nghĩa toàn Chromium complete không?"

Không. `--complete` chỉ yêu cầu đọc đủ các file mà extractor hỗ trợ, bên trong một partition có phạm vi nhỏ và rõ ràng.

Nó không có nghĩa công cụ đọc hoặc hiểu toàn bộ Chromium. Với những subsystem quá lớn, công cụ từ chối chế độ này.

### "Cache có thể làm report sai không?"

Cache đã ghi lại bộ lọc, schema version và phạm vi của snapshot, để tránh dùng nhầm artifact cũ.

Tuy nhiên, nếu đầu vào là một branch còn thay đổi hoặc là source trên máy, người chạy vẫn phải kiểm tra commit và dùng `--refresh` khi nội dung đã đổi.

### "Test xanh chứng minh gì?"

Chứng minh 368 hành vi đã được viết thành test vẫn hoạt động đúng.

Test **không** chứng minh extractor hiểu mọi cú pháp Chromium, và không cho biết Samsung đang dùng finding nào.

### "Có false positive không?"

Có. Ví dụ: một route bị xoá có thể chỉ vì chức năng đã chuyển sang route khác; hoặc coverage thiếu có thể làm một file move trông giống như bị delete.

Signal, coverage và việc gom nhóm finding giúp giảm báo thừa, nhưng không thể loại bỏ hoàn toàn.

### "Có false negative không?"

Có. Bốn nguồn chính: thay đổi chỉ nằm trong thân function, cú pháp parser chưa hỗ trợ, logic chỉ thể hiện trong `BUILD.gn`, và hành vi TypeScript hoặc code riêng của Samsung.

### "Vậy tại sao vẫn hữu ích?"

Vì công cụ phát hiện sớm nhiều nhóm rủi ro khó thấy nếu chỉ dựa vào compiler hoặc release notes, đồng thời thu hẹp một Git diff rất lớn thành danh sách có owner, có lý do và có vị trí source.

Và quan trọng không kém: những phần chưa đọc được cũng được ghi rõ, thay vì bị che đi.

### "Làm sao chứng minh ROI?"

Thử trên một đợt nâng phiên bản đã hoàn thành, hoặc một đợt sắp làm. Đo năm thứ:

- Bao nhiêu finding ưu tiên cao tìm thấy nơi sử dụng trong Samsung source hoặc config.
- Bao nhiêu finding trong số đó trở thành đầu việc thật.
- Bao nhiêu lỗi build hoặc lỗi runtime được phát hiện trước khi merge.
- Thời gian phân loại so với cách làm hiện tại.
- Tỷ lệ báo thừa theo signal và theo loại `Fact`, để điều chỉnh rule về sau.

## 29. Checklist vận hành

```text
[ ] Ghi version FROM/TO đầy đủ bốn phần
[ ] Chạy chromedrift check
[ ] Chạy bộ wide cho lần lập kế hoạch chính thức
[ ] Kiểm tra coverage của bản cũ, bản mới và từng nhóm file
[ ] Xác nhận missing_targets = 0 và out_of_scope_files = 0
[ ] Ghi số liên kết chưa tìm thấy đầu còn lại vào phần giới hạn
[ ] Phân loại Breaking theo owner
[ ] Phân loại Behaviour change trên Windows
[ ] Trong Housekeeping, lọc riêng flag sắp hết hạn và config cũ cần dọn
[ ] Tìm trong Samsung source: key, biến cũ/mới, pref/switch string và tên đầy đủ của Mojo object
[ ] Kiểm tra nơi server bật/tắt feature, cùng script và automation ngoài source repo
[ ] Ghi trạng thái sau khi đối chiếu và owner thực tế
[ ] Chỉ ước lượng effort sau khi tìm thấy nơi Samsung sử dụng
[ ] Lưu JSON, Markdown, HTML và lệnh đã chạy
[ ] Vẫn thực hiện quy trình merge, build, test và kiểm tra sản phẩm hiện có
```

## 30. Kết luận đề xuất

ChromeDrift đáng dùng vì nó giải đúng một phần việc đang tốn thời gian và dễ sai trong mỗi đợt nâng phiên bản Chromium:

- Chuyển các khai báo trong source thành `Fact` ổn định, để so sánh được giữa hai version.
- Tách bạch bốn nhóm: thay đổi có thể phá contract, thay đổi hành vi, phần mới xuất hiện, và phần chỉ dọn code.
- Xác định thay đổi có nằm trong Windows build hay không.
- Đo coverage và hạ độ tin cậy khi chưa đủ bằng chứng để kết luận một đối tượng đã biến mất.
- Giao finding cho đúng owner và giữ vị trí source để kiểm tra lại.
- Cung cấp checklist để engineer hoặc agent đối chiếu với Samsung source.

Đề nghị hợp lý **không phải** là "dùng tool làm release gate ngay". Đề nghị là:

> **Thử ChromeDrift như một lớp phát hiện sớm trước khi merge một phiên bản Chromium thật: chạy `wide`, đối chiếu finding với Samsung source và config, rồi đo xem bao nhiêu finding trở thành đầu việc.**

Nếu lần thử cho thấy công cụ tìm được công việc liên quan tới C++ symbol, config hoặc IPC **trước khi merge**, và giảm được thời gian đọc Git diff, thì giá trị của project đã được chứng minh.

Kết quả đó cũng chính là dữ liệu cần thiết để xây một cách chấm điểm riêng cho Samsung và hỗ trợ dự báo effort về sau.

## 31. Bản đồ source để kiểm tra lại

Dành cho người muốn tự đọc code thay vì tin tài liệu:

- CLI và orchestration: `chromedrift/cli.py`
- Xác định version, Gitiles/local source, cache marker: `chromedrift/acquire.py`
- Dựng snapshot, cache và meta: `chromedrift/snapshot.py`
- Target set, discovery, coverage, partition: `chromedrift/targets.py`
- Điều kiện thuộc sản phẩm, dùng chung: `chromedrift/eligibility.py`
- Registry extractor và việc đóng dấu platform: `chromedrift/extract/__init__.py`
- Bộ đánh giá platform cho C++/GRIT/Mojo: `chromedrift/extract/_cpp.py`
- Chín extractor: `chromedrift/extract/*.py`
- Schema của Fact/Snapshot/Change/Finding/Report: `chromedrift/model.py`
- So sánh ngữ nghĩa, signal, bucket, owner: `chromedrift/diff.py`
- Các modifier khi chấm điểm: `chromedrift/score.py`
- Reference closure và kiểm tra phạm vi: `chromedrift/catalog.py`
- Gom nhóm các thay đổi liên quan: `chromedrift/cluster.py`
- Ngữ cảnh từ Chromestatus: `chromedrift/enrich/chromestatus.py`
- Câu chữ của report, Markdown và HTML: `chromedrift/report/`
- Playbook cho người và agent: `skills/analyzing-chromium-uprevs/`
- Tests: `tests/test_extract.py`, `tests/test_pipeline.py`, `tests/js/report_dom.js`
- Audit kỹ thuật chi tiết và lịch sử: `docs/ChromeDrift Project Audit.md`

## Phụ lục: thuật ngữ riêng của Chromium

| Thuật ngữ | Ý nghĩa trong project |
|---|---|
| Uprev | Chuyển Samsung Browser từ một Chromium version lên version mới hơn |
| Blink | Rendering engine của Chromium; xử lý DOM, layout và phần lớn Web Platform API mà website sử dụng |
| Web IDL | Ngôn ngữ khai báo Web API mà Blink cung cấp cho JavaScript — interface, method, property |
| Mojo / `.mojom` | IPC framework của Chromium. File `.mojom` khai báo interface, method và data type trao đổi giữa các process. `Interface` ở đây là IPC contract, **không phải** UI |
| WebUI | Framework dùng cho page nội bộ như `chrome://settings` hoặc `chrome://downloads`; phần hiển thị dùng HTML/TypeScript và dữ liệu thường đến từ C++ handler |
| Preference / `pref` | Setting được browser lưu trong user profile, chẳng hạn có hỏi trước khi download hay không |
| `base::Feature` | Feature flag trong C++ của Chromium; mỗi feature có tên nhận diện và trạng thái mặc định bật hoặc tắt |
| `FeatureParam` | Giá trị đi kèm feature, chẳng hạn `button_style=compact`; mỗi nhóm thử nghiệm có thể nhận giá trị khác nhau |
| Finch | Hệ thống rollout và A/B testing của Chrome; server quyết định feature nào được bật cho nhóm người dùng nào, không cần phát hành browser mới |
| `chrome://flags` | Page nội bộ cho phép bật/tắt feature thử nghiệm; mỗi entry thường có milestone hết hạn |
| Milestone, ví dụ M151 | Major version của Chrome/Chromium; M151 gồm nhiều bản vá `151.x.x.x` |
| ChromiumDash | Service cung cấp thông tin về các Chrome release; công cụ dùng nó để tìm bản Stable Windows khi đầu vào chỉ là milestone |
| Gitiles | HTTP interface để đọc Chromium Git repository theo một ref cụ thể, không cần clone toàn bộ repository |
| Chromestatus | Thông tin về vòng đời Web Platform feature; chỉ dùng làm bối cảnh, không quyết định score |
| GRIT | Hệ thống build resource của Chromium; điều kiện GRIT cho biết WebUI resource có nằm trong Windows build hay không |
| Polymer / Lit | Hai framework component được các thế hệ WebUI của Chromium sử dụng |
| Origin Trial | Cơ chế cho phép một số website thử Web API chưa phát hành rộng, bằng token có thời hạn |
