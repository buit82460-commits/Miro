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
      || [...document.querySelectorAll("a,button")].find(
        (el) => /^\s*log\s*in\s*$/i.test(el.innerText || ""));
    let profileHref = "";
    const nav = document.querySelector("nav")
      || document.querySelector("aside")
      || document.querySelector('[data-e2e="side-nav"]');
    const scopeLinks = (nav ? [...nav.querySelectorAll('a[href^="/@"]')] : [])
      .concat([...document.querySelectorAll('a[href^="/@"]')]
        .filter((a) => /profile/i.test(
          (a.innerText || "") + " " + (a.getAttribute("aria-label") || ""))));
    const pool = scopeLinks.length ? scopeLinks : links;
    const isHandle = (h) => /^[\w.\-]{2,24}$/.test(h || "");
    const tailOf = (href) => (href || "").slice(2).split("/")[0].split("?")[0];
    // Loai "Following accounts" trong sidebar: cung la /@handle don nhung
    // KHONG phai user dang nhap (anh + bai cua ban da chi ro).
    const inFollowing = (a) => {
      let el = a;
      for (let i = 0; i < 6 && el; i++) {
        el = el.parentElement;
        const t = ((el && el.innerText) || "").slice(0, 60);
        if (/following accounts/i.test(t)) return true;
      }
      return false;
    };
    const poolClean = pool.filter((a) => !inFollowing(a));
    // Uu tien link Profile cua user dang nhap: anchor /@handle DON (khong
    // chua /video/), thuong nam o sidebar/nav. Link feed /@author/video/...
    // la tac gia video (vd @nghia68683), KHONG phai actor dang nhap.
    // Tieu chi manh nhat: anchor co text/aria "Profile" (nut Profile o
    // sidebar luon tro ve trang ca nhan cua user dang nhap).
    const textOf = (a) => ((a.innerText || "") + " "
      + (a.getAttribute("aria-label") || "")).trim();
    const ownProfile = poolClean.find((a) => {
      const href = a.getAttribute("href") || "";
      if (href.includes("/video/")) return false;
      if (!isHandle(tailOf(href))) return false;
      return /profile/i.test(textOf(a));
    });
    const own = ownProfile || poolClean.find((a) => {
      const href = a.getAttribute("href") || "";
      if (href.includes("/video/")) return false;
      return isHandle(tailOf(href));
    });
    const good = own || poolClean.find((a) => isHandle(tailOf(a.getAttribute("href"))));
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
  // TRANG /video/... (URL chua aweme). Feed homepage dung "feed-video".
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
  // Video dau tien trong feed For You (trang chu https://www.tiktok.com/).
  // URL trang van la homepage nen phai mo anchor /video/ that trong DOM.
  // CHI lay trong feed chinh (recommend-list-item-container), BO QUA
  // anchor o sidebar/notification (author dang so ID nhu @7455898...).
  // KHONG caption day du/comment — chi preview 300 ky tu.
  "feed-video": () => {
    const url = location.href || "";
    const isHandle = (h) => /^[\w.\-]{2,24}$/.test(h || "")
      && !/^\d{10,}$/.test(h || "");
    const pick = (root) => {
      const anchors = [...root.querySelectorAll('a[href*="/video/"]')];
      for (const a of anchors) {
        const href = a.getAttribute("href") || "";
        const m = href.match(/\/video\/(\d+)/);
        const am = href.match(/\/@([^/?]+)/);
        if (!m || !am || !isHandle(am[1])) continue;
        const vurl = href.startsWith("http") ? href
          : ("https://www.tiktok.com" + (href.startsWith("/") ? href : "/" + href));
        return { a, href: vurl, aweme: m[1], author: "@" + am[1] };
      }
      return null;
    };
    // Uu tien feed chinh truoc, toan trang chi la fallback.
    const feed = document.querySelector(
      '[data-e2e="recommend-list-item-container"]')
      || document.querySelector('[data-e2e="feed"]')
      || document.querySelector("main")
      || document.body;
    let hit = pick(feed) || pick(document);
    let caption = "";
    if (hit) {
      const scope = hit.a.closest(
        '[data-e2e="recommend-list-item-container"]')
        || hit.a.closest("article") || hit.a.closest("div");
      caption = (((scope || {})).innerText || "").slice(0, 300);
    }
    const hasVideo = !!document.querySelector("video");
    return {
      title: document.title,
      url: url,
      video_url: hit ? hit.href : "",
      aweme_id: hit ? hit.aweme : "",
      author: hit ? hit.author : "",
      caption_preview: caption,
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
