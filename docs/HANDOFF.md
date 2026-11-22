# HANDOFF（2026-11-22 時点）

## 目的
mediaforge のパッケージ更新・堅牢化・systemd 同梱（認証なし・0.0.0.0 待ち受けは意図なので変えない）。

## できたこと（すべて commit 済み・未 push）
- 依存を最新へ（fastapi 0.165.0 / uvicorn 0.54.0 / psutil 7.2.2 / aiofiles 25.1.0 / python-multipart 0.0.34）。`.venv` で起動・動画→GIF・ダウンロード・ブラウズの動作確認済み。`requirements.txt`（直接）と `requirements.lock`（全固定）。`run.sh` は .venv の python を使う
- yt-dlp を 2026.10.26 へ（pipx）。URL は http(s) のみ、`--` を挟む
- `DELETE /api/output-files` は outputs/downloads/uploads 内のみ（外は 403）
- main.py: yt-dlp フォーマット取得にタイムアウト、ffprobe/yt-dlp の JSON エラー処理、`/api/system` のブロック回避、Task 参照保持、永続化ファイルのアトミック書き込み、ダウンロード名のエンコード
- Tailwind 3.4.17 とフォント 4 種を `static/vendor/` に同梱（外部通信なし）。旧版とのスクショ差 0.02%、screen-auditor は崩れなし
- README・CONTEXT を最新化（旧名 ffmpeg_studio を mediaforge に。ADR に旧名は無かった）
- systemd user unit: `systemd/mediaforge.service`（ひな形）と `systemd/install.sh`

## 残り・注意
- **systemd の実インストール（`./systemd/install.sh`）は自動判定で拒否されたため未実行**。unit のひな形は `systemd-analyze verify` で警告なし、install.sh は構文確認のみ
- push は未実施（本人の確認待ち）
- 作業中のテストで作った `.venv` は .gitignore 済み

## 次にやること
本人が `./systemd/install.sh` を実行し、`curl localhost:7860/` で確認。
