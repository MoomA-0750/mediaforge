# Unified job queue across all Tools

All Tools (ffmpeg, ImageMagick, yt-dlp) share a single in-memory job queue exposed at `/api/jobs`. Job Type distinguishes which Tool runs. The Queue UI filters by Tool rather than showing separate queues.

The alternative was a separate endpoint and state dict per Tool (`/api/image-jobs`, `/api/download-jobs`). That would have given each Tool an independent lifecycle, but would have duplicated the progress-streaming, cancellation, and log infrastructure three times. Since every Job shares the same lifecycle shape — pending → running → done/error/cancelled — there is no behaviour that separate queues would have handled better. The filter UI in the Queue tab recovers the per-tool view without the duplication cost.
