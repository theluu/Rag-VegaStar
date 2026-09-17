# Mã nhận dạng tàu

## MMSI
MMSI (Maritime Mobile Service Identity) là số 9 chữ số dùng để nhận dạng thiết bị vô tuyến của tàu, phát trong mọi bản tin AIS. Ba chữ số đầu là MID (Maritime Identification Digits) cho biết quốc gia cấp số, thường trùng với quốc gia treo cờ. Một số MID thường gặp ở vùng Biển Đông: 574 Việt Nam; 412, 413, 414 Trung Quốc; 477 Hồng Kông; 416 Đài Loan; 563, 564, 565, 566 Singapore; 525 Indonesia; 533 Malaysia; 548 Philippines; 567 Thái Lan; 351–357 và 370–373 Panama; 636 Liberia; 538 Quần đảo Marshall; 215, 229, 248, 249, 256 Malta. MMSI có thể thay đổi khi tàu đổi cờ, nên không phải khoá định danh vĩnh viễn.

## IMO
Số IMO gồm 7 chữ số, gắn với thân tàu suốt vòng đời, không đổi khi đổi tên, đổi cờ hay đổi chủ. Chữ số cuối là số kiểm tra: nhân 6 chữ số đầu lần lượt với 7, 6, 5, 4, 3, 2, cộng lại, chữ số hàng đơn vị của tổng phải bằng chữ số cuối. Ví dụ với số 9074729: 9×7 + 0×6 + 7×5 + 4×4 + 7×3 + 2×2 = 139, chữ số cuối là 9 — hợp lệ. Tàu nhỏ, tàu cá thường không có số IMO, vì vậy cột IMO có thể rỗng.

## Hô hiệu (callsign)
Hô hiệu là mã vô tuyến gồm chữ và số do quốc gia treo cờ cấp, dùng khi liên lạc bằng thoại. Tiền tố cho biết quốc gia (ví dụ 9V Singapore, 3F/3E/H3 Panama, VR Hồng Kông, XV Việt Nam).

## Tên tàu
Tên tàu không phải định danh duy nhất: nhiều tàu có thể trùng tên, tên có thể viết khác nhau (dấu cách, số La Mã) và một số bản ghi không có tên. Khi tra cứu, nên ưu tiên MMSI hoặc IMO; nếu dùng tên mà có nhiều kết quả, hệ thống sẽ liệt kê để người dùng chọn.

## Trong hệ thống
Mỗi tàu có một vessel_id nội bộ dùng làm khoá nối giữa bảng vị trí, bảng dark gap và bảng chủ sở hữu. Người dùng có thể hỏi theo tên (không phân biệt hoa thường, chấp nhận sai chính tả nhẹ), MMSI, IMO hoặc hô hiệu.
