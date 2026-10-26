"""裏の合否判定ミーティング（自律討議 ＆ 厳格採点フィードバック）モジュール。

面接終了後、候補者が退室した後に面接官同士が自律的に選考ミーティングを行い、
議事録、厳格な合否判定、および良かった点・悪かった点の率直な箇条書きを出力する。
"""

import json
from typing import Optional
from google import genai
from google.genai import types

from config import get_genai_client, settings
from models import (
    CandidateProfile,
    CompanyInfo,
    EvaluationReport,
    Interviewer,
    JobPosting,
    MeetingUtterance,
    Utterance,
)


class EvaluationMeeting:
    """面接終了後の裏合否判定会議エンジン"""

    def __init__(self, client: Optional[genai.Client] = None, mock: bool = False):
        self._client = client
        self.mock = mock

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            self._client = get_genai_client()
        return self._client

    def conduct_meeting(
        self,
        company: CompanyInfo,
        job: JobPosting,
        candidate: CandidateProfile,
        interviewers: list[Interviewer],
        conversation_history: list[Utterance],
        interviewer_thoughts: dict[str, list[str]],
    ) -> EvaluationReport:
        """面接の全履歴と各面接官の本音メモから、厳格な選考会議を行い総合評価レポートを出力する"""

        if self.mock or not settings.get_effective_api_key():
            return self._generate_mock_report(
                company=company,
                job=job,
                candidate=candidate,
                interviewers=interviewers,
                conversation_history=conversation_history,
            )

        # 面接官情報のまとめ
        interviewers_info = "\n".join([
            f"- {i.name} (役割: {i.role}, ID: {i.id}, 性別: {i.gender}, 特徴: {i.personality})"
            for i in interviewers
        ])

        # 会話ログ（候補者と面接官の全対話）
        transcript_lines = []
        for u in conversation_history:
            transcript_lines.append(f"[{u.speaker_name} ({u.speaker_type})]: {u.content}")
        full_transcript = "\n".join(transcript_lines)

        # 面接中に蓄積された各面接官の心の声メモ
        thoughts_sections = []
        for interviewer in interviewers:
            notes = interviewer_thoughts.get(interviewer.id, [])
            notes_str = "\n".join([f"  * {n}" for n in notes]) if notes else "  (特になし)"
            thoughts_sections.append(f"【{interviewer.name} ({interviewer.role}) の本音メモ】:\n{notes_str}")
        all_thoughts = "\n".join(thoughts_sections)

        prompt = f"""あなたはプロの厳格な採用判定ファシリテーターです。
たった今、候補者「{candidate.name}」が面接室を退室し、残った面接官たちだけで
【裏の合否判定ミーティング（自律討議）】を開始します。

【参加する面接官たち】
{interviewers_info}

【志望企業 & 募集ポジション】
- 企業名: {company.name}
- 事業内容: {company.business_summary}
- カルチャー・理念: {company.culture_values}
- 募集職種: {job.title}
- 業務内容: {job.description}
- 必須要件: {", ".join(job.requirements)}

【応募者（候補者）情報】
- 氏名: {candidate.name}
- 経歴: {candidate.resume_summary}

【面接本編の全会話ログ】
{full_transcript}

【面接中に各面接官が心の中で抱いていた本音メモ】
{all_thoughts}

【最重要判定指針（AI特有の甘い評価を徹底排除）】
1. **お世辞や忖度は一切禁止**: 候補者への過度な褒め言葉や、当たり障りのないお世辞は不要です。
2. **要求基準に満たなければ容赦なく「見送り」または「保留」**:
   - 必須要件に届いていない点、回答が表面的で具体性に欠けた点、カルチャーマッチへの懸念があれば、妥協せず「見送り」と判断してください。
   - 甘い評価は面接対策としての価値を損ないます。本番で落とされるポイントを厳しく突いてください。
3. **良い点・悪い点は端的な箇条書きで**:
   - ダラダラした長文ではなく、何が評価され、何が不合格要因になり得るかを箇条書き3〜5点で明確に言語化してください。

【出力要件 (JSON)】
1. `passed` (bool): 合格なら true, 見送りなら false
2. `decision_type` (str): "合格" / "見送り" / "保留"
3. `verdict_summary` (str): 合否判定理由の総括サマリー
4. `good_points` (list[str]): 面接で評価された点・良かった点（箇条書き3〜5点）
5. `improvement_points` (list[str]): 懸念された点・悪かった点・改善すべき点（箇条書き3〜5点）
6. `meeting_transcript` (list[MeetingUtterance]): 面接官同士のリアルな本音の討議ログ
"""

        response = self.client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=EvaluationReport,
                temperature=0.4,
            ),
        )

        try:
            return EvaluationReport.model_validate_json(response.text)
        except Exception:
            text = response.text or ""
            if "{" in text and "}" in text:
                try:
                    start = text.index("{")
                    end = text.rindex("}") + 1
                    json_data = json.loads(text[start:end])
                    return EvaluationReport.model_validate(json_data)
                except Exception:
                    pass
            return EvaluationReport(
                passed=False,
                decision_type="保留",
                verdict_summary="討議の結果、さらなる詳細な確認が必要と判断されました。",
                good_points=["落ち着いた対話姿勢"],
                improvement_points=["質問に対する具体的なエピソード・技術選定の根拠が不足している"],
                meeting_transcript=[],
            )

    def _generate_mock_report(
        self,
        company: CompanyInfo,
        job: JobPosting,
        candidate: CandidateProfile,
        interviewers: list[Interviewer],
        conversation_history: list[Utterance],
    ) -> EvaluationReport:
        """テスト・オフライン検証用のリアルな合否判定レポート生成"""
        # 自律討議ログ
        transcript = [
            MeetingUtterance(
                interviewer_id=interviewers[0].id,
                interviewer_name=interviewers[0].name,
                role=interviewers[0].role,
                content=(
                    f"お疲れ様でした。まずは技術面から率直に申し上げます。"
                    f"田中さんはFinTechでのマイクロサービス移行やFastAPIの知見はあり、基礎力は確かです。"
                    "ただ、ボトルネック特定や分散整合性について、具体的なアーキテクチャ名や数値での説明がやや曖昧でした。"
                ),
            ),
        ]

        if len(interviewers) > 1:
            transcript.append(
                MeetingUtterance(
                    interviewer_id=interviewers[1].id,
                    interviewer_name=interviewers[1].name,
                    role=interviewers[1].role,
                    content=(
                        "人事からも同意見です。受け答えは誠実で好印象ですが、"
                        "チームでの合意形成や対立時のアプローチについて、抽象的な回答に留まっていたのが気になりました。"
                        f"弊社の『{company.culture_values.split('、')[0]}』を満たすには、もう一段のリーダーシップの発揮事例が欲しいところです。"
                    ),
                )
            )

        if len(interviewers) > 2:
            transcript.append(
                MeetingUtterance(
                    interviewer_id=interviewers[2].id,
                    interviewer_name=interviewers[2].name,
                    role=interviewers[2].role,
                    content=(
                        "CTOの渡辺です。事業成長に対する意識は感じられますが、シニア枠としてはやや受け身な印象も残りました。"
                        "とはいえ、ポテンシャルと基本設計力は高いため、今回の判定は【保留（次回課題付き面接）】、"
                        "または実技課題での見極めを提案したいと考えます。"
                    ),
                )
            )
            transcript.append(
                MeetingUtterance(
                    interviewer_id=interviewers[0].id,
                    interviewer_name=interviewers[0].name,
                    role=interviewers[0].role,
                    content="了解しました。では、設計課題の追加提出を条件とした【保留】で合意しましょう。",
                )
            )

        return EvaluationReport(
            passed=False,
            decision_type="保留",
            verdict_summary=(
                f"{candidate.name}さんは、バックエンドの基本スキルと開発経験は有しているものの、"
                "シニアエンジニアとして求められる『分散設計の深い根拠』や『周囲を巻き込むリーダーシップ』の具体性がやや不足していました。"
                "技術的なポテンシャルは認められるため、今回は即内定ではなく【保留（追加課題・次回確認）】と判定いたします。"
            ),
            good_points=[
                "FinTech決済基盤におけるFastAPIやマイクロサービス移行の実務経験を有している点",
                "質問に対して冷静かつ誠実に受け答えができるコミュニケーションの安定感",
                "生成AIを活用した自社SaaSの事業理念に対する高い関心と志望意欲",
            ],
            improvement_points=[
                "技術選定の根拠や分散トランザクション（Saga/Outbox等）の具体的な設計パターンの言語化が不十分",
                "チーム内の意見対立を解消したプロセスの説明が抽象的で、主導的な行動特性が見えにくかった点",
                "シニア枠として、自身がボトルネックを主導して解決した定量的な実績（レイテンシ削減率、スループット向上数値）の提示不足",
            ],
            meeting_transcript=transcript,
        )
