// Popup chinh: phan anh trang thai he thong, khong tu tao trang thai.
// Nguyen tac: khong doc duoc != Revoked; loi API hien dung ban chat.
// Trang thai: NOT_PAIRED / DISCONNECTED / BRIDGE_OFFLINE / CONNECTING /
// RECONNECTING / PERMISSION_REQUIRED / PERMISSION_REVOKED / READY / UNKNOWN.
const BASE = "http://127.0.0.1:18767";

const el = (id) => document.getElementById(id);

async function bg(type, extra) {
  try {
    return await chrome.runtime.sendMessage({ type, ...(extra || {}) });
  } catch (e) {
    return null; // background chua san sang
  }
}

async function bridgeUp() {
  try {
    const r = await fetch(BASE + "/health", { method: "GET" });
    return r.ok;
  } catch (e) {
    return false;
  }
}

async function fetchPolicy() {
  // Dung kenh da xac thuc: background giu session, khong lo token ra popup.
  const s = await bg("miro-policy");
  if (!s) return { error: "BG_UNAVAILABLE" };
  return s;
}

function render(state, detail) {
  // state: ma trang thai; detail: {displayName, instanceId, capabilities}.
  const p = el("power"), t = el("state"), h = el("hint");
  const vn = el("v-name"), vi = el("v-inst"), dot = el("v-dot");
  const names = {
    NOT_PAIRED: ["Disconnected", "Bam de ket noi Miro"],
    DISCONNECTED: ["Disconnected", "Bam de ket noi Miro"],
    LINK_WAITING: ["Cho duyet", "Mo Miro de Cho phep ket noi 1 lan"],
    BRIDGE_OFFLINE: ["Bridge offline", "Miro tren may chua chay"],
    CONNECTING: ["Dang ket noi", "..."],
    RECONNECTING: ["Dang ket noi lai", "..."],
    PERMISSION_REQUIRED: ["Can cap quyen", "Mo Settings de xac nhan"],
    PERMISSION_REVOKED: ["Quyen da thu hoi", "Mo Settings de cap lai"],
    READY: ["Connected", "San sang nhan nhiem vu"],
    UNKNOWN: ["Khong xac dinh", "Khong doc duoc trang thai"],
  };
  const n = names[state] || names.UNKNOWN;
  t.textContent = n[0];
  h.textContent = n[1];
  const on = (state === "READY");
  p.className = on ? "on" : "";
  p.textContent = "\u23FB";
  vn.textContent = (detail && detail.displayName) || "Chua dat ten";
  vi.textContent = (detail && detail.instanceId) || "Chua co";
  dot.className = "dot" + (on ? " ok" : "");
  // Form pair an mac dinh; chi hien khi user bam nut nguon luc chua pair.
  if (state !== "NOT_PAIRED" && state !== "DISCONNECTED") {
    el("pairbox").style.display = "none";
  }
  el("grantbox").style.display =
    (state === "PERMISSION_REQUIRED" || state === "PERMISSION_REVOKED")
    ? "" : "none";
  return state;
}

async function refresh() {
  const st = el("st");
  const up = await bridgeUp();
  const s = await bg("miro-status");
  if (!s) return render("UNKNOWN", {});
  const paired = !!(s.session || (s.sessionId && s.token));
  const detail = { displayName: s.displayName || "Chua dat ten",
                   instanceId: s.instanceId || "Chua co" };
  if (!paired) {
    if (!up) return render("BRIDGE_OFFLINE", detail);
    // One-click: da gui yeu cau, dang doi user duyet tren Miro.
    if (s.linkPending) return render("LINK_WAITING", detail);
    return render("NOT_PAIRED", detail);
  }
  if (s.enabled === false) return render("DISCONNECTED", detail);
  if (!up) return render("BRIDGE_OFFLINE", detail);
  // Da pair + bat: hoi policy qua kenh xac thuc de phan biet
  // READY / PERMISSION_REQUIRED / PERMISSION_REVOKED / UNKNOWN.
  if (s.connecting) return render("CONNECTING", detail);
  if (s.reconnecting) return render("RECONNECTING", detail);
  const pol = await fetchPolicy();
  if (pol && pol.ok) {
    if (pol.read_allowed) {
      await renderAdv(pol);
      return render("READY", {
        displayName: pol.display_name || detail.displayName,
        instanceId: s.instanceId || "Chua co",
      });
    }
    await renderAdv(pol);
    return render(pol.revoked ? "PERMISSION_REVOKED"
                             : "PERMISSION_REQUIRED", {
      displayName: pol.display_name || detail.displayName,
      instanceId: s.instanceId || "Chua co",
    });
  }
  // Loi doc policy: hien dung ban chat, KHONG doi thanh Revoked/OFF.
  await renderAdv(pol);
  return render("UNKNOWN", detail);
}

async function renderAdv(pol) {
  const s = await bg("miro-status");
  const lines = [];
  lines.push("instance: " + ((s && s.instanceId) || "?"));
  lines.push("device: " + ((s && s.deviceId)
    ? String(s.deviceId).slice(0, 12) + "..." : "?"));
  if (pol && pol.ok) {
    lines.push("capability: " + (pol.capabilities || []).join(","));
    lines.push("origins: " + (pol.origins || []).join(","));
    lines.push("policy: " + (pol.read_allowed ? "granted"
      : (pol.revoked ? "revoked" : "required")));
  } else {
    lines.push("policy: unreadable (" +
      String((pol && (pol.error || pol.code)) || "unknown") + ")");
  }
  el("adv").textContent = lines.join("\n");
}

// Nut nguon la hanh dong duy nhat ngoai Settings:
// - Chua pair -> bam: hien form nhap code (khong tu hien).
// - Da pair + dang bat -> bam: tat (giu link + policy).
// - Da pair + dang tat -> bam: bat lai (tu reconnect neu can).
el("power").addEventListener("click", async () => {
  const st = el("st");
  st.textContent = "...";
  const s = await bg("miro-status");
  if (!s) { st.textContent = "Background chua san sang."; refresh(); return; }
  const paired = !!(s.session || (s.sessionId && s.token));
  if (!paired) {
    const box = el("pairbox");
    box.style.display = (box.style.display === "none") ? "" : "none";
    st.textContent = "";
    return;
  }
  const on = (s.enabled !== false);
  if (on) {
    await bg("miro-disconnect");
    st.textContent = "Da tat. Lien ket va quyen duoc giu nguyen.";
  } else {
    const r = await bg("miro-connect");
    st.textContent = (r && r.ok) ? "Dang bat..." : "Bat that bai.";
  }
  refresh();
});

// Banh rang: mo/dong Settings (diagnostics + doi ten + revoke + forget).
el("gear").addEventListener("click", async () => {
  const box = el("settings");
  const open = (box.style.display === "none") || !box.style.display;
  box.style.display = open ? "" : "none";
  if (open) {
    const pol = await fetchPolicy();
    await renderAdv(pol);
  }
});

// One-click Approval: lan dau bam Ket noi -> extension gui yeu cau,
// user duyet 1 lan tren Miro, extension tu redeem ngam (khong nhap code).
// Ten goi nho do user dat, chi la nhan hien thi, khong dung cho auth.
async function linkTick(st) {
  for (let i = 0; i < 30; i++) {
    await new Promise((r) => setTimeout(r, 2000));
    const r = await bg("miro-link-redeem");
    if (r && r.ok) {
      st.textContent = "Da ket noi.";
      el("pairbox").style.display = "none";
      refresh();
      return;
    }
    if (!r || (r.error !== "LINK_NOT_APPROVED" &&
               r.error !== "BRIDGE_UNREACHABLE")) {
      st.textContent = "FAIL: " + ((r && r.error) || "unknown");
      refresh();
      return;
    }
    st.textContent = "Dang cho duyet tren Miro... (" + (i + 1) + ")";
  }
  st.textContent = "Het han cho duyet. Bam Ket noi de gui lai.";
  refresh();
}

el("go").addEventListener("click", async () => {
  const st = el("st");
  const disp = el("dispname").value.trim();
  st.textContent = "...";
  const q = await bg("miro-link-request", { hint: disp });
  if (!q || !q.ok) {
    st.textContent = "FAIL: " + ((q && q.error) || "khong tao duoc yeu cau");
    return;
  }
  el("pairbox").style.display = "none";
  refresh();
  st.textContent = "Da gui yeu cau. Mo Miro de Cho phep (1 lan).";
  linkTick(st);
});

// Advanced du phong: ket noi bang pairing code khi One-click khong dung duoc.
el("gocode").addEventListener("click", async () => {
  const st = el("st");
  const code = el("code").value.trim();
  const disp = el("dispname").value.trim();
  st.textContent = "...";
  try {
    const res = await fetch(BASE + "/redeem", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, profile_name: disp }),
    });
    const data = await res.json();
    if (!data.ok) {
      st.textContent = "FAIL: " + (data.error || res.status);
      return;
    }
    await chrome.runtime.sendMessage({ type: "miro-pair",
      baseUrl: BASE,
      sessionId: data.session_id, token: data.token,
      deviceId: data.device_id || "",
      instanceId: data.instance_id || "" });
    st.textContent = "Da ket noi.";
  } catch (e) {
    st.textContent = "FAIL: no backend (chay server.py 18767 chua?)";
  }
  refresh();
});

// Cap lai quyen sau revoke: thao tac xac nhan ro rang (confirm:true),
// khong pair lai, khong mo rong origin/capability.
el("grantback").addEventListener("click", async () => {
  const st = el("st");
  st.textContent = "...";
  const r = await bg("miro-grant-policy");
  st.textContent = (r && r.ok) ? "Da cap lai quyen doc."
    : ("FAIL: " + ((r && (r.error || r.code)) || "unknown"));
  refresh();
});

el("rename").addEventListener("click", async () => {
  const st = el("st");
  const name = prompt("Ten goi nho cho thiet bi nay:", "");
  if (name === null) return;
  const r = await bg("miro-rename", { displayName: String(name || "") });
  st.textContent = (r && r.ok) ? "Da doi ten."
    : ("FAIL: " + ((r && (r.error || r.code)) || "unknown"));
  refresh();
});

el("revoke").addEventListener("click", async () => {
  const st = el("st");
  st.textContent = "...";
  const r = await bg("miro-revoke-policy");
  st.textContent = (r && r.ok)
    ? "Da thu hoi. Lien ket duoc giu; cap lai bat cu luc nao."
    : ("FAIL: " + ((r && (r.error || r.code)) || "unknown"));
  refresh();
});

el("forget").addEventListener("click", async () => {
  const st = el("st");
  st.textContent = "...";
  const r = await bg("miro-forget");
  st.textContent = (r && r.ok) ? "Da xoa lien ket. Can pair lai tu dau."
    : ("FAIL: " + ((r && (r.error || r.code)) || "unknown"));
  refresh();
});

refresh();
