# HUONG DAN SU DUNG HE THONG CCTV AGV

Tai lieu nay danh cho cong nhan van hanh, ky thuat vien van hanh tai nha may.

Muc tieu:

- biet cach mo chuong trinh
- biet cach xem ket qua
- biet khi nao he thong binh thuong
- biet khi nao can bao ky thuat vien

---

## 1. He thong nay dung de lam gi

He thong camera nay dung de kiem tra tai tung vi tri:

- co hang
- khong co hang
- hoac chua chac chan

He thong se gui thong tin nay cho AGV/AMR de hoat dong dung quy trinh.

---

## 2. Y nghia ket qua

### 2.1 `occupied`

Nghia la:

- vi tri dang co hang

### 2.2 `empty`

Nghia la:

- vi tri dang trong

### 2.3 `unknown`

Nghia la:

- he thong chua chac chan
- hoac camera dang co van de
- hoac du lieu chua cap nhat on dinh

Khi thay `unknown`, khong tu y ket luan la co hang hay khong co hang.

---

## 3. Cach mo chuong trinh

He thong thuong se co 2 phan:

- phan xu ly backend
- phan man hinh giam sat frontend

Ky thuat vien se cau hinh san. Nguoi van hanh chi can mo theo dung thu tu.

### 3.1 Mo backend truoc

Chay:

```bash
python mainProcess.py
```

### 3.2 Mo giao dien giam sat sau

Chay:

```bash
python mainCCTV.py
```

Neu chi mo `mainCCTV.py` ma khong mo `mainProcess.py`, man hinh co the khong co du lieu.

---

## 4. Cach xem man hinh

## 4.1 Man hinh grid camera

Moi o la 1 camera.

Neu o camera co hinh:

- he thong dang nhan duoc du lieu camera

Neu o camera hien `No Signal`:

- backend chua co hinh
- hoac camera dang mat ket noi
- hoac he thong chua mo backend

## 4.2 Man hinh detail

Khi bam vao 1 camera:

- ben trai: hinh goc
- ben phai: hinh da xu ly
- ben duoi: thong tin zone va trang thai

---

## 5. Cach thao tac hang ngay

1. Mo `mainProcess.py`
2. Mo `mainCCTV.py`
3. Quan sat grid camera
4. Bam vao camera can xem chi tiet
5. Doc trang thai `occupied`, `empty`, `unknown`
6. Theo doi xem tat ca camera can thiet co hoat dong binh thuong khong

---

## 6. Dau hieu he thong dang binh thuong

He thong duoc coi la binh thuong khi:

- tat ca camera can thiet deu co hinh
- trang thai zone cap nhat lien tuc
- khong bi dung hinh lau
- khong co qua nhieu `unknown`

---

## 7. Khi nao can bao ky thuat vien

Can bao ngay khi co mot trong cac truong hop sau:

- camera mat hinh lau
- nhieu camera cung `No Signal`
- trang thai `unknown` xuat hien lau bat thuong
- man hinh bi dung
- ket qua hien thi khong dung voi thuc te
- chuong trinh khong mo duoc
- AGV nhan sai thong tin so voi thuc te hien truong

---

## 8. Cach khoi dong lai khi loi nhe

Neu he thong bi tre nhe hoac man hinh khong cap nhat:

1. Dong `mainCCTV.py`
2. Dong `mainProcess.py`
3. Mo lai `mainProcess.py`
4. Mo lai `mainCCTV.py`

Neu van loi, bao ky thuat vien.

---

## 9. Nhung dieu khong duoc tu y lam

Khong tu y:

- sua file config
- sua duong dan camera
- sua model
- xoa file trong thu muc output
- tat backend khi he thong dang van hanh

Neu can thay doi, goi ky thuat vien hoac nguoi phu trach he thong.

---

## 10. Cach hieu nhanh ket qua tren thuc te

### 10.1 Neu vi tri dang co hang

He thong dung mong doi:

- `occupied`

### 10.2 Neu vi tri dang trong

He thong dung mong doi:

- `empty`

### 10.3 Neu he thong chua chac

He thong hien:

- `unknown`

Truong hop nay can:

- nhin lai camera
- doi them mot luc ngan
- neu van `unknown` thi bao ky thuat vien

---

## 11. Muc tieu cuoi cung cua he thong

He thong nay tra loi cau hoi rat don gian cho AGV:

- vi tri nay co hang hay khong

Ket qua he thong:

- `occupied` -> co hang
- `empty` -> khong co hang
- `unknown` -> chua chac chan

---

## 12. Lien he ho tro

Khi co van de:

- ghi lai camera nao bi loi
- ghi lai thoi gian bi loi
- chup man hinh neu can
- bao ngay cho ky thuat vien hoac nguoi phu trach he thong
