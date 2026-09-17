# Loại tàu theo mã AIS

## Cấu trúc mã loại tàu
Mã loại tàu AIS (ship and cargo type, ITU-R M.1371) là số hai chữ số. Chữ số đầu cho biết nhóm tàu, chữ số sau cho biết loại hàng nguy hiểm đang chở:
- x0: mọi tàu thuộc loại này ("all ships of this type").
- x1: chở hàng nguy hiểm, hàng độc hại hoặc chất ô nhiễm biển (DG/HS/MP) nhóm X — mức rủi ro cao nhất theo phụ lục II MARPOL.
- x2: nhóm Y.
- x3: nhóm Z.
- x4: nhóm OS (other substances – chất khác).
- x9: không có thông tin bổ sung.
Nhãn như "Cargo ships, carrying DG and/or MHB, HS, or MP, IMO hazard or pollutant category X" nghĩa là tàu hàng đang khai báo chở hàng nguy hiểm nhóm X. Vì khai báo tay, nhãn có thể không phản ánh đúng chuyến đi hiện tại.

## Các nhóm mã chính
- 30: tàu đánh cá.
- 31, 32: tàu đang lai kéo (32: đoàn kéo dài trên 200 m hoặc rộng trên 25 m).
- 33: tàu nạo vét hoặc công trình dưới nước; 34: tàu phục vụ lặn; 35: tàu quân sự; 36: tàu buồm; 37: tàu du lịch, giải trí.
- 40–49: tàu cao tốc (HSC).
- 50: tàu hoa tiêu; 51: tàu tìm kiếm cứu nạn; 52: tàu lai dắt (tug); 53: tàu phục vụ cảng; 54: tàu chống ô nhiễm; 55: tàu thực thi pháp luật; 58: tàu y tế.
- 60–69: tàu khách.
- 70–79: tàu hàng (cargo) — gồm tàu container, tàu hàng rời, tàu hàng tổng hợp, tàu chở ô tô…
- 80–89: tàu chở chất lỏng (tanker) — dầu thô, sản phẩm dầu, hoá chất, khí hoá lỏng LPG/LNG.
- 90–99: các loại khác.

## Nhóm loại tàu dùng trong hệ thống
Để người dùng hỏi bằng từ thông dụng, hệ thống gộp nhãn AIS thành các nhóm:
- cargo (tàu hàng): mọi nhãn bắt đầu bằng "Cargo" — tàu container, hàng rời, hàng tổng hợp, ro-ro.
- tanker (tàu chở dầu, hoá chất, khí): mọi nhãn bắt đầu bằng "Tanker".
- fishing (tàu cá), tug (tàu kéo, lai dắt, kể cả "Towing"), passenger (tàu khách), high_speed (tàu cao tốc HSC), pleasure (tàu du lịch, tàu buồm).
- special (tàu công vụ): nạo vét, hoa tiêu, thực thi pháp luật, nghiên cứu, hỗ trợ ngoài khơi, quân sự.
- other (loại khác) và unknown (chưa rõ: "Not available", "Reserved").
Cột "loại tàu chi tiết" (ship_type_detail_name) lấy từ đăng kiểm, ví dụ "Container Ship", "Bulk Carrier", "LPG Tanker", nên cụ thể hơn nhãn AIS.
