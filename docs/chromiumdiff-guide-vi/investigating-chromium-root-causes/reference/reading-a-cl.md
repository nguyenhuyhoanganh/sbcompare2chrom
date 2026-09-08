# Đọc chính bản CL

Bản dịch của `skills/investigating-chromium-root-causes/reference/reading-a-cl.md`.
Khi hai bản lệch nhau thì lấy bản tiếng Anh.

## Mục lục

- Vì sao một verdict chưa phải là điểm dừng
- Thang bằng chứng, và mỗi nấc cho phép nói gì
- Khoảng cách từ vựng: chữ của tác giả không phải identifier
- Đọc commit message
- Đọc bản diff
- Bốn câu hỏi mà chỉ bản diff trả lời được
- Khi bản diff bác bỏ chính CL đó
- Câu lệnh

## Vì sao một verdict chưa phải là điểm dừng

`why.py` cho biết **công cụ đã tìm ra CL bằng cách nào**. `introduced`, `exact`,
`declares` là phát biểu về **một lần tìm kiếm**, không phải về nhân quả. Lần tìm
đó hỏi "diff của CL này trên file này có chạm vào identifier này không"; nó không
bao giờ hỏi "đây có phải thay đổi mà finding đang nói tới không".

Phần lớn trường hợp hai điều đó trùng nhau. Câu trả lời sai đến từ khoảng cách
giữa chúng, và chỉ mở CL ra đọc mới khép được khoảng cách đó.

Hãy làm vậy mỗi khi câu trả lời có trọng lượng: trước khi trích một CL vào
ticket, mỗi khi verdict là `declares` hoặc `described`, mỗi khi tiêu đề đọc lên
có vẻ không liên quan, và mỗi khi một dòng mang nhiều CL và phải chọn một.

## Thang bằng chứng, và mỗi nấc cho phép nói gì

Từ thấp lên cao. Mỗi nấc đều kiểm chứng được; không nấc nào là ý kiến chủ quan.

| Nấc | Bằng chứng | Được phép nói |
|---|---|---|
| 1 | file đã bị chạm vào | "các CL này đã sửa file chứa khai báo" |
| 2 | một verdict gọi tên fact | "một dòng đã đổi có chứa identifier" |
| 3 | commit message giải thích nó | "tác giả nói CL này làm X" |
| 4 | bản diff cho thấy trạng thái trước và sau | "CL này đã tạo ra thay đổi mà finding báo cáo" |
| 5 | issue nêu rõ khiếm khuyết | "việc này được làm vì Y đang hỏng" |

Nấc 1 và 2 đến từ `why.py`. Nấc 3 và 4 cần `cl.py`. Nấc 5 cần chip issue, hoặc
`why.py` trên một báo cáo đang được serve.

**Báo cáo đúng nấc cao nhất thật sự đã tới, và nói rõ đó là nấc nào.** Một dòng
được trả lời ở nấc 2 nhưng viết ra như nấc 4 chính là lỗi mà skill này được viết
ra để ngăn.

## Khoảng cách từ vựng: chữ của tác giả không phải identifier

Đây là lý do phổ biến nhất khiến một CL đúng trông như sai.

Tiêu đề CL của Chromium viết theo dạng `[khu vực] cái gì đã đổi`, và phần khu vực
là **tên mà tác giả gọi mảng sản phẩm đó** — tên nhóm, tên viết tắt — chứ không
phải identifier mà báo cáo giữ. Tìm identifier trong tiêu đề mà không thấy thì
gần như không nói lên điều gì.

Đo trên 84 dòng Mojo và Web IDL của một lần chạy M148 → M151 thật: commit message
đầy đủ của CL có chứa identifier ở 39 dòng. Đọc 45 dòng còn lại, tất cả trừ năm
dòng đều rõ nghĩa ngay khi đọc bằng chính chữ của tác giả:

| Finding giữ | CL có tiêu đề |
|---|---|
| `SubAppsServiceRemoveResult.manifest_id` | `[sub apps] change web api` |
| `TextAutosizerPageInfo.main_frame_width` | `[autosizer] Delete the text autosizer` |
| `blink.mojom.RTCMetadata` | `[RTCLogging] Add metadata parameter to finishDiagnosticLogging` |
| `payments.mojom.PaymentRequestEventData` | `Allow web-based payment handlers to indicate error (3/N)` |
| `CastStreamingWinHardwareH264` | `[Cast Streaming] Enable hw H264 encoding by default` |

Vậy nên: **đừng đánh giá mức liên quan từ tiêu đề.** Đọc phần thân, và đọc bản
diff. Phần thân thường gọi tên struct, tên file và lý do; bản diff thì luôn cho
thấy thay đổi.

`(3/N)` và `[2/3]` trong tiêu đề nghĩa là thay đổi được chia thành nhiều CL. CL
bạn đang cầm có thể chỉ là phần đường ống, và một CL anh em mới là phần quan
trọng. Issue nối chúng lại — đó là công dụng của chip issue.

## Đọc commit message

Bốn phần, mỗi phần trả lời một chuyện khác nhau.

- **Tiêu đề** — khu vực và ý định, bằng chữ của tác giả. Tốt cho câu hỏi "đây là
  họ thay đổi nào", vô dụng cho câu hỏi "đây có phải identifier của tôi không".
- **Phần thân** — thường gọi tên struct, file và lý do. Đây là chỗ một thay đổi
  Mojo nói rõ kiểu nào chuyển thành kiểu nào và vì sao.
- **Footer `Bug:` / `Fixed:`** — issue tương ứng. `Fixed:` đóng issue, `Bug:`
  tham chiếu tới nó; Chromium dùng dạng thứ hai nhiều hơn hẳn.
- **Footer máy sinh** — `Cr-Commit-Position: refs/heads/main@{#N}` là bằng chứng
  CL đã land trên main và land ở đâu. Reviewer và `Change-Id` hiếm khi là thứ
  bạn cần.

Một bản revert mang `revert_of`, một bản cherry-pick mang `cherry_pick_of_change`
trong chính bản ghi của Gerrit, và `cl.py` in chúng phía trên message. Chúng đáng
tin hơn việc đọc chuỗi `Revert "..."` từ tiêu đề.

## Đọc bản diff

Gerrit trả bản diff theo từng khối, và loại khối có ý nghĩa:

| Khối | Nghĩa |
|---|---|
| `ab` | không đổi, hiển thị làm ngữ cảnh |
| `a` | bị xoá |
| `b` | được thêm |
| `common: true` | **cùng nội dung, chỉ khác nhau bên trong dòng** |

Loại cuối là một lần thụt lề lại hoặc xuống dòng lại. `cl.py` đánh dấu nó bằng
`~` chứ không phải `-`/`+`, vì tính nó là một lần sửa sẽ khiến một CL chỉ format
lại file trở thành khớp `exact` với mọi khai báo trong file đó.

Phải so **cả hai phía**. Một finding ghi lại trạng thái trước và sau của một khai
báo; CL tạo ra thay đổi đó là CL có dòng **bị xoá** mang giá trị trước và dòng
**được thêm** mang giá trị sau:

```
  -   string? url;
  +   url.mojom.Url? url;
```

Đó là `blink.mojom.TokenError.url` đổi kiểu, và đó chính là bằng chứng mà
`introduced` dựa vào — đọc trực tiếp, không tin theo.

**Tìm trong diff theo giá trị đã đổi, không theo identifier.** Identifier thường
cũng nằm trên các dòng không đổi, và mọi dòng như vậy đều là nhiễu. `cl.py --find`
chỉ đánh dấu các dòng mà CL đã đổi, chính vì lý do đó.

Một file bị CL đổi tên sẽ trả lời dưới đường dẫn cũ, với cả file là một khối duy
nhất và không có dấu hiệu rename. `cl.py` in `(renamed from ...)` khi metadata của
Gerrit nói vậy; một bản diff "rỗng" ở một mục bị xoá thường chính là trường hợp
này.

## Bốn câu hỏi mà chỉ bản diff trả lời được

Hỏi theo thứ tự. Dừng ở câu "không" đầu tiên.

1. **Phía bị xoá có mang giá trị "trước" của finding không?** Nếu finding nói
   `Vector2d → Vector2dF` mà không dòng bị xoá nào chứa `Vector2d`, thì CL này
   không tạo ra thay đổi đó.
2. **Phía được thêm có mang giá trị "sau" không?** Có cả hai phía là bằng chứng
   mạnh nhất có thể có, ngoài việc chạy thật code.
3. **Thay đổi có nằm bên trong đúng khai báo mà finding gọi tên không**, hay nằm
   ở chỗ khác trong cùng file? Một file toàn khai báo khiến CL nào cũng có một
   dòng nằm gần khai báo nào đó.
4. **Nó có hơn một lần thụt lề lại không?** Mọi dòng đánh dấu `~` và không có
   dòng `-`/`+` nào nghĩa là chỉ format lại, và format lại không gây ra gì cả.

Ba câu "có" thì CL đó là nguyên nhân. Một câu "không" thì nó là ngữ cảnh — hãy
nói rõ là ngữ cảnh.

## Khi bản diff bác bỏ chính CL đó

Chuyện này có xảy ra, và một lần bác bỏ là một kết quả thật. Để ý các dấu hiệu:

- **Diff chạm vào một member khác của cùng struct.** Hay gặp với Mojo: CL sửa
  phần thân của khai báo nên được gán `declares`, nhưng member nó sửa không phải
  member của bạn.
- **Toàn bộ diff là `~`.** Chỉ format lại.
- **Thay đổi đi theo chiều ngược lại.** CL xoá đi thứ mà finding nói là được thêm.
- **Ngày nằm ngoài khoảng của hai cây source.** `why.py` giờ không hiện các CL
  này, nhưng một CL bạn tới được từ lịch sử của một issue thì có thể thuộc bất kỳ
  milestone nào.

Khi một trong số đó đúng, dòng đó **chưa được trả lời**. Quay lại các CL khác của
nó, tăng `--budget`, hoặc báo cáo rằng lần tìm đã tới được file nhưng chưa tới
được nguyên nhân.

## Câu lệnh

```bash
# CL tự nói gì về nó, và nó chạm vào những file nào
python3 skills/investigating-chromium-root-causes/scripts/cl.py 7982397

# diff của một file, chỉ đánh dấu các dòng đã đổi có mang giá trị cần tìm
python3 skills/investigating-chromium-root-causes/scripts/cl.py \
  7982397 federated_auth_request.mojom --find 'url.mojom.Url? url'

# toàn bộ diff của file đó, không đánh dấu
python3 skills/investigating-chromium-root-causes/scripts/cl.py \
  7982397 federated_auth_request.mojom --context 0
```

`--find` lặp lại được; truyền cả giá trị trước và giá trị sau cùng lúc để thấy
hai phía của thay đổi trong một lần.
