# Vision Auto AMR Pallet Dispatch - Specification

## 0. Ket luan thiet ke

Ket luan ky thuat chac chan nhat cho chu trinh ban tu dong va full tu dong:

- RCS van la bo dieu phoi robot.
- Vision khong dieu khien dong co, khong tu di chuyen AMR, khong thay the RCS.
- Vision dong vai tro orchestration layer:
  - doc trang thai PK/FG da qua state tracker
  - chon cap lay/tra theo thu tu nghiep vu
  - reserve source/destination de tranh tao task trung
  - goi RCS tao task bang `genAgvSchedulingTask`
  - theo doi task bang `agvCallback` va/hoac `queryTaskStatus`
  - verify ket qua bang camera truoc khi tao task tiep theo
  - fail-safe khi Vision/RCS/callback khong du tin cay

Khong nen code auto task theo kieu "thay FG empty + PK occupied la goi task ngay". Cach dung phai la state machine co reservation, task ledger, timeout va verification.

Cap nhat sau Phase 1 da nghiem thu:

- Manual bind/unbind hien tai la baseline production, khong duoc pha vo khi them Phase 2.
- FG dang dung policy `hybrid_fg_canonical`: moi pallet vao FG, ke ca do AMR mang tu PK xuong, cuoi cung phai duoc quan ly dang `FG_xx = FG_xx` tren Storage Bin Management.
- Auto dispatcher chi duoc tao task moi khi bridge bind/unbind va canonical FG dang healthy; khong tao task khi FG con dang giu ctnrCode `PK_xx`.
- Elevator interlock/blockArea van la safety gate rieng cua Phase 1; auto dispatcher khong bypass Waiting Point, blockArea, hay logic thang may cua RCS.
- Semi-auto la buoc production dau tien cua Phase 2; full-auto chi bat sau khi semi-auto da on dinh va co manual interlock that.

## 1. Pham vi

Tai lieu nay chi noi ve AMR pallet PK <-> FG.

Bao gom:

- 3.1 Manual hien tai: giu nguyen lam baseline production
- 3.2 Semi-auto: operator click mot lan, Vision tao mot batch task tu PK xuong FG
- 3.3 Full-auto: Vision tu dong tao task khi co source/destination hop le

Khong bao gom trong phase dau:

- FMR trolley auto dispatch
- tu dong dieu khien thang may truc tiep
- tu dong cancel task dang chay khi khong co yeu cau tu RCS/AGV
- dieu khien robot bo qua RCS
- tao nhieu task song song cho nhieu AMR
- tu dong sua Storage Bin Management ngoai logic canonical FG da nghiem thu

## 2. Co so tu tai lieu HIK RCS-2000

Tai lieu tham chieu:

- `UD35865B_RCS-2000 API_Developer Guide_V3.3_20231204(1).pdf`

Nhung API va y nghia can dung:

### 2.1 `genAgvSchedulingTask`

Chuc nang:

- third-party platform tao task
- RCS-2000 ap dung task cho AMR

Endpoint:

```text
POST /rcms/services/rest/hikRpcService/genAgvSchedulingTask
```

Nhung truong chac chan quan trong:

- `reqCode`: bat buoc, lap request thi reqCode phai giong nhau
- `reqTime`: optional
- `clientCode`, `tokenCode`: optional tuy cau hinh auth
- `taskTyp`: bat buoc
- `positionCodePath`: danh sach diem di chuyen, toi da 50 diem
- `positionCodePath[].type`: loai diem
- `positionCodePath[].positionCode`: ma diem
- `priority`: 1..127, so lon hon uu tien cao hon
- `agvCode`: optional, de trong thi RCS tu chon AMR
- `taskCode`: optional, de trong thi RCS tu sinh
- `data`: custom content JSON string

Gia tri task type trong tai lieu:

- `F01`: carry and transfer rack
- `F02`: empty/full rack exchange
- `F03`: carry and transfer by CMR
- `F04`: rack outbound
- `F05`: rotate rack
- `F06`: elevator task
- `F11..F20`: nhom FMR

Gia tri `positionCodePath[].type` quan trong:

- `00`: actual location on map
- `02`: available location of area selection strategy
- `04`: available location in an area
- `05`: bin ID, for FMR/CTU
- `07`: container ID
- `08`: roadway strategy
- `09`: roadway area

Ket luan:

- Auto pallet nen dung `genAgvSchedulingTask`, nhung `taskTyp` va `positionCodePath.type` phai lay tu task PDA/RCS onsite da chay thanh cong.
- Khong duoc tu doan `taskTyp=F01` la production truoc khi team AGV xac nhan.
- Neu `agvCode` de trong, RCS se tu chon AMR; day la mode khuyen nghi ban dau de Vision khong gan sai robot.
- `response.data` co the la task ID RCS sinh ra; dispatcher phai luu ca `taskCode` Vision gui va `rcs_task_code` RCS tra ve.

### 2.2 `queryTaskStatus`

Chuc nang:

- hoi task status theo `taskCodes` hoac `agvCode`

Endpoint:

```text
POST /rcms/services/rest/hikRpcService/queryTaskStatus
```

Trang thai task quan trong:

- `0`: sending exception
- `1`: created
- `2`: executing
- `3`: sending
- `4`: canceling
- `5`: canceled
- `6`: resending
- `9`: completed
- `10`: interrupted

Ket luan:

- Day la co che polling backup neu `agvCallback` bi tre/mat.
- Dispatcher chi verify camera sau khi task vao terminal status `9`, `5`, `10`, hoac callback terminal tuong duong.

### 2.3 `agvCallback`

Chuc nang:

- RCS goi nguoc sang third-party de bao task executing status

Endpoint third-party:

```text
POST /service/rest/agvCallbackService/agvCallback
```

Truong quan trong:

- `method`: `start`, `outbin`, `end`, `cancel`, `ctu`
- `robotCode`
- `taskCode`
- `currentPositionCode`
- `stgBinCode`
- `ctnrCode`, `ctnrTyp`
- `wbCode`

Ket luan:

- `agvCallback(method=end)` la tin hieu manh nhat de chuyen reservation sang phase verify bang Vision.
- `agvCallback(method=cancel)` phai dua dispatcher vao fault/recovery, khong tao task tiep am tham.
- Neu RCS co the gui callback cho tat ca task manual/auto, Vision co the dung `taskCode`/`data` de phan biet task cua Vision va task manual.
- Neu RCS chi gui callback cho task do Vision tao, full-auto bat buoc can mot manual interlock khac tu AGV/RCS/PDA.

### 2.4 `bindNotify` va canonical FG

Chuc nang:

- RCS notify thao tac bind/unbind giua container va bin.

Endpoint third-party dung theo tai lieu:

```text
POST /service/rest/bindNotify
```

Config production hien tai:

```text
http://192.168.10.44:2112/service/rest/bindNotify
```

Truong quan trong:

- `method`: `bindCtnrAndBin`
- `indBind`: `1` bind, `0` unbind
- `bindParam[].ctnrCode`
- `bindParam[].ctnrType` hoac `ctnrTyp`
- `bindParam[].stgBinCode`

Ket luan:

- Auto dispatcher khong chi can Vision state; no con can biet FG da canonical xong hay chua.
- Sau task AMR tu PK xuong FG, RCS Record co the bind tam `FG_xx = PK_xx`; bridge phai canonicalize ve `FG_xx = FG_xx` truoc khi dispatcher tao task tiep.
- `bindNotify` la bang chung tot nhat de biet actual `ctnrCode` va trang thai canonical cua FG.

### 2.5 `cancelTask`, `setTaskPriority`, `queryAgvStatus`, `continueTask`

`cancelTask`:

- dung de cancel task theo `taskCode` hoac `agvCode`
- nguy hiem trong production vi co the lam AMR dat rack/pallet tai vi tri hien tai
- phase dau khong cho Vision tu cancel task, tru khi co SOP ro rang voi AGV

`setTaskPriority`:

- chi co tac dung voi task chua assign AMR
- task da assign thi set priority khong con hieu luc
- auto priority nen duoc set ngay trong request `genAgvSchedulingTask`

`queryAgvStatus`:

- dung monitoring AMR, khong phai nguon chinh de chon PK/FG
- tai lieu khuyen nghi tan suat theo so AMR, voi <100 AMR la 5 giay

`continueTask`:

- chi dung khi task template tren RCS duoc cau hinh co sub-task/can trigger tiep.
- Phase 2 khong tu goi `continueTask` neu chua co flow mau va trigger type do team AGV xac nhan.

## 3. Nhung dieu co the cam ket va nhung dieu bat buoc phai chot

Co the cam ket ve kien truc:

- Vision co the chon source/dest dua tren camera state.
- Vision co the tao task qua RCS bang API chinh thuc.
- Vision co the theo doi task bang callback/status.
- Vision co the verify ket qua bang camera truoc khi tao task tiep.
- Vision co the fail-safe neu bat ky dieu kien nao khong chac chan.
- Vision co the giu thu tu PK/FG bang planner va reservation ledger.
- Vision co the dam bao sau moi task thanh cong, source/dest duoc verify bang camera va FG canonical truoc khi task tiep theo duoc tao.

Khong duoc cam ket truoc khi AGV/RCS chot:

- `taskTyp` production la gi
- `positionCodePath.type` production la gi
- task PK -> FG qua thang may la mot task duy nhat hay nhieu sub-task
- RCS co tu xu ly elevator task hay can task F06 rieng
- PDA/manual priority chinh xac la bao nhieu
- task bi chan vi Waiting Point lock se pending hay fail
- RCS co tra `taskCode` trong `data` on dinh hay khong
- callback `agvCallback` co gui ve cho tat ca task hay chi task do Vision tao
- RCS co endpoint/trang thai nao de biet manual task dang active hay khong
- RCS co cho Vision submit task khi Storage Bin Management dang bi lock boi active task hay khong
- RCS co gioi han rate tao task hay gioi han queue task theo area hay khong

Do do, viec dau tien cua phase 0 la lay request/response mau tu PDA/RCS khi operator tao task thanh cong.

## 4. Source of truth cua Vision

Dispatcher chi doc cac snapshot da qua pipeline on dinh:

- `outputs/runtime/agv_latest.json`
- hoac payload trong memory cua `mainProcess`
- `outputs/runtime/hik_rcs/bridge_state.json`
- `outputs/runtime/hik_rcs/callbacks/bindNotify.jsonl`
- `outputs/runtime/hik_rcs/callbacks/agvCallback.jsonl`

Khong doc raw detection.
Khong doc bbox truc tiep.
Khong suy luan tu frame don le.

Moi zone hop le can co:

- `state`: `occupied` hoac `empty`
- `health`: `online`
- `score >= min_score`
- camera online
- timestamp fresh
- khong co reservation active
- HIK bind/unbind gan nhat khong co loi non-retryable

`unknown` bi loai trong moi truong hop.

Dieu kien rieng cho FG:

- mapping FG phai dang dung `dispatch_policy=hybrid_fg_canonical`
- neu FG `occupied`, bridge state phai biet `last_bound_ctnr_code=FG_xx` hoac `hybrid_session.owner=canonical_fg`
- neu FG vua duoc AMR/RCS bind bang `PK_xx`, dispatcher phai doi bridge canonicalize xong moi xem FG la stable occupied
- neu `hybrid_session.needs_reconcile=true`, dispatcher dung va yeu cau operator/AGV doi chieu Storage Bin Management

Dieu kien rieng cho PK:

- PK source duoc chon khi Vision thay `occupied`, camera fresh, va khong co active reservation
- neu RCS tra loi ctnrCode PK dang bi bind o noi khac, dispatcher dung; day la loi dong bo Storage Bin Management, khong duoc tao task auto

## 5. Scope vi tri va canh bao mapping

Config HIK hien tai dang co 15 vi tri PK va 12 vi tri FG:

PK:

- `PK_AA1`, `PK_AA2`, `PK_AA3`, `PK_AA4`
- `PK_BB1`, `PK_BB2`, `PK_BB3`, `PK_BB4`
- `PK_CC1`, `PK_CC2`, `PK_CC3`
- `PK_DD1`, `PK_DD2`, `PK_DD3`, `PK_DD4`

FG:

- `FG_AA1`, `FG_AA2`, `FG_AA3`, `FG_AA4`, `FG_AA5`, `FG_AA6`
- `FG_BB1`, `FG_BB2`, `FG_BB3`, `FG_BB4`, `FG_BB5`, `FG_BB6`

Phai co file scope chinh xac cu the (mapping Vision - HIK production), vi du:

```json
{
  "pk_pick_order": [
    "PK_AA4", "PK_AA3", "PK_AA2", "PK_AA1",
    "PK_BB4", "PK_BB3", "PK_BB2", "PK_BB1",
    "PK_CC3", "PK_CC2", "PK_CC1",
    "PK_DD4", "PK_DD3", "PK_DD2", "PK_DD1"
  ],
  "fg_put_order": [
    "FG_BB6", "FG_BB5", "FG_BB4", "FG_BB3", "FG_BB2", "FG_BB1",
    "FG_AA6", "FG_AA5", "FG_AA4", "FG_AA3", "FG_AA2", "FG_AA1"
  ]
}
```

## 6. Thu tu lay va tra

PK pick order theo FILO tung hang:

```text
A4 -> A3 -> A2 -> A1
B4 -> B3 -> B2 -> B1
C3 -> C2 -> C1
D4 -> D3 -> D2 -> D1
```

FG put order:

```text
B6 -> B5 -> B4 -> B3 -> B2 -> B1
A6 -> A5 -> A4 -> A3 -> A2 -> A1
```

Nguyen tac:

- moi task chi chon 1 PK source va 1 FG dest
- chi co 1 task active trong dispatcher phase dau
- chi tao task tiep theo sau khi task truoc da completed va Vision verify xong

## 7. Kien truc module de trien khai

De xuat them cac file sau khi code:

- `configs/auto_dispatch.json`
- `core/auto_dispatch_types.py`
- `core/auto_dispatch_planner.py`
- `core/auto_dispatch_runtime.py`
- `core/auto_dispatch_ledger.py`
- `core/hik_rcs_task_client.py` hoac mo rong `HikRcsClient`
- `tools/auto_dispatch_cmd.py`
- `docs/vision_auto_amr_pallet_dispatch_spec_vi.md`

Runtime output:

- `outputs/runtime/auto_dispatch/latest.json`
- `outputs/runtime/auto_dispatch/ledger.json`
- `outputs/runtime/auto_dispatch/events.jsonl`
- `outputs/runtime/auto_dispatch/task_requests.jsonl`

Trach nhiem module:

- `auto_dispatch_planner`: chi tinh candidate, khong goi RCS, khong sua ledger.
- `auto_dispatch_ledger`: tao/luu reservation, dam bao atomic write va replay duoc sau khi restart.
- `auto_dispatch_runtime`: state machine semi/full-auto, dieu phoi planner, task client, callback, verification.
- `hik_rcs_task_client`: dong goi `genAgvSchedulingTask`, `queryTaskStatus`, va sau nay co the them `cancelTask` neu co SOP.
- `auto_dispatch_cmd`: CLI onsite de `plan`, `start-batch`, `pause`, `resume`, `status`, `recover`.

Nguyen tac tich hop voi code hien tai:

- Khong nhung logic auto vao `HikRcsBridge`; bridge tiep tuc chiu trach nhiem bind/unbind/canonical FG.
- Auto dispatcher doc ket qua cua bridge, khong thay bridge gui bind/unbind.
- Neu app restart, ledger phai doc lai active reservation va tiep tuc tracking truoc khi cho tao task moi.

## 8. Cau hinh de xuat

```json
{
  "enabled": false,
  "mode": "disabled",
  "dry_run": true,
  "max_active_tasks": 1,
  "min_zone_score": 0.8,
  "vision_fresh_timeout_sec": 2.0,
  "post_task_verify_timeout_sec": 30.0,
  "task_submit_retry_count": 1,
  "task_submit_retry_interval_sec": 5.0,
  "task_running_timeout_sec": 900.0,
  "poll_task_status_interval_sec": 3.0,
  "dispatch_cooldown_sec": 5.0,
  "max_tasks_per_batch": 12,
  "max_tasks_per_hour": 30,
  "require_bind_notify": true,
  "require_fg_canonical": true,
  "require_manual_interlock": true,
  "manual_pause_enabled": true,
  "manual_interlock_source": "TBD_BY_AGV",
  "manual_priority": 80,
  "auto_priority": 20,
  "task_template": {
    "api": "genAgvSchedulingTask",
    "taskTyp": "TBD_BY_AGV",
    "path_type_source": "TBD_BY_AGV",
    "path_type_dest": "TBD_BY_AGV",
    "include_elevator_points": false,
    "agvCode": "",
    "agvTyp": "",
    "podCode": "",
    "podTyp": "",
    "taskMode": "",
    "materialLot": ""
  },
  "positions": {
    "PK_AA1": {"camera_id": "cam4", "zone_id": "A1"},
    "PK_AA2": {"camera_id": "cam4", "zone_id": "A2"},
    "PK_AA3": {"camera_id": "cam4", "zone_id": "A3"},
    "PK_AA4": {"camera_id": "cam4", "zone_id": "A4"},
    "FG_BB6": {"camera_id": "cam10", "zone_id": "B6"}
  },
  "pk_pick_order": [],
  "fg_put_order": [],
  "unknown_policy": {
    "pk": "conservative_by_row",
    "fg": "conservative"
  }
}
```

`mode` hop le:

- `disabled`
- `semi_auto`
- `full_auto`

## 9. Reservation ledger

Ledger la bat buoc.

Moi record:

```json
{
  "reservation_id": "R20260615_000001",
  "batch_id": "B20260615_000001",
  "req_code": "9f4d2c7e6c3c4c8bb1a9b51c4c8af001",
  "request_hash": "",
  "task_code": "VISION_PK_AA4_TO_FG_BB6_20260615_101530",
  "rcs_task_code": "",
  "mode": "semi_auto",
  "source_position": "PK_AA4",
  "dest_position": "FG_BB6",
  "source_camera_id": "cam4",
  "source_zone_id": "A4",
  "dest_camera_id": "cam10",
  "dest_zone_id": "B6",
  "state": "reserved",
  "created_at": 1781518530.0,
  "submitted_at": 0.0,
  "started_at": 0.0,
  "completed_at": 0.0,
  "verified_at": 0.0,
  "last_task_status": "",
  "last_callback_method": "",
  "last_bind_notify_at": 0.0,
  "source_expected_after": "empty",
  "dest_expected_after": "occupied_canonical",
  "dest_canonical_ctnr_code": "FG_BB6",
  "last_error": "",
  "attempt_count": 0
}
```

State hop le:

- `reserved`
- `submitting`
- `submitted`
- `running`
- `completed_wait_vision_verify`
- `verified`
- `failed`
- `canceled`
- `interrupted`
- `expired`
- `operator_recovery_required`

Quy tac:

- source/dest co reservation active thi khong duoc chon lai
- submit fail thi release reservation chi khi chac chan RCS chua tao task
- submit success nhung callback mat thi polling `queryTaskStatus`
- task completed nhung Vision chua verify thi khong tao task tiep
- timeout/fail/cancel/interrupted thi dung dispatcher va yeu cau operator recovery
- retry submit cung mot logical task phai giu nguyen `reqCode` va `taskCode`
- neu khong biet RCS da tao task hay chua, khong retry bang request moi; chuyen sang `operator_recovery_required`

## 10. Planner

Input:

- snapshot Vision
- config positions/order
- ledger active reservations
- health RCS/callback

Output:

```json
{
  "can_dispatch": true,
  "source": "PK_AA4",
  "dest": "FG_BB6",
  "reason": "ok"
}
```

Algorithm:

1. Build map position -> zone payload.
2. Loai position khong fresh/online/score du.
3. Loai position dang reserved.
4. Loai toan bo dispatcher neu FG canonical bridge dang `needs_reconcile`.
5. Kiem tra manual interlock; neu manual active -> `PAUSED_MANUAL`.
6. Chon source dau tien trong `pk_pick_order` co `state=occupied`.
7. Chon dest dau tien trong `fg_put_order` co `state=empty`.
8. Neu thieu source -> `BLOCKED_NO_SOURCE`.
9. Neu thieu dest -> `BLOCKED_NO_DEST`.
10. Neu co source/dest -> tao candidate.

Khong duoc skip qua source dau tien neu source do `unknown`. Khi mot position trong order bi `unknown`, co 2 policy:

- conservative: dung planner vi khong chac thu tu FILO
- permissive: bo qua unknown va lay position sau

Khuyen nghi production:

- PK dung conservative theo tung hang
- FG dung conservative trong pilot; chi permissive khi team AGV xac nhan thu tu tra FG khong bi anh huong boi slot unknown
- Neu bat ky slot uu tien cao hon dang `unknown`, khong skip im lang trong pilot

## 11. Submit task

Request skeleton:

```json
{
  "taskTyp": "TBD_BY_AGV",
  "positionCodePath": [
    {"type": "TBD_BY_AGV", "positionCode": "PK_AA4"},
    {"type": "TBD_BY_AGV", "positionCode": "FG_BB6"}
  ],
  "priority": "20",
  "agvCode": "",
  "agvTyp": "",
  "taskCode": "VISION_PK_AA4_TO_FG_BB6_20260615_101530",
  "data": "{\"source\":\"vision\",\"mode\":\"semi_auto\",\"reservation_id\":\"R20260615_000001\",\"from\":\"PK_AA4\",\"to\":\"FG_BB6\"}"
}
```

Quy tac reqCode:

- voi retry cung mot request logic, giu cung `reqCode`
- neu tao task moi khac, sinh `reqCode` moi
- luu request/response vao JSONL de audit
- `reqCode` phai duoc luu vao ledger truoc khi gui HTTP
- neu HTTP timeout sau khi gui request, trang thai la `submit_unknown`; khong duoc gui request moi voi `reqCode` moi

Quy tac taskCode:

- nen de Vision sinh deterministic unique taskCode
- neu RCS bat buoc tu sinh, luu response `data` lam `rcs_task_code`
- sau submit, moi tracking phai dua tren taskCode RCS thuc te
- `taskCode` nen co prefix `VISION_` de phan biet voi task PDA/manual trong callback/log
- field `data` nen chua JSON: `source=vision_auto`, `mode`, `reservation_id`, `batch_id`, `from`, `to`

Quy tac submit production:

- Khong submit khi callback server chua healthy neu `require_bind_notify=true`.
- Khong submit khi dang co active reservation.
- Khong submit khi RCS Storage Bin Management dang co loi canonical/duplicate ctnrCode.
- Khong submit khi manual interlock active.
- Khong goi `continueTask`, `cancelTask`, `setTaskPriority` trong loop auto neu chua co SOP.

## 12. Theo doi task

Nguon chinh:

- `agvCallback`

Nguon backup:

- `queryTaskStatus`

Mapping task state:

- callback `start` -> `running`
- callback `outbin` -> `running`
- callback `end` -> `completed_wait_vision_verify`
- callback `cancel` -> `canceled`
- query `taskStatus=1/2/3/6` -> non-terminal
- query `taskStatus=9` -> `completed_wait_vision_verify`
- query `taskStatus=5` -> `canceled`
- query `taskStatus=10` -> `interrupted`
- query `taskStatus=0` -> `failed`

Neu callback va query mau thuan:

- terminal failure thang: `canceled/interrupted/failed`
- neu callback `end` nhung query chua `9`, cho them grace time roi query lai
- neu qua timeout, dung dispatcher

## 13. Vision verification sau task

Sau khi task terminal completed:

1. Cho mot khoang settle time de AMR roi khoi ROI.
2. Doc Vision snapshot.
3. Xac nhan source:
   - `source_position` -> `empty`
4. Xac nhan dest:
   - `dest_position` -> `occupied`
5. Xac nhan bridge/RCS:
   - PK source da unbind hoac khong con bao loi bind/unbind
   - FG dest da canonical thanh `FG_xx = FG_xx`
   - khong co `needs_reconcile`
6. Neu tat ca dung -> reservation `verified`, tao task tiep.
7. Neu sai -> `operator_recovery_required`.

Khong duoc tao task tiep neu:

- source van occupied
- dest van empty
- source/dest unknown
- camera offline
- bind/unbind RCS chua dong bo
- FG dest con actual `ctnrCode=PK_xx`
- callback terminal chua ro task nao neu RCS khong tra taskCode khop ledger

## 14. Mode 3.2 - Semi-auto

Ban chat:

- operator cap quyen mot lan
- Vision chay batch lien tiep den khi het source/dest hop le hoac gap loi
- moi batch co `batch_id` rieng va gioi han `max_tasks_per_batch`
- operator click lan tiep theo tao batch moi, khong noi tiep ngam batch cu

Trigger de xuat:

```json
{
  "command": "start_batch",
  "mode": "semi_auto",
  "max_tasks": 12,
  "requested_by": "PDA_OR_OPERATOR",
  "timestamp": 1781518530.0
}
```

State machine:

- `DISABLED`
- `IDLE`
- `BATCH_ARMED`
- `EVALUATING`
- `RESERVING`
- `SUBMITTING`
- `WAITING_RCS`
- `VERIFYING_VISION`
- `BATCH_DONE`
- `PAUSED`
- `FAULT`

Loop semi-auto:

1. Nhan `start_batch`.
2. Neu dispatcher khong idle -> reject.
3. Neu RCS/Vision/callback khong healthy -> reject.
4. Neu manual interlock bao co task khac dang active -> reject hoac pause.
5. Tinh candidate source/dest.
6. Neu khong co source/dest -> `BATCH_DONE`.
7. Tao reservation.
8. Submit task.
9. Wait RCS complete.
10. Verify bang Vision va FG canonical.
11. Tang `completed_count`.
12. Neu `completed_count >= max_tasks` -> done.
13. Quay lai buoc 5.

Dung batch khi:

- FG full
- PK het pallet
- operator stop/pause
- task canceled/interrupted/failed
- Vision unknown/stale
- RCS HTTP error lien tiep
- callback/query timeout
- manual override active

## 15. Mode 3.3 - Full-auto

Ban chat:

- Vision tu dong lap task khi dieu kien du
- operator chi bat/tat auto va xu ly fault
- bat buoc co manual interlock that truoc khi production
- chi nen pilot sau khi semi-auto da chay on dinh nhieu ngay/nhieu batch

State machine:

- `DISABLED`
- `AUTO_IDLE`
- `EVALUATING`
- `RESERVING`
- `SUBMITTING`
- `TASK_RUNNING`
- `VERIFYING`
- `BLOCKED_NO_SOURCE`
- `BLOCKED_NO_DEST`
- `PAUSED_MANUAL`
- `FAULT`

Loop full-auto:

1. Neu `enabled=false` -> `DISABLED`.
2. Neu manual active -> `PAUSED_MANUAL`.
3. Neu co active reservation -> theo doi reservation.
4. Neu callback/canonical/RCS health khong dat -> `FAULT` hoac `PAUSED_HEALTH`.
5. Neu khong co active reservation -> evaluate.
6. Co candidate -> reserve + submit.
7. Khong co source -> `BLOCKED_NO_SOURCE`.
8. Khong co dest -> `BLOCKED_NO_DEST`.
9. Sau completed -> verify.
10. Verified -> doi cooldown roi quay lai evaluate.

De tranh tao task lien tuc qua nhanh:

- them `dispatch_cooldown_sec`
- them `max_tasks_per_hour` neu can
- chi cho 1 active task trong phase dau

## 16. Manual priority va pause auto

Manual phai uu tien cao hon auto.

Can co mot co che nhan biet manual active. Cac option:

1. RCS/PDA gui flag manual active cho Vision.
2. RCS gui `agvCallback` cho tat ca task, Vision thay task khong co prefix/data cua Vision.
3. AGV adapter ghi file/manual lock.
4. Operator bam pause auto tren GUI/tool.
5. RCS cung cap endpoint/task list rieng de query task active trong area.

Chinh sach:

- khi manual active, full-auto khong tao task moi
- semi-auto batch dang chay thi pause sau task hien tai
- khong cancel task auto dang chay neu khong co SOP
- auto priority thap hon manual priority
- neu chua co manual interlock that, chi cho phep `semi_auto`; `full_auto` phai de `enabled=false`
- manual task dang active nhung Vision khong nhan biet duoc la rui ro production khong chap nhan

## 17. Fail-safe va recovery

Fail-safe trigger:

- camera PK/FG offline
- zone source/dest unknown
- RCS HTTP error lien tiep
- callback server offline
- task status canceled/interrupted/failed
- task running timeout
- Vision verification mismatch
- ledger corrupted
- duplicate active reservation
- FG canonical timeout
- bridge `needs_reconcile=true`
- submit status unknown sau HTTP timeout
- callback taskCode khong khop ledger
- manual interlock mat tin hieu khi full-auto dang enabled
- RCS bao storage bin locked qua thoi gian task cho phep

Fail-safe action:

- dung tao task moi
- giu ledger active
- ghi event JSONL
- xuat snapshot `FAULT`
- yeu cau operator recovery

Operator recovery can co:

- view active reservation
- mark verified manually
- cancel reservation locally
- disable auto
- retry submit neu task chua tao tren RCS
- resume after inspect

SOP recovery toi thieu:

1. Dung auto dispatcher, khong tao task moi.
2. Ghi lai `reservation_id`, `taskCode`, `source`, `dest`, response RCS gan nhat.
3. Kiem tra RCS task status.
4. Kiem tra Storage Bin Management cho source/dest.
5. Kiem tra Vision snapshot source/dest.
6. Neu RCS task chua tao -> cho phep retry submit cung `reqCode`.
7. Neu RCS task da tao/khong chac -> khong retry request moi; operator xu ly tren RCS/PDA.
8. Neu Storage Bin sai -> team AGV/operator sua Storage Bin, sau do clear local reservation co ghi audit.
9. Chi resume khi planner dry-run bao source/dest/order/canonical deu healthy.

## 18. Chuong trinh can code theo phase

### Phase 0 - Protocol proof

Input can lay tu team AGV/RCS:

- request PDA/RCS mau khi tao task PK -> FG thanh cong
- response RCS mau
- callback `agvCallback` mau cho `start/outbin/end/cancel`
- callback `bindNotify` mau khi AMR bind/unbind PK/FG
- `taskTyp`
- `positionCodePath.type`
- priority manual/auto
- quy tac task qua thang may
- cach nhan biet manual task active
- rule RCS khi task bi chan boi `blockArea` elevator

Output:

- file `docs/hik_rcs_auto_dispatch_protocol_notes_vi.md`
- confirmed `auto_dispatch.json`

### Phase 1 - Planner dry-run

Code:

- `auto_dispatch_planner`
- config scope/order
- output candidate JSON

Khong goi RCS.

Acceptance:

- full PK + empty FG -> candidate dung thu tu
- FG full -> no dest
- PK empty -> no source
- unknown trong PK/FG -> dung theo policy

### Phase 2 - Task request dry-run

Code:

- build `genAgvSchedulingTask` payload
- ledger reservation
- dry-run submit
- event log

Khong goi RCS real.

### Phase 3 - RCS integration 1 task

Code:

- goi `genAgvSchedulingTask`
- track `queryTaskStatus`
- nhan `agvCallback`
- verify bang Vision
- doi FG canonical xong

Test 1 cap:

- `PK_AA4 -> FG_BB6`

### Phase 4 - Semi-auto batch

Code:

- command start/stop/pause
- max task per batch
- loop batch

Acceptance:

- 1 click -> chay nhieu task den khi FG full/PK empty
- gap loi -> dung batch

### Phase 5 - Full-auto pilot

Code:

- mode full_auto
- manual interlock
- telemetry
- operator recovery UI/tool

Acceptance:

- auto tao task khi co dieu kien
- manual override pause duoc auto
- manual task active lam auto dung tao task
- fail-safe dung khi co unknown/error

### Phase 6 - Production hardening

Them:

- dashboard status
- alarm/fault report
- backup ledger
- replay/audit tool
- SOP recovery

## 19. Checklist hop voi team AGV/RCS

Bat buoc chot:

1. API tao task co dung `genAgvSchedulingTask` khong?
2. `taskTyp` cho PK -> FG la gi?
3. `positionCodePath.type` source/dest la gi?
4. Path co chi gom PK/FG hay can them Waiting Point/thang may?
5. Task qua thang may la mot task hay nhieu sub-task?
6. RCS co tu xu ly elevator mode trong task khong?
7. Priority manual la bao nhieu?
8. Priority auto nen dat bao nhieu?
9. RCS response `data` co luon la taskCode khong?
10. Callback URL Vision can cau hinh tren RCS la gi?
11. Callback `method` onsite co dung `start/outbin/end/cancel` khong?
12. Khi task failed/canceled/interrupted, operator recovery flow la gi?
13. RCS co endpoint/flag bao manual task active khong?
14. Neu Waiting Point bi lock, task pending hay fail?
15. Gioi han tan suat tao task cua RCS la bao nhieu?
16. Co can chi dinh `agvCode` hay de RCS auto select?
17. Co can `podCode`, `podTyp`, `materialLot`, `taskMode`, `agvTyp` khong?
18. Co the copy/export request payload tu PDA task thanh cong khong?
19. RCS co gui `agvCallback` cho task PDA/manual ve Vision khong?
20. RCS co gui `bindNotify` cho moi `bindCtnrAndBin` record/unbind khong?
21. Khi Vision gui taskCode rieng, RCS co giu nguyen taskCode hay sinh taskCode moi trong `data`?
22. Callback `agvCallback.data` co tra lai custom `data` Vision gui len khong?
23. Khi RCS Record bind `FG_xx = PK_xx`, Vision canonicalize ngay bang unbind/bind co duoc chap nhan trong SOP khong?
24. Trong luc AMR dang thuc hien task, Storage Bin FG bi lock bao lau va khi nao Vision duoc phep canonicalize?
25. Co can set `priority` auto thap hon PDA/manual trong template hay trong request?
26. Neu task submit thanh cong nhung callback mat, `queryTaskStatus` co du thong tin terminal khong?
27. Neu task qua thang may bi blockArea chan, RCS giu task pending, reroute, hay fail?
28. Operator recovery onsite khi auto task fail: ai cancel RCS task, ai clear reservation Vision, ai sua Storage Bin?

## 20. Checklist nghiem thu

### Planner

- dung pick order PK
- dung put order FG
- khong chon zone unknown
- khong chon zone reserved
- khong chon camera offline

### Submit

- payload dung template AGV da chot
- reqCode/taskCode duoc log
- retry khong tao duplicate task
- RCS error duoc ghi ro
- HTTP timeout khong tao task moi voi reqCode moi
- response `data`/taskCode duoc luu de tracking

### Tracking

- callback start/outbin/end/cancel duoc luu
- queryTaskStatus backup duoc
- timeout dung dispatcher
- callback task manual khong lam Vision danh dau nham task auto

### Verification

- task completed nhung source/dest sai -> fault
- task completed va source empty/dest occupied -> verified
- verification unknown -> operator recovery
- dest occupied nhung FG chua canonical -> chua verified
- `needs_reconcile=true` -> fault, khong tao task tiep

### Semi-auto

- 1 click chay nhieu task
- dung khi FG full
- dung khi PK empty
- dung khi gap fault
- pause/stop hoat dong
- click lan hai khi batch dang chay bi reject ro rang

### Full-auto

- tu tao task khi co dieu kien
- khong tao task khi manual active
- khong tao task khi RCS/camera/callback unhealthy
- recovery sau fault co SOP
- khong cho enable production neu `require_manual_interlock=true` nhung chua co manual interlock source

## 21. CLI van hanh Phase 2

Tat ca lenh Phase 2 nam trong:

```bash
python tools/auto_dispatch_cmd.py <command>
```

Lenh audit/kiem tra an toan:

```bash
python tools/auto_dispatch_cmd.py status
python tools/auto_dispatch_cmd.py plan --mode semi_auto
python tools/auto_dispatch_cmd.py plan --mode full_auto
```

Lenh build payload de gui team AGV review, khong submit RCS:

```bash
python tools/auto_dispatch_cmd.py build-task --source PK_AA4 --dest FG_BB6 --mode semi_auto
```

Lenh semi-auto:

```bash
python tools/auto_dispatch_cmd.py start-batch --max-tasks 12 --requested-by operator --tick
python tools/auto_dispatch_cmd.py pause --reason operator --tick
python tools/auto_dispatch_cmd.py resume --tick
python tools/auto_dispatch_cmd.py stop --reason operator --tick
```

Lenh manual interlock cho pilot:

```bash
python tools/auto_dispatch_cmd.py manual-lock --active --reason pda_manual_task
python tools/auto_dispatch_cmd.py manual-lock --inactive --reason manual_done
```

Lenh recovery:

```bash
python tools/auto_dispatch_cmd.py recover --reservation-id <RID> --reason inspect_required
python tools/auto_dispatch_cmd.py mark-verified --reservation-id <RID> --reason operator_checked
python tools/auto_dispatch_cmd.py clear-fault --tick
```

Rule quan trong:

- `build-task` chi tao payload va validation errors, khong tao task RCS.
- `start-batch --tick` chi submit that khi `configs/auto_dispatch.json` co `enabled=true`, `mode=semi_auto`, `dry_run=false`, va task template da het `TBD_BY_AGV`.
- Mac dinh config dang `enabled=false`, `mode=disabled`, `dry_run=true`, nen Phase 1 khong bi anh huong.

## 22. Go/No-Go gates

### Gate A - Duoc phep code planner dry-run

Cho phep code khi:

- Phase 1 manual bind/unbind dang on dinh.
- PK/FG mapping trong `hik_rcs.json` da chot.
- PK pick order va FG put order da chot.
- `hybrid_fg_canonical` dang enabled cho FG.

Chua can:

- task template AGV
- API submit task real
- manual interlock

### Gate B - Duoc phep code task request dry-run

Cho phep code khi co:

- request mau PDA/RCS tao task PK -> FG thanh cong
- response mau cua `genAgvSchedulingTask`
- taskCode/data convention
- priority auto/manual du kien

Van giu `dry_run=true`.

### Gate C - Duoc phep submit 1 task real

Cho phep khi co:

- `taskTyp` production
- `positionCodePath.type` production
- callback `agvCallback` ve Vision
- callback `bindNotify` ve Vision
- SOP khi task fail/cancel/interrupted
- RCS xac nhan task bi blockArea elevator se pending hoac co recovery ro rang

Chi test 1 cap source/dest, 1 active task.

### Gate D - Duoc phep bat semi-auto production

Cho phep khi:

- 1-task real pass nhieu lan lien tiep.
- Verify source empty/dest occupied/canonical FG pass on dinh.
- Timeout/retry/submit_unknown da duoc test.
- Operator co command pause/stop/recover.
- Batch dang chay reject click lan hai ro rang.

### Gate E - Duoc phep bat full-auto pilot

Cho phep khi:

- Semi-auto da on dinh onsite.
- Co manual interlock that tu RCS/PDA/AGV adapter/callback toan cuc.
- Full-auto khong tao task khi manual task active.
- Co SOP recovery duoc team AGV va operator dong y.
- Co dashboard/status de operator nhin duoc ly do `BLOCKED_NO_SOURCE`, `BLOCKED_NO_DEST`, `PAUSED_MANUAL`, `FAULT`.

Neu thieu bat ky dieu kien nao trong Gate E, `full_auto.enabled` phai giu `false`.

## 23. Request mau de test sau khi AGV chot

Vi du chi de test, khong hard-code production:

```json
{
  "taskTyp": "F01",
  "positionCodePath": [
    {"positionCode": "PK_AA4", "type": "00"},
    {"positionCode": "FG_BB6", "type": "00"}
  ],
  "priority": "20",
  "agvCode": "",
  "taskCode": "VISION_PK_AA4_TO_FG_BB6_20260615_101530",
  "data": "{\"source\":\"vision_auto\",\"mode\":\"semi_auto\",\"batch_id\":\"B20260615_000001\",\"reservation_id\":\"R20260615_000001\",\"from\":\"PK_AA4\",\"to\":\"FG_BB6\"}"
}
```

Test CLI:

```bash
python tools/hik_rcs_cli.py call-rpc genAgvSchedulingTask payload.json
python tools/hik_rcs_cli.py query-task --task-code VISION_PK_AA4_TO_FG_BB6_20260615_101530
```

## 24. Ket luan

Phuong an hoan chinh la:

1. Giu manual hien tai lam baseline.
2. Xay planner dry-run truoc, khong goi RCS.
3. Them ledger/reservation truoc khi submit task real.
4. Submit task bang `genAgvSchedulingTask` sau khi co template AGV xac nhan.
5. Theo doi bang callback + query status.
6. Verify bang Vision truoc task tiep theo.
7. Doi FG canonical xong truoc task tiep theo.
8. Semi-auto production truoc.
9. Full-auto chi bat sau khi semi-auto da on dinh va co manual interlock ro rang.

Day la cach trien khai chac chan nhat vi moi quyet dinh auto deu co ba lop bao ve:

- Vision state on dinh
- RCS task status/callback
- Vision verification sau task
- RCS bind/canonical FG dong bo
