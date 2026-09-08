---
name: investigating-chromium-root-causes
description: Lần một thay đổi Chromium ngược về review đã tạo ra nó và con bug mà review đó đang sửa, rồi đánh giá xem nguyên nhân ấy có thật sự giải thích được triệu chứng đang được báo hay không. Dùng khi được hỏi một finding cụ thể thật ra nghĩa là gì, vì sao một flag lật, một thay đổi để làm gì, nên đọc review hay issue nào, cái gì đã hỏng sau một đợt nâng version Chromium và vì sao, hoặc khi có một triệu chứng được báo mà không finding nào rõ ràng giải thích được nó. Mỗi lần chỉ làm việc với một identifier hoặc một triệu chứng. Dùng analyzing-chromium-upgrades thay cho skill này khi cần một báo cáo xếp hạng đầy đủ về mọi thứ đã đổi giữa hai version.
---

# Truy nguyên nguyên nhân gốc của một thay đổi Chromium

Một báo cáo nói **cái gì đã đổi**. Skill này trả lời **vì sao nó đổi, và điều đó có giải thích được thứ mà bạn được hỏi hay không.**

Báo cáo không làm được việc đó. Nó so hai cây source, mà cây source không ghi lại ý định: `disabled → enabled` là tất cả những gì một bản diff cho biết. Ý định nằm trên review server của Chromium, và skill này lấy nó về.

## Ba câu hỏi, thường xuyên bị gộp thành một

Gần như mọi câu trả lời sai ở đây đều là một trong ba câu này được trả lời bằng bằng chứng của câu khác.

| # | Câu hỏi | Bằng chứng nào trả lời được |
|---|---|---|
| 1 | Cái gì đã đổi? | `report.json` — signal, phần chênh lệch, `path:line` |
| 2 | Vì sao Chromium đổi nó? | CL, và **issue** mà CL đó dẫn |
| 3 | Vì sao bản build *của mình* hỏng? | cây source của mình, đọc đối chiếu với 1 và 2 |

**Một signal không phải một nguyên nhân.** `ipc_signature_change` nói rằng một cấu trúc dữ liệu đã đổi. Nó không nói vì sao có người đổi nó, và nó không bao giờ nói triệu chứng của bạn đến từ đó. Báo cáo một signal như nguyên nhân gốc là trả lời câu 2 bằng bằng chứng của câu 1, và đó là lỗi skill này được viết ra để ngăn.

**Một CL không phải là lỗi.** CL nói *đã làm gì*. Issue nói *cái gì đã sai*. Người hỏi "lỗi thật sự là gì" là đang hỏi về issue.

**Không có gì ở đây chạm tới câu hỏi 3.** Công cụ so Chromium với Chromium. Hãy nói rõ điều đó, mọi lần, thay vì để một câu trả lời tự tin cho câu 2 bị đọc thành câu trả lời cho câu 3.

## Trước khi bắt đầu

Chạy mọi lệnh **từ thư mục gốc của repo `chromiumdiff`**: mọi đường dẫn dưới đây đều tương đối so với gốc repo, và `python3 -m chromiumdiff` cần import được package nên ở thư mục khác nó báo `No module named chromiumdiff`.

Một **finding** là một dòng của báo cáo — một phần tử của mảng `findings` trong `report.json`. Bên trong nó, `change` giữ phần mô tả khai báo đã đổi: `kind`, `signals`, `locations`, `before`, `after`. Nghĩa của từng signal nằm ở **[reference/reading-a-finding.md](investigating-chromium-root-causes/reference/reading-a-finding.md)**.

## Quy trình

```
- [ ] 1. Ghim câu hỏi vào đúng một identifier
- [ ] 2. Lấy dòng tương ứng, hoặc xác định là không có dòng nào
- [ ] 3. Lấy CL và issue
- [ ] 4. Đọc chính lời văn và chính bản diff của CL, và issue đứng sau nó
- [ ] 5. Kiểm tra khẳng định nhân quả với triệu chứng
- [ ] 6. Trả lời ở đúng nấc bằng chứng mà bạn thật sự đạt tới
```

### Bước 1: Ghim câu hỏi vào đúng một identifier

Mọi thứ phía sau đều tra theo `uid` = `kind:key`, ví dụ `base_feature:BackForwardCachePauseMicrotasks` hoặc `mojo_field:blink.mojom.CommitNavigationParams.early_hints_preloaded_resources`.

**Nếu đã có sẵn một finding, một tên flag, hoặc một identifier** — thì bạn đã có nó rồi.

**Nếu chỉ có một triệu chứng** ("trang downloads mất một toggle", "các trang extension bị treo") — báo cáo được đánh chỉ mục theo tên khai báo, không theo triệu chứng. Grep nó bằng chính những từ trong lời phàn nàn thì không tìm ra gì, và cũng không có nghĩa gì. Hãy ánh xạ triệu chứng sang một `kind` trước: **[reference/symptom-to-uid.md](investigating-chromium-root-causes/reference/symptom-to-uid.md)**.

Nếu yêu cầu nêu ra nhiều thứ, làm từng thứ một. Một câu trả lời gộp sẽ che mất bằng chứng nào thuộc về khẳng định nào.

### Bước 2: Lấy dòng tương ứng, hoặc xác định là không có dòng nào

```bash
python3 skills/investigating-chromium-root-causes/scripts/why.py \
  out/M148_to_M151 BackForwardCachePauseMicrotasks
```

Phần tìm kiếm nhận một uid, một key, một tên, hoặc một mẩu đường dẫn. Khi có nhiều kết quả khớp, nó in ra một danh sách đã xếp hạng rồi dừng, nên hãy chạy lại với đúng một uid. Không khớp gì cả **không** xác lập rằng source không đổi — đọc **[reference/no-row.md](investigating-chromium-root-causes/reference/no-row.md)** để phân biệt các nguyên nhân trước khi kết luận.

### Bước 3: Lấy CL và issue

Vẫn là câu lệnh đó. Nếu finding chưa từng được tra, script sẽ hỏi Gerrit rồi in kết quả ra; nếu đã tra rồi, nó in ra thứ đã lưu. Các tuỳ chọn:

| Tuỳ chọn | Mặc định | Dùng khi |
|---|---|---|
| `--budget N` | 600 | một file khai báo quá đông CL bị từ chối; nâng nó lên |
| `--save` | tắt | muốn ghi câu trả lời ngược vào `report.json` |
| `--json` | tắt | cần khối dữ liệu thô thay vì văn xuôi |
| `--issues N` | 6 | số issue script đi lấy về cùng lúc; hạ xuống nếu chỉ cần CL |
| `--limit N` | 15 | số dòng in ra khi tìm kiếm khớp nhiều kết quả |
| `--cache DIR` | `.chromiumdiff-cache` ở gốc repo, hoặc `CHROMIUMDIFF_CACHE` | source đã tải nằm ở chỗ khác |

Những gì một phiên `serve` tìm được chỉ được lưu vào `report.json` chứ không vào đâu khác. `report.md` và `report.html` trên đĩa vẫn là những gì lần chạy đã ghi ra, nên hãy render lại trước khi đưa bất kỳ file nào trong hai file đó cho ai:

```bash
python3 -m chromiumdiff report out/M148_to_M151/report.json --format both --out out/M148_to_M151/report
```

Đó cũng là bước đưa phần gom nhóm vào: các finding dùng chung một CL được nối lại khi lần tra cứu mang CL đó về, và `report.md` gọi tên nhóm ngay trong phần riêng của từng finding — đúng chỗ mà người đọc sẽ dán vào ticket.

Nó cần truy cập mạng tới `chromium-review.googlesource.com`. `python3 -m chromiumdiff check` kiểm tra host đó.

**Serve là lựa chọn thay thế, không phải điều kiện bắt buộc.** `python3 -m chromiumdiff serve <dir>` cho một con người có được đúng phần tra cứu ấy bằng cách bấm vào một dòng. Đề xuất cách đó khi người đọc là con người; dùng script khi người đọc là bạn.

**Mỗi CL đều mang một verdict, và verdict đặt trần cho những gì bạn được phép khẳng định.**

| Verdict | Bạn được phép nói |
|---|---|
| `introduced` | "CL này đã tạo ra thay đổi" — một dòng được thêm vào bên trong khai báo mang giá trị mới |
| `exact` | "CL này đã sửa một dòng có chứa identifier" |
| `moved` | "file chứa khai báo đã bị CL này đổi tên; không dòng nào đổi" |
| `declares` | "CL này đã sửa phần thân của khai báo" — nhiều khả năng đúng, và phải nói rõ vì sao nó không phải `exact` |
| `described` | "tiêu đề của chính CL có gọi tên nó" — không đọc diff nào |
| `crowded` | **không nói gì về nguyên nhân.** Những CL này cùng sửa một khai báo; đọc danh sách như lịch sử của khai báo đó |
| `touched` | **không nói gì về nguyên nhân.** Những CL này chỉ đơn giản là có chạm vào file |

Trích `crowded` hay `touched` như nguyên nhân là bịa ra một nguyên nhân. Chính vì vậy script gắn nhãn `LEAD ONLY` cho cả hai.

### Bước 4: Đọc chính lời văn và chính bản diff của CL, và issue đứng sau nó

**Đọc chính bằng chứng, đừng đọc bản tóm tắt của nó.** Lần ra theo thứ tự này, và dừng ngay khi câu trả lời đã đủ:

1. **Tiêu đề của issue.** Thường chính là lỗi thật, gói trong một dòng.
2. **Những CL khác cùng dẫn issue đó.** `why.py` lấy sẵn các issue này về và in ra cùng CL — mặc định tối đa 6, đổi bằng `--issues`. Không phải đi bấm gì cả; bấm chuột là đường của người dùng trang `serve`, ở đó chip issue mở lịch sử ngay dưới CL. Đây là lịch sử sửa lỗi, gồm cả việc bug có nghiêm trọng tới mức phải merge ngược về các nhánh đã phát hành hay không. Tiền tố `[M148]` hay `[m147]` trên tiêu đề một CL đúng là dấu hiệu đó, và nó là bằng chứng mạnh cho thấy con bug đã ảnh hưởng tới người dùng thật.
3. **Chính lời văn và chính bản diff của CL**, mỗi khi câu trả lời có trọng lượng — và luôn luôn phải đọc trước khi trích một CL vào ticket, mỗi khi verdict là `declares` hoặc `described`, và mỗi khi tiêu đề đọc lên có vẻ không liên quan tới finding:

   ```bash
   python3 skills/investigating-chromium-root-causes/scripts/cl.py 7982397
   python3 skills/investigating-chromium-root-causes/scripts/cl.py \
     7982397 federated_auth_request.mojom --find 'url.mojom.Url? url'
   ```

   **Đừng đánh giá mức liên quan qua tiêu đề.** Tiêu đề CL của Chromium có dạng `[khu vực] việc gì`, và khu vực là cách tác giả gọi mảng sản phẩm đó, không phải identifier — `[sub apps] change web api` chính là CL đứng sau `SubAppsServiceRemoveResult.manifest_id`. Đo trên 84 dòng Mojo và Web IDL của một lần chạy thật M148 → M151: toàn bộ commit message gọi đúng tên identifier ở 39 dòng; đọc nốt phần còn lại thì tất cả trừ năm dòng đều rõ ràng theo cách dùng từ của tác giả.
   **[reference/reading-a-cl.md](investigating-chromium-root-causes/reference/reading-a-cl.md)** nói cách đọc cả hai, và mỗi mức bằng chứng cho phép khẳng định tới đâu.

**Một issue bị hạn chế truy cập là chuyện bình thường, không phải một thất bại.** Gần một nửa trả về HTTP 403 — 44 trong 97 issue mà top 150 finding của một lần chạy M148 → M151 dẫn tới — các component security, abuse, hoặc nội bộ Google. Các CL vẫn công khai và tiêu đề của chúng cho biết chuyện gì đã xảy ra. Hãy báo cáo lịch sử sửa lỗi và ghi rõ là không mở được issue; đừng báo cáo rằng công cụ hỏng.

### Bước 5: Kiểm tra khẳng định nhân quả với triệu chứng

Trước khi viết câu trả lời, đem khẳng định đó đối chiếu với những điểm sau. Mỗi điểm đều đã từng tạo ra một câu trả lời sai mà tự tin.

- **Ngày tháng có khớp không, ở cả hai đầu?** Một CL được merge trước điểm rẽ nhánh của version *from* thì có mặt trong cả hai cây và không thể giải thích một sự khác biệt. Một CL được merge sau điểm rẽ nhánh của version *to* thì hoàn toàn không có trong cây đã phát hành — `Cr-Branched-From` trong mỗi tag cho cả hai mốc ngày. Phần tra cứu ép cả hai điều kiện, và một dòng đã serve nhưng được ghi theo cửa sổ cũ và rộng hơn sẽ bị nhận ra và hỏi lại chứ không phục vụ nguyên trạng — nên một ngày vượt quá điểm rẽ nhánh của version đích trên một dòng đã serve là dấu hiệu của chuyện khác, và đáng báo lại.
- **Chiều có khớp không?** Một flag đi từ `enabled → disabled` thì không được giải thích bởi một CL có tiêu đề "Enable …". Kiểm tra xem phần chênh lệch thật sự đi theo chiều nào.
- **CL nói về khai báo này, hay chỉ nói về file?** Một file bị chạm bởi một lần đổi tên, một lần format lại và cả thay đổi thật thì báo cáo cả ba. `introduced` và `exact` phân biệt được; riêng `declares` thì không. Bản diff trả lời được, qua bốn câu hỏi: có dòng bị xoá nào mang giá trị trước của finding không, có dòng được thêm nào mang giá trị sau không, thay đổi có nằm bên trong khai báo mà finding gọi tên không, và nó có nhiều hơn một lần thụt lề lại không? Ba câu có thì CL là nguyên nhân; một câu không thì nó là bối cảnh. Gerrit đánh dấu một lần thụt lề lại là `common: true` và `cl.py` in nó bằng `~`, vì tính một dòng như vậy thành một chỉnh sửa sẽ biến một lần format lại thành bằng chứng.
- **Cơ chế đó có với tới triệu chứng không?** Một lần lật flag giải thích được thay đổi hành vi trên đúng platform mà flag đã lật. Đọc `change.before.platform_state.windows` và `change.after.platform_state.windows`; ngay cạnh chúng có `default_state` — đó là mặc định chung của Chromium, không phải của Windows.
- **Đây là nguyên nhân, hay chỉ là một bước trong chuỗi?** Launch → revert → reland là một thay đổi và nhiều CL. CL cũ nhất là chỗ bắt đầu; CL mới nhất là trạng thái hiện tại. Báo cáo cả hai.

Nếu một phép kiểm tra không đạt thì CL là bối cảnh, không phải nguyên nhân. Hãy nói rõ nó là cái nào.

### Bước 6: Trả lời ở đúng nấc bằng chứng mà bạn thật sự đạt tới

```markdown
**What changed:** [khai báo đó, kèm `path:line`, và đi theo chiều nào]
**Why:** [lỗi mà issue mô tả, gói trong một câu, rồi tới CL đã hành động lên nó]
**The history:** [launch/revert/reland và mọi lần merge ngược, cũ nhất trước]
**Confidence:** [một dòng lấy từ bảng dưới đây, có gọi tên verdict]
**What this does not establish:** [rằng nó ảnh hưởng tới bản build của mình — luôn luôn phải có]
**To check next:** [identifier cần grep trong cây source của mình]
```

| Được nói | Khi nào |
|---|---|
| Nguyên nhân là CL N | bản diff cho thấy giá trị trước của finding bị xoá và giá trị sau được thêm, ngay bên trong khai báo |
| Nhiều khả năng nguyên nhân là CL N | `introduced` hoặc `exact`, ngày tháng và chiều đều khớp, nhưng chưa đọc diff |
| Có liên quan, chưa chứng minh được là nguyên nhân | `declares` hoặc `described`, hoặc nhiều CL cùng một chuỗi |
| Đây là các ứng viên, không phải nguyên nhân | `crowded` hoặc `touched`, hoặc các phép kiểm tra ở bước 5 không đạt |
| Chưa xác lập được | lần tra cứu trượt, lỗi, hoặc bị từ chối — nói rõ là trường hợp nào |

Dòng đầu tiên đòi phải có bản diff. Nấc 4 của thang bằng chứng trong [reference/reading-a-cl.md](investigating-chromium-root-causes/reference/reading-a-cl.md) là nấc duy nhất cho phép dùng chữ "gây ra"; mọi nấc dưới nó chỉ cho phép "gọi tên", "có chạm vào", hoặc "được tìm thấy nhờ". **Hãy báo cáo nấc cao nhất mà bạn thật sự đạt tới, và nói rõ đó là nấc nào** — một dòng chỉ được trả lời từ verdict rồi viết ra như thể đã đọc diff là lỗi skill này được viết ra để ngăn.

Đừng bao giờ làm tròn hai mức cuối lên. "Ứng viên" mà viết thành "nguyên nhân" là lỗi nặng nhất có thể mắc ở bước này.

## Ví dụ có lời giải

Câu hỏi: *"`BackForwardCachePauseMicrotasks` đi từ disabled sang enabled ở M148 → M151. Đó là cái gì, và có quan trọng không?"*

Chỉ riêng báo cáo thì nói: score 75, `behaviour`, các signal `enabled_by_default` và `default_flip_on`, `disabled → enabled` trên Windows, tại `third_party/blink/common/features.cc:168`. Đọc chừng đó sẽ hiểu thành một lần ra mắt tính năng, và hiểu vậy là sai.

Lần tra cứu trả về hai CL và hai issue:

```
CL 7747043  2026-04-10  [declares]  Disable BackForwardCachePauseMicrotasks
CL 7789307  2026-04-23  [declares]  Enable BackForwardCachePauseMicrotasks by default

issue 500975618
  Extension iframe causes Promises to stall in all extension pages after navigation
    CL 7747043  2026-04-10  Disable BackForwardCachePauseMicrotasks
    CL 7756901  2026-04-13  [m147] Disable BackForwardCachePauseMicrotasks
    CL 7757083  2026-04-14  [M148] Disable BackForwardCachePauseMicrotasks
    CL 7763401  2026-04-21  Do not ... pause microtasks for extension iframes
issue 501771345 (RESTRICTED)
    CL 7774414  2026-04-22  Disable BFCache for pages with extension subframes
    CL 7789307  2026-04-23  Enable BackForwardCachePauseMicrotasks by default
```

**Câu trả lời ngược với những gì báo cáo gợi ý.** Đây không phải một lần ra mắt tính năng. Tính năng vốn đang bật, nó làm treo mọi Promise trên các trang extension sau một lần điều hướng, nó bị tắt đi và được merge ngược về M147 và M148 như một biện pháp khẩn cấp, con bug thật được sửa một cách hẹp, rồi nó mới được bật lại. `disabled → enabled` giữa hai version của chúng ta chính là lần *khôi phục*, và thứ đáng đem đi test là thứ đã hỏng: các trang extension có iframe, và Promise sau khi điều hướng.

Một bản diff không cho ra được điều đó, và đọc `features.cc` cũng không.

Độ tin cậy: nhiều khả năng là nguyên nhân — cả hai CL đều là `declares` chứ không phải `exact`, vì phần chỉnh sửa nằm trong thân khai báo chứ không nằm trên dòng đặt tên flag. Thứ làm câu trả lời trở nên thuyết phục là lịch sử issue, không phải verdict.

## Tài liệu tham chiếu

- **[reference/reading-a-cl.md](investigating-chromium-root-causes/reference/reading-a-cl.md)** — thang bằng chứng và mỗi nấc cho phép khẳng định tới đâu; vì sao cách dùng từ của tác giả không phải là identifier; cách đọc một commit message và một bản diff, và bốn câu hỏi mà chỉ bản diff mới trả lời được.
- **[reference/no-row.md](investigating-chromium-root-causes/reference/no-row.md)** — các trường hợp một lần tra cứu không trả về kết quả: không có finding nào khớp (A1–A5) và có finding nhưng không có CL giải thích được (B1–B6), kèm bảng đọc các trường chẩn đoán trong `enrichment.gerrit`. Trường hợp A3 và A4 chuyển sang thủ tục đọc lịch sử trực tiếp trong `analyzing-chromium-upgrades/reference/history.md`.
- **[reference/symptom-to-uid.md](investigating-chromium-root-causes/reference/symptom-to-uid.md)** — bắt đầu từ một triệu chứng người dùng thấy được thay vì từ một identifier.
- **[reference/reading-a-finding.md](investigating-chromium-root-causes/reference/reading-a-finding.md)** — các signal của skill này nghĩa là gì, những cách đi tới kết luận sai từ một finding đúng, và chuỗi mắt xích đứng sau một control trong settings. Đọc trước khi diễn giải bất kỳ mục bị xoá nào.

## Những gì skill này không xác lập được

Nêu những điều này kèm theo câu trả lời, không phải thay cho câu trả lời.

- **Rằng thay đổi này ảnh hưởng tới một sản phẩm cụ thể.** Ở đây Chromium được so với Chromium. Grep identifier đó trong cây source của chính mình mới là bước trả lời câu ấy, và skill này không làm hộ bạn bước đó.
- **Rằng một CL có gọi tên thay đổi thì đã gây ra triệu chứng.** Nó chỉ xác lập rằng một CL đã sửa thứ đó trong khoảng thời gian đang xét. Bước 5 là chỗ còn thiếu, và không phải lúc nào cũng bù được.
- **Chuyện gì đã xảy ra bên trong thân một hàm.** Chỉ khai báo mà thôi.
- **Bất cứ thứ gì nằm ngoài repository** — Finch, enterprise policy, script khởi chạy. Một flag đã lật giá trị mặc định vẫn có thể bị override ở đó, và bản override ấy thì ở đây không nhìn thấy được.
