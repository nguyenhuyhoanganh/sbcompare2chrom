# Giữ nguyên input của review

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
