"""应用配置：全部从环境变量 / .env 读取，不硬编码。"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_API_DIR = Path(__file__).resolve().parents[1]
_PROJECT_DIR = _API_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(_PROJECT_DIR / ".env", _API_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 应用
    app_name: str = "Echo"
    app_env: str = "development"
    app_debug: bool = True
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    cors_origins: str = "http://localhost:5173"

    # 安全
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    fernet_key: str = ""

    # PostgreSQL
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "echo"
    postgres_password: str = "echo"
    postgres_db: str = "echo"
    # PG 连接池
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30  # 取连接超时（秒）
    db_pool_recycle: int = 1800  # 连接回收（秒），防被 DB 端断开
    db_pool_pre_ping: bool = True  # 取连接前 ping，剔除失效连接
    db_statement_timeout_ms: int = 60000  # 单条 SQL 超时（毫秒）

    # Elasticsearch
    es_host: str = "http://localhost:9200"
    es_username: str = ""
    es_password: str = ""
    es_max_retries: int = 3
    es_request_timeout: int = 30  # 秒
    es_max_connections: int = 25

    # Neo4j
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "echoneo4j"
    neo4j_max_pool_size: int = 50
    neo4j_connection_timeout: int = 30  # 秒

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    redis_max_connections: int = 50
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # 每日新闻邮件
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = "回声 Echo"
    smtp_security: str = "starttls"  # starttls | ssl | none

    # 文件存储
    storage_backend: str = "local"  # local | oss
    storage_dir: str = "./storage"

    # 阿里云 OSS
    oss_endpoint: str = ""
    oss_access_key_id: str = ""
    oss_access_key_secret: str = ""
    oss_bucket_name: str = ""

    # 日志
    log_level: str = "INFO"  # DEBUG/INFO/WARNING/ERROR
    log_to_console: bool = True
    log_to_file: bool = True
    log_file_path: str = "./logs/echo.log"
    log_max_bytes: int = 10 * 1024 * 1024  # 单文件 10MB
    log_backup_count: int = 5  # 轮转保留份数
    db_echo: bool = False  # 是否打印 SQL（调试用，默认关，避免日志刷屏）

    # 知识库 RAG
    embedding_dims: int = 1024  # 向量维度，ES 索引与 embed 调用统一用此值
    rag_docling_enabled: bool = True
    rag_docling_do_ocr: bool = True
    rag_docling_max_pages: int = 100
    rag_docling_max_file_size: int = 50 * 1024 * 1024
    rag_docling_cache_dir: str = "./storage/docling-models"
    rag_parse_time_limit_seconds: int = 900

    # 全局搜索语义门控（精确导向）：只展示余弦相似度 ≥ 阈值的结果，没有就不展示
    # 阈值为真实余弦相似度（-1~1），按实测可调；偏高更精准、偏低召回更多
    global_search_min_vector_score: float = 0.45
    memory_search_min_vector_score: float = 0.45

    # 反思引擎（归纳高层洞察 Insight）
    reflection_top_k: int = 25  # 反思输入：top-N 高重要度/高频实体
    reflection_stmt_per_entity: int = 4  # 每个实体取几条代表性陈述
    reflection_min_insights: int = 3  # 期望产出洞察下限
    reflection_max_insights: int = 6  # 期望产出洞察上限
    reflection_min_entities: int = 5  # 实体少于此数不反思（信息太少）
    reflection_trigger_threshold: int = 20  # 增量触发：累计新增记忆达标触发一次反思

    # 记忆主动召回（对话每轮注入相关记忆 + 洞察）
    active_recall_entity_top_k: int = 5  # 召回实体数
    active_recall_insight_top_k: int = 2  # 召回洞察数
    active_recall_min_score: float = 0.5  # 实体召回余弦门控（低于不注入，节流防噪声）
    active_recall_min_confidence: float = 0.6  # 低于此置信度的记忆不进入回答侧主动召回
    active_recall_uncertain_confidence: float = 0.75  # 低于此置信度的记忆注入时标为待确认
    active_recall_max_chars: int = 600  # 注入背景块长度上限

    # 跨会话上下文（注入最近其他会话的摘要，默认关）
    cross_session_max_convs: int = 3  # 取最近几个其他会话
    cross_session_turns_per_conv: int = 4  # 每会话取最后几轮
    cross_session_max_chars: int = 1200  # 注入上限

    # 深度研究
    research_max_queries: int = 8
    research_search_top_k: int = 8
    research_search_concurrency: int = 2
    research_search_retries: int = 3
    research_fetch_top_n: int = 8
    research_fetch_concurrency: int = 4
    research_fetch_timeout: int = 12
    research_source_truncate_chars: int = 3000
    research_max_sections: int = 6
    research_kb_top_k: int = 6
    research_mcp_enabled: bool = True
    research_mcp_max_iterations: int = 3
    research_mcp_timeout: int = 40
    research_section_context_sources: int = 6
    research_distill_concurrency: int = 4
    research_relevance_min: float = 0.3
    research_max_learnings: int = 60
    research_reflection_rounds: int = 1
    research_reflection_max_queries: int = 4
    research_learnings_per_section: int = 10
    research_subquestions_per_section: int = 3
    research_source_quality_filter: bool = True
    research_min_source_chars: int = 120

    # Verifier Loop
    loop_enabled: bool = True
    loop_verifier_kind: str = "same"
    loop_max_iterations: int = 2

    # Agent Tracing
    tracing_enabled: bool = True
    tracing_sample_rate: float = 1.0
    tracing_batch_size: int = 20
    tracing_flush_interval: float = 2.0
    tracing_queue_maxsize: int = 5000

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
