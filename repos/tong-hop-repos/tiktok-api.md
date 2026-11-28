# tiktok-api

> Unofficial TikTok API in Python — retrieve data from TikTok.com.

- **Nguồn:** `research/repos/tiktok-api`
- **Bản chất:** Wrapper Python không chính thức để **lấy dữ liệu** TikTok (trending, thông tin user cụ thể...).
- **Giới hạn quan trọng:** KHÔNG post/upload thay user; KHÔNG hỗ trợ route cần login (cái gì logout không xem được thì API cũng không).

## Cài đặt & dùng

```bash
pip install TikTokApi
```

Docs đầy đủ: davidteather.github.io/TikTok-Api. Ví dụ trong `examples/`.

## Điểm chính

- Miễn phí, mã nguồn mở (MIT); tác giả duy trì qua sponsor/GitHub sponsors.
- Hệ sinh thái trả phí liên quan: TikAPI, EnsembleData, TikHub (700+ endpoints đa nền tảng).
- Cần proxy/ẩn danh khi scrape nhiều (Webshare...).

## Dùng cho JARVIS

- Nguồn dữ liệu TikTok cho trend/social listening (chỉ chiều đọc).
- Lưu ý rủi ro: API không chính thức → dễ gãy khi TikTok đổi; cần cơ chế fallback (agent-reach, TikHub...).
