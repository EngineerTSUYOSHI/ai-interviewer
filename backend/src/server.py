"""FastAPI ＆ WebSocket 面接対話サーバー。

企業・求人・職務経歴書のスマート取り込みAPI、
リアルタイム面接セッション管理、面接官同士の自律討議裏会議を提供する。
"""

import os
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, File, Form, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import settings
from coordinator import InterviewCoordinator
from extractor import SmartExtractor
from models import (
    CandidateProfile,
    CompanyInfo,
    EvaluationReport,
    Interviewer,
    InterviewPhase,
    JobPosting,
    PersonaCompletion,
)

app = FastAPI(title="AI Interviewer API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

extractor = SmartExtractor()

# リクエストスキーマ
class UrlExtractRequest(BaseModel):
    url: str

class TextExtractRequest(BaseModel):
    text: str

class PersonaRequest(BaseModel):
    role: str
    company_name: str
    business_summary: str
    culture_values: str = ""


# --- REST API: スマート取り込み ---

@app.post("/api/extract/job/url")
async def extract_job_from_url(req: UrlExtractRequest):
    """求人URLから企業・求人情報を抽出"""
    return extractor.extract_job_from_url(req.url)


@app.post("/api/extract/job/text")
async def extract_job_from_text(req: TextExtractRequest):
    """求人テキストから企業・求人情報を抽出"""
    return extractor.extract_job_from_text(req.text)


@app.post("/api/extract/job/file")
async def extract_job_from_file(file: UploadFile = File(...)):
    """求人ファイル（PDF/Word/画像）から抽出"""
    content = await file.read()
    return extractor.extract_job_from_file(content, file.filename or "file", file.content_type or "")


@app.post("/api/extract/candidate/text")
async def extract_candidate_from_text(req: TextExtractRequest):
    """職務経歴書テキストから候補者プロフィールを抽出"""
    return extractor.extract_candidate_from_text(req.text)


@app.post("/api/extract/candidate/file")
async def extract_candidate_from_file(file: UploadFile = File(...)):
    """職務経歴書ファイル（PDF/Word/画像）から抽出"""
    content = await file.read()
    return extractor.extract_candidate_from_file(content, file.filename or "file", file.content_type or "")


@app.post("/api/interviewer/complete-persona")
async def complete_interviewer_persona(req: PersonaRequest):
    """面接官の役割からAIがリアルなペルソナを自動補完"""
    temp_interviewer = Interviewer(id="temp", name="面接官", role=req.role)
    temp_company = CompanyInfo(name=req.company_name, business_summary=req.business_summary, culture_values=req.culture_values)
    temp_job = JobPosting(title="", description="")

    from agent import InterviewerAgent
    agent = InterviewerAgent(interviewer=temp_interviewer)
    agent.ensure_persona_completed(temp_company, temp_job)
    return {"personality": temp_interviewer.personality}


# --- WebSocket: リアルタイム面接セッション ---

class SessionPayload(BaseModel):
    company: CompanyInfo
    job: JobPosting
    candidate: CandidateProfile
    interviewers: list[Interviewer]
    qa_turns_per_interviewer: int = 2
    mock: bool = False


@app.websocket("/ws/interview")
async def interview_websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    coordinator: Optional[InterviewCoordinator] = None

    try:
        while True:
            data = await websocket.receive_json()
            event_type = data.get("type")

            if event_type == "START_SESSION":
                # セッション初期化
                payload = data.get("payload", {})
                company = CompanyInfo(**payload.get("company", {}))
                job = JobPosting(**payload.get("job", {}))
                candidate = CandidateProfile(**payload.get("candidate", {}))
                interviewers = [Interviewer(**i) for i in payload.get("interviewers", [])]
                is_mock = payload.get("mock", False) or not bool(settings.get_effective_api_key())

                coordinator = InterviewCoordinator(
                    company=company,
                    job=job,
                    candidate=candidate,
                    interviewers=interviewers,
                    qa_turns_per_interviewer=payload.get("qa_turns_per_interviewer", 2),
                    mock=is_mock,
                )

                # ペルソナ自動補完の通知
                coordinator.initialize_personas()
                await websocket.send_json({
                    "type": "PERSONAS_READY",
                    "interviewers": [i.model_dump() for i in coordinator.interviewers]
                })

                # Phase 1 のオープニング発話
                await websocket.send_json({
                    "type": "SPEAKER_STATUS",
                    "status": "speaking",
                    "speaker_id": coordinator.lead_interviewer.id,
                    "speaker_name": coordinator.lead_interviewer.name,
                    "message": "面接官が発話中（マイク自動ロック中）",
                })

                opening_utterance = coordinator.start_interview()

                await websocket.send_json({
                    "type": "INTERVIEWER_UTTERANCE",
                    "utterance": opening_utterance.model_dump(mode="json"),
                    "current_phase": coordinator.current_phase.value,
                })

            elif event_type == "CANDIDATE_MESSAGE":
                if not coordinator:
                    await websocket.send_json({"type": "ERROR", "message": "セッションが開始されていません。"})
                    continue

                candidate_text = data.get("content", "").strip()

                # 面接官の応答生成ステータス
                await websocket.send_json({
                    "type": "SPEAKER_STATUS",
                    "status": "speaking",
                    "message": "面接官が検討・発話中（マイク自動ロック中）",
                })

                utterance = coordinator.process_candidate_turn(candidate_text)

                await websocket.send_json({
                    "type": "INTERVIEWER_UTTERANCE",
                    "utterance": utterance.model_dump(mode="json"),
                    "current_phase": coordinator.current_phase.value,
                })

                if coordinator.current_phase == InterviewPhase.CLOSING:
                    # 終了フェーズに到達
                    await websocket.send_json({
                        "type": "INTERVIEW_CLOSING",
                        "message": "面接の全フェーズが完了しました。裏の合否判定ミーティングを開始できます。",
                    })

            elif event_type == "RUN_EVALUATION_MEETING":
                if not coordinator:
                    await websocket.send_json({"type": "ERROR", "message": "セッションがありません。"})
                    continue

                await websocket.send_json({
                    "type": "EVALUATION_STARTED",
                    "message": "候補者が退室しました。面接官による裏の合否判定ミーティングを開始します...",
                })

                report: EvaluationReport = coordinator.run_evaluation_meeting()

                # 議事録を順次送信して臨場感を演出
                for meeting_msg in report.meeting_transcript:
                    await websocket.send_json({
                        "type": "MEETING_UTTERANCE",
                        "utterance": meeting_msg.model_dump(),
                    })

                # 最終総合レポートの送信
                await websocket.send_json({
                    "type": "EVALUATION_REPORT",
                    "report": report.model_dump(mode="json"),
                })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        await websocket.send_json({"type": "ERROR", "message": str(e)})


# フロントエンド静的配信ディレクトリの設定（ルートの frontend または backend/src/frontend）
frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
if not frontend_dir.exists():
    frontend_dir.mkdir(parents=True, exist_ok=True)

app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
