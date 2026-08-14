# Huong dan van hanh tai site - Vision AGV

Tai lieu nay danh cho nguoi van hanh tai site. Muc tieu la biet khi nao chay manual, khi nao bam auto, va can quan sat nhung gi trong qua trinh AMR pallet/FMR trolley van chuyen hang.

## 1. Nguyen tac van hanh

He thong Vision co 2 lane van hanh doc lap:

- AMR pallet: `manual`, `auto + PK_AB`, `auto + PK_CD`
- FMR trolley: `manual`, `auto + 3T_COIL`

`manual` la trang thai an toan mac dinh cua tung lane. Khi mot lane o `manual`, Vision van nhan dien trang thai hang va dong bo bind/unbind voi RCS, nhung lane do khong tu tao task AGV moi.

AMR va FMR co the van hanh song song. Vi du AMR dang `auto + PK_AB` thi FMR van co the `auto + 3T_COIL`, vi moi lane co mode, batch va task dang chay rieng.

## 2. Chuan bi truoc khi van hanh

1. Kiem tra chuong trinh Vision dang chay tren PC Vision.
2. Kiem tra cac camera khu PK, FG, 3T, COIL co hinh anh on dinh.
3. Kiem tra RCS/AGV dang online va san sang nhan task.
4. Kiem tra diem put con vi tri trong neu muon chay auto.
5. Kiem tra PDA/ung dung goi API chuyen mode da ket noi duoc toi Vision.

## 3. Van hanh mode manual

Su dung `manual` khi:

- Cong nhan muon van chuyen thu cong.
- Chua muon Vision tu dong tao task.
- Can dung auto de kiem tra lai hang, camera, RCS hoac khu vuc put.

Trong mode `manual`:

- Vision van nhan dien `occupied` / `empty`.
- Vision van bind/unbind container/bin voi RCS theo trang thai thuc te.
- Vision khong sinh task AGV moi cho lane dang manual.
- Neu muon AGV chay, nguoi van hanh dung RCS/PDA/quy trinh khac theo thiet lap site.

## 4. Van hanh auto AMR PK_AB

Chi bam `auto + PK_AB` khi:

- PK_AB da du 8 pallet.
- Cac vi tri PK_AB gom: `PK_AA5`, `PK_AA3`, `PK_AA2`, `PK_AA1`, `PK_BB4`, `PK_BB3`, `PK_BB2`, `PK_BB1`.
- FG con it nhat 1 vi tri trong.
- Nguoi van hanh da san sang cho AMR tu dong lay hang.

Khi bam `auto + PK_AB`, Vision tao task theo thu tu tren. Moi lan Vision chi tao 1 task; task hien tai completed tren RCS thi Vision moi tao task tiep theo.

## 5. Van hanh auto AMR PK_CD

Chi bam `auto + PK_CD` khi:

- PK_CD da du 7 pallet.
- Cac vi tri PK_CD gom: `PK_CC3`, `PK_CC2`, `PK_CC1`, `PK_DD4`, `PK_DD3`, `PK_DD2`, `PK_DD1`.
- FG con it nhat 1 vi tri trong.
- Nguoi van hanh da san sang cho AMR tu dong lay hang.

Khi bam `auto + PK_CD`, Vision tao task theo thu tu tren. Moi lan Vision chi tao 1 task; task hien tai completed tren RCS thi Vision moi tao task tiep theo.

## 6. Van hanh auto FMR 3T_COIL

Chi bam `auto + 3T_COIL` khi:

- Khu 3T da du 3 trolley.
- Cac vi tri pick gom: `3T_A1`, `3T_A2`, `3T_A3`.
- COIL con it nhat 1 vi tri trong.
- Nguoi van hanh da san sang cho FMR tu dong lay trolley.

Khi bam `auto + 3T_COIL`, Vision tao task theo thu tu:

1. `3T_A1`
2. `3T_A2`
3. `3T_A3`

Destination COIL duoc Vision uu tien theo thu tu:

```text
COIL_FF10 -> COIL_FF11 -> COIL_FF12 -> COIL_FF13
```

Moi lan Vision chi tao 1 task FMR. Task hien tai completed tren RCS thi Vision moi tao task tiep theo neu `3T` van con trolley va `COIL` van con vi tri trong.

## 7. Khi nao auto dung

Auto co the dung hoac khong tao task moi khi:

- Source chua du so luong yeu cau: PK_AB 8/8, PK_CD 7/7, 3T_COIL 3/3.
- Destination khong con vi tri trong.
- Task dang chay chua completed.
- Trang thai bind/unbind cua vi tri pick hoac put chua hop le.
- Camera/zone bi unknown hoac offline.
- PDA/API chuyen lane do ve `manual`.

Luu y: Mode cua AMR va FMR la doc lap. Bam `manual` AMR khong lam dung FMR, va nguoc lai.

## 8. API PDA can goi

PC Vision tai site:

```text
192.168.10.44:8023
```

AMR:

```text
POST /service/rest/visionAutoDispatch/amr/setMode
```

FMR:

```text
POST /service/rest/visionAutoDispatch/fmr/setMode
```

Payload AMR auto PK_AB:

```json
{
  "reqCode": "REQ_AUTO_AB_001",
  "operation_mode": "auto",
  "profile_id": "PK_AB",
  "updated_by": "third_party",
  "note": "start auto PK_AB"
}
```

Payload AMR auto PK_CD:

```json
{
  "reqCode": "REQ_AUTO_CD_001",
  "operation_mode": "auto",
  "profile_id": "PK_CD",
  "updated_by": "third_party",
  "note": "start auto PK_CD"
}
```

Payload FMR auto 3T_COIL:

```json
{
  "reqCode": "REQ_AUTO_FMR_001",
  "operation_mode": "auto",
  "profile_id": "3T_COIL",
  "updated_by": "third_party",
  "note": "start auto FMR 3T_COIL"
}
```

Payload manual:

```json
{
  "reqCode": "REQ_MANUAL_001",
  "operation_mode": "manual",
  "profile_id": "PK_AB",
  "updated_by": "third_party",
  "note": "stop auto"
}
```

Voi FMR manual, doi `profile_id` thanh `3T_COIL`.

## 9. Sau khi hoan thanh mot dot van hanh

1. Kiem tra AGV da hoan thanh task cuoi cung tren RCS.
2. Kiem tra hang da duoc dua toi dung khu put.
3. Neu khong muon lane tiep tuc tu dong tao task khi dieu kien lai du, bam `manual` tren PDA cho dung lane.
4. Neu muon chay dot tiep theo, chuan bi source/destination roi bam lai auto tuong ung.

## 10. Xu ly nhanh khi co bat thuong

Neu bam auto nhung Vision khong tao task:

- Kiem tra source da du so luong yeu cau chua.
- Kiem tra destination co slot empty khong.
- Kiem tra Vision dang o dung profile.
- Kiem tra AGV/RCS co dang ban task khac khong.
- Bao dev Vision kiem tra log `outputs/runtime/auto_dispatch_amr/state.json` hoac `outputs/runtime/auto_dispatch_fmr/state.json`.

Neu AGV dang chay ma muon dung tao task moi:

- Bam `manual` tren PDA cho dung lane.
- Vision se khong tao batch/task moi cho lane do.
- Task da tao tren RCS can xu ly theo quy trinh RCS/AGV tai site.
