# openclaw

> Your assistant, on your devices, in your chats.

- **Nguồn:** `research/repos/openclaw`
- **Bản chất:** Trợ lý AI mã nguồn mở chạy trên máy của bạn, gặp mặt trong Discord, iMessage, Slack, Teams, Telegram, WhatsApp + app native macOS/iOS/Android/Windows/Linux.
- **Triết lý:** State/memory/credential nằm trên hardware của bạn; model và harness (Claude, Codex, local) là plugin thay được.

## Cài đặt

```bash
curl -fsSL https://openclaw.ai/install.sh | bash   # macOS/Linux/WSL2
npm install -g openclaw@latest --allow-scripts=openclaw
openclaw onboard --install-daemon
```

Yêu cầu Node 24.22.1+ hoặc 26.12.1+ (khuyên 26), pnpm.

## Điểm chính

- 1 Gateway chạy personal hoặc team deployment, khác nhau ở config.
- Không paid tier/hosted service/token; stewarded bởi OpenClaw Foundation 501(c)(3).
- Telemetry mặc định chỉ version check hàng ngày; stats ẩn danh opt-in.
- Plugin-first: core nhỏ, capability ở edge; skill/tool/model/provider là plugin.
- Skill liên quan: `openclaw-pr-maintainer`, `openclaw-testing`, `control-ui-e2e`, telegram/discord/slack e2e.

## Dùng cho JARVIS

- Tham khảo mô hình Gateway + plugin + multi-channel để đưa JARVIS lên chat app.
- Tham khảo prompt-caching ổn định, audit doctrine, database/state rules.
