# Miro Capability Map — 52 lĩnh vực / 12 nhóm

> Bản đồ quy hoạch năng lực tham khảo cho Miro. Đây là **tài liệu quy hoạch**,
> chưa phải code, chưa phải contract, chưa phải biên bản verify.
> Không repo nào trong này được tự động đưa vào source — mỗi repo muốn thử nghiệm
> phải có task/nhánh riêng và tuân thủ `docs/PLATFORM_RUNBOOK.md`.

- Ngày chốt danh sách: 2026-11-23
- Tổng: **52 lĩnh vực / 12 nhóm / 52 repo đề xuất**
- Top 10 ưu tiên nghiên cứu: xem §13

## Nguyên tắc tích hợp (cứng)

1. Mọi thao tác trình duyệt qua Browser Gateway (`miro/browser/gateway.py`), luật REA-mắt.
2. Mỗi platform đúng 1 adapter (xem `docs/PLATFORM_RUNBOOK.md`).
3. Công cụ điều khiển đi qua permission + lock hiện tại của Miro.
4. Publication + journal là source of truth; UNKNOWN không replay.

## 1. Nhận thức & Trí tuệ AI (01–05)

| STT | Lĩnh vực | Repo đề xuất | Ứng dụng cho Miro | Trạng thái Miro | Module liên quan |
| --- | --- | --- | --- | --- | --- |
| 01 | Computer Vision | [OpenCV](https://github.com/opencv/opencv) | Nhận diện hình ảnh, xử lý frame, theo dõi vật thể |  |  |
| 02 | Video Understanding | [VideoLLaMA3](https://github.com/DAMO-NLP-SG/VideoLLaMA3) | Hiểu nội dung, hành động và diễn biến video |  |  |
| 03 | Audio Intelligence | [pyannote-audio](https://github.com/pyannote/pyannote-audio) | Xác định ai đang nói và phân đoạn người nói |  |  |
| 04 | Multimodal Reasoning | [Qwen2.5-VL](https://github.com/QwenLM/Qwen2.5-VL) | Kết hợp hình ảnh và văn bản để hiểu tình huống |  |  |
| 05 | Spatial Reasoning | [Nerfstudio](https://github.com/nerfstudio-project/nerfstudio) | Nghiên cứu tái tạo không gian 3D từ hình ảnh |  |  |

Ghi chú: VideoLLaMA3 bổ sung khả năng hiểu nội dung video, khác với `rea-video`
vốn tập trung phân tích cách video được sản xuất.

## 2. Tư duy & Điều phối Agent (06–10)

| STT | Lĩnh vực | Repo đề xuất | Ứng dụng cho Miro | Trạng thái Miro | Module liên quan |
| --- | --- | --- | --- | --- | --- |
| 06 | Autonomous Planning | [LangGraph](https://github.com/langchain-ai/langgraph) | Xây dựng workflow Agent có trạng thái |  |  |
| 07 | Multi-Agent Collaboration | [CrewAI](https://github.com/crewAIInc/crewAI) | Phối hợp nhiều Agent chuyên trách |  |  |
| 08 | Self-Reflection & Verification | [Inspect AI](https://github.com/UKGovernmentBEIS/inspect_ai) | Đánh giá và kiểm thử hành vi AI Agent |  |  |
| 09 | Skill Discovery | [Skills](https://github.com/vercel-labs/skills) | Tìm, quản lý và cài đặt Agent Skills |  |  |
| 10 | Constraint Solving | [OR-Tools](https://github.com/google/or-tools) | Lập lịch và phân bổ tác vụ có ràng buộc |  |  |

Ghi chú: LangGraph và CrewAI đều có thể điều phối Agent, nhưng không nên triển
khai hai bộ orchestrator độc lập nếu Miro đã có tầng điều phối riêng.

## 3. Điều khiển & Automation (11–15)

| STT | Lĩnh vực | Repo đề xuất | Ứng dụng cho Miro | Trạng thái Miro | Module liên quan |
| --- | --- | --- | --- | --- | --- |
| 11 | Desktop Automation | [Microsoft UFO](https://github.com/microsoft/UFO) | Điều khiển ứng dụng Windows bằng Agent |  | agent-desktop |
| 12 | Browser Automation | [browser-use](https://github.com/browser-use/browser-use) | Điều khiển và tương tác website |  |  |
| 13 | Mobile Automation | [Appium](https://github.com/appium/appium) | Automation ứng dụng Android/iOS |  |  |
| 14 | Terminal & File Automation | [Open Interpreter](https://github.com/openinterpreter/open-interpreter) | Thực thi code, shell và thao tác file |  |  |
| 15 | Remote Computer Control | [RustDesk](https://github.com/rustdesk/rustdesk) | Truy cập và điều khiển máy tính từ xa |  |  |

Ghi chú: Microsoft UFO đáng nghiên cứu — tương tác Windows qua UI Automation API,
phối hợp GUI với native API, rất đáng tham khảo cho `agent-desktop`.

## 4. Giao tiếp & Tương tác con người (16–20)

| STT | Lĩnh vực | Repo đề xuất | Ứng dụng cho Miro | Trạng thái Miro | Module liên quan |
| --- | --- | --- | --- | --- | --- |
| 16 | Conversational Agent | [Rasa](https://github.com/RasaHQ/rasa) | Quản lý luồng hội thoại và ngữ cảnh |  |  |
| 17 | Real-time Voice Agent | [Pipecat](https://github.com/pipecat-ai/pipecat) | Xây dựng trợ lý giọng nói thời gian thực |  |  |
| 18 | Human-in-the-loop | [i-am-not-a-robot](https://github.com/mcpware/i-am-not-a-robot) | Chuyển CAPTCHA cho người dùng xác minh |  |  |
| 19 | Meeting Assistant | [Meetily](https://github.com/Zackriya-Solutions/meetily) | Ghi âm, chuyển lời nói thành văn bản, tóm tắt họp |  |  |
| 20 | Multilingual Communication | [Seamless Communication](https://github.com/facebookresearch/seamless_communication) | Dịch và xử lý giao tiếp đa ngôn ngữ |  |  |

Ghi chú: Meetily đáng nghiên cứu vì xử lý cuộc họp on-device, hỗ trợ
transcription và speaker diarization.

## 5. Sáng tạo & Sản xuất Media (21–25)

| STT | Lĩnh vực | Repo đề xuất | Ứng dụng cho Miro | Trạng thái Miro | Module liên quan |
| --- | --- | --- | --- | --- | --- |
| 21 | Image Generation & Editing | [ComfyUI](https://github.com/Comfy-Org/ComfyUI) | Tạo và chỉnh sửa ảnh bằng workflow AI |  |  |
| 22 | AI Video Production | [rea-video](https://github.com/JuneYaooo/rea-video) | Phân tích ngược video, tạo kế hoạch remake |  | rea-video |
| 23 | Voice Dubbing & Lip-sync | [LinlyDubbing](https://github.com/kikokang/LinlyDubbing) | Dịch video, lồng tiếng và xử lý lip-sync |  |  |
| 24 | Motion Graphics & 3D | [Remotion](https://github.com/remotion-dev/remotion) | Tạo motion graphics và dựng video bằng code |  | media pipeline |
| 25 | Character Consistency | [InstantID](https://github.com/instantX-research/InstantID) | Giữ đặc điểm nhận dạng nhân vật khi tạo ảnh |  |  |

Pipeline gợi ý: `rea-video → phân tích → tạo ảnh/video → lồng tiếng → dựng bằng
Remotion → kiểm tra → render`. Giữ nhân vật nhất quán suốt video vẫn cần kiểm
soát thêm qua các frame và model video.

## 6. Lập trình & Phát triển phần mềm (26–30)

| STT | Lĩnh vực | Repo đề xuất | Ứng dụng cho Miro | Trạng thái Miro | Module liên quan |
| --- | --- | --- | --- | --- | --- |
| 26 | Coding Agent | [OpenHands](https://github.com/OpenHands/OpenHands) | Viết, sửa, chạy và kiểm tra code |  |  |
| 27 | Codebase Understanding | [Zoekt](https://github.com/sourcegraph/zoekt) | Index và tìm kiếm code trong repository |  |  |
| 28 | Automated Testing | [Playwright](https://github.com/microsoft/playwright) | Kiểm thử website và thao tác trình duyệt |  |  |
| 29 | DevOps & Deployment | [GitHub Actions Runner](https://github.com/actions/runner) | Thực thi job CI/CD |  |  |
| 30 | Database Agent | [DB-GPT](https://github.com/eosphoros-ai/DB-GPT) | Xây dựng trợ lý AI làm việc với dữ liệu |  |  |

Ghi chú: Zoekt đặc biệt hữu ích với codebase lớn nhờ khả năng index và tìm kiếm source code.

## 7. Dữ liệu & Nghiên cứu (31–34)

| STT | Lĩnh vực | Repo đề xuất | Ứng dụng cho Miro | Trạng thái Miro | Module liên quan |
| --- | --- | --- | --- | --- | --- |
| 31 | Deep Research | [GPT Researcher](https://github.com/assafelovic/gpt-researcher) | Tự nghiên cứu, thu thập và tổng hợp nguồn |  |  |
| 32 | Document Intelligence | [Docling](https://github.com/docling-project/docling) | Trích xuất nội dung và cấu trúc tài liệu |  |  |
| 33 | Web Data Extraction | [Firecrawl](https://github.com/firecrawl/firecrawl) | Thu thập dữ liệu website cho AI |  |  |
| 34 | Data Analysis | [Pandas](https://github.com/pandas-dev/pandas) | Phân tích và xử lý bảng dữ liệu |  |  |

## 8. Memory & Cá nhân hóa (35–38)

| STT | Lĩnh vực | Repo đề xuất | Ứng dụng cho Miro | Trạng thái Miro | Module liên quan |
| --- | --- | --- | --- | --- | --- |
| 35 | Long-term Agent Memory | [Mem0](https://github.com/mem0ai/mem0) | Lưu và truy xuất memory cho Agent |  |  |
| 36 | Personal Knowledge Base | [Khoj](https://github.com/khoj-ai/khoj) | Tìm kiếm kiến thức cá nhân bằng AI |  |  |
| 37 | Preference Learning | [Graphiti](https://github.com/getzep/graphiti) | Lưu quan hệ, sự kiện và ngữ cảnh theo thời gian |  |  |
| 38 | Adaptive Learning Assistant | [Anki](https://github.com/ankitects/anki) | Tham khảo spaced repetition để cá nhân hóa việc học |  |  |

Ghi chú: Anki không phải AI Tutoring Agent hoàn chỉnh — phù hợp để nghiên cứu
thuật toán ôn tập và quản lý tiến độ học.

## 9. Tự động hóa công việc (39–42)

| STT | Lĩnh vực | Repo đề xuất | Ứng dụng cho Miro | Trạng thái Miro | Module liên quan |
| --- | --- | --- | --- | --- | --- |
| 39 | Email & Calendar Agent | [n8n](https://github.com/n8n-io/n8n) | Tạo workflow xử lý email, lịch và thông báo |  |  |
| 40 | Office Automation | [ONLYOFFICE DocumentServer](https://github.com/ONLYOFFICE/DocumentServer) | Xem và chỉnh sửa tài liệu Office |  |  |
| 41 | Business Process Automation | [Activepieces](https://github.com/activepieces/activepieces) | Tự động hóa quy trình giữa nhiều dịch vụ |  |  |
| 42 | Social Media Management | [Postiz](https://github.com/gitroomhq/postiz-app) | Lên lịch và quản lý xuất bản nội dung |  |  |

Ghi chú: Postiz là nguồn tham khảo cho Social Media Management, nhưng cần xem lại
hỗ trợ nền tảng, OAuth và giấy phép AGPL-3.0 trước khi tích hợp.

## 10. Security & Reliability (43–46)

| STT | Lĩnh vực | Repo đề xuất | Ứng dụng cho Miro | Trạng thái Miro | Module liên quan |
| --- | --- | --- | --- | --- | --- |
| 43 | Sandbox & Permission Control | [E2B Infrastructure](https://github.com/e2b-dev/infra) | Nghiên cứu môi trường thực thi code cách ly |  |  |
| 44 | Secrets & Identity Management | [HashiCorp Vault](https://github.com/hashicorp/vault) | Quản lý secret, token và API key |  |  |
| 45 | Prompt Injection Defense | [LLM Guard](https://github.com/protectai/llm-guard) | Phát hiện, lọc và kiểm tra dữ liệu đầu vào AI |  |  |
| 46 | Privacy & Data Protection | [Presidio](https://github.com/data-privacy-stack/presidio) | Nhận diện và ẩn dữ liệu cá nhân nhạy cảm |  |  |

Ghi chú: LLM Guard chỉ là một lớp bảo vệ bổ sung, không thay thế permission,
sandbox và kiểm soát quyền thực thi.

## 11. Hạ tầng & Vận hành (47–49)

| STT | Lĩnh vực | Repo đề xuất | Ứng dụng cho Miro | Trạng thái Miro | Module liên quan |
| --- | --- | --- | --- | --- | --- |
| 47 | Durable Workflow Execution | [Temporal](https://github.com/temporalio/temporal) | Phục hồi workflow sau sự cố |  |  |
| 48 | Model Routing & Local Inference | [LiteLLM](https://github.com/BerriAI/litellm) | Định tuyến request tới nhiều LLM provider |  |  |
| 49 | Resource Scheduling | [Ray](https://github.com/ray-project/ray) | Phân phối và lập lịch tác vụ tính toán |  |  |

Ghi chú: LiteLLM giải quyết kết nối và định tuyến model, không tự cung cấp local
inference engine. Nếu cần chạy model trực tiếp trên Windows, nghiên cứu bổ sung
[Ollama](https://github.com/ollama/ollama).

## 12. Event-driven & Chủ động (50–52)

| STT | Lĩnh vực | Repo đề xuất | Ứng dụng cho Miro | Trạng thái Miro | Module liên quan |
| --- | --- | --- | --- | --- | --- |
| 50 | Event Intelligence & Watchers | [Chokidar](https://github.com/paulmillr/chokidar) | Theo dõi sự kiện thay đổi file |  |  |
| 51 | Proactive Automation | [Windmill](https://github.com/windmill-labs/windmill) | Chạy workflow theo trigger và lịch |  |  |
| 52 | Observability & Anomaly Detection | [Langfuse](https://github.com/langfuse/langfuse) | Theo dõi LLM calls, traces và hỗ trợ phân tích lỗi |  |  |

Ghi chú: Chokidar là file watcher, không trực tiếp theo dõi DOM hoặc tin nhắn
website. Để triển khai mục 50 cho Chrome, Miro vẫn cần `MutationObserver`, event
listener và event bridge qua Extension hoặc Browser Runtime.

## 13. Top 10 ưu tiên nghiên cứu

| Hạng | Repo | Vai trò cho Miro |
| --- | --- | --- |
| 1 | VideoLLaMA3 | Hiểu video — bổ sung khả năng hiểu nội dung video cho rea-video |
| 2 | Microsoft UFO | Desktop Agent — học cách kết hợp GUI và Windows native API |
| 3 | LangGraph | Agent Orchestration — điều phối Agent, trạng thái và luồng thực thi |
| 4 | Temporal | Workflow Recovery — tăng khả năng phục hồi nhiệm vụ dài |
| 5 | Pipecat | Real-time Voice — hướng tới giao tiếp trực tiếp bằng giọng nói |
| 6 | Mem0 | Agent Memory — ghi nhớ kinh nghiệm và ngữ cảnh dài hạn |
| 7 | LiteLLM | Model Routing — chọn LLM provider tùy yêu cầu và chi phí |
| 8 | Langfuse | Observability — truy dấu lỗi và quan sát từng bước Agent |
| 9 | Docling | Document AI — đọc hiểu và cấu trúc hóa tài liệu |
| 10 | LLM Guard | Security — bổ sung lớp phát hiện dữ liệu đầu vào nguy hiểm |

## 14. Bước tiếp theo

Đối chiếu từng repo với các phần Miro đã có (`agent-desktop`, REA, `rea-video`,
browser controller, media pipeline), đánh dấu vào cột **Trạng thái Miro**:
`Đã có / Đang phát triển / Cần nâng cấp / Chưa có` — rồi chỉ thử nghiệm những
repo đem lại năng lực mới thực sự.
