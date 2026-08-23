# 5. Cơ chế so sánh, chấm điểm, bucket và owner

## Bốn khái niệm không được trộn với nhau

| Khái niệm | Câu hỏi nó trả lời |
|---|---|
| `signal` | Chính xác chuyện gì đã xảy ra? |
| `severity` | Loại thay đổi đó đáng được xem sớm đến đâu nếu bằng chứng đầy đủ? |
| `score` | Sau khi xét Windows build và độ đầy đủ của lần đọc, thứ tự cuối là bao nhiêu? |
| `bucket` | Đây là breaking contract, behaviour change, new surface hay housekeeping? |
| `owner` | Technical area nào nên kiểm tra finding trước? |

Score không phải probability, không phải effort và không phải mức chắc chắn Samsung có bug. Một finding score 80 nghĩa là “theo rule của tool, đây là loại upstream change cần được review trước”, không có nghĩa “80% Samsung Browser bị lỗi”.

## Luồng so sánh

```text
Fact cũ + Fact mới
        │
        ▼
ghép theo uid = kind:key
        │
        ├── chỉ có bên mới → added
        ├── chỉ có bên cũ  → removed
        └── có cả hai      → so meaningful attrs
                                  │
                                  └── khác → modified + deltas
        │
        ▼
post-pass: rename / WebUI control repoint
        │
        ▼
tạo một hoặc nhiều signal
        │
        ▼
chọn leading signal
        │
        ├── severity
        ├── bucket ban đầu
        └── owner override nếu có
        │
        ▼
score stage
  Windows build + coverage/acquisition holes
        │
        ▼
Finding(score, bucket, reasons)
```

## Bước 1: chỉ so attribute có ý nghĩa

Mỗi kind có whitelist riêng. Ví dụ:

- `base_feature`: default, Windows/platform state, condition, C++ variable;
- `mojo_method`: signature, params, response, attrs, ordinal, stable position, platform state;
- `webui_control`: control type, pref, label, build/platform condition;
- `flag_entry`: chỉ expiry milestone.

Những field không ảnh hưởng semantics bị bỏ khỏi comparison. `BASE_FEATURE` đổi macro form, line number đổi hoặc `method_count` đổi vì một method Fact đã được add/remove không tạo thêm change mơ hồ.

Platform state `compiled` được chuẩn hoá tương đương với “không có guard”. Vì vậy bỏ `#if !IS_ANDROID` khỏi declaration vẫn có trên Windows không tạo noise.

## Bước 2: ba direction cơ bản và hai post-pass

### Added, removed, modified

- `added`: UID chỉ có ở snapshot mới.
- `removed`: UID chỉ có ở snapshot cũ.
- `modified`: UID có ở cả hai nhưng meaningful attrs khác.

### Rename detection

Pref, switch và base feature string dùng external string làm identity. Khi string đổi, basic diff thấy một removed + một added. Tool ghép chúng nếu C++ variable giữ nguyên:

```text
before: pref key old.path, var kFoo
after:  pref key new.path, var kFoo
                     ↓
modified + pref_renamed
```

Phân biệt hai case:

- string đổi, symbol giữ: external config/data có thể mất tác dụng;
- string giữ, symbol đổi: external data an toàn nhưng Samsung C++ reference có thể build fail.

### WebUI control repoint detection

Pref là một phần identity của control. Khi control giữ page và element id nhưng chuyển pref, basic diff cũng thấy remove + add. Tool ghép theo `(surface, page, element_id hoặc label)` để tạo `ui_control_repointed`.

## Bước 3: signal được tạo từ direction và delta

Signal là rule deterministic, không phải nhận xét tự do. Một Change có thể có nhiều signal:

```text
base_feature modified
deltas:
  platform_state: disabled → enabled
  var: kOld → kNew
signals:
  enabled_by_default
  feature_symbol_renamed
```

Leading signal là signal có severity cao nhất. Nếu hai signal cùng điểm, tool chọn theo tên để output không phụ thuộc order.

Severity lấy **chính xác từ leading signal**. Bảng base theo kind + direction chỉ dùng khi Change không có signal nào. Tool không lấy `max(base severity, signal severity)`, vì coarse base từng đẩy một thay đổi Mojo attribute bình thường lên ngang ABI signature change.

## Bảng base severity khi không có signal

| Kind | Added | Removed | Modified |
|---|---:|---:|---:|
| `base_feature` | 20 | 30 | 45 |
| `feature_param` | 15 | 35 | 35 |
| `blink_runtime_feature` | 25 | 20 | 40 |
| `idl_interface` | 30 | 70 | 40 |
| `idl_member` | 25 | 60 | 45 |
| `mojo_interface` | 20 | 70 | 40 |
| `mojo_method` | 20 | 70 | 75 |
| `mojo_struct` | 20 | 70 | 60 |
| `mojo_field` | 20 | 70 | 60 |
| `mojo_enum` | 20 | 65 | 45 |
| `switch` | 10 | 30 | 40 |
| `pref` | 10 | 35 | 45 |
| `flag_entry` | 5 | 30 | 15 |
| `webui_route` | 40 | 55 | 45 |
| `webui_control` | 25 | 35 | 30 |
| `webui_gate` | 25 | 40 | 45 |

Base table là fallback để không mất một Change lạ. Mọi case product quan trọng nên có signal cụ thể.

## Bảng đầy đủ 60 signal

### Feature lifecycle và default state

| Signal | Severity | Bucket | Cách đọc |
|---|---:|---|---|
| `enabled_by_default` | 75 | Behaviour change | Windows state chuyển sang ON |
| `disabled_by_default` | 60 | Behaviour change | Windows state chuyển sang OFF |
| `default_flip_on` | 60 | Behaviour change | Default declaration chuyển ON |
| `default_flip_off` | 50 | Behaviour change | Default declaration chuyển OFF |
| `feature_deleted` | 65 | Behaviour change | Feature bị xoá nhưng state trước đó không đọc được |
| `flag_retired_on` | 35 | Housekeeping | Feature đã ship; flag bị dọn nên behaviour ON trở thành cố định |
| `flag_retired_off` | 30 | Housekeeping | Feature chưa ship; flag và code bị bỏ, không bật lại được |
| `new_feature_on_by_default` | 55 | Behaviour change | Feature mới xuất hiện và ON ngay |
| `feature_string_renamed` | 75 | Breaking | Tên Finch/`--enable-features` đổi; config cũ im lặng mất tác dụng |
| `feature_symbol_renamed` | 60 | Breaking | C++ symbol đổi; downstream reference có thể không compile |

`flag_retired_on/off` không bị gọi là Behaviour change vì việc bật/tắt đã xảy ra trước đó; release này chủ yếu dọn chiếc công tắc. Tuy nhiên override bên ngoài repository vẫn phải được tìm và xoá.

### Web Platform và Web IDL

| Signal | Severity | Bucket | Cách đọc |
|---|---:|---|---|
| `web_api_shipped` | 65 | Behaviour change | Blink runtime feature đạt stable trên Windows |
| `web_api_unshipped` | 70 | Breaking | API bị rút khỏi stable |
| `web_api_removed` | 70 | Breaking | Interface/member đang reachable bị remove |
| `web_api_added` | 30 | New surface | API mới, tool chưa xác định gate mở hay đóng |
| `web_api_added_live` | 35 | New surface | API mới và page có thể gọi ngay |
| `web_api_added_gated` | 20 | New surface | API mới nhưng runtime gate còn đóng |
| `web_api_removed_gated` | 30 | Housekeeping | API bị remove khi chưa page nào reach được |
| `killswitch_retired` | 35 | Housekeeping | Blink flag stable bị xoá; API trở thành permanent |
| `experimental_dropped` | 20 | Housekeeping | Experimental/test runtime flag bị bỏ |
| `web_api_signature_change` | 50 | Breaking | Signature hoặc member kind đổi |
| `web_api_overload_removed` | 60 | Breaking | Một argument list của member bị mất |
| `web_api_overload_added` | 25 | New surface | Có overload mới, không đụng arity cũ |
| `web_api_overload_shadowed` | 45 | Behaviour change | Overload mới có arity cũ đã dùng; call có thể resolve khác |
| `web_api_exposure_changed` | 45 | Behaviour change | `Exposed`, extended attrs hoặc runtime gate đổi |
| `web_api_shape_changed` | 45 | Behaviour change | Inheritance hoặc enum values đổi |
| `web_api_status_moved` | 25 | Housekeeping | Chuyển giữa test/experimental nhưng chưa stable |
| `origin_trial_change` | 35 | Behaviour change | Tên, OS, third-party hoặc trial access đổi |
| `runtime_flag_rewired` | 30 | Housekeeping | Base feature/dependency/public/internal wiring đổi mà Windows exposure chưa đổi |

Added/removed Web IDL còn hỏi runtime gate. Nếu `[RuntimeEnabled=Foo]` và `Foo` stable, API được xem là reachable. Nếu flag chưa được snapshot đọc, tool dùng signal undecided thay vì đoán.

### Mojo và IPC

| Signal | Severity | Bucket | Cách đọc |
|---|---:|---|---|
| `ipc_signature_change` | 80 | Breaking | Mojo method params/response đổi |
| `ipc_removed` | 75 | Breaking | Interface/method/data declaration bị remove |
| `ipc_shape_changed` | 80 | Breaking | Field type/ordinal, stable position hoặc struct-vs-union đổi |
| `ipc_ordinal_changed` | 80 | Breaking | Method wire ordinal hoặc stable position đổi |
| `ipc_enum_changed` | 55 | Breaking | Enum values đổi; peer cũ có thể reject value lạ |
| `ipc_field_annotated` | 35 | Behaviour change | Default hoặc `[MinVersion]` của field đổi |
| `ipc_stability_changed` | 40 | Behaviour change | `[Stable]` xuất hiện hoặc biến mất |

`position` chỉ là bằng chứng ABI khi có giá trị ở cả hai bên. `[Stable]` bị bỏ làm `position` biến mất không được nhân thành một ABI break cho từng member; container nhận `ipc_stability_changed`.

### Pref, switch, param và external config

| Signal | Severity | Bucket | Cách đọc |
|---|---:|---|---|
| `pref_renamed` | 70 | Breaking | Stored value ở key cũ có thể bị orphan |
| `switch_renamed` | 60 | Breaking | Launch/automation argument cũ mất tác dụng |
| `pref_left_scan` | 35 | Breaking ban đầu | Không còn thấy pref; có thể xoá hoặc move khỏi files đã đọc |
| `switch_left_scan` | 30 | Breaking ban đầu | Không còn thấy switch; có thể xoá hoặc move |
| `pref_symbol_renamed` | 55 | Breaking | Pref key giữ nguyên, C++ constant đổi |
| `switch_symbol_renamed` | 45 | Breaking | Switch string giữ nguyên, C++ constant đổi |
| `param_default_changed` | 40 | Behaviour change | FeatureParam default đổi |
| `param_removed` | 35 | Breaking | Config tiếp tục set param sẽ im lặng mất tác dụng |
| `param_rewired` | 35 | Breaking | Type hoặc owning feature của param đổi |

`pref_left_scan` và `switch_left_scan` có thể bị scoring chuyển sang Housekeeping nếu coverage không đủ xác nhận removal. Rename đã ghép được bằng symbol là bằng chứng mạnh hơn và không bị hạ theo rule này.

### WebUI

| Signal | Severity | Bucket | Cách đọc |
|---|---:|---|---|
| `ui_page_removed` | 55 | Behaviour change | Route/page bị remove |
| `ui_page_added` | 40 | New surface | Route/page mới |
| `ui_page_regated` | 45 | Behaviour change | Guard quyết định page visible đổi |
| `ui_page_moved` | 30 | Behaviour change | URL hoặc parent route đổi |
| `ui_control_type_changed` | 45 | Behaviour change | Control type đổi, ví dụ dropdown thành toggle |
| `ui_control_repointed` | 50 | Breaking | Control vẫn còn nhưng ghi sang pref khác |
| `ui_control_removed` | 35 | Behaviour change | Control bị remove khỏi template |
| `ui_control_added` | 25 | New surface | Control mới |
| `ui_gate_changed` | 45 | Behaviour change | C++ expression/feature phía sau `loadTimeData` key đổi |
| `ui_gate_removed` | 40 | Behaviour change | Visibility condition bị bỏ; phần được guard có thể unconditional hoặc mất theo |
| `ui_gate_added` | 25 | New surface | Visibility condition mới |
| `ui_control_relabelled` | 20 | Housekeeping | i18n key của label đổi; tool chưa đọc display string để biết user có thấy khác không |

### Build, move và scheduling

| Signal | Severity | Bucket | Cách đọc |
|---|---:|---|---|
| `build_gate_changed` | 35 | Behaviour change | Declaration có thể vào/ra Windows binary |
| `declaration_moved` | 25 | Housekeeping | Cùng declaration chuyển file |
| `flag_expiring` | 45 | Housekeeping | Flag dự kiến bị xoá trước hoặc trong hai milestone sau target |
| `flag_expiry_moved` | 10 | Housekeeping | Lịch xoá đổi nhưng chưa đổi runtime behaviour |

`flag_expiring` nằm Housekeeping theo bản chất source change, nhưng owner được route sang config để người đang phụ thuộc flag lập kế hoạch. Housekeeping không đồng nghĩa với “không bao giờ có việc”.

## Bước 4: score được tính thế nào

Pseudo-code đúng với implementation:

```text
severity = severity(leading signal)
        hoặc base_severity(kind, direction) nếu không có signal

if declaration không được compile vào Windows ở mọi side đang tồn tại:
    score = 0
    bucket = Housekeeping
    stop

score = severity
bucket = bucket(leading signal)

direction_for_absence = added / removed
nếu delta overload signatures:
    mất signature  → coi như removed
    chỉ thêm        → coi như added

if kết luận dựa trên absence và surface coverage < 95%
   hoặc acquisition side tương ứng có hard hole:
    score -= 15
    ghi rõ reason

if leading signal là pref_left_scan hoặc switch_left_scan
   và absence chưa được xác nhận:
    bucket = Housekeeping

if addition không thể chứng minh absent ở old side vì hard hole:
    bucket = Housekeeping

score = clamp(score, 0, 100)
```

### Không có điểm cộng

Severity là trần. Modifier chỉ trừ hoặc đưa về 0; không có rule “Samsung patch file này nên +20” vì ChromeDrift không có Samsung source profile trong core pipeline. Mọi chênh lệch giữa severity và score đều phải xuất hiện trong `reasons`.

### Windows build rule

Chỉ đưa về 0 khi declaration `not_compiled` ở **mọi side đang tồn tại**.

- Android-only trước và sau: score 0.
- Có trên Windows trước, bị loại khỏi Windows sau: giữ nguyên score vì chính việc rời binary là change.
- Chưa có trước, vào Windows ở version mới: giữ nguyên score.

### Coverage rule

Ngưỡng xác nhận absence là `95%`, tính theo surface của kind:

- feature flags;
- web platform flags;
- web API definitions;
- process-boundary interfaces;
- preference keys and switches;
- flags entries;
- routes, controls, gates.

Removal hỏi coverage của snapshot mới: “không còn ở version mới” chỉ đáng tin nếu bên mới đã được đọc. Addition thường là thứ tool nhìn thấy thật ở bên mới; nó chỉ bị nghi ngờ khi old acquisition có hard hole làm tool không thể chứng minh thứ đó chưa tồn tại, không bị hạ chỉ vì target set cũ có partial coverage thông thường.

Penalty cố định `15`, không nhân theo phần trăm. Coverage đếm file, không đếm declaration; default có thể đọc ít file nhưng đó là những file chứa phần lớn feature declaration. Dùng coverage như probability sẽ tạo cảm giác chính xác giả.

## Bước 5: bucket được chọn thế nào

Leading signal quyết định bucket. Nếu không có signal:

- added → New surface;
- removed → Housekeeping;
- modified → Behaviour change.

Ý nghĩa:

### Breaking

Một contract bên ngoài binary có thể ngừng hoạt động mà không được compiler hoặc runtime báo sớm: profile data, launch script, Finch config, live website hoặc peer process.

Đây không phải khẳng định Samsung chắc chắn hỏng. Nó nói loại contract này phải được đối chiếu Samsung usage.

### Behaviour change

Windows build làm hoặc expose điều khác sau uprev. Có người dùng, site hoặc flow test có thể quan sát khác.

### New surface

Declaration/API/page/control mới tồn tại. Việc tồn tại không tự chứng minh Samsung cần adopt hoặc feature đã ON.

### Housekeeping

Upstream dọn flag, move declaration, đổi lịch hoặc evidence chưa đủ để nói breaking. Vẫn có thể tạo task config cleanup hoặc future planning.

## Bước 6: owner được phân loại thế nào

Owner là routing theo technical surface hoặc nơi cần sửa, không phải Chromium CODEOWNERS.

### Fallback theo kind

| Owner trong report | Fact kinds |
|---|---|
| `Process boundaries` (`ipc`) | 5 Mojo kinds |
| `Web platform` (`webplatform`) | Blink runtime, IDL interface/member |
| `Browser C++` (`native`) | base feature, FeatureParam, pref, switch, flags metadata |
| `WebUI front-end` (`webui`) | route, control, visibility gate |
| `Outside the repository` (`config`) | Chỉ đến từ signal override |

### Signal override sang config

Các signal sau luôn route `Outside the repository` vì fix/cleanup chính nằm ngoài Chromium declaration file:

```text
feature_string_renamed
switch_renamed
param_removed
param_rewired
flag_retired_on
flag_retired_off
killswitch_retired
flag_expiring
flag_expiry_moved
```

Ví dụ quan trọng:

- `switch_renamed`: external launch script phải đổi → config.
- `switch_symbol_renamed`: string CLI vẫn giữ, Samsung C++ reference đổi → Browser C++.
- `feature_string_renamed`: Finch/feature config phải đổi → config.
- `feature_symbol_renamed`: C++ reference phải đổi → Browser C++.
- `pref_renamed`: cần migration/registration/read fallback trong browser code → Browser C++.

Owner là nơi kiểm tra đầu tiên. Sau khi search Samsung usage, một finding có thể cần nhiều team cùng làm.

## Ví dụ chấm điểm đầy đủ

### Ví dụ A: feature bật mặc định trên Windows

```text
kind: base_feature
direction: modified
delta: windows disabled → enabled
signal: enabled_by_default
severity: 75
compiled on Windows: yes
coverage issue: none
score: 75
bucket: Behaviour change
owner: Browser C++
```

Việc tiếp theo: tìm Samsung patch/reference của feature, kiểm tra Finch override, chạy test flow chịu ảnh hưởng.

### Ví dụ B: Mojo method đổi signature

```text
kind: mojo_method
direction: modified
signal: ipc_signature_change
severity/score: 80
bucket: Breaking
owner: Process boundaries
```

Việc tiếp theo: tìm cả caller và implementation phía Samsung, kiểm tra generated binding/version compatibility và runtime tests qua process boundary.

### Ví dụ C: Mojo method chỉ đổi build attribute

```text
base severity cho mojo_method modified: 75
signal cụ thể: build_gate_changed
signal severity: 35
score: 35, không phải 75
```

Signal cụ thể thắng coarse prior. Đây là lý do bảng điểm có thể audit được.

### Ví dụ D: pref không còn trong default scan

```text
signal: pref_left_scan
severity: 35
coverage surface: dưới 95%
penalty: -15
score: 20
bucket: Housekeeping thay vì Breaking
reason: có thể key chỉ chuyển sang file target set chưa đọc
```

Chạy lại `wide` để xác nhận. Nếu wide thấy cùng C++ variable ở path mới, đó là move; nếu ghép được string mới, đó là rename; nếu vẫn mất với coverage đủ cao, removal đáng tin hơn.

### Ví dụ E: feature bị dọn sau khi đã ON

```text
signal: flag_retired_on
severity/score: 35
bucket: Housekeeping
owner: Outside the repository
```

Không nên mở bug “behaviour vừa bật”. Việc đúng là search Samsung rollout/config còn set flag hay không vì override đó sẽ không còn tác dụng.

### Ví dụ F: declaration Android-only ở cả hai version

```text
platform_state.windows: not_compiled → not_compiled
score: 0
bucket: Housekeeping
```

Finding vẫn tồn tại để audit nhưng không cạnh tranh với Windows work.

## Vì sao có thể tin nhưng không nên tin mù quáng

### Những điểm làm kết quả audit được

- Fact và Change là JSON deterministic, không phụ thuộc LLM.
- Mỗi score có `reasons`: severity đến từ signal nào, bị trừ vì sao.
- Signal table, bucket table, owner override và meaningful attrs nằm tập trung trong code.
- Test giữ signal severity và bucket có cùng key set; signal không thể rơi qua bucket mặc định mà không bị phát hiện.
- Same input tree phải tạo same Fact order; dedupe không dựa filesystem arrival.
- Diff từ chối target set khác nhau và snapshot lệch số Fact bất thường.
- Removal confidence dùng coverage đúng surface và đúng side.
- `path:line`, before/after, delta vẫn còn để reviewer mở source kiểm tra.

### Những điều điểm số không chứng minh

- Samsung code có reference symbol đó.
- Samsung build/runtime chắc chắn hỏng.
- Severity 80 luôn tốn công hơn severity 60.
- Parser đã hiểu mọi grammar Chromium có thể thêm trong tương lai.
- Default target set phủ implementation logic.
- Config ngoài repository đã được kiểm tra.

Vì thế report là ranked evidence và triage input, không phải auto-approval cho uprev.

## Đọc và filter report như thế nào

### Các field quan trọng trong JSON

```json
{
  "change": {
    "change_type": "modified",
    "kind": "mojo_method",
    "key": "network.mojom.Probe.Start",
    "before": {},
    "after": {},
    "deltas": {},
    "locations": ["path/to/file.mojom:42"],
    "signals": ["ipc_signature_change"],
    "severity": 80
  },
  "reasons": ["severity 80 — ..."],
  "score": 80,
  "bucket": "breaking",
  "enrichment": {}
}
```

Owner hiện được tính từ Change khi render/summarize, không lưu lặp trong từng Finding JSON. Nếu automation cần owner, phải dùng cùng `owner_of(change)` hoặc dùng dữ liệu hàng đã render trong HTML.

### Filter trong HTML

HTML có bốn filter độc lập và một search box:

- Bucket: Breaking / Behaviour / New surface / Housekeeping.
- Surface/kind: 16 Fact kinds, được group thành Behaviour switches, External contracts, UI and scheduling.
- Consequence group: ba nhóm trên.
- Owner: IPC, Web Platform, Browser C++, WebUI, Outside repository.
- Search: match name, raw kind, mô tả, screen/directory, signal, path và ChromeStatus summary.

Các filter kết hợp theo AND. Search không thay thế owner/kind filter. Mặc định sort score giảm dần; click header để đổi sort. Chỉ render 100 row đầu để report lớn vẫn phản hồi nhanh; nút `Show more` không làm mất dữ liệu. Click row mở signal, location, tối đa các delta chính, score reasons và enrichment.

### Luồng triage đề xuất

1. Kiểm tra refs, target set, coverage, missing targets và extraction errors.
2. Filter owner của team mình.
3. Xử lý Breaking score cao trước, nhưng đọc signal thay vì chỉ nhìn số.
4. Xem Behaviour change cho các flow Samsung customize.
5. Xem New surface để lập test/adoption backlog.
6. Cuối cùng xử lý Housekeeping thuộc config như flag retirement/expiry; không bỏ toàn bộ bucket.
