/**
 * AI Interviewer - Frontend Application Logic
 * Smart Extraction, Realtime WebSocket Interview, Dynamic Audio UX, and Evaluation Dashboard.
 */

// --- アプリケーション状態 ---
const state = {
  ws: null,
  isThoughtsVisible: true, // 練習モード (true) vs 本番モード (false)
  interviewers: [],
  currentPhase: "ORIENTATION",
  lastEvaluationReport: null,
};

// デフォルト面接官リスト (1〜5名)
const defaultInterviewers = [
  {
    id: "interviewer_1",
    name: "佐藤 健一",
    role: "テックリード / アーキテクト",
    personality: "",
    is_lead: true,
    voice_preset: "male_low",
  },
  {
    id: "interviewer_2",
    name: "高橋 美咲",
    role: "人事採用責任者 (HRBP)",
    personality: "",
    is_lead: false,
    voice_preset: "female_calm",
  },
  {
    id: "interviewer_3",
    name: "渡辺 徹",
    role: "執行役員 CTO",
    personality: "",
    is_lead: false,
    voice_preset: "male_calm",
  },
];

// 面接官アバターカラー
const INTERVIEWER_COLORS = [
  { bg: "linear-gradient(135deg, #4f46e5, #06b6d4)", text: "#38bdf8" },
  { bg: "linear-gradient(135deg, #ec4899, #a855f7)", text: "#f472b6" },
  { bg: "linear-gradient(135deg, #f59e0b, #ef4444)", text: "#fbbf24" },
  { bg: "linear-gradient(135deg, #10b981, #06b6d4)", text: "#34d399" },
  { bg: "linear-gradient(135deg, #8b5cf6, #3b82f6)", text: "#a78bfa" },
];

// --- 初期化 ---
document.addEventListener("DOMContentLoaded", () => {
  state.interviewers = JSON.parse(JSON.stringify(defaultInterviewers));
  setupTabs();
  setupDropzones();
  setupInterviewerCards();
  setupEventHandlers();
  loadPresetData(); // 初期値としてプリセットを読み込んでおく
});

// ==========================================================================
// タブ切り替え制御
// ==========================================================================
function setupTabs() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      const parentCard = btn.closest(".card");
      parentCard.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      parentCard.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));

      btn.classList.add("active");
      const targetId = `tab-${btn.dataset.tab}`;
      const targetContent = document.getElementById(targetId);
      if (targetContent) targetContent.classList.add("active");
    });
  });
}

// ==========================================================================
// ドロップゾーン（ファイルアップロード）
// ==========================================================================
function setupDropzones() {
  // 求人票ドロップゾーン
  const dropJob = document.getElementById("dropzone-job");
  const fileJob = document.getElementById("file-job");
  dropJob.addEventListener("click", () => fileJob.click());
  dropJob.addEventListener("dragover", (e) => { e.preventDefault(); dropJob.classList.add("dragover"); });
  dropJob.addEventListener("dragleave", () => dropJob.classList.remove("dragover"));
  dropJob.addEventListener("drop", (e) => {
    e.preventDefault();
    dropJob.classList.remove("dragover");
    if (e.dataTransfer.files.length > 0) handleJobFileUpload(e.dataTransfer.files[0]);
  });
  fileJob.addEventListener("change", (e) => {
    if (e.target.files.length > 0) handleJobFileUpload(e.target.files[0]);
  });

  // 職務経歴書ドロップゾーン
  const dropCand = document.getElementById("dropzone-candidate");
  const fileCand = document.getElementById("file-candidate");
  dropCand.addEventListener("click", () => fileCand.click());
  dropCand.addEventListener("dragover", (e) => { e.preventDefault(); dropCand.classList.add("dragover"); });
  dropCand.addEventListener("dragleave", () => dropCand.classList.remove("dragover"));
  dropCand.addEventListener("drop", (e) => {
    e.preventDefault();
    dropCand.classList.remove("dragover");
    if (e.dataTransfer.files.length > 0) handleCandidateFileUpload(e.dataTransfer.files[0]);
  });
  fileCand.addEventListener("change", (e) => {
    if (e.target.files.length > 0) handleCandidateFileUpload(e.target.files[0]);
  });
}

// ==========================================================================
// スマート取り込み API 呼び出し
// ==========================================================================
async function handleJobUrlExtract() {
  const urlInput = document.getElementById("input-job-url");
  const url = urlInput.value.trim();
  const alertBox = document.getElementById("alert-job-error");
  alertBox.classList.add("hidden");

  if (!url) {
    showError(alertBox, "求人ページのURLを入力してください。");
    return;
  }

  const btn = document.getElementById("btn-extract-job-url");
  btn.disabled = true;
  btn.textContent = "AI解析中...";

  try {
    const res = await fetch("/api/extract/job/url", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await res.json();

    if (!data.success) {
      showError(alertBox, data.error_message || "URLからの取得に失敗しました。");
    } else {
      populateJobForm(data.company, data.job);
    }
  } catch (err) {
    showError(alertBox, "解析サーバーとの通信に失敗しました。テキスト入力をお試しください。");
  } finally {
    btn.disabled = false;
    btn.textContent = "AI解析";
  }
}

async function handleJobTextExtract() {
  const text = document.getElementById("input-job-raw").value.trim();
  const alertBox = document.getElementById("alert-job-error");
  alertBox.classList.add("hidden");

  if (!text) {
    showError(alertBox, "求人票テキストを入力してください。");
    return;
  }

  const btn = document.getElementById("btn-extract-job-text");
  btn.disabled = true;
  btn.textContent = "抽出中...";

  try {
    const res = await fetch("/api/extract/job/text", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    const data = await res.json();
    populateJobForm(data.company, data.job);
  } catch (err) {
    showError(alertBox, "テキストの抽出に失敗しました。");
  } finally {
    btn.disabled = false;
    btn.textContent = "テキストから要件を抽出";
  }
}

async function handleJobFileUpload(file) {
  const statusEl = document.getElementById("file-job-status");
  const alertBox = document.getElementById("alert-job-error");
  alertBox.classList.add("hidden");
  statusEl.textContent = `解析中: ${file.name} ...`;
  statusEl.classList.remove("hidden");

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("/api/extract/job/file", {
      method: "POST",
      body: formData,
    });
    const data = await res.json();
    if (!data.success) {
      showError(alertBox, data.error_message || "ファイルの解析に失敗しました。");
      statusEl.classList.add("hidden");
    } else {
      statusEl.textContent = `✓ 完了: ${file.name}`;
      populateJobForm(data.company, data.job);
    }
  } catch (err) {
    showError(alertBox, "ファイル送信エラーが発生しました。");
    statusEl.classList.add("hidden");
  }
}

async function handleCandidateTextExtract() {
  const text = document.getElementById("input-candidate-raw").value.trim();
  const alertBox = document.getElementById("alert-candidate-error");
  alertBox.classList.add("hidden");

  if (!text) {
    showError(alertBox, "経歴書テキストを入力してください。");
    return;
  }

  const btn = document.getElementById("btn-extract-candidate-text");
  btn.disabled = true;
  btn.textContent = "抽出中...";

  try {
    const res = await fetch("/api/extract/candidate/text", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    const data = await res.json();
    populateCandidateForm(data.candidate);
  } catch (err) {
    showError(alertBox, "経歴書の抽出に失敗しました。");
  } finally {
    btn.disabled = false;
    btn.textContent = "経歴からサマリーを抽出";
  }
}

async function handleCandidateFileUpload(file) {
  const statusEl = document.getElementById("file-candidate-status");
  const alertBox = document.getElementById("alert-candidate-error");
  alertBox.classList.add("hidden");
  statusEl.textContent = `解析中: ${file.name} ...`;
  statusEl.classList.remove("hidden");

  const formData = new FormData();
  formData.append("file", file);

  try {
    const res = await fetch("/api/extract/candidate/file", {
      method: "POST",
      body: formData,
    });
    const data = await res.json();
    if (!data.success) {
      showError(alertBox, data.error_message || "経歴書ファイルの解析に失敗しました。");
      statusEl.classList.add("hidden");
    } else {
      statusEl.textContent = `✓ 完了: ${file.name}`;
      populateCandidateForm(data.candidate);
    }
  } catch (err) {
    showError(alertBox, "ファイル送信エラーが発生しました。");
    statusEl.classList.add("hidden");
  }
}

function populateJobForm(company, job) {
  if (company) {
    document.getElementById("company-name").value = company.name || "";
    document.getElementById("company-business").value = company.business_summary || "";
    document.getElementById("company-culture").value = company.culture_values || "";
  }
  if (job) {
    document.getElementById("job-title").value = job.title || "";
    document.getElementById("job-description").value = job.description || "";
    document.getElementById("job-requirements").value = (job.requirements || []).join(", ");
  }
}

function populateCandidateForm(candidate) {
  if (candidate) {
    document.getElementById("candidate-name").value = candidate.name || "";
    document.getElementById("candidate-resume").value = candidate.resume_summary || "";
    document.getElementById("candidate-motivation").value = candidate.motivation || "";
  }
}

function showError(el, msg) {
  el.textContent = msg;
  el.classList.remove("hidden");
}

// ==========================================================================
// 面接官管理カード（1〜5名）
// ==========================================================================
function setupInterviewerCards() {
  const container = document.getElementById("interviewers-list");
  container.innerHTML = "";

  state.interviewers.forEach((interviewer, idx) => {
    const card = document.createElement("div");
    card.className = `interviewer-card ${interviewer.is_lead ? "lead" : ""}`;

    const leadBadge = interviewer.is_lead
      ? `<span class="badge-lead">★ 代表面接官 (進行役)</span>`
      : `<button class="btn btn-secondary btn-sm" onclick="setLeadInterviewer(${idx})">代表にする</button>`;

    const removeBtn = state.interviewers.length > 1
      ? `<button class="btn-remove" onclick="removeInterviewer(${idx})" title="削除">✕</button>`
      : "";

    card.innerHTML = `
      <div class="interviewer-card-top">
        <div class="flex-row items-center gap-2">
          <div class="avatar-circle" style="background: ${INTERVIEWER_COLORS[idx % INTERVIEWER_COLORS.length].bg}">
            ${interviewer.name ? interviewer.name[0] : "面"}
          </div>
          <span style="font-weight: 700; font-size: 14px;">Interviewer #${idx + 1}</span>
        </div>
        <div class="flex-row items-center gap-2">
          ${leadBadge}
          ${removeBtn}
        </div>
      </div>
      <div class="input-group mb-2">
        <label>面接官氏名</label>
        <input type="text" value="${escapeHtml(interviewer.name)}" onchange="updateInterviewerField(${idx}, 'name', this.value)">
      </div>
      <div class="input-group mb-2">
        <label>役職・役割 * (例: テックリード, 人事, CTO)</label>
        <input type="text" value="${escapeHtml(interviewer.role)}" placeholder="必須" onchange="updateInterviewerField(${idx}, 'role', this.value)">
      </div>
      <div class="input-group">
        <div class="flex-between">
          <label>性格・人物特徴 (空欄時はAI自動補完)</label>
          <button class="btn-toggle" onclick="autoCompletePersona(${idx})">✨ AI自動生成</button>
        </div>
        <textarea rows="2" placeholder="空欄の場合、役割からAIが自動補完します" onchange="updateInterviewerField(${idx}, 'personality', this.value)">${escapeHtml(interviewer.personality || "")}</textarea>
      </div>
    `;
    container.appendChild(card);
  });
}

window.updateInterviewerField = function(index, field, value) {
  state.interviewers[index][field] = value;
};

window.setLeadInterviewer = function(index) {
  state.interviewers.forEach((i, idx) => i.is_lead = (idx === index));
  setupInterviewerCards();
};

window.removeInterviewer = function(index) {
  if (state.interviewers.length <= 1) return;
  state.interviewers.splice(index, 1);
  if (!state.interviewers.some(i => i.is_lead)) {
    state.interviewers[0].is_lead = true;
  }
  setupInterviewerCards();
};

window.autoCompletePersona = async function(index) {
  const interviewer = state.interviewers[index];
  const companyName = document.getElementById("company-name").value || "志望企業";
  const business = document.getElementById("company-business").value || "事業内容";
  const culture = document.getElementById("company-culture").value || "";

  try {
    const res = await fetch("/api/interviewer/complete-persona", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        role: interviewer.role || "面接官",
        company_name: companyName,
        business_summary: business,
        culture_values: culture,
      }),
    });
    const data = await res.json();
    interviewer.personality = data.personality;
    setupInterviewerCards();
  } catch (err) {
    alert("ペルソナの自動生成に失敗しました。");
  }
};

function addInterviewer() {
  if (state.interviewers.length >= 5) {
    alert("面接官は最大5名までです。");
    return;
  }
  state.interviewers.push({
    id: `interviewer_${state.interviewers.length + 1}`,
    name: `面接官 ${state.interviewers.length + 1}`,
    role: "現場エンジニア",
    personality: "",
    is_lead: false,
    voice_preset: "male_calm",
  });
  setupInterviewerCards();
}

function loadPresetData() {
  populateJobForm(
    {
      name: "株式会社ネクストバリュー (NextValue Inc.)",
      business_summary: "生成AIを活用したエンタープライズ向け業務自動化SaaSプラットフォームの開発・運営。",
      culture_values: "徹底した顧客価値主義、技術的好奇心とオーナーシップ、透明性の高い率直な議論。",
    },
    {
      title: "シニアバックエンドエンジニア",
      description: "自社SaaSのバックエンドAPI、大規模リアルタイム推論基盤、データパイプラインの設計・開発・運用。",
      requirements: [
        "Python / FastAPI によるWebアプリケーションの設計・開発実務経験3年以上",
        "RDBMSおよびNoSQLを用いたデータモデリングとパフォーマンスチューニング経験",
        "マイクロサービスや分散システムのアーキテクチャ設計経験",
      ],
    }
  );

  populateCandidateForm({
    name: "田中 雄大",
    resume_summary: "Webバックエンドエンジニアとして5年間の実務経験。直近はFinTech企業にてFastAPIを用いた決済連携API基盤をマイクロサービス化し、ピーク時スループットを3倍に改善。DBクエリ最適化や分散トランザクションの知見を有する。",
    motivation: "貴社が推進する生成AI基盤の社会実装に強く共感しており、これまでの高負荷バックエンド設計の知見を活かして、スケールする信頼性の高いAI基盤を創り上げたいと考えています。",
  });
}

// ==========================================================================
// イベントハンドラー設定
// ==========================================================================
function setupEventHandlers() {
  document.getElementById("btn-load-preset").addEventListener("click", loadPresetData);
  document.getElementById("btn-extract-job-url").addEventListener("click", handleJobUrlExtract);
  document.getElementById("btn-extract-job-text").addEventListener("click", handleJobTextExtract);
  document.getElementById("btn-extract-candidate-text").addEventListener("click", handleCandidateTextExtract);
  document.getElementById("btn-add-interviewer").addEventListener("click", addInterviewer);
  document.getElementById("btn-start-interview").addEventListener("click", startInterviewSession);
  document.getElementById("btn-send-message").addEventListener("click", sendCandidateMessage);
  document.getElementById("btn-force-finish").addEventListener("click", triggerEvaluationMeeting);
  document.getElementById("btn-close-modal").addEventListener("click", () => document.getElementById("evaluation-modal").classList.add("hidden"));
  document.getElementById("btn-restart").addEventListener("click", () => location.reload());
  document.getElementById("btn-download-report").addEventListener("click", downloadReportMarkdown);

  // 心の声メモ表示トグル
  const toggleBtn = document.getElementById("toggle-thoughts");
  toggleBtn.addEventListener("click", () => {
    state.isThoughtsVisible = !state.isThoughtsVisible;
    if (state.isThoughtsVisible) {
      toggleBtn.textContent = "練習モード (ON)";
      toggleBtn.classList.add("active");
    } else {
      toggleBtn.textContent = "本番モード (OFF)";
      toggleBtn.classList.remove("active");
    }
    document.querySelectorAll(".inner-thought-box").forEach((el) => {
      el.classList.toggle("hidden", !state.isThoughtsVisible);
    });
  });

  // テキストエリアで Enter 送信 (Shift+Enterで改行)
  const chatInput = document.getElementById("candidate-chat-input");
  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendCandidateMessage();
    }
  });
}

// ==========================================================================
// WebSocket リアルタイム面接セッション
// ==========================================================================
function startInterviewSession() {
  const companyName = document.getElementById("company-name").value.trim();
  const jobTitle = document.getElementById("job-title").value.trim();
  const candidateName = document.getElementById("candidate-name").value.trim();

  if (!companyName || !jobTitle || !candidateName) {
    alert("企業名、募集職種、候補者氏名を入力してください。");
    return;
  }

  // ビューの切り替え
  document.getElementById("setup-view").classList.remove("active");
  document.getElementById("interview-view").classList.add("active");

  // WebSocket の接続
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/interview`;
  state.ws = new WebSocket(wsUrl);

  const statusText = document.getElementById("connection-status-text");

  state.ws.onopen = () => {
    statusText.textContent = "Connected";

    // セッション開始ペイロード
    const payload = {
      company: {
        name: companyName,
        business_summary: document.getElementById("company-business").value.trim(),
        culture_values: document.getElementById("company-culture").value.trim(),
      },
      job: {
        title: jobTitle,
        description: document.getElementById("job-description").value.trim(),
        requirements: document.getElementById("job-requirements").value.split(",").map(s => s.trim()).filter(Boolean),
      },
      candidate: {
        name: candidateName,
        resume_summary: document.getElementById("candidate-resume").value.trim(),
        motivation: document.getElementById("candidate-motivation").value.trim(),
      },
      interviewers: state.interviewers,
      mock: false,
    };

    state.ws.send(JSON.stringify({ type: "START_SESSION", payload }));
  };

  state.ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    handleWsEvent(data);
  };

  state.ws.onclose = () => {
    statusText.textContent = "Disconnected";
  };

  state.ws.onerror = (err) => {
    console.error("WebSocket Error:", err);
    statusText.textContent = "Error";
  };
}

function handleWsEvent(data) {
  switch (data.type) {
    case "PERSONAS_READY":
      state.interviewers = data.interviewers;
      renderRoomInterviewers();
      break;

    case "SPEAKER_STATUS":
      updateAudioUxStatus(data.status, data.message, data.speaker_id);
      break;

    case "INTERVIEWER_UTTERANCE":
      appendInterviewerMessage(data.utterance);
      if (data.current_phase) updatePhaseStepper(data.current_phase);
      break;

    case "INTERVIEW_CLOSING":
      updateAudioUxStatus("active", "面接が終了しました。右上の「裏会議を見る」ボタンを押してください。");
      break;

    case "EVALUATION_STARTED":
      openEvaluationModal();
      break;

    case "MEETING_UTTERANCE":
      appendMeetingUtterance(data.utterance);
      break;

    case "EVALUATION_REPORT":
      state.lastEvaluationReport = data.report;
      renderEvaluationReport(data.report);
      break;

    case "ERROR":
      alert("エラーが発生しました: " + data.message);
      break;
  }
}

// ==========================================================================
// 画面レンダリング（面接ルーム）
// ==========================================================================
function renderRoomInterviewers() {
  const container = document.getElementById("room-interviewers-container");
  container.innerHTML = "";

  state.interviewers.forEach((interviewer, idx) => {
    const chip = document.createElement("div");
    chip.id = `room-interviewer-${interviewer.id}`;
    chip.className = "room-interviewer-chip";

    const color = INTERVIEWER_COLORS[idx % INTERVIEWER_COLORS.length];
    chip.innerHTML = `
      <div class="avatar-circle" style="background: ${color.bg}">${interviewer.name[0]}</div>
      <div>
        <div class="chip-name">${escapeHtml(interviewer.name)}</div>
        <div class="chip-role">${escapeHtml(interviewer.role)}</div>
      </div>
    `;
    container.appendChild(chip);
  });
}

function updateAudioUxStatus(status, message, speakerId) {
  const banner = document.getElementById("audio-ux-banner");
  const textEl = document.getElementById("audio-ux-text");
  const inputEl = document.getElementById("candidate-chat-input");
  const sendBtn = document.getElementById("btn-send-message");

  textEl.textContent = message;

  // 面接官チップのハイライト
  document.querySelectorAll(".room-interviewer-chip").forEach(c => c.classList.remove("speaking"));
  if (speakerId) {
    const chip = document.getElementById(`room-interviewer-${speakerId}`);
    if (chip) chip.classList.add("speaking");
  }

  if (status === "speaking") {
    banner.className = "audio-ux-banner locked";
    inputEl.disabled = true;
    sendBtn.disabled = true;
  } else {
    banner.className = "audio-ux-banner active";
    inputEl.disabled = false;
    sendBtn.disabled = false;
    inputEl.focus();
  }
}

function appendInterviewerMessage(utterance) {
  const list = document.getElementById("messages-list");
  const row = document.createElement("div");
  row.className = "message-row interviewer";

  const passHtml = utterance.pass_to_id
    ? `<div class="pass-badge">👉 次の質問を他の面接官へパスしました</div>`
    : "";

  const thoughtHtml = utterance.thought
    ? `<div class="inner-thought-box ${state.isThoughtsVisible ? "" : "hidden"}">
        <span>💭</span>
        <div><strong>本音メモ:</strong> ${escapeHtml(utterance.thought)}</div>
       </div>`
    : "";

  row.innerHTML = `
    <div class="message-meta">
      <span class="speaker-name"><strong>${escapeHtml(utterance.speaker_name)}</strong></span>
      <span class="phase-tag">${escapeHtml(utterance.phase)}</span>
    </div>
    <div class="message-bubble">${escapeHtml(utterance.content)}</div>
    ${thoughtHtml}
    ${passHtml}
  `;

  list.appendChild(row);
  list.scrollTop = list.scrollHeight;
}

function sendCandidateMessage() {
  const inputEl = document.getElementById("candidate-chat-input");
  const content = inputEl.value.trim();
  if (!content || !state.ws) return;

  // 候補者のメッセージを即座に描画
  const list = document.getElementById("messages-list");
  const row = document.createElement("div");
  row.className = "message-row candidate";
  row.innerHTML = `
    <div class="message-meta" style="justify-content: flex-end;">
      <span>あなた (候補者)</span>
    </div>
    <div class="message-bubble">${escapeHtml(content)}</div>
  `;
  list.appendChild(row);
  list.scrollTop = list.scrollHeight;

  // サーバーへ送信
  state.ws.send(JSON.stringify({ type: "CANDIDATE_MESSAGE", content }));
  inputEl.value = "";
}

function updatePhaseStepper(phase) {
  state.currentPhase = phase;
  const phases = ["ORIENTATION", "ORIENTATION_QA", "SELF_INTRODUCTION", "INTERVIEW_QA", "REVERSE_QA", "CLOSING"];
  const currentIdx = phases.indexOf(phase);

  document.querySelectorAll(".step-item").forEach((item) => {
    const itemPhase = item.dataset.phase;
    const itemIdx = phases.indexOf(itemPhase);

    item.classList.remove("active", "completed");
    if (itemIdx < currentIdx) {
      item.classList.add("completed");
    } else if (itemIdx === currentIdx) {
      item.classList.add("active");
    }
  });
}

function triggerEvaluationMeeting() {
  if (!state.ws) return;
  state.ws.send(JSON.stringify({ type: "RUN_EVALUATION_MEETING" }));
}

// ==========================================================================
// 裏の合否判定ミーティング ＆ 総合レポートモーダル
// ==========================================================================
function openEvaluationModal() {
  const modal = document.getElementById("evaluation-modal");
  modal.classList.remove("hidden");
  document.getElementById("meeting-transcript-list").innerHTML = "";
  document.getElementById("model-answers-list").innerHTML = "";
  document.getElementById("scores-table-container").innerHTML = "";
}

function appendMeetingUtterance(msg) {
  const container = document.getElementById("meeting-transcript-list");
  const item = document.createElement("div");
  item.className = "meeting-item";
  item.innerHTML = `
    <div class="meeting-speaker">${escapeHtml(msg.interviewer_name)} (${escapeHtml(msg.role)})</div>
    <div>${escapeHtml(msg.content)}</div>
  `;
  container.appendChild(item);
  container.scrollTop = container.scrollHeight;
}

function renderEvaluationReport(report) {
  // 合否サマリー
  const banner = document.getElementById("verdict-banner");
  const typeEl = document.getElementById("verdict-decision");
  const sumEl = document.getElementById("verdict-summary-text");

  banner.className = `verdict-banner ${report.passed ? "passed" : "failed"}`;
  typeEl.textContent = report.decision_type || (report.passed ? "合格" : "見送り");
  sumEl.textContent = report.verdict_summary;

  // レーダーチャート描画
  drawRadarChart(report.scores || []);

  // スコア一覧表
  const scoresContainer = document.getElementById("scores-table-container");
  let tableHtml = `<table><thead><tr><th>評価項目</th><th>得点</th><th>理由・フィードバック</th></tr></thead><tbody>`;
  (report.scores || []).forEach((s) => {
    tableHtml += `
      <tr>
        <td><strong>${escapeHtml(s.category)}</strong></td>
        <td><span class="score-badge">${s.score}</span> / 10</td>
        <td style="color: var(--text-muted);">${escapeHtml(s.reason)}</td>
      </tr>
    `;
  });
  tableHtml += `</tbody></table>`;
  scoresContainer.innerHTML = tableHtml;

  // 満点模範解答
  const answersContainer = document.getElementById("model-answers-list");
  answersContainer.innerHTML = "";
  (report.model_answers || []).forEach((ma, idx) => {
    const card = document.createElement("div");
    card.className = "model-answer-card";
    card.innerHTML = `
      <div class="ma-question">Q${idx + 1}: ${escapeHtml(ma.question)}</div>
      <div class="ma-box ma-candidate"><strong>あなたの回答:</strong><br>${escapeHtml(ma.candidate_answer)}</div>
      <div class="ma-box ma-critique"><strong>改善指摘・減点理由:</strong><br>${escapeHtml(ma.critique)}</div>
      <div class="ma-box ma-perfect"><strong>💯 100点満点の模範解答例:</strong><br>${escapeHtml(ma.model_answer)}</div>
    `;
    answersContainer.appendChild(card);
  });
}

function drawRadarChart(scores) {
  const canvas = document.getElementById("radarChart");
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  const centerX = width / 2;
  const centerY = height / 2;
  const radius = Math.min(centerX, centerY) - 40;

  ctx.clearRect(0, 0, width, height);
  if (!scores || scores.length === 0) return;

  const numSides = scores.length;
  const angleStep = (Math.PI * 2) / numSides;

  // 背景の同心円（目盛り）
  const levels = 5;
  for (let l = 1; l <= levels; l++) {
    const r = (radius / levels) * l;
    ctx.beginPath();
    for (let i = 0; i < numSides; i++) {
      const angle = i * angleStep - Math.PI / 2;
      const x = centerX + r * Math.cos(angle);
      const y = centerY + r * Math.sin(angle);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.closePath();
    ctx.strokeStyle = "rgba(255, 255, 255, 0.08)";
    ctx.lineWidth = 1;
    ctx.stroke();
  }

  // 放射線軸
  for (let i = 0; i < numSides; i++) {
    const angle = i * angleStep - Math.PI / 2;
    const x = centerX + radius * Math.cos(angle);
    const y = centerY + radius * Math.sin(angle);
    ctx.beginPath();
    ctx.moveTo(centerX, centerY);
    ctx.lineTo(x, y);
    ctx.strokeStyle = "rgba(255, 255, 255, 0.12)";
    ctx.stroke();

    // 項目名ラベル
    const labelX = centerX + (radius + 22) * Math.cos(angle);
    const labelY = centerY + (radius + 18) * Math.sin(angle);
    ctx.fillStyle = "#94a3b8";
    ctx.font = "11px Inter, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    const shortLabel = scores[i].category.length > 8 ? scores[i].category.substring(0, 7) + "…" : scores[i].category;
    ctx.fillText(shortLabel, labelX, labelY);
  }

  // データポリゴンの描画
  ctx.beginPath();
  scores.forEach((s, i) => {
    const scoreVal = Math.max(1, Math.min(10, s.score));
    const r = (radius * (scoreVal / 10));
    const angle = i * angleStep - Math.PI / 2;
    const x = centerX + r * Math.cos(angle);
    const y = centerY + r * Math.sin(angle);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.closePath();

  ctx.fillStyle = "rgba(6, 182, 212, 0.25)";
  ctx.fill();
  ctx.strokeStyle = "#06b6d4";
  ctx.lineWidth = 2.5;
  ctx.stroke();

  // ポイント描画
  scores.forEach((s, i) => {
    const scoreVal = Math.max(1, Math.min(10, s.score));
    const r = (radius * (scoreVal / 10));
    const angle = i * angleStep - Math.PI / 2;
    const x = centerX + r * Math.cos(angle);
    const y = centerY + r * Math.sin(angle);

    ctx.beginPath();
    ctx.arc(x, y, 4, 0, Math.PI * 2);
    ctx.fillStyle = "#ffffff";
    ctx.fill();
    ctx.strokeStyle = "#4f46e5";
    ctx.lineWidth = 2;
    ctx.stroke();
  });
}

function downloadReportMarkdown() {
  if (!state.lastEvaluationReport) return;
  const report = state.lastEvaluationReport;

  let md = `# 🎙️ 面接総合評価レポート\n\n`;
  md += `## ■ 最終選考結果: ${report.decision_type} (${report.passed ? "合格" : "見送り"})\n\n`;
  md += `### 総括フィードバック:\n${report.verdict_summary}\n\n`;
  md += `## ■ 評価項目別スコア\n\n| 項目 | 得点 | 採点理由 |\n|---|---|---|\n`;
  (report.scores || []).forEach(s => {
    md += `| ${s.category} | ${s.score}/10 | ${s.reason} |\n`;
  });
  md += `\n## ■ 満点模範解答集\n\n`;
  (report.model_answers || []).forEach((ma, i) => {
    md += `### Q${i+1}: ${ma.question}\n- **あなたの回答:** ${ma.candidate_answer}\n- **改善指摘:** ${ma.critique}\n- **💯 100点満点模範解答:** ${ma.model_answer}\n\n`;
  });

  const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `interview_report_${new Date().toISOString().slice(0, 10)}.md`;
  a.click();
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
