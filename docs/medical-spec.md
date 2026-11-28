# Spec đầy đủ file medical.html (để dựng lại)

> Nguồn: `prototype/taste-demo/medical.html` (364 dòng, 1 file duy nhất, không phụ thuộc). Font Inter 400–800 qua Google Fonts. Ảnh avatar `i.pravatar.cc`.

## 1. Token màu (:root)

| Token | Giá trị | Dùng ở đâu |
|---|---|---|
| `--blue` | `#2f38f0` | nút primary, số lớn, ngày chọn, pill b |
| `--blue2` | `#3b43f2` | (khai báo, ít dùng) |
| `--ink` | `#17183a` | chữ chính body |
| `--mut` | `#6e7191` | chữ phụ |
| `--mut2` | `#9a9cb5` | chữ mờ (label, `...`, th bảng) |
| `--line` | `#ececf3` | viền card/topbar/sidebar |
| `--card` | `#ffffff` | nền card |
| `--bg` | `#f6f6fb` | nền shell trong |
| `--yellow` | `#fdf0a3` | badge, pro-pill, pill y |
| `--green-bg` | `#e7f7ec` | nền pill g |
| `--green` | `#0ca34e` | chữ pill g |
| `--red-bg` | `#fdeceb` | nền pill r |
| `--red` | `#c9342c` | chữ pill r |
| `--lav` | `#ebeaff` | (khai báo) |
| `--radius` | `18px` | radius card chuẩn |
| Màu lẻ trong file | `#f2f2fd` (menu active), `#e9e9fd` (card lav), `#eef0ff/#dfe1fb` (slot), `#e7f7ec/#c9ecd4` (slot g), `#fff8dd/#efe08a` (slot y), `#22244a` (popup tối), `#353861` (nút popup), `#ffd84d` (chấm vàng), `#6a1de0` (viền bar + số donut), `#f6b9f2/#a9dcf5/#8a8df8` (donut), `#9be3d0` (legend), `#a48cf7` (pbar) | chi tiết từng khối dưới |

## 2. Font + chữ

- Family: `"Inter","Segoe UI",system-ui,sans-serif` (body), form inherit.
- Weight dùng: 400 (sub), 500 (menu/label/chead), 600 (th, pill, calhead, form label), 700 (welcome, btn, badge, phead, dpill), 800 (logo, bignum, ngày chọn, ptitle).
- Size: body mặc định 16 → các khối: mlabel 12, cmd/dpill/pill 12, sub/ptitle p 13.5, user span 12, btn/form input/tbl 14, menu/chead 15, procard h3 17 = calhead h3 17, phead h3 18, logo 22, ptitle h2 24, welcome 25, donut b 31, bignum 37.
- Letter-spacing: logo +.01em, mlabel +.14em, tbl th +.06em, welcome −.01em, ptitle h2 −.01em, bignum −.02em.

## 3. Khung trang (width/height)

- `body`: nền `linear-gradient(180deg,#b3b2f2,#dcd9f8 55%,#efedfd)`, `min-height:100vh`, `padding:26px`.
- `.shell`: `max-width:1560px`, margin auto, nền `var(--bg)`, `radius:26px`, `overflow:hidden`, shadow `0 30px 80px rgba(80,80,180,.28)`.
- `.layout`: grid `262px 1fr`, `min-height:900px`.
- `.main`: `padding:18px 20px 22px`, grid `gap:18px`.
- Responsive `@media(max-width:1150px)`: layout 1 cột, stats 2 cột, mid/bot 1 cột, ẩn sidebar.

## 4. Topbar (13px 24px, nền trắng, viền dưới)

- `.topbar`: flex, gap 14, `padding:13px 24px`, viền dưới `1px var(--line)`.
- Logo: 22px/800, icon `.ic` 42×42 radius 12 gradient `135deg,#8b8dfc→#2f38f0`, chữ trắng, shadow `0 4px 12px rgba(47,56,240,.4)`.
- `.hicon` 34×34 radius 9; `.back` 30×30 tròn viền + shadow `0 2px 8px rgba(0,0,0,.08)`.
- `.welcome` 25px/700.
- `.search` margin-left auto, gap 12. `.sbox`: viền `#e3e3ee`, radius 11, `padding:10px 14px`, `width:252px`; input border 0, 14px; `.cmd` 12px mờ.
- `.btn`: radius 11, `padding:11px 18px`, viền `#e2e2ef`, 700/14px, inline-flex gap 8. `.primary`: nền+viền blue, chữ trắng, shadow `0 6px 14px rgba(47,56,240,.35)`.

## 5. Sidebar (262px, nền trắng, viền phải)

- `aside`: viền phải line, `padding:20px 16px 16px`, flex column.
- `.mlabel`: 12px, ls .14em, mờ, 500, margin `10px 10px 8px`. Hai nhóm: MAIN MENU / MANAGEMENT.
- `.mi`: flex gap 12, `padding:11px 12px`, radius 11, 15px/500, màu `#3c3d58`. `.active`: nền `#f2f2fd`, chữ blue, 700.
- `.badge`: margin-left auto, nền yellow, chữ `#5c5510`, 12px/700, radius 20, `padding:3px 10px` (Message 10, Notification 12). `.chev` mờ.
- `.pro` margin-top auto. `.procard`: nền `#f5f5fb`, radius 16, padding 16. `.pro-pill` nền yellow 12/700 radius 16 padding `4px 12px`. h3 17px, p 13px `#5c5c74`. Nút Renew/Cancel: flex 1, radius 24, padding 10 0.
- `.user`: flex gap 10, `margin-top:14px`, `padding:12px 6px 2px`, viền trên. Avatar 46×46 tròn. b 14px, span 12px mờ.

## 6. Khối dùng chung

- `.card`: nền trắng, viền line, radius 18, `padding:16px 18px`. `.lav`: nền `#e9e9fd`, viền `#e2e1fb`.
- `.chead`: flex gap 9, 15px/500, màu `#3c3d58`. `.cicon` 34×34 tròn, nền `#f1f1fa` viền `#e4e4f0`. `.dots` margin-left auto, mờ, ls 2px, 800.
- `.bignum`: 37px/800, ls −.02em, margin `10px 0 6px`, flex gap 10. `.blue` chữ blue.
- `.dpill`: 12px/700, radius 20, `padding:4px 10px`. `.r` nền `#fde9e4` chữ `#c0532f`; `.g` nền `#e3f6e9` chữ `#0e9b4d`.
- `.sub`: 13.5px, màu `#3c3d58`, lh 1.45.
- `.pbar`: nền `#f1f1f7`, radius 8, `height:26px`, relative, margin-top 12, overflow hidden. `i` absolute trái gradient `90deg,#a48cf7→#2f38f0` radius 8. `span` absolute phải 10/top 4, 12px mờ.
- `.pill` (trạng thái): margin-left auto, 12px/600, radius 16, `padding:5px 12px`. g: nền green-bg/chữ green/viền `#c9ecd4`. r: nền red-bg/chữ red/viền `#f5cfc9`. y: nền yellow/chữ `#6b5d00`/viền `#efe08a`. b: nền `#e8e9ff`/chữ blue/viền `#d3d5fb`.
- `.ptitle`: flex gap 12. h2 24px/800 ls −.01em. p 13.5px mờ.
- `.toolbar`: flex gap 10 wrap. `.sbox` trong toolbar `width:280px`.
- `.tbl`: full width, collapse, 14px. th trái, 12px, ls .06em, mờ2, 600, `padding:10px 12px`, viền dưới line. td `padding:12px`, viền dưới `#f0f0f6`. Hàng cuối không viền.
- `.form`: grid 2 cột gap 14. label 13px/600 `#3c3d58` grid gap 6. input/select viền `#e3e3ee` radius 11 `padding:11px 13px` 14px nền trắng. `.full` span 2 cột.
- `.kv`: grid 4 cột gap 18.

## 7. Dashboard (trang mặc định)

- `.stats`: grid `1.08fr 1fr 1fr 1fr` gap 18.
  - Card 1 (lav): Total doctors, `300+` + dpill r `↓ 2.5%`, minibars 4 cột (`width:30px` radius 8 gradient `180deg,#b9baff→#4a53f5`, cao 52/30/44/56) + sub 3 dòng.
  - Card 2: Book appointment `15.140` + dpill g `↑ 3.5%`, sub 2 dòng, pbar 46% + "1.435 today".
  - Card 3: Room availability `15.140` + dpill g `↑ 500`, 2 `.roomrow` (flex gap 10, 14px; b margin-left auto 15px; `.ric` 28×28 tròn; General `#e3f2fd` 100, Private `#fdf0a3` 75).
  - Card 4: Overall visitor `1.140` + dpill g, sub, pbar 52% + "1.000 today".
- `.mid`: grid `1fr 420px` gap 18.
  - Patient overview: `.phead` (icon 18px, h3 18/700, `.select` margin-left auto viền radius 11 `padding:9px 14px` 14px/500 nền trắng, `.iconbtn` viền radius 11 42×42 nền trắng). `.legend` flex gap 18, 13.5px; `.dot` 9×9 tròn. `.chart` grid `64px 1fr 44px` gap 6. `.yaxis` column space-between 12px mờ, padding `6px 0 26px`. `.plot` relative. `.grid` absolute 5 đường dashed `#e3e3ec`. `.bars` grid 7 cột gap 22, cao 236, padding `0 14px`. `.bar` radius 11 relative: `.lite` absolute top −34 nền `#ececfb` radius 11; `.deep` absolute bottom gradient `180deg,#9a96fb→#2f38f0` radius 11. Cao lite/deep từng cột: (150/70) (170/110) (190/140 + outline `3px #6a1de0` radius 13) (0/80) (0/92) (170/130) (155/112). `.xlabels` grid 7 gap 22, 12.5px mờ. `.tooltip` absolute left 38% top −6, nền trắng viền line radius 12 shadow `0 14px 34px rgba(20,20,60,.16)` padding `12px 16px` 13px `width:238px`; 3 dòng chấm 18px viền 3px.
  - Lịch: `.calhead` flex space-between, h3 17/600, `.navbtn` 38×38 radius 10 viền nền trắng. `.dow` grid 7, 12.5px/700 `#6a6c85`, margin `14px 0 4px`. `.days` grid 7, 14px `#2b2c46`; span `padding:11px 0` radius 10; `.dim` `#b3b4c6`; `.sel` nền blue chữ trắng 800 + shadow blue + `::after "••"` 9px `#ffd84d` đáy. `.apop` nền `#22244a` chữ trắng radius 14 `padding:14px 16px` margin-top 12 13px; h4 13/600; `.r` flex space-between padding 5 0; `.adot` 8×8 tròn; `.addbtn` margin-top 10 nền `#353861` chữ `#cfd0e6` radius 9 padding 9 600 giữa.
- `.bot`: grid `1fr 1.15fr 1.15fr` gap 18.
  - Donut: `.donutwrap` giữa padding `8px 0 4px`. `.donut` 236×236 tròn `conic-gradient(from -40deg,#2f38f0 0 22%,#f6b9f2 22% 52%,#a9dcf5 52% 76%,#8a8df8 76% 100%)` giữa; `::before inset:34px` nền trắng tròn. `.dcenter` giữa: small 13px mờ, b 31px/800 `#6a1de0` (500). `.dleg` flex gap 14 giữa 13px.
  - Doctor's schedule: `.avtotals` viền line radius 13 `padding:12px 16px` grid 3: b 15px, `.n` 21/800, small mờ. p 14px mờ margin `12px 0 4px`. `.drow` flex gap 12 `padding:11px 2px` viền dưới `#f0f0f6` 14px; img 42×42 tròn; small mờ.
  - Appointment: 5 `.arow` flex gap 12 `padding:10px 2px` viền dưới; img 44×44 tròn; `.t` margin-left auto phải, small mờ, b 15px. Hàng cuối không viền.

## 8. 9 trang còn lại (chuyển bằng click menu, JS cuối file)

- **Message** (`pg-message`): ptitle + select. Grid `1fr 1.4fr` gap 18. Trái 4 `.msg` (flex gap 12, `padding:12px 2px`, viền dưới, 14px; img 44 tròn; pill b/g/y). Phải header b + pill g Online + dots; 2 bong bóng (trái nền `#f2f2fd` radius 12 padding `10px 14px`; phải nền blue chữ trắng, row-reverse phải); toolbar input + Send.
- **Schedule** (`pg-schedule`): ptitle + Export/New session. Card `.sched` grid `110px 1fr`: `.hh` padding `14px 6px` mờ viền dưới dashed; `.slot` margin `8px 0` nền `#eef0ff` viền `#dfe1fb` radius 12 padding `10px 14px`; `.g` nền `#e7f7ec`/viền `#c9ecd4`; `.y` nền `#fff8dd`/viền `#efe08a`. 5 mốc 09/11/13/15/16h.
- **Notification** (`pg-notif`): kv 4 card (System 4, Appointments 5, Pharmacy 2, Beds 1 + sub). Card list 3 `.msg` icon 20px + pill System/Booking/Stock.
- **Transaction** (`pg-trans`): kv 4 (lav Total revenue `$84.200` + g 8.1%; Paid 1.204; Pending 86; Refunded 12). Bảng INVOICE/PATIENT/CLINIC/AMOUNT/STATUS, 4 hóa đơn `#INV-9041→38` ($240/180/320/150, Paid/Pending/Overdue).
- **Doctor** (`pg-doctor`): ptitle + search + Add doctor. Bảng DOCTOR/SPECIALTY/PATIENTS/SCHEDULE/STATUS, 4 bác sĩ (Lutfi 128, Nasrul 214, Albert 96, Benu 120) kèm avatar + pill.
- **Medicine** (`pg-medicine`): kv 4 (In stock 1.392; Low 62 + dpill r restock; Expiring 26; lav Out of stock 0). Bảng MEDICINE/CATEGORY/STOCK/EXPIRY/STATUS, 4 thuốc (Amoxicillin 40 Low, Paracetamol 320 Expiring, Omeprazole 210 OK, Salbutamol 88 OK).
- **Bedroom** (`pg-bedroom`): kv 4 (General 82/100 + pbar 82%; Private 68/75 + pbar 90%; Cleaning 9; lav Ready 16). Bảng ROOM/TYPE/PATIENT/SINCE/STATUS, 4 phòng (G-101 Occupied, G-102 Ready, P-201 Occupied, P-202 Cleaning).
- **Appointment** (`pg-appoint`): form card (Patient/Clinic/Doctor/Date/Note full) + Book/Cancel; bảng PATIENT/CLINIC/TIME/DOCTOR/STATUS, 4 lịch 09:40 Today (Confirmed/Waiting).
- **Patient** (`pg-patient`): kv 4 (lav Total 1.140 + g; Dental 120; Internist 249; Neurologist 165). Bảng PATIENT/CLINIC/LAST VISIT/NEXT/STATUS, 4 bệnh nhân kèm avatar (Active/Follow-up).

## 9. JS + ảnh

- Script cuối: click `.mi[data-page]` → đổi active, hiện `.page` tương ứng (`pg-...`), đổi `.welcome` theo map titles, scroll top.
- Ảnh duy nhất: avatar `https://i.pravatar.cc/84|88|92?img=...`. Không chart lib — bars/donut/minibars/pbar đều CSS thuần.
