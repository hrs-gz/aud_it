from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUD_IT_")

    project_root: Path = Path(__file__).resolve().parent.parent
    storage_dir: Path = project_root / "storage"
    data_dir: Path = project_root / "data"
    database_url: str = f"sqlite:///{data_dir / 'aud_it.db'}"

    render_scale: float = 2.0
    ocr_word_threshold: int = 5
    frontend_dir: Path = project_root / "frontend"
    allow_hard_reset: bool = True


settings = Settings()

for directory in (
    settings.storage_dir / "originals",
    settings.storage_dir / "pages",
    settings.storage_dir / "exports",
    settings.storage_dir / "work",
    settings.data_dir,
):
    directory.mkdir(parents=True, exist_ok=True)
