# WORKSHEET CHOT TICH HOP UI RCS-2000 <-> VISION

Tai lieu nay dung khi ban dang co:

- code Vision bridge trong project
- API Developer Guide cua HIK RCS-2000
- file `UIRCS.pdf` la anh chup giao dien that cua RCS

Muc tieu cua worksheet:

1. Nhin giao dien that cua RCS va xac dinh dung tham so can dien.
2. Quy doi thong tin tren UI sang field trong `configs/hik_rcs.json`.
3. Chot duoc 1 quy trinh test live nho, an toan, co bang chung.

---

## 1. Tu duy chot nhanh

Dieu can chot khong phai la "Vision gui occupied sang RCS the nao".

Dieu can chot la:

- zone nao map vao business object nao trong RCS
- UI RCS dang quan ly object bang ma nao
- site nay dung API business nao
- callback URL tren RCS dang tro ve dau

Neu 4 diem nay chua ro, chua test live.

---

## 2. Bang quy doi UI RCS -> config bridge

Dung bang nay khi mo `UIRCS.pdf` hoac dang ngoi truoc man hinh RCS.

| Nhom thong tin tren UI RCS | Can tim tren UI | Dien vao dau trong project | Ghi chu |
|---|---|---|---|
| Server host/IP | IP hoac hostname server RCS | `configs/hik_rcs.json -> host` | Khong doan, phai lay dung moi truong test/prod |
| RPC port | Port cho REST service cua `hikRpcService` | `rpc_port` | Thuong 8182 nhung phai doi chieu site |
| DPS port | Port query AGV | `dps_port` | Thuong 8083 |
| Client code | Ma client he thong Vision | `client_code` | Phai duoc HIK cap |
| Token code | Token xac thuc | `token_code` | Khong bo trong neu site yeu cau auth |
| RPC path | Duong dan REST service | `rpc_base_path` | Mac dinh `/rcms/services/rest/hikRpcService` |
| Query AGV path | Duong dan query trang thai AGV | `query_agv_path` | Mac dinh `/rcms-dps/rest/queryAgvStatus` |
| Callback base URL | URL RCS goi nguoc ve Vision | `callback_server.base_path` va config tren RCS | Thuong `/service/rest` hoac `/service/rest/agvCallbackService` |
| Position code | Ma vi tri trong RCS | `mapping.position_code` | Day la field can xac nhan ky nhat |
| Pod code | Ma rack/trolley/pod | `mapping.pod_code` | Dung cho `bindPodAndBerth` hoac `bindPodAndMat` |
| Material lot | Ma lot vat tu | `mapping.material_lot` | Dung cho `bindPodAndMat` |
| Container code | Ma pallet/container | `mapping.ctnr_code` | Dung cho `bindCtnrAndBin` |
| Container type | Loai container/pallet | `mapping.ctnr_typ` | Dung cho `bindCtnrAndBin` |
| Storage bin code | Ma bin/staging bin | `mapping.stg_bin_code` | Dung cho `bindCtnrAndBin` |
| Map short name | Alias ban do AGV | Payload `query-agv` | Can de test query AGV |
| Task code | Ma lenh/tac vu | Payload `query-task` | Can de test query task |

---

## 3. Bang mapping phai lap khi doc UI

Khong sua `configs/hik_rcs.json` truoc khi dien xong bang nay.

| camera_id | zone_id | doi tuong that tren hien truong | man hinh UI RCS dang thay ma gi | method | positionCode | podCode | materialLot | ctnrCode | ctnrTyp | stgBinCode | unknown_action | da xac nhan voi ai |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cam1 | A1 |  |  |  |  |  |  |  |  |  | lockPosition |  |
| cam1 | A2 |  |  |  |  |  |  |  |  |  | lockPosition |  |
| cam2 | A1 |  |  |  |  |  |  |  |  |  | lockPosition |  |

Quy tac chon `method`:

- Neu UI/business dang quan ly rack tai mot vi tri: `bindPodAndBerth`
- Neu UI/business dang gan rack voi lot vat tu: `bindPodAndMat`
- Neu UI/business dang quan ly pallet/container/bin: `bindCtnrAndBin`
- Neu zone la vung an toan chi can co vat la AGV phai dung: `lockPosition`

---

## 4. Nhung man hinh can tim trong UIRCS.pdf

Khi xem `UIRCS.pdf`, hay danh dau nhung man hinh sau:

1. Trang system parameter hoac integration parameter
2. Trang callback/config external interface
3. Trang quan ly position/bin/berth
4. Trang quan ly rack/pod/container/material lot
5. Trang AGV status
6. Trang task status
7. Trang alarm/warn/notification

Moi khi gap mot man hinh, hay tu hoi:

- Man hinh nay xac nhan duoc field nao trong config?
- Ma dang hien thi la ma business that hay chi la ten hien thi?
- Truong nay co phai `positionCode/podCode/ctnrCode` hay khong?

---

## 5. Checklist chot callback

Can chot ro 5 diem:

1. RCS goi callback ve host nao cua Vision?
2. RCS goi vao base path nao:
   - `/service/rest`
   - hay `/service/rest/agvCallbackService`
3. RCS co gui `tokenCode` va `clientCode` trong payload hay khong?
4. RCS co goi du ca 3 callback sau hay chi mot phan:
   - `agvCallback`
   - `warnCallback`
   - `bindNotify`
5. Site co bat firewall chan port callback khong?

Config doi chieu:

```json
"callback_server": {
  "enabled": true,
  "host": "0.0.0.0",
  "port": 9000,
  "base_path": "/service/rest/agvCallbackService",
  "validate_token_code": false
}
```

Neu UI/tai lieu site dang dung base URL kieu:

- `http://<vision-host>:9000/service/rest`

thi code hien tai van nhan duoc ca:

- `/service/rest/agvCallbackService/agvCallback`
- `/service/rest/agvCallbackService/warnCallback`
- `/service/rest/agvCallbackService/bindNotify`

Va cung chap nhan bien the base path co hoac khong co `agvCallbackService`.

---

## 6. Mau config chot 1 zone dau tien

Chi bat 1 zone duy nhat de test live dau tien.

```json
{
  "enabled": true,
  "dry_run": true,
  "scheme": "http",
  "host": "192.168.1.200",
  "rpc_port": 8182,
  "dps_port": 8083,
  "rpc_base_path": "/rcms/services/rest/hikRpcService",
  "query_agv_path": "/rcms-dps/rest/queryAgvStatus",
  "http_timeout_sec": 5.0,
  "client_code": "VISION01",
  "token_code": "TOKEN_FROM_HIK",
  "include_interface_name": false,
  "require_online_health": true,
  "min_score": 0.6,
  "retry_interval_sec": 5.0,
  "callback_server": {
    "enabled": true,
    "host": "0.0.0.0",
    "port": 9000,
    "base_path": "/service/rest/agvCallbackService",
    "validate_token_code": false
  },
  "mappings": [
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
  ]
}
```

Luu y:

- `enabled=true` o cap toan cuc cho phep bridge xet dispatch
- `dry_run=true` de test logic truoc
- chi bat 1 mapping

---

## 7. Trinh tu test thuc dia ngan gon nhat

### Buoc 1. Chot tham so tu UI

Chot du:

- `host`
- `rpc_port`
- `dps_port`
- `client_code`
- `token_code`
- callback base URL
- 1 dong mapping day du cho 1 zone

Luu y cho thang may:

- Neu phia AGV chi can biet thang may dang an toan hay khong an toan, thi can xin dung `positionCode` cua thang may trong RCS.
- Truong hop nay khong can `podCode`, `materialLot`, `ctnrCode`.
- Mapping uu tien se la `method=lockPosition`.

### Buoc 2. Test callback rieng

Ky vong:

- RCS goi ve dung path
- file callback sinh ra trong `outputs/runtime/hik_rcs/callbacks/`

### Buoc 3. Test logic dry-run

Ky vong:

- `occupied` sinh bind `indBind=1`
- `empty` sinh unbind `indBind=0`
- `unknown` sinh `lockPosition(indBind=0)` neu da chon fail-safe

### Buoc 4. Test request tay

Uu tien:

- `queryTaskStatus`
- `queryAgvStatus`
- `lockPosition disable`
- `lockPosition enable`

Neu 4 lenh nay chua thong, chua test bind live.

### Buoc 5. Bat live 1 zone duy nhat

Dat:

- mapping duy nhat `enabled=true`
- `dry_run=false`

Ky vong:

- request vao dung endpoint
- response thanh cong
- callback neu co thi ve
- RCS/AGV hanh xu dung

---

## 8. Tieu chi ket luan "co the thanh cong"

Co the tu tin di tiep neu va chi neu:

1. UI RCS cho thay dung business code that cua zone dang test.
2. Ban da map duoc zone do vao dung 1 trong 3 method business.
3. Callback URL duoc xac nhan bang UI hoac bo phan HIK.
4. Test tay `query` va `lockPosition` da pass.
5. Dry-run cua zone dau tien da dung logic.

Neu 5 dieu nay dat, thi phan con lai khong con la "mo ho protocol" nua, ma chi la commissioning co kiem soat.

---

## 9. Ket luan thuc chien

Voi code hien tai trong project nay, protocol giao tiep dang dung la:

`Vision zone state -> business mapping -> REST API HIK RCS -> callback/notification tu RCS`

No khong phai bai toan thieu code nen khong chay.
No la bai toan phai chot dung:

- ma business
- endpoint
- auth
- callback
- thu tu test

Khi doi chieu `UIRCS.pdf`, hay dung worksheet nay de dien lan luot. Sau do moi sua `configs/hik_rcs.json` va test live.
