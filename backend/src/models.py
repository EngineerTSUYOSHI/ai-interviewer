"""AI Interviewer のデータモデル定義。

企業・求人・候補者情報、面接官設定（1〜5名）、
進行フェーズ、会話履歴、心の声メモ、評価レポートのPydanticモデル。
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class InterviewPhase(str, Enum):
    """面接の進行フェーズ"""
    ORIENTATION = "ORIENTATION"                # Phase 1: 企業・求人の説明 (面接官代表)
    ORIENTATION_QA = "ORIENTATION_QA"          # Phase 2: 説明への質疑確認
    SELF_INTRODUCTION = "SELF_INTRODUCTION"    # Phase 3: 候補者の自己紹介
    INTERVIEW_QA = "INTERVIEW_QA"              # Phase 4: メイン質問・深掘り (1〜5名交代)
    REVERSE_QA = "REVERSE_QA"                  # Phase 5: 逆質問 (候補者から面接官へ)
    CLOSING = "CLOSING"                        # Phase 6: 終了の挨拶
    EVALUATION_MEETING = "EVALUATION_MEETING"  # ★ 裏の合否判定会議 (自律討議)
    COMPLETED = "COMPLETED"                    # 完了


class CompanyInfo(BaseModel):
    """志望企業情報"""
    name: str = Field(..., description="企業名")
    business_summary: str = Field(..., description="事業内容・ビジネスモデル")
    culture_values: str = Field(default="", description="企業カルチャー・求める人物像・バリュー")


class JobPosting(BaseModel):
    """募集求人情報"""
    title: str = Field(..., description="募集ポジション・職種名")
    description: str = Field(..., description="業務内容・募集背景")
    requirements: list[str] = Field(default_factory=list, description="必須要件・スキル")
    preferred_requirements: list[str] = Field(default_factory=list, description="歓迎要件")


class CandidateProfile(BaseModel):
    """応募者（ユーザー）プロフィール"""
    name: str = Field(..., description="候補者氏名")
    resume_summary: str = Field(..., description="経歴概要・スキル・主要実績")
    motivation: str = Field(default="", description="志望動機・今回の面接でアピールしたい点")


class Interviewer(BaseModel):
    """面接官設定（最低1名〜最大5名）"""
    id: str = Field(..., description="面接官識別ID (例: 'interviewer_1')")
    name: str = Field(..., description="面接官氏名 (例: '佐藤 健一')")
    role: str = Field(..., description="役割・役職 (例: 'テックリード', '人事採用責任者', 'CTO')")
    personality: Optional[str] = Field(
        default=None,
        description="人物特徴・性格・質問スタンス（オプショナル。空欄時は役割からAIがリアルなペルソナを自動補完）"
    )
    voice_preset: str = Field(
        default="male_low",
        description="音声合成プリセット (male_low, male_calm, female_calm, female_energetic)"
    )
    is_lead: bool = Field(
        default=False,
        description="代表面接官フラグ（Phase 1の説明やPhase 6のクロージングを担当）"
    )


class PersonaCompletion(BaseModel):
    """ペルソナ自動補完の出力スキーマ"""
    personality: str = Field(..., description="役割や企業文化から生成されたリアルな面接官の性格・関心事・質問スタンス")


class Utterance(BaseModel):
    """会話の発話ログ"""
    speaker_type: str = Field(..., description="'interviewer' | 'candidate' | 'system'")
    speaker_id: Optional[str] = Field(default=None, description="面接官ID (候補者の場合はNone)")
    speaker_name: str = Field(..., description="発話者氏名")
    phase: InterviewPhase = Field(..., description="発話時の面接フェーズ")
    content: str = Field(..., description="実際の発言内容")
    thought: Optional[str] = Field(default=None, description="面接官発言時に生成された心の声メモ（本音）")
    pass_to_id: Optional[str] = Field(default=None, description="発話後にパスした面接官ID")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="発話日時")


class InterviewerResponse(BaseModel):
    """Gemini が面接官ターンで生成する構造化出力"""
    thought: str = Field(
        ...,
        description="面接官のリアルタイムの本音・心の声メモ（好印象な点、違和感や懸念点、次に確認したい着眼点など）"
    )
    speech: str = Field(
        ...,
        description="候補者（または同席面接官）に向けた実際の発話・問いかけテキスト"
    )
    pass_to_interviewer_id: Optional[str] = Field(
        default=None,
        description="同席している別の面接官に質問や回答を振る場合の面接官ID（自分自身が続ける場合や指名しない場合はNone）"
    )
    ready_for_next_phase: bool = Field(
        default=False,
        description="現在のフェーズにおける確認・質問が十分に完了し、次のフェーズへ移行すべきと判断した場合はTrue"
    )


class MeetingUtterance(BaseModel):
    """裏の合否判定会議での面接官同士の発言"""
    interviewer_id: str = Field(..., description="発言した面接官ID")
    interviewer_name: str = Field(..., description="面接官氏名")
    role: str = Field(..., description="役職・役割")
    content: str = Field(..., description="討議での発言内容")


class EvaluationScore(BaseModel):
    """レーダーチャート用評価スコア"""
    category: str = Field(..., description="評価項目 (例: '技術力・設計思想', '論理的思考・説明力', 'カルチャーマッチ', '主体性・熱意')")
    score: int = Field(..., ge=1, le=10, description="1〜10点の評価スコア")
    reason: str = Field(..., description="採点理由・評価した根拠")


class ModelAnswer(BaseModel):
    """面接質問に対する満点模範解答"""
    question: str = Field(..., description="面接中に面接官から投げかけられた質問")
    candidate_answer: str = Field(..., description="候補者が実際に行った回答")
    critique: str = Field(..., description="候補者回答の弱点・不足していた視点・懸念された点")
    model_answer: str = Field(..., description="この企業・求人において合格を勝ち取るための100点満点の模範解答例")


class EvaluationReport(BaseModel):
    """裏の合否判定会議の総合レポート"""
    passed: bool = Field(..., description="最終合否判定 (True: 合格 / False: 見送り)")
    decision_type: str = Field(..., description="判定結果 ('合格' | '見送り' | '保留')")
    verdict_summary: str = Field(..., description="面接官全員による最終合否理由の総括コメント")
    meeting_transcript: list[MeetingUtterance] = Field(..., description="面接官同士のリアルな裏会議議事録（ディスカッション履歴）")
    scores: list[EvaluationScore] = Field(..., description="評価カテゴリ別スコア（レーダーチャート描画用）")
    model_answers: list[ModelAnswer] = Field(..., description="各主要質問に対する添削と100点満点模範解答")
