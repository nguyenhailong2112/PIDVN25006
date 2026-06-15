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

### 2.4 `cancelTask`, `setTaskPriority`, `queryAgvStatus`

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

## 3. Nhung dieu co the cam ket va nhung dieu bat buoc phai chot

Co the cam ket ve kien truc:

- Vision co the chon source/dest dua tren camera state.
- Vision co the tao task qua RCS bang API chinh thuc.
- Vision co the theo doi task bang callback/status.
- Vision co the verify ket qua bang camera truoc khi tao task tiep.
- Vision co the fail-safe neu bat ky dieu kien nao khong chac chan.

Khong duoc cam ket truoc khi AGV/RCS chot:

- `taskTyp` production la gi
- `positionCodePath.type` production la gi
- task PK -> FG qua thang may la mot task duy nhat hay nhieu sub-task
- RCS co tu xu ly elevator task hay can task F06 rieng
- PDA/manual priority chinh xac la bao nhieu
- task bi chan vi Waiting Point lock se pending hay fail
- RCS co tra `taskCode` trong `data` on dinh hay khong

Do do, viec dau tien cua phase 0 la lay request/response mau tu PDA/RCS khi operator tao task thanh cong.

## 4. Source of truth cua Vision

Dispatcher chi doc cac snapshot da qua pipeline on dinh:

- `outputs/runtime/agv_latest.json`
- hoac payload trong memory cua `mainProcess`

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
  "manual_pause_enabled": true,
  "manual_priority": 80,
  "auto_priority": 20,
  "task_template": {
    "api": "genAgvSchedulingTask",
    "taskTyp": "TBD_BY_AGV",
    "path_type_source": "TBD_BY_AGV",
    "path_type_dest": "TBD_BY_AGV",
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
  "fg_put_order": []
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
- submit fail thi release reservation neu chua co task tren RCS
- submit success nhung callback mat thi polling `queryTaskStatus`
- task completed nhung Vision chua verify thi khong tao task tiep
- timeout/fail/cancel/interrupted thi dung dispatcher va yeu cau operator recovery

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
4. Chon source dau tien trong `pk_pick_order` co `state=occupied`.
5. Chon dest dau tien trong `fg_put_order` co `state=empty`.
6. Neu thieu source -> `BLOCKED_NO_SOURCE`.
7. Neu thieu dest -> `BLOCKED_NO_DEST`.
8. Neu co source/dest -> tao candidate.

Khong duoc skip qua source dau tien neu source do `unknown`. Khi mot position trong order bi `unknown`, co 2 policy:

- conservative: dung planner vi khong chac thu tu FILO
- permissive: bo qua unknown va lay position sau

Khuyen nghi production:

- PK dung conservative theo tung hang
- FG co the permissive neu team AGV chap nhan

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

Quy tac taskCode:

- nen de Vision sinh deterministic unique taskCode
- neu RCS bat buoc tu sinh, luu response `data` lam `rcs_task_code`
- sau submit, moi tracking phai dua tren taskCode RCS thuc te

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
5. Neu ca hai dung -> reservation `verified`, tao task tiep.
6. Neu sai -> `operator_recovery_required`.

Khong duoc tao task tiep neu:

- source van occupied
- dest van empty
- source/dest unknown
- camera offline
- bind/unbind RCS chua dong bo

## 14. Mode 3.2 - Semi-auto

Ban chat:

- operator cap quyen mot lan
- Vision chay batch lien tiep den khi het source/dest hop le hoac gap loi

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
4. Tinh candidate source/dest.
5. Neu khong co source/dest -> `BATCH_DONE`.
6. Tao reservation.
7. Submit task.
8. Wait RCS complete.
9. Verify bang Vision.
10. Tang `completed_count`.
11. Neu `completed_count >= max_tasks` -> done.
12. Quay lai buoc 4.

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
4. Neu khong co active reservation -> evaluate.
5. Co candidate -> reserve + submit.
6. Khong co source -> `BLOCKED_NO_SOURCE`.
7. Khong co dest -> `BLOCKED_NO_DEST`.
8. Sau completed -> verify.
9. Verified -> quay lai evaluate.

De tranh tao task lien tuc qua nhanh:

- them `dispatch_cooldown_sec`
- them `max_tasks_per_hour` neu can
- chi cho 1 active task trong phase dau

## 16. Manual priority va pause auto

Manual phai uu tien cao hon auto.

Can co mot co che nhan biet manual active. Cac option:

1. RCS/PDA gui flag manual active cho Vision.
2. Vision query task list/status va thay task khong do Vision tao.
3. AGV adapter ghi file/manual lock.
4. Operator bam pause auto tren GUI/tool.

Chinh sach:

- khi manual active, full-auto khong tao task moi
- semi-auto batch dang chay thi pause sau task hien tai
- khong cancel task auto dang chay neu khong co SOP
- auto priority thap hon manual priority

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

## 18. Chuong trinh can code theo phase

### Phase 0 - Protocol proof

Input can lay tu team AGV/RCS:

- request PDA/RCS mau khi tao task PK -> FG thanh cong
- response RCS mau
- callback `agvCallback` mau cho `start/outbin/end/cancel`
- `taskTyp`
- `positionCodePath.type`
- priority manual/auto
- quy tac task qua thang may

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
- manual pause
- telemetry
- operator recovery UI/tool

Acceptance:

- auto tao task khi co dieu kien
- manual override pause duoc auto
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

### Tracking

- callback start/outbin/end/cancel duoc luu
- queryTaskStatus backup duoc
- timeout dung dispatcher

### Verification

- task completed nhung source/dest sai -> fault
- task completed va source empty/dest occupied -> verified
- verification unknown -> operator recovery

### Semi-auto

- 1 click chay nhieu task
- dung khi FG full
- dung khi PK empty
- dung khi gap fault
- pause/stop hoat dong

### Full-auto

- tu tao task khi co dieu kien
- khong tao task khi manual active
- khong tao task khi RCS/camera/callback unhealthy
- recovery sau fault co SOP

## 21. Request mau de test sau khi AGV chot

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
  "data": "{\"source\":\"vision_auto\",\"mode\":\"semi_auto\",\"reservation_id\":\"R20260615_000001\",\"from\":\"PK_AA4\",\"to\":\"FG_BB6\"}"
}
```

Test CLI:

```bash
python tools/hik_rcs_cli.py call-rpc genAgvSchedulingTask payload.json
python tools/hik_rcs_cli.py query-task --task-code VISION_PK_AA4_TO_FG_BB6_20260615_101530
```

## 22. Ket luan

Phuong an hoan chinh la:

1. Giu manual hien tai lam baseline.
2. Xay planner dry-run truoc, khong goi RCS.
3. Them ledger/reservation truoc khi submit task real.
4. Submit task bang `genAgvSchedulingTask` sau khi co template AGV xac nhan.
5. Theo doi bang callback + query status.
6. Verify bang Vision truoc task tiep theo.
7. Semi-auto production truoc.
8. Full-auto chi bat sau khi semi-auto da on dinh va co manual override ro rang.

Day la cach trien khai chac chan nhat vi moi quyet dinh auto deu co ba lop bao ve:

- Vision state on dinh
- RCS task status/callback
- Vision verification sau task
