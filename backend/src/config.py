"""設定管理および Gemini API クライアント初期化モジュール。"""

import os
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from pydantic_settings import BaseSettings, SettingsConfigDict

# ルートおよびbackendの .env を探索して読み込む
env_paths = [
    Path(__file__).resolve().parent.parent / ".env",          # backend/.env
    Path(__file__).resolve().parent.parent.parent / ".env",   # プロジェクトルート/.env
]
for env_path in env_paths:
    if env_path.exists():
        load_dotenv(env_path)


class Settings(BaseSettings):
    """アプリケーション設定"""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # API キー（GEMINI_API_KEY または GOOGLE_API_KEY から取得）
    gemini_api_key: str = ""
    # デフォルトのGeminiモデル
    gemini_model: str = "gemini-2.5-flash"

    def get_effective_api_key(self) -> str:
        """有効なAPIキーを解決して取得"""
        if self.gemini_api_key:
            return self.gemini_api_key
        # 環境変数のフォールバック
        return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""


settings = Settings()


def get_genai_client() -> genai.Client:
    """Gemini API クライアントを取得。

    APIキーが設定されていない場合はわかりやすい例外を送出する。
    """
    api_key = settings.get_effective_api_key()
    if not api_key:
        raise ValueError(
            "Gemini APIキーが設定されていません。\n"
            "環境変数 GEMINI_API_KEY または backend/.env に GEMINI_API_KEY=your_key を設定してください。"
        )
    return genai.Client(api_key=api_key)
