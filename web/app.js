"use strict";

/* ==========================================================================
   Replay Chronicle · Private AoE2 Replay Coaching Web Application
   Zero-Terminal UX · Real-Time Progress Polling · Tactical Coaching Viewer
   ========================================================================== */

const $ = (id) => document.getElementById(id);

let platform = "geforce"; // default to Vincent's Mac setup
let me = null;
let activePollTimer = null;
let currentJob = null;

// Zero-Terminal Platform Guides
const STEPS = {
  geforce: [
    "Open <strong>GeForce NOW</strong> on your Mac and load your chosen match in <code>Single Player → Load Game → Replays</code>.",
    "Click <strong>Start Replay Review</strong> below. The spectator helper automatically sets spectator mode and follows the match.",
    "When the replay ends, the video streams automatically to generate your coaching report with fight clips and voice analysis."
  ],
  mac: [
    "Launch <em>Age of Empires II: DE</em> directly via Steam on your Mac and open your replay.",
    "Click <strong>Start Replay Review</strong> below to begin the automated camera tour.",
    "When finished, your tactical coaching breakdown and combat clips will appear in the Coaching Archives."
  ],
  windows: [
    "Open <em>Age of Empires II: DE</em> via Steam on your Windows PC and open your replay.",
    "Click <strong>Start Replay Review</strong> below to begin the automated camera tour.",
    "When finished, your tactical coaching breakdown and combat clips will appear in the Coaching Archives."
  ]
};

// Utilities
function esc(str) {
  if (str === null || str === undefined) return "";
  return String(str).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;"
  }[c]));
}

function fmtDur(seconds) {
  if (!isFinite(seconds) || seconds === null || seconds === undefined) return "--";
  const s = Math.max(0, Math.round(Number(seconds)));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${r < 10 ? "0" : ""}${r}`;
}

async function api(path, body) {
  try {
    const r = await fetch(path, {
      method: body ? "POST" : "GET",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined
    });
    const data = await r.json().catch(() => ({}));
    return { status: r.status, data };
  } catch (err) {
    return { status: 0, data: { error: err.message || "Network request failed" } };
  }
}

// ==========================================================================
// Authentication & User State
// ==========================================================================

function openAuthModal(msg) {
  const modal = $("authModal");
  if (!modal) return;
  modal.hidden = false;
  $("authMsg").textContent = msg || "";
  $("authMsg").className = "note text-center auth-status";
}

function closeAuthModal() {
  const modal = $("authModal");
  if (!modal) return;
  modal.hidden = true;
}

$("navLoginBtn").onclick = () => openAuthModal();
$("closeAuthModalBtn").onclick = () => closeAuthModal();
const archiveSignInBtn = $("archiveSignInBtn");
if (archiveSignInBtn) archiveSignInBtn.onclick = () => openAuthModal();

// Close modal when clicking on backdrop outside card
$("authModal").onclick = (e) => {
  if (e.target === $("authModal")) closeAuthModal();
};

async function refreshMe() {
  const { data } = await api("/api/me");
  me = data.user;
  const loggedIn = !!me;

  const navLoginBtn = $("navLoginBtn");
  const userBadge = $("userBadge");
  const archivePrompt = $("archivePrompt");

  if (navLoginBtn) navLoginBtn.style.display = loggedIn ? "none" : "inline-block";
  if (userBadge) {
    userBadge.style.display = loggedIn ? "inline-flex" : "none";
    $("userEmail").textContent = me || "";
  }
  if (archivePrompt) {
    archivePrompt.style.display = loggedIn ? "none" : "block";
  }

  if (loggedIn) {
    closeAuthModal();
    loadReviews();
    restoreActiveJob();
  }
}

$("loginBtn").onclick = async () => {
  const email = $("email").value.trim();
  const password = $("password").value;
  if (!email || !password) {
    $("authMsg").textContent = "Please enter both email and passphrase.";
    return;
  }
  const { status, data } = await api("/api/login", { email, password });
  if (status === 200) {
    $("authMsg").textContent = "Signed in successfully.";
    await refreshMe();
  } else {
    $("authMsg").textContent = data.error || "Login failed. Check your credentials.";
  }
};

$("registerBtn").onclick = async () => {
  const email = $("email").value.trim();
  const password = $("password").value;
  if (!email || password.length < 8) {
    $("authMsg").textContent = "Valid email and 8+ character password required.";
    return;
  }
  const { status, data } = await api("/api/register", { email, password });
  if (status === 200) {
    $("authMsg").textContent = "Account created and logged in.";
    await refreshMe();
  } else {
    $("authMsg").textContent = data.error || "Could not create account.";
  }
};

const logoutBtn = $("logoutBtn");
if (logoutBtn) {
  logoutBtn.onclick = async () => {
    await api("/api/logout", {});
    me = null;
    if (activePollTimer) clearInterval(activePollTimer);
    refreshMe();
  };
}

// Navigation Tabs Switching
function switchTab(tab) {
  const tabs = {
    review: { btn: $("navNewReview"), view: $("viewReview") },
    live: { btn: $("navLiveJob"), view: $("viewLive") },
    archives: { btn: $("navSavedReviews"), view: $("saved") },
    pro: { btn: $("navProTier"), view: $("viewPro") }
  };
  for (const [key, t] of Object.entries(tabs)) {
    if (!t.btn || !t.view) continue;
    if (key === tab) {
      t.btn.classList.add("active");
      t.view.hidden = false;
      t.view.style.display = "block";
    } else {
      t.btn.classList.remove("active");
      t.view.hidden = true;
      t.view.style.display = "none";
    }
  }
  if (tab === "archives" && me) {
    loadReviews();
  }
  window.scrollTo({ top: 0, behavior: "smooth" });
}

$("navNewReview").onclick = () => switchTab("review");
$("navLiveJob").onclick = () => switchTab("live");
$("navSavedReviews").onclick = () => switchTab("archives");
const navProTier = $("navProTier");
if (navProTier) navProTier.onclick = () => switchTab("pro");

// Pro Tier Waitlist Form Handling
const proWaitlistForm = $("proWaitlistForm");
const proWaitlistMsg = $("proWaitlistMsg");
const proEmailInput = $("proEmail");

if (proWaitlistForm) {
  try {
    const savedWaitlist = localStorage.getItem("aoe2_pro_waitlist");
    if (savedWaitlist && proWaitlistMsg) {
      proWaitlistMsg.style.display = "block";
      if (proEmailInput) proEmailInput.value = savedWaitlist;
    }
  } catch (e) {}

  proWaitlistForm.onsubmit = async (e) => {
    e.preventDefault();
    const email = proEmailInput ? proEmailInput.value.trim() : "";
    if (!email) return;
    try {
      localStorage.setItem("aoe2_pro_waitlist", email);
      await api("/api/waitlist", { email });
    } catch (err) {}
    if (proWaitlistMsg) proWaitlistMsg.style.display = "block";
    const btn = proWaitlistForm.querySelector("button");
    if (btn) btn.disabled = true;
  };
}

// ==========================================================================
// Platform Selection
// ==========================================================================

function updatePlatform(plat) {
  platform = plat;
  document.querySelectorAll("#platformBtns .platform-btn").forEach((btn) => {
    btn.classList.toggle("sel", btn.dataset.platform === plat);
  });
  
  const dlBtn = $("downloadHelperBtn");
  if (dlBtn) {
    dlBtn.href = `/api/helper/download/${plat}`;
    const span = dlBtn.querySelector("span");
    const small = dlBtn.querySelector("small");
    if (span) {
      span.textContent = plat === "windows" ? "⬇ Download Helper for Windows" : "⬇ Download Helper App for macOS";
    }
    if (small) {
      small.textContent = plat === "windows" ? "Steam on Windows PC" : "1-Click App Bundle (GeForce NOW & Steam Mac)";
    }
  }

  $("platformSteps").innerHTML = `
    <h4>Verified Setup: ${plat === "geforce" ? "GeForce NOW" : (plat === "mac" ? "Steam on Mac" : "Steam on Windows")}</h4>
    <ol>${STEPS[plat].map((s) => `<li>${s}</li>`).join("")}</ol>
  `;
  $("startBtn").disabled = false;
}

document.querySelectorAll("#platformBtns .platform-btn").forEach((btn) => {
  btn.onclick = () => updatePlatform(btn.dataset.platform);
});

// Initialize default platform
updatePlatform(platform);

// ==========================================================================
// Job Creation & Real-Time Status Polling
// ==========================================================================

// Coach Mode & Gemini Key Handling
const coachModeSelect = $("coachMode");
const geminiKeyBox = $("geminiKeyBox");
const geminiApiKeyInput = $("geminiApiKey");

if (geminiApiKeyInput) {
  try {
    const savedKey = localStorage.getItem("aoe2_gemini_api_key");
    if (savedKey) geminiApiKeyInput.value = savedKey;
  } catch (e) {}
}

if (coachModeSelect) {
  coachModeSelect.onchange = () => {
    if (geminiKeyBox) {
      geminiKeyBox.style.display = coachModeSelect.value === "gemini" ? "block" : "none";
    }
  };
}

$("startBtn").onclick = async () => {
  if (!me) {
    openAuthModal("Please sign in or create an account to start your review.");
    return;
  }
  if (!platform) return;
  const optInChecked = $("optin").checked;
  if (!optInChecked) {
    alert("Please check the opt-in consent box before starting the review.");
    return;
  }

  const coachMode = coachModeSelect ? coachModeSelect.value : "builtin";
  const geminiKey = geminiApiKeyInput ? geminiApiKeyInput.value.trim() : "";
  if (geminiKey) {
    try { localStorage.setItem("aoe2_gemini_api_key", geminiKey); } catch (e) {}
  }

  $("startBtn").disabled = true;
  $("startBtn").textContent = "Creating Job…";

  const payload = {
    platform,
    replay_choice: $("replayChoice").value,
    in_game_name: $("ign").value.trim() || "Player",
    camera_pace: $("cameraPace").value,
    coach_mode: coachMode,
    gemini_api_key: geminiKey,
    opt_in: optInChecked
  };

  const { status, data } = await api("/api/jobs", payload);
  $("startBtn").disabled = false;
  $("startBtn").textContent = "Start Replay Review";

  if (status !== 200) {
    $("jobBox").innerHTML = `
      <div class="callout-box parser-estimate" style="border-left-color:var(--red);">
        <div class="callout-header" style="color:var(--red);">Job Creation Failed</div>
        <p class="callout-body">${esc(data.error || "Could not create coaching job.")}</p>
      </div>`;
    return;
  }

  currentJob = {
    job_id: data.job_id,
    token: data.token,
    launch_url: data.launch_url,
    platform
  };
  try {
    sessionStorage.setItem("aoe2_active_job", JSON.stringify(currentJob));
  } catch (e) {}

  switchTab("live");
  renderActiveJobBox(currentJob);
  startPolling(currentJob.job_id, currentJob.token);

  // Attempt automatic protocol launch if helper is registered
  if (data.launch_url) {
    try {
      window.location.href = data.launch_url;
    } catch (e) {}
  }
};

function renderActiveJobBox(job) {
  const phoneUrl = `/job-status?job=${job.job_id}&token=${job.token}`;
  $("jobBox").innerHTML = `
    <div class="job-card">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:1rem;flex-wrap:wrap;">
        <h3 style="margin:0;">Job Dispatched: <code>${esc(job.job_id)}</code></h3>
        <span class="tag ready" id="jobStatusBadge">INITIALIZING</span>
      </div>
      <p class="note" style="margin-top:0.3rem;">Platform: <strong>${esc(job.platform)}</strong> · Focus Player: <strong>${esc($("ign").value || "Player")}</strong></p>

      <div class="row-btns">
        <a class="btn big gold-btn" href="${esc(job.launch_url)}">Launch Camera Director</a>
        <a class="btn ghost" href="/api/helper/download/${esc(job.platform)}" download="AoE2ReviewHelper.zip">⬇ Download Helper (.zip)</a>
        <button type="button" class="btn ghost danger-hover" id="cancelJobBtn" style="color:#e06c75;border-color:rgba(224,108,117,0.4);">✕ Cancel Review</button>
      </div>
      <div class="callout-box" style="margin-top:1rem;background:rgba(212,175,55,0.08);border-left:3px solid var(--gold);padding:0.9rem;">
        <p style="margin:0;font-size:0.92rem;line-height:1.5;">
          <strong>Starting your match:</strong><br>
          1. Make sure your replay is loaded and playing in <strong>GeForce NOW</strong>.<br>
          2. Click <strong>Launch Camera Director</strong> above, or double-click <strong>Start_Review.command</strong> inside your downloaded helper folder.<br>
          3. The camera director will automatically find this review job and begin recording!
        </p>
      </div>

      <!-- Live Progress Bar -->
      <div class="progress-shell">
        <div class="progress-bar" id="liveProgressBar" style="width: 10%;"></div>
      </div>
      <div class="progress-meta">
        <span id="liveProgressStage">Initializing helper connection…</span>
        <span id="liveProgressPct">10%</span>
      </div>

      <!-- Live Stages -->
      <h4 style="margin:1.1rem 0 0.4rem;font-size:1rem;">Director &amp; Coaching Pipeline Stages</h4>
      <ul class="stage-list" id="stageList">
        <li class="doing" data-stage="init">Job created: awaiting camera director launch</li>
        <li data-stage="gate">Game window detection</li>
        <li data-stage="roster">Scoreboard roster scanning and color match</li>
        <li data-stage="record">Autonomous camera recording (bases and battles)</li>
        <li data-stage="upload">Replay complete: video and parser metrics upload</li>
        <li data-stage="analysis">Coaching engine analysis and voice generation</li>
      </ul>

      <!-- Phone Monitoring Card -->
      <div class="phone-box">
        <span class="phone-icon">📱</span>
        <div class="phone-content">
          <h4>Monitor from Your Phone</h4>
          <p>Playing in fullscreen? Open the lightweight, auto-refreshing status page on your mobile device:</p>
          <p style="margin-top:0.35rem;"><a href="${phoneUrl}" target="_blank" rel="noopener"><strong>${window.location.origin}${phoneUrl}</strong> ↗</a></p>
        </div>
      </div>
    </div>
  `;

  const cancelBtn = $("cancelJobBtn");
  if (cancelBtn) {
    cancelBtn.onclick = async () => {
      if (activePollTimer) clearInterval(activePollTimer);
      try {
        sessionStorage.removeItem("aoe2_active_job");
      } catch (e) {}
      try {
        await api(`/api/jobs/${job.job_id}/cancel?token=${job.token}`, {});
      } catch (e) {}
      currentJob = null;
      $("jobBox").innerHTML = `
        <div class="callout-box" style="border-left:3px solid var(--gold);padding:1rem;background:rgba(212,175,55,0.08);">
          <p style="margin:0;font-size:0.95rem;color:var(--text);">
            Review job cancelled. You can configure and start a new review anytime.
          </p>
        </div>`;
      setTimeout(() => switchTab("launch"), 1000);
    };
  }
}

function restoreActiveJob() {
  try {
    const raw = sessionStorage.getItem("aoe2_active_job");
    if (raw) {
      const job = JSON.parse(raw);
      if (job && job.job_id && job.token) {
        currentJob = job;
        renderActiveJobBox(job);
        startPolling(job.job_id, job.token);
      }
    }
  } catch (e) {}
}

function startPolling(job_id, token) {
  if (activePollTimer) clearInterval(activePollTimer);

  const poll = async () => {
    const { status, data } = await api(`/api/jobs/${job_id}/status?token=${token}`);
    if (status !== 200) {
      if (status === 403 || status === 404) {
        clearInterval(activePollTimer);
        activePollTimer = null;
      }
      return;
    }

    updateJobProgressUI(data);

    if (data.status === "done") {
      clearInterval(activePollTimer);
      activePollTimer = null;
      try {
        sessionStorage.removeItem("aoe2_active_job");
      } catch (e) {}

      // Refresh review list and automatically render this finished review
      await loadReviews();
      const reviewResp = await api(`/api/reviews/${job_id}`);
      if (reviewResp.status === 200 && reviewResp.data && reviewResp.data.review) {
        renderReview(reviewResp.data.review);
        $("reviewDetail").scrollIntoView({ behavior: "smooth" });
      }
    }
  };

  // Immediate poll then 2-second interval
  poll();
  activePollTimer = setInterval(poll, 2000);
}

function updateJobProgressUI(data) {
  const bar = $("liveProgressBar");
  const pct = $("liveProgressPct");
  const stageEl = $("liveProgressStage");
  const badge = $("jobStatusBadge");
  const list = $("stageList");

  if (!bar || !pct || !stageEl || !badge) return;

  const status = data.status || "pending";
  badge.textContent = status.toUpperCase();

  const progressEvents = data.progress || [];
  const latest = progressEvents.length ? progressEvents[progressEvents.length - 1] : null;

  // Derive estimated percentage and active stage
  let percentage = 15;
  let activeStageKey = "init";
  let stageDescription = "Waiting for spectator helper to connect…";

  const stageKeys = progressEvents.map((p) => (p.stage || "").toLowerCase());

  if (status === "done") {
    percentage = 100;
    activeStageKey = "done";
    stageDescription = "Review generated and ready in Coaching Archives!";
  } else if (stageKeys.some((s) => s.includes("analyz") || s.includes("coaching") || s.includes("report"))) {
    percentage = 95;
    activeStageKey = "analysis";
    stageDescription = latest ? latest.detail || "Synthesizing tactical coaching analysis & clips…" : "Synthesizing coaching…";
  } else if (stageKeys.some((s) => s.includes("upload"))) {
    percentage = 85;
    activeStageKey = "upload";
    stageDescription = latest ? latest.detail || "Uploading match video & parser JSON…" : "Uploading video…";
  } else if (stageKeys.some((s) => s.includes("record") || s.includes("tour") || s.includes("director"))) {
    percentage = 65;
    activeStageKey = "record";
    stageDescription = latest ? latest.detail || "Camera director recording active gameplay…" : "Recording replay…";
  } else if (stageKeys.some((s) => s.includes("roster") || s.includes("scoreboard"))) {
    percentage = 45;
    activeStageKey = "roster";
    stageDescription = latest ? latest.detail || "Scoreboard inspected: focus team matched." : "Roster matched.";
  } else if (stageKeys.some((s) => s.includes("gate") || s.includes("window") || s.includes("found"))) {
    percentage = 30;
    activeStageKey = "gate";
    stageDescription = latest ? latest.detail || "Game window detected: spectator setup underway." : "Window detected.";
  }

  bar.style.width = `${percentage}%`;
  pct.textContent = `${percentage}%`;
  stageEl.textContent = stageDescription;

  // Update stage list items
  if (list) {
    const items = list.querySelectorAll("li");
    const order = ["init", "gate", "roster", "record", "upload", "analysis"];
    const currentIdx = order.indexOf(activeStageKey);

    items.forEach((li, idx) => {
      const key = li.dataset.stage;
      const liIdx = order.indexOf(key);

      if (status === "done") {
        li.className = "done";
      } else if (liIdx < currentIdx) {
        li.className = "done";
      } else if (liIdx === currentIdx) {
        li.className = "doing";
        if (latest && latest.detail) {
          let detailSpan = li.querySelector(".stage-detail");
          if (!detailSpan) {
            detailSpan = document.createElement("span");
            detailSpan.className = "stage-detail";
            li.appendChild(detailSpan);
          }
          detailSpan.textContent = `${latest.detail} (${latest.created_at || ""})`;
        }
      } else {
        li.className = "";
      }
    });
  }
}

// ==========================================================================
// Saved Reviews & Detailed Tactical Coaching Presentation
// ==========================================================================

async function loadReviews() {
  if (!me) {
    const list = $("reviewList");
    if (list) list.innerHTML = "";
    return;
  }
  const { status, data } = await api("/api/reviews");
  const reviews = data.reviews || [];
  const list = $("reviewList");
  if (!list) return;

  if (reviews.length === 0) {
    list.innerHTML = `<li class="note" style="padding:1rem 0;">No coaching reviews saved yet. Run your first review above!</li>`;
    return;
  }

  list.innerHTML = reviews.map((r) => `
    <li class="review-item" data-id="${esc(r.id)}">
      <div class="r-main">
        <div class="r-title">${esc(r.title)}</div>
        <div class="r-sub">Reviewed on ${esc(r.created_at)} · Job: ${esc(r.job_id || r.id)}</div>
      </div>
      <button type="button" class="btn" style="padding:0.45rem 0.9rem;font-size:0.9rem;">Read Coaching Report</button>
    </li>
  `).join("");

  list.querySelectorAll(".review-item").forEach((el) => {
    el.onclick = async () => {
      const rid = el.dataset.id;
      const { status, data: d } = await api(`/api/reviews/${rid}`);
      if (status === 200 && d.review) {
        renderReview(d.review);
        $("reviewDetail").scrollIntoView({ behavior: "smooth" });
      } else {
        alert("Could not load review details.");
      }
    };
  });
}

function renderReview(v) {
  const container = $("reviewDetail");
  if (!container) return;

  const isDraft = v.draft_only;
  const camera = v.camera || {};
  const hasParser = !!v.parser;
  const audioEndpoint = `/api/reviews/${esc(v.id)}/audio`;

  // Key-value metadata tiles
  const durationText = fmtDur(v.duration_s);
  const platformText = (v.platform || "geforce").toUpperCase();
  const playerText = esc(v.in_game_name || "Ken Grabshaw");
  const replayChoice = esc(v.replay_choice || "newest");

  // Camera verification banner
  let cameraBanner = "";
  if (camera.verified) {
    cameraBanner = `
      <div class="camera-badge-card verified">
        <span class="camera-icon">🛡</span>
        <div>
          <strong>Minimap Camera Director Verified</strong>
          <p style="margin:0.15rem 0 0;font-size:0.9rem;">Autonomous minimap director tracked active bases and verified <strong>${camera.fight_windows || 0} combat windows</strong>. Zero void views.</p>
        </div>
      </div>`;
  } else if (camera.directed) {
    cameraBanner = `
      <div class="camera-badge-card verified">
        <span class="camera-icon">🛡</span>
        <div>
          <strong>Minimap Camera Director Active</strong>
          <p style="margin:0.15rem 0 0;font-size:0.9rem;">Minimap director operated during capture with ${camera.fight_windows || 0} fight priorities.</p>
        </div>
      </div>`;
  } else {
    cameraBanner = `
      <div class="camera-badge-card fallback">
        <span class="camera-icon">⚠</span>
        <div>
          <strong>Fixed Tour / Unverified Camera Fallback</strong>
          <p style="margin:0.15rem 0 0;font-size:0.9rem;">Camera recorded on periodic quadrant sweep. Full-map fight tracking was unverified.</p>
        </div>
      </div>`;
  }

  // 10-minute phases
  const phasesHtml = (v.phases || []).map((p) => {
    const pName = esc(p.phase || "Game Phase");
    const pWhen = `${fmtDur(p.start_s)} to ${fmtDur(p.end_s)}`;
    const pFocus = esc(p.focus || "Strategic focus and military positioning.");
    return `
      <div class="phase-card">
        <div class="phase-header">
          <h4 class="phase-title">${pName}</h4>
          <span class="phase-when">${pWhen}</span>
        </div>
        <p class="phase-focus">${pFocus}</p>
      </div>`;
  }).join("");

  // Coaching tips & actionable drills
  const tipsHtml = (v.tips || []).map((t) => {
    const category = esc(t.phase || t.kind || "Tactics");
    const tipText = esc(t.tip || "");
    const drillText = esc(t.drill || "Practice standard build order execution.");
    const evidenceText = esc(t.evidence || "Observed from camera feed");
    const isParser = t.kind === "parser-backed" || evidenceText.toLowerCase().includes("parser");

    return `
      <div class="tip-card">
        <div class="tip-header">
          <span class="tip-player">${playerText}</span>
          <span class="tag ${isParser ? 'ready' : ''}">${category}</span>
        </div>
        <p class="tip-text">${tipText}</p>
        <div class="drill-box">
          <div class="drill-title">Recommended Practice Drill</div>
          <p class="drill-action">${drillText}</p>
        </div>
        <div class="tip-evidence">Evidence: ${evidenceText} ${isParser ? "(Parser Estimate)" : "(Observed Visual)"}</div>
      </div>`;
  }).join("");

  // Featured 10-30s Normal-Speed Video Clips
  const clips = v.clips || [];
  let clipsHtml = "";
  if (clips.length > 0) {
    clipsHtml = `
      <h3 style="margin-top:1.8rem;">Featured Combat Clips (10-30s Normal Speed)</h3>
      <p class="note">Clipped directly from battle windows identified by the camera director. Captured at 1.0x Normal playback speed without distortion.</p>
      <div class="clips-grid">
        ${clips.map((c) => `
          <figure class="clip-card">
            <div class="clip-badge-bar">
              <span>Normal Speed (1.0x)</span>
              <span>${c.duration_s || 15}s</span>
            </div>
            <video controls preload="metadata" src="/api/clips/${esc(c.file)}"></video>
            <figcaption>
              <strong>${esc(c.caption)}</strong>
              ${c.reason ? `<p class="clip-reason">Triggered by: ${esc(c.reason)}</p>` : ""}
            </figcaption>
          </figure>
        `).join("")}
      </div>`;
  } else {
    clipsHtml = `
      <h3 style="margin-top:1.8rem;">Combat Video Clips</h3>
      <p class="note">No micro clips generated for this session (${isDraft ? "draft review: full video processing required" : "fastest-speed mode suppresses micro-clips"}).</p>`;
  }

  // Supporting Parser Summary (if present)
  let parserStatsHtml = "";
  if (hasParser && v.parser) {
    const p = v.parser;
    parserStatsHtml = `
      <div class="callout-box parser-estimate" style="margin-top:1.5rem;">
        <div class="callout-header">📊 Supporting Parser Summary · Build ${esc(p.game_build || "188329")}</div>
        <p class="callout-body">
          Parser: <code>${esc(p.parser || "mgz-fast")}</code> · 
          Summed Unit Counters: ${esc(JSON.stringify(p.unit_counters_amount_summed || {}))}
        </p>
      </div>`;
  }

  // Render Full Report DOM
  const chronicleUrl = v.id === "sample-arabia-3v3" ? "/api/sample-review/chronicle" : `/api/reviews/${esc(v.id)}/chronicle`;
  container.innerHTML = `
    <div class="review-header-card">
      <div class="review-header-top">
        <h3 class="review-title">${esc(v.title || "Game Review")}</h3>
        <div style="display:flex;gap:0.6rem;align-items:center;flex-wrap:wrap;">
          <a class="btn gold-btn small" href="${chronicleUrl}" target="_blank">Export Match Chronicle</a>
          <span class="tag ${isDraft ? 'draft' : 'ready'}">${isDraft ? 'Draft Review' : 'Full Video Review'}</span>
        </div>
      </div>
      <p class="note" style="margin-bottom:0.8rem;">Review ID: <code>${esc(v.id)}</code> · Player: <strong>${playerText}</strong></p>

      <!-- Key Value Tiles -->
      <div class="kv-grid">
        <div class="kv-tile"><b>Game Duration</b><span>${durationText}</span></div>
        <div class="kv-tile"><b>Platform</b><span>${platformText}</span></div>
        <div class="kv-tile"><b>Focus Player</b><span>${playerText}</span></div>
        <div class="kv-tile"><b>Replay</b><span>${replayChoice}</span></div>
      </div>

      <!-- Camera Banner -->
      ${cameraBanner}

      <!-- Spoken Tactical Audio Report -->
      <div class="audio-card">
        <h3><span>🎙</span> Spoken Tactical Coaching Report</h3>
        <p>Full spoken audio breakdown voiced with expert tactical tips and specific drills for ${playerText} and teammates.</p>
        <audio controls preload="metadata" src="${audioEndpoint}"></audio>
      </div>

      <!-- Strict Integrity Distinction: Parser Estimates vs Visual Observed -->
      <div class="callout-box parser-estimate">
        <div class="callout-header">⚖ Integrity Mandate: Parser Estimates vs Observed Visual Evidence</div>
        <p class="callout-body">
          <strong>Estimates (Parser):</strong> All kill estimates, villager counts alive, stockpiles, and queue numbers from <code>.aoe2record</code> are estimates (click times only; queue amounts summed per Ken's rule).<br>
          <strong>Observed (Visual):</strong> Frontline fights, unit positioning, idle town centers, and base collapses are confirmed by the camera director watching the rendered video.
        </p>
      </div>

      ${parserStatsHtml}

      <!-- 10-Minute Phases -->
      <h3 style="margin-top:1.8rem;">Phase-by-Phase Tactical Breakdown</h3>
      <p class="note">The game analyzed in 10-minute strategic brackets (Opening, Feudal/Castle, Imperial, and Endgame).</p>
      <div class="phase-container">
        ${phasesHtml || "<p class='note'>No phase breakdown available.</p>"}
      </div>

      <!-- Coaching Tips -->
      <h3 style="margin-top:1.8rem;">Strategic Advice &amp; Practice Drills</h3>
      <p class="note">Personalized mechanical and strategic guidance based on directly observed play habits.</p>
      <div class="tips-grid">
        ${tipsHtml || "<p class='note'>No tips recorded for this review.</p>"}
      </div>

      <!-- Video Clips -->
      ${clipsHtml}

      <!-- Feedback Section -->
      <div class="feedback-box">
        <div class="feedback-text">
          <strong>Help the Coach Learn:</strong> Did these tactical tips and drills help reinforce habits for your next game?
        </div>
        <div class="row">
          <button type="button" class="btn green" onclick="window.feedback('${esc(v.id)}', 'drill-helped')">Drill Helped</button>
          <button type="button" class="btn ghost" onclick="window.feedback('${esc(v.id)}', 'report-was-wrong')">🛡 Report Was Inaccurate</button>
        </div>
      </div>
    </div>
  `;
}

// Learning Loop Feedback Handler
window.feedback = async (id, kind) => {
  const { status, data } = await api(`/api/reviews/${id}/feedback`, { kind });
  if (status === 200) {
    alert("Thank you! Your feedback has been recorded and feeds the cross-game habit learning loop.");
  } else {
    alert(data.error || "Could not record feedback.");
  }
};

// ==========================================================================
// Showcase Carousel & Sample Review Loader
// ==========================================================================

let currentSlideIdx = 0;
const slides = document.querySelectorAll(".carousel-slide");
const dots = document.querySelectorAll(".c-dot");

function showSlide(idx) {
  if (!slides.length) return;
  currentSlideIdx = (idx + slides.length) % slides.length;
  slides.forEach((s, i) => s.classList.toggle("active", i === currentSlideIdx));
  dots.forEach((d, i) => d.classList.toggle("active", i === currentSlideIdx));
}

const cPrevBtn = $("cPrevBtn");
const cNextBtn = $("cNextBtn");
if (cPrevBtn) cPrevBtn.onclick = () => showSlide(currentSlideIdx - 1);
if (cNextBtn) cNextBtn.onclick = () => showSlide(currentSlideIdx + 1);

dots.forEach((d) => {
  d.onclick = () => showSlide(parseInt(d.dataset.index, 10));
});

// Auto-advance carousel every 7 seconds
setInterval(() => {
  showSlide(currentSlideIdx + 1);
}, 7000);

async function loadSampleReview() {
  switchTab("archives");
  const { status, data } = await api("/api/sample-review");
  if (status === 200 && data.review) {
    renderReview(data.review);
    const detail = $("reviewDetail");
    if (detail) detail.scrollIntoView({ behavior: "smooth" });
  }
}

const loadSampleReviewBtn = $("loadSampleReviewBtn");
if (loadSampleReviewBtn) loadSampleReviewBtn.onclick = loadSampleReview;

const viewSampleHeroBtn = $("viewSampleHeroBtn");
if (viewSampleHeroBtn) viewSampleHeroBtn.onclick = loadSampleReview;

// ==========================================================================
// Archive Subtabs & Interactive Drills Checklist
// ==========================================================================

const archiveTabReviews = $("archiveTabReviews");
const archiveTabHabits = $("archiveTabHabits");
const reviewsSubView = $("reviewsSubView");
const habitsSubView = $("habitsSubView");

if (archiveTabReviews && archiveTabHabits) {
  archiveTabReviews.onclick = () => {
    archiveTabReviews.classList.add("active");
    archiveTabHabits.classList.remove("active");
    if (reviewsSubView) reviewsSubView.hidden = false;
    if (habitsSubView) habitsSubView.hidden = true;
  };
  archiveTabHabits.onclick = () => {
    archiveTabHabits.classList.add("active");
    archiveTabReviews.classList.remove("active");
    if (habitsSubView) habitsSubView.hidden = false;
    if (reviewsSubView) reviewsSubView.hidden = true;
  };
}

// Interactive Drills Checklist Persistence
const drillCheckboxes = document.querySelectorAll("#drillsChecklist input[type='checkbox']");
let savedDrills = {};
try {
  savedDrills = JSON.parse(localStorage.getItem("aoe2_completed_drills") || "{}");
} catch (e) {}

drillCheckboxes.forEach((cb) => {
  const id = cb.dataset.drillId;
  if (id && savedDrills[id]) {
    cb.checked = true;
  }
  cb.onchange = () => {
    savedDrills[id] = cb.checked;
    try {
      localStorage.setItem("aoe2_completed_drills", JSON.stringify(savedDrills));
    } catch (e) {}
  };
});

// Start application
refreshMe();
