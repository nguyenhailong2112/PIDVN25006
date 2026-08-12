# Huong dan van hanh tai site - Vision AGV

Tai lieu nay danh cho nguoi van hanh tai site. Muc tieu la biet khi nao chay manual, khi nao bam auto, va can quan sat nhung gi trong qua trinh AGV van chuyen hang.

## 1. Nguyen tac van hanh

He thong Vision co 3 trang thai van hanh:

- `manual`
- `auto + PK_AB`
- `auto + PK_CD`

`manual` la trang thai an toan mac dinh. Khi o `manual`, Vision chi lam nhiem vu nhan dien trang thai hang va dong bo bind/unbind voi RCS. Vision khong tu tao task AGV.

`auto + PK_AB` la lenh cho Vision tu tao task van chuyen tu khu PK hang A va B xuong FG.

`auto + PK_CD` la lenh cho Vision tu tao task van chuyen tu khu PK hang C va D xuong FG.

## 2. Chuan bi truoc khi van hanh

1. Kiem tra chuong trinh Vision dang chay tren PC Vision.
2. Kiem tra cac camera khu PK va FG co hinh anh on dinh.
3. Kiem tra RCS/AGV dang online va san sang nhan task.
4. Kiem tra FG con vi tri trong neu muon chay auto.
5. Kiem tra PDA/ung dung goi API chuyen mode da ket noi duoc toi Vision.

## 3. Van hanh mode manual

Su dung `manual` khi:

- Cong nhan muon van chuyen thu cong.
- Chua muon AGV tu dong tao task.
- Can dung auto de kiem tra lai hang, camera, RCS hoac khu vuc FG.

Trong mode `manual`:

- Vision van nhan dien `occupied` / `empty`.
- Vision van bind/unbind container/bin voi RCS theo trang thai thuc te.
- Vision khong sinh task AGV moi.
- Neu muon AGV chay, nguoi van hanh dung RCS/PDA/quy trinh khac theo thiet lap site.

## 4. Van hanh auto PK_AB

Chi bam `auto + PK_AB` khi:

- PK_AB da du 8 pallet.
- Cac vi tri PK_AB gom: `PK_AA5`, `PK_AA3`, `PK_AA2`, `PK_AA1`, `PK_BB4`, `PK_BB3`, `PK_BB2`, `PK_BB1`.
- FG con it nhat 1 vi tri trong.
- Nguoi van hanh da san sang cho AGV tu dong lay hang.

Khi bam `auto + PK_AB`, Vision se tao task theo thu tu:

1. `PK_AA5`
2. `PK_AA3`
3. `PK_AA2`
4. `PK_AA1`
5. `PK_BB4`
6. `PK_BB3`
7. `PK_BB2`
8. `PK_BB1`

Vision moi lan chi tao 1 task. Task hien tai completed tren RCS thi Vision moi tao task tiep theo.

## 5. Van hanh auto PK_CD

Chi bam `auto + PK_CD` khi:

- PK_CD da du 7 pallet.
- Cac vi tri PK_CD gom: `PK_CC3`, `PK_CC2`, `PK_CC1`, `PK_DD4`, `PK_DD3`, `PK_DD2`, `PK_DD1`.
- FG con it nhat 1 vi tri trong.
- Nguoi van hanh da san sang cho AGV tu dong lay hang.

Khi bam `auto + PK_CD`, Vision se tao task theo thu tu:

1. `PK_CC3`
2. `PK_CC2`
3. `PK_CC1`
4. `PK_DD4`
5. `PK_DD3`
6. `PK_DD2`
7. `PK_DD1`

Vision moi lan chi tao 1 task. Task hien tai completed tren RCS thi Vision moi tao task tiep theo.

## 6. Khi nao auto dung

Auto co the dung hoac khong tao task moi khi:

- PK_AB chua du 8/8 pallet hoac PK_CD chua du 7/7 pallet.
- FG khong con vi tri trong.
- Task dang chay chua completed.
- Trang thai bind/unbind cua vi tri pick hoac put chua hop le.
- Camera/zone bi unknown hoac offline.
- PDA/API chuyen mode ve `manual`.

Luu y quan trong: Theo chuong trinh local hien tai, mode `auto` duoc giu trong file control cho toi khi PDA/API chuyen lai `manual`. Neu cong nhan muon dung quyen tu dong tao task, can bam `manual` tren PDA.

## 7. Sau khi hoan thanh mot dot van hanh

1. Kiem tra AGV da hoan thanh task cuoi cung tren RCS.
2. Kiem tra hang da duoc dua xuong dung khu FG.
3. Neu khong muon Vision tiep tuc tu dong tao task khi dieu kien lai du, bam `manual` tren PDA.
4. Neu muon chay dot tiep theo, chuan bi PK/FG roi bam lai `auto + PK_AB` hoac `auto + PK_CD`.

## 8. Xu ly nhanh khi co bat thuong

Neu bam auto nhung Vision khong tao task:

- Kiem tra PK da du so pallet yeu cau chua.
- Kiem tra FG co slot empty khong.
- Kiem tra Vision dang o dung profile `PK_AB` hoac `PK_CD`.
- Kiem tra AGV/RCS co dang ban task khac khong.
- Bao dev Vision kiem tra log trong `outputs/runtime/auto_dispatch/state.json`.

Neu AGV dang chay ma muon dung tao task moi:

- Bam `manual` tren PDA.
- Vision se khong tao batch/task moi.
- Task da tao tren RCS can xu ly theo quy trinh RCS/AGV tai site.

