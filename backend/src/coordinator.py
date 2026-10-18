"""面接進行コーディネーター（ステートマシン・面接官ターン制御）モジュール。

Phase 1〜6の進行フェーズ管理、面接官同士のパス制御、会話ログおよび心の声メモの保持を行う。
"""

from typing import Optional
from agent import InterviewerAgent
from meeting import EvaluationMeeting
from models import (
    CandidateProfile,
    CompanyInfo,
    EvaluationReport,
    Interviewer,
    InterviewPhase,
    JobPosting,
    Utterance,
)


class InterviewCoordinator:
    """面接全体の進行を司るコーディネーター"""

    def __init__(
        self,
        company: CompanyInfo,
        job: JobPosting,
        candidate: CandidateProfile,
        interviewers: list[Interviewer],
        qa_turns_per_interviewer: int = 2,
        mock: bool = False,
    ):
        if not interviewers:
            raise ValueError("面接官は最低1名以上設定してください。")
        if len(interviewers) > 5:
            raise ValueError("面接官の人数は最大5名までです。")

        self.company = company
        self.job = job
        self.candidate = candidate
        self.interviewers = interviewers
        self.qa_turns_per_interviewer = qa_turns_per_interviewer
        self.mock = mock

        # 代表面接官（lead）の選定（未設定なら先頭を代表とする）
        lead_candidates = [i for i in self.interviewers if i.is_lead]
        if not lead_candidates:
            self.interviewers[0].is_lead = True
            self.lead_interviewer = self.interviewers[0]
        else:
            self.lead_interviewer = lead_candidates[0]

        # エージェントの初期化
        self.agents: dict[str, InterviewerAgent] = {
            i.id: InterviewerAgent(interviewer=i, mock=self.mock) for i in self.interviewers
        }

        # セッション状態
        self.current_phase = InterviewPhase.ORIENTATION
        self.conversation_history: list[Utterance] = []
        self.interviewer_thoughts: dict[str, list[str]] = {i.id: [] for i in self.interviewers}
        self.current_speaker_id: str = self.lead_interviewer.id

        # フェーズごとの内部カウンタ
        self.phase_turn_count: int = 0
        self.interviewer_qa_counts: dict[str, int] = {i.id: 0 for i in self.interviewers}

        # 裏会議エンジン
        self.meeting_engine = EvaluationMeeting(mock=self.mock)

    def initialize_personas(self) -> None:
        """全面接官のペルソナ（オプショナルな性格）が未設定の場合、自動補完を行う"""
        for agent in self.agents.values():
            agent.ensure_persona_completed(self.company, self.job)

    def start_interview(self) -> Utterance:
        """面接を開始し、Phase 1 (ORIENTATION) の説明発話を行う"""
        self.initialize_personas()
        self.current_phase = InterviewPhase.ORIENTATION
        self.current_speaker_id = self.lead_interviewer.id

        lead_agent = self.agents[self.lead_interviewer.id]
        response = lead_agent.respond(
            phase=self.current_phase,
            company=self.company,
            job=self.job,
            candidate=self.candidate,
            other_interviewers=self.interviewers,
            conversation_history=self.conversation_history,
            my_past_thoughts=self.interviewer_thoughts[self.lead_interviewer.id],
            instruction="面接を開始し、候補者に歓迎の挨拶と企業概要・求人の募集背景を説明してください。",
        )

        utterance = self._record_interviewer_utterance(
            speaker_id=self.lead_interviewer.id,
            thought=response.thought,
            content=response.speech,
            pass_to_id=None,
        )

        # 説明完了後、質疑確認フェーズへ進める
        self.current_phase = InterviewPhase.ORIENTATION_QA
        self.phase_turn_count = 0
        return utterance

    def process_candidate_turn(self, candidate_input: str) -> Utterance:
        """候補者の入力を受け取り、会話ログに記録した上で、次に応答すべき面接官の発話を生成する"""
        # 候補者発話の記録
        self.conversation_history.append(
            Utterance(
                speaker_type="candidate",
                speaker_name=self.candidate.name,
                phase=self.current_phase,
                content=candidate_input.strip(),
            )
        )
        self.phase_turn_count += 1

        # フェーズ遷移と次発話者の選定
        instruction = self._evaluate_and_advance_phase(candidate_input)

        # 次の発話者エージェントを取得して発話を生成
        active_agent = self.agents[self.current_speaker_id]
        response = active_agent.respond(
            phase=self.current_phase,
            company=self.company,
            job=self.job,
            candidate=self.candidate,
            other_interviewers=self.interviewers,
            conversation_history=self.conversation_history,
            my_past_thoughts=self.interviewer_thoughts[self.current_speaker_id],
            instruction=instruction,
        )

        # 面接官発話を記録
        utterance = self._record_interviewer_utterance(
            speaker_id=self.current_speaker_id,
            thought=response.thought,
            content=response.speech,
            pass_to_id=response.pass_to_interviewer_id,
        )

        # 次の発話者の更新（パスがあればその面接官、なければ状況判断）
        self._update_next_speaker(response.pass_to_interviewer_id)

        return utterance

    def run_evaluation_meeting(self) -> EvaluationReport:
        """面接終了後、裏の合否判定会議を自律的に実施し総合評価レポートを作成する"""
        self.current_phase = InterviewPhase.EVALUATION_MEETING
        report = self.meeting_engine.conduct_meeting(
            company=self.company,
            job=self.job,
            candidate=self.candidate,
            interviewers=self.interviewers,
            conversation_history=self.conversation_history,
            interviewer_thoughts=self.interviewer_thoughts,
        )
        self.current_phase = InterviewPhase.COMPLETED
        return report

    def _evaluate_and_advance_phase(self, candidate_input: str) -> Optional[str]:
        """フェーズ遷移ロジックおよび追加指示の生成"""
        text = candidate_input.lower().strip()

        if self.current_phase == InterviewPhase.ORIENTATION_QA:
            # 質疑確認フェーズ: 「特にありません」「大丈夫です」等、または質問があった場合
            has_no_question = any(w in text for w in ["特に", "ありません", "大丈夫", "次へ", "問題"])
            if has_no_question or self.phase_turn_count >= 2:
                self.current_phase = InterviewPhase.SELF_INTRODUCTION
                self.current_speaker_id = self.lead_interviewer.id
                self.phase_turn_count = 0
                return "候補者に自己紹介とこれまでの経歴の概要を話すよう促してください。"
            else:
                return "候補者の質問に簡潔かつ丁寧に回答し、他に質問がなければ自己紹介へ進むよう案内してください。"

        elif self.current_phase == InterviewPhase.SELF_INTRODUCTION:
            # 自己紹介を聞き終えたらメイン質問フェーズ (INTERVIEW_QA) へ
            self.current_phase = InterviewPhase.INTERVIEW_QA
            self.phase_turn_count = 0
            # メイン質問の1番手を決定（代表または最初の面接官）
            self.current_speaker_id = self.interviewers[0].id
            return "候補者の自己紹介を受け止め、あなたの役割に応じた最初の深掘り質問を開始してください。"

        elif self.current_phase == InterviewPhase.INTERVIEW_QA:
            # メイン質問フェーズ: 各面接官の質問回数をインクリメント
            self.interviewer_qa_counts[self.current_speaker_id] += 1

            # 全面接官が十分な質問を行ったか確認
            total_questions = sum(self.interviewer_qa_counts.values())
            target_questions = len(self.interviewers) * self.qa_turns_per_interviewer

            if total_questions >= target_questions:
                # 逆質問フェーズへ遷移
                self.current_phase = InterviewPhase.REVERSE_QA
                self.phase_turn_count = 0
                self.current_speaker_id = self.lead_interviewer.id
                return "面接官からの質問は以上である旨を伝え、候補者からの逆質問（何か質問はありますか？）を受け付けてください。"
            return "候補者の回答を踏まえ、さらに鋭く深掘りするか、別の面接官にパスを回してください。"

        elif self.current_phase == InterviewPhase.REVERSE_QA:
            # 逆質問フェーズ: 候補者からの逆質問に回答、または終了確認
            has_no_more = any(w in text for w in ["以上", "ありません", "特に", "十分", "大丈夫"])
            if has_no_more or self.phase_turn_count >= 3:
                # 終了の挨拶フェーズへ遷移
                self.current_phase = InterviewPhase.CLOSING
                self.phase_turn_count = 0
                self.current_speaker_id = self.lead_interviewer.id
                return "本日の面接に対する感謝と労いを述べ、今後の選考連絡について伝えて面接を締めくくってください。"
            else:
                return "候補者の逆質問に対し、社内のリアルな実情や魅力を踏まえて誠実に回答してください。"

        elif self.current_phase == InterviewPhase.CLOSING:
            self.current_phase = InterviewPhase.EVALUATION_MEETING
            return "面接は終了しました。"

        return None

    def _update_next_speaker(self, pass_to_id: Optional[str]) -> None:
        """次のターンで発言する面接官を更新"""
        if pass_to_id and pass_to_id in self.agents:
            self.current_speaker_id = pass_to_id
            return

        if self.current_phase == InterviewPhase.INTERVIEW_QA:
            # まだ質問回数が少ない面接官を優先的に選択
            sorted_interviewers = sorted(
                self.interviewers,
                key=lambda x: self.interviewer_qa_counts.get(x.id, 0)
            )
            # 現在の面接官以外で最も回数が少ない人を選択
            candidates = [i for i in sorted_interviewers if i.id != self.current_speaker_id]
            if candidates:
                self.current_speaker_id = candidates[0].id
            else:
                self.current_speaker_id = sorted_interviewers[0].id
        elif self.current_phase in [InterviewPhase.ORIENTATION, InterviewPhase.ORIENTATION_QA, InterviewPhase.CLOSING]:
            self.current_speaker_id = self.lead_interviewer.id

    def _record_interviewer_utterance(
        self,
        speaker_id: str,
        thought: str,
        content: str,
        pass_to_id: Optional[str],
    ) -> Utterance:
        """面接官の発言および心の声メモをセッションに記録"""
        interviewer = next((i for i in self.interviewers if i.id == speaker_id), self.lead_interviewer)
        if thought:
            self.interviewer_thoughts[speaker_id].append(thought)

        utterance = Utterance(
            speaker_type="interviewer",
            speaker_id=speaker_id,
            speaker_name=interviewer.name,
            phase=self.current_phase,
            content=content,
            thought=thought,
            pass_to_id=pass_to_id,
        )
        self.conversation_history.append(utterance)
        return utterance
