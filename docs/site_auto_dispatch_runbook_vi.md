# Site Runbook - Vision Bind/Unbind va Auto Dispatch PK -> FG

Tai lieu nay dung cho go-live site cua chuong trinh Vision PIDVN25006.

Pham vi:

- Vision bind/unbind hang voi HIK RCS bang `bindCtnrAndBin`.
- Vision nhan `bindNotify` de canonical hoa container code tai tung slot.
- Vision tao task AGV don gian `ROADWAY -> AREA` khi mode `auto` va profile hop le.
- Third-party goi API Vision de chuyen `manual` / `auto` va chon `profile_id`.

Khong nam trong pham vi:

- Vision khong tu toi uu diem tra hang tren RCS.
- Vision khong can thiep route chi tiet cua AGV.
- Vision khong tao task full-PK ngoai `PK_AB` va `PK_CD`.

## 1. Nguyen tac van hanh

Mode mac dinh la `manual`.

Trong `manual`, Vision chi lam bind/unbind va safety lock theo mapping RCS. Vision khong tao task AGV.

Trong `auto`, Vision chi tao task khi tat ca dieu kien sau deu dung:

- `profile_id = PK_AB`: 8/8 slot PK_A va PK_B dang `occupied`.
- `profile_id = PK_CD`: 7/7 slot PK_C va PK_D dang `occupied`.
- FG co it nhat 1 slot `empty`.
- Slot source PK va dest FG co bridge state hop le.
- Mapping source/dest dang policy `hybrid_canonical`.
- Bind/unbind gan nhat khong fail.
- `hybrid_session.needs_reconcile = false`.
- Source occupied dang canonical dung ma slot, vi du `PK_AA4 = PK_AA4`.
- Callback server `bindNotify` dang enabled.

Moi lan Vision chi tao 1 task active. Sau khi task do completed theo `queryTaskStatus`, Vision moi xet task tiep theo.

Neu FG het slot empty trong giua batch, batch dung lai. Cac pallet con lai khong duoc queue ngam; lan tiep theo muon chay phai thoa lai dieu kien full profile.

## 2. Mapping chinh

PK roadway:

- Hang A: `PK_AA4`, `PK_AA3`, `PK_AA2`, `PK_AA1` -> `11${06}`
- Hang B: `PK_BB4`, `PK_BB3`, `PK_BB2`, `PK_BB1` -> `22${06}`
- Hang C: `PK_CC3`, `PK_CC2`, `PK_CC1` -> `33${06}`
- Hang D: `PK_DD4`, `PK_DD3`, `PK_DD2`, `PK_DD1` -> `44${06}`

FG area:

- `FG_AA1` den `FG_BB6` -> `2${02}`

Task payload Vision tao co dang:

```json
{
  "interfaceName": "genAgvSchedulingTask",
  "taskTyp": "QUANGPRO",
  "taskCode": "VISION_PK_AA4_TO_FG_BB2_YYYYMMDD_HHMMSS",
  "data": {
    "from": "PK_AA4",
    "to": "FG_BB2"
  },
  "userCallCodePath": ["11${06}", "2${02}"],
  "ctnrTyp": "2"
}
```

## 3. File cau hinh

`configs/hik_rcs.json`

- Tat ca mapping `bindCtnrAndBin` dung `dispatch_policy = hybrid_canonical`.
- Callback `bindNotify` bat qua `callback_server.enabled = true`.
- Port callback RCS hien tai: `2112`.

`configs/auto_dispatch.json`

- `operation_mode = manual` la default an toan.
- `profile_id = PK_AB` la default.
- `api_server.port = 2113`.
- Chi co 2 profile hop le: `PK_AB`, `PK_CD`.

`outputs/runtime/auto_dispatch/mode_control.json`

- File runtime do API tao/cap nhat.
- Neu file nay ton tai, no override `operation_mode` va `profile_id` trong config.

## 4. API cho third-party

Base URL:

```text
http://<VISION_IP>:2113/service/rest/visionAutoDispatch
```

### 4.1 Health

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

### 4.2 Status

```http
GET /service/rest/visionAutoDispatch/status
```

Hoac:

```http
POST /service/rest/visionAutoDispatch/getStatus
```

Response gom:

- `control`: mode/profile hien tai.
- `state`: active task, batch, last completed/failed task.
- `allowed_profiles`: `PK_AB`, `PK_CD`.
- `require_bind_notify`, `require_canonical`.
- `callback_server_enabled`.

### 4.3 Set Mode

Chuyen sang manual:

```http
POST /service/rest/visionAutoDispatch/setMode
Content-Type: application/json
```

```json
{
  "reqCode": "REQ_MANUAL_001",
  "operation_mode": "manual",
  "profile_id": "PK_AB",
  "updated_by": "third_party",
  "note": "stop auto dispatch"
}
```

Chuyen sang auto PK_AB:

```json
{
  "reqCode": "REQ_AUTO_AB_001",
  "operation_mode": "auto",
  "profile_id": "PK_AB",
  "updated_by": "third_party",
  "note": "start AB batch when gates pass"
}
```

Chuyen sang auto PK_CD:

```json
{
  "reqCode": "REQ_AUTO_CD_001",
  "operation_mode": "auto",
  "profile_id": "PK_CD",
  "updated_by": "third_party",
  "note": "start CD batch when gates pass"
}
```

Response thanh cong:

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
      "updated_at": 1780000000.0,
      "updated_by": "third_party",
      "note": "start AB batch when gates pass"
    },
    "state": {}
  }
}
```

Response loi:

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

## 5. Log va audit file

Bind/unbind RCS:

- `outputs/runtime/hik_rcs/bridge_state.json`
- `outputs/runtime/hik_rcs/http_exchange.jsonl`
- `outputs/runtime/hik_rcs/callbacks/bindNotify_latest.json`
- `outputs/runtime/hik_rcs/callbacks/bindNotify.jsonl`

Auto dispatch:

- `outputs/runtime/auto_dispatch/state.json`
- `outputs/runtime/auto_dispatch/events.jsonl`
- `outputs/runtime/auto_dispatch/mode_control.json`

API third-party:

- `outputs/runtime/auto_dispatch/control_api_latest.json`
- `outputs/runtime/auto_dispatch/control_api.jsonl`

Snapshot Vision:

- `outputs/runtime/process_latest.json`
- `outputs/runtime/agv_latest.json`
- `outputs/runtime/cameras/cam*.json`

## 6. Quy trinh test site

### 6.1 Test bindNotify/canonical

1. Bat chuong trinh Vision.
2. Kiem tra callback server Vision port `2112` online.
3. Tren RCS cau hinh notify `bindCtnrAndBin` ve:

```text
http://<VISION_IP>:2112/service/rest/bindNotify
```

4. Dat pallet/trolley vao 1 slot.
5. Kiem tra `bridge_state.json`:

- `dispatch_policy = hybrid_canonical`
- `last_seen_state = occupied`
- `hybrid_session.needs_reconcile = false`
- `hybrid_session.actual_ctnr_code` bang ma static cua slot.

6. Neu RCS truoc do bind source khac, vi du `FG_BB4 = PK_AA4`, Vision phai canonical hoa ve `FG_BB4 = FG_BB4`.

### 6.2 Test manual mode

1. Goi API:

```json
{"operation_mode": "manual", "profile_id": "PK_AB"}
```

2. Dat/lay pallet tai PK/FG.
3. Xac nhan Vision van bind/unbind.
4. Xac nhan `state.json` khong co `active_task` moi.

### 6.3 Test auto PK_AB

1. Lam day du 8/8 slot:

```text
PK_AA4, PK_AA3, PK_AA2, PK_AA1,
PK_BB4, PK_BB3, PK_BB2, PK_BB1
```

2. Dam bao FG co slot empty.
3. Goi:

```json
{"operation_mode": "auto", "profile_id": "PK_AB"}
```

4. Xac nhan task dau tien dung thu tu source:

```text
PK_AA4 -> FG empty dau tien theo thu tu FG_AA1..FG_BB6
```

5. Khi task completed tren RCS, Vision moi tao task ke tiep.

### 6.4 Test auto PK_CD

1. Lam day du 7/7 slot:

```text
PK_CC3, PK_CC2, PK_CC1,
PK_DD4, PK_DD3, PK_DD2, PK_DD1
```

2. Dam bao FG co slot empty.
3. Goi:

```json
{"operation_mode": "auto", "profile_id": "PK_CD"}
```

4. Xac nhan payload dau tien:

```json
{
  "data": {"from": "PK_CC3", "to": "FG_AA1"},
  "userCallCodePath": ["33${06}", "2${02}"]
}
```

### 6.5 Test FG it cho trong hon PK

Vi du PK_AB du 8 pallet, FG chi con 5 slot empty `FG_BB2..FG_BB6`.

Vision chi tao toi da 5 task:

- `PK_AA4 -> FG_BB2`
- `PK_AA3 -> FG_BB3`
- `PK_AA2 -> FG_BB4`
- `PK_AA1 -> FG_BB5`
- `PK_BB4 -> FG_BB6`

Sau do batch dung voi status `stopped_no_fg_empty`.

Cac pallet `PK_BB3`, `PK_BB2`, `PK_BB1` khong duoc queue ngam. Lan sau muon chay tiep phai thoa lai dieu kien PK_AB 8/8 va FG co empty.

## 7. Dieu kien nghiem thu

- Manual mode khong tao task AGV.
- Auto mode chi chap nhan `PK_AB` hoac `PK_CD`.
- PK_AB thieu bat ky slot nao thi khong tao task.
- PK_CD thieu bat ky slot nao thi khong tao task.
- FG khong co empty thi khong tao task.
- Source/dest co `needs_reconcile=true` thi khong tao task.
- Source co ctnr khac static slot thi khong tao task.
- Moi task payload dung `genAgvSchedulingTask`, `taskTyp=QUANGPRO`, `ctnrTyp=2`.
- Source roadway dung `11${06}`, `22${06}`, `33${06}`, `44${06}`.
- Dest FG luon dung `2${02}`.
- Chi co 1 active task tai mot thoi diem.
- Task sau chi tao sau khi task truoc completed.
- API request/response duoc ghi vao `control_api.jsonl`.

## 8. Xu ly su co nhanh

`blocked_bind_guard:*`

- Xem `outputs/runtime/hik_rcs/bridge_state.json`.
- Kiem tra `needs_reconcile`, `actual_ctnr_code`, `bind_dispatch.success`.
- Kiem tra RCS Storage Bin Management slot do.

`waiting_pk_full:PK_AB:x/8` hoac `waiting_pk_full:PK_CD:x/7`

- PK chua du hang theo profile.
- Kiem tra camera/ROI cua cac slot dang unknown/empty.

`stopped_no_fg_empty`

- FG da het slot empty trong batch.
- Khong phai loi; day la dung logic an toan.

`bind_notify_callback_disabled`

- Kiem tra `configs/hik_rcs.json`.
- `callback_server.enabled` phai la `true`.
- RCS phai goi callback dung URL port `2112`.

`waiting_task:<taskCode>`

- Vision dang doi RCS bao task completed.
- Dung CLI query task hoac xem `http_exchange.jsonl`.
