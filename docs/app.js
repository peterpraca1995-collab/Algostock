function fmt(n, d = 2) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return Number(n).toLocaleString("sk-SK", { minimumFractionDigits: d, maximumFractionDigits: d });
}

function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("sk-SK", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

function tickClock() {
  document.getElementById("clock").textContent = new Date().toLocaleString("sk-SK");
}
setInterval(tickClock, 1000);
tickClock();

async function loadAll() {
  let data;
  try {
    const res = await fetch(`data/status.json?_=${Date.now()}`);
    data = await res.json();
  } catch (e) {
    document.getElementById("account-bar").innerHTML =
      `<span style="color:var(--red)">Dáta sa ešte nenačítali (prvý beh appky príde do hodiny) alebo chyba: ${e}</span>`;
    return;
  }

  const acct = data.account || {};
  const bar = document.getElementById("account-bar");
  if (acct.error) {
    bar.innerHTML = `<span style="color:var(--red)">Chyba účtu: ${acct.error}</span>`;
  } else {
    bar.innerHTML = `
      <div><span class="label">Equity</span><b>$${fmt(acct.equity)}</b></div>
      <div><span class="label">Cash</span><b>$${fmt(acct.cash)}</b></div>
      <div><span class="label">Buying power</span><b>$${fmt(acct.buying_power)}</b></div>
      <div><span class="label">Účet</span><b>${acct.account_number || ""}</b></div>
      <div><span class="label">Dáta k</span><b>${fmtTime(data.generated_at)}</b></div>
    `;
  }

  const positionsBySymbol = {};
  (data.positions || []).forEach(p => positionsBySymbol[p.symbol] = p);

  const tbody = document.querySelector("#symbols-table tbody");
  tbody.innerHTML = "";
  (data.tickers || []).forEach(sym => {
    const t = (data.latest_ticks || {})[sym] || {};
    const pos = positionsBySymbol[sym];
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><b>${sym}</b></td>
      <td>${t.price ? "$" + fmt(t.price) : "—"}</td>
      <td>${fmt(t.ema_fast)}</td>
      <td>${fmt(t.ema_slow)}</td>
      <td>${fmt(t.rsi, 1)}</td>
      <td>${fmt(t.macd_hist, 3)}</td>
      <td>${fmt(t.cci, 0)}</td>
      <td>${fmt(t.adx, 1)}</td>
      <td><b>${t.score !== undefined && t.score !== null ? (t.score > 0 ? "+" : "") + t.score : "—"}</b></td>
      <td class="sig-${t.signal || 'HOLD'}">${t.signal || "—"}</td>
      <td class="act-${t.action || ''}">${t.action || "—"}</td>
      <td>${pos ? pos.qty + " ks @ $" + fmt(pos.avg_entry_price) : "—"}</td>
      <td>${pos ? "$" + fmt(pos.unrealized_pl) : "—"}</td>
    `;
    tbody.appendChild(tr);
  });

  document.getElementById("schedule-info").textContent =
    `Naposledy vyhodnotené: ${fmtTime(data.generated_at)} · beží každých 15 min cez GitHub Actions`;

  const rows = data.history || [];
  const logTbody = document.querySelector("#log-table tbody");
  logTbody.innerHTML = "";
  rows.forEach(r => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${fmtTime(r.ts)}</td>
      <td>${r.symbol}</td>
      <td class="sig-${r.signal}">${r.signal || "—"}</td>
      <td class="act-${r.action}">${r.action || "—"}</td>
      <td>${r.reason || ""}</td>
      <td>${r.notes || ""}</td>
    `;
    logTbody.appendChild(tr);
  });

  const points = data.equity || [];
  const canvas = document.getElementById("equity-chart");
  const ctx = canvas.getContext("2d");
  const w = canvas.width, h = canvas.height;
  ctx.clearRect(0, 0, w, h);
  if (points.length < 2) {
    ctx.fillStyle = "#8b96ad";
    ctx.font = "13px sans-serif";
    ctx.fillText("Zatiaľ nie je dosť dát na krivku (vytvorí sa po prvých behoch).", 12, h / 2);
    return;
  }
  const values = points.map(p => p.equity);
  const min = Math.min(...values), max = Math.max(...values);
  const pad = 20;
  const range = Math.max(1, max - min);
  ctx.strokeStyle = "#3ddc84";
  ctx.lineWidth = 2;
  ctx.beginPath();
  points.forEach((p, i) => {
    const x = pad + (i / (points.length - 1)) * (w - 2 * pad);
    const y = h - pad - ((p.equity - min) / range) * (h - 2 * pad);
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.stroke();
}

loadAll();
setInterval(loadAll, 60000);
