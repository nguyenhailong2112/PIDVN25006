# Tai lieu logic ky thuat - Vision AGV Auto Dispatch

Tai lieu nay mo ta dung chuong trinh local hien tai cua du an `PIDVN25006`. Muc tieu la giup dev/ky su trien khai nam ro logic van hanh Phase 1 manual, Phase 2 auto, giao tiep Vision - RCS, API PDA/third-party, log va cach audit.

## 1. Tong quan he thong

Runtime chinh la `mainProcess.py`.

Khi khoi dong, `CentralBackendRuntime` thuc hien:

1. Load cau hinh camera, rule, ingest, runtime.
2. Khoi tao camera reader va YOLO inference.
3. Chuyen ket qua detection thanh trang thai zone `occupied`, `empty`, `unknown`.
4. Export snapshot runtime ra `outputs/runtime`.
5. Khoi tao `HikRcsBridge` tu `configs/hik_rcs.json`.
6. Khoi tao AMR `AutoDispatcher` tu config merge `configs/auto_dispatch.json` + `configs/auto_dispatch_amr.json`.
7. Khoi tao FMR `AutoDispatcher` tu config merge `configs/auto_dispatch.json` + `configs/auto_dispatch_fmr.json`.
8. Moi chu ky runtime, dong bo:
   - camera payload -> HIK RCS bind/unbind
   - camera payload + bridge state -> AMR auto dispatch task
   - camera payload + bridge state -> FMR auto dispatch task

Luon co 2 lop logic tach rieng:

- `HikRcsBridge`: quan ly bind/unbind, bindNotify, lock/block theo tung diem hang.
- AMR `AutoDispatcher`: quan ly mode manual/auto cho pallet PK -> FG, tao task `QUANGPRO`, query dung task Vision tao.
- FMR `AutoDispatcher`: quan ly mode manual/auto cho trolley 3T -> COIL, tao task `FMR2`, query dung task Vision tao.

## 2. Cau hinh quan trong

### 2.1 HIK RCS

File: `configs/hik_rcs.json`

Gia tri local hien tai:

- `enabled = true`
- `dry_run = false`
- RCS host: `192.168.10.38`
- RPC port: `8182`
- Callback bindNotify port Vision: `2112`
- Callback base path: `/service/rest`
- Tong mapping enabled: 56
- Mapping `bindCtnrAndBin`: 52
- Mapping `blockArea`: 4
- Tat ca mapping `bindCtnrAndBin` dang dung `dispatch_policy = hybrid_canonical`

### 2.2 Auto dispatch config chung

File: `configs/auto_dispatch.json`

Day la config nen dung chung cho tat ca lane auto dispatch. Khi runtime khoi dong, Vision doc:

```text
configs/auto_dispatch.json + configs/auto_dispatch_amr.json -> AMR config hoan chinh
configs/auto_dispatch.json + configs/auto_dispatch_fmr.json -> FMR config hoan chinh
```

Quy tac merge:

- Field object/dict duoc merge de lane co the override tung field con.
- Field list/string/number/bool cua lane se thay the gia tri chung.
- File lane rieng chi nen chua thong tin dac thu cua lane do.

Gia tri chung hien tai:

- `enabled = true`
- `dry_run = false`
- default `operation_mode = manual`
- `require_bind_notify = true`
- `require_canonical = true`
- query interval: `5.0` giay
- default query task co gui `agvCode`: `query_task_include_agv_code = true`
- completed statuses: `completed`, `complete`, `finish`, `finished`, `ended`, `success`, `9`
- failed statuses: `failed`, `fail`, `cancel`, `canceled`, `cancelled`, `abort`, `aborted`
- API server port: `8023`
- API base path: `/service/rest/visionAutoDispatch`
- IP allowlist hien tai: `192.168.10.105`
- task API mac dinh: `genAgvSchedulingTask`

### 2.3 AMR auto dispatch

File rieng: `configs/auto_dispatch_amr.json`

Gia tri local hien tai:

- `dispatcher_id = amr`
- default `profile_id = PK_AB`
- control file: `outputs/runtime/auto_dispatch_amr/mode_control.json`
- query AGV code: `16675`
- task type: `QUANGPRO`
- task code prefix: `QUANGPRO`
- ctnr type: `2`
- routing/source/destination/positions/profiles cua pallet PK -> FG

Neu PC Vision tai site la `192.168.10.44`, App Caller/PDA goi:

```text
http://192.168.10.44:8023/service/rest/visionAutoDispatch/amr
```

Route AMR cu khong co `/amr` van duoc giu de tuong thich:

```text
http://192.168.10.44:8023/service/rest/visionAutoDispatch
```

### 2.4 FMR auto dispatch

File rieng: `configs/auto_dispatch_fmr.json`

Gia tri local hien tai:

- `dispatcher_id = fmr`
- default `profile_id = 3T_COIL`
- control file: `outputs/runtime/auto_dispatch_fmr/mode_control.json`
- query AGV code: `10476`
- FMR query task khong gui `agvCode`, chi gui `taskCodes` cua task Vision tao
- task type: `FMR2`
- task code prefix: `FMR2`
- ctnr type: `3`
- genTask co `robotCode = 10476`
- routing/source/destination/positions/profiles cua trolley 3T -> COIL
- API namespace: `/service/rest/visionAutoDispatch/fmr`

FMR khong mo port API rieng. FMR duoc dang ky vao cung API server cua AMR tren port `8023`, nhung state, batch, active task va control file hoan toan tach rieng.

## 3. Phase 1 - Logic mode manual

### 3.1 Muc tieu

Mode `manual` la phase ban dau va la mode an toan. Trong mode nay:

- Vision van chay camera, inference, zone reasoning.
- Vision van dong bo bind/unbind voi RCS.
- Vision khong tao task AGV moi.
- AGV neu can chay se duoc goi tu RCS/PDA/quy trinh ngoai Vision.

### 3.2 Dieu kien vao manual

Vision duoc coi la manual khi `operation_mode` khac `auto` trong control runtime.

Nguon control:

1. Mac dinh tu config sau merge cua tung lane: file chung `configs/auto_dispatch.json` + file rieng `configs/auto_dispatch_amr.json` hoac `configs/auto_dispatch_fmr.json`.
2. Neu ton tai, doc tu control file rieng cua tung lane: `outputs/runtime/auto_dispatch_amr/mode_control.json` hoac `outputs/runtime/auto_dispatch_fmr/mode_control.json`.
3. PDA/third-party co the ghi control moi qua API `setMode`.

Payload chuyen ve manual:

```json
{
  "reqCode": "REQ_MANUAL_001",
  "operation_mode": "manual",
  "profile_id": "PK_AB",
  "updated_by": "third_party",
  "note": "switch to manual"
}
```

### 3.3 Hanh vi trong manual

Trong `AutoDispatcher.sync()`:

- Neu mode khong phai `auto`, dispatcher set status `manual_mode`.
- Dispatcher xoa `batch` noi bo neu co.
- Dispatcher khong tao task AGV.

Trong `HikRcsBridge.sync()`:

- Van xu ly tat ca mapping enabled.
- Van danh gia tung zone theo trang thai Vision.
- Van goi RCS bind/unbind/lock/block neu can.
- Van luu state vao `outputs/runtime/hik_rcs/bridge_state.json`.

### 3.4 Bind/unbind trong manual

Tat ca diem hang `bindCtnrAndBin` dang dung `hybrid_canonical`.

Y nghia:

- Khi Vision thay vi tri `occupied`, RCS phai co bind canonical dung voi `ctnr_code` cau hinh cua vi tri do.
- Khi Vision thay vi tri `empty`, Vision unbind container dang biet khoi bin do.
- Neu RCS dang co container khac o bin hien tai, Vision uu tien reconcile ve canonical.
- Neu `bindNotify` tra ve container/bin, Vision dung hint nay de cap nhat session va tranh bind sai.

Vi du mapping PK:

```json
{
  "camera_id": "cam4",
  "zone_id": "A1",
  "method": "bindCtnrAndBin",
  "dispatch_policy": "hybrid_canonical",
  "position_code": "PK_AA1",
  "stg_bin_code": "A0000103501013",
  "ctnr_code": "PK_AA1",
  "ctnr_typ": "2"
}
```

Neu zone `cam4:A1` occupied, canonical container la `PK_AA1`.

## 4. Cach van hanh manual cho Vision va AGV

### 4.1 Khoi dong

Windows:

```bat
run_forever.cmd
```

Linux:

```bash
./run_forever.sh
```

Supervisor se khoi dong:

- Backend: `mainProcess.py`
- Frontend CCTV: `mainCCTV.py`

### 4.2 Kiem tra manual

Goi status:

```http
GET /service/rest/visionAutoDispatch/status
```

Hoac:

```http
POST /service/rest/visionAutoDispatch/getStatus
```

Ky vong:

- `control.operation_mode = manual`
- `state.status = manual_mode`
- Khong co `active_task` moi do Vision tao

### 4.3 Van hanh AGV trong manual

Vision khong tao task. Neu can AGV chay, su dung RCS/PDA/quy trinh ngoai Vision theo thiet lap site.

Vision van giu vai tro:

- Kiem tra occupied/empty.
- Dong bo storage bin/container voi RCS.
- Ghi log de audit khi co sai lech.

## 5. Phase 2 AMR - Logic mode auto

Day la phan quan trong nhat.

Mode auto co 2 profile:

- `auto + PK_AB`
- `auto + PK_CD`

PDA/third-party phai goi API `setMode` de chuyen Vision sang auto.

### 5.1 Dieu kien chung de tao task

Vision chi tao task khi tat ca dieu kien sau dung:

1. `operation_mode = auto`
2. `profile_id` la `PK_AB` hoac `PK_CD`
3. Callback bindNotify dang enabled trong `configs/hik_rcs.json`
4. PK profile du so luong pallet yeu cau
5. FG co it nhat 1 vi tri `empty`
6. Khong co `active_task` dang chay
7. Source pick tiep theo dat bind guard
8. Destination put tiep theo dat bind guard

### 5.2 Profile PK_AB

Source order:

```text
PK_AA5 -> PK_AA3 -> PK_AA2 -> PK_AA1 -> PK_BB4 -> PK_BB3 -> PK_BB2 -> PK_BB1
```

Dieu kien bat dau batch:

- 8/8 vi tri tren occupied.
- FG co it nhat 1 vi tri empty.

Roadway call code:

- Hang A: `11${06}`
- Hang B: `22${06}`

### 5.3 Profile PK_CD

Source order:

```text
PK_CC3 -> PK_CC2 -> PK_CC1 -> PK_DD4 -> PK_DD3 -> PK_DD2 -> PK_DD1
```

Dieu kien bat dau batch:

- 7/7 vi tri tren occupied.
- FG co it nhat 1 vi tri empty.

Roadway call code:

- Hang C: `33${06}`
- Hang D: `44${06}`

### 5.4 Destination FG

FG la area, call code:

```text
2${02}
```

FG observation order:

```text
FG_AA1, FG_AA2, FG_AA3, FG_AA4, FG_AA5, FG_AA6,
FG_BB1, FG_BB2, FG_BB3, FG_BB4, FG_BB5, FG_BB6
```

Vision chi chon cac vi tri FG dang `empty`. Vi tri FG da duoc dung trong batch hien tai se khong duoc chon lai trong cung batch.

### 5.5 Cach tao batch

Khi mode auto va chua co batch phu hop:

1. Vision dem so source occupied trong profile.
2. Neu khong du:
   - status: `waiting_pk_full:<profile>:<count>/<required>`
   - khong tao task
3. Neu du:
   - tao `batch`
   - luu `profile_id`
   - luu `source_order`
   - `dispatched_sources = []`
   - `dispatched_dests = []`
   - log event `batch_started`

### 5.6 Cach tao tung task

Vision moi lan chi tao 1 task.

Task tiep theo duoc tao khi:

- Khong co `active_task`
- Task truoc da completed hoac chua co task
- Batch con source chua dispatch
- Source do van `occupied`
- FG con vi tri `empty`
- Bind guard source va dest deu hop le

Sau khi tao task thanh cong:

- Source duoc them vao `batch.dispatched_sources`
- Dest duoc them vao `batch.dispatched_dests`
- Task duoc luu vao `state.active_task`
- Log event `task_created`

### 5.7 Payload genAgvSchedulingTask

API RCS:

```text
genAgvSchedulingTask
```

Payload mau:

```json
{
  "interfaceName": "genAgvSchedulingTask",
  "taskTyp": "QUANGPRO",
  "taskCode": "QUANGPROPKAA5FGAA120260811080000",
  "data": {
    "from": "PK_AA5",
    "to": "FG_AA1"
  },
  "userCallCodePath": [
    "11${06}",
    "2${02}"
  ],
  "ctnrTyp": "2"
}
```

Quy tac `taskCode`:

```text
QUANGPRO<source_without_underscore><dest_without_underscore><YYYYMMDDHHMMSS>
```

Vi du:

```text
QUANGPROPKAA5FGAA120260811080000
QUANGPROPKCC3FGBB620260811134500
```

Khong dung dau `_` trong `taskCode`.

### 5.8 Query task status

Sau khi tao task, Vision query:

```text
queryTaskStatus
```

Payload:

```json
{
  "taskCodes": ["QUANGPROPKAA5FGAA120260811080000"],
  "agvCode": "16675"
}
```

Vision chi quan tam dung `taskCode` ma Vision vua tao. Neu RCS tra ve danh sach nhieu task, Vision loc dung item co `taskCode` trung khop.

Completed statuses hien tai:

```text
completed, complete, finish, finished, ended, success, 9
```

Failed statuses hien tai:

```text
failed, fail, cancel, canceled, cancelled, abort, aborted
```

Khi task completed:

- `active_task` duoc xoa
- task duoc luu vao `last_completed_task`
- log event `task_completed`
- chu ky sync sau do Vision co the tao task tiep theo trong batch

### 5.9 Khi batch dung

Batch dung khi:

- Destination het slot empty: `stopped_no_destination_empty`
- Source tiep theo khong con occupied: `stopped_source_not_occupied`
- Tat ca source trong batch da dispatch: `batch_completed`
- Bind guard khong dat: `blocked_bind_guard:<reason>`
- Task create failed: `task_create_failed:<taskCode>`

Theo chuong trinh local hien tai, khi batch dung, `batch` bi xoa khoi state. Tuy nhien `operation_mode` trong `mode_control.json` van giu theo lan PDA/API set gan nhat. Neu muon dung auto hoan toan, PDA/API can goi `manual`.

## 6. Phase 2 FMR - Logic auto 3T_COIL

FMR la lane doc lap voi AMR. AMR pallet va FMR trolley co the cung chay trong mot runtime Vision:

- Chung camera payload va HIK bridge.
- Chung RCS client/log HTTP exchange.
- Khong chung `operation_mode`, `profile_id`, `batch`, `active_task`, state file.
- PDA goi `/amr/setMode` de dieu khien AMR, goi `/fmr/setMode` de dieu khien FMR.

### 6.1 Profile 3T_COIL

Source order:

```text
3T_A1 -> 3T_A2 -> 3T_A3
```

Dieu kien bat dau batch:

- 3/3 vi tri source tren occupied.
- COIL co it nhat 1 vi tri empty.
- Bind guard source/destination hop le.

Source roadway call code:

```text
55${06}
```

Destination COIL area call code:

```text
CO1${04}
```

Destination order:

```text
COIL_FF10 -> COIL_FF11 -> COIL_FF12 -> COIL_FF13
```

### 6.2 Payload genAgvSchedulingTask FMR

Payload Vision gui toi RCS gom cac field chinh:

```json
{
  "materialLot": "",
  "robotCode": "10476",
  "userCallCode": "",
  "interfaceName": "genAgvSchedulingTask",
  "taskTyp": "FMR2",
  "taskCode": "FMR23TA1COILFF1020260814110000",
  "userCallCodePath": [
    "55${06}",
    "CO1${04}"
  ],
  "ctnrTyp": "3"
}
```

FMR khong gui field `data.from/to`, de payload gan voi task mau da chay tay tai site.

Quy tac `taskCode`:

```text
FMR2<source_without_underscore><dest_without_underscore><YYYYMMDDHHMMSS>
```

Vi du:

```text
FMR23TA1COILFF1020260814110000
FMR23TA2COILFF1120260814110500
FMR23TA3COILFF1220260814111000
```

### 6.3 Query task FMR

Sau khi tao FMR task, Vision chi query dung task vua tao:

```json
{
  "taskCodes": ["FMR23TA1COILFF1020260814110000"]
}
```

Ly do khong gui `agvCode`: RCS site tra loi loi neu `queryTaskStatus` nhan dong thoi task order va robot code. `robotCode = 10476` chi giu trong `genAgvSchedulingTask` FMR.

Khi RCS tra `taskStatus = 9` hoac mot completed status tuong duong, Vision xoa `active_task` va chu ky sau tao task tiep theo neu dieu kien van hop le.

## 7. Cach van hanh auto cho Vision va AGV

### 7.1 Chuyen sang auto PK_AB

Endpoint:

```http
POST /service/rest/visionAutoDispatch/amr/setMode
```

Payload:

```json
{
  "reqCode": "REQ_AUTO_AB_001",
  "operation_mode": "auto",
  "profile_id": "PK_AB",
  "updated_by": "third_party",
  "note": "start auto PK_AB"
}
```

### 7.2 Chuyen sang auto PK_CD

```json
{
  "reqCode": "REQ_AUTO_CD_001",
  "operation_mode": "auto",
  "profile_id": "PK_CD",
  "updated_by": "third_party",
  "note": "start auto PK_CD"
}
```

### 7.3 Chuyen ve manual AMR

```json
{
  "reqCode": "REQ_MANUAL_001",
  "operation_mode": "manual",
  "profile_id": "PK_AB",
  "updated_by": "third_party",
  "note": "stop auto"
}
```

### 7.4 Chuyen sang auto FMR 3T_COIL

Endpoint:

```http
POST /service/rest/visionAutoDispatch/fmr/setMode
```

Payload:

```json
{
  "reqCode": "REQ_AUTO_FMR_001",
  "operation_mode": "auto",
  "profile_id": "3T_COIL",
  "updated_by": "third_party",
  "note": "start auto FMR 3T_COIL"
}
```

### 7.5 Chuyen ve manual FMR

```json
{
  "reqCode": "REQ_MANUAL_FMR_001",
  "operation_mode": "manual",
  "profile_id": "3T_COIL",
  "updated_by": "third_party",
  "note": "stop auto FMR"
}
```

### 7.6 Response setMode thanh cong

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

### 7.7 IP allowlist

Auto dispatch API chi cho phep IP trong:

```json
"allowlist": ["192.168.10.105"]
```

Neu PDA doi IP, cap nhat allowlist trong `configs/auto_dispatch.json`:

```json
"allowlist": ["192.168.10.105", "192.168.10.106"]
```

Neu request bi chan:

```json
{
  "code": "403",
  "message": "forbidden by allowlist"
}
```

## 8. API Vision cung cap

Base URL site neu PC Vision la `192.168.10.44`:

```text
http://192.168.10.44:8023/service/rest/visionAutoDispatch/amr
http://192.168.10.44:8023/service/rest/visionAutoDispatch/fmr
```

Route legacy AMR van ton tai:

```text
http://192.168.10.44:8023/service/rest/visionAutoDispatch
```

### 8.1 Health

```http
GET /amr/health
GET /fmr/health
```

Dung de kiem tra API online.

### 8.2 Status

```http
GET /amr/status
POST /amr/getStatus
GET /fmr/status
POST /fmr/getStatus
```

Dung de xem:

- `enabled`
- `dry_run`
- `control.operation_mode`
- `control.profile_id`
- `state.status`
- `state.active_task`
- `state.batch`

### 8.3 Set mode

```http
POST /amr/setMode
POST /fmr/setMode
```

Dung cho PDA/third-party chuyen `manual`, `auto + PK_AB`, `auto + PK_CD`, `auto + 3T_COIL`.

### 8.4 Query AGV status

```http
POST /amr/queryAgvStatus
POST /fmr/queryAgvStatus
```

Payload AMR:

```json
{
  "reqCode": "REQ_QUERY_AGV_001",
  "agvCode": "16675"
}
```

Payload FMR:

```json
{
  "reqCode": "REQ_QUERY_FMR_001",
  "agvCode": "10476"
}
```

### 8.5 Query task status

```http
POST /amr/queryTaskStatus
POST /fmr/queryTaskStatus
```

Payload:

```json
{
  "reqCode": "REQ_QUERY_TASK_001",
  "taskCode": "QUANGPROPKAA5FGAA120260811080000",
  "agvCode": "16675"
}
```

API Vision chap nhan `taskCode` de team test goi gon. Khi gui sang RCS, Vision doi thanh `taskCodes: ["<taskCode>"]` theo schema RCS. Neu thieu `taskCode`/`taskCodes`, Vision tra `CONFIG_ERROR`.

## 9. Bind guard truoc khi tao task

Truoc khi tao task, Vision kiem tra bind guard cho:

- source pick: phai `occupied`
- dest put: phai `empty`

Guard dat khi:

1. Co bridge state cua vi tri.
2. `last_seen_state` trung voi trang thai yeu cau.
3. `hybrid_session.needs_reconcile = false`.
4. Neu `require_canonical = true`, policy phai la `hybrid_canonical` hoac `hybrid_fg_canonical`.
5. Neu source occupied co `actual_ctnr_code`, code nay phai trung voi position code.

Ly do block thuong gap:

```text
missing_bridge_state
bridge_state_not_occupied
bridge_state_not_empty
needs_reconcile
not_hybrid_canonical
noncanonical_ctnr:<code>
```

Khi bi block, state dang:

```text
blocked_bind_guard:<position>:<reason>
```

## 10. Trang thai va log can audit

### 10.1 Auto dispatch

```text
outputs/runtime/auto_dispatch_amr/state.json
outputs/runtime/auto_dispatch_amr/events.jsonl
outputs/runtime/auto_dispatch_amr/mode_control.json
outputs/runtime/auto_dispatch_amr/control_api_latest.json
outputs/runtime/auto_dispatch_amr/control_api.jsonl

outputs/runtime/auto_dispatch_fmr/state.json
outputs/runtime/auto_dispatch_fmr/events.jsonl
outputs/runtime/auto_dispatch_fmr/mode_control.json
outputs/runtime/auto_dispatch_fmr/control_api_latest.json
outputs/runtime/auto_dispatch_fmr/control_api.jsonl
```

Y nghia:

- `state.json`: trang thai dispatcher hien tai.
- `events.jsonl`: lich su batch/task.
- `mode_control.json`: mode hien tai do API set.
- `control_api_latest.json`: request/response API moi nhat.
- `control_api.jsonl`: lich su API.

### 10.2 HIK RCS

```text
outputs/runtime/hik_rcs/bridge_state.json
outputs/runtime/hik_rcs/http_exchange.jsonl
outputs/runtime/hik_rcs/callbacks/bindNotify_latest.json
outputs/runtime/hik_rcs/callbacks/bindNotify.jsonl
```

Y nghia:

- `bridge_state.json`: state bind/unbind tung mapping.
- `http_exchange.jsonl`: payload Vision gui toi RCS va response RCS.
- `bindNotify*.json`: callback RCS gui ve Vision.

### 10.3 Runtime camera

```text
outputs/runtime/process_latest.json
outputs/runtime/agv_latest.json
outputs/runtime/cameras/*.json
outputs/runtime/preview/*.jpg
outputs/runtime/debug/*.jpg
```

## 11. Checklist audit khi auto khong tao task

1. Kiem tra `mode_control.json`.
   - `operation_mode` co phai `auto` khong?
   - `profile_id` co dung `PK_AB`, `PK_CD` hoac `3T_COIL` khong?
2. Kiem tra `state.json`.
   - `status` dang la gi?
   - Co `active_task` dang chay khong?
   - Co `batch` dang active khong?
3. Kiem tra source profile.
   - AMR PK_AB phai 8/8 occupied.
   - AMR PK_CD phai 7/7 occupied.
   - FMR 3T_COIL phai 3/3 occupied.
4. Kiem tra destination.
   - Co it nhat 1 vi tri empty khong?
5. Kiem tra bind guard.
   - Source/dest co trong `bridge_state.json` khong?
   - `needs_reconcile` co false khong?
   - `actual_ctnr_code` co canonical khong?
6. Kiem tra RCS exchange.
   - `genAgvSchedulingTask` co duoc gui khong?
   - Response RCS code la `0` hay loi?
7. Kiem tra task status.
   - Vision query dung taskCode chua?
   - RCS tra status completed `9` chua?

## 12. Checklist audit khi bind/unbind sai

1. Mo `configs/hik_rcs.json`, tim mapping theo `camera_id`, `zone_id`.
2. Kiem tra:
   - `method = bindCtnrAndBin`
   - `dispatch_policy = hybrid_canonical`
   - `position_code`
   - `stg_bin_code`
   - `ctnr_code`
   - `ctnr_typ`
3. Mo `bridge_state.json`, tim key:

```text
<camera_id>:<zone_id>:bindCtnrAndBin
```

4. Kiem tra:
   - `last_seen_state`
   - `bound_state`
   - `last_bound_ctnr_code`
   - `hybrid_session.owner`
   - `hybrid_session.actual_ctnr_code`
   - `hybrid_session.needs_reconcile`
   - `bind_dispatch.response`
5. Mo `http_exchange.jsonl`, tim `ctnrCode` hoac `stgBinCode`.
6. Doi chieu RCS Storage Bin Management.

## 13. Cac status auto dispatch can hieu

```text
manual_mode
auto_mode_requested:<profile>
waiting_pk_full:<profile>:<count>/<required>
task_created:<taskCode>
waiting_task:<taskCode>
waiting_task:<taskCode>:<status>
batch_completed
stopped_no_destination_empty
stopped_source_not_occupied
blocked_bind_guard:<reason>
task_create_failed:<taskCode>
```

## 14. Gioi han pham vi hien tai

Theo version local hien tai:

- AMR khong chi dinh diem FG cho RCS theo slot cu the trong route; RCS nhan area FG `2${02}`.
- AMR khong truyen `agvCode` vao `genAgvSchedulingTask`.
- FMR truyen `robotCode = 10476` vao `genAgvSchedulingTask` theo task mau da chay tay tai site.
- AMR dung `agvCode = 16675` khi query task/AGV status.
- FMR dung `agvCode = 10476` khi query AGV status, nhung query task chi gui `taskCodes`.
- Moi lane chi tao 1 task tai 1 thoi diem. AMR va FMR la 2 lane doc lap nen co the cung co task rieng.
- Vision chi quan tam taskCode do Vision tao.
- Vision auto hien tai duoc dieu khien bang API `setMode`; neu muon dung auto, PDA/API can set ve `manual` cho dung lane `amr` hoac `fmr`.
