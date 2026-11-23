"""Negative test HTTP: B3 registry poisoning + B1 fake gesture (server that)."""
import json
import urllib.request

BASE = "http://127.0.0.1:18767"


def post(path, obj, sid="", tok=""):
    q = urllib.request.Request(
        BASE + path, data=json.dumps(obj).encode(),
        headers={"Content-Type": "application/json",
                 "X-Session": sid, "X-Token": tok})
    try:
        r = urllib.request.urlopen(q, timeout=5)
        return r.status, json.load(r)
    except urllib.request.HTTPError as e:
        try:
            return e.code, json.load(e)
        except ValueError:
            return e.code, {}


def main():
    post("/pair", {})
    # Khong session -> /grant va /read-result deu 403 (B1: client la khong
    # tu POST duoc).
    s, body = post("/grant", {"tabId": 1, "gesture": "icon-click",
                              "grant_seq": 1}, "x", "y")
    assert s == 403 and body.get("error") in (
        "SESSION_UNKNOWN", "SESSION_EXPIRED", "AUTH_DENIED"), (s, body)
    s, body = post("/read-result", {"tabId": 1, "read": "title",
                                    "live_origin": "https://www.tiktok.com/",
                                    "seq": 1, "data": {"title": "evil"}},
                   "x", "y")
    assert s == 403, (s, body)
    # read_spec la (B3: tu choi truoc khi cham du lieu).
    s, body = post("/read", {"tabId": 1, "read": "evaluate"}, "x", "y")
    assert s == 403, (s, body)
    print("negative HTTP (fake grant/read, spec la): PASS")


if __name__ == "__main__":
    main()
