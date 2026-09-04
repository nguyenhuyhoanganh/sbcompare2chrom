# 3. Vì sao có 9 nhóm file và bộ lọc hoạt động ra sao

Tài liệu này trả lời hai câu hỏi: **công cụ đọc những loại file nào**, và **một file phải qua bao nhiêu lớp lọc trước khi thật sự được phân tích**.

## Trước hết, sửa một cách gọi chưa chính xác

Người ta hay nói "ChromiumDiff đọc 9 loại file". Cách gọi đó gây hiểu nhầm.

Chính xác thì ChromiumDiff có **9 extractor** — tức 9 bộ đọc, mỗi bộ phụ trách một nguồn sự thật. Quan hệ giữa extractor và file không phải một-một:

- một extractor có thể đọc nhiều dạng tên file, và tạo ra nhiều loại `Fact`;
- ngược lại, một file C++ có thể được hơn một extractor cùng đọc.

Bốn ví dụ cụ thể:

- `base_features` tạo ra hai loại `Fact`: `base_feature` và `feature_param`;
- `mojom` tạo ra năm loại: interface, method, struct/union, field và enum;
- `constants` đọc cùng một loại file `.cc/.h`, nhưng tạo ra `pref` hay `switch` tuỳ theo tên file;
- một file `.cc` có thể khớp cả `base_features` lẫn `constants`, nếu tên file cho thấy nó chứa cả feature lẫn switch.

Vì vậy cách nói đúng là:

> Công cụ theo dõi 9 nhóm nguồn khai báo, và qua đó tạo ra 16 loại `Fact`.

## Năm lớp lọc, từ cây Chromium xuống tới một `Fact`

Một file phải vượt qua đủ năm lớp mới sinh ra dữ liệu:

```text
Toàn bộ file trong một Chromium tag
        │
        ▼
1. Product scope
   bỏ file test, file do máy sinh, thư viện vendor, binary khác, platform không build
        │
        ▼
2. Target scope
   default / minimal / wide / partition / complete
        │
        ▼
3. Bộ lọc include khi giải nén archive
   khi tải cả một thư mục, chỉ giữ file có tên khớp đuôi đã khai báo
        │
        ▼
4. applies_to(path) của extractor
   kiểm tra đường dẫn và dialect, chặt hơn nhiều so với chỉ nhìn đuôi file
        │
        ▼
5. Grammar của parser
   chỉ khai báo viết đúng cú pháp mà công cụ hiểu mới tạo ra Fact
```

Năm lớp này không trùng nhau, vì mỗi lớp trả lời một câu hỏi khác nhau:

| Lớp | Câu hỏi nó trả lời |
|---|---|
| Product scope | File này có thuộc sản phẩm browser trên Windows không? |
| Target scope | Lần chạy này có cam kết đọc vùng đó không? |
| Include filter | File này có đáng lấy ra từ một archive lớn không? |
| `applies_to` | Extractor này có hiểu đúng dialect và đường dẫn đó không? |
| Grammar | Nội dung có chứa khai báo cụ thể cần theo dõi không? |

Một hệ quả cần nhớ: **file vượt qua bộ lọc đuôi chưa chắc tạo ra `Fact`**. Ví dụ, một file `features.cc` không chứa `BASE_FEATURE` hợp lệ nào vẫn được đọc, nhưng tạo ra 0 `Fact`. Đó là lý do báo cáo có hai con số riêng: **coverage** đếm số file đã đọc, còn **extract stats** đếm số khai báo thực sự trích xuất được.

## Bộ lọc tên file dùng khi giải nén archive

Hằng số `READABLE_SUFFIXES` hiện chứa các cách viết sau:

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

Hai điều cần hiểu đúng về danh sách này.

**Thứ nhất, đây là so khớp phần đuôi của tên file, không phải 27 loại ngữ nghĩa khác nhau.** Chuỗi `features.cc` khớp đồng thời với `features.cc`, `chrome_features.cc` và `download_features.cc`.

**Thứ hai, bộ lọc này cố tình rộng hơn `applies_to()` của từng extractor.** Ở bước giải nén, công cụ chỉ loại những file chắc chắn không extractor nào dùng tới. Quyết định chính xác về dialect được để lại cho registry ở lớp sau. Làm chặt quá sớm sẽ khiến một file hợp lệ bị loại mà không ai biết.

## Tổng quan 9 extractor

Bảng này là bản đồ của cả tài liệu. Cột cuối cùng cho biết mỗi extractor tồn tại để trả lời câu hỏi gì trong một đợt uprev.

| Extractor | File / đường dẫn chính | `Fact` tạo ra | Câu hỏi uprev nó trả lời |
|---|---|---|---|
| `base_features` | Các file feature C++ | `base_feature`, `feature_param` | Feature hoặc param nào đổi mặc định, đổi C++ symbol, hoặc đổi điều kiện build? |
| `blink_runtime` | `runtime_enabled_features.json5` | `blink_runtime_feature` | Feature Web Platform nào đang stable/experimental/test trên Windows, và cách đấu nối nào đã đổi? |
| `web_idl` | File `.idl` của Blink | `idl_interface`, `idl_member` | Website nhìn thấy API nào được thêm, bị bỏ, hoặc đổi signature/phạm vi expose? |
| `mojom` | File `.mojom` | 5 loại `Fact` Mojo | Contract IPC nào — method hay dữ liệu — đã đổi khi đi qua ranh giới process? |
| `constants` | File `.cc/.h` chứa switch và pref | `switch`, `pref` | Tham số khởi động hoặc khoá lưu trong profile nào đã đổi? |
| `flags_metadata` | `flag-metadata.json` | `flag_entry` | Flag nào sắp hết hạn, hoặc lịch xoá nào vừa thay đổi? |
| `webui_routes` | `route.ts`, `routes.ts` | `webui_route` | Trang `chrome://` nào được thêm, bị bỏ, đổi vị trí, hoặc đổi điều kiện hiển thị? |
| `webui_controls` | `.html`, `.html.ts` | `webui_control` | Control nào đổi kiểu, đổi pref, đổi nhãn, hoặc đổi điều kiện build? |
| `webui_gates` | File `.cc` của WebUI | `webui_gate` | Khoá `loadTimeData` nào đang nối một trang với feature hoặc cấu hình nào? |

Chín mục dưới đây đi vào chi tiết từng extractor, theo cùng một khuôn: **đọc file nào** → **khai báo nào tạo `Fact`** → **vì sao cần theo dõi** → **ví dụ**.

## 1. `base_features` — feature flag và FeatureParam trong C++

### Đọc file nào

Đường dẫn phải kết thúc bằng `.cc` hoặc `.h`, và tên file phải chứa một trong các dạng sau:

```text
features       switches       feature_list
field_trial    fieldtrial     flags
_util          _handler       _manager
```

Những tên chứa `_unittest.`, `_browsertest.`, `_test.`, `_testing.`, `test_util.`, `_test_util.` hoặc `_test_helper.` bị loại.

Ở đây có một quyết định thiết kế đáng chú ý: **không chỉ đọc `*_features.cc`**. Chromium đặt feature thật trong `*_fieldtrial.cc`, `*_util.cc`, `*_handler.cc` và nhiều quy ước khác. Việc chỉ bám vào một hậu tố hẹp đã từng khiến công cụ bỏ sót phần lớn feature nằm trong `chrome/browser/ui/webui`.

### Khai báo nào tạo `Fact`

- `BASE_FEATURE(...)` ở cả dạng 2 và 3 tham số;
- dạng cũ `const base::Feature kFoo{...}`;
- `base::FeatureParam<T> kParam{...}`;
- `BASE_FEATURE_PARAM(...)`.

### Vì sao cần theo dõi

Năm kiểu hậu quả khác nhau, xếp theo mức độ dễ phát hiện giảm dần:

- **Feature đổi mặc định** là tín hiệu trực tiếp cho biết bản build Windows sẽ hành xử khác.
- **C++ symbol đổi tên** báo trước một lỗi build sẽ xảy ra ở phía Samsung.
- **Feature string đổi tên** làm cấu hình Finch và `--enable-features` cũ mất tác dụng, trong khi build vẫn qua bình thường — đây là kiểu khó phát hiện nhất.
- **Param đổi mặc định** có thể làm timeout, ngưỡng hoặc chế độ khác đi, dù trạng thái feature vẫn giữ nguyên.
- **Điều kiện build đổi** có thể đưa feature vào hoặc ra khỏi binary Windows.

### Ví dụ

```cpp
BASE_FEATURE(kBackForwardCache,
             "BackForwardCache",
             base::FEATURE_ENABLED_BY_DEFAULT);
```

Công cụ bỏ qua khoảng trắng và bỏ qua khác biệt giữa các dạng macro. Nó theo dõi bốn thứ: chuỗi `BackForwardCache`, symbol `kBackForwardCache`, trạng thái mặc định, và trạng thái trên platform Windows.

Nó **không** đọc mọi logic `IsEnabled()` nằm trong phần implementation, và không chứng minh được Samsung có đang dùng feature này hay không.

## 2. `blink_runtime` — trạng thái runtime của feature Blink

### Đọc file nào

Tên file phải chính xác là `runtime_enabled_features.json5`.

### Khai báo nào tạo `Fact`

Mỗi entry trong mảng `data` có trường `name` sẽ tạo ra một `Fact` loại `blink_runtime_feature`. Trạng thái được chuẩn hoá riêng cho Windows và cho giá trị mặc định.

### Vì sao cần theo dõi

Web IDL và runtime manifest trả lời hai câu hỏi khác nhau, và cần cả hai mới đủ:

- **Web IDL** nói: code của API này có tồn tại không.
- **Runtime manifest** nói: API đó có thật sự được expose ra ngoài không.

Vì vậy, chỉ khi một API chuyển từ `experimental` sang `stable` thì mới có tín hiệu rằng các trang web thật có thể bắt đầu dùng nó rộng rãi. Ngược lại, một API bị rút khỏi stable có thể làm site đang chạy bị hỏng.

Manifest còn cho biết thêm bốn thứ: base feature nào đứng sau runtime flag, feature này phụ thuộc hoặc được ngụ ý bởi feature nào, có cho truy cập public hay chỉ internal, cách đấu nối Origin Trial, và browser process có quyền đọc/ghi nó hay không.

### Ví dụ

```json5
{
  name: "LocalNetworkAccess",
  status: { "Win": "stable", "default": "experimental" },
  base_feature: "LocalNetworkAccessChecks"
}
```

Trên Windows, feature này được coi là `stable`. Không được lấy giá trị `default` để suy ngược ra trạng thái Windows — đây chính là loại nhầm lẫn mà việc tách riêng trạng thái theo platform sinh ra để phòng.

Manifest nói về gate và trạng thái; còn hình dạng cụ thể của method và attribute mà JavaScript nhìn thấy thì đến từ Web IDL.

## 3. `web_idl` — Web API mà website gọi được

### Đọc file nào

Phải thoả **đồng thời** hai điều kiện:

```text
đường dẫn kết thúc bằng .idl
đường dẫn bắt đầu bằng third_party/blink/renderer/
```

Điều kiện thứ hai không thừa. Đuôi `.idl` còn được dùng cho Chrome Extensions IDL và cho Windows MIDL. Nếu đem parse chúng như Web IDL, báo cáo sẽ sinh ra những finding kiểu "API mà site nhìn thấy đã thay đổi" hoàn toàn sai.

### Khai báo nào tạo `Fact`

- interface, callback interface, interface mixin;
- dictionary, namespace, enum;
- operation, attribute, field, constructor, const, và các dạng iterable/maplike/setlike;
- extended attribute như `[RuntimeEnabled=Foo]`, `[Exposed=Window]`.

Riêng `partial interface` không tạo ra một `Fact` interface mới, nhưng các member khai báo bên trong nó vẫn được gắn vào interface gốc.

### Vì sao cần theo dõi

- **Interface hoặc member bị bỏ**: website đang chạy có thể lỗi.
- **Signature đổi**: chỗ gọi cũ có thể không còn khớp.
- **Thêm overload**: nếu trùng số lượng tham số với overload cũ, cách gọi có thể được phân giải sang một hàm khác.
- **`Exposed` hoặc `RuntimeEnabled` đổi**: API vẫn còn đó, nhưng ngữ cảnh hoặc điều kiện truy cập đã khác.
- **Quan hệ kế thừa hoặc giá trị enum đổi**: hình dạng mà JavaScript quan sát được thay đổi.

### Ví dụ

```webidl
[Exposed=Window]
interface Example {
  [RuntimeEnabled=Foo] Promise<DOMString> connect(DOMString host);
};
```

Công cụ tạo hai `Fact`: một cho `Example`, một cho `Example.connect`. Sau đó nó nối `RuntimeEnabled=Foo` với trạng thái của runtime feature `Foo`, để biết member này đang thật sự dùng được hay còn bị chặn sau gate.

Giới hạn cần biết: parser ở đây là một lexer thực dụng, viết cho dialect mà Blink thường dùng. Nó không phải một parser Web IDL đầy đủ theo chuẩn.

## 4. `mojom` — contract IPC giữa các process

### Đọc file nào

Mọi đường dẫn kết thúc bằng `.mojom` nằm trong phạm vi sản phẩm của target set đang chạy.

### Khai báo nào tạo `Fact`

- `interface`, cùng các method dạng request và request/response;
- `struct` và `union`;
- từng field;
- enum, kèm danh sách giá trị.

Những thông tin sau được giữ lại khi chúng có ý nghĩa: module, tên đầy đủ, ordinal, kiểu dữ liệu, phần response, `[Stable]`, `[MinVersion]` và `[EnableIf...]`.

### Vì sao cần theo dõi

Đây là nhóm nguy hiểm nhất, vì lý do sau: code của Samsung có thể đang hiện thực hoặc đang gọi **một đầu** của một Mojo interface, còn đầu kia là code upstream.

Khi đó, mọi thay đổi sau đều có thể tạo ra bất tương thích IPC: method đổi tham số hoặc response, ordinal đổi, field đổi kiểu, struct chuyển thành union, enum có thêm giá trị mới, hoặc khai báo `[Stable]` bị đảo thứ tự. Và với một ranh giới do Samsung tự dựng, lỗi có thể chỉ lộ ra lúc chạy.

### Ví dụ

```mojom
module network.mojom;

[Stable] interface Probe {
  Start@0(string url) => (bool accepted);
};
```

Identity của method này là `network.mojom.Probe.Start`; còn signature và ordinal là các thuộc tính được đem đi so sánh.

Công cụ chưa tìm mọi chỗ gọi và mọi phần hiện thực trong code Samsung. Nó chỉ chỉ ra rằng contract phía upstream đã đổi.

## 5. `constants` — pref key và command-line switch

### Đọc file nào

Đường dẫn phải kết thúc bằng `.cc` hoặc `.h`. Tên file phải chứa `switches.`, hoặc khớp một trong các quy ước đặt tên pref: `pref_names.`, `pref_names_`, `_pref_names.`, `_prefs.`, `prefs.`.

Hai cú pháp khai báo hằng chuỗi được hỗ trợ:

```cpp
const char kFoo[] = "foo";
inline constexpr std::string_view kFoo = "foo";
```

Nếu tên file khớp quy ước pref, `Fact` sinh ra có `kind` là `pref`; còn lại là `switch`. Điểm quan trọng: **identity là giá trị chuỗi, không phải tên biến C++.**

### Vì sao cần theo dõi

Năm trường hợp, và hậu quả của chúng khác hẳn nhau — đây là lý do phải tách bạch chuỗi với symbol:

| Thay đổi | Hậu quả |
|---|---|
| Chuỗi pref đổi | Profile cũ vẫn giữ khoá cũ; setting của người dùng có thể quay về mặc định |
| C++ symbol của pref đổi, chuỗi giữ nguyên | Dữ liệu người dùng an toàn, nhưng build của Samsung có thể fail |
| Chuỗi switch đổi | Script khởi động và automation cũ **im lặng** mất tác dụng |
| C++ symbol của switch đổi | Code không compile được, nhưng script bên ngoài vẫn an toàn |
| Điều kiện platform đổi | Khoá có thể ra hoặc vào bản build Windows |

### Ví dụ

```cpp
const char kPromptForDownload[] = "download.prompt_for_download";
```

`Fact` được đánh khoá bằng `download.prompt_for_download`. Cách chọn khoá này cho hai kết quả có ích: nếu chỉ C++ symbol đổi thì đây là `modified`; còn nếu chuỗi đổi thì bộ phát hiện đổi tên vẫn ghép lại được nhờ symbol không đổi.

Chỉ những quy ước đặt tên đã được kiểm chứng mới được đọc, để tránh biến một hằng chuỗi bình thường thành một contract với bên ngoài.

## 6. `flags_metadata` — vòng đời của entry trong `chrome://flags`

### Đọc file nào

Tên file chính xác là `flag-metadata.json`. Mỗi object có trường `name` tạo ra một `flag_entry`; công cụ giữ lại `expiry_milestone` và `owners`.

### Vì sao cần theo dõi

Đây là nguồn duy nhất trong cả 9 nhóm nói trực tiếp về **tương lai**.

Nếu một flag mà Samsung đang override sắp hết hạn trong milestone đích hoặc trong hai milestone kế tiếp, team có thể lập backlog ngay từ bây giờ, trước khi upstream xoá cả khai báo lẫn phần đấu nối.

### Ví dụ

```json
{
  "name": "enable-foo",
  "owners": ["team@example.com"],
  "expiry_milestone": 154
}
```

Trường `owners` ở đây là người liên hệ phía upstream của metadata này; nó **khác** với owner routing trong báo cáo. Và file này cũng không chứng minh được Samsung có dùng flag hay không.

## 7. `webui_routes` — danh mục trang và trang con

### Đọc file nào

Đường dẫn bắt đầu bằng `chrome/browser/resources/`, và tên file là `route.ts` hoặc `routes.ts`.

### Khai báo nào tạo `Fact`

Các phép gán theo hai mẫu sau:

```ts
r.NAME = r.PARENT.createChild('path');
r.NAME = r.PARENT.createSection('path', 'section');
```

Extractor đồng thời theo dõi ngăn xếp các câu `if (loadTimeData.getBoolean('key'))` bao quanh route đó.

### Vì sao cần theo dõi

Khi một trang biến mất khỏi bảng route, có tới bốn khả năng khác nhau: nó thật sự biến mất, nó đổi URL hoặc đổi route cha, nó được thay bằng một trang mới, hoặc nó vốn đã bị ẩn từ trước bởi một guard.

Nếu không giữ lại guard, báo cáo sẽ kết luận sai về **thời điểm** người dùng nhìn thấy thay đổi — báo một trang "vừa bị xoá ở M151" trong khi thực tế người dùng đã không thấy nó từ nhiều milestone trước.

### Ví dụ

```ts
if (loadTimeData.getBoolean('enableFooSetting')) {
  r.FOO = r.PRIVACY.createChild('foo');
}
```

`Fact` giữ ba thứ: route `foo`, route cha `PRIVACY`, và guard `enableFooSetting`.

Giới hạn: những phần điều hướng được dựng hoàn toàn động bằng cú pháp khác chưa nằm trong phạm vi extractor này.

## 8. `webui_controls` — control trong template Polymer/Lit

### Đọc file nào

Đường dẫn nằm dưới `chrome/browser/resources/` và kết thúc bằng `.html` hoặc `.html.ts`.

### Nhận ra một control bằng rule nào

Mọi custom element (tag có dấu `-` trong tên) đều được xét. Nó được coi là control nếu thoả **ít nhất một** trong ba điều kiện:

1. Có binding tới một pref.
2. Là một tag cấu trúc đã biết, ví dụ `settings-subpage`, `settings-section`, `downloads-item`.
3. Tag chứa một đoạn mang tính tương tác — `button`, `toggle`, `checkbox`, `radio`, `input`, `select`, `slider`, `menu`, `row`... — **và** có identity ổn định nhờ `id` hoặc nhãn.

Rule này dựa trên **hình dạng** thay vì một danh sách tag đóng, vì danh sách đóng rất nhanh lỗi thời. Những element không có pref, không có id và không có nhãn thường bị bỏ qua, vì cách duy nhất để nhận diện chúng là theo vị trí — mà vị trí thì đổi liên tục mỗi khi template được sắp xếp lại.

Binding tới pref được hiểu ở cả Polymer lẫn Lit:

```html
pref="{{prefs.download.prompt_for_download}}"
pref="[[prefs.download.prompt_for_download]]"
.pref="${this.prefs.download.prompt_for_download}"
pref-key="download.prompt_for_download"
```

Tiền tố `prefs.` là bắt buộc, để không nhầm một property thông thường của component thành một pref.

### Vì sao cần theo dõi

- **Toggle đổi thành dropdown** là thay đổi về cách tương tác và về ngữ nghĩa.
- **Control chuyển sang pref khác** khiến giá trị cũ bị bỏ lại và pref mới bắt đầu từ mặc định — người dùng mất setting mà không có thông báo.
- **Control bị thêm hoặc bị bỏ** cho biết bề mặt Settings đã đổi.
- **Điều kiện GRIT đổi** cho biết control ra hoặc vào bản build Windows.

### Ví dụ

```html
<settings-toggle-button
    id="promptForDownload"
    pref="{{prefs.download.prompt_for_download}}"
    label="$i18n{promptForDownload}">
</settings-toggle-button>
```

Bốn thứ công cụ **không** làm ở đây: nó không render giao diện, không đọc CSS hay layout, không kiểm tra event handler, và không đọc chuỗi hiển thị thật trong file `.grd`. Nhãn được lưu trong `Fact` là khoá i18n, không phải câu chữ người dùng đọc thấy.

## 9. `webui_gates` — cầu nối từ WebUI sang feature/config phía C++

### Đọc file nào

Đường dẫn bắt đầu bằng `chrome/browser/ui/webui/` và kết thúc bằng `.cc`.

### Khai báo nào tạo `Fact`

Các lời gọi dạng `AddBoolean`, `AddInteger`, `AddString` hoặc `AddDouble`, với tham số đầu tiên là một chuỗi literal đóng vai trò khoá. Công cụ giữ lại biểu thức đã được chuẩn hoá, danh sách các `features::k...` được tham chiếu, và feature nằm bên trong `IsEnabled()`.

```cpp
html_source->AddBoolean(
    "enableFooSetting",
    base::FeatureList::IsEnabled(features::kFoo));
```

### Vì sao cần theo dõi

Bản thân route và template chỉ biết tới một khoá `loadTimeData`, chứ không biết phía sau khoá đó là gì. `webui_gate` chính là mắt xích bổ sung để nối tiếp sang phía C++:

```text
guard của route: enableFooSetting
        ↓ ghép bằng data_key
WebUI gate: IsEnabled(features::kFoo)
        ↓ ghép bằng symbol/tên của feature
base_feature: trạng thái mặc định + trạng thái trên Windows
```

Nhờ chuỗi liên kết này, một agent phân biệt được hai tình huống rất khác nhau: *"trang bị xoá, nhưng nó đã bị ẩn từ trước"* và *"trang đang hiển thị bình thường rồi biến mất trong đợt uprev này"*.

Trường hợp riêng: một gate phụ thuộc hoàn toàn vào policy hoặc profile vẫn tạo ra `Fact`, nhưng sẽ không nối được sang `base_feature` nào.

## Vì sao lại là đúng 9 nhóm này

Chín nhóm được chọn để phủ ba loại rủi ro mà việc compile và test thông thường khó phát hiện:

1. **Công tắc hành vi** — feature, giá trị mặc định, trạng thái runtime đổi, làm browser hành xử khác đi.
2. **Contract với bên ngoài** — pref, switch, Web API và Mojo đổi, làm dữ liệu, script, website hoặc process khác không còn tương thích.
3. **Giao diện và lịch trình** — trang, control, gate đổi, hoặc flag sắp bị xoá.

Điểm chung của cả chín: mỗi nhóm có một nguồn sự thật đủ ổn định để đặt được một khoá ngữ nghĩa. Phần implementation trong `.cc` và `.ts` vẫn rất quan trọng, nhưng diff thô của chúng chứa quá nhiều nhiễu từ refactor và thường không có identity ổn định để ghép giữa hai version.

### Nếu muốn thêm nhóm thứ mười

Cần trả lời được cả năm câu hỏi sau. Thiếu một câu là nhóm đó chưa sẵn sàng:

- Nguồn sự thật nào chứa khai báo này?
- Khoá nào ổn định giữa hai version, kể cả khi cú pháp bị refactor?
- Thuộc tính nào thật sự làm thay đổi hành vi hoặc contract?
- Có đo được khoảng trống về grammar và về coverage không?
- Finding sinh ra sẽ dẫn tới hành động review cụ thể nào?

## Kiểm tra bộ lọc có đáng tin không

Bốn cách, xếp từ rẻ tới đắt:

1. Viết unit test cho `applies_to()`, với bốn nhóm đầu vào: đường dẫn đúng, đường dẫn gần giống nhưng sai dialect, file test, và đường dẫn của platform khác.
2. Viết unit test theo cặp "source đầu vào → `Fact` mong đợi" cho mọi cú pháp được hỗ trợ.
3. Chạy catalog và coverage trên một version thật, để tìm ra quy ước đặt tên bị bỏ sót.
4. Diff hai version thật, để tìm những finding sai do refactor, do chuyển file, do overload hoặc do điều kiện platform.

### Một cảnh báo về con số coverage

Coverage 100% chỉ nói lên đúng một điều: **đã đọc mọi file mà rule hiện tại gọi là candidate.**

Nó không chứng minh parser hiểu 100% grammar bên trong những file đó, và cũng không chứng minh rule không bỏ quên một quy ước đặt tên mới xuất hiện. Vì vậy hai thứ phải tồn tại song song: kiểm tra catalog để canh rule, và test parser để canh grammar.
