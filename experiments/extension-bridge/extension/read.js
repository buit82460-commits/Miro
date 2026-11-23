// Ham doc co dinh (Phien A) — KHONG arbitrary evaluate.
// Backend chi gui read_spec enum; extension map sang func cung duoi day.
// Them scripting+activeTab de goi chrome.scripting, nhung chi 3 func nay.
const READ_FUNCS = {
  "title": () => ({ title: document.title, url: location.href }),
  "meta": () => ({
    title: document.title,
    url: location.href,
    description:
      (document.querySelector('meta[name="description"]') || {}).content || "",
    h1: (document.querySelector("h1") || {}).innerText || "",
  }),
  "text-limited": () => ({
    title: document.title,
    url: location.href,
    text: (document.body || {}).innerText
      ? document.body.innerText.slice(0, 2000) : "",
  }),
  // Tin hieu login co cau truc cho actor verification (TikTok).
  // KHONG caption/comment/text tu do — chi 3 dau hieu doc lap. Bat ky
  // selector la nao khac -> khong chay (func cung, backend validate schema).
  "actor-login": () => {
    const q = (s) => document.querySelector(s);
    const loginBtn = q('[data-e2e="top-login-button"]')
      || q('[data-e2e="nav-login-button"]')
      || q('button:has-text("Log in")')
      || [...document.querySelectorAll("a,button")].find(
        (el) => /^\s*log\s*in\s*$/i.test(el.innerText || ""));
    let profileHref = "";
    const links = [...document.querySelectorAll('a[href^="/@"]')];
    const good = links.find((a) => {
      const href = a.getAttribute("href") || "";
      const tail = href.slice(2).split("/")[0].split("?")[0];
      return /^[\w.\-]{2,24}$/.test(tail);
    });
    if (good) profileHref = good.getAttribute("href") || "";
    const upload = q('[data-e2e="upload-icon"]')
      || q('a[href^="/upload"]')
      || [...document.querySelectorAll("a")].find(
        (a) => /upload/i.test(a.getAttribute("href") || ""));
    return {
      title: document.title,
      url: location.href,
      has_login_button: loginBtn ? "1" : "",
      profile_href: profileHref,
      has_upload_link: upload ? "1" : "",
    };
  },
  // Video identity TikTok: aweme_id tu URL that + caption preview hep.
  // KHONG caption day du/comment — chi du de REA/Eye xac dinh dung video.
  "video-identity": () => {
    const url = location.href || "";
    let aweme = "";
    const m = url.match(/\/video\/(\d+)/);
    if (m) aweme = m[1];
    const cap = document.querySelector(
      '[data-e2e="browse-video-desc"], h1[data-e2e="video-desc"], '
      + '[data-e2e="video-desc"]');
    const hasVideo = !!document.querySelector("video");
    return {
      title: document.title,
      url: url,
      aweme_id: aweme,
      caption_preview: ((cap || {}).innerText || "").slice(0, 300),
      has_video: hasVideo ? "1" : "",
    };
  },
};

async function readFixed(tabId, spec) {
  const fn = READ_FUNCS[spec];
  if (!fn) throw new Error("READ_SPEC_DENIED");
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    func: fn,
  }).catch((e) => {
    const msg = (chrome.runtime && chrome.runtime.lastError
      && chrome.runtime.lastError.message) || (e && e.message) || e;
    console.log("[miro-bridge] executeScript denied:", String(msg));
    throw new Error("SCRIPTING_DENIED: " + String(msg));
  });
  return (results && results[0] && results[0].result) || {};
}
