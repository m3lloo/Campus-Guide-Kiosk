"""
Configuration management for Campus Guide Kiosk.
Centralizes all configuration using environment variables and dataclasses.
"""

import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class FirebaseConfig:
    """Firebase configuration."""

    service_account_key: str = field(
        default_factory=lambda: os.getenv(
            "FIREBASE_KEY_PATH", "firebase/campus_guide_kiosk.json"
        )
    )
    faq_collection: str = field(
        default_factory=lambda: os.getenv("FAQ_COLLECTION", "faqs")
    )
    events_collection: str = field(
        default_factory=lambda: os.getenv("EVENTS_COLLECTION", "events")
    )
    query_logs_collection: str = field(
        default_factory=lambda: os.getenv("QUERY_LOGS_COLLECTION", "query_logs")
    )


@dataclass
class GeminiConfig:
    """Google Gemini API configuration."""

    api_keys: list = field(
        default_factory=lambda: [
            key.strip()
            for key in os.getenv("GEMINI_API_KEYS", "").split(",")
            if key.strip()
        ]
    )
    model: str = field(
        default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    )
    timeout: int = field(default_factory=lambda: int(os.getenv("GEMINI_TIMEOUT", 30)))


@dataclass
class EmbeddingConfig:
    """Embedding model configuration."""

    model_name: str = field(
        default_factory=lambda: os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
    )
    vector_dimension: int = 384  # For all-MiniLM-L6-v2


@dataclass
class AppConfig:
    """Flask application configuration."""

    debug: bool = field(
        default_factory=lambda: os.getenv("FLASK_DEBUG", "False").lower() == "true"
    )
    host: str = field(default_factory=lambda: os.getenv("FLASK_HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("FLASK_PORT", 5000)))
    answer_min_score: float = field(
        default_factory=lambda: float(os.getenv("ANSWER_MIN_SCORE", 0.5))
    )
    cache_max_size: int = field(
        default_factory=lambda: int(os.getenv("CACHE_MAX_SIZE", 128))
    )
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    # Number of trusted reverse proxy hops in front of this app (e.g. nginx = 1).
    # When > 0, Flask trusts X-Forwarded-For/X-Forwarded-Proto from that many
    # hops so rate limiting and logging see the real client IP. Leave at 0
    # (default) when the app is reachable directly — otherwise clients could
    # spoof their IP via those headers and bypass rate limiting.
    trusted_proxy_count: int = field(
        # `or 0` (not just the getenv default) so a blank TRUSTED_PROXY_COUNT=
        # in .env falls back to 0 instead of crashing the app on int("").
        default_factory=lambda: int(os.getenv("TRUSTED_PROXY_COUNT") or 0)
    )


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""

    enabled: bool = field(
        default_factory=lambda: os.getenv("RATE_LIMIT_ENABLED", "True").lower()
        == "true"
    )
    requests_per_minute: int = field(
        default_factory=lambda: int(os.getenv("RATE_LIMIT_RPM", 60))
    )
    requests_per_hour: int = field(
        default_factory=lambda: int(os.getenv("RATE_LIMIT_RPH", 1000))
    )


@dataclass
class SecurityConfig:
    """Security configuration."""

    cors_origins: list = field(
        default_factory=lambda: [
            origin.strip()
            for origin in os.getenv("CORS_ORIGINS", "*").split(",")
            if origin.strip()
        ]
    )
    max_query_length: int = field(
        default_factory=lambda: int(os.getenv("MAX_QUERY_LENGTH", 500))
    )
    sanitize_input: bool = field(
        default_factory=lambda: os.getenv("SANITIZE_INPUT", "True").lower() == "true"
    )


@dataclass
class Config:
    """Main configuration class."""

    firebase: FirebaseConfig = field(default_factory=FirebaseConfig)
    gemini: GeminiConfig = field(default_factory=GeminiConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    app: AppConfig = field(default_factory=AppConfig)
    rate_limit: RateLimitConfig = field(default_factory=RateLimitConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    environment: str = field(
        default_factory=lambda: os.getenv("ENVIRONMENT", "development")
    )

    @classmethod
    def from_env(cls) -> "Config":
        """Create config from environment variables."""
        return cls()


# Global config instance
config = Config.from_env()
