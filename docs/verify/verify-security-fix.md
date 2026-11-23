# Biên bản verify fix bảo mật — commit 3a88071

- Commit được kiểm: `3a880719f0dfd9877c4d039c1faa117d5126a85a`
  `fix: actor verify fail-closed mac dinh (chi True ro rang moi post) + origin check scheme/host/port o acquire+navigate ke ca URL cuoi; them test`
- Người kiểm tra (checker): subagent thường trực Miro
- Ngày kiểm: 2026-11-21 (UTC+7)
- Phạm vi: actor verify fail-closed + origin check scheme/host/port ở acquire + navigate + URL cuối.

## 1. Diff đã đọc

- `apps/backend/src/miro/publishing/publisher.py`
  - Cũ (`b2afcdb`): `if ok is False: raise ...; return` → `None`/`"UNKNOWN"`/`0`/`""` lọt qua và được post.
  - Cũ: browser không có `verify_actor`/`declared_actor` thì chỉ chặn khi `MIRO_REQUIRE_ACTOR=1`; mặc định production vẫn cho post.
  - Mới (`3a88071`): `verify_actor` phải trả về đúng `True`, còn lại → `ACTOR_UNVERIFIED` + `before_submit=True`.
  - Mới: không có gì cả → chặn mặc định; chỉ nới lỏng khi `MIRO_ALLOW_UNVERIFIED_ACTOR=1` (test/fake).
- `apps/backend/src/miro/browser/runtime.py`
  - Cũ: `acquire_tab` dùng `url.startswith(o)` → `https://example.com.evil.com` lọt prefix.
  - Cũ: `navigate_tab` không check origin trước `goto`, không check URL cuối sau redirect.
  - Mới: `_origin_of` (scheme/host/port, port mặc định 443/80, host lowercase) + `_check_origin` fail-closed tại acquire, trước `goto`, và sau `goto` (URL cuối).
- Test mới: 5 test origin trong `test_browser_single_owner.py`, 4 test actor trong `test_publisher_threads.py`; mock `MockBrowser`/`ReadOnlyBrowser` bổ sung `verify_actor → True`.

## 2. Lệnh đã chạy + kết quả (tự chạy, không tin báo cáo)

| # | Lệnh (trong `C:\Miro\apps\backend`) | Kết quả |
|---|--------------------------------------|---------|
| 1 | `python -m pytest tests/test_publisher_threads.py tests/test_browser_single_owner.py tests/test_browser_m1.py -q` | **36 passed** (1 warning pytest_asyncio config, không liên quan) |
| 2 | `python -m pytest tests/test_publisher_threads.py -q -k "actor_contract" -v` | **5 passed** (requires_explicit_true, missing_everything_blocks, relaxation_only_with_env, explicit_true_posts, mismatch_blocks cũ) |
| 3 | `python -m pytest tests/test_browser_single_owner.py -q -k "origin or navigate" -v` | **6 passed** (prefix_spoof, scheme_port_mismatch, explicit_default_port, navigate_before_goto, redirect_off_origin + origin cũ) |

## 3. Kết luận từng mục

| Mục kiểm | Kết quả | Bằng chứng |
|----------|---------|------------|
| Actor `None`/`False`/`UNKNOWN` (và `0`/`""`) bị chặn `FAILED_BEFORE_POST`, 0 post | **ĐẠT** | `test_actor_contract_requires_explicit_true` pass; `post_once` raise `AssertionError("must not post...")` nếu bị gọi — không test nào kích hoạt; logic mới `if ok is True: return` + còn lại raise |
| Browser bare (không verify/declared) bị chặn mặc định, chỉ nới lỏng bằng `MIRO_ALLOW_UNVERIFIED_ACTOR=1` | **ĐẠT** | `test_actor_contract_missing_everything_blocks_by_default` + `test_actor_contract_relaxation_only_with_explicit_env` pass |
| `verify_actor → True` rõ ràng thì được post | **ĐẠT** | `test_actor_contract_explicit_true_posts` pass |
| Origin spoof `example.com.evil.com` bị chặn ở acquire | **ĐẠT** | `test_origin_prefix_spoof_rejected_on_acquire` pass (`URL_NOT_REGISTERED`); code cũ `startswith` đã xác nhận lọt |
| Lệch scheme/port bị chặn, port mặc định tương đương được cho qua | **ĐẠT** | `test_origin_scheme_port_mismatch_rejected` + `test_origin_explicit_default_port_allowed` pass |
| Navigate lệch origin bị từ chối TRƯỚC `goto` (`goto_calls == []`) | **ĐẠT** | `test_navigate_enforces_policy_before_goto` pass |
| Redirect mở (URL cuối lệch origin) bị từ chối, record giữ URL cũ | **ĐẠT** | `test_navigate_rejects_redirect_off_origin` pass |

## 4. Kết luận chung

**ĐẠT** — commit `3a88071` sửa đúng 2 lỗ hổng đã nêu, red-test là thật (code cũ `b2afcdb` lọt đúng các case trên), toàn bộ 36 test liên quan pass. Không push (theo yêu cầu).
