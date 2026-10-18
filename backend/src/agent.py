"""面接官AIエージェントモジュール。

面接官のペルソナ自動補完、心の声（本音メモ）と発言の同時生成、
面接官同士のパス・掛け合いを制御する。
"""

import json
from typing import Optional
from google import genai
from google.genai import types

from config import get_genai_client, settings
from models import (
    CandidateProfile,
    CompanyInfo,
    Interviewer,
    InterviewerResponse,
    InterviewPhase,
    JobPosting,
    PersonaCompletion,
    Utterance,
)


class InterviewerAgent:
    """個別の面接官AIエージェント"""

    def __init__(self, interviewer: Interviewer, client: Optional[genai.Client] = None, mock: bool = False):
        self.interviewer = interviewer
        self._client = client
        self.mock = mock

    @property
    def client(self) -> genai.Client:
        if self._client is None:
            self._client = get_genai_client()
        return self._client

    def ensure_persona_completed(self, company: CompanyInfo, job: JobPosting) -> None:
        """オプショナルな性格・人物特徴が未設定の場合、企業や役割からAIがリアルなペルソナを自動補完する"""
        if self.interviewer.personality and self.interviewer.personality.strip():
            return

        # モックまたはAPIキー未設定時のリアルなフォールバック
        if self.mock or not settings.get_effective_api_key():
            role_lower = self.interviewer.role.lower()
            if "テック" in role_lower or "アーキ" in role_lower or "技術" in role_lower or "エンジニア" in role_lower:
                self.interviewer.personality = (
                    "論理的かつ技術的好奇心が旺盛。アーキテクチャ設計思想やボトルネック解消の泥臭い工夫を重視し、"
                    "表面的なスキルではなく『なぜその技術を選定したか』の根拠を鋭く深掘りする。"
                )
            elif "人事" in role_lower or "hr" in role_lower or "採用" in role_lower:
                self.interviewer.personality = (
                    "温厚で傾聴力が高く、候補者が本音を話しやすい雰囲気を作る。"
                    "チームへのカルチャーフィットや困難を乗り越えた行動特性、企業理念への共感度を丁寧に見極める。"
                )
            elif "cto" in role_lower or "役員" in role_lower or "経営" in role_lower:
                self.interviewer.personality = (
                    "大局的なビジネス視点と技術経営の視座を併せ持つ。事業成長に対する技術的貢献度や、"
                    "組織を牽引するリーダーシップ、中長期的なビジョンの一致度を洞察する。"
                )
            else:
                self.interviewer.personality = f"{self.interviewer.role}として、専門的な視点から冷静かつ的確に候補者の適性を見極める。"
            return

        prompt = f"""あなたはプロの採用設計コンサルタントです。
以下の企業・求人において、面接官「{self.interviewer.name}」（役割: {self.interviewer.role}）の
リアルで深みのあるペルソナ（性格、面接時の着眼点、口調や質問スタイル）を生成してください。

【志望企業】
- 企業名: {company.name}
- 事業内容: {company.business_summary}
- カルチャー: {company.culture_values}

【求人情報】
- 職種: {job.title}
- 業務内容: {job.description}

【面接官の基本情報】
- 氏名: {self.interviewer.name}
- 役割: {self.interviewer.role}

【出力要件】
この役割にふさわしい、具体的でリアリティのある人物特徴（例: 論理的で設計思想を重視する、カルチャーフィットや誠実さを丁寧に見極める、等）を日本語で端的にまとめてください。
"""
        response = self.client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=PersonaCompletion,
                temperature=0.7,
            ),
        )
        try:
            completed = PersonaCompletion.model_validate_json(response.text)
            self.interviewer.personality = completed.personality
        except Exception:
            self.interviewer.personality = f"{self.interviewer.role}として、専門的な視点から冷静かつ的確に候補者の適性を見極める。"

    def respond(
        self,
        phase: InterviewPhase,
        company: CompanyInfo,
        job: JobPosting,
        candidate: CandidateProfile,
        other_interviewers: list[Interviewer],
        conversation_history: list[Utterance],
        my_past_thoughts: list[str],
        instruction: Optional[str] = None,
    ) -> InterviewerResponse:
        """現在のフェーズと会話文脈に基づき、心の声と実際の発言を生成する"""

        # モックまたはAPIキー未設定時の応答
        if self.mock or not settings.get_effective_api_key():
            return self._generate_mock_response(
                phase=phase,
                company=company,
                job=job,
                candidate=candidate,
                other_interviewers=other_interviewers,
                conversation_history=conversation_history,
            )

        # 同席面接官のリスト文字列
        colleagues_desc = "\n".join([
            f"- {other.name} (役割: {other.role}, ID: {other.id})"
            for other in other_interviewers if other.id != self.interviewer.id
        ])
        if not colleagues_desc:
            colleagues_desc = "（同席面接官なし。1対1の面接です）"

        # 過去の会話ログのフォーマット
        recent_logs = []
        for u in conversation_history[-10:]:  # 直近10発話
            speaker_tag = f"[{u.speaker_name} ({u.speaker_type})]"
            recent_logs.append(f"{speaker_tag}: {u.content}")
        logs_str = "\n".join(recent_logs) if recent_logs else "（まだ会話はありません）"

        # 過去の自身の心の声
        thoughts_str = "\n".join([f"- {t}" for t in my_past_thoughts[-5:]]) if my_past_thoughts else "（まだメモはありません）"

        # フェーズごとのガイダンス
        phase_instructions = self._get_phase_guidance(phase, instruction)

        system_instruction = f"""あなたは企業の面接官「{self.interviewer.name}」です。
現在、採用面接がリアルタイムに進行しています。

【あなたのプロフィール】
- 氏名: {self.interviewer.name}
- 役職・役割: {self.interviewer.role}
- 性格・人物特徴・スタンス: {self.interviewer.personality or '専門的な観点から的確に見極める'}
- 代表面接官か: {'はい' if self.interviewer.is_lead else 'いいえ'}

【同席している他の面接官】
{colleagues_desc}

【志望企業・募集求人】
- 企業名: {company.name}
- 事業内容: {company.business_summary}
- カルチャー: {company.culture_values}
- 募集ポジション: {job.title}
- 業務内容: {job.description}
- 求める要件: {", ".join(job.requirements)}

【応募者（候補者）】
- 氏名: {candidate.name}
- 経歴概要: {candidate.resume_summary}
- 志望動機・アピール: {candidate.motivation}

【あなたの過去の「心の声メモ」（本音）】
{thoughts_str}

【直近の会話ログ】
{logs_str}

【現在の面接フェーズ】: {phase.value}
{phase_instructions}

【重要な行動規範】
1. **心の声（thought）の本音出力**: 候補者の受け答えに対する率直な好感、疑念、専門的視点でのチェックメモを必ず含めてください。
2. **リアリティのある発話（speech）**: 機械的な定型句ではなく、候補者の発言内容をしっかり受け止めた上で、あなたらしい口調・視点で発言してください。
3. **同席面接官へのパス（pass_to_interviewer_id）**:
   - 複数人で面接を行っている場合、自分の質問が一区切りついたら「技術面は以上です。人事の〇〇さん、何かありますか？」のように自然にパスを出してください（同席面接官のIDを指定）。
   - まだ自分が深掘りを続けたい場合や1名面接の場合は null にしてください。
4. **フェーズ完了フラグ（ready_for_next_phase）**:
   - 現フェーズでの目的（自己紹介受付、説明の質疑、逆質問への回答など）が十分に完了したと判断した場合、true にしてください。
"""

        prompt = f"""上記の文脈を踏まえ、面接官「{self.interviewer.name}」としての次の【心の声】と【発話内容】を出力してください。
追加指示: {instruction or '状況に応じて適切に対話を進めてください。'}"""

        response = self.client.models.generate_content(
            model=settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=InterviewerResponse,
                temperature=0.7,
            ),
        )

        try:
            return InterviewerResponse.model_validate_json(response.text)
        except Exception:
            # 万が一パースエラー時の救済処理
            text = response.text or ""
            # JSONブロックの抽出を試みる
            if "{" in text and "}" in text:
                try:
                    start = text.index("{")
                    end = text.rindex("}") + 1
                    json_data = json.loads(text[start:end])
                    return InterviewerResponse.model_validate(json_data)
                except Exception:
                    pass
            return InterviewerResponse(
                thought="候補者の発言内容を確認し、次の観点を検討している。",
                speech=f"なるほど、ありがとうございます。{candidate.name}さんのお考えがよくわかりました。",
                pass_to_interviewer_id=None,
                ready_for_next_phase=False,
            )

    def _get_phase_guidance(self, phase: InterviewPhase, instruction: Optional[str]) -> str:
        """各進行フェーズに応じた詳細プロンプト指示"""
        if phase == InterviewPhase.ORIENTATION:
            return """- 【Phase 1: 企業・求人の説明】
- 代表面接官として、候補者に本日の面接のお礼を述べ、企業概要および本ポジション（求人内容）の募集背景を分かりやすく説明してください。
- 威圧感を与えず、候補者の緊張を和らげるように配慮してください。
- 説明が終わったら ready_for_next_phase を true にしてください。"""

        elif phase == InterviewPhase.ORIENTATION_QA:
            return """- 【Phase 2: 説明への質疑確認】
- 代表面接官として、「ここまでで何かご質問や確認されたい点はございますか？」と候補者に確認してください。
- 候補者から質問があれば丁寧に回答し、質問がなければ「では選考に入らせていただきます」と進めてください。"""

        elif phase == InterviewPhase.SELF_INTRODUCTION:
            return """- 【Phase 3: 候補者の自己紹介】
- 「では、まず初めに〇〇さんの自己紹介と、これまでのご経歴を簡単にお話しいただけますでしょうか」と促してください。
- 候補者の自己紹介を聞き終えたら、簡単なお礼と受け止めを述べ、ready_for_next_phase を true にしてください。"""

        elif phase == InterviewPhase.INTERVIEW_QA:
            return f"""- 【Phase 4: メイン質問・深掘り】
- あなたの役割（{self.interviewer.role}）に基づき、候補者のスキル・実績・思考プロセス・企業へのマッチ度を深掘り質問してください。
- 直前の候補者の回答を踏まえ、具体例（STARメソッド: 状況・課題・行動・成果）を引き出す鋭い問いかけを行ってください。
- 自分の質問が一段落したら、他の面接官へ自然にパスを回すか、さらに深く突っ込むか判断してください。"""

        elif phase == InterviewPhase.REVERSE_QA:
            return """- 【Phase 5: 逆質問フェーズ】
- 候補者からの質問を受けるフェーズです。
- 「面接官からの質問は以上となります。〇〇さんから、弊社や業務に関して何かご質問はございますでしょうか？」と案内してください。
- 候補者から質問が来たら、誠実かつ社内の実情が伝わるように回答してください。
- 候補者が「特にありません」「以上です」と述べた場合、ready_for_next_phase を true にしてください。"""

        elif phase == InterviewPhase.CLOSING:
            return """- 【Phase 6: 終了の挨拶】
- 本日の面接に対する感謝を伝え、今後の選考結果のご連絡（例: 1週間以内にメールにてご連絡等）について伝えて面接を終了してください。
- 締めくくりとして ready_for_next_phase を true にしてください。"""

        return ""

    def _generate_mock_response(
        self,
        phase: InterviewPhase,
        company: CompanyInfo,
        job: JobPosting,
        candidate: CandidateProfile,
        other_interviewers: list[Interviewer],
        conversation_history: list[Utterance],
    ) -> InterviewerResponse:
        """テスト・オフライン検証用のリアルなモックレスポンス生成"""
        colleagues = [i for i in other_interviewers if i.id != self.interviewer.id]
        next_colleague_id = colleagues[0].id if colleagues else None
        next_colleague_name = colleagues[0].name if colleagues else ""

        last_utterance = conversation_history[-1].content if conversation_history else ""

        if phase == InterviewPhase.ORIENTATION:
            return InterviewerResponse(
                thought="第一印象は落ち着いていて礼儀正しい。まずは緊張をほぐしつつ、募集の背景をクリアに伝えよう。",
                speech=(
                    f"本日はお忙しい中、{company.name}の{job.title}ポジションの面接にお越しいただきありがとうございます。"
                    f"私、本日の代表面接を務めます{self.interviewer.name}（{self.interviewer.role}）と申します。"
                    f"弊社では現在、{company.business_summary}を推進しており、その中核となる技術基盤を強化できる方を求めています。"
                    "本日はリラックスして、普段の取り組みについてお話しいただければ幸いです。"
                ),
                pass_to_interviewer_id=None,
                ready_for_next_phase=True,
            )

        elif phase == InterviewPhase.ORIENTATION_QA:
            return InterviewerResponse(
                thought="こちらの説明に対して能動的な疑問や関心を持っているか確認する。",
                speech=(
                    f"ここまでの会社概要や募集ポジションについて、{candidate.name}さんの方で何か確認されたい点やご質問はございますか？"
                ),
                pass_to_interviewer_id=None,
                ready_for_next_phase=False,
            )

        elif phase == InterviewPhase.SELF_INTRODUCTION:
            return InterviewerResponse(
                thought="事前のレジュメにある実績をどのように構造化して話せるか、プレゼンテーション能力をチェックしよう。",
                speech=(
                    f"ありがとうございます。それでは、まず初めに{candidate.name}さんの自己紹介と、"
                    "これまでのエンジニアとしてのご経歴や得意領域についてお話しいただけますでしょうか？"
                ),
                pass_to_interviewer_id=None,
                ready_for_next_phase=False,
            )

        elif phase == InterviewPhase.INTERVIEW_QA:
            role_lower = self.interviewer.role.lower()
            if "テック" in role_lower or "技術" in role_lower or "アーキ" in role_lower:
                return InterviewerResponse(
                    thought=(
                        f"候補者の回答「{last_utterance[:30]}...」を確認。マイクロサービス化の実績は素晴らしいが、"
                        "トランザクションの整合性や障害時のフォールバック設計をどこまで自ら主導したか深掘りしたい。"
                    ),
                    speech=(
                        f"経歴のご説明ありがとうございます。先ほどお話しいただいた中で、"
                        "FinTech基盤におけるマイクロサービス化とスループット3倍改善という実績に大変興味を持ちました。"
                        "この移行にあたり、分散環境でのデータ整合性の担保や、最も苦労された技術的なボトルネックと"
                        "それをどう設計で解決されたのか、具体的に教えていただけますでしょうか？"
                    ),
                    pass_to_interviewer_id=next_colleague_id,
                    ready_for_next_phase=False,
                )
            elif "人事" in role_lower or "hr" in role_lower:
                return InterviewerResponse(
                    thought=(
                        "技術力は申し分なさそう。チーム内での合意形成や、予期せぬ意見の対立が起きた際のスタンスを確認したい。"
                    ),
                    speech=(
                        f"ありがとうございます。私、人事の{self.interviewer.name}からも1点お伺いさせてください。"
                        "チームで大規模な設計変更を進める際、他のメンバーとの意見の相違や優先順位の対立が生じることもあったかと思います。"
                        f"{candidate.name}さんは周囲を巻き込み、どのように納得感のある合意形成を図られましたか？"
                    ),
                    pass_to_interviewer_id=next_colleague_id,
                    ready_for_next_phase=False,
                )
            else:
                return InterviewerResponse(
                    thought="事業インパクトを意識して設計できているか、経営視点で質問を投げる。",
                    speech=(
                        f"{self.interviewer.role}の{self.interviewer.name}です。"
                        f"弊社は『{company.culture_values}』を掲げています。技術的な卓越性だけでなく、"
                        "それがエンドユーザーや事業のグロースにどう直結したか、田中さんが最も手応えを感じたエピソードを教えてください。"
                    ),
                    pass_to_interviewer_id=None,
                    ready_for_next_phase=True,
                )

        elif phase == InterviewPhase.REVERSE_QA:
            return InterviewerResponse(
                thought="意欲的な逆質問を期待したい。会社の課題やビジョンに対する解像度を見極める。",
                speech=(
                    f"ありがとうございます。私ども面接官からの質問は以上となります。"
                    f"最後に、{candidate.name}さんから弊社や開発チームの体制について、何か聞いておきたい点（逆質問）はございますか？"
                ),
                pass_to_interviewer_id=None,
                ready_for_next_phase=False,
            )

        elif phase == InterviewPhase.CLOSING:
            return InterviewerResponse(
                thought="総じて優秀で誠実なエンジニアという印象。裏の選考会議でしっかり議論しよう。",
                speech=(
                    f"本日は多くの貴重なお話をお聞かせいただき、誠にありがとうございました。"
                    f"本日の選考結果につきましては、1週間以内に採用担当よりメールにてご連絡を差し上げます。"
                    "本日はありがとうございました。どうぞお気をつけてお帰りください。"
                ),
                pass_to_interviewer_id=None,
                ready_for_next_phase=True,
            )

        return InterviewerResponse(
            thought="状況を把握し、次の対応を検討中。",
            speech=f"なるほど、承知いたしました。{candidate.name}さんのお考えがよく伝わりました。",
            pass_to_interviewer_id=None,
            ready_for_next_phase=False,
        )

