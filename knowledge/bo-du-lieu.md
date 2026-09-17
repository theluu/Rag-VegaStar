# Bộ dữ liệu của hệ thống

## Phạm vi
- Khoảng 1.000 tàu, dữ liệu vị trí AIS từ 10/09/2026 đến hết 12/09/2026 (UTC).
- Chỉ gồm các điểm nằm trong vùng 102–118°E, 6–23°N. Tàu có thể rời vùng rồi quay lại, tạo ra khoảng không có điểm.
- Bốn bảng: vị trí AIS, thông tin tĩnh của tàu (bản ghi mới nhất), sự kiện mất tín hiệu từ 3 giờ trở lên, và quan hệ tàu – công ty theo vai trò.
- Dữ liệu là ảnh chụp tĩnh cho mục đích phân tích, không phải dữ liệu thời gian thực.

## Chất lượng dữ liệu và cách hệ thống xử lý
- Tên tàu rỗng hoặc gần trùng: tìm theo tên có chuẩn hoá và so khớp gần đúng; nếu mơ hồ thì hỏi lại.
- Điểm GPS nhảy bất thường: điểm mà tốc độ suy ra tới cả điểm trước và điểm sau vượt ngưỡng (mặc định 50 knot) bị loại khỏi thống kê hành trình; số điểm bị loại được báo cùng kết quả.
- Khoảng trống giữa các điểm: khoảng lớn hơn 3 giờ được tách riêng khi vẽ bản đồ và được báo trong phần cảnh báo; quãng đường đi qua khoảng trống được tính theo đường thẳng và nêu riêng.
- Tên công ty có biến thể: chuẩn hoá hậu tố pháp lý; pháp nhân khác tên không bị gộp.
- Nhiều tàu không có thông tin chủ sở hữu hoặc số IMO.
- Vị trí tại một thời điểm: lấy điểm gần nhất trước và sau; nếu cả hai lệch quá 60 phút thì báo không có dữ liệu gần thời điểm đó; nếu hai điểm cách nhau không quá 3 giờ thì nội suy tuyến tính theo thời gian.

## Những gì bộ dữ liệu không có
Không có tên cảng đã ghé, hàng hoá thực tế, thuyền trưởng, thuyền viên, thời tiết, lịch sử trước 10/09/2026 hay sau 12/09/2026. Trường "điểm đến" chỉ là thông tin tàu tự khai báo.
