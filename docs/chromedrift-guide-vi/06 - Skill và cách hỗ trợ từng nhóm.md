# 6. Skill và agent hỗ trợ từng team như thế nào

## Câu trả lời trực tiếp

Có. Khi gắn skill `analyzing-chromium-uprevs` vào một agent, agent có thể tạo report riêng cho WebUI và Browser C++/WebNative, đọc đúng signal, theo chain gate và giải thích việc cần kiểm tra.

Nhưng có hai mức câu trả lời khác nhau:

1. Chỉ có hai Chromium version và ChromeDrift report: agent trả lời được **upstream đã đổi gì, vì sao đáng chú ý và team nào nên xem**.
2. Có thêm Samsung source, build config, patch và config/rollout bên ngoài: agent mới trả lời được **Samsung đang phụ thuộc chỗ nào, file nào cần sửa và test nào cần chạy**.

Không có Samsung source/config mà nói “Samsung chắc chắn bị ảnh hưởng” là vượt quá bằng chứng.

## Tool, skill và agent là ba lớp khác nhau

```text
ChromeDrift tool
  lấy source → trích Fact → diff → signal → score → report
        │
        ▼
Skill analyzing-chromium-uprevs
  quy định cách đọc report, tránh bẫy và hỏi đúng câu theo owner
        │
        ▼
Agent
  chạy tool, mở finding, search Samsung source/config, nối evidence,
  viết kết luận cho từng team
        │
        ▼
Owner + tech lead + QA/config owner
  xác nhận product intent, effort, test plan và quyết định nhận việc
```

### Tool làm gì

Tool tạo evidence deterministic:

- exact upstream refs;
- coverage và acquisition status;
- before/after Facts;
- Change, signal, severity, score, bucket;
- location `path:line`;
- owner routing ban đầu.

Tool không dùng agent để quyết định Fact hay score.

### Skill làm gì

Skill là playbook cho agent. Nó buộc agent:

- dùng exact full version, không dùng milestone mơ hồ cho kết luận chính thức;
- dùng Windows state thay vì global/default state;
- chọn `wide` cho release-level question;
- đọc report theo owner và signal thay vì nhìn raw row count;
- phân biệt feature code landed, feature actually turned on và flag later retired;
- không áp dụng lifecycle của flag cho Mojo/pref/switch, vì các contract này không có gate;
- kiểm tra coverage trước khi gọi một declaration là removed;
- theo route guard → `loadTimeData` gate → backing feature cho WebUI;
- báo rõ những nguồn tool không nhìn thấy.

Skill không thêm dữ liệu. Nó giúp agent dùng dữ liệu đúng cách.

### Agent làm gì

Agent có thể:

- chạy ChromeDrift và đọc JSON/HTML/Markdown;
- nhóm finding theo team, signal, screen hoặc feature chain;
- mở upstream `path:line` và đọc code xung quanh;
- search identifier/string/pref/route trong Samsung tree;
- tìm custom patch đang chạm cùng file hoặc symbol;
- theo caller/implementation của Mojo;
- đề xuất test matrix và task candidate;
- phân biệt “đã xác nhận usage” với “chưa thấy trong phạm vi search”.

Agent không thể tự truy cập repository/config chưa được cấp và không được biến “search không thấy” thành bằng chứng tuyệt đối rằng Samsung không dùng.

## Input tối thiểu để agent làm việc đáng tin

```json
{
  "from_version": "full version cũ",
  "to_version": "full version mới",
  "platform": "Windows",
  "target_set": "wide cho release review",
  "samsung_src": "path hoặc repository được cấp quyền",
  "samsung_build_config": "nếu tách khỏi source",
  "external_config_sources": [
    "rollout/feature config",
    "launch scripts",
    "automation",
    "enterprise policy mapping"
  ],
  "team_scope": "WebUI | WebNative | IPC | Web Platform | all"
}
```

Nếu chỉ có report, ba field source/config có thể bỏ nhưng output phải dùng từ “cần kiểm tra”, không dùng “cần sửa”.

## Agent cần đọc report theo thứ tự nào

1. Xác nhận `from_ref`, `to_ref`, platform và target set.
2. Đọc coverage theo surface, missing targets và extraction errors.
3. Xem owner counts để biết team nào có danh sách việc.
4. Trong mỗi owner: Breaking → Behaviour change → New surface.
5. Housekeeping chỉ đọc kỹ các signal liên quan config/lịch như `flag_expiring`, retirement và rename.
6. Mở từng finding có khả năng liên quan Samsung, đọc `locations`, `deltas`, `signals`, `reasons`.
7. Search Samsung source/config rồi mới gắn nhãn impact.

## Mức kết luận agent nên dùng

| Mức | Bằng chứng | Cách viết |
|---|---|---|
| Upstream fact | Chỉ có ChromeDrift + source Chromium | “Upstream đã đổi…” |
| Samsung reference found | Tìm thấy exact symbol/string/path ở Samsung | “Samsung đang reference tại…” |
| Likely affected | Reference nằm trên flow build/runtime phù hợp nhưng chưa test | “Có khả năng phải sửa/kiểm thử…” |
| Confirmed affected | Build/test/reproduction xác nhận | “Đã xác nhận ảnh hưởng…” |
| No reference found in scope | Search không thấy trong nguồn được cấp | “Chưa thấy reference trong phạm vi đã search…” |
| External check required | Source không chứa config cần xác minh | “Cần owner config kiểm tra…” |

Không nên dùng “safe” chỉ vì search exact string không thấy. Wrapper, generated code, renamed fork symbol hoặc config ở hệ thống khác vẫn có thể giữ dependency.

## Đội WebUI cần biết gì ở mỗi đợt uprev

### 1. Page và navigation nào thay đổi

Từ `webui_route`:

- route nào add/remove;
- URL/path đổi;
- parent route đổi;
- guard list đổi;
- page cũ và page mới có phải hai nửa của một migration không.

Action của agent:

1. Filter owner `WebUI front-end` và kind `webui_route`.
2. Group theo `surface` và page.
3. Theo guard sang `webui_gate`.
4. Xem backing `base_feature` đang ON/OFF trên Windows ở hai version.
5. Search route constant/path trong Samsung WebUI code và navigation tests.

Output nên nói rõ **thời điểm user-visible change**. Route bị xoá ở M151 nhưng flag thay thế đã ON từ M148 thường là cleanup của migration, không phải UI vừa đổi ở M151.

### 2. Control nào thay đổi

Từ `webui_control`:

- control mới hoặc bị remove;
- toggle/dropdown/radio/input đổi type;
- `id` hoặc i18n label key liên quan;
- pref binding giữ nguyên hay chuyển key;
- GRIT/build condition có đưa control vào/ra Windows không;
- Polymer `.html` sang Lit `.html.ts` có giữ cùng semantic control không.

`ui_control_repointed` phải được xem trước `ui_control_removed/added`, vì nó nói control vẫn ở đó nhưng bắt đầu ghi sang pref khác. Đây có thể làm setting cũ của user bị bỏ lại.

Agent cần search:

- Samsung template override/custom component;
- event listener hoặc query theo element `id`;
- route navigation;
- pref read/write phía TypeScript và C++;
- i18n resources nếu label key đổi;
- WebUI test fixture/screenshot test hiện có.

### 3. Visibility gate nào thay đổi

Từ `webui_gate`:

- `loadTimeData` key add/remove;
- expression C++ đổi;
- backing feature list đổi;
- `IsEnabled()` đổi hoặc thêm điều kiện profile/policy.

Agent phải dựng chain:

```text
WebUI page/control
    → guard data key
    → C++ AddBoolean/Add* expression
    → base::Feature / pref / policy condition
    → Windows state
```

Chỉ đọc route/control mà không theo chain này rất dễ gọi một phần tử “removed” khi nó chỉ đổi cách gate.

### 4. Pref nào ảnh hưởng UI

WebUI team không chỉ xem owner `webui`. Các finding `pref_renamed`, `pref_symbol_renamed`, `build_gate_changed` thuộc Browser C++ có thể trực tiếp ảnh hưởng setting control.

Agent nên join theo `webui_control.attrs.pref` và tìm:

- pref registration/default;
- sync/policy ownership;
- migration code cho key cũ;
- Samsung override của default;
- control nào cùng bind pref.

### 5. Test plan WebUI nên nhận

Cho mỗi screen bị ảnh hưởng:

- route/deep link mở được;
- control visible đúng với Windows build và feature state;
- initial value đúng từ pref cũ/mới;
- thay control có ghi đúng pref;
- restart/profile persistence;
- policy/managed state nếu có;
- accessibility/name/keyboard interaction khi control type đổi;
- visual/layout test cho shortlist đã xác định.

ChromeDrift không render UI, nên screenshot dùng để **xác nhận shortlist**, không dùng để tự khám phá toàn bộ thay đổi.

### Mẫu output riêng cho WebUI

```markdown
## WebUI verdict
[Số screen có thay đổi visible; screen nào chỉ cleanup/migration.]

## Cần sửa hoặc xác minh
### settings › downloads_page
- Upstream change: ...
- Gate/feature state trên Windows: ...
- Samsung reference: file:số dòng hoặc chưa thấy trong phạm vi search
- Tác động dự kiến: ...
- Test cần chạy: ...

## New surface để cân nhắc
[Page/control mới đang live hoặc còn gated.]

## Config/pref cần phối hợp Browser C++
[Pref rename, default, registration, policy.]

## Chưa phủ
[TypeScript behaviour, CSS/layout, external strings/config.]
```

## Đội WebNative/Browser C++ cần biết gì

Tên `WebNative` không phải owner chuẩn trong ChromeDrift. Trong phần này, nó được hiểu là team làm C++ backend/native integration của browser, bao gồm feature wiring, pref/switch và phần C++ đứng sau WebUI. Nếu nội bộ Samsung dùng “WebNative” cho phạm vi khác, cần map lại owner trước khi chạy agent.

### 1. Feature nào thực sự đổi hành vi trên Windows

Từ `base_feature` và `feature_param`:

- `disabled → enabled` hoặc `enabled → disabled` trên Windows;
- feature mới ON by default;
- feature ra/vào Windows build;
- FeatureParam default/type/owner đổi;
- C++ symbol đổi;
- feature string đổi và cần phối hợp config owner.

Agent cần search:

- `features::k...` reference trong Samsung code;
- `FeatureList::IsEnabled` và `GetFieldTrialParam...`;
- Samsung default override/buildflag;
- test parameterization;
- config/rollout dùng feature string hoặc param name.

Flag bị remove phải đọc prior state:

- `flag_retired_on`: behaviour đã ON từ trước, release này dọn khả năng tắt;
- `flag_retired_off`: experiment bị bỏ, không phải feature vừa tắt trong release;
- `feature_deleted`: state không rõ, cần đọc implementation/history sâu hơn.

### 2. Pref nào đổi contract với profile

Agent cần tách rõ:

- pref key rename: stored data có thể orphan, cần migration/read fallback;
- C++ pref symbol rename: data an toàn, code reference cần sửa;
- pref disappearance chưa confirmed: chạy `wide` hoặc search full Chromium tree;
- registration/default/platform guard đổi;
- WebUI control nào đang bind key;
- policy hoặc sync layer nào liên quan.

Work item có thể gồm schema migration, copy value từ old key sang new key, cleanup old key sau grace period, test profile upgrade và managed pref.

### 3. Command-line switch nào ảnh hưởng integration

Agent search cả:

- Samsung launcher/updater/shortcut;
- automated test command line;
- CI scripts;
- enterprise deployment;
- C++ code append switch.

String rename thuộc external config/launch side; symbol rename thuộc C++ side. Unknown switch thường bị Chromium bỏ qua im lặng nên build/test không đảm bảo bắt được.

### 4. Mojo nào chạm Samsung custom code

Mojo được route owner `Process boundaries`, nhưng WebNative thường phải tham gia nếu Samsung có caller/implementation native.

Agent cần:

1. Search qualified interface/method/type trong Samsung tree.
2. Xác định Samsung nằm ở caller, receiver hay cả hai.
3. Kiểm tra hai đầu có luôn regenerate/build từ cùng mojom không.
4. Xem signature, ordinal, struct field type, enum values và `[MinVersion]` delta.
5. Kiểm tra Windows platform state.
6. Đề xuất compile target và integration test đi qua đúng process boundary.

Nếu cả hai đầu luôn build từ cùng source và không có out-of-tree adapter, nhiều thay đổi sẽ thành compile work. Nếu Samsung có peer versioned, component tách rời hoặc custom serialization, runtime compatibility quan trọng hơn.

### 5. Native backend của WebUI

WebNative cần nhận các `webui_gate` và pref finding liên quan screen Samsung customize:

- `AddBoolean/Add*` key đổi;
- feature expression đổi;
- pref registration/default đổi;
- policy handler/data source đổi;
- route/control cần data key mới.

Đây là vùng giao nhau giữa WebUI front-end và Browser C++; report nên chỉ định một owner chính và một owner phối hợp, không đẩy cùng task sang hai backlog mà không có boundary.

### 6. Test plan Browser C++/WebNative

- build target chứa exact changed symbol;
- unit test feature ON và OFF nếu flag còn tồn tại;
- param boundary/default tests;
- profile upgrade test cho pref rename;
- launcher/automation test cho switch;
- browser test cho Windows build gate;
- Mojo integration test qua đúng process;
- WebUI browser test cho C++ data source/gate;
- rollout fallback/kill-switch procedure nếu feature trở thành permanent.

### Mẫu output riêng cho WebNative

```markdown
## Browser C++ / WebNative verdict
[Feature flips, contract changes và config risks chính.]

## Build work đã tìm thấy reference
- Finding + upstream location
- Samsung locations
- Sửa dự kiến
- Target/test

## Runtime behaviour cần regression test
- Windows state trước → sau
- Flow Samsung bị chạm
- Feature ON/OFF hoặc pref migration matrix

## IPC cần phối hợp
- Caller / receiver / versioning model
- Signature/data delta
- Test qua boundary

## External config cần owner xác minh
- Feature strings, params, switches, retired/expiring flags

## Chưa kết luận
- Finding chỉ có upstream evidence hoặc coverage chưa đủ
```

## Web Platform là một queue riêng

Nếu “WebNative” trong tổ chức không sở hữu compatibility với website, đừng gộp `Web platform` vào Browser C++. Queue này cần biết:

- API nào stable trên Windows;
- interface/member nào remove hoặc đổi signature;
- API mới live hay còn gated;
- Origin Trial/exposure context nào đổi;
- Samsung có Blink patch, compatibility shim hoặc web-facing test nào chạm API;
- site regression suite nào cần chạy.

Agent có thể tạo queue này từ `blink_runtime_feature`, `idl_interface` và `idl_member` mà không ảnh hưởng cách route WebUI/native.

## Ai tham gia ở bước nào

| Bước | Tool | Agent | Con người cần xác nhận |
|---|---|---|---|
| Resolve version, fetch, extract, diff, score | Chính | Chạy và kiểm tra lỗi | Release owner xác nhận exact versions |
| Giải thích signal/upstream source | Cung cấp evidence | Chính | Domain owner review case khó |
| Tìm Samsung reference | Không | Chính nếu được cấp source | Code owner xác nhận dependency thực |
| Tìm Finch/rollout/script/policy | Không | Chỉ khi được cấp nguồn | Config/infra/enterprise owner |
| Ước lượng effort và ưu tiên sprint | Không | Đề xuất | Tech lead/team owner quyết định |
| Xác nhận build/runtime/UI | Không | Có thể chạy test được cấp | QA/domain owner sign-off |

## Câu hỏi agent trả lời được và chưa trả lời được

### Trả lời được chỉ từ ChromeDrift report

- Upstream feature nào đổi default trên Windows?
- Web API/Mojo/pref/switch/WebUI declaration nào đổi?
- Loại hậu quả và technical owner nào phù hợp?
- Finding nào có bằng chứng removal yếu do coverage?
- Route/control nào liên quan cùng gate hoặc pref?
- Flag nào retired/expiring cần config owner xem?

### Cần Samsung source

- Samsung có reference symbol/key/interface đó không?
- Custom patch có conflict với declaration/file mới không?
- Caller/receiver nào của Mojo thuộc Samsung?
- WebUI screen nào đã fork/override?
- Pref rename cần migration ở module nào?

### Cần config ngoài repository

- Feature string/FeatureParam có đang được rollout không?
- Launch/automation còn truyền switch cũ không?
- Policy backend/store metadata có dùng key cũ không?

### Cần build/test/runtime verification

- Finding có thực sự gây build failure?
- Behaviour change có đi qua Samsung flow không?
- UI có visual/layout regression không?
- Mojo peer có tương thích trong deployment model thật không?

## Prompt mẫu để gắn cho agent

### WebUI

```text
Phân tích uprev Chromium <from_full_version> → <to_full_version> trên Windows.
Chạy ChromeDrift target-set wide. Chỉ lập report cho WebUI, nhưng kéo thêm
base_feature và pref liên quan bằng route/control/gate chain. Với mỗi screen:
nói upstream đổi gì, Windows user có thấy khác không, Samsung source có reference
ở đâu, việc cần sửa hoặc test, và phần nào chưa xác minh. Không gọi một route
removed là user-visible change trước khi kiểm tra guard và backing feature.
```

### Browser C++/WebNative

```text
Phân tích uprev Chromium <from_full_version> → <to_full_version> trên Windows.
Chạy ChromeDrift target-set wide. Tạo queue Browser C++/WebNative gồm feature
state/param, pref, switch, C++ symbol và Mojo có Samsung reference. Tách rõ
build work, runtime behaviour, stored-profile migration và external config.
Flag retired phải đọc prior Windows state. Mọi kết luận Samsung bị ảnh hưởng
phải kèm Samsung path:line; nếu chỉ có upstream evidence, ghi là cần kiểm tra.
```

## Điều kiện để tin report do agent tạo

Trước khi nhận kết luận, tech lead chỉ cần kiểm tra năm điểm:

1. Exact full versions và Windows được ghi ở đầu.
2. Release verdict dùng `wide`, hoặc giới hạn của target set khác được nói rõ.
3. Mọi câu “Samsung dùng” có Samsung `path:line` hoặc nguồn config cụ thể.
4. Mọi removal đều đã đọc coverage/reason, không suy từ absence mù quáng.
5. Report tách upstream fact, product impact, action và test; không trộn chúng thành một câu chắc chắn quá mức.

Skill làm agent nhất quán hơn, không làm agent toàn tri. Giá trị lớn nhất là biến report hàng nghìn row thành queue có bằng chứng cho từng team và giữ cho kết luận không đi xa hơn dữ liệu được cấp.
