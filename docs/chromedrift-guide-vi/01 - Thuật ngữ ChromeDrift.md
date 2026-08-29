# 1. Thuật ngữ dùng trong ChromeDrift

Tài liệu này là từ điển tra cứu. Không cần đọc hết một lượt — khi gặp một từ lạ trong báo cáo hoặc trong các phần khác của bộ tài liệu, quay lại đây tìm.

Mỗi mục được viết theo cùng một khuôn: **từ đó nghĩa là gì**, **ví dụ cụ thể**, và khi cần thì thêm **vì sao ChromeDrift quan tâm**.

## Mười từ nên biết trước

Nếu chỉ đọc được mười dòng, hãy đọc mười dòng này. Chúng là bộ khung của toàn bộ công cụ.

| Từ | Hiểu nhanh |
|---|---|
| `uprev` | Một đợt nâng nền Chromium của Samsung Browser từ version cũ lên version mới |
| `upstream` | Chromium gốc do Google phát triển; đối lập với `downstream` là Samsung Browser |
| Khai báo (declaration) | Một dòng source định nghĩa ra một thứ có tên: một feature flag, một Web API, một preference key... |
| `Fact` | Một khai báo đã được ChromeDrift rút gọn thành object JSON nhỏ để so sánh được giữa hai version |
| `Snapshot` | Toàn bộ `Fact` đọc được ở **một** version Chromium |
| `Change` | Kết quả so sánh một `Fact` giữa hai snapshot: được thêm, bị bỏ, hay bị sửa |
| `signal` | Nhãn mô tả chính xác chuyện gì đã xảy ra, ví dụ `pref_renamed` (preference key đã bị đổi tên) |
| `score` | Điểm ưu tiên từ 0 đến 100 để biết nên xem thay đổi nào trước — **không phải** xác suất có bug |
| `bucket` | Bốn nhóm hậu quả: Breaking / Behaviour change / New surface / Housekeeping |
| `owner` | Team kỹ thuật nên kiểm tra thay đổi này đầu tiên |

Luồng chạy nối các từ trên lại thành một chuỗi:

```text
Chromium version cũ  ──┐
                       ├──► Fact ──► Snapshot ──┐
Chromium version mới ──┘                        ├──► Change ──► signal ──► score + bucket + owner ──► báo cáo
                                                ┘
```

## Nhóm 1 — Phiên bản và mã nguồn

### Chromium

Project mã nguồn mở làm nền cho Chrome và nhiều browser khác. Trong toàn bộ tài liệu này, khi nói "Chromium" là nói tới mã nguồn `upstream` mà Samsung Browser lấy về để tích hợp.

### Chromium khác Chrome ở chỗ nào

Chromium là codebase mở, ai cũng tải được. Chrome là sản phẩm của Google, được build từ Chromium rồi cộng thêm branding, các service riêng và cấu hình riêng.

ChromeDrift đọc **mã nguồn Chromium**, và đọc thêm **dữ liệu release của Chromium/Chrome** chỉ để xác định một số version là bản nào. Công cụ không mở file binary của Chrome và không so binary Chrome với binary Samsung Browser.

### Upstream, downstream và fork

Ba từ này mô tả quan hệ giữa Chromium và Samsung Browser:

- `upstream`: Chromium gốc — nguồn mà code chảy xuống từ đó.
- `downstream`: sản phẩm lấy Chromium làm nền và có phần sửa riêng. Ở đây là Samsung Browser.
- `fork`: nhánh code phát triển ra từ Chromium.

Cần lưu ý: `fork` **không** có nghĩa là tách hẳn và không quay lại. Samsung vẫn định kỳ nhận code mới từ upstream, và chính việc nhận code định kỳ đó tạo ra bài toán mà ChromeDrift muốn giải.

### Uprev

`uprev` là việc nâng phiên bản nền của một dependency lên bản mới hơn. Với Samsung Browser, một đợt uprev nghĩa là: chuyển nền Chromium từ version cũ sang version mới, merge các thay đổi upstream, xử lý conflict, sửa những chỗ code riêng không còn tương thích, rồi kiểm tra những hành vi mới xuất hiện.

Trong tài liệu và trong ticket, nên viết "đợt uprev Chromium" hoặc "nâng version Chromium". Không cần cố dịch `uprev` thành một cụm tiếng Việt dài dòng.

### Milestone

Số major của Chromium, ví dụ `M151`. Một milestone không phải một bản build duy nhất — nó có nhiều bản vá stable lần lượt ra đời, dạng `151.0.x.y`.

### Full version

Version đủ bốn phần, ví dụ `151.0.7922.138`.

Đây là thứ xác định **chính xác một bản release**. Khi cần một kết quả mà người khác chạy lại cũng ra y hệt, phải dùng full version chứ không dùng mỗi số `151`.

### Ref, tag và commit SHA

Ba cách chỉ tới một trạng thái mã nguồn trong Git:

- `ref`: từ chung mà Git dùng để chỉ một trạng thái source. Nó có thể là một branch, một tag, hoặc một SHA.
- `tag`: một cái tên cố định gắn với một bản release, ví dụ `refs/tags/151.0.7922.138`. Tag đã tạo thì không đổi nữa.
- `commit SHA`: mã định danh của một commit cụ thể.

ChromeDrift luôn quy full version về dạng tag. Nếu người dùng chỉ nhập milestone, công cụ đi tìm bản Windows Stable mới nhất của milestone đó trước, rồi mới tạo tag từ full version tìm được.

### ChromiumDash

Một API công khai cung cấp thông tin về các bản release của Chromium/Chrome. ChromeDrift chỉ gọi tới nó trong đúng một tình huống: đầu vào chỉ có milestone, và công cụ cần biết full version Windows Stable tương ứng là bản nào.

ChromiumDash **không** cung cấp mã nguồn. Bước lấy source dùng nguồn khác.

### Gitiles

Một web service cho phép đọc Git repository của Chromium qua HTTP, không cần clone toàn bộ repository về máy. ChromeDrift dùng Gitiles để làm ba việc:

- xem danh sách file trong một thư mục, tại đúng tag cần đọc;
- tải về một file đơn lẻ;
- tải về cả một thư mục dưới dạng archive nén `.tar.gz`.

### Checkout và thư mục `src/`

`checkout` là bản mã nguồn đã được lấy về máy. Trong một checkout Chromium chuẩn, `src/` là thư mục gốc, bên trong chứa `chrome/`, `content/`, `components/`, `third_party/` và nhiều thư mục khác.

Khi chạy ChromeDrift với option `--local-src` (đọc source có sẵn trên máy thay vì tải qua mạng), phải truyền đúng đường dẫn tới thư mục `src/` — không phải thư mục cha của nó, và cũng không phải một thư mục con đã bị cắt bớt.

### `depot_tools` và `gclient sync`

`depot_tools` là bộ công cụ chuẩn của Chromium; `gclient sync` là lệnh dùng để tạo ra một checkout Chromium đầy đủ — kéo về dependency, generated file và các repository liên quan. Đây là quy trình bình thường khi muốn build Chromium.

ChromeDrift **không cần** chạy `gclient sync` khi dùng Gitiles, vì nó chỉ đọc một số file khai báo chứ không build gì cả. Nhưng nếu chọn dùng checkout có sẵn trên máy, thì việc checkout đó đầy đủ và đúng version là trách nhiệm của người chuẩn bị source, công cụ không tự kiểm tra hộ.

### Source tree, directory tree và relative path

Ba mức phạm vi khác nhau khi nói về cấu trúc thư mục:

- `source tree`: toàn bộ cấu trúc thư mục và file của mã nguồn ở một version.
- `directory tree`: một nhánh con trong đó, ví dụ `chrome/browser/resources/settings/`.
- `relative path`: đường dẫn tính từ thư mục `src/` của Chromium, ví dụ `content/common/features.cc`.

ChromeDrift luôn giữ nguyên relative path khi lưu file về máy. Có hai lý do: bộ đọc nhận ra đúng loại file nhờ đường dẫn, và báo cáo trỏ được về đúng `path:dòng` để người đọc mở source kiểm tra.

### Archive

Gói nén của một thư mục tại đúng một Git ref. Gitiles có thể trả về archive cho cả một nhánh con.

Khi giải nén, ChromeDrift kiểm tra từng đường dẫn bên trong để archive không thể ghi file ra ngoài thư mục đích, và chỉ ghi ra những file khớp bộ lọc đuôi file đã khai báo.

### Cache

Dữ liệu được lưu lại để lần chạy sau không phải tải và xử lý lại phần không đổi. Cache của ChromeDrift gồm bốn thứ:

- danh sách cây file theo từng ref;
- cây source đã tải về;
- marker đánh dấu một target đã tải thành công, hay thực sự không tồn tại;
- snapshot đã trích xuất xong.

Tag release là bất biến, nên cache theo tag có thể tái sử dụng an toàn. Khi schema hoặc bộ lọc của công cụ thay đổi, khoá cache cũng đổi theo, để không bao giờ đọc nhầm dữ liệu cũ với logic mới.

## Nhóm 2 — Phạm vi đọc mã nguồn

Nhóm từ này trả lời câu hỏi: một lần chạy ChromeDrift **cam kết đọc những gì**, và đọc được bao nhiêu phần trăm so với những gì đáng lẽ nên đọc.

### Target

Một chỉ dẫn tải source. Có hai dạng:

- `file`: tải đúng một file;
- `tree`: tải archive của cả một thư mục, nhưng chỉ giữ lại những file có tên khớp bộ lọc `include`.

Mỗi target có bốn thuộc tính: `path` (tải ở đâu), `kind` (file hay tree), `include` (giữ lại những đuôi file nào) và `note` (ghi chú để người đọc biết target này phục vụ gì).

### Target set

Một tập hợp target, tương ứng với một mức độ quét. ChromeDrift có ba target set:

| Target set | Dùng khi nào | Đặc điểm |
|---|---|---|
| `minimal` | Thử xem công cụ có chạy được không | Rất nhanh, chỉ giữ phần lõi, không đủ để kết luận gì |
| `default` | Chạy hằng ngày | Khoảng 40 MB mỗi version theo ghi chú hiện tại của project |
| `wide` | Phân tích cho một đợt release thật | Phủ toàn bộ dạng tên file mà bộ đọc hiểu, trong những thư mục gốc đã chọn; lớn hơn đáng kể |

### Partition

Giới hạn một lần chạy vào một khu vực chức năng, ví dụ `settings`, `downloads`, `network` hoặc `webplatform`.

Partition rất tiện khi cần điều tra nhanh một area. Nhưng nó **không phù hợp** làm cửa kiểm tra cuối trước khi release, vì một thay đổi ảnh hưởng Settings hoàn toàn có thể nằm ở một subsystem khác, ngoài partition đang chọn.

### `--complete`

Một option áp dụng cho một số partition có thư mục gốc đủ nhỏ. Khi bật, công cụ tải mọi file mà bộ đọc có thể hiểu bên trong thư mục gốc đó.

Từ "complete" ở đây dễ gây hiểu nhầm, nên nói rõ: nó **không** có nghĩa là "toàn bộ Chromium". Những partition quá lớn như `webplatform` không được phép dùng `--complete`, vì Gitiles chỉ có thể gửi nguyên cả thư mục và chi phí sẽ quá lớn.

### Discovery

Bước hỏi cây source: file nào đang tồn tại ở version này, và trong số đó file nào có hình dạng mà một bộ đọc có thể hiểu được.

Discovery dùng để **đo** phạm vi, chứ không tự quyết định tải hết mọi file tìm thấy. Việc tải gì do target set quyết định.

### Candidate file

File có đường dẫn hoặc tên khớp ít nhất một điều kiện `applies_to()` của một extractor, và không thuộc các nhóm đã bị loại (file test, output do máy sinh ra, code của platform khác, hoặc binary khác không phải browser).

Từ "candidate" (ứng viên) được chọn có chủ ý: file đó **có khả năng** chứa khai báo, chứ không bảo đảm nó thật sự tạo ra `Fact` nào.

### Coverage

Tỷ lệ candidate file mà target set thực sự đọc tới:

```text
coverage = số candidate file mà target chạm tới / tổng số candidate file nhìn thấy được
```

Coverage được tính cả ở mức tổng thể và ở mức từng nhóm (từng surface). Coverage theo từng nhóm mới là con số quan trọng khi đánh giá một kết luận dạng "khai báo này đã biến mất": target set `default` có thể đọc gần hết file Web IDL, nhưng chỉ đọc được một phần rất nhỏ file chứa pref và switch.

### Missing target

Một target được yêu cầu nhưng không tồn tại ở version đó.

Với version cũ, đây có thể là chuyện hoàn toàn bình thường — file chưa được tạo ra. Nhưng nó bắt buộc phải xuất hiện trong metadata và trong báo cáo, vì "file này chưa tồn tại" và "khai báo này đã bị xoá" là hai kết luận khác hẳn nhau, không được phép lẫn lộn.

### Incomplete acquisition

Một lần lấy source bị lỗi hoặc bị thủng, khiến một file đáng lẽ phải đọc lại không có dữ liệu.

Hậu quả: mọi bằng chứng về việc "đã bị xoá" trong lần chạy đó đều yếu đi, vì "không thấy" lúc này có thể chỉ là do tải hỏng.

## Nhóm 3 — Kiến trúc của browser

Nhóm từ này giải thích các bộ phận bên trong Chromium mà ChromeDrift theo dõi.

### Browser process, renderer process và process boundary

Chromium không chạy trong một process duy nhất. Nó tách browser thành nhiều process:

- **browser process** quản lý tab, profile, setting và quyền;
- **renderer process** chạy nội dung web của từng trang;
- các process khác lo network, GPU, media...

`process boundary` là ranh giới giữa hai process. Dữ liệu muốn đi qua ranh giới này phải tuân theo một contract chung mà cả hai bên cùng hiểu — và đó chính là chỗ dễ hỏng khi một bên đổi mà bên kia không đổi.

### IPC

`Inter-Process Communication` (giao tiếp giữa các process): cơ chế để các process trao đổi message với nhau. Trong Chromium, hệ thống IPC chính là Mojo.

Điều làm IPC nguy hiểm khi uprev: một thay đổi IPC có thể **không** làm phần code Samsung đang sửa báo lỗi lúc compile, nhưng vẫn gây lỗi lúc chạy, vì hai đầu hiểu message theo hai cách khác nhau.

### Mojo

Framework IPC của Chromium, kèm theo một ngôn ngữ riêng để khai báo contract. File `.mojom` mô tả:

| Thành phần | Nghĩa |
|---|---|
| `interface` | Nhóm method có thể gọi xuyên qua ranh giới process |
| `method` | Một message request, có thể kèm response |
| `struct` / `union` | Cấu trúc dữ liệu được truyền qua đường truyền (wire) |
| `field` | Một trường bên trong cấu trúc dữ liệu đó |
| `enum` | Tập giá trị được truyền qua wire |
| `ordinal` | Con số dùng để nhận diện method hoặc field trên wire |
| `[Stable]`, `[MinVersion]` | Cam kết về tương thích và đánh version |

### ABI

Contract ở mức binary hoặc mức đường truyền.

Trong báo cáo, khi thấy câu "Mojo ABI changed", nghĩa là hình dạng của message hoặc của dữ liệu đi qua IPC đã đổi. Nó **không** đồng nghĩa với ABI của C/C++ trên toàn bộ browser.

### Blink

Rendering engine của Chromium, đồng thời là nơi hiện thực phần Web Platform. Blink quyết định một trang web có thể gọi được những Web API nào, và mỗi feature đang ở trạng thái nào: đang test, đang thử nghiệm (experimental), hay đã ổn định (stable).

### Web Platform và Web API

Các API mà website gọi được — DOM, CSS, media, storage, networking...

Cần phân biệt rõ với WebUI: Web Platform là bề mặt dành cho **nội dung web bên ngoài**, còn WebUI là các trang nội bộ của chính browser.

### Web IDL

Ngôn ngữ dùng để khai báo hình dạng của một Web API. Một file `.idl` cho biết interface có những gì: method, attribute, tham số, kiểu trả về, quan hệ kế thừa và các extended attribute.

Một quy tắc quan trọng của ChromeDrift: chỉ những file `.idl` nằm dưới `third_party/blink/renderer/` mới được coi là Web IDL của Blink. Các file `.idl` ở chỗ khác — của extension API, hoặc của Windows MIDL — là những dialect hoàn toàn khác, đọc nhầm sẽ tạo ra kết luận sai.

### Interface

Trong bộ tài liệu này, từ `interface` được giữ nguyên tiếng Anh, vì dịch thành "giao diện" sẽ mất nghĩa. Tuỳ ngữ cảnh, nó là một trong ba thứ khác nhau:

| Ngữ cảnh | `interface` nghĩa là |
|---|---|
| Web IDL | Contract mà JavaScript trên website nhìn thấy |
| Mojo | Contract để gọi xuyên qua IPC |
| UI / WebUI | Màn hình hoặc phần người dùng tương tác |

Ba nghĩa này tuyệt đối không được trộn với nhau. Khi đọc báo cáo, hãy nhìn `kind` của `Fact` để biết đang nói về nghĩa nào.

### Runtime-enabled feature

Một entry trong file `runtime_enabled_features.json5`, dùng để điều khiển việc Blink có expose một Web API ra ngoài hay không. Trạng thái của cùng một feature có thể khác nhau giữa các platform.

### Origin Trial

Cơ chế cho phép một website được cấp token để dùng thử một feature Web Platform chưa mở rộng rãi. Các thuộc tính của trial — tên, hệ điều hành nào được phép, có cho bên thứ ba dùng không, có cho phép trong ngữ cảnh không bảo mật không — quyết định ai thật sự tiếp cận được feature.

### WebUI

Các trang nội bộ của browser, được viết bằng công nghệ web và thường có URL dạng `chrome://...` — ví dụ Settings, History, Downloads, Bookmarks, Extensions.

WebUI không phải website thông thường, và cũng không phải toàn bộ giao diện native của browser.

### Route

Định nghĩa một trang hoặc trang con, cùng quan hệ điều hướng giữa chúng, trong một surface WebUI. Một route có tên, có path, có route cha, và có thể được bảo vệ bằng một điều kiện `loadTimeData`.

### Control

Thành phần mà người dùng tương tác trong template WebUI: toggle, dropdown, radio group, ô nhập, nút bấm...

ChromeDrift theo dõi bốn thứ ở mỗi control: tag của element, thuộc tính `id`, khoá label dùng cho đa ngôn ngữ, pref mà nó ghi vào, và điều kiện build.

### `loadTimeData`

Cầu nối đưa dữ liệu và cấu hình từ phía C++ sang phía TypeScript/HTML của WebUI.

Một route hoặc control ở phía giao diện gọi `loadTimeData.getBoolean('key')` để hỏi giá trị; phía C++ dùng `AddBoolean("key", biểu_thức)` để đặt giá trị đó. Nếu một trong hai đầu đổi mà đầu kia không đổi, trang có thể biến mất hoặc hiện ra không đúng lúc.

### Gate và guard

Điều kiện quyết định một khai báo, một trang hoặc một control có tồn tại — hoặc có được nhìn thấy — hay không. Chromium có nhiều loại:

| Loại | Cú pháp |
|---|---|
| C++ guard | `#if BUILDFLAG(...)` |
| Mojo guard | `[EnableIf=...]` |
| GRIT guard | `<if expr="...">` |
| WebUI runtime guard | `loadTimeData.getBoolean(...)` |
| Blink gate | `[RuntimeEnabled=...]` |

### GRIT

Hệ thống quản lý resource và build của Chromium. Trong phạm vi những file mà ChromeDrift đọc, điều kiện GRIT `<if expr>` quyết định một template hoặc một control có được đưa vào bản build cho Windows hay không.

### Polymer và Lit

Hai cách Chromium viết template WebUI. Polymer thường dùng file `.html` với binding kiểu `{{prefs.x}}`; Lit thường dùng file `.html.ts` với template literal.

ChromeDrift hỗ trợ cả hai, vì các surface WebUI đang chuyển từ Polymer sang Lit với tốc độ không đồng đều — cùng một lúc trong Chromium sẽ có cả hai kiểu.

## Nhóm 4 — Feature và cấu hình

### `base::Feature`

Feature flag ở phía C++ của Chromium. Mỗi khai báo chứa: tên C++ dạng `kFoo`, chuỗi tên feature dạng `"Foo"`, trạng thái mặc định, và có thể có thêm điều kiện build theo platform.

### Feature string và C++ symbol — hai tên của cùng một feature

Đây là một trong những chỗ dễ nhầm nhất, nên tách riêng ra:

| | C++ symbol | Feature string |
|---|---|---|
| Trông như thế nào | `features::kFoo` | `"Foo"` |
| Ai dùng | Code C++ gọi trực tiếp | Finch và `--enable-features` |
| Nếu bị đổi tên | Build thường fail ngay — dễ phát hiện | Cấu hình cũ **im lặng** mất tác dụng — rất khó phát hiện |

Chính sự bất đối xứng này là lý do ChromeDrift theo dõi cả hai tên riêng biệt.

### `FeatureParam`

Tham số đi kèm một feature — ví dụ một timeout, một ngưỡng, hoặc một chế độ. Finch có thể đặt cho param một giá trị khác với mặc định.

Hai kiểu thay đổi cần phân biệt: đổi giá trị mặc định thì hành vi mặc định thay đổi; còn xoá hoặc đổi tên param thì cấu hình cũ không còn hiệu lực nữa.

### Feature flag

Tên gọi chung cho cơ chế bật/tắt một feature. Từ này mơ hồ, nên khi đọc phải nhìn ngữ cảnh để biết đang nói về `base::Feature`, về Blink runtime feature, về một entry trong `chrome://flags`, hay về một cấu hình khác.

### Finch

Hệ thống phía server của Chrome, dùng để triển khai thử nghiệm và thay đổi cấu hình cho từng nhóm người dùng mà không cần phát hành bản binary mới. Finch thường quyết định ba thứ:

- một `base::Feature` được bật hay tắt;
- giá trị cụ thể cho một `FeatureParam`;
- rule chọn nhóm người dùng hoặc nhóm thiết bị nào nhận cấu hình đó.

Giới hạn cần nói rõ: ChromeDrift chỉ nhìn thấy **tên và cách đấu nối được khai báo trong mã nguồn Chromium**. Nó không biết Samsung có hệ thống rollout tương đương hay không, đang dùng tên feature nào, hay đang đặt param bằng bao nhiêu — trừ khi được cấp riêng nguồn cấu hình đó.

### Kill switch

Một flag cho phép tắt nhanh một feature đã ship, phòng khi có sự cố.

Khi Chromium xoá kill switch sau lúc feature đã ổn định, thường thì hành vi đã trở thành cố định từ trước rồi. Việc cần kiểm tra lúc này không phải "hành vi vừa đổi", mà là "còn cấu hình bên ngoài nào vẫn cố override flag đó không".

### Command-line switch

Tham số truyền vào khi khởi động process, ví dụ `--enable-foo`. Script, automation hoặc test harness có thể đang phụ thuộc vào đúng chuỗi này.

Khác với Finch ở chỗ: switch nằm trên dòng lệnh của chính process, còn Finch là cấu hình gửi từ server xuống.

### Preference, gọi tắt là pref

Khoá dùng để lưu một setting trong profile người dùng hoặc trong local state, ví dụ `download.prompt_for_download`.

Hậu quả khi đổi pref key rất đặc thù: dữ liệu cũ vẫn nằm nguyên trên ổ đĩa, nhưng code mới không đọc nó bằng khoá cũ nữa, nên setting của người dùng có thể quay về mặc định mà không có cảnh báo nào. Cũng như với feature, C++ symbol của pref và chuỗi key là hai thứ khác nhau.

### Entry trong `chrome://flags`

Mục mà người dùng hoặc developer nhìn thấy trên trang `chrome://flags`.

File `flag-metadata.json` chủ yếu cho ChromeDrift biết ai là owner upstream và milestone dự kiến xoá entry. Nó **không** phải khai báo đầy đủ của feature phía C++.

### Cấu hình nằm ngoài repository

Những thứ ảnh hưởng tới browser nhưng không nằm trong mã nguồn Chromium đang được quét: cấu hình Finch/rollout, script khởi động, automation, deployment cho doanh nghiệp, và backend chứa policy.

Trong báo cáo, owner `config` được hiển thị bằng nhãn `Outside the repository`, để nhắc người đọc rằng việc xác minh phải diễn ra ở một nguồn khác, không tìm trong Chromium được.

## Nhóm 5 — Dữ liệu bên trong ChromeDrift

Đây là nhóm từ riêng của công cụ. Hiểu nhóm này là hiểu cách đọc báo cáo.

### Extractor

Một bộ đọc chuyên trách cho một dạng source. Mỗi extractor gồm đúng hai phần:

- `applies_to(path)`: trả lời câu hỏi "file này có đúng dialect và đúng đường dẫn mà tôi hiểu không?";
- `extract(text, path)`: đọc nội dung file và tạo ra danh sách `Fact`.

### Fact

Một khai báo đã được chuẩn hoá thành object có identity ổn định.

Ba điều `Fact` **không** phải: nó không phải toàn bộ nội dung file, không phải một đoạn AST đầy đủ, và không phải nhận xét do AI sinh ra. Nó là dữ liệu có cấu trúc, do một parser lấy trực tiếp từ source.

### `kind`, `key`, `name`, `path`, `line`, `attrs`

Sáu trường của một `Fact`:

| Trường | Dùng để làm gì |
|---|---|
| `kind` | Loại `Fact`, ví dụ `mojo_method` |
| `key` | Identity ổn định trong cùng một `kind` |
| `name` | Tên dùng để hiển thị cho người đọc |
| `path`, `line` | Bằng chứng nằm ở đâu trong source |
| `attrs` | Những thuộc tính cần để hiểu và so sánh khai báo |

### UID

Identity dùng để ghép một khai báo giữa hai version, ghép bằng cách nối `kind` với `key`:

```text
uid = kind + ":" + key
```

Ví dụ `pref:download.prompt_for_download`. Hai `Fact` có cùng UID được coi là cùng một khai báo, quan sát ở hai version khác nhau.

### Normalization (chuẩn hoá)

Đưa nhiều cách viết source khác nhau nhưng cùng ý nghĩa về một biểu diễn chung.

Ví dụ: macro `BASE_FEATURE` có dạng hai tham số và dạng ba tham số; cả hai đều được chuẩn hoá về cùng một feature name, cùng trạng thái, cùng trạng thái theo platform. Mục đích là bỏ qua thay đổi thuần cú pháp, nhưng vẫn giữ lại thay đổi thật về hành vi.

### Deduplication (loại bản ghi trùng)

Gộp các `Fact` trùng UID theo một quy tắc cố định. ChromeDrift chọn khai báo có `(path, line)` nhỏ nhất, đồng thời tổng hợp thêm metadata của các overload khi cần.

Lý do phải cố định: nếu không, kết quả sẽ phụ thuộc vào thứ tự file mà hệ điều hành trả về, và hai lần chạy trên cùng một cây source có thể ra hai kết quả khác nhau.

### Snapshot

Toàn bộ `Fact` của một Chromium ref, kèm theo milestone, target set, coverage, thống kê tải file, và danh sách lỗi hoặc target bị thiếu.

Snapshot là **đầu ra** của hai bước lấy source và trích xuất, đồng thời là **đầu vào** của bước so sánh.

### Semantic diff (so sánh theo ý nghĩa)

So sánh dựa trên ý nghĩa thay vì so từng dòng text. ChromeDrift ghép các `Fact` theo UID, rồi chỉ so những thuộc tính được coi là có hậu quả.

Ví dụ cụ thể: `declared_form` đổi vì Chromium thay macro thì **không** tạo ra finding nào; còn `default_state` đổi thì có.

### Change

Kết quả cho thấy một `Fact` khác nhau giữa hai snapshot. Một `Change` gồm:

- `change_type`: `added` (chỉ có ở bản mới), `removed` (chỉ có ở bản cũ) hoặc `modified` (có ở cả hai nhưng khác nhau);
- `deltas`: giữ cặp `[giá trị cũ, giá trị mới]`;
- `signals`: giải thích bản chất của thay đổi;
- `severity`: mức nghiêm trọng cơ sở.

### Signal và leading signal

`signal` là một nhãn có ngữ nghĩa rõ ràng, ví dụ `ipc_signature_change` hoặc `pref_renamed`. Một `Change` có thể mang nhiều signal cùng lúc.

`leading signal` là signal có severity cao nhất trong số đó. Nếu có hai signal bằng điểm, công cụ chọn theo thứ tự tên, để kết quả luôn giống nhau ở mọi lần chạy.

Leading signal quan trọng vì nó quyết định ba thứ: severity, bucket, và đôi khi cả việc chuyển finding sang owner khác.

### Severity và score

Hai con số khác nhau, rất hay bị nhầm:

- `severity` là mức quan trọng **cơ sở** của loại thay đổi, lấy từ leading signal, hoặc từ bảng mặc định theo `kind` + hướng thay đổi nếu không có signal nào.
- `score` là điểm **cuối cùng**, sau khi đã xét thêm hai yếu tố: khai báo có nằm trong bản build Windows không, và bằng chứng cho kết luận "đã biến mất" có đáng tin không.

Cần nói rõ điều `score` không phải: nó không phải xác suất Samsung bị lỗi, và cũng không phải ước lượng số ngày công.

### Bucket

Cách phân loại bản chất của một finding. Có đúng bốn nhóm:

| Bucket | Nghĩa |
|---|---|
| `Breaking` | Một contract bên ngoài binary có thể ngừng hoạt động mà không có cảnh báo rõ ràng nào |
| `Behaviour change` | Bản build Windows sẽ hành xử khác đi |
| `New surface` | Có API, trang hoặc control mới xuất hiện — nhưng sự tồn tại của khai báo không tự động bật một hành vi nào |
| `Housekeeping` | Dọn flag, đổi lịch xoá, chuyển khai báo sang file khác, hoặc bằng chứng chưa đủ để kết luận là breaking |

### Owner

Khu vực nên nhận finding đầu tiên. Có năm giá trị: `Process boundaries`, `Web platform`, `Browser C++`, `WebUI front-end` và `Outside the repository`.

Lưu ý: đây là routing theo **bề mặt kỹ thuật và nơi cần sửa**, không phải tên một cá nhân, và cũng không phải file CODEOWNERS của Chromium.

### Finding

Một `Change` sau khi đã được chấm điểm và xếp bucket, kèm theo trường `reasons` giải thích từng bước tính điểm.

`Finding` là đơn vị chính mà người đọc nhìn thấy trong báo cáo.

### Enrichment và cluster

Hai bước bổ sung ngữ cảnh, không ảnh hưởng tới điểm số:

- `enrichment`: thêm ngữ cảnh từ nguồn ngoài, ví dụ metadata từ ChromeStatus khi được bật.
- `cluster`: gom các finding có liên quan lại, để người đọc thấy một đợt migration như một câu chuyện liền mạch, thay vì mấy dòng rời rạc không hiểu vì sao lại xuất hiện cùng lúc.

### Báo cáo dạng JSON, Markdown và HTML

Cùng một dữ liệu, ba định dạng cho ba mục đích:

| Định dạng | Dùng khi |
|---|---|
| JSON | Cần dữ liệu đầy đủ cho automation hoặc cho agent xử lý |
| Markdown | Cần review, lưu lại làm artifact, hoặc dán vào ticket |
| HTML | Cần duyệt và lọc tương tác theo bucket, owner, kind, điểm số và từ khoá |

## Nhóm 6 — Truy nguyên thay đổi

Nhóm này chỉ dùng cho chặng trả lời câu hỏi *vì sao* một thay đổi xảy ra. Toàn bộ cơ chế nằm trong [phần 7](<07 - Truy nguyên CL và issue.md>).

### Gerrit

Review server của Chromium, tại `chromium-review.googlesource.com`. Mọi thay đổi vào Chromium đều phải đi qua đây trước khi vào cây source, nên nó là nơi duy nhất trả lời được câu hỏi *ai đã làm việc này*.

Đọc được **ẩn danh**, không cần tài khoản. Nhưng nó dừng ở 500 dòng cho một truy vấn ẩn danh và không hề báo rằng nó đã dừng.

### CL (changelist)

Một thay đổi đã được review và merge vào Chromium — tương đương khái niệm pull request ở nơi khác. Mỗi CL có một số, ví dụ `7885356`, và mở được tại `chromium-review.googlesource.com/c/chromium/src/+/7885356`.

Một CL mang theo: tiêu đề do tác giả viết, diff của từng file, ngày merge, và footer ghi issue liên quan.

ChromeDrift quan tâm vì tiêu đề CL thường chính là finding được viết bằng lời của người đã tạo ra nó — *"android: Enable AndroidCaptureKeyEvents by default"* nói đúng cái mà `platform_state: disabled → enabled` nói, nhưng nói được cả ý định.

### Issue

Một mục trong bug tracker của Chromium, tại `issues.chromium.org`. CL ghi issue của nó ở footer commit message theo hai dạng:

- `Bug: 41494401` — CL này liên quan tới issue đó;
- `Fixed: 41494401` — CL này đóng issue đó.

Hai dạng được hiển thị **tách nhau**, vì tham chiếu và đóng là hai khẳng định khác nhau.

Khoảng **ba trong mười** issue được liên kết trả về HTTP 403 — bị giới hạn cho tài khoản Google, thường vì chúng nằm trong component security hoặc nội bộ. Đó là chuyện bình thường, không phải lỗi công cụ, và các CL thì vẫn đọc được.

### Điểm nhánh (branch point) và `Cr-Branched-From`

Một release branch của Chromium được cắt ra khỏi `main` từ rất sớm, rồi mới được đóng tag nhiều tuần sau đó. Commit message của tag ghi lại chính xác chỗ nó rời `main`, ở dòng `Cr-Branched-From:`.

Điểm nhánh của M148 là **2026-04-06**, tức bảy tuần trước ngày ghi trên chính cái tag M148. Lấy ngày tag làm mốc thì mất bảy tuần CL.

### Merge-back

Một CL land lên release branch **sau khi** branch đã được cắt, thường là bản vá cho một lỗi tìm thấy muộn. Nó nằm trong cây đang được so, nhưng nó không nằm trên `main`.

Đây là lý do câu hỏi tìm CL phải được hỏi lại một lần nữa với ghim branch bị gỡ bỏ.

### Cửa sổ CL (window)

Khoảng thời gian mà một CL phải nằm trong đó để được coi là ứng viên: từ **điểm nhánh của tag cũ** tới **ngày của tag mới**. Hai đầu lấy theo hai cách khác nhau có chủ ý — đầu dưới lấy điểm nhánh để không mất CL, đầu trên lấy ngày tag để không mất merge-back.

### Verdict

Nhãn nói rõ một CL được buộc vào một `Fact` **bằng cách nào**, xếp từ mạnh tới yếu:

| Verdict | Nghĩa |
|---|---|
| `introduced` | CL thêm vào một dòng, nằm trong chính declaration này, mang giá trị mà `Fact` chuyển sang |
| `exact` | một dòng CL đã sửa có mang identifier này |
| `moved` | file bị đổi tên và `Fact` đi theo; không dòng nào thay đổi |
| `declares` | CL sửa thân declaration, không phải dòng đặt tên nó |
| `described` | tiêu đề hoặc mô tả của chính CL nhắc tên nó |
| `crowded` | quá nhiều CL cùng sửa declaration này, nên không cái nào chỉ ra được cái nào |
| `touched` | không gì khớp identifier; đây chỉ là các CL đã chạm file |

Verdict **không** được cộng lại thành điểm số, vì chúng trả lời những câu hỏi khác nhau.

### Trích dẫn và manh mối (citation, lead)

Ranh giới quan trọng nhất trong nhóm này. Các verdict phía trên **gọi tên được `Fact`** — chúng là trích dẫn. Hai verdict cuối chỉ gọi tên được **file** — chúng là manh mối.

Một manh mối tồn tại để một dòng luôn có câu trả lời, chứ không phải để được dán vào ticket như nguyên nhân. Báo cáo giữ hai loại này tách nhau ở ba chỗ độc lập: trạng thái của dòng, màu badge, và một câu chữ ngay trên danh sách.

### Revert, reland và cherry-pick

Ba việc thường xảy ra quanh một feature flag, và Gerrit ghi lại cả ba:

- **revert**: một CL đảo ngược một CL trước đó, thường vì nó làm hỏng test hoặc gây hồi quy;
- **reland**: CL đưa thay đổi đó trở lại sau khi đã sửa nguyên nhân;
- **cherry-pick**: cùng một thay đổi được đưa thêm sang một branch khác.

Vòng đời đầy đủ của một flag thường đọc là: thêm flag → bật mặc định → launch → revert → reland → revert → reland → gỡ bỏ. Đó là lý do một dòng giữ **cả chuỗi** CL chứ không giữ cái tốt nhất, và đọc theo thứ tự **cũ trước**.

### Same-origin và vì sao cần một server

Trình duyệt không cho JavaScript của một trang đọc phản hồi từ một site khác, trừ khi site đó gửi header `Access-Control-Allow-Origin` cho phép. Gerrit không gửi header đó.

Nên `report.html` mở thẳng từ đĩa **không thể** tự hỏi Gerrit. `chromedrift serve` giải quyết bằng cách đổi **ai đi hỏi**: trang gọi `127.0.0.1`, và Python gọi Gerrit. Quy tắc này tồn tại bên trong trình duyệt để bảo vệ cookie người dùng; `urllib` chưa bao giờ chịu nó.

## Những cặp khái niệm dễ hiểu nhầm

Bảng này gom lại các nhầm lẫn đã thực sự xảy ra khi trình bày công cụ. Cột trái là câu người ta hay nói; cột phải là cách hiểu đúng.

| Câu dễ nói nhầm | Cách hiểu đúng |
|---|---|
| "`interface` là giao diện người dùng" | Có thể là contract Web IDL, contract Mojo IPC, hoặc giao diện — phải xem `kind` mới biết |
| "Feature đã được khai báo nghĩa là đã bật" | Khai báo chỉ nói code và flag có tồn tại; còn bật hay không phải xem mặc định, trạng thái theo platform, trạng thái runtime và gate |
| "File đã tải nghĩa là file đã được đọc" | File còn phải qua phạm vi target, qua rule loại trừ, rồi qua `applies_to()` mới thật sự được parse |
| "`removed` nghĩa là upstream đã xoá" | Khi coverage chưa đủ, rất có thể khai báo chỉ chuyển sang một file chưa được đọc |
| "`Breaking` nghĩa là Samsung chắc chắn hỏng" | Nó nói đây là **loại** contract change cần đối chiếu với cách Samsung đang dùng |
| "Score 80 nghĩa là 80% có bug" | Score là thứ tự ưu tiên tính theo rule, không phải xác suất |
| "Owner là người chắc chắn sẽ sửa" | Owner là hàng đợi kiểm tra đầu tiên; sau khi tra cứu thực tế, việc có thể chuyển sang team khác |
| "`wide` nghĩa là toàn bộ implementation của Chromium" | `wide` là toàn bộ **dạng tên file** mà công cụ được thiết kế để đọc, trong các thư mục gốc đã chọn |
| "Finch chính là command-line switch" | Finch là cấu hình/rollout từ phía server; switch là tham số truyền vào lúc khởi động process |
| "`chrome://flags` là toàn bộ hệ thống feature flag" | Nó chỉ là giao diện và metadata cho một phần flag; `base::Feature` và Blink runtime flag là các lớp khác |
| "Không tra được CL nghĩa là không có CL" | Hai cây source khác nhau thì chắc chắn đã có gì đó land. Dòng trống là phát biểu về **cuộc tìm kiếm**, không phải về Chromium |
| "CL được trích dẫn nghĩa là CL đó gây ra finding" | Nó nghĩa là CL đó đã sửa một dòng mang identifier, trong cửa sổ. Một file bị chạm bởi rename, reformat và thay đổi thật sẽ báo cả ba |
| "`crowded` và `touched` cũng là CL tìm được" | Chúng gọi tên file, không gọi tên `Fact`. Đừng trích chúng như nguyên nhân |
| "Issue 403 nghĩa là công cụ hỏng" | Nghĩa là issue bị giới hạn tài khoản. Các CL vẫn công khai và vẫn đọc được |
| "Tra cứu CL chạy trong `run`" | Không. `run` không chạm Gerrit; chỉ `serve` chạm, và chỉ khi có người mở một dòng ra |
