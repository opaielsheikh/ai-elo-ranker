// State management
let ws = null;
let soundEnabled = true;
let totalMatchesCounter = 0;
let tournamentStartTime = null;
let audioCtx = null;

// DOM Elements
const statusDot = document.getElementById("statusDot");
const statusText = document.getElementById("statusText");

const metricMatches = document.getElementById("metricMatches");
const metricRounds = document.getElementById("metricRounds");
const metricSpeed = document.getElementById("metricSpeed");
const metricLatency = document.getElementById("metricLatency");
const metricShift = document.getElementById("metricShift");

// BYOK Elements
const inputApiKey = document.getElementById("inputApiKey");
const btnToggleKey = document.getElementById("btnToggleKey");
const chkResetDb = document.getElementById("chkResetDb");

const datasetSelect = document.getElementById("datasetSelect");
const concurrencyRange = document.getElementById("concurrencyRange");
const concurrencyVal = document.getElementById("concurrencyVal");
const roundsRange = document.getElementById("roundsRange");
const roundsVal = document.getElementById("roundsVal");
const btnStart = document.getElementById("btnStart");
const btnSound = document.getElementById("btnSound");

const arenaRoundBadge = document.getElementById("arenaRoundBadge");
const arenaMatchBadge = document.getElementById("arenaMatchBadge");
const vsOrb = document.getElementById("vsOrb");
const vsLatency = document.getElementById("vsLatency");

const cardA = document.getElementById("cardA");
const cardATitle = document.getElementById("cardATitle");
const cardAElo = document.getElementById("cardAElo");
const cardAContent = document.getElementById("cardAContent");
const cardADelta = document.getElementById("cardADelta");

const cardB = document.getElementById("cardB");
const cardBTitle = document.getElementById("cardBTitle");
const cardBElo = document.getElementById("cardBElo");
const cardBContent = document.getElementById("cardBContent");
const cardBDelta = document.getElementById("cardBDelta");

const verdictWinner = document.getElementById("verdictWinner");
const verdictReason = document.getElementById("verdictReason");

const feedList = document.getElementById("feedList");
const feedCounter = document.getElementById("feedCounter");
const leaderboardList = document.getElementById("leaderboardList");
const boardItemsCount = document.getElementById("boardItemsCount");

// Web Audio API Sound FX
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
    // Ignore audio context errors
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

// BYOK Key Management
if (inputApiKey) {
  const savedKey = localStorage.getItem("jev_api_key") || "";
  inputApiKey.value = savedKey;

  inputApiKey.addEventListener("input", (e) => {
    localStorage.setItem("jev_api_key", e.target.value.trim());
    inputApiKey.style.borderColor = "";
  });
}

if (btnToggleKey && inputApiKey) {
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
      // Populate past statistics and history immediately
      if (data.stats && data.stats.total_matches !== undefined) {
        totalMatchesCounter = data.stats.total_matches;
        metricMatches.textContent = totalMatchesCounter.toLocaleString();
        if (data.stats.avg_latency_ms) {
          metricLatency.innerHTML = `${Math.round(data.stats.avg_latency_ms)} <span class="metric-unit">ms</span>`;
        }
      }

      // Populate past match history
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

      // Populate historical leaderboard
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
      if (data.initial_leaderboard) {
        renderLeaderboard(data.initial_leaderboard);
      }
      break;

    case "round_start":
      arenaRoundBadge.textContent = `ROUND ${data.round_num}`;
      metricRounds.textContent = `Round ${data.round_num} of ${data.max_rounds}`;
      break;

    case "match_complete":
      totalMatchesCounter++;
      metricMatches.textContent = totalMatchesCounter;
      metricLatency.innerHTML = `${Math.round(data.latency_ms)} <span class="metric-unit">ms</span>`;
      
      // Calculate speed
      if (tournamentStartTime) {
        const elapsedSec = (performance.now() - tournamentStartTime) / 1000;
        if (elapsedSec > 0) {
          const speed = (totalMatchesCounter / elapsedSec).toFixed(1);
          metricSpeed.innerHTML = `${speed} <span class="metric-unit">m/s</span>`;
        }
      }

      renderDuel(data);
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
    case "tournament_error":
      setRunningState(false);
      statusText.textContent = data.error || "Stopped";
      break;
  }
}

// Render active duel
function renderDuel(data) {
  const itemA = data.item_a;
  const itemB = data.item_b;
  const isWinnerA = data.winner_id === itemA.id;

  arenaMatchBadge.textContent = `MATCH #${data.match_idx}`;
  vsLatency.textContent = `${Math.round(data.latency_ms)} ms`;

  // Candidate A
  cardATitle.textContent = itemA.title;
  cardAElo.textContent = itemA.elo_after.toFixed(1);
  cardAContent.textContent = itemA.content;

  // Candidate B
  cardBTitle.textContent = itemB.title;
  cardBElo.textContent = itemB.elo_after.toFixed(1);
  cardBContent.textContent = itemB.content;

  // Visual winner highlight
  cardA.className = `candidate-card ${isWinnerA ? "winner" : "loser"}`;
  cardB.className = `candidate-card ${!isWinnerA ? "winner" : "loser"}`;

  // Delta bubbles
  cardADelta.textContent = itemA.delta >= 0 ? `+${itemA.delta.toFixed(1)}` : `${itemA.delta.toFixed(1)}`;
  cardADelta.className = `delta-bubble ${itemA.delta >= 0 ? "show-pos" : "show-neg"}`;

  cardBDelta.textContent = itemB.delta >= 0 ? `+${itemB.delta.toFixed(1)}` : `${itemB.delta.toFixed(1)}`;
  cardBDelta.className = `delta-bubble ${itemB.delta >= 0 ? "show-pos" : "show-neg"}`;

  // Pulse VS orb
  vsOrb.classList.add("pulsing");
  setTimeout(() => vsOrb.classList.remove("pulsing"), 400);

  // Verdict banner
  verdictWinner.textContent = `Winner: ${data.winner_title}`;
  verdictReason.textContent = `Rationale: "${data.reason}"`;
}

// Append item to live feed ticker
function appendFeedItem(data) {
  const isWinnerA = data.winner_id === data.item_a.id;
  const winner = isWinnerA ? data.item_a : data.item_b;
  const loser = isWinnerA ? data.item_b : data.item_a;

  const itemEl = document.createElement("div");
  itemEl.className = "feed-item";
  itemEl.innerHTML = `
    <div class="feed-left">
      <span class="feed-tag">#${data.match_idx}</span>
      <span class="feed-winner">${winner.title}</span>
      <span style="color:var(--text-dim)">def.</span>
      <span style="color:var(--text-muted)">${loser.title}</span>
      <span class="feed-reason">"${data.reason}"</span>
    </div>
    <div class="feed-right">
      <span style="color:var(--green)">+${winner.delta.toFixed(1)}</span>
      <span style="color:var(--text-dim)">|</span>
      <span>${Math.round(data.latency_ms)}ms</span>
    </div>
  `;

  feedList.insertBefore(itemEl, feedList.firstChild);

  // Keep list bounded to last 35 items
  while (feedList.children.length > 35) {
    feedList.removeChild(feedList.lastChild);
  }

  feedCounter.textContent = `${totalMatchesCounter} matches resolved`;
}

// Render the definitive leaderboard
function renderLeaderboard(items) {
  if (!items || items.length === 0) return;

  boardItemsCount.textContent = `${items.length} Items`;
  leaderboardList.innerHTML = "";

  const maxElo = items[0].elo || 1200;
  const minElo = items[items.length - 1].elo || 1000;
  const spread = Math.max(1, maxElo - minElo);

  items.forEach((item, index) => {
    const rank = index + 1;
    const rankClass = rank === 1 ? "rank-1" : rank === 2 ? "rank-2" : rank === 3 ? "rank-3" : "";
    const rankLabel = rank === 1 ? "🥇" : rank === 2 ? "🥈" : rank === 3 ? "🥉" : `#${rank}`;
    const percent = Math.max(8, Math.min(100, ((item.elo - minElo) / spread) * 100));

    const row = document.createElement("div");
    row.className = `board-row ${rankClass}`;
    row.innerHTML = `
      <div class="row-rank">${rankLabel}</div>
      <div class="row-info">
        <div class="row-title" title="${item.title}">${item.title}</div>
        <div class="row-bar-wrap">
          <div class="row-bar" style="width: ${percent}%"></div>
        </div>
      </div>
      <div class="row-stats">
        <div class="row-elo">${item.elo.toFixed(1)}</div>
        <div class="row-record">${item.wins}W - ${item.losses}L (${item.matches_count}M)</div>
      </div>
    `;
    leaderboardList.appendChild(row);
  });
}

function setRunningState(running) {
  if (running) {
    statusDot.className = "status-indicator running";
    statusText.textContent = "Tournament Live Streaming";
    btnStart.disabled = true;
    btnStart.innerHTML = `<span class="btn-icon">⚡</span> BATTLING...`;
  } else {
    statusDot.className = "status-indicator";
    btnStart.disabled = false;
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

// Initialization
loadDatasets();
connectWebSocket();
