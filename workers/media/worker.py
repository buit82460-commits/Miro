"""Media worker skeleton (ffmpeg).

Nguồn merge sau: C:\\dubtool\\core\\{render,studio_render,editor_media,mix,
audio,ffmpeg_utils}.py. Khung chỉ giữ interface; chưa copy nghiệp vụ.
"""

from dataclasses import dataclass


@dataclass
class MediaJob:
    job_id: str
    render_id: str


def run(job: MediaJob) -> dict:
    raise NotImplementedError("merge từ nhánh nghiệp vụ (workers/media)")
