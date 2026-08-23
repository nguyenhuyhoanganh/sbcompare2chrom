# 2. ChromeDrift lấy source tree, thư mục và file như thế nào

Tài liệu này trả lời một câu hỏi duy nhất: **công cụ lấy mã nguồn Chromium từ đâu, lấy bao nhiêu, và làm sao biết là đã lấy đúng.** Nếu không tin bước này, mọi kết luận phía sau đều không đáng tin.

## Trả lời ngắn

ChromeDrift làm việc với hai trạng thái source hoàn toàn độc lập: một bên là version cũ, một bên là version mới. Với mỗi bên, công cụ lần lượt làm ba việc:

1. xác định một Git ref cụ thể (một điểm cố định trong lịch sử Chromium);
2. hỏi cây file của **chính ref đó** để đo xem phạm vi đọc được là bao nhiêu;
3. dựng một cây source cục bộ trên máy, chỉ chứa những file thật sự cần đọc.

Có hai nguồn để lấy mã nguồn:

- **Gitiles** — tải trực tiếp từng file, hoặc tải cả một thư mục con, tại đúng tag cần đọc;
- **local checkout** — sao chép đúng những file cần thiết từ một thư mục Chromium `src/` đã có sẵn trên máy.

Cây source mà ChromeDrift dựng ra là một cây **không đầy đủ** (partial tree), nhưng đường dẫn tương đối của mỗi file vẫn giữ nguyên như trên upstream. Ví dụ file `chrome/browser/resources/settings/route.ts` của Chromium vẫn nằm đúng ở đường dẫn đó trong cache; nó không bị gom vào một thư mục phẳng kiểu "routes". Phần "Bước 6" giải thích vì sao chi tiết này lại quan trọng đến vậy.

## Toàn bộ luồng, nhìn từ trên xuống

```text
from_ref / to_ref  (hai version cần so)
       │
       ▼
resolve_ref()   — quy mọi kiểu đầu vào về một ref cụ thể
   milestone     → tìm bản Windows Stable mới nhất → refs/tags/x.y.z.w
   full version  → refs/tags/x.y.z.w
   ref/SHA thô   → giữ nguyên
       │
       ▼
chọn target set / partition / complete   — quyết định "sẽ đọc vùng nào"
       │
       ├── list_recursive()  — nhìn cây file của đúng ref, để đo coverage
       │
       └── materialize()     — tải hoặc copy các target vào cache
                    │
                    ▼
        cache/trees/<safe-ref>/
          chrome/...
          components/...
          content/...
          third_party/blink/...
                    │
                    ▼
        extractor duyệt cây này, nhưng vẫn bị giới hạn trong phạm vi target set
                    │
                    ▼
        Snapshot(ref, facts, coverage, fetch_stats, missing_targets)
```

Chín mục dưới đây đi qua từng bước trong sơ đồ trên.

## Bước 1 — Version đến từ đâu

Người chạy có thể nhập ba kiểu đầu vào khác nhau, và công cụ xử lý mỗi kiểu một cách.

### Nhập full version — cách nên dùng

Với đầu vào như `151.0.7922.138`, công cụ tạo ra:

```json
{
  "input": "151.0.7922.138",
  "resolved_ref": "refs/tags/151.0.7922.138",
  "milestone": 151
}
```

Đây là cách nên dùng cho mọi báo cáo chính thức, vì hai người chạy lại ở hai thời điểm khác nhau vẫn đọc đúng cùng một trạng thái mã nguồn.

### Nhập milestone — tiện nhưng có tính thời điểm

Với đầu vào chỉ là `151`, công cụ gọi ChromiumDash, hỏi channel Stable trên platform Windows, lấy full version stable cao nhất thuộc M151, rồi mới chuyển thành tag.

Cách này tiện khi cần chạy nhanh, nhưng kết quả phụ thuộc **thời điểm chạy**: nếu milestone đó còn tiếp tục nhận bản vá, lần chạy sau có thể resolve sang một full version mới hơn và cho kết quả khác. Vì vậy báo cáo phải luôn hiển thị `resolved_ref`, để người đọc biết source thực tế là bản nào.

### Nhập ref hoặc SHA thô

Nếu đầu vào không phải milestone và cũng không có dạng version bốn phần, công cụ giữ nguyên không xử lý gì. Cách này hữu ích khi cần so hai branch hoặc hai SHA nội bộ, nhưng người chạy phải tự bảo đảm ref đó thật sự tồn tại trên source server.

## Bước 2 — Target set quyết định "sẽ lấy vùng nào"

Một `FetchTarget` (một mục trong danh sách cần tải) về mặt khái niệm có dạng như sau. Đây là target kiểu thư mục:

```json
{
  "path": "chrome/browser/resources/settings",
  "kind": "tree",
  "include": [".html", ".html.ts", "route.ts", "routes.ts"],
  "note": "chrome://settings UI"
}
```

Và đây là target kiểu file đơn:

```json
{
  "path": "chrome/browser/flag-metadata.json",
  "kind": "file",
  "include": null,
  "note": "flag expiry milestones"
}
```

Khác biệt giữa hai kiểu: `kind=file` tải đúng một đường dẫn. `kind=tree` tải archive của cả thư mục, nhưng khi giải nén chỉ ghi ra đĩa những file có tên khớp một trong các đuôi liệt kê ở `include`.

Ba target set phục vụ ba mục đích khác nhau:

| Target set | Dùng khi | Điều cần nhớ |
|---|---|---|
| `minimal` | Smoke test — kiểm tra công cụ và cache còn chạy đúng không | Không bao giờ đủ để kết luận cho một release |
| `default` | Báo cáo hằng ngày, giữ chi phí ở khoảng 40 MB mỗi version theo thiết kế hiện tại | Được chọn lọc theo các surface có giá trị cao; bắt buộc phải đọc báo cáo coverage kèm theo kết quả |
| `wide` | Phân tích ở mức release, hoặc cần xác minh một khai báo có thật sự bị xoá không | Đọc mọi dạng tên file mà công cụ hiểu, trong các thư mục gốc đã chọn; lớn hơn nhiều nhưng giảm hẳn số kết luận "đã bị xoá" sai |

Ngoài target set, `partition` còn lọc tiếp danh sách target theo khu vực chức năng. Ví dụ `--partition settings` chỉ giữ lại các file lõi cùng những target có tiền tố liên quan tới Settings.

Nhưng partition không thay thế được một lần chạy đầy đủ ở cuối, vì code ảnh hưởng tới Settings hoàn toàn có thể nằm ở `content/`, ở một file Mojo, hoặc ở Blink — tức là ngoài partition đang chọn.

## Bước 3 — Discovery lấy "cây file" như thế nào

Với Gitiles, công cụ gọi lệnh liệt kê đệ quy cho từng thư mục gốc cần khảo sát, chẳng hạn:

- `chrome/`
- `components/`
- `content/`
- `services/`
- `third_party/blink/`
- `base/`, `device/`, `cc/`, `sandbox/`, `storage/`...

Kết quả trả về là danh sách đường dẫn của mọi file nằm dưới thư mục gốc đó, tại đúng ref đang xét. Danh sách này được cache lại theo cặp (ref, thư mục gốc).

Sau đó công cụ hỏi registry của 9 extractor một câu cho từng đường dẫn: *có extractor nào trả lời `applies_to(path) == true` không?* Nếu có, và file đó vẫn nằm trong phạm vi sản phẩm browser, thì file được đánh dấu là **candidate**.

### Điểm dễ nhầm nhất trong cả bước này

**Discovery không đồng nghĩa với tải về.** Ba con số dưới đây là ba thứ khác nhau:

```text
discovery candidates = những file CÓ THỂ chứa loại khai báo mà công cụ hiểu
target reach         = những candidate mà target set THỰC SỰ chạm tới
coverage             = target reach / discovery candidates
```

Tách bạch hai khái niệm này có một lợi ích rất cụ thể: nó giúp phát hiện danh sách target đã cũ. Giả sử Chromium thêm một file `*_prefs.cc` mới nằm ngoài danh sách target mặc định. Khi đó số candidate tăng lên và coverage giảm xuống — thay vì file đó lặng lẽ biến mất khỏi cả tử số lẫn mẫu số và không ai biết là mình đang bỏ sót.

## Bước 4 — Gitiles tải file và thư mục ra sao

### Tải một file đơn

Công cụ gọi endpoint `?format=TEXT` tại đúng ref. Gitiles trả về nội dung đã mã hoá base64; công cụ giải mã rồi ghi vào đúng đường dẫn tương đối trong cache.

Kết quả rơi vào một trong ba trạng thái, và cả ba đều được ghi lại:

| Trạng thái | Nghĩa |
|---|---|
| `file <size>B` | Tải được, kèm kích thước |
| `missing` | Ref này thực sự không có file đó |
| `cached` | Đã có sẵn bản cache hợp lệ, không cần tải lại |

HTTP 404 được ghi là `missing` và **không** làm cả lần chạy thất bại ngay, vì một file hoàn toàn có thể chưa tồn tại ở milestone cũ. Nhưng nếu **mọi** target đều missing, công cụ dừng lại — vì tình huống đó gần như chắc chắn là ref sai hoặc proxy sai, chứ không phải Chromium bỗng dưng rỗng.

### Tải một thư mục

Công cụ tải archive `.tar.gz` của cả nhánh con. Trong lúc giải nén, mỗi file phải qua bộ lọc `include`. Chỉ file thường được giữ lại, và mọi đường dẫn đều bị kiểm tra để archive không thể ghi ra ngoài thư mục đích.

Một ví dụ cho thấy bộ lọc mạnh tới mức nào: archive của `chrome/browser/resources/settings/` chứa rất nhiều file `.ts`, ảnh, CSS và file test. Với target dành cho template WebUI, cây cục bộ chỉ giữ lại:

```text
*.html
*.html.ts
route.ts
routes.ts
```

Cần đọc điều này cho đúng. Nó **không** có nghĩa là các file còn lại vô dụng với browser. Nó chỉ có nghĩa là extractor hiện tại không đọc phần implementation viết bằng TypeScript, không đọc CSS và không đọc ảnh — nên tải chúng về cũng không làm snapshot có thêm được `Fact` nào, chỉ tốn dung lượng.

### Chạy song song và thử lại

Năm quy tắc bảo vệ ở bước tải:

- Archive thư mục có kích thước lớn nên được xử lý lần lượt, không song song.
- File đơn được tải song song, tối đa 8 luồng.
- Mọi request HTTP đều có timeout, có thử lại, và khoảng chờ giữa các lần thử tăng dần.
- Response rỗng luôn được thử lại, để phân biệt một file thật sự rỗng với một response bị cắt giữa chừng.
- Nếu một file gặp lỗi tải không xác định được nguyên nhân, cả bước lấy source thất bại, thay vì lặng lẽ ghi file đó là `missing`. Nếu làm ngược lại, báo cáo sẽ tự bịa ra một khai báo "đã bị xoá" trong khi thực tế chỉ là mạng lỗi.

## Bước 5 — Dùng source có sẵn trên máy thì khác gì

Khi truyền `--local-src`, công cụ **không** đọc tuỳ ý toàn bộ checkout. Nó vẫn dùng đúng target set như khi tải qua mạng:

- với target kiểu file: copy đúng file đó;
- với target kiểu tree: duyệt nhánh con và copy những file khớp bộ lọc `include`;
- vẫn giữ nguyên đường dẫn tương đối;
- bỏ qua `.git`, `out` và `__pycache__`.

Nói cách khác: nguồn từ xa và nguồn cục bộ khác nhau ở chỗ **byte đến từ đâu**, chứ không khác nhau ở **phạm vi được đọc**.

### Bốn thứ phải kiểm tra trước khi tin một lần chạy local

1. Đường dẫn phải là thư mục `src/` của Chromium, tức là bên trong có `chrome/`, `content/`, `components/`, `third_party/`.
2. Checkout phải đang ở đúng ref được ghi nhãn trong lần chạy đó.
3. Không được dùng sparse checkout hoặc checkout đã bị cắt bớt rồi coi như source đầy đủ.
4. Nếu mục tiêu là so hai bản release gốc, không được để generated file hoặc bản vá cục bộ vô tình đại diện cho upstream.

Có một lớp bảo vệ tự động cho tình huống tệ nhất: bước so sánh sẽ từ chối chạy nếu một bên có ít hơn 50% số `Fact` so với bên kia, trong khi tổng số `Fact` vẫn đủ lớn để đây là một lần chạy thật. Trường hợp này gần như luôn là lỗi chuẩn bị source, không phải Chromium thay đổi.

## Bước 6 — Vì sao cây thư mục không đầy đủ vẫn cho kết quả đúng

Extractor xác định dialect của một file bằng **đường dẫn tương đối và tên file**, chứ không phải bằng nội dung. Bốn ví dụ:

- một file `.idl` chỉ được coi là Blink Web IDL nếu đường dẫn bắt đầu bằng `third_party/blink/renderer/`;
- `route.ts` chỉ được đọc nếu nằm dưới `chrome/browser/resources/`;
- một file `.cc` chỉ trở thành nguồn WebUI gate nếu nằm dưới `chrome/browser/ui/webui/`;
- `pref_names.cc` và `switches.cc` dựa vào tên file để quyết định tạo `Fact` loại `pref` hay loại `switch`.

Hệ quả: nếu gom hết file về một thư mục phẳng, toàn bộ các rule trên mất ngữ cảnh và công cụ sẽ parse nhầm dialect. Giữ nguyên cấu trúc thư mục vì thế là một phần của **tính đúng đắn**, không phải để báo cáo nhìn cho đẹp.

## Bước 7 — Phạm vi trích xuất bị khoá lại theo target set

Cache dùng chung một cây thư mục cho mỗi ref. Điều đó tạo ra một rủi ro: một lần chạy `wide` để lại rất nhiều file trong cache; nếu sau đó chạy `minimal` trên cùng ref, extractor có thể vô tình đọc phải những file còn sót và tạo ra một snapshot mang nhãn `minimal` nhưng chứa dữ liệu của `wide`.

Để chặn tình huống này, trước khi duyệt cây, bộ dựng snapshot truyền vào hai tập hợp giới hạn:

```json
{
  "allow_paths": ["các target file chính xác"],
  "allow_prefixes": {
    "mỗi/tree/prefix/": ["suffix", "filter"]
  }
}
```

Extractor chỉ được phép đọc những file mà phạm vi hiện tại chạm tới. Nhờ đó nhãn của snapshot luôn đúng với dữ liệu bên trong nó.

## Bước 8 — Những file bị loại vì không thuộc sản phẩm

Sau khi qua phạm vi target, file còn phải qua một lớp lọc nữa, gọi là product scope. Các nhóm bị loại:

- file test, browser test, fuzzer, mock và web test;
- output do máy sinh ra, và thư mục `.git`;
- các binary không phải sản phẩm browser: `content_shell`, headless shell, updater, remote desktop, các Windows service độc lập;
- thư viện third-party được vendor sẵn, trừ phần Blink;
- với đa số extractor, cả source chỉ dành riêng cho ChromeOS/Ash/iOS/Fuchsia.

### Một ngoại lệ có chủ ý

Extractor `constants` vẫn đọc các chuỗi pref và switch nằm trong cây source của platform khác. Lý do rất cụ thể: nếu một pref key được chuyển từ file dùng chung sang một file riêng của ChromeOS, việc đó phải được nhận ra là **move** (chuyển chỗ), chứ không được hiểu nhầm thành **deleted** (đã xoá).

Ngoại lệ này không làm nhiễu kết quả, vì sau đó trạng thái theo platform và bước chấm điểm vẫn ngăn những thay đổi không thuộc Windows tranh thứ tự ưu tiên với các finding thật.

## Bước 9 — Đọc gì để biết bước lấy source có đáng tin không

Phần metadata của snapshot nên được đọc **trước** khi đọc bất kỳ finding nào. Cấu trúc của nó như sau — các con số ở đây chỉ để minh hoạ hình dạng, không phải số liệu của một release cụ thể:

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

Khi review một báo cáo thật, đây là sáu câu cần tự hỏi:

1. `ref` của cả hai bên có đúng là hai full version cần uprev không?
2. `target_set`, `partitions` và `complete` của hai bên có giống nhau không?
3. `missing_targets` có mục nào bất thường không?
4. `_errors` trong phần trích xuất có bằng 0 không?
5. Với surface đang được dùng để kết luận "đã bị xoá", coverage có đạt ngưỡng xác nhận 95% không?
6. Tổng số `Fact` của hai bên có cùng bậc độ lớn không?

## Vì sao không dùng thẳng một Git diff của cả checkout

Một Git diff trên toàn bộ cây trả lời câu hỏi *"dòng text nào đã đổi"*. Nhưng câu hỏi ChromeDrift cần trả lời là *"contract nào trong các khai báo đã đổi"*. Đó là hai câu hỏi khác nhau.

Việc chỉ tải vừa đủ các file chứa khai báo mang lại ba lợi ích cụ thể:

- chạy được **trước khi** Samsung bắt đầu merge, không cần chờ có cây code đã merge;
- snapshot và cache nhỏ, nên có thể sửa logic so sánh hoặc chấm điểm rồi chạy lại rất nhanh mà không tải lại source;
- parser tập trung vào nguồn sự thật của từng contract, thay vì bị chôn vùi trong hàng nghìn dòng refactor.

Đổi lại, công cụ không phát hiện được mọi thay đổi ở phần implementation. Vì vậy cách mô tả đúng về phạm vi là: *"phủ các surface khai báo đã liệt kê, và đo rõ phần chưa phủ"* — chứ không phải *"phủ toàn bộ thay đổi của Chromium"*.
