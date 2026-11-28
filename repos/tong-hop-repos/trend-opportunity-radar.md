# trend-opportunity-radar

> Evidence-backed social listening and trend research for AI Agents — one topic, one platform, one clear next decision.

- **Nguồn:** `research/repos/trend-opportunity-radar` (v0.14.1 candidate)
- **Bản chất:** Agent Skill độc lập, brand-neutral cho social listening, market research, competitor-user research, content research, product-demand validation.
- **Nguyên tắc:** 1 topic + 1 platform + sampling plan bounded; mở source gốc, phân biệt platform fact / machine extraction / model judgment; yêu cầu counterexample; xuất HTML + MD + JSON local.

## Start in 60 seconds

```bash
npx skills add datou202307-design/trend-opportunity-radar -g
```

Rồi mở Agent task mới và dán first-study request (xem README gốc).

## Điểm chính

- 5 research scenarios, 7 platform research routes.
- So với prompt search 1 dòng: freeze phạm vi, mở source, semantic review + counterexample, kết thúc bằng next test cụ thể (không dự đoán virality/traffic/revenue).
- Báo cáo mẫu trong `case-gallery/`; workspace local riêng tư; state-aware install.
- Song ngữ EN/ZH, MIT license.

## Dùng cho JARVIS

- Khung phương pháp "evidence-backed research" rất hợp để chuẩn hoá output trend của JARVIS: topic + platform + bằng chứng + giới hạn + next action.
- Có thể kết hợp nguồn: tiktok-api / agent-reach (thu thập) → radar skill (phân tích) → báo cáo.
