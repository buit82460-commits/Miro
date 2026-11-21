# HỎI-tab-01: targetId thật lấy bằng cách nào khi page không có attr target_id

## Câu hỏi (bên hỏi: C)

- Khâu: tab (luật 1-tab)
- File C đang port: `apps/backend/src/miro/browser/live_chrome.py` (`_cdp_target_id`)
- File A/B gốc: `C:\dubtool\core\browser_runtime.py:70-75` (`_target` qua `new_cdp_session`)
- Hỏi gì: A lấy targetId thật qua `session.send('Target.getTargetInfo')`. C port fallback `live-{id(page):x}` khi page fake không có attr. Hỏi A: ngoài `getTargetInfo` còn đường nào lấy targetId ổn định hơn cho Playwright page đã có? Có nên cache theo `id(page)` không?

## Trả lời

- Bên trả lời (A/B/C):
- Đáp + bằng chứng file:dòng:
- Kết luận port thế nào:

## Trạng thái

- [x] Đang hỏi
- [ ] Đã đáp, chờ port
- [ ] Đã port + test, chờ Checker
- [ ] XONG
