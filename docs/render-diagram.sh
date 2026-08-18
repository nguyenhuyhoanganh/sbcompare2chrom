#!/usr/bin/env bash
# Dựng lại pipeline-diagram.png từ pipeline-diagram.html.
#
# Ảnh là thứ dán vào Confluence, nhưng nguồn của nó là HTML — sửa chữ, sửa số,
# chạy lại script này. Đừng sửa file .png.
#
# Chiều cao cửa sổ được chọn để vừa khít nội dung: đặt lớn hơn thì ảnh thừa
# một dải trắng ở dưới, đặt nhỏ hơn thì cắt mất băng cuối.
set -euo pipefail
cd "$(dirname "$0")"

CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
[ -x "$CHROME" ] || CHROME="$(command -v google-chrome || command -v chromium || true)"
[ -n "$CHROME" ] || { echo "không tìm thấy Chrome; đặt biến CHROME=..." >&2; exit 1; }

"$CHROME" --headless --disable-gpu --hide-scrollbars \
  --force-device-scale-factor=2 \
  --window-size=1680,890 \
  --screenshot=pipeline-diagram.png \
  pipeline-diagram.html 2>/dev/null

echo "pipeline-diagram.png: $(sips -g pixelWidth -g pixelHeight pipeline-diagram.png 2>/dev/null | tail -2 | tr -d ' \n')"
