# Kết quả chạy kịch bản

Model `gpt-4o-mini`, MEMORY_WINDOW_TURNS = `2`. Chi phí ước tính theo giá $0.15/1M token vào, $0.6/1M token ra.

| Kịch bản | Lượt | Tool call | Lỗi | TTFT TB (s) | Thời gian TB (s) | Token vào | Token ra | Chi phí (USD) |
|---|---|---|---|---|---|---|---|---|
| [Kịch bản 1 — Thông tin tàu, chủ sở hữu và vị trí](s1_vessel_owner_position.md) | 4 | 3 | 0 | 3.52 | 5.84 | 32,726 | 1,540 | 0.0058 |
| [Kịch bản 2 — Đường đi và dark gap](s2_track_dark_gap.md) | 3 | 4 | 0 | 3.49 | 5.08 | 25,787 | 943 | 0.0044 |
| [Kịch bản 3 — Bộ nhớ dài hạn vượt context window](s3_long_memory.md) | 14 | 12 | 0 | 3.48 | 4.38 | 145,984 | 2,038 | 0.0231 |
| [Kịch bản 4 — Dark gap và trả lời khi thiếu dữ liệu](s4_longest_gap_missing_data.md) | 3 | 2 | 0 | 3.02 | 3.85 | 19,289 | 336 | 0.0031 |
| [Kịch bản 5 — Nhiều hành trình trên bản đồ](s5_multi_tracks.md) | 3 | 2 | 0 | 3.38 | 5.1 | 26,820 | 864 | 0.0045 |
| [Biến thể 1 — Tên sai chính tả, đại từ, thời điểm khác](v1_typo_and_followups.md) | 5 | 4 | 0 | 3.47 | 4.86 | 41,002 | 1,109 | 0.0068 |
| [Biến thể 2 — MMSI khác, so sánh ngày](v2_other_mmsi_days.md) | 3 | 3 | 0 | 4.3 | 8.01 | 31,138 | 1,517 | 0.0056 |
| [Biến thể 4 — Diễn đạt khác, hỏi dữ liệu không có](v4_rephrased_gap.md) | 4 | 2 | 0 | 3.06 | 3.89 | 23,533 | 403 | 0.0038 |
| [Biến thể 5 — Công ty và loại tàu khác](v5_other_company_type.md) | 4 | 3 | 0 | 3.67 | 5.64 | 32,476 | 1,138 | 0.0056 |

Transcript đầy đủ từng sự kiện: `results/raw/*.jsonl`. Đáp án đối chiếu bằng SQL: [facts.md](facts.md).
