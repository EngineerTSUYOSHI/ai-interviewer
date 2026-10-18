"""企業・求人票・職務経歴書のスマート取り込みモジュール。

URL（Gemini Search Grounding）、PDF、Word、画像、テキスト直接入力から
CompanyInfo, JobPosting, CandidateProfile を構造化抽出する。
"""

import io
from typing import Optional
from google import genai
from google.genai import types
from pydantic import BaseModel, Field
import pypdf
import docx

from config import get_genai_client, settings
from models import CandidateProfile, CompanyInfo, JobPosting


class ExtractedJobData(BaseModel):
    """求人・企業情報の抽出結果"""
    company: CompanyInfo
    job: JobPosting
    success: bool = True
    error_message: Optional[str] = None


class ExtractedCandidateData(BaseModel):
    """候補者プロフィールの抽出結果"""
    candidate: CandidateProfile
    success: bool = True
    error_message: Optional[str] = None


class SmartExtractor:
    """Gemini 2.5 Flash を活用したスマート情報抽出器"""

    def __init__(self, client: Optional[genai.Client] = None, mock: bool = False):
        self._client = client
        self.mock = mock

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            self._client = get_genai_client()
        return self._client

    # --- 求人情報の抽出 ---

    def extract_job_from_url(self, url: str) -> ExtractedJobData:
        """URL から求人情報・企業情報を抽出（Gemini Google Search Grounding を活用）"""
        if self.mock or not settings.get_effective_api_key():
            return self._mock_job_data(f"URL ({url}) から抽出したサンプル企業")

        prompt = f"""以下の求人ページまたは企業採用ページのURLを参照し、企業情報と募集要件を抽出してください。
URL: {url}

もしログインが必要なページ、非公開求人、ボットアクセス制限などでページの内容が参照できない場合は、
company.name を "ERROR_URL_UNREACHABLE" とし、事業内容に理由を記載してください。

【抽出項目】
1. 企業名、事業内容・ビジネスモデル、カルチャー・社風・求める人物像
2. 募集ポジション（職種）、業務内容、必須要件リスト、歓迎要件リスト
"""
        try:
            response = self.client.models.generate_content(
                model=settings.gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[{"google_search": {}}],
                    response_mime_type="application/json",
                    response_schema=ExtractedJobData,
                    temperature=0.2,
                ),
            )
            result = ExtractedJobData.model_validate_json(response.text)
            if result.company.name == "ERROR_URL_UNREACHABLE":
                return ExtractedJobData(
                    company=CompanyInfo(name="", business_summary=""),
                    job=JobPosting(title="", description=""),
                    success=False,
                    error_message=(
                        "このURLからは求人情報を直接取得できませんでした（要ログイン、アクセス制限、または非公開ページの可能性があります）。\n"
                        "求人票のテキストを貼り付けるか、ファイル（PDF/Word/画像）のアップロードをお試しください。"
                    ),
                )
            return result
        except Exception as e:
            return ExtractedJobData(
                company=CompanyInfo(name="", business_summary=""),
                job=JobPosting(title="", description=""),
                success=False,
                error_message=f"URLの解析中にエラーが発生しました: {str(e)}。テキスト直接入力またはファイルをご利用ください。",
            )

    def extract_job_from_text(self, text: str) -> ExtractedJobData:
        """テキスト（求人票・募集要項のコピペ等）から構造化抽出"""
        if self.mock or not settings.get_effective_api_key():
            return self._mock_job_data("テキストから抽出したサンプル企業")

        prompt = f"""以下の求人票・募集要項テキストから、企業情報および求人情報を抽出して構造化JSONで出力してください。

【求人票テキスト】
{text}
"""
        try:
            response = self.client.models.generate_content(
                model=settings.gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ExtractedJobData,
                    temperature=0.2,
                ),
            )
            return ExtractedJobData.model_validate_json(response.text)
        except Exception as e:
            return ExtractedJobData(
                company=CompanyInfo(name="企業名未設定", business_summary=text[:100]),
                job=JobPosting(title="職種未設定", description=text[:200]),
                success=False,
                error_message=f"テキスト解析中にエラーが発生しました: {str(e)}",
            )

    def extract_job_from_file(self, file_bytes: bytes, filename: str, mime_type: str) -> ExtractedJobData:
        """ファイル（PDF, Word, 画像）から求人情報を抽出"""
        lower = filename.lower()
        if "pdf" in lower or mime_type == "application/pdf":
            extracted_text = self._parse_pdf(file_bytes)
            return self.extract_job_from_text(extracted_text)
        elif "docx" in lower or "doc" in lower:
            extracted_text = self._parse_docx(file_bytes)
            return self.extract_job_from_text(extracted_text)
        elif any(ext in lower for ext in [".png", ".jpg", ".jpeg", ".webp"]) or "image" in mime_type:
            return self._extract_job_from_image(file_bytes, mime_type)
        else:
            try:
                text = file_bytes.decode("utf-8")
                return self.extract_job_from_text(text)
            except Exception:
                return ExtractedJobData(
                    company=CompanyInfo(name="", business_summary=""),
                    job=JobPosting(title="", description=""),
                    success=False,
                    error_message=f"対応していないファイル形式です: {filename}",
                )

    def _extract_job_from_image(self, image_bytes: bytes, mime_type: str) -> ExtractedJobData:
        """画像（求人票スクリーンショット等）からマルチモーダルで抽出"""
        if self.mock or not settings.get_effective_api_key():
            return self._mock_job_data("スクリーンショットから抽出したサンプル企業")

        image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type or "image/png")
        prompt = """この画像は求人票または採用ページのスクリーンショットです。
画像内のテキストや表を読み取り、企業情報と求人要件を正確に抽出して構造化JSONで出力してください。"""

        try:
            response = self.client.models.generate_content(
                model=settings.gemini_model,
                contents=[image_part, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ExtractedJobData,
                    temperature=0.2,
                ),
            )
            return ExtractedJobData.model_validate_json(response.text)
        except Exception as e:
            return ExtractedJobData(
                company=CompanyInfo(name="", business_summary=""),
                job=JobPosting(title="", description=""),
                success=False,
                error_message=f"画像の解析に失敗しました: {str(e)}",
            )

    # --- 候補者（職務経歴書・履歴書）の抽出 ---

    def extract_candidate_from_text(self, text: str) -> ExtractedCandidateData:
        """職務経歴書・履歴書テキストから構造化抽出"""
        if self.mock or not settings.get_effective_api_key():
            return self._mock_candidate_data("田中 雄大")

        prompt = f"""以下の職務経歴書・履歴書テキストから、候補者の氏名、経歴概要・実績サマリー、志望動機・アピールポイントを抽出して構造化JSONで出力してください。

【経歴書テキスト】
{text}
"""
        try:
            response = self.client.models.generate_content(
                model=settings.gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ExtractedCandidateData,
                    temperature=0.2,
                ),
            )
            return ExtractedCandidateData.model_validate_json(response.text)
        except Exception as e:
            return ExtractedCandidateData(
                candidate=CandidateProfile(name="候補者", resume_summary=text[:200]),
                success=False,
                error_message=f"経歴書の解析中にエラーが発生しました: {str(e)}",
            )

    def extract_candidate_from_file(self, file_bytes: bytes, filename: str, mime_type: str) -> ExtractedCandidateData:
        """ファイル（PDF, Word, 画像）から候補者経歴を抽出"""
        lower = filename.lower()
        if "pdf" in lower or mime_type == "application/pdf":
            extracted_text = self._parse_pdf(file_bytes)
            return self.extract_candidate_from_text(extracted_text)
        elif "docx" in lower or "doc" in lower:
            extracted_text = self._parse_docx(file_bytes)
            return self.extract_candidate_from_text(extracted_text)
        elif any(ext in lower for ext in [".png", ".jpg", ".jpeg", ".webp"]) or "image" in mime_type:
            return self._extract_candidate_from_image(file_bytes, mime_type)
        else:
            try:
                text = file_bytes.decode("utf-8")
                return self.extract_candidate_from_text(text)
            except Exception:
                return ExtractedCandidateData(
                    candidate=CandidateProfile(name="候補者", resume_summary=""),
                    success=False,
                    error_message=f"対応していないファイル形式です: {filename}",
                )

    def _extract_candidate_from_image(self, image_bytes: bytes, mime_type: str) -> ExtractedCandidateData:
        """職務経歴書の画像からマルチモーダル抽出"""
        if self.mock or not settings.get_effective_api_key():
            return self._mock_candidate_data("佐藤 拓也")

        image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type or "image/png")
        prompt = """この画像は職務経歴書または履歴書です。
画像内の氏名、これまでの経歴やスキル、主要な実績、アピールポイントを読み取り構造化JSONで出力してください。"""

        try:
            response = self.client.models.generate_content(
                model=settings.gemini_model,
                contents=[image_part, prompt],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=ExtractedCandidateData,
                    temperature=0.2,
                ),
            )
            return ExtractedCandidateData.model_validate_json(response.text)
        except Exception as e:
            return ExtractedCandidateData(
                candidate=CandidateProfile(name="候補者", resume_summary=""),
                success=False,
                error_message=f"経歴書画像の解析に失敗しました: {str(e)}",
            )

    # --- ヘルパーメソッド ---

    def _parse_pdf(self, file_bytes: bytes) -> str:
        """PDF からテキストを抽出"""
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        texts = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                texts.append(t)
        return "\n".join(texts)

    def _parse_docx(self, file_bytes: bytes) -> str:
        """Word docx からテキストを抽出"""
        doc = docx.Document(io.BytesIO(file_bytes))
        return "\n".join([p.text for p in doc.paragraphs if p.text])

    def _mock_job_data(self, name_prefix: str) -> ExtractedJobData:
        """モック用の求人データ"""
        return ExtractedJobData(
            company=CompanyInfo(
                name=f"{name_prefix} (AIイノベーションズ)",
                business_summary="生成AIを活用したエンタープライズ向け自律型エージェント基盤の開発・提供。",
                culture_values="徹底したオーナーシップ、プロフェッショナリズム、心理的安全性と率直な議論。",
            ),
            job=JobPosting(
                title="シニアバックエンド / AIエンジニア",
                description="LLM推論API基盤の設計・実装およびリアルタイム通信ストリーミングサーバーの高速化。",
                requirements=[
                    "Python / FastAPI によるバックエンドAPIの設計・開発実務経験3年以上",
                    "RDBMS / NoSQL を用いたデータモデリングおよびパフォーマンスチューニング",
                    "マイクロサービスや分散システムのアーキテクチャ設計・運用経験",
                ],
                preferred_requirements=[
                    "Gemini API / LLM を用いたプロダクション開発経験",
                    "WebSocket や WebRTC を用いたリアルタイム双方向通信の開発経験",
                ],
            ),
            success=True,
        )

    def _mock_candidate_data(self, name: str) -> ExtractedCandidateData:
        """モック用の候補者データ"""
        return ExtractedCandidateData(
            candidate=CandidateProfile(
                name=name,
                resume_summary=(
                    "Webバックエンドエンジニアとして5年間の実務経験。直近はFinTech企業にてFastAPIを用いた決済連携基盤を"
                    "マイクロサービス化し、ピーク時スループットを3倍に改善。DBクエリ最適化や分散トランザクションの知見を有する。"
                ),
                motivation=(
                    "貴社が推進するAIエージェント基盤の社会実装に強く共感しており、これまでの高負荷バックエンド設計の知見を活かして、"
                    "スケーラブルで堅牢なAI通信基盤を創り上げたいと考えています。"
                ),
            ),
            success=True,
        )
