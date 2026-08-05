# App Caller API Contract - Vision Auto Dispatch

Tài liệu cho team PDA/Third-party tích hợp với Vision.

Phạm vi:

- Chuyển mode vận hành Vision.
- Lấy trạng thái vận hành Vision.
- Query đúng AGV status nếu cần.
- Query đúng task do Vision tạo ra.

## 1. Base URL

```text
http://192.168.10.44:2113/service/rest/visionAutoDispatch
```

Luu y:

- Vision API chi cho phep cac IP nam trong allowlist.
- Muon them thiet bi moi, cap nhat `configs/auto_dispatch.json` -> `api_server.allowlist`.
- Neu IP client khong nam trong allowlist, request bi tra `403 forbidden by allowlist`.

## 2. Các API cung cấp

1. `GET /health`
2. `GET /status`
3. `POST /getStatus`
4. `POST /setMode`
5. `POST /queryAgvStatus`
6. `POST /queryTaskStatus`

## 3. API detail

### 3.1 Health

Mục đích: Kiểm tra service Vision auto dispatch có đang online hay không.

Request:

```http
GET /service/rest/visionAutoDispatch/health
```

Response:

```json
{
  "code": "0",
  "message": "successful",
  "reqCode": "",
  "reqTime": "YYYY-MM-DD HH:MM:SS",
  "data": {
    "service": "auto_dispatch",
    "status": "online"
  }
}
```

### 3.2 Status

Mục đích: Lấy trạng thái vận hành hiện tại của Vision.

Request:

```http
GET /service/rest/visionAutoDispatch/status
```

Hoặc:

```http
POST /service/rest/visionAutoDispatch/getStatus
```

Response mẫu:

```json
{
  "code": "0",
  "message": "successful",
  "reqCode": "REQ_001",
  "reqTime": "YYYY-MM-DD HH:MM:SS",
  "data": {
    "enabled": true,
    "dry_run": false,
    "control": {
      "operation_mode": "auto",
      "profile_id": "PK_AB"
    },
    "state": {
      "status": "waiting_task:...",
      "active_task": {},
      "batch": {}
    },
    "allowed_profiles": ["PK_AB", "PK_CD"],
    "require_bind_notify": true,
    "require_canonical": true,
    "callback_server_enabled": true
  }
}
```

### 3.3 Set Mode

Mục đích: Chuyển mode vận hành Vision.

Mode hợp lệ:

- `manual`
- `auto` + `PK_AB`
- `auto` + `PK_CD`

Request dùng cho `manual`:

```json
{
  "reqCode": "REQ_MANUAL_001",
  "operation_mode": "manual",
  "profile_id": "PK_AB",
  "updated_by": "third_party",
  "note": "pause auto"
}
```

Request dùng cho `auto + PK_AB`:

```json
{
  "reqCode": "REQ_AUTO_AB_001",
  "operation_mode": "auto",
  "profile_id": "PK_AB",
  "updated_by": "third_party",
  "note": "start auto PK_AB"
}
```

Request dùng cho `auto + PK_CD`:

```json
{
  "reqCode": "REQ_AUTO_CD_001",
  "operation_mode": "auto",
  "profile_id": "PK_CD",
  "updated_by": "third_party",
  "note": "start auto PK_CD"
}
```

Response thành công:

```json
{
  "code": "0",
  "message": "successful",
  "reqCode": "REQ_AUTO_AB_001",
  "reqTime": "YYYY-MM-DD HH:MM:SS",
  "data": {
    "accepted": true,
    "reason": "ok",
    "control": {
      "operation_mode": "auto",
      "profile_id": "PK_AB",
      "updated_by": "third_party",
      "note": "start auto PK_AB"
    },
    "state": {}
  }
}
```

Response lỗi:

```json
{
  "code": "CONFIG_ERROR",
  "message": "profile_id must be one of ['PK_AB', 'PK_CD']",
  "reqCode": "REQ_BAD_001",
  "reqTime": "YYYY-MM-DD HH:MM:SS",
  "data": {
    "accepted": false,
    "reason": "profile_id must be one of ['PK_AB', 'PK_CD']"
  }
}
```

### 3.4 Query AGV Status

Mục đích: Query trạng thái AGV.

Request:

```json
{
  "reqCode": "REQ_QUERY_AGV_001",
  "agvCode": "16675"
}
```

Lưu ý:

- API này dùng để lấy trạng thái AGV.
- Không dùng API này để quyết định sinh task auto.

Response:

- Vision trả về payload query AGV từ RCS.
- `reqCode` va `reqTime` đc Vision bổ sung nếu thiếu.

### 3.5 Query Task Status

Mục đích: Query đúng task do Vision tạo ra.

Request:

```json
{
  "reqCode": "REQ_QUERY_TASK_001",
  "taskCode": "QUANGPROPKAA5FGBB220260731080000",
  "agvCode": "16675"
}
```

Quy tắc bắt buộc:

- Phải truyền `taskCode`.
- Task phải là task do Vision tạo ra.
- Không dùng task của AGV ngoài phạm vi Vision để sinh task tiếp theo.

Response:

- Vision trả về trạng thái của đúng task này.
- Nếu task đã completed (9), state của Vision sẽ cho phép sinh task tiếp theo nếu điều kiện PK/FG vẫn hợp lệ.

## 4. Rule chuyển mode

### 4.1 Dừng mode

1. App Caller gọi `setMode` với `operation_mode = manual`.
2. Nếu response `code = 0`, Vision sẽ ghi control state mới.
3. Trong chu kỳ sync tiếp theo, Vision dừng tạo task auto mới.

### 4.2 Bật auto PK_AB

1. App Caller gọi `setMode` với `operation_mode = auto`, `profile_id = PK_AB`.
2. Nếu response `code = 0`, Vision áp dụng auto PK_AB.
3. Vision chỉ tạo task khi PK_AB đủ 8/8 pallet và FG còn slot EMPTY.

### 4.3 Bật auto PK_CD

1. App Caller gọi `setMode` với `operation_mode = auto`, `profile_id = PK_CD`.
2. Nếu response `code = 0`, Vision áp dụng auto PK_CD.
3. Vision chỉ tạo task khi PK_CD đủ 7/7 pallet và FG còn slot EMPTY.

### 4.4 Thứ tự vận hành

1. Kiểm tra `GET /health`.
2. Kiểm tra `GET /status`.
3. Gọi `POST /setMode`.
4. Kiểm tra lại `GET /status`.
5. Nếu auto đang bật, Vision sẽ:
   - tạo task đầu tiên,
   - query đúng task đó,
   - khi task completed thì tạo task tiếp theo nếu còn đủ điều kiện.

## 5. Payload task Vision tạo ra

Task Vision tạo ra có dạng:

```json
{
  "interfaceName": "genAgvSchedulingTask",
  "taskTyp": "QUANGPRO",
  "taskCode": "QUANGPROPKAA5FGBB220260731080000",
  "data": {
    "from": "PK_AA5",
    "to": "FG_BB2"
  },
  "userCallCodePath": ["11${06}", "2${02}"],
  "ctnrTyp": "2"
}
```

Quy ước taskCode:

- Không có dấu `_`. (một cái rất ngu của HIK mà Vision đã phát hiên ra trong quá trình test ~~)
- Dịnh dạng: `QUANGPRO` + `source` + `dest` + `YYYYMMDDHHMMSS`.

## 6. Phản hồi cần nhớ

- `manual`: chỉ bind/unbind, không sinh task mới. (Phase 1)
- `auto + PK_AB`: chỉ sinh batch PK_AB.
- `auto + PK_CD`: chỉ sinh batch PK_CD.
- Vision chỉ theo dõi đúng taskCode do chính Vision tạo ra.
- Task ngoài phạm vi Vision không ảnh hưởng đến việc sinh task tiếp theo.
