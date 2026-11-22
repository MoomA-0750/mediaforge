# HANDOFF（2026-11-23 時点・「今の状態」として上書き）

## 目的
mediaforge（ffmpeg / ImageMagick / yt-dlp のローカル Web UI、FastAPI + 単一 index.html）の依存更新・堅牢化・systemd 同梱・M3 Expressive 化。認証なし・0.0.0.0 待ち受けは本人の意図なので変えない。

## 今どこまでできたか
- 依存を最新に固定（`requirements.txt` 直接 / `requirements.lock` 全固定、`.venv`、`run.sh` は .venv の python）。fastapi 0.165.0 / uvicorn 0.54.0 / psutil 7.2.2 / aiofiles 25.1.0 / python-multipart 0.0.34
- yt-dlp 2026.10.26（pipx）。URL は http(s) のみ、`--` を挟む
- `DELETE /api/output-files` は outputs/downloads/uploads 内のみ（外は 403）。ブラウズ・読み出しは制限しない（意図）
- main.py の堅牢化（yt-dlp タイムアウト、JSON エラー処理、`/api/system` の非ブロック化、Task 参照保持、永続化の原子的書き込み、ダウンロード名のエンコード）
- Tailwind 3.4.17 とフォントを `static/vendor/` に同梱（外部通信なし）
- README・CONTEXT 更新（旧名 ffmpeg_studio は README のみにあり修正済み。ADR に旧名なし）
- systemd user unit を登録・起動済み（`systemd/install.sh`、`mediaforge.service` は enabled / active、http 200 確認、Linger=yes 済み）。操作は README 参照
- M3 Expressive の上書き層を `static/index.html` の `<style>` 末尾に追加（形・動き・state layer・switch・slider・nav）。Tailwind の radius も拡大。CRF/Bitrate 切替の未選択表示、スマホ下部ナビの切れ、select の省略も対応。確認は Video・Download（ダーク／ライト・デスクトップ／スマホ幅）のみ

## 残っていること
- 未確認の画面: Files・Queue・Image・Trim/Crop・Settings・ダッシュボードの M3E 見た目（撮って見ていない）
- 任意: フォントを Roboto Flex に替える（今は Inter のまま）
- 未対応の軽微な点: サイドバーの CPU バーが値よりやや長く見えることがある（更新タイミングの見え方と判断）

## 次のセッションが最初にやること
1. `git status` / `git log origin/main..HEAD` で未 push を確認
2. 本人の判断（下記）を確認してから push
3. 未確認画面を撮って screen-auditor に回し、崩れがあれば `static/index.html` の「Material 3 Expressive layer」ブロックを直す

## 本人の判断待ち（確認一覧にも記録済み: 2026-11-23/mediaforge-4f1cb39a.md#M3E 化）
- M3E 化の commit 3 件（ccefc63 / 05372f7 / 76f42c1、未 push）を push してよいか
- フォントを Roboto Flex に替えるか

## 触ってはいけないもの・注意
- 待ち受け 0.0.0.0・認証なしは意図。変えない
- systemd のサービスは動かしたままにしてある（`systemctl --user restart mediaforge` で `index.html`・`main.py` の変更が反映される。止めるなら `./systemd/install.sh uninstall`）
- M3E を戻す: `git revert ccefc63`（その後のナビ調整は 76f42c1）。M3E はブロックごと消せば元に戻る
- `.venv`・`completed_outputs.json`・`uploads/ outputs/ downloads/` は .gitignore 済み
- sudo はパスワードなし無効（`passwordless-sudo check` = off）

## 資料
README.md（起動・systemd・API・構成）／CONTEXT.md（用語）／docs/adr/（キュー・バッチの決定）
