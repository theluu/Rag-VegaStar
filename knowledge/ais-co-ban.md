# AIS cơ bản

## AIS là gì
AIS (Automatic Identification System – hệ thống nhận dạng tự động) là thiết bị trên tàu tự động phát bản tin vô tuyến VHF chứa danh tính, vị trí, tốc độ và hướng đi. Công ước SOLAS bắt buộc lắp AIS loại A cho tàu từ 300 GT chạy tuyến quốc tế, tàu hàng từ 500 GT và mọi tàu khách. Tàu nhỏ, tàu cá, tàu du lịch thường dùng AIS loại B (công suất thấp hơn, phát thưa hơn). Bản tin được thu bởi trạm bờ (tầm khoảng 20–40 hải lý) và vệ tinh (phủ rộng nhưng có thể thu không liên tục ở vùng đông tàu).

## Tần suất phát bản tin
Theo chuẩn ITU-R M.1371, AIS loại A phát bản tin vị trí mỗi 2–10 giây khi tàu đang chạy (càng nhanh hoặc càng đổi hướng thì càng dày) và khoảng 3 phút khi tàu neo hoặc cập cầu. AIS loại B phát thưa hơn, thường 30 giây đến 3 phút. Bộ dữ liệu tổng hợp thường đã được lấy mẫu thưa lại (vài phút một điểm), nên khoảng cách giữa hai điểm liên tiếp lớn hơn tần suất phát thực tế.

## Các trường trong bản tin vị trí
- Vị trí (vĩ độ, kinh độ) theo hệ WGS84, độ thập phân.
- SOG (speed over ground – tốc độ so với mặt đất), đơn vị hải lý/giờ (knot), bước 0,1 knot; giá trị 102,3 nghĩa là không có dữ liệu.
- COG (course over ground – hướng di chuyển thực), đơn vị độ, 0–359,9.
- Heading (hướng mũi tàu), đơn vị độ; giá trị 511 nghĩa là không có dữ liệu (tàu không nối la bàn con quay với AIS).
- Trạng thái hành hải (navigational status) do sĩ quan trên tàu chọn tay.
- Mớn nước (draught) và điểm đến (destination) là dữ liệu hành trình do thuyền viên nhập tay, có thể sai hoặc không cập nhật.
Khác biệt giữa COG và heading là bình thường khi có dòng chảy, gió hoặc khi tàu đứng yên.

## Trạng thái hành hải (navigational status)
Mã trạng thái theo ITU-R M.1371 và cách hiểu:
- 0 – Under way using engine: đang chạy bằng máy.
- 1 – At anchor: đang thả neo.
- 2 – Not under command: mất khả năng điều động (hỏng máy, hỏng lái…).
- 3 – Restricted manoeuvrability: hạn chế khả năng điều động (đang làm công việc như nạo vét, lai dắt, tiếp nhiên liệu).
- 4 – Constrained by her draught: bị hạn chế bởi mớn nước, phải đi trong luồng sâu.
- 5 – Moored: đã buộc dây, cập cầu.
- 6 – Aground: mắc cạn.
- 7 – Engaged in fishing: đang đánh bắt cá.
- 8 – Under way sailing: đang chạy bằng buồm.
- 9, 10, 13 – Reserved (dự phòng cho tàu cao tốc, tàu WIG và mục đích sau này).
- 11, 12 – tàu kéo phía sau / đẩy phía trước (dùng theo khu vực).
- 14 – AIS-SART, MOB-AIS, EPIRB-AIS đang hoạt động: thiết bị cứu nạn phát tín hiệu.
- 15 – Undefined (default): chưa khai báo.
Vì trạng thái do người nhập, cần đối chiếu với tốc độ: tàu báo "Moored" nhưng SOG 12 knot là dữ liệu mâu thuẫn. Trong bộ dữ liệu, "Class B" xuất hiện ở cột trạng thái cho các tàu dùng AIS loại B (loại này không phát trường trạng thái).

## Giới hạn của dữ liệu AIS
AIS có thể bị tắt, bị nhiễu, bị giả mạo vị trí (spoofing) hoặc khai báo sai danh tính. Các điểm "nhảy" bất thường (tốc độ suy ra giữa hai điểm vượt xa khả năng của tàu) thường là lỗi GPS hoặc lỗi giải mã. Khi phân tích nên kết hợp nhiều nguồn và luôn nêu rõ độ tin cậy.
