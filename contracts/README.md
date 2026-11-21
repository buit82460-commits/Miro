# Contracts

Nguồn chân lý cho API Miro. Mọi implementation (backend, workers, web)
phải tuân thủ 2 file schema này.

| Contract | File | Khóa lũy đẳng | Xung đột |
|---|---|---|---|
| Render | `render.json` | `request_id` | cùng mã + khác `(project_id, expected_revision, content_hash)` → `409` + `existing_render_id` |
| Publisher | `publisher.json` | `(publication_id, attempt_id)` | trùng khóa → `201` replay (`replayed: true`), không tạo job mới |

## Render — tóm tắt hành vi

```
POST /renders {request_id, project_id, expected_revision, content_hash, spec}
  -> 201 {render_id, status}                 # lần đầu
  -> 201 {render_id, status, replayed:true}  # retry cùng mã + cùng nội dung
  -> 409 {detail, existing_render_id}        # cùng mã + khác nội dung
GET /renders/{render_id} -> 200 | 404
```

## Publisher — tóm tắt hành vi

```
POST /publications {publication_id, attempt_id, render_id, channel}
  -> 201 {publication_id, attempt_id, status}                 # attempt mới
  -> 201 {..., replayed:true}                                 # retry trùng cặp khóa
GET /publications/{publication_id} -> 200 [attempts] | 404
```
