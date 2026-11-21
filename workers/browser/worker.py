"""Browser worker skeleton (Playwright).

Nguồn merge sau: C:\\dubtool\\core\\browser_runtime.py + browser_registry.py,
D:\\JARVIS-Assistant\\backend\\app\\integrations\\live_chrome*.py.
Khung chỉ giữ interface; chưa copy nghiệp vụ.
"""

from dataclasses import dataclass


@dataclass
class BrowserTask:
    task_id: str
    url: str
    action: str = "extract"


def run(task: BrowserTask) -> dict:
    raise NotImplementedError("merge từ nhánh nghiệp vụ (workers/browser)")
