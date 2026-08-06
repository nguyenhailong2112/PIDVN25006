# Vision Auto Dispatch Quickstart

Tai lieu nay danh cho dev moi nhan ban giao Vision.

Muc tieu:

- Hieu Vision khoi dong nhu the nao.
- Hieu khi thirt-party/PDA switch mode thi Vision se phan ung ra sao.
- Hieu dung API nao de test nhanh.

## 1. Vision khoi dong nhu the nao

### 1.1 Thu tu khoi dong khuyen dung

1. Kiem tra `configs/hik_rcs.json`.
2. Kiem tra `configs/auto_dispatch.json`.
3. Khoi dong Vision main process.
4. Kiem tra callback server bindNotify cua Vision online.
5. Kiem tra API control server cua Vision online.

### 1.2 Cac service can co

- Main Vision process.
- HIK RCS bridge.
- Callback server cho `bindNotify`.
- Auto dispatch control API server.

### 1.3 Port mac dinh

- Callback bindNotify: `2112`
- Auto dispatch API: `8023`

### 1.4 IP site

- PC Vision: `192.168.10.44`
- Default client target trong script test: `http://192.168.10.44:8023/service/rest/visionAutoDispatch`

## 2. Cac file cau hinh can biet

### 2.1 `configs/hik_rcs.json`

File nay quyet dinh:

- host/port RCS
- callback server
- mapping bind/unbind

### 2.2 `configs/auto_dispatch.json`

File nay quyet dinh:

- `operation_mode`
- `profile_id`
- API control server
- quy tac auto dispatch PK -> FG
- `api_server.allowlist` chi cho phep cac IP duoc khai bao truy cap API

### 2.3 Runtime control file

```text
outputs/runtime/auto_dispatch/mode_control.json
```

File nay duoc `setMode` cap nhat.

## 3. Vision van hanh ra sao

### 3.1 Mode `manual`

Khi `manual`:

- Vision chi bind/unbind.
- Vision khong tao task AGV moi.
- Vision van nhan callback bindNotify va cap nhat state.

Trang thai binh thuong:

- `status = manual_mode`
- `state.batch` khong active
- `state.active_task` khong co task moi

### 3.2 Mode `auto + PK_AB`

Khi `auto` va `profile_id = PK_AB`:

- Vision chi check batch PK_AB.
- Vision chi tao task khi PK_AB du 8/8 slot occupied.
- FG phai con it nhat 1 slot empty.
- Moi lan chi co 1 `active_task`.
- Task hien tai completed thi Vision moi sinh task tiep theo.

### 3.3 Mode `auto + PK_CD`

Khi `auto` va `profile_id = PK_CD`:

- Vision chi check batch PK_CD.
- Vision chi tao task khi PK_CD du 7/7 slot occupied.
- FG phai con it nhat 1 slot empty.
- Moi lan chi co 1 `active_task`.

## 4. Khi thirt-party switch mode thi se co gi xay ra

### 4.1 Chuyen sang `manual`

1. App Caller goi `POST /setMode`.
2. Neu hop le, Vision ghi `mode_control.json`.
3. Chu ky sync tiep theo, Vision dung sinh task moi.
4. Task dang chay neu co se duoc theo doi toi luc xong, nhung khong sinh batch moi.

### 4.2 Chuyen sang `auto`

1. App Caller goi `POST /setMode`.
2. Neu hop le, Vision ghi `mode_control.json`.
3. Chu ky sync tiep theo, Vision bat dau check PK/FG.
4. Neu du dieu kien, Vision tao task dau tien.
5. Sau moi task completed, Vision tao task tiep theo neu buffer con du dieu kien.

## 5. API test nhanh

### 5.1 Health

```http
GET /service/rest/visionAutoDispatch/health
```

### 5.2 Status

```http
GET /service/rest/visionAutoDispatch/status
```

Hoac:

```http
POST /service/rest/visionAutoDispatch/getStatus
```

### 5.3 Set mode

```http
POST /service/rest/visionAutoDispatch/setMode
```

### 5.4 Query AGV status

```http
POST /service/rest/visionAutoDispatch/queryAgvStatus
```

### 5.5 Query task status

```http
POST /service/rest/visionAutoDispatch/queryTaskStatus
```

## 6. Quan sat runtime

Khi test, xem cac file sau:

- `outputs/runtime/auto_dispatch/state.json`
- `outputs/runtime/auto_dispatch/events.jsonl`
- `outputs/runtime/auto_dispatch/mode_control.json`
- `outputs/runtime/auto_dispatch/control_api_latest.json`
- `outputs/runtime/hik_rcs/http_exchange.jsonl`

Neu task da completed nhung khong sinh task tiep theo, thuong la do:

- mode chua la `auto`
- `profile_id` sai
- FG khong con slot empty
- task status chua duoc Vision ghi nhan dung

## 7. Script test API doc lap

Dung file:

```text
tools/vision_auto_dispatch_client.py
```

Vi du:

```bash
python tools/vision_auto_dispatch_client.py health
python tools/vision_auto_dispatch_client.py status
python tools/vision_auto_dispatch_client.py set-mode --mode auto --profile-id PK_AB
python tools/vision_auto_dispatch_client.py query-task --task-code QUANGPROPKAA5FGBB220260731080000
```
