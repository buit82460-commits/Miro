// Pairing: user nhap code 6 so -> redeem lay session. Khong log token.
// Popup dong moi khi chuyen tab (hanh vi chuan Chrome) — trang thai pair
// nam o background, popup mo lai se hoi status, khong can nhap lai code.
async function refreshStatus() {
  const st = document.getElementById("st");
  const code = document.getElementById("code");
  const go = document.getElementById("go");
  try {
    const s = await chrome.runtime.sendMessage({ type: "miro-status" });
    if (s && s.paired) {
      code.style.display = "none";
      go.style.display = "none";
      st.textContent = "Da pair. Bam Grant DOM de cap quyen doc tab hien tai.";
      return true;
    }
  } catch (e) { /* background chua san sang */ }
  return false;
}
refreshStatus();
document.getElementById("go").addEventListener("click", async () => {
  const st = document.getElementById("st");
  const code = document.getElementById("code").value.trim();
  st.textContent = "...";
  try {
    const res = await fetch("http://127.0.0.1:18767/redeem", {
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
      baseUrl: "http://127.0.0.1:18767",
      sessionId: data.session_id, token: data.token });
    st.textContent = "Paired. Bam Grant DOM de cap quyen doc tab hien tai.";
  } catch (e) {
    st.textContent = "FAIL: no backend (chay server.py 18767 chua?)";
  }
});

// Grant DOM: user gesture ro rang cho phep doc tab HIEN TAI.
// Pairing KHONG tu dong la grant. Gui ve background de xin grant tu backend.
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
    if (!(res && res.ok)) {
      st.textContent = "FAIL: " + ((res && res.error) || "no backend");
      return;
    }
    st.textContent = "Granted tab " + tab.id + ". Dang doc title...";
    // Grant xong tu doc title + actor-login bang func cung (khong JS tuy y).
    const rd = await chrome.runtime.sendMessage({ type: "miro-read",
      tabId: tab.id, spec: "title" });
    const ra = await chrome.runtime.sendMessage({ type: "miro-read",
      tabId: tab.id, spec: "actor-login" });
    if (rd && rd.ok && ra && ra.ok) {
      st.textContent = "Granted tab " + tab.id + " (120s). Da doc title+actor.";
    } else if (rd && rd.ok) {
      st.textContent = "Granted tab " + tab.id + " (120s). Da doc title.";
    } else {
      st.textContent = "Granted tab " + tab.id + ". Doc that bai: " +
        ((rd && rd.error) || "no backend");
    }
  } catch (e) {
    st.textContent = "FAIL: " + String(e && e.message || e);
  }
});

document.getElementById("feed").addEventListener("click", async () => {
  const st = document.getElementById("st");
  st.textContent = "...";
  try {
    const tabs = await chrome.tabs.query(
      { active: true, currentWindow: true });
    const tab = tabs && tabs[0];
    if (!tab) { st.textContent = "FAIL: khong thay tab"; return; }
    const rd = await chrome.runtime.sendMessage(
      { type: "miro-read", tabId: tab.id, spec: "feed-video" });
    st.textContent = (rd && rd.ok)
      ? ("Da doc feed-video tab " + tab.id + ".")
      : ("Doc feed that bai: " + ((rd && rd.error) || "no backend"));
  } catch (e) {
    st.textContent = "FAIL: " + String(e && e.message || e);
  }
});
