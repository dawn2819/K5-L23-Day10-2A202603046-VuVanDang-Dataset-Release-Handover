# Bảo mật khi làm việc

## 1. Ca USB: hết giờ, muốn chép lô về nhà làm tiếp

Tuyệt đối không được sao chép dữ liệu của dự án ra thiết bị lưu trữ cá nhân như USB, ổ cứng ngoài hay tải lên Google Drive, gửi qua email cá nhân. Dữ liệu gán nhãn là tài sản sở hữu trí tuệ của tổ chức và thường chịu ràng buộc nghiêm ngặt bởi thỏa thuận bảo mật (NDA). Việc tự ý chép về máy cá nhân hoặc nhờ người khác làm hộ sẽ vi phạm an toàn thông tin nghiêm trọng, làm lộ lọt dữ liệu khách hàng và mất kiểm soát truy vết nguồn gốc. Nếu hết giờ làm việc mà chưa hoàn thành lô, giải pháp chuẩn là lưu lại trạng thái công việc trên hệ thống nội bộ công ty (Git/CVAT server), báo cáo tiến độ với Project Manager hoặc Tech Lead để xin gia hạn hoặc bàn giao tiếp ca làm việc thông qua hạ tầng VPN/VDI bảo mật được phê duyệt.

## 2. Năm việc: được hay không

1. Mở job được giao trên máy công ty: ĐƯỢC. Đây là môi trường làm việc tiêu chuẩn, đã được áp dụng các chính sách bảo mật của doanh nghiệp.
2. Chụp màn hình gửi người quen: KHÔNG ĐƯỢC. Hành vi này làm lộ thông tin dự án ra bên ngoài, vi phạm thỏa thuận bảo mật dữ liệu và đạo đức nghề nghiệp.
3. Chép lô ra USB: KHÔNG ĐƯỢC. Thiết bị lưu trữ ngoài không được kiểm soát có nguy cơ lây nhiễm mã độc và dẫn đến thất thoát dữ liệu bí mật.
4. Dán nhãn thật lên chatbot công cộng: KHÔNG ĐƯỢC. Dữ liệu nhập vào các chatbot bên thứ ba có thể bị lưu lại để huấn luyện mô hình công khai, dẫn đến vi phạm bản quyền và rò rỉ dữ liệu khách hàng.
5. Đưa tài khoản CVAT cho đồng nghiệp: KHÔNG ĐƯỢC. Tài khoản gán nhãn gắn liền với định danh truy vết cá nhân (annotator/reviewer trong jobs.csv). Chia sẻ tài khoản làm sai lệch nhật ký truy vết trách nhiệm và vi phạm quy chế quản lý truy cập.

## 3. Ca khuôn mặt: thấy mặt người rõ trong lô, guideline yêu cầu làm mờ

Quyết định đối với lô này là **HOLD**. Khi phát hiện hình ảnh có khuôn mặt người rõ nét (ví dụ ảnh `000000006763` và `000000009483`) mà chưa được làm mờ (de-identification) theo đúng yêu cầu bảo vệ quyền riêng tư (Privacy & GDPR/PII), người kiểm tra không được tự ý chỉnh sửa hay dùng công cụ cá nhân để xóa/mờ ảnh vì sẽ phá vỡ chuỗi hash SHA-256 và tính toàn vẹn của lô dữ liệu. Quy trình xử lý chuẩn là ghi nhận mã ảnh, chuyển trạng thái kiểm định lô sang **HOLD**, lập ticket báo cáo cho Data Privacy Officer và Data Manager để chuyển lại pipeline tiền xử lý (pre-processing de-identification) tập trung. Chỉ khi toàn bộ hình ảnh chứa thông tin định danh cá nhân được làm mờ đạt chuẩn bảo mật thì lô mới được xem xét phê duyệt Release.
