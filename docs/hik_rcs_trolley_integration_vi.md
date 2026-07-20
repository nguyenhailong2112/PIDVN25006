# Tich Hop Trolley Vision -> HIK RCS-2000

Tai lieu nay la ban tong quan cho chu trinh FMR trolley. Huong van hanh hien tai da chot: Vision dung `bindCtnrAndBin` cho trolley, va moi diem hang trolley dung `hybrid_canonical` de chay song song FMR + cong nhan.

Chi tiet truyen thong va checklist onsite nam tai [docs/hik_rcs_trolley_bind_ctnr_vi.md](C:\Users\longn\PyCharmMiscProject\PIDVN25006\docs\hik_rcs_trolley_bind_ctnr_vi.md).

## 1. Ket luan API

Trong tai lieu `UD35865B_RCS-2000 API_Developer Guide_V3.3_20231204(1)`, cac API bind lien quan gom:

- `bindCtnrAndBin`
- `bindPodAndBerth`
- `bindPodAndMat`

Voi site hien tai, team du an da chot FMR trolley se di theo `bindCtnrAndBin`, vi mapping RCS dang duoc quan ly theo storage bin/container tuong tu AMR pallet. Hai API `bindPod...` chi giu lai nhu phuong an tham khao neu sau nay RCS doi mo hinh trolley thanh pod/rack nghiep vu.

## 2. Vai tro cua Vision

Vision chi xac nhan:

- ROI co trolley hay khong.
- Zone dang `occupied`, `empty`, hoac `unknown`.
- Khi co/khong on dinh thi gui bind/unbind toi RCS.
- Khi RCS/FMR hoac cong nhan tao ra actual ctnr khac static ctnr cua diem, Vision canonical hoa ve static ctnr cua diem do.

Vision khong thay RCS dieu phoi task FMR trong phase hien tai.

## 3. Camera va zone trolley

| Camera | Khu vuc | Zone |
| --- | --- | --- |
| `cam2` | Coil | `A1`..`A5` |
| `cam3` | Warehouse | `A1`, `A2`, `B1`, `B2` |
| `cam7` | Thang may FMR | dang `enabled=false` |
| `cam8` | 3T | `A1`..`A9` |
| `cam11` | Coil | `A1`..`A7` |

Tong so diem hang trolley dang bat: 25 diem, khong tinh `cam7` thang may.

## 4. Chu trinh FMR can cover

- `3T -> Coil`: pick `cam8 A4..A9`, put `cam2 A1..A4`.
- `Coil -> 3T`: pick `cam2 A5`, put `cam8 A1..A3`.
- `Coil -> Warehouse`: pick `cam11 A1..A7`, put `cam3 A1`, `A2`, `B1`, `B2`.

Chu trinh co the van hanh song song voi cong nhan. Vi vay moi diem trolley khong nen chi dung bind/unbind static thuan tuy, ma phai dung canonical session de xu ly actual ctnr do RCS/FMR tao ra.

## 5. Policy runtime

Trong [configs/hik_rcs.json](C:\Users\longn\PyCharmMiscProject\PIDVN25006\configs\hik_rcs.json), moi mapping trolley non-elevator phai co:

```json
{
  "method": "bindCtnrAndBin",
  "dispatch_policy": "hybrid_canonical",
  "canonical_owner": "canonical_trolley",
  "unknown_action": "lockPosition"
}
```

Y nghia:

- `hybrid_canonical`: Vision chap nhan ca manual flow va RCS/FMR record flow, sau do dua Storage Bin Management ve ma static cua diem hien tai.
- `canonical_owner=canonical_trolley`: tach session trolley khoi canonical FG pallet, giup log/reconcile ro rang.
- `unknown_action=lockPosition`: neu camera/runtime khong du tin cay, Vision khong suy dien empty; tuy site can xac nhan lockPosition co phu hop voi diem trolley do hay khong.

## 6. BindNotify la bat buoc de dat muc chac chan cao

Neu chi nhin ROI, Vision biet co trolley hay khong nhung khong luon biet actual `ctnrCode` RCS dang giu. `bindNotify` cho Vision biet actual ctnr ma RCS vua bind/unbind, tu do canonical hoa dung.

RCS can cau hinh:

- App name: `VISION`
- Base Path: `/service/rest`
- Port Vision: `2112`
- Task Notify: `bindCtnrAndBin`
- Notification path: `/bindNotify`

URL mau:

```text
http://<VISION_IP>:2112/service/rest/bindNotify
```

## 7. Quy trinh rollout

1. Xac nhan ROI `cam2`, `cam3`, `cam8`, `cam11` dung voi mat bang thuc te.
2. Xac nhan 25 mapping trong `hik_rcs.json` khop RCS: `position_code`, `stg_bin_code`, `ctnr_code`, `ctnr_typ`.
3. Xac nhan RCS da bat `bindNotify`.
4. Test CLI dry-run cho 1 diem moi camera.
5. Test request that cho 1 diem moi camera.
6. Test FMR task that co RCS record, kiem tra Vision canonical hoa ctnr diem put.
7. Test manual trolley vao/ra cung cum diem, kiem tra khong xung dot voi ctnr FMR.
8. Moi cho chay full camera trolley.

## 8. Dau hieu pass/fail

Pass khi:

- RCS Interface Call Log co request bind/unbind tu Vision.
- Vision co callback `bindNotify` trong `outputs/runtime/hik_rcs/callbacks`.
- Storage Bin Management cuoi cung luon hien thi ctnr static cua diem hien tai.
- Diem pick co the bind lai sau khi trolley cu da duoc FMR mang sang diem put.
- Unknown/che khuat khong gay unbind sai.

Fail/reconcile khi:

- RCS bao storage bin locked.
- RCS bao container incomplete task.
- Ctnr static cua diem pick dang bi giu tai diem put va Vision khong nhan duoc `bindNotify`.
- Mapping trung `ctnr_code` hoac sai `ctnr_typ`.

