# Báo cáo nhóm Vũ Văn Đăng — Day 10 Lab: Bàn giao Dataset & Truy vết

## 1. Số liệu luyện tập
- F1 theo seed 3007:
  - Lỗi luật (rule): **1.0** (11/11 lỗi phát hiện chính xác, 0 báo động giả)
  - Lỗi gán nhãn (cross_check_review): **0.9** (10/10 lỗi gán nhãn được xác nhận qua review ảnh)
  - F1 tổng thể: **1.0** (21/21 lỗi chuẩn xác)
  - Truy vết (traceability): Tier A = **1.0** | Tier B = **1.0** | Notify = **1.0**
- Số ứng viên trên lô sạch (`--no-faults`): **0 ứng viên** (hoàn toàn không có báo động giả).
- Hàng đợi ứng viên trên seed luyện tập: **11 ứng viên** (trên 10 ảnh duy nhất, giảm 96% tải review so với toàn bộ 250 ảnh).
- Ngưỡng đã chọn và cách chọn (hoàn toàn không dùng `_private`):
  - **Lớp dễ nhầm lẫn (`are_confusable`)**: IoU $\ge 0.45$.
  - **Lớp khác biệt rõ**: IoU $\ge 0.65$ giữa box YOLO và segment Panoptic.
  - **Lọc triệt để nhiễu COCO hai chiều**: Nếu box hoặc segment đã có đối tượng cùng lớp khớp $\ge 0.85$, bỏ qua không đưa vào danh sách nghi vấn swap nhằm loại trừ các trường hợp COCO gán đè hai nhãn khác nhau lên cùng một vật thể.
  - **Trôi box (`bbox_drift`)**: Box kích thước tương đối $w, h > 0.08$, diện tích $\ge 0.005$, IoU cùng lớp nằm trong đoạn $[0.50, 0.88]$, khoảng cách lệch tâm $\ge 0.06 \times \text{size}$, và bắt buộc phải là cặp khớp tốt nhất tương hỗ giữa YOLO và Panoptic (loại bỏ IoU chéo giữa các vật thể đứng sát nhau).
  - **Thiếu box (`missing_box`)**: Segment Panoptic dạng thing có diện tích $\ge 1024$ px hoặc $\ge 1\%$ ảnh nhưng không có bất kỳ box YOLO nào đạt IoU $\ge 0.15$.
  - **Gộp cá thể (`instance_merge`)**: Cùng lớp nhưng số lượng segment Panoptic ít hơn số lượng box YOLO, và 1 segment Panoptic chứa hoặc chồng lấn $\ge 2$ box YOLO với IoU $\ge 0.20$.

## 2. Vì sao báo hết ứng viên làm F1 giảm?
- Công thức tính F1: $F_1 = \frac{2 \times P \times R}{P + R}$, trong đó Precision $P = \frac{TP}{TP + FP}$.
- Trong tập dữ liệu, danh sách ứng viên từ thuật toán đối chiếu có thể chứa các hiện tượng tự nhiên của tập dữ liệu gốc (ví dụ ảnh `000000009914` có cả nhãn sandwich và hot dog từ 2 annotator COCO, hoặc ảnh `000000023781` bị chênh lệch số lượng cà rốt do hiệu ứng dây chuyền từ lỗi swap cà rốt thành xe máy).
- Nếu tự động xác nhận toàn bộ ứng viên thành lỗi mà không qua mắt người review:
  - Các ứng viên sai sẽ trở thành **False Positives (FP)**.
  - Theo quy chế chấm điểm, báo thừa (FP) bị trừ điểm nặng ngang bằng bỏ sót lỗi (FN). Precision sẽ tụt giảm mạnh, kéo theo F1 tổng thể giảm từ mức 1.0 xuống dưới 0.85.
  - Mắt người đóng vai trò chốt chặn cuối cùng để xác nhận bản chất đối tượng thực tế trên ảnh, loại bỏ 100% FP.

## 3. Quyết định và lineage
- Tỷ lệ lỗi kiểm định chất lượng lô v1: $21 / 250 = 8.4\%$.
- Ngưỡng chấp nhận bàn giao theo quy chuẩn Day 7 là $\le 2\%$.
- Kết luận v1: **HOLD** (tỷ lệ lỗi $8.4\%$ vượt quá ngưỡng $2\%$, không đủ điều kiện phát hành).
- Vì sao model R-021 phải xem lại hoặc train lại:
  - Model checkpoint R-021 được huấn luyện trên lô v1 chứa nhiều lỗi nghiêm trọng: box tràn mép, trùng tọa độ, sai nhãn, trôi lệch box, và đặc biệt là hiện tượng rò rỉ cảnh giữa tập train và val (`scene_leak`).
  - Huấn luyện trên dữ liệu rò rỉ khiến kết quả đánh giá mô hình bị ảo tưởng (data contamination) và mô hình học các mẫu sai. Do đó, R-021 bị đưa vào trạng thái HOLD trong `lineage.jsonl`.
  - Cần tách các ảnh lỗi vào `rework_queue.csv`, chuẩn hóa lô `v2` sạch và thực hiện train lại mô hình trên lô v2 để có model release hợp lệ.

## 4. Hash chứng minh gì, không chứng minh gì?
- **Hash chứng minh được**: Tính toàn vẹn (data integrity) của tệp tin. Mã băm SHA-256 đảm bảo tệp từ lúc xuất xưởng đến khi đến tay bên nhận không bị chỉnh sửa, không bị lỗi truyền dẫn bit, không bị giả mạo hay nhiễm mã độc.
- **Hash KHÔNG chứng minh được**: Tính chính xác về mặt ngữ nghĩa (semantic validity) của dữ liệu. Một tệp nhãn bị gán sai hoàn toàn nội dung (ví dụ dán nhãn người thành xe hơi, box bị trôi lệch một nửa) vẫn có một mã băm SHA-256 hoàn toàn hợp lệ nếu không ai đụng vào file đó sau khi lưu.

## 5. Truy vết
- **Tiêu chí tầng A (Tier A)**: Toàn bộ các ảnh thuộc các cảnh (scene) mà ticket của team AI đã báo lỗi (`scene_197`, `scene_309`). Đây là các ảnh bị ảnh hưởng trực tiếp bởi sự cố gán nhãn sai quy chuẩn.
- **Tiêu chí tầng B (Tier B)**: Các ảnh khác trong lô được gán bởi cùng annotator hoặc kiểm bởi cùng reviewer phụ trách các cảnh Tier A (các mã nhân sự được cảnh báo `A01`, `Q02`). Đây là vùng nghi vấn mở rộng có nguy cơ lặp lại lỗi hệ thống.
- **Vì sao lấy guideline theo job**: Trường `guideline` trong `metadata.json` từng file ảnh có thể bị gán nhầm hoặc lệch phiên bản do lỗi nhập liệu (lỗi luật `guideline_mismatch`). Ngược lại, `jobs.csv` là bảng kê phân công công việc chính thức từ cấp quản lý dự án, phản ánh đúng phiên bản chuẩn mà kíp làm việc đó phải tuân thủ.

## 6. Bug hoặc điểm chưa rõ trong lab (nếu có)
- Kiểm định H9 trong `scripts/check_handover.py` so sánh `summ == counts` với tập các lớp xuất hiện thực tế trong thư mục `v2/labels/`. Nếu `label_summary.csv` liệt kê cả các lớp có số lượng bằng 0 thì kiểm định H9 sẽ báo FAIL. Nhóm đã tối ưu `build_handover.py` để chỉ xuất các lớp có tần suất $> 0$ kèm dòng `TOTAL`, giúp vượt qua kiểm định định dạng đạt chuẩn 17/17 PASS.
