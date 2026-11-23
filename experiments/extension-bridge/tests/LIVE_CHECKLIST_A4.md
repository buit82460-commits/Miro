# A4 Live Read-Only E2E Checklist (pair/grant/read/revoke)

> Chi chay khi Lead noi san sang. Dung 1 luot Pair/Grant duy nhat.
> A4 KHONG tu live neu can user thao tac (nhap pairing code, mo tab...).

## Dieu kien truoc live

- [ ] Chrome Profile 20 dang mo, da login TikTok dung account can verify.
- [ ] Extension bridge da load (unpacked), service worker khong bao loi.
- [ ] Server bridge **chua chay** (Lead start moi, lay pairing code tren console).

## Buoc live (Lead dieu phoi, 1 luot duy nhat)

1. Lead start server: `python bridge/server.py 18767` (chay tren 127.0.0.1).
   Server in `PAIRING_CODE: XXXXXX` ra console.
2. User nhap code vao extension (popup) trong TTL (qua TTL -> Pairing INVALID,
   cho phep pair lai 1 lan, khong tinh la luot 2).
3. Extension tu dong: redeem -> push event tab TikTok live (`opened`/`updated`).
4. Lead kiem tra: `python tests/live_check.py 18767`
   - Dieu kien PASS: `/health` 200 ok + `/tabs` 200 co tab TikTok `av=fresh`.
5. Xin grant + read (qua server, khong doc DOM truc tiep):
   - `POST /grant` `{tabId, grant_seq}` -> 200 ok.
   - `POST /read` `{tabId, read: "actor-login"}` -> 200 `AUTHORIZED`.
   - Extension thuc thi func dong goi -> `POST /read-result` (observation
     untrusted, chuyen cho REA/Eye xac minh, khong tu thanh Evidence).
6. Thu hoi: `POST /revoke` -> 200; `GET /tabs` sau revoke khong con fresh.

## Fail-closed (dung la PASS, khong retry vo toi han)

- `/grant` tab chua tung push event -> `TAB_UNKNOWN` (dung).
- Navigation khac origin giua chung -> `ORIGIN_MISMATCH` + grant bi thu hoi.
- `POST /read-result` sai seq / thieu grant -> 403 (dung).
- Bat ky WRITE nao (`click/type/evaluate/...`) -> `ACTION_FORBIDDEN`.

## Ket qua (Lead dien sau live)

- [ ] /health + /tabs PASS (dan output).
- [ ] tab TikTok live: tabId=____ url=____ av=____.
- [ ] grant/read actor-login: PASS / FAIL (error=____).
- [ ] revoke: PASS / FAIL.
- So luot Pair/Grant da dung: ____ / 1.
