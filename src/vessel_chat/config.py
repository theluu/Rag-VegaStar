"""Cấu hình ứng dụng.

Mọi giá trị đọc từ biến môi trường (hoặc file `.env`). Kết nối, secret, tên model và
đường dẫn dữ liệu KHÔNG có giá trị mặc định trong mã: thiếu thì `require()` báo lỗi rõ ràng
khi khởi động. Các ngưỡng có mặc định hợp lý nhưng đều ghi đè được.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Kết nối / secret / model (bắt buộc cấu hình) ---
    database_url: str = ""
    test_database_url: str = ""
    openai_api_key: str = ""
    openai_base_url: str | None = None
    llm_model: str = ""
    embedding_model: str = ""
    data_dir: str = ""

    embedding_dim: int = 1536
    llm_temperature: float = 0.1
    llm_timeout_seconds: float = 60.0
    summary_max_tokens: int = 600

    # --- Bộ nhớ hội thoại ---
    memory_window_turns: int = 6
    memory_window_max_tokens: int = 6000
    memory_top_k: int = 4
    memory_min_score: float = 0.25
    memory_compaction_wait_seconds: float = 20.0
    debug_memory_events: bool = True

    # --- Vòng lặp tool ---
    max_tool_iterations: int = 8
    tool_result_max_rows: int = 30

    # --- Xử lý dữ liệu AIS ---
    max_plausible_speed_knots: float = 50.0
    track_gap_split_hours: float = 3.0
    position_max_offset_minutes: float = 60.0
    interpolation_max_gap_minutes: float = 180.0
    vessel_match_threshold: float = 0.35
    company_match_threshold: float = 0.45
    multi_track_max_vessels: int = 1000
    multi_track_max_points: int = 60000
    max_tracks_per_page: int = 100

    # --- Hạ tầng ---
    db_statement_timeout_ms: int = 15000
    db_pool_min: int = 1
    db_pool_max: int = 10
    cors_origins: str = ""
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def require(self, *names: str) -> None:
        missing = [n.upper() for n in names if not getattr(self, n)]
        if missing:
            raise RuntimeError(f"Thiếu biến môi trường bắt buộc: {', '.join(missing)} (xem .env.example)")


@lru_cache
def get_settings() -> Settings:
    return Settings()
