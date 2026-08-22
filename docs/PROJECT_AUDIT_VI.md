# Báo cáo đọc, kiểm thử và đánh giá ChromeDrift

> Ngày đánh giá ban đầu: 21-08-2026
> Follow-up review: 22-08-2026
> Baseline mới nhất được review: commit `bee9e7d` — schema `39`
> Lịch sử đến baseline đã được đọc: đủ 76/76 commit, từ `d9fca08` đến `bee9e7d`, gồm subject, body và diff của các quyết định quan trọng.
> Phạm vi: toàn bộ source Python, extractor, target, cache, snapshot, diff, scoring, report, test và dữ liệu cache M130/M136/M139/M143/M147/M148/M151 có sẵn trong project.

> **Cách đọc phiên bản report này:** phần phân tích ban đầu được giữ lại để thấy lỗi xuất phát từ đâu. Review của `8ced148` nằm ở mục 27, `b844108` ở mục 28, `5edc91e`/`a88f5fc` ở mục 29, `cd1ee05` → `0933dcd` ở mục 30; review mới nhất của `843dd96` và `bee9e7d` nằm ở **mục 31** và có quyền thay thế các con số/verdict cũ. Các mục trước đó là lịch sử lập luận ở từng baseline.

## 1. Đọc phần này trước nếu bạn không rành kỹ thuật

ChromeDrift là một công cụ dùng để trả lời câu hỏi đại loại như:

> “Khi nâng Chromium từ phiên bản A lên phiên bản B, có những khai báo kỹ thuật nào thay đổi và thay đổi nào đáng để đội sản phẩm kiểm tra trước?”

Công cụ hiện làm được khá nhiều việc tốt. Nó đọc source Chromium, rút ra hàng chục nghìn mẩu thông tin, so hai phiên bản và tạo một báo cáo có điểm ưu tiên.

Nhưng kết luận quan trọng nhất của lần review này là:

> **ChromeDrift đạt mục tiêu làm radar cảnh báo sớm: phát hiện được một phần thay đổi đáng chú ý để con người kiểm tra trước. Project không cần, và hiện cũng không tuyên bố, chứng minh 100% thay đổi hoặc tự động kết luận một bản nâng cấp an toàn.**

Chủ dự án đã làm rõ rằng **automated release gate không phải acceptance criterion hiện tại**. Vì vậy các đoạn cũ nói “chưa đạt release gate” chỉ nên đọc như ranh giới sử dụng, không phải verdict project thất bại. Tiêu chuẩn đúng ở baseline này là:

- có bắt được một tập thay đổi hữu ích đủ sớm hay không;
- finding có dẫn người đọc tới evidence để kiểm tra hay không;
- kết quả có deterministic và đủ ổn định để dùng lặp lại hay không;
- blind spot và mức không chắc chắn có được nói rõ, thay vì biến “không thấy” thành “chắc chắn không có” hay không.

Theo tiêu chuẩn đó, verdict là **đạt**.

Sau khi đọc toàn bộ commit history, đánh giá về engineering quality tích cực hơn ban đầu:

- Nhiều rule không được chọn tùy ý; commit body ghi phép đo trên M130–M151, phương án đã thử rồi bỏ và test giữ invariant.
- Việc bỏ AI judgement, fork/product scoring và provenance khỏi core là quyết định có chủ ý: core dừng ở evidence thay vì giả vờ hiểu product usage.
- Determinism, scope guard, reference closure và score ceiling đều có rationale rõ và test đi kèm.
- Function body, TypeScript behavior, `.grd` và GN config schema là documented exclusions, không phải phần tác giả quên làm.

Hai commit `843dd96` và `bee9e7d` sửa đúng những lỗi ảnh hưởng trực tiếp tới chất lượng radar: không còn biến việc rút `[Stable]` thành hàng trăm Breaking rows; `cmd_run` truyền coverage cả hai phía; guard được so theo Windows verdict thay vì khác nhau về cách viết; per-surface coverage cho một file thuộc mọi extractor thật sự đọc nó; và các overload locations của current pair không còn bị renderer giấu. Bare `unittest discover` chạy đủ **362 test** trên cả Python 3.14 và 3.9.

Với mục tiêu early detection, baseline hiện tại **đủ tốt để dùng ngay**. Full matrix sáu tổ hợp không còn Breaking row dựa trên một `position` biến mất mà không có type/ordinal evidence. Không còn first-match bias trong số per-surface, và current M148 → M151 overload findings có tối đa năm locations nên cả Markdown/HTML hiện đủ. Backlog đáng sửa nhất còn lại là duplication: M143 → M147 wide vẫn tạo 164 child `ipc_stability_changed` rows cho 32 container-level stability events. Đây là nhiễu mức Behaviour, không còn là báo động Breaking giả. Các grammar chưa model và parser edge case chưa có current yield nên chỉ cần công khai known scope, không phải tiếp tục đuổi coverage 100%.

Nói dễ hiểu hơn:

- Nếu ChromeDrift báo một thay đổi nguy hiểm, ta nên mở source ra kiểm tra lại. Báo cáo có thể đúng, nhưng cũng có thể là cảnh báo nhầm.
- Nếu ChromeDrift không báo gì nguy hiểm, ta vẫn chưa thể nói bản nâng cấp an toàn. Công cụ có thể chưa tải file đó, parser có thể không hiểu cú pháp đó, hoặc hai declaration khác nhau đã bị gộp làm một.
- Coverage M151 hiện là `8.295 / 8.366 (99%)` cho `wide`, còn thiếu 71 file. Đây là file-scope coverage, không phải parser/product completeness. Raw inventory M151 còn 85 callback definitions, 144 typedefs, 200 `includes` relations, 18 Mojo `feature` blocks và hàng trăm Mojo constants không có fact kind. Với mục tiêu hiện tại, chỉ cần ghi rõ đây là known scope; không cần viết ngay mọi extractor.
- Điểm `75` không có nghĩa là “75% khả năng xảy ra lỗi”. Nó chỉ là một trọng số do người viết công cụ đặt bằng tay để sắp xếp kết quả.

Đây không phải là đánh giá rằng project “tệ”. Ngược lại, project có nhiều ý tưởng đúng, test khá nhiều và code có tính kỷ luật. Điều cần giữ là tài liệu mô tả đúng đây là early-warning inventory và không biến một lần “không thấy” thành bằng chứng “không có”.

### Nếu bạn không muốn đọc toàn bộ tài liệu dài

Bạn có thể đọc theo lộ trình này:

- Muốn hiểu công cụ làm gì: đọc mục 2, 3 và 4.
- Muốn biết target có đủ không: đọc mục 5.
- Muốn biết extractor có lấy hết không: đọc mục 6.
- Muốn hiểu conflict giữa các version: đọc mục 7.
- Muốn hiểu fact và score: đọc mục 9, 10 và 11.
- Muốn biết commit history đã quyết định gì: đọc mục 17 và 18.
- Muốn biết lỗi nào cần sửa trước: đọc mục 19, 20 và 21.
- Muốn có kết luận mới nhất và biết nên dừng ở đâu: đọc mục 31.

### Bảng trả lời nhanh

| Câu hỏi | Trả lời ngắn nhất |
|---|---|
| Target `default` đủ chưa? | **Đủ cho lượt scan nhanh**, vì mục tiêu của nó là lấy mẫu có chủ đích; không phải exhaustive scan. |
| Target `wide` đủ chưa? | **Đủ cho lượt scan rộng theo rule hiện có**: 8.295 / 8.366 candidate file. Nó không đồng nghĩa parser/product coverage 100%; 378 multi-surface files hiện đã được tính đúng vào từng surface. |
| Đã extract hết source đã tải chưa? | Chưa, và mục tiêu hiện tại không bắt buộc phải lấy hết. Overload signature/gate/ext/location đã được giữ tốt hơn; WebIDL callback/typedef/includes và Mojo feature/constant là known scope chưa model. |
| Hai version được nối với nhau thế nào? | Bằng `kind:key`, rồi so một allowlist thuộc tính. |
| Conflict trong cùng version xử lý thế nào? | Phần lớn giữ bản có path/line nhỏ nhất. WebIDL overload hiện gộp signature, gate, ext và location của variants; location không tham gia diff là đúng. Current changed groups có tối đa năm vị trí và đều được render. |
| Fact đủ làm release verdict chưa? | Chưa; đủ cho inventory và manual triage. |
| Có đạt mục tiêu cảnh báo sớm một phần không? | **Có.** Tool bắt được hàng nghìn thay đổi trên version thật, có evidence và thứ tự ưu tiên để con người triage. |
| Score có phải xác suất lỗi không? | Không; đó là trọng số heuristic để xếp thứ tự đọc. |
| 362 test pass có chứng minh đầy đủ không? | Không, nhưng cùng full six-pair matrix nó là evidence đủ tốt cho early detection. Vẫn cần giữ test ở đúng pipeline boundary vì commit `bee9e7d` thay năm behavior nhưng chỉ thêm một test mới. |
| Có nên dùng project không? | **Có**, để phát hiện sớm và manual triage. Nên ưu tiên sửa các lỗi làm nhiễu hoặc gắn nhãn sai finding. |

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

**Tốt hơn rất nhiều so với bản review đầu, nhưng vẫn chưa đủ để gọi là complete.**

- `minimal`: chắc chắn không đủ, và project cũng không tuyên bố là đủ.
- `default`: cố ý không đủ để đổi lấy tốc độ.
- `wide`: đạt `8.276 / 8.349` candidate file, tức khoảng `99,1%`; còn 73 file mà chính denominator hiện tại nói là có thể chứa declaration.

### Commit `46dae58` đã sửa đúng điều gì?

Trước commit này, denominator chỉ biết hai nhóm tên file: preference và feature/switch. `.mojom`, `.idl`, JSON5 và WebUI templates không được tính. Vì vậy con số `1.164 / 1.164 (100%)` tự chấm điểm trên một tập quá hẹp.

Hiện tại `_discovery_rules()` lấy trực tiếp `applies_to()` của cả 9 extractor trong `REGISTRY`. Một extractor mới được thêm vào registry sẽ tự mở rộng denominator. Đây là sửa kiến trúc đúng hướng và là thay đổi lớn, không phải sửa cosmetic.

Số liệu M151 schema 29 đã kiểm lại từ cache:

| Target set | Fact sau dedupe | Candidate file target chạm tới | Tổng candidate | Tỷ lệ |
|---|---:|---:|---:|---:|
| `default` | 29.118 | 3.669 | 8.349 | 43,9% |
| `wide` | 54.451 | 8.276 | 8.349 | 99,1% |

73 candidate còn thiếu tập trung ở `chrome/services/`, `chrome/credential_provider/`, `chrome/installer/` và vài path nhỏ hơn. Việc run in tên các path này là tốt: khoảng trống đã nhìn thấy được thay vì bị che bởi số 100%.

### Vì sao vẫn chưa thể nói “denominator và extraction không thể bất đồng”?

`applies_to()` đã dùng chung, nhưng policy quyết định file nào bị bỏ vẫn còn hai bản:

- `targets.py` dùng `_TEST_RE`, `_NOT_THE_PRODUCT_RE`, `_VENDORED_THIRD_PARTY_RE` và `_OTHER_PLATFORM_RE`;
- `extract/__init__.py` dùng `SKIP_DIR_PARTS`, `SKIP_FILE_RE` và `_other_platform()`.

Targeted check trên listing M151 tìm được bất đồng theo cả hai hướng:

- Denominator đếm hai file `content/web_test/common/*.mojom`, nhưng extraction chủ động skip thư mục `/web_test/`. Hai file này xuất hiện trong chính danh sách 73 file “chưa đọc”, dù policy extraction nói đó là test code không nên đọc.
- Denominator loại các tên chứa `_test_` ở bất kỳ vị trí nào. Vì vậy ít nhất 9 file product API hợp lệ như `cc/mojom/hit_test_opaqueness.mojom`, hai Mojo file dưới `services/viz/.../hit_test/` và sáu WebIDL `xr_hit_test_*.idl` không nằm trong denominator. Snapshot `wide` vẫn thật sự chứa fact từ các file này.

Test mới chỉ kiểm `rule.applies is extractor.applies`. Nó không kiểm các global exclusion quanh predicate, nên vẫn pass trước các ví dụ trên.

Nói dễ hiểu: hai người đã dùng chung câu hỏi “file này có đúng loại extractor đọc không?”, nhưng vẫn dùng hai danh sách khác nhau cho câu hỏi “file này có phải test/platform noise không?”. Vì vậy câu “không còn second list” đúng với predicate loại file, nhưng chưa đúng với toàn bộ eligibility policy.

### “Read” ở đây chính xác có nghĩa gì?

`coverage_against()` kiểm target scope có **reaches** candidate path hay không. Nó không chứng minh file đã tải thành công, parser đã chạy thành công hoặc mọi declaration trong file đã thành fact.

Do đó nên đọc câu `reads 8.276 of 8.349` như:

> “Target set được khai báo có thể chạm tới 8.276 candidate path.”

Không nên diễn giải thành:

> “8.276 file đã parse hoàn hảo và không còn declaration nào bị mất.”

Missing target và extract error có metadata riêng, nhưng scorer hiện chỉ nhận coverage scalar. Một run vẫn có thể vượt ngưỡng 95% và xác nhận removal dù một target cụ thể bị tải lỗi; report có warning, còn score không dùng warning đó.

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

> “Wide đã phủ 99%, nên mọi absence chắc chắn là removal.”

Nên dùng câu:

> “Wide chạm tới 99,1% candidate path theo policy hiện tại. Nó là target rộng nhất hiện có, nhưng 73 path, eligibility mismatch, parse completeness và missing-target state vẫn phải được xét trước khi xác nhận removal.”

## 6. Trả lời câu hỏi: “Đã extract hết chưa?”

### Câu trả lời ngắn

**Chưa. Có cả false negative và false positive.**

- False negative: source có declaration thay đổi nhưng công cụ không tạo fact nên không báo.
- False positive: công cụ tạo fact hoặc diễn giải platform sai nên báo thay đổi không ảnh hưởng sản phẩm.

### 6.1. Mojo ordinal: extraction đã sửa, comparison chưa sửa

Commit `46dae58` sửa regex để nhận cả:

```text
MethodName(...)
MethodName@0(...)
```

Điều này có hiệu lực thật. M151 có 269 raw declaration mang explicit ordinal trong 23 file; sau platform/test filtering, snapshot `wide` tăng từ 5.903 lên 6.099 `mojo_method` fact.

Nhưng commit message còn nói ordinal “is now a compared attribute”. Phần này chưa đúng với code hiện tại.

`mojom.py` ghi `ordinal` vào `Fact.attrs`, còn `diff.py` chỉ so các thuộc tính sau cho `KIND_MOJO_METHOD`:

```python
("signature", "params", "response", "attrs")
```

`ordinal` không nằm trong tuple. Signature cũng được tạo từ tên, params và response, không chứa ordinal.

Probe tái hiện tối thiểu:

```mojom
// old
interface I { Foo@0(int32 x); };

// new
interface I { Foo@1(int32 x); };
```

Kết quả đã chạy trên `46dae58`:

```text
old fact ordinal: 0
new fact ordinal: 1
diff changes: 0
```

Test mới chỉ assert extractor tạo fact và lưu `ordinal`; nó không diff hai snapshot. Comment trong test nói “ordinal is compared”, nhưng assertion không chứng minh câu đó.

Đây là blocker nghiêm trọng vì thay đổi wire ordinal nằm đúng trên process boundary, bề mặt mà project xếp severity cao nhất. Cách sửa nhỏ nhất là thêm `"ordinal"` vào `MEANINGFUL_ATTRS[KIND_MOJO_METHOD]` và thêm regression test `@0 → @1` phải tạo `MODIFIED` change cùng signal phù hợp.

### 6.2. WebIDL: lỗi `margin-top` đã sửa, overload vẫn bị gộp

Ví dụ một interface có:

```webidl
disconnect();
disconnect(AudioNode destination);
disconnect(unsigned long output);
```

ChromeDrift vẫn định danh cả ba bằng:

```text
AudioNode.disconnect
```

Phản hồi B2 đúng ở một điểm quan trọng: một phần collision ban đầu không phải overload. Regex cũ đọc `margin-top` thành `top`; nếu chỉ thêm signature vào identity thì collision biến mất nhưng tên fact vẫn sai. Sửa parser trước là quyết định đúng.

Vì vậy con số và cách diễn đạt cũ của report cần điều chỉnh: không nên gọi toàn bộ 133/138 collision là overload.

Tuy nhiên lỗi overload độc lập vẫn còn sau khi parser được sửa. Quét raw facts trên M151 schema 29 cho kết quả:

- 12.158 raw `idl_member` facts;
- 11.964 member UID;
- 121 UID có nhiều declaration và khác nhau ở thuộc tính mà diff quan tâm.

Đối chiếu raw overload set M148 với M151:

- 109 UID tồn tại ở cả hai version nhưng tập overload thay đổi;
- deterministic dedupe vẫn làm lộ 107 thay đổi vì overload được chọn tình cờ cũng đổi;
- 2 thay đổi biến mất hoàn toàn vì declaration thấp nhất theo `(path, line)` không đổi.

Hai false negative đã tái hiện được là:

- `Navigator.install`: M151 thêm overload `install(InstallParams params)`, nhưng overload `install()` được giữ ở cả hai bên nên diff không báo.
- `Document.parseHTMLUnsafe`: overload set và gate thay đổi, nhưng declaration được dedupe giữ lại giống nhau nên diff không báo.

Kết luận công bằng cho B2 là:

1. maintainer đúng khi sửa parser thay vì dùng identity để che lỗi tên;
2. nhận định “overload có thể bị mất bởi dedupe” vẫn đúng và nay có hai false negative thật giữa M148–M151;
3. bước tiếp theo nên lưu một stable variant set hoặc overload discriminator **sau khi** parser đã trả đúng tên, không nhét raw signature vào UID một cách mù quáng.

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

Baseline M151 schema 28 trước commit `46dae58`:

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

## 8. Platform projection: lỗi chính đã được sửa

> **Trạng thái tại `46dae58`: fixed cho hai case đã nêu trong review.** Phần dưới giải thích lỗi trước khi sửa và vì sao thay đổi này đúng.

### Cơ chế mong muốn

Nếu một declaration không được compile vào Windows ở cả hai version, finding đó phải score 0 và được đưa vào housekeeping.

### Cơ chế từng có vấn đề

Base feature extractor lưu hai thứ riêng biệt:

- `platform_state`: suy ra chủ yếu từ nội dung macro;
- `conditions`: các `#if` bao quanh declaration.

Scorer dựa vào `platform_state` để kết luận có trong Windows binary hay không, nhưng extractor cũ chưa kết hợp đầy đủ enclosing `#if` vào trường đó.

Ví dụ:

```cpp
#if BUILDFLAG(IS_ANDROID)
BASE_FEATURE(kAndroidOnly,
             "AndroidOnly",
             base::FEATURE_ENABLED_BY_DEFAULT);
#endif
```

Parser có thể thấy `FEATURE_ENABLED_BY_DEFAULT` rồi ghi feature là enabled, trong khi điều quan trọng nhất là toàn declaration nằm dưới `IS_ANDROID`.

### Số liệu trước khi sửa

M151 `wide`:

- 441 base features có enclosing conditions loại Windows.
- 428 trong số đó vẫn bị ghi active enabled/disabled thay vì `not_compiled`.

Diff M148 → M151:

- 141 findings mà mọi source guard hiện hữu đều loại Windows vẫn có score lớn hơn 0.
- 28 findings score 75.
- 19 findings score 55.

Ví dụ có Android-only `AccessibilityAtomicLiveRegions` và Mac-only `ApplicationAudioCaptureMac`.

Ngoài ra path-based detector cũ biết Android, ChromeOS, iOS, Fuchsia và một số platform khác nhưng không nhận directory `/mac/` và `/linux/`.

M151 có ít nhất 79 Mojo facts trong exact Mac/Linux directories không được đánh dấu `not_compiled` cho Windows.

### Kết quả sau khi sửa

- `base_features._platform_states()` hiện AND default state trong macro với enclosing `#if` conditions.
- `PLATFORM_DIR_RE` đã thêm exact directory `/mac/` và `/linux/`.
- 79 Mojo facts Mac/Linux trong M151 hiện có `platform_state.windows = not_compiled`.
- Default M148 → M151 tăng số finding score 0 từ 118 lên 187; con số đã tái tạo lại từ snapshot schema 29.
- Regression tests phân biệt Android-only, Windows-relevant và condition không quyết định được.

Không tìm thấy regression cụ thể trong hai fix này. Đây là hai mục có thể đánh dấu **đã sửa** trong follow-up review.

## 9. Fact hiện tại có đủ để so sánh compatibility không?

### Những gì fact model làm tương đối tốt

- Thống kê và so nhiều declaration phổ biến.
- Cho biết source path và line làm bằng chứng.
- Tách nhiều bề mặt: feature, Mojo, IDL, preferences, switches, flags, WebUI.
- Hữu ích để khám phá nhanh hàng nghìn thay đổi giữa hai milestone.

### Những gì fact model không chứng minh được

| Câu hỏi | Fact hiện tại trả lời được không? | Vì sao? |
|---|---|---|
| Một `base::Feature` đổi default không? | Thường có | Enclosing platform guard đã sửa; condition ngoài grammar được hiểu vẫn có thể là `conditional`. |
| Một Mojo signature phổ biến đổi không? | Thường có | Explicit-ordinal method nay đã được extract, nhưng chính `ordinal` chưa nằm trong comparison allowlist. |
| Một WebIDL overload đổi không? | Không đáng tin | Các overload cùng tên bị collapse. |
| API có thật sự được expose trên Windows không? | Chưa đáng tin | Build conditions và runtime gates chưa đầy đủ. |
| SB-AXon có dùng symbol này không? | Không | Không có dependency/usage scan của sản phẩm. |
| Logic C++/TypeScript có đổi behavior không? | Không | Công cụ chủ yếu đọc declaration. |
| Finch có bật feature cho user không? | Không | Finch/server config nằm ngoài source snapshot. |
| Enterprise policy hoặc automation có phụ thuộc switch/pref không? | Không đầy đủ | Không scan consumer/config bên ngoài. |
| UI có bị vỡ layout không? | Không | Không render/screenshot/interaction test. |
| Mojo change có thực sự break endpoint đang deploy không? | Không đầy đủ | Không model lifecycle, version negotiation và deployment topology. |

### “Fact count cao” không đồng nghĩa “đã đủ”

M151 `wide` schema 29 có 54.451 facts. Đây là con số lớn nhưng completeness không được suy ra từ số lượng tuyệt đối.

Ví dụ, parser nay lấy thêm 196 explicit-ordinal methods vào snapshot, nhưng comparison vẫn có thể bỏ thay đổi của chính ordinal. Tổng fact tăng đúng mà semantic diff vẫn thiếu.

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

Scorer hiện nhận một coverage scalar chung của version mới. Commit `46dae58` đã sửa denominator toàn cục, nên scalar của `default` đổi từ khoảng 5% giả thành 43,9% có nghĩa hơn. Nhưng vấn đề “một scalar cho mọi kind” vẫn còn nguyên.

Đối chiếu M151 bằng từng predicate của 9 extractor và target scope hiện tại:

| Extractor/bề mặt | `default` | `wide` |
|---|---:|---:|
| Base feature | 363 / 3.003 = 12,1% | 2.963 / 3.003 = 98,7% |
| Blink runtime JSON5 | 1 / 1 = 100% | 1 / 1 = 100% |
| WebIDL | 2.161 / 2.165 = 99,8% | 2.161 / 2.165 = 99,8% |
| Mojo | 367 / 1.462 = 25,1% | 1.436 / 1.462 = 98,2% |
| Pref/switch constants | 9 / 529 = 1,7% | 526 / 529 = 99,4% |
| Flags metadata | 1 / 1 = 100% | 1 / 1 = 100% |
| WebUI routes | 1 / 1 = 100% | 1 / 1 = 100% |
| WebUI controls | 434 / 1.031 = 42,1% | 1.031 / 1.031 = 100% |
| WebUI gates | 534 / 534 = 100% | 534 / 534 = 100% |

Các hàng có thể overlap vì một file có thể hợp với nhiều extractor; đây là lý do global total không phải tổng đơn giản của bảng.

### Phản hồi B3 đúng ở đâu?

Maintainer đúng rằng:

- coverage hiện chỉ đi vào scoring ở removal path;
- file share không phải xác suất một declaration bị mất;
- không nên lấy 12,1% rồi nhân trực tiếp severity như một probability giả.

Flat penalty `-15` vẫn có rationale hợp lý và không cần thay bằng linear scaling.

### Phản hồi B3 chưa giải quyết điều gì?

Trước khi áp dụng flat `-15`, scorer phải trả lời câu yes/no: **absence của kind này đã được xác nhận chưa?** Câu trả lời phải dựa trên coverage của chính kind đó.

Ví dụ trên `default`:

- WebIDL đạt 99,8%, vượt ngưỡng confirm 95%; một IDL removal không nên bị gọi là “chưa đọc đủ tree” chỉ vì global coverage là 43,9%.
- Pref/switch chỉ đạt 1,7% và Mojo 25,1%; removal ở hai nhóm này đúng là chưa được xác nhận.
- WebUI gate đạt 100%, nhưng vẫn chịu cùng trạng thái global với pref/switch.

Commit mới chỉ log số candidate riêng của từng rule, ví dụ “N file(s) could declare: web API definitions”. Đó mới là denominator riêng, chưa có numerator `target reaches N of M`, không được lưu vào snapshot và không được truyền vào `Scope`.

Vì vậy “coverage riêng theo extractor” không phải một công thức chấm điểm mới. Nó là input cần thiết để flat yes/no rule hiện tại được áp dụng đúng bề mặt. Sau đó vẫn giữ nguyên penalty `-15` nếu policy muốn.

Ngoài file-scope coverage, cần một trục riêng cho parse status: `parsed`, `unsupported`, `error`, `skipped`. Target chạm tới file không chứng minh parser hiểu toàn bộ file.

## 12. Các nguồn false positive khác

### 12.1. Test và fuzzer Mojo bị đưa vào report sản phẩm

Commit `46dae58` đã thêm `/fuzzers/`, `/fuzzer/`, `/web_test/`, `/web_tests/` và một filename regex cho `_test`, `_unittest`, `_browsertest`, `_fuzzer`, `_test_api`, cùng exact `fuzz.mojom`. Các ví dụ regression test mới đều bị loại đúng. Phần lớn 151 fact noise ban đầu đã biến mất.

Tuy nhiên filter chưa phủ naming phổ biến `_test_service.mojom`. Snapshot M151 `wide` schema 29 vẫn chứa 22 deduped facts từ 8 file có tên rõ ràng như test service:

- `components/media_router/.../media_router_traits_test_service.mojom`;
- `services/network/.../network_traits_test_service.mojom`;
- `ui/gfx/.../traits_test_service.mojom`;
- `ui/gl/.../traits_test_service.mojom`;
- `ui/ozone/.../wayland_overlay_config_traits_test_service.mojom`.

Vì vậy trạng thái chính xác là **partial fix**, không phải “test/fuzzer declarations never reach a product report” như tên test hiện viết.

Không nên sửa bằng regex “thấy chữ test ở đâu cũng bỏ”. Chromium có product API hợp lệ như `hit_test_region_list.mojom` và `xr_hit_test_source.idl`. Chính `_TEST_RE` rộng ở coverage đang loại nhầm các file này. Cần shared eligibility policy với test hai chiều:

- tên chắc chắn là test service/fuzzer phải bị loại;
- product term chứa `hit_test` vẫn phải được giữ.

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

### 14.1. Inline `</script>` injection đã sửa; unsafe spec URL còn mở

Report HTML nhúng JSON findings trực tiếp vào JavaScript:

```html
<script>window.__FINDINGS__=...;</script>
```

Trước `46dae58`, `json.dumps()` không escape chuỗi `</script>`. Nếu một fact name hoặc dữ liệu trong report chứa:

```html
</script><script>/* mã JavaScript */</script>
```

browser có thể kết thúc script dữ liệu sớm và chạy script chèn vào khi người dùng mở report.

Escape DOM về sau không sửa được vấn đề vì payload đã phá khỏi script ngay lúc HTML được parse.

Fix hiện tại dùng `_embed()` để escape `<`, `>`, `&`, U+2028 và U+2029 trước khi đặt JSON vào inline script. Targeted payload không còn chứa literal `</script>` và vẫn parse ngược thành JSON gốc. Lỗi zero-click/script-breakout ban đầu có thể đánh dấu **fixed**.

Một đường HTML khác vẫn cần sửa: `summary.milestone_brief[].spec` được HTML-escape rồi đặt thẳng vào `href`. HTML escaping chặn phá quote, nhưng không chặn URL scheme nguy hiểm.

Probe với:

```json
{"spec": "javascript:alert(1)"}
```

tạo đúng:

```html
<a href="javascript:alert(1)" rel="noreferrer">...</a>
```

Đây là click-triggered risk, thấp hơn lỗi `</script>` tự chạy khi mở file, nhưng vẫn không nên tồn tại trong report nhận data có thể sửa tay hoặc lấy từ remote enrichment. Chỉ render link cho `https:`/`http:`; scheme khác nên hiển thị plain text.

### 14.2. Cache traversal chính đã sửa; sanitizer còn bị duplicate

`snapshot._safe_name()` hiện allow-list `[A-Za-z0-9._-]`, thay backslash/separator lạ và collapse `..`. Probe `..\..\victim` không còn thoát khỏi snapshot/tree cache. Tên cache cũ như `refs_tags_151.0.7922.138` được giữ nguyên. Lỗi nghiêm trọng ban đầu có thể đánh dấu **fixed**.

Nhưng project còn một `_safe_name()` thứ hai trong `acquire.py` dùng cho listing cache. Bản này vẫn trả nguyên exact string `..`:

```text
acquire._safe_name("..") == ".."
```

Do đó listing path có thể đi từ `cache/listings/<ref>/...` lên `cache/...`. Nó không còn là đường unpack whole source tree như lỗi ban đầu và không thoát khỏi toàn bộ cache root trong probe này, nên severity thấp hơn. Nhưng hai sanitizer cho cùng một trust boundary là dấu hiệu dễ drift trở lại.

Cách sửa tốt nhất là một shared function hoặc hash cho mọi cache component, reject `.`/`..`/Windows reserved names, rồi kiểm `commonpath` ở nơi tạo path.

### 14.3. Proxy credential: fixed

`_redact_proxy()` hiện giữ scheme/host/port và thay userinfo bằng `<redacted>`. Hai case có và không có credential đều có test. Không tìm thấy đường print proxy nào khác trong CLI.

```text
http://user:password@proxy.corp:8080
→ http://<redacted>@proxy.corp:8080
```

## 15. Test hiện tại chứng minh được gì?

### Kết quả tốt

Lệnh đúng trong README:

```bash
python3 -m unittest discover -s tests -q
```

chạy **316 test** và tất cả đều pass trên Python 3.14.6.

Ngoài ra:

- Python source compile được.
- CLI khởi động được.
- JavaScript report không có syntax error.
- Git whitespace check sạch.
- Snapshot M143/M147/M148/M151 hiện có không ghi extract error hoặc missing target theo metadata hiện tại.

### Những điều 316 test không chứng minh

Nhiều test kiểm tra tính nhất quán nội bộ, ví dụ:

```text
README ghi 54.451 facts
snapshot cũng có 54.451 facts
→ test pass
```

Nhưng nếu extractor bỏ sót cùng một nhóm declaration từ trước, README và snapshot vẫn khớp nhau. Test đó không so kết quả với một oracle độc lập từ compiler/AST hoặc full Chromium inventory.

11 test mới là cải tiến có giá trị và đã bắt được các payload/case cụ thể của commit. Nhưng test hiện vẫn chưa bắt được:

- Mojo method ordinal thay đổi nhưng comparison trả 0 change;
- 121 WebIDL overload UID còn collapse và hai false negative M148–M151;
- global eligibility giữa coverage và extraction bất đồng;
- `_test_service.mojom` còn lọt;
- per-kind coverage không đi vào `Scope`;
- raw duplicate UID khác semantics;
- unsafe URL scheme trong spec link;
- sanitizer duplicate ở listing cache;
- reuse cache giữa hai local source khác nhau;
- report JSON sai schema;
- default unittest discovery có behavior khác nhau theo Python version.

### Green test nhưng CI có thể chạy 0 test

Từ repository root:

```bash
python3 -m unittest discover
```

Tại runtime đang review, kết quả là:

```text
Python 3.14.6
Ran 0 tests
NO TESTS RAN
exit code 5
```

Vì vậy câu cũ của report rằng lệnh này “kết thúc thành công” là **sai đối với runtime hiện tại**. Phản hồi B1 của maintainer đúng ở điểm đó.

Rủi ro tương thích vẫn có thật: [CPython 3.12](https://github.com/python/cpython/blob/3.12/Lib/unittest/main.py) thêm `_NO_TESTS_EXITCODE = 5`, trong khi [source CPython 3.11](https://github.com/python/cpython/blob/3.11/Lib/unittest/main.py) chưa có nhánh này. README của project ghi Debian + Python 3.9 là fully working. Vì thế trên một phần dải runtime mà project tự đưa vào compatibility matrix, zero-test discovery vẫn có thể trả 0.

Kết luận đúng phải là: không thể nói CI chắc chắn xanh trên mọi runtime, nhưng command mặc định vẫn không đáng tin vì nó chạy 0 test; exit code chỉ quyết định hệ thống có nhận ra hay không.

CI nên có guard riêng:

```text
test count phải > 0
```

và nên biến `tests/` thành package hoặc cấu hình runner tiêu chuẩn. Guard này vẫn nên có ngay cả khi Python mới đã trả code 5, vì nó làm contract của project độc lập với behavior của stdlib version.

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

## 17. Toàn bộ lịch sử 66 commit nói gì?

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

History là một nhánh thẳng gồm 66 commit, không có merge commit, do một author chính tạo từ tối 16-08 đến 22-08-2026. Trong khoảng năm ngày, project tăng từ 60 lên 316 test và đi tới schema 29. Đây là tốc độ của một prototype được audit dồn dập, chưa phải dấu hiệu của một release gate đã ổn định lâu dài.

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
| 64 | `9ca63f1` | Rút skill thành procedure, chuyển evidence về README. | Baseline của review đầu: 304 test, workflow evidence-first. |

### 17.6. Giai đoạn 5 — phản hồi external review

| # | Commit | Quyết định ghi trong commit message | Ý nghĩa đối với review |
|---:|---|---|---|
| 65 | `a864787` | Sửa bốn headline figures đã stale và thêm test đọc prose trong README/pipeline/skills. | Chủ động biến một phần documentation thành checked contract; nhưng matcher chỉ phủ ba sentence pattern nên nhiều số 5%/100% và bucket table cũ vẫn pass. |
| 66 | `46dae58` | Tự xác minh từng claim của external review trên M151; sửa denominator, platform, parser, security/cache/log và thêm 11 test. | Phản hồi nghiêm túc, schema 29 và nhiều fix đúng. Commit message cũng trở thành oracle để bắt omission: nó nói Mojo ordinal được compare, nhưng `diff.py` và probe cho thấy chưa. |

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

#### Coverage contract và release-gate wording

History đã hai lần phát hiện denominator tự chấm trên vùng nó biết. Commit `46dae58` đã sửa đúng lỗi lớn này bằng cách lấy predicate từ toàn bộ extractor registry; `wide` hiện là 99,1% của 8.349 candidates.

> Mức phê bình được hạ xuống: core denominator fix là tốt. Phần còn lại là shared eligibility, per-kind/parse completeness và CLI vẫn còn release-gate promise.

#### Mojo explicit ordinal

History gọi Mojo là high-severity runtime contract. Parser nay đọc explicit-ordinal method, nhưng diff allowlist vẫn không chứa `ordinal`.

> Đây vẫn là correctness blocker, nhưng vị trí lỗi đã chuyển từ extraction sang comparison; cần regression test đi qua cả hai snapshot.

#### Base-feature Windows projection

Nhiều commit xây một platform verdict dùng chung cho C++ `#if`, Mojo `[EnableIf]` và path. Enclosing `#if` của base feature đã được nối vào verdict ở `46dae58`.

> Mục này đã fixed; giữ lại trong history để thấy vì sao số score 0 thay đổi.

#### Test/fuzzer Mojo facts

Commit `062e7a2` và comment từ `095990a` đều nói test code là noise và phải loại. Filter mới bỏ phần lớn `_test.mojom`/fuzzer facts, nhưng `_test_service.mojom` vẫn còn 22 facts.

> Đây là partial fix; cần shared two-way eligibility test để không loại nhầm `hit_test` product APIs.

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
| Target completeness | Cải thiện lớn, chưa đạt | `wide=99,1%` trên 8.349 candidates; còn 73 path và eligibility policy vẫn duplicate. |
| Extraction completeness | Chưa đạt | Mojo method nay được extract nhưng ordinal change chưa được diff; WebIDL forms/overloads và parser fail-open còn. |
| Platform Windows | Đạt cho findings đã review | Base enclosing guard và exact `/mac/`/`/linux/` đã sửa, có test và số thực xác nhận. |
| Cross-version diff | Khá cho case đơn giản | `kind:key` dễ hiểu, nhưng rename/variant chưa đầy đủ. |
| Fact model | Một phần | Tốt cho inventory, chưa đủ cho compatibility verdict. |
| Core scoring | Khá–tốt cho evidence triage | Leading signal và score ceiling có measurement; chưa có per-kind confidence. |
| Product relevance | Cố ý ngoài scope | Đúng cho core; cần downstream integration layer nếu dùng trong release workflow. |
| Cache với full tag | Khá–tốt | Schema/scope/marker guards tốt; vẫn nên ghi commit/content hash. |
| Cache với local/raw ref | Chưa đạt | Không pin HEAD/content và có stale overlay/reuse risk. |
| Report UX | Khá | Có evidence và grouping, nhưng một số label sai semantics. |
| Security | Phần chính đã sửa, còn residual | Inline script breakout, main cache traversal và proxy leak fixed; unsafe spec scheme và duplicate listing sanitizer còn. |
| Documentation contract | Chưa nhất quán | README đã có bảng 43%/99% nhưng nhiều đoạn active vẫn nói 4–5%/100%; CLI vẫn gọi `wide` là release gate. |
| Test | Tốt cho regression, chưa đủ cho completeness | 316 pass; test mới tốt nhưng Mojo test dừng ở extraction, coverage test bỏ qua global filters, prose test chỉ match vài sentence. |
| Release gate | Chưa đạt | False negative và false positive chưa được kiểm soát. |

## 20. Thứ tự sửa đề xuất

### Giai đoạn 0: Ngăn kết luận sai và lỗ hổng rõ ràng

Ưu tiên làm ngay:

1. Bỏ release-gate promise còn sót trong CLI và sửa toàn bộ đoạn active đang nói 4–5%/100%.
2. Thêm URL scheme validation cho spec link; inline JSON escaping đã sửa.
3. Dùng chung cache sanitizer cho snapshot/tree/listing và reject special path components; main Windows traversal đã sửa.
4. Validate schema khi đọc snapshot/report.
5. Nếu có extract error hoặc missing target, report phải có trạng thái `incomplete` và scorer không được xác nhận removal chỉ bằng scope coverage.
6. CI phải assert test count lớn hơn 0 trên mọi Python version hỗ trợ.

### Giai đoạn 1: Sửa correctness cốt lõi

1. Thêm `ordinal` vào Mojo method comparison và test `@0 → @1` ở diff layer.
2. Hợp nhất toàn bộ eligibility/skip/platform policy giữa coverage và extraction, không chỉ `applies_to()`.
3. Lưu coverage riêng cho từng extractor/kind và dùng nó cho removal của kind tương ứng.
4. Mỗi file có trạng thái `parsed`, `skipped`, `unsupported`, `error`.
5. Redesign IDL representation để giữ overload variant set sau khi parser trả đúng tên.
6. Parse callback, typedef và `includes`.
7. Inherit partial-interface gate vào member.
8. Hoàn tất test/fuzzer filtering bằng rule hai chiều, gồm `_test_service` và giữ `hit_test` product APIs.

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

Tách các trục và hiển thị riêng:

```text
severity: nếu thay đổi thật thì hậu quả có thể lớn đến đâu?
extraction confidence: ta chắc extractor/diff đã thấy đúng đến đâu?
product relevance: SB-AXon có evidence sử dụng contract này không?
exposure: code path hoặc user population bị ảnh hưởng có rộng không?
```

Sau đó bổ sung:

- SB-AXon dependency/usage scan;
- config/policy/automation inputs;
- endpoint ownership;
- release telemetry hoặc incident history;
- allowlist cho expected changes;
- regression/integration tests trên binary thật.

Không nhân bốn giá trị này thành một số duy nhất khi chúng chưa được calibration. Phản hồi B4 của maintainer đúng: phép nhân đó đưa product guess trở lại quyết định xếp hạng dưới một tên khác và làm một giá trị `unknown` khó biểu diễn.

Display phù hợp hơn:

```text
severity: 75 / 80 ceiling
extraction confidence: low | medium | high
product relevance: unknown | referenced | confirmed-used
exposure: unknown | bounded | broad
```

Có thể sort theo policy rõ ràng hoặc filter từng trục, nhưng giữ nguyên evidence thay vì biến các ordinal label thành probability giả.

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
10. Với Mojo, kiểm tra method có ordinal và version attributes không; hiện ordinal change vẫn có thể bị diff bỏ qua.
11. Inline `</script>` breakout đã sửa, nhưng không bấm spec link từ report không tin cậy cho tới khi URL scheme được validate.
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

### “316 test đều pass, tại sao vẫn nói chưa an toàn?”

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

An toàn hơn trước: payload `</script>` không còn thoát khỏi inline JSON. Nhưng spec URL vẫn có thể giữ scheme `javascript:` và chạy khi người dùng bấm. Với report không tin cậy, có thể mở để đọc nhưng không nên click external/spec links cho tới khi renderer chỉ cho phép `http:`/`https:`.

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

1. **Completeness chưa được chứng minh:** `wide` đã đạt 99,1% file-scope nhưng còn 73 candidate, eligibility mismatch và chưa có parse/per-kind completeness.
2. **Semantics chưa được giữ đầy đủ:** Mojo ordinal được extract nhưng chưa được compare; WebIDL overload/variants và một số syntax vẫn bị mất.
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

## 26. Follow-up review commit `46dae58`

Phần này là kết luận có hiệu lực mới nhất. Nó được viết sau khi:

- đọc trọn commit message và diff của `a864787` và `46dae58`;
- đối chiếu lại source tại schema 29;
- chạy đủ 316 test;
- tái tạo default và wide reports trong memory từ cached snapshots;
- quét raw M148/M151 IDL facts trước dedupe;
- chạy targeted probes cho Mojo ordinal, HTML embedding/link, test filename và cache sanitizer;
- đối chiếu behavior `unittest` hiện tại với source chính thức của CPython 3.11/3.12.

### 26.1. Kết luận ngắn nhất

Commit này là một phản hồi review tốt: không sửa số liệu cho đẹp mà mở M151 tree, đo từng claim, bump schema và thêm regression tests. Những số chính maintainer đưa ra đều tái tạo được.

Nhưng có một claim quan trọng chưa đúng:

> Mojo `ordinal` đã được extract, **chưa được compare**.

Vì vậy `Foo@0 → Foo@1` hiện biến mất hoàn toàn khỏi report. Chỉ riêng lỗi này đã đủ để giữ verdict “chưa dùng làm automated release gate”, vì nó nằm trên process-boundary ABI và test mới đang cho cảm giác đã khóa behavior trong khi chỉ khóa nửa đầu pipeline.

Ngoài blocker đó, coverage architecture tiến bộ lớn nhưng per-kind scope và shared eligibility chưa hoàn tất; WebIDL overload vẫn có false negative thật; test-service noise, unsafe spec link và documentation contract còn sót.

### 26.2. Đánh giá từng mục trong bảng 9 thay đổi

| Mục | Kết luận follow-up | Bằng chứng ngắn |
|---|---|---|
| Coverage bỏ `.mojom`/`.idl` | **Core denominator fix đúng, tổng thể partial** | Registry predicate đã dùng chung; `wide` là 8.276/8.349. Global skip policy vẫn duplicate và scorer vẫn dùng một scalar. |
| Base feature enclosing `#if` | **Fixed** | Android-only fixture thành `not_compiled`; default zero-score 118 → 187. |
| Mojo `Foo@0(...)` | **Partial, còn blocker** | 6.099 methods được extract, nhưng `ordinal` không có trong `MEANINGFUL_ATTRS`; `@0 → @1` cho 0 change. |
| `/mac/`, `/linux/` | **Fixed** | 79 M151 Mojo facts được stamp `not_compiled` cho Windows. |
| WebIDL `margin-top` | **Fixed cho parser bug** | `margin-top` và `top` thành hai UID. 121 overload collision khác vẫn còn, nên broader identity problem chưa fixed. |
| Test/fuzzer filename | **Partial** | Ba fixtures mới bị skip; schema 29 vẫn còn 22 facts từ 8 `*_test_service.mojom` files. |
| Inline `</script>` | **Fixed** | `<`, `>`, `&`, U+2028/U+2029 được escape; payload không còn literal closing script. Spec URL scheme là residual riêng. |
| Windows cache traversal | **Fixed ở snapshot/tree path chính** | `..\..\victim` được sanitize. Listing cache còn dùng sanitizer thứ hai và giữ exact `..`. |
| Proxy credential | **Fixed** | Userinfo được thay bằng `<redacted>`; host/port vẫn đủ để debug. |

Nếu chấm theo đúng narrow bug được mô tả trong từng row, 6 mục fixed hoàn toàn và 3 mục partial. Con số “8/9” có thể hiểu được nếu coi “đã có code change cho 8 mục”, nhưng không nên dùng nó như “8 mục đã đóng correctness contract”.

### 26.3. Blocker 1 — Mojo ordinal có fact nhưng comparison không nhìn

Pipeline này có hai cửa khác nhau:

```text
source → extractor tạo Fact → diff chọn attrs để so → signal/score/report
```

Commit mới đã mở cửa thứ nhất. Trong `mojom.py`:

```python
"ordinal": parsed["ordinal"]
```

Nhưng cửa thứ hai trong `diff.py` vẫn là:

```python
KIND_MOJO_METHOD: ("signature", "params", "response", "attrs")
```

`ordinal` không nằm ở đây. Signature được tạo như `Foo(int32 x)`, cũng không mang `@0`.

Probe đã chạy:

```text
old attrs ordinal = 0
new attrs ordinal = 1
diff_snapshots(...) = []
```

Đây là ví dụ rất rõ cho nhận định “test đang chứng minh internal consistency chứ chưa chắc correctness”. Test mới có comment:

```text
The ordinal is part of the wire contract, so it is compared
```

nhưng assertion chỉ kiểm key tồn tại trong fact. Một câu trong comment và commit body cùng nói comparison đã hoạt động; code path thật chưa được gọi trong test.

Fix và test cần có:

```python
KIND_MOJO_METHOD: (
    "signature", "params", "response", "attrs", "ordinal"
)
```

Sau đó tạo old/new snapshots và assert:

- có đúng một `MODIFIED` change;
- delta là `ordinal: ["0", "1"]`;
- signal/severity mô tả wire contract change;
- HTML/Markdown hiển thị lý do dễ hiểu.

### 26.4. Coverage mới tốt hơn ở đâu và còn sai ở đâu?

#### Phần đã đúng

Denominator không còn chỉ biết prefs/features. Nó hỏi đủ 9 extractor predicates, nên `.mojom`, `.idl`, JSON5 và WebUI templates đều vào tập đo. Con số 43%/99% phản ánh target scope tốt hơn rất nhiều so với 5%/100% cũ.

#### Phần policy vẫn bị copy

Coverage và extraction vẫn có hai bộ global exclusions. Hai ví dụ đối nghịch:

```text
content/web_test/common/mojo_echo.mojom
coverage: candidate
extraction: skip vì /web_test/
```

```text
cc/mojom/hit_test_opaqueness.mojom
coverage: bỏ vì regex thấy _test_
extraction: đọc và snapshot có fact
```

Nói “predicate là cùng object” chưa đủ chứng minh hai pipeline không thể bất đồng, vì cả hai còn bọc predicate bằng policy khác nhau.

Thiết kế cần một function dùng chung, ví dụ:

```text
eligibility(path, extractor, platform)
→ candidate | intentional_skip(reason) | out_of_scope(reason)
```

Coverage và extraction phải gọi cùng function. Test nên lấy một real M151 listing rồi kiểm hai chiều:

- mọi candidate mà target reaches và materialization có trên disk đều được ít nhất một extractor thử đọc;
- mọi file extractor thật sự đọc đều có mặt trong denominator hoặc có reason rõ vì sao là out-of-denominator auxiliary evidence.

#### Per-kind coverage vẫn cần thiết

Global `default = 43,9%` che sự khác biệt cực lớn:

```text
WebIDL       99,8%
WebUI gates 100,0%
Mojo         25,1%
base feature 12,1%
pref/switch   1,7%
```

Flat `-15` không sai vì nó là policy step, không phải probability. Sai nằm ở việc dùng một scalar để quyết định step có chạy hay không. WebIDL removal gần 100% file-scope không nên nhận cùng “unconfirmed” state với preference removal 1,7%.

Mỗi coverage row cần ít nhất:

```json
{
  "web_idl": {"candidates": 2165, "read": 2161},
  "mojom": {"candidates": 1462, "read": 367}
}
```

và `Scope.confirms_absence(kind)` thay vì `Scope.confirms_absence()`.

### 26.5. WebIDL: nhận phản biện đúng nhưng không đóng nhầm finding

B2 giúp tìm được một parser bug thật. `margin-top` bị cắt thành `top`; sửa regex trước là đúng. Bản review này rút lại cách diễn đạt khiến người đọc có thể hiểu toàn bộ collision count đều là overload.

Sau fix, raw M151 vẫn có 121 `idl_member` UID mang nhiều semantic variants. Quét M148–M151 tìm 109 UID tồn tại ở cả hai bên nhưng overload set thay đổi. Dedupe làm mất hoàn toàn hai thay đổi:

```text
Navigator.install
M151 thêm install(InstallParams params)
selected overload install() không đổi
→ current diff không báo
```

```text
Document.parseHTMLUnsafe
overload/options/gate set thay đổi
selected one-argument overload không đổi
→ current diff không báo
```

Do đó hai nhận định cùng đúng:

- không dùng signature identity để che parser bug;
- sau khi parser đúng, vẫn phải giữ overload variants thay vì deterministic drop.

Deterministic dedupe giải quyết “hai máy phải cho cùng kết quả”. Nó không giải quyết “kết quả được giữ có đủ semantics không”.

### 26.6. Test/fuzzer filtering: cần tránh cả false positive lẫn false negative

Regex mới giảm noise đáng kể, nhưng snapshot hiện tại còn 22 facts từ 8 file `_test_service.mojom`. Đây là false positive: test-only interface có thể được xếp ở Mojo severity.

Ở chiều ngược lại, coverage regex `_test_` quá rộng và loại product concepts thật như `hit_test`. Sửa bằng một regex rộng hơn nữa sẽ chuyển false positive thành false negative.

Policy tốt hơn nên kết hợp:

- exact directory conventions;
- suffix conventions rõ như `_test`, `_unittest`, `_browsertest`, `_test_service`, `_fuzzer`;
- explicit exceptions/fixtures cho domain words `hit_test`;
- nếu muốn chính xác hơn nữa, dùng BUILD target metadata thay vì chỉ filename.

### 26.7. Security follow-up

#### Inline JSON

Fixed. `_embed()` xử lý đúng class attack đã report.

#### Spec links

Vẫn còn click-triggered unsafe scheme:

```text
input spec = javascript:alert(1)
output href = javascript:alert(1)
```

HTML escape chỉ bảo vệ cấu trúc attribute, không biến URL scheme thành an toàn. Chỉ allow `http:`/`https:` hoặc render plain text.

Browser automation không chạy được trong vòng audit này vì browser runtime trả lỗi metadata trước khi tạo tab. Vì vậy kết luận residual link dựa trên exact renderer output và browser URL semantics, không được trình bày như một completed browser E2E test.

#### Cache sanitizer

Main `snapshot_path`/`tree_path` traversal đã fixed. Residual ở `acquire._safe_name()` nhỏ hơn nhưng nên dọn ngay để không có hai security policies cùng tên.

#### Proxy

Fixed; targeted cases không lộ user/password.

### 26.8. Phản hồi B1–B4, kết luận từng điểm

#### B1 — đồng ý và sửa report

Maintainer đúng: trên Python hiện tại, zero tests trả exit 5, không phải success. Local run Python 3.14.6 xác nhận. CPython 3.12 source cũng có `_NO_TESTS_EXITCODE = 5`; CPython 3.11 source chưa có.

Điểm còn lại: command mặc định vẫn chạy 0 test, và README đưa Python 3.9 vào compatibility matrix. Guard `test_count > 0` vẫn nên tồn tại để behavior CI không phụ thuộc stdlib version.

#### B2 — đồng ý một nửa

Đồng ý parser diagnosis `margin-top` và thứ tự sửa parser trước. Không đồng ý rằng điều này loại bỏ overload finding: 121 collisions và hai false negatives thật vẫn còn sau fix.

#### B3 — đồng ý flat penalty rationale, không đồng ý đóng per-kind coverage

Không linear-scale score theo file percentage. Nhưng yes/no “removal đã confirmed chưa?” phải dùng coverage của kind tương ứng. Log candidate count riêng chưa phải coverage riêng và hiện không đi vào snapshot/scorer.

#### B4 — đồng ý hoàn toàn với phản biện công thức

Report cũ đề xuất:

```text
severity × extraction_confidence × product_relevance × exposure
```

Đề xuất đó không nhất quán với chính lời khuyên “không đưa product guess trở lại core scoring”. Nó cũng nhân các giá trị chưa calibrated như thể chúng là ratio-scale quantities. Công thức đã được rút khỏi mục 20.

Hướng mới là giữ severity, extraction confidence, product relevance và exposure thành các cột/trục riêng. Product relevance mặc định là `unknown`, chỉ đổi khi downstream SB-AXon evidence chứng minh usage.

### 26.9. Con số nào đã được xác nhận?

Từ snapshot và diff in memory tại `46dae58`:

| Target | Facts M148 → M151 | Changes | Breaking | Behaviour | New | Housekeeping | Score 0 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `default` | 28.487 → 29.118 | 3.027 | 282 | 468 | 1.240 | 1.037 | 187 |
| `wide` | 52.519 → 54.451 | 6.071 | 804 | 696 | 2.980 | 1.591 | 441 |

Coverage M151:

```text
default: 3.669 / 8.349, missing 4.680
wide:    8.276 / 8.349, missing 73
```

Test:

```text
python3 -m unittest discover -s tests -q
Ran 316 tests
OK
```

Các con số maintainer gửi về bucket/fact/coverage khớp với lần đo độc lập này.

### 26.10. Documentation vẫn tự mâu thuẫn dù tests xanh

Commit `a864787` thêm test kiểm một số headline sentence, nhưng test matcher chỉ giữ ba pattern cụ thể. Vì vậy 316 test vẫn pass khi các đoạn active sau mâu thuẫn với bảng mới:

- README có bảng `default 43% / wide 99%`, rồi ngay dưới nói “5%”, tiếp theo lại nói “4%”.
- README score examples và comparison table vẫn ghi `default 5% / wide 100%`.
- `docs/pipeline.html` còn nhiều label 5%/100%.
- `reference/signals.md` còn nói default 5%.
- `score.py` comment còn “a twentieth”.
- CLI `--target-set` help vẫn nói wide “reads everything an extractor understands. Use it for a release gate”.
- CLI partition help vẫn nói dùng full set cho release gate.
- README cùng một M148→M151 story vừa nói `226 of 282 Breaking`, vừa còn câu “two of the 315 Breaking rows” và bucket table cũ 239/492/1.148/921.

Điều này không làm extractor sai, nhưng làm user contract sai. Đặc biệt, maintainer nói đã bỏ chữ release gate khỏi target table là đúng; nhưng promise đó vẫn tồn tại trong CLI, nơi người dùng thật đọc ngay trước khi chạy.

Test docs nên kiểm semantic facts có tên ổn định thay vì vài literal sentence, ví dụ generate một canonical data block rồi render README/pipeline examples từ đó, hoặc parse tất cả active coverage/bucket tables và fail khi có hơn một current value.

### 26.11. Release-gate verdict sau commit này

Verdict vẫn là **chưa đạt**, nhưng lý do đã hẹp và cụ thể hơn bản đầu:

1. Mojo ordinal change có false negative tái hiện được.
2. WebIDL overload có hai false negative thật trên M148–M151.
3. Removal confidence dùng global coverage thay vì kind coverage và không tích hợp parse/missing-target completeness.
4. Test/fuzzer eligibility còn bất đồng và test-service facts còn lọt.
5. CLI vẫn hứa release gate trong khi `wide` còn 73 candidates và các completeness layer trên chưa đóng.

Các lỗi base-platform, Mac/Linux, inline JSON, main cache traversal và proxy leak không còn là blocker sau commit này.

### 26.12. Thứ tự sửa ngắn nhất từ đây

1. Thêm Mojo method `ordinal` vào comparison và regression test ở diff/report layer.
2. Giữ WebIDL overload variant set; test hai false negative `Navigator.install` và `Document.parseHTMLUnsafe`.
3. Tạo shared eligibility policy cho discovery/extraction; thêm `_test_service` nhưng giữ `hit_test`.
4. Lưu per-extractor coverage và gọi `confirms_absence(kind)`.
5. Khi có missing target/extract error, không xác nhận removal chỉ bằng coverage scope.
6. Validate `spec` URL scheme; hợp nhất cache sanitizer.
7. Xóa release-gate wording còn lại và sửa toàn bộ active 4–5%/100% examples.
8. Thêm test count guard hoặc package discovery để bare `unittest discover` thật sự chạy test.

Sau các bước 1–5, chạy lại real-version matrix ít nhất M143/M147/M148/M151 và so raw grammar inventory với deduped snapshot. Khi đó mới nên đánh giá lại release gate, không chỉ dựa vào việc toàn bộ regression tests pass.

## 27. Follow-up review commit `8ced148` — schema 30

### 27.1. Kết luận trước, để không bị ngợp bởi chi tiết

Commit này là một bước tiến thật. Maintainer đã nhận đúng lỗi mình vừa tạo ở commit trước, không né tránh, và regression test mới cho explicit Mojo ordinal đi qua cả ba tầng `extract → diff → score`. Bare `unittest discover` cũng đã được sửa đúng, kể cả trên Python 3.9 là phiên bản thấp nhất project tuyên bố hỗ trợ.

Nhưng câu “ba mục partial đã đóng nốt” vẫn hơi sớm. Kết quả review độc lập là:

| Hạng mục | Kết quả review mới | Trạng thái |
|---|---|---|
| `Foo@0 → Foo@1` | Có delta `ordinal`, signal `ipc_ordinal_changed`, score 80, Breaking | **Fixed** |
| Ordinal Mojo nói chung | Ordinal ngầm theo vị trí vẫn không được lưu hoặc compare | **Partial** |
| Shared eligibility | Đã thống nhất test/vendor/product filter; platform policy vẫn khác có chủ ý, và 17 test-only facts vẫn lọt | **Partial** |
| Per-surface removal confidence | Scorer hỏi đúng surface; denominator của hai surface bị thiếu membership vì mỗi path chỉ giữ surface đầu tiên | **Partial** |
| Hiển thị per-surface coverage | Có trong snapshot/report JSON, chưa xuất hiện trong CLI, Markdown hoặc HTML bình thường | **Chưa đúng claim “in ra”** |
| `javascript:` trong spec | Non-HTTP(S) render thành text, không thành link | **Fixed** |
| Cache sanitizer thứ hai | Đã hợp nhất vào `acquire.safe_name` và chặn traversal cũ | **Fixed**, còn edge case portability/collision |
| Bare `unittest discover` | Chạy đủ 327 test trên Python 3.14 và Python 3.9 | **Fixed** |
| “Docs test quét mọi con số có nhãn trong mọi tài liệu” | Test chỉ nhận ba sentence shape và bốn bucket label; nhiều số active vẫn cũ | **Chưa fixed** |
| WebIDL overload | Maintainer đã ghi nhận, chưa sửa | **Open** |
| Missing target / parse error đi vào absence confidence | Maintainer đã ghi nhận, chưa sửa | **Open** |

Kết luận release gate vẫn là **chưa đạt**. Lý do lần này cụ thể hơn: explicit ordinal đã đóng, nhưng process-boundary comparison vẫn có hai false-negative class tái hiện được là **implicit ordinal** và **enclosing build guard**.

### 27.2. Tôi đã kiểm lại những gì?

Tại thời điểm bắt đầu phép đo, baseline ở đúng trạng thái:

```text
HEAD             8ced148
main             8ced148
origin/main      8ced148
source tree      clean
schema           30
commit history   67 commit
```

Trong lúc hoàn thiện file audit, một process khác trong cùng workspace tạo thay đổi cho WebIDL overload và absence completeness, rồi commit/push thành `b844108`. Tôi không tạo, sửa hoặc push commit đó. Các thay đổi này xuất hiện sau khi số đo đã hoàn tất, nên mục 27 vẫn review đúng baseline được yêu cầu là `8ced148`; hai mục được đánh dấu Open bên dưới không phải là đánh giá lại implementation ở `b844108`.

Hai cách discover test đều chạy thật:

```text
python3 -m unittest discover -q
Ran 327 tests
OK

python3 -m unittest discover -s tests -q
Ran 327 tests
OK
```

Tôi còn chạy bare discovery bằng `/usr/bin/python3` 3.9.6. Kết quả vẫn là 327 test, exit code 0. Vì vậy fix `tests/__init__.py` không chỉ đúng trên Python 3.14.6 của môi trường hiện tại mà còn đúng ở lower bound Python 3.9 được README hỗ trợ.

Đo lại snapshot M148 → M151 từ cache schema 30, có truyền `target_milestone` giống đường chạy thật của CLI:

| Target | Facts M148 → M151 | Changes | Breaking | Behaviour | New | Housekeeping | Score 0 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `default` | 28.507 → 29.138 | 3.027 | 282 | 468 | 1.240 | 1.037 | 187 |
| `wide` | 52.367 → 54.298 | 6.069 | 804 | 695 | 2.979 | 1.591 | 441 |

Coverage M151:

```text
default: 3.677 / 8.366, missing 4.689
wide:    8.295 / 8.366, missing 71
```

Các số maintainer gửi là đúng. Một chi tiết cần nói rõ: M148 → M151 không có explicit ordinal delta thật nào. M151 `default` có 0 method fact mang `ordinal`, `wide` có 196; nhưng không có method `@N` chung giữa hai phía đổi từ số này sang số khác. Vì vậy signal mới được chứng minh bằng synthetic contract test, không phải là nguyên nhân làm bucket count của real report thay đổi.

Per-surface scoring cũng có hiệu ứng đúng như maintainer mô tả:

- 77 WebIDL removals không còn nhận dòng `-15 unconfirmed`.
- 45 removal giữ score 70; 32 removal còn score 30 vì build/platform evidence, không phải vì coverage.
- `default` có 139 `pref_left_scan` và 1 `switch_left_scan`; surface này chỉ được đọc rất ít nên chúng vẫn bị giảm confidence.
- `wide` không trừ unconfirmed penalty cho các pref/switch removal đó.

### 27.3. Explicit ordinal đã được sửa đúng — đây là điểm nên ghi nhận

Ở commit trước, test chỉ hỏi:

> “Fact có key `ordinal` không?”

Câu hỏi đó chỉ kiểm cửa thứ nhất là extraction. Test mới hỏi đủ chuỗi:

```text
old mojom: Foo@0(int32 a)
new mojom: Foo@1(int32 a)
        ↓
diff_snapshots
        ↓
deltas = {"ordinal": ["0", "1"]}
signal = ipc_ordinal_changed
score  = 80
bucket = Breaking
```

Đây là regression test đúng loại: nếu một ngày parser vẫn extract nhưng `MEANINGFUL_ATTRS` lại bỏ `ordinal`, test sẽ đỏ. Comment và assertion giờ cùng chứng minh một claim.

Signal riêng cũng hợp lý hơn việc gộp vào `ipc_signature_change`: signature chữ có thể không đổi trong khi số định tuyến trên wire đổi. Label giải thích trực tiếp hậu quả cho người đọc report.

### 27.4. Blocker mới: explicit ordinal không phải toàn bộ ordinal

#### Ví dụ cực ngắn

Mojom cho phép không viết `@N`:

```mojom
// Version cũ
interface I {
  Foo();  // ordinal ngầm 0
  Bar();  // ordinal ngầm 1
};

// Version mới
interface I {
  Bar();  // ordinal ngầm 0
  Foo();  // ordinal ngầm 1
};
```

Hai method vẫn cùng tên, cùng params, cùng response và không có field `ordinal` trong Fact. Probe chạy đúng code hiện tại trả:

```text
implicit method reorder changes: []
```

Nói đời thường: commit mới đã kiểm được số ghế khi số được in trên vé. Nhưng khi rạp tự đánh số ghế theo thứ tự hàng, ChromeDrift không lưu thứ tự đó, nên đổi chỗ hai ghế vẫn bị coi là “không có gì thay đổi”.

Đây không phải giả định riêng của review. Tài liệu Mojom chính thức nói ordinal ngầm được gán theo lexical position; explicit ordinal phải được dùng nhất quán trong declaration. Xem [Mojom IDL documentation](https://chromium.googlesource.com/chromium/src/+/master/mojo/public/tools/bindings/README.md).

Đối với method, tình hình còn có thêm một lớp build-time:

- bindings generator đi qua các method theo thứ tự và dùng index cho method không có explicit ordinal; xem [mojom bindings generator](https://chromium.googlesource.com/chromium/src/+/master/mojo/public/tools/bindings/mojom_bindings_generator.py);
- Chromium desktop mặc định có message-ID scrambling dựa trên `chrome/VERSION`, và từng GN target có thể tắt bằng `scramble_message_ids`; xem [mojom.gni](https://chromium.googlesource.com/chromium/src/+/master/mojo/public/tools/bindings/mojom.gni).

Vì vậy “wire ID thực tế” có thể phụ thuộc đồng thời vào:

```text
explicit @N, nếu có
hoặc lexical position, nếu không có
+ generator salt/version
+ GN target configuration
```

ChromeDrift hiện chỉ thấy dòng đầu tiên.

#### Đo trên M148 → M151 thật

Tôi dựng lại vị trí bằng `path + line`, chỉ xét fact tồn tại ở cả hai version và không có explicit `ordinal`:

| Kind | Fact cũ còn tồn tại nhưng vị trí ngầm đổi | Số container bị ảnh hưởng | Không có diff row nào cho fact đó | Có row, nhưng vì thuộc tính khác |
|---|---:|---:|---:|---:|
| Mojo method | 503 | 48 interface | 485 | 18 |
| Mojo field | 607 | 72 struct/union | 602 | 5 |

Không được đọc bảng này thành “có chắc 1.110 breaking change”. Mức nguy hiểm phụ thuộc vào:

- declaration có `[Stable]` hay không;
- hai peer có được build và deploy cùng version hay có version skew;
- GN target có scramble message ID hay không;
- thay đổi là append hợp lệ hay insert/reorder phá vị trí cũ;
- interface có thực sự đi qua boundary mà sản phẩm quan tâm hay không.

Nhưng bảng đủ chứng minh một điều hẹp và chắc chắn: **comparison model hiện chưa thể phát hiện hoặc giải thích class thay đổi này**. Việc không báo không có nghĩa là an toàn.

#### Cách sửa đúng, không nên chỉ nhét một field rồi chấm tất cả 80

Parser nên lưu tối thiểu:

```text
ordinal_source: explicit | implicit
declared_ordinal: N | null
lexical_index: N
```

Sau đó comparison tách ba trường hợp:

1. Explicit `@N` đổi: signal mạnh như hiện tại.
2. Existing implicit member đổi `lexical_index`: tạo signal riêng, mang warning về build config/version skew.
3. Member mới được append cuối: không gắn cùng severity với reorder/insert trước member cũ.

Nếu muốn gọi đây là wire-compatible release gate, tool còn phải đọc hoặc được truyền GN policy và phải giữ `[Stable]` evidence. Nếu chưa có dữ liệu đó, report nên nói “implicit wire order changed; compatibility depends on generated binding policy”, không nên giả vờ chắc chắn bằng một score 80 cho mọi trường hợp.

### 27.5. Blocker mới thứ hai: enclosing Mojo guard được extract nhưng không compare

Probe:

```mojom
// old
[EnableIf=is_android]
interface I { Foo(); };

// new
[EnableIf=is_win]
interface I { Foo(); };
```

Fact thực tế cho thấy extractor làm đúng phần việc của nó:

```text
old Foo: conditions=[EnableIf=is_android], windows=not_compiled
new Foo: conditions=[EnableIf=is_win],     windows=compiled
```

Nhưng kết quả diff vẫn là:

```text
enclosing guard changes: []
```

Nguyên nhân rất giống lỗi ordinal vừa sửa:

| Kind | Extractor có lưu guard? | `MEANINGFUL_ATTRS` có compare? |
|---|---|---|
| `mojo_interface` | Có `conditions`, `platform_state` | Không; tuple rỗng |
| `mojo_method` | Có inherited `conditions`, `platform_state` | Không; chỉ compare signature/params/response/attrs/ordinal |
| `mojo_struct` | Có | Không; chỉ `mojo_kind` |
| `mojo_field` | Có | Không; chỉ type/ordinal/default/attrs |
| `mojo_enum` | Có | Không; chỉ values |

M151 `wide` có khá nhiều fact mang enclosing condition:

| Kind | Có `conditions` | Tổng fact |
|---|---:|---:|
| Interface | 28 | 1.479 |
| Method | 288 | 6.012 |
| Struct/union | 53 | 2.867 |
| Field | 314 | 13.015 |
| Enum | 24 | 1.477 |

Trong pair M148 → M151 hiện tại, tôi không tìm thấy thêm pure enclosing-guard transition làm thay đổi bucket count: những row có condition/platform delta quan sát được đồng thời còn có direct attribute hoặc signature delta. Vì vậy đây là **contract false negative tái hiện bằng fixture**, chưa phải tuyên bố rằng real report đang thiếu đúng N row.

Cách sửa cần tránh tạo hàng trăm row trùng nhau. Nếu interface guard đổi, mọi method con đều đổi effective platform state. Một design sạch hơn là lưu riêng:

```text
own_conditions
inherited_conditions
effective_platform_state
```

Sau đó:

- guard của interface/struct đổi thì emit một container-level finding;
- direct guard của method/field đổi thì emit member-level finding;
- child chỉ mang inherited evidence để giải thích, không tự nhân bản cùng một finding cho mọi member;
- compare effective state cho platform đang review, còn raw condition text là evidence phụ.

### 27.6. Per-surface scoring đúng hướng, nhưng denominator chưa thật sự per-surface

Phần score đã sửa đúng logic chính:

```text
removal kind
    ↓ KIND_SURFACE
surface coverage row
    ↓
>= 95%  → xác nhận absence, không trừ 15
<  95%  → trừ 15; pref/switch inferred removal chuyển Housekeeping
```

Lỗi nằm trước đó, khi tạo các row. `discover_candidates()` trả `Dict[path, note]` và dùng:

```python
found.setdefault(path, rule.note)
```

Một file có thể được cả extractor feature, pref và WebUI gate đọc. Nhưng `setdefault` chỉ giữ note của extractor match đầu tiên. Từ đó trở đi file biến mất khỏi denominator của các surface còn lại.

Trên listing M151 có **378 path match nhiều hơn một surface**:

| Overlap | Số file |
|---|---:|
| feature flags + chrome:// visibility gates | 194 |
| feature flags + preference keys and switches | 181 |
| preference keys and switches + visibility gates | 3 |

So row đang lưu với phép đếm độc lập theo từng extractor:

| Surface | Row hiện tại `default` | Đúng theo membership `default` | Row hiện tại `wide` | Đúng theo membership `wide` |
|---|---:|---:|---:|---:|
| Preference keys and switches | 4 / 348 = 1,1% | 9 / 529 = 1,7% | 345 / 348 = 99,1% | 526 / 529 = 99,4% |
| Visibility gates | 340 / 340 = 100% | 537 / 537 = 100% | 340 / 340 = 100% | 537 / 537 = 100% |

Feature flags đứng trước nên giữ cả các file overlap; row của nó vẫn là 363 / 3.011 ở `default` và 2.971 / 3.011 ở `wide`.

Hiện tại lỗi này chưa đổi quyết định `confirms_absence` vì:

- `default` pref vẫn dưới 95% theo cả hai cách;
- `wide` pref vẫn trên 95%;
- visibility gate vẫn 100%.

Tức là score của pair hiện tại vẫn đúng theo threshold đã chọn. Nhưng label “coverage của preference keys and switches” đang không đúng population, và một surface gần mốc 95% có thể đổi kết luận chỉ vì registry order.

Cách sửa:

```text
path -> set(surface)
```

Global coverage vẫn dedupe path để có `8.295 / 8.366`. Riêng từng surface thì một path được tính vào mọi surface mà extractor tương ứng có thể đọc. Tổng candidate của các row được phép lớn hơn global total; đó là overlap thật, không phải double-count bug.

Ngoài ra `_EXTRACTOR_NOTES` trong `targets.py` và `KIND_SURFACE` trong `score.py` là hai mapping phải tự nhớ cập nhật cùng nhau. Kind mới không có mapping sẽ silently fallback về global coverage. Tốt hơn là registry khai một lần:

```text
extractor name
candidate surface
fact kinds produced
```

và test bắt mọi fact kind phải có surface rõ ràng, thay vì coi global fallback là behavior hợp lệ.

### 27.7. “Coverage per-surface giờ in ra thật” chưa đúng với normal output

Điều đã có thật:

- `snapshot.meta.coverage.by_surface` có dữ liệu;
- report JSON giữ dữ liệu đó ở `meta.coverage.from/to.by_surface`;
- `Scope` dùng row tương ứng để score removal.

Điều chưa có:

- snapshot log chỉ in overall `read / candidates`;
- Markdown report chỉ in overall coverage và ba directory gap lớn nhất;
- HTML không có bảng surface coverage;
- tìm toàn source, `by_surface` chỉ xuất hiện ở targets, score và tests, không nằm trong renderer.

Vì vậy bảng maintainer gửi là bảng có thể lấy từ JSON, không phải thứ user bình thường nhìn thấy sau command. Claim chính xác nên là:

> “Per-surface coverage đã được lưu và dùng khi score; UI/report table chưa expose.”

Một câu khác trong generated `out/report.md` vẫn overclaim:

```text
Run --target-set wide to read every file an extractor understands.
```

Ngay cùng run, `wide` là 8.295 / 8.366 và còn 71 file. Câu đúng là “use the widest built-in target set; the report will still name remaining gaps”.

### 27.8. Shared eligibility đã tốt hơn, nhưng cần mô tả đúng biên

`eligibility.py` là sửa đúng cho lỗi hai chiều đã nêu:

- exact directory component loại `web_test/`;
- suffix trước extension loại `_test_service.mojom`;
- `hit_test_opaqueness.mojom` không còn bị substring `_test_` bắt nhầm;
- discovery và extraction cùng gọi một test/vendor/product filter.

Nhưng hai pipeline vẫn có policy khác nhau với platform directory:

- discovery loại Android/Ash/iOS/Mac/Linux/Fuchsia khỏi denominator của Windows run;
- extraction vẫn cho extractor `constants` đọc các file đó để tìm pref/switch đã chuyển sang platform khác.

Trên full cached listing M151 có 68 file dạng này mà `constants` có thể đọc:

```text
default reaches 1 / 68
wide reaches   64 / 68
```

Bốn file còn lại nằm dưới `fuchsia_web/`. Những file này không nằm trong per-surface denominator dù fact của 64 file có thể được dùng để tránh kết luận nhầm “pref đã bị xóa”. Đây có thể là design đúng: chúng là **auxiliary cross-platform evidence**, không phải Windows product candidates. Nhưng contract cần nói rõ vậy; câu “cả hai pipeline có một eligibility policy” hiện rộng hơn code thực tế.

Eligibility theo filename cũng chưa đóng hết test-only source. M151 `wide` vẫn có 17 Mojo facts từ bốn file có mục đích test rất rõ:

| File | Facts | Evidence trong tên/comment |
|---|---:|---|
| `components/autofill/core/common/mojom/test_autofill_types.mojom` | 9 | Interface `TypeTraitsTest` |
| `components/heap_profiling/in_process/mojom/test_connector.mojom` | 4 | Comment nói dùng cho multiprocess test |
| `services/audio/public/mojom/testing_api.mojom` | 2 | Comment nói chỉ expose trong testing environment |
| `services/video_capture/public/mojom/testing_controls.mojom` | 2 | Comment nói integration testing |

Không nên sửa bằng regex “filename bắt đầu bằng `test_` thì loại ở mọi extractor”: WebIDL có những tên chuẩn chứa `test_` thật và generic rule có thể đổi false positive thành false negative. Hướng an toàn hơn:

1. Có convention riêng theo extractor/language.
2. Nếu có Chromium checkout đầy đủ, đọc `BUILD.gn` `testonly = true` hoặc target reachability.
3. Cho phép explicit include/exclude override và in reason trong catalog.

Bốn file trên không tạo finding trong M148 → M151, nên chúng chưa làm bucket count hiện tại sai; chúng chứng minh eligibility contract vẫn còn lỗ.

### 27.9. Documentation test lại mắc đúng lỗi “test chứng minh ít hơn comment”

Commit message nói:

> “Test figure giờ quét mọi con số có nhãn trong mọi tài liệu.”

Code thật không làm vậy. `TestTheDocumentedM148FiguresAreStillTrue` kiểm:

- ba regex sentence cụ thể;
- bốn label bucket: Breaking, Behaviour change, New surface, Housekeeping;
- một invariant retired-flag total bằng 132.

Nó không kiểm mọi labelled number, không hiểu schema/test/fact/coverage count, và regex label còn phụ thuộc label đứng ngay trước con số trong một vài dạng Markdown. HTML layout khác có thể không match.

Quan trọng hơn, test gọi `skipTest` nếu `out/report.json` không tồn tại hoặc không đúng pair/target. `out/` nằm trong `.gitignore`, nên fresh checkout chạy unit tests không tự có oracle này trừ khi CI tạo report trước. Nói cách khác, guard docs là optional local check, chưa phải CI contract độc lập.

327 test vẫn pass trong khi các active docs đang giữ số cũ:

| Nơi | Đang ghi | Đo lại schema 30 |
|---|---:|---:|
| README default coverage | 3.669 / 8.349 | 3.677 / 8.366 |
| README wide coverage | 8.276 / 8.349 | 8.295 / 8.366 |
| README default facts | 29.118 | 29.138 |
| `docs/pipeline.html` default facts | 29.118 | 29.138 |
| `docs/pipeline.html` coverage | 3.669 / 8.349 và 8.276 / 8.349 | 3.677 / 8.366 và 8.295 / 8.366 |
| Skill coverage example | 3.669 / 8.349 | 3.677 / 8.366 |

README còn câu “5% sounds terrible” ngay sau bảng nói 43%. Bảng scoring vẫn ghi `default 5% / wide 100%` cho `pref_left_scan`; semantics mới phải là coverage của pref/switch surface, khoảng 1% / 99%, không phải global coverage. `docs/pipeline.html` còn widget dùng global 44% để minh họa deduction, trong khi scorer đã chuyển sang per-surface.

Fix bền hơn không phải thêm regex thứ năm. Nên có một canonical machine-readable measurement fixture, rồi:

- generate bảng README/pipeline/skill từ fixture;
- hoặc parse tất cả code block/table có marker rõ như `data-audit-figure="m148-m151"`;
- CI phải tự build hoặc tải fixture, không được silently skip;
- test phải fail nếu tài liệu có current-value block ngoài canonical renderer.

Historical numbers vẫn có thể tồn tại nếu được gắn nhãn commit/schema rõ ràng. Điều cần cấm là hai con số cùng tự nhận là trạng thái hiện tại.

### 27.10. Mojo attributes chưa đủ để chấm đúng semantics

Parser hiện chia attribute theo cách quá thô:

- trên interface/struct/enum, `_conditions()` chỉ giữ `EnableIf*`; các attribute khác bị bỏ;
- trên method, toàn bộ direct attribute được giữ trong một dict `attrs`;
- diff thấy bất kỳ pure `attrs` delta nào ở method đều gắn `build_gate_changed`.

Nhưng Mojom attribute không cùng nghĩa. Ví dụ:

| Nhóm | Ví dụ | Ý nghĩa gần đúng |
|---|---|---|
| Build availability | `EnableIf`, `EnableIfNot` | Declaration có được compile không |
| Wire/versioning | `Stable`, `Extensible`, `MinVersion` | Version skew và compatibility contract |
| Sandbox/context | `AllowedContext`, `RequireContext`, `ServiceSandbox` | Context nào được phép bind/call service |
| Call behavior | `Sync` và attribute khác | Cách call/binding hoạt động |

Trong 8.295 candidate file mà `wide` thực sự tải ở M151, scan attribute block sau khi mask comment thấy, ví dụ:

```text
Stable          215 occurrences / 58 files
Extensible      149 occurrences / 33 files
AllowedContext   18 occurrences / 9 files
RequireContext   20 occurrences / 16 files
```

Đặc biệt, tài liệu Mojom dùng `[Stable]` để đánh dấu type/interface phù hợp với version-skewed independent binaries. Đây là evidence rất quan trọng để biết implicit ordinal change nào đáng báo mạnh, nhưng ChromeDrift đang bỏ nó ở container.

Có một misclassification thật trong M148 → M151:

```text
network.mojom.NetworkContext.CreateNetLogExporter
attrs: {} → {AllowedContext=sandbox.mojom.Context.kBrowser}
```

Tool hiện báo:

```text
signal: build_gate_changed
score: 35
reason: declaration may no longer be in the binary we ship
```

Đây là context/sandbox restriction, không phải Windows build condition. Row có thể vẫn đáng review, nhưng reason đang giải thích sai cơ chế.

Fix nên parse attribute thành field có type rõ, ví dụ `build_conditions`, `stability`, `min_version`, `sandbox_context`; rồi map signal theo semantic group. Không nên để mọi `attrs` delta đi qua một `elif` chung.

### 27.11. Security: URL fix tốt; cache traversal cũ đóng, sanitizer còn edge case

#### Spec URL

Tôi chạy output thật của HTML renderer với ba giá trị:

```text
javascript:alert(1)
data:text/html,...
https://example.test/spec
```

Sau đó parse DOM bằng `html.parser`:

- hai scheme đầu xuất hiện dưới dạng visible text, không có `<a>`;
- chỉ HTTPS tạo anchor;
- payload chứa `<script>` được escape, không xuất hiện thành element.

Như vậy fix scheme allow-list hoạt động đúng ở renderer output, không chỉ đúng ở helper predicate. Tôi chưa gọi đây là browser E2E vì browser connector của môi trường review lỗi trước khi mở page (`sandboxPolicy` metadata bị thiếu); đó là giới hạn của môi trường review, không phải lỗi project.

#### Cache name

Việc bỏ `_safe_name` thứ hai và dùng một allow-list đã đóng đường `..\\..\\` trên Windows mà review trước nêu. Tuy nhiên helper hiện vẫn có ba edge case:

```text
safe_name(".")   -> "."
safe_name("a/b") -> "a_b"
safe_name("a:b") -> "a_b"
safe_name("a\\b")-> "a_b"
safe_name("CON") -> "CON"
```

Hệ quả:

- `trees/.` được filesystem normalize thành chính container `trees/`, không phải một child riêng;
- nhiều ref khác nhau collision vào cùng cache key;
- `CON`, `NUL`, `COM1`, tên kết thúc bằng dấu chấm là reserved/problematic trên Windows.

Đây không còn là traversal blocker giống lỗi cũ, nhưng là reliability và cache-isolation residual. Cách đơn giản là tạo slug dễ đọc cộng hash ngắn của raw value, đồng thời reject `.` và Windows reserved basenames.

### 27.12. Hai blocker maintainer đã thừa nhận vẫn giữ nguyên

#### WebIDL overload / variant identity

Sửa `margin-top` là đúng nhưng không giải quyết overload. Sau parser fix vẫn còn 121 collision UID trong raw M151 inventory và hai false negative thật ở pair này:

- `Navigator.install`
- `Document.parseHTMLUnsafe`

Không nên đưa signature thẳng vào UID rồi coi xong, vì như vậy signature change dễ biến thành remove + add và có thể che parser collision. Cần variant set dưới một stable declaration identity, sau đó compare multiset/signature set.

#### Parse/missing-target completeness

`coverage >= 95%` hiện chỉ nói “đã fetch phần lớn filename candidate”. Nó không nói:

- target được yêu cầu nhưng fetch lỗi;
- extractor exception;
- parser gặp declaration nhưng không hiểu;
- dedupe collapse hai variant;
- file được đọc nhưng extractor trả 0 bất thường.

`meta.missing_targets` và `extract_stats._errors` chưa làm `confirms_absence(kind)` fail closed. Vì vậy một removal vẫn có thể được xác nhận chỉ nhờ file coverage cao dù chính file quan trọng bị thiếu hoặc parse thất bại.

Confidence nên là nhiều cột evidence, không phải một percentage duy nhất:

```text
file_scope_complete
fetch_complete
parse_complete_for_kind
identity_collision_free
comparison_attribute_complete
```

Chỉ khi các cột cần thiết đều đạt mới dùng chữ “confirmed removal”.

### 27.13. Cơ chế score hiện tại, giải thích lại thật ngắn

Đây là đường đi thật của một finding:

```text
Fact cũ + Fact mới
        ↓ match bằng kind:key
Meaningful attribute delta
        ↓ signal
leading signal chọn severity ceiling và bucket
        ↓ policy deductions
not compiled → score 0
unconfirmed removal → -15; một số signal chuyển Housekeeping
        ↓
score cuối 0..100 + reason lines
```

Điểm tốt:

- `leading signal` làm câu giải thích và severity đi cùng nhau;
- score chỉ giảm từ evidence ceiling, không cộng product guess;
- platform-out-of-build về 0;
- per-surface absence tốt hơn global scalar rõ rệt.

Điểm chưa đóng:

- signal chỉ tốt bằng `MEANINGFUL_ATTRS`; implicit ordinal và enclosing guard đang không qua cửa này;
- generic Mojo `attrs` làm signal sai nghĩa;
- coverage row đang first-match biased;
- fetch/parse error chưa hạ confidence;
- score 80 vẫn chỉ là heuristic priority, không phải “80% khả năng break”.

Tách severity và confidence thành hai cột vẫn là hướng đúng. Không nhân chúng với product relevance; product relevance nên để `unknown` trong core và chỉ được downstream evidence của SB-AXon điền.

### 27.14. Release-gate verdict và thứ tự sửa mới

#### P0 — correctness trước khi thêm surface mới

1. Model implicit ordinal cho method và field; giữ explicit/implicit provenance, lexical index và `[Stable]` evidence.
2. Compare Mojo effective platform state, nhưng tách own/inherited guard để không tạo duplicate finding.
3. Sửa WebIDL variant identity và khóa hai false negative thật bằng end-to-end tests.
4. Cho missing target, fetch error, extractor error và parser anomaly làm absence confidence fail closed theo kind.

#### P1 — làm coverage và eligibility đúng với tên gọi

5. Đổi candidate map thành `path -> set(surface)`; giữ global total unique.
6. Gộp extractor → fact kinds → coverage surface vào một registry có invariant test.
7. Expose bảng per-surface trong CLI, Markdown và HTML; bỏ câu “wide reads every file”.
8. Ghi rõ auxiliary cross-platform evidence; bổ sung extractor-specific test-only policy hoặc BUILD ownership.

#### P1 — giữ docs/test trung thực

9. Thay optional regex docs test bằng canonical generated measurement fixture chạy trong CI.
10. Sửa toàn bộ active 3.669/8.349, 8.276/8.349, 29.118, 5%/100% và global-44% scoring examples.

#### P2 — hardening

11. Phân loại Mojo attributes theo semantics thay vì generic `attrs`.
12. Làm cache key collision-resistant và Windows-safe.
13. Thêm browser-level security test khi CI có browser runtime; DOM-level regression vẫn giữ.

### 27.15. Verdict cuối cùng sau `8ced148`

Maintainer đúng ở bốn điểm quan trọng:

- họ đã tự nhận và sửa đúng explicit ordinal bug;
- per-surface scoring là hướng đúng và đã sửa 45 Web API removals;
- bare discovery giờ thật sự chạy test;
- URL scheme và duplicate sanitizer issue đã được xử lý nghiêm túc.

Nhưng review mới cũng bắt được đúng pattern mà commit đang cố loại bỏ:

> Comment nói rộng hơn assertion và data model thực tế.

Ba ví dụ cụ thể:

1. “Compare ordinal” mới compare explicit `@N`, chưa compare implicit position.
2. “One eligibility policy” chưa bao gồm platform/auxiliary policy và vẫn lọt test-only naming khác.
3. “Quét mọi con số có nhãn trong mọi tài liệu” chỉ là ba sentence regex cộng bốn bucket labels, lại có thể skip khi `out/report.json` không tồn tại.

Vì vậy đánh giá công bằng nhất là:

> **Commit `8ced148` đóng tốt explicit ordinal, bare discovery và spec-link security; đóng phần scoring decision của per-surface coverage; nhưng chưa đóng process-boundary comparison completeness, coverage membership completeness, documentation correctness contract hay release gate.**

Project vẫn rất đáng tiếp tục. Điểm mạnh nhất của maintainer là chịu đo, ghi rationale trong commit message và chấp nhận rút claim sai. Bước tiếp theo nên dùng chính kỷ luật đó cho implicit ordinal và enclosing guard: fixture nhỏ chứng minh cơ chế, real-version measurement để biết quy mô, rồi mới chọn signal/score.

## 28. Follow-up review commit `b844108` — schema 31

### 28.1. Kết luận ngắn nhất

Hai thay đổi của commit đều có giá trị, nhưng mức độ đóng khác nhau:

| Claim | Kết quả review độc lập | Trạng thái |
|---|---|---|
| Hai WebIDL false negative cụ thể đã xuất hiện | Đúng: `Document.parseHTMLUnsafe` 60/Breaking, `Navigator.install` 25/New | **Fixed ở hai case** |
| Fact giữ “whole overload set” | Có giữ tập signature; chưa giữ attribute, runtime gate, path và line theo từng overload | **Partial** |
| Signal tách đúng theo direction | Chỉ đúng khi representative signature không đổi; xoá overload đứng đầu và đứng cuối cho score khác nhau | **Partial / order-dependent** |
| Thêm overload không thể phá call site cũ | Không đúng tổng quát theo WebIDL overload resolution | **Rationale quá mạnh** |
| Missing target / parse error chặn confirmed absence | Đúng cho whole-fact `REMOVED` ở snapshot mới | **Fixed phần hẹp** |
| Mọi absence-shaped change đều bị chặn | Overload removal là `MODIFIED` nên bypass; snapshot cũ thủng vẫn sinh false addition | **Chưa fixed** |
| Fix làm thay đổi report hiện tại | Overload thêm 2 findings; completeness latch không đổi gì vì mọi error count hiện bằng 0 | **Đúng** |
| 335 test | Chạy đủ trên Python 3.14 và 3.9 | **Verified** |

Verdict release gate vẫn là **chưa đạt**. Commit này đóng hai false negative WebIDL đã biết, nhưng chưa đóng overload contract. Missing-target latch là một safety improvement tốt, song hiện mới che một chiều và một loại change.

### 28.2. Những con số đã được kiểm lại

Baseline:

```text
HEAD             b844108
origin/main      b844108
schema           31
commit history   68 commit
```

Test:

```text
python3 -m unittest discover -q
Ran 335 tests
OK

python3 -m unittest discover -s tests -q
Ran 335 tests
OK

/usr/bin/python3 -m unittest discover -q   # Python 3.9.6
Ran 335 tests
OK
```

Snapshot schema 31 và report thật:

| Target | Facts M148 → M151 | Changes | Breaking | Behaviour | New | Housekeeping | Score 0 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `default` | 28.507 → 29.138 | 3.029 | 283 | 468 | 1.241 | 1.037 | 187 |
| `wide` | 52.367 → 54.298 | 6.071 | 805 | 695 | 2.980 | 1.591 | 441 |

M143, M147, M148 và M151 snapshots có trong cache đều có `missing_targets = 0` và `extract_stats._errors = 0` ở những target đã đo. Vì vậy maintainer nói latch không đổi score hôm nay là đúng.

Đếm WebIDL sau eligibility filter:

```text
M148: 122 member có nhiều hơn một signature
M151: 121 member có nhiều hơn một signature
```

Nếu so full signature set của các member tồn tại ở cả hai phía, 56 member đổi set. Trong đó 54 đã có representative `signature` đổi nên code cũ vốn đã tạo row; hai member có representative giữ nguyên chính là hai false negative đã nêu. Cách diễn đạt này chính xác hơn câu dễ bị hiểu thành “56 trong 121 overload group đều thay đổi”.

Sau schema 31, real diff có bốn row mang delta `signatures`:

- hai row vẫn được gắn `web_api_signature_change` vì representative cũng đổi;
- một `web_api_overload_removed` là `Document.parseHTMLUnsafe`;
- một `web_api_overload_added` là `Navigator.install`.

### 28.3. Phần WebIDL đã sửa đúng điều gì?

Giữ một stable member identity rồi đặt variant set bên trong là hướng đúng hơn việc thêm signature vào UID:

```text
idl_member:Navigator.install
    signatures:
      - install()
      - install(USVString)
      - install(InstallParams)
```

Ưu điểm:

- signature mới không bị biến thành một member mới hoàn toàn;
- mất một overload không bị biến thành xóa cả member;
- partial declarations ở nhiều file vẫn có thể gộp vào cùng member;
- fact count không nổ;
- schema bump 31 là đúng vì serialized Fact đã đổi.

Hai regression test mới chạy qua extract → dedupe → diff → score, nên tốt hơn kiểu test chỉ soi key trên Fact. Hai row thật cũng xuất hiện đúng:

```text
Document.parseHTMLUnsafe  web_api_overload_removed  60  Breaking
Navigator.install        web_api_overload_added    25  New surface
```

Nói gọn: **hai false negative cũ đã được đóng thật**. Các finding bên dưới là về contract rộng hơn, không phủ nhận kết quả này.

### 28.4. Lỗi mới quan trọng nhất: score phụ thuộc overload bị xoá đứng đầu hay đứng cuối

Code hiện kiểm theo thứ tự:

```python
if "signature" in change.deltas:
    web_api_signature_change
elif "signatures" in change.deltas:
    web_api_overload_removed / added
```

`signature` là declaration có `(path, line)` nhỏ nhất. Vì vậy khi overload đầu tiên bị xóa, representative đổi và nhánh generic chạy trước. Khi overload cuối bị xóa, representative giữ nguyên và nhánh overload chạy.

Probe cùng một semantics:

| Case | Old | New | Signal | Score |
|---|---|---|---|---:|
| Xóa overload đứng đầu | `f(long); f(DOMString)` | `f(DOMString)` | `web_api_signature_change` | 50 |
| Xóa overload đứng cuối | `f(long); f(DOMString)` | `f(long)` | `web_api_overload_removed` | 60 |

Trong cả hai case, member mất đúng một argument list. Vị trí source khác nhau không nên quyết định severity hoặc wording.

Real M148 → M151 đã có hai row cùng hình dạng bị giữ ở signal generic 50:

- `GPUQueue.copyElementImageToTexture`: ba overload cũ bị thay bằng một form mới;
- `WebGLRenderingContextBase.texElementImage2D`: bốn overload cũ bị thay bằng một form mới.

Hai row này có cả delta `signature` và `signatures`, nhưng dedicated removal signal không chạy vì `elif`. Vậy implementation mới không thật sự “tách theo direction” cho toàn bộ overload change; nó chỉ gắn signal mới cho case mà representative tình cờ không đổi.

Cách sửa ngắn:

```text
if signatures delta:
    nếu old - new khác rỗng: append overload_removed
    nếu new - old khác rỗng: append overload_added

nếu chỉ signature delta và không có variant-set delta:
    append web_api_signature_change
```

Khi vừa mất vừa thêm, giữ cả hai signal; `leading_signal` tự chọn removal 60 làm headline, addition 25 vẫn còn làm evidence. Cần test permutation: đổi thứ tự declaration không được đổi signal/score.

### 28.5. `signatures: [string]` chưa phải whole variant set

Mỗi overload không chỉ có signature. Nó còn có extended attributes, runtime gate, nơi khai báo và line riêng.

Đo raw M151 trên đúng population sau eligibility:

| Trong 121 overload group | Số group |
|---|---:|
| Các overload có `ext` khác nhau | 42 |
| Các overload có `runtime_enabled` khác nhau | 12 |
| Các overload nằm ở nhiều file | 1 |

Fact sống sót hiện giữ:

```text
signatures = toàn bộ chuỗi signature
ext/runtime_enabled/path/line = chỉ của representative thấp nhất
```

Điều này tạo ba vấn đề.

#### 1. Gate của overload bị mất

Ở M148, hai variant của `Document.parseHTMLUnsafe` là:

```text
line 88  parseHTMLUnsafe(html)
         runtime gate: none

line 92  parseHTMLUnsafe(html, SetHTMLUnsafeOptions)
         runtime gate: SanitizerAPI
```

Variant bị xóa là line 92 có gate riêng. Fact chỉ giữ attrs của line 88, nên scorer không biết gate của thứ vừa mất. Trong pair này `SanitizerAPI` đang stable, vì vậy Breaking vẫn là kết luận hợp lý. Nhưng data model không đủ để đưa ra kết luận đó; nó tình cờ đúng nhờ trạng thái thật của gate bị bỏ mất.

M151 thêm hai variant ở line 92 và 93; một variant phụ thuộc `TrustedTypesCreateParserOptions`, hiện experimental. Row chỉ nói member được modified và không thể phân biệt overload live với overload experimental.

#### 2. Location trỏ vào declaration không đổi

Change `Document.parseHTMLUnsafe` hiện cite:

```text
third_party/blink/renderer/core/dom/document.idl:88
```

Nhưng line 88 là overload không đổi. Thứ bị xóa ở old line 92; hai thứ thêm ở new line 92/93. Người đọc click đúng file nhưng sai declaration.

#### 3. Ví dụ cross-file tự chứng minh cần provenance theo variant

`URL.createObjectURL` trải hai file như commit message nói. Hai overload còn có `Exposed` khác nhau. Gộp ở `dedupe_facts` là đúng nơi, nhưng giữ path/ext của một representative lại làm mất chính thông tin khiến cross-file aggregation cần thiết.

Fact nên mang variant records, không chỉ string set:

```json
"variants": [
  {
    "signature": "...",
    "ext": {"RuntimeEnabled": "..."},
    "runtime_enabled": "...",
    "path": "...",
    "line": 92
  }
]
```

Identity vẫn là một member; snapshot chỉ tăng rất ít vì M151 có 121 group. Diff có thể lấy đúng removed/added variants, đúng gate và đúng line.

### 28.6. “Thêm overload không phá call site nào” là một khẳng định quá mạnh

WebIDL không chọn overload chỉ bằng tên. Nó xây một effective overload set rồi chọn callable dựa trên số lượng và type của JavaScript arguments. Đây là cơ chế trong [Web IDL overload resolution algorithm](https://webidl.spec.whatwg.org/#dfn-overload-resolution-algorithm).

Ví dụ tối giản:

```webidl
// old
undefined f(DOMString value);

// new
undefined f(DOMString value);
undefined f(Node value);
```

Trước đây, một object có thể đi qua conversion sang string và vào overload cũ. Sau khi thêm overload `Node`, một Node object có thể được dispatch sang callable mới. Call site vẫn chạy nhưng không nhất thiết “match overload nó luôn match”.

Đối với `Navigator.install`, variant mới nhận `InstallParams` dictionary bên cạnh các `USVString` variants. Một call cũ truyền object có thể được overload resolver xử lý khác sau khi dictionary variant xuất hiện. Đây là inference từ thuật toán của spec, không phải khẳng định rằng Chromium M151 chắc chắn phá một site cụ thể.

Vì vậy bucket New surface có thể vẫn là policy chấp nhận được, nhưng label/reason nên trung thực hơn:

> “A new argument shape is available; existing calls with values distinguishable as that shape may resolve differently.”

Không nên dùng câu tuyệt đối “every existing call still matches the overload it always did”. Nếu muốn giữ score 25, tài liệu phải nói đây là heuristic, không phải proof of non-breakage.

### 28.7. Signature normalization vẫn tạo false positive

`collapse_ws()` chỉ gom nhiều whitespace thành một; nó không canonicalize khoảng trắng quanh punctuation. M148 → M151 `wide` có **7 WebIDL rows** mà old/new signature chỉ khác whitespace, nhưng mỗi row nhận:

```text
web_api_signature_change
score 50
Breaking
```

Ví dụ:

```text
SubtleCrypto.importKey(
→ SubtleCrypto.importKey(␠
```

Sau khi bỏ whitespace, hai chuỗi giống hệt. Các row khác gồm `deriveBits`, `unwrapKey`, `decapsulateBits`, `decapsulateKey`, `encapsulateBits` và `encapsulateKey`.

Đây là pre-existing parser normalization issue, không phải regression do `b844108`. Nhưng schema 31 dùng chính signature string làm set element, nên vấn đề này giờ ảnh hưởng cả representative comparison lẫn variant-set comparison. Cần canonical token serialization của WebIDL; không nên đơn giản xóa mọi space vì `unsigned long` và identifier boundary vẫn cần được phân biệt.

### 28.8. Absence latch: phần tốt và bốn lỗ còn lại

#### Phần tốt

`cmd_run` giờ lấy `missing_targets` và `extract_stats._errors` của snapshot mới, chuyển thành reason rồi đưa vào `Scope`. Với whole-fact removal:

```text
new snapshot incomplete
        ↓
confirms_absence(kind) = false
        ↓
-15 và reason nói target missing hay file parse failed
```

Đây là fail-closed behavior hợp lý. Test mới chứng minh helper build đúng reason và whole pref removal bị hạ confidence.

#### Lỗ 1 — overload removal là `MODIFIED`, nên bypass hoàn toàn

Điều kiện score hiện là:

```python
if change.change_type == REMOVED and not scope.confirms_absence(...):
```

Mất một overload không xóa member, nên change type là `modified`. Probe:

```text
old: f(long); f(DOMString)
new: f(long)
snapshot mới: 1 file would not parse

result:
  change_type = modified
  signal      = web_api_overload_removed
  score       = 60
  bucket      = Breaking
  unconfirmed reason = none
```

Đây là đúng interaction giữa hai feature mới: variant absence vừa được thêm nhưng safety latch không áp dụng cho nó. Với overload trải nhiều file như `URL.createObjectURL`, mất một partial file có thể tạo đúng hình dạng này.

Confidence phải dựa vào **removal-like semantic delta**, không chỉ top-level `change_type`. Ít nhất `web_api_overload_removed` phải đi qua absence guard. Về lâu dài, enum member/variant-set removal cũng cần cùng abstraction.

#### Lỗ 2 — snapshot cũ thủng vẫn sinh “New surface” chắc chắn

`cmd_run` chỉ gọi:

```text
incomplete = _incomplete_reason(new)
```

Probe:

```text
old snapshot: missing target chứa N.install, nên không có Fact
new snapshot: complete, có N.install

result:
  change_type = added
  signal      = web_api_added_live
  score       = 35
  bucket      = New
  confidence warning = none
```

Presence ở version mới là chắc. Nhưng claim “được thêm giữa hai version” không chắc; nó có thể đã tồn tại trong file old run không đọc. Chính comment cũ trong `snapshot.py` cũng nói missing target là khác biệt giữa “feature was added” và “we never fetched the file declaring it”.

Scope cần hai phía:

```text
REMOVED / removed variant  → hỏi completeness phía new
ADDED / added variant      → hỏi completeness phía old cho claim novelty
MODIFIED value             → hai fact đều có, thường không cần absence check
```

Nếu project cố ý chỉ quan tâm “present in adopted version”, label phải là “observed in new snapshot”, không phải “New surface”.

#### Lỗ 3 — reason đưa advice sai

Dù nguyên nhân là parse error hay target missing, code vẫn nối:

```text
— --target-set wide settles it
```

Probe thật cho ra:

```text
-15 unconfirmed: 1 file(s) that would not parse ...
— --target-set wide settles it
```

Chạy `wide` không sửa parser, không làm target xuất hiện và có thể chính run hiện tại đã là `wide`. Test mới chỉ assert có chữ `would not parse` và không có `of that surface`; nó không assert advice cuối câu. Đây lại là một case comment đúng hơn assertion.

Advice nên phụ thuộc reason:

- coverage gap + target hiện chưa wide: đề nghị wide;
- parse error: in file/extractor bị lỗi và yêu cầu fix parser;
- missing target: xác minh tree listing/path migration;
- đã wide: không đề nghị chạy lại đúng command.

#### Lỗ 4 — `_errors = 0` chưa có nghĩa là parse complete

WebIDL extractor tự mô tả rằng nó bỏ qua syntax không hiểu thay vì fail file. Những silent skips đó không tăng `_errors`. Ngoài ra `_errors` đang là global count: một WebUI extractor exception sẽ làm mọi WebIDL/Mojo removal mất confirmation, dù per-surface coverage vừa được xây để tránh đúng kiểu trộn surface đó.

Một release-grade completeness model cần ít nhất:

```text
from/to side
surface hoặc extractor
missing target paths
fetch failures
extractor exceptions
parser warnings / unmatched candidate declarations
variant/identity collisions
```

Nếu muốn fail closed toàn report khi bất kỳ lỗi nào xảy ra, nên đặt một banner `comparison incomplete` ở đầu report. Trừ 15 âm thầm trên từng whole removal không thay thế được release validity status.

### 28.9. Documentation lại chứng minh test chưa quét “mọi con số”

Commit sửa đúng bucket headline 282 → 283, New 1.240 → 1.241 và test count 327 → 335. Nhưng 335 test vẫn pass khi các active số khác mâu thuẫn:

| Nơi | Đang ghi | Schema 31 thực tế |
|---|---:|---:|
| README cold/warm run story | 3.027 changes | 3.029 |
| README owner table — Web platform | 724 | 726 |
| Tổng owner table README | 3.027 | 3.029 |
| `reference/signals.md` denominator | 3.027 | 3.029 |
| README/pipeline/skill coverage | vẫn dùng 3.669/8.349 và 8.276/8.349 | 3.677/8.366 và 8.295/8.366 |

`out/report.json` schema 31 có `by_owner.webplatform = 726`, nên đây không phải chênh do cách nhóm. Hai overload findings đều thuộc Web platform; table chỉ chưa được cập nhật.

Nguyên nhân vẫn như mục 27.9:

- docs test chỉ match ba sentence pattern và bốn bucket labels;
- `out/report.json` bị ignore và test có thể skip trên fresh checkout;
- owner/fact/coverage/performance totals không nằm trong contract.

Commit này tự tạo thêm ví dụ đúng cho nhận xét “suite chứng minh phần matcher biết nhìn, không chứng minh toàn tài liệu đúng”. Canonical generated figures vẫn là fix cần thiết.

### 28.10. Các blocker cũ thay đổi ra sao?

| Finding trước | Sau `b844108` |
|---|---|
| Hai WebIDL silent cases | **Đóng** |
| WebIDL variant contract đầy đủ | **Chưa**: order, attrs, gate, location và overload-resolution semantics |
| Missing target / extractor error không ảnh hưởng confidence | **Đóng một phần** cho whole removal phía new |
| Implicit Mojo method ordinal | Không đổi: 503 position changes, 485 không có row |
| Implicit Mojo field ordinal | Không đổi: 607 position changes, 602 không có row |
| Enclosing Mojo build guard | Không đổi: synthetic `not_compiled → compiled` vẫn diff rỗng |
| Per-surface candidate first-match | Không đổi: 378 multi-surface paths |
| Per-surface coverage không in trong normal report | Không đổi |
| Mojo semantic attrs / `AllowedContext` mislabel | Không đổi |
| 17 obvious test-only Mojo facts | Không đổi |
| Cache key `.` / collision / Windows reserved names | Không đổi |

Vì vậy `b844108` giảm WebIDL false-negative risk, nhưng process-boundary comparison completeness vẫn là blocker lớn nhất.

### 28.11. Thứ tự sửa sau schema 31

#### P0 — đóng đúng overload contract

1. Đổi `signatures` thành variant records có signature, ext, runtime gate, path và line.
2. Tính added/removed variant độc lập với representative; giữ cả hai signal khi set vừa mất vừa thêm.
3. Thêm permutation test: xoá overload đầu/cuối phải cho cùng signal và score.
4. Test gated overload và cross-file overload; report phải cite đúng declaration line.
5. Đổi wording overload addition để không hứa existing dispatch không đổi.

#### P0 — làm completeness directional và semantic

6. Scope giữ `from` và `to` completeness.
7. Áp dụng confidence cho removal-like deltas như `web_api_overload_removed`, không chỉ `change_type == removed`.
8. Old-side hole phải hạ confidence của claim `added/new` hoặc đổi label thành “newly observed”.
9. Bỏ advice `wide settles it` khi nguyên nhân là parse/missing target hoặc run đã wide.
10. Lưu errors theo extractor/surface; thêm parser anomaly counters.

#### P0 còn lại từ vòng trước

11. Model implicit Mojo ordinal và `[Stable]`/GN evidence.
12. Compare enclosing Mojo guard với own/inherited provenance.

#### P1

13. Canonicalize WebIDL tokens để loại 7 whitespace-only Breaking rows.
14. Sửa multi-surface coverage membership và expose bảng trong report.
15. Generate docs figures từ một canonical artifact chạy trong CI.

### 28.12. Phản biện trực tiếp nhận định của maintainer

#### “Overload là lỗi thật nhưng không phải blocker”

Nếu câu này chỉ nói hai silent rows của M148 → M151 thì tôi đồng ý về blast radius: commit đã thêm đúng 2 / 3.029 findings, trong đó một Breaking.

Nếu câu này nói overload model đã đủ an toàn thì chưa. Hai probe mới chứng minh:

- cùng một overload removal có thể được 50 hoặc 60 tùy source order;
- 42 / 121 overload groups có variant attrs khác nhau, nhưng fact không giữ mapping;
- incomplete snapshot không hạ confidence của overload removal vì nó là `modified`;
- addition có thể đổi overload dispatch của một existing call.

Do đó overload không phải blocker lớn nhất của toàn project, nhưng implementation schema 31 vẫn là **partial correctness fix**, chưa phải closed contract.

#### “missing_targets chưa từng là lỗi, chỉ là chốt”

Đồng ý về dữ liệu hiện tại: mọi measured run đều bằng 0, nên không có current finding nào đổi vì latch.

Không đồng ý rằng chốt đã đóng đủ. Nó chỉ nhìn snapshot mới, chỉ chạy cho whole removal và còn đưa advice sai. Cách gọi chính xác là:

> “Đã thêm fail-closed latch cho whole-fact removals khi new snapshot báo hard extraction incompleteness.”

Đó là improvement tốt, nhưng hẹp hơn “absence needs more than coverage” nói chung.

#### Verdict

> **`b844108` sửa thật hai WebIDL false negatives và thêm một new-side whole-removal safety latch. Nó chưa đóng overload variant semantics hoặc bidirectional/semantic absence confidence. Release-gate verdict vẫn là chưa đạt.**

## 29. Follow-up review commits `5edc91e` và `a88f5fc` — schema 33

### 29.1. Kết luận ngắn nhất

Hai commit tiếp tục sửa đúng nhiều lỗi thật, nhưng câu “mọi thứ trong danh sách giờ đã đóng hoặc có lý do đo được” vẫn quá sớm.

| Claim của maintainer | Kết quả kiểm chứng độc lập | Trạng thái |
|---|---|---|
| Overload removal không còn phụ thuộc representative | Probe cũ 50/60 giờ đều 60 | **Fixed đúng lỗi gốc** |
| Same declared arity có thể shadow call cũ | Đúng với `Navigator.install` | **Fixed case hiện tại** |
| New declared arity không thể nhận call cũ | Sai: extra arguments bị bỏ qua; optional/variadic tạo nhiều effective arity | **Policy mới sai** |
| Bảy whitespace-only Breaking rows đã mất | Đúng: 7 → 0, Breaking 283 → 276 | **Fixed current pair** |
| Normalization mới chỉ bỏ formatting | Sai: nó rewrite cả string literal/default và có thể nuốt semantic change | **Regression mới** |
| Completeness đã được latch cả hai direction | Có `from_incomplete`, nhưng direction bị trộn; old coverage vẫn không tồn tại; false New label còn nguyên | **Partial** |
| `platform_state` đã qua comparison ở những kind cần nó | Cả 10 kind hiện mang thuộc tính này đều được compare | **Fixed mechanism** |
| Fix đó làm 14 finding vô hình xuất hiện | Không: real pair thêm 0 row; “14” là tổng build-gate rows vốn đã tồn tại | **Claim số liệu sai** |
| Reviewer sai về Mojo ordinal | Audit nói rõ implicit ordinal; explicit đã được công nhận fixed | **Phản bác sai claim** |
| Số đo ordinal là 1.460 interface / 50 interface shift | Snapshot cho 1.396 common interface facts, 1.357 method-bearing common interfaces và 48 interface shift | **Không tái hiện được** |
| Per-overload runtime gate đã được giữ | Probe gate của non-representative giờ sinh `web_api_exposure_changed` | **Fixed** |
| Variant issue cuối cùng đã đóng | Per-overload extended attributes và provenance vẫn mất; synthetic attr change vẫn diff rỗng | **Chưa đóng** |
| README issue chỉ là schema 27/28 trong changelog | Audit chưa từng phê bình hai nhãn đó; active counts/coverage/owner table vẫn stale | **Phản bác lệch vấn đề** |
| 340 test | Bare/explicit discovery đều chạy đủ trên Python 3.14 và 3.9 | **Verified** |

Verdict vẫn là **chưa đạt release gate**. Điểm đáng ghi nhận là maintainer tiếp tục kiểm chứng và sửa nhanh. Điểm cần siết lại là phân biệt ba câu khác nhau:

1. code đã mang thêm evidence;
2. current M148 → M151 report có thêm row;
3. correctness contract đã đóng.

Ba câu đó không tự động đồng nghĩa.

### 29.2. Baseline và số liệu đã chạy lại

```text
HEAD             a88f5fc
origin/main      a88f5fc
schema           33
commit history   70 commit
working tree     clean trước khi cập nhật audit
```

Test:

```text
Python 3.14.6  python3 -m unittest discover -q
Ran 340 tests — OK

Python 3.14.6  python3 -m unittest discover -s tests -q
Ran 340 tests — OK

Python 3.9.6   /usr/bin/python3 -m unittest discover -q
Ran 340 tests — OK
```

Snapshot và report schema 33:

| Target | Facts M148 → M151 | Changes | Breaking | Behaviour | New | Housekeeping | Score 0 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `default` | 28.507 → 29.138 | 3.022 | 276 | 469 | 1.240 | 1.037 | 187 |
| `wide` | 52.367 → 54.298 | 6.064 | 798 | 696 | 2.979 | 1.591 | 441 |

Coverage M151 không đổi:

```text
default  3.677 / 8.366
wide     8.295 / 8.366
```

Schema 33 default owner totals thật:

```text
ipc             339
webplatform     719
native        1.157
webui           277
config          530
```

### 29.3. Order-dependent 50/60 đã sửa, nhưng overload model lại có một threshold bug

Phần đúng trước: nhánh `signatures` không còn là `elif` của `signature`. Với member đã có nhiều overload ở cả hai phía, removal signal được phát dù representative signature cũng đổi. Hai real rows trước đây là generic 50 giờ có dedicated removal 60:

- `GPUQueue.copyElementImageToTexture`;
- `WebGLRenderingContextBase.texElementImage2D`.

Original probe “xóa overload đầu hay cuối” giờ đều có `web_api_overload_removed` và score 60. Lỗi order dependence nêu ở mục 28.4 đã đóng.

Nhưng `signatures` chỉ được ghi khi member có **nhiều hơn một** signature. Transition 1 → 2 có shape:

```text
old.signature   = f(DOMString)
old.signatures  = absent

new.signature   = f(DOMString)
new.signatures  = [f(DOMString), f(Node)]
```

`_overload_signals()` chỉ nhận delta `signatures`, nên nó thấy before là empty set. Nó không biết `f(DOMString)` đã tồn tại ở old snapshot.

Probe:

```webidl
// old
void f(DOMString x);

// new
void f(DOMString x);
void f(Node x);
```

Kết quả schema 33:

```text
signal  web_api_overload_added
score   25
bucket  New surface
```

Đây chính là same-arity shadowing mà signal 45 được tạo để bắt. Test mới không thấy vì fixture `ONE` đã có hai overload trước khi thêm overload thứ ba.

Fact nên luôn mang canonical variant set, kể cả singleton. Nếu không muốn serialized shape đổi với mọi member, diff ít nhất phải reconstruct singleton set từ `signature` khi `signatures` absent.

### 29.4. Declared arity không phải effective overload set

`_arity()` chỉ đếm parameter viết trong signature. WebIDL không vận hành đơn giản như vậy.

[Web IDL Standard](https://webidl.spec.whatwg.org/#dfn-effective-overload-set) tạo **effective overload set**; optional và variadic arguments làm một declaration có nhiều argument-count shape. Thuật toán resolution còn nói rõ: nếu JavaScript truyền nhiều argument hơn overload dài nhất, các trailing arguments bị bỏ qua trước khi chọn overload.

Điều đó bác trực tiếp comment của test mới:

> “No existing call can reach it, because resolution counts first.”

Ví dụ không cần optional:

```webidl
// old
void f(DOMString x);

// new
void f(DOMString x);
void f(DOMString x, Node y);
```

Call site cũ `f("x", node)` vẫn gọi được old API; argument thứ hai bị bỏ qua. Sau khi overload hai parameter xuất hiện, cùng call site có thể đi vào callable mới. Vậy “new argument count” không chứng minh non-breaking behavior.

Ba probe khác đều bị chấm 25/New:

| Old | Overload thêm | Vì sao có overlap thật |
|---|---|---|
| `f(DOMString, optional DOMString)` | `f(Node)` | old declaration nhận cả một và hai argument |
| `f(DOMString)` | `f(Node, optional long)` | new declaration nhận cả một và hai argument |
| `f(DOMString...)` | `f(Node, Node)` | variadic old declaration nhận hai argument |

Đo thêm trên toàn bộ cache M130/M136/M139/M143/M147/M148/M151:

- bốn singleton → overload-set additions có same declared arity nhưng threshold bug chấm 25 thay vì 45: hai ở M136 → M139 và hai ở M143 → M147;
- `Document.write` và `Document.writeln` ở M130 → M136 có effective-arity overlap do variadic, nhưng declared-count heuristic không thấy.

M148 → M151 chỉ có một pure overload addition là `Navigator.install`; old side đã có ba signatures nên current pair tình cờ được phân loại đúng 45. Điều này giải thích vì sao bucket hiện tại đúng mà contract tổng quát vẫn sai.

Hướng an toàn:

- hoặc coi mọi overload addition là ít nhất Behaviour change;
- hoặc implement effective argument-count ranges, optional/variadic và extra-argument behavior;
- không gọi một branch “safe” chỉ từ declared parameter count.

### 29.5. Whitespace fix loại đúng bảy false positive nhưng tạo false negative mới

Phần đo current pair là đúng:

```text
whitespace-only signature rows   7 → 0
Breaking                       283 → 276
```

Nhưng `_normalize_signature()` dùng global `str.replace()` quanh `(`, `)`, comma, `<`, `>`. Nó không biết token đang nằm trong type syntax hay string literal.

Probe:

```webidl
// old
void f(optional DOMString x = "a,b");

// new
void f(optional DOMString x = "a, b");
```

Đây là hai default string khác nhau. Schema 33 trả:

```text
NO CHANGE
```

Vì normalizer đổi cả hai thành cùng chuỗi. Tương tự, space sau `(` nằm bên trong quoted default cũng có thể bị xóa. Fix formatting vì thế đã đổi từ bảy false positives hiện tại thành một class false negative mới.

Không có test mới cho normalization trong `5edc91e`. Cần token-aware canonicalization giữ nguyên string/escape/comment tokens, chỉ chuẩn hóa whitespace giữa syntax tokens.

### 29.6. Directional completeness vẫn chưa directional thật

`cmd_run` giờ truyền cả:

```text
incomplete       = lỗi hard của new snapshot
from_incomplete  = lỗi hard của old snapshot
```

Đó là bước đúng. Nhưng `Scope.confirms_absence()` trả false nếu **một trong hai** khác rỗng, bất kể finding đang dựa vào absence phía nào.

Các probe schema 33:

| Change | Hole đặt ở đâu | Kết quả hiện tại | Vấn đề |
|---|---|---|---|
| Whole removal | old only | 35 → 20 | old hole không làm new-side absence kém chắc |
| Overload removal | old only | 60 → 45 | cùng lỗi direction |
| Overload addition | new only | 25 → 10 | presence mới đã quan sát được; novelty hỏi old side |
| Whole addition | old only | score bị trừ nhưng bucket vẫn `New` | vẫn tuyên bố novelty trong chính bucket name |

Ngoài ra:

1. Scope chỉ lưu per-surface coverage của `to`; old-side 1% coverage không thể được biểu diễn.
2. Mọi delta `signatures` đều bị coi là cùng một absence shape; code không tách added variants khỏi removed variants.
3. Khi cả hai phía lỗi, reason chỉ lấy `new or old`, nên một phía bị mất khỏi lời giải thích.
4. Class docstring vẫn tuyên bố “Only the new side matters, and only for removals”, trái với code mới.

Với old hard hole, một added Web API vẫn được label “Web API added” và nằm trong bucket New; chỉ score thấp hơn. Vậy latch chưa chặn false novelty, nó chỉ hạ thứ tự đọc.

Không có test nào chứa `from_incomplete`. `5edc91e` chỉ thêm hai overload tests; completeness, normalization và platform-state changes không có regression test mới.

Model đúng cần API theo direction, ví dụ:

```text
scope.confirms_absence(side="to", kind=...)    # removal
scope.confirms_absence(side="from", kind=...)  # novelty
```

Với variant set, diff phải truyền rõ `removed_variants` và `added_variants`, không suy direction từ việc key `signatures` có delta.

### 29.7. `platform_state`: code fix đúng, nhưng “14 finding mới” là phép đếm sai

Schema 33 M151 có `platform_state` trên đúng mười kind:

```text
base_feature, feature_param,
mojo_interface, mojo_method, mojo_struct, mojo_field, mojo_enum,
pref, switch, webui_control
```

Trước commit, ba kind được compare; commit thêm bảy kind còn lại. Vì vậy mechanism hiện đã nối đủ mọi kind thực tế đang mang `platform_state`. Đây là fix đúng.

Nhưng yield trên M148 → M151 không phải 14 finding mới:

| Target | Rows trước/sau khi bỏ bảy attr mới khỏi `MEANINGFUL_ATTRS` | New rows | Existing rows đổi signal/bucket |
|---|---:|---:|---:|
| `default` | 3.022 / 3.022 | 0 | 0 |
| `wide` | 6.064 / 6.064 | 0 | 0 |

Ở `wide`, đúng một existing Mojo row nhận thêm `platform_state` delta:

```text
optimization_guide.mojom.ModelBroker.AddModelDownloadProgressObserver
```

Row này vốn đã có `signature`, `params`, `attrs` delta và `ipc_signature_change` 80; score, bucket và signal không đổi.

Con số 14 là tổng `build_gate_changed` findings trong default report hiện tại:

- 12 `webui_control` đã có `build_conditions` delta;
- 2 `base_feature` đã có `conditions` delta.

Cả 14 đều đã hiện trước platform-state patch. Tổng report xác nhận điều đó: schema 31 có 3.029 rows, bỏ bảy whitespace rows còn đúng 3.022; không có cộng 14 ở giữa.

Cách ghi chính xác:

> “Nối comparison cho bảy kind còn lại; measured yield trên pair này là 0 new rows, 1 existing row có thêm evidence.”

Đây vẫn là mechanism fix đáng giữ, giống completeness latch và overload gate. Nhưng gọi 14 rows là “previously invisible” làm sai provenance của chính phép đo.

### 29.8. `overload_gates` sửa đúng gate; extended attributes vẫn mất

Đo raw WebIDL lại cho kết quả giống commit message:

```text
M151 overload groups                 121
groups khác runtime gate              12
groups khác extended attributes       42
full (signature, gate, ext) tuple
  đổi nhưng signature set giữ nguyên  53
schema 32 đã có row                    53
schema 32 silent                        0
```

Kết luận “current yield bằng 0” đúng. Giải thích trong commit body lại chưa chính xác: cả 53 rows đã hiện vì representative `ext` đổi; 19 trong số đó đồng thời có representative `runtime_enabled` đổi. Không row nào cần “bare signature set moved”, vì population này được định nghĩa là signature set không đổi.

Phần code của `a88f5fc` hoạt động đúng với runtime gate:

- fact mang mapping `signature [gate]` khi overloads bất đồng gate;
- gate của non-representative đổi sinh `overload_gates` delta;
- signal là `web_api_exposure_changed` 45/Behaviour;
- không giả thành `web_api_overload_removed` 60;
- M148 → M151 chỉ có một `overload_gates` delta, trên `Document.parseHTMLUnsafe`, nên buckets không đổi như dự đoán.

Nhưng commit không lưu per-overload `ext`. Probe:

```webidl
// old
void f(long x);
void f(double x);

// new
void f(long x);
[SecureContext] void f(double x);
```

Representative là overload đầu, signatures không đổi, runtime gates đều rỗng. Schema 33 trả:

```text
NO CHANGE
```

Đây là cùng “two doors” bug, chỉ đổi `RuntimeEnabled` thành một extended attribute khác. WebIDL định nghĩa extended attributes là annotations điều khiển cách bindings xử lý definition/member; tool cũng đã coi representative `ext` change là `web_api_exposure_changed`. Vì vậy giữ gate mà bỏ 42-group attribute dimension chưa đóng variant contract.

Location cũng không chỉ luôn “cách vài dòng”. Đo 120 same-file groups:

```text
median span       2 dòng
p75               5 dòng
15 groups        >10 dòng
7 groups         >25 dòng
2 groups        131 dòng
```

`Document.createElement` và `createElementNS` trải 131 dòng. `URL.createObjectURL` còn ở hai file. Same-file 120/121 là đúng, nhưng categorical claim “right file and within a few lines” không đúng cho toàn bộ population.

Fact variant đúng nên là structured records:

```json
{
  "signature": "...",
  "runtime_enabled": "...",
  "ext": {"...": "..."},
  "path": "...",
  "line": 92
}
```

### 29.9. Phản bác Mojo ordinal không trúng claim, và bỏ quên field ordinal

Audit ở mục 27 đã viết rõ:

> “Compare ordinal mới compare explicit `@N`, chưa compare implicit position.”

Nó còn có fixture `Bar(); Foo();` → `Foo(); Bar();`, bảng method/field riêng và đã công nhận `Foo@0 → Foo@1` fixed từ schema 30. Vì vậy chạy lại explicit ordinal không bác finding nào của reviewer.

Đo độc lập schema 33 `wide`:

| Measurement | Kết quả |
|---|---:|
| `mojo_interface` facts M148 | 1.407 |
| `mojo_interface` facts M151 | 1.479 |
| Interface fact tồn tại ở cả hai | 1.396 |
| Interface có method ở cả hai | 1.357 |
| M151 methods | 6.012 |
| Explicit `@N` methods | 196 |
| Implicit methods đổi lexical index | 503 |
| Interface chứa các shift đó | 48 |
| Common methods thực sự reorder | 0 |
| Explicit ordinal đổi value | 0 |

Hai con số cuối của maintainer là đúng; `1.460 common interfaces` và `50 shifted interfaces` thì không tái hiện được từ snapshot mà report dùng. Con số audit cũ 503/48 vẫn khớp.

Về policy, ghi trap 13 tốt hơn để hazard im lặng. Nhưng trap không biến hazard thành fixed. [Mojom IDL documentation](https://chromium.googlesource.com/chromium/src/+/master/mojo/public/tools/bindings/README.md#Versioning) nói implicit ordinal được gán theo lexical position và existing ordinal phải giữ nguyên để backward-compatible. [Bindings generator](https://chromium.googlesource.com/chromium/src/+/master/mojo/public/tools/bindings/mojom_bindings_generator.py) cũng đi qua method order khi tạo scrambled ordinal cho method không explicit.

Lập luận “hai đầu cùng build một tree” đúng cho stock same-version process pair. Nhưng trap 10 và score 80 của chính project giữ Mojo changes vì separately shipped, part-updated hoặc out-of-tree peer. Nếu lý do đó đủ để báo signature change, nó cũng là lý do cần giữ evidence cho implicit wire-ID shift. Có thể không nên cho cả 503 rows score 80; giải pháp là model `[Stable]`, `MinVersion`, explicit/implicit provenance và hiển thị một confidence/risk tier riêng — không phải xóa evidence.

Quan trọng hơn, phản hồi chỉ nói **method** và bỏ hẳn field finding:

| Field measurement M148 → M151 | Kết quả |
|---|---:|
| M151 fields | 13.015 |
| Explicit ordinal fields | 121 |
| Implicit fields đổi lexical index | 607 |
| Struct/union containers bị ảnh hưởng | 72 |
| Shifted fields không có diff row | 602 |

Mojom docs đặc biệt yêu cầu new fields được append và existing field ordinal không đổi trong versioned structs. Trap 13 không nhắc field, nên câu “mọi thứ trong danh sách đã đóng hoặc có reason” chưa đúng ngay cả theo chiến lược document-only.

### 29.10. Phản bác documentation đã trả lời nhầm vấn đề

Đúng: `schema 27` và `schema 28` trong bảng “Chromium says this in three different ways” là lịch sử capability, không phải current schema number. Audit không yêu cầu sửa chúng.

Finding ở mục 28.9 là **active figures**. Sau schema 33 chúng vẫn sai:

| Active document figure | Đang ghi | Schema 33 thật |
|---|---:|---:|
| README warm-run changes | 3.027 | 3.022 |
| README/pipeline default coverage | 3.669 / 8.349 | 3.677 / 8.366 |
| README/pipeline wide coverage | 8.276 / 8.349 | 8.295 / 8.366 |
| README/pipeline Web platform owner | 724 | 719 |
| README/pipeline Browser C++ owner | 1.386 | 1.157 |
| README/pipeline Outside repository owner | 301 | 530 |
| `signals.md` no-signal fraction | 971 / 3.027 | 981 / 3.022 |

Owner table hiện vẫn cộng thành 3.027, nên đây rõ ràng là snapshot figure cũ chứ không phải changelog. Bucket headlines và `187 / 3.022` đã được cập nhật đúng; những con số matcher biết nhìn xanh, các con số ngoài matcher vẫn cũ.

340 tests vẫn pass vì docs contract chỉ quét ba sentence patterns và bốn bucket labels; owner, total-story, coverage và no-signal ratio không nằm trong assertion. Test còn có thể skip nếu `out/report.json` không tồn tại trên fresh checkout.

Vì vậy documentation finding được giữ nguyên. Phản hồi “schema 27/28 là changelog” là một phản bác đúng với một claim reviewer không đưa ra.

### 29.11. Chất lượng năm test mới

`5edc91e` tăng 335 → 337 bằng hai tests:

1. same-arity `Navigator.install`;
2. removal có representative đổi vẫn score 60.

`a88f5fc` tăng 337 → 340 bằng ba gate tests:

1. non-representative runtime gate change visible;
2. gate change không thành overload removal;
3. overloads cùng gate không mang list thừa.

Các gate tests chạy end-to-end và khóa đúng mechanism. Hai tests của `5edc91e` cũng có giá trị, nhưng có hai lỗ:

- “verdict does not depend on which copy survived” không phải permutation test: case thứ hai vừa mất hai signatures vừa thêm signature mới, không phải cùng semantic event đổi declaration order;
- same-arity test bắt đầu với một member đã có hai overload, nên không chạm threshold 1 → 2.

Không test mới nào khóa:

- seven whitespace-only rows hoặc string-literal preservation;
- `from_incomplete` và direction matrix;
- `platform_state` trên một trong bảy kind mới;
- old-side per-surface coverage;
- optional/variadic/extra-argument overload behavior;
- non-runtime extended attributes theo overload;
- implicit Mojo field ordinal.

Vì vậy 340 pass vẫn là internal consistency cho population test đã chọn, chưa phải correctness contract của năm thay đổi được tuyên bố.

### 29.12. Thứ tự sửa sau schema 33 và verdict

#### P0 — WebIDL overload model

1. Luôn reconstruct full old/new variant set kể cả singleton.
2. Bỏ kết luận “new declared arity is safe”; hoặc mọi addition là Behaviour, hoặc implement effective overload set đúng spec.
3. Variant record phải mang signature, runtime gate, full ext, path và line.
4. Token-aware normalization không rewrite string/default literal.
5. Thêm tests cho singleton → two, optional, variadic, extra trailing args, permutation và quoted defaults.

#### P0 — completeness

6. Lưu `from` và `to` coverage/errors theo surface.
7. Hỏi đúng side cho whole/variant addition và removal.
8. Không giữ label/bucket “New” chắc chắn khi old-side absence chưa confirmed.
9. Test ma trận old-hole/new-hole × added/removed/variant-added/variant-removed.

#### P0 — process-boundary completeness

10. Lưu implicit lexical index cho method và field.
11. Lưu container `[Stable]`, `MinVersion` và provenance để phân tier thay vì gán 80 đồng loạt.
12. Đóng enclosing guard với own/inherited provenance.

#### P1

13. Generate toàn bộ measured documentation figures từ canonical report artifact.
14. Giữ docs contract chạy được trên fresh checkout thay vì optional `out/report.json`.
15. Sửa per-surface first-match membership và expose bảng trong normal report.

#### Verdict cuối

> **`5edc91e` sửa thật order-dependent removal, bảy current whitespace false positives, same-arity `Navigator.install` và platform-state comparison mechanism. `a88f5fc` sửa thật per-overload runtime gate. Nhưng declared-arity policy mới không đúng WebIDL, normalization mới có false negative, completeness direction vẫn trộn, extended attributes/provenance chưa được giữ, implicit field ordinal chưa được trả lời, và phản bác documentation nhắm sai claim. Danh sách chưa đóng; release-gate verdict vẫn là chưa đạt.**

## 30. Review cuối chuỗi `cd1ee05` → `3f28ac8` → `0a9638e` → `0933dcd` — schema 37

### 30.1. Kết luận ngắn nhất

Chuỗi bốn commit này **sửa thật nhiều mục**. Sau khi chủ dự án làm rõ mục tiêu là cảnh báo sớm một phần, không phải automated release gate hay coverage 100%, verdict cần được đặt lại:

> **Schema 37 đạt mục tiêu hiện tại: phát hiện sớm một tập thay đổi hữu ích, xếp chúng để con người kiểm tra và giữ evidence truy vết được.**

Câu “xong hết danh sách” vẫn chưa chính xác, vì full version matrix tìm ra một regression thật trên M143 → M147. Nhưng regression này là backlog cải thiện precision của radar; nó không làm toàn bộ công cụ mất giá trị hay không đạt mục tiêu sản phẩm.

| Claim của maintainer | Kiểm chứng độc lập | Trạng thái |
|---|---|---|
| Singleton → overload set đã so đúng | Old singleton signature được reconstruct; same-arity addition đi 45/Behaviour | **Fixed** |
| Optional và extra-argument behavior đã xử lý | Các fixture mới đúng; long overload không còn bị gọi là safe | **Fixed phần chính** |
| Whitespace normalizer không viết lại literal | Literal đơn giản đã giữ nguyên | **Fixed case đã nêu; escaped quote còn hở** |
| Per-overload extended attributes được giữ | `overload_traits` mang signature + gate + ext; probe non-representative ext có row | **Fixed** |
| Directional hard-hole matrix | 16 tổ hợp whole/variant × old/new/both/no-hole chạy đúng trong `Scope` | **Fixed ở unit API** |
| Pipeline dùng coverage đúng hai phía | `cmd_run` vẫn tạo `Scope({"to": ...})`, không truyền old coverage | **Chưa wired** |
| Bucket New không còn khẳng định khi old snapshot thủng | Đúng với hard missing/parse hole; partial old coverage vẫn bị bỏ qua | **Partial** |
| `[Stable]`/`MinVersion` đã thành tier đúng | Stable transition tạo 164 child Breaking rows giả trên real M143 → M147; method MinVersion chưa có field riêng | **High-priority precision bug** |
| Own/inherited guard provenance đã đóng | Chỉ method/field giữ `inherited_conditions`; child fan-out, nested container vẫn silent | **Chưa đóng** |
| Per-surface first-match đã xử lý | Code vẫn `continue` ở claimant thứ hai và ghi “under the first” | **Không sửa, chỉ công khai policy** |
| Mọi số tài liệu sinh từ artifact | Artifact hiện đúng cho selected figures; nhiều active figures ngoài artifact, clean checkout vẫn skip report oracle | **Partial** |
| Row trỏ tới mọi overload | JSON giữ đủ; Markdown/HTML cắt tối đa ba | **Partial ở data, chưa xong ở output** |
| 360 test pass | Python 3.14 và 3.9 đều 360/360 | **Verified, nhưng không bắt interaction** |

Verdict:

> **Chấp nhận schema 37 cho early warning/manual triage. Không chấp nhận claim hẹp hơn rằng mọi backlog correctness đã đóng. Stable transition, novelty confidence và guard aggregation nên được cải thiện; parser grammar còn thiếu là known scope, không phải blocker nếu tài liệu nói rõ.**

### 30.2. Baseline, test và full real-version matrix

Baseline:

```text
HEAD / origin/main   0933dcd
schema               37
commit history       74 / 74 commit
working tree         clean trước khi cập nhật audit
```

Test:

```text
Python 3.14.6  python3 -m unittest discover -q
Ran 360 tests — OK

Python 3.9.6   /usr/bin/python3 -m unittest discover -q
Ran 360 tests — OK
```

Tôi rebuild schema 37 cho M143 và M147, gồm cả `wide`, rồi chạy ba adjacent pairs thay vì chỉ M148 → M151.

#### Default

| Pair | Facts | Changes | Breaking | Behaviour | New | Housekeeping | Score 0 | Coverage phía `to` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| M143 → M147 | 28.133 → 28.531 | 4.023 | 339 | 923 | 1.426 | 1.335 | 189 | 3.578 / 8.019 |
| M147 → M148 | 28.531 → 28.507 | 1.273 | 79 | 252 | 434 | 508 | 159 | 3.605 / 8.094 |
| M148 → M151 | 28.507 → 29.138 | 3.022 | 276 | 469 | 1.240 | 1.037 | 187 | 3.677 / 8.366 |

#### Wide

| Pair | Facts | Changes | Breaking | Behaviour | New | Housekeeping | Score 0 | Coverage phía `to` |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| M143 → M147 | 50.535 → 52.030 | 8.045 | 1.330 | 1.266 | 3.278 | 2.171 | 517 | 7.949 / 8.019 |
| M147 → M148 | 52.030 → 52.367 | 2.250 | 276 | 330 | 966 | 678 | 245 | 8.024 / 8.094 |
| M148 → M151 | 52.367 → 54.298 | 6.064 | 798 | 696 | 2.979 | 1.591 | 441 | 8.295 / 8.366 |

Mọi snapshot trên có:

```text
missing_targets = 0
extract_stats._errors = 0
```

Current M148 → M151 count/buckets do tái hiện đúng commit message. `docs/figures.json` cũng bằng byte-level data structure với artifact sinh lại từ default report và wide report thật. Vấn đề nằm ở interaction trên pair khác và ở population extractor không model, không phải current headline bị cộng sai.

### 30.3. Những gì bốn commit đã sửa đúng

Phần này cần ghi rõ để không biến review thành “cứ sửa gì cũng bị bác”.

1. **Singleton → two overload.** `signatures` phía old có thể là `None`, nhưng signal code reconstruct từ `old_fact.signature`. Case một parameter string + một parameter object giờ là `web_api_overload_shadowed`, 45/Behaviour.
2. **Optional và extra trailing arguments.** `_arity_range()` đã model khoảng required → declared, và overload dài hơn ceiling cũ được xem là có thể capture call cũ. Hai sai lầm ở schema 32/33 đã được sửa.
3. **Simple quoted literal.** Normalization giữ riêng literal trước khi sửa whitespace; probe `"a,b"` và `"a, b"` không còn bằng nhau.
4. **Per-overload ext.** `overload_traits` giữ signature, runtime gate và extended attributes. Gate/ext của non-representative đổi sinh `web_api_exposure_changed`, không giả thành overload removal.
5. **Hard hole direction.** Whole addition/removal và overload addition/removal hỏi đúng old/new hard hole trong `Scope`; advice `--target-set wide` không còn nối vào parse/missing-target reason.
6. **Hard-hole New bucket.** Khi old source thật sự thiếu target hoặc parse fail, addition không còn nằm trong `New surface`.
7. **Location data.** Snapshot schema 37 giữ `overload_locations`; `report.json` M148 → M151 có đủ location union hai phía cho bốn overload-set changes hiện tại.
8. **Figures hiện tại.** Nếu gọi command đúng với default + wide report thật, artifact sinh lại bằng chính xác file đang commit.

Đây là các improvement có giá trị. Các mục dưới giải thích vì sao chúng chưa tạo thành correctness closure.

### 30.4. Lỗi precision ưu tiên cao: `[Stable]` xuất hiện/mất đi tự tạo ordinal changes

#### Cơ chế lỗi

Extractor chỉ ghi `position` lên child khi container có `[Stable]`:

```text
old container [Stable]   child.position = N, child.stable = true
new container thường     child.position = absent, child.stable = absent
```

Diff không biết “absent vì policy không serialize”. Nó chỉ thấy:

```text
position: N → None
stable:   true → None
```

Vì `position` là meaningful attr:

- method nhận `ipc_ordinal_changed`, 80/Breaking;
- field nhận `ipc_shape_changed`, 80/Breaking.

Nhưng lexical position có thể hoàn toàn không đổi. Đúng ra đây là một **container stability-promise change**, không phải N method/field wire ordinals cùng đổi.

#### Real M143 → M147 wide measurement

| Measurement | Kết quả |
|---|---:|
| Rows có `stable` delta | 225 |
| Trong đó Breaking | 193 |
| Trong đó Behaviour | 32 |
| Child method/field rows | 183 |
| Child rows chỉ có `stable + position` | **164** |
| 164 rows có lexical index thật giữ nguyên | **164 / 164** |
| Annotation rows bị `position` nâng từ 35 lên 80 | 14 |
| Rows có type change thật và vẫn đáng 80 | 5 |
| Pure container stability rows | 32 |

Tức là full matrix tìm được:

- **164 extra Breaking rows** không có signature, type, ordinal hoặc lexical order change;
- **14 rows có annotation change thật nhưng bị nâng sai lên 80**;
- chỉ 5 child rows có type change thật đủ lý do giữ 80.

Ví dụ:

```text
device.mojom.HidCollectionInfo.children
position: 6 → None
stable: true → None
signal: ipc_shape_changed + ipc_stability_changed
score/bucket: 80 / Breaking

raw lexical index: 6 → 6
```

Đây không phải edge case tưởng tượng: nhóm `PhotoSettings` một mình sinh 47 child rows, `PhotoState` 33, `HidReportItem` 25.

#### Signal container cũng chưa đúng

Pure stability delta trên interface được label đúng `ipc_stability_changed` 40. Nhưng struct và enum đi qua nhánh:

```python
elif any(a in deltas for a in ("default", "attrs", "min_version", "stable")):
    ipc_field_annotated
```

Nên 17 struct và 10 enum pure-stability rows bị kể bằng câu “field default or version annotation changed”, dù row là container và không có field default.

#### `MinVersion` mới chỉ partial

Field có dedicated `min_version`; method chưa có. M151 wide có:

```text
Mojo fields có MinVersion    97 — dedicated key: 97
Mojo methods có MinVersion   55 — dedicated key: 0
```

Method vẫn giữ `{"MinVersion=10": true}` bên trong generic `attrs`. Probe `MinVersion=1 → 2` sinh:

```text
signal: build_gate_changed
```

Đó là label sai: MinVersion là version annotation, không phải build condition.

#### Hướng sửa

Không nên serialize position chỉ ở một phía rồi so presence của field đó. Cần:

1. luôn giữ lexical index/provenance trong fact;
2. quyết định **có compare index hay không** dựa trên Stable tier của container;
3. Stable appearing/disappearing emit một container row;
4. child chỉ emit ordinal/shape row khi raw index thật đổi;
5. parse MinVersion thành field riêng cho method và dùng signal đúng.

### 30.5. Own/inherited guard provenance vẫn chưa đóng và có fan-out

Commit `0a9638e` thêm `inherited_conditions` cho `mojo_method` và `mojo_field`. Ý tưởng giữ provenance là đúng. Implementation hiện chưa đạt design audit yêu cầu.

#### Chỉ child giữ provenance

`mojo_interface`, `mojo_struct` và `mojo_enum` không có `inherited_conditions` trong meaningful attrs. Vì vậy:

- member biết một guard đến từ container;
- nested container không biết guard của nó hay của ancestor;
- guard move giữa nested struct và enclosing interface vẫn có thể im lặng.

Probe:

```mojom
// old
interface I {
  [EnableIf=is_win] struct S { int32 x; };
};

// new
[EnableIf=is_win] interface I {
  struct S { int32 x; };
};
```

Kết quả cho `S` và `S.x`: không có provenance delta. Chỉ interface có generic platform row do absent → compiled representation.

#### Container guard bị nhân xuống mọi child

Probe một struct hai fields, chuyển guard từ field lên struct, sinh ba rows:

```text
field a   attrs + inherited_conditions
field b   inherited_conditions + platform_state
struct S  platform_state
```

Với N fields, pattern là container + N child rows. Đây đúng kiểu duplicate fan-out mà mục 27.5 đã cảnh báo phải tránh.

Real M143 → M147 wide có bảy rows mang `inherited_conditions` delta. Sáu row thuộc `UpdateScrollbarThemeParams` đi cùng container guard change; một row mới chỉ tồn tại vì provenance:

```text
proxy_resolver.mojom.SystemProxyResolver.GetProxyForUrl
inherited: EnableIf=is_win → EnableIf=is_win|is_mac
Windows verdict: compiled → compiled
score/bucket: 35 / Behaviour
```

Tool cố định product platform là Windows; row này không thay đổi việc declaration có nằm trong Windows binary hay không, nhưng label vẫn nói “may no longer be in the binary we ship”.

Design sạch hơn vẫn là design audit đã đề xuất:

- container guard change → một container-level row;
- direct member guard change → member-level row;
- child giữ inherited provenance để giải thích, nhưng provenance-only change không tự fan-out;
- compare effective product verdict riêng với source-ownership provenance.

### 30.6. Directional completeness: hard holes tốt hơn, novelty confidence vẫn sai

#### `Scope` đúng hơn nhưng product path chưa truyền old coverage

`Scope` hiện có `shares["from"]` và `shares["to"]`. Unit test gọi trực tiếp với cả hai nên pass. Nhưng `cmd_run` vẫn wiring:

```python
Scope({"to": new.meta["coverage"]}, ...)
```

Report meta đã giữ cả hai, nhưng scoring path chỉ truyền `to`. Đây lại là lỗi “hai cửa”: data model có capability, pipeline thật chưa dùng nó.

Current counts chưa đổi vì code cố ý không dùng partial coverage để nghi ngờ addition; old coverage chỉ ảnh hưởng hard hole. Điều đó không biến wiring thành đúng.

#### “Addition là thứ nhìn thấy” không chứng minh nó mới

Maintainer đúng một nửa:

- declaration **có mặt ở new snapshot** là fact quan sát được;
- declaration **không tồn tại ở old version** là claim dựa trên absence.

Bucket `New surface` khẳng định cả hai, không chỉ câu đầu.

Đối chiếu default additions với old wide snapshot cho M148 → M151:

| Default row | Default nói gì | Old wide truth | Wide diff đúng |
|---|---|---|---|
| `IncomingCallNotifications` | Added, on by default | Đã tồn tại và đã enabled ở old version | Chỉ `declaration_moved` |
| `Prerender2FallbackPrefetchSpecRules` | New feature, on by default | Đã tồn tại disabled ở old version | `default_flip_on` + moved |
| `NewTabPageCustomizationThemeSync` | Added | Old copy Android-only, not compiled on Windows | Windows availability thật sự mới |
| `NewTabPageCustomizationV2` | Added | Old copy Android-only, not compiled on Windows | Windows availability thật sự mới |

Vậy current default report có ít nhất **hai false novelty claims** mà wide snapshot chứng minh được ngay. Không nên giải quyết bằng cách đẩy toàn bộ 1.240 New rows xuống Housekeeping; lần thử đó đúng là phá usefulness. Cách đúng là tách:

```text
observed_presence = chắc chắn có ở new snapshot
novelty_confidence = old surface có đủ để chứng minh trước đó không có hay chưa
```

Hoặc đổi label partial-read thành “newly observed in this scope”, không gọi chắc chắn “New surface”.

#### Phần hard-hole đã fixed

Khi old snapshot có missing target/parse error thật, whole/variant addition bị penalty và New bucket bị hạ. Khi hole ở phía không trả lời câu hỏi, score giữ nguyên. Ma trận 16 tổ hợp hiện khóa đúng phần này.

### 30.7. Per-surface first-match: mục này chưa được sửa

Code hiện vẫn làm:

```python
if path in found:
    shared += 1
    continue
found[path] = rule.note
```

Commit body không sửa membership; nó quyết định rằng per-surface rows phải partition global denominator và thêm log “under the first”. Nhưng hai phép đo trả lời hai câu khác nhau:

- global denominator: unique file count, phải dedupe path;
- surface denominator: file có thể khai báo kind của surface nào, phải thuộc mọi matching surface.

M151 measurement:

```text
unique global candidates       8.366
multi-surface paths              378
extra memberships                378
```

Không phải 368 ở M151; 368 là old M148 side. Pair có 368 → 378.

Hai surface bị lệch:

| Surface / target | First-match hiện tại | Multi-membership đúng |
|---|---:|---:|
| Pref/switch — default | 4 / 348 (1,15%) | 9 / 529 (1,70%) |
| Pref/switch — wide | 345 / 348 (99,14%) | 526 / 529 (99,43%) |
| Visibility gates — default | 340 / 340 | 537 / 537 |
| Visibility gates — wide | 340 / 340 | 537 / 537 |

Current threshold 95% tình cờ cho cùng yes/no verdict, nên bucket count chưa đổi. Mẫu số và population vẫn sai; lần target/rule tiếp theo có thể cắt qua threshold.

Ngoài ra normal `report.md` và `report.html` vẫn chỉ in overall coverage. Tìm sáu surface labels trong hai report đều không có kết quả. `by_surface` chỉ nằm trong JSON meta.

Kết luận: mục #3 trong danh sách “còn lại” vẫn còn nguyên; commit chỉ documented disagreement, không implement requested behavior.

### 30.8. Per-overload location: data fixed, renderer chưa fixed

Quyết định **không đưa line number vào `MEANINGFUL_ATTRS` là đúng**. Dịch vài dòng do code phía trên thay đổi không phải Web API change.

Data layer schema 37 cũng làm đúng phần lớn:

- M151 có 121 overload groups;
- mỗi group nhiều signature có `overload_locations`;
- `Change.locations` union vị trí old/new;
- current report JSON có đủ location cho các row thật.

Nhưng commit nói “reader lands on the right lines” và “row points at every overload”. Renderer vẫn cắt:

```python
Markdown detail: where[:3]
HTML data:       paths[:3]
Markdown table:  where[0]
```

Real examples:

| Finding | JSON locations | Markdown detail | HTML |
|---|---:|---:|---:|
| `Navigator.install` | 5 | 3 | 3 |
| `WebGLRenderingContextBase.texElementImage2D` | 4 | 3 | 3 |

Ở WebGL row, line `651` là một overload bị xoá thật và bị renderer bỏ. Test mới chỉ assert một fixture có `len(change.locations) == 2`; nó không render finding có hơn ba locations.

Hướng sửa nhỏ:

- render tất cả changed-variant locations;
- hoặc hiện ba dòng đầu + “and N more” có thể expand;
- test JSON **và** Markdown/HTML trên group 4–5 variants.

### 30.9. `docs/figures.json`: improvement thật nhưng chưa phải single source cho mọi số

#### Phần đúng

Sinh lại từ:

```bash
chromedrift figures out/report.json --wide <wide-report.json>
```

cho object bằng đúng `docs/figures.json` hiện commit. Current selected metrics không stale:

```text
total          3.022
buckets        276 / 469 / 1.240 / 1.037
owners         339 / 719 / 1.157 / 277 / 530
no_signal      981
coverage       3.677 / 8.366; 8.295 / 8.366
```

Ba document↔artifact tests cũng chạy được trên clean checkout.

#### Clean checkout vẫn có skip

Chạy riêng test class trên một `git archive HEAD` sạch:

```text
Ran 4 tests
OK (skipped=1)
```

Test bị skip chính là artifact↔real-report oracle:

```text
no out/report.json; run the pair to check the artifact
```

Nghĩa là fresh CI chứng minh “docs khớp artifact đã commit”, không chứng minh “artifact khớp code + Chromium data hiện tại”. Repo cũng chưa có release/CI step tự chạy report + `figures`.

#### Wide oracle chưa được test

Test artifact↔report chỉ mở `out/report.json` default và chỉ compare `coverage.default`. `_WIDE_READ = 8295` được khai báo nhưng không dùng. Ngay cả khi có `out-wide/report.json`, test không đọc file đó.

Command cũng không validate input. Truyền chính default report vào `--wide` được chấp nhận và ghi:

```json
"wide": {"read": 3677, "candidates": 8366}
```

thay vì từ chối target set sai.

#### Không phải mọi measured figure đã vào artifact

Artifact chỉ chứa total, buckets, owners, Breaking-by-owner, no-signal và overall coverage. Nhiều active measurements vẫn viết tay và nằm ngoài matcher, ví dụ:

- `220 of 276 Breaking rows are Mojo or web API`;
- control inventory `971 / 955 / 190 / 156 / 130 / 15`;
- `14 of 187` platform-divergent flags;
- ordinal/Stable tables trong `traps.md`.

Vậy cách gọi chính xác là:

> “Đã tạo canonical artifact cho nhóm headline figures hiện tại.”

Chưa thể gọi là “mọi con số tài liệu sinh từ report” hoặc “không cần sửa tay nữa”.

### 30.10. Effective arity và normalization còn hai residual mechanism

#### Variadic range được nhận diện nhưng dùng sai

`_arity_range("void f(long... a)")` trả `(0, None)` đúng. Nhưng `_overload_signals()` chỉ thêm `low` vào `served`, rồi đặt `ceiling = None`. Khi thêm overload arity lớn hơn `low`:

```webidl
// old
void f(DOMString... xs);

// new
void f(DOMString... xs);
void f(long x, long y);
```

old variadic đã nhận call hai arguments. Current result vẫn là:

```text
web_api_overload_added — 25 / New
```

thay vì shadowing/Behaviour. Bốn real overload groups M151 có variadic signature; không có observed addition thuộc đúng failing shape trong M143–M151 pairs, nên đây là contract hole chưa có current yield.

`_arity_range()` cũng split comma mà không giữ string literal. Signature có default string chứa comma bị đếm sai parameter. Đây cùng lớp lexer issue với normalizer.

#### Literal regex không hiểu escaped quote

Simple `"a,b"` đã fixed. `_LITERAL_RE = r'"[^"]*"|...'` không hiểu escape. Probe:

```webidl
"a\",b"  →  "a\", b"
```

vẫn normalize thành cùng string. Không thấy real M143–M151 row dùng shape này; cần test/tokenizer nhỏ trước khi gọi normalization contract closed.

### 30.11. Raw grammar inventory: `0 parser errors` không có nghĩa là đọc hết grammar

Đây là việc maintainer tự ghi “đáng làm tiếp”, và kết quả giải thích rõ vì sao 359/360 tests chưa phải oracle.

#### Extracted facts trước/sau dedupe

| Version wide | WebIDL raw output → deduped | Mojo raw output → deduped | Extract errors |
|---|---:|---:|---:|
| M143 | 14.323 → 14.134 | 22.569 → 22.563 | 0 |
| M147 | 14.505 → 14.303 | 23.521 → 23.513 | 0 |
| M148 | 14.567 → 14.371 | 23.829 → 23.821 | 0 |
| M151 | 14.763 → 14.569 | 24.858 → 24.850 | 0 |

WebIDL dedupe loss hiện chủ yếu là overload/duplicate UID; schema 37 giữ signature, traits và locations tốt hơn trước. Nhưng bảng này vẫn chỉ đếm thứ extractor **đã nhận ra**.

#### WebIDL grammar không có fact kind

Trong 2.166 M151 IDL files đã tải/đọc, lexical inventory có:

| Top-level grammar | M151 records | M148 → M151 changes |
|---|---:|---:|
| Callback function definitions | 85 | 0 |
| Typedefs | 144 | +1 |
| `Interface includes Mixin` relations | 200 | +7 / −7 |

Tổng **429 records** không có fact kind. `includes` đặc biệt quan trọng: member của mixin được key dưới mixin, nhưng relation nói concrete interface nào thực sự nhận member đó.

Current pair có 14 includes relation moves. Tool báo nhiều mixin/member add/remove liên quan, nhưng không lưu relation `HTMLElement includes ...`, `SVGElement includes ...`, v.v. Typedef `SanitizerPI` được thêm và members dùng tên đó có row, nhưng typedef shape itself không có row.

Concrete historical false negative:

```text
M143 → M147
typedef LanguageModelMessageValue changed underlying union
ChromeDrift rows mentioning that identity: 0
```

Member signatures dùng alias name giữ nguyên, nên allowlist comparison không thấy underlying type đổi.

#### Mojo grammar không có fact kind

M151 materialized `.mojom` inventory có:

```text
feature blocks             18
const identities          311
const declaration variants 337
```

Extractor hiện chỉ model interface/method/struct/union/field/enum. M148 → M151 lexical inventory thấy:

```text
feature  +1 / -2 / ~1
const    +4 / -12 / ~3
```

Ví dụ `kWebNNCompilerProcess` được thêm, `kWebNNDirectML` bị bỏ, `kWebNNLiteRT` đổi body; M151 wide snapshot không có fact nào chứa các identity đó. File vẫn được tính là process-boundary candidate đã đọc.

Không nhất thiết mọi const phải có severity cao. Nhưng phải chọn một trong hai cách trung thực:

1. thêm fact kind/grammar support;
2. ghi rõ exclusion và không dùng “read 99% process-boundary interfaces” như bằng chứng parser completeness.

Điểm chính:

> `_errors = 0` chỉ nghĩa là extractor không throw exception trên grammar nó thử. Nó không chứng minh extractor nhận ra mọi declaration class trong file.

### 30.12. Test quality, thứ tự sửa và verdict cuối

#### Vì sao 360 pass vẫn bỏ lọt các lỗi trên

Các test mới tốt hơn trước ở chỗ nhiều fixture đi qua extract → dedupe → diff → score. Nhưng chúng vẫn khóa từng local behavior riêng:

- Stable reorder test bắt hai stable snapshots, không bắt Stable → non-Stable;
- location test dùng đúng hai locations, không đi qua renderer limit ba;
- coverage test dựng `Scope` trực tiếp, không đi qua `cmd_run` wiring;
- documentation test có artifact sẵn, không tự tạo oracle report;
- first-match test hiện khóa chính policy first-match, không kiểm semantic membership;
- grammar không được extract thì snapshot-based test không biết population đó tồn tại.

Full matrix là phần tìm lỗi giá trị nhất vòng này: current M148 → M151 bằng 0 stability rows làm mechanism trông an toàn; M143 → M147 lập tức tạo 225 stability delta rows và phơi ra 164 row giả.

#### Thứ tự sửa đề nghị

##### Ưu tiên cao — làm radar bớt nhiễu và tránh label sai

1. Sửa Stable transition: luôn giữ raw lexical index, compare theo container tier, không duplicate container stability xuống child.
2. Tách `stable` khỏi `ipc_field_annotated`; parse method MinVersion riêng và signal đúng.
3. Thiết kế lại guard provenance theo container/member aggregation; không fan-out inherited-only rows.
4. Truyền cả old/new coverage vào `Scope` từ `cmd_run`; tách observed presence khỏi novelty confidence.
5. Thêm regression bằng hai current false novelty facts (`IncomingCallNotifications`, `Prerender2FallbackPrefetchSpecRules`).
6. Ghi rõ coverage contract cho WebIDL callback/typedef/includes và Mojo feature/const grammar; chỉ thêm extractor mới khi các surface này có giá trị thực tế với người dùng.

##### Ưu tiên tiếp theo — report và hạ tầng

7. Per-surface multi-membership: global dedupe, surface overlap; in bảng vào normal report.
8. Renderer hiện đủ changed overload locations hoặc có expandable “N more”.
9. `figures` validate pair/schema/target set; test wide report; chạy artifact generation/check trong CI/release.
10. Mở rộng artifact/templates cho các active measured figures còn viết tay.
11. Làm arity parser quote/escape/variadic-aware và thêm escaped-literal regression.

#### Verdict cuối

> **Schema 37 tốt hơn schema 33 rõ rệt, current M148 → M151 headline figures là reproducible và project đạt mục tiêu làm static early-warning inventory cho manual triage. Full matrix vẫn chứng minh Stable modeling tạo false Breaking rows quy mô lớn; first-match, guard aggregation, CLI old-coverage wiring và renderer location còn backlog. Raw grammar cho biết những surface tool chưa đọc, nhưng với mục tiêu phát hiện một phần thì đây là known scope cần document và ưu tiên theo giá trị, không phải yêu cầu phải đạt 100%.**

## 31. Review `843dd96` và `bee9e7d` — xác định thế nào là “đủ tốt” cho early detection

### 31.1. Kết luận dễ hiểu

Mục tiêu đã được chốt lại là:

> Không cần tìm 100% thay đổi. Cần bắt sớm một phần đủ hữu ích, ít báo động giả nghiêm trọng, chỉ đúng chỗ để con người kiểm tra và nói rõ phần mình không đọc.

Theo mục tiêu đó:

> **Schema 39 đủ tốt để dùng ngay. Không phát hiện lỗi nào ở mức phải dừng sử dụng.**

Hai commit mới đóng đúng các lỗi nặng mà audit trước tìm ra. Full matrix hiện không còn row nào bị đưa vào Breaking chỉ vì `position` biến mất theo `[Stable]`; current overload findings cũng không còn bị giấu mất declaration location. Những thứ còn lại chia thành ba loại rất khác nhau:

1. một duplication bug nên sửa sớm để radar bớt nhiễu;
2. vài known scope/edge case chỉ cần ghi rõ và chờ real yield;
3. hạ tầng có thể cải thiện sau, không ảnh hưởng việc dùng tool hôm nay.

### 31.2. Kiểm chứng độc lập hai commit

Baseline:

```text
HEAD / origin/main   bee9e7d
schema               39
history              76 / 76 commit
Python 3.14           362 / 362 test pass
Python 3.9            362 / 362 test pass
```

#### `843dd96`: sửa đúng false Breaking

Cơ chế sửa là đúng: `position` chỉ được coi là ordinal evidence khi cả hai phía đều có một vị trí để so. Delta `[6, None]` không còn tự biến thành `ipc_shape_changed`/`ipc_ordinal_changed` 80 điểm.

Kết quả chạy lại schema 39:

| Pair | Default Breaking | Wide Breaking | Breaking chỉ dựa vào `position → None` |
|---|---:|---:|---:|
| M143 → M147 | 339 | 1.152 | 0 / 0 |
| M147 → M148 | 79 | 276 | 0 / 0 |
| M148 → M151 | 276 | 798 | 0 / 0 |

Năm M143 → M147 wide rows còn `position` trong Breaking đều có `type` delta độc lập; giữ 80 điểm là đúng.

Đây là bản sửa quan trọng nhất vì radar báo Breaking giả hàng loạt sẽ nhanh chóng làm người dùng ngừng đọc radar.

#### `bee9e7d`: năm hướng sửa chính đều hợp lý

1. **Hai phía coverage đã vào pipeline thật.** `cmd_run` truyền cả `old.meta.coverage` và `new.meta.coverage` cho `Scope`; không còn tình trạng data model biết hai phía nhưng call site chỉ đưa phía `to`.
2. **So Windows verdict thay vì cách viết guard.** `absent` và `{windows: compiled}` được normalize về cùng một trạng thái. Probe guard chuyển từ field lên struct không còn làm field không đổi trong Windows bị kể là “may no longer be in our binary”.
3. **Inherited provenance không còn tự tạo child row.** `inherited_conditions` vẫn được lưu để giải thích nhưng ra khỏi comparison allowlist. Sáu real-version runs có `inherited_conditions` delta rows bằng 0.
4. **Per-surface membership đúng câu hỏi.** Global vẫn đếm 8.366 unique files; một file được tính vào mọi surface có extractor đọc nó. M151 thực tế:

```text
pref/switch default     9 / 529
pref/switch wide      526 / 529
visibility gates      537 / 537
multi-surface files          378
```

5. **Renderer đủ cho current findings.** `Navigator.install` có 5 locations và `WebGLRenderingContextBase.texElementImage2D` có 4; cả hai hiện đầy đủ. Markdown hiện sáu rồi ghi `and N more`. HTML giữ sáu.

### 31.3. Một việc code còn đáng sửa sớm

#### `[Stable]` đã hết báo Breaking giả, nhưng vẫn lặp 164 dòng Behaviour

M143 → M147 wide hiện có:

```text
196 ipc_stability_changed findings
 32 container rows
164 method/field rows chỉ có deltas = {stable, position}
```

164 child rows đều đến từ ba file và cùng kể lại việc container mất `[Stable]`:

```text
image_capture.mojom          74
hid.mojom                    66
video_capture_types.mojom    24
```

Nó không còn nguy hiểm như trước:

- không nằm trong Breaking;
- không tuyên bố ABI ordinal đã đổi;
- chỉ chiếm khoảng 2% của report wide 8.044 rows.

Nhưng trong riêng bucket Behaviour, 164 rows là hơn 11%. Một upstream annotation edit vẫn chiếm quá nhiều chỗ đọc. Vì mục tiêu là early-warning radar, đây là **việc code có yield rõ nhất nên làm tiếp**.

Hướng đủ dùng, không cần thiết kế lớn:

- container emit một `ipc_stability_changed` row;
- child có `stable/position` thay đổi chỉ vì container mất/nhận `[Stable]` thì không emit riêng;
- child vẫn emit nếu raw type, explicit ordinal hoặc lexical position thật sự đổi.

Sửa mục này xong có thể dừng vòng correctness hiện tại.

### 31.4. Test còn thiếu cho chính commit mới

`bee9e7d` thay đổi năm behavior nhưng chỉ thêm một test mới, cho multi-surface membership. Các test cũ giúp suite pass nhưng chưa khóa trực tiếp bốn boundary còn lại.

Nên thêm bốn regression nhỏ:

1. một test đi qua `cmd_run` hoặc helper tạo `Scope`, assert coverage hai phía thật sự được truyền;
2. guard `absent ↔ compiled` không sinh row, còn `compiled ↔ not_compiled` vẫn sinh;
3. guard move không tạo inherited-only fan-out;
4. Markdown và HTML cùng render một finding có 4–5 locations.

Đây là việc rẻ nhưng đáng làm. History đã có ba lần “capability tồn tại ở cửa đầu, pipeline thật không dùng ở cửa sau”; khóa boundary quan trọng hơn tăng số test chung chung.

### 31.5. Những thứ chỉ cần biết và ghi rõ, chưa nên viết thêm extractor

#### Grammar chưa model

M151 có các declaration class tool chưa biến thành fact:

| Known scope | Số lượng |
|---|---:|
| WebIDL callback definitions | 85 |
| WebIDL typedefs | 144 |
| WebIDL `includes` relations | 200 |
| Mojo `feature` blocks | 18 |
| Mojo constants | 311 identities |

Có missed example thật, như `LanguageModelMessageValue` đổi underlying union ở M143 → M147 và `kWebNNDirectML` biến mất ở M151. Nhưng mục tiêu hiện tại không yêu cầu parser completeness.

Quyết định hợp lý bây giờ:

1. thêm danh sách này vào phần “What the tool does not read” của README/report;
2. đổi wording nào còn gợi ý input là “complete” thành “bounded and measured”;
3. chỉ viết extractor khi real review chứng minh surface đó thường xuyên tạo actionable finding.

Nếu sau này chỉ chọn một, `includes` hoặc `typedef` có yield rõ hơn callback. Không cần làm cả năm loại cùng lúc.

#### Parser edge cases chưa có current yield

- variadic overload có thể bị gọi là `added` thay vì `shadowed`;
- parameter splitter chưa hiểu comma trong quoted default;
- literal normalizer chưa hiểu escaped quote hoàn chỉnh.

Bốn milestone thật chưa rơi vào failing shape. Ghi chúng vào backlog và thêm fixture khi sửa parser; không cần chặn việc dùng schema 39.

### 31.6. Hạ tầng nào có thể để sau

- `docs/figures.json` đã đủ cho headline numbers. Không cần chạy Chromium download trong mọi commit hook.
- Artifact↔report oracle có thể là bước thủ công trước một lần publish tài liệu lớn.
- HTML hiện tối đa sáu locations và không ghi `N more`; current changed group tối đa năm, nên đây chưa phải lỗi thực tế.
- Không cần so line number như semantic data; giữ nó chỉ để dẫn người đọc là quyết định đúng.
- Không cần theo đuổi coverage 100% hay automated release verdict.

### 31.7. Default có hai “new” label chưa hoàn toàn chắc — nhưng không phải lỗi nặng

`cmd_run` đã truyền old coverage, nhưng scoring cố ý không hạ toàn bộ additions chỉ vì default scan phía old đọc ít. Nếu làm vậy, `New surface` từng rơi từ 1.240 xuống 0 và report mất tác dụng.

Hệ quả còn lại: default M148 → M151 gọi `IncomingCallNotifications` và `Prerender2FallbackPrefetchSpecRules` là added/new-on-by-default, trong khi wide scan thấy declaration cũ và phân loại chính xác là move/default flip.

Với early detection, đây vẫn là signal hữu ích: có thay đổi thật và wide scan sửa lại câu chuyện. Không cần đổi score ngay. Nếu muốn wording chặt hơn, default report có thể dùng “newly observed in this scan” thay cho claim tuyệt đối “did not exist before”.

### 31.8. Điểm dừng đề nghị

Làm ba việc sau là đủ để khép vòng này:

1. gộp/suppress 164 child stability-only rows;
2. thêm bốn boundary regression tests cho `bee9e7d`;
3. công khai năm grammar classes chưa đọc trong user-facing documentation.

Sau đó **dừng mở rộng theo audit giả định**. Dùng tool trên các uprev thật, ghi lại:

- top findings nào giúp phát hiện việc thật;
- false positive nào làm người đọc mất thời gian;
- thay đổi quan trọng nào con người tìm được nhưng tool bỏ sót.

Chỉ mở extractor hoặc scoring rule mới khi có một ví dụ thật và expected action rõ. Đó là cách tối ưu một early-warning tool; không phải cố biến nó thành parser hoàn chỉnh.

#### Verdict cuối schema 39

> **Dùng được ngay. Không còn known false Breaking regression hay current overload location bị giấu. Việc code đáng sửa nhất là 164 stability child rows lặp; phần grammar chưa đọc cần document, không cần giải quyết hết. Sau một fix nhỏ, bốn boundary tests và một scope note, project đã “đủ tốt” cho mục tiêu cảnh báo sớm và nên chuyển từ audit-driven expansion sang học từ các uprev thật.**
