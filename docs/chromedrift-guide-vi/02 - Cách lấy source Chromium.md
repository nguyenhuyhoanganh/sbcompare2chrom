# 2. ChromeDrift lấy source tree, thư mục và file như thế nào

## Câu trả lời ngắn

ChromeDrift làm việc với hai trạng thái source độc lập: version cũ và version mới. Với mỗi bên, tool xác định một Git ref cụ thể, hỏi cây file của chính ref đó để đo phạm vi, rồi materialize một cây source cục bộ chỉ chứa các target cần đọc.

Có hai nguồn:

- Gitiles: tải trực tiếp file hoặc archive của subtree tại đúng tag;
- local checkout: copy đúng các target từ một Chromium `src/` đã có sẵn.

Cây local mà ChromeDrift tạo là partial tree nhưng relative path vẫn giống upstream. Ví dụ file upstream `chrome/browser/resources/settings/route.ts` vẫn nằm đúng path đó dưới cache; nó không bị gom vào một thư mục “routes”.

## Luồng dữ liệu

```text
from_ref / to_ref
       │
       ▼
resolve_ref()
milestone → Windows Stable full version → refs/tags/x.y.z.w
full version → refs/tags/x.y.z.w
raw ref/SHA → giữ nguyên
       │
       ▼
chọn target set / partition / complete
       │
       ├── list_recursive(): nhìn cây của đúng ref để đo coverage
       │
       └── materialize(): tải/copy các target vào cache tree
                    │
                    ▼
cache/trees/<safe-ref>/
  chrome/...
  components/...
  content/...
  third_party/blink/...
                    │
                    ▼
extractor walk cây này nhưng vẫn bị giới hạn bởi scope của target set
                    │
                    ▼
Snapshot(ref, facts, coverage, fetch_stats, missing_targets)
```

## Bước 1: version được lấy từ đâu

### Nhập full version

Với đầu vào như `151.0.7922.138`, tool tạo:

```json
{
  "input": "151.0.7922.138",
  "resolved_ref": "refs/tags/151.0.7922.138",
  "milestone": 151
}
```

Đây là cách nên dùng cho report chính thức vì hai người chạy lại sẽ đọc đúng cùng một source state.

### Nhập milestone

Với đầu vào `151`, tool gọi ChromiumDash, hỏi channel Stable và platform Windows, lấy full version stable cao nhất thuộc M151, sau đó chuyển thành tag.

Milestone tiện cho chạy nhanh nhưng có tính thời điểm: nếu milestone còn nhận patch release, lần chạy sau có thể resolve sang full version mới hơn. Report nên luôn hiển thị `resolved_ref` để người đọc biết source thực tế là bản nào.

### Nhập raw ref hoặc SHA

Nếu input không phải milestone và không có dạng version bốn phần, tool giữ nguyên. Trường hợp này hữu ích khi so branch/SHA nội bộ nhưng người chạy phải tự đảm bảo ref có trên source server.

## Bước 2: target set quyết định “sẽ lấy vùng nào”

Một `FetchTarget` có dạng khái niệm:

```json
{
  "path": "chrome/browser/resources/settings",
  "kind": "tree",
  "include": [".html", ".html.ts", "route.ts", "routes.ts"],
  "note": "chrome://settings UI"
}
```

Hoặc file đơn:

```json
{
  "path": "chrome/browser/flag-metadata.json",
  "kind": "file",
  "include": null,
  "note": "flag expiry milestones"
}
```

`kind=file` tải đúng path. `kind=tree` tải archive của cả thư mục nhưng chỉ materialize các member có basename khớp suffix trong `include`.

Ba target set có mục đích khác nhau:

| Target set | Dùng khi | Điều cần nhớ |
|---|---|---|
| `minimal` | Smoke test, kiểm tra tool và cache | Không đủ làm kết luận release |
| `default` | Báo cáo hằng ngày, giữ chi phí khoảng 40 MB/version theo thiết kế hiện tại | Curated theo các surface giá trị cao; coverage report phải được đọc cùng kết quả |
| `wide` | Release-level analysis hoặc xác minh removal | Đọc mọi filename shape tool hiểu trong các root được chọn; lớn hơn nhiều nhưng giảm false removal |

Partition tiếp tục lọc target list theo area. Ví dụ `--partition settings` giữ core files và target có prefix liên quan Settings. Vì code ảnh hưởng Settings có thể nằm ở `content/`, Mojo hoặc Blink, partition không thay thế full run cuối.

## Bước 3: discovery lấy “cây” như thế nào

Với Gitiles, tool gọi listing recursive cho từng discovery root, chẳng hạn:

- `chrome/`
- `components/`
- `content/`
- `services/`
- `third_party/blink/`
- `base/`, `device/`, `cc/`, `sandbox/`, `storage/`…

Kết quả là danh sách path của mọi blob bên dưới root tại đúng ref. Listing được cache theo ref và root.

Sau đó tool hỏi registry của 9 extractor: với mỗi path, có extractor nào trả lời `applies_to(path) == true` không? Nếu có và file vẫn nằm trong product scope thì file là candidate.

Quan trọng: discovery không đồng nghĩa với fetch.

```text
discovery candidates = những file có thể khai báo dữ liệu tool hiểu
target reach          = những candidate target set thực sự chạm tới
coverage              = target reach / discovery candidates
```

Tách hai khái niệm này giúp phát hiện target list đã cũ. Nếu Chromium thêm một `*_prefs.cc` mới ngoài default targets, candidate count tăng và coverage giảm, thay vì file biến mất khỏi cả tử số lẫn mẫu số.

## Bước 4: Gitiles tải file và thư mục ra sao

### File đơn

Tool gọi endpoint `?format=TEXT` tại ref cụ thể. Gitiles trả nội dung base64; tool decode rồi ghi vào đúng relative path trong cache tree.

Kết quả có ba trạng thái đáng chú ý:

- tải được: `file <size>B`;
- ref thực sự không có file: `missing`;
- đã có cache hợp lệ: `cached`.

HTTP 404 được xem là `missing`, không lập tức làm run fail, vì một file có thể chưa tồn tại ở milestone cũ. Nhưng nếu mọi target đều missing, tool dừng vì ref/proxy có khả năng sai.

### Thư mục

Tool tải archive `.tar.gz` của subtree. Trong lúc giải nén, mỗi file phải qua `include` filter. Chỉ regular file được giữ; path bị kiểm tra để archive không thể ghi ra ngoài destination.

Ví dụ archive `chrome/browser/resources/settings/` có nhiều `.ts`, image, CSS và test file. Với WebUI template target, partial tree chỉ giữ:

```text
*.html
*.html.ts
route.ts
routes.ts
```

Đây không phải kết luận rằng các file khác vô dụng với browser. Nó chỉ nói extractor hiện tại không đọc implementation TypeScript, CSS hay image nên tải chúng không làm snapshot có thêm Fact.

### Song song và retry

- Tree archive lớn được xử lý lần lượt.
- File đơn được tải song song với tối đa 8 worker.
- HTTP có timeout, retry và exponential backoff.
- Body rỗng được retry để phân biệt file thật sự rỗng với response bị cắt.
- Nếu một file gặp lỗi tải không thể xác định, acquisition fail thay vì ghi nó là missing. Nếu không, report có thể bịa ra removal.

## Bước 5: local checkout được dùng ra sao

Khi truyền `--local-src`, tool không đọc tuỳ ý toàn bộ checkout. Nó vẫn dùng cùng target set:

- target file: copy file đó;
- target tree: walk subtree và copy file khớp `include` filter;
- vẫn giữ relative path;
- bỏ `.git`, `out` và `__pycache__`.

Do đó remote và local khác ở nguồn byte, không khác ở semantics của phạm vi.

Điểm cần kiểm tra trước khi tin local run:

1. Path phải là Chromium `src/` chứa `chrome/`, `content/`, `components/`, `third_party/`.
2. Checkout phải đúng ref được gắn nhãn trong lần chạy.
3. Không dùng sparse/truncated checkout mà vẫn coi là full source.
4. Không để generated hoặc local patch vô tình đại diện cho upstream nếu mục tiêu là so hai release gốc.

Diff có guard chống hai snapshot lệch quá lớn: nếu một bên có ít hơn 50% số Fact của bên kia và số Fact đủ lớn để là real run, tool từ chối so sánh.

## Bước 6: vì sao cây partial vẫn chính xác cho parser

Extractor quyết định dialect bằng relative path và basename. Ví dụ:

- `.idl` chỉ được xem là Blink Web IDL nếu path bắt đầu bằng `third_party/blink/renderer/`;
- `route.ts` chỉ được đọc nếu nằm dưới `chrome/browser/resources/`;
- `.cc` chỉ thành WebUI gate source nếu nằm dưới `chrome/browser/ui/webui/`;
- `pref_names.cc` và `switches.cc` dùng basename để chọn `pref` hay `switch`.

Nếu flatten file về một thư mục, những rule này mất context và có thể parse sai dialect. Giữ nguyên tree path là một phần của correctness, không chỉ để report đẹp.

## Bước 7: extraction bị khoá lại theo target scope

Cache tree được dùng chung theo ref. Một lần `wide` có thể để nhiều file hơn trong cache so với `minimal`. Vì vậy, trước khi walk tree, snapshot builder truyền hai tập:

```json
{
  "allow_paths": ["các target file chính xác"],
  "allow_prefixes": {
    "mỗi/tree/prefix/": ["suffix", "filter"]
  }
}
```

Extractor chỉ được đọc file mà scope hiện tại chạm tới. Điều này ngăn lần chạy hẹp vô tình đọc file còn sót từ lần chạy rộng rồi tạo snapshot sai nhãn.

## Bước 8: skip rule loại nhiễu nào

Sau target scope, file còn qua product-scope rule:

- bỏ test, browser test, fuzzer, mock và web tests;
- bỏ generated output và `.git`;
- bỏ binary không phải browser product như `content_shell`, headless shell, updater, remote desktop và Windows services độc lập;
- bỏ vendored third-party ngoài Blink;
- bỏ source chỉ dành cho ChromeOS/Ash/iOS/Fuchsia đối với đa số extractor.

Ngoại lệ là constants extractor vẫn đọc pref/switch strings trong platform tree khác. Lý do: một pref key chuyển từ file chung vào ChromeOS file phải được nhận ra là “move”, không bị hiểu nhầm là “deleted”. Sau đó platform state và scoring vẫn ngăn thay đổi không thuộc Windows tranh thứ tự với finding thật.

## Bước 9: output nào chứng minh acquisition đáng tin

Snapshot metadata nên được đọc trước finding:

```json
{
  "ref": "refs/tags/151.0.7922.138",
  "milestone": 151,
  "meta": {
    "target_set": "default",
    "platform": "Windows",
    "coverage": {
      "candidates": 1200,
      "read": 100,
      "missed": 1100,
      "by_surface": {}
    },
    "fetch_stats": {},
    "missing_targets": [],
    "extract_stats": {}
  }
}
```

Các con số trên chỉ là shape minh hoạ, không phải số của một release cụ thể. Khi review report thật, cần hỏi:

- `ref` hai bên có đúng full version cần uprev không?
- `target_set`, `partitions`, `complete` có giống nhau không?
- `missing_targets` có gì bất thường không?
- `_errors` trong extraction có bằng 0 không?
- coverage của surface đang kết luận removal có đạt ngưỡng xác nhận 95% không?
- tổng Fact hai bên có cùng order of magnitude không?

## Vì sao không dùng một Git diff của toàn checkout

Git diff toàn tree trả lời “dòng text nào đổi”, trong khi ChromeDrift cần “declaration contract nào đổi”. Tải vừa đủ declaration sources mang lại ba lợi ích:

- chạy được trước khi Samsung bắt đầu merge;
- snapshot/cache nhỏ, có thể lặp lại diff và scoring nhanh;
- parser tập trung vào source of truth thay vì bị implementation churn lấn át.

Đổi lại, tool không phát hiện mọi implementation change. Vì vậy kết luận đúng là “phủ các declaration surface đã nêu và đo rõ phần chưa phủ”, không phải “phủ toàn bộ thay đổi Chromium”.
