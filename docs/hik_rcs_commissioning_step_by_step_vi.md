# HUONG DAN CAM TAY CHI VIEC: VISION -> HIK RCS / AGV / AMR

Tai lieu nay dung cho ky su trien khai khi can dua he thong Vision hien tai ket noi that voi HIK RCS-2000.

Muc tieu:

1. Lay output tu he thong Vision.
2. Map output do thanh du lieu nghiep vu cua HIK.
3. Gui REST request dung API.
4. Nhan callback tu HIK.
5. Kiem thu tung zone de xac nhan he thong chay that.

---

## 1. Hieu dung bai toan truoc khi setup

He thong Vision cua ban hien tai xuat ra:

- `occupied`
- `empty`
- `unknown`

Nhung HIK RCS khong co API "update occupancy" chung chung.

Ban phai quy doi sang nghiep vu ma RCS hieu:

- `bindPodAndBerth`
- `bindPodAndMat`
- `bindCtnrAndBin`
- `lockPosition`

Noi don gian:

- `occupied` = bind
- `empty` = unbind
- `unknown` = khong bind/unbind mu, uu tien `lockPosition`

---

## 2. 6 thong tin bat buoc phai xin duoc tu HIK/WMS/AGV

Truoc khi sua code hay config, ban phai co du 6 thong tin sau:

1. Dia chi HIK RCS:
   - `host`
   - `rpc_port`
   - `dps_port`

2. Xac thuc:
   - `client_code`
   - `token_code`

3. Bang mapping zone:
   - `camera_id`
   - `zone_id`
   - `positionCode`
   - loai API phai dung cho zone do

4. Ma doi tuong nghiep vu:
   - `podCode`
   - hoac `materialLot`
   - hoac `ctnrCode` + `ctnrTyp`

5. Callback URL ma RCS se goi nguoc lai:
   - `http://<vision-host>:<port>/service/rest`
   - hoac full path `.../service/rest/agvCallbackService`

6. Quy tac fail-safe:
   - khi `unknown` thi khoa vi tri bang `lockPosition`
   - hay chi canh bao

Neu chua co 6 thong tin nay, chua du dieu kien de ket luan "da tich hop xong".

---

## 3. Quy doi output Vision sang API HIK

### 3.1 Truong hop 1 - Zone dai dien cho rack/trolley tai vi tri

Dung:

- `bindPodAndBerth`

Quy doi:

- `occupied` -> `indBind=1`
- `empty` -> `indBind=0`
- `unknown` -> `lockPosition(indBind=0)`

Du lieu can co:

- `positionCode`
- `podCode`

### 3.2 Truong hop 2 - Zone dai dien cho rack va material lot

Dung:

- `bindPodAndMat`

Quy doi:

- `occupied` -> bind rack voi lot
- `empty` -> unbind rack voi lot
- `unknown` -> lock vi tri neu can

Du lieu can co:

- `podCode`
- `materialLot`

### 3.3 Truong hop 3 - Zone dai dien cho pallet/container/bin

Dung:

- `bindCtnrAndBin`

Quy doi:

- `occupied` -> `indBind=1`
- `empty` -> `indBind=0`
- `unknown` -> `lockPosition(indBind=0)`

Du lieu can co:

- `ctnrCode`
- `ctnrTyp`
- `stgBinCode` hoac `positionCode`

---

## 4. File can sua trong du an

Ban se thao tac chu yeu tren:

- `configs/hik_rcs.json`
- `mainProcess.py`
- `outputs/runtime/agv_latest.json`
- `outputs/runtime/hik_rcs/http_exchange.jsonl`
- `outputs/runtime/hik_rcs/callbacks/`

Code da duoc noi san roi. Trien khai thuc te chu yeu la dien config dung.

---

## 5. Cac buoc setup chi tiet

## BUOC 1 - Xac dinh loai zone cua tung camera

Voi tung zone, tra loi:

- zone nay dai dien cho rack/trolley?
- hay material lot?
- hay pallet/container/bin?

Tu do chon `method`:

- `bindPodAndBerth`
- `bindPodAndMat`
- `bindCtnrAndBin`

## BUOC 2 - Lap bang mapping nghiep vu

Lap bang excel hoac bang text nhu sau:

| camera_id | zone_id | method | positionCode | podCode | materialLot | ctnrCode | ctnrTyp | stgBinCode |
|---|---|---|---|---|---|---|---|---|
| cam101 | A1 | bindPodAndBerth | P-A1 | RACK-001 |  |  |  |  |
| cam101 | A2 | bindPodAndBerth | P-A2 | RACK-002 |  |  |  |  |
| cam104 | B1 | bindCtnrAndBin | P-B1 |  |  | PALLET-001 | PALLET | BIN-B1 |

Ban phai xac nhan bang nay voi ben HIK/WMS/AGV.

## BUOC 3 - Dien `configs/hik_rcs.json`

Mo file:

```json
{
  "enabled": false,
  "dry_run": true,
  "scheme": "http",
  "host": "192.168.1.200",
  "rpc_port": 8182,
  "dps_port": 8083,
  "client_code": "VISION01",
  "token_code": "TOKEN_FROM_HIK",
  "callback_server": {
    "enabled": true,
    "host": "0.0.0.0",
    "port": 9000,
    "base_path": "/service/rest"
  },
  "mappings": [
    {
      "enabled": true,
      "camera_id": "cam101",
      "zone_id": "A1",
      "method": "bindPodAndBerth",
      "position_code": "P-A1",
      "pod_code": "RACK-001",
      "pod_dir": "0",
      "unknown_action": "lockPosition"
    },
    {
      "enabled": true,
      "camera_id": "cam104",
      "zone_id": "B1",
      "method": "bindCtnrAndBin",
      "position_code": "P-B1",
      "stg_bin_code": "BIN-B1",
      "ctnr_code": "PALLET-001",
      "ctnr_typ": "PALLET",
      "unknown_action": "lockPosition"
    }
  ]
}
```

Nguyen tac:

- lan dau de `enabled=false`, `dry_run=true`
- chua gui that khi chua test

## BUOC 4 - Cau hinh callback phia HIK

Theo tai lieu, can cau hinh callback URL trong system parameters:

- `10012`
- `10013`
- `10014`

Khuyen nghi:

- de callback base la `http://<vision-ip>:9000/service/rest`

Bridge hien tai chap nhan ca:

- `/service/rest/agvCallbackService/agvCallback`
- `/service/rest/agvCallbackService/warnCallback`
- `/service/rest/agvCallbackService/bindNotify`

## BUOC 5 - Chay callback server

Neu muon test rieng callback:

```bash
python tools/hik_rcs_cli.py serve-callbacks
```

Khi RCS goi ve thanh cong, se co file:

- `outputs/runtime/hik_rcs/callbacks/agvCallback_latest.json`
- `outputs/runtime/hik_rcs/callbacks/warnCallback_latest.json`
- `outputs/runtime/hik_rcs/callbacks/bindNotify_latest.json`

## BUOC 6 - Chay backend Vision o che do dry-run

Dat:

```json
"enabled": true,
"dry_run": true
```

Roi chay:

```bash
python mainProcess.py
```

Luc nay bridge se:

- doc zone state that
- tao request dung logic
- KHONG gui that
- ghi log request gia lap

Kiem tra:

- `outputs/runtime/hik_rcs/http_exchange.jsonl`
- `outputs/runtime/hik_rcs/bridge_state.json`

Neu zone chuyen `occupied`, ban phai thay log dung API va dung payload.

## BUOC 7 - Test thu cong tung API truoc

### 7.1 Query task

```bash
python tools/hik_rcs_cli.py query-task --task-code TASK-001
```

### 7.2 Query AGV

```bash
python tools/hik_rcs_cli.py query-agv --map-short-name test
```

### 7.3 Khoa/mo vi tri

```bash
python tools/hik_rcs_cli.py lock-position --position-code P-A1 --action disable
python tools/hik_rcs_cli.py lock-position --position-code P-A1 --action enable
```

### 7.4 Gia lap zone state

```bash
python tools/hik_rcs_cli.py bind-zone --camera-id cam101 --zone-id A1 --state occupied --dry-run
python tools/hik_rcs_cli.py bind-zone --camera-id cam101 --zone-id A1 --state empty --dry-run
python tools/hik_rcs_cli.py bind-zone --camera-id cam101 --zone-id A1 --state unknown --dry-run
```

Neu ket qua logic dung, chuyen sang request that.

## BUOC 8 - Bat gui that

Sua:

```json
"enabled": true,
"dry_run": false
```

Roi chay lai backend:

```bash
python mainProcess.py
```

Luc nay he thong se gui request that sang HIK RCS.

## BUOC 9 - Kiem thu tung zone tai hien truong

Voi moi zone, test 3 tinh huong:

### Tinh huong A - Co hang

Ky vong:

- Vision -> `occupied`
- Bridge -> API bind voi `indBind=1`
- HIK server nhan request dung
- neu co callback, callback duoc luu ve file

### Tinh huong B - Khong co hang

Ky vong:

- Vision -> `empty`
- Bridge -> API bind voi `indBind=0`

### Tinh huong C - Camera khong chac chan

Ky vong:

- Vision -> `unknown`
- Bridge -> `lockPosition(indBind=0)` neu mapping co cau hinh

Ban phai lap bien ban test cho tung zone.

---

## 6. Vi du cu the va de hieu nhat

### Vi du 1 - cam101 A1 la vi tri dat trolley

Dieu kien:

- `camera_id = cam101`
- `zone_id = A1`
- vi tri HIK la `P-A1`
- trolley ma HIK quan ly la `RACK-001`

Config:

```json
{
  "enabled": true,
  "camera_id": "cam101",
  "zone_id": "A1",
  "method": "bindPodAndBerth",
  "position_code": "P-A1",
  "pod_code": "RACK-001",
  "pod_dir": "0",
  "unknown_action": "lockPosition"
}
```

Khi camera thay trolley trong ROI:

- Vision output: `occupied`
- Bridge gui:
  - API: `bindPodAndBerth`
  - `positionCode=P-A1`
  - `podCode=RACK-001`
  - `indBind=1`

Khi trolley roi khoi ROI:

- Vision output: `empty`
- Bridge gui:
  - API: `bindPodAndBerth`
  - `indBind=0`

Khi camera bi che, out net, hoac khong chac:

- Vision output: `unknown`
- Bridge gui:
  - API: `lockPosition`
  - `positionCode=P-A1`
  - `indBind=0`

### Vi du 2 - cam104 B1 la pallet/bin

Dieu kien:

- `camera_id = cam104`
- `zone_id = B1`
- `ctnrCode = PALLET-001`
- `ctnrTyp = PALLET`
- `stgBinCode = BIN-B1`

Config:

```json
{
  "enabled": true,
  "camera_id": "cam104",
  "zone_id": "B1",
  "method": "bindCtnrAndBin",
  "position_code": "P-B1",
  "stg_bin_code": "BIN-B1",
  "ctnr_code": "PALLET-001",
  "ctnr_typ": "PALLET",
  "unknown_action": "lockPosition"
}
```

---

## 7. Thu tu thao tac khuyen nghi khi di nha may

Day la thu tu thuc chien khuyen nghi:

1. Xac nhan camera chay on.
2. Xac nhan zone detect dung.
3. Xac nhan `outputs/runtime/agv_latest.json` dung.
4. Xin du bang mapping HIK that.
5. Dien `configs/hik_rcs.json`.
6. Bat callback server.
7. Test callback.
8. Bat `dry_run=true`.
9. Test tung zone.
10. Bat request that.
11. Test tung zone lan 2 voi HIK/RCS that.
12. Test `unknown`.
13. Test mat mang/camera.
14. Lap checklist nghiem thu.

---

## 8. Cac loi hay gap va cach xu ly

### Loi 1 - Vision da ra `occupied` nhung HIK khong phan ung

Kiem tra:

- `enabled=true` chua
- `dry_run=false` chua
- `positionCode` co dung ma that khong
- `podCode/materialLot/ctnrCode` co dung khong
- `token_code` dung khong
- xem `outputs/runtime/hik_rcs/http_exchange.jsonl`

### Loi 2 - Request gui di nhung HIK bao sai du lieu

Nguyen nhan hay gap:

- dung sai API so voi nghiep vu
- nham `positionCode`
- nham `podCode`
- thieu `ctnrTyp`
- RCS dang dung duong dan cu va can `include_interface_name=true`

### Loi 3 - Callback khong ve

Kiem tra:

- firewall
- port callback
- system parameter 10012/10013/10014
- ben HIK dang goi ve `service/rest` hay full path

### Loi 4 - `unknown` xuat hien nhieu

Kiem tra:

- camera co bi rung/che khong
- timeout co qua gan khong
- score threshold co qua cao khong
- model co detect on dinh khong

---

## 9. Tieu chi de duoc coi la "tich hop thanh cong"

Chi nen chot la thanh cong khi dat du 5 dieu kien:

1. Vision detect dung tren hien truong.
2. Mapping zone -> HIK code da duoc xac nhan boi nghiep vu.
3. Request HIK da gui that thanh cong.
4. Callback HIK da ve va duoc luu.
5. AGV/AMR da phan ung dung theo tinh huong test.

Neu thieu bat ky dieu kien nao, chua nen ket luan la production-ready.

---

## 10. KET LUAN THUC TE NHAT

Phan code cua du an hien tai da san sang cho viec tich hop.

Phan quyet dinh thanh cong ngoai hien truong se nam o:

- mapping nghiep vu dung
- token dung
- callback dung
- test tung zone dung

Hay dung tai lieu nay dung thu tu, khong bo qua buoc, va test tung zone mot cach co ghi nhan.
