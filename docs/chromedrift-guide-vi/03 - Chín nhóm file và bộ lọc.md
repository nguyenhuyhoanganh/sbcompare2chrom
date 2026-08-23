# 3. Vì sao có 9 nhóm file và bộ lọc hoạt động ra sao

## “9 loại file” là cách gọi chưa hoàn toàn chính xác

ChromeDrift có **9 extractor**, tức 9 bộ đọc cho 9 source of truth. Một extractor có thể đọc nhiều filename và tạo nhiều loại Fact. Ngược lại, một file C++ có thể được hơn một extractor đọc.

Ví dụ:

- `base_features` tạo cả `base_feature` và `feature_param`;
- `mojom` tạo 5 loại Fact: interface, method, struct/union, field và enum;
- `constants` đọc cùng `.cc/.h` nhưng tạo `pref` hoặc `switch` theo filename;
- `.cc` có thể khớp cả `base_features` lẫn `constants` nếu basename cho thấy file chứa cả feature và switch.

Vì vậy nên trình bày là:

> Tool theo dõi 9 nhóm declaration source, qua đó tạo 16 loại Fact.

## Năm lớp lọc từ cây Chromium đến Fact

```text
Toàn bộ file trong Chromium tag
        │
        ▼
1. Product scope
   bỏ test/generated/vendored/binary khác/platform không build
        │
        ▼
2. Target scope
   default / minimal / wide / partition / complete
        │
        ▼
3. Archive include filter
   khi tải một tree, chỉ giữ basename khớp suffix
        │
        ▼
4. Extractor applies_to(path)
   kiểm tra path/dialect chính xác hơn suffix
        │
        ▼
5. Parser grammar
   chỉ declaration đúng syntax tool hiểu mới tạo Fact
```

Mỗi lớp trả lời một câu khác nhau:

- Product scope: file có thuộc browser product trên Windows không?
- Target scope: lần chạy này có cam kết đọc vùng đó không?
- Include filter: file có đáng materialize từ archive lớn không?
- `applies_to`: extractor này có hiểu đúng dialect/path không?
- Parser grammar: nội dung có declaration cụ thể cần theo dõi không?

File vượt qua suffix filter chưa chắc tạo Fact. Ví dụ một `features.cc` không có `BASE_FEATURE` hợp lệ vẫn được đọc nhưng tạo 0 Fact. Coverage đo file đã đọc, còn extract stats đo declaration thực tế trích xuất được.

## Bộ lọc filename dùng khi tải archive

`READABLE_SUFFIXES` hiện chứa các spelling sau:

```text
features.cc       features.h
switches.cc       switches.h
feature_list.cc   feature_list.h
field_trial.cc    field_trial.h
fieldtrial.cc     fieldtrial.h
flags.cc          flags.h
_handler.cc       _util.cc       _manager.cc
pref_names.cc     pref_names.h
prefs.cc          prefs.h
.mojom            .idl           .json5
route.ts          routes.ts
.html             .html.ts
flag-metadata.json
```

Đây là suffix match trên basename, không phải 27 loại semantic khác nhau. Suffix `features.cc` khớp cả `features.cc`, `chrome_features.cc` và `download_features.cc`.

Filter này cố tình rộng hơn `applies_to()` của một extractor. Bước tải archive chỉ loại file chắc chắn không extractor nào dùng; quyết định dialect chính xác nằm ở registry phía sau.

## Tổng quan 9 extractor

| Extractor | File/path chính | Fact tạo ra | Câu hỏi uprev nó trả lời |
|---|---|---|---|
| `base_features` | C++ feature files | `base_feature`, `feature_param` | Feature/param nào đổi default, C++ symbol hoặc build gate? |
| `blink_runtime` | `runtime_enabled_features.json5` | `blink_runtime_feature` | Web Platform feature nào stable/experimental/test trên Windows và wiring nào đổi? |
| `web_idl` | Blink `.idl` | `idl_interface`, `idl_member` | Website nhìn thấy API shape nào được thêm, bỏ hoặc đổi signature/exposure? |
| `mojom` | `.mojom` | 5 Mojo kinds | IPC method/data contract nào đổi qua process boundary? |
| `constants` | switch/pref `.cc/.h` | `switch`, `pref` | Launch argument hoặc profile key nào đổi? |
| `flags_metadata` | `flag-metadata.json` | `flag_entry` | Flag nào sắp hết hạn hoặc lịch xoá thay đổi? |
| `webui_routes` | `route.ts`, `routes.ts` | `webui_route` | Page/subpage `chrome://` nào thêm, bỏ, move hoặc đổi guard? |
| `webui_controls` | `.html`, `.html.ts` | `webui_control` | Control nào đổi type, pref binding, label hoặc build condition? |
| `webui_gates` | WebUI C++ `.cc` | `webui_gate` | `loadTimeData` key nào nối page với feature/config nào? |

## 1. `base_features`: C++ feature flag và FeatureParam

### File nào được đọc

Path phải kết thúc bằng `.cc` hoặc `.h`; basename chứa một trong các shape:

```text
features       switches       feature_list
field_trial    fieldtrial     flags
_util          _handler       _manager
```

Các basename chứa `_unittest.`, `_browsertest.`, `_test.`, `_testing.`, `test_util.`, `_test_util.` hoặc `_test_helper.` bị bỏ.

Không chỉ đọc `*_features.cc`. Chromium đặt real feature trong `*_fieldtrial.cc`, `*_util.cc`, `*_handler.cc` và nhiều convention khác. Chỉ bám một suffix hẹp từng bỏ phần lớn feature trong `chrome/browser/ui/webui`.

### Declaration nào tạo Fact

- `BASE_FEATURE(...)` dạng 2 hoặc 3 argument;
- legacy `const base::Feature kFoo{...}`;
- `base::FeatureParam<T> kParam{...}`;
- `BASE_FEATURE_PARAM(...)`.

### Vì sao cần theo dõi

- Feature default flip là tín hiệu trực tiếp rằng Windows build đổi hành vi.
- C++ symbol đổi tên báo trước build break ở Samsung code.
- Feature string đổi tên làm Finch/`--enable-features` cũ mất tác dụng mà build vẫn qua.
- Param default đổi có thể làm timeout/threshold/mode khác dù feature vẫn giữ state.
- Build guard đổi có thể đưa feature vào hoặc ra khỏi Windows binary.

```cpp
BASE_FEATURE(kBackForwardCache,
             "BackForwardCache",
             base::FEATURE_ENABLED_BY_DEFAULT);
```

Tool bỏ qua whitespace và sự khác nhau giữa macro form. Nó theo dõi `BackForwardCache`, `kBackForwardCache`, default state và Windows platform state. Nó không đọc mọi logic `IsEnabled()` trong implementation và không chứng minh Samsung đang dùng feature.

## 2. `blink_runtime`: trạng thái runtime feature của Blink

### File nào được đọc

Basename phải chính xác là `runtime_enabled_features.json5`.

### Declaration nào tạo Fact

Mỗi entry trong `data` có `name` tạo một `blink_runtime_feature` Fact. Status được chuẩn hoá cho Windows và default.

### Vì sao cần theo dõi

Web IDL nói API code tồn tại; runtime manifest nói API có được expose hay không. Một API chuyển `experimental → stable` mới là tín hiệu page thật có thể bắt đầu dùng rộng rãi. Stable bị rút lại có thể làm site break.

Manifest còn cho biết base feature đứng sau runtime flag, dependency/implied feature, public/internal access, Origin Trial wiring và browser process có quyền read/write hay không.

```json5
{
  name: "LocalNetworkAccess",
  status: { "Win": "stable", "default": "experimental" },
  base_feature: "LocalNetworkAccessChecks"
}
```

Trên Windows, feature này được xem là `stable`; không dùng giá trị global để suy diễn ngược. Manifest nói gate/status, còn shape method/attribute JavaScript đến từ Web IDL.

## 3. `web_idl`: Web API mà website gọi được

### File nào được đọc

Hai điều kiện đồng thời:

```text
path kết thúc bằng .idl
path bắt đầu bằng third_party/blink/renderer/
```

`.idl` còn được dùng cho Chrome Extensions IDL và Windows MIDL; parse chúng như Web IDL sẽ tạo finding “site-visible API changed” sai.

### Declaration nào tạo Fact

- interface, callback interface, interface mixin;
- dictionary, namespace, enum;
- operation, attribute, field, constructor, const, iterable/maplike/setlike;
- extended attributes như `[RuntimeEnabled=Foo]`, `[Exposed=Window]`.

Partial interface không tạo interface Fact mới nhưng member của partial vẫn được gắn vào interface gốc.

### Vì sao cần theo dõi

- Removed interface/member: live website có thể không còn chạy.
- Signature đổi: call site cũ có thể không match.
- Overload thêm có thể đổi resolution nếu trùng arity.
- `Exposed`/`RuntimeEnabled` đổi: API vẫn còn nhưng context hoặc gate truy cập thay đổi.
- Inheritance/enum values đổi: shape JavaScript quan sát được thay đổi.

```webidl
[Exposed=Window]
interface Example {
  [RuntimeEnabled=Foo] Promise<DOMString> connect(DOMString host);
};
```

Tool tạo một Fact cho `Example` và một Fact cho `Example.connect`, rồi nối `RuntimeEnabled=Foo` với runtime feature status để biết member đang live hay gated. Parser là pragmatic lexer cho dialect Blink thường dùng, không phải Web IDL parser hoàn chỉnh.

## 4. `mojom`: IPC contract giữa các process

### File nào được đọc

Mọi path kết thúc `.mojom` trong product scope của target set.

### Declaration nào tạo Fact

- `interface` và request/response method;
- `struct` và `union`;
- field;
- enum cùng danh sách values.

Module, qualified name, ordinal, type, response, `[Stable]`, `[MinVersion]` và `[EnableIf...]` được giữ khi có ý nghĩa.

### Vì sao cần theo dõi

Samsung code có thể implement hoặc call một Mojo interface khác phía với upstream code. Method đổi parameter/response, ordinal đổi, field đổi type, struct thành union, enum có value mới hoặc stable declaration bị reorder đều có thể tạo IPC incompatibility. Custom boundary có thể chỉ lộ lỗi khi chạy.

```mojom
module network.mojom;

[Stable] interface Probe {
  Start@0(string url) => (bool accepted);
};
```

Identity method là `network.mojom.Probe.Start`; signature và ordinal là attribute so sánh. Tool chưa tìm mọi call site/implementation trong Samsung code; nó chỉ chỉ ra contract upstream đã đổi.

## 5. `constants`: pref key và command-line switch

### File nào được đọc

Path phải là `.cc` hoặc `.h`. Basename có `switches.` hoặc khớp một pref convention: `pref_names.`, `pref_names_`, `_pref_names.`, `_prefs.` hay `prefs.`.

Hai syntax string constant được hỗ trợ:

```cpp
const char kFoo[] = "foo";
inline constexpr std::string_view kFoo = "foo";
```

Nếu basename khớp pref convention, Fact kind là `pref`; còn lại là `switch`. Identity là string value, không phải C++ variable.

### Vì sao cần theo dõi

- Pref string đổi: profile cũ vẫn giữ key cũ, setting có thể reset về default.
- Pref C++ symbol đổi nhưng string giữ: stored value an toàn, Samsung build có thể fail.
- Switch string đổi: launch script/automation cũ im lặng không còn hiệu lực.
- Switch C++ symbol đổi: code compile fail nhưng external script vẫn an toàn.
- Platform guard đổi: key có thể ra/vào Windows build.

```cpp
const char kPromptForDownload[] = "download.prompt_for_download";
```

Fact được key bằng `download.prompt_for_download`. Nhờ vậy đổi C++ symbol là modified; đổi string được rename detector ghép bằng symbol ổn định. Chỉ filename convention đã được kiểm chứng được đọc để tránh biến string thường thành external contract.

## 6. `flags_metadata`: lịch vòng đời `chrome://flags`

### File nào được đọc

Basename chính xác là `flag-metadata.json`.

Mỗi object có `name` tạo một `flag_entry`; tool giữ `expiry_milestone` và `owners`.

### Vì sao cần theo dõi

Đây là source nói trực tiếp về tương lai. Nếu flag Samsung đang override sẽ hết hạn trong target milestone hoặc hai milestone tiếp theo, team có thể tạo backlog trước khi upstream xoá declaration/wiring.

```json
{
  "name": "enable-foo",
  "owners": ["team@example.com"],
  "expiry_milestone": 154
}
```

`owners` trong Fact là upstream contact của metadata, khác với owner routing trong report. File này không chứng minh Samsung có dùng flag.

## 7. `webui_routes`: inventory page/subpage

### File nào được đọc

Path bắt đầu bằng `chrome/browser/resources/` và basename là `route.ts` hoặc `routes.ts`.

### Declaration nào tạo Fact

Các assignment theo pattern:

```ts
r.NAME = r.PARENT.createChild('path');
r.NAME = r.PARENT.createSection('path', 'section');
```

Extractor theo dõi stack của `if (loadTimeData.getBoolean('key'))` bao quanh route.

### Vì sao cần theo dõi

Một page bị xoá khỏi route table có thể thật sự biến mất, đổi URL/parent, được thay bằng page mới hoặc vốn đã hidden vì guard. Không giữ guard sẽ làm report kết luận sai thời điểm user-visible change.

```ts
if (loadTimeData.getBoolean('enableFooSetting')) {
  r.FOO = r.PRIVACY.createChild('foo');
}
```

Fact giữ route `foo`, parent `PRIVACY` và guard `enableFooSetting`. Navigation dựng hoàn toàn động bằng syntax khác chưa nằm trong coverage của extractor.

## 8. `webui_controls`: control trong Polymer/Lit template

### File nào được đọc

Path dưới `chrome/browser/resources/` và kết thúc `.html` hoặc `.html.ts`.

### Control được nhận ra bằng rule nào

Mọi custom element có dấu `-` được xét. Nó thành control nếu thỏa ít nhất một:

1. Có pref binding.
2. Là structural tag đã biết như `settings-subpage`, `settings-section`, `downloads-item`.
3. Tag có segment tương tác như `button`, `toggle`, `checkbox`, `radio`, `input`, `select`, `slider`, `menu`, `row`… và có identity ổn định bằng `id` hoặc label.

Rule dựa trên shape thay danh sách tag đóng dễ cũ. Element không pref, không id và không label thường bị bỏ vì chỉ nhận diện được bằng vị trí, rất dễ churn khi template reorder.

Pref binding được hiểu ở cả Polymer và Lit:

```html
pref="{{prefs.download.prompt_for_download}}"
pref="[[prefs.download.prompt_for_download]]"
.pref="${this.prefs.download.prompt_for_download}"
pref-key="download.prompt_for_download"
```

Prefix `prefs.` là bắt buộc để không nhầm component property thường thành pref.

### Vì sao cần theo dõi

- Toggle thành dropdown là interaction/semantics change.
- Control chuyển pref làm giá trị cũ bị bỏ lại và pref mới bắt đầu từ default.
- Control bị remove/add cho biết Settings surface đổi.
- GRIT condition đổi cho biết control ra/vào Windows build.

```html
<settings-toggle-button
    id="promptForDownload"
    pref="{{prefs.download.prompt_for_download}}"
    label="$i18n{promptForDownload}">
</settings-toggle-button>
```

Tool không render UI, không đọc CSS/layout, không kiểm tra event handler và không đọc display string trong `.grd`. Label Fact là i18n key.

## 9. `webui_gates`: cầu nối từ WebUI sang C++ feature/config

### File nào được đọc

Path bắt đầu bằng `chrome/browser/ui/webui/` và kết thúc `.cc`.

### Declaration nào tạo Fact

Các call dạng `AddBoolean`, `AddInteger`, `AddString` hoặc `AddDouble` với argument đầu là literal key. Tool giữ expression đã chuẩn hoá, danh sách `features::k...` được tham chiếu và feature nằm trong `IsEnabled()`.

```cpp
html_source->AddBoolean(
    "enableFooSetting",
    base::FeatureList::IsEnabled(features::kFoo));
```

### Vì sao cần theo dõi

Route/template chỉ biết `loadTimeData` key. Gate Fact tạo hop tới feature phía C++:

```text
route guard: enableFooSetting
        ↓ join bằng data_key
WebUI gate: IsEnabled(features::kFoo)
        ↓ join bằng feature symbol/name
base_feature: default + Windows state
```

Nhờ chain này, agent có thể phân biệt “page bị xoá nhưng đã hidden từ trước” với “page đang visible rồi mất trong lần uprev”. Gate dựa hoàn toàn vào policy/profile vẫn tạo Fact nhưng không join tới `base_feature`.

## Vì sao đúng 9 nhóm này

Chín nhóm phủ ba loại rủi ro khó thấy qua compile/test thông thường:

1. **Behaviour switches**: feature/default/runtime status đổi làm browser hành xử khác.
2. **External contracts**: pref, switch, Web API và Mojo đổi làm dữ liệu/script/site/process khác không còn tương thích.
3. **UI and scheduling**: page/control/gate đổi hoặc flag sắp bị xoá.

Mỗi nhóm có source of truth đủ ổn định để tạo semantic key. Implementation `.cc/.ts` vẫn quan trọng nhưng raw diff của nó có nhiều refactor noise và thường không có identity ổn định.

Muốn thêm nhóm thứ mười, cần trả lời được:

- Source of truth nào chứa declaration?
- Key nào ổn định giữa version dù syntax/refactor đổi?
- Attribute nào thật sự thay đổi hành vi hoặc contract?
- Grammar gap và coverage có đo được không?
- Finding tạo ra dẫn tới hành động review nào?

## Cách kiểm tra bộ lọc có đáng tin không

1. Unit test `applies_to()` với path đúng, path gần giống nhưng sai dialect, test file và platform path.
2. Unit test input source → Fact cho mọi syntax hỗ trợ.
3. Catalog/coverage trên version thật để tìm filename convention bị bỏ sót.
4. Diff hai version thật để tìm false positive do refactor, move, overload hoặc platform guard.

Coverage 100% chỉ nói đã đọc mọi file mà rule hiện tại gọi là candidate. Nó không chứng minh parser hiểu 100% grammar trong file, và cũng không chứng minh rule không quên convention mới. Catalog audit và parser tests vẫn cần tồn tại song song.
