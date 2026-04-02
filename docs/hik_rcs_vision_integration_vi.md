# Tich Hop Vision CCTV voi HIK RCS-2000

## 1. Muc tieu
Backend Vision hien tai da xac dinh duoc trang thai zone:
- `occupied` / `bind` / `1`
- `empty` / `unbind` / `0`
- `unknown`

Tai lieu RCS-2000 cho thay HIK khong co API "gui occupancy thuan tuy".
Thay vao do, RCS lam viec theo nghiep vu:
- bind/unbind rack voi vi tri: `bindPodAndBerth`
- bind/unbind rack voi material lot: `bindPodAndMat`
- bind/unbind container voi bin: `bindCtnrAndBin`
- khoa/mo vi tri de scheduling khong su dung vi tri khong an toan: `lockPosition`

Vi vay, de Vision truyen thong tin dung nghia cho HIK RCS, can map moi `camera_id + zone_id`
voi ma nghiep vu cua HIK:
- `positionCode`
- `podCode` hoac `materialLot` hoac `ctnrCode + ctnrTyp`

## 2. Tu duy tich hop dung
Khong nen coi Vision la bo dieu khien AGV truc tiep.

Kien truc dung:
`Vision -> state bridge -> HIK RCS APIs -> RCS scheduling -> AGV/AMR`

Y nghia:
- `occupied`: gui lenh bind.
- `empty`: gui lenh unbind.
- `unknown`: khong duoc bind/unbind mu, uu tien `lockPosition` de khoa vi tri.

## 3. File da duoc bo sung
- `configs/hik_rcs.json`
- `core/hik_rcs_client.py`
- `core/hik_callback_server.py`
- `core/hik_rcs_bridge.py`
- `tools/hik_rcs_cli.py`

Bridge da duoc noi vao `mainProcess.py`.
Moi lan backend export camera snapshot, bridge se doc zone state va dispatch sang RCS neu config cho phep.

## 4. Cach cau hinh
Mo file `configs/hik_rcs.json`.

### 4.1 Cau hinh ket noi RCS
Can dien:
- `host`
- `rpc_port` thuong la `8182`
- `dps_port` thuong la `8083`
- `client_code`
- `token_code`

Neu deployment HIK dung duong dan cu, co the doi:
- `rpc_base_path`
- `query_agv_path`

Neu deployment cu can truong `interfaceName`, dat:
- `include_interface_name: true`

### 4.2 Cau hinh callback server
Neu muon RCS goi nguoc ve Vision platform:
- bat `callback_server.enabled`
- chon `callback_server.port`

Sau do trong RCS can cau hinh callback base address theo tai lieu:
- system parameters `10012`, `10013`, `10014`

Base address phia Vision nen co dang:
- `http://<vision-host>:<port>/service/rest`
- hoac dat `base_path=/service/rest/agvCallbackService` neu muon bridge nhan full path truc tiep

Bridge da mo 3 endpoint callback:
- `/service/rest/agvCallbackService/agvCallback`
- `/service/rest/agvCallbackService/warnCallback`
- `/service/rest/agvCallbackService/bindNotify`

## 5. Cau hinh mapping zone -> HIK
Moi mapping trong `configs/hik_rcs.json` la mot quy tac nghiep vu.

### 5.1 Rack + berth
Su dung khi Vision xac nhan vi tri dat rack/trolley.

Vi du:
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

Ket qua:
- `occupied` -> `bindPodAndBerth(indBind=1)`
- `empty` -> `bindPodAndBerth(indBind=0)`
- `unknown` -> `lockPosition(indBind=0)`

### 5.2 Rack + material lot
Su dung khi Vision dai dien cho quan he rack va lot vat tu.

```json
{
  "enabled": true,
  "camera_id": "cam3",
  "zone_id": "A3",
  "method": "bindPodAndMat",
  "pod_code": "RACK-003",
  "material_lot": "LOT-ABC-001",
  "unknown_action": "lockPosition",
  "position_code": "P-A3"
}
```

### 5.3 Container + bin
Su dung khi bai toan nghiep vu la pallet/container/bin.

```json
{
  "enabled": true,
  "camera_id": "cam4",
  "zone_id": "A1",
  "method": "bindCtnrAndBin",
  "ctnr_code": "PALLET-001",
  "ctnr_typ": "PALLET",
  "stg_bin_code": "BIN-A1",
  "position_code": "P-A1",
  "unknown_action": "lockPosition"
}
```

### 5.4 Elevator / vung an toan chi can "co vat la khoa"
Su dung khi zone Vision dai dien cho buong thang may, cua lien dong, hoac vung an toan ma AGV khong duoc di vao khi co bat ky vat the nao xuat hien.

Trong use-case nay:
- khong can phan biet person, pallet, trolley hay obstacle
- chi can co bat ky object nao cat vao ROI thi coi la `occupied`
- HIK/RCS nen nhan du lieu theo kieu khoa/mo vi tri bang `lockPosition`

Trong code hien tai, cach cau hinh dung la:
- tao 1 ROI lon phu gan het vung trong thang may
- dat `target_object` la `*`
- dat `spatial_method` la `bbox_intersects`
- map zone do sang `method=lockPosition`

Ket qua:
- `occupied` -> `lockPosition(indBind=0)`
- `empty` -> `lockPosition(indBind=1)`
- `unknown` -> `lockPosition(indBind=0)`

## 6. Yeu cau nghiep vu can lam ro voi HIK
Day la diem quan trong nhat de tich hop thanh cong.

Bridge nay da hoan chinh ve mat ky thuat, nhung de chay dung nghiep vu can chot voi HIK/WMS/AGV:
- `zone_id` nay tuong ung voi `positionCode` nao trong RCS?
- doi tuong o zone nay la `podCode`, `materialLot` hay `ctnrCode`?
- neu Vision chi biet co hang/khong co hang nhung khong biet ID doi tuong, ai cap ID nay?
- `unknown` can duoc xu ly bang `lockPosition`, `blockArea`, hay chi can log va canh bao?

Neu ban chua co `podCode/materialLot/ctnrCode`, thi khong the goi dung nghia cac API bind cua RCS.
Trong truong hop do, ban phai bo sung:
- mapping co dinh 1-1
hoac
- adapter tu WMS/MES/HIK de cap ma nghiep vu cho moi zone

## 7. Trang thai bridge hien tai
Bridge co cac co che sau:
- chi dispatch khi trang thai thay doi hoac request truoc do that bai
- co retry theo `retry_interval_sec`
- co `dry_run` de test ma khong gui that
- tu dong `lockPosition` khi `unknown` neu mapping yeu cau
- tu dong `enable` lai vi tri khi state quay ve `occupied/empty`
- ho tro `method=lockPosition` cho cac zone safety interlock nhu thang may AGV
- luu state tai `outputs/runtime/hik_rcs/bridge_state.json`
- log request/response tai `outputs/runtime/hik_rcs/http_exchange.jsonl`
- luu callback tai `outputs/runtime/hik_rcs/callbacks/`

## 8. Cach chay
### 8.1 Test khong gui that
Dat:
```json
"enabled": true,
"dry_run": true
```

Chay backend:
```bash
python mainProcess.py
```

Khi zone thay doi, xem log va file:
- `outputs/runtime/hik_rcs/http_exchange.jsonl`
- `outputs/runtime/hik_rcs/bridge_state.json`

### 8.2 Test bang CLI
Gui mot zone state gia lap:
```bash
python tools/hik_rcs_cli.py bind-zone --camera-id cam1 --zone-id A1 --state occupied --dry-run
```

Query AGV:
```bash
python tools/hik_rcs_cli.py query-agv --map-short-name test
```

Query task:
```bash
python tools/hik_rcs_cli.py query-task --task-code TASK-001
```

Khoa/mo vi tri thu cong:
```bash
python tools/hik_rcs_cli.py lock-position --position-code P-A1 --action disable
python tools/hik_rcs_cli.py lock-position --position-code P-A1 --action enable
```

Call API bat ky bang payload JSON:
```bash
python tools/hik_rcs_cli.py call-rpc genAgvSchedulingTask payload.json
```

### 8.3 Chay callback server rieng
Bat trong `configs/hik_rcs.json`:
```json
"callback_server": {
  "enabled": true,
  "host": "0.0.0.0",
  "port": 9000,
  "base_path": "/service/rest"
}
```

Roi chay:
```bash
python tools/hik_rcs_cli.py serve-callbacks
```

## 9. Khuyen nghi production
- Ban dau chay `dry_run=true`.
- Sau khi doi chieu dung `positionCode/podCode/...`, moi chuyen `dry_run=false`.
- Chi bat `enabled=true` cho nhung mapping da duoc nghiep vu xac nhan.
- Dung `unknown_action=lockPosition` cho zone quan trong, de tranh AGV nhan lenh tai vi tri khong chac chan.
- Neu muon truy vet day du, luu them `taskCode/robotCode` tu callback cua RCS vao he thong log noi bo.

## 10. Diem ket luan
Phan tich hop quan trong nhat khong nam o HTTP client, ma nam o `business mapping`.

Code da san sang cho tich hop.
Thu viec con lai de chay production dung 100% la:
- chot ma nghiep vu HIK cho tung zone
- chot API bind nao la API dung cho bai toan cua ban
- chot xu ly `unknown`
- test voi RCS that
