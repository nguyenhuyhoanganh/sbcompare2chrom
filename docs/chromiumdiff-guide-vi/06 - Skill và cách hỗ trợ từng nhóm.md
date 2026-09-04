# 6. Skill và agent hỗ trợ từng team như thế nào

Câu hỏi mà tài liệu này trả lời: **có thể giao cho một AI agent đọc báo cáo ChromiumDiff rồi tự tạo ra danh sách việc riêng cho từng team không?**

## Trả lời trực tiếp

Có. Khi gắn skill `analyzing-chromium-uprevs` vào một agent, agent có thể tạo báo cáo riêng cho WebUI và cho Browser C++/WebNative, đọc đúng ý nghĩa của từng signal, lần theo chuỗi gate, và giải thích những việc cần kiểm tra.

Nhưng câu trả lời có **hai mức**, và trộn hai mức này lại là sai lầm nguy hiểm nhất khi dùng agent:

| Có trong tay | Agent trả lời được tới đâu |
|---|---|
| Chỉ có hai version Chromium và báo cáo ChromiumDiff | **Upstream đã đổi gì, vì sao đáng chú ý, và team nào nên xem** |
| Có thêm source Samsung, build config, patch và cấu hình/rollout bên ngoài | **Samsung đang phụ thuộc ở chỗ nào, file nào cần sửa, test nào cần chạy** |

Không có source và config của Samsung mà vẫn nói "Samsung chắc chắn bị ảnh hưởng" là **vượt quá bằng chứng đang có**.

## Tool, skill và agent là ba lớp khác nhau

Ba từ này hay bị dùng lẫn lộn. Chúng là ba lớp xếp chồng, mỗi lớp làm một việc:

```text
ChromiumDiff tool
  lấy source → trích Fact → so sánh → sinh signal → chấm điểm → xuất báo cáo
        │
        ▼
Skill analyzing-chromium-uprevs
  quy định cách đọc báo cáo, các bẫy cần tránh, và câu hỏi đúng cho từng owner
        │
        ▼
Agent
  chạy tool, mở từng finding, tìm trong source/config Samsung,
  nối bằng chứng lại, viết kết luận cho từng team
        │
        ▼
Owner + tech lead + QA/config owner
  xác nhận ý đồ sản phẩm, công sức, kế hoạch test, và quyết định nhận việc
```

### Tool làm gì

Tool tạo ra bằng chứng cố định — chạy lại lần nào cũng ra như vậy:

- ref chính xác của hai bản upstream;
- coverage và trạng thái của bước lấy source;
- `Fact` trước và sau;
- `Change`, signal, severity, score, bucket;
- vị trí `path:line`;
- owner routing ban đầu.

Điểm cần nhấn mạnh: tool **không** dùng agent để quyết định một `Fact` là gì hay một score là bao nhiêu.

### Skill làm gì

Skill là playbook cho agent. Nó buộc agent tuân theo chín quy tắc:

- dùng full version chính xác, không dùng milestone mơ hồ cho kết luận chính thức;
- dùng trạng thái trên Windows, không dùng trạng thái global hay default;
- chọn `wide` khi câu hỏi ở mức release;
- đọc báo cáo theo owner và theo signal, thay vì nhìn tổng số dòng;
- phân biệt ba việc rất khác nhau: code của feature đã được đưa vào, feature thật sự đã được bật, và flag sau đó bị dọn đi;
- không áp dụng vòng đời của flag cho Mojo, pref hay switch, vì các contract đó không có gate;
- kiểm tra coverage trước khi gọi một khai báo là đã bị xoá;
- với WebUI, lần theo chuỗi guard của route → gate `loadTimeData` → feature đứng sau;
- nói rõ những nguồn mà tool không nhìn thấy được.

Skill **không** thêm dữ liệu nào. Nó chỉ giúp agent dùng dữ liệu sẵn có cho đúng.

### Agent làm gì

Agent có thể:

- chạy ChromiumDiff và đọc cả ba dạng JSON/HTML/Markdown;
- nhóm finding theo team, theo signal, theo màn hình hoặc theo chuỗi feature;
- mở đúng `path:line` phía upstream và đọc code xung quanh;
- tìm identifier, chuỗi, pref, route trong cây source Samsung;
- tìm bản vá riêng đang chạm vào cùng file hoặc cùng symbol;
- lần theo phía gọi và phía hiện thực của một Mojo interface;
- đề xuất ma trận test và các đầu việc ứng viên;
- phân biệt "đã xác nhận có dùng" với "chưa thấy trong phạm vi đã tìm".

Hai điều agent **không** được làm: tự truy cập repository hoặc config chưa được cấp quyền, và biến kết quả "tìm không thấy" thành bằng chứng tuyệt đối rằng Samsung không dùng.

## Đầu vào tối thiểu để agent làm việc đáng tin

```json
{
  "from_version": "full version cũ",
  "to_version": "full version mới",
  "platform": "Windows",
  "target_set": "wide cho việc review ở mức release",
  "samsung_src": "đường dẫn hoặc repository đã được cấp quyền",
  "samsung_build_config": "nếu tách khỏi source",
  "external_config_sources": [
    "cấu hình rollout/feature",
    "script khởi động",
    "automation",
    "ánh xạ policy cho doanh nghiệp"
  ],
  "team_scope": "WebUI | WebNative | IPC | Web Platform | all"
}
```

Nếu chỉ có báo cáo mà không có ba trường về source và config, vẫn chạy được — nhưng đầu ra bắt buộc phải dùng từ **"cần kiểm tra"**, không được dùng từ **"cần sửa"**.

## Agent nên đọc báo cáo theo thứ tự nào

1. Xác nhận `from_ref`, `to_ref`, platform và target set.
2. Đọc coverage theo từng surface, danh sách missing target và lỗi trích xuất.
3. Xem số lượng finding theo owner, để biết team nào có việc.
4. Trong mỗi owner, đi theo thứ tự: Breaking → Behaviour change → New surface.
5. Với Housekeeping, chỉ đọc kỹ các signal liên quan tới cấu hình và lịch trình — `flag_expiring`, các flag bị dọn, và các trường hợp đổi tên.
6. Mở từng finding có khả năng liên quan tới Samsung, đọc `locations`, `deltas`, `signals`, `reasons`.
7. Tìm trong source và config của Samsung, **rồi mới** gắn nhãn mức độ ảnh hưởng.

## Sáu mức kết luận agent nên dùng

Đây là thang đo để agent không nói quá bằng chứng đang có. Mỗi mức có một cách diễn đạt riêng:

| Mức | Bằng chứng đang có | Cách viết |
|---|---|---|
| Upstream fact | Chỉ có ChromiumDiff và source Chromium | "Upstream đã đổi…" |
| Đã tìm thấy tham chiếu ở Samsung | Tìm thấy đúng symbol, chuỗi hoặc đường dẫn trong source Samsung | "Samsung đang tham chiếu tại…" |
| Có khả năng bị ảnh hưởng | Tham chiếu nằm trên luồng build/runtime phù hợp, nhưng chưa test | "Có khả năng phải sửa hoặc kiểm thử…" |
| Đã xác nhận bị ảnh hưởng | Build, test hoặc tái hiện đã xác nhận | "Đã xác nhận ảnh hưởng…" |
| Chưa thấy tham chiếu trong phạm vi tìm | Tìm không ra trong nguồn được cấp | "Chưa thấy tham chiếu trong phạm vi đã tìm…" |
| Cần kiểm tra bên ngoài | Source không chứa cấu hình cần xác minh | "Cần owner của config kiểm tra…" |

Một cảnh báo cụ thể: **không được kết luận "an toàn" chỉ vì tìm chuỗi chính xác không ra.** Wrapper, code do máy sinh, symbol đã bị đổi tên trong fork, hoặc cấu hình nằm ở một hệ thống khác — tất cả đều có thể vẫn đang giữ dependency đó.

## Đội WebUI cần biết gì ở mỗi đợt uprev

### 1. Trang và điều hướng nào thay đổi

Từ `webui_route`, agent lấy ra năm thứ:

- route nào được thêm, route nào bị bỏ;
- URL hoặc path nào đổi;
- route cha nào đổi;
- danh sách guard nào đổi;
- một trang cũ và một trang mới có phải hai nửa của cùng một đợt migration không.

**Việc agent cần làm:**

1. Lọc owner `WebUI front-end` và kind `webui_route`.
2. Gom theo `surface` và theo trang.
3. Lần theo guard sang `webui_gate`.
4. Xem `base_feature` đứng sau đang BẬT hay TẮT trên Windows, ở cả hai version.
5. Tìm hằng route và path trong code WebUI của Samsung và trong các test điều hướng.

Đầu ra phải nói rõ **thời điểm người dùng nhìn thấy thay đổi**. Ví dụ: một route bị xoá ở M151, nhưng flag thay thế nó đã BẬT từ M148 — đây thường là bước dọn dẹp cuối của một đợt migration, chứ không phải giao diện vừa đổi ở M151.

### 2. Control nào thay đổi

Từ `webui_control`:

- control nào mới, control nào bị bỏ;
- toggle/dropdown/radio/input nào đổi loại;
- `id` hoặc khoá nhãn i18n nào liên quan;
- pref binding giữ nguyên hay chuyển sang khoá khác;
- điều kiện GRIT/build có đưa control ra hoặc vào bản Windows không;
- việc chuyển Polymer `.html` sang Lit `.html.ts` có giữ nguyên ngữ nghĩa của control không.

Trong nhóm này, `ui_control_repointed` phải được xem **trước** `ui_control_removed` và `ui_control_added`. Lý do: nó cho biết control vẫn còn nguyên đó nhưng đã bắt đầu ghi sang một pref khác — và hậu quả là setting cũ của người dùng bị bỏ lại.

**Agent cần tìm những gì:**

- template override hoặc component tuỳ biến của Samsung;
- event listener hoặc truy vấn theo element `id`;
- phần điều hướng route;
- chỗ đọc/ghi pref ở cả phía TypeScript lẫn phía C++;
- resource i18n, nếu khoá nhãn đã đổi;
- các test fixture và screenshot test hiện có của WebUI.

### 3. Điều kiện hiển thị nào thay đổi

Từ `webui_gate`:

- khoá `loadTimeData` nào được thêm hoặc bị bỏ;
- biểu thức C++ nào đổi;
- danh sách feature đứng sau nào đổi;
- `IsEnabled()` đổi, hoặc có thêm điều kiện về profile/policy.

Agent phải dựng đủ chuỗi liên kết này:

```text
trang hoặc control WebUI
    → khoá data của guard
    → biểu thức AddBoolean/Add* phía C++
    → base::Feature / pref / điều kiện policy
    → trạng thái trên Windows
```

Nếu chỉ đọc route và control mà không lần theo chuỗi trên, rất dễ gọi một phần tử là "đã bị xoá" trong khi nó chỉ đổi cách gate.

### 4. Pref nào ảnh hưởng tới giao diện

Team WebUI không nên chỉ xem owner `webui`. Các finding `pref_renamed`, `pref_symbol_renamed` và `build_gate_changed` thuộc về Browser C++ nhưng có thể ảnh hưởng trực tiếp tới control trong Settings.

Agent nên ghép theo `webui_control.attrs.pref`, rồi tìm năm thứ:

- chỗ đăng ký pref và giá trị mặc định của nó;
- quyền sở hữu từ phía sync hoặc policy;
- code migration cho khoá cũ;
- override mặc định của Samsung;
- những control nào khác cùng bind vào pref đó.

### 5. Kế hoạch test mà WebUI nên nhận

Với mỗi màn hình bị ảnh hưởng:

- route và deep link có mở được không;
- control có hiển thị đúng với bản build Windows và đúng trạng thái feature không;
- giá trị ban đầu có đọc đúng từ pref cũ hoặc pref mới không;
- thay đổi control có ghi đúng pref không;
- giá trị có tồn tại qua restart và qua profile không;
- trạng thái policy/managed, nếu có;
- accessibility, tên và tương tác bàn phím, khi loại control thay đổi;
- test về visual và layout cho danh sách rút gọn đã xác định.

Một giới hạn cần nhắc lại ở đây: ChromiumDiff không render giao diện. Vì vậy ảnh chụp màn hình dùng để **xác nhận danh sách rút gọn**, chứ không dùng để tự khám phá ra toàn bộ thay đổi.

### Mẫu đầu ra dành riêng cho WebUI

```markdown
## WebUI verdict
[Số màn hình có thay đổi người dùng thấy được; màn hình nào chỉ là dọn dẹp/migration.]

## Cần sửa hoặc xác minh
### settings › downloads_page
- Upstream đổi gì: ...
- Trạng thái gate/feature trên Windows: ...
- Tham chiếu phía Samsung: file:số dòng, hoặc "chưa thấy trong phạm vi đã tìm"
- Tác động dự kiến: ...
- Test cần chạy: ...

## Bề mặt mới cần cân nhắc
[Trang hoặc control mới, đang live hay còn bị gate.]

## Config/pref cần phối hợp với Browser C++
[Pref đổi tên, giá trị mặc định, đăng ký, policy.]

## Chưa phủ được
[Hành vi TypeScript, CSS/layout, chuỗi và cấu hình bên ngoài.]
```

## Đội WebNative / Browser C++ cần biết gì

Trước hết, một lưu ý về tên gọi: **`WebNative` không phải một owner chuẩn trong ChromiumDiff.** Trong phần này, nó được hiểu là team làm phần C++ backend và native integration của browser — bao gồm việc đấu nối feature, pref/switch, và phần C++ đứng sau WebUI.

Nếu nội bộ Samsung dùng từ "WebNative" cho một phạm vi khác, cần ánh xạ lại owner trước khi cho agent chạy.

### 1. Feature nào thực sự đổi hành vi trên Windows

Từ `base_feature` và `feature_param`:

- `disabled → enabled` hoặc ngược lại, trên Windows;
- feature mới BẬT ngay theo mặc định;
- feature ra hoặc vào bản build Windows;
- FeatureParam đổi giá trị mặc định, đổi kiểu, hoặc đổi feature sở hữu;
- C++ symbol đổi;
- feature string đổi — trường hợp này cần phối hợp với owner của config.

**Agent cần tìm:**

- các tham chiếu `features::k...` trong code Samsung;
- `FeatureList::IsEnabled` và `GetFieldTrialParam...`;
- override mặc định hoặc buildflag riêng của Samsung;
- việc tham số hoá trong test;
- cấu hình rollout đang dùng feature string hoặc tên param.

**Khi một flag bị xoá, bắt buộc phải đọc trạng thái trước đó của nó.** Ba signal, ba kết luận khác hẳn nhau:

| Signal | Nghĩa thật |
|---|---|
| `flag_retired_on` | Hành vi đã BẬT từ trước; release này chỉ dọn đi khả năng tắt |
| `flag_retired_off` | Thí nghiệm bị bỏ; đây **không** phải feature vừa bị tắt trong release này |
| `feature_deleted` | Trạng thái trước đó không rõ; cần đọc implementation và lịch sử sâu hơn |

### 2. Pref nào đổi contract với profile người dùng

Agent cần tách rõ sáu tình huống:

- **pref key đổi tên**: dữ liệu đang lưu có thể bị bỏ rơi; cần migration hoặc đọc fallback;
- **C++ symbol của pref đổi tên**: dữ liệu an toàn, nhưng tham chiếu trong code phải sửa;
- **pref biến mất nhưng chưa xác nhận**: chạy `wide`, hoặc tìm trong toàn bộ cây Chromium;
- **đăng ký, giá trị mặc định hoặc điều kiện platform đổi**;
- **control WebUI nào đang bind vào khoá đó**;
- **lớp policy hoặc sync nào có liên quan**.

Đầu việc sinh ra từ nhóm này có thể gồm: migration schema, copy giá trị từ khoá cũ sang khoá mới, dọn khoá cũ sau một khoảng ân hạn, test nâng cấp profile, và test pref ở chế độ managed.

### 3. Command-line switch nào ảnh hưởng tới tích hợp

Agent phải tìm ở cả năm nơi:

- launcher, updater và shortcut của Samsung;
- dòng lệnh trong test tự động;
- script CI;
- deployment cho doanh nghiệp;
- code C++ tự thêm switch vào dòng lệnh.

Quy tắc phân chia: **đổi tên chuỗi** thuộc phía cấu hình và script bên ngoài; **đổi tên symbol** thuộc phía C++.

Điều làm switch nguy hiểm: một switch không được nhận ra thường bị Chromium bỏ qua **im lặng**. Nghĩa là build và test không bảo đảm sẽ bắt được lỗi này.

### 4. Mojo nào chạm vào code riêng của Samsung

Mojo được route về owner `Process boundaries`, nhưng WebNative thường vẫn phải tham gia nếu Samsung có phía gọi hoặc phía hiện thực bằng native code.

Sáu bước agent cần làm:

1. Tìm tên đầy đủ của interface, method hoặc type trong cây source Samsung.
2. Xác định Samsung đang ở phía gọi, phía nhận, hay cả hai.
3. Kiểm tra hai đầu có luôn được sinh lại và build từ cùng một file mojom không.
4. Xem delta của signature, ordinal, kiểu của field trong struct, giá trị enum và `[MinVersion]`.
5. Kiểm tra trạng thái trên platform Windows.
6. Đề xuất build target và integration test đi qua đúng ranh giới process đó.

Kết luận phụ thuộc vào bước 3. Nếu cả hai đầu luôn được build từ cùng một nguồn và không có adapter nào nằm ngoài cây source, phần lớn thay đổi sẽ chỉ là công việc sửa cho compile được. Ngược lại, nếu Samsung có peer được đánh version riêng, có component tách rời, hoặc có serialization tuỳ biến, thì tương thích lúc chạy mới là vấn đề chính.

### 5. Phần native đứng sau WebUI

WebNative cần nhận các finding `webui_gate` và pref liên quan tới những màn hình mà Samsung có tuỳ biến:

- khoá `AddBoolean`/`Add*` đổi;
- biểu thức feature đổi;
- đăng ký hoặc giá trị mặc định của pref đổi;
- policy handler hoặc data source đổi;
- route/control cần một data key mới.

Đây là vùng giao nhau giữa WebUI front-end và Browser C++. Cách xử lý đúng: báo cáo chỉ định **một owner chính và một owner phối hợp**, chứ không đẩy cùng một task vào hai backlog mà không phân định ranh giới.

### 6. Kế hoạch test cho Browser C++ / WebNative

- build target chứa đúng symbol đã thay đổi;
- unit test cho cả trạng thái BẬT và TẮT, nếu flag vẫn còn tồn tại;
- test biên và test giá trị mặc định cho param;
- test nâng cấp profile cho trường hợp pref đổi tên;
- test launcher và automation cho switch;
- browser test cho điều kiện build trên Windows;
- integration test Mojo đi qua đúng process;
- browser test WebUI cho data source và gate phía C++;
- quy trình fallback hoặc kill-switch cho rollout, nếu feature trở thành vĩnh viễn.

### Mẫu đầu ra dành riêng cho WebNative

```markdown
## Browser C++ / WebNative verdict
[Các feature đổi trạng thái, các contract thay đổi, và rủi ro chính về config.]

## Việc build đã tìm thấy tham chiếu
- Finding + vị trí phía upstream
- Vị trí phía Samsung
- Dự kiến sửa gì
- Build target / test

## Hành vi runtime cần regression test
- Trạng thái Windows trước → sau
- Luồng nào của Samsung bị chạm
- Ma trận feature BẬT/TẮT hoặc ma trận migration pref

## IPC cần phối hợp
- Phía gọi / phía nhận / mô hình versioning
- Delta của signature và dữ liệu
- Test đi qua ranh giới process

## Config bên ngoài cần owner xác minh
- Feature string, param, switch, các flag đã bị dọn hoặc sắp hết hạn

## Chưa kết luận được
- Finding chỉ có bằng chứng upstream, hoặc coverage chưa đủ
```

## Web Platform là một hàng đợi riêng

Nếu trong tổ chức, "WebNative" không phải nơi sở hữu việc tương thích với website, thì **đừng gộp `Web platform` vào Browser C++.** Đây là một hàng đợi độc lập, cần biết sáu thứ:

- API nào đang stable trên Windows;
- interface hoặc member nào bị xoá hoặc đổi signature;
- API mới đang live hay còn bị gate;
- Origin Trial hoặc ngữ cảnh expose nào đã đổi;
- Samsung có bản vá Blink, shim tương thích, hoặc test hướng web nào chạm tới API đó không;
- bộ test regression trên site thật nào cần chạy.

Agent có thể dựng hàng đợi này từ `blink_runtime_feature`, `idl_interface` và `idl_member`, mà không ảnh hưởng gì tới cách route của WebUI và native.

## Ai tham gia ở bước nào

| Bước | Tool | Agent | Con người cần xác nhận |
|---|---|---|---|
| Xác định version, tải, trích xuất, so sánh, chấm điểm | Làm chính | Chạy và kiểm tra lỗi | Release owner xác nhận đúng hai full version |
| Giải thích signal và source upstream | Cung cấp bằng chứng | Làm chính | Domain owner review các ca khó |
| Tìm nơi Samsung đang dùng | Không làm | Làm chính, nếu được cấp source | Code owner xác nhận dependency thật |
| Tìm Finch/rollout/script/policy | Không làm | Chỉ khi được cấp nguồn | Owner của config/infra/enterprise |
| Ước lượng công sức và ưu tiên sprint | Không làm | Đề xuất | Tech lead hoặc team owner quyết định |
| Xác nhận build/runtime/giao diện | Không làm | Có thể chạy những test được cấp quyền | QA hoặc domain owner ký duyệt |

## Câu hỏi agent trả lời được và chưa trả lời được

### Trả lời được chỉ từ báo cáo ChromiumDiff

- Feature upstream nào đổi mặc định trên Windows?
- Khai báo Web API, Mojo, pref, switch hoặc WebUI nào đã đổi?
- Loại hậu quả là gì, và owner kỹ thuật nào phù hợp?
- Finding nào có bằng chứng "đã bị xoá" còn yếu vì coverage?
- Route và control nào cùng liên quan tới một gate hoặc một pref?
- Flag nào đã bị dọn hoặc sắp hết hạn, cần owner của config xem?

### Cần có source Samsung mới trả lời được

- Samsung có tham chiếu tới symbol, khoá hoặc interface đó không?
- Bản vá riêng có xung đột với khai báo hoặc file mới không?
- Phía gọi hoặc phía nhận nào của Mojo thuộc về Samsung?
- Màn hình WebUI nào đã bị fork hoặc override?
- Việc đổi tên pref cần migration ở module nào?

### Cần cấu hình bên ngoài repository mới trả lời được

- Feature string hoặc FeatureParam đó có đang được rollout không?
- Script khởi động hoặc automation còn truyền switch cũ không?
- Backend policy hoặc metadata của store có dùng khoá cũ không?

### Cần build/test/runtime mới trả lời được

- Finding này có thật sự gây lỗi build không?
- Thay đổi hành vi có đi qua luồng nào của Samsung không?
- Giao diện có bị lỗi visual hoặc layout không?
- Peer Mojo có tương thích trong mô hình triển khai thật không?

## Prompt mẫu để gắn cho agent

### WebUI

```text
Phân tích uprev Chromium <from_full_version> → <to_full_version> trên Windows.
Chạy ChromiumDiff target-set wide. Chỉ lập report cho WebUI, nhưng kéo thêm
base_feature và pref liên quan bằng route/control/gate chain. Với mỗi screen:
nói upstream đổi gì, Windows user có thấy khác không, Samsung source có reference
ở đâu, việc cần sửa hoặc test, và phần nào chưa xác minh. Không gọi một route
removed là user-visible change trước khi kiểm tra guard và backing feature.
```

### Browser C++ / WebNative

```text
Phân tích uprev Chromium <from_full_version> → <to_full_version> trên Windows.
Chạy ChromiumDiff target-set wide. Tạo queue Browser C++/WebNative gồm feature
state/param, pref, switch, C++ symbol và Mojo có Samsung reference. Tách rõ
build work, runtime behaviour, stored-profile migration và external config.
Flag retired phải đọc prior Windows state. Mọi kết luận Samsung bị ảnh hưởng
phải kèm Samsung path:line; nếu chỉ có upstream evidence, ghi là cần kiểm tra.
```

## Năm điều kiện để tin một báo cáo do agent tạo

Trước khi nhận kết luận của agent, tech lead chỉ cần kiểm tra năm điểm:

1. **Version và platform** — full version chính xác của cả hai bên, cùng chữ "Windows", được ghi ngay ở đầu báo cáo.
2. **Phạm vi** — kết luận ở mức release phải dùng `wide`; nếu dùng target set khác, giới hạn của nó phải được nói rõ.
3. **Bằng chứng cho mọi câu về Samsung** — mọi câu "Samsung dùng…" phải kèm `path:line` phía Samsung, hoặc một nguồn config cụ thể.
4. **Bằng chứng cho mọi kết luận đã bị xoá** — phải đã đọc coverage và lý do, không suy từ sự vắng mặt một cách mù quáng.
5. **Tách bạch bốn lớp** — báo cáo phải tách rõ: fact phía upstream, tác động lên sản phẩm, hành động, và test. Không trộn cả bốn vào một câu chắc chắn quá mức.

Skill làm cho agent nhất quán hơn, chứ không làm cho agent toàn tri. Giá trị lớn nhất của nó là biến một báo cáo hàng nghìn dòng thành một hàng đợi có bằng chứng cho từng team, đồng thời giữ cho kết luận không đi xa hơn dữ liệu thực sự được cấp.
