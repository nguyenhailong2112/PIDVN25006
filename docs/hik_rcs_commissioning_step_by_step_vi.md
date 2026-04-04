# HƯỚNG DẪN CẦM TAY CHỈ VIỆC: TRIỂN KHAI VISION <-> HIK RCS-2000

Tài liệu này là bản hướng dẫn triển khai thực địa hoàn chỉnh để kết nối hệ thống Vision trong dự án này với HIK RCS-2000, phục vụ điều phối AGV/AMR.

Mục tiêu của tài liệu:

1. Giúp bạn hiểu đúng bản chất giao tiếp giữa hai hệ thống.
2. Giúp bạn xác định chính xác phải cấu hình gì trong code, trong RCS và trên hiện trường.
3. Giúp bạn thực hiện test theo đúng thứ tự, an toàn, có kiểm soát, có bằng chứng.
4. Giúp bạn đi từ trạng thái “đang mơ hồ” đến trạng thái “đủ chắc chắn để commissioning”.

Tài liệu này được viết theo hướng:

- đầy đủ
- có trình tự
- dễ làm theo
- hạn chế suy đoán
- bám sát code đang có trong project

---

## 1. Kết luận quan trọng nhất phải nắm trước

### 1.1 Vision không gửi “occupied/empty” thuần túy sang RCS

Đây là điểm quan trọng nhất của toàn bộ bài toán.

HIK RCS-2000 không làm việc theo kiểu:

- Vision gửi lên: “ô này có hàng”
- RCS nhận một bit occupancy rồi tự hiểu toàn bộ nghiệp vụ

Thay vào đó, RCS làm việc theo API nghiệp vụ.

Tức là Vision phải quy đổi trạng thái zone sang một hành động nghiệp vụ mà RCS hiểu, ví dụ:

- bind rack vào vị trí
- unbind rack khỏi vị trí
- bind rack với material lot
- bind container với bin
- khóa vị trí khi trạng thái không chắc chắn

### 1.2 Kiến trúc đúng của hệ thống

Tư duy đúng phải là:

`Vision -> Zone State -> Bridge nghiệp vụ -> HIK RCS API -> RCS scheduling -> AGV/AMR`

Ý nghĩa:

- Vision chỉ xác nhận hiện trường.
- Bridge chuyển trạng thái Vision sang đúng API nghiệp vụ.
- HIK RCS mới là hệ thống quản lý business object, scheduling và điều phối AGV/AMR.

### 1.3 Muốn thành công thì phải chốt đúng 4 điểm

Code đã có. Giao thức đã có. API hãng đã có. UI RCS cũng đã có.

Thành bại thực tế bây giờ nằm ở 4 điểm sau:

1. Mapping nghiệp vụ đúng.
2. Auth đúng.
3. Callback đúng.
4. Trình tự test đúng.

Nếu 4 điểm này đúng, việc tích hợp sẽ rõ ràng và làm được.

---

## 2. Hệ thống code hiện tại trong project đang làm được gì

Trong project này, phần giao tiếp HIK RCS đã có sẵn các thành phần chính:

- [`core/hik_rcs_client.py`](C:\Users\longn\PycharmProjects\PIDVN25006\core\hik_rcs_client.py)
  Vai trò: gửi HTTP POST JSON sang HIK RCS.

- [`core/hik_rcs_bridge.py`](C:\Users\longn\PycharmProjects\PIDVN25006\core\hik_rcs_bridge.py)
  Vai trò: đọc state Vision và map sang API nghiệp vụ của HIK.

- [`core/hik_callback_server.py`](C:\Users\longn\PycharmProjects\PIDVN25006\core\hik_callback_server.py)
  Vai trò: nhận callback từ HIK RCS.

- [`tools/hik_rcs_cli.py`](C:\Users\longn\PycharmProjects\PIDVN25006\tools\hik_rcs_cli.py)
  Vai trò: test thủ công từng API, từng zone mapping, callback server.

- [`configs/hik_rcs.json`](C:\Users\longn\PycharmProjects\PIDVN25006\configs\hik_rcs.json)
  Vai trò: cấu hình kết nối, auth, callback và mapping zone -> business API.

### 2.1 Các API nghiệp vụ mà code đang hỗ trợ

Code hiện tại đang hỗ trợ đúng các nhóm API chính:

- `bindPodAndBerth`
- `bindPodAndMat`
- `bindCtnrAndBin`
- `lockPosition`
- `queryAgvStatus`
- `queryTaskStatus`

### 2.2 Callback mà code hiện tại đang nhận

Code callback server hiện tại hỗ trợ:

- `agvCallback`
- `warnCallback`
- `bindNotify`

### 2.3 Ý nghĩa state Vision trong bridge

Trong hệ thống này, state từ Vision được hiểu như sau:

- `occupied`
  Nghĩa là vị trí có đối tượng cần quản lý.

- `empty`
  Nghĩa là vị trí trống.

- `unknown`
  Nghĩa là không đủ cơ sở kết luận an toàn.

Quy tắc bridge hiện tại:

- `occupied` -> bind
- `empty` -> unbind
- `unknown` -> không bind/unbind mù, ưu tiên `lockPosition` nếu cấu hình `unknown_action=lockPosition`

---

## 3. 3 nhóm use-case nghiệp vụ mà bạn phải chọn đúng

Bạn không được bắt đầu test live khi chưa chốt zone đó thuộc nhóm nghiệp vụ nào.

### 3.1 Nhóm 1: Rack/Trolley tại một vị trí

Dùng API:

- `bindPodAndBerth`

Ý nghĩa:

- Khi Vision xác nhận vị trí đang có rack/trolley -> bind rack với vị trí
- Khi Vision xác nhận vị trí trống -> unbind rack khỏi vị trí

Field nghiệp vụ cần có:

- `positionCode`
- `podCode`
- tùy chọn `podDir`
- tùy chọn `characterValue`

Quy đổi:

- `occupied` -> `indBind=1`
- `empty` -> `indBind=0`
- `unknown` -> ưu tiên `lockPosition(indBind=0)` nếu site yêu cầu fail-safe

### 3.2 Nhóm 2: Rack/Trolley gắn với material lot

Dùng API:

- `bindPodAndMat`

Field nghiệp vụ cần có:

- `podCode`
- `materialLot`

Quy đổi:

- `occupied` -> bind
- `empty` -> unbind
- `unknown` -> xử lý fail-safe theo quy tắc site

### 3.3 Nhóm 3: Pallet/Container/Bin

Dùng API:

- `bindCtnrAndBin`

Field nghiệp vụ cần có:

- `ctnrCode`
- `ctnrTyp`
- một trong hai:
  - `stgBinCode`
  - hoặc `positionCode`

Quy đổi:

- `occupied` -> `indBind=1`
- `empty` -> `indBind=0`
- `unknown` -> ưu tiên `lockPosition(indBind=0)` nếu đây là zone quan trọng

### 3.4 Kết luận chốt method

Bạn phải tự trả lời chính xác câu này cho từng zone:

- Zone này ngoài hiện trường đang đại diện cho rack tại vị trí?
- Hay rack gắn với material lot?
- Hay pallet/container/bin?

Chỉ sau khi trả lời được câu đó mới được chọn:

- `bindPodAndBerth`
- hoặc `bindPodAndMat`
- hoặc `bindCtnrAndBin`

### 3.5 Use-case đặc biệt: thang máy AGV hoặc vùng an toàn chỉ cần "có vật là chặn"

Đây là use-case rất quan trọng trong dự án hiện tại.

Bài toán:

- Camera nhìn vào buồng thang máy.
- Chỉ cần trong ROI có bất kỳ object nào thì AGV không được vào thang máy.

Tư duy đúng:

- Đây vẫn là bài toán zone-based state.
- Nhưng đây không phải bài toán bind một business object như rack hay pallet.
- Đây là bài toán safety interlock.

Cách làm đúng trong code:

1. Tạo ROI lớn phủ gần toàn bộ vùng trong thang máy.
2. Đặt `target_object="*"` để nhận mọi class detect được.
3. Dùng `spatial_method="bbox_intersects"` để chỉ cần bbox chạm ROI là tính có vật.
4. Vision vẫn sinh state zone chuẩn:
   - có vật -> `occupied`
   - không có vật -> `empty`
   - không chắc chắn -> `unknown`
5. Mapping sang HIK bằng `method="lockPosition"`:
   - `occupied` -> `lockPosition(indBind=0)`
   - `empty` -> `lockPosition(indBind=1)`
   - `unknown` -> `lockPosition(indBind=0)`

Đây là cách triển khai đúng nhất cho use-case thang máy nếu mục tiêu thực sự là cho phép hoặc cấm AGV đi vào vùng đó.

---

## 4. 8 nhóm thông tin bắt buộc phải có trước khi đi commissioning

Không được đi live khi chưa có đủ 8 nhóm thông tin sau.

### 4.1 Thông tin kết nối RCS

Phải có:

- `host`
- `rpc_port`
- `dps_port`
- `scheme`

### 4.2 Thông tin xác thực

Phải có:

- `client_code`
- `token_code`

Nếu bên HIK nói không cần token, vẫn phải xác nhận rõ bằng tài liệu kỹ thuật hoặc trao đổi chính thức.

### 4.3 Bảng mapping zone -> business code

Phải có cho từng zone cần test:

- `camera_id`
- `zone_id`
- `method`
- `positionCode`
- và mã nghiệp vụ tương ứng:
  - `podCode`
  - hoặc `materialLot`
  - hoặc `ctnrCode + ctnrTyp`

### 4.4 Quy tắc fail-safe cho `unknown`

Phải xác nhận:

- `unknown` có được phép bind/unbind hay không
- có dùng `lockPosition` hay không
- nếu có thì khóa vị trí nào
- khi nào mở lại vị trí

### 4.5 Callback

Phải xác nhận:

- RCS có gọi callback hay không
- callback base URL là gì
- RCS đang gọi theo dạng:
  - `/service/rest/...`
  - hay `/service/rest/agvCallbackService/...`

### 4.6 Quy tắc object ID

Phải xác nhận:

- object trong zone là rack, trolley, pallet, container hay lot
- object ID là cố định theo zone hay thay đổi theo lệnh/ngày/sản xuất
- nếu thay đổi thì hệ thống nào cấp ID đó

### 4.7 Điều kiện mạng

Phải xác nhận:

- Vision PC đi được tới RCS
- RCS gọi ngược được về Vision callback server
- port callback không bị firewall chặn

### 4.8 Điều kiện nghiệm thu

Phải xác nhận trước:

- test bao nhiêu zone
- test những tình huống nào
- ai là người xác nhận bên HIK/AGV/WMS

---

## 5. Cách dùng UI RCS để chốt đúng thông tin

Bạn đã có thêm `UIRCS.pdf`, đây là lợi thế rất lớn.

Từ thời điểm này, UI RCS không còn chỉ để “xem tham khảo”, mà phải được dùng để xác nhận từng field nghiệp vụ.

### 5.1 Những màn hình cần tìm trong UI RCS

Khi xem `UIRCS.pdf` hoặc ngồi trực tiếp trước màn hình RCS, hãy tìm bằng được các nhóm màn hình sau:

1. Màn hình system parameter hoặc integration parameter
2. Màn hình cấu hình external interface hoặc callback
3. Màn hình quản lý position/berth/bin
4. Màn hình quản lý pod/rack/container/material lot
5. Màn hình AGV status
6. Màn hình task status
7. Màn hình cảnh báo/warning/notification

### 5.2 Khi nhìn một màn hình UI, phải tự hỏi 3 câu

1. Màn hình này xác nhận được field nào trong config?
2. Mã đang hiện trên UI là mã business thật hay chỉ là tên hiển thị?
3. Trường này có đúng là `positionCode`, `podCode`, `ctnrCode`, `materialLot` không?

### 5.3 Không được nhầm giữa “tên hiển thị” và “business code”

Ví dụ:

- “Kệ A1”
- “Zone rack đầu line”
- “Pallet khu vực 3”

Các chuỗi trên có thể chỉ là tên hiển thị.

Cái bạn cần cho tích hợp không phải tên mô tả, mà là business code thật dùng trong API, ví dụ:

- `P-A1`
- `RACK-001`
- `PALLET-001`
- `LOT-ABC-001`

### 5.4 Bảng quy đổi UI RCS -> file config

Khi đọc UI RCS, hãy quy đổi như sau:

| Thông tin trên UI | Điền vào đâu |
|---|---|
| Server host/IP | `configs/hik_rcs.json -> host` |
| RPC port | `rpc_port` |
| DPS port | `dps_port` |
| Client code | `client_code` |
| Token code | `token_code` |
| RPC path | `rpc_base_path` |
| Query AGV path | `query_agv_path` |
| Callback base URL | `callback_server.base_path` và phần cấu hình trên RCS |
| Position code | `mapping.position_code` |
| Pod code | `mapping.pod_code` |
| Material lot | `mapping.material_lot` |
| Container code | `mapping.ctnr_code` |
| Container type | `mapping.ctnr_typ` |
| Storage bin code | `mapping.stg_bin_code` |
| Map short name | payload test `query-agv` |
| Task code | payload test `query-task` |

---

## 6. Bảng mapping bắt buộc phải lập trước khi sửa config

Tuyệt đối không sửa ngay `configs/hik_rcs.json` theo cảm tính.

Trước hết phải lập bảng mapping này:

| camera_id | zone_id | đối tượng thật ngoài hiện trường | mã business trên UI RCS | method | positionCode | podCode | materialLot | ctnrCode | ctnrTyp | stgBinCode | unknown_action | đã xác nhận với ai |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cam1 | A1 |  |  |  |  |  |  |  |  |  | lockPosition |  |
| cam1 | A2 |  |  |  |  |  |  |  |  |  | lockPosition |  |
| cam2 | A1 |  |  |  |  |  |  |  |  |  | lockPosition |  |

### 6.1 Quy tắc điền bảng mapping

- Mỗi dòng là một `camera_id + zone_id`
- Một zone chỉ được chọn một `method`
- Không được để một zone vừa là `bindPodAndBerth` vừa là `bindCtnrAndBin`
- Không được dùng mã suy đoán
- Không được bỏ trống cột business code quan trọng rồi vẫn test live

### 6.2 Đây là bước quan trọng nhất của toàn bộ commissioning

HTTP client đúng nhưng mapping sai thì vẫn thất bại.

Vì vậy, đừng coi `host/port/token` là khó nhất.
Khó nhất luôn là:

- zone nào
- đối tượng nào
- mã nào
- API nào

---

## 7. Giải thích đầy đủ file `configs/hik_rcs.json`

Đây là file trung tâm cho toàn bộ tích hợp.

### 7.1 Nhóm cấu hình kết nối và xác thực

Ví dụ:

```json
{
  "enabled": false,
  "dry_run": true,
  "scheme": "http",
  "host": "192.168.1.200",
  "rpc_port": 8182,
  "dps_port": 8083,
  "rpc_base_path": "/rcms/services/rest/hikRpcService",
  "query_agv_path": "/rcms-dps/rest/queryAgvStatus",
  "http_timeout_sec": 3.0,
  "client_code": "VISION01",
  "token_code": "TOKEN_FROM_HIK",
  "include_interface_name": false,
  "require_online_health": true,
  "min_score": 0.6,
  "retry_interval_sec": 5.0
}
```

Giải thích:

- `enabled`
  - `false`: bridge không gửi request
  - `true`: bridge được phép xét dispatch

- `dry_run`
  - `true`: vẫn chạy logic nhưng không gửi HTTP thật
  - `false`: gửi request thật sang HIK

- `scheme`
  - `http` hoặc `https`

- `host`
  - IP hoặc hostname của HIK RCS

- `rpc_port`
  - port cho các API trong `hikRpcService`

- `dps_port`
  - port cho `queryAgvStatus`

- `rpc_base_path`
  - đường dẫn REST cho nhóm RPC API

- `query_agv_path`
  - đường dẫn query AGV

- `http_timeout_sec`
  - timeout mỗi request

- `client_code`
  - mã client do HIK cấp cho hệ thống Vision

- `token_code`
  - token xác thực

- `include_interface_name`
  - một số deployment cũ yêu cầu field `interfaceName`

- `require_online_health`
  - nếu `true`, camera hoặc zone không online thì bridge coi là `unknown`

- `min_score`
  - ngưỡng score tối thiểu để cho phép dispatch

- `retry_interval_sec`
  - thời gian chờ trước khi retry nếu request trước đó fail

### 7.2 Nhóm cấu hình callback server

Ví dụ:

```json
"callback_server": {
  "enabled": true,
  "host": "0.0.0.0",
  "port": 9000,
  "base_path": "/service/rest/agvCallbackService",
  "validate_token_code": false
}
```

Giải thích:

- `enabled`
  - `true`: bật HTTP server để nhận callback

- `host`
  - thường để `0.0.0.0`

- `port`
  - port callback mở trên Vision PC

- `base_path`
  - code hiện tại chấp nhận cả:
    - `/service/rest`
    - hoặc `/service/rest/agvCallbackService`

- `validate_token_code`
  - nếu `true`, callback phải mang đúng `tokenCode` và `clientCode`

### 7.3 Nhóm mapping

Ví dụ 1:

```json
{
  "enabled": true,
  "camera_id": "cam1",
  "zone_id": "A1",
  "method": "bindPodAndBerth",
  "position_code": "P-A1",
  "pod_code": "RACK-001",
  "pod_dir": "0",
  "unknown_action": "lockPosition"
}
```

Ví dụ 2:

```json
{
  "enabled": true,
  "camera_id": "cam4",
  "zone_id": "B1",
  "method": "bindCtnrAndBin",
  "position_code": "P-B1",
  "stg_bin_code": "BIN-B1",
  "ctnr_code": "PALLET-001",
  "ctnr_typ": "PALLET",
  "unknown_action": "lockPosition"
}
```

Ví dụ 3 cho zone an toàn kiểu thang máy:

```json
{
  "enabled": true,
  "camera_id": "cam6",
  "zone_id": "LIFT_1",
  "method": "lockPosition",
  "position_code": "LIFT-01"
}
```

Field quan trọng:

- `enabled`
- `camera_id`
- `zone_id`
- `method`
- `position_code`
- `pod_code`
- `material_lot`
- `ctnr_code`
- `ctnr_typ`
- `stg_bin_code`
- `bin_name`
- `pod_dir`
- `character_value`
- `unknown_action`
- `min_score`

### 7.4 Template field

Code hiện tại có hỗ trợ template như:

- `pod_code_template`
- `ctnr_code_template`

Ví dụ:

```json
"ctnr_code_template": "CTNR_{camera_id}_{zone_id}"
```

Chỉ dùng template khi:

- object ID thực sự cố định theo zone
- hoặc business chấp nhận naming rule cố định

Không dùng template nếu object ID thay đổi theo lệnh hoặc theo ngày.

---

## 8. Quy tắc an toàn khi chỉnh config

Luôn làm theo đúng thứ tự này:

1. Ban đầu để:
   - `enabled=false`
   - `dry_run=true`
2. Điền đầy đủ kết nối, auth, callback.
3. Lập xong bảng mapping.
4. Review lại từng zone.
5. Chuyển sang:
   - `enabled=true`
   - `dry_run=true`
6. Test logic.
7. Chỉ khi pass mới đổi:
   - `dry_run=false`

Không được:

- bật request thật khi chưa test dry-run
- bật nhiều mapping live cùng lúc ở lần test đầu
- đoán mã `positionCode` hoặc `podCode`

---

## 9. Checklist hạ tầng trước khi chạy

### 9.1 Trên máy Vision

Phải kiểm tra:

- môi trường Python chạy được
- model đúng đường dẫn
- cấu hình camera đúng
- output Vision đang sinh bình thường

### 9.2 Kết nối mạng tới RCS

Phải kiểm tra:

- Vision PC đi được tới host RCS
- callback từ RCS quay về được Vision PC
- port callback không bị firewall chặn

### 9.3 Camera

Phải kiểm tra:

- camera online
- stream mở được
- ảnh đúng camera
- ROI đúng hiện trường

### 9.4 Output Vision trước bridge

Phải xem:

- `outputs/runtime/agv_latest.json`
- `outputs/runtime/process_latest.json`
- `outputs/runtime/cameras/<camera_id>.json`

Bạn chỉ được phép đi tiếp khi:

- zone state đúng
- không flicker bất thường
- `unknown` xuất hiện hợp lý

---

## 10. Trình tự commissioning chuẩn từ đầu đến cuối

Đây là phần quan trọng nhất của tài liệu.

Hãy làm theo đúng thứ tự, không đảo bước.

### BƯỚC 1 - Xác nhận Vision độc lập, chưa bridge

Mục tiêu:

- xác nhận Vision tự nó đã đúng

Thiết lập:

- `configs/hik_rcs.json -> enabled=false`

Chạy:

```bash
python mainProcess.py
```

Kiểm tra:

- `outputs/runtime/agv_latest.json`
- `outputs/runtime/process_latest.json`
- `outputs/runtime/cameras/*.json`

Pass khi:

- zone state cập nhật đúng
- hiện trường có hàng -> `occupied`
- hiện trường trống -> `empty`
- khi camera lỗi hoặc dữ liệu không chắc -> `unknown`

Nếu bước này chưa pass, dừng lại và sửa Vision trước.

### BƯỚC 2 - Dùng UI RCS để lập bảng mapping

Mục tiêu:

- chốt đúng nghiệp vụ và business code

Thao tác:

1. Mở `UIRCS.pdf` hoặc vào trực tiếp UI RCS.
2. Tìm màn hình position/berth/bin.
3. Tìm màn hình pod/rack/container/material lot.
4. Ghi lại đúng business code thật.
5. Điền bảng mapping cho từng zone.
6. Xác nhận lại với phía HIK/AGV/WMS nếu còn mơ hồ.

Pass khi:

- mỗi zone đã có đúng `method`
- mỗi zone đã có đủ business code cần thiết
- không còn dòng nào “để test tạm”

Lưu ý riêng cho thang máy:

- Nếu mục tiêu là chặn AGV khi trong buồng thang máy có vật, ưu tiên hỏi đúng `positionCode` của thang máy trong RCS.
- Không cố ép use-case này sang `bindPodAndBerth` nếu bản chất không có pod business thật.
- Mapping đúng trong đa số trường hợp sẽ là `lockPosition`.

### BƯỚC 3 - Điền `configs/hik_rcs.json`

Mục tiêu:

- đưa mapping và thông số thật vào config

Thao tác:

1. Điền `host`, `rpc_port`, `dps_port`, `client_code`, `token_code`
2. Điền callback server config
3. Chỉ bật đúng 1 mapping đầu tiên để test
4. Để:
   - `enabled=true`
   - `dry_run=true`

Ví dụ cấu hình test 1 zone:

```json
{
  "enabled": true,
  "dry_run": true,
  "scheme": "http",
  "host": "192.168.1.200",
  "rpc_port": 8182,
  "dps_port": 8083,
  "rpc_base_path": "/rcms/services/rest/hikRpcService",
  "query_agv_path": "/rcms-dps/rest/queryAgvStatus",
  "http_timeout_sec": 5.0,
  "client_code": "VISION01",
  "token_code": "TOKEN_FROM_HIK",
  "include_interface_name": false,
  "require_online_health": true,
  "min_score": 0.6,
  "retry_interval_sec": 5.0,
  "callback_server": {
    "enabled": true,
    "host": "0.0.0.0",
    "port": 9000,
    "base_path": "/service/rest/agvCallbackService",
    "validate_token_code": false
  },
  "mappings": [
    {
      "enabled": true,
      "camera_id": "cam1",
      "zone_id": "A1",
      "method": "bindPodAndBerth",
      "position_code": "P-A1",
      "pod_code": "RACK-001",
      "pod_dir": "0",
      "unknown_action": "lockPosition"
    }
  ]
}
```

Pass khi:

- config không còn field mơ hồ
- chỉ còn 1 zone test đầu tiên được bật

### BƯỚC 4 - Test callback riêng

Mục tiêu:

- xác nhận RCS gọi ngược về Vision được

Thiết lập:

- `callback_server.enabled=true`

Chạy:

```bash
python tools/hik_rcs_cli.py serve-callbacks
```

Sau đó:

- nhờ bên HIK gửi callback test
- hoặc dùng công cụ mô phỏng nội bộ nếu có

Kiểm tra:

- `outputs/runtime/hik_rcs/callbacks/agvCallback_latest.json`
- `outputs/runtime/hik_rcs/callbacks/warnCallback_latest.json`
- `outputs/runtime/hik_rcs/callbacks/bindNotify_latest.json`

Pass khi:

- callback đến đúng path
- file callback được tạo
- nếu bật validate token thì callback pass xác thực

### BƯỚC 5 - Test logic dry-run bằng CLI

Mục tiêu:

- xác nhận mapping của zone đầu tiên là đúng logic

Chạy:

```bash
python tools/hik_rcs_cli.py bind-zone --camera-id cam1 --zone-id A1 --state occupied --dry-run
python tools/hik_rcs_cli.py bind-zone --camera-id cam1 --zone-id A1 --state empty --dry-run
python tools/hik_rcs_cli.py bind-zone --camera-id cam1 --zone-id A1 --state unknown --dry-run
```

Bạn phải kiểm tra:

- API nào được chọn
- payload business field là gì
- `occupied` có ra `indBind=1` không
- `empty` có ra `indBind=0` không
- `unknown` có sinh `lockPosition(indBind=0)` không

Pass khi:

- đúng hoàn toàn theo mapping đã chốt

Với zone thang máy dùng `method=lockPosition`, kỳ vọng phải là:

- `occupied` -> dispatch `lock:disable`
- `empty` -> dispatch `lock:enable`
- `unknown` -> dispatch `lock:disable`

### BƯỚC 6 - Test bridge dry-run từ backend thật

Mục tiêu:

- xác nhận luồng Vision thật -> bridge thật là đúng

Thiết lập:

- `enabled=true`
- `dry_run=true`

Chạy:

```bash
python mainProcess.py
```

Kiểm tra:

- log console
- `outputs/runtime/hik_rcs/bridge_state.json`

Pass khi:

- zone đổi trạng thái thì bridge sinh dispatch đúng
- không có bind/unbind sai logic
- `unknown` được xử lý đúng fail-safe

### BƯỚC 7 - Test request thủ công tới HIK thật

Mục tiêu:

- xác nhận endpoint, auth, path đều đúng

Ưu tiên test theo thứ tự:

```bash
python tools/hik_rcs_cli.py query-task --task-code TASK-001
python tools/hik_rcs_cli.py query-agv --map-short-name test
python tools/hik_rcs_cli.py lock-position --position-code P-A1 --action disable
python tools/hik_rcs_cli.py lock-position --position-code P-A1 --action enable
```

Nếu bên HIK cung cấp payload mẫu:

```bash
python tools/hik_rcs_cli.py call-rpc genAgvSchedulingTask payload.json
```

Nếu bài toán pallet chưa rõ `ctnrCode`, có thể dùng thêm:

```bash
python tools/hik_rcs_cli.py probe-bin --ctnr-typ 1 --stg-bin-code 00000101501013 --position-code P-A1
```

Ý nghĩa:

- nếu probe bind thành công rồi unbind lại ngay: bin đang rỗng
- nếu response báo `has bind container code ...`: bin đang được bind với container code đó
- đây là một kỹ thuật thực dụng để truy vết trạng thái container khi UI chưa cho thấy rõ

Pass khi:

- không lỗi auth
- không lỗi path
- response hợp lệ

Nếu các lệnh này chưa pass, tuyệt đối chưa chuyển sang bind live.

### BƯỚC 8 - Test live 1 zone duy nhất

Mục tiêu:

- thu hẹp rủi ro

Thiết lập:

- chỉ 1 mapping `enabled=true`
- `dry_run=false`

Chạy backend:

```bash
python mainProcess.py
```

Kiểm tra:

- `outputs/runtime/hik_rcs/http_exchange.jsonl`
- `outputs/runtime/hik_rcs/bridge_state.json`
- callback files
- trạng thái thực tế trên UI RCS
- hành vi thực tế của AGV/AMR nếu có liên động

Pass khi:

- request đi đúng endpoint
- payload đúng business code
- response thành công
- callback nếu có thì quay về đúng
- RCS/AGV phản ứng đúng nghiệp vụ

### BƯỚC 9 - Mở rộng từng zone còn lại

Sau khi zone đầu tiên pass:

1. Bật thêm 1 mapping nữa
2. Test lại đủ 3 tình huống:
   - `occupied`
   - `empty`
   - `unknown`
3. Ghi biên bản

Không được bật toàn bộ zone cùng lúc ở lần đầu.

### BƯỚC 10 - Nghiệm thu toàn luồng

Cần test các tình huống:

- có hàng
- không có hàng
- che camera
- camera mất kết nối
- restart backend
- callback về
- request fail rồi retry

---

## 11. Checklist riêng cho callback

Phải chốt rõ 5 câu hỏi:

1. RCS gọi callback về host nào của Vision?
2. RCS gọi vào base path nào?
3. RCS có gửi `tokenCode` và `clientCode` không?
4. RCS có dùng cả 3 callback hay chỉ một phần?
5. Firewall có chặn port callback không?

### 11.1 Đường callback mà code hiện tại hỗ trợ

Code hiện tại chấp nhận các endpoint:

- `/service/rest/agvCallbackService/agvCallback`
- `/service/rest/agvCallbackService/warnCallback`
- `/service/rest/agvCallbackService/bindNotify`

Ngoài ra, code cũng chấp nhận biến thể base path cấu hình theo:

- `/service/rest`
- hoặc `/service/rest/agvCallbackService`

Điều này giúp tương thích với nhiều cách cấu hình trên site.

---

## 12. Quy tắc pass/fail cho từng tình huống

### 12.1 Tình huống `occupied`

Kỳ vọng:

- Vision ra `state=occupied`
- bridge chọn đúng API business
- request có `indBind=1`
- response thành công

### 12.2 Tình huống `empty`

Kỳ vọng:

- Vision ra `state=empty`
- bridge chọn đúng API business
- request có `indBind=0`
- response thành công

### 12.3 Tình huống `unknown`

Kỳ vọng:

- Vision ra `state=unknown`
- bridge không bind/unbind mù
- nếu cấu hình fail-safe:
  - gọi `lockPosition(indBind=0)`

### 12.4 Tình huống callback

Kỳ vọng:

- callback file được tạo
- route callback đúng
- payload callback lưu lại được

### 12.5 Tình huống request lỗi

Kỳ vọng:

- request/response được log
- không spam liên tục
- retry theo `retry_interval_sec`

---

## 13. Cách đọc log và bằng chứng commissioning

### 13.1 `outputs/runtime/agv_latest.json`

Dùng để xác nhận:

- output Vision nội bộ
- state zone hiện tại

### 13.2 `outputs/runtime/process_latest.json`

Dùng để xác nhận:

- snapshot backend tổng quát hơn

### 13.3 `outputs/runtime/hik_rcs/bridge_state.json`

Dùng để xác nhận:

- zone nào đã dispatch
- `req_code` cuối cùng
- response cuối cùng
- `bound_state`
- `lock_state`

### 13.4 `outputs/runtime/hik_rcs/http_exchange.jsonl`

Dùng để xác nhận:

- request thật đã gửi đi chưa
- gửi tới URL nào
- payload thực tế là gì
- response HIK ra sao

### 13.5 `outputs/runtime/hik_rcs/callbacks/`

Dùng để xác nhận:

- callback có quay về không
- route nào đã được gọi
- payload callback là gì

---

## 14. Những lỗi thường gặp và cách nghĩ đúng để xử lý

### 14.1 Vision đúng nhưng HIK không phản ứng

Đừng kết luận ngay là lỗi code.

Hãy kiểm tra theo đúng thứ tự:

1. mapping có đúng business code không
2. API method đã chọn có đúng use-case không
3. auth có đúng không
4. path có đúng không
5. callback có về không
6. scheduling rule phía RCS có cho phép không

### 14.2 `unknown` xuất hiện nhiều

Hãy kiểm tra:

- camera rung
- ánh sáng thay đổi
- ROI sai
- ngưỡng score quá cao
- camera health không ổn định

Không được tự động coi `unknown` như `empty`.

### 14.3 Query được nhưng bind không thành công

Điều này thường có nghĩa:

- kết nối và auth có thể đã đúng
- nhưng mapping nghiệp vụ còn sai

Tức là vấn đề không nằm ở HTTP client, mà nằm ở business code hoặc method.

### 14.4 Callback không về

Hãy kiểm tra:

- callback server có đang chạy không
- RCS có gọi đúng base path không
- port callback có mở không
- firewall Windows có chặn không
- token/client callback có khớp không

---

## 15. Tiêu chí để được phép kết luận “đủ điều kiện live”

Chỉ được phép nói hệ thống đã đủ điều kiện khi đồng thời đạt tất cả điều kiện sau:

1. Vision detect đúng ngoài hiện trường.
2. Bảng mapping đã được xác nhận.
3. Callback test pass.
4. Dry-run pass.
5. Test manual `query` và `lockPosition` pass.
6. Ít nhất 1 zone live pass.
7. Có log request/response/callback làm bằng chứng.
8. AGV/RCS phản ứng đúng nghiệp vụ.

Thiếu bất kỳ điều kiện nào, chưa được phép kết luận là production-ready.

---

## 16. Quy trình thao tác chuẩn để mang ra hiện trường

Đây là phiên bản checklist ngắn gọn nhất để mang theo khi đi site:

1. Xác nhận camera online.
2. Xác nhận output Vision đúng.
3. Xác nhận host/port RCS.
4. Xác nhận `client_code` và `token_code`.
5. Mở UI RCS, chốt business code thật.
6. Lập bảng mapping.
7. Sửa `configs/hik_rcs.json`.
8. Bật callback server.
9. Test callback.
10. Bật bridge ở `dry_run=true`.
11. Test `bind-zone` cho 1 zone bằng CLI.
12. Chạy backend dry-run với camera thật.
13. Test `query-task`, `query-agv`, `lock-position`.
14. Chuyển `dry_run=false` cho 1 mapping duy nhất.
15. Test live 1 zone.
16. Kiểm tra log, callback, UI RCS và hành vi AGV.
17. Mở rộng từng zone.
18. Test `unknown`.
19. Test restart backend.
20. Lập biên bản nghiệm thu.

---

## 17. Kết luận thực chiến cuối cùng

Phần code của dự án này đã sẵn sàng cho tích hợp về mặt kỹ thuật.

Muốn triển khai thành công ngoài hiện trường, bạn không cần nghĩ bài toán là “làm sao viết thêm giao thức truyền thông”.

Bạn phải nghĩ đúng bài toán là:

- zone nào
- object nào
- mã business nào
- API nào
- auth nào
- callback nào
- test theo thứ tự nào

Nếu bạn đi đúng toàn bộ trình tự trong tài liệu này thì giao tiếp giữa Vision và HIK RCS sẽ không còn là một vùng mơ hồ nữa, mà trở thành một quy trình commissioning có thể kiểm soát, có thể kiểm chứng và có thể hoàn thành.
