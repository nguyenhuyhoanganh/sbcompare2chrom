# 4. Fact là gì và từng extractor tạo Fact như thế nào

Đây là tài liệu tham chiếu. Phần đầu giải thích khái niệm `Fact`; phần sau đi qua đủ 16 loại `Fact`, mỗi loại có một ví dụ "source đầu vào → JSON đầu ra" thật.

## `Fact` là một khai báo đã được chuẩn hoá

Một file mã nguồn có thể dài hàng nghìn dòng, và phần lớn thay đổi của nó đến từ format lại hoặc refactor. Nếu đem nguyên file đi so, kết quả sẽ ngập trong nhiễu.

Vì vậy ChromiumDiff làm khác: nó lấy ra từng khai báo có ý nghĩa, chuyển mỗi khai báo thành một object nhỏ gọi là `Fact`, rồi ghép các `Fact` tương ứng giữa hai version với nhau.

Mọi `Fact` đều dùng chung một schema:

```json
{
  "kind": "loại khai báo",
  "key": "identity ổn định trong cùng kind",
  "name": "tên để hiển thị",
  "path": "đường dẫn tương đối tính từ Chromium src/",
  "line": 123,
  "attrs": {
    "thuộc tính": "giá trị đã chuẩn hoá"
  }
}
```

Định danh dùng khi so sánh được ghép từ hai trường đầu:

```text
uid = kind + ":" + key
```

Một vài UID thật để hình dung:

```text
base_feature:BackForwardCache
idl_member:Example.connect
mojo_method:network.mojom.Probe.Start
pref:download.prompt_for_download
webui_route:settings/LOCAL_NETWORK
```

## Vai trò của từng trường

| Trường | Dùng để làm gì | Có được đem đi so sánh không? |
|---|---|---|
| `kind` | Chọn ngữ nghĩa, bảng thuộc tính, signal và owner | Là một phần của UID |
| `key` | Ghép cùng một khai báo giữa hai version | Là phần chính của UID |
| `name` | Hiển thị cho người đọc | Không |
| `path` | Dẫn tới bằng chứng, và phát hiện khai báo bị chuyển file | Đường dẫn khác nhau tạo ra delta `path` |
| `line` | Mở đúng dòng trong source | Không — chỉ đổi số dòng thì không tạo ra thay đổi |
| `attrs` | Giữ trạng thái, kiểu, signature, gate, cách đấu nối... | Chỉ những thuộc tính nằm trong danh sách cho phép của từng `kind` |

Vì sao `path` và `line` không nằm trong `attrs`? Vì chúng là **provenance** (thông tin về nguồn gốc), không phải nội dung của khai báo. Một khai báo bị đẩy xuống 20 dòng chỉ vì ai đó thêm comment phía trên thì không phải thay đổi hành vi.

Riêng việc khai báo chuyển sang file khác vẫn được giữ lại dưới dạng signal `declaration_moved`, để người tích hợp tìm lại include hoặc bản vá của mình — nhưng nó mang severity thấp.

## "Chuẩn hoá" cụ thể là làm những gì

Cần nói rõ ngay: chuẩn hoá ở đây **không** phải dịch text, và **không** phải để AI tóm tắt. Nó là một tập rule cố định, chạy lần nào cũng ra kết quả y hệt:

1. Chọn identity theo ý nghĩa, không theo cú pháp.
2. Rút gọn khoảng trắng trong signature và biểu thức, nhưng không đụng vào nội dung chuỗi literal.
3. Quy các điều kiện platform về một kết luận dành riêng cho Windows.
4. Tách tên đầy đủ (qualified name) ra để tránh trùng khoá giữa hai module.
5. Giữ cùng một schema cho nhiều dạng khai báo cũ và mới.
6. Bỏ những thuộc tính chỉ phản ánh cách viết mà không đổi hành vi.

Ví dụ rõ nhất là quy tắc 1 và 5. Chromium đã từng viết cùng một feature theo ba dạng:

```cpp
BASE_FEATURE(kFoo, "Foo", base::FEATURE_ENABLED_BY_DEFAULT);
BASE_FEATURE(kFoo, base::FEATURE_ENABLED_BY_DEFAULT);
const base::Feature kFoo{"Foo", base::FEATURE_ENABLED_BY_DEFAULT};
```

Cả ba đều được chuẩn hoá về cùng một kết quả: key `Foo`, symbol `kFoo`, trạng thái `enabled`.

Trường `declared_form` vẫn được lưu để debug, nhưng nó không nằm trong danh sách thuộc tính được so sánh. Nhờ vậy, một đợt Chromium chuyển đồng loạt sang dạng macro mới sẽ không tạo ra hàng nghìn finding giả.

## Từ hai `Fact` đến một `Change`

```text
Snapshot cũ, đánh chỉ mục theo uid      Snapshot mới, đánh chỉ mục theo uid
             │                                        │
             └──────────────────┬─────────────────────┘
                                ▼
                      cùng uid có ở cả hai bên không?
                    │           │            │
                    │           │            └─ chỉ có ở bên cũ  → removed
                    │           └────────────── chỉ có ở bên mới → added
                    └────────────────────────── có ở cả hai      → so các thuộc tính có ý nghĩa
                                                                     │
                                                                     └─ khác nhau → modified + deltas
```

Sau lượt ghép cơ bản này, còn hai bước ghép đặc biệt nữa, dành cho các trường hợp mà chính `key` đã thay đổi:

- **Đổi tên pref / switch / feature string**: ghép một `removed` với một `added` nếu biến C++ của chúng giữ nguyên.
- **WebUI control chuyển pref**: ghép một `removed` với một `added` nếu surface, trang và element id giữ nguyên, chỉ có pref trong khoá là đổi.

## 16 loại `Fact` và extractor sinh ra chúng

| Extractor | Các loại `Fact` |
|---|---|
| `base_features` | `base_feature`, `feature_param` |
| `blink_runtime` | `blink_runtime_feature` |
| `web_idl` | `idl_interface`, `idl_member` |
| `mojom` | `mojo_interface`, `mojo_method`, `mojo_struct`, `mojo_field`, `mojo_enum` |
| `constants` | `switch`, `pref` |
| `flags_metadata` | `flag_entry` |
| `webui_routes` | `webui_route` |
| `webui_controls` | `webui_control` |
| `webui_gates` | `webui_gate` |

Các ví dụ dưới đây là **đầu ra thật** của extractor hiện tại, chạy trên đầu vào tối giản.

## 1. `base_feature`

### Đầu vào

Đường dẫn: `content/common/features.cc`

```cpp
BASE_FEATURE(kBackForwardCache,
             "BackForwardCache",
             base::FEATURE_ENABLED_BY_DEFAULT);
```

### `Fact` sinh ra

```json
{
  "kind": "base_feature",
  "key": "BackForwardCache",
  "name": "BackForwardCache",
  "path": "content/common/features.cc",
  "line": 1,
  "attrs": {
    "var": "kBackForwardCache",
    "default_state": "enabled",
    "platform_state": {"windows": "enabled"},
    "declared_form": "macro3",
    "conditions": []
  }
}
```

### Tiêu chí trích xuất và ý nghĩa từng trường

- Tham số đầu tiên của macro phải là một biến C++ dạng `k...`.
- `key` ưu tiên lấy feature string ở dạng macro 3 tham số; với dạng 2 tham số, key được suy ra bằng cách bỏ chữ `k` ở đầu tên biến.
- `default_state` nhận một trong ba giá trị: `enabled`, `disabled`, `unknown`.
- `platform_state.windows` được tính bằng cách giải cả điều kiện nằm trong macro lẫn khối `#if` bao bên ngoài.
- `conditions` giữ nguyên chuỗi guard thô, để người đọc truy ngược lại được.
- `var` cần thiết để phát hiện code Samsung còn đang dùng symbol cũ.
- `declared_form` chỉ để giải thích parser đã đọc dạng nào; không bao giờ đem so ngữ nghĩa.

**Thuộc tính được so sánh:** `default_state`, `platform_state`, `conditions`, `var`.

## 2. `feature_param`

### Đầu vào

```cpp
BASE_FEATURE_PARAM(int,
                   kTimeToLiveSeconds,
                   &kBackForwardCache,
                   "time_to_live_seconds",
                   1800);
```

### `Fact` sinh ra

```json
{
  "kind": "feature_param",
  "key": "BackForwardCache/time_to_live_seconds",
  "name": "time_to_live_seconds",
  "path": "content/common/features.cc",
  "line": 1,
  "attrs": {
    "feature": "BackForwardCache",
    "type": "int",
    "var": "kTimeToLiveSeconds",
    "default": "1800"
  }
}
```

### Tiêu chí và cách chọn identity

`key` có dạng `feature/name`. Nếu khai báo không có tên dạng chuỗi, tên param được suy ra từ tên biến — mục đích là để việc đổi giá trị mặc định không kéo theo đổi identity.

Chi tiết này quan trọng hơn vẻ ngoài của nó. Giả sử parser nhầm `1800` là tên param: khi Chromium đổi `1800 → 3600`, báo cáo sẽ hiện thành **một param bị xoá cộng một param mới được thêm**, thay vì đúng bản chất là `param_default_changed`. Người đọc sẽ mất thời gian đi tìm một param không hề tồn tại.

**Thuộc tính được so sánh:** `default`, `type`, `feature`, `var`, `platform_state`.

## 3. `blink_runtime_feature`

### Đầu vào

Đường dẫn: `third_party/blink/renderer/platform/runtime_enabled_features.json5`

```json5
{
  data: [
    {
      name: "LocalNetworkAccess",
      status: {"Win": "stable", "default": "experimental"},
      base_feature: "LocalNetworkAccessChecks",
      public: true
    }
  ]
}
```

### `Fact` sinh ra

```json
{
  "kind": "blink_runtime_feature",
  "key": "LocalNetworkAccess",
  "name": "LocalNetworkAccess",
  "path": "third_party/blink/renderer/platform/runtime_enabled_features.json5",
  "line": 3,
  "attrs": {
    "status": "per-platform",
    "platform_status": {
      "windows": "stable",
      "default": "experimental"
    },
    "windows_status": "stable",
    "base_feature": "LocalNetworkAccessChecks",
    "public": true
  }
}
```

### Tiêu chí và thuộc tính

Mọi entry có trường `name` đều tạo ra `Fact`. Trường `status` được xử lý theo hai trường hợp:

- nếu `status` là một chuỗi, giá trị đó áp dụng cho cả Windows lẫn mặc định;
- nếu `status` là một object, khoá `Win` được ánh xạ thành `windows`. Khi object không có khoá `default`, những platform không được liệt kê nhận trạng thái rỗng — **không** được tự hiểu là stable.

Ngoài các trường trên, extractor còn giữ lại mọi thông tin đấu nối quan trọng đang có trong manifest: `base_feature_status`, `origin_trial_feature_name`, `depends_on`, `implied_by`, `copied_from_base_feature_if`, `settable_from_internals`, quyền truy cập của bên thứ ba và của browser process, cùng các trường về OS/loại trial/ngữ cảnh không bảo mật và trạng thái protected.

Tất cả những trường này đều được đem so sánh, vì chúng quyết định hai điều: feature được bật bởi **cái gì**, và **ai** tiếp cận được nó.

## 4. `idl_interface`

### Đầu vào

Đường dẫn: `third_party/blink/renderer/modules/example/example.idl`

```webidl
[Exposed=Window, RuntimeEnabled=LocalNetworkAccess]
interface Example : EventTarget {
  Promise<DOMString> connect(DOMString host);
};
```

### `Fact` sinh ra

```json
{
  "kind": "idl_interface",
  "key": "Example",
  "name": "Example",
  "path": "third_party/blink/renderer/modules/example/example.idl",
  "line": 2,
  "attrs": {
    "idl_kind": "interface",
    "partial": false,
    "inherits": "EventTarget",
    "ext": {
      "Exposed": "Window",
      "RuntimeEnabled": "LocalNetworkAccess"
    }
  }
}
```

### Tiêu chí và thuộc tính

Identity là tên interface. Một khai báo `partial interface Example` **không** tạo ra `Fact` interface thứ hai, vì identity thuộc về định nghĩa gốc; nhưng các member bên trong khối partial vẫn tạo ra `idl_member` với `from_partial=true`.

Với enum, `attrs` có thêm trường `values`.

**Thuộc tính được so sánh:** `idl_kind`, `inherits`, `ext`, `values`. Trường `partial` chỉ là provenance — nó ghi lại việc khai báo được ghép từ đâu, và không dùng để tạo thay đổi ngữ nghĩa cho interface gốc.

## 5. `idl_member`

### Đầu vào

```webidl
interface Example {
  [RuntimeEnabled=LocalNetworkAccess]
  Promise<DOMString> connect(DOMString host);
};
```

### `Fact` sinh ra

```json
{
  "kind": "idl_member",
  "key": "Example.connect",
  "name": "connect",
  "path": "third_party/blink/renderer/modules/example/example.idl",
  "line": 3,
  "attrs": {
    "interface": "Example",
    "member_type": "operation",
    "signature": "Promise<DOMString> connect(DOMString host)",
    "ext": {"RuntimeEnabled": "LocalNetworkAccess"},
    "runtime_enabled": "LocalNetworkAccess",
    "from_partial": false
  }
}
```

### Tiêu chí và cách xử lý overload

Khoá có dạng `Interface.member`. Parser nhận được các loại member: operation, attribute, trường của dictionary, const, constructor, và các member khai báo kiểu declarative. Khoảng trắng quanh `(`, `<`, `>`, `,` được chuẩn hoá, nhưng nội dung bên trong chuỗi literal thì giữ nguyên.

Overload cần cách xử lý riêng: nếu một UID có nhiều overload, bước loại trùng sẽ tổng hợp lại thành `signatures`, `overload_traits` và `overload_locations`. Nhờ vậy, việc thêm hoặc bỏ một overload không bị mất dấu chỉ vì dictionary chỉ giữ được một UID duy nhất.

**Thuộc tính được so sánh:** `signature`, `signatures`, `overload_traits`, `member_type`, `ext`, `runtime_enabled`.

## 6. `mojo_method`

### Đầu vào

Đường dẫn: `services/network/public/mojom/example.mojom`

```mojom
module network.mojom;
[Stable] interface Probe {
  Start@0(string url) => (bool accepted);
};
```

### `Fact` sinh ra

```json
{
  "kind": "mojo_method",
  "key": "network.mojom.Probe.Start",
  "name": "Start",
  "path": "services/network/public/mojom/example.mojom",
  "line": 3,
  "attrs": {
    "interface": "network.mojom.Probe",
    "module": "network.mojom",
    "signature": "Start(string url) => (bool accepted)",
    "params": "string url",
    "response": "bool accepted",
    "attrs": {},
    "ordinal": "0",
    "position": 0,
    "stable": true
  }
}
```

### Tiêu chí và thuộc tính

Tên interface đầy đủ (kèm module) ngăn hai module khác nhau cùng có `Probe.Start` bị trùng khoá.

Hai trường cần giải thích thêm:

- `ordinal` chỉ có mặt khi source khai báo tường minh.
- `position` **chỉ** được ghi lại bên trong interface có `[Stable]`. Lý do: ở một interface không stable, việc đảo thứ tự method là chuyện bình thường, vì hai đầu luôn được build lại cùng nhau. Nhưng ở interface stable, vị trí trong file chính là một lời hứa về wire format.

**Thuộc tính được so sánh:** `signature`, `params`, `response`, `attrs` của method, `ordinal`, `position` (chỉ khi có ở cả hai bên), `platform_state`.

## 7. `mojo_interface`

Cùng đầu vào ở mục 6 còn tạo thêm `Fact` này:

```json
{
  "kind": "mojo_interface",
  "key": "network.mojom.Probe",
  "name": "Probe",
  "path": "services/network/public/mojom/example.mojom",
  "line": 2,
  "attrs": {
    "module": "network.mojom",
    "method_count": 1,
    "methods": ["Start"],
    "stable": true
  }
}
```

Hai trường `methods` và `method_count` được giữ để giúp giải thích `Fact`, nhưng **không** được đem so sánh.

Lý do rất thực tế: mỗi method đã có `Fact` riêng của nó rồi. Nếu so thêm danh sách ở mức interface, một thay đổi duy nhất sẽ hiện ra hai lần trong báo cáo — một dòng mơ hồ ("danh sách method đã đổi") và một dòng chính xác ("method X bị xoá"). Dòng mơ hồ chỉ làm loãng báo cáo.

**Thuộc tính được so sánh của interface:** chỉ `stable` và `platform_state`.

## 8. `mojo_struct` và union

### Đầu vào

```mojom
[Stable] struct Result {
  int32 code@0;
  [MinVersion=1] string? detail@1;
};
```

### `Fact` của container

```json
{
  "kind": "mojo_struct",
  "key": "network.mojom.Result",
  "name": "Result",
  "path": "services/network/public/mojom/example.mojom",
  "line": 5,
  "attrs": {
    "module": "network.mojom",
    "mojo_kind": "struct",
    "field_count": 2,
    "fields": ["code", "detail"],
    "stable": true
  }
}
```

Trường `mojo_kind` phân biệt `struct` với `union` khi cả hai cùng nằm dưới một tên đầy đủ. Trường `fields` không được đem so sánh, vì mỗi field đã có `Fact` riêng — cùng lý do như ở `mojo_interface`.

**Thuộc tính được so sánh:** `mojo_kind`, `stable`, `platform_state`.

## 9. `mojo_field`

Cùng đầu vào ở mục 8 tạo ra hai `Fact` field. Đây là `Fact` có chú thích version:

```json
{
  "kind": "mojo_field",
  "key": "network.mojom.Result.detail",
  "name": "detail",
  "path": "services/network/public/mojom/example.mojom",
  "line": 7,
  "attrs": {
    "struct": "network.mojom.Result",
    "module": "network.mojom",
    "type": "string?",
    "ordinal": "1",
    "attrs": "MinVersion=1",
    "min_version": "1",
    "stable": true,
    "position": 1
  }
}
```

**Thuộc tính được so sánh:** `type`, `ordinal`, `default`, `attrs` của field, `position` (chỉ khi có ở cả hai bên), `min_version`, `platform_state`.

Cần phân biệt hai nhóm hậu quả trong danh sách trên:

- `type`, `ordinal` và `position` trong một container stable có thể làm **đổi hình dạng dữ liệu trên wire** — hai đầu sẽ đọc byte khác nhau.
- `default` và `MinVersion` đổi **những gì một peer cũ nhìn thấy**, nhưng không đổi cách đọc byte.

## 10. `mojo_enum`

### Đầu vào

```mojom
enum State {
  kIdle = 0,
  kRunning = 1,
};
```

### `Fact` sinh ra

```json
{
  "kind": "mojo_enum",
  "key": "network.mojom.State",
  "name": "State",
  "path": "services/network/public/mojom/example.mojom",
  "line": 9,
  "attrs": {
    "module": "network.mojom",
    "values": ["kIdle = 0", "kRunning = 1"]
  }
}
```

Từng member của enum **không** trở thành `Fact` riêng. Thay vào đó, một `Fact` enum giữ nguyên danh sách giá trị theo thứ tự.

Đây là một đánh đổi có chủ ý: enum trong Mojo được mở rộng rất thường xuyên, nên nếu tách từng member thành `Fact`, báo cáo sẽ có thêm hàng chục nghìn dòng mà không cho biết gì nhiều hơn so với delta của danh sách.

**Thuộc tính được so sánh:** `values`, `stable`, `platform_state`.

## 11. `switch`

### Đầu vào

Đường dẫn: `content/public/common/content_switches.cc`

```cpp
const char kEnableFoo[] = "enable-foo";
```

### `Fact` sinh ra

```json
{
  "kind": "switch",
  "key": "enable-foo",
  "name": "enable-foo",
  "path": "content/public/common/content_switches.cc",
  "line": 1,
  "attrs": {
    "var": "kEnableFoo"
  }
}
```

Identity là chuỗi command-line mà bên ngoài dùng, không phải tên biến C++.

**Thuộc tính được so sánh:** `var`, `platform_state`.

Trường `conditions` thô có thể được giữ lại để giải thích, nhưng chỉ **kết luận cuối cùng về platform** mới được đem so. Nếu so cả chuỗi điều kiện thô, mỗi lần Chromium dọn một guard vốn chưa bao giờ loại Windows, báo cáo sẽ hiện ra một thay đổi không có thật.

## 12. `pref`

### Đầu vào

Đường dẫn: `chrome/common/pref_names.cc`

```cpp
const char kDownloadPrompt[] = "download.prompt_for_download";
```

### `Fact` sinh ra

```json
{
  "kind": "pref",
  "key": "download.prompt_for_download",
  "name": "download.prompt_for_download",
  "path": "chrome/common/pref_names.cc",
  "line": 1,
  "attrs": {
    "var": "kDownloadPrompt"
  }
}
```

Identity là khoá thật được lưu trong profile người dùng. Từ đó suy ra hai trường hợp đối xứng:

- biến vẫn là `kDownloadPrompt` nhưng chuỗi đổi → bộ phát hiện đổi tên ghép hai `Fact` lại thành `pref_renamed`;
- chuỗi giữ nguyên nhưng biến đổi → đó là `pref_symbol_renamed`.

## 13. `flag_entry`

### Đầu vào

Đường dẫn: `chrome/browser/flag-metadata.json`

```json
[
  {
    "name": "enable-foo",
    "owners": ["team@example.com"],
    "expiry_milestone": 154
  }
]
```

### `Fact` sinh ra

```json
{
  "kind": "flag_entry",
  "key": "enable-foo",
  "name": "enable-foo",
  "path": "chrome/browser/flag-metadata.json",
  "line": 2,
  "attrs": {
    "expiry_milestone": 154,
    "owners": ["team@example.com"]
  }
}
```

Chỉ `expiry_milestone` được đem so sánh ngữ nghĩa. `owners` là thông tin liên hệ phía upstream; danh sách owner đổi không làm hành vi browser đổi, nên nó không tạo ra finding nào.

## 14. `webui_route`

### Đầu vào

Đường dẫn: `chrome/browser/resources/settings/route.ts`

```ts
if (loadTimeData.getBoolean('enableLocalNetworkAccessSetting')) {
  r.LOCAL_NETWORK = r.SITE_SETTINGS.createChild('localNetwork');
}
```

### `Fact` sinh ra

```json
{
  "kind": "webui_route",
  "key": "settings/LOCAL_NETWORK",
  "name": "LOCAL_NETWORK",
  "path": "chrome/browser/resources/settings/route.ts",
  "line": 2,
  "attrs": {
    "surface": "settings",
    "route": "localNetwork",
    "parent": "SITE_SETTINGS",
    "route_kind": "child",
    "guards": ["enableLocalNetworkAccessSetting"]
  }
}
```

Khoá gồm surface cộng tên hằng của route.

**Thuộc tính được so sánh:** `route`, `parent`, `guards`. Trường `route_kind` được giữ để giải thích, nhưng hiện chưa nằm trong danh sách so sánh.

## 15. `webui_control`

### Đầu vào

Đường dẫn: `chrome/browser/resources/settings/downloads_page/downloads_page.html`

```html
<settings-toggle-button
    id="promptForDownload"
    pref="{{prefs.download.prompt_for_download}}"
    label="$i18n{promptForDownload}">
</settings-toggle-button>
```

### `Fact` sinh ra

```json
{
  "kind": "webui_control",
  "key": "settings/downloads_page/downloads_page/pref:download.prompt_for_download#promptForDownload",
  "name": "pref:download.prompt_for_download#promptForDownload",
  "path": "chrome/browser/resources/settings/downloads_page/downloads_page.html",
  "line": 1,
  "attrs": {
    "surface": "settings",
    "page": "downloads_page",
    "file": "downloads_page",
    "control": "settings-toggle-button",
    "pref": "download.prompt_for_download",
    "label": "promptForDownload",
    "element_id": "promptForDownload",
    "build_conditions": []
  }
}
```

### Thứ tự ưu tiên khi chọn identity

Control là loại `Fact` khó đặt identity nhất, vì template thay đổi liên tục. Công cụ thử lần lượt năm phương án, từ ổn định nhất tới kém ổn định nhất:

1. `pref` cộng `element_id`;
2. chỉ `pref`;
3. chỉ `element_id`;
4. khoá nhãn i18n;
5. tag cộng vị trí — chỉ dùng khi bốn cách trên đều không có.

Khoá còn chứa thêm surface, tên trang và phần gốc của tên file. Chi tiết cuối này có một tác dụng cụ thể: khi một file `.html` được migrate sang `.html.ts`, phần gốc tên file vẫn giữ nguyên, nên việc migrate không tự sinh ra nhiễu.

**Thuộc tính được so sánh:** `control`, `pref`, `label`, `build_conditions`, `platform_state`. Các trường `surface`, `page`, `file`, `element_id` chủ yếu phục vụ identity, routing và việc phát hiện control chuyển pref.

## 16. `webui_gate`

### Đầu vào

Đường dẫn: `chrome/browser/ui/webui/settings/settings_ui.cc`

```cpp
html_source->AddBoolean(
    "enableLocalNetworkAccessSetting",
    base::FeatureList::IsEnabled(
        network::features::kLocalNetworkAccessChecks));
```

### `Fact` sinh ra

```json
{
  "kind": "webui_gate",
  "key": "settings_ui/enableLocalNetworkAccessSetting",
  "name": "enableLocalNetworkAccessSetting",
  "path": "chrome/browser/ui/webui/settings/settings_ui.cc",
  "line": 1,
  "attrs": {
    "data_key": "enableLocalNetworkAccessSetting",
    "handler": "settings_ui",
    "value_type": "boolean",
    "expression": "base::FeatureList::IsEnabled(network::features::kLocalNetworkAccessChecks)",
    "features": ["kLocalNetworkAccessChecks"],
    "enabled_checks": ["kLocalNetworkAccessChecks"]
  }
}
```

Khoá gồm handler cộng data key, vì cùng một khoá `loadTimeData` có thể được nhiều handler khác nhau đặt với biểu thức khác nhau. Trường `data_key` vẫn được giữ riêng, để ghép với guard của route.

**Thuộc tính được so sánh:** `expression`, `features`, `enabled_checks`. Trường `value_type` hiện chỉ là ngữ cảnh, không nằm trong danh sách so sánh.

## Bảng tổng hợp: thuộc tính nào được so sánh theo từng `kind`

| Kind | Thuộc tính được so sánh |
|---|---|
| `base_feature` | `default_state`, `platform_state`, `conditions`, `var` |
| `feature_param` | `default`, `type`, `feature`, `var`, `platform_state` |
| `blink_runtime_feature` | Trạng thái và trạng thái theo platform; base feature, dependency, public/internal, cách đấu nối Origin Trial |
| `idl_interface` | `idl_kind`, `inherits`, `ext`, `values` |
| `idl_member` | `signature`, tập overload và traits của chúng, `member_type`, `ext`, `runtime_enabled` |
| `mojo_interface` | `stable`, `platform_state` |
| `mojo_method` | signature/params/response, attrs, ordinal, position (khi có ở cả hai bên), platform state |
| `mojo_struct` | `mojo_kind`, `stable`, `platform_state` |
| `mojo_field` | type, ordinal, default, attrs, position (khi có ở cả hai bên), min version, platform state |
| `mojo_enum` | values, stable, platform state |
| `pref`, `switch` | Biến C++ và platform state |
| `flag_entry` | Milestone hết hạn |
| `webui_route` | Đường dẫn route, route cha, guards |
| `webui_control` | Loại control, pref, nhãn, điều kiện build/platform |
| `webui_gate` | Biểu thức, danh sách feature, các `IsEnabled` check |

Danh sách cho phép này tồn tại vì hai mục đích:

- tránh nhiễu từ những trường chỉ để trình bày hoặc chỉ ghi lại nguồn gốc;
- buộc mỗi thuộc tính được đem so phải có một signal và một câu chữ giải thích được cho người đọc. Nếu không diễn đạt được hậu quả của nó, thuộc tính đó không nên nằm trong danh sách.

## Loại bản ghi trùng hoạt động thế nào

Một UID hoàn toàn có thể xuất hiện nhiều lần trong cùng một lần chạy: header và implementation cùng khai báo, IDL có khối partial, một member có nhiều overload, hoặc cùng một chuỗi xuất hiện trong file riêng của từng platform.

Yêu cầu bắt buộc: kết quả **không được** phụ thuộc vào thứ tự mà `os.walk` trả về file.

Rule tổng quát là chọn `Fact` có `(path, line)` nhỏ nhất. Nhưng trước khi chọn, một số logic đặc thù có thể tổng hợp thêm:

- gộp các signature và vị trí của overload trong IDL;
- gộp trạng thái platform, nếu UID chỉ tồn tại trong thư mục của một platform khác;
- ưu tiên khai báo nằm ngoài cây source của platform khác, khi cùng một UID cũng xuất hiện ở file dùng chung.

Vì sao tính cố định này quan trọng đến vậy: cùng một cây source chạy hai lần phải cho ra snapshot y hệt nhau. Nếu không, công cụ có thể đem một version đi so với **chính nó** mà vẫn sinh ra thay đổi — và lúc đó không còn cách nào phân biệt lỗi công cụ với thay đổi thật.

## Những gì `Fact` cố tình không chứa

`Fact` không cố gắng chứa:

- toàn bộ nội dung source;
- logic implementation của feature, method hay control;
- nơi Samsung đang dùng, hay chỗ gọi trong code Samsung;
- ước lượng công sức;
- kết luận kiểu "Samsung chắc chắn bị ảnh hưởng";
- nội dung giao diện sau khi render;
- lời giải thích do AI sinh ra.

Cách hình dung đúng: `Fact` là **lớp bằng chứng**. `Change` và `signal` trả lời câu hỏi *upstream đã đổi gì*. Còn việc đối chiếu với source và cấu hình của Samsung để biến nó thành một đầu việc là trách nhiệm của skill, của agent và của owner — không phải của lớp dữ liệu này.
