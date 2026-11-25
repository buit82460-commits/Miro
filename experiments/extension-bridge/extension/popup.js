// Slice 01B: One-click connection popup.
// Nut nguon: Connect/Disconnect (tat = dung thuc thi, giu link+policy).
// Pair code chi khi thiet lap lan dau / device bi forget.
const BASE = "http://127.0.0.1:18767";

async function refresh() {
  const st = document.getElementById("st");
  const power = document.getElementById("power");
  const vb = document.getElementById("v-bridge");
  const vp = document.getElementById("v-policy");
  let status = null;
  try {
    status = await chrome.runtime.sendMessage({ type: "miro-status" });
  } catch (e) { /* background chua san sang */ }
  const on = !!(status && status.paired && status.enabled !== false);
  vb.textContent = on ? "Online" : "Off";
  vb.className = "dot" + (on ? "" : " off");
  power.textContent = on ? "Dang bat (bam de tat)" : "Dang tat (bam de bat)";
  try {
    const r = await fetch(BASE + "/policy");
    const p = await r.json();
    vp.textContent = (p && p.read_allowed) ? "Until revoked"
      : "Revoked";
  } catch (e) {
    vp.textContent = "Unknown";
  }
  return status;
}
refresh();

document.getElementById("power").addEventListener("click", async () => {
  const st = document.getElementById("st");
  st.textContent = "...";
  try {
    const s = await chrome.runtime.sendMessage({ type: "miro-status" });
    const on = !!(s && s.paired && s.enabled !== false);
    if (on) {
      await chrome.runtime.sendMessage({ type: "miro-disconnect" });
      st.textContent = "Da tat. Miro khong thuc thi nua.";
    } else if (s && s.paired) {
      const r = await chrome.runtime.sendMessage({ type: "miro-connect" });
      st.textContent = (r && r.ok) ? "Da bat. Tu ket noi."
        : "Bat that bai: can pair lai.";
    } else {
      st.textContent = "Chua pair. Nhap code o muc thiet lap lan dau.";
    }
  } catch (e) {
    st.textContent = "FAIL: " + String(e && e.message || e);
  }
  refresh();
});

document.getElementById("go").addEventListener("click", async () => {
  const st = document.getElementById("st");
  const code = document.getElementById("code").value.trim();
  st.textContent = "...";
  try {
    const res = await fetch(BASE + "/redeem", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    });
    const data = await res.json();
    if (!data.ok) {
      st.textContent = "FAIL: " + (data.error || res.status);
      return;
    }
    await chrome.runtime.sendMessage({ type: "miro-pair",
      baseUrl: BASE,
      sessionId: data.session_id, token: data.token,
      deviceId: data.device_id || "" });
    st.textContent = "Da ket noi. Quyen doc duy tri den khi thu hoi.";
  } catch (e) {
    st.textContent = "FAIL: no backend (chay server.py 18767 chua?)";
  }
  refresh();
});

// Tuy chon nang cao: giu lai de debug + ho tro truong hop policy bi revoke.
document.getElementById("grant").addEventListener("click", async () => {
  const st = document.getElementById("st");
  st.textContent = "...";
  try {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const tab = tabs && tabs[0];
    if (!tab) {
      st.textContent = "FAIL: khong thay tab hien tai";
      return;
    }
    const res = await chrome.runtime.sendMessage({ type: "miro-grant",
      tabId: tab.id });
    st.textContent = (res && res.ok)
      ? ("Granted tab " + tab.id + " (manual, uu tien).")
      : ("FAIL: " + ((res && res.error) || "no backend"));
  } catch (e) {
    st.textContent = "FAIL: " + String(e && e.message || e);
  }
});

document.getElementById("revoke").addEventListener("click", async () => {
  const st = document.getElementById("st");
  st.textContent = "...";
  try {
    const res = await fetch(BASE + "/revoke-policy", { method: "POST" });
    const data = await res.json();
    st.textContent = (data && data.ok)
      ? "Da thu hoi quyen. Auto-grant dung; grant tay van duoc."
      : ("FAIL: " + ((data && data.error) || res.status));
  } catch (e) {
    st.textContent = "FAIL: " + String(e && e.message || e);
  }
  refresh();
});

document.getElementById("forget").addEventListener("click", async () => {
  const st = document.getElementById("st");
  st.textContent = "...";
  try {
    const s = await chrome.runtime.sendMessage({ type: "miro-status" });
    const res = await fetch(BASE + "/forget", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ device_id: (s && s.deviceId) || "" }),
    });
    const data = await res.json();
    st.textContent = (data && data.ok)
      ? "Da xoa lien ket. Can pair lai tu dau."
      : ("FAIL: " + ((data && data.error) || res.status));
  } catch (e) {
    st.textContent = "FAIL: " + String(e && e.message || e);
  }
  refresh();
});
