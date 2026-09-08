# Lưu kết quả phân tích và giữ nguyên input

MUST đọc tài liệu này trước khi khởi tạo, tiếp tục, ghi quyết định hoặc refresh
review. Xác nhận phạm vi với user trước theo [scoping.md](scoping.md). Có report
hoặc cache không có nghĩa đã biết user muốn phân tích phần nào.

## Đọc cấu hình đã lưu

Chạy đoạn dưới đây từ thư mục gốc của repo, chỉ thay đường dẫn thư mục review.
Nó in ra các trường cần thiết mà không đưa toàn bộ index vào context.

```bash
python3 - out/upgrade/review <<'PY'
import json
import sys
from pathlib import Path

index = json.loads((Path(sys.argv[1]) / "review-index.json").read_text(encoding="utf-8"))
keys = ("report", "refs", "cache", "source_roots", "source_scope",
        "platform", "target_set", "partitions", "coverage")
print(json.dumps({key: index["inputs"].get(key) for key in keys}, indent=2))
print(json.dumps({"warnings": index["warnings"]}, indent=2))
PY
```

`source_scope.mode` cho biết đang dùng file trong cache hay dùng repo Git.
`source_roots` là các cây source đã cache. Ở chế độ Git, đọc commit đã ghi lại
trong repo; **không** giả định checkout hiện tại khớp với ref nào trong hai ref.
Giữ lại đường dẫn cache vừa in ra để dùng cho `why.py` và `cl.py`.

## Làm theo từng đợt nhỏ

MUST giữ phạm vi đã xác nhận trong `request.md`. Chạy `review overview` trước
truy vấn chi tiết; không nạp hàng nghìn dòng không liên quan vào context.
Giữ trong context các câu hỏi hiện tại và một danh sách event ngắn. Chỉ đọc
những trường của finding, những khai báo liên quan và những đoạn source cần cho
các câu hỏi đó. Sau mỗi đợt, lưu quyết định đầy đủ vào `review.json`.

Mỗi item đã index cần một quyết định:

- `event` — item thuộc về một event. Event khác vẫn có thể trích nó làm bằng
  chứng phụ mà không gán nó hai lần.
- `explained` — đã xem, nhưng không cần một event riêng. Nêu lý do và vị trí
  trong source; một nhãn kiểu "cleanup" không phải một lời giải thích.
- `out_of_scope` — bị loại theo phạm vi user đưa, kèm lý do cụ thể.
- `unresolved` — còn một câu hỏi cần bằng chứng. Nêu bước kiểm tiếp theo.

Item chưa có quyết định là `pending`. Các trạng thái này theo dõi tiến độ phân
tích; chúng không phải phân loại cho báo cáo cuối.

Một item `file:` đại diện cho **toàn bộ** bản diff của file. Với file nằm trong
phạm vi đã xác nhận, đọc các hunk thay đổi của nó và ghi event nào giải thích
hunk nào. Với file dùng chung nằm ngoài phạm vi, chỉ đọc những hunk mà finding
và reference của nó trỏ tới, rồi ghi file đó là `out_of_scope` kèm tên các hunk
chưa đọc. Một file khai báo trung tâm có thể mang hàng trăm hunk thuộc các khu
vực sản phẩm khác; đọc chúng không thuộc phạm vi review theo scope. Không ghi
là đã giải thích một file khi còn hunk chưa đọc. Cùng một file có thể phục vụ
nhiều event; gán file cho một event không giải thích các thay đổi còn lại.

Bản tóm tắt milestone là một nguồn độc lập, phải đối chiếu với đúng hai version
đang so. Riêng nó không chứng minh một capability đã có ở đó.

### Lặp lại cho đến khi xử lý hết phần việc còn lại

Mỗi phiên bắt đầu từ yêu cầu và review đã lưu, không chọn lại nhóm điểm cao.
Danh sách không lọc dưới đây phủ toàn bộ index. Với review tập trung, dùng
overview và cách truy vấn trong `scoping.md` trước; hết kết quả trong bộ lọc
không có nghĩa toàn bộ index đã được xử lý:

```bash
python3 -m chromiumdiff review check out/upgrade/review
python3 -m chromiumdiff review index out/upgrade/review --status pending --limit 30
```

Khi chưa xong, `check` chủ động trả mã 1; đọc JSON của nó và tiếp tục.
`total` và `counts` tính trên toàn bộ index, không phải trang đang đọc.
`by_kind` tách finding, source delta và bản tóm tắt milestone, giúp nhận ra
phần source chưa được xem dù nhiều finding đã có quyết định.

Với mỗi item thuộc phạm vi đã xác nhận, đọc bằng chứng rồi ghi event hoặc quyết định cụ thể
không tạo event. Thiếu bằng chứng thì ghi `unresolved` cùng bước kiểm tiếp
theo. Không dùng vòng lặp shell để gán cùng một lời giải thích cho các item
chưa xem. Lưu xong một đợt thì chạy lại lệnh lấy `pending` từ cursor 0, không
truyền `--query` hay `--after`. Các item đã có quyết định không xuất hiện nữa;
lệnh trả những item tiếp theo. Lặp khi còn pending. Nếu số pending không giảm,
kiểm tra kết quả ghi quyết định thay vì chọn một mẫu khác.

Với các đợt tập trung, giữ bộ lọc đường dẫn/kind đã chọn khi đọc tiếp cùng
truy vấn. Đọc riêng source hỗ trợ và các thành phần phụ thuộc ngoài bộ lọc.
Review tập trung trên index rộng hơn có thể vẫn là `PARTIAL` khi kiểm toàn bộ
index: báo riêng phạm vi đã đánh giá và phần chưa xem, không tạo hàng nghìn
quyết định loại trừ không có căn cứ.

Sau đó đọc hết các trang của `index --status unresolved` và các event còn
`provisional`. Thực hiện bước kiểm tiếp theo khi có thể rồi cập nhật quyết
định. `review unresolved` là lệnh khác: nó liệt kê tham chiếu graph chưa giải
được. Kiểm tra lại pending sau khi sửa event hoặc refresh, vì các thao tác này
có thể đưa item về pending. Đối chiếu bằng chứng giữa các đợt; ranh giới giữa
hai đợt làm việc không phải ranh giới giữa hai event.

Khi context gần đầy, lưu quyết định hiện tại, vị trí source, câu hỏi và bước
kiểm tiếp theo trước khi chuyển sang context mới nếu môi trường chạy hỗ trợ.
Tiếp tục cùng thư mục review. Giới hạn context không phải giới hạn số event;
môi trường chạy vẫn có thể đặt giới hạn riêng cho tổng công việc. Nếu chạm
giới hạn đó, báo số mục chưa xong và lý do. Không tự nhận đã hoàn thành hoặc
âm thầm thu hẹp phạm vi.

## Định nghĩa và sửa lại event

Một event phải trả lời đúng một câu hỏi: **thay đổi liên quan nào đã xảy ra?**
Giải thích vì sao các item của nó thuộc về nhau và khác gì với công việc lân
cận. Tham chiếu trong source, consumer, key đã lưu dùng chung và lịch sử commit
có thể xác lập quan hệ. Chỉ trùng tên, trùng flag, trùng file hay trùng CL thì
không.

Đọc lại các event đã lưu khi phân tích đợt tiếp theo. Gộp các mảnh liên quan
hoặc tách các thay đổi không liên quan khi bằng chứng đòi hỏi. Graph không phải
call graph đầy đủ, nên phải tự đọc những quan hệ trong source mà graph thiếu.

## Ghi quyết định

Tạo một file JSON theo cấu trúc dưới đây bằng cơ chế sửa file của môi trường
đang chạy. Thay các giá trị ví dụ bằng ID thật và quan sát thật.

```json
{
  "events": [{
    "title": "Mô tả thay đổi liên quan",
    "status": "provisional",
    "items": ["kind:actual-key"],
    "before": "Trạng thái quan sát được ở version cũ",
    "after": "Trạng thái quan sát được ở version mới",
    "mechanism": "Code đã đổi ra sao, và vì sao các item này thuộc về nhau",
    "impact": "Consumer bị ảnh hưởng; nêu rõ phần chưa chắc phụ thuộc sản phẩm",
    "conditions": "Điều kiện build, runtime và triển khai liên quan",
    "action": "Việc kiểm tra hoặc cập nhật cụ thể, kèm vị trí consumer",
    "uncertainties": ["Câu hỏi vẫn còn cần bằng chứng"],
    "evidence": [{
      "item": "kind:actual-key",
      "supports": "Quan sát mà item này chống đỡ"
    }]
  }],
  "dispositions": [{
    "id": "file:path/from/index.cc",
    "status": "unresolved",
    "reason": "Đoạn source chưa giải thích được, bằng chứng còn thiếu, bước kiểm tiếp theo"
  }]
}
```

```bash
python3 -m chromiumdiff review record out/upgrade/review --file /path/to/decisions.json
python3 -m chromiumdiff review check out/upgrade/review
```

`record` kiểm tra phần thay đổi được đề xuất trước khi ghi. Mọi thành viên của
một event đều cần một câu giải thích bằng chứng. ID lạ, gán trùng thành viên
chính, và quyết định trỏ tới event không tồn tại đều bị từ chối. Nó kiểm
**cấu trúc và tham chiếu**, không kiểm kết luận có đúng hay không.

`confirmed` nghĩa là kết luận được chống đỡ **trong phạm vi đã nêu**.
`provisional` nghĩa là còn một câu hỏi chưa giải quyết có thể làm đổi kết luận.
Không biết trạng thái triển khai vẫn có thể là một giới hạn đã nêu của một thay
đổi `confirmed` ở mức source; nó không cho phép khẳng định tính năng đã sẵn dùng
trong sản phẩm.

ID của event mặc định là hash của danh sách item đã sắp xếp, không phụ thuộc câu
chữ hay score. Sửa một event thì đưa lại `id` của nó. Tách hoặc gộp event thì
đưa `remove_events: ["event:old-id"]` cùng các event thay thế trong **một**
patch. Item bị gỡ khỏi event sẽ quay về `pending` nếu không được gán lại.
Trường `order` (số không âm, tuỳ chọn) chỉ điều khiển thứ tự trình bày, không
ảnh hưởng phạm vi điều tra.

Một mục bằng chứng có thể dùng `item` cho một finding hoặc một node không đổi,
`url` cho một trang source/CL/bug qua HTTPS, hoặc `source` cho bằng chứng cục bộ
có kiểm hash:

```json
{
  "source": {
    "side": "to",
    "path": "path/to/consumer.cc",
    "sha256": "COPY_FULL_SHA256_FROM_SOURCE_RESULT",
    "start": 100,
    "end": 120
  },
  "supports": "Những dòng source này xác lập điều gì"
}
```

Dùng **số dòng của source**, không dùng số dòng trong output diff. Đọc một URL
trước khi trích nội dung của nó. Khâu kiểm tra không tải URL và không xác minh
rằng nguồn đó chống đỡ được khẳng định đang nêu. Một issue không truy cập được
vẫn là bằng chứng còn thiếu.

## Refresh sau khi lưu bằng chứng mới

`why.py --save` ghi thay đổi vào `report.json`. Phải refresh review trước khi
làm tiếp, dùng đúng cấu hình đã lưu của nó. CLI **không** tự giữ lại `--cache`
hay `--source-repo` trước đó khi chúng bị bỏ trống ở `review init --refresh`.

Chạy đoạn dưới đây từ thư mục gốc của repo sau khi lưu kết quả tra cứu. Nó giữ
đúng cấu hình cho cả review chỉ dùng cache lẫn review có repo Git, không phải
đoán đường dẫn:

```bash
python3 - out/upgrade/review <<'PY'
import json
import subprocess
import sys
from pathlib import Path

directory = Path(sys.argv[1]).resolve()
index = json.loads((directory / "review-index.json").read_text(encoding="utf-8"))
inputs = index["inputs"]
command = [sys.executable, "-m", "chromiumdiff", "review", "init",
           inputs["report"], "--directory", str(directory),
           "--cache", inputs["cache"], "--refresh"]
scope = inputs["source_scope"]
if scope["mode"] == "git":
    command.extend(["--source-repo", scope["repository"]])
subprocess.run(command, check=True)
PY
```

Đọc phần warning của kết quả:

- Bằng chứng giống hệt thì quyết định cũ được giữ nguyên. Riêng thứ hạng hay
  thứ tự input đổi thì không làm mất hiệu lực quyết định.
- Thay đổi chỉ ở phần ngữ cảnh sẽ lưu trữ bản quyết định cũ, đánh dấu các event
  liên quan thành `provisional` và các quyết định không phải event thành
  `unresolved`. Quyết định không liên quan được giữ; item mới là `pending`.
  Phép kiểm phụ thuộc này có thể mở lại nhiều event nằm dưới một điều kiện
  chung, **nhưng điều đó không có nghĩa các event đó nên gộp làm một**.
- Thay đổi ở source, snapshot hay phạm vi sẽ lưu trữ và reset các quyết định.
  Nếu thay đổi đó ngoài ý muốn, kiểm tra lại cấu hình trước khi phân tích tiếp.
- File tải thêm bằng `review source --fetch` nằm ở một cache riêng và **không**
  mở rộng phạm vi quét gốc.

## Kiểm tra mức hoàn thành

`review check` trả mã 1 khi còn item `pending`/`unresolved`, còn event
`provisional`, bản ghi không hợp lệ, hoặc input đã đổi. Mã 0 chỉ nghĩa là mọi
item đã index đều có quyết định hợp lệ. **Nó không chứng minh phân tích đã đầy
đủ về mặt ngữ nghĩa và không chứng minh sản phẩm an toàn.** Báo cáo render ra
sẽ đánh dấu phân tích chưa xong là `PARTIAL`.

Khi xuất bản cuối một review toàn bộ index, dùng:

```bash
python3 -m chromiumdiff review render out/upgrade/review --require-complete
```

Nếu còn item hoặc event chưa xong, lệnh trả mã 1 và không ghi hay thay thế
`review.md`. Một review theo phạm vi hẹp không bao giờ tới trạng thái đó, vì
các item ngoài phạm vi vẫn ở pending; render nó không kèm tuỳ chọn này và giữ
nguyên trạng thái PARTIAL. Lệnh `render` thông thường vẫn dùng được để xuất báo
cáo một phần có ghi rõ trạng thái; mã 0 của nó chỉ nghĩa là đã ghi file. Cả hai
lệnh đều không xác minh ý nghĩa các lời giải thích của agent.

Trước khi giao, xem lại ranh giới các event, phần source chống đỡ chúng, các
điều kiện và các hunk còn lại của từng file. Bản tóm tắt có thể chọn các event
chính, nhưng báo cáo đầy đủ được liên kết phải giữ mọi event có bằng chứng.
Một review theo phạm vi hẹp được giao khi phạm vi đã xác nhận của nó được kế
toán xong: báo phạm vi đó, tổng số item, số quyết định theo trạng thái và loại
item, số event provisional, và các item nằm ngoài phạm vi. Nếu giới hạn tài
nguyên, bằng chứng thiếu hoặc yêu cầu dừng của user khiến công việc trong phạm
vi chưa xong, báo là cái nào và các bước kiểm tiếp theo. Nếu không bị cản trở
thì tiếp tục từ trạng thái đã lưu; tìm đủ một số lượng event thuận tiện không
phải điều kiện dừng. Thiếu thời gian, điểm thấp hay khó phân tích không
khiến một item nằm ngoài phạm vi hoặc giải thích được tác động của nó.
