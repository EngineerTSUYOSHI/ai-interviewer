"""裏の合否判定ミーティング（自律討議 ＆ 満点模範解答生成）モジュール。

面接終了後、候補者が退室した後に面接官同士が自律的に選考ミーティングを行い、
議事録、合否判定、レーダーチャート採点、および各質問に対する満点模範解答を生成する。
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
    EvaluationScore,
    Interviewer,
    JobPosting,
    MeetingUtterance,
    ModelAnswer,
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
        """面接の全履歴と各面接官の本音メモから、自律的な選考会議を行い総合評価レポートを出力する"""

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
            f"- {i.name} (役割: {i.role}, ID: {i.id}, 性格/特徴: {i.personality})"
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

        prompt = f"""あなたはプロの採用担当役員および会議ファシリテーターです。
たった今、候補者「{candidate.name}」が退室し、面接室に残った面接官たちだけで
【裏の合否判定ミーティング（自律討議）】を開始します。

【参加する面接官たち】
{interviewers_info}

【志望企業 & 募集ポジション】
- 企業名: {company.name}
- 事業内容: {company.business_summary}
- カルチャー・理念: {company.culture_values}
- 募集職種: {job.title}
- 業務内容: {job.description}
- 求める要件: {", ".join(job.requirements)}

【候補者情報】
- 氏名: {candidate.name}
- 経歴: {candidate.resume_summary}

【面接本編の全会話ログ】
{full_transcript}

【面接中に各面接官が心の中で抱いていた本音メモ】
{all_thoughts}

【あなたに課されたタスク】
面接官たちがそれぞれの役割（技術、人事、経営など）の観点から、リアルで歯に衣着せぬ議論を交わす裏ミーティングをシミュレートし、以下の内容を含む総合評価レポート（JSON）を作成してください。

1. **meeting_transcript (自律討議の議事録)**:
   - 各面接官が順番に「私は〜〜と感じました」「いや、あの受け答えは要件を満たしていないのでは？」「一方でこの実績は買える」など、本音メモと面接ログに基づき活発に意見を戦わせるリアルな会話（最低4〜8往復以上の充実した発言）。
2. **passed & decision_type (合否判定)**:
   - passed (bool): 合格なら true, 見送りなら false
   - decision_type (str): "合格" / "見送り" / "保留"
3. **verdict_summary (最終総括)**:
   - 面接官全員が合意した最終的な合否理由と、候補者への率直なフィードバック総括。
4. **scores (レーダーチャート用評価スコア)**:
   - 以下の5項目それぞれについて、1〜10点のスコアと具体的な採点理由を記載:
     1. 「専門技術力・設計思想」
     2. 「論理的思考力・問題解決力」
     3. 「カルチャーフィット・行動特性」
     4. 「熱意・主体性・志望度」
     5. 「コミュニケーション力・伝達力」
5. **model_answers (満点模範解答集)**:
   - 本面接で候補者が受け答えした主要な質問（2〜4問程度）をピックアップ。
   - `question`: 面接官がした質問
   - `candidate_answer`: 候補者の実際の回答
   - `critique`: 面接官から見て何が足りなかったか、どの点が減点・懸念要因になったかの解説
   - `model_answer`: この企業・求人で100点満点の評価を勝ち取るための具体的で説得力のある模範改善解答例
"""

        response = self.client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=EvaluationReport,
                temperature=0.6,
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
            # 最低限のフォールバック
            return EvaluationReport(
                passed=False,
                decision_type="保留",
                verdict_summary="討議の結果、さらなる詳細な確認が必要と判断されました。",
                meeting_transcript=[],
                scores=[],
                model_answers=[],
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
        # 会話ログから質問と回答のペアを抽出
        candidate_utterances = [u for u in conversation_history if u.speaker_type == "candidate"]
        last_answer = candidate_utterances[-1].content if candidate_utterances else "特になし"

        # 自律討議ログ
        transcript = [
            MeetingUtterance(
                interviewer_id=interviewers[0].id,
                interviewer_name=interviewers[0].name,
                role=interviewers[0].role,
                content=(
                    f"お疲れ様でした。まずは技術面から振り返らせてください。"
                    f"田中さんはFinTechでの高負荷マイクロサービス移行経験があり、FastAPIや非同期処理の勘所は非常にしっかりしています。"
                    "ボトルネックの特定アプローチも論理的で、即戦力として開発をリードできる水準だと感じました。"
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
                        "人事の視点からも同感です。コミュニケーションが非常に落ち着いており、受け答えが簡潔で分かりやすいです。"
                        "他部署やチームメンバーとの合意形成のスタンスも協調性があり、"
                        f"弊社の『{company.culture_values.split('、')[0]}』というカルチャーにもよく馴染んでくれそうです。"
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
                        "CTOの渡辺です。事業成長のインパクトを意識して設計できている点が高評価ですね。"
                        "単に言われたものを作るのではなく、ユーザー価値やシステムのスケールを見据えて自発的に提案できるマインドを持っています。"
                        "私としては【合格（内定提案）】で強く推薦したいと考えます。"
                    ),
                )
            )
            transcript.append(
                MeetingUtterance(
                    interviewer_id=interviewers[0].id,
                    interviewer_name=interviewers[0].name,
                    role=interviewers[0].role,
                    content="異論ありません。チームのアーキテクチャ刷新を牽引する中核メンバーとしてぜひお迎えしましょう！",
                )
            )

        # 評価スコア
        scores = [
            EvaluationScore(
                category="専門技術力・設計思想",
                score=9,
                reason="高負荷APIのマイクロサービス化や分散トランザクション設計の知見が深く、実務で即戦力となる高い技術力を確認。",
            ),
            EvaluationScore(
                category="論理的思考力・問題解決力",
                score=8,
                reason="課題の要因特定から解決策の選定プロセスまで論理的で筋が通っており、説得力がある。",
            ),
            EvaluationScore(
                category="カルチャーフィット・行動特性",
                score=9,
                reason="謙虚さとオーナーシップを兼ね備えており、チームコラボレーションと透明性を重んじる社風にマッチ。",
            ),
            EvaluationScore(
                category="熱意・主体性・志望度",
                score=8,
                reason="弊社の事業モデルとAI技術基盤への関心が高く、明確な目的意識を持って選考に臨んでいる。",
            ),
            EvaluationScore(
                category="コミュニケーション力・伝達力",
                score=8,
                reason="質問の意図を正確に捉え、STAR形式で簡潔かつ具体的に要点を伝えることができている。",
            ),
        ]

        # 満点模範解答
        model_answers = [
            ModelAnswer(
                question="マイクロサービス移行における分散データ整合性の担保と、ボトルネック解消の具体的な設計について教えてください。",
                candidate_answer=last_answer,
                critique=(
                    "経験の概要は伝わったが、具体的に採用した分散トランザクションパターン（Sagaパターン、Outboxパターン等）"
                    "や、障害発生時の補償トランザクションの設計、スループット計測の具体数値まで踏み込むとさらに説得力が増します。"
                ),
                model_answer=(
                    "「前職のFinTech決済基盤では、DBへの書き込み負荷集中と強整合性の担保が最大の課題でした。"
                    "そこでTransactional OutboxパターンとKafkaを用いたイベント駆動アーキテクチャを採用し、"
                    "結果整合性と冪等性を担保しました。同時にRedisクラスタによる読み取りキャッシュと接続プーリングを最適化したことで、"
                    "ピーク時のレイテンシを65%削減し、スループット3倍（秒間15,000 req）を無停止で達成しました。」"
                ),
            ),
            ModelAnswer(
                question="チームで意見の対立が生じた際、どのように納得感のある合意形成を図られましたか？",
                candidate_answer="メンバーと話し合って、お互いの意見を聞いて調整しました。",
                critique=(
                    "調整したという結論だけでは『どのような基準で判断したのか』『対立をどう建設的な議論に昇華させたか』が不透明です。"
                    "客観的なデータやプロトタイプ検証を挟むプロセスを言語化すべきです。"
                ),
                model_answer=(
                    "「設計思想の対立が起きた際は、主観での議論を避け、判断軸を『ユーザーへの提供価値』と『運用保守コスト』に定義し直しました。"
                    "その上で双方のアーキテクチャの簡易PoCを2日間で作成し、ベンチマークと実装複雑性をチーム全員で可視化・比較しました。"
                    "客観的なデータに基づきメリット・デメリットを共有したことで、全員が納得して最適な方式を選択できました。」"
                ),
            ),
        ]

        return EvaluationReport(
            passed=True,
            decision_type="合格",
            verdict_summary=(
                f"{candidate.name}さんは、高いバックエンド設計力と実務での問題解決実績を兼ね備えており、"
                f"{company.name}が求めるシニアエンジニア像に合致しています。"
                "技術力・カルチャーフィットともに申し分なく、全員一致で【合格】と判定いたしました。"
            ),
            meeting_transcript=transcript,
            scores=scores,
            model_answers=model_answers,
        )

