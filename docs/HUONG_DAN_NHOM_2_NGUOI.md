# Hướng Dẫn & Kế Hoạch Tác Chiến Nhóm 2 Người — Day 10 Lab

> **Dành cho thành viên thứ 2 clone repo về:** Đọc kỹ tài liệu này để nắm ngay toàn bộ quy trình, công cụ và nhiệm vụ của mình. Bạn không cần đọc lại hàng trăm dòng tài liệu dài, chỉ cần làm đúng theo lộ trình này.

---

## 1. Phân chia công việc giữa 2 người

| Hạng mục | Người A (Vũ Văn Đăng - `dawn2819`) | Người B (Bạn) |
|---|---|---|
| **Vai trò chính** | **Lead Engine / Algorithm** | **Lead Pipeline / Handover & Compliance** |
| **Pha 0: Chuẩn bị** | Chạy `download_public.py`, sinh dữ liệu `run_lab.py --seeds 3007`. | Điền thông tin cá nhân vào `submission/TEAM.md`. |
| **Pha 1: Lỗi luật** | Code 9 lỗi luật trong `validator/validate.py`. | Chuẩn bị công cụ xem ảnh trực quan (Visualizer helper). |
| **Pha 2: Đối chiếu & Review** | Code module ghép YOLO ↔ Panoptic để trích xuất `candidates.json`.<br>Review 50% ảnh nghi vấn đầu danh sách. | Dùng công cụ xem ảnh để review 50% ảnh nghi vấn cuối danh sách.<br>Tổng hợp vào `review_log.csv`. |
| **Pha 3: Quyết định & Lineage** | Hỗ trợ tính tỷ lệ lỗi v1. | Chạy `lineage.py record --decision HOLD` và `lineage.py impact`. |
| **Pha 4: Bàn giao Lô v2** | Hỗ trợ review chéo mã hash. | Xây dựng thư mục `handover/<release_id>_v2/` và chạy `check_handover.py` đạt 17/17 PASS. |
| **Pha 5: Truy vết Ticket** | Hỗ trợ đọc changelog. | Viết logic trích xuất `trace.json` (`tier_a`, `tier_b`, `notify`). |
| **Pha 6a: Bảo mật** | Đóng góp ý kiến câu hỏi bảo mật. | Soạn thảo hoàn thiện `security.md` và `REPORT.md`. |
| **Pha 6b: ĐỀ ẨN (40')** | Bấm lệnh quét lỗi tự động ngay khi có đề. Cùng review ảnh. | Cùng review ảnh, trích xuất `trace.json`, kiểm tra `export_submission.py`, commit & push. |

---

## 2. Các lệnh cần thiết (Cheat Sheet)

### Bước 1: Khởi động trên máy của bạn
```bash
# 1. Kiểm tra Python (cần 3.10+)
python --version   # Windows: py --version

# 2. Tải dữ liệu COCO (khoảng 1 GB, chỉ chạy 1 lần)
python scripts/download_public.py

# 3. Tạo lô luyện tập seed 3007 (nếu chưa có thư mục runs/r3007)
python scripts/run_lab.py --seeds 3007
```

### Bước 2: Đo lường & Kiểm thử chất lượng
```bash
# Quét lỗi bằng validator:
python validator/validate.py runs/r3007/delivery --out runs/r3007/rules.json --candidates runs/r3007/candidates.json

# Tự đo điểm F1 (F1 lỗi luật phải ~ 1.0, F1 tổng > 0.9):
python scripts/score_findings.py --run runs/r3007

# Kiểm tra độ chuẩn của bàn giao v2 (H1 - H17):
python scripts/check_handover.py --run runs/r3007
```

### Bước 3: Đồng bộ sang thư mục submission trước khi nộp
```bash
# Copy các file kết quả từ runs/ sang submission/
python scripts/export_submission.py --run runs/r3007
```

---

## 3. Quy tắc "Sống Còn" để không bị trừ điểm

1. **Tuyệt đối không sửa thư mục `runs/r3007/delivery/` (Lô v1):** Bất kỳ chỉnh sửa nào vào v1 sẽ làm sai lệch `release_id` và khiến `check_handover.py` báo FAIL ngay lập tức ở mã H1. Mọi chỉnh sửa chỉ được đưa vào lô `handover/..._v2/`.
2. **Review mắt phải có ghi chú thật ($\ge 20$ ký tự):**
   - Không được ghi cụt ngủn như "OK", "lỗi", "sai lớp".
   - Phải mô tả mắt nhìn thấy gì trên ảnh: ví dụ: *"xe tải lớn có thùng kín phía sau nhưng detection dán nhãn car $\implies$ class_swap"*.
3. **Mỗi người bắt buộc phải có ít nhất 2 commit:**
   - Khi commit trên máy của bạn, hãy đảm bảo git đã cấu hình tên và email của bạn:
     ```bash
     git config user.name "Tên Của Bạn"
     git config user.email "email-cua-ban@gmail.com"
     ```
   - Commit riêng các phần mình làm, không để 1 người commit hộ toàn bộ bài.

---

## 4. Chuẩn bị cho 3 phút vấn đáp (Oral Exam)
Giảng viên sẽ hỏi ngẫu nhiên 1 trong 3 câu:
- **Câu 1:** Mở một đoạn code trong `validator/validate.py` và giải thích nguyên lý hoạt động.
- **Câu 2:** Mở một dòng bất kỳ mà bạn đã ghi `confirmed` hoặc `rejected` trong `review_log.csv` và giải thích bạn đã nhìn thấy gì trên ảnh lúc đó.
- **Câu 3:** Mở file `README.txt` trong lô v2, giải thích tại sao `QC v1 = x/250`, tại sao kết luận `HOLD` (ngưỡng 2%), và tại sao ảnh lỗi Panoptic thì vẫn ở lại v2 còn ảnh lỗi Detection thì bị đưa sang `rework_queue.csv`.
