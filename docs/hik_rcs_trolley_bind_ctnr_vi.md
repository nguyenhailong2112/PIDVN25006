# FMR Trolley - bindCtnrAndBin + Hybrid Canonical

Tai lieu nay chot huong truyen thong Vision -> HIK RCS cho chu trinh FMR trolley. Quyet dinh hien tai: trolley dung `bindCtnrAndBin`, dong bo voi cach AMR pallet dang truyen thong, nhung dung policy canonical rieng cho trolley.

## 1. Trang thai da trien khai

- Mapping FMR trolley da co trong [configs/hik_rcs.json](C:\Users\longn\PyCharmMiscProject\PIDVN25006\configs\hik_rcs.json).
- Tat ca diem hang trolley non-elevator dang `enabled=true`.
- `cam7` thang may FMR van `enabled=false`, cho team AGV/RCS chot thong tin site.
- Moi diem hang trolley dung:

```json
"method": "bindCtnrAndBin",
"dispatch_policy": "hybrid_canonical",
"canonical_owner": "canonical_trolley"
```

## 2. Co so API HIK

Theo `UD35865B_RCS-2000 API_Developer Guide_V3.3_20231204(1)`:

- `bindCtnrAndBin` bind/unbind container voi storage bin.
- `indBind="1"` la bind.
- `indBind="0"` la unbind.
- `ctnrCode` va `ctnrTyp` la bat buoc.
- It nhat mot trong `stgBinCode` hoac `positionCode` phai co.
- `characterValue` co the dung khi FMR roadway/trait can them dieu kien nghiep vu.

## 3. Mapping trolley hien tai

| Camera | Khu vuc | Zone Vision | Position/ctnr prefix | `ctnr_typ` |
| --- | --- | --- | --- | --- |
| `cam2` | Coil | `A1`..`A5` | `COIL_FF10`..`COIL_FF14` | `3` |
| `cam3` | Warehouse | `A1`, `A2`, `B1`, `B2` | `WH_A1`, `WH_A2`, `WH_B1`, `WH_B2` | `4` |
| `cam8` | 3T | `A1`..`A9` | `3T_A1`..`3T_A9` | `3` |
| `cam11` | Coil | `A1`..`A7` | `COIL_AA1`..`COIL_AA7` | `4` |

Tong so diem trolley non-elevator dang duoc Vision quan ly: 25 diem.

## 4. Chu trinh van hanh FMR trolley

Vision chi quan ly trang thai co/khong trolley tai ROI va truyen bind/unbind cho RCS. Task dieu phoi FMR van do RCS/AGV thuc hien theo process da teach.

Chu trinh da chot theo zone Vision:

- `3T -> Coil`: pick `cam8 A4..A9`, put `cam2 A1..A4`.
- `Coil -> 3T`: pick `cam2 A5`, put `cam8 A1..A3`.
- `Coil -> Warehouse`: pick `cam11 A1..A7`, put `cam3 A1`, `A2`, `B1`, `B2`.

Neu tren RCS co rule FILO/roadway, rule do la rule nghiep vu cua RCS. Vision khong tu sap xep task FMR trong Phase nay; Vision chi dam bao Storage Bin Management phan anh dung vi tri trolley hien tai.

## 5. Hybrid canonical cho trolley

Ly do can `hybrid_canonical`:

- FMR/RCS co the tu bind trolley theo actual `ctnrCode` cua diem pick.
- Cong nhan van co the day trolley thu cong vao/ra cac diem.
- Neu de actual `ctnrCode` cua diem pick nam tai diem put, ctnr do co the bi trung khi diem pick lai co trolley moi.
- Vision phai canonical hoa ve ma static cua diem dang check, tuong tu FG pallet, nhung owner rieng la `canonical_trolley`.

Ket qua mong muon tren Storage Bin Management:

- `cam8 A4` co trolley -> RCS bind `3T_A4` tai bin cua `3T_A4`.
- FMR mang `3T_A4` sang `cam2 A1`; neu RCS record bind actual `3T_A4` tai `COIL_FF10`, Vision doc bindNotify va canonical hoa ve `COIL_FF10`.
- Sau canonical, `3T_A4` duoc giai phong de bind lai tai `cam8 A4` neu cong nhan dat trolley moi.

Nguyen tac:

- Occupied on dinh -> diem do phai co canonical static `ctnr_code` cua chinh diem do.
- Empty on dinh -> unbind actual ctnr neu Vision/RCS da biet actual, uu tien thong tin tu `bindNotify`.
- `unknown` khong bao gio duoc suy ra empty.
- Neu RCS bao bin dang lock hoac container co incomplete task, Vision ghi session can reconcile va khong retry vo han.

## 6. Yeu cau bindNotify tren RCS

De canonical chay chac chan, RCS can bat notify cho `bindCtnrAndBin` ve Vision:

- Application: `VISION`
- Type: `MES System/device access control service (WCS)`
- Vision IP: IP may chay Vision
- Port: `2112`
- Base Path: `/service/rest`
- Task Notify: `bindCtnrAndBin`
- Notification Path: `/bindNotify`
- Full URL mau: `http://<VISION_IP>:2112/service/rest/bindNotify`

Vision luu callback tai:

- `outputs/runtime/hik_rcs/callbacks/bindNotify_latest.json`
- `outputs/runtime/hik_rcs/callbacks/bindNotify.jsonl`

## 7. Checklist test onsite

1. Xac nhan `configs/hik_rcs.json` dung IP RCS, port, token/client neu co.
2. Xac nhan callback server Vision dang bat:

```json
"callback_server": {
  "enabled": true,
  "port": 2112,
  "base_path": "/service/rest"
}
```

3. Test tung zone bang CLI voi `dry_run` truoc:

```bash
python tools/hik_rcs_cli.py bind-zone --camera-id cam2 --zone-id A1 --state occupied --dry-run
python tools/hik_rcs_cli.py bind-zone --camera-id cam2 --zone-id A1 --state empty --dry-run
```

4. Chuyen sang request that, test 1 diem dai dien moi cum:

```bash
python tools/hik_rcs_cli.py bind-zone --camera-id cam2 --zone-id A1 --state occupied
python tools/hik_rcs_cli.py bind-zone --camera-id cam8 --zone-id A4 --state occupied
python tools/hik_rcs_cli.py bind-zone --camera-id cam11 --zone-id A1 --state occupied
python tools/hik_rcs_cli.py bind-zone --camera-id cam3 --zone-id A1 --state occupied
```

5. Kiem tra RCS Storage Bin Management: moi diem phai bind dung canonical static ctnr cua chinh diem do.
6. Thuc hien 1 task FMR that, de RCS bind actual tu diem pick sang diem put.
7. Xac nhan Vision nhan `bindNotify`, sau do canonical hoa diem put ve ctnr static cua diem put.
8. Dat trolley moi vao diem pick cu, xac nhan diem pick bind lai duoc, khong bi trung ctnr.

## 8. Dieu kien nghiem thu

FMR trolley bind/unbind duoc xem la pass khi:

- 25 diem trolley non-elevator co mapping day du va khong trung `position_code`, `stg_bin_code`, `ctnr_code`.
- Manual trolley va FMR trolley co the van hanh song song.
- RCS Storage Bin Management cuoi cung luon ve dang canonical theo diem hien tai.
- Ctnr cua diem pick khong bi giu o diem put sau khi Vision da canonical.
- `bindNotify` co log day du de truy vet actual ctnr.
- Cac loi lock/incomplete task duoc ghi log va chuyen sang trang thai can reconcile, khong spam request.

