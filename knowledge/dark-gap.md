# Mất tín hiệu AIS (dark gap)

## Định nghĩa trong bộ dữ liệu
Một "dark gap" là khoảng thời gian liên tục từ 3 giờ trở lên mà không thu được bản tin AIS nào của tàu. Mỗi sự kiện ghi: thời điểm mất và thời điểm có lại tín hiệu (UTC), độ dài (giây), vị trí điểm cuối trước khi mất và điểm đầu sau khi có lại, khoảng cách đường thẳng giữa hai điểm (hải lý) và tốc độ suy ra (khoảng cách chia cho thời gian).

## Nguyên nhân thường gặp
- Ngoài vùng phủ sóng: tàu ở xa trạm bờ, hoặc vệ tinh thu không liên tục ở vùng biển đông tàu — nguyên nhân phổ biến nhất.
- Ra khỏi vùng dữ liệu: bộ dữ liệu chỉ gồm điểm trong vùng 102–118°E, 6–23°N, nên tàu đi ra ngoài vùng rồi quay lại sẽ tạo khoảng trống.
- Lỗi thiết bị, mất nguồn điện, bảo dưỡng.
- Chủ động tắt AIS: có thể vì lý do an ninh (vùng có cướp biển) nhưng cũng là dấu hiệu rủi ro được giới phân tích quan tâm — đánh bắt bất hợp pháp (IUU), chuyển tải hàng giữa hai tàu trên biển (STS) để né lệnh trừng phạt, đi vào vùng cấm.
Không thể kết luận nguyên nhân chỉ từ một khoảng mất tín hiệu; cần kết hợp bối cảnh.

## Cách diễn giải khi phân tích
- So sánh tốc độ suy ra với tốc độ thường thấy của tàu: tốc độ suy ra gần với tốc độ trước khi mất cho thấy tàu vẫn đi thẳng bình thường (thường do vùng phủ sóng).
- Tốc độ suy ra rất thấp trong khoảng thời gian dài nghĩa là tàu gần như đứng yên hoặc đi vòng — có thể neo đậu, chờ cảng, hoặc hoạt động không khai báo.
- Tốc độ suy ra lớn hơn khả năng của tàu gợi ý lỗi vị trí hoặc giả mạo.
- Vị trí mất và vị trí có lại nằm xa tuyến hàng hải thông thường, hoặc gần một tàu khác cũng mất tín hiệu cùng lúc, là tín hiệu nên điều tra thêm.
- Độ dài khoảng mất tính theo dữ liệu gốc; khe tính từ các điểm vị trí hiện có có thể lệch vài phút so với bảng dark gap vì bảng này được tính trên nguồn dữ liệu dày hơn.

## Tốc độ trước và sau khi mất tín hiệu
Hệ thống lấy tốc độ trước khi mất từ điểm AIS cuối cùng tại hoặc trước thời điểm mất, và tốc độ sau khi có lại từ điểm AIS đầu tiên tại thời điểm có lại. Nếu tàu không còn điểm nào trong dữ liệu sau khi có lại (ví dụ tín hiệu có lại ở ngoài vùng dữ liệu), hệ thống báo không có dữ liệu thay vì suy đoán.
