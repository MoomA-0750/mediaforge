# MediaForge

ffmpeg・ImageMagick・yt-dlp をまとめて操作できるローカル Web UI。  
FastAPI + vanilla JS SPA、ポート **7860** で動く。

---

## 起動

```bash
cd ~/ffmpeg_studio
./run.sh
# または
python3 -m uvicorn main:app --host 0.0.0.0 --port 7860
```

ブラウザで http://localhost:7860 を開く。

### 依存パッケージ（Python）

```bash
pip install -r requirements.txt
# fastapi / uvicorn[standard] / psutil / aiofiles / python-multipart
```

### 外部ツール（オプション）

| ツール | 用途 | インストール例 |
|--------|------|----------------|
| `ffmpeg` + `ffprobe` | 動画変換・トリム・クロップ | `sudo dnf install ffmpeg` |
| `imagemagick` (`convert` または `magick`) | 画像処理 | `sudo dnf install ImageMagick` |
| `yt-dlp` | 動画ダウンロード | `pip install yt-dlp` |

ツールが存在しなくても起動する。該当タブに **Install Banner** が表示され、インストールコマンドを案内する。

---

## ファイル構成

```
ffmpeg_studio/
├── main.py                  # FastAPI バックエンド（全 API）
├── static/
│   └── index.html           # SPA 全体（HTML + CSS + JS、約 3700 行）
├── uploads/                 # アップロードファイル置き場
├── outputs/                 # 変換・処理後ファイル置き場
├── downloads/               # yt-dlp ダウンロード先
├── completed_outputs.json   # 出力ファイル一覧の永続化
├── requirements.txt
├── run.sh
├── CONTEXT.md               # 用語集（Tool / Capability / Job / Batch / Feature / Install Banner）
└── docs/adr/
    ├── 0001-unified-job-queue.md       # 全ツール共通キューの理由
    └── 0002-batch-one-job-per-file.md  # バッチ=1ファイル1ジョブの理由
```

---

## 実装済み機能

### Dashboard
- CPU / RAM / 温度のリアルタイム表示（`/api/system` → psutil）
- クイックアクショングリッド（各ツールのタブへのショートカット）
- 最近のジョブ一覧

### Video タブ群（ffmpeg）

**Convert**
- ファイル選択（複数可）→ 同じ設定で一括変換
- コーデック・ビットレート・解像度・HWアクセラレーション
- CRF / ビットレートモード切り替え
- コマンドプレビューリアルタイム更新

**Trim**
- ファイル選択（複数可）→ 同じ開始/終了時刻で一括トリム
- HTML5 video プレビュー + ドラッグ可能タイムライン
- 波形表示
- 精確カット（再エンコード）モードトグル

**Crop**
- ファイル選択（複数可）→ 同じクロップ設定で一括処理
- サムネイルプレビュー上でドラッグ操作（マウス・タッチ共通）
- 8方向ハンドル + アスペクト比ロック（16:9 / 4:3 / 1:1 / 3:4 / 9:16 / Free）
- ピクセル値の直接入力
- アスペクト比維持ドラッグ：端まで引いても比率を保つ（アンカーベースのクランプ）
- 4-pane オーバーレイ方式（`overflow:hidden` 不使用、ハンドルがはみ出しても見える）

### Image タブ（ImageMagick）

**4つのオペレーション（ピル切り替え）:**
- **Resize** — px / アスペクト維持
- **Convert** — フォーマット変換 + クオリティ
- **Compress** — クオリティ圧縮 + メタ削除
- **Crop** — ドラッグ操作 + アスペクト比ロック（動画クロップと同じ `initCropDrag` 共有）

ファイル選択で複数選択可能。同じ操作を一括実行（1ファイル = 1ジョブ）。

### Download タブ（yt-dlp）
- URL 入力 + 品質プリセット
- フォーマット一覧取得・選択
- 字幕ダウンロード
- プレイリスト対応
- 出力ディレクトリ指定
- クッキーファイル指定

### Queue タブ
- 全ジョブのリアルタイム進捗（SSE）
- ジョブごとのログビューア
- キャンセル
- ツール別フィルタ

### Files タブ
- アップロード済みファイル一覧・削除
- 出力ファイル一覧・ダウンロード・削除

### Settings タブ
- ツール検出状態（Capability Check 結果）
- ディレクトリパス表示
- テーマ切り替え（ダーク / ライト / システム）

---

## ファイルピッカー

- 全タブ共通のモーダル（`#fp-modal`）
- **シングル選択**：ファイルをタップで即座に選択・閉じる
- **マルチ選択**（`multi=true` で開いた場合）：
  - タブバー非表示、アップロード・出力ファイルを 1 ページにグループ表示
  - チェックボックスで複数選択 → 「確定」ボタンでコールバックに渡す
  - タブ再読み込みしてもチェック状態は `_fpFiles` オブジェクトで保持・復元
- アップロードボタンでその場にファイルを追加可能（進捗バー付き）

---

## API エンドポイント

| Method | Path | 概要 |
|--------|------|------|
| GET | `/api/capabilities` | ツール検出結果（ffmpeg / imagemagick / yt_dlp など） |
| GET | `/api/browse?path=` | ディレクトリ一覧 |
| POST | `/api/upload` | ファイルアップロード |
| GET | `/api/uploads` | アップロード済みファイル一覧 |
| DELETE | `/api/uploads/{filename}` | アップロードファイル削除 |
| GET | `/api/output-files` | 出力ファイル一覧 |
| DELETE | `/api/output-files?path=` | 出力ファイル削除 |
| GET | `/api/media?path=` | メディアファイル配信（HTML5 video 用） |
| GET | `/api/thumbnail?path=&t=&w=` | ffmpeg / ImageMagick でサムネイル生成 |
| GET | `/api/probe?path=` | ffprobe JSON 情報 |
| GET | `/api/file-info?path=` | ファイル基本情報 |
| GET | `/api/system` | CPU / RAM / 温度（psutil） |
| GET | `/api/ytdlp/formats?url=` | yt-dlp フォーマット一覧 |
| POST | `/api/jobs` | ジョブ作成 `{type, input_path, output_path, params}` |
| GET | `/api/jobs` | ジョブ一覧 |
| GET | `/api/jobs/{id}` | ジョブ詳細 |
| DELETE | `/api/jobs/{id}` | ジョブキャンセル |
| GET | `/api/jobs/{id}/stream` | SSE 進捗ストリーム |
| GET | `/api/download?path=` | ファイルダウンロード |

---

## アーキテクチャ

### バックエンド（`main.py`）

- **Capability Check**: 起動時に `shutil.which` で各ツールを検出、`CAPABILITIES` dict に保存
- **ジョブキュー**: `jobs: dict`（インメモリ）。サーバー再起動でリセット
- **ジョブ実行**: `asyncio` + `subprocess`、stdout を SSE でストリーミング
- **Job Type 判別**:
  - `image_*` → `_build_imagemagick_cmd()`
  - `ytdlp_*` → `_build_ytdlp_cmd()`
  - それ以外（`convert` / `trim` / `crop`）→ `_build_ffmpeg_cmd()`
- **出力ファイル管理**: `completed_outputs.json` に永続化（サーバー再起動後も Files タブに残る）

### フロントエンド（`static/index.html`）

- **単一ファイル SPA**。Tailwind CDN + Material Symbols フォント
- **テーマ**: Material 3 ダークテーマ、CSS カスタムプロパティ（`--c-*`）で定義。ライトテーマは `:root.light`
- **状態管理**: グローバル `state` オブジェクト（`state.crop`, `state.imgcrop`, `state.convFiles` など）
- **クロップドラッグ**: `initCropDrag(wrapEl, stateRef, renderFn)` が動画・画像で共用
- **オーバーレイ**: 4-pane 方式（`_updateCropOverlay(prefix, b)`）、`overflow:hidden` 不使用

---

## 既知の設計メモ

- ジョブはインメモリのみ。**サーバー再起動でキューはリセット**される
- `libopenh264` を動画クロップのデフォルトコーデックとして使用（`libx264` より広い環境で動く）
- バッチ送信は「1ファイル = 1ジョブ」（ADR 0002 参照）。`mogrify` は使わない
- ImageMagick の `convert` コマンドは IM7 では `magick convert` に変わっている。`capabilities.imagemagick_cmd` で吸収

---

## 今後の追加候補（未実装）

- 動画クロップの出力コーデック選択 UI（現在 `libopenh264` 固定）
- yt-dlp ダウンロード進捗の詳細表示
- ジョブのサーバー再起動後の永続化
- 複数ファイルトリム時のプレビュー（現在は1ファイル目のみ表示）
