// Miro Tab Bridge — background service worker (read-only probe).
// Buoc 3: gui event tu dong ve backend qua kenh xac thuc (pairing + seq).
// Chi event read-only. Khong DOM, khong debugger, khong click/type/evaluate.
importScripts("read.js");
const seen = new Map();
let cfg = { baseUrl: "", sessionId: "", token: "", seq: 0 };

async function loadCfg() {
  try {
    const cur = await chrome.storage.local.get(
      { bridge: { baseUrl: "", sessionId: "", token: "", seq: 0 } });
    cfg = { ...cfg, ...(cur.bridge || {}) };
  } catch (e) { /* chua pairing: chi log local */ }
}
async function saveCfg() {
  try {
    await chrome.storage.local.set(
      { bridge: { baseUrl: cfg.baseUrl, sessionId: cfg.sessionId,
                  token: "", seq: cfg.seq } });
    // NOTE: khong luu token dai han o spike nay; pairing lai sau restart.
  } catch (e) { /* ignore */ }
}

function describe(tab) {
  return {
    tabId: tab.id,
    url: tab.url || "",
    title: tab.title || "",
    status: tab.status || "",
    observed_at: Date.now(),
  };
}

async function send(events) {
  if (!cfg.baseUrl || !cfg.sessionId || !cfg.token) return; // chua pairing
  const seq = cfg.seq + 1;
  let res;
  try {
    res = await fetch(cfg.baseUrl + "/push", {
      method: "POST",
      headers: { "Content-Type": "application/json",
                 "X-Session": cfg.sessionId, "X-Token": cfg.token },
      body: JSON.stringify({ seq, events }),
    });
  } catch (e) {
    console.log("[miro-bridge] push net-fail seq=", seq);
    return;
  }
  if (res.status === 409) {
    // RESYNC_REQUIRED: gui full tab list (authoritative snapshot: complete).
    try {
      const tabs = await chrome.tabs.query({});
      await fetch(cfg.baseUrl + "/resync", {
        method: "POST",
        headers: { "Content-Type": "application/json",
                   "X-Session": cfg.sessionId, "X-Token": cfg.token },
        body: JSON.stringify({ seq: cfg.seq + 1, generation: cfg.seq + 1,
          complete: true,
          tabs: tabs.map((t) => ({ tabId: t.id })) }),
      });
      const cur = await chrome.tabs.query({});
      cfg.seq += 1;
      await saveCfg();
      console.log("[miro-bridge] resync sent, tabs=", cur.length);
    } catch (e) { /* ignore */ }
    return;
  }
  if (res.ok) {
    cfg.seq = seq;
    await saveCfg();
  } else {
    console.log("[miro-bridge] push denied:", res.status);
  }
}

async function report(event, tab) {
  const info = describe(tab || {});
  seen.set(info.tabId, { ...info, event });
  console.log("[miro-bridge]", event, info);
  try {
    const cur = await chrome.storage.local.get({ outbox: [] });
    const outbox = Array.isArray(cur.outbox) ? cur.outbox : [];
    outbox.push({ event, ...info });
    await chrome.storage.local.set({ outbox: outbox.slice(-200) });
  } catch (e) { /* ignore */ }
  await send([{ event, ...info }]);
}

// Nhan pairing tu popup/options (buoc 3): {baseUrl, sessionId, token}.
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg && msg.type === "miro-pair" && msg.sessionId && msg.token) {
    cfg.baseUrl = String(msg.baseUrl || "");
    cfg.sessionId = String(msg.sessionId);
    cfg.token = String(msg.token);
    console.log("[miro-bridge] paired, session set (token hidden)");
    return;
  }
  // Popup hoi trang thai (mo lai sau khi chuyen tab): da pair hay chua.
  if (msg && msg.type === "miro-status") {
    sendResponse({ paired: !!(cfg.sessionId && cfg.token) });
    return;
  }
  if (msg && msg.type === "miro-grant" && msg.tabId) {
    // B1: extension tu kiem tra tab active + quyen truoc khi xin grant.
    // Khong gui `gesture` de backend tin; gui grant_seq don dieu.
    (async () => {
      try {
        const tabs = await chrome.tabs.query(
          { active: true, currentWindow: true });
        const active = tabs && tabs[0];
        if (!active || active.id !== msg.tabId) {
          sendResponse({ ok: false, error: "NOT_ACTIVE_TAB" });
          return;
        }
        const res = await fetch(cfg.baseUrl + "/grant", {
          method: "POST",
          headers: { "Content-Type": "application/json",
                     "X-Session": cfg.sessionId, "X-Token": cfg.token },
          body: JSON.stringify({ tabId: msg.tabId,
            grant_seq: cfg.seq + 1 }),
        });
        const data = await res.json().catch(() => ({}));
        if (res.ok) {
          cfg.seq += 1;
          await saveCfg();
        }
        sendResponse({ ok: !!data.ok,
          error: data.ok ? "" : (data.error || res.status) });
      } catch (e) {
        sendResponse({ ok: false, error: "no backend" });
      }
    })();
    return true; // giu kenh mo cho sendResponse bat dong bo
  }
  // Len doc co dinh tu backend: chi spec enum, map sang func cung read.js.
  // Khong nhan JS tuy y. Chi chay khi co grant (backend da kiem).
  if (msg && msg.type === "miro-read" && msg.tabId && msg.spec) {
    // B2+B3: kiem live URL truoc/sau doc, gui /read-result rieng.
    // Khong do DOM vao /push lifecycle.
    (async () => {
      try {
        const tabs = await chrome.tabs.query({ active: true,
          currentWindow: true });
        const active = tabs && tabs[0];
        if (!active || active.id !== msg.tabId) {
          sendResponse({ ok: false, error: "NOT_ACTIVE_TAB" });
          return;
        }
        const before = active.url || "";
        const data = await readFixed(msg.tabId, msg.spec);
        const afterTabs = await chrome.tabs.get(msg.tabId).catch(() => null);
        const after = (afterTabs && afterTabs.url) || "";
        if (after !== before) {
          console.log("[miro-bridge] read refused: navigation race");
          sendResponse({ ok: false, error: "NAVIGATION_RACE" });
          return;
        }
        const res = await fetch(cfg.baseUrl + "/read-result", {
          method: "POST",
          headers: { "Content-Type": "application/json",
                     "X-Session": cfg.sessionId, "X-Token": cfg.token },
          body: JSON.stringify({ seq: cfg.seq + 1, tabId: msg.tabId,
            read: msg.spec, live_origin: after, data }),
        });
        const out = await res.json().catch(() => ({}));
        if (res.ok) {
          cfg.seq += 1;
          await saveCfg();
        }
        sendResponse({ ok: res.ok,
          error: res.ok ? "" : (out.error || res.status) });
        console.log("[miro-bridge] read served:", msg.spec, "tab=", msg.tabId);
      } catch (e) {
        sendResponse({ ok: false,
          error: String(e && e.message || e) });
        console.log("[miro-bridge] read denied:", String(e && e.message || e));
      }
    })();
    return true;
  }
});

// Poll inbox: server -> extension (dispatch tu dong, khong can mo popup).
// Contract: CLAIM truoc EXECUTE (atomic claim). Hai poll dong thoi lan 2
// -> CLAIM_CONFLICT, khong double-exec. Late result sau deadline bi server
// tu choi (REQUEST_EXPIRED/CANCELLED). Execution loi (NAVIGATION_RACE,
// NOT_ACTIVE_TAB) -> gui exec_error de backend nhan terminal thay vi data gia.
async function pollInbox() {
  if (!cfg.baseUrl || !cfg.sessionId || !cfg.token) return;
  let res;
  try {
    res = await fetch(cfg.baseUrl + "/inbox", {
      method: "POST",
      headers: { "Content-Type": "application/json",
                 "X-Session": cfg.sessionId, "X-Token": cfg.token },
      body: JSON.stringify({}),
    });
  } catch (e) {
    return; // bridge chua chay: im lang, poll lai vong sau
  }
  if (!res.ok) return;
  const out = await res.json().catch(() => ({}));
  const pend = (out && out.pending) || [];
  for (const job of pend) {
    if (!job || !job.request_id || !job.tabId || !job.spec) continue;
    // 1. Claim nguyen tu: chi 1 worker thang.
    let claim;
    try {
      claim = await fetch(cfg.baseUrl + "/claim", {
        method: "POST",
        headers: { "Content-Type": "application/json",
                   "X-Session": cfg.sessionId, "X-Token": cfg.token },
        body: JSON.stringify({ request_id: job.request_id }),
      });
    } catch (e) {
      continue;
    }
    if (!claim.ok) continue; // CLAIM_CONFLICT/CANCELLED/EXPIRED: bo qua
    // 2. Execute: doc FIXED func, kem live_origin de server check grant.
    let data = null;
    let execError = "";
    try {
      data = await readFixed(job.tabId, job.spec);
    } catch (e) {
      execError = String(e && e.message || e).slice(0, 200);
    }
    let liveUrl = "";
    try {
      const tabs = await chrome.tabs.get(job.tabId).catch(() => null);
      liveUrl = (tabs && tabs.url) || "";
    } catch (e) { execError = execError || "TAB_GONE"; }
    if (!liveUrl && !execError) execError = "TAB_GONE";
    // 3. Report: thanh cong -> data; that bai -> exec_error (terminal).
    try {
      const r = await fetch(cfg.baseUrl + "/read-result", {
        method: "POST",
        headers: { "Content-Type": "application/json",
                   "X-Session": cfg.sessionId, "X-Token": cfg.token },
        body: JSON.stringify(execError
          ? { seq: cfg.seq + 1, tabId: job.tabId, read: job.spec,
              live_origin: liveUrl, data: {}, request_id: job.request_id,
              exec_error: execError }
          : { seq: cfg.seq + 1, tabId: job.tabId, read: job.spec,
              live_origin: liveUrl, data, request_id: job.request_id }),
      });
      if (r.ok) { cfg.seq += 1; await saveCfg(); }
      else {
        const err = await r.json().catch(() => ({}));
        console.log("[miro-bridge] inbox result refused:",
          (err && err.error) || r.status);
      }
    } catch (e) { /* net-fail: giu claim, retry o poll sau */ }
    console.log("[miro-bridge] inbox served:", job.spec,
      "request=", job.request_id, execError ? ("err=" + execError) : "ok");
  }
}
setInterval(pollInbox, 1000);

// Worker lifecycle observability: heartbeat moi 15s de kiem thu
// service worker con song khi popup dong (khong can mo DevTools).
setInterval(async () => {
  try {
    await chrome.storage.local.set(
      { bridge_heartbeat: Date.now(), bridge_seq: cfg.seq });
  } catch (e) { /* ignore */ }
}, 15000);

chrome.tabs.onCreated.addListener((tab) => report("opened", tab));
chrome.tabs.onRemoved.addListener((tabId) => {
  seen.delete(tabId);
  report("closed", { id: tabId });
});
chrome.tabs.onUpdated.addListener((tabId, change, tab) => {
  if (change.url || change.title || change.status === "complete") {
    report(change.url ? "url-changed" : "updated", tab);
  }
});

chrome.runtime.onStartup.addListener(async () => {
  await loadCfg();
  const tabs = await chrome.tabs.query({});
  tabs.forEach((t) => seen.set(t.id, { ...describe(t), event: "startup" }));
  console.log("[miro-bridge] startup tabs:", tabs.length);
});
chrome.runtime.onInstalled.addListener(async () => {
  const tabs = await chrome.tabs.query({});
  console.log("[miro-bridge] installed, tabs:", tabs.length);
});
loadCfg();
