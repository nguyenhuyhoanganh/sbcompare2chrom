# Báo cáo đọc, kiểm thử và đánh giá ChromeDrift

> Ngày đánh giá: 21-08-2026  
> Commit được đọc: `9ca63f1`  
> Lịch sử được đọc: đủ 64/64 commit, từ `d9fca08` đến `9ca63f1`, gồm cả subject, body và diff của các quyết định quan trọng.
> Phạm vi: toàn bộ source Python, extractor, target, cache, snapshot, diff, scoring, report, test và dữ liệu cache M143/M147/M148/M151 có sẵn trong project.

## 1. Đọc phần này trước nếu bạn không rành kỹ thuật

ChromeDrift là một công cụ dùng để trả lời câu hỏi đại loại như:

> “Khi nâng Chromium từ phiên bản A lên phiên bản B, có những khai báo kỹ thuật nào thay đổi và thay đổi nào đáng để đội sản phẩm kiểm tra trước?”

Công cụ hiện làm được khá nhiều việc tốt. Nó đọc source Chromium, rút ra hàng chục nghìn mẩu thông tin, so hai phiên bản và tạo một báo cáo có điểm ưu tiên.

Nhưng kết luận quan trọng nhất của lần review này là:

> **ChromeDrift hiện phù hợp để tìm manh mối và lập danh sách việc cần kiểm tra. Nó chưa đủ đáng tin để tự động kết luận một bản nâng cấp là an toàn hay không an toàn.**

Sau khi đọc toàn bộ commit history, release-gate verdict ở trên **không đổi**, nhưng đánh giá về engineering quality tích cực hơn ban đầu:

- Nhiều rule không được chọn tùy ý; commit body ghi phép đo trên M130–M151, phương án đã thử rồi bỏ và test giữ invariant.
- Việc bỏ AI judgement, fork/product scoring và provenance khỏi core là quyết định có chủ ý: core dừng ở evidence thay vì giả vờ hiểu product usage.
- Determinism, scope guard, reference closure và score ceiling đều có rationale rõ và test đi kèm.
- Function body, TypeScript behavior, `.grd` và GN config schema là documented exclusions, không phải phần tác giả quên làm.

Phần phê bình còn lại tập trung vào nơi implementation hoặc release-gate promise vượt quá chính boundary mà history đã đặt ra.

Nói dễ hiểu hơn:

- Nếu ChromeDrift báo một thay đổi nguy hiểm, ta nên mở source ra kiểm tra lại. Báo cáo có thể đúng, nhưng cũng có thể là cảnh báo nhầm.
- Nếu ChromeDrift không báo gì nguy hiểm, ta vẫn chưa thể nói bản nâng cấp an toàn. Công cụ có thể chưa tải file đó, parser có thể không hiểu cú pháp đó, hoặc hai declaration khác nhau đã bị gộp làm một.
- Con số `100% coverage` hiện tại không có nghĩa là “đã đọc 100% mọi thứ có thể ảnh hưởng đến sản phẩm”.
- Điểm `75` không có nghĩa là “75% khả năng xảy ra lỗi”. Nó chỉ là một trọng số do người viết công cụ đặt bằng tay để sắp xếp kết quả.

Đây không phải là đánh giá rằng project “tệ”. Ngược lại, project có nhiều ý tưởng đúng, test khá nhiều và code có tính kỷ luật. Vấn đề là tài liệu đang hứa nhiều hơn mức mà cơ chế hiện tại thật sự chứng minh được.

### Nếu bạn không muốn đọc toàn bộ tài liệu dài

Bạn có thể đọc theo lộ trình này:

- Muốn hiểu công cụ làm gì: đọc mục 2, 3 và 4.
- Muốn biết target có đủ không: đọc mục 5.
- Muốn biết extractor có lấy hết không: đọc mục 6.
- Muốn hiểu conflict giữa các version: đọc mục 7.
- Muốn hiểu fact và score: đọc mục 9, 10 và 11.
- Muốn biết commit history đã quyết định gì: đọc mục 17 và 18.
- Muốn biết lỗi nào cần sửa trước: đọc mục 19, 20 và 21.
- Muốn có kết luận ngắn cuối cùng: đọc mục 24.

### Bảng trả lời nhanh

| Câu hỏi | Trả lời ngắn nhất |
|---|---|
| Target `default` đủ chưa? | Không; nó cố ý chỉ lấy mẫu để chạy nhanh. |
| Target `wide` đủ chưa? | Chưa; số 100% dùng denominator hẹp và vẫn bỏ file mà extractor đọc được. |
| Đã extract hết source đã tải chưa? | Chưa; có cú pháp Mojo/WebIDL bị bỏ và lỗi parser có thể bị nuốt. |
| Hai version được nối với nhau thế nào? | Bằng `kind:key`, rồi so một allowlist thuộc tính. |
| Conflict trong cùng version xử lý thế nào? | Hiện giữ bản có path/line nhỏ nhất; ổn định nhưng có thể sai semantics. |
| Fact đủ làm release verdict chưa? | Chưa; đủ cho inventory và manual triage. |
| Score có phải xác suất lỗi không? | Không; đó là trọng số heuristic để xếp thứ tự đọc. |
| 304 test pass có chứng minh đầy đủ không? | Không; nhiều test chứng minh self-consistency, chưa có oracle độc lập đủ mạnh. |
| Có nên bỏ project không? | Không; nền tảng tốt, nhưng cần sửa completeness, variants, platform và provenance. |

## 2. Một ví dụ đời thường để hiểu toàn bộ hệ thống

Hãy tưởng tượng ta muốn biết hai siêu thị A và B khác nhau thế nào.

ChromeDrift làm gần giống quy trình sau:

1. **Target** là danh sách khu vực trong siêu thị mà nhân viên được yêu cầu đi kiểm kê.
2. **Extractor** là các nhân viên chuyên đọc từng loại kệ. Một người đọc nước uống, một người đọc thực phẩm, một người đọc đồ điện.
3. **Fact** là một phiếu kiểm kê, ví dụ “kệ nước có chai X, dung tích 500 ml, giá 20.000 đồng”.
4. **Snapshot** là toàn bộ tập phiếu kiểm kê của một siêu thị tại một thời điểm.
5. **Diff** đặt snapshot A cạnh snapshot B và tìm món mới, món mất, hoặc thuộc tính đã đổi.
6. **Score** cho mỗi khác biệt một điểm ưu tiên.
7. **Report** trình bày các khác biệt để con người quyết định nên kiểm tra gì trước.

Vấn đề của ChromeDrift hiện nay tương đương với những tình huống này:

- Danh sách target quên một vài kho hàng nhưng vẫn nói đã kiểm kê 100%.
- Một nhân viên chỉ nhận ra nhãn dạng `Tên(...)`, nên bỏ qua nhãn dạng `Tên@0(...)`.
- Hai món cùng tên nhưng dành cho hai quốc gia khác nhau bị gộp thành một; công cụ giữ món nằm ở kệ có tên alphabet nhỏ hơn.
- Một món chỉ bán ở Android vẫn được đưa vào báo cáo dành cho Windows.
- Nhân viên gặp một kệ không đọc được nhưng chỉ ghi chú nhỏ rồi tiếp tục; cuối cùng report vẫn được tạo như bình thường.
- Điểm ưu tiên dựa vào bảng quy tắc chung, không biết sản phẩm SB-AXon có thực sự sử dụng món đó hay không.

Sau khi hiểu ví dụ này, các phần kỹ thuật bên dưới sẽ dễ đọc hơn nhiều.

## 3. Giải thích các từ thường gặp

### 3.1. Ref và version

`ref` là cách chỉ vào một trạng thái source Chromium.

Ví dụ:

- `151`: milestone rút gọn.
- `151.0.7922.138`: phiên bản đầy đủ.
- `refs/tags/151.0.7922.138`: tag Git cụ thể.
- Một branch hoặc commit SHA cũng có thể là ref.

Phiên bản đầy đủ hoặc commit SHA ổn định hơn branch. Branch có thể thay đổi nội dung theo thời gian dù tên branch không đổi.

### 3.2. Target

Target nói cho chương trình biết cần tải hoặc đọc file/thư mục nào của Chromium.

Project có ba target set:

- `minimal`: chỉ vài file, dùng kiểm tra pipeline có chạy được không.
- `default`: danh sách file/thư mục chọn lọc, chạy nhanh hơn.
- `wide`: tải nhiều thư mục lớn hơn, được tài liệu gọi là dùng cho release gate.

Target không phải fact. Target chỉ là nơi mà extractor được phép đi tìm fact.

### 3.3. Extractor

Extractor là bộ đọc source cho một nhóm cú pháp. Project hiện có 9 extractor chính:

1. `base_features`: đọc `base::Feature` và feature parameters.
2. `blink_runtime`: đọc Blink runtime-enabled features từ JSON5.
3. `web_idl`: đọc WebIDL.
4. `mojom`: đọc Mojo interface, method, struct, field và enum.
5. `constants`: đọc preference key và command-line switch.
6. `flags_metadata`: đọc metadata của `chrome://flags`.
7. `webui_routes`: đọc route của WebUI.
8. `webui_controls`: đọc control và preference binding trong WebUI.
9. `webui_gates`: đọc dữ liệu được đẩy từ C++ sang WebUI qua `AddBoolean`, `AddString` và các hàm tương tự.

Extractor không compile Chromium. Phần lớn extractor dò source bằng regular expression và một số parser nhỏ tự viết. Vì thế nó nhanh, nhưng không thể hiểu mọi cú pháp giống compiler thật.

### 3.4. Fact

Fact là một bản ghi đã chuẩn hóa.

Ví dụ đơn giản:

```json
{
  "kind": "base_feature",
  "key": "DeviceBoundSessions",
  "path": "components/.../features.cc",
  "attrs": {
    "default_state": "enabled",
    "platform_state": {"windows": "enabled"}
  }
}
```

Một fact thường gồm:

- `kind`: loại fact.
- `key`: định danh mà công cụ dùng để nối fact giữa hai phiên bản.
- `path` và `line`: vị trí trong source.
- `attrs`: các thuộc tính cụ thể được đem ra so sánh.

### 3.5. Snapshot

Snapshot là danh sách toàn bộ fact công cụ rút ra cho một version, cộng metadata như target set, coverage và số lỗi extraction.

Snapshot không phải bản sao hoàn chỉnh của Chromium. Nó chỉ là “những gì công cụ đã nhìn thấy và hiểu được”.

### 3.6. Diff

Diff so fact của version cũ với version mới.

Hai fact được xem là cùng một đối tượng khi chúng có cùng:

```text
kind:key
```

Ví dụ:

```text
base_feature:DeviceBoundSessions
mojo_method:network.mojom.CookieManager.GetAllCookies
idl_member:AudioNode.disconnect
```

Sau khi nối được hai bên, công cụ chỉ so các thuộc tính được liệt kê là “meaningful”. Nó không so mọi byte của source.

### 3.7. Signal, severity, score và bucket

- **Signal**: lời giải thích cụ thể về loại thay đổi, ví dụ signature của Mojo method đổi.
- **Severity**: trọng số ban đầu của signal hoặc của loại fact.
- **Score**: severity sau một số điều chỉnh.
- **Bucket**: nhóm hiển thị như Breaking, Behavior, New hay Housekeeping.

Điểm và bucket có liên quan nhưng không hoàn toàn là một thứ.

## 4. ChromeDrift chạy như thế nào, từng bước một

Giả sử chạy:

```bash
python3 -m chromedrift run 148.0.7778.217 151.0.7922.138 \
  --target-set wide \
  --no-enrich
```

### Bước 1: Chuẩn hóa version

Phiên bản đầy đủ được đổi thành tag, ví dụ:

```text
151.0.7922.138
→ refs/tags/151.0.7922.138
```

Nếu chỉ truyền `151`, chương trình hỏi dịch vụ ChromiumDash để tìm stable Windows patch mới nhất của milestone 151 tại thời điểm chạy.

Điều này có nghĩa là cùng câu lệnh dùng milestone rút gọn có thể resolve khác nhau nếu stable patch thay đổi theo thời gian.

### Bước 2: Chọn target

Target set quyết định file và thư mục nào được tải.

`default` dùng danh sách curated. `wide` lấy nhiều directory archive như `components/`, `chrome/browser/`, `services/`, `content/...`, `third_party/blink/...` và các thư mục khác.

### Bước 3: Materialize source vào cache tree

Source từ Gitiles hoặc local checkout được copy/extract vào một thư mục cache theo ref.

### Bước 4: Chạy extractor

Mỗi file được thử với registry extractor. Nếu đường dẫn hợp với `applies_to()` của một extractor, extractor đó đọc text và tạo fact.

### Bước 5: Gắn thông tin platform và dedupe

Công cụ cố gắng xác định declaration có thuộc Android, ChromeOS, iOS hoặc platform khác không. Sau đó fact trùng UID bị gộp lại.

### Bước 6: Lưu snapshot

Fact đã dedupe được ghi thành JSON cache.

### Bước 7: So snapshot

Công cụ nối fact cũ và mới theo UID, sau đó tạo:

- `added`: chỉ có ở version mới;
- `removed`: chỉ có ở version cũ;
- `modified`: có ở cả hai nhưng meaningful attributes khác nhau.

### Bước 8: Phát hiện một số rename/repoint

Một vài trường hợp đặc biệt được ghép lại:

- Pref hoặc switch đổi tên nhưng giữ cùng C++ variable.
- WebUI control đổi preference mà nó ghi vào.

Các loại rename khác có thể vẫn xuất hiện dưới dạng một removed và một added.

### Bước 9: Chấm điểm và tạo report

Signal mạnh nhất quyết định severity. Scorer điều chỉnh theo platform và coverage rồi tạo Markdown/HTML/JSON report.

## 5. Trả lời câu hỏi: “Target đã đủ chưa?”

### Câu trả lời ngắn

**Chưa.**

- `minimal`: chắc chắn không đủ, và project cũng không tuyên bố là đủ.
- `default`: cố ý không đủ để đổi lấy tốc độ.
- `wide`: rộng hơn rất nhiều nhưng vẫn chưa đủ, mặc dù README đang gọi nó là 100% và dùng cho release gate.

### Tại sao `wide` nói 100% nhưng vẫn thiếu?

Coverage hiện chỉ đếm hai quy tắc tên file:

- file có vẻ chứa preference;
- file có vẻ chứa feature hoặc switch.

Nó không dùng toàn bộ 9 extractor để tạo denominator. Vì thế `.mojom`, `.idl`, JSON5, WebUI route và nhiều file khác không được tính đúng vào con số “declaration files”.

Ví dụ đời thường:

> Một kho có hộp đỏ, hộp xanh và hộp vàng. Hệ thống chỉ đếm hộp đỏ, đã đọc đủ 100/100 hộp đỏ rồi in “coverage 100%”. Câu đó đúng nếu hiểu là “100% hộp đỏ”, nhưng sai nếu người đọc hiểu là “100% cả kho”.

Đây chính là vấn đề của số `1.164 / 1.164`.

### Số liệu thực tế từ M151

Snapshot M151 có sẵn trong cache cho thấy:

| Target set | Fact sau dedupe | Số file extractor thực sự mở | Coverage được in |
|---|---:|---:|---:|
| `default` | 29.118 | 3.924 | 64 / 1.164 |
| `wide` | 54.255 | 8.723 | 1.164 / 1.164 |

Việc extractor mở 8.723 file nhưng coverage nói “đã đọc 1.164 declaration files” cho thấy hai con số đang nói về hai tập khác nhau.

Khi đối chiếu full tree listing M151 với chính `applies_to()` của các extractor:

- Có 74 file vẫn hợp lệ với extractor nhưng nằm ngoài target `wide` sau các exclusion hiện hành.
- Chạy extractor trên 74 file đó tạo thêm 329 raw facts.
- Sau khi bỏ các nhóm rõ ràng là Android, Mac, iOS hoặc test, vẫn còn ít nhất 221 facts có vẻ liên quan browser/Windows.

Một số vùng đáng chú ý bị thiếu:

- Glic preferences.
- Credential Provider dành cho Windows.
- `chrome/services/file_util`.
- PDF và printing services.
- Removable storage.
- Media parser.
- `chrome/services/util_win`.
- `content/utility/sandbox_delegate_data.mojom`.

Target `wide` lấy `services/`, nhưng đó không bao gồm `chrome/services/`. Hai đường dẫn này là hai cây khác nhau.

### Reference closure cũng chưa đầy đủ

Sau extraction, công cụ kiểm tra một số liên kết như:

```text
WebUI route → gate
gate → base feature
control → preference
Blink runtime feature → base feature
feature parameter → owning feature
```

Kết quả M151:

- `default`: 180 reference chưa resolve.
- `wide`: 89 reference chưa resolve.

Điều này có nghĩa là ngay cả theo đồ thị quan hệ do chính công cụ hiểu, snapshot vẫn chưa self-contained.

### Kết luận về target

Không nên dùng câu:

> “Wide đã phủ 100%, nên absence chắc chắn là removal.”

Nên dùng câu:

> “Wide phủ toàn bộ tập file mà denominator hiện tại biết đếm, nhưng denominator đó chưa bao phủ mọi extractor và vẫn còn file/fact bên ngoài.”

## 6. Trả lời câu hỏi: “Đã extract hết chưa?”

### Câu trả lời ngắn

**Chưa. Có cả false negative và false positive.**

- False negative: source có declaration thay đổi nhưng công cụ không tạo fact nên không báo.
- False positive: công cụ tạo fact hoặc diễn giải platform sai nên báo thay đổi không ảnh hưởng sản phẩm.

### 6.1. Mojo method có ordinal bị bỏ qua

Parser hiện tìm method theo dạng:

```text
MethodName(...)
```

Nhưng Mojo có thể có ordinal:

```text
MethodName@0(...)
```

Regex dừng vì gặp `@0` trước dấu `(`.

Trong M151 `wide` đã tải:

- 196 declaration method có explicit ordinal.
- 186 declaration còn lại nếu bỏ Android.
- Không declaration nào trong nhóm này trở thành `mojo_method` fact.

Nói đơn giản: file đã được tải, nhưng nhân viên kiểm kê không nhận ra kiểu nhãn đó.

Đây là lỗi nghiêm trọng vì Mojo thường là contract giữa process/service.

### 6.2. WebIDL overload bị gộp

Ví dụ một interface có:

```webidl
disconnect();
disconnect(AudioNode destination);
disconnect(unsigned long output);
```

ChromeDrift định danh cả ba bằng:

```text
AudioNode.disconnect
```

Sau đó dedupe chỉ giữ một bản. Nếu Chromium sửa overload thứ hai nhưng bản được giữ là overload đầu tiên, diff có thể hoàn toàn không thấy thay đổi.

M151 có 133 UID IDL member bị trùng và khác signature.

Identity nên chứa signature hoặc overload discriminator, không chỉ chứa tên member.

### 6.3. Một số dạng WebIDL không được model

Parser hiện chưa tạo fact đầy đủ cho:

- callback typedef;
- typedef;
- câu `A includes B;`;
- quan hệ mixin đầy đủ;
- một số extended attributes ở partial interface.

Trong M151 đã đo được ít nhất:

- 91 callback typedef;
- 137 typedef;
- 200 câu `includes`;

mà model hiện không biểu diễn.

`includes` đặc biệt quan trọng vì nó quyết định member của mixin xuất hiện trên interface nào.

### 6.4. Runtime gate của partial interface không truyền xuống member

Ví dụ khái niệm:

```webidl
[RuntimeEnabled=ExperimentalFeature]
partial interface Navigator {
  void experimentalMethod();
};
```

Nếu gate nằm trên partial interface, member `experimentalMethod` cũng phải được hiểu là nằm sau gate đó.

Parser hiện đọc extended attributes của interface, nhưng member chỉ nhận attributes viết trực tiếp trước member. Vì vậy method có thể xuất hiện trong snapshot như một API bình thường dù thực tế còn experimental hoặc chỉ dành cho test.

M151 có 59 runtime-gated partial definitions với 100 members.

### 6.5. Lỗi parser có thể bị nuốt

Khi một extractor ném exception, pipeline:

1. tăng biến đếm lỗi;
2. ghi log;
3. bỏ file đó;
4. tiếp tục tạo snapshot và report.

Một số parser JSON5/metadata còn tự bắt lỗi và trả về danh sách rỗng, nên bộ đếm lỗi ngoài cùng có thể vẫn là 0.

Rủi ro:

```text
Parser cũ không hiểu cú pháp mới
→ file tạo 0 fact
→ fact cũ trông như bị removed
→ report báo breaking change giả
```

Với release gate, parse error không nên là warning nhỏ. Nó phải làm trạng thái completeness trở thành `unknown` hoặc làm run thất bại.

## 7. Trả lời câu hỏi: “Các phiên bản conflict với nhau thì sao?”

Câu này cần chia thành ba loại conflict khác nhau.

### 7.1. Cùng một fact giữa version cũ và mới

Đây là trường hợp bình thường.

Ví dụ:

```text
M148: base_feature:X = disabled
M151: base_feature:X = enabled
```

Hai fact có cùng `kind:key`, nên được nối với nhau và trở thành `modified`.

Không có bên nào “thắng”. Report giữ `before`, `after` và mô tả delta.

### 7.2. Đối tượng đổi tên hoặc đổi identity

Nếu key cũ biến mất và key mới xuất hiện, mặc định kết quả là:

```text
removed old-key
added new-key
```

Project có logic đặc biệt để ghép một số pref/switch rename qua C++ variable và ghép WebUI control repoint. Các kind khác chưa có rename detection tương đương.

Vì vậy một file move thường không sao nếu `kind:key` giữ nguyên, nhưng một rename có thể bị báo thành hai sự kiện.

### 7.3. Nhiều declaration conflict ngay trong cùng một version

Đây mới là vấn đề nghiêm trọng.

Chromium thường có source dạng:

```cpp
#if BUILDFLAG(IS_WIN)
BASE_FEATURE(kExample, "Example", base::FEATURE_ENABLED_BY_DEFAULT);
#else
BASE_FEATURE(kExample, "Example", base::FEATURE_DISABLED_BY_DEFAULT);
#endif
```

Hai declaration có cùng feature key nhưng giá trị khác nhau vì platform khác nhau.

ChromeDrift hiện dedupe theo quy tắc:

> Giữ fact có `(path, line)` nhỏ nhất theo thứ tự.

Quy tắc này ổn định giữa các máy, nhưng không giải quyết semantics. Nó giống như nói “nếu hai giấy tờ mâu thuẫn, giữ giấy nằm trong ngăn kéo có tên alphabet nhỏ hơn”.

M151 `wide`:

- 54.676 raw facts trước dedupe.
- 54.255 facts sau dedupe.
- 298 UID bị trùng.
- 258 UID trùng nhưng khác meaningful attributes.

Các kind conflict nhiều nhất gồm:

- 133 IDL members.
- 25 WebUI controls.
- 23 WebUI gates.
- 20 base features.
- 19 feature params.
- 15 switches.
- 14 prefs.
- Mojo field/method và WebUI route cũng có conflict.

Ví dụ thực tế:

- `GlicActor`: Android disabled, nhánh khác enabled.
- `DeviceBoundSessions`: Windows enabled, nhánh khác disabled.
- `mojo_base.FilePath.path`: `string` hoặc `array<uint16>` theo build flag.
- `SocketBroker.CreateTcpSocket`: signature Windows và non-Windows khác nhau.
- WebUI key `disableAnimations`: hai nhánh có giá trị true/false.

### Cách xử lý đúng nên là gì?

Một trong hai hướng:

1. **Variant-aware model**: giữ mọi variant cùng điều kiện của nó trong một fact set.
2. **Platform projection**: resolve điều kiện build cho Windows trước, sau đó chỉ giữ variant thực sự compile trên Windows.

Trong cả hai trường hợp, conflict không được biến mất âm thầm.

Report nên có một mục riêng:

```text
ambiguous/conflicting declarations
```

để người đọc biết kết luận chưa chắc chắn.

## 8. Lỗi platform: report Windows nhưng vẫn chấm điểm Android/Mac

### Cơ chế mong muốn

Nếu một declaration không được compile vào Windows ở cả hai version, finding đó phải score 0 và được đưa vào housekeeping.

### Cơ chế đang có vấn đề

Base feature extractor lưu hai thứ riêng biệt:

- `platform_state`: suy ra chủ yếu từ nội dung macro;
- `conditions`: các `#if` bao quanh declaration.

Scorer lại dựa vào `platform_state` để kết luận có trong Windows binary hay không, nhưng extractor chưa kết hợp đầy đủ enclosing `#if` vào trường đó.

Ví dụ:

```cpp
#if BUILDFLAG(IS_ANDROID)
BASE_FEATURE(kAndroidOnly,
             "AndroidOnly",
             base::FEATURE_ENABLED_BY_DEFAULT);
#endif
```

Parser có thể thấy `FEATURE_ENABLED_BY_DEFAULT` rồi ghi feature là enabled, trong khi điều quan trọng nhất là toàn declaration nằm dưới `IS_ANDROID`.

### Số liệu

M151 `wide`:

- 441 base features có enclosing conditions loại Windows.
- 428 trong số đó vẫn bị ghi active enabled/disabled thay vì `not_compiled`.

Diff M148 → M151:

- 141 findings mà mọi source guard hiện hữu đều loại Windows vẫn có score lớn hơn 0.
- 28 findings score 75.
- 19 findings score 55.

Ví dụ có Android-only `AccessibilityAtomicLiveRegions` và Mac-only `ApplicationAudioCaptureMac`.

Ngoài ra path-based detector biết Android, ChromeOS, iOS, Fuchsia và một số platform khác nhưng không nhận directory `/mac/` và `/linux/`.

M151 có ít nhất 79 Mojo facts trong exact Mac/Linux directories không được đánh dấu `not_compiled` cho Windows.

### Hậu quả

- False positive: đội Windows mất thời gian điều tra thay đổi chỉ dành cho platform khác.
- Điểm số và bucket summary sai.
- Finding thật bị đẩy xuống dưới vì danh sách ưu tiên bị nhiễu.

Đây là một trong những blocker lớn nhất trước khi dùng report làm release gate Windows.

## 9. Fact hiện tại có đủ để so sánh compatibility không?

### Những gì fact model làm tương đối tốt

- Thống kê và so nhiều declaration phổ biến.
- Cho biết source path và line làm bằng chứng.
- Tách nhiều bề mặt: feature, Mojo, IDL, preferences, switches, flags, WebUI.
- Hữu ích để khám phá nhanh hàng nghìn thay đổi giữa hai milestone.

### Những gì fact model không chứng minh được

| Câu hỏi | Fact hiện tại trả lời được không? | Vì sao? |
|---|---|---|
| Một `base::Feature` đổi default không? | Thường có | Nhưng platform branch có thể bị chọn sai. |
| Một Mojo signature phổ biến đổi không? | Thường có | Method có explicit ordinal đang bị bỏ. |
| Một WebIDL overload đổi không? | Không đáng tin | Các overload cùng tên bị collapse. |
| API có thật sự được expose trên Windows không? | Chưa đáng tin | Build conditions và runtime gates chưa đầy đủ. |
| SB-AXon có dùng symbol này không? | Không | Không có dependency/usage scan của sản phẩm. |
| Logic C++/TypeScript có đổi behavior không? | Không | Công cụ chủ yếu đọc declaration. |
| Finch có bật feature cho user không? | Không | Finch/server config nằm ngoài source snapshot. |
| Enterprise policy hoặc automation có phụ thuộc switch/pref không? | Không đầy đủ | Không scan consumer/config bên ngoài. |
| UI có bị vỡ layout không? | Không | Không render/screenshot/interaction test. |
| Mojo change có thực sự break endpoint đang deploy không? | Không đầy đủ | Không model lifecycle, version negotiation và deployment topology. |

### “Fact count cao” không đồng nghĩa “đã đủ”

M151 `wide` có 54.255 facts. Đây là con số lớn nhưng completeness không được suy ra từ số lượng tuyệt đối.

Ví dụ, một parser có thể lấy 13.000 Mojo fields nhưng bỏ đúng 186 methods có cú pháp khác. Tổng fact vẫn rất lớn, nhưng nhóm bị bỏ có thể quan trọng hơn nhiều fact đã lấy.

### Kết luận

Fact hiện đủ cho:

> “Hãy cho tôi một danh sách có cấu trúc về những declaration mà công cụ nhìn thấy đã thay đổi.”

Fact hiện chưa đủ cho:

> “Nếu report không có Breaking finding thì nâng cấp chắc chắn an toàn.”

## 10. Cơ chế so sánh và chấm điểm, giải thích thật đơn giản

### 10.1. Bước 1: Chọn các thuộc tính cần so

Mỗi kind có danh sách meaningful attributes riêng.

Ví dụ:

- Base feature: default state, platform state, conditions và C++ variable.
- IDL member: signature, member type, extended attributes và runtime gate.
- Mojo method: signature, params, response và attributes.
- Mojo field: type, ordinal, default và attributes.
- Pref/switch: variable và platform state.
- WebUI route: path, parent và guards.

Các thuộc tính ngoài allowlist không tạo modified finding.

### 10.2. Bước 2: Tạo signal

Từ change type và delta, code suy ra signal cụ thể.

Ví dụ khái niệm:

```text
mojo_method signature đổi
→ signal: Mojo ABI/signature change

base feature disabled → enabled
→ signal: default behavior enabled

pref chỉ còn ở version cũ
→ signal: pref left scan
```

### 10.3. Bước 3: Chọn severity

Nếu finding có signal, signal có trọng số cao nhất được chọn.

Nếu không có signal, dùng bảng base severity theo:

```text
(kind, added/removed/modified)
```

Nhiều signal không cộng điểm với nhau. Chỉ signal lớn nhất thắng. Nếu hai signal cùng điểm, tên signal được dùng để phá hòa nhằm giữ kết quả deterministic.

### 10.4. Bước 4: Điều chỉnh theo platform

Nếu mọi phía hiện hữu đều có:

```text
platform_state.windows = not_compiled
```

thì score bằng 0 và bucket thành housekeeping.

Quy tắc này hợp lý, nhưng dữ liệu `platform_state` hiện có bug nên kết quả chưa đáng tin hoàn toàn.

### 10.5. Bước 5: Điều chỉnh removal theo coverage

Nếu finding là `removed` và coverage của version mới dưới 95%:

```text
score = severity - 15
```

Lý do là absence trong một scan chưa đầy đủ có thể chỉ có nghĩa “đã chuyển sang file chưa đọc”, không chắc là thật sự bị xóa.

Với hai signal `pref_left_scan` và `switch_left_scan`, finding còn bị chuyển sang housekeeping khi absence chưa được xác nhận.

### 10.6. Công thức rút gọn

```text
severity = điểm signal mạnh nhất
           hoặc base score nếu không có signal

nếu chắc chắn ngoài Windows ở cả hai phía:
    score = 0
ngược lại nếu là removal và coverage < 95%:
    score = severity - 15
ngược lại:
    score = severity

score cuối được giới hạn trong khoảng 0..100
```

### 10.7. Ví dụ dễ hiểu

#### Ví dụ A: Mojo signature đổi

Giả sử signal table gán severity 75:

```text
severity 75
không bị loại khỏi Windows
không phải removal
→ score 75
```

Điều đó chỉ có nghĩa “quy tắc xếp loại đặt việc này ở nhóm ưu tiên cao”. Nó không có nghĩa 75% chắc chắn ứng dụng sẽ hỏng.

#### Ví dụ B: Một declaration bị mất trong default scan

Giả sử severity ban đầu là 65 và default coverage dưới 95%:

```text
65 - 15 = 50
```

Nhưng nếu denominator coverage không đúng với kind đó, mức giảm 15 cũng không phản ánh confidence thật.

#### Ví dụ C: Android-only feature

Mong muốn:

```text
not compiled on Windows
→ score 0
```

Hiện tại, nếu platform state bị parse sai, finding có thể giữ score 75 dù Windows không compile declaration đó.

### 10.8. Vì sao scoring chưa đủ làm quyết định release?

Scoring không biết:

- SB-AXon có dùng API/flag/pref đó không;
- code path đó có bao nhiêu user đi qua;
- có fallback không;
- endpoint Mojo có được deploy đồng bộ không;
- thay đổi từng gây incident thực tế chưa;
- parser confidence của fact là bao nhiêu;
- coverage riêng của kind đó là bao nhiêu.

Vì vậy score hiện là **thứ tự đọc**, không phải **risk probability**.

## 11. Coverage scalar đang làm score sai như thế nào?

Scorer hiện nhận một con số coverage chung của version mới.

Nhưng mức phủ giữa các extractor rất khác nhau. Đối chiếu M151 cho thấy gần đúng:

| Bề mặt | Default đọc được so với candidate | Nhận xét |
|---|---:|---|
| WebIDL | khoảng 2.161 / 2.165 file | Gần đầy đủ theo path candidate hiện thấy. |
| WebUI gate | 534 / 534 | Đầy đủ hơn nhiều bề mặt khác. |
| Mojo | khoảng 367 / 1.465 | Chỉ khoảng một phần tư. |
| Base feature | khoảng 363 / 3.013 | Rất thấp theo số file candidate. |
| Pref/switch constants | khoảng 9 / 530 | Rất thấp theo file candidate. |

Nhưng tất cả removal đều nhận cùng coverage tổng `64 / 1.164`, tức khoảng 5%.

Hậu quả:

- Một IDL removal có thể bị giảm confidence dù gần như mọi IDL file đã được đọc.
- Một Mojo removal dùng denominator không đại diện cho Mojo.
- `wide` có thể xác nhận absence quá mạnh vì scalar đạt 100% dù parser hoặc target vẫn có lỗ hổng.
- `minimal` không đo coverage rõ ràng; `unknown` hiện được xử lý giống như đủ để xác nhận absence.

Cần coverage riêng theo extractor/kind, cộng parser completeness riêng.

## 12. Các nguồn false positive khác

### 12.1. Test và fuzzer Mojo bị đưa vào report sản phẩm

Filter hiện bỏ directory tên chính xác `/test/`, `/tests/`, `/testing/`, nhưng không bỏ đầy đủ:

- file `_test.mojom`;
- directory `/fuzzers/`;
- directory `/web_test/`;
- một số test data theo naming khác.

M151 `wide` chứa ít nhất 137 facts rõ ràng từ các file test/fuzzer như:

- `network_service_test.mojom`;
- `indexed_db_control_test.mojom`;
- `usb_manager_test.mojom`;
- `mojo/public/tools/fuzzers/fuzz.mojom`.

Một thay đổi trong test interface có thể bị trình bày như breaking product contract.

### 12.2. Mọi `AddString` cũng bị gọi là visibility gate

WebUI extractor nhận:

```cpp
AddBoolean(...)
AddInteger(...)
AddString(...)
AddDouble(...)
```

và gọi chung là gate.

Nhưng `AddString("undoDescription", text)` là nội dung hiển thị, không phải điều kiện visibility. URL, metric name, background position hoặc error message cũng không phải gate.

M151 có 764 facts dạng này:

- 405 boolean;
- 319 string;
- 40 integer;
- 655 không nhắc đến base feature.

Trong diff M148 → M151 có những string change bị mô tả như “visibility condition changed”. Đây là sai về semantics dù extraction text có thể đúng.

Nên tách ít nhất:

- boolean visibility/capability gate;
- load-time data value;
- display string;
- URL/metric/config value.

### 12.3. Route guard làm mất dấu phủ định

Hai điều kiện sau có nghĩa ngược nhau:

```ts
if (loadTimeData.getBoolean('isGuest')) { ... }
if (!loadTimeData.getBoolean('isGuest')) { ... }
```

Parser chỉ lưu `isGuest`, không lưu polarity. Vì vậy report không biết route hiện khi guest hay khi không phải guest.

### 12.4. String constants bị phân loại quá rộng

Nếu filename trông giống pref file, mọi matching string constant được coi là pref. Nếu filename trông giống switch file, mọi matching string constant được coi là switch.

Điều này có thể biến các option token như:

```text
enabled
disabled
d3d11
bgra
auto
0
1
```

thành command-line switches, dù chúng chỉ là giá trị của một option.

Tương tự, nested dictionary keys như `name`, `id`, `hash`, `install_time` có thể bị gọi là preference paths. Một nested stored-data key có thể quan trọng, nhưng hậu quả không giống một top-level registered preference bị rename.

### 12.5. Cluster nối các finding không thật sự liên quan

Code có ý định chỉ nối Blink runtime feature với base feature khi Chromium khai báo liên kết.

Tuy nhiên sau kiểm tra đó, code vẫn nối theo cùng tên. Với Blink fact có `base_feature: "none"`, cùng tên không chứng minh có quan hệ.

Diff M148 → M151 có ít nhất 8 cặp bị cluster theo cách này.

Cluster sai không đổi raw diff nhưng có thể làm report kể một “câu chuyện thay đổi” sai và khiến người đọc nghĩ nhiều finding có chung nguyên nhân.

## 13. Cache và tính tái lập

### Điều hiện tại làm tốt

- Full version trở thành tag cụ thể.
- Snapshot cache có schema version.
- Target set, partition và `complete` có mặt trong tên snapshot.
- Diff từ chối hai snapshot có target configuration khác nhau.
- Diff từ chối khi một bên có ít hơn một nửa số fact của bên kia với snapshot đủ lớn.

### Những gì còn thiếu

Cache key chưa chứa:

- source type: Gitiles hay local checkout;
- local checkout path;
- local checkout HEAD SHA;
- content/tree hash;
- platform;
- target definition hash;
- extractor code hash/version ngoài schema thủ công.

### Tình huống sai có thể xảy ra

#### Tình huống A: hai local checkout khác nhau dùng cùng ref label

```text
Run 1: ref M151 + checkout A
→ lưu snapshot M151

Run 2: ref M151 + checkout B
→ cache hit trước khi xem checkout B
→ trả snapshot của A nhưng người dùng tưởng là B
```

#### Tình huống B: refresh nhưng file đã xóa vẫn còn

Materialize hiện copy file mới vào shared tree cũ. Nó không xây một tree rỗng rồi atomic replace.

```text
Lần trước tree có old_file.mojom
Lần sau source không còn file đó
refresh chỉ copy những file hiện có
old_file.mojom có thể vẫn nằm trong cache tree
extractor tiếp tục thấy fact cũ
```

#### Tình huống C: raw branch thay đổi

Branch cùng tên có thể trỏ đến commit mới. Cache theo tên branch không phân biệt commit cũ và mới. Nhiều request fetch riêng lẻ cũng không được chứng minh cùng một commit nếu branch di chuyển trong lúc chạy.

#### Tình huống D: report schema cũ

Lệnh render report đọc JSON vào model mà không kiểm tra schema. Một report cũ dùng scoring/bucket semantics khác vẫn có thể được render bởi code hiện tại như thể nó là report mới.

### Cách thiết kế an toàn hơn

Mỗi artifact nên ghi:

```text
requested_ref
resolved_ref
resolved_commit_sha
source_kind
source_path hoặc source URL
tree/content hash
target-definition hash
extractor/schema version
platform
creation time
```

Cache nên đặt dưới commit SHA và được tạo trong temp directory, sau đó atomic rename khi hoàn tất.

## 14. Vấn đề bảo mật

### 14.1. Stored XSS trong HTML report

Report HTML nhúng JSON findings trực tiếp vào JavaScript:

```html
<script>window.__FINDINGS__=...;</script>
```

`json.dumps()` không tự escape chuỗi `</script>`. Nếu một fact name hoặc dữ liệu trong report chứa:

```html
</script><script>/* mã JavaScript */</script>
```

browser có thể kết thúc script dữ liệu sớm và chạy script chèn vào khi người dùng mở report.

Escape DOM về sau không sửa được vấn đề vì payload đã phá khỏi script ngay lúc HTML được parse.

Nguồn Chromium chính thức tương đối đáng tin, nhưng công cụ cũng nhận local source và report JSON. Vì vậy report HTML không nên coi input là trusted.

Cách sửa:

- escape `<`, `>`, `&`, U+2028 và U+2029 trong JSON nhúng;
- hoặc dùng block `application/json` an toàn rồi parse text;
- validate schema và type;
- chỉ chấp nhận `http:`/`https:` cho spec links.

### 14.2. Cache path traversal trên Windows

Tên cache thay `/` và `:`, nhưng chưa thay backslash `\`.

Trên Windows, raw ref như:

```text
..\..\victim
```

có thể trở thành path đi ra ngoài cache directory.

Cách sửa tốt nhất là không dùng raw ref làm filename. Hãy dùng SHA-256 hoặc một slug sanitizer chỉ cho phép `[A-Za-z0-9._-]`, sau đó kiểm tra `commonpath`.

### 14.3. Proxy credential bị in ra log

Lệnh `chromedrift check` in nguyên giá trị:

```text
HTTPS_PROXY
https_proxy
NO_PROXY
no_proxy
```

Proxy URL có thể chứa username/password. Khi chạy trong CI, credential có thể đi vào log artifact.

Chỉ nên in tên biến và hostname đã redacted, hoặc đơn giản nói biến đang được cấu hình.

## 15. Test hiện tại chứng minh được gì?

### Kết quả tốt

Lệnh đúng trong README:

```bash
python3 -m unittest discover -s tests -q
```

chạy 304 test và tất cả đều pass.

Ngoài ra:

- Python source compile được.
- CLI khởi động được.
- JavaScript report không có syntax error.
- Git whitespace check sạch.
- Snapshot M143/M147/M148/M151 hiện có không ghi extract error hoặc missing target theo metadata hiện tại.

### Những điều 304 test không chứng minh

Nhiều test kiểm tra tính nhất quán nội bộ, ví dụ:

```text
README ghi 54.255 facts
snapshot cũng có 54.255 facts
→ test pass
```

Nhưng nếu extractor bỏ sót cùng một nhóm declaration từ trước, README và snapshot vẫn khớp nhau. Test đó không so kết quả với một oracle độc lập từ compiler/AST hoặc full Chromium inventory.

Test hiện cũng chưa bắt được:

- extractor-applicable file nằm ngoài coverage denominator;
- Mojo method có explicit ordinal;
- WebIDL overload bị collapse;
- platform guard của base feature không đi vào `platform_state`;
- raw duplicate UID khác semantics;
- HTML `</script>` injection;
- Windows backslash path traversal;
- reuse cache giữa hai local source khác nhau;
- report JSON sai schema;
- default unittest discovery chạy 0 test.

### Green test nhưng CI có thể chạy 0 test

Từ repository root:

```bash
python3 -m unittest discover -v
```

kết thúc thành công nhưng chạy 0 test, vì cấu trúc discovery hiện yêu cầu chỉ rõ `-s tests`.

CI nên có guard riêng:

```text
test count phải > 0
```

và nên biến `tests/` thành package hoặc cấu hình runner tiêu chuẩn.

## 16. Những điểm project đang làm tốt

Để đánh giá công bằng, project có nhiều phần đáng giữ lại:

- Kiến trúc pipeline chia module rõ: acquire, target, extract, snapshot, diff, score, cluster, report.
- Fact model cho phép report có bằng chứng path/line thay vì chỉ đưa ra text mơ hồ.
- Extraction và output được sort để giảm nondeterminism.
- Có schema version cho snapshot.
- Có guard không cho so target set/partition không tương thích.
- Có lopsided fact-count guard để chặn checkout bị truncate quá nặng.
- Có cảnh báo missing target.
- Có rename/repoint detection cho một số surface.
- Có giải thích lý do score trong report.
- Tar extraction có kiểm tra traversal và subprocess không dùng shell string.
- Test suite có quy mô tốt đối với một project Python stdlib-only.
- Comment trong code ghi lại khá nhiều lỗi lịch sử và lý do thiết kế, giúp bảo trì.

Nền tảng này đáng tiếp tục phát triển. Phần cần thay đổi là định nghĩa completeness, identity/variant và provenance, không nhất thiết phải viết lại toàn bộ project.

## 17. Toàn bộ lịch sử 64 commit nói gì?

### 17.1. Vì sao commit message của repo này quan trọng?

Ở nhiều repo, commit message chỉ nói “fix bug” hoặc “update docs”. Repo này khác: phần body thường ghi khá đầy đủ:

- câu hỏi tác giả đang cố trả lời;
- số liệu đo trên milestone thật;
- phương án đầu tiên đã thử và vì sao nó sai;
- trade-off được chấp nhận;
- invariant và test được thêm để giữ quyết định;
- schema nào cần bump;
- phần nào cố ý chưa làm.

Vì vậy chỉ đọc source ở `HEAD` sẽ dễ đánh giá thiếu công bằng. Ví dụ, nhìn riêng `score.py` có thể tưởng penalty `-15` là số chọn tùy ý; body của commit `bafc44a` giải thích vì sao không scale theo file coverage và đưa số liệu từ sáu comparison thật. Theo chiều ngược lại, commit message cũng giúp bắt bug: `47e6dae` nói Blink flag có `base_feature: "none"` sẽ không bị cluster bằng name similarity, nhưng source do chính commit đó thêm vẫn nối cùng tên ngay sau guard.

History là một nhánh thẳng gồm 64 commit, không có merge commit, do một author chính tạo từ tối 16-08 đến tối 21-08-2026. Trong chưa đầy năm ngày, project thay đổi hơn 14 nghìn dòng, bỏ hơn 3 nghìn dòng, tăng từ 60 lên 304 test và đi tới schema 28. Đây là tốc độ của một prototype được audit dồn dập, chưa phải dấu hiệu của một release gate đã ổn định lâu dài.

### 17.2. Giai đoạn 1 — dựng pipeline và nhận ra bài toán product integration

| # | Commit | Quyết định ghi trong commit message | Ý nghĩa đối với review |
|---:|---|---|---|
| 1 | `d9fca08` | Tạo ChromeDrift; tải tarball nhỏ thay vì full checkout, normalize trước khi diff, làm stages deterministic rồi mới để AI judge shortlist. | Đặt nền semantic diff đúng, nhưng nhiều parser grammar hiện tại cũng bắt đầu từ đây. |
| 2 | `bdeccf3` | Viết lại README từ đầu để giải thích vì sao Chromium diff khó đọc. | Documentation được xem là một phần của product ngay từ đầu. |
| 3 | `85b4b29` | Bỏ giới hạn top findings; route theo product/infra/platform vì scope theo feature làm mất 1.802/2.226 findings. | Tác giả đã đo và tránh lọc mất các row severity cao. |
| 4 | `47e6dae` | Thêm WebUI routes/controls/gates và union-find cluster theo declared edges, không theo name similarity. | Ý định đúng; implementation cùng commit lại mâu thuẫn ở Blink `base_feature:none`. |
| 5 | `67ec4a1` | Tách “chưa đọc” khỏi “cố ý không đọc”; nói rõ TypeScript behavior nằm ngoài model. | Function bodies và TS logic là scope boundary đã công bố, không phải bug bị quên. |
| 6 | `85be946` | Thêm fork mode và checkout riêng cho hai phía; uprev và fork comparison cần vocabulary ngược nhau. | Cho thấy tác giả từng thử product/fork semantics thật. |
| 7 | `b8aab1d` | Thêm provenance states để phân biệt stale merge debt với deliberate divergence. | Two-way diff không đủ suy ra intent; history đã hiểu điều này. |
| 8 | `9a3ee25` | Nhận ra fork thường shadow upstream bằng build flag; thêm enclosing conditions. | Build conditions trở thành fact quan trọng từ rất sớm. |
| 9 | `7ace48b` | Ghi HANDOFF cho phần cần internal source, LLM và merge history; công khai những gì chưa từng chạy. | Mức trung thực tốt; product evidence được xác nhận là không thể tự đo trong repo này. |
| 10 | `c7b2805` | Đo target gap: thiếu 964 features và Lit templates; sửa cache marker theo filter hash. | Bắt đầu chuỗi quyết định “đừng đoán completeness”. |
| 11 | `062e7a2` | Mở rộng feature filename rules nhưng loại test declarations. | Policy rõ: test code không được vào product report. |
| 12 | `db760d6` | Thêm `catalog` bằng blobless clone để biến coverage gap thành danh sách đo được. | Một quyết định kiến trúc mạnh và vẫn còn giá trị ở `HEAD`. |
| 13 | `cc61534` | Khóa platform vào Windows desktop; thêm partition và đưa partition vào cache key. | Windows là core contract, không phải option trang trí. |
| 14 | `2c96550` | Sửa fork mode bị mất qua stages, cache 404 poisoning và flags được CLI nhận nhưng bỏ qua. | Cross-stage drift là defect class lặp lại. |
| 15 | `3839704` | Hợp nhất meaningful attrs, thêm orphaned state, đồng nhất legacy feature shape, từ chối platform profile sai. | “Một fact, một định nghĩa” trở thành design principle. |
| 16 | `d8e7728` | Sửa skill nói quá khả năng; công khai coverage thấp; đo WebIDL overload collision và Mojo key collision. | WebIDL overload là known limitation; Mojo ordinal lại chưa được kiểm tra. |

### 17.3. Giai đoạn 2 — bounded completeness, oracle và bỏ AI judgement

| # | Commit | Quyết định ghi trong commit message | Ý nghĩa đối với review |
|---:|---|---|---|
| 17 | `7f76597` | Thêm `--complete` theo roots và reference closure; completeness chỉ được chứng minh trên bounded surface. | Đây là định nghĩa completeness tốt hơn một scalar toàn cục. |
| 18 | `18a119e` | Viết coverage/PIPELINE, công khai các lớp evidence và phần ngoài model. | Declaration-only boundary được nêu rõ. |
| 19 | `0dde1fc` | Giải thích mechanism bằng output thật: guards, three-valued evaluator, diff passes, rename và clustering. | Tăng auditability và khả năng tái hiện. |
| 20 | `4dffad3` | Discover vendor files bằng marker thay vì bắt người dùng nhớ; tách FIXABLE khỏi OUT OF MODEL. | Hiểu đúng rằng fetch thêm không giúp nếu parser không đọc. |
| 21 | `c51c754` | Đo HTML freeze trên 3.120 findings; thêm paging, lazy details, debounce và event delegation. | Report performance được đo thực nghiệm; commit này cũng đặt JSON trực tiếp trong script, nơi XSS hiện còn. |
| 22 | `6b646df` | Sửa table layout cost cho máy Windows yếu; nói rõ chưa test browser thật tại chỗ. | Commit body phân biệt phần đã đo và phần mới suy luận khá tốt. |
| 23 | `6e465d5` | Dựng oracle độc lập cho Settings route/gate/pref-bound control, đạt recall 100% trong scope đó. | Test quality mạnh hơn self-consistency thuần túy, nhưng oracle chỉ phủ một surface. |
| 24 | `7f970b8` | Tạo walkthrough cho 9 declaration sources và giải thích vì sao không đọc function body. | Củng cố boundary có chủ ý. |
| 25 | `895f2ec` | Làm pipeline HTML standalone, UTF-8 và offline. | Air-gapped/offline là requirement thật. |
| 26 | `e94a65c` | Hiển thị comparison/scoring tương tác thay vì chỉ mô tả; kiểm tra scenario bằng code. | Documentation có executable consistency. |
| 27 | `34d3297` | Tạo PNG pipeline cho Confluence từ editable HTML. | Chủ yếu là UX/docs; về sau bị xóa để tránh copy drift. |
| 28 | `7ffc0fa` | Bỏ toàn bộ AI judgement; tool dừng ở evidence vì AI failure có thể trông giống clean result. | Quyết định hợp lý; review không nên đòi core tự phán product verdict. |
| 29 | `55dee51` | Viết lại pipeline cho người ngoài project, giữ technical vocabulary và thêm identity rules. | Readability là mục tiêu rõ. |
| 30 | `1868c48` | Nhóm 13 fact kinds theo consequence thay vì gọi tất cả là feature. | Giảm sai semantics trong report. |
| 31 | `d5bf1e3` | Mang suffix filter từ fetch sang extraction; sửa 803 Mojo removals giả do cache tree rộng hơn scope. | Scope isolation hiện có evidence mạnh. |
| 32 | `7e0e66d` | Đọc mọi pref-name file; 892/1.575 keys từng bị thiếu; đổi deletion thành `left_scan` khi chưa chắc. | Absence uncertainty là bài toán đã được hiểu sâu. |

### 17.4. Giai đoạn 3 — hợp nhất định nghĩa, determinism và thử nhiều report layout

| # | Commit | Quyết định ghi trong commit message | Ý nghĩa đối với review |
|---:|---|---|---|
| 33 | `7d549e1` | Audit sáu version; sửa symbol rename, control repoint, `*_prefs`, fake pref binding và Blink attrs. | So sánh kind-by-kind đã bắt nhiều defect thật. |
| 34 | `afe7e44` | Mỗi run đo candidate từ tree; thêm default/wide và in coverage. | `DISCOVERY_RULES` hai nhóm hiện tại bắt đầu ở đây. |
| 35 | `e739567` | Giữ minimal nhỏ, đo partition riêng, đồng bộ docs; công khai Mojo/WebUI/content gap. | Scope modes có meaning rõ. |
| 36 | `095990a` | Mở Mojo/WebUI/content và ChromeOS pref exception; lần đầu gọi wide 100%. | Coverage label bắt đầu rộng hơn denominator thực tế. |
| 37 | `d44aa5a` | Hợp nhất scope/candidate rules; sửa bare `switches.cc`, flags denominator và ignored CLI flags. | Tiếp tục chống duplicated definitions. |
| 38 | `04b7d86` | Dùng một `READABLE_SUFFIXES`, tách tree coverage khỏi area coverage, hợp nhất `kFoo→Foo`. | Single source of truth tốt, nhưng `READABLE_SUFFIXES` vẫn không đại diện toàn extractor registry. |
| 39 | `5a34072` | Sort walk và deterministic dedupe; sửa gate/control identity; giải thích mọi meaningful attr. | Reproducibility được sửa đúng; arbitrary semantic selection được thừa nhận. |
| 40 | `6e71be2` | Sửa line evidence; ngừng đọc Extensions IDL và MIDL như WebIDL; sort mọi walk. | “Đọc sai dialect tệ hơn công khai gap” là nguyên tắc tốt. |
| 41 | `f57ad95` | Thêm per-screen summary và human wording. | Report dễ đọc hơn nhưng không đổi fact count. |
| 42 | `4a62ed7` | Thử layout theo câu hỏi của reader, grouping theo signal và surface. | Derived values được tập trung để tránh renderer drift. |
| 43 | `c08ea00` | Bỏ tên vendor khỏi tool; không guess marker khi thiếu input. | Core trở thành generic Chromium comparator. |
| 44 | `e948063` | Thử menu theo team/surface vì signal headings quá nhiều. | Một UX experiment có measurement và browser verification. |
| 45 | `bc32bf9` | Bỏ menu, quay về một bảng vì menu làm mất global search/sort. | Tác giả sẵn sàng revert design không hiệu quả. |
| 46 | `2f5a04b` | Bỏ cột change nhưng giữ direction glyph ở đầu row. | Tối ưu mà không làm mất information. |
| 47 | `cf658e0` | Tăng khoảng cách giữa card và filter. | Thay đổi presentation thuần túy. |
| 48 | `7830a05` | Chuẩn hóa design system cho HTML report. | Thay đổi presentation/offline UX. |

### 17.5. Giai đoạn 4 — coverage lần hai, evidence-only scoring và Mojo data

| # | Commit | Quyết định ghi trong commit message | Ý nghĩa đối với review |
|---:|---|---|---|
| 49 | `725ce2e` | Đổi severity bar thành color wash vì bo góc làm bar trông lỗi. | Presentation. |
| 50 | `e96b9fa` | Thử glass design, có fallback và cân nhắc performance/offline. | Presentation experiment. |
| 51 | `0c6816b` | Revert glass design ngay sau đó. | History giữ cả quyết định đã bị bác bỏ. |
| 52 | `c775a3d` | Đồng bộ docs với single table và ghi lý do hai layout bị bỏ. | Commit body đóng vai trò design record. |
| 53 | `9afafdd` | Lấy WebUI handler root từ extractor thay vì lặp literal. | Một single-definition fix chính xác. |
| 54 | `0be4212` | Audit M143/M147/M148/M151; thay curated lists bằng rules, sửa params/prefs/Blink attrs/enrichment/report. | Một trong các audit commit mạnh nhất; bump schema 22. |
| 55 | `8727f7f` | Phát hiện denominator tự chấm trên scope roots, đưa ra whole tree; chặn truncated checkout và đưa missing targets vào report. | History từng gặp đúng class “100% giả” đang được review lại. |
| 56 | `b57bc54` | Thêm 13 roots để đạt 1.164/1.164 theo current rules và gọi wide là release gate. | Thành công theo rule hẹp, nhưng promise rộng hơn rule. |
| 57 | `40f493c` | Đồng bộ toàn bộ số liệu và behavior trong docs sau hai coverage commit. | Docs được quản lý nghiêm túc. |
| 58 | `bafc44a` | Xóa fork/profile/provenance/product vocabulary; core chỉ so hai Chromium versions; rewrite severity/score/buckets. | Evidence-only boundary là quyết định trung tâm của `HEAD`. |
| 59 | `8beed19` | Nêu ngoại lệ `flag_expiring` trong Housekeeping. | Reading order được tinh chỉnh theo use case. |
| 60 | `3283289` | Thêm Mojo struct/union/field/enum; fact count thành 29.118/54.255; schema 26. | Tăng mạnh semantic coverage nhưng không tăng file-coverage denominator. |
| 61 | `0e91541` | Hỏi câu riêng theo surface; thêm Mojo platform gates, WebIDL live/gated signals và owner routing. | Platform/gate architecture mạnh; đồng thời làm lộ base-feature integration gap. |
| 62 | `70772fa` | Hợp nhất path-platform rules và chỉ đánh dấu khi mọi declaration của UID đều ngoài Windows. | Sửa 164 false positives; nguyên tắc “mọi declaration đều ngoài Windows” đáng giữ. |
| 63 | `7a695de` | Ngừng dùng flag lifecycle như toàn bộ câu chuyện; tách gated và ungated contracts. | Framing đúng hơn: Mojo/prefs/switches không theo lifecycle của flag. |
| 64 | `9ca63f1` | Rút skill thành procedure, chuyển evidence về README. | `HEAD`: 304 test, workflow evidence-first. |

## 18. Đánh giá lại sau khi đọc commit history

### 18.1. Những điểm cần hạ mức phê bình

#### Không có product-specific score

Ban đầu có thể coi đây là thiếu sót. History cho thấy đây là boundary đúng: project từng có fork/profile/AI stages, đo thấy bucket mất ý nghĩa, rồi chủ động xóa. Core evidence không nên đoán SB-AXon usage.

> Đây không phải correctness bug. Đây là lý do tool chỉ nên cung cấp input cho release workflow, không phải tự thay thế toàn bộ workflow.

#### Deterministic dedupe

Rule `(path,line)` là arbitrary, nhưng nó sửa một lỗi thật: cùng tree tự diff từng tạo 68 phantom changes do filesystem order. Không nên bỏ determinism trước khi có variant model tốt hơn.

> Reproducibility: tốt. Semantic conflict resolution: chưa đủ.

#### Flat removal penalty và leading signal

Cả hai đều có measurement và rationale. Leading signal sửa hàng trăm over-ranking; flat `-15` tránh giả vờ file coverage là xác suất.

> Heuristic ranking được thiết kế tốt hơn vẻ ngoài của code; thiếu per-kind confidence vẫn là vấn đề khác.

#### Cache nói chung

Workflow dùng full immutable tag đã có marker, schema, scope và lopsided guards qua nhiều commit.

> Pinned-tag cache khá tốt; local checkout và raw ref provenance vẫn yếu.

#### Function body, TypeScript, GN và UI layout

Đây là documented exclusions từ sớm.

> Không gọi chúng là extractor defect. Chúng chỉ chứng minh tool không thể tự đưa ra release verdict toàn diện.

### 18.2. Những điểm cần nâng mức nghiêm trọng

#### `wide=100%` và release-gate wording

History đã hai lần phát hiện denominator tự chấm trên vùng nó biết. Denominator hiện vẫn chỉ có feature/pref filename rules, trong khi các commit sau thêm hàng chục nghìn Mojo/WebIDL/UI facts mà không mở coverage contract.

> Đây không chỉ là metric chưa đẹp; nó là recurrence của defect class mà `8727f7f` đã mô tả, đồng thời mâu thuẫn trực tiếp với CLI/README promise.

#### Mojo explicit ordinal

History gọi Mojo là high-severity runtime contract. Method parser không đổi từ commit đầu và self-count không thể thấy declaration nó bỏ.

> Đây là correctness blocker rõ ràng; cần regression test lấy từ real `.mojom` grammar.

#### Base-feature Windows projection

Nhiều commit xây một platform verdict dùng chung cho C++ `#if`, Mojo `[EnableIf]` và path. Enclosing `#if` của base feature chưa đi vào verdict đó.

> Đây là implementation gap so với chính platform architecture của project, không phải khác biệt quan điểm.

#### Test/fuzzer Mojo facts

Commit `062e7a2` và comment từ `095990a` đều nói test code là noise và phải loại. `_test.mojom`/fuzzer facts hiện tại trái với policy đó.

> Đây là cross-extractor regression cần sửa, không phải intentional inclusion.

#### Blink cluster với `base_feature:none`

Commit `47e6dae` nói rõ không join theo name similarity khi source khai báo `none`; code do chính commit đó thêm lại làm unconditional same-name join ngay sau guard đúng.

> Đây là bug chắc chắn, không cần tranh luận về product semantics.

### 18.3. Kết luận sau khi đọc history

Trước khi đọc history, project có thể trông như một prototype chứa nhiều heuristic chưa được cân nhắc. Sau khi đọc đủ subject, body và diff, mô tả công bằng hơn là:

> **Đây là một prototype có engineering discipline mạnh, measurement culture tốt và nhiều quyết định đúng; nhưng project phát triển quá nhanh trong chưa đầy năm ngày, nên contract giữa target, extractor, coverage, platform và report tiếp tục drift.**

History nâng mức tin tưởng vào path/line evidence, deterministic output, basic semantic normalization và usefulness cho manual review. Nó không chứng minh rằng `wide` đã lấy hết, absence luôn là removal, Windows score đúng cho mọi kind, hoặc report sạch đồng nghĩa uprev an toàn.

Vì vậy release-gate verdict vẫn là **chưa đạt**, nhưng engineering-quality verdict tăng từ “khá” lên **“tốt nhưng chưa trưởng thành”**.

## 19. Ma trận đánh giá hiện tại

| Hạng mục | Đánh giá | Giải thích ngắn |
|---|---|---|
| Cấu trúc code | Tốt | Module rõ, dễ lần pipeline. |
| Design rationale trong commit history | Tốt | Quyết định thường có measurement, rejected alternatives và invariant/test đi kèm. |
| Determinism | Tốt | Sort và deterministic dedupe loại phantom diff; semantic variant vẫn chưa được resolve đúng. |
| Target completeness | Chưa đạt | `wide=100%` dùng denominator hẹp và còn file ngoài target. |
| Extraction completeness | Chưa đạt | Mojo ordinal, WebIDL forms/overloads và parser fail-open. |
| Platform Windows | Chưa đạt | Nhiều declaration ngoài Windows vẫn có điểm cao. |
| Cross-version diff | Khá cho case đơn giản | `kind:key` dễ hiểu, nhưng rename/variant chưa đầy đủ. |
| Fact model | Một phần | Tốt cho inventory, chưa đủ cho compatibility verdict. |
| Core scoring | Khá–tốt cho evidence triage | Leading signal và score ceiling có measurement; chưa có per-kind confidence. |
| Product relevance | Cố ý ngoài scope | Đúng cho core; cần downstream integration layer nếu dùng trong release workflow. |
| Cache với full tag | Khá–tốt | Schema/scope/marker guards tốt; vẫn nên ghi commit/content hash. |
| Cache với local/raw ref | Chưa đạt | Không pin HEAD/content và có stale overlay/reuse risk. |
| Report UX | Khá | Có evidence và grouping, nhưng một số label sai semantics. |
| Security | Cần sửa trước khi dùng input không tin cậy | Stored XSS, Windows traversal, proxy secret logging. |
| Test | Tốt cho regression, chưa đủ cho completeness | 304 pass, có real-version và Settings oracle; thiếu grammar oracle, CI, platform và security tests. |
| Release gate | Chưa đạt | False negative và false positive chưa được kiểm soát. |

## 20. Thứ tự sửa đề xuất

### Giai đoạn 0: Ngăn kết luận sai và lỗ hổng rõ ràng

Ưu tiên làm ngay:

1. Đổi tài liệu từ “wide dùng cho release gate” thành “wide experimental/manual review” cho tới khi acceptance criteria đạt.
2. Sửa HTML JSON escaping và URL scheme validation.
3. Hash/sanitize cache filename cho Windows.
4. Không in proxy secret.
5. Validate schema khi đọc snapshot/report.
6. Nếu có extract error hoặc missing target, report phải hiển thị banner nổi bật và trạng thái `incomplete`.
7. CI phải fail nếu test count bằng 0.

### Giai đoạn 1: Sửa correctness cốt lõi

1. Coverage denominator lấy từ toàn bộ registry extractor.
2. Coverage riêng cho từng extractor/kind.
3. Mỗi file có trạng thái `parsed`, `skipped`, `unsupported`, `error`.
4. Fix Mojo explicit ordinal.
5. Redesign IDL member identity để giữ overload.
6. Parse callback, typedef và `includes`.
7. Inherit partial-interface gate vào member.
8. Resolve enclosing platform conditions trước khi score.
9. Bổ sung Mac/Linux và thống nhất platform filter giữa target/extract/score.
10. Loại test/fuzzer bằng rule được test hai chiều.

### Giai đoạn 2: Sửa conflict và provenance

1. Không drop conflicting fact variants.
2. Ghi condition/platform vào identity hoặc variant set.
3. Pin snapshot bằng commit SHA.
4. Xác minh local checkout HEAD với requested ref.
5. Cache key chứa target/extractor/config hash.
6. Build tree mới trong temp directory; không overlay lên tree cũ.
7. Thêm file lock cho concurrent run.

### Giai đoạn 3: Thêm downstream evidence riêng cho SB-AXon

Không đưa product guess trở lại core scoring. Giữ core là evidence giữa hai Chromium versions, rồi thêm một optional layer nhận evidence do SB-AXon cung cấp.

Tách hai trục:

```text
severity: nếu thay đổi thật thì hậu quả có thể lớn đến đâu?
confidence: ta chắc finding này đúng và liên quan đến đâu?
```

Sau đó bổ sung:

- SB-AXon dependency/usage scan;
- config/policy/automation inputs;
- endpoint ownership;
- release telemetry hoặc incident history;
- allowlist cho expected changes;
- regression/integration tests trên binary thật.

Một công thức tương lai có thể là:

```text
risk_priority = severity
              × extraction_confidence
              × product_relevance
              × exposure
```

Không nhất thiết phải hiển thị dưới dạng phần trăm nếu chưa được calibration.

## 21. Acceptance criteria trước khi gọi là release gate

Một run chỉ nên được xem là đủ điều kiện release gate khi thỏa tất cả:

- Ref hai bên resolve thành commit SHA và được ghi trong artifact.
- Local checkout HEAD khớp ref hoặc người dùng xác nhận override rõ ràng.
- Target/config/extractor hash được lưu.
- Không missing target ngoài allowlist có giải thích.
- Không silent parser error.
- Coverage là 100% cho từng extractor-relevant candidate trong phạm vi đã công bố.
- Unsupported syntax được đếm và hiển thị, không biến thành zero fact âm thầm.
- Không unresolved reference ngoài allowlist.
- Không conflicting UID bị drop; mọi variant được resolve hoặc báo ambiguous.
- Windows platform projection có golden tests cho `#if/#elif/#else`, line continuation và path platform.
- Mojo ordinal và WebIDL overload có regression tests.
- Test/fuzzer facts không đi vào product report.
- Report schema hợp lệ và HTML an toàn với untrusted strings.
- Test suite chạy trên Linux và Windows; test count được kiểm tra.
- Có một oracle độc lập trên một số Chromium milestones, không chỉ snapshot tự sinh.
- Những finding cao được nối với usage/dependency của SB-AXon hoặc được đánh dấu `product relevance unknown`.

Nếu một điều kiện chưa đạt, report vẫn có thể được tạo nhưng phải mang trạng thái:

```text
INCOMPLETE — FOR MANUAL TRIAGE ONLY
```

## 22. Cách dùng project an toàn trong trạng thái hiện tại

Nếu vẫn cần dùng ChromeDrift ngay bây giờ:

1. Luôn truyền full version hoặc commit SHA; tránh raw branch.
2. Dùng một cache directory mới cho mỗi audit quan trọng thay vì tin hoàn toàn vào `--refresh`.
3. Chạy `wide`, nhưng không gọi nó là complete.
4. Kiểm tra metadata: missing targets, extractor errors, raw/deduped counts và unresolved references.
5. Với mỗi Breaking/Behavior finding quan trọng, mở source ở cả hai version.
6. Kiểm tra enclosing `#if`, GN target và platform thực tế.
7. Kiểm tra SB-AXon có gọi/dùng symbol đó không.
8. Với removal, tìm toàn tree để phân biệt “xóa” với “move sang file ngoài target”.
9. Với IDL overloaded method, kiểm tra mọi signature cùng tên.
10. Với Mojo, kiểm tra method có ordinal và version attributes không.
11. Không mở HTML report từ source/report JSON không tin cậy cho tới khi sửa XSS; dùng JSON/Markdown trước.
12. Lưu lại exact command, commit SHA, cache path và hash artifact để audit có thể lặp lại.

Một report hiện tại nên được diễn giải như sau:

```text
Breaking
→ kiểm tra trước, không có nghĩa chắc chắn break

Behavior
→ có khả năng đổi hành vi, cần xác minh usage và platform

New
→ declaration mới được công cụ thấy, không chắc sản phẩm dùng được hoặc bật sẵn

Housekeeping
→ ưu tiên thấp hoặc absence chưa xác nhận, không có nghĩa chắc chắn vô hại
```

## 23. Các câu hỏi thường gặp

### “304 test đều pass, tại sao vẫn nói chưa an toàn?”

Vì test chủ yếu chứng minh code hoạt động theo quy tắc hiện tại. Nếu chính quy tắc coverage hoặc identity chưa đúng, test có thể pass nhưng kết luận ngoài đời vẫn sai.

### “Wide có nhiều hơn 54 nghìn facts, còn thiếu vài trăm có đáng kể không?”

Có thể có. Mức quan trọng không phụ thuộc số lượng. Một method contract bị bỏ sót có thể quan trọng hơn hàng nghìn constants housekeeping.

### “Nếu target không lấy file thì có phải mọi fact trong file bị mất không?”

Đúng. Extractor chỉ đọc những file đã materialize và nằm trong scope target.

### “Nếu file đã lấy nhưng parser không hiểu thì sao?”

Fact vẫn có thể bị mất. Target coverage và parser coverage là hai loại coverage khác nhau.

### “Nếu một fact bị removed thì chắc chắn source đã xóa?”

Không. Có ít nhất bốn khả năng:

1. source thật sự xóa;
2. declaration chuyển sang file ngoài target;
3. parser mới/cũ không hiểu một phía;
4. dedupe chọn variant khác.

### “File move có bị báo removed không?”

Nếu `kind:key` giữ nguyên và extractor vẫn đọc destination, thường không. Nếu destination ngoài target, key đổi hoặc parser khác, nó có thể thành removed.

### “Score càng cao thì càng chắc chắn?”

Không. Score hiện chủ yếu phản ánh severity heuristic, không phản ánh extraction confidence hoặc product relevance.

### “Breaking bucket có nghĩa binary chắc chắn crash?”

Không. Nó nghĩa signal được phân loại vào nhóm cần chú ý nhất. Cần kiểm tra product có dùng contract đó và thay đổi có thật sự áp dụng cho Windows không.

### “Có thể so milestone rút gọn như 148 và 151 không?”

Có, nhưng milestone được resolve sang stable patch tại lúc chạy. Để tái lập audit, nên ghi full version hoặc commit SHA.

### “Có thể dùng local Chromium checkout không?”

Có, nhưng hiện tool không chứng minh checkout HEAD khớp ref label và cache có thể reuse snapshot cũ. Nên dùng cache mới và tự ghi SHA của hai checkout.

### “Report HTML có an toàn không?”

Với data chính thức, rủi ro thực tế thấp hơn input tùy ý, nhưng cơ chế hiện có stored XSS. Không nên mở HTML tạo từ report/source không tin cậy trước khi sửa.

### “Công cụ có biết SB-AXon dùng những API nào không?”

Chưa. Scoring là Chromium-centric, không phải product-specific.

### “Vậy project có đáng giữ lại không?”

Có. Pipeline, fact model và report là nền tảng hữu ích. Nên xem đây là một static change inventory đang trưởng thành, không phải bỏ đi. Cần sửa completeness, variants, platform và provenance trước khi nâng vai trò của nó.

## 24. Kết luận cuối cùng

ChromeDrift hiện trả lời khá tốt câu hỏi:

> “Trong phần source mà tôi đã tải và parser hiểu được, những declaration nào trông có vẻ thay đổi?”

Nó chưa trả lời chắc chắn câu hỏi:

> “Nâng Chromium từ A lên B có an toàn cho SB-AXon hay không?”

Ba nguyên nhân lớn nhất là:

1. **Completeness chưa được chứng minh:** target và coverage còn bỏ sót.
2. **Semantics chưa được giữ đầy đủ:** variants, platform guards, overloads và một số syntax bị mất.
3. **Core cố ý dừng trước product verdict:** đây là boundary hợp lý, nhưng đồng nghĩa release workflow phải có downstream step riêng để kiểm tra SB-AXon có dùng change đó hay không.

Sau khi đọc toàn bộ commit history, câu mô tả công bằng nhất là:

> ChromeDrift có engineering discipline và design rationale tốt hơn một prototype thông thường. Chính vì core được thiết kế để dừng ở evidence, nó hữu ích cho manual review nhưng chưa thể một mình đóng vai trò release gate.

Quyết định thực tế ở thời điểm này:

- Dùng ChromeDrift để tạo inventory và ưu tiên manual review: **Có**.
- Dùng `default` để kết luận release an toàn: **Không**.
- Dùng `wide` hiện tại làm automated release gate: **Không**.
- Tiếp tục đầu tư sửa project: **Có, vì nền tảng hiện tại đủ tốt để nâng cấp dần thay vì viết lại từ đầu**.

## 25. Bản đồ source để kiểm tra lại

Các vị trí quan trọng được nhắc trong tài liệu:

- Target và coverage rules: [`chromedrift/targets.py`](../chromedrift/targets.py)
- Ref resolution và local materialization: [`chromedrift/acquire.py`](../chromedrift/acquire.py)
- Snapshot/cache: [`chromedrift/snapshot.py`](../chromedrift/snapshot.py)
- Extractor registry và error handling: [`chromedrift/extract/__init__.py`](../chromedrift/extract/__init__.py)
- Base feature extraction: [`chromedrift/extract/base_features.py`](../chromedrift/extract/base_features.py)
- Mojo extraction: [`chromedrift/extract/mojom.py`](../chromedrift/extract/mojom.py)
- WebIDL extraction: [`chromedrift/extract/web_idl.py`](../chromedrift/extract/web_idl.py)
- Platform parsing: [`chromedrift/extract/_cpp.py`](../chromedrift/extract/_cpp.py)
- Constants classification: [`chromedrift/extract/constants.py`](../chromedrift/extract/constants.py)
- WebUI routes/gates: [`chromedrift/extract/webui_routes.py`](../chromedrift/extract/webui_routes.py), [`chromedrift/extract/webui_gates.py`](../chromedrift/extract/webui_gates.py)
- Fact dedupe: [`chromedrift/model.py`](../chromedrift/model.py)
- Diff và severity signals: [`chromedrift/diff.py`](../chromedrift/diff.py)
- Score và coverage adjustment: [`chromedrift/score.py`](../chromedrift/score.py)
- Clustering: [`chromedrift/cluster.py`](../chromedrift/cluster.py)
- Reference closure: [`chromedrift/catalog.py`](../chromedrift/catalog.py)
- HTML report: [`chromedrift/report/html.py`](../chromedrift/report/html.py)
- CLI và report loading: [`chromedrift/cli.py`](../chromedrift/cli.py)
- Test suite: [`tests/`](../tests/)
