# FMR Trolley - bindCtnrAndBin + hybrid_canonical

## 1. Muc tieu

Tai lieu nay chot cach Vision truyen thong bind/unbind cho chu trinh FMR trolley.

Quyet dinh hien tai:

- FMR trolley dung `bindCtnrAndBin`, dong bo voi pipeline AMR pallet.
- Tat ca diem hang trolley khong thuoc thang may dung `dispatch_policy = "hybrid_canonical"`.
- Tat ca diem trolley dung `canonical_owner = "canonical_trolley"` de tach session canonical trolley voi cac luong khac.
- Callback `bindNotify` cua RCS la dieu kien bat buoc de Vision biet actual `ctnrCode` ma RCS/FMR vua bind vao slot.
- Thang may `cam7` khong nam trong luong bind/unbind trolley; thang may van di theo `blockArea`.

## 2. Co so API HIK

Theo `UD35865B_RCS-2000 API_Developer Guide_V3.3_20231204(1)`, `bindCtnrAndBin` dung de bind/unbind container va storage bin/position.

Thong so chinh:

- `indBind = "1"`: bind container vao bin/position.
- `indBind = "0"`: unbind container khoi bin/position.
- `ctnrCode`: ma container/trolley can bind hoac unbind.
- `ctnrTyp`: container type.
- `stgBinCode` hoac `positionCode`: vi tri RCS can tac dong.

Voi chu trinh FMR co RCS dieu phoi, RCS co the tu bind actual `ctnrCode` duoc mang tu diem pick sang diem put. Vi vay Vision khong duoc gia dinh rang actual `ctnrCode` tai diem put luon bang static `ctnr_code` trong config. Vision phai doc `bindNotify`, nho actual `ctnrCode`, sau do canonical hoa ve static code cua slot neu can.

## 3. Mapping trolley hien tai

Trong [configs/hik_rcs.json](C:\Users\longn\PyCharmMiscProject\PIDVN25006\configs\hik_rcs.json), cac mapping trolley dang duoc bat cho:

| Camera | Khu vuc | Zone Vision | RCS position | ctnrTyp |
|---|---|---|---|---|
| `cam2` | Coil | `A1` -> `A5` | `COIL_FF10` -> `COIL_FF14` | `3` |
| `cam3` | Warehouse | `A1`, `A2`, `B1`, `B2` | `WH_A1`, `WH_A2`, `WH_B1`, `WH_B2` | `4` |
| `cam8` | 3T | `A1` -> `A9` | `3T_A1` -> `3T_A9` | `3` |
| `cam11` | Coil | `A1` -> `A7` | `COIL_AA1` -> `COIL_AA7` | `4` |

Tong cong: 25 diem trolley.

Moi mapping trolley can co dang:

```json
{
  "enabled": true,
  "camera_id": "cam8",
  "zone_id": "A1",
  "method": "bindCtnrAndBin",
  "dispatch_policy": "hybrid_canonical",
  "canonical_owner": "canonical_trolley",
  "position_code": "3T_A1",
  "stg_bin_code": "...",
  "ctnr_code": "3T_A1",
  "ctnr_typ": "3",
  "unknown_action": "lockPosition"
}
```

## 4. Logic hybrid_canonical cho trolley

### 4.1 Khi Vision thay trolley OCCUPIED

Vision xu ly theo thu tu:

1. Kiem tra session hien tai cua slot.
2. Neu RCS da notify actual `ctnrCode` bang `bindNotify`, Vision dung actual code do lam source truth tam thoi.
3. Neu actual code khac static `ctnr_code` cua slot, Vision canonical hoa:
   - unbind actual `ctnrCode` hien dang nam o slot.
   - bind lai static `ctnr_code` cua chinh slot.
4. Neu actual code da bang static code cua slot, Vision chi danh dau slot dang canonical OK.

Ket qua mong muon: moi slot trolley tren RCS duoc quan ly bang static `ctnr_code` cua chinh slot, tranh viec ma trolley cua diem pick bi giu tai diem put va lam diem pick khong bind lai duoc.

### 4.2 Khi Vision thay trolley EMPTY

Vision khong unbind mu quang theo static code. Vision uu tien:

1. Actual `ctnrCode` da hoc duoc tu `bindNotify`.
2. Static `ctnr_code` cua mapping neu chua co actual code.

Neu RCS bao bin dang locked hoac container co incomplete task, Vision giu session de reconcile sau, khong ep unbind sai trong luc FMR dang thuc hien task.

### 4.3 Khi Vision thay UNKNOWN

`UNKNOWN` khong duoc suy dien thanh `EMPTY`.

Neu mapping co `unknown_action = "lockPosition"` thi bridge co the goi action bao ve theo config hien co. Voi trolley, nen uu tien tuning debounce/hold time cua ROI de tranh nhay trang thai do che khuat hoac trolley di ngang.

## 5. Cau hinh RCS bat buoc

RCS can mo callback:

- Application name: `VISION`
- Type: WCS/device access control service
- IP: IP may Vision
- Port: `2112`
- Protocol: `http`
- Base path phia Vision: `/service/rest`
- Task Notify: `bindCtnrAndBin`
- Notification path: `/bindNotify`

Endpoint day du tren Vision:

```text
http://<VISION_IP>:2112/service/rest/bindNotify
```

## 6. Dieu kien nghiem thu

Trolley hybrid canonical duoc xem la pass khi:

- 25 diem trolley deu co `dispatch_policy = "hybrid_canonical"`.
- 25 diem trolley deu co `canonical_owner = "canonical_trolley"`.
- RCS bind trolley do FMR mang tu diem khac den, Vision nhan duoc `bindNotify`.
- Vision co the unbind actual code va bind lai static code cua slot khi slot OCCUPIED on dinh.
- Khi trolley duoc lay ra khoi slot, Vision unbind dung actual/static code dang duoc quan ly.
- Log locked/incomplete task khong bi retry ep sai vo han; slot duoc giu de reconcile.
- Thang may `cam7` khong bi tac dong boi policy bind/unbind nay.

## 7. Cach audit nhanh truoc khi chay site

Chay:

```powershell
python -m py_compile core\hik_rcs_bridge.py
```

Kiem tra config trolley:

```powershell
python -c "import json; c=json.load(open('configs/hik_rcs.json',encoding='utf-8')); ms=[m for m in c['mappings'] if m.get('method')=='bindCtnrAndBin' and m.get('camera_id') in {'cam2','cam3','cam8','cam11'}]; print(len(ms)); print([m.get('position_code') for m in ms if m.get('dispatch_policy')!='hybrid_canonical' or m.get('canonical_owner')!='canonical_trolley'])"
```

Ket qua mong muon:

```text
25
[]
```

## 8. Ket luan

Ve phia Vision, FMR trolley da duoc scale len cung co che bindNotify/canonical nhu pallet. Diem khac biet quan trong la trolley dung owner rieng `canonical_trolley`, giup chuong trinh quan ly dung actual/static `ctnrCode` cho toan bo diem trolley ma khong lam lan session voi AMR pallet.
