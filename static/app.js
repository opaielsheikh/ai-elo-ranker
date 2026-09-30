// State management
let ws = null;
let soundEnabled = true;
let totalMatchesCounter = 0;
let tournamentStartTime = null;
let audioCtx = null;
let currentLeaderboardData = [];
let currentRatingMode = "elo";

// DOM Elements
const statusDot = document.getElementById("statusDot");
const statusText = document.getElementById("statusText");

const metricMatches = document.getElementById("metricMatches");
const metricRounds = document.getElementById("metricRounds");
const metricSpeed = document.getElementById("metricSpeed");
const metricLatency = document.getElementById("metricLatency");
const metricShift = document.getElementById("metricShift");
const metricModel = document.getElementById("metricModel");

// Controls Elements
const modeSelect = document.getElementById("modeSelect");
const cohortGroup = document.getElementById("cohortGroup");
const cohortSizeSelect = document.getElementById("cohortSizeSelect");
const judgeSelect = document.getElementById("judgeSelect");
const localModelRow = document.getElementById("localModelRow");
const inputLocalUrl = document.getElementById("inputLocalUrl");
const inputLocalModel = document.getElementById("inputLocalModel");

const inputApiKey = document.getElementById("inputApiKey");
const btnToggleKey = document.getElementById("btnToggleKey");
const keyStatusPill = document.getElementById("keyStatusPill");
const chkResetDb = document.getElementById("chkResetDb");

const datasetSelect = document.getElementById("datasetSelect");
const concurrencyRange = document.getElementById("concurrencyRange");
const concurrencyVal = document.getElementById("concurrencyVal");
const roundsRange = document.getElementById("roundsRange");
const roundsVal = document.getElementById("roundsVal");
const btnStart = document.getElementById("btnStart");
const btnStop = document.getElementById("btnStop");
const btnSound = document.getElementById("btnSound");

const arenaRoundBadge = document.getElementById("arenaRoundBadge");
const arenaMatchBadge = document.getElementById("arenaMatchBadge");
const duelStage = document.getElementById("duelStage");
const vsOrb = document.getElementById("vsOrb");
const vsLatency = document.getElementById("vsLatency");

const verdictBanner = document.getElementById("verdictBanner");
const verdictWinner = document.getElementById("verdictWinner");
const verdictReason = document.getElementById("verdictReason");

const feedList = document.getElementById("feedList");
const feedCounter = document.getElementById("feedCounter");
const leaderboardList = document.getElementById("leaderboardList");
const boardItemsCount = document.getElementById("boardItemsCount");
const boardSearchInput = document.getElementById("boardSearchInput");

// Mode & Judge Toggle Listeners
modeSelect.addEventListener("change", (e) => {
  currentRatingMode = e.target.value;
  if (currentRatingMode === "trueskill") {
    cohortGroup.style.display = "flex";
  } else {
    cohortGroup.style.display = "none";
  }
});

judgeSelect.addEventListener("change", (e) => {
  const jtype = e.target.value;
  if (jtype === "local" || jtype === "ensemble") {
    localModelRow.style.display = "flex";
  } else {
    localModelRow.style.display = "none";
  }
  updateKeyPillStatus();
});

// Sound synthesizer
function playCyberChirp(isWin = true) {
  if (!soundEnabled) return;
  try {
    if (!audioCtx) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioCtx.state === "suspended") {
      audioCtx.resume();
    }
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.connect(gain);
    gain.connect(audioCtx.destination);

    const now = audioCtx.currentTime;
    if (isWin) {
      osc.type = "sine";
      osc.frequency.setValueAtTime(587.33, now); // D5
      osc.frequency.exponentialRampToValueAtTime(880, now + 0.08); // A5
      gain.gain.setValueAtTime(0.08, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.12);
      osc.start(now);
      osc.stop(now + 0.12);
    } else {
      osc.type = "triangle";
      osc.frequency.setValueAtTime(440, now);
      osc.frequency.exponentialRampToValueAtTime(330, now + 0.08);
      gain.gain.setValueAtTime(0.05, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.1);
      osc.start(now);
      osc.stop(now + 0.1);
    }
  } catch (e) {
    // Ignore audio context issues
  }
}

// Sliders listener
concurrencyRange.addEventListener("input", (e) => {
  concurrencyVal.textContent = e.target.value;
});

roundsRange.addEventListener("input", (e) => {
  roundsVal.textContent = e.target.value;
});

btnSound.addEventListener("click", () => {
  soundEnabled = !soundEnabled;
  btnSound.textContent = soundEnabled ? "🔊" : "🔇";
});

// API Key Storage and Visibility
function updateKeyPillStatus() {
  const keyVal = (inputApiKey ? inputApiKey.value.trim() : "");
  const jtype = judgeSelect.value;
  if (jtype === "mock") {
    keyStatusPill.textContent = "Offline Mode (No Key Needed)";
    keyStatusPill.style.color = "var(--green)";
    keyStatusPill.style.background = "rgba(16, 185, 129, 0.15)";
  } else if (jtype === "local") {
    keyStatusPill.textContent = "Local Server (No Key Needed)";
    keyStatusPill.style.color = "var(--cyan)";
    keyStatusPill.style.background = "rgba(0, 242, 254, 0.15)";
  } else if (keyVal.length > 5) {
    keyStatusPill.textContent = "Key Active";
    keyStatusPill.style.color = "var(--green)";
    keyStatusPill.style.background = "rgba(16, 185, 129, 0.15)";
  } else {
    keyStatusPill.textContent = "No Key Set";
    keyStatusPill.style.color = "var(--text-dim)";
    keyStatusPill.style.background = "rgba(255, 255, 255, 0.06)";
  }
}

if (inputApiKey) {
  const savedKey = localStorage.getItem("typesafe_api_key");
  if (savedKey) {
    inputApiKey.value = savedKey;
  }
  updateKeyPillStatus();

  inputApiKey.addEventListener("input", (e) => {
    const val = e.target.value.trim();
    if (val) {
      localStorage.setItem("typesafe_api_key", val);
    } else {
      localStorage.removeItem("typesafe_api_key");
    }
    updateKeyPillStatus();
  });
}

if (btnToggleKey) {
  btnToggleKey.addEventListener("click", () => {
    if (inputApiKey.type === "password") {
      inputApiKey.type = "text";
      btnToggleKey.textContent = "🔒";
    } else {
      inputApiKey.type = "password";
      btnToggleKey.textContent = "👁";
    }
  });
}

// Load available datasets
async function loadDatasets() {
  try {
    const res = await fetch("/api/datasets");
    const json = await res.json();
    if (json.datasets && json.datasets.length > 0) {
      datasetSelect.innerHTML = "";
      json.datasets.forEach((ds) => {
        const opt = document.createElement("option");
        opt.value = ds.filename;
        opt.textContent = `${ds.name} (${ds.count.toLocaleString()} items)`;
        datasetSelect.appendChild(opt);
      });
    }
  } catch (err) {
    console.error("Failed to load datasets:", err);
  }
}

// WebSocket Connection
function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    statusDot.className = "status-indicator";
    statusText.textContent = "Live Connected";
  };

  ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    handleServerEvent(message.type, message.data);
  };

  ws.onclose = () => {
    statusDot.className = "status-indicator";
    statusText.textContent = "Disconnected (Reconnecting...)";
    setTimeout(connectWebSocket, 2000);
  };
}

// Handle WebSocket Events
function handleServerEvent(type, data) {
  switch (type) {
    case "init":
      if (data.stats && data.stats.total_matches !== undefined) {
        totalMatchesCounter = data.stats.total_matches;
        metricMatches.textContent = totalMatchesCounter.toLocaleString();
        if (data.stats.avg_latency_ms) {
          metricLatency.innerHTML = `${Math.round(data.stats.avg_latency_ms)} <span class="metric-unit">ms</span>`;
        }
      }

      if (data.mode) {
        modeSelect.value = data.mode;
        currentRatingMode = data.mode;
        cohortGroup.style.display = data.mode === "trueskill" ? "flex" : "none";
      }

      if (data.recent_matches && data.recent_matches.length > 0) {
        feedList.innerHTML = "";
        data.recent_matches.forEach((m) => {
          const itemEl = document.createElement("div");
          itemEl.className = "feed-item";
          const isWinnerA = m.winner_id === m.item_a_id;
          const winnerTitle = isWinnerA ? m.item_a_title : m.item_b_title;
          const loserTitle = isWinnerA ? m.item_b_title : m.item_a_title;
          const winDelta = isWinnerA ? m.delta_a : m.delta_b;

          itemEl.innerHTML = `
            <div class="feed-left">
              <span class="feed-tag">#${m.id}</span>
              <span class="feed-winner">${winnerTitle || "Winner"}</span>
              <span style="color:var(--text-dim)">def.</span>
              <span style="color:var(--text-muted)">${loserTitle || "Opponent"}</span>
              <span class="feed-reason">"${m.reason || "Decisive victory"}"</span>
            </div>
            <div class="feed-right">
              <span style="color:var(--green)">+${Math.abs(winDelta || 0).toFixed(1)}</span>
              <span style="color:var(--text-dim)">|</span>
              <span>${Math.round(m.latency_ms || 0)}ms</span>
            </div>
          `;
          feedList.appendChild(itemEl);
        });
        feedCounter.textContent = `${totalMatchesCounter.toLocaleString()} matches in history`;
      }

      if (data.leaderboard && data.leaderboard.length > 0) {
        renderLeaderboard(data.leaderboard);
      }

      if (data.is_running) {
        setRunningState(true);
      }
      break;

    case "tournament_start":
      setRunningState(true);
      tournamentStartTime = performance.now();
      totalMatchesCounter = 0;
      feedList.innerHTML = "";
      metricMatches.textContent = "0";
      metricRounds.textContent = `Max Rounds: ${data.max_rounds}`;
      if (data.model) {
        metricModel.textContent = data.model;
      }
      if (data.rating_mode) {
        currentRatingMode = data.rating_mode;
      }
      if (data.initial_leaderboard) {
        renderLeaderboard(data.initial_leaderboard);
      }
      break;

    case "round_start":
      arenaRoundBadge.textContent = `ROUND ${data.round_num}`;
      metricRounds.textContent = `Round ${data.round_num} of ${data.max_rounds}`;
      break;

    case "cohort_match_complete":
    case "match_complete":
      totalMatchesCounter++;
      metricMatches.textContent = totalMatchesCounter;
      metricLatency.innerHTML = `${Math.round(data.latency_ms || 0)} <span class="metric-unit">ms</span>`;
      
      if (tournamentStartTime) {
        const elapsedSec = (performance.now() - tournamentStartTime) / 1000;
        if (elapsedSec > 0) {
          const speed = (totalMatchesCounter / elapsedSec).toFixed(1);
          metricSpeed.innerHTML = `${speed} <span class="metric-unit">m/s</span>`;
        }
      }

      if (data.rating_mode === "trueskill" && data.candidates && data.candidates.length > 2) {
        renderCohortArena(data);
      } else {
        renderDuel(data);
      }
      appendFeedItem(data);

      if (data.current_leaderboard) {
        renderLeaderboard(data.current_leaderboard);
      }
      playCyberChirp(true);
      break;

    case "round_complete":
      metricShift.textContent = `${data.avg_shift.toFixed(2)}`;
      if (data.leaderboard) {
        renderLeaderboard(data.leaderboard);
      }
      break;

    case "tournament_complete":
      setRunningState(false);
      statusText.textContent = "Tournament Complete 🏆";
      metricMatches.textContent = data.total_matches;
      metricSpeed.innerHTML = `${data.matches_per_sec} <span class="metric-unit">m/s</span>`;
      metricLatency.innerHTML = `${Math.round(data.avg_latency_ms)} <span class="metric-unit">ms</span>`;
      if (data.final_leaderboard) {
        renderLeaderboard(data.final_leaderboard);
      }
      break;

    case "tournament_stopped":
      setRunningState(false);
      statusText.textContent = data.reason || "Stopped by user";
      break;

    case "tournament_error":
      setRunningState(false);
      statusText.textContent = "Error: " + (data.error || "Tournament failed");
      alert("⚠️ Tournament Error:\n\n" + (data.error || "Tournament failed"));
      break;

  }
}

// Render Classic 1v1 Pairwise Duel Arena
function renderDuel(data) {
  duelStage.className = "duel-stage";
  const itemA = data.item_a || {};
  const itemB = data.item_b || {};
  const isWinnerA = data.winner_id === itemA.id;

  arenaMatchBadge.textContent = `MATCH #${data.match_idx}`;

  const deltaStrA = (itemA.delta !== undefined && itemA.delta >= 0) ? `+${itemA.delta.toFixed(1)}` : `${(itemA.delta || 0).toFixed(1)}`;
  const deltaStrB = (itemB.delta !== undefined && itemB.delta >= 0) ? `+${itemB.delta.toFixed(1)}` : `${(itemB.delta || 0).toFixed(1)}`;

  duelStage.innerHTML = `
    <!-- Candidate A -->
    <div class="candidate-card ${isWinnerA ? 'winner' : 'loser'}" id="cardA">
      <div class="candidate-header">
        <span class="cand-tag">CANDIDATE A</span>
        <span class="cand-elo">${(itemA.elo_after || itemA.scaled_rating || 1200).toFixed(1)}</span>
      </div>
      <h3 class="cand-title">${itemA.title || 'Item A'}</h3>
      <p class="cand-content">${itemA.content || ''}</p>
      <div class="delta-bubble ${itemA.delta >= 0 ? 'show-pos' : 'show-neg'}">${deltaStrA}</div>
    </div>

    <!-- VS Badge & Latency -->
    <div class="vs-container">
      <div class="vs-orb pulsing" id="vsOrb">VS</div>
      <div class="vs-latency" id="vsLatency">${Math.round(data.latency_ms || 0)} ms</div>
    </div>

    <!-- Candidate B -->
    <div class="candidate-card ${!isWinnerA ? 'winner' : 'loser'}" id="cardB">
      <div class="candidate-header">
        <span class="cand-tag">CANDIDATE B</span>
        <span class="cand-elo">${(itemB.elo_after || itemB.scaled_rating || 1200).toFixed(1)}</span>
      </div>
      <h3 class="cand-title">${itemB.title || 'Item B'}</h3>
      <p class="cand-content">${itemB.content || ''}</p>
      <div class="delta-bubble ${itemB.delta >= 0 ? 'show-pos' : 'show-neg'}">${deltaStrB}</div>
    </div>
  `;

  verdictWinner.textContent = `Winner: ${data.winner_title}`;
  verdictReason.textContent = `[${data.model_name || 'Judge'}] Rationale: "${data.reason}"`;
}

// Render Multi-Candidate Cohort Arena (TrueSkill / OpenSkill)
function renderCohortArena(data) {
  duelStage.className = "duel-stage multi-stage";
  arenaMatchBadge.textContent = `COHORT #${data.match_idx} (${data.cohort_size} PLAYERS)`;

  const cardsHtml = data.candidates.map((cand) => {
    const isWinner = cand.rank === 1;
    const rankClass = cand.rank === 1 ? "rank-1" : cand.rank === 2 ? "rank-2" : cand.rank === 3 ? "rank-3" : "rank-other";
    const rankLabel = cand.rank === 1 ? "🥇 1ST PLACE" : cand.rank === 2 ? "🥈 2ND PLACE" : cand.rank === 3 ? "🥉 3RD PLACE" : `#${cand.rank} PLACE`;
    const deltaStr = cand.delta_mu >= 0 ? `+${cand.delta_mu.toFixed(2)}` : `${cand.delta_mu.toFixed(2)}`;

    return `
      <div class="candidate-card ${isWinner ? 'winner' : 'loser'}">
        <div class="candidate-header">
          <span class="rank-badge ${rankClass}">${rankLabel}</span>
          <div>
            <span class="cand-elo">${cand.scaled_rating.toFixed(1)}</span>
            <span class="cand-sigma">μ:${cand.new_mu.toFixed(1)} (±${cand.new_sigma.toFixed(1)})</span>
          </div>
        </div>
        <h3 class="cand-title">${cand.title}</h3>
        <p class="cand-content">${cand.content}</p>
        <div class="delta-bubble ${cand.delta_mu >= 0 ? 'show-pos' : 'show-neg'}">${deltaStr} μ</div>
      </div>
    `;
  }).join("");

  duelStage.innerHTML = cardsHtml;

  verdictWinner.textContent = `Cohort Champion: ${data.winner_title}`;
  verdictReason.textContent = `[${data.model_name || 'TrueSkill Judge'}] Rationale: "${data.reason}"`;
}

// Append item to live feed ticker
function appendFeedItem(data) {
  const itemEl = document.createElement("div");
  itemEl.className = "feed-item";

  if (data.rating_mode === "trueskill" && data.candidates && data.candidates.length > 2) {
    const winner = data.candidates[0] || {};
    const runnersUp = data.candidates.slice(1).map(c => c.title).join(", ");
    itemEl.innerHTML = `
      <div class="feed-left">
        <span class="feed-tag">#${data.match_idx}</span>
        <span class="feed-winner">${winner.title}</span>
        <span style="color:var(--text-dim)">placed 1st vs</span>
        <span style="color:var(--text-muted)">${runnersUp}</span>
        <span class="feed-reason">"${data.reason}"</span>
      </div>
      <div class="feed-right">
        <span style="color:var(--green)">+${Math.abs(winner.delta_mu || 0).toFixed(2)} μ</span>
        <span style="color:var(--text-dim)">|</span>
        <span>${Math.round(data.latency_ms || 0)}ms</span>
      </div>
    `;
  } else {
    const isWinnerA = data.winner_id === data.item_a.id;
    const winner = isWinnerA ? data.item_a : data.item_b;
    const loser = isWinnerA ? data.item_b : data.item_a;
    itemEl.innerHTML = `
      <div class="feed-left">
        <span class="feed-tag">#${data.match_idx}</span>
        <span class="feed-winner">${winner.title || "Winner"}</span>
        <span style="color:var(--text-dim)">def.</span>
        <span style="color:var(--text-muted)">${loser.title || "Opponent"}</span>
        <span class="feed-reason">"${data.reason}"</span>
      </div>
      <div class="feed-right">
        <span style="color:var(--green)">+${Math.abs(winner.delta || 0).toFixed(1)}</span>
        <span style="color:var(--text-dim)">|</span>
        <span>${Math.round(data.latency_ms || 0)}ms</span>
      </div>
    `;
  }

  feedList.insertBefore(itemEl, feedList.firstChild);

  while (feedList.children.length > 35) {
    feedList.removeChild(feedList.lastChild);
  }

  feedCounter.textContent = `${totalMatchesCounter} matches resolved`;
}

// Render the definitive leaderboard with search filter support
function renderLeaderboard(items) {
  if (items && items.length > 0) {
    currentLeaderboardData = items;
  }
  const pool = currentLeaderboardData || [];
  if (pool.length === 0) return;

  const query = boardSearchInput ? boardSearchInput.value.toLowerCase().trim() : "";
  let filtered = pool;
  if (query) {
    filtered = pool.filter((item) => {
      const title = (item.title || "").toLowerCase();
      let author = "";
      try {
        if (typeof item.metadata === "string") {
          const meta = JSON.parse(item.metadata);
          author = (meta.author || "").toLowerCase();
        } else if (item.metadata) {
          author = (item.metadata.author || "").toLowerCase();
        }
      } catch (e) {}
      return title.includes(query) || author.includes(query);
    });
    boardItemsCount.textContent = `${filtered.length} of ${pool.length.toLocaleString()} found`;
  } else {
    boardItemsCount.textContent = `${pool.length.toLocaleString()} Items`;
  }

  leaderboardList.innerHTML = "";

  if (filtered.length === 0) {
    leaderboardList.innerHTML = `<div class="feed-empty">No items matching "${query}"</div>`;
    return;
  }

  const maxElo = pool[0].elo || 1200;
  const minElo = pool[pool.length - 1].elo || 1000;
  const spread = Math.max(1, maxElo - minElo);

  filtered.slice(0, 100).forEach((item) => {
    const globalRank = pool.findIndex((p) => p.id === item.id) + 1;
    const rankLabel = globalRank === 1 ? "🥇" : globalRank === 2 ? "🥈" : globalRank === 3 ? "🥉" : `#${globalRank}`;
    const rankClass = globalRank === 1 ? "rank-1" : globalRank === 2 ? "rank-2" : globalRank === 3 ? "rank-3" : "";
    const percent = Math.max(8, Math.min(100, ((item.elo - minElo) / spread) * 100));

    let authorStr = "";
    try {
      if (typeof item.metadata === "string") {
        const meta = JSON.parse(item.metadata);
        if (meta.author) authorStr = ` • ${meta.author}`;
      } else if (item.metadata && item.metadata.author) {
        authorStr = ` • ${item.metadata.author}`;
      }
    } catch (e) {}

    const bayesianStr = item.mu !== undefined && item.sigma !== undefined
      ? `<span class="cand-sigma" title="Bayesian Skill μ ± Uncertainty σ">μ:${item.mu.toFixed(1)} ±${item.sigma.toFixed(1)}</span>`
      : "";

    const row = document.createElement("div");
    row.className = `board-row ${rankClass}`;
    row.innerHTML = `
      <div class="row-rank">${rankLabel}</div>
      <div class="row-info">
        <div class="row-title" title="${item.title}">${item.title}</div>
        <div class="row-sub">${item.wins}W - ${item.losses}L (${item.matches_count}M)${authorStr} ${bayesianStr}</div>
        <div class="row-bar-wrap">
          <div class="row-bar" style="width: ${percent}%"></div>
        </div>
      </div>
      <div class="row-stats">
        <div class="row-elo">${item.elo.toFixed(1)}</div>
      </div>
    `;
    leaderboardList.appendChild(row);
  });
}

if (boardSearchInput) {
  boardSearchInput.addEventListener("input", () => renderLeaderboard());
}

function setRunningState(running) {
  if (running) {
    statusDot.className = "status-indicator running";
    statusText.textContent = "Tournament Live Streaming";
    btnStart.disabled = true;
    btnStart.style.display = "none";
    btnStop.style.display = "inline-flex";
  } else {
    statusDot.className = "status-indicator";
    btnStart.disabled = false;
    btnStart.style.display = "inline-flex";
    btnStop.style.display = "none";
    btnStart.innerHTML = `<span class="btn-icon">⚡</span> START TOURNAMENT`;
  }
}

// Start tournament button action
btnStart.addEventListener("click", async () => {
  try {
    const keyVal = inputApiKey ? inputApiKey.value.trim() : "";
    const resetDbVal = chkResetDb ? chkResetDb.checked : false;

    const payload = {
      dataset: datasetSelect.value,
      mode: modeSelect.value,
      cohort_size: parseInt(cohortSizeSelect.value),
      judge_type: judgeSelect.value,
      local_url: inputLocalUrl ? inputLocalUrl.value.trim() : "http://localhost:11434/v1",
      local_model: inputLocalModel ? inputLocalModel.value.trim() : "qwen2.5:7b",
      concurrency: parseInt(concurrencyRange.value),
      rounds: parseInt(roundsRange.value),
      threshold: 0.4,
      reset_db: resetDbVal,
      api_key: keyVal || undefined
    };

    const res = await fetch("/api/tournament/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!res.ok) {
      const err = await res.json();
      if (err.error && err.error.toLowerCase().includes("key")) {
        if (inputApiKey) {
          inputApiKey.focus();
          inputApiKey.style.borderColor = "var(--red)";
        }
      }
      alert(`Tournament Error: ${err.error || "Could not start tournament"}`);
    }
  } catch (err) {
    console.error("Start failed:", err);
  }
});

// Stop tournament button action
btnStop.addEventListener("click", async () => {
  try {
    await fetch("/api/tournament/stop", { method: "POST" });
    setRunningState(false);
  } catch (err) {
    console.error("Stop failed:", err);
  }
});

// Initialization
loadDatasets();
connectWebSocket();
