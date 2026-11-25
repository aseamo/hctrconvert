"""
HctrConvert — Entry Point
───────────────────────
Run with: python run.py
Or with:  uvicorn app.main:app --reload --port 8001
"""
import uvicorn
from app.core.config import get_settings


def main():
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
    )


if __name__ == "__main__":
    main()
