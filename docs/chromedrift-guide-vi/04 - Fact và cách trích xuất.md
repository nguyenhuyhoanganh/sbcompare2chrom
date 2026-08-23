# 4. Fact là gì và từng extractor tạo Fact như thế nào

## Fact là một declaration đã được chuẩn hoá

Một source file có thể dài hàng nghìn dòng và thay đổi nhiều vì format/refactor. ChromeDrift không đem nguyên file đi so. Nó lấy từng declaration có ý nghĩa, chuyển thành object nhỏ gọi là `Fact`, rồi ghép cùng Fact giữa hai version.

Schema chung:

```json
{
  "kind": "loại declaration",
  "key": "identity ổn định trong kind",
  "name": "tên để hiển thị",
  "path": "relative path từ Chromium src/",
  "line": 123,
  "attrs": {
    "thuộc tính": "giá trị đã chuẩn hoá"
  }
}
```

UID dùng khi so sánh là:

```text
uid = kind + ":" + key
```

Ví dụ:

```text
base_feature:BackForwardCache
idl_member:Example.connect
mojo_method:network.mojom.Probe.Start
pref:download.prompt_for_download
webui_route:settings/LOCAL_NETWORK
```

## Vai trò của từng field

| Field | Dùng để làm gì | Có phải luôn được so sánh không? |
|---|---|---|
| `kind` | Chọn semantics, bảng attribute, signal, owner | Là một phần UID |
| `key` | Ghép cùng declaration giữa hai version | Là phần chính của UID |
| `name` | Hiển thị cho người đọc | Không |
| `path` | Dẫn tới bằng chứng và phát hiện declaration move | Path khác nhau tạo delta `path` |
| `line` | Mở đúng dòng trong source | Không tạo change nếu chỉ line đổi |
| `attrs` | Giữ state, type, signature, gate, wiring… | Chỉ whitelist theo từng kind được so |

`path` và `line` không nằm trong `attrs` vì chúng là provenance. Một declaration dịch xuống 20 dòng do comment thêm không phải behaviour change. Declaration chuyển file được giữ như `declaration_moved` để người tích hợp tìm lại include/patch, nhưng có severity thấp.

## “Chuẩn hoá” cụ thể là làm gì

Chuẩn hoá không phải dịch text hay để AI tóm tắt. Đó là các rule deterministic:

1. Chọn identity theo nghĩa, không theo syntax.
2. Collapse whitespace trong signature/expression nhưng không sửa string literal.
3. Chuyển platform condition thành verdict dành cho Windows.
4. Tách qualified name để tránh collision.
5. Giữ cùng schema cho nhiều declaration form cũ/mới.
6. Bỏ attribute chỉ phản ánh cách viết mà không đổi hành vi.

Ví dụ Chromium từng viết cùng feature theo các dạng:

```cpp
BASE_FEATURE(kFoo, "Foo", base::FEATURE_ENABLED_BY_DEFAULT);
BASE_FEATURE(kFoo, base::FEATURE_ENABLED_BY_DEFAULT);
const base::Feature kFoo{"Foo", base::FEATURE_ENABLED_BY_DEFAULT};
```

Cả ba đều được chuẩn hoá về key `Foo`, symbol `kFoo`, state `enabled`. `declared_form` được giữ để debug nhưng không nằm trong whitelist so sánh; migrate macro không tạo hàng loạt finding giả.

## Từ hai Fact đến một Change

```text
Snapshot cũ index theo uid       Snapshot mới index theo uid
             │                              │
             └──────────────┬───────────────┘
                            ▼
                  cùng uid ở hai bên?
                    │       │       │
                    │       │       └─ chỉ cũ  → removed
                    │       └───────── chỉ mới → added
                    └───────────────── cả hai  → so meaningful attrs
                                                  │
                                                  └─ khác → modified + deltas
```

Sau pass cơ bản còn hai bước ghép đặc biệt:

- pref/switch/feature string rename: ghép removed + added nếu C++ variable giữ nguyên;
- WebUI control repoint: ghép removed + added nếu surface/page/element id giữ nguyên nhưng pref trong key thay đổi.

## 16 loại Fact và nguồn tạo ra

| Extractor | Fact kinds |
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

Các ví dụ sau là output thực của extractor hiện tại trên input tối giản.

## 1. `base_feature`

### Input

Path: `content/common/features.cc`

```cpp
BASE_FEATURE(kBackForwardCache,
             "BackForwardCache",
             base::FEATURE_ENABLED_BY_DEFAULT);
```

### Fact

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

### Tiêu chí trích xuất và ý nghĩa field

- Macro đầu tiên phải là C++ variable dạng `k...`.
- `key` ưu tiên feature string ở macro 3 argument; macro 2 argument suy ra bằng cách bỏ `k` khỏi variable.
- `default_state`: `enabled`, `disabled` hoặc `unknown`.
- `platform_state.windows`: resolve cả condition nằm trong macro và `#if` bao ngoài.
- `conditions`: giữ raw guard chain để người đọc truy nguyên.
- `var`: cần phát hiện Samsung code dùng symbol cũ.
- `declared_form`: để giải thích parser, không được so semantic.

Meaningful attrs: `default_state`, `platform_state`, `conditions`, `var`.

## 2. `feature_param`

### Input

```cpp
BASE_FEATURE_PARAM(int,
                   kTimeToLiveSeconds,
                   &kBackForwardCache,
                   "time_to_live_seconds",
                   1800);
```

### Fact

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

### Tiêu chí và identity

`key` là `feature/name`. Nếu declaration không có string name, param name được suy từ variable để default đổi không làm identity đổi theo. Đây là chi tiết quan trọng: nếu nhầm `1800` là param name, đổi `1800 → 3600` sẽ bị báo thành remove + add thay vì `param_default_changed`.

Meaningful attrs: `default`, `type`, `feature`, `var`, `platform_state`.

## 3. `blink_runtime_feature`

### Input

Path: `third_party/blink/renderer/platform/runtime_enabled_features.json5`

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

### Fact

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

### Tiêu chí và attrs

Mọi entry object có `name` đều tạo Fact. Nếu `status` là string, giá trị áp dụng cho Windows và default. Nếu là object, `Win` được map thành `windows`; khi object không có `default`, platform không được liệt kê mang status rỗng, không tự hiểu là stable.

Ngoài các field trên, extractor giữ mọi wiring quan trọng đang có trong manifest: `base_feature_status`, `origin_trial_feature_name`, `depends_on`, `implied_by`, `copied_from_base_feature_if`, `settable_from_internals`, third-party/browser-process access, trial OS/type/insecure và protected state.

Các field này được so vì chúng quyết định feature được bật bởi cái gì và ai có thể tiếp cận nó.

## 4. `idl_interface`

### Input

Path: `third_party/blink/renderer/modules/example/example.idl`

```webidl
[Exposed=Window, RuntimeEnabled=LocalNetworkAccess]
interface Example : EventTarget {
  Promise<DOMString> connect(DOMString host);
};
```

### Fact

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

### Tiêu chí và attrs

Identity là interface name. `partial interface Example` không tạo Fact interface thứ hai vì identity thuộc base definition; member bên trong partial vẫn tạo `idl_member` với `from_partial=true`.

Với enum, attrs có thêm `values`. Meaningful attrs là `idl_kind`, `inherits`, `ext`, `values`; `partial` là provenance của cách declaration được ghép và không dùng để tạo semantic diff cho interface gốc.

## 5. `idl_member`

### Input

```webidl
interface Example {
  [RuntimeEnabled=LocalNetworkAccess]
  Promise<DOMString> connect(DOMString host);
};
```

### Fact

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

### Tiêu chí và overload

Key là `Interface.member`. Member parser nhận operation, attribute, dictionary field, const, constructor và declarative members. Whitespace quanh `(`, `<`, `>`, `,` được chuẩn hoá nhưng nội dung string literal được giữ nguyên.

Nếu một UID có nhiều overload, dedupe tổng hợp `signatures`, `overload_traits` và `overload_locations`. Nhờ vậy thêm/bỏ overload không bị mất vì dictionary index chỉ giữ một UID.

Meaningful attrs: `signature`, `signatures`, `overload_traits`, `member_type`, `ext`, `runtime_enabled`.

## 6. `mojo_method`

### Input

Path: `services/network/public/mojom/example.mojom`

```mojom
module network.mojom;
[Stable] interface Probe {
  Start@0(string url) => (bool accepted);
};
```

### Fact

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

### Tiêu chí và attrs

Qualified interface name ngăn hai module có `Probe.Start` collision. `ordinal` chỉ có khi source khai báo. `position` chỉ được ghi bên trong `[Stable]`, vì reorder ở unstable interface là việc bình thường khi hai đầu luôn rebuild cùng nhau; trong stable interface, lexical position là wire promise.

Meaningful attrs: `signature`, `params`, `response`, method `attrs`, `ordinal`, paired `position`, `platform_state`.

## 7. `mojo_interface`

Cùng input trên tạo thêm:

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

`methods` và `method_count` giúp giải thích Fact nhưng không được so. Mỗi method đã có Fact riêng; so list ở interface sẽ báo một thay đổi hai lần, một dòng mơ hồ và một dòng chính xác. Meaningful attrs của interface chỉ là `stable` và `platform_state`.

## 8. `mojo_struct` và union

### Input

```mojom
[Stable] struct Result {
  int32 code@0;
  [MinVersion=1] string? detail@1;
};
```

### Fact container

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

`mojo_kind` phân biệt `struct` và `union` dưới cùng qualified name. `fields` không được so vì mỗi field có Fact riêng. Meaningful attrs: `mojo_kind`, `stable`, `platform_state`.

## 9. `mojo_field`

Cùng input tạo hai Fact; đây là Fact có version annotation:

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

Meaningful attrs: `type`, `ordinal`, `default`, field `attrs`, paired `position`, `min_version`, `platform_state`. Type/ordinal/position trong stable container có thể đổi wire shape; default/MinVersion đổi điều older peer nhìn thấy nhưng không đổi cách đọc byte.

## 10. `mojo_enum`

### Input

```mojom
enum State {
  kIdle = 0,
  kRunning = 1,
};
```

### Fact

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

Enum member không thành Fact riêng. Một enum Fact giữ ordered value list vì Mojo enum thường xuyên được mở rộng; hàng chục nghìn member Fact sẽ làm report chìm trong noise mà không thêm thông tin hơn delta của list.

Meaningful attrs: `values`, `stable`, `platform_state`.

## 11. `switch`

### Input

Path: `content/public/common/content_switches.cc`

```cpp
const char kEnableFoo[] = "enable-foo";
```

### Fact

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

Identity là external command-line string. Meaningful attrs: `var`, `platform_state`. Raw `conditions` có thể được giữ để giải thích nhưng chỉ resolved platform verdict được so, tránh báo thay đổi khi Chromium dọn một guard không bao giờ loại Windows.

## 12. `pref`

### Input

Path: `chrome/common/pref_names.cc`

```cpp
const char kDownloadPrompt[] = "download.prompt_for_download";
```

### Fact

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

Identity là key thực được lưu trong profile. Nếu variable giữ `kDownloadPrompt` nhưng string đổi, rename detector ghép hai Fact thành `pref_renamed`. Nếu string giữ mà variable đổi, đó là `pref_symbol_renamed`.

## 13. `flag_entry`

### Input

Path: `chrome/browser/flag-metadata.json`

```json
[
  {
    "name": "enable-foo",
    "owners": ["team@example.com"],
    "expiry_milestone": 154
  }
]
```

### Fact

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

Chỉ `expiry_milestone` được semantic diff. `owners` là context/contact upstream; owner list đổi không làm browser behavior đổi nên không tạo finding.

## 14. `webui_route`

### Input

Path: `chrome/browser/resources/settings/route.ts`

```ts
if (loadTimeData.getBoolean('enableLocalNetworkAccessSetting')) {
  r.LOCAL_NETWORK = r.SITE_SETTINGS.createChild('localNetwork');
}
```

### Fact

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

Key gồm surface + route constant name. Meaningful attrs: `route`, `parent`, `guards`. `route_kind` được giữ để giải thích nhưng hiện không nằm trong comparison whitelist.

## 15. `webui_control`

### Input

Path: `chrome/browser/resources/settings/downloads_page/downloads_page.html`

```html
<settings-toggle-button
    id="promptForDownload"
    pref="{{prefs.download.prompt_for_download}}"
    label="$i18n{promptForDownload}">
</settings-toggle-button>
```

### Fact

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

### Identity ưu tiên

Identity được chọn theo độ ổn định:

1. `pref + element_id`;
2. chỉ pref;
3. element id;
4. i18n label key;
5. tag + position, chỉ là phương án cuối.

Key còn có surface, page và file stem. `.html` migrate sang `.html.ts` vẫn giữ cùng file stem nên không tự tạo churn.

Meaningful attrs: `control`, `pref`, `label`, `build_conditions`, `platform_state`. `surface/page/file/element_id` chủ yếu phục vụ identity, routing và repoint detection.

## 16. `webui_gate`

### Input

Path: `chrome/browser/ui/webui/settings/settings_ui.cc`

```cpp
html_source->AddBoolean(
    "enableLocalNetworkAccessSetting",
    base::FeatureList::IsEnabled(
        network::features::kLocalNetworkAccessChecks));
```

### Fact

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

Key gồm handler + data key vì cùng `loadTimeData` key có thể được nhiều handler đặt với expression khác nhau. `data_key` riêng vẫn được giữ để join route guard.

Meaningful attrs: `expression`, `features`, `enabled_checks`. `value_type` hiện là context, không nằm trong whitelist.

## Bảng attribute được so theo từng kind

| Kind | Meaningful attrs |
|---|---|
| `base_feature` | `default_state`, `platform_state`, `conditions`, `var` |
| `feature_param` | `default`, `type`, `feature`, `var`, `platform_state` |
| `blink_runtime_feature` | status/platform status, base feature/dependency/public/internal/origin-trial wiring |
| `idl_interface` | `idl_kind`, `inherits`, `ext`, `values` |
| `idl_member` | `signature`, overload sets/traits, `member_type`, `ext`, `runtime_enabled` |
| `mojo_interface` | `stable`, `platform_state` |
| `mojo_method` | signature/params/response, attrs, ordinal, paired position, platform state |
| `mojo_struct` | `mojo_kind`, `stable`, `platform_state` |
| `mojo_field` | type, ordinal, default, attrs, paired position, min version, platform state |
| `mojo_enum` | values, stable, platform state |
| `pref`, `switch` | C++ variable và platform state |
| `flag_entry` | expiry milestone |
| `webui_route` | route path, parent, guards |
| `webui_control` | control type, pref, label, build/platform conditions |
| `webui_gate` | expression, features, enabled checks |

Whitelist có hai mục đích:

- tránh noise từ field chỉ để trình bày/provenance;
- buộc mỗi attribute được so phải có signal/wording giải thích được.

## Dedupe hoạt động thế nào

Một UID có thể xuất hiện nhiều lần: header và implementation cùng declare, partial IDL, overload hoặc cùng string ở platform-specific file. Kết quả không được phụ thuộc thứ tự `os.walk`.

Rule tổng quát chọn Fact có `(path, line)` nhỏ nhất. Trước khi chọn, logic đặc thù có thể tổng hợp:

- IDL overload signatures và location;
- platform state nếu UID chỉ tồn tại trong platform directory khác;
- ưu tiên declaration nằm ngoài other-platform tree khi cùng UID tồn tại ở source dùng chung.

Tính deterministic này quan trọng: cùng một tree chạy hai lần phải cho snapshot giống nhau, nếu không tool có thể diff một version với chính nó mà vẫn sinh change.

## Fact không chứa gì

Fact không cố chứa:

- toàn bộ source body;
- implementation logic của feature/method/control;
- Samsung usage/call site;
- effort estimate;
- kết luận “Samsung chắc chắn bị ảnh hưởng”;
- nội dung visual render;
- AI explanation.

Fact là evidence layer. Change/Signal trả lời upstream đã đổi gì; skill/agent và owner mới đối chiếu Samsung source/config để chuyển thành work item.
