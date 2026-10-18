"""Rich を使った対話型CLIテストスクリプト。

企業・求人・面接官1〜5名の対話、リアルタイム心の声メモ表示、
音声UXのシミュレーション、裏の合否判定ミーティング、レーダー評価、満点模範解答を出力する。
"""

import sys
import time
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule
from rich.markdown import Markdown
from rich.prompt import Prompt

from coordinator import InterviewCoordinator
from models import (
    CandidateProfile,
    CompanyInfo,
    Interviewer,
    InterviewPhase,
    JobPosting,
)

console = Console()

# 面接官ごとのカラーパレット
INTERVIEWER_COLORS = ["cyan", "magenta", "yellow", "green", "blue"]


def get_default_dataset() -> tuple[CompanyInfo, JobPosting, CandidateProfile, list[Interviewer]]:
    """テスト用のデフォルトデータセット"""
    company = CompanyInfo(
        name="株式会社ネクストバリュー (NextValue Inc.)",
        business_summary="生成AIを活用したエンタープライズ向け業務自動化SaaSプラットフォームの開発・運営。",
        culture_values="徹底した顧客価値主義、技術的好奇心とオーナーシップ、透明性の高い率直な議論。",
    )

    job = JobPosting(
        title="シニアバックエンドエンジニア",
        description="自社SaaSのバックエンドAPI、大規模リアルタイム推論基盤、データパイプラインの設計・開発・運用。",
        requirements=[
            "Python / FastAPI または Go によるWebアプリケーションの設計・開発経験3年以上",
            "RDBMSおよびNoSQLを用いたデータモデリングとパフォーマンスチューニング経験",
            "マイクロサービスや分散システムのアーキテクチャ設計経験",
        ],
        preferred_requirements=[
            "LLM（Gemini, OpenAI等）を用いたプロダクション開発経験",
            "テックリードやアーキテクトとしてのチームリード経験",
        ],
    )

    candidate = CandidateProfile(
        name="田中 雄大",
        resume_summary="Webバックエンドエンジニアとして5年間の実務経験。直近はFinTech企業にてFastAPIを用いた決済連携API基盤をマイクロサービス化し、ピーク時スループットを3倍に改善。DBクエリ最適化や分散トランザクションの知見を有する。",
        motivation="貴社が推進する生成AI基盤の社会実装に強く共感しており、これまでの高負荷バックエンド設計の知見を活かして、スケールする信頼性の高いAI基盤を創り上げたいと考えています。",
    )

    # 3名の面接官（性格・特徴は意図的にNoneにして、AIが自動補完する機能を検証）
    interviewers = [
        Interviewer(
            id="interviewer_1",
            name="佐藤 健一",
            role="テックリード / アーキテクト",
            personality=None,  # AIによる自動補完
            is_lead=True,
            voice_preset="male_low",
        ),
        Interviewer(
            id="interviewer_2",
            name="高橋 美咲",
            role="人事採用責任者 (HRBP)",
            personality=None,  # AIによる自動補完
            is_lead=False,
            voice_preset="female_calm",
        ),
        Interviewer(
            id="interviewer_3",
            name="渡辺 徹",
            role="執行役員 CTO",
            personality=None,  # AIによる自動補完
            is_lead=False,
            voice_preset="male_calm",
        ),
    ]

    return company, job, candidate, interviewers


def main():
    import argparse
    parser = argparse.ArgumentParser(description="AI Interviewer CLI Simulator")
    parser.add_argument("--mock", action="store_true", help="Gemini APIを使わずモックデータで動作検証する")
    args = parser.parse_args()

    # APIキーの存在判定
    from config import settings
    has_api_key = bool(settings.get_effective_api_key())
    is_mock = args.mock or not has_api_key

    console.print()
    console.print(
        Panel.fit(
            "[bold white]🎙️ AI Interviewer - Step 1: 頭脳コア (CLI Simulator)[/bold white]\n"
            "[dim]〜 複数面接官対話・心の声メモ・裏の合否判定ミーティング・満点模範解答 〜[/dim]",
            border_style="bold blue",
        )
    )

    if not has_api_key:
        console.print(
            Panel(
                "[bold yellow]⚠️ Gemini APIキーが設定されていません。[/bold yellow]\n"
                "[dim]Gemini 2.5 Flash によるリアルタイム推論を行う場合は、backend/.env に GEMINI_API_KEY=xxx を設定してください。\n"
                "現在は【オフライン検証モックモード】で動作します。全UI、フェーズ進行、裏会議、模範解答を体験いただけます。[/dim]",
                border_style="yellow",
            )
        )
    elif is_mock:
        console.print("[dim yellow]※ --mock フラグが指定されたため、モックモードで起動します。[/dim yellow]\n")
    else:
        console.print(f"[bold green]✓ Gemini API 接続確認済み (モデル: {settings.gemini_model})[/bold green]\n")

    company, job, candidate, interviewers = get_default_dataset()

    # 概要表示
    console.print(Rule("[bold cyan]1. セッション基本情報[/bold cyan]"))
    info_table = Table(show_header=False, box=None)
    info_table.add_row("[bold]志望企業:[/bold]", f"[cyan]{company.name}[/cyan]")
    info_table.add_row("[bold]募集職種:[/bold]", f"[yellow]{job.title}[/yellow]")
    info_table.add_row("[bold]候補者氏名:[/bold]", f"[green]{candidate.name}[/green]")
    info_table.add_row(
        "[bold]面接官人数:[/bold]",
        f"{len(interviewers)}名 (" + ", ".join([f"{i.name} [{i.role}]" for i in interviewers]) + ")",
    )
    console.print(info_table)
    console.print()

    # コーディネーターの初期化
    with console.status("[bold green]面接官ペルソナを自動補完中（AI分析）...[/bold green]"):
        coordinator = InterviewCoordinator(
            company=company,
            job=job,
            candidate=candidate,
            interviewers=interviewers,
            qa_turns_per_interviewer=1,  # CLIテスト用に各面接官1問ずつに設定
            mock=is_mock,
        )
        coordinator.initialize_personas()

    # 自動補完されたペルソナの確認表示
    console.print(Rule("[bold magenta]面接官ペルソナ自動補完結果[/bold magenta]"))
    for idx, interviewer in enumerate(coordinator.interviewers):
        color = INTERVIEWER_COLORS[idx % len(INTERVIEWER_COLORS)]
        lead_badge = " [bold red][代表面接官][/bold red]" if interviewer.is_lead else ""
        console.print(
            Panel(
                f"[bold {color}]{interviewer.name}[/bold {color}]（{interviewer.role}）{lead_badge}\n"
                f"[dim]生成されたペルソナ・スタンス:[/dim]\n{interviewer.personality}",
                border_style=color,
                title=f"Interviewer #{idx + 1}",
            )
        )
    console.print()

    # 面接の開始
    console.print(Rule("[bold green]2. 面接セッション開始[/bold green]"))
    initial_utterance = coordinator.start_interview()

    # 初期発話の描画
    display_interviewer_utterance(initial_utterance, coordinator.interviewers)

    # 対話ループ
    while coordinator.current_phase not in [InterviewPhase.EVALUATION_MEETING, InterviewPhase.COMPLETED]:
        # 音声UXポリシーのメッセージ
        console.print(
            "[bold green]🎙️ [マイク有効化] あなたの発言を入力してください[/bold green] "
            "[dim](そのままEnterで送信 / 'exit'で終了):[/dim]"
        )
        try:
            candidate_input = Prompt.ask("[bold white]候補者（あなた）[/bold white]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]入力を終了し、裏会議へ移行します。[/yellow]")
            break

        if not candidate_input.strip() or candidate_input.strip().lower() in ["exit", "quit"]:
            console.print("[yellow]面接を終了し、裏会議へ移行します。[/yellow]")
            break

        console.print()
        # 面接官発話中のマイク自動ロックUXメッセージ
        console.print("[dim]🔒 面接官が考え、発話しています（マイクは自動ロック中）...[/dim]")

        # 面接官ターンの実行
        with console.status("[bold cyan]面接官が応答を生成中...[/bold cyan]"):
            utterance = coordinator.process_candidate_turn(candidate_input)

        display_interviewer_utterance(utterance, coordinator.interviewers)

        if coordinator.current_phase == InterviewPhase.CLOSING:
            # クロージング発話が出たら終了へ
            console.print("[bold yellow]面接の全フェーズが完了しました。[/bold yellow]\n")
            break

    # 3. 裏の合否判定ミーティング
    console.print()
    console.print(Rule("[bold red]★ 3. 裏の合否判定ミーティング（自律討議）[/bold red]"))
    console.print("[dim]候補者が退室しました。面接官たちだけでリアルな合否判定ミーティングを開始します...[/dim]\n")

    with console.status("[bold red]面接官同士が自律討議を行い、評価レポートを生成中...[/bold red]"):
        report = coordinator.run_evaluation_meeting()

    # 自律討議の議事録の表示
    console.print("[bold white underline]👥 面接官同士の選考討議ログ（議事録）:[/bold white underline]\n")
    for msg in report.meeting_transcript:
        interviewer = next((i for i in coordinator.interviewers if i.id == msg.interviewer_id), None)
        color = "cyan"
        if interviewer:
            idx = coordinator.interviewers.index(interviewer)
            color = INTERVIEWER_COLORS[idx % len(INTERVIEWER_COLORS)]

        console.print(f"[bold {color}]{msg.interviewer_name} ({msg.role}):[/bold {color}] {msg.content}")
        time.sleep(0.3)

    console.print()

    # 合否判定バナー
    decision_color = "green" if report.passed else "red"
    if report.decision_type == "保留":
        decision_color = "yellow"

    console.print(
        Panel(
            f"[bold {decision_color}]最終判定: {report.decision_type}[/bold {decision_color}]\n\n"
            f"[bold]総括フィードバック:[/bold]\n{report.verdict_summary}",
            title="選考結果判定サマリー",
            border_style=decision_color,
        )
    )
    console.print()

    # レーダーチャート用スコア一覧
    console.print(Rule("[bold cyan]📊 評価項目別スコア（レーダーチャート用データ）[/bold cyan]"))
    score_table = Table(title="評価スコア (10点満点)", header_style="bold magenta")
    score_table.add_column("評価項目", style="bold white", width=30)
    score_table.add_column("得点", justify="center", style="bold yellow", width=10)
    score_table.add_column("評価理由・フィードバック", style="dim white")

    for score in report.scores:
        bar = "★" * score.score + "☆" * (10 - score.score)
        score_table.add_row(score.category, f"{score.score}/10\n{bar}", score.reason)
    console.print(score_table)
    console.print()

    # 満点模範解答集
    console.print(Rule("[bold green]💡 各質問に対する添削 ＆ 100点満点模範解答[/bold green]"))
    for idx, ma in enumerate(report.model_answers, start=1):
        console.print(
            Panel(
                f"[bold cyan]質問 {idx}:[/bold cyan] {ma.question}\n\n"
                f"[bold yellow]あなたの回答:[/bold yellow]\n{ma.candidate_answer}\n\n"
                f"[bold red]減点・改善ポイント:[/bold red]\n{ma.critique}\n\n"
                f"[bold green]💯 100点満点の模範解答例:[/bold green]\n{ma.model_answer}",
                title=f"Question #{idx} Feedback & Model Answer",
                border_style="green",
            )
        )
    console.print()
    console.print("[bold cyan]✨ Step 1 頭脳コア CLI の全工程が完了しました。[/bold cyan]\n")


def display_interviewer_utterance(utterance, interviewers: list[Interviewer]):
    """面接官の発言と心の声メモを美しく描画"""
    interviewer = next((i for i in interviewers if i.id == utterance.speaker_id), None)
    idx = interviewers.index(interviewer) if interviewer else 0
    color = INTERVIEWER_COLORS[idx % len(INTERVIEWER_COLORS)]
    role_str = f" ({interviewer.role})" if interviewer else ""

    pass_text = ""
    if utterance.pass_to_id:
        target = next((i for i in interviewers if i.id == utterance.pass_to_id), None)
        target_name = target.name if target else utterance.pass_to_id
        pass_text = f"\n\n[bold italic {color}]👉 次の質問を {target_name} さんへパスしました[/bold italic {color}]"

    thought_box = ""
    if utterance.thought:
        thought_box = f"\n\n[dim italic]💭 【本音・心の声メモ】: {utterance.thought}[/dim italic]"

    content = f"[white]{utterance.content}[/white]{thought_box}{pass_text}"

    console.print(
        Panel(
            content,
            title=f"[bold {color}]{utterance.speaker_name}{role_str}[/bold {color}] - [{utterance.phase.value}]",
            border_style=color,
            subtitle="[dim]🔒 音声再生中（マイクOFF）[/dim]",
        )
    )
    console.print()


if __name__ == "__main__":
    main()
