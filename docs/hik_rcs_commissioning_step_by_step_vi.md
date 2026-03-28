# HUONG DAN CAM TAY CHI VIEC: VISION -> HIK RCS / AGV / AMR

Tai lieu nay la runbook trien khai thuc dia cho ky su setup, commissioning va nghiem thu ket noi giua he thong Vision va HIK RCS-2000 de AGV/AMR van hanh that.

Muc tieu cua tai lieu:

1. Hieu dung output cua Vision la gi.
2. Quy doi output do sang nghiep vu ma HIK RCS hieu.
3. Dien config dung, khong bo sot field.
4. Test tung buoc theo thu tu an toan.
5. Biet ro khi nao duoc phep chuyen tu dry-run sang request that.
6. Biet ro khi nao co the ket luan "tich hop thanh cong".

Tai lieu nay khong rut gon thao tac. Hay di tung buoc, danh dau pass/fail ro rang, khong bo qua buoc nao.

---

## 1. Hieu dung bai toan va gioi han cua he thong

He thong Vision hien tai xuat ra 3 trang thai nghiep vu cho moi zone:

- `occupied`
- `empty`
- `unknown`

Y nghia:

- `occupied`: Vision ket luan vi tri dang co doi tuong can quan ly.
- `empty`: Vision ket luan vi tri dang trong.
- `unknown`: Vision khong du co so de ket luan an toan.

Dieu quan trong nhat:

- HIK RCS khong co API "gui occupancy thuan tuy".
- Vision khong giao tiep truc tiep voi robot AMR bang mot lenh "di lam viec".
- Vision phai quy doi ket qua sang nghiep vu ma HIK RCS hieu, roi HIK RCS moi scheduling va dieu phoi AMR.

Kien truc dung:

`Vision -> zone state -> HIK bridge -> HIK RCS API -> RCS scheduling -> AGV/AMR`

Hay giu tu duy nay trong suot qua trinh trien khai:

- Vision chi xac nhan trang thai hien truong.
- HIK RCS quan ly business object va scheduling.
- AGV/AMR phan ung dua tren trang thai nghiep vu ma HIK RCS da nhan.

---

## 2. 3 nhom use-case ma HIK RCS dang ho tro trong du an nay

### 2.1 Rack/Trolley tai mot vi tri

Dung API:

- `bindPodAndBerth`

Quy doi:

- `occupied` -> `indBind=1`
- `empty` -> `indBind=0`
- `unknown` -> uu tien `lockPosition(indBind=0)` neu zone yeu cau fail-safe

Du lieu can co:

- `positionCode`
- `podCode`
- tuy chon `podDir`
- tuy chon `characterValue`

### 2.2 Rack/Trolley gan voi material lot

Dung API:

- `bindPodAndMat`

Quy doi:

- `occupied` -> bind rack voi lot
- `empty` -> unbind rack voi lot
- `unknown` -> fail-safe theo quy tac site

Du lieu can co:

- `podCode`
- `materialLot`

### 2.3 Pallet/Container/Bin

Dung API:

- `bindCtnrAndBin`

Quy doi:

- `occupied` -> `indBind=1`
- `empty` -> `indBind=0`
- `unknown` -> uu tien `lockPosition(indBind=0)` neu zone quan trong

Du lieu can co:

- `ctnrCode`
- `ctnrTyp`
- mot trong hai truong:
  - `stgBinCode`
  - `positionCode`

Ket luan:

- Khong co API "Vision occupied".
- Luon phai chon dung API business.

---

## 3. 8 thong tin bat buoc phai co truoc khi di commissioning

Khong bat dau commissioning khi chua co du 8 nhom thong tin duoi day.

### 3.1 Thong tin ket noi HIK RCS

Phai xin duoc:

- `host`
- `rpc_port`
- `dps_port`
- `scheme`:
  - thuong la `http`
  - neu site yeu cau TLS thi xac nhan `https`

### 3.2 Thong tin xac thuc

Phai xin duoc:

- `client_code`
- `token_code`

Neu site noi "khong can token":

- van phai xac nhan bang van ban hoac email ky thuat.
- khong duoc tu suy doan.

### 3.3 Bang mapping zone -> HIK business code

Phai co bang mapping ro rang:

- `camera_id`
- `zone_id`
- `method`
- `positionCode`
- va mot trong cac nhom:
  - `podCode`
  - `materialLot`
  - `ctnrCode` + `ctnrTyp`

### 3.4 Quy tac fail-safe cho `unknown`

Phai xac nhan:

- `unknown` co duoc bind/unbind khong
- co dung `lockPosition` khong
- neu dung `lockPosition` thi khoa vi tri nao
- khi nao duoc mo lai vi tri

### 3.5 Callback tu HIK

Phai xac nhan:

- HIK co goi callback khong
- callback base URL la gi
- HIK dang goi theo path:
  - `/service/rest/...`
  - hay `/service/rest/agvCallbackService/...`

### 3.6 Quy tac nghiep vu cua doi tuong duoc quan ly

Phai xac nhan:

- doi tuong trong ROI la rack, trolley, pallet, container hay lot
- object ID do la co dinh theo zone hay thay doi theo ngay/lenh
- neu thay doi, he thong nao cap ID moi

### 3.7 Dieu kien mang va firewall

Phai xac nhan:

- Vision PC ping duoc HIK RCS
- HIK RCS goi nguoc callback ve Vision PC duoc
- port callback mo qua firewall
- DNS hay IP co on dinh

### 3.8 Dieu kien nghiem thu

Phai xac nhan truoc:

- can bao nhieu zone test
- can test nhung tinh huong nao
- ai la nguoi ky xac nhan ben AGV/HIK/WMS

Neu chua co du 8 nhom thong tin tren, chua du dieu kien de ket luan "co the di live".

---

## 4. File va module can nam long truoc khi deploy

Trong du an nay, cac file quan trong nhat cho tich hop HIK/AGV la:

- `run_forever.sh`
- `run_forever.cmd`
- `deploy/systemd/pidvn25006.service`
- `configs/hik_rcs.json`
- `mainProcess.py`
- `core/hik_rcs_bridge.py`
- `core/hik_rcs_client.py`
- `core/hik_callback_server.py`
- `tools/run_forever.py`
- `tools/hik_rcs_cli.py`
- `outputs/runtime/agv_latest.json`
- `outputs/runtime/hik_rcs/http_exchange.jsonl`
- `outputs/runtime/hik_rcs/bridge_state.json`
- `outputs/runtime/hik_rcs/callbacks/`
- `outputs/runtime/supervisor/supervisor.log`

Y nghia tung thanh phan:

- `run_forever.sh`: lenh Linux/Ubuntu mot cham de khoi dong watchdog.
- `run_forever.cmd`: lenh Windows mot cham de khoi dong watchdog.
- `deploy/systemd/pidvn25006.service`: mau service cho Ubuntu Server de auto-start sau reboot.
- `mainProcess.py`: backend Vision sinh ra zone state va goi bridge.
- `hik_rcs_bridge.py`: map state Vision sang API HIK.
- `hik_rcs_client.py`: gui HTTP POST JSON sang HIK.
- `hik_callback_server.py`: nhan callback tu HIK.
- `tools/run_forever.py`: supervisor giu backend/frontend song va tu restart khi crash.
- `agv_latest.json`: snapshot local cho he thong AGV/noi bo neu can doc file.
- `http_exchange.jsonl`: bang chung request/response that hoac dry-run.

---

## 5. Hieu dung output cua Vision truoc khi noi vao HIK

Truoc khi noi HIK, ban phai test Vision rieng va xac nhan 3 dieu:

1. Zone detect dung tren thuc te hien truong.
2. Zone khong flicker bat thuong.
3. `unknown` xuat hien dung ly do, khong phai vi config sai.

Kiem tra tai:

- `outputs/runtime/agv_latest.json`
- `outputs/runtime/process_latest.json`
- `outputs/runtime/cameras/<camera_id>.json`

Dieu ban can thay:

- moi `camera_id` co danh sach `zones`
- moi `zone_id` co:
  - `state`
  - `value`
  - `binding`
  - `health`
  - `score`

Chi khi output Vision da dung, moi tiep tuc setup HIK.

---

## 6. Lap bang mapping nghiep vu truoc khi sua config

Truoc khi mo file `configs/hik_rcs.json`, hay lap bang mapping day du nhu sau va xin ben HIK/WMS/AGV ky confirm.

| camera_id | zone_id | method | positionCode | podCode | podDir | materialLot | ctnrCode | ctnrTyp | stgBinCode | binName | unknown_action |
|---|---|---|---|---|---|---|---|---|---|---|---|
| cam101 | A1 | bindPodAndBerth | P-A1 | RACK-001 | 0 |  |  |  |  |  | lockPosition |
| cam101 | A2 | bindPodAndBerth | P-A2 | RACK-002 | 0 |  |  |  |  |  | lockPosition |
| cam103 | A3 | bindPodAndMat | P-A3 | RACK-003 |  | LOT-ABC-001 |  |  |  |  | lockPosition |
| cam104 | B1 | bindCtnrAndBin | P-B1 |  |  |  | PALLET-001 | PALLET | BIN-B1 |  | lockPosition |

Quy tac lap bang:

- moi dong la 1 `camera_id + zone_id`
- 1 zone chi duoc chon 1 `method`
- khong duoc de 1 zone vua la `bindPodAndBerth` vua la `bindCtnrAndBin`
- neu object ID la co dinh theo zone, co the dien truc tiep
- neu object ID sinh dong theo business, phai xac dinh adapter nao cap gia tri nay

Khong duoc bo qua buoc ky xac nhan bang mapping.
Day la buoc quan trong nhat cua toan bo commissioning.

---

## 7. Giai thich day du file `configs/hik_rcs.json`

Day la file trung tam de cau hinh ket noi HIK.

### 7.1 Cap toan cuc

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

Giai thich tung field:

- `enabled`
  - `false`: bridge khong gui di bat ky request nao
  - `true`: bridge duoc phep xet dispatch

- `dry_run`
  - `true`: van tao request logic nhung khong gui that
  - `false`: gui HTTP that sang HIK

- `scheme`
  - `http` hoac `https`
  - dung theo site thuc te

- `host`
  - IP hoac hostname HIK RCS

- `rpc_port`
  - port cho cac API trong `hikRpcService`

- `dps_port`
  - port cho `queryAgvStatus`

- `rpc_base_path`
  - mac dinh theo tai lieu
  - chi doi khi HIK site dung path khac

- `query_agv_path`
  - path API query AGV status

- `http_timeout_sec`
  - timeout moi request
  - site mang cham co the tang len `5.0` hoac `8.0`

- `client_code`
  - ma he thong Vision duoc HIK cap

- `token_code`
  - token xac thuc duoc HIK cap

- `include_interface_name`
  - mot so deployment cu yeu cau field `interfaceName`
  - neu HIK thong bao thieu field nay thi bat `true`

- `require_online_health`
  - neu `true`, camera/zone khong online thi bridge quy ve `unknown`

- `min_score`
  - score toi thieu de zone duoc phep dispatch

- `retry_interval_sec`
  - khoang cach retry khi request truoc do fail

### 7.2 Callback server

```json
"callback_server": {
  "enabled": true,
  "host": "0.0.0.0",
  "port": 9000,
  "base_path": "/service/rest",
  "validate_token_code": false
}
```

Y nghia:

- `enabled`
  - `true`: mo HTTP server de nhan callback
  - `false`: khong nhan callback

- `host`
  - thuong de `0.0.0.0`

- `port`
  - port callback Vision PC mo ra

- `base_path`
  - co the dat:
    - `/service/rest`
    - hoac `/service/rest/agvCallbackService`
  - code hien tai chap nhan ca hai dang

- `validate_token_code`
  - neu `true`, callback den se bi kiem tra `tokenCode` va `clientCode`
  - chi bat khi da xac nhan chuan callback that

### 7.3 Mappings

Moi mapping la 1 quy tac dispatch.

Vi du 1:

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

Vi du 2:

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

Field quan trong trong mapping:

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

Code bridge co ho tro template nhu:

- `pod_code_template`
- `ctnr_code_template`

Vi du:

```json
"ctnr_code_template": "CTNR_{camera_id}_{zone_id}"
```

Chi dung template khi:

- business chap nhan object ID sinh theo quy tac co dinh
- hoac zone map 1-1 sang 1 object co ten co dinh

Khong dung template neu object ID thay doi theo ca san xuat hoac theo lenh.

---

## 8. Quy tac an toan khi chinh config

Hay dung thu tu sau va khong dao thu tu:

1. Ban dau de:
   - `"enabled": false`
   - `"dry_run": true`
2. Dien day du host, port, client, token, callback.
3. Dien bang mapping.
4. Review lai tung zone.
5. Chuyen sang:
   - `"enabled": true`
   - `"dry_run": true`
6. Test logic.
7. Chi khi pass moi doi:
   - `"dry_run": false`

Khong duoc:

- bat request that khi chua test dry-run
- bat mapping that khi chua doi chieu business code
- chuyen nhieu tham so cung luc ma khong ghi lai thay doi

Khuyen nghi:

- luu 1 ban `hik_rcs.json` cua tung site theo ten rieng
- ghi changelog moi lan sua config

---

## 9. Kiem tra ha tang truoc khi chay

Truoc khi mo backend, thuc hien checklist sau:

### 9.1 Tren Vision PC

- xac nhan Python environment chay duoc
- xac nhan model va data duong dan dung
- xac nhan camera RTSP/video chay duoc

### 9.2 Ket noi mang toi HIK

Kiem tra:

- Vision PC ping duoc IP HIK RCS
- neu co policy mang, xac nhan route va VLAN
- neu callback dung port `9000`, xac nhan port nay mo 2 chieu

### 9.3 Kiem tra camera

- camera online
- stream mo duoc
- hinh dung camera, dung zone

### 9.4 Kiem tra output Vision truoc bridge

Mo:

- `outputs/runtime/agv_latest.json`

Xac nhan:

- camera can test co trong danh sach
- `zone_id` dung
- `state`, `binding`, `score` hop ly

Neu output Vision da sai, dung ngay va sua Vision truoc.

---

## 10. Trinh tu commissioning an toan tu dau den cuoi

### BUOC 1 - Chay backend Vision khong bridge

Muc tieu:

- xac nhan Vision tu no da on dinh

Dat:

- `enabled=false`

Chay:

```bash
python mainProcess.py
```

Neu muon test backend theo cach van hanh gan production hon:

```bash
chmod +x run_forever.sh
./run_forever.sh --no-frontend
```

Kiem tra:

- `outputs/runtime/agv_latest.json`
- `outputs/runtime/process_latest.json`
- `outputs/runtime/cameras/*.json`

Pass khi:

- zone state cap nhat on dinh
- `occupied/empty/unknown` phan anh dung hien truong

### BUOC 2 - Dien bang mapping va review noi bo

Muc tieu:

- xac nhan file config dung nghiep vu

Thao tac:

1. Lap bang mapping.
2. Dien vao `configs/hik_rcs.json`.
3. Doc lai tung dong.
4. So tung `camera_id`, `zone_id` voi file zone config.
5. So tung `positionCode`, `podCode`, `ctnrCode`, `ctnrTyp` voi bang confirm cua HIK.

Pass khi:

- khong con dong mapping nao mo ho
- khong con zone nao chua xac dinh API business

### BUOC 3 - Test callback rieng

Muc tieu:

- xac nhan HIK co the goi nguoc ve Vision

Dat:

- `callback_server.enabled=true`

Chay:

```bash
python tools/hik_rcs_cli.py serve-callbacks
```

Sau do:

- nho ben HIK goi test callback
- hoac dung cong cu noi bo neu co

Kiem tra:

- `outputs/runtime/hik_rcs/callbacks/agvCallback_latest.json`
- `outputs/runtime/hik_rcs/callbacks/warnCallback_latest.json`
- `outputs/runtime/hik_rcs/callbacks/bindNotify_latest.json`

Pass khi:

- callback den dung path
- file callback duoc tao
- neu bat validate token thi callback pass xac thuc

### BUOC 4 - Bat bridge o che do dry-run

Dat:

```json
"enabled": true,
"dry_run": true
```

Chay:

```bash
python mainProcess.py
```

Neu dang setup tren may van hanh, khuyen nghi chay:

```bash
chmod +x run_forever.sh
./run_forever.sh
```

Luc nay:

- bridge van doc state that
- van tao request dung theo logic
- nhung khong gui ra HIK
- neu backend/frontend crash, watchdog se tu khoi dong lai

Kiem tra:

- `outputs/runtime/hik_rcs/bridge_state.json`
- log backend
- `outputs/runtime/supervisor/supervisor.log`

Luu y:

- do `dry_run` trong code hien tai tra response gia va khong ghi `http_exchange.jsonl`
- vi vay o buoc nay hay tap trung xem:
  - state trong `bridge_state.json`
  - log console cua backend

Pass khi:

- moi zone doi state tao dung `bind_dispatch` hoac `lock_dispatch`
- state `occupied` sinh `indBind=1`
- state `empty` sinh `indBind=0`
- state `unknown` sinh `lockPosition(indBind=0)` neu mapping yeu cau

### BUOC 5 - Test tung zone bang CLI truoc

Muc tieu:

- test logic dispatch tung zone ma khong can doi camera

Lenh:

```bash
python tools/hik_rcs_cli.py bind-zone --camera-id cam101 --zone-id A1 --state occupied --dry-run
python tools/hik_rcs_cli.py bind-zone --camera-id cam101 --zone-id A1 --state empty --dry-run
python tools/hik_rcs_cli.py bind-zone --camera-id cam101 --zone-id A1 --state unknown --dry-run
```

Voi moi zone can nghiem thu, lap lai 3 lenh tren.

Ban phai ghi lai:

- API nao duoc chon
- payload business field la gi
- req_code co duoc tao
- `unknown` co dispatch `lockPosition` hay khong

Pass khi:

- logic trung khop bang mapping da duoc ky xac nhan

### BUOC 6 - Test request tay voi HIK that

Muc tieu:

- xac nhan host, port, token, path, xac thuc deu dung

Chay tung API truoc:

```bash
python tools/hik_rcs_cli.py query-task --task-code TASK-001
python tools/hik_rcs_cli.py query-agv --map-short-name test
python tools/hik_rcs_cli.py lock-position --position-code P-A1 --action disable
python tools/hik_rcs_cli.py lock-position --position-code P-A1 --action enable
```

Neu co mot payload JSON duoc HIK cap:

```bash
python tools/hik_rcs_cli.py call-rpc genAgvSchedulingTask payload.json
```

Pass khi:

- HIK tra response hop le
- khong bao loi auth
- khong bao loi sai path

### BUOC 7 - Bat request that cho 1 zone duy nhat

Muc tieu:

- khoanh pham vi rui ro

Thao tac:

1. Trong `configs/hik_rcs.json`, chi bat `enabled=true` cho 1 mapping.
2. Dat:
   - `"enabled": true`
   - `"dry_run": false`
3. Restart backend:

```bash
python mainProcess.py
```

Khuyen nghi o site that:

```bash
chmod +x run_forever.sh
./run_forever.sh
```

Kiem tra:

- `outputs/runtime/hik_rcs/http_exchange.jsonl`
- console backend
- callback files
- phan ung thuc te cua HIK/AGV
- `outputs/runtime/supervisor/supervisor.log`

Pass khi:

- request gui that dung API
- payload dung code business
- response `code="0"` hoac thanh cong theo site
- neu co callback thi callback den
- AGV/AMR phan ung dung nghiep vu

### BUOC 8 - Lap lai cho tung zone con lai

Sau khi 1 zone dau tien pass:

1. Bat them 1 mapping nua.
2. Test lai 3 tinh huong:
   - `occupied`
   - `empty`
   - `unknown`
3. Ghi lai bien ban.

Khong bat toan bo zone cung luc neu chua co nghiem thu zone dau tien.

### BUOC 9 - Chay nghiem thu toan he thong

Muc tieu:

- xac nhan toan bo luong van hanh end-to-end

Ban test phai co:

- nguoi phu trach Vision
- ky su HIK/RCS
- nguoi phu trach AGV/AMR
- neu can, nguoi WMS/MES

Can test:

- co hang
- khong co hang
- che camera
- mat mang camera
- restart backend
- callback ve
- request fail va retry

---

## 11. Quy tac pass/fail cho tung tinh huong nghiem thu

### 11.1 Tinh huong `occupied`

Ky vong:

- Vision xuat `state=occupied`
- `binding=bind`
- bridge dispatch API business dung
- `indBind=1`
- response HIK thanh cong
- AGV/AMR hanh xu dung theo quy trinh

### 11.2 Tinh huong `empty`

Ky vong:

- Vision xuat `state=empty`
- `binding=unbind`
- bridge dispatch API business dung
- `indBind=0`
- response HIK thanh cong
- AGV/AMR hanh xu dung theo quy trinh

### 11.3 Tinh huong `unknown`

Ky vong:

- Vision xuat `state=unknown`
- bridge khong bind/unbind mu
- neu mapping yeu cau:
  - `lockPosition(indBind=0)`
- AGV/AMR khong duoc coi zone nay la an toan cho scheduling

### 11.4 Tinh huong callback

Ky vong:

- callback file duoc tao trong `outputs/runtime/hik_rcs/callbacks/`
- token/client dung neu callback validation dang bat
- callback payload luu lai duoc

### 11.5 Tinh huong request loi

Ky vong:

- request duoc ghi vao `http_exchange.jsonl`
- bridge khong spam lien tuc
- retry theo `retry_interval_sec`

---

## 12. Cach doc cac file log va bang chung commissioning

### 12.1 `outputs/runtime/agv_latest.json`

Dung de xac nhan:

- output Vision noi bo
- camera nao dang online/offline
- zone state hien tai

### 12.2 `outputs/runtime/process_latest.json`

Dung de xac nhan:

- snapshot backend day du hon
- camera nao co debug

### 12.3 `outputs/runtime/hik_rcs/bridge_state.json`

Dung de xac nhan:

- zone nao da duoc dispatch
- req_code cuoi cung la gi
- response cuoi cung la gi
- lock state va bound state hien tai

### 12.4 `outputs/runtime/hik_rcs/http_exchange.jsonl`

Dung de xac nhan:

- request that gui den dau
- payload that gui di la gi
- http_status la bao nhieu
- HIK tra `code`, `message` gi

### 12.5 `outputs/runtime/hik_rcs/callbacks/`

Dung de xac nhan:

- HIK co goi nguoc callback hay khong
- route callback la gi
- payload callback co du du lieu nghiep vu hay khong

---

## 13. Nhung diem can dac biet luu y khi di site that

### 13.1 `agv_latest.json` khong phai la HIK request

Day chi la snapshot local.

Neu co ben thu ba muon doc file local de tich hop rieng, co the dung file nay.
Nhung voi HIK RCS/AMR, phan truyen thong thuc te van la REST bridge.

### 13.2 Mapping dung quan trong hon HTTP client

HTTP client dung nhung mapping sai van that bai nghiep vu.
Day la ly do khong duoc tu dien `positionCode` hoac `podCode`.

### 13.3 Token dung nhung path sai van that bai

Neu HIK bao:

- 404
- unsupported interface
- invalid request

Can kiem tra:

- `rpc_base_path`
- `query_agv_path`
- `include_interface_name`

### 13.4 `unknown` phai duoc coi la fail-safe

Khong duoc coi `unknown` nhu `empty`.
Neu coi `unknown` la `empty`, AGV co the thao tac sai vi tri.

### 13.5 Khong mo rong pham vi test qua nhanh

Chi test:

- 1 zone
- roi 1 camera
- roi 1 nhom camera
- roi moi den toan bo line

### 13.6 Watchdog khong thay the `systemd` hoac service manager cua OS

`run_forever.sh`, `run_forever.cmd` va `tools/run_forever.py` se giu he thong song khi:

- backend crash
- frontend crash
- child process exit bat thuong

Nhung watchdog nay van song trong user session hien tai.

Vi vay:

- neu may shutdown, watchdog cung dung
- neu user logoff hoac desktop session ket thuc, watchdog cung dung
- tren Ubuntu, neu muon auto-run sau reboot, phai cau hinh them `systemd`
- tren Windows, neu muon auto-run sau reboot hoac sau logon, phai cau hinh them Task Scheduler hoac service Windows

### 13.7 Khuyen nghi cho Ubuntu Server

Neu may la Ubuntu Server va nhiem vu chinh la:

- sinh output runtime
- bridge sang HIK RCS
- khong can mo GUI tai chinh may do

Thi khuyen nghi production:

- chay `run_forever.sh --no-frontend`
- dang ky bang `systemd`
- chi mo frontend tren may desktop giam sat rieng neu can
- neu ky su quen khong truyen `--no-frontend` tren Linux headless, supervisor se tu phat hien khong co `DISPLAY`/`WAYLAND_DISPLAY` va ha xuong backend-only

---

## 14. Troubleshooting chi tiet

### Loi 1 - Bridge khong gui gi ca

Kiem tra theo thu tu:

1. `configs/hik_rcs.json` co `enabled=true` chua
2. mapping co `enabled=true` chua
3. `camera_id` va `zone_id` trong mapping co ton tai that khong
4. zone co dang `unknown` vi health/score khong dat khong
5. co dang de `dry_run=true` khong

### Loi 2 - GUI thay dung nhung HIK khong co request

Kiem tra:

1. `agv_latest.json` co state dung khong
2. `bridge_state.json` co dispatch entry khong
3. `http_exchange.jsonl` co exchange khong
4. host/port dung khong
5. firewall co chan outbound khong

### Loi 3 - HIK tra loi auth fail

Kiem tra:

- `client_code`
- `token_code`
- sai moi truong test/prod
- token da het han hay chua

### Loi 4 - HIK tra loi sai du lieu

Kiem tra:

- sai `method`
- sai `positionCode`
- sai `podCode`
- sai `ctnrCode`
- thieu `ctnrTyp`
- thieu `stgBinCode` va `positionCode`
- object code khong ton tai trong RCS

### Loi 5 - Callback khong ve

Kiem tra:

- callback server co dang chay khong
- `callback_server.enabled=true` chua
- HIK co dang goi dung URL khong
- port co mo khong
- firewall Windows co chan khong
- ben HIK dang goi `/service/rest/...` hay `/service/rest/agvCallbackService/...`

### Loi 6 - `unknown` xuat hien nhieu lam bridge khoa lien tuc

Kiem tra:

- camera rung
- anh sang thay doi
- ROI sai
- threshold score qua cao
- camera health khong on dinh
- `require_online_health` co phu hop site khong

### Loi 7 - Request thanh cong nhung AGV khong phan ung

Kiem tra:

- HIK da nhan request business dung chua
- callback/notification co ve khong
- scheduling rule ben RCS co cho phep khong
- AGV dang o trang thai san sang khong
- use-case da chon dung API business chua

---

## 15. Bien ban nghiem thu de khuyen nghi lap tai site

Voi moi zone, lap 1 dong bien ban:

| ngay gio | camera_id | zone_id | method | tinh huong | Vision state | payload gui | response HIK | callback | hanh vi AGV | ket qua |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-03-24 10:30 | cam101 | A1 | bindPodAndBerth | co hang | occupied | indBind=1 | code=0 | co | dung | PASS |

Tinh huong toi thieu phai co:

- co hang
- khong co hang
- unknown
- restart backend
- callback

Chua co bien ban nay thi chua nen chot production-ready.

---

## 16. Tieu chi de duoc phep bat live

Chi bat live khi dat du tat ca dieu kien sau:

1. Vision detect dung tai hien truong.
2. Bang mapping duoc HIK/WMS/AGV xac nhan.
3. Dry-run pass.
4. Test API tay pass.
5. It nhat 1 zone gui request that pass.
6. Callback test pass.
7. AGV/AMR phan ung dung tren hien truong.
8. Da lap bien ban nghiem thu.

Thieu bat ky dieu kien nao o tren:

- khong bat live toan bo he thong.

---

## 17. Thu tu thao tac chuan khi ra nha may

Hay in muc nay ra giay va danh dau tung buoc.

1. Xac nhan camera online.
2. Xac nhan output Vision dung.
3. Xac nhan host/port HIK.
4. Xac nhan token/client code.
5. Xac nhan bang mapping.
6. Sua `configs/hik_rcs.json`.
7. Bat callback server.
8. Test callback.
9. Bat bridge `enabled=true`, `dry_run=true`.
10. Test tung zone bang CLI.
11. Test tung zone bang camera that.
12. Test API tay voi HIK that.
13. Chuyen `dry_run=false` cho 1 mapping.
14. Test 1 zone live.
15. Test callback live.
16. Test AGV phan ung live.
17. Lap lai cho tung zone con lai.
18. Test `unknown`.
19. Test restart backend.
20. Chot bien ban nghiem thu.

---

## 18. Ket luan thuc te nhat

Phan code cua du an nay da san sang de tich hop ve mat ky thuat.

Phan quyet dinh thanh cong khi ra hien truong nam o 4 diem:

- mapping nghiep vu dung
- auth dung
- callback dung
- test tung zone day du

Neu ban di dung thu tu trong tai lieu nay, khong bo qua buoc nao, va luon luu bang chung log/callback/bien ban test, thi ban se setup he thong theo cach an toan va co the kiem soat duoc rui ro trong commissioning.
