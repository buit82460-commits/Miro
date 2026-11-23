"""A4 live check (read-only): kiem tra server bridge da chay hay chua.

KHONG start server, KHONG pair/grant, KHONG can user thao tac o buoc nay.
Lead chi chay script nay SAU KHI server + extension da san sang (1 luot
Pair/Grant duy nhat do Lead dieu phoi), de xac nhan /health + /tabs.

Cach dung (khi live san sang):
    python live_check.py [port]        # mac dinh 18767
"""
import json
import sys
import urllib.request

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18767
BASE = "http://127.0.0.1:%d" % PORT


def get(path):
    req = urllib.request.Request(BASE + path, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status, json.load(r)
    except urllib.request.HTTPError as e:
        try:
            return e.code, json.load(e)
        except ValueError:
            return e.code, {}
    except OSError as e:
        return -1, {"error": "SERVER_NOT_RUNNING: %s" % e}


def main():
    s, body = get("/health")
    print("GET /health ->", s, body)
    assert s == 200 and body.get("ok") is True, "server chua chay /health FAIL"
    s, body = get("/tabs")
    print("GET /tabs ->", s, json.dumps(body, ensure_ascii=False)[:2000])
    assert s == 200 and body.get("ok") is True, "/tabs FAIL"
    for t in body.get("tabs", []):
        assert set(("browser", "tab", "url", "title", "event", "av")) <= set(t), t
    print("live_check: PASS (server song, /tabs doc duoc)")


if __name__ == "__main__":
    main()
