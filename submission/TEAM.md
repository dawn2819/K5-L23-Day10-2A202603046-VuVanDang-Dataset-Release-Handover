# Nhóm Day 10 — Bàn giao dataset & Truy vết (K5-L23)

- **Seed luyện tập đề xuất:** `3007` (hoặc seed nhóm thống nhất)
- **Repo:** `https://github.com/dawn2819/K5-L23-Day10-2A202603046-VuVanDang-Dataset-Release-Handover`

## 1. Thành viên & Phân công vai trò

| Họ và tên | MSHV | Tài khoản GitHub | Phần chính phụ trách |
|---|---|---|---|
| **Vũ Văn Đăng** (Người A) | 2A202603046 | dawn2819 | **Lead Engine:** Xây dựng `validator/validate.py` (9 lỗi luật + module đối chiếu chéo cross-check YOLO ↔ Panoptic), đo F1, review 50% ảnh nghi vấn |
| **<<Thành viên 2>>** (Người B) | <<MSHV>> | <<GitHub>> | **Lead Pipeline:** Xây dựng công cụ xem ảnh, script tự động bàn giao lô v2 (`handover/`), truy vết (`trace.json`), bảo mật (`security.md`), review 50% ảnh nghi vấn |

---

## 2. Bản đồ công việc chi tiết cho 2 thành viên

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                         QUY TRÌNH PHỐI HỢP NHÓM 2 NGƯỜI                          │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │
        ┌────────────────────────────────┴────────────────────────────────┐
        ▼                                                                 ▼
┌──────────────────────────────────────────────┐  ┌──────────────────────────────────────────────┐
│        NGƯỜI A: THUẬT TOÁN & BỘ KIỂM         │  │       NGƯỜI B: PIPELINE & BÀN GIAO           │
│             (Vũ Văn Đăng)                    │  │              (Thành viên 2)                  │
├──────────────────────────────────────────────┤  ├──────────────────────────────────────────────┤
│ 1. Viết `validator/validate.py`:             │  │ 1. Viết công cụ xem ảnh (Visualizer Helper): │
│    - Bắt 9 lỗi luật (F1 target = 1.0)        │  │    - Hiển thị song song ảnh + box + mask      │
│    - Ghép Detection ↔ Panoptic               │  │    - Hỗ trợ zoom cận cảnh vật thể nghi vấn    │
│    - Xuất `candidates.json` đã lọc nhiễu     │  │                                              │
│ 2. Chạy thử nghiệm trên nhiều seed & lô sạch │  │ 2. Xây dựng pipeline Bàn giao Lô v2:         │
│ 3. Review 50% số ảnh trong `candidates.json` │  │    - Tách `rework_queue.csv` (đúng người)     │
│ 4. Chốt `errors.json` cùng Người B           │  │    - Sinh `manifest.csv`, `label_summary.csv` │
│ 5. Đề ẩn: Chạy lệnh quét lỗi trong 2 phút đầu│  │    - Chuẩn hóa `truyvet.csv` & `README.txt`   │
│                                              │  │    - Đạt 17/17 PASS kiểm định `check_handover`│
│                                              │  │ 3. Lập `trace.json` (truy vết ticket AI)     │
│                                              │  │ 4. Soạn `security.md` & `REPORT.md`          │
│                                              │  │ 5. Review 50% số ảnh trong `candidates.json` │
└──────────────────────────────────────────────┘  └──────────────────────────────────────────────┘
```

---

## 3. Quy trình làm việc theo từng Pha (Checkpoints 4 Giờ)

### Pha 0: Chuẩn bị & Đồng bộ môi trường (15')
1. **Cả 2 người:** Clone repo về máy:
   ```bash
   git clone https://github.com/dawn2819/K5-L23-Day10-2A202603046-VuVanDang-Dataset-Release-Handover.git
   cd K5-L23-Day10-2A202603046-VuVanDang-Dataset-Release-Handover
   ```
2. **Cả 2 người:** Tải dữ liệu ảnh COCO val2017 (khoảng 1 GB, chỉ chạy 1 lần):
   ```bash
   python scripts/download_public.py
   ```
3. Tạo lô luyện tập seed `3007`:
   ```bash
   python scripts/run_lab.py --seeds 3007
   ```

### Pha 1: Bắt lỗi luật (40')
- **Người A:** Code 9 hàm bắt lỗi luật trong `validator/validate.py` (file, class, bbox tràn mép, duplicate box, scene leak, guideline mismatch, category panoptic, thing overlap).
- **Người B:** Xây dựng script xem ảnh (Visualizer helper) để chuẩn bị cho Pha 2.

### Pha 2: Đối chiếu & Review bằng mắt (55')
- **Người A:** Hoàn thiện module ghép YOLO ↔ Panoptic trong `validate.py`, chạy lệnh trích xuất ứng viên:
  ```bash
  python validator/validate.py runs/r3007/delivery --out runs/r3007/rules.json --candidates runs/r3007/candidates.json
  ```
- **Cả 2 người chia đôi danh sách ứng viên:**
  - Người A xem nửa đầu danh sách.
  - Người B xem nửa sau danh sách.
  - Dùng công cụ của Người B để mở ảnh, xác định lỗi và ghi vào `runs/r3007/review_log.csv` (`image,type,verdict,note` — note $\ge 20$ ký tự, miêu tả chi tiết thấy gì trên ảnh).
- Gộp lỗi:
  ```bash
  python scripts/merge_review.py --rules runs/r3007/rules.json --review runs/r3007/review_log.csv --out runs/r3007/errors.json
  python scripts/score_findings.py --run runs/r3007
  ```

### Pha 3 & 4: Quyết định, Lineage & Bàn giao v2 (55')
- **Người B chủ trì (Người A hỗ trợ review):**
  1. Ghi nhận Lineage cho v1 (nếu tỉ lệ lỗi $> 2\% \implies$ HOLD):
     ```bash
     python scripts/lineage.py record --event decision --release-id <release_id_v1> --decision HOLD
     python scripts/lineage.py impact --release-id <release_id_v1>
     ```
  2. Tạo thư mục bàn giao v2: `runs/r3007/handover/<release_id_v1>_v2/` gồm 7 phần.
  3. Đóng gói & kiểm tra:
     ```bash
     python scripts/pack_release.py runs/r3007/handover/<release_id_v1>_v2
     python scripts/lineage.py record --event release --release-id <release_id_v1>_v2 --parent <release_id_v1>
     python scripts/check_handover.py --run runs/r3007
     ```
     *(Phải đạt 17/17 PASS không còn dòng FAIL nào).*

### Pha 5: Truy vết Ticket AI (20')
- **Người B:** Đọc `incoming/ticket.md` và `guideline/changelog.md` của lô, điền `runs/r3007/trace.json`:
  - `tier_a`: Các ảnh trong cảnh ticket nêu, thuộc job guideline cũ v1.2, có box detection lớp bị đổi quy tắc.
  - `tier_b`: Các ảnh còn lại trong lô thỏa mãn điều kiện trên.
  - `notify`: Danh sách annotator và reviewer phụ trách các job ở tier_a và tier_b.

### Pha 6: Bảo mật (10') & Đề Ẩn (40')
- **Bảo mật:** Người B hoàn thành `runs/r3007/security.md` (3 tình huống: USB/remote, 5 hành vi bảo mật, ca khuôn mặt: HOLD + mã ảnh người thật trong lô).
- **Đề ẩn (40 phút):**
  1. Giải nén `de_an.zip` vào thư mục gốc được folder `delivery/`.
  2. Người A chạy:
     ```bash
     python validator/validate.py delivery --out submission/de_an/rules.json --candidates submission/de_an/candidates.json
     ```
  3. Người A và B chia đôi danh sách ứng viên, soi ảnh và ghi `submission/de_an/review_log.csv`.
  4. Gộp lỗi thành `submission/de_an/errors.json`.
  5. Người B xuất `submission/de_an/trace.json`.
  6. Chạy `python scripts/export_submission.py --run runs/r3007` để đồng bộ bài luyện tập sang `submission/r3007/`.
  7. Commit và Push lên Git trước hạn!

---

## 4. Quy ước Commit Git (Bắt buộc theo Rubric)

Mỗi người **phải có ít nhất 2 commit có nội dung thực tế**, mang đúng username/email của mình:

- **Người A (dawn2819):**
  - Commit 1: `P1: Implement 9 rule-based validation checks in validate.py`
  - Commit 2: `P2: Implement cross-check matching between YOLO and Panoptic masks`
- **Người B:**
  - Commit 1: `P2: Add lightweight visualizer tool and review findings`
  - Commit 2: `P4-P5: Complete handover v2 pipeline, trace.json and security.md`
