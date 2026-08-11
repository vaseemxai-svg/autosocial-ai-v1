"""
Single place that reads .env. No other module should call os.environ directly —
import Config from here instead. This is what makes "centralize folder paths /
config in one file" true, and makes V2's multi-account support a matter of
extending this class, not hunting through the codebase.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # allow running without python-dotenv installed, e.g. in Docker where
    # env vars are injected directly by docker-compose


BASE_DIR = Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "yes")


@dataclass
class AccountConfig:
    username: str
    ig_account_id: str
    ig_access_token: str


@dataclass
class Config:
    mock_mode: bool = field(default_factory=lambda: _bool("MOCK_MODE", True))

    # Local folders (centralized here — nothing else hardcodes a path)
    local_output_dir: Path = field(default_factory=lambda: BASE_DIR / "output")
    local_memes_dir: Path = field(default_factory=lambda: BASE_DIR / "output" / "memes")
    local_logs_dir: Path = field(default_factory=lambda: BASE_DIR / "output" / "logs")

    # Drive
    drive_folder_id: str = field(default_factory=lambda: os.getenv("GOOGLE_DRIVE_FOLDER_ID", ""))
    drive_service_account_path: str = field(
        default_factory=lambda: os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_PATH", "")
    )

    # Scheduler
    generation_times: list[str] = field(
        default_factory=lambda: [
            t.strip() for t in os.getenv("GENERATION_TIMES", "09:00,19:00").split(",") if t.strip()
        ]
    )
    timezone: str = field(default_factory=lambda: os.getenv("TIMEZONE", "Asia/Kolkata"))

    # Web
    web_host: str = field(default_factory=lambda: os.getenv("WEB_HOST", "0.0.0.0"))
    web_port: int = field(default_factory=lambda: int(os.getenv("WEB_PORT", "8000")))
    # Shared-secret required by /post-now and /generate so the app is safe to
    # bind on 0.0.0.0 (needed for Docker port publishing) without letting
    # anyone on the same network trigger a real Instagram post. Empty in
    # mock mode by default (nothing real can happen anyway); REQUIRED and
    # enforced once MOCK_MODE=false — see require_live_credentials().
    post_now_token: str = field(default_factory=lambda: os.getenv("POST_NOW_TOKEN", ""))

    # V1 = single account. V2 will populate this list from a JSON/YAML block
    # instead of flat env vars — nothing outside config.py needs to know that
    # when it happens.
    active_account: AccountConfig = field(
        default_factory=lambda: AccountConfig(
            username=os.getenv("IG_USERNAME", "laggaye_broo"),
            ig_account_id=os.getenv("IG_ACCOUNT_ID", ""),
            ig_access_token=os.getenv("IG_ACCESS_TOKEN", ""),
        )
    )

    def __post_init__(self):
        self.local_output_dir.mkdir(parents=True, exist_ok=True)
        self.local_memes_dir.mkdir(parents=True, exist_ok=True)
        self.local_logs_dir.mkdir(parents=True, exist_ok=True)

    def require_live_credentials(self):
        """Call this before any real (non-mock) Graph API call. Fails loud and
        early instead of letting a half-configured account hit Instagram."""
        if self.mock_mode:
            return
        missing = [
            name
            for name, val in [
                ("IG_ACCOUNT_ID", self.active_account.ig_account_id),
                ("IG_ACCESS_TOKEN", self.active_account.ig_access_token),
                ("POST_NOW_TOKEN", self.post_now_token),
            ]
            if not val
        ]
        if missing:
            raise RuntimeError(
                f"MOCK_MODE is false but these are not set: {', '.join(missing)}. "
                "Set them in .env or switch MOCK_MODE=true. POST_NOW_TOKEN is "
                "mandatory once live — it's what stops anyone on the same "
                "network from triggering a real post via /post-now."
            )


config = Config()
