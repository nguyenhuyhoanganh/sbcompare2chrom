# Kiến trúc và luồng chạy của ChromeDrift

> Tài liệu đọc hiểu implementation hiện tại của project `sbcompare2chrom`  
> Phạm vi kiểm tra: mã nguồn đang có trong workspace, schema `40`  
> Ngày đối chiếu: 2026-08-24

## Kết luận ngắn

ChromeDrift là một máy so sánh có quy tắc cố định. Nó đọc một số dạng khai báo trong hai phiên bản Chromium, biến mỗi khai báo thành một bản ghi chuẩn gọi là `Fact`, so hai tập `Fact`, gắn nhãn ý nghĩa, chấm mức ưu tiên và sinh báo cáo.

Skill `analyzing-chromium-uprevs` là lớp hướng dẫn cho AI hoặc người phân tích sử dụng báo cáo đó. Skill không phải parser và cũng không tự chạy bên trong ChromeDrift. Phần phân chia trách nhiệm này được ghi ngay trong [SKILL.md:8](/Users/m/project/sbcompare2chrom/skills/analyzing-chromium-uprevs/SKILL.md:8) và [cli.py:9](/Users/m/project/sbcompare2chrom/chromedrift/cli.py:9).

Thiết kế này hợp lý nếu mục tiêu là:

- tìm nhanh các thay đổi quan trọng trong một lần nâng phiên bản Chromium;
- tạo bằng chứng có thể mở lại tại `file:line`;
- xếp thứ tự để con người không phải đọc hàng nghìn file diff;
- làm đầu vào cho bước kiểm tra source browser riêng của công ty.

Thiết kế này không đủ để tự động kết luận “browser của công ty chắc chắn tương thích” hoặc dùng như release gate duy nhất. ChromeDrift không đọc toàn bộ cú pháp Chromium, không hiểu mọi thân hàm và không biết fork của công ty đang dùng khai báo nào.

---

## Mục lục

1. Mục tiêu và giới hạn đề tài
2. Các khái niệm cần hiểu trước
3. Kiến trúc tổng thể
4. Luồng chạy từ đầu đến cuối
5. ChromeDrift xác định file cần đọc như thế nào
6. Danh sách target và pattern đầy đủ
7. Chín bộ đọc: gồm những bộ nào và vì sao là chín
8. Chuẩn hóa về `Fact`
9. So sánh hai snapshot thành `Change`
10. Signal, severity, bucket, owner và score
11. Cluster và báo cáo
12. Luồng riêng khi chỉ quan tâm Settings
13. Guard rail, giới hạn và rủi ro cần trình bày
14. Cách đánh giá phương án trước hội đồng kỹ thuật
15. Bản đồ source code

---

## 1. Mục tiêu và giới hạn đề tài

### 1.1. Bài toán được giải

Tên phạm vi nên trình bày là:

> So sánh thay đổi trên các bề mặt khai báo của Chromium Desktop Windows giữa hai phiên bản chính xác, chuẩn hóa chúng thành bằng chứng có cấu trúc và xếp thứ tự để hỗ trợ đánh giá ảnh hưởng khi nâng phiên bản browser riêng.

“Bề mặt khai báo” ở đây là những nơi source công bố một feature, API, hợp đồng giao tiếp, pref, switch, route hoặc control. Công cụ ưu tiên các nơi này vì chúng có cấu trúc tương đối ổn định và có thể đọc mà không cần build toàn bộ Chromium.

### 1.2. Trong phạm vi

- Hai version Chromium phải được pin chính xác, ví dụ `148.0.7778.217` và `151.0.7922.138`, không chỉ ghi `148` và `151`. Skill yêu cầu điều này tại [SKILL.md:47](/Users/m/project/sbcompare2chrom/skills/analyzing-chromium-uprevs/SKILL.md:47).
- Chromium desktop cho Windows. Platform đang được cố định thành `windows` tại [_cpp.py:35](/Users/m/project/sbcompare2chrom/chromedrift/extract/_cpp.py:35).
- Ba nhóm ý nghĩa và 16 loại `Fact` đang được code khai báo tại [model.py:454](/Users/m/project/sbcompare2chrom/chromedrift/model.py:454).
- Chín loại nguồn: feature/param, Blink runtime feature, Blink Web IDL, Mojo, pref/switch, flag metadata, WebUI route, WebUI control và WebUI gate.
- Tải source từ Chromium Gitiles hoặc đọc từ hai checkout local; hai cơ chế cùng tuân theo giao diện `Source` tại [acquire.py:192](/Users/m/project/sbcompare2chrom/chromedrift/acquire.py:192).
- Đo coverage theo file và theo từng bề mặt.
- Kiểm tra các liên kết khai báo: route → gate → feature, control → pref, Blink runtime → base feature và feature param → base feature tại [catalog.py:204](/Users/m/project/sbcompare2chrom/chromedrift/catalog.py:204).
- Semantic diff, signal, severity, bucket, owner, score, cluster và ba dạng report.
- Bằng chứng `path:line` để người review mở đúng vị trí Chromium.
- AI hoặc kỹ sư đọc báo cáo rồi tìm identifier trong fork của công ty để xác nhận tác động thực tế.

### 1.3. Ngoài phạm vi

- Android, iOS, ChromeOS Settings. Desktop Settings và mobile Settings là các implementation khác nhau; tài liệu của skill nói rõ tại [settings-surface.md:13](/Users/m/project/sbcompare2chrom/skills/analyzing-chromium-uprevs/reference/settings-surface.md:13).
- Nội dung thay đổi bên trong thân hàm C++ nếu không làm thay đổi một khai báo mà extractor nhận ra.
- Logic TypeScript tổng quát, event handler, import graph và call graph.
- `chrome/browser/resources/settings/page_visibility.ts`; đây là file cần đọc thủ công khi câu hỏi là trang có hiện hay không, theo [settings-surface.md:25](/Users/m/project/sbcompare2chrom/skills/analyzing-chromium-uprevs/reference/settings-surface.md:25).
- `BUILD.gn` và dependency graph đầy đủ. Việc lọc platform dựa vào guard/path convention, không phải kết quả build thật.
- CSS, layout, icon, ảnh chụp, visual regression, accessibility, hiệu năng và runtime test.
- Giá trị chuỗi giao diện trong `.grd` hoặc hệ thống i18n đầy đủ.
- Finch rollout phía server, enterprise deployment, launch script, test automation và policy nằm ngoài source đã đọc.
- Chrome Extensions IDL và MIDL; extractor Web IDL chỉ nhận file trong Blink.
- Năm nhóm cú pháp đã được chính skill công bố là chưa tạo Fact: Web IDL `callback`, `typedef`, quan hệ `Interface includes Mixin`, Mojo `feature` block và Mojo constant; xem [SKILL.md:237](/Users/m/project/sbcompare2chrom/skills/analyzing-chromium-uprevs/SKILL.md:237).
- Tự động chứng minh fork browser của công ty có sử dụng một contract hay không.
- Tự động đưa ra quyết định cuối cùng “được release” hoặc “không được release”.

### 1.4. Tiêu chí hoàn thành hợp lý cho một lần phân tích

- FROM và TO trỏ đúng hai source tree/version cần so.
- Hai snapshot dùng cùng `target_set`, cùng partition và cùng chế độ `complete`.
- Không có missing target hoặc parser error chưa được giải thích.
- Coverage của cả FROM và TO được đưa vào báo cáo.
- Mọi kết luận quan trọng có `path:line`.
- Mọi unresolved reference được giải quyết hoặc ghi thành giới hạn.
- Với quyết định nâng version chính thức, có một lần chạy `wide` không partition.
- Có bước tìm identifier trong source fork của công ty.
- Có test build/runtime có mục tiêu cho danh sách rủi ro còn lại.
- Báo cáo phân biệt ba mức: “đã phát hiện source thay đổi”, “có khả năng ảnh hưởng” và “đã xác nhận ảnh hưởng sản phẩm”.

---

## 2. Các khái niệm cần hiểu trước

| Từ dùng trong project | Nghĩa đơn giản | Ví dụ |
|---|---|---|
| Skill | Tài liệu hướng dẫn AI/người phân tích phải làm và phải kiểm tra gì | `skills/analyzing-chromium-uprevs/SKILL.md` |
| ChromeDrift | Chương trình Python đọc và so sánh source Chromium | package `chromedrift/` |
| Target | Một file hoặc một thư mục được phép tải/đọc | `chrome/common/pref_names.h` hoặc tree `third_party/blink/public/mojom` |
| Extractor, hay “bộ đọc” | Parser nhỏ, nhận một dạng file và trả về các Fact | bộ đọc `mojom` đọc `.mojom` |
| Fact | Một khai báo đã được đổi thành bản ghi có định danh ổn định | pref key `download.prompt_for_download` |
| Snapshot | Toàn bộ Fact thu được từ một version trong phạm vi đã chọn | Snapshot của Chromium 148 |
| Change | Kết quả ghép cùng Fact giữa hai snapshot: added, removed hoặc modified | Mojo method đổi signature |
| Signal | Nhãn giải thích điều gì đã xảy ra | `ipc_signature_change` |
| Severity | Mức độ lý thuyết của loại thay đổi, từ 0 đến 100 | Mojo signature đổi là 80 |
| Score | Severity sau khi xét Windows và độ đầy đủ của chính lần chạy | 80 hoặc bị trừ còn 65 |
| Bucket | Nhóm hậu quả | Breaking, Behaviour change, New surface, Housekeeping |
| Owner | Nhóm nên kiểm tra/sửa | ipc, webplatform, native, webui, config |
| Cluster | Một nhóm finding có liên kết khai báo trực tiếp | route + gate + base feature |
| Coverage | Tỷ lệ file có khả năng chứa khai báo mà target hiện tại thực sự đọc | `read / candidates` |

### 2.1. API khác Mojo như thế nào

Trong báo cáo này, “Web API” chủ yếu có nghĩa là Web IDL của Blink: hợp đồng mà JavaScript trên website có thể gọi, ví dụ một interface `Gamepad` và method `vibrate()`. Bộ đọc chỉ nhận `.idl` dưới `third_party/blink/renderer/`, theo [web_idl.py:100](/Users/m/project/sbcompare2chrom/chromedrift/extract/web_idl.py:100).

Mojo là ngôn ngữ mô tả thông điệp giữa các process hoặc component native trong Chromium. Nó mô tả interface, method, struct, field và enum trên đường truyền IPC. Bộ đọc nhận mọi `.mojom` nằm trong target đã tải, theo [mojom.py:130](/Users/m/project/sbcompare2chrom/chromedrift/extract/mojom.py:130).

Vì vậy:

- Web IDL trả lời: “Website có thể gọi gì từ JavaScript?”
- Mojo trả lời: “Hai phía native/process gửi cho nhau message có hình dạng gì?”
- Một file Mojo có thể được dùng giữa WebUI và native, chẳng hạn file trong `chrome/browser/ui/webui/downloads/`, nên trong trường hợp đó có thể gọi nó là hợp đồng WebUI ↔ native.
- Nhưng Mojo không chỉ dành cho WebUI. Có hàng nghìn `.mojom` cho renderer, network, GPU, Blink và các service khác.

Nói ngắn gọn trước hội đồng: **Web IDL là API hướng ra website; Mojo là contract IPC bên trong kiến trúc Chromium. Cả hai đều là hợp đồng, nhưng khác đối tượng sử dụng và khác ranh giới hệ thống.**

### 2.2. Flag, base feature, pref, switch, Settings và WebUI

- `base::Feature`: công tắc hành vi được compile trong Chromium, thường có trạng thái mặc định enabled hoặc disabled.
- Blink runtime feature: trạng thái cho một capability của web platform, có thể là test, experimental hoặc stable.
- `chrome://flags` entry: metadata về một lựa chọn trong trang flags, trong project này chủ yếu dùng để biết mốc hết hạn.
- Pref: key lưu cấu hình trong profile, ví dụ `download.prompt_for_download`.
- Command-line switch: tham số lúc khởi động browser, ví dụ `--disable-gpu`.
- Settings: màn hình `chrome://settings`; trên desktop nó là WebUI gồm TypeScript/HTML được C++ phục vụ.
- WebUI route: đường dẫn của một trang bên trong `chrome://`.
- WebUI control: toggle, dropdown, radio group hoặc custom element người dùng tương tác.
- WebUI gate: giá trị `loadTimeData` mà C++ đẩy sang frontend, thường dùng để ẩn/hiện route hay control.

---

## 3. Kiến trúc tổng thể

### 3.1. Hai lớp có trách nhiệm khác nhau

```text
┌──────────────────────────────────────────────────────────────────────┐
│ LỚP 1 — AGENT SKILL                                                  │
│                                                                      │
│ User: "So sánh Chromium 148.0.7778.217 → 151.0.7922.138"             │
│                           │                                          │
│                           ▼                                          │
│              Chốt FROM / TO / Windows / phạm vi                     │
│                           │                                          │
│                           ▼                                          │
│                 Gọi chương trình ChromeDrift                         │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│ LỚP 2 — CHROMEDRIFT, DETERMINISTIC ENGINE                            │
│                                                                      │
│      Chromium FROM                         Chromium TO                │
│            │                                    │                    │
│            ▼                                    ▼                    │
│   Target → Extractor → Fact             Target → Extractor → Fact    │
│            │                                    │                    │
│            ▼                                    ▼                    │
│       Snapshot FROM                         Snapshot TO               │
│            └──────────────────┬─────────────────┘                    │
│                               ▼                                      │
│                 Semantic diff → Change                               │
│                               ▼                                      │
│          Signal → Severity → Bucket → Owner → Score                  │
│                               ▼                                      │
│                    Cluster + enrichment                              │
│                               ▼                                      │
│               report.json / report.md / report.html                  │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────┐
│ LỚP 1 — AGENT SKILL TIẾP TỤC                                         │
│                                                                      │
│ Đọc report → đối chiếu fork công ty → giải thích → đề xuất test      │
│ → con người quyết định có nâng version hay không                     │
└──────────────────────────────────────────────────────────────────────┘
```

### 3.2. Các module chính

| Khối | Trách nhiệm | Source chính |
|---|---|---|
| Agent skill | Chốt input, gọi tool, đọc report, tránh kết luận sai và trình bày theo owner | [SKILL.md:37](/Users/m/project/sbcompare2chrom/skills/analyzing-chromium-uprevs/SKILL.md:37) |
| CLI | Điều phối toàn bộ pipeline | [cli.py:93](/Users/m/project/sbcompare2chrom/chromedrift/cli.py:93) |
| Acquire | Đọc Gitiles hoặc checkout local, materialize file/tree target | [acquire.py:192](/Users/m/project/sbcompare2chrom/chromedrift/acquire.py:192) |
| Targets | Định nghĩa target set, discovery, coverage và partition | [targets.py:1](/Users/m/project/sbcompare2chrom/chromedrift/targets.py:1) |
| Snapshot | Resolve version, tải source, chạy extractor, lưu cache | [snapshot.py:62](/Users/m/project/sbcompare2chrom/chromedrift/snapshot.py:62) |
| Extract registry | Đăng ký và gọi chín bộ đọc | [extract/__init__.py:32](/Users/m/project/sbcompare2chrom/chromedrift/extract/__init__.py:32) |
| Model | Định nghĩa Fact, Snapshot, Change, Finding, Report | [model.py:589](/Users/m/project/sbcompare2chrom/chromedrift/model.py:589) |
| Catalog | Đo coverage và kiểm tra reference closure | [catalog.py:204](/Users/m/project/sbcompare2chrom/chromedrift/catalog.py:204) |
| Diff | Ghép Fact, tạo delta, signal, severity, bucket và owner | [diff.py:673](/Users/m/project/sbcompare2chrom/chromedrift/diff.py:673) |
| Score | Điều chỉnh độ ưu tiên theo Windows và evidence của lần chạy | [score.py:242](/Users/m/project/sbcompare2chrom/chromedrift/score.py:242) |
| Cluster | Nối các finding liên quan bằng liên kết khai báo | [cluster.py:94](/Users/m/project/sbcompare2chrom/chromedrift/cluster.py:94) |
| Report | Render JSON, Markdown và HTML | [cli.py:232](/Users/m/project/sbcompare2chrom/chromedrift/cli.py:232) |

### 3.3. Điểm vào chương trình

Khi chạy `python3 -m chromedrift`, Python vào [__main__.py:1](/Users/m/project/sbcompare2chrom/chromedrift/__main__.py:1), gọi [cli.py:671](/Users/m/project/sbcompare2chrom/chromedrift/cli.py:671), parse command rồi gọi `cmd_run` nếu subcommand là `run`.

---

## 4. Luồng chạy từ đầu đến cuối

### Bước 0 — Nhận input và chốt phạm vi

Input tối thiểu:

- `FROM`: version/ref cũ;
- `TO`: version/ref mới;
- nguồn Gitiles hoặc hai source checkout;
- `target-set`: `minimal`, `default` hoặc `wide`;
- partition nếu chỉ điều tra một vùng;
- output directory.

Các option được khai báo tại [cli.py:542](/Users/m/project/sbcompare2chrom/chromedrift/cli.py:542). Với hai source local khác nhau, dùng:

```bash
python3 -m chromedrift run 148.0.7778.217 151.0.7922.138 \
  --from-src /path/to/chromium-148/src \
  --to-src /path/to/chromium-151/src \
  --target-set wide \
  --no-enrich \
  --out out/M148_to_M151
```

Không dùng một checkout cho cả hai version trừ khi chính checkout đó thực sự thay đổi theo từng bước bên ngoài lệnh. `--from-src` và `--to-src` tồn tại để tránh lỗi này; xem [cli.py:581](/Users/m/project/sbcompare2chrom/chromedrift/cli.py:581).

### Bước 1 — Resolve ref và kiểm tra cache snapshot

`build_snapshot` đổi ref thành ref cụ thể và milestone, sau đó tính đường dẫn cache dựa trên ref, target set, partition và `complete`. Snapshot cache chỉ được dùng nếu schema trùng schema hiện tại; xem [snapshot.py:62](/Users/m/project/sbcompare2chrom/chromedrift/snapshot.py:62).

Ý nghĩa: cùng một version nhưng khác target set không được coi là cùng một snapshot.

### Bước 2 — Tạo danh sách target thực sự sẽ tải

`get_targets` chọn một trong ba target set, sau đó mới lọc theo partition hoặc thay bằng complete targets; xem [targets.py:752](/Users/m/project/sbcompare2chrom/chromedrift/targets.py:752).

Mỗi target là:

```text
FetchTarget(path, kind, include, note)

path    = file hoặc directory trong Chromium src
kind    = file hoặc tree
include = danh sách suffix được giữ khi giải nén/copy tree
note    = mô tả cho người đọc log
```

Định nghĩa thật nằm tại [acquire.py:426](/Users/m/project/sbcompare2chrom/chromedrift/acquire.py:426).

### Bước 3 — Discovery để đo coverage

ChromeDrift lấy recursive listing của các discovery root, hỏi trực tiếp từng extractor xem file nào “có thể chứa declaration mà nó đọc”, rồi tạo:

- `candidates`: mỗi file được tính một lần trong coverage tổng;
- `memberships`: một file có thể thuộc nhiều extractor/surface;
- `missed`: candidate không được target hiện tại chạm tới.

Thuật toán nằm tại [targets.py:241](/Users/m/project/sbcompare2chrom/chromedrift/targets.py:241), coverage được tính tại [targets.py:325](/Users/m/project/sbcompare2chrom/chromedrift/targets.py:325).

Discovery **không tự thêm file vào target tải**. Nó chỉ làm lỗ hổng trở nên nhìn thấy được. Lý do implementation ghi rõ: tải khoảng một nghìn file bằng request riêng mất gần 17 phút mỗi version, còn directory archive khoảng 3 phút; xem [targets.py:249](/Users/m/project/sbcompare2chrom/chromedrift/targets.py:249).

### Bước 4 — Materialize source

- Với Gitiles: file target được fetch riêng; tree target dùng `.tar.gz`, giải nén và chỉ giữ suffix cần thiết tại [acquire.py:305](/Users/m/project/sbcompare2chrom/chromedrift/acquire.py:305).
- Với local checkout: file được copy; tree được copy có filter tại [acquire.py:403](/Users/m/project/sbcompare2chrom/chromedrift/acquire.py:403).

Nếu mọi target đều missing, pipeline dừng thay vì tạo snapshot rỗng; xem [snapshot.py:135](/Users/m/project/sbcompare2chrom/chromedrift/snapshot.py:135).

### Bước 5 — Chạy chín bộ đọc trên tree đã materialize

`run_on_tree` đi qua file theo thứ tự ổn định, áp dụng ba chốt:

1. file phải thuộc product scope;
2. file phải nằm trong target scope của lần chạy hiện tại;
3. ít nhất một extractor phải trả về `applies_to(path) == true`.

Một file có thể được nhiều extractor đọc. Sau đó extractor trả về danh sách Fact. Code điều phối ở [extract/__init__.py:123](/Users/m/project/sbcompare2chrom/chromedrift/extract/__init__.py:123), đoạn matching ở [extract/__init__.py:168](/Users/m/project/sbcompare2chrom/chromedrift/extract/__init__.py:168).

### Bước 6 — Chuẩn hóa platform, loại Fact trùng và tạo Snapshot

- Fact chỉ nằm trong directory platform khác được gắn `platform_state.windows = not_compiled` tại [extract/__init__.py:201](/Users/m/project/sbcompare2chrom/chromedrift/extract/__init__.py:201).
- Fact trùng UID được xử lý xác định; Web IDL overload được gom thành tập signatures tại [model.py:916](/Users/m/project/sbcompare2chrom/chromedrift/model.py:916).
- Snapshot lưu facts, ref, milestone, coverage, target set, missing targets và extractor stats tại [snapshot.py:161](/Users/m/project/sbcompare2chrom/chromedrift/snapshot.py:161).

Hai phía FROM và TO chạy cùng quy trình này tại [cli.py:103](/Users/m/project/sbcompare2chrom/chromedrift/cli.py:103).

### Bước 7 — Kiểm tra reference closure và scope

Sau khi có snapshot TO, ChromeDrift tìm các link đã extract nhưng không tìm thấy đích:

- route guard không có gate;
- gate gọi feature nhưng không có base feature;
- control bind pref nhưng không có pref;
- Blink runtime khai báo base feature nhưng không có base feature;
- feature param không tìm thấy owner feature.

Code ở [catalog.py:235](/Users/m/project/sbcompare2chrom/chromedrift/catalog.py:235). Hiện tại closure chỉ được tính cho snapshot TO tại [cli.py:114](/Users/m/project/sbcompare2chrom/chromedrift/cli.py:114), không có closure độc lập cho FROM.

Đồng thời pipeline kiểm tra stale cache không làm lọt file ngoài target scope tại [cli.py:120](/Users/m/project/sbcompare2chrom/chromedrift/cli.py:120).

### Bước 8 — Semantic diff hai snapshot

Hai Fact được ghép bằng `uid = kind:key`. Kết quả là added, removed hoặc modified. Chỉ các attrs có ý nghĩa mới được so; path được so riêng, line chỉ làm bằng chứng. Thuật toán chính ở [diff.py:673](/Users/m/project/sbcompare2chrom/chromedrift/diff.py:673).

Sau diff cơ bản, hai post-pass ghép một số cặp remove + add thành một thay đổi đúng nghĩa hơn:

- rename feature string, pref hoặc switch nếu C++ variable vẫn cho thấy đó là cùng khai báo tại [diff.py:1535](/Users/m/project/sbcompare2chrom/chromedrift/diff.py:1535);
- WebUI control đổi pref nhưng giữ page và identity thành `ui_control_repointed` tại [diff.py:1465](/Users/m/project/sbcompare2chrom/chromedrift/diff.py:1465).

### Bước 9 — Gắn signal, severity, bucket và owner

Mỗi Change được phân tích theo kind để tạo một hoặc nhiều signal tại [diff.py:1069](/Users/m/project/sbcompare2chrom/chromedrift/diff.py:1069). Signal nặng nhất quyết định severity, bucket và có thể override owner.

Ví dụ:

```text
mojo_method signature đổi
→ signal ipc_signature_change
→ severity 80
→ bucket Breaking
→ owner ipc
```

### Bước 10 — Điều chỉnh thành score của lần chạy

`score_change` bắt đầu từ severity, sau đó:

- đưa score về 0 nếu declaration không compile vào Windows ở cả hai phía tồn tại;
- trừ 15 khi thay đổi dựa vào sự vắng mặt nhưng evidence của phía cần chứng minh chưa đủ;
- có thể chuyển bucket về Housekeeping khi “biến mất” chưa được chứng minh.

Code đầy đủ ở [score.py:242](/Users/m/project/sbcompare2chrom/chromedrift/score.py:242). Score không bao giờ được tăng cao hơn severity.

### Bước 11 — Cluster các finding liên quan

Cluster dùng liên kết exact chứ không dùng AI similarity chung:

- route → gate qua guard key;
- gate → base feature qua feature variable;
- Blink runtime → base feature;
- feature param → owner feature;
- control → route khi label hoặc element id match sau chuẩn hóa chữ.

Code ở [cluster.py:94](/Users/m/project/sbcompare2chrom/chromedrift/cluster.py:94). Cluster chỉ giúp kể một câu chuyện; nó không thay đổi score, bucket hay owner.

### Bước 12 — Enrichment tùy chọn

Nếu không có `--no-enrich`, pipeline lấy context Chrome Status cho dải milestone tại [cli.py:163](/Users/m/project/sbcompare2chrom/chromedrift/cli.py:163). Đây là context bổ sung; lỗi enrichment không được dùng thay bằng chứng source và không làm đổi semantic diff.

### Bước 13 — Sinh report

Ba file được ghi tại [cli.py:232](/Users/m/project/sbcompare2chrom/chromedrift/cli.py:232):

- `report.json`: dữ liệu canonical đầy đủ, phù hợp cho script hoặc AI;
- `report.md`: bản đọc tuần tự, phù hợp đưa vào ticket;
- `report.html`: dashboard có filter cho người triage.

### Bước 14 — Skill phân tích kết quả và kiểm tra fork

Skill yêu cầu đọc report theo thứ tự owner → signal → bucket, rồi với từng finding phải trả lời:

1. Source Chromium thay đổi gì?
2. Windows/user có nhìn thấy thay đổi đó không?
3. Fork công ty có dùng contract/identifier đó không?
4. Ai phải làm gì và cần test gì?

Workflow của skill nằm tại [SKILL.md:114](/Users/m/project/sbcompare2chrom/skills/analyzing-chromium-uprevs/SKILL.md:114). Đây là bước mà deterministic engine cố ý không tự phán quyết.

---

## 5. ChromeDrift xác định file cần đọc như thế nào

### 5.1. Công thức chính xác

Tập file thực sự được mở là:

```text
file được target materialize
∩ file thuộc target scope của đúng lần chạy
∩ file thuộc product scope
∩ file match applies_to của ít nhất một extractor
```

Do đó có ba danh sách dễ bị nhầm:

| Danh sách | Quyết định gì | Có làm file được tải không |
|---|---|---|
| Fetch targets | File/tree nào được materialize | Có |
| Discovery candidates | Những file nào trong Chromium tree có hình dạng mà extractor có thể đọc | Không, chỉ đo coverage |
| Extractor `applies_to` | Bộ đọc nào được chạy trên một file đã materialize và hợp lệ | Không tự tải file |

### 5.2. Vì sao không chỉ `git diff` toàn bộ Chromium

- Diff toàn bộ chứa quá nhiều thay đổi implementation không trực tiếp nói hợp đồng nào đổi.
- Một thay đổi cú pháp nhưng cùng ý nghĩa có thể tạo noise. Ví dụ macro `BASE_FEATURE` đổi dạng nhưng semantic feature vẫn là một.
- Một contract đổi tên string có thể compile bình thường nhưng làm launch script hoặc config cũ mất tác dụng.
- Một flag bị xóa có thể chỉ là cleanup sau khi đã ship, không phải tính năng vừa bị mất.
- ChromeDrift cần một định danh ổn định để ghép hai version, nên nó đọc declaration và chuẩn hóa trước khi diff.

### 5.3. Vì sao chọn những file declaration này

Mỗi file/pattern phải thỏa phần lớn các tiêu chí sau:

1. Là source of truth cho một contract hoặc công tắc có tác động uprev.
2. Có cú pháp đủ cấu trúc để parse bằng Python mà không build Chromium.
3. Có semantic key tương đối ổn định giữa hai version.
4. Thay đổi có thể route đến một owner cụ thể.
5. Có thể trích `path:line` để kiểm chứng.
6. Chi phí fetch và parse chấp nhận được.
7. Có thể đo được lỗ hổng coverage thay vì âm thầm coi file không đọc là không có thay đổi.

### 5.4. Product scope và file bị loại

Policy dùng chung cho discovery và extraction nằm tại [eligibility.py:56](/Users/m/project/sbcompare2chrom/chromedrift/eligibility.py:56).

Các directory component bị loại đầy đủ:

```text
testing
test
tests
out
.git
__pycache__
fuzzers
fuzzer
web_test
web_tests
mock
```

Các suffix tên file test bị loại đầy đủ:

```text
_test
_tests
_unittest
_browsertest
_perftest
_test_api
_test_service
_test_util
_test_utils
_fuzzer
_mock
```

Tên file chính xác `fuzz.<ext>` và `mock.<ext>` cũng bị loại. Các binary không phải browser product bị loại:

```text
content/shell/
chrome/test/
tools/
headless/
remoting/
chrome/updater/
chrome/enterprise_companion/
chrome/windows_services/
```

Vendored third-party bị loại, trừ Blink; rule thật tại [eligibility.py:50](/Users/m/project/sbcompare2chrom/chromedrift/eligibility.py:50).

Chú ý: đây vẫn là convention, không phải kết quả đọc `BUILD.gn`. Vì vậy “in scope” có nghĩa là hợp rule của ChromeDrift, không tự chứng minh code đi vào binary.

---

## 6. Danh sách target và pattern đầy đủ

### 6.1. Ba target set

| Target set | Thành phần | Mục đích đúng | Không nên dùng để |
|---|---|---|---|
| `minimal` | Ba file | Smoke test, kiểm tra CLI/cache | Đánh giá uprev |
| `default` | Danh sách curated khoảng 40 MB/version | Điều tra hằng ngày, vòng phân tích nhanh | Khẳng định absence trên toàn Chromium |
| `wide` | `default` cộng các whole-directory archive có filter | Lần đọc rộng nhất hiện có trước review chính thức | Tự động kết luận release an toàn |

Ba factory được đăng ký tại [targets.py:607](/Users/m/project/sbcompare2chrom/chromedrift/targets.py:607).

### 6.2. `minimal`: đầy đủ ba file

Định nghĩa tại [targets.py:475](/Users/m/project/sbcompare2chrom/chromedrift/targets.py:475):

```text
third_party/blink/renderer/platform/runtime_enabled_features.json5
content/public/common/content_features.cc
content/public/common/content_switches.cc
```

`minimal` cố ý không chạy discovery coverage; xem [snapshot.py:97](/Users/m/project/sbcompare2chrom/chromedrift/snapshot.py:97).

### 6.3. `default`: toàn bộ target được khai báo

Danh sách dưới đây bung đầy đủ generator trong [targets.py:360](/Users/m/project/sbcompare2chrom/chromedrift/targets.py:360). Không có mục ẩn sau dấu rút gọn.

#### Core, feature, switch và pref targets

```text
tree content/public/common
     include: .cc, .h

file third_party/blink/public/common/features.h
file third_party/blink/common/features.cc
file net/base/features.cc
file net/base/features.h
file media/base/media_switches.cc
file media/base/media_switches.h
file ui/base/ui_base_features.cc
file ui/base/ui_base_features.h
file gpu/config/gpu_finch_features.cc
file gpu/config/gpu_finch_features.h
file services/network/public/cpp/features.cc
file services/network/public/cpp/features.h
file components/viz/common/features.cc
file components/viz/common/features.h
file components/autofill/core/common/autofill_features.cc
file components/password_manager/core/common/password_manager_features.cc
file components/safe_browsing/core/common/features.cc
file components/permissions/features.cc
file components/download/public/common/download_features.cc
file chrome/common/chrome_features.cc
file chrome/common/chrome_features.h
file content/common/features.cc
file components/omnibox/common/omnibox_features.cc
file extensions/common/extension_features.cc
file components/sync/base/features.cc
file components/segmentation_platform/public/features.cc
file components/optimization_guide/core/optimization_guide_features.cc
file components/search_engines/search_engines_switches.cc
file components/history/core/browser/features.cc
file components/bookmarks/common/bookmark_features.cc
file printing/printing_features.cc
file ui/views/views_features.cc
file third_party/blink/renderer/platform/runtime_enabled_features.json5
```

#### Web IDL, Mojo và metadata targets

```text
tree third_party/blink/renderer/modules
     include: toàn bộ READABLE_SUFFIXES ở mục 6.7

tree third_party/blink/renderer/core
     include: toàn bộ READABLE_SUFFIXES ở mục 6.7

tree third_party/blink/public/mojom
     include: .mojom

file content/public/common/content_switches.cc
file chrome/common/pref_names.h
file chrome/browser/flag-metadata.json
```

#### Tám WebUI resource trees

Các surface gốc được liệt kê tại [targets.py:35](/Users/m/project/sbcompare2chrom/chromedrift/targets.py:35). Mỗi tree chỉ giữ `.html`, `.html.ts`, `route.ts`, `routes.ts`:

```text
tree chrome/browser/resources/settings
tree chrome/browser/resources/history
tree chrome/browser/resources/downloads
tree chrome/browser/resources/bookmarks
tree chrome/browser/resources/extensions
tree chrome/browser/resources/password_manager
tree chrome/browser/resources/new_tab_page
tree chrome/browser/resources/print_preview
```

#### WebUI C++ tree

```text
tree chrome/browser/ui/webui
     include: .cc
```

Điểm quan trọng: đây là toàn bộ `.cc` dưới `chrome/browser/ui/webui/`, không chỉ `*_handler.cc` và cũng không chỉ directory `settings/`. Rule của extractor nằm tại [webui_gates.py:47](/Users/m/project/sbcompare2chrom/chromedrift/extract/webui_gates.py:47).

### 6.4. `wide`: toàn bộ root được cộng vào `default`

`wide` được tạo bằng `default_targets() + _WIDE_ROOTS`, tại [targets.py:588](/Users/m/project/sbcompare2chrom/chromedrift/targets.py:588). Mỗi root dưới đây là tree target dùng toàn bộ `READABLE_SUFFIXES` ở mục 6.7:

```text
components
chrome/browser
media
extensions
services
net
ui
gpu
printing
chrome/common
content/browser
content/common
content/public
content/renderer
content/child
content/services
third_party/blink/common
third_party/blink/public
base
device
cc
google_apis
sandbox
storage
pdf
mojo
apps
crypto
gin
skia
url
third_party/blink/renderer/platform
```

Danh sách thật và lý do cho từng root nằm tại [targets.py:488](/Users/m/project/sbcompare2chrom/chromedrift/targets.py:488).

`wide` là “widest available read”, không phải “đọc toàn bộ source Chromium” và không phải release verdict. Help text của CLI nói rõ tại [cli.py:542](/Users/m/project/sbcompare2chrom/chromedrift/cli.py:542).

### 6.5. Discovery roots: phạm vi dùng để đo denominator

Danh sách đầy đủ tại [targets.py:101](/Users/m/project/sbcompare2chrom/chromedrift/targets.py:101):

```text
chrome
components
content
extensions
services
net
ui
media
printing
gpu
third_party/blink
base
device
cc
google_apis
sandbox
storage
pdf
mojo
apps
crypto
gin
skia
url
dbus
```

Đây là denominator do project chọn, chưa phải toàn bộ repository. Một file ngoài các root này không được tính là missed dù extractor về lý thuyết có thể đọc cú pháp của nó.

### 6.6. Tất cả rule `applies_to` của chín bộ đọc

| Bộ đọc | File được nhận, ghi đầy đủ | Source rule |
|---|---|---|
| `base_features` | Basename kết thúc `.cc` hoặc `.h`, chứa một trong các token ở mục 6.6.1 và không chứa test token ở mục 6.6.2 | [base_features.py:83](/Users/m/project/sbcompare2chrom/chromedrift/extract/base_features.py:83) |
| `blink_runtime` | Basename chính xác `runtime_enabled_features.json5` | [blink_runtime.py:34](/Users/m/project/sbcompare2chrom/chromedrift/extract/blink_runtime.py:34) |
| `web_idl` | Kết thúc `.idl` và path bắt đầu `third_party/blink/renderer/` | [web_idl.py:100](/Users/m/project/sbcompare2chrom/chromedrift/extract/web_idl.py:100) |
| `mojom` | Kết thúc `.mojom` | [mojom.py:130](/Users/m/project/sbcompare2chrom/chromedrift/extract/mojom.py:130) |
| `constants` | Basename kết thúc `.cc` hoặc `.h`, chứa switch/pref token ở mục 6.6.3 | [constants.py:54](/Users/m/project/sbcompare2chrom/chromedrift/extract/constants.py:54) |
| `flags_metadata` | Basename chính xác `flag-metadata.json` | [flags_metadata.py:25](/Users/m/project/sbcompare2chrom/chromedrift/extract/flags_metadata.py:25) |
| `webui_routes` | Path bắt đầu `chrome/browser/resources/`, basename chính xác `route.ts` hoặc `routes.ts` | [webui_routes.py:50](/Users/m/project/sbcompare2chrom/chromedrift/extract/webui_routes.py:50) |
| `webui_controls` | Path bắt đầu `chrome/browser/resources/`, kết thúc `.html` hoặc `.html.ts` | [webui_controls.py:126](/Users/m/project/sbcompare2chrom/chromedrift/extract/webui_controls.py:126) |
| `webui_gates` | Path bắt đầu `chrome/browser/ui/webui/`, kết thúc `.cc` | [webui_gates.py:47](/Users/m/project/sbcompare2chrom/chromedrift/extract/webui_gates.py:47) |

#### 6.6.1. Toàn bộ token filename của `base_features`

Code dùng substring của basename, không dùng shell glob. Danh sách token chính xác tại [base_features.py:53](/Users/m/project/sbcompare2chrom/chromedrift/extract/base_features.py:53):

```text
features.cc
features.h
switches.cc
switches.h
fieldtrial.cc
fieldtrial.h
field_trial.cc
field_trial.h
flags.cc
flags.h
feature_list.cc
feature_list.h
_util.cc
_handler.cc
_manager.cc
```

Viết theo cách nhìn file Chromium, các dạng tương ứng là:

```text
*features.cc
*features.h
*switches.cc
*switches.h
*fieldtrial.cc
*fieldtrial.h
*field_trial.cc
*field_trial.h
*flags.cc
*flags.h
*feature_list.cc
*feature_list.h
*_util.cc
*_handler.cc
*_manager.cc
```

Không có rule riêng cho `handler.h`, `util.h` hoặc `manager.h` trong implementation hiện tại.

#### 6.6.2. Toàn bộ test token riêng của `base_features`

Danh sách tại [base_features.py:68](/Users/m/project/sbcompare2chrom/chromedrift/extract/base_features.py:68):

```text
_unittest.
_browsertest.
_test.
_testing.
test_util.
_test_util.
_test_helper.
```

Đây là lớp lọc riêng của extractor. Product-scope filter ở mục 5.4 vẫn chạy trước.

#### 6.6.3. Toàn bộ token filename của `constants`

Switch token tại [constants.py:44](/Users/m/project/sbcompare2chrom/chromedrift/extract/constants.py:44):

```text
switches.
```

Pref tokens tại [constants.py:50](/Users/m/project/sbcompare2chrom/chromedrift/extract/constants.py:50):

```text
pref_names.
pref_names_
_pref_names.
_prefs.
prefs.
```

Basename vẫn phải kết thúc `.cc` hoặc `.h`.

### 6.7. Toàn bộ `READABLE_SUFFIXES`

Đây là filter dùng cho wide root và complete partition. Danh sách chính xác tại [targets.py:568](/Users/m/project/sbcompare2chrom/chromedrift/targets.py:568):

```text
features.cc
features.h
switches.cc
switches.h
feature_list.cc
feature_list.h
field_trial.cc
field_trial.h
fieldtrial.cc
fieldtrial.h
flags.cc
flags.h
_handler.cc
_util.cc
_manager.cc
pref_names.cc
pref_names.h
prefs.cc
prefs.h
.mojom
.idl
.json5
route.ts
routes.ts
.html
.html.ts
flag-metadata.json
```

`webui_gates` là ngoại lệ: complete target dưới `chrome/browser/ui/webui` cộng thêm `.cc`, vì rule thật của nó là mọi `.cc`, xem [targets.py:730](/Users/m/project/sbcompare2chrom/chromedrift/targets.py:730).

### 6.8. Partition đầy đủ

Mỗi partition là filter target, không phải bằng chứng rằng Chromium được tổ chức trọn vẹn theo feature. Danh sách tại [targets.py:637](/Users/m/project/sbcompare2chrom/chromedrift/targets.py:637):

| Partition | Prefix/file riêng |
|---|---|
| `settings` | `chrome/browser/resources/settings`, `chrome/browser/ui/webui`, `chrome/common/chrome_features.cc`, `chrome/common/chrome_features.h` |
| `downloads` | `chrome/browser/resources/downloads`, `components/download/` |
| `bookmarks` | `chrome/browser/resources/bookmarks`, `components/bookmarks/` |
| `history` | `chrome/browser/resources/history`, `components/history/` |
| `extensions` | `chrome/browser/resources/extensions`, `extensions/` |
| `passwords` | `chrome/browser/resources/password_manager`, `components/password_manager/` |
| `printing` | `chrome/browser/resources/print_preview`, `printing/` |
| `newtab` | `chrome/browser/resources/new_tab_page` |
| `webplatform` | `third_party/blink/` |
| `network` | `net/base/`, `services/network/` |
| `media` | `media/base/` |

Ba core files được giữ trong mọi partition tại [targets.py:630](/Users/m/project/sbcompare2chrom/chromedrift/targets.py:630):

```text
chrome/common/pref_names.h
chrome/browser/flag-metadata.json
content/public/common/content_switches.cc
```

---

## 7. Chín bộ đọc: gồm những bộ nào và vì sao là chín

### 7.1. “Chạy chín bộ đọc” thực sự có nghĩa gì

Chín bộ đọc được đăng ký trong một registry tại [extract/__init__.py:32](/Users/m/project/sbcompare2chrom/chromedrift/extract/__init__.py:32). Chúng không phải chín bước chạy nối tiếp trên mọi file. Với từng file, registry chỉ gọi những bộ có `applies_to(path)` trả về true.

Ví dụ `chrome/common/pref_names.h` có thể match cả `base_features` và `constants` nếu tên cũng hợp token tương ứng; một `.mojom` chỉ match `mojom`; `downloads_ui.cc` có thể match `webui_gates` và cũng có thể match `base_features` nếu basename thuộc pattern của bộ đó.

### 7.2. Tiêu chí tách thành một bộ đọc

Một extractor riêng được tạo khi nguồn có:

1. Cú pháp/grammar riêng cần parser riêng.
2. Một source of truth rõ ràng.
3. Quy tắc semantic key riêng.
4. Tập attrs riêng cần so.
5. Hậu quả uprev và owner riêng.
6. Có thể viết `applies_to` để cả extraction lẫn coverage dùng chung.
7. Có thể unit test như pure function `extract(text, path) -> list[Fact]`; contract này được mô tả tại [extract/__init__.py:1](/Users/m/project/sbcompare2chrom/chromedrift/extract/__init__.py:1).

Vì vậy “chín” không phải con số tối ưu về toán học. Nó là số grammar/source authority độc lập mà implementation hiện tại đã chọn để bao phủ 16 loại Fact. Nếu thêm một source authority mới, registry có thể có bộ thứ mười. Nếu gom hai grammar không liên quan vào một parser, code khó test và coverage không còn biết surface nào đã được đọc.

### 7.3. Bảng đầy đủ chín bộ đọc

| # | Bộ đọc | Source of truth và file ví dụ để mở trong Chromium | Fact tạo ra | Vì sao cần riêng |
|---:|---|---|---|---|
| 1 | `base_features` | `chrome/common/chrome_features.cc`, `content/public/common/content_features.cc`, `net/base/features.cc` | `base_feature`, `feature_param` | Hiểu macro/legacy C++, default state, param và build guard |
| 2 | `blink_runtime` | `third_party/blink/renderer/platform/runtime_enabled_features.json5` | `blink_runtime_feature` | JSON5 manifest có status Windows, stable/experimental và wiring tới base feature |
| 3 | `web_idl` | `third_party/blink/renderer/modules/gamepad/gamepad.idl`, `third_party/blink/renderer/core/dom/document.idl` | `idl_interface`, `idl_member` | Grammar Web IDL, extended attributes, overload và RuntimeEnabled khác C++/Mojo |
| 4 | `mojom` | `third_party/blink/public/mojom/frame/frame.mojom`, `chrome/browser/ui/webui/downloads/downloads.mojom` nếu file có trong version đang đọc | `mojo_interface`, `mojo_method`, `mojo_struct`, `mojo_field`, `mojo_enum` | Wire contract IPC cần module-qualified identity, ordinal, type và stable position |
| 5 | `constants` | `chrome/common/pref_names.h`, `content/public/common/content_switches.cc`, các file `*_prefs.cc` | `pref`, `switch` | Identity thật là string bên phải declaration, không phải tên C++ variable |
| 6 | `flags_metadata` | `chrome/browser/flag-metadata.json` | `flag_entry` | JSON metadata có expiry milestone và owners, không nằm trong C++ feature declaration |
| 7 | `webui_routes` | `chrome/browser/resources/settings/route.ts`, `chrome/browser/resources/history/routes.ts` | `webui_route` | Route tree và guard trong TypeScript có grammar riêng |
| 8 | `webui_controls` | `chrome/browser/resources/settings/downloads_page/downloads_page.html`, các template `.html.ts` | `webui_control` | Polymer/Lit template khai báo control, pref binding, label, id và build condition |
| 9 | `webui_gates` | `chrome/browser/ui/webui/settings/settings_ui.cc`, `chrome/browser/ui/webui/downloads/downloads_ui.cc` | `webui_gate` | Đọc lời gọi `AddBoolean`, `AddInteger`, `AddString`, `AddDouble` để nối loadTimeData key với expression/feature |

### 7.4. Vì sao không chọn theo tên “API, flag, setting, Mojo, WebUI” thành đúng năm bộ

Các tên đó là khái niệm sản phẩm, không phải năm grammar:

- “API” tách thành Blink runtime status và Web IDL shape vì hai nguồn trả lời hai câu hỏi khác nhau: có reachable không và shape là gì.
- “Flag” tách thành base feature declaration, Blink runtime feature và flag expiry metadata.
- “Setting” tách thành route, control và C++ gate vì ba hop nằm trong ba dạng file khác nhau.
- “Mojo” là một grammar nhưng tạo năm Fact kind vì interface, method, struct/union, field và enum có identity/compatibility rule khác nhau.
- “Pref” và “switch” dùng cùng C++ string-constant grammar nên được gom trong một extractor, nhưng vẫn ra hai Fact kind.

### 7.5. Ba nhóm ý nghĩa mà chín bộ đọc bao phủ

Implementation gom 16 kind thành ba nhóm tại [model.py:470](/Users/m/project/sbcompare2chrom/chromedrift/model.py:470):

| Nhóm | Fact kinds | Ý nghĩa |
|---|---|---|
| Behaviour switches | `base_feature`, `feature_param`, `blink_runtime_feature` | Có khả năng trực tiếp làm hành vi Windows đổi |
| External contracts | `pref`, `switch`, hai Web IDL kind và năm Mojo kind | Có bên ngoài declaration phụ thuộc: profile, script, website hoặc process khác |
| UI and scheduling | `webui_route`, `webui_control`, `webui_gate`, `flag_entry` | UI nhìn thấy gì hoặc một flag được lên lịch xóa khi nào |

### 7.6. Tiêu chí để hội đồng chấp nhận hoặc yêu cầu thêm extractor

Một extractor hiện tại nên được giữ nếu:

- có ít nhất một contract uprev quan trọng mà extractor khác không mô tả;
- key ổn định qua version;
- parser có test cho syntax chính và syntax lỗi;
- attrs được diff có lý do compatibility rõ;
- `applies_to` vừa dùng cho extraction vừa dùng cho coverage;
- false positive/false negative được công bố.

Một extractor mới chỉ nên thêm khi:

- chỉ ra source of truth mới chưa được chín bộ hiện tại đọc;
- định nghĩa được Fact kind/key/attrs;
- định nghĩa được meaningful attrs, signals và owner;
- bổ sung target/filter, coverage và test cùng lúc;
- giải thích chi phí fetch.

---

## 8. Chuẩn hóa về `Fact`

### 8.1. Cấu trúc chung

`Fact` được định nghĩa tại [model.py:589](/Users/m/project/sbcompare2chrom/chromedrift/model.py:589):

```text
Fact
├── kind   loại khai báo
├── key    semantic key ổn định qua version
├── name   tên để hiển thị
├── path   file bằng chứng
├── line   dòng bằng chứng
└── attrs  thuộc tính riêng của kind
```

Định danh dùng để ghép hai version là:

```text
uid = kind + ":" + key
```

Property thật ở [model.py:607](/Users/m/project/sbcompare2chrom/chromedrift/model.py:607).

Ý nghĩa từng field:

- `kind`: tránh một pref và một switch có cùng string bị coi là một đối tượng.
- `key`: định danh semantic, không lấy nguyên cả dòng source.
- `name`: chỉ phục vụ hiển thị; không phải identity.
- `path`: bằng chứng và được so riêng. Cùng UID nhưng chuyển file sinh signal `declaration_moved` tại [diff.py:718](/Users/m/project/sbcompare2chrom/chromedrift/diff.py:718).
- `line`: giúp mở đúng declaration, nhưng thay đổi line không tạo finding.
- `attrs`: dữ liệu riêng của kind. Chỉ attrs trong whitelist `MEANINGFUL_ATTRS` mới có thể tạo `modified`.

### 8.2. “Chuẩn hóa” không phải một hàm global duy nhất

Mỗi extractor chịu trách nhiệm:

1. Parse cú pháp riêng.
2. Tạo semantic key ổn định.
3. Đổi dữ liệu source về shape attrs thống nhất của kind đó.
4. Gắn path và line.

Sau đó lớp dùng chung mới:

1. gắn trạng thái platform directory;
2. dedupe theo UID;
3. sort kết quả để cùng input luôn cho cùng output.

Do đó thêm một attr vào extractor nhưng quên thêm nó vào `MEANINGFUL_ATTRS` sẽ làm report lưu attr mà không bao giờ báo thay đổi. Whitelist đầy đủ nằm tại [diff.py:61](/Users/m/project/sbcompare2chrom/chromedrift/diff.py:61).

### 8.3. Quy tắc semantic key của 16 Fact kind

| Fact kind | Quy tắc `key` |
|---|---|
| `base_feature` | Feature string; với macro hai tham số có thể suy ra bằng cách bỏ tiền tố `k` khỏi C++ variable |
| `feature_param` | `FeatureName/ParamName`; nếu không tìm được owner thì dùng `path:ParamName` |
| `blink_runtime_feature` | Trường `name` trong JSON5 |
| `idl_interface` | Tên interface, dictionary, namespace hoặc enum |
| `idl_member` | `InterfaceName.MemberName`; các overload cùng tên được gom dưới cùng UID |
| `mojo_interface` | `module.Interface` |
| `mojo_method` | `module.Interface.Method`; signature nằm trong attrs để đổi signature thành modified |
| `mojo_struct` | Fully-qualified struct/union name, gồm cả nested type |
| `mojo_field` | `FullyQualifiedStruct.Field` |
| `mojo_enum` | Fully-qualified enum name |
| `switch` | String switch thực tế, không phải C++ variable |
| `pref` | String pref key thực tế, không phải C++ variable |
| `flag_entry` | Trường `name` trong `flag-metadata.json` |
| `webui_route` | `surface/ROUTE_CONSTANT` |
| `webui_control` | `surface/page/file/identity`; identity ưu tiên `pref#id`, rồi `pref`, `id`, label, cuối cùng vị trí |
| `webui_gate` | `handler-stem/data-key` |

### 8.4. Ký hiệu dùng trong bảng attrs

- `Δ`: attr nằm trong `MEANINGFUL_ATTRS`; đổi attr có thể tạo Change `modified`.
- `?`: attr chỉ tồn tại khi source có thông tin tương ứng hoặc bước hậu xử lý gắn thêm.
- Không có `Δ`: attr được lưu làm evidence hoặc hỗ trợ join nhưng riêng thay đổi đó không tạo `modified`.

Ngoài danh sách dưới đây, bước hậu xử lý có thể gắn `platform_state` vào bất kỳ Fact nào nếu mọi declaration của UID đều nằm trong platform directory không thuộc Windows; xem [extract/__init__.py:201](/Users/m/project/sbcompare2chrom/chromedrift/extract/__init__.py:201). Attr này chỉ tham gia diff ở kind có liệt kê `platform_state` trong whitelist.

### 8.5. Nhóm Behaviour switches: attrs và ví dụ

#### `base_feature`

Nguồn tạo Fact: [base_features.py:184](/Users/m/project/sbcompare2chrom/chromedrift/extract/base_features.py:184).

- Common fields: `key` là feature string, `name = key`, `path` là file `.cc/.h`, `line` là dòng macro/declaration.
- Toàn bộ attrs: `Δ var`, `Δ default_state`, `Δ platform_state`, `declared_form`, `Δ conditions`.
- Cả năm attr được tạo; value có thể rỗng tùy syntax.
- `declared_form` không được diff để đổi cách viết macro nhưng không đổi semantics không tạo noise.

Ví dụ minh họa:

```json
{"kind":"base_feature","key":"BackForwardCache","name":"BackForwardCache","path":"content/public/common/content_features.cc","line":40,"attrs":{"var":"kBackForwardCache","default_state":"enabled","platform_state":{"windows":"enabled"},"declared_form":"macro2","conditions":[]}}
```

#### `feature_param`

Nguồn tạo Fact: [base_features.py:323](/Users/m/project/sbcompare2chrom/chromedrift/extract/base_features.py:323).

- Common fields: `key = FeatureName/ParamName`; `name` là param name.
- Toàn bộ attrs: `Δ feature`, `Δ type`, `Δ var`, `Δ default`, `Δ platform_state?`.

Ví dụ minh họa:

```json
{"kind":"feature_param","key":"Spare/timeout_seconds","name":"timeout_seconds","path":"components/example/features.cc","line":52,"attrs":{"feature":"Spare","type":"int","var":"kSpareTimeout","default":"30"}}
```

#### `blink_runtime_feature`

Nguồn tạo Fact: [blink_runtime.py:119](/Users/m/project/sbcompare2chrom/chromedrift/extract/blink_runtime.py:119); danh sách optional fields được đọc tại [blink_runtime.py:94](/Users/m/project/sbcompare2chrom/chromedrift/extract/blink_runtime.py:94).

- Luôn có: `Δ status`, `Δ platform_status`, `Δ windows_status`.
- Có điều kiện: `Δ base_feature?`, `Δ base_feature_status?`, `Δ public?`, `Δ origin_trial_feature_name?`, `Δ depends_on?`, `Δ implied_by?`, `Δ copied_from_base_feature_if?`, `Δ settable_from_internals?`, `Δ origin_trial_allows_third_party?`, `Δ browser_process_read_access?`, `Δ browser_process_read_write_access?`, `Δ origin_trial_os?`, `Δ origin_trial_type?`, `Δ origin_trial_allows_insecure?`, `Δ is_protected_feature?`.

Ví dụ minh họa:

```json
{"kind":"blink_runtime_feature","key":"GamepadButtonAxisEvents","name":"GamepadButtonAxisEvents","path":"third_party/blink/renderer/platform/runtime_enabled_features.json5","line":120,"attrs":{"status":"stable","platform_status":{"default":"stable","windows":"stable"},"windows_status":"stable","base_feature":"GamepadButtonAxisEvents"}}
```

### 8.6. Nhóm External contracts: attrs và ví dụ

#### `idl_interface`

Nguồn tạo Fact: [web_idl.py:262](/Users/m/project/sbcompare2chrom/chromedrift/extract/web_idl.py:262).

- Common fields: `key` và `name` là tên interface/dictionary/namespace/enum. Partial definition không tạo interface Fact riêng.
- Luôn có: `Δ idl_kind`, `partial`, `Δ inherits`, `Δ ext`.
- Có điều kiện: `Δ values?` với enum.
- `platform_state?` có thể được gắn sau nhưng không được diff cho kind này.

Ví dụ minh họa:

```json
{"kind":"idl_interface","key":"Gamepad","name":"Gamepad","path":"third_party/blink/renderer/modules/gamepad/gamepad.idl","line":8,"attrs":{"idl_kind":"interface","partial":false,"inherits":"EventTarget","ext":{"Exposed":"Window"}}}
```

#### `idl_member`

Nguồn tạo Fact: [web_idl.py:287](/Users/m/project/sbcompare2chrom/chromedrift/extract/web_idl.py:287).

- Luôn có từ extractor: `interface`, `Δ member_type`, `Δ signature`, `Δ ext`, `Δ runtime_enabled`, `from_partial`.
- Dedupe overload có thể thêm: `Δ signatures?`, `Δ overload_traits?`, `overload_locations?`; xem [model.py:936](/Users/m/project/sbcompare2chrom/chromedrift/model.py:936).
- `platform_state?` có thể được gắn sau nhưng không được diff cho kind này.

Ví dụ minh họa:

```json
{"kind":"idl_member","key":"Gamepad.vibrate","name":"vibrate","path":"third_party/blink/renderer/modules/gamepad/gamepad.idl","line":15,"attrs":{"interface":"Gamepad","member_type":"operation","signature":"undefined vibrate(double duration)","ext":{},"runtime_enabled":"","from_partial":false}}
```

#### `mojo_interface`

Nguồn tạo Fact: [mojom.py:275](/Users/m/project/sbcompare2chrom/chromedrift/extract/mojom.py:275).

- Luôn có: `module`, `method_count`, `methods`.
- Có điều kiện: `Δ stable?`, `conditions?`, `Δ platform_state?`.
- `method_count` và `methods` không được diff vì từng method đã là Fact riêng; nếu so cả hai sẽ báo trùng một thay đổi.

Ví dụ minh họa:

```json
{"kind":"mojo_interface","key":"blink.mojom.WidgetHost","name":"WidgetHost","path":"third_party/blink/public/mojom/widget.mojom","line":10,"attrs":{"module":"blink.mojom","method_count":1,"methods":["SetCursor"],"stable":true}}
```

#### `mojo_method`

Nguồn tạo Fact: [mojom.py:247](/Users/m/project/sbcompare2chrom/chromedrift/extract/mojom.py:247).

- Luôn có: `interface`, `module`, `Δ signature`, `Δ params`, `Δ response`, `Δ attrs`.
- Có điều kiện: `Δ ordinal?`, `conditions?`, `Δ platform_state?`, `inherited_conditions?`, `stable?`, `Δ position?`.
- `position` được dùng cho member trong stable interface để theo dõi wire order.

Ví dụ minh họa:

```json
{"kind":"mojo_method","key":"blink.mojom.WidgetHost.SetCursor","name":"SetCursor","path":"third_party/blink/public/mojom/widget.mojom","line":12,"attrs":{"interface":"blink.mojom.WidgetHost","module":"blink.mojom","signature":"SetCursor(Cursor cursor)","params":"Cursor cursor","response":"","attrs":{},"ordinal":"0"}}
```

#### `mojo_struct`

Nguồn tạo Fact: [mojom.py:473](/Users/m/project/sbcompare2chrom/chromedrift/extract/mojom.py:473).

- Kind này dùng cho cả `struct` và `union`.
- Luôn có: `module`, `Δ mojo_kind`, `field_count`, `fields`.
- Có điều kiện: `Δ stable?`, `conditions?`, `Δ platform_state?`.
- `field_count` và `fields` không được diff vì từng field đã là Fact riêng.

Ví dụ minh họa:

```json
{"kind":"mojo_struct","key":"blink.mojom.Payload","name":"Payload","path":"third_party/blink/public/mojom/payload.mojom","line":20,"attrs":{"module":"blink.mojom","mojo_kind":"struct","field_count":2,"fields":["data","url"]}}
```

#### `mojo_field`

Nguồn tạo Fact: [mojom.py:417](/Users/m/project/sbcompare2chrom/chromedrift/extract/mojom.py:417).

- Luôn có: `struct`, `module`, `Δ type`.
- Có điều kiện: `Δ ordinal?`, `Δ default?`, `Δ attrs?`, `Δ min_version?`, `conditions?`, `Δ platform_state?`, `inherited_conditions?`, `stable?`, `Δ position?`.

Ví dụ minh họa:

```json
{"kind":"mojo_field","key":"blink.mojom.Payload.url","name":"url","path":"third_party/blink/public/mojom/payload.mojom","line":22,"attrs":{"struct":"blink.mojom.Payload","module":"blink.mojom","type":"url.mojom.Url","ordinal":"0","attrs":"MinVersion=1","min_version":"1"}}
```

#### `mojo_enum`

Nguồn tạo Fact: [mojom.py:461](/Users/m/project/sbcompare2chrom/chromedrift/extract/mojom.py:461).

- Luôn có: `module`, `Δ values`.
- Có điều kiện: `Δ stable?`, `conditions?`, `Δ platform_state?`.
- `values` giữ thứ tự và numeric value khai báo vì đó là wire representation.

Ví dụ minh họa:

```json
{"kind":"mojo_enum","key":"blink.mojom.WaitMode","name":"WaitMode","path":"third_party/blink/public/mojom/task.mojom","line":30,"attrs":{"module":"blink.mojom","values":["kNone = 0","kWait = 1"]}}
```

#### `switch`

Nguồn tạo Fact chung với pref: [constants.py:102](/Users/m/project/sbcompare2chrom/chromedrift/extract/constants.py:102).

- Luôn có: `Δ var`.
- Có điều kiện: `conditions?`, `Δ platform_state?`.
- `key` là string command-line thật; đổi C++ symbol nhưng giữ string là modified, đổi string có thể được rename post-pass ghép lại.

Ví dụ minh họa:

```json
{"kind":"switch","key":"disable-gpu","name":"disable-gpu","path":"content/public/common/content_switches.cc","line":40,"attrs":{"var":"kDisableGpu"}}
```

#### `pref`

Nguồn tạo Fact chung với switch: [constants.py:102](/Users/m/project/sbcompare2chrom/chromedrift/extract/constants.py:102); kind được chọn theo basename tại [constants.py:61](/Users/m/project/sbcompare2chrom/chromedrift/extract/constants.py:61).

- Luôn có: `Δ var`.
- Có điều kiện: `conditions?`, `Δ platform_state?`.
- `key` là string lưu trong profile, nên một C++ variable đổi tên và một pref string đổi tên có hậu quả khác nhau.

Ví dụ minh họa:

```json
{"kind":"pref","key":"download.prompt_for_download","name":"download.prompt_for_download","path":"chrome/common/pref_names.h","line":90,"attrs":{"var":"kPromptForDownload"}}
```

### 8.7. Nhóm UI and scheduling: attrs và ví dụ

#### `flag_entry`

Nguồn tạo Fact: [flags_metadata.py:59](/Users/m/project/sbcompare2chrom/chromedrift/extract/flags_metadata.py:59).

- Luôn có: `Δ expiry_milestone`, `owners`.
- `expiry_milestone` có thể là `null`; `owners` mặc định là list rỗng.
- `owners` hiện được lưu nhưng không được diff.

Ví dụ minh họa:

```json
{"kind":"flag_entry","key":"download-bubble","name":"download-bubble","path":"chrome/browser/flag-metadata.json","line":220,"attrs":{"expiry_milestone":155,"owners":["team@example.com"]}}
```

#### `webui_route`

Nguồn tạo Fact: [webui_routes.py:100](/Users/m/project/sbcompare2chrom/chromedrift/extract/webui_routes.py:100).

- Luôn có: `surface`, `Δ route`, `Δ parent`, `route_kind`, `Δ guards`.
- `route_kind` được lưu nhưng hiện không được diff.
- `platform_state?` có thể được gắn sau nhưng không được diff cho kind này.

Ví dụ minh họa:

```json
{"kind":"webui_route","key":"settings/SITE_SETTINGS","name":"SITE_SETTINGS","path":"chrome/browser/resources/settings/route.ts","line":80,"attrs":{"surface":"settings","route":"content","parent":"BASIC","route_kind":"child","guards":["enableSiteSettings"]}}
```

#### `webui_control`

Nguồn tạo Fact: [webui_controls.py:285](/Users/m/project/sbcompare2chrom/chromedrift/extract/webui_controls.py:285).

- Luôn có: `surface`, `page`, `file`, `Δ control`, `Δ pref`, `Δ label`, `element_id`, `Δ build_conditions`.
- Có điều kiện: `Δ platform_state?`.
- `element_id` thường tham gia key nhưng riêng attr không được diff. Đổi id có thể thành remove + add thay vì modified.

Ví dụ minh họa:

```json
{"kind":"webui_control","key":"settings/downloads_page/downloads_page/pref:download.prompt_for_download#prompt","name":"pref:download.prompt_for_download#prompt","path":"chrome/browser/resources/settings/downloads_page/downloads_page.html","line":45,"attrs":{"surface":"settings","page":"downloads_page","file":"downloads_page","control":"settings-toggle-button","pref":"download.prompt_for_download","label":"promptForDownload","element_id":"prompt","build_conditions":[]}}
```

#### `webui_gate`

Nguồn tạo Fact: [webui_gates.py:101](/Users/m/project/sbcompare2chrom/chromedrift/extract/webui_gates.py:101).

- Luôn có: `data_key`, `handler`, `value_type`, `Δ expression`, `Δ features`, `Δ enabled_checks`.
- `value_type` được lưu nhưng hiện không được diff.
- `platform_state?` có thể được gắn sau nhưng không được diff cho kind này.

Ví dụ minh họa:

```json
{"kind":"webui_gate","key":"downloads_ui/enableDownloadBubble","name":"enableDownloadBubble","path":"chrome/browser/ui/webui/downloads/downloads_ui.cc","line":70,"attrs":{"data_key":"enableDownloadBubble","handler":"downloads_ui","value_type":"boolean","expression":"base::FeatureList::IsEnabled(features::kDownloadBubble)","features":["kDownloadBubble"],"enabled_checks":["kDownloadBubble"]}}
```

### 8.8. Danh sách attrs thực sự được so, đối chiếu một chỗ

Đây là bản chép đầy đủ từ [diff.py:61](/Users/m/project/sbcompare2chrom/chromedrift/diff.py:61):

```text
base_feature:
  default_state, platform_state, conditions, var

feature_param:
  default, type, feature, var, platform_state

blink_runtime_feature:
  status, platform_status, windows_status,
  base_feature, base_feature_status,
  origin_trial_feature_name, depends_on, implied_by, public,
  copied_from_base_feature_if,
  origin_trial_allows_third_party, settable_from_internals,
  browser_process_read_access, browser_process_read_write_access,
  origin_trial_os, origin_trial_type,
  origin_trial_allows_insecure, is_protected_feature

idl_interface:
  idl_kind, inherits, ext, values

idl_member:
  signature, signatures, overload_traits,
  member_type, ext, runtime_enabled

mojo_interface:
  stable, platform_state

mojo_method:
  signature, params, response, attrs, ordinal,
  position, platform_state

mojo_struct:
  mojo_kind, stable, platform_state

mojo_field:
  type, ordinal, default, attrs, position,
  min_version, platform_state

mojo_enum:
  values, stable, platform_state

switch:
  var, platform_state

pref:
  var, platform_state

flag_entry:
  expiry_milestone

webui_route:
  route, parent, guards

webui_control:
  control, pref, label, build_conditions, platform_state

webui_gate:
  expression, features, enabled_checks
```

### 8.9. Attr được lưu nhưng không tạo diff: điểm cần hội đồng biết

Một số là chủ ý tốt:

- `base_feature.declared_form`: không báo noise khi chỉ đổi syntax macro.
- `mojo_interface.methods` và `mojo_struct.fields`: tránh báo trùng vì method/field đã là Fact riêng.
- `idl_member.overload_locations`: chỉ để dẫn tới source.
- Raw `conditions` trên Mojo/pref/switch: giữ evidence; diff ưu tiên trạng thái Windows đã resolve.

Một số là giới hạn/risk cần maintainer xác nhận:

- `flag_entry.owners` đổi không tạo finding.
- `webui_route.route_kind` đổi không tạo finding nếu route/parent/guards giữ nguyên.
- `webui_gate.value_type` đổi không tạo finding nếu expression/features/enabled_checks giữ nguyên.
- `webui_control.element_id` đổi có thể biểu diễn thành removed + added vì id tham gia key.
- `mojo_method.stable` và `mojo_field.stable` được lưu nhưng không diff trực tiếp; `position` mới là member-level attr được so.
- `line` không được diff; đúng cho citation nhưng không dùng để phát hiện movement.

---

## 9. So sánh hai snapshot thành `Change`

### 9.1. Tiền điều kiện

`diff_snapshots` từ chối so nếu hai snapshot không cùng `(target_set, partitions, complete)`; xem [diff.py:673](/Users/m/project/sbcompare2chrom/chromedrift/diff.py:673). Điều này ngăn một snapshot wide bị so với một snapshot default rồi hàng chục nghìn Fact chỉ có ở wide bị hiểu thành add/remove.

Với run đủ lớn từ 500 Fact, code cũng từ chối nếu phía nhỏ có ít hơn 50% số Fact của phía lớn; guard tại [diff.py:753](/Users/m/project/sbcompare2chrom/chromedrift/diff.py:753).

### 9.2. Ghép bằng UID

Với mỗi `uid` trong hợp của hai snapshot:

```text
uid chỉ có ở TO                         → added
uid chỉ có ở FROM                       → removed
uid có ở cả hai, meaningful attrs khác  → modified
uid có ở cả hai, meaningful attrs giống → không có Change
```

Với modified:

```text
deltas[attr] = [old_value, new_value]
```

`position` chỉ được so khi tồn tại ở cả hai phía. Quy tắc này tránh việc một container Mojo bỏ annotation `[Stable]` bị hiểu sai thành hàng loạt ordinal change. Vòng so chính nằm tại [diff.py:697](/Users/m/project/sbcompare2chrom/chromedrift/diff.py:697).

### 9.3. Chuẩn hóa trước khi so attrs

`meaningful_attrs` chỉ lấy whitelist của kind. Riêng `platform_state.windows == compiled` được chuẩn hóa như không có guard, để hai cách viết “không guard” và “có guard nhưng Windows vẫn compile” không tạo false positive; xem [diff.py:559](/Users/m/project/sbcompare2chrom/chromedrift/diff.py:559).

### 9.4. `Change` chứa gì

`Change` được định nghĩa tại [model.py:686](/Users/m/project/sbcompare2chrom/chromedrift/model.py:686):

```text
change_type  added | removed | modified
kind         Fact kind
key          semantic key
name         display name
before       attrs cũ hoặc null
after        attrs mới hoặc null
deltas       attr -> [old, new]
paths        file hai phía
locations    path:line hai phía
signals      nhãn semantic
severity     độ nặng lý thuyết
```

### 9.5. Ví dụ Mojo: tại sao key không chứa signature

Source minh họa:

```mojom
module chrome.mojom;

interface Downloads {
  Pause(int32 id) => (bool ok);
};
```

Fact method có key:

```text
chrome.mojom.Downloads.Pause
```

và có `signature`, `params`, `response` trong attrs. Nếu TO đổi `int32 id` thành `int64 id`, UID vẫn match và kết quả là một `modified` có signal `ipc_signature_change`. Nếu signature bị nhét vào key, công cụ sẽ thấy một removed và một added, làm mất câu chuyện “cùng method nhưng wire contract đã đổi”.

### 9.6. Web IDL overload

Các declaration cùng `Interface.member` được dedupe thành:

- `signatures`: toàn bộ signature;
- `overload_traits`: thông tin arity/optional/variadic;
- `overload_locations`: vị trí source.

Diff không chỉ đếm parameter. `_arity_range` tính khoảng số argument thực sự nhận được, và `_overload_signals` phát hiện overload add/remove/shadow; xem [diff.py:959](/Users/m/project/sbcompare2chrom/chromedrift/diff.py:959) và [diff.py:1000](/Users/m/project/sbcompare2chrom/chromedrift/diff.py:1000).

### 9.7. Các post-pass sửa identity

Semantic key không thể luôn giữ nguyên khi chính external string đổi. Hai post-pass cố gắng ghép lại:

- feature/pref/switch remove + add có cùng C++ variable → rename;
- WebUI control remove + add có cùng page và id/label → repointed.

Điều này hữu ích vì một pref string đổi tên nên là “contract rename” chứ không phải hai sự kiện không liên quan. Tuy nhiên các rename không có đủ bằng chứng vẫn có thể còn dạng removed + added và cần review thủ công.

---

## 10. Signal, severity, bucket, owner và score

### 10.1. Năm khái niệm không được trộn

| Khái niệm | Câu hỏi nó trả lời |
|---|---|
| Signal | Chính xác loại thay đổi nào đã xảy ra? |
| Severity | Nếu loại thay đổi này liên quan tới sản phẩm, chi phí/rủi ro lý thuyết là bao nhiêu? |
| Bucket | Hậu quả thuộc breaking, behaviour, new hay housekeeping? |
| Owner | Nhóm nào phải kiểm tra hoặc sửa? |
| Score | Trong chính lần chạy này, nên xem finding sớm đến đâu sau khi xét platform và evidence? |

Score là heuristic ưu tiên từ 0 đến 100, không phải xác suất “browser sẽ hỏng”.

### 10.2. Tạo signal như thế nào

Dispatcher ở [diff.py:1069](/Users/m/project/sbcompare2chrom/chromedrift/diff.py:1069). Một Change có thể có nhiều signal.

| Surface | Các câu hỏi semantic chính |
|---|---|
| Base feature | Default Windows bật/tắt? Feature bị xóa khi trước đó on hay off? String hay symbol đổi? Build condition đổi? |
| Blink runtime | Stable/experimental đổi? Web API ship/unship? Base-feature wiring hoặc origin trial đổi? |
| Web IDL | Interface/member add/remove? API live, gated hay unknown? Signature, exposure, overload hay shape đổi? |
| Mojo | Signature, ordinal, wire shape, enum value, annotation, stability hay build gate đổi? |
| Feature param | Param bị xóa, default đổi, owner/type/symbol đổi? |
| Pref/switch | External string đổi, symbol đổi, build state đổi, hay chỉ biến mất khỏi scan? |
| Flag metadata | Expiry đến gần target milestone hay chỉ chuyển mốc? |
| WebUI | Route/control/gate add/remove/move/regate/repoint/type/label/expression đổi? |

Các rule chung còn thêm `declaration_moved`, `build_gate_changed` hoặc `ipc_stability_changed` khi phù hợp.

### 10.3. Chọn leading signal và severity

Công thức implementation:

```text
leading_signal(change)
  = signal có SIGNAL_SEVERITY lớn nhất
  = nếu bằng điểm, chọn theo tên để kết quả ổn định

severity(change)
  = SIGNAL_SEVERITY[leading_signal]            nếu có signal
  = BASE_SEVERITY[(kind, change_type)]         nếu không có signal
  = 20                                         nếu không có cả hai
```

Code tại [diff.py:860](/Users/m/project/sbcompare2chrom/chromedrift/diff.py:860) và [diff.py:874](/Users/m/project/sbcompare2chrom/chromedrift/diff.py:874).

Điểm rất dễ trình bày sai: khi có signal, base severity **không phải điểm sàn** và không lấy `max(base, signal)`. Signal cụ thể thay thế hoàn toàn phỏng đoán theo kind/direction.

### 10.4. Bảng `BASE_SEVERITY` đầy đủ

Bảng thật có 48 cặp tại [diff.py:143](/Users/m/project/sbcompare2chrom/chromedrift/diff.py:143):

| Fact kind | Added | Removed | Modified |
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

Base table chỉ dùng khi không có signal cụ thể.

### 10.5. Bảng 60 signal severity đầy đủ

Nguồn code hiện tại tại [diff.py:198](/Users/m/project/sbcompare2chrom/chromedrift/diff.py:198). `SKILL.md` vẫn ghi “55 signals” tại [SKILL.md:226](/Users/m/project/sbcompare2chrom/skills/analyzing-chromium-uprevs/SKILL.md:226), nhưng mapping runtime hiện có 60; khi thẩm định phải coi code là nguồn đúng và nên sửa con số trong skill.

| Signal | Severity | Signal | Severity |
|---|---:|---|---:|
| `build_gate_changed` | 35 | `declaration_moved` | 25 |
| `default_flip_off` | 50 | `default_flip_on` | 60 |
| `disabled_by_default` | 60 | `enabled_by_default` | 75 |
| `experimental_dropped` | 20 | `feature_deleted` | 65 |
| `feature_string_renamed` | 75 | `feature_symbol_renamed` | 60 |
| `flag_expiring` | 45 | `flag_expiry_moved` | 10 |
| `flag_retired_off` | 30 | `flag_retired_on` | 35 |
| `ipc_enum_changed` | 55 | `ipc_field_annotated` | 35 |
| `ipc_ordinal_changed` | 80 | `ipc_removed` | 75 |
| `ipc_shape_changed` | 80 | `ipc_signature_change` | 80 |
| `ipc_stability_changed` | 40 | `killswitch_retired` | 35 |
| `new_feature_on_by_default` | 55 | `origin_trial_change` | 35 |
| `param_default_changed` | 40 | `param_removed` | 35 |
| `param_rewired` | 35 | `pref_left_scan` | 35 |
| `pref_renamed` | 70 | `pref_symbol_renamed` | 55 |
| `runtime_flag_rewired` | 30 | `switch_left_scan` | 30 |
| `switch_renamed` | 60 | `switch_symbol_renamed` | 45 |
| `ui_control_added` | 25 | `ui_control_relabelled` | 20 |
| `ui_control_removed` | 35 | `ui_control_repointed` | 50 |
| `ui_control_type_changed` | 45 | `ui_gate_added` | 25 |
| `ui_gate_changed` | 45 | `ui_gate_removed` | 40 |
| `ui_page_added` | 40 | `ui_page_moved` | 30 |
| `ui_page_regated` | 45 | `ui_page_removed` | 55 |
| `web_api_added` | 30 | `web_api_added_gated` | 20 |
| `web_api_added_live` | 35 | `web_api_exposure_changed` | 45 |
| `web_api_overload_added` | 25 | `web_api_overload_removed` | 60 |
| `web_api_overload_shadowed` | 45 | `web_api_removed` | 70 |
| `web_api_removed_gated` | 30 | `web_api_shape_changed` | 45 |
| `web_api_shipped` | 65 | `web_api_signature_change` | 50 |
| `web_api_status_moved` | 25 | `web_api_unshipped` | 70 |

### 10.6. Bucket

Bucket ban đầu:

```text
nếu có leading signal:
  SIGNAL_BUCKET[leading signal]
nếu không có signal và added:
  New surface
nếu không có signal và removed:
  Housekeeping
nếu không có signal và modified:
  Behaviour change
```

Code tại [diff.py:903](/Users/m/project/sbcompare2chrom/chromedrift/diff.py:903), bảng signal-to-bucket tại [diff.py:441](/Users/m/project/sbcompare2chrom/chromedrift/diff.py:441).

| Bucket | Nghĩa đúng trong report |
|---|---|
| Breaking | Contract bên ngoài binary có thể ngừng hoạt động mà không được compiler cảnh báo |
| Behaviour change | Windows build hành xử khác; người dùng có thể thấy |
| New surface | Khai báo/surface mới; riêng việc xuất hiện chưa có nghĩa đã bật cho user |
| Housekeeping | Cleanup, scheduling hoặc evidence chưa đủ để kết luận observable change |

Định nghĩa canonical ở [model.py:775](/Users/m/project/sbcompare2chrom/chromedrift/model.py:775).

### 10.7. Owner

Nếu leading signal có override thì dùng `SIGNAL_OWNERS`; nếu không, dùng owner theo Fact kind. Code tại [diff.py:926](/Users/m/project/sbcompare2chrom/chromedrift/diff.py:926) và [diff.py:946](/Users/m/project/sbcompare2chrom/chromedrift/diff.py:946).

| Owner | Fact kinds hoặc trường hợp |
|---|---|
| `ipc` | Năm Mojo kinds |
| `webplatform` | Blink runtime và hai Web IDL kinds |
| `native` | Base feature, param, pref, switch, flag metadata |
| `webui` | Route, control, gate |
| `config` | Override theo signal: feature string rename, switch rename, param remove/rewire, retired/expiring flag |

Owner nghĩa là “nơi có hành động sửa/kiểm tra”, không nhất thiết là “nơi user quan sát lỗi”.

### 10.8. Coverage được dùng trong score

Coverage tổng và per-surface được tính:

```text
coverage_share = read / candidates
```

Mapping kind → surface ở [score.py:82](/Users/m/project/sbcompare2chrom/chromedrift/score.py:82). Ngưỡng để xác nhận một sự vắng mặt:

```text
CONFIRMING_COVERAGE = 0.95
UNCONFIRMED_PENALTY = 15
```

Hai hằng số tại [score.py:49](/Users/m/project/sbcompare2chrom/chromedrift/score.py:49).

Nếu snapshot cũ không có measurement coverage theo schema hiện tại, `_share` trả về unknown và implementation cố ý coi unknown là không cần trừ điểm, miễn không có hard hole. Quy tắc này nằm tại [score.py:195](/Users/m/project/sbcompare2chrom/chromedrift/score.py:195). Vì vậy report dùng cache/schema cũ phải ghi rõ coverage unknown; không nên diễn giải nó như coverage 100%.

Phía evidence phụ thuộc direction:

- Removed nghĩa là “không còn trong TO”, nên xét coverage/hole của TO.
- Added nghĩa là “không có trong FROM”, nên hard hole của FROM có thể làm mất khả năng gọi nó là New surface.
- Modified overload có signature bị mất xét như removed; có signature mới xét như added.

Logic hai phía trong `Scope` tại [score.py:119](/Users/m/project/sbcompare2chrom/chromedrift/score.py:119).

### 10.9. Công thức score chính xác

```text
nếu mọi phía tồn tại của declaration đều not_compiled trên Windows:
    score  = 0
    bucket = Housekeeping
ngược lại:
    score = severity

    nếu change dựa trên absence và phía evidence không đạt 95%
       hoặc phía đó có missing target/parser error:
        score = score - 15

    nếu leading signal là pref_left_scan hoặc switch_left_scan
       và absence chưa được xác nhận:
        bucket = Housekeeping

    nếu change là addition, bucket ban đầu là New
       nhưng FROM có missing target/parser error:
        bucket = Housekeeping

    score = min(100, max(0, score))
```

Hai điểm tinh tế:

- Partial coverage của FROM không tự trừ mọi addition chỉ vì thứ gì đó có thể từng nằm trong file không đọc. Code chỉ áp penalty cho addition khi FROM có hard hole như missing target/parser error; xem [score.py:261](/Users/m/project/sbcompare2chrom/chromedrift/score.py:261).
- Declaration đi vào hoặc rời Windows build không bị đưa về 0, vì chính chuyển động đó là thay đổi. Chỉ declaration ở ngoài Windows trong mọi phía tồn tại mới về 0; xem [score.py:213](/Users/m/project/sbcompare2chrom/chromedrift/score.py:213).

Mọi deduction phải thêm câu giải thích vào `reasons`, rồi `score_all` sort theo `(-score, kind, key)` tại [score.py:331](/Users/m/project/sbcompare2chrom/chromedrift/score.py:331).

### 10.10. Bốn ví dụ chấm điểm

#### Ví dụ A — Mojo method đổi signature

```text
kind                  mojo_method
change                modified
signal                ipc_signature_change
severity              80
Windows               có compile
absence evidence       không áp dụng
score                  80
bucket                 Breaking
owner                  ipc
```

Lý do: signature là wire contract; cả hai phía đều có Fact nên không cần suy luận từ sự vắng mặt.

#### Ví dụ B — Pref biến mất trong default scan

```text
kind                  pref
change                removed
signal                pref_left_scan
severity              35
coverage TO/pref      80%
penalty               -15
score                  20
bucket ban đầu         Breaking
bucket sau evidence    Housekeeping
owner                  native
```

Lý do: tool chỉ biết pref không còn trong các file đã đọc. Với coverage dưới 95%, nó có thể đã chuyển sang file không được target mở.

#### Ví dụ C — Declaration Android-only ở cả hai phía

```text
severity              45
platform_state        windows = not_compiled ở mọi phía tồn tại
score                  0
bucket                 Housekeeping
```

Lý do: declaration đó không đi vào Windows product mà đề tài đang đánh giá.

#### Ví dụ D — Settings route bị xóa

```text
kind                  webui_route
signal                ui_page_removed
severity              55
Settings coverage TO   100%
missing/parser error   không có
score                  55
bucket                 Behaviour change
owner                  webui
```

Sau đó vẫn phải follow guard/feature và đọc `page_visibility.ts` thủ công trước khi nói “user chắc chắn mất trang”.

### 10.11. Vì sao score này hợp lý và giới hạn của nó

Hợp lý:

- deterministic và audit được;
- signal cụ thể thắng prior chung;
- không tăng điểm bằng phỏng đoán;
- severity 80 dành cho wire-shape/signature/ordinal thay đổi;
- absence bị hạ khi scope không đủ;
- Windows-out-of-build không tranh vị trí với thay đổi product.

Giới hạn:

- con số do maintainer quy định, không được hiệu chỉnh bằng thống kê incident thực tế;
- 80 không có nghĩa 80% lỗi;
- score không biết fork công ty có call method hay dùng pref đó không;
- coverage theo file không phải grammar completeness;
- một attr không có trong whitelist sẽ không tạo Change dù extractor đã lưu nó;
- cluster không làm score thông minh hơn.

---

## 11. Cluster và báo cáo

### 11.1. Cluster hoạt động như thế nào

Cluster dùng union-find và chỉ nối khi có liên kết khai báo trực tiếp; implementation tại [cluster.py:94](/Users/m/project/sbcompare2chrom/chromedrift/cluster.py:94).

```text
webui_route  --guards-->       webui_gate
webui_gate   --features-->     base_feature
blink_runtime --base_feature-> base_feature
feature_param --feature-->     base_feature
webui_control --id/label-->    webui_route
```

Nó đọc attrs cả before và after để route đổi guard vẫn có thể giữ câu chuyện hai phía. Chỉ component có ít nhất hai finding mới trở thành cluster.

`annotate` gắn vào từng finding:

```text
id
label
size
kinds
top_score
```

Code tại [cluster.py:184](/Users/m/project/sbcompare2chrom/chromedrift/cluster.py:184).

### 11.2. Cluster không làm gì

- Không nối bằng fuzzy name similarity chung.
- Không tự nối control → pref; liên kết này có trong reference closure nhưng không có trong cluster hiện tại.
- Không thay score, severity, bucket hay owner.
- Chỉ cluster các **finding thay đổi**. Nếu node giữa không thay đổi nên không có finding, nó không luôn làm cầu nối giữa hai finding khác.
- Không chứng minh các member cùng cluster là một product capability duy nhất; người đọc vẫn phải xác nhận.

### 11.3. Nội dung report

`Report` được định nghĩa tại [model.py:829](/Users/m/project/sbcompare2chrom/chromedrift/model.py:829) và được dựng tại [cli.py:187](/Users/m/project/sbcompare2chrom/chromedrift/cli.py:187). Nội dung gồm:

- findings;
- change count và by-kind;
- by-bucket, by-owner, by-group, by-signal;
- clusters;
- milestone brief nếu enrich;
- coverage FROM và TO;
- missing targets;
- unresolved references;
- out-of-scope files;
- target set, partitions, complete và tool version.

### 11.4. Ba output dùng khi nào

| File | Vai trò |
|---|---|
| `report.json` | Nguồn dữ liệu đầy đủ/canonical; dùng cho automation, AI và audit |
| `report.md` | Tóm tắt tuần tự; dùng trong ticket hoặc báo cáo kỹ thuật |
| `report.html` | Triage tương tác; filter theo bucket, surface, group, owner và search |

Markdown render theo thứ tự bucket counts, owner routing, what happened, WebUI screens, clusters, milestone context, các bảng finding và provenance; entry tại [report/markdown.py:110](/Users/m/project/sbcompare2chrom/chromedrift/report/markdown.py:110).

Housekeeping vẫn có đầy đủ trong JSON/HTML dù Markdown không in bảng dài cho tất cả housekeeping rows; xem [report/markdown.py:152](/Users/m/project/sbcompare2chrom/chromedrift/report/markdown.py:152).

---

## 12. Luồng riêng khi chỉ quan tâm Settings

### 12.1. Trước hết phải nói rõ “một Settings feature” lớn đến đâu

Skill chia ba mức tại [settings-surface.md:54](/Users/m/project/sbcompare2chrom/skills/analyzing-chromium-uprevs/reference/settings-surface.md:54):

| Mức | Ví dụ | Evidence chính |
|---|---|---|
| Control | Một toggle đổi thành dropdown | Template `.html` hoặc `.html.ts` |
| Page/entry | Thêm hoặc xóa một route | `route.ts` hoặc `routes.ts` |
| Capability | Một migration gồm route, controls, flags, Blink hoặc Mojo liên quan | Cluster theo liên kết khai báo và kiểm tra source thủ công |

Nếu nói “chỉ so Setting feature X” nhưng không chốt mức này, hai người có thể trả hai báo cáo rất khác nhau mà đều nghĩ mình đúng.

### 12.2. Lệnh nhanh trong quá trình phát triển

```bash
python3 -m chromedrift run 148.0.7778.217 151.0.7922.138 \
  --from-src /path/to/chromium-148/src \
  --to-src /path/to/chromium-151/src \
  --partition settings \
  --no-enrich \
  --out out/settings-fast
```

Đúng khi:

- đang phát triển parser;
- triage nhanh một route/control cụ thể;
- muốn chi phí nhỏ.

Không đúng khi cần kết luận đầy đủ cho cả đợt uprev.

### 12.3. Lệnh khuyến nghị cho một vòng phân tích Settings

```bash
python3 -m chromedrift run 148.0.7778.217 151.0.7922.138 \
  --from-src /path/to/chromium-148/src \
  --to-src /path/to/chromium-151/src \
  --partition settings \
  --complete \
  --no-enrich \
  --out out/settings-complete
```

`--complete` chỉ hợp lệ với các partition có root đủ nhỏ; Settings nằm trong danh sách closable tại [targets.py:717](/Users/m/project/sbcompare2chrom/chromedrift/targets.py:717).

### 12.4. Bảy target của Settings partition

Ba core files:

```text
chrome/common/pref_names.h
chrome/browser/flag-metadata.json
content/public/common/content_switches.cc
```

Bốn target riêng Settings:

```text
chrome/common/chrome_features.cc
chrome/common/chrome_features.h
chrome/browser/resources/settings
chrome/browser/ui/webui
```

Tổng cộng bảy target descriptor. Nguồn partition tại [targets.py:637](/Users/m/project/sbcompare2chrom/chromedrift/targets.py:637).

Với `--complete`:

- tree `chrome/browser/resources/settings` giữ mọi suffix trong `READABLE_SUFFIXES`;
- tree `chrome/browser/ui/webui` giữ mọi suffix trong `READABLE_SUFFIXES` cộng toàn bộ `.cc`;
- năm exact files còn lại giữ nguyên.

Vì vậy `complete` nghĩa là “đọc hoàn chỉnh các dạng file extractor hiểu bên trong các root đã chọn”, không có nghĩa “mọi dependency của Settings trên toàn Chromium”.

### 12.5. Cảnh báo về `--target-set wide --partition settings`

Không dùng lệnh này với kỳ vọng nó rộng hơn Settings partition:

```bash
python3 -m chromedrift run FROM TO \
  --target-set wide \
  --partition settings \
  --out out/settings-wide-name-only
```

Theo `get_targets`, khi có partition, target list được lọc bằng việc target path phải bắt đầu bằng partition prefix; wide root lớn như `components` hoặc `chrome/browser` không bắt đầu bằng prefix hẹp `chrome/browser/resources/settings`, nên bị loại tại [targets.py:776](/Users/m/project/sbcompare2chrom/chromedrift/targets.py:776).

Kết quả hiện tại vẫn là bảy Settings target nói trên. Tên `wide` trong command không biến nó thành “Settings wide”.

### 12.6. Lệnh dùng làm bằng chứng trước review uprev chính thức

Chạy full wide, không partition:

```bash
python3 -m chromedrift run 148.0.7778.217 151.0.7922.138 \
  --from-src /path/to/chromium-148/src \
  --to-src /path/to/chromium-151/src \
  --target-set wide \
  --no-enrich \
  --out out/full-wide
```

Sau đó lọc report theo:

- kind `webui_route`, `webui_control`, `webui_gate`;
- path chứa `settings`;
- cluster liên quan;
- base feature, pref, switch, Mojo hoặc Web API mà Settings feature tham chiếu.

Full wide tăng cơ hội tìm được feature/pref nằm ngoài Settings roots. Nó vẫn không đọc generic TypeScript behavior, `page_visibility.ts`, `.grd` hoặc fork công ty.

### 12.7. Luồng dữ liệu Settings

```text
chrome/browser/resources/settings/route.ts
    │
    │ extractor webui_routes
    ▼
webui_route Fact: route + parent + guards
    │
    │ guard là bare loadTimeData key
    ▼
chrome/browser/ui/webui/**/*.cc
    │
    │ extractor webui_gates đọc AddBoolean/AddInteger/AddString/AddDouble
    ▼
webui_gate Fact: data_key + expression + feature variables
    │
    │ feature variable được chuẩn hóa bỏ tiền tố k
    ▼
base_feature Fact

chrome/browser/resources/settings/**/*.html hoặc **/*.html.ts
    │
    │ extractor webui_controls
    ▼
webui_control Fact: type + pref binding + label + id + build conditions
    │
    │ pref string exact
    ▼
pref Fact
```

Source authority ba-hop được mô tả tại [settings-surface.md:25](/Users/m/project/sbcompare2chrom/skills/analyzing-chromium-uprevs/reference/settings-surface.md:25).

### 12.8. Luồng từng bước nếu chỉ điều tra một Settings feature X

Giả sử feature có một trong các identifier đã biết: route constant, route path, loadTimeData key, feature variable, pref key, element id hoặc control label.

#### Step S1 — Pin input

Ghi rõ:

```text
FROM exact version
TO exact version
Windows desktop
feature/capability X
identifier đã biết
```

#### Step S2 — Chạy `settings --complete`

Mục tiêu là có route/control/gate evidence nhanh và reference closure trong bounded Settings roots.

#### Step S3 — Tìm mọi Fact liên quan X trong `report.json`

Không chỉ tìm tên marketing. Tìm lần lượt:

```text
route constant
route path
loadTimeData key
base::Feature variable và feature string
pref key
element id
label key
Mojo/Web IDL identifier nếu capability có contract đó
```

#### Step S4 — Theo route chain

```text
route Fact
→ attrs.guards
→ gate Fact có attrs.data_key tương ứng
→ attrs.features hoặc attrs.enabled_checks
→ base_feature Fact
→ platform_state.windows và default_state
```

Không dừng ở việc route added/removed. Route có thể vẫn được khai báo nhưng gate off, hoặc bị bỏ sau khi feature đã ship.

#### Step S5 — Theo control chain

```text
control Fact
→ attrs.pref
→ pref Fact
→ tìm tất cả chỗ fork công ty đọc/ghi pref string và C++ variable
```

Kiểm tra `control`, `label`, `element_id` và `build_conditions` để phân biệt redesign với behavior change.

#### Step S6 — Đọc reference closure

Nếu report có unresolved `gate`, `feature` hoặc `pref`, không được kết luận chain hoàn chỉnh. Chuyển sang full wide hoặc tìm declaration thủ công.

Lưu ý closure hiện chỉ kiểm tra snapshot TO. Một link chỉ tồn tại ở FROM rồi biến mất không xuất hiện trong closure TO.

#### Step S7 — Chạy full wide nếu là đánh giá chính thức

Tìm dependency ngoài Settings, đặc biệt:

```text
components/
content/
services/
net/
third_party/blink/
Mojo contracts
Blink runtime/Web IDL contracts
```

#### Step S8 — Kiểm tra file ChromeDrift không đọc

Tối thiểu đọc thủ công:

```text
chrome/browser/resources/settings/page_visibility.ts
TypeScript handler liên quan feature X
BUILD.gn nếu platform/dependency là câu hỏi
.grd nếu label/value hiển thị là câu hỏi
Finch/policy/enterprise config nếu feature được điều khiển bên ngoài
```

#### Step S9 — Tìm trong fork browser công ty

Tìm cả external string và C++ symbol:

```text
feature string
kFeatureSymbol
pref string
kPrefSymbol
command-line switch string
Mojo qualified method/type
Web IDL interface/member
route path
loadTimeData key
```

Đây là bước trả lời “có ảnh hưởng đến chúng ta không”; ChromeDrift chỉ trả lời “Chromium đã đổi gì”.

#### Step S10 — Test có mục tiêu và kết luận ba mức

```text
Phát hiện: source declaration nào đổi
Khả năng ảnh hưởng: chain nào đi tới Settings X
Xác nhận: fork có dùng và test nào chứng minh
```

### 12.9. Những gì Settings flow hiện tại dễ bỏ sót

- Route/page visibility quyết định trong `page_visibility.ts`.
- Logic TypeScript không nằm trong route/template grammar.
- Gate được tính từ các lời gọi `Add*`; một expression khác cách viết có thể khó nối tự động.
- `webui_gates` quét toàn bộ `chrome/browser/ui/webui/**/*.cc`, nên Settings report có thể có gate của WebUI khác.
- Một feature/pref nằm ngoài bảy target sẽ unresolved hoặc hoàn toàn không xuất hiện.
- Label key được đọc nhưng value dịch thực tế không được đọc.
- Control được render động mà không có template declaration nhận dạng được có thể bị bỏ sót.
- Cluster không nối control với pref.
- “Reference closure complete” chỉ nói mọi link **đã được parser nhận ra trong TO snapshot** tìm thấy đích; nó không chứng minh parser nhận ra mọi dependency.

### 12.10. Quy trình hai vòng được khuyến nghị

```text
Vòng 1 — Settings complete
  nhanh, dùng để triage route/control/gate và tìm unresolved links

Vòng 2 — Full wide
  dùng trước review chính thức để tìm dependency ngoài Settings

Sau hai vòng
  đọc page_visibility.ts + tìm fork + build/runtime test có mục tiêu
```

---

## 13. Guard rail, giới hạn và rủi ro cần trình bày

### 13.1. Guard rail đang có

| Guard rail | Hành vi | Source |
|---|---|---|
| Platform cố định | Windows không có CLI option để đổi tùy tiện | [_cpp.py:35](/Users/m/project/sbcompare2chrom/chromedrift/extract/_cpp.py:35) |
| Cache identity | Cache snapshot chứa ref, target set, partitions và complete | [snapshot.py:31](/Users/m/project/sbcompare2chrom/chromedrift/snapshot.py:31) |
| Schema gate | Cache khác schema bị rebuild | [snapshot.py:71](/Users/m/project/sbcompare2chrom/chromedrift/snapshot.py:71) |
| Target scope | File thừa từ cache cũ không được extractor đọc | [snapshot.py:148](/Users/m/project/sbcompare2chrom/chromedrift/snapshot.py:148) |
| All targets missing | Dừng bằng `AcquireError` | [snapshot.py:135](/Users/m/project/sbcompare2chrom/chromedrift/snapshot.py:135) |
| Fetch error | Không âm thầm đổi network error thành missing | [acquire.py:335](/Users/m/project/sbcompare2chrom/chromedrift/acquire.py:335) |
| Snapshot mismatch | Từ chối khác target-set/partition/complete | [diff.py:673](/Users/m/project/sbcompare2chrom/chromedrift/diff.py:673) |
| Lopsided facts | Từ chối run lớn nếu một phía dưới 50% phía kia | [diff.py:753](/Users/m/project/sbcompare2chrom/chromedrift/diff.py:753) |
| Missing/parse hole | Hạ score cho kết luận dựa trên absence | [cli.py:277](/Users/m/project/sbcompare2chrom/chromedrift/cli.py:277) |
| Deterministic walk/dedupe | Sort filesystem traversal và giữ kết quả xác định | [extract/__init__.py:151](/Users/m/project/sbcompare2chrom/chromedrift/extract/__init__.py:151) |
| Optional enrichment | ChromeStatus không phải điều kiện cho semantic diff | [cli.py:163](/Users/m/project/sbcompare2chrom/chromedrift/cli.py:163) |

### 13.2. Coverage phải được diễn giải đúng

Coverage hiện tại là **file coverage trong discovery roots**:

```text
số candidate file target chạm tới / số candidate file discovery tìm thấy
```

Nó không phải:

- phần trăm toàn bộ file Chromium;
- phần trăm toàn bộ declaration;
- phần trăm grammar đã parse;
- phần trăm capability của browser;
- xác suất không bỏ sót regression.

Một file lớn có thể chứa hàng trăm declaration, một file nhỏ chỉ một. Vì vậy 95% file không đồng nghĩa 95% Fact hoặc 95% rủi ro.

### 13.3. Reference closure phải được diễn giải đúng

Closure tốt hơn coverage file ở chỗ nó kiểm tra graph do data khai báo. Nhưng nó vẫn bị giới hạn bởi:

- chỉ link mà parser biết;
- hiện chỉ chạy cho TO;
- không đọc TypeScript call graph, BUILD graph hoặc runtime dependency;
- empty unresolved list không chứng minh parser grammar complete.

### 13.4. Parser là regex/structured parser có chủ đích, không phải compiler Chromium

Điểm mạnh:

- nhẹ, thuần Python, dễ cache;
- test từng string độc lập;
- đủ tốt cho declaration có shape ổn định;
- không cần build hàng giờ.

Rủi ro:

- macro/preprocessor phức tạp có thể không được hiểu hết;
- syntax Chromium mới có thể vượt grammar cũ;
- generic code behavior không có declaration change sẽ vô hình;
- parse error được đếm, nhưng parser có thể parse thiếu mà không throw error.

### 13.5. Các quyết định attrs hiện cần review thêm

Hội đồng nên yêu cầu maintainer giải thích hoặc thêm test cho:

- vì sao `flag_entry.owners` không meaningful;
- vì sao `webui_route.route_kind` không meaningful;
- vì sao `webui_gate.value_type` không meaningful;
- behavior mong muốn khi `webui_control.element_id` đổi;
- member-level `stable` của Mojo có cần diff trực tiếp không;
- closure có cần chạy cả FROM và TO không.

### 13.6. Sự không nhất quán tài liệu đã xác nhận

- Runtime mapping có 60 signals, trong khi skill vẫn nói 55 tại [SKILL.md:231](/Users/m/project/sbcompare2chrom/skills/analyzing-chromium-uprevs/SKILL.md:231).
- Vì vậy các con số mô tả trong skill/report không nên được tin lâu dài nếu không được sinh từ code hoặc test tự động.

### 13.7. Verdict kỹ thuật hợp lý

> Chấp nhận ChromeDrift như công cụ discovery, evidence normalization và triage có tính deterministic. Không chấp nhận nó như release gate độc lập. Muốn dùng trong quy trình chính thức phải bắt buộc full-wide evidence, công bố coverage/holes, kiểm tra fork và test có mục tiêu.

---

## 14. Cách đánh giá phương án trước hội đồng kỹ thuật

### 14.1. Cấu trúc trình bày 10–15 phút

#### Phút 1 — Nêu vấn đề

“Chromium cập nhật liên tục. Raw git diff quá lớn và không trả lời trực tiếp contract nào ảnh hưởng browser riêng. Team cần một bước máy móc để thu hẹp hàng nghìn thay đổi thành evidence có cấu trúc.”

#### Phút 2–3 — Nêu ranh giới trách nhiệm

“ChromeDrift chỉ so Chromium với Chromium và xếp hạng. Skill/human mới đối chiếu fork và đưa verdict. Chúng ta cố ý không để AI tự biến source diff thành quyết định release.”

#### Phút 4–6 — Trình bày pipeline

```text
target → extractor → Fact → snapshot → semantic diff
→ signal/severity → evidence-adjusted score → cluster → report
→ kiểm tra fork → targeted tests → quyết định
```

#### Phút 7–9 — Giải thích hai quyết định thiết kế

1. Chọn declaration surfaces thay vì toàn bộ thân hàm vì cần semantic identity ổn định và chi phí thấp.
2. Tách chín extractor theo grammar/source authority, nhưng chuẩn hóa về một Fact model chung để diff thống nhất.

#### Phút 10–11 — Demo một finding

Nên chọn một ví dụ Mojo signature đổi hoặc Settings route → gate → feature. Trình bày đủ:

```text
source cũ/mới
Fact cũ/mới
delta
signal
severity
coverage/platform adjustment
score/bucket/owner
fork usage
test đề xuất
```

#### Phút 12–13 — Nói giới hạn trước khi bị hỏi

“Wide không phải all source; coverage là file coverage; parser không đọc function body, generic TS, BUILD.gn, Finch server hay fork. Vì vậy report là evidence đầu vào, không phải giấy chứng nhận tương thích.”

#### Phút 14–15 — Xin quyết định cụ thể

Đề nghị hội đồng phê duyệt:

- pilot trong vài đợt uprev;
- dùng Settings complete cho triage, full wide cho review chính thức;
- bắt buộc path:line, coverage, missing/error và unresolved references;
- đo precision/recall trên các incident hoặc breaking changes đã biết;
- chỉ nâng thành release gate sau khi có tiêu chí đo và kiểm tra downstream fork.

### 14.2. Các câu hỏi hội đồng có thể hỏi và câu trả lời ngắn

#### “Tại sao chọn API, flag, setting, Mojo và WebUI?”

Vì đây là các contract/công tắc có source of truth rõ, semantic identity ổn định, ảnh hưởng uprev cao và có thể parse không cần build. Chúng bao phủ website, process boundary, profile/script, hành vi feature và UI. Đây không phải toàn bộ Chromium; implementation-only change vẫn ngoài scope.

#### “Tại sao đúng chín bộ đọc?”

Vì hiện có chín grammar/source authority độc lập. Con số có thể tăng khi thêm nguồn mới. Tiêu chí là parser/key/attrs/owner riêng, không phải cố đạt một con số định trước.

#### “Tại sao không dùng một AI đọc git diff?”

Parser deterministic cho kết quả lặp lại, có schema, coverage và path:line. AI phù hợp ở bước giải thích và đối chiếu sản phẩm, không phù hợp làm nguồn dữ liệu canonical không audit được.

#### “Tại sao không dùng AST/compile database?”

AST/BUILD-aware analysis có thể chính xác hơn nhưng chi phí build, dependency và platform lớn hơn nhiều. Regex/structured parsers là trade-off cho discovery nhanh. Nếu dùng như gate, cần bổ sung AST/build evidence cho các surface critical.

#### “Tại sao Mojo không được gọi chung là API?”

Mojo đúng là một dạng API contract, nhưng là IPC nội bộ giữa process/component; Web IDL là API hướng ra website. Tách tên giúp owner và compatibility rule đúng: Mojo quan tâm wire type/ordinal, Web IDL quan tâm reachability/exposure/overload.

#### “Tại sao Settings phải tách route, control và gate?”

Vì chúng nằm ở ba source khác nhau và trả lời ba câu hỏi khác nhau: trang nào tồn tại, control nào bind pref, C++ value nào quyết định visibility. Gom một bước sẽ mất chuỗi bằng chứng.

#### “Ai đặt severity 80?”

Đó là policy heuristic trong `SIGNAL_SEVERITY`, không phải xác suất. 80 dành cho signature/ordinal/wire-shape Mojo vì mismatch có thể phá serialization. Hội đồng có thể thay policy, nhưng phải giữ test và reason rõ.

#### “Coverage 100% có nghĩa không bỏ sót?”

Không. Nó chỉ nghĩa target chạm tới toàn bộ candidate file trong denominator/root đã chọn. Nó không chứng minh grammar, behavior, dependency và product usage đầy đủ.

#### “Settings complete có đủ cho một Settings feature không?”

Đủ cho vòng triage route/control/gate trong các Settings roots. Không đủ để kết luận chính thức vì base feature/pref/Mojo có thể nằm ngoài roots; cần full wide, manual files và fork check.

#### “Breaking bucket có nghĩa browser chắc chắn hỏng?”

Không. Nó nghĩa một external contract trong Chromium đã đổi theo rule. Browser công ty chỉ bị ảnh hưởng nếu fork hoặc hệ thống ngoài repo thực sự phụ thuộc contract đó.

### 14.3. Ma trận đánh giá tính hợp lý

| Tiêu chí | Đánh giá hiện tại | Điều kiện nâng mức tin cậy |
|---|---|---|
| Tính lặp lại | Tốt | Giữ deterministic tests và cache identity |
| Audit/evidence | Tốt | Bắt buộc path:line và report.json |
| Chi phí chạy | Hợp lý cho discovery | Theo dõi bandwidth/cache cho wide |
| Coverage file | Có đo, nhưng bounded | Công bố denominator và missed paths |
| Grammar completeness | Chưa đầy đủ | Thêm extractor/grammar tests theo failure thực |
| Windows relevance | Có projection, chưa build-aware hoàn toàn | Đối chiếu BUILD.gn/build output cho critical change |
| Product impact | Không tự biết | Tích hợp search/index của fork và ownership |
| Release decision | Chưa đủ | Full wide + downstream evidence + targeted tests |

### 14.4. Backlog tối thiểu nên yêu cầu

Ưu tiên ngay:

- sửa con số 55/60 signals để docs và code không lệch;
- quyết định/test `owners`, `route_kind`, `value_type`, `element_id` có phải meaningful attrs;
- ghi closure cho cả FROM và TO;
- có golden test trên ít nhất một cặp Chromium thật cho từng extractor;
- đưa “coverage là file coverage, không phải grammar completeness” vào mọi report chính thức.

Ưu tiên tiếp theo:

- tạo chế độ report chỉ lọc Settings nhưng build snapshot từ full wide;
- thêm downstream usage evidence từ source fork của công ty;
- đo false positive/false negative trên các uprev đã biết;
- bổ sung parser cho các grammar ngoài scope nếu incident thực tế chứng minh cần thiết;
- định nghĩa tiêu chí khi nào một finding bắt buộc build test, runtime test hoặc manual review.

---

## 15. Bản đồ source code

### Skill và tài liệu domain

- [skills/analyzing-chromium-uprevs/SKILL.md:1](/Users/m/project/sbcompare2chrom/skills/analyzing-chromium-uprevs/SKILL.md:1) — vai trò, workflow, cách đọc report và giới hạn.
- [reference/settings-surface.md:1](/Users/m/project/sbcompare2chrom/skills/analyzing-chromium-uprevs/reference/settings-surface.md:1) — kiến trúc Desktop Settings và route → gate → feature.
- [reference/signals.md:1](/Users/m/project/sbcompare2chrom/skills/analyzing-chromium-uprevs/reference/signals.md:1) — giải thích signal cho người sử dụng skill.
- [reference/traps.md:1](/Users/m/project/sbcompare2chrom/skills/analyzing-chromium-uprevs/reference/traps.md:1) — các bẫy khi diễn giải uprev.

### Entry và orchestration

- [chromedrift/__main__.py:1](/Users/m/project/sbcompare2chrom/chromedrift/__main__.py:1) — entry của `python -m chromedrift`.
- [chromedrift/cli.py:93](/Users/m/project/sbcompare2chrom/chromedrift/cli.py:93) — pipeline `run`.
- [chromedrift/cli.py:522](/Users/m/project/sbcompare2chrom/chromedrift/cli.py:522) — parser và command-line options.

### Source acquisition, target và scope

- [chromedrift/acquire.py:192](/Users/m/project/sbcompare2chrom/chromedrift/acquire.py:192) — abstraction `Source`.
- [chromedrift/acquire.py:212](/Users/m/project/sbcompare2chrom/chromedrift/acquire.py:212) — `GitilesSource`.
- [chromedrift/acquire.py:380](/Users/m/project/sbcompare2chrom/chromedrift/acquire.py:380) — `LocalSource`.
- [chromedrift/acquire.py:426](/Users/m/project/sbcompare2chrom/chromedrift/acquire.py:426) — `FetchTarget`.
- [chromedrift/targets.py:101](/Users/m/project/sbcompare2chrom/chromedrift/targets.py:101) — discovery roots.
- [chromedrift/targets.py:241](/Users/m/project/sbcompare2chrom/chromedrift/targets.py:241) — discovery candidates.
- [chromedrift/targets.py:325](/Users/m/project/sbcompare2chrom/chromedrift/targets.py:325) — coverage.
- [chromedrift/targets.py:360](/Users/m/project/sbcompare2chrom/chromedrift/targets.py:360) — default targets.
- [chromedrift/targets.py:475](/Users/m/project/sbcompare2chrom/chromedrift/targets.py:475) — minimal targets.
- [chromedrift/targets.py:488](/Users/m/project/sbcompare2chrom/chromedrift/targets.py:488) — wide roots.
- [chromedrift/targets.py:568](/Users/m/project/sbcompare2chrom/chromedrift/targets.py:568) — readable suffixes.
- [chromedrift/targets.py:637](/Users/m/project/sbcompare2chrom/chromedrift/targets.py:637) — partitions.
- [chromedrift/targets.py:730](/Users/m/project/sbcompare2chrom/chromedrift/targets.py:730) — complete partition targets.
- [chromedrift/targets.py:752](/Users/m/project/sbcompare2chrom/chromedrift/targets.py:752) — target selection.
- [chromedrift/eligibility.py:56](/Users/m/project/sbcompare2chrom/chromedrift/eligibility.py:56) — product scope exclusions.

### Snapshot và extractor

- [chromedrift/snapshot.py:62](/Users/m/project/sbcompare2chrom/chromedrift/snapshot.py:62) — build snapshot.
- [chromedrift/extract/__init__.py:32](/Users/m/project/sbcompare2chrom/chromedrift/extract/__init__.py:32) — registry chín extractor.
- [chromedrift/extract/__init__.py:123](/Users/m/project/sbcompare2chrom/chromedrift/extract/__init__.py:123) — chạy extractor trên tree.
- [chromedrift/extract/base_features.py:140](/Users/m/project/sbcompare2chrom/chromedrift/extract/base_features.py:140) — extract base feature/param.
- [chromedrift/extract/blink_runtime.py:78](/Users/m/project/sbcompare2chrom/chromedrift/extract/blink_runtime.py:78) — extract Blink runtime manifest.
- [chromedrift/extract/web_idl.py:231](/Users/m/project/sbcompare2chrom/chromedrift/extract/web_idl.py:231) — extract Web IDL.
- [chromedrift/extract/mojom.py:215](/Users/m/project/sbcompare2chrom/chromedrift/extract/mojom.py:215) — extract Mojo interface/method.
- [chromedrift/extract/mojom.py:451](/Users/m/project/sbcompare2chrom/chromedrift/extract/mojom.py:451) — extract Mojo struct/field/enum.
- [chromedrift/extract/constants.py:68](/Users/m/project/sbcompare2chrom/chromedrift/extract/constants.py:68) — extract pref/switch.
- [chromedrift/extract/flags_metadata.py:44](/Users/m/project/sbcompare2chrom/chromedrift/extract/flags_metadata.py:44) — extract flags metadata.
- [chromedrift/extract/webui_routes.py:93](/Users/m/project/sbcompare2chrom/chromedrift/extract/webui_routes.py:93) — extract route.
- [chromedrift/extract/webui_controls.py:210](/Users/m/project/sbcompare2chrom/chromedrift/extract/webui_controls.py:210) — extract control.
- [chromedrift/extract/webui_gates.py:67](/Users/m/project/sbcompare2chrom/chromedrift/extract/webui_gates.py:67) — extract gate.

### Model, diff, score, cluster và report

- [chromedrift/model.py:589](/Users/m/project/sbcompare2chrom/chromedrift/model.py:589) — `Fact`.
- [chromedrift/model.py:633](/Users/m/project/sbcompare2chrom/chromedrift/model.py:633) — `Snapshot`.
- [chromedrift/model.py:686](/Users/m/project/sbcompare2chrom/chromedrift/model.py:686) — `Change`.
- [chromedrift/model.py:789](/Users/m/project/sbcompare2chrom/chromedrift/model.py:789) — `Finding`.
- [chromedrift/model.py:829](/Users/m/project/sbcompare2chrom/chromedrift/model.py:829) — `Report`.
- [chromedrift/model.py:916](/Users/m/project/sbcompare2chrom/chromedrift/model.py:916) — dedupe Facts và Web IDL overload aggregation.
- [chromedrift/diff.py:61](/Users/m/project/sbcompare2chrom/chromedrift/diff.py:61) — meaningful attrs.
- [chromedrift/diff.py:143](/Users/m/project/sbcompare2chrom/chromedrift/diff.py:143) — base severity.
- [chromedrift/diff.py:198](/Users/m/project/sbcompare2chrom/chromedrift/diff.py:198) — signal severity.
- [chromedrift/diff.py:441](/Users/m/project/sbcompare2chrom/chromedrift/diff.py:441) — signal bucket.
- [chromedrift/diff.py:673](/Users/m/project/sbcompare2chrom/chromedrift/diff.py:673) — semantic diff.
- [chromedrift/diff.py:860](/Users/m/project/sbcompare2chrom/chromedrift/diff.py:860) — leading signal.
- [chromedrift/diff.py:946](/Users/m/project/sbcompare2chrom/chromedrift/diff.py:946) — owner.
- [chromedrift/score.py:102](/Users/m/project/sbcompare2chrom/chromedrift/score.py:102) — evidence Scope.
- [chromedrift/score.py:242](/Users/m/project/sbcompare2chrom/chromedrift/score.py:242) — scoring.
- [chromedrift/cluster.py:94](/Users/m/project/sbcompare2chrom/chromedrift/cluster.py:94) — clustering.
- [chromedrift/catalog.py:235](/Users/m/project/sbcompare2chrom/chromedrift/catalog.py:235) — unresolved references.
- [chromedrift/report/markdown.py:110](/Users/m/project/sbcompare2chrom/chromedrift/report/markdown.py:110) — Markdown report.
- [chromedrift/report/html.py:422](/Users/m/project/sbcompare2chrom/chromedrift/report/html.py:422) — HTML row data.

---

## Kết luận cuối

Kiến trúc cốt lõi của ChromeDrift có tính hợp lý: tách acquisition, extraction, normalization, semantic diff, evidence-aware ranking và human judgement; giữ engine deterministic; dùng Fact làm ranh giới chung cho nhiều grammar; công bố source location và coverage.

Điều phải bảo vệ khi trình bày là ranh giới của lời hứa:

> ChromeDrift không chứng minh uprev an toàn. Nó biến một bài toán source diff quá lớn thành một danh sách bằng chứng có thứ tự, để team biết phải đọc gì, hỏi owner nào và test ở đâu.

Nếu Tech Leader chấp nhận đúng lời hứa này, cộng quy trình hai vòng Settings-complete/full-wide và bước kiểm tra fork bắt buộc, giải pháp đáng để pilot và tiếp tục đầu tư. Nếu tổ chức muốn dùng output làm release gate tự động, implementation hiện tại chưa đủ và cần thêm downstream usage, build-aware evidence, grammar coverage và phép đo chất lượng trên dữ liệu uprev thực tế.
