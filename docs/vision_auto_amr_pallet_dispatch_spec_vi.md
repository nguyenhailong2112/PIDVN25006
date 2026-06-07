# Vision Auto AMR Pallet Dispatch - Scope va Roadmap

## 1. Muc tieu

Tai lieu nay de xuat huong trien khai Vision dieu lenh AMR pallet tu khu PK xuong khu FG.

Pham vi:

- 3.1 Manual hien tai: giu nguyen
- 3.2 Semi-auto: cong nhan click mot lan tren PDA, Vision/adapter tao chuoi task cho cac cap PK -> FG hop le
- 3.3 Full-auto: Vision tu dong tao task khi PK co pallet va FG con cho trong

Nguyen tac an toan:

- Manual luon uu tien hon auto
- auto mac dinh disabled
- khong tao task khi Vision/RCS/callback khong du tin cay
- `unknown` khong bao gio duoc xem la `empty`
- moi task phai co reservation de tranh tao trung nguon/dich

## 2. He thong hien tai dang co gi

Vision hien tai da lam dung vai tro "con mat" cho AGV:

1. Detect `pallet`.
2. Xac dinh ROI `occupied / empty / unknown`.
3. Bind/unbind len RCS bang `bindCtnrAndBin`.
4. RCS/AGV dung thong tin bind/unbind de quyet dinh co duoc lay/tra pallet hay khong.
5. PDA/operator tao task manual area-to-area.

Day la mode 3.1 va van phai giu lam baseline production.

## 3. Scope vi tri

Theo scope moi cua AMR pallet:

PK sources, 14 vi tri:

- `PK_A1`, `PK_A2`, `PK_A3`, `PK_A4`
- `PK_B1`, `PK_B2`, `PK_B3`, `PK_B4`
- `PK_C1`, `PK_C2`, `PK_C3`
- `PK_D1`, `PK_D2`, `PK_D3`

FG destinations, 12 vi tri:

- `FG_A1`, `FG_A2`, `FG_A3`, `FG_A4`, `FG_A5`, `FG_A6`
- `FG_B1`, `FG_B2`, `FG_B3`, `FG_B4`, `FG_B5`, `FG_B6`

Can audit config hien tai:

- `configs/hik_rcs.json` hien co them cac mapping PK ngoai scope nhu `PK_E1..PK_E4`
- `configs/zones_cam4.json` va `configs/zones_cam5.json` cung co nhieu ROI pallet hon scope 26 diem
- truoc khi code auto, phai chot lai danh sach zone nao duoc auto dispatcher su dung

## 4. Thu tu lay va tra

PK pick order theo FILO tung hang:

```text
PK_A4, PK_A3, PK_A2, PK_A1,
PK_B4, PK_B3, PK_B2, PK_B1,
PK_C3, PK_C2, PK_C1,
PK_D3, PK_D2, PK_D1
```

FG put order:

```text
FG_B6, FG_B5, FG_B4, FG_B3, FG_B2, FG_B1,
FG_A6, FG_A5, FG_A4, FG_A3, FG_A2, FG_A1
```

Eligibility:

- PK source hop le khi state = `occupied`, health = `online`, score >= threshold, khong reserved
- FG destination hop le khi state = `empty`, health = `online`, score >= threshold, khong reserved
- state `unknown` bi loai
- zone stale/camera offline bi loai
- bind/unbind dispatch dang loi thi loai

## 5. Co so API HIK cho auto task

API can dung la `genAgvSchedulingTask`.

Theo tai lieu HIK:

- third-party platform goi `genAgvSchedulingTask` de tao task cho RCS
- `taskTyp` la bat buoc
- F01 la built-in carry and transfer rack
- F06 la elevator task
- F11..F20 la nhom FMR task, khong phai pallet AMR mac dinh
- neu muon chi dinh nhieu vi tri trong task thi dung `positionCodePath`
- `positionCodePath` gom cac phan tu co `type` va `positionCode`
- `priority` co range 1..127, so lon uu tien cao hon
- response `data` co the tra task ID
- `queryTaskStatus` dung de hoi trang thai task
- `agvCallback` la callback RCS gui ve third-party de bao `start/outbin/end/cancel`

Request mau can AGV/RCS xac nhan:

```json
{
  "taskTyp": "TBD_BY_AGV",
  "taskCode": "VISION_PK_A4_TO_FG_B6_YYYYMMDDHHMMSS",
  "positionCodePath": [
    {"type": "00", "positionCode": "PK_A4"},
    {"type": "00", "positionCode": "FG_B6"}
  ],
  "priority": "TBD_BY_AGV",
  "agvCode": "",
  "agvTyp": "",
  "data": "{\"source\":\"vision_auto\",\"mode\":\"semi_auto\",\"from\":\"PK_A4\",\"to\":\"FG_B6\"}"
}
```

Khong duoc hard-code request mau nay thanh production truoc khi AGV/RCS xac nhan:

- `taskTyp` dung voi template area-to-area onsite
- `positionCodePath.type` dung cho PK/FG point
- co can `podCode`, `podTyp`, `materialLot`, `wbCode`, `taskMode` hay khong
- task qua thang may can mot task tong hay nhieu sub-task

## 6. Mode 3.2 - Semi-auto mot lan click PDA

Y tuong:

- operator van la nguoi cap quyen
- PDA chi click mot lan de bat dau batch
- Vision/adapter tao task lien tiep cho den khi het FG empty hoac het PK occupied

Dieu kien bat dau batch:

- co trigger tu PDA/RCS/adapter
- auto dispatcher dang idle
- Vision snapshot fresh
- HIK bridge khong co loi ket noi nghiem trong
- callback server san sang nhan `agvCallback`
- khong co manual override active

Algorithm:

1. Doc snapshot Vision.
2. Tim `source = first occupied PK` theo PK pick order.
3. Tim `dest = first empty FG` theo FG put order.
4. Neu thieu source hoac dest thi dung batch.
5. Reserve source va dest.
6. Goi `genAgvSchedulingTask`.
7. Neu RCS accept, luu `taskCode`, `from`, `to`, reservation.
8. Cho `agvCallback(method=end)` hoac `queryTaskStatus=9`.
9. Xac nhan bang Vision:
   - source tro thanh `empty`
   - dest tro thanh `occupied`
10. Release reservation.
11. Lap lai buoc 1.

Dung batch khi:

- FG full
- PK empty
- task failed/canceled/interrupted
- Vision unknown/stale
- manual mode duoc bat
- operator stop/pause
- qua timeout

## 7. Mode 3.3 - Full-auto

Y tuong:

- Vision tu dong tao task khi dieu kien san sang
- operator chi bat/tat che do auto va xu ly ngoai le
- manual PDA task luon uu tien cao hon

State machine de xuat:

- `DISABLED`
- `AUTO_IDLE`
- `EVALUATING`
- `TASK_SUBMITTING`
- `TASK_RUNNING`
- `VERIFYING_COMPLETION`
- `PAUSED_MANUAL`
- `BLOCKED_NO_SOURCE`
- `BLOCKED_NO_DEST`
- `FAULT`

Loop:

1. Neu mode disabled -> khong lam gi.
2. Neu manual active -> `PAUSED_MANUAL`.
3. Neu Vision/RCS/callback unhealthy -> `FAULT`.
4. Tim cap PK/FG hop le.
5. Neu khong co PK -> `BLOCKED_NO_SOURCE`.
6. Neu khong co FG -> `BLOCKED_NO_DEST`.
7. Tao task.
8. Theo doi task.
9. Verify bang Vision.
10. Tao task tiep theo.

## 8. Reservation ledger

Bat buoc can ledger de tranh sai lech giua task RCS va state Vision.

Moi reservation can luu:

- `reservation_id`
- `task_code`
- `source_position`
- `dest_position`
- `source_camera_id`
- `source_zone_id`
- `dest_camera_id`
- `dest_zone_id`
- `created_at`
- `state`
- `last_rcs_status`
- `last_callback_method`
- `attempt_count`
- `operator_mode`

State reservation:

- `reserved`
- `submitted`
- `running`
- `completed_wait_vision_verify`
- `verified`
- `failed`
- `canceled`
- `expired`

Nguyen tac:

- zone da reserved thi khong duoc chon cho task moi
- neu submit fail thi release reservation
- neu task complete nhung Vision chua verify thi van giu reservation
- neu timeout thi chuyen `FAULT`, khong tu release am tham

## 9. Manual priority

Manual co uu tien cao nhat:

- khi operator chay manual, auto dispatcher phai pause
- khong tao task moi trong khi manual active
- task auto dang chay thi khong cancel tu dong, tru khi AGV/RCS yeu cau
- priority cua auto task phai thap hon manual task
- field `priority` cua `genAgvSchedulingTask` can team AGV chot

Can team AGV/RCS cung cap co che nhan biet manual active:

- callback PDA/manual task
- query task list
- flag tu RCS
- hoac endpoint adapter rieng

## 10. Thong tin bat buoc can hoi team AGV/RCS

Chua nen code 3.2/3.3 neu chua chot cac cau hoi sau:

1. API chinh tao task area-to-area la `genAgvSchedulingTask` hay API template rieng?
2. `taskTyp` cho AMR pallet PK -> FG la gi?
3. `positionCodePath` dung `type="00"` hay type khac?
4. Thu tu path can 2 diem hay can them diem thang may/intermediate?
5. Task qua thang may la 1 task tong hay nhieu sub-task?
6. RCS co tu xu ly elevator F06 hay Vision phai authorize elevator rieng?
7. Manual task priority va auto task priority la bao nhieu?
8. RCS co tra task ID trong response `data` on dinh khong?
9. Callback `agvCallback` co bat buoc cau hinh URL nao?
10. `method=end/cancel/outbin/start` duoc map chinh xac voi trang thai task nhu the nao?
11. Neu task failed, Vision nen retry hay cho operator xu ly?
12. Gioi han tan suat tao task cua RCS la bao nhieu?
13. Co can chi dinh `agvCode` hay de RCS tu chon AMR?
14. RCS co cung cap flag manual active de Vision pause auto khong?

## 11. Roadmap trien khai

Phase 0 - Chot giao thuc:

- lay task sample tu PDA dang chay thanh cong
- lay request/response RCS khi PDA tao task PK -> FG
- chot `taskTyp`, `positionCodePath`, `priority`, callback
- chot danh sach 26 vi tri va mapping camera/zone

Phase 1 - Dry-run planner:

- tao module planner chi doc snapshot
- tinh source/dest theo order
- xuat candidate task ra JSON
- khong goi RCS

Phase 2 - Semi-auto internal:

- them trigger local file/API
- tao tung task voi `dry_run=true`
- ledger reservation
- verify state sau task bang fake callback/test CLI

Phase 3 - Semi-auto RCS real:

- `dry_run=false` cho 1 cap PK/FG
- tao task that
- theo doi `agvCallback` va `queryTaskStatus`
- verify source/dest bang Vision

Phase 4 - Semi-auto production:

- bat one-click batch
- gioi han max task per batch
- them pause/stop/operator recovery

Phase 5 - Full-auto pilot:

- bat auto trong khung gio test
- priority thap hon manual
- telemetry day du
- operator co nut disable nhanh

Phase 6 - Full-auto production:

- auto chay lien tuc
- alert khi blocked/fault
- bao cao throughput va loi

## 12. Acceptance criteria

Mode 3.2 pass khi:

- 1 click tao du chuoi task hop le
- dung khi FG full hoac PK empty
- khong tao trung source/dest
- manual override pause duoc batch
- task loi dung batch va bao ly do
- Vision verify duoc source empty va dest occupied sau moi task

Mode 3.3 pass khi:

- auto tu tao task khi co source/dest hop le
- auto dung khi het dieu kien
- manual task luon uu tien
- khong task nao duoc tao khi zone unknown/stale
- moi task co audit trail day du
- co nut disable/pause va restart an toan

## 13. Ket luan ky thuat

Huong trien khai dung khong phai de Vision "lai robot" truc tiep. Vision se dong vai tro orchestration layer:

- doc state PK/FG da on dinh
- chon cap lay/tra theo rule da chot
- goi RCS tao task bang API chinh thuc
- theo doi callback/status
- verify ket qua bang camera
- fail-safe khi mat tin cay

Day la kien truc dung cho moi truong nha may: RCS van la bo dieu phoi robot, Vision la bo ra quyet dinh task dua tren nhan thuc thuc te va safety gate.
