import os

# Provide safe defaults before any app module imports get_settings()
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("BOT_TOKEN", "123456:TEST_TOKEN_FOR_PYTEST")
os.environ.setdefault("API_KEY", "test-api-key")
os.environ.setdefault("WEBHOOK_SECRET", "test-webhook-secret")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://domik:domik@localhost:5432/domik")
