# 1. Thuật ngữ dùng trong ChromeDrift

## Nhóm phiên bản và source code

### Chromium

Project mã nguồn mở làm nền cho Chrome và nhiều browser khác. Trong tài liệu này, “Chromium” luôn chỉ source upstream mà Samsung Browser lấy về để tích hợp.

### Chrome và Chromium

Chromium là codebase mở. Chrome là sản phẩm của Google được build từ Chromium cùng với branding, service và config riêng. ChromeDrift đọc Chromium source và dữ liệu release của Chromium/Chrome để xác định version; nó không so sánh binary Chrome với Samsung Browser.

### Upstream, downstream và fork

- `upstream`: Chromium gốc.
- `downstream`: sản phẩm lấy Chromium làm nền và có phần sửa riêng, ở đây là Samsung Browser.
- `fork`: nhánh code phát triển từ Chromium. Fork không có nghĩa là tách hẳn; Samsung vẫn định kỳ nhận code mới từ upstream.

### Uprev

`uprev` là nâng phiên bản nền của một dependency lên bản mới hơn. Với Samsung Browser, đây là việc chuyển nền Chromium từ version cũ sang version mới, merge thay đổi upstream, sửa conflict, sửa code không còn tương thích và kiểm tra hành vi mới.

Nên nói “đợt uprev Chromium” hoặc “nâng version Chromium”, không cần dịch thành một cụm tiếng Việt dài.

### Milestone

Số major của Chromium, ví dụ `M151`. Một milestone có thể có nhiều bản vá stable như `151.0.x.y`.

### Full version

Version đủ bốn phần, ví dụ `151.0.7922.138`. Đây là version xác định chính xác một release, tốt hơn chỉ ghi `151` khi cần kết quả có thể chạy lại.

### Ref, tag và commit SHA

- `ref`: tên chung mà Git dùng để chỉ một trạng thái source, có thể là branch, tag hoặc SHA.
- `tag`: tên cố định gắn với một release, ví dụ `refs/tags/151.0.7922.138`.
- `commit SHA`: mã định danh của một commit.

ChromeDrift chuẩn hoá version đầy đủ thành tag. Nếu nhập milestone, tool tìm bản Windows Stable mới nhất của milestone đó rồi mới tạo tag.

### ChromiumDash

API cung cấp thông tin release Chromium/Chrome. ChromeDrift dùng nó khi đầu vào chỉ là milestone, nhằm tìm full version Windows Stable tương ứng. ChromiumDash không cung cấp source code cho bước trích xuất.

### Gitiles

Web service để đọc Git repository của Chromium qua HTTP. ChromeDrift dùng Gitiles để:

- xem danh sách file trong một thư mục của đúng tag;
- tải một file đơn lẻ;
- tải một thư mục dưới dạng archive `.tar.gz`.

### Checkout và `src/`

`checkout` là bản source đã được lấy về máy. Trong checkout Chromium chuẩn, `src/` là root chứa các thư mục như `chrome/`, `content/`, `components/` và `third_party/`.

Khi dùng `--local-src`, phải truyền đúng thư mục `src/`, không phải parent của nó và không phải một thư mục con bị cắt nhỏ.

### `depot_tools`, `gclient sync`

Bộ công cụ và lệnh phổ biến để tạo một checkout Chromium đầy đủ, lấy dependency, generated files và các repository liên quan. ChromeDrift không cần chạy `gclient sync` khi dùng Gitiles vì nó chỉ đọc một số declaration sources. Nếu dùng local checkout thì việc checkout đó đầy đủ và đúng version là trách nhiệm của người chuẩn bị source.

### Source tree, directory tree và relative path

- `source tree`: toàn bộ cấu trúc thư mục/file của source ở một version.
- `directory tree`: một nhánh con, ví dụ `chrome/browser/resources/settings/`.
- `relative path`: đường dẫn tính từ Chromium `src/`, ví dụ `content/common/features.cc`.

ChromeDrift giữ nguyên relative path để extractor nhận ra đúng loại file và report trỏ lại đúng `path:line`.

### Archive

Gói nén của một thư mục tại đúng Git ref. Gitiles trả về archive cho một subtree. ChromeDrift giải nén có kiểm tra path traversal và chỉ ghi các file khớp suffix filter.

### Cache

Dữ liệu lưu lại để lần chạy sau không tải và trích xuất lại phần không đổi. Cache gồm:

- listing cây file theo ref;
- cây source đã materialize;
- marker cho biết target đã tải thành công hay thực sự không tồn tại;
- snapshot đã trích xuất.

Tag release là bất biến nên cache có thể tái sử dụng an toàn. Khi schema hoặc filter đổi, cache key/schema đổi để tránh đọc nhầm dữ liệu cũ.

## Nhóm phạm vi đọc source

### Target

Một chỉ dẫn tải source, có hai dạng:

- `file`: tải đúng một file;
- `tree`: tải archive của một thư mục và chỉ giữ filename khớp `include` filter.

Target có `path`, `kind`, `include` và `note`.

### Target set

Một tập target phục vụ mức độ quét khác nhau:

- `minimal`: nhanh, chỉ giữ phần cốt lõi để thử luồng;
- `default`: mức dùng hằng ngày, khoảng 40 MB mỗi version theo ghi chú hiện tại của project;
- `wide`: phủ toàn bộ filename shape mà extractor hiểu trong các Chromium root được chọn, lớn hơn đáng kể.

### Partition

Giới hạn lần chạy vào một khu vực như `settings`, `downloads`, `network` hoặc `webplatform`. Partition phù hợp để điều tra nhanh một area; không phù hợp làm release gate cuối vì thay đổi liên quan có thể nằm ở subsystem khác.

### `--complete`

Với một số partition có root đủ nhỏ, option này tải mọi file mà extractor có thể đọc bên trong root đó. Nó không có nghĩa là “toàn bộ Chromium”. Các partition quá lớn như `webplatform` không cho dùng `--complete` vì Gitiles chỉ có thể gửi cả thư mục và chi phí quá lớn.

### Discovery

Bước hỏi source tree xem file nào đang tồn tại và file nào có hình dạng mà một extractor có thể đọc. Discovery dùng để đo coverage, không tự quyết định tải toàn bộ các file tìm thấy.

### Candidate file

File có path/name khớp ít nhất một `applies_to()` của extractor và không thuộc test, generated output, platform khác hoặc binary khác đã bị loại. “Candidate” nghĩa là file có khả năng chứa declaration, không đảm bảo file đó thật sự tạo ra Fact.

### Coverage

Tỷ lệ candidate file mà target set thực sự đọc:

```text
coverage = số candidate file được target chạm tới / tổng candidate file nhìn thấy
```

Coverage được tính cả tổng thể và theo từng surface. Coverage theo surface quan trọng hơn khi đánh giá một kết luận “đã biến mất”: default có thể đọc gần hết Web IDL nhưng chỉ đọc một phần nhỏ pref/switch files.

### Missing target

Target được yêu cầu nhưng không tồn tại ở version đó. Đây có thể là điều bình thường với version cũ. Tuy nhiên nó phải xuất hiện trong metadata/report, vì “file chưa tồn tại” và “khai báo đã bị xoá” không được phép bị trộn lẫn.

### Incomplete acquisition

Lần lấy source có lỗi hoặc lỗ hổng khiến một file đáng lẽ phải đọc lại không có dữ liệu. Trường hợp này làm bằng chứng về removal yếu đi vì “không thấy” có thể do tải lỗi.

## Nhóm kiến trúc browser

### Browser process, renderer process và process boundary

Chromium tách browser thành nhiều process. Browser process quản lý tab, profile, setting và quyền; renderer chạy nội dung web; các service khác xử lý network, GPU, media… `process boundary` là ranh giới giữa hai process. Dữ liệu đi qua ranh giới này phải theo một contract chung.

### IPC

`Inter-Process Communication`: cơ chế các process trao đổi message. Trong Chromium, Mojo là hệ thống IPC chính. Một thay đổi IPC có thể không làm phần code Samsung đang sửa báo lỗi compile nhưng vẫn gây lỗi khi hai đầu hiểu message khác nhau.

### Mojo

Framework và ngôn ngữ khai báo IPC của Chromium. File `.mojom` mô tả:

- `interface`: nhóm method có thể gọi qua process;
- `method`: message request/response;
- `struct`/`union`: data truyền qua wire;
- `field`: trường của data;
- `enum`: tập giá trị truyền qua wire;
- `ordinal`: số dùng để nhận diện method/field trên wire;
- `[Stable]`, `[MinVersion]`: cam kết compatibility/versioning.

### ABI

Contract ở mức binary/wire. Trong report, “Mojo ABI changed” nghĩa là hình dạng message hoặc data qua IPC đã đổi. Nó không đồng nghĩa với C/C++ ABI của toàn bộ browser.

### Blink

Rendering engine và phần hiện thực Web Platform trong Chromium. Blink quyết định page có thể gọi Web API nào và feature đó đang ở trạng thái test, experimental hay stable.

### Web Platform và Web API

Các API mà website gọi được, ví dụ DOM, CSS, media, storage hoặc networking APIs. Đây là surface dành cho web content, khác với WebUI nội bộ của browser.

### Web IDL

Ngôn ngữ khai báo shape của Web API. File `.idl` cho biết interface, method, attribute, argument, kiểu trả về, inheritance và extended attributes. ChromeDrift chỉ coi `.idl` dưới `third_party/blink/renderer/` là Web IDL của Blink; `.idl` ở extension API hoặc MIDL là dialect khác.

### Interface

Trong tài liệu, giữ nguyên từ `interface` vì nó chính xác hơn “giao diện”. Tuỳ ngữ cảnh:

- Web IDL interface: contract mà JavaScript trên website nhìn thấy;
- Mojo interface: contract gọi qua IPC;
- UI/WebUI: màn hình hoặc phần tương tác người dùng.

Ba nghĩa này không được trộn với nhau.

### Runtime-enabled feature

Entry trong `runtime_enabled_features.json5` dùng để điều khiển khả năng expose một Web API của Blink. Trạng thái có thể khác theo platform.

### Origin Trial

Cơ chế cho phép website được cấp token để dùng thử một Web Platform feature chưa mở rộng rãi. Các thuộc tính như tên trial, OS cho phép, cho third party hay insecure context quyết định ai có thể truy cập feature.

### WebUI

Các trang nội bộ của browser được viết bằng web technology, thường có URL `chrome://...`, ví dụ Settings, History, Downloads, Bookmarks và Extensions. WebUI không phải website thông thường và cũng không phải toàn bộ UI native.

### Route

Định nghĩa một page/subpage và quan hệ điều hướng trong một WebUI surface. Route có tên, path, parent và có thể được bảo vệ bằng một `loadTimeData` guard.

### Control

Thành phần người dùng tương tác trong WebUI template, ví dụ toggle, dropdown, radio group, input hoặc button. ChromeDrift theo dõi tag, `id`, label key, pref binding và build condition.

### `loadTimeData`

Cầu nối đưa dữ liệu/config từ C++ handler sang TypeScript/HTML của WebUI. Một route hoặc control có thể gọi `loadTimeData.getBoolean('key')`; C++ dùng `AddBoolean("key", expression)` để đặt giá trị.

### Gate và guard

Điều kiện quyết định một declaration/page/control có tồn tại hoặc được nhìn thấy hay không.

- C++ guard: `#if BUILDFLAG(...)`;
- Mojo guard: `[EnableIf=...]`;
- GRIT guard: `<if expr="...">`;
- WebUI runtime guard: `loadTimeData.getBoolean(...)`;
- Blink gate: `[RuntimeEnabled=...]`.

### GRIT

Hệ thống resource/build của Chromium. Trong phần tool đang đọc, GRIT `<if expr>` quyết định template/control có được đưa vào build cho Windows hay không.

### Polymer và Lit

Hai cách Chromium viết WebUI template. Polymer thường dùng `.html` và binding `{{prefs.x}}`; Lit thường dùng `.html.ts` và template literal. ChromeDrift hỗ trợ cả hai vì các WebUI surface đang migrate không đồng đều.

## Nhóm feature và config

### `base::Feature`

Feature flag phía C++ của Chromium. Declaration chứa tên C++ như `kFoo`, feature string như `"Foo"`, default state và có thể có build guard theo platform.

### Feature string và C++ symbol

Hai tên khác nhau của cùng feature:

- C++ symbol: `features::kFoo`, code gọi trực tiếp; đổi tên thường làm build fail.
- feature string: `"Foo"`, Finch và `--enable-features` dùng; đổi tên có thể khiến config cũ im lặng mất tác dụng.

### `FeatureParam`

Tham số của một feature, ví dụ timeout, threshold hoặc mode. Finch có thể đặt giá trị khác default cho param. Đổi default làm hành vi mặc định thay đổi; xoá/đổi tên param khiến config cũ không còn hiệu lực.

### Feature flag

Tên chung cho cơ chế bật/tắt một feature. Cần nhìn ngữ cảnh để biết đó là `base::Feature`, Blink runtime feature, `chrome://flags` entry hay một config khác.

### Finch

Hệ thống server-side của Chrome dùng để rollout thử nghiệm và thay đổi config cho từng nhóm người dùng mà không cần phát hành binary mới. Finch thường đặt:

- một `base::Feature` bật hay tắt;
- giá trị cho `FeatureParam`;
- rule chọn nhóm người dùng/device.

ChromeDrift chỉ thấy tên và wiring được khai báo trong Chromium source. Nó không thấy Samsung có hệ thống rollout nào tương đương, đang dùng feature name nào hoặc đang set param gì nếu không được cấp nguồn config đó.

### Kill switch

Flag cho phép tắt nhanh một feature đã ship nếu có sự cố. Khi Chromium xoá kill switch sau khi feature ổn định, hành vi thường đã trở thành cố định; điều cần kiểm tra là config bên ngoài còn cố override flag đó hay không.

### Command-line switch

Tham số truyền khi khởi động process, ví dụ `--enable-foo`. Script, automation hoặc test harness có thể phụ thuộc vào string này. Nó khác với Finch: switch nằm trên command line của process, Finch là config/rollout từ server.

### Preference hoặc pref

Key lưu setting trong profile/local state, ví dụ `download.prompt_for_download`. Đổi pref key có thể khiến dữ liệu cũ vẫn nằm trên disk nhưng code mới không đọc nó nữa. C++ symbol của pref và string key cũng là hai thứ khác nhau.

### `chrome://flags` entry

Mục người dùng hoặc developer nhìn thấy ở trang `chrome://flags`. `flag-metadata.json` chủ yếu cho ChromeDrift biết owner và milestone dự kiến xoá entry; nó không phải declaration đầy đủ của feature phía C++.

### Config ngoài repository

Những thứ ảnh hưởng browser nhưng không nằm trong Chromium source đang quét, ví dụ Finch/rollout config, launch script, automation, enterprise deployment và policy backend. Owner `config` trong report được hiển thị là `Outside the repository` để nhắc rằng việc xác minh phải diễn ra ở nguồn khác.

## Nhóm dữ liệu của ChromeDrift

### Extractor

Bộ đọc chuyên cho một dạng source. Mỗi extractor có hai phần:

- `applies_to(path)`: file này có đúng dialect/path mà extractor hiểu không;
- `extract(text, path)`: đọc nội dung và tạo danh sách Fact.

### Fact

Một declaration đã được chuẩn hoá thành object có identity ổn định. Fact không phải toàn bộ file và không phải nhận xét do AI tạo ra. Nó là dữ liệu có cấu trúc được parser lấy từ source.

### `kind`, `key`, `name`, `path`, `line`, `attrs`

- `kind`: loại Fact, ví dụ `mojo_method`.
- `key`: identity ổn định trong cùng kind.
- `name`: tên để hiển thị.
- `path`, `line`: bằng chứng nằm ở đâu.
- `attrs`: những thuộc tính cần dùng để hiểu và so sánh declaration.

### UID

Identity dùng để ghép hai version: `kind:key`. Ví dụ `pref:download.prompt_for_download`. Hai Fact cùng UID được xem là cùng một declaration qua hai version.

### Normalization

Đưa nhiều cách viết source có cùng ý nghĩa về một biểu diễn chung. Ví dụ macro `BASE_FEATURE` hai tham số và ba tham số đều được chuẩn hoá về cùng feature name, state và platform state. Mục đích là bỏ qua thay đổi cú pháp nhưng vẫn giữ thay đổi hành vi.

### Deduplication

Gộp các Fact trùng UID theo rule ổn định. ChromeDrift chọn declaration có `(path, line)` nhỏ nhất, đồng thời tổng hợp overload metadata khi cần. Việc này tránh kết quả phụ thuộc thứ tự filesystem.

### Snapshot

Tập Fact của một Chromium ref, kèm milestone, target set, coverage, fetch stats và lỗi/missing target. Snapshot là đầu ra của acquisition + extraction và đầu vào của semantic diff.

### Semantic diff

So sánh theo ý nghĩa thay vì so text. ChromeDrift ghép Fact theo UID rồi chỉ so các attribute được xem là có hậu quả. Ví dụ `declared_form` đổi do Chromium thay macro không tạo finding; `default_state` đổi thì có.

### Change

Kết quả khác nhau của một Fact giữa hai snapshot. `change_type` là `added`, `removed` hoặc `modified`; `deltas` giữ `[giá trị cũ, giá trị mới]`; `signals` giải thích bản chất thay đổi; `severity` là mức cơ sở.

### Signal và leading signal

`signal` là nhãn có ngữ nghĩa, ví dụ `ipc_signature_change` hoặc `pref_renamed`. Một Change có thể có nhiều signal. `leading signal` là signal có severity cao nhất; nếu bằng điểm thì chọn theo tên để kết quả deterministic. Leading signal quyết định severity, bucket và đôi khi override owner.

### Severity và score

- `severity`: mức quan trọng cơ sở của loại thay đổi, lấy từ leading signal hoặc bảng mặc định theo kind + direction.
- `score`: điểm cuối sau khi xét Windows build và độ tin cậy của bằng chứng absence.

Score không phải xác suất Samsung bị lỗi, cũng không phải ước lượng số ngày công.

### Bucket

Cách phân loại bản chất finding:

- `Breaking`: contract bên ngoài binary có thể ngừng hoạt động mà không có cảnh báo rõ.
- `Behaviour change`: Windows build sẽ có hành vi khác.
- `New surface`: API/page/control mới xuất hiện nhưng không tự bật một hành vi chỉ vì declaration tồn tại.
- `Housekeeping`: dọn flag, đổi lịch xoá, move declaration hoặc bằng chứng chưa đủ để kết luận breaking.

### Owner

Khu vực nên nhận finding đầu tiên: `Process boundaries`, `Web platform`, `Browser C++`, `WebUI front-end` hoặc `Outside the repository`. Đây là routing theo technical surface/fix location, không phải tên cá nhân hay CODEOWNERS của Chromium.

### Finding

Một Change sau khi được chấm điểm và xếp bucket, kèm `reasons` giải thích từng bước. Finding là đơn vị chính người đọc thấy trong report.

### Enrichment và cluster

- `enrichment`: ngữ cảnh bổ sung, ví dụ metadata từ ChromeStatus khi bật.
- `cluster`: gom các finding có liên quan để người đọc thấy một migration dưới dạng một câu chuyện thay vì nhiều dòng rời rạc.

### Report JSON, Markdown và HTML

- JSON: dữ liệu đầy đủ cho automation/agent.
- Markdown: phù hợp review, lưu artifact hoặc comment.
- HTML: phù hợp duyệt/filter tương tác theo bucket, owner, kind, score và từ khoá.

## Những cặp khái niệm dễ hiểu nhầm

| Không nên hiểu là | Cách hiểu đúng |
|---|---|
| `interface` luôn là giao diện người dùng | Có thể là Web IDL contract, Mojo IPC contract hoặc UI; phải đọc theo kind |
| Feature được declaration là feature đã bật | Declaration chỉ nói code/flag tồn tại; phải xem default, platform state, runtime status và gate |
| File đã tải là file đã được parser đọc | File còn phải qua target scope, skip rule và `applies_to()` |
| `removed` luôn là upstream xoá | Với partial coverage, có thể declaration chuyển sang file chưa đọc |
| `Breaking` nghĩa là Samsung chắc chắn hỏng | Đây là loại contract change cần đối chiếu Samsung usage |
| Score 80 nghĩa là 80% có bug | Score là thứ tự ưu tiên theo rule, không phải probability |
| Owner là người sửa chắc chắn | Owner là hàng đợi kiểm tra đầu tiên; usage thực tế có thể chuyển việc sang team khác |
| `wide` là toàn bộ Chromium implementation | `wide` là toàn bộ filename shape trong các root mà tool thiết kế để đọc |
| Finch là command-line switch | Finch là server-side rollout/config; switch là tham số lúc khởi động process |
| `chrome://flags` là toàn bộ hệ thống feature flag | Nó chỉ là UI/metadata cho một phần flag; `base::Feature` và Blink runtime flag là các lớp khác |
