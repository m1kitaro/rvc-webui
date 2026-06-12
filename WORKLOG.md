# WORKLOG: rvc-webui Blackwell 対応

作業ブランチ: `feature/blackwell-support`  
最終更新: 2026-06-13  
対象リポジトリ: ddPn08/rvc-webui フォーク（origin: `m1kitaro/rvc-webui`）

---

## Step 1: 現状把握（コード変更なし）

### 1-1. 起動・インストール機構（最重要）

#### 起動チェーン全体

```
webui-user.bat
  └─ call webui.bat
       ├─ [venv 作成/再利用]
       └─ %PYTHON% launch.py %*
            ├─ prepare_environment()  … 依存インストール
            └─ start()                … webui.py 起動
                 └─ ui.create_ui() → preload() → Gradio Blocks
```

**Windows 正規起動経路**

| 段階 | ファイル | 役割 |
|------|----------|------|
| ユーザー設定 | `webui-user.bat` | `PYTHON`, `GIT`, `VENV_DIR`, `COMMANDLINE_ARGS` を上書き可能（現状はすべて空＝デフォルト） |
| シェル | `webui.bat` | Python/pip 確認 → venv 作成/有効化 → `launch.py` 実行 |
| インストール | `launch.py` | torch インストール → `requirements.txt` インストール |
| アプリ | `webui.py` | `modules.ui.create_ui()` → Gradio 起動 |

**Linux/Mac 正規起動経路**

```
webui-user.sh (任意) → webui.sh → venv 作成/activate → launch.py
```

`webui.sh` は AMD GPU 時のみ `TORCH_COMMAND` を ROCm 用に上書き（79–82 行）。Windows 側には同等ロジックなし。

#### webui.bat の venv 処理

- **デフォルト venv パス**: `VENV_DIR=%~dp0venv`（リポジトリ直下 `venv/`）
- **作成条件**: `%VENV_DIR%\Scripts\Python.exe` が存在しなければ `%PYTHON% -m venv "%VENV_DIR%"` で新規作成
- **再利用条件**: 上記 Python.exe が存在すればその venv を使い続ける（バージョン検証・再作成なし）
- **venv スキップ**:
  - `VENV_DIR=-` → venv 不使用
  - `SKIP_VENV=1` → venv 不使用
- **Python 指定**: 環境変数 `PYTHON`（未設定時 `python`）。venv 有効化後は `venv\Scripts\Python.exe` に差し替え

#### launch.py の依存インストール（核心）

`prepare_environment()`（91–123 行）の処理順:

1. **`--skip-install`**: 以降のインストールをすべてスキップ
2. **torch / torchaudio**（109–114 行）:
   - 条件: `--reinstall-torch` **または** `torch` / `torchaudio` が未インストール（`importlib.util.find_spec` で判定）
   - コマンド: `python -m {TORCH_COMMAND}`（**pip サブコマンド文字列を `-m` に渡す**）
   - **デフォルト `TORCH_COMMAND`**（97–100 行）:
     ```
     pip install torch torchaudio --extra-index-url https://download.pytorch.org/whl/cu118
     ```
   - **バージョン固定なし**（`torch==…` なし）→ 実行時点の PyPI / cu118 インデックス最新が入る
   - **上書き**: 環境変数 `TORCH_COMMAND` で完全置換可能
3. **pyngrok**（116–117 行）: `--ngrok` 指定時のみ
4. **requirements.txt**（119–123 行）:
   - 毎回実行: `python -m pip install -r requirements.txt`
   - **`--upgrade` なし** → 既存 venv では満た済みパッケージは原則維持
   - **新規 venv** では未固定の推移的依存が **2026 年時点の最新版** に解決される

**その他の環境変数（launch.py）**

| 変数 | 用途 | デフォルト |
|------|------|------------|
| `TORCH_COMMAND` | torch インストールコマンド全文 | cu118 インデックス、バージョン未固定 |
| `INDEX_URL` | `run_pip()` 経由 pip の `--index-url` | 空（未使用） |
| `COMMANDLINE_ARGS` | `webui.py` へ追加 argv | 空 |
| `GIT` | コミットハッシュ取得 | `git` |

**注意**: `webui-user.sh` に `REQS_FILE` のコメントがあるが、`launch.py` は **`requirements.txt` 固定**（SD-WebUI 由来の未使用残骸）。

#### requirements ファイル構成

```
requirements.txt          → `-r requirements/main.txt` のみ
requirements/main.txt     → 本番依存（17 パッケージ固定 + 3 パッケージ未固定）
requirements/dev.txt      → black, isort（main.txt はコメントアウト）
```

**torch / torchaudio は requirements に含まれない** → 必ず `launch.py` の `TORCH_COMMAND` 経由で別途インストール。

#### ベースライン障害との因果関係（gradio_client）

- `requirements/main.txt` は `gradio==3.36.1` を固定
- PyPI メタデータ: `gradio==3.36.1` は `gradio-client>=0.2.7` のみ（**上限なし**）
  - 出典: https://pypi.org/pypi/gradio/3.36.1/json
- `gradio 3.36.1` ソースは `from gradio_client import serializing` を使用
  - 出典: https://github.com/gradio-app/gradio/blob/v3.36.1/gradio/blocks.py
- `gradio-client 2.0.0` 以降は `serializing` モジュール削除
  - 出典: https://github.com/gradio-app/gradio/issues/12844
- 2026 年の新規 venv では pip が `gradio-client 2.x`（現最新 2.5.0）を解決 →  
  `ModuleNotFoundError: No module named 'gradio_client.serializing'`（INSTRUCTIONS 記載のベースライン障害）

**結論**: インストール機構上、**torch は launch.py、それ以外は requirements/main.txt** だが、**推移的依存（gradio-client 等）の上限固定がなく経年劣化で破壊**される。Step 2 で gradio / gradio_client ペアの明示固定が必要。

#### 起動時フロー図

```mermaid
flowchart TD
    A[webui-user.bat] --> B[webui.bat]
    B --> C{venv/Scripts/Python.exe 存在?}
    C -->|No| D[python -m venv venv/]
    C -->|Yes| E[venv Python を使用]
    D --> E
    E --> F[launch.py prepare_environment]
    F --> G{torch/torchaudio 未インストール?}
    G -->|Yes| H["TORCH_COMMAND 実行<br/>(default: cu118, 版固定なし)"]
    G -->|No| I[pip install -r requirements.txt]
    H --> I
    I --> J[webui.py → ui.create_ui]
    J --> K[preload: モデルDL / ffmpeg]
    K --> L[Gradio launch]
```

---

### 1-2. 依存の現状記録

#### requirements/main.txt の固定バージョン

| パッケージ | 指定 | 備考 |
|------------|------|------|
| gradio | `==3.36.1` | gradio-client は推移的（`>=0.2.7`、上限なし） |
| tqdm | `==4.65.0` | |
| numpy | `==1.23.5` | `<2` ではないが 1.x 固定 |
| faiss-cpu | `==1.7.3` | |
| fairseq | `==0.12.2` | PyPI 版。Windows ビルド要 VS Build Tools |
| matplotlib | `==3.7.1` | |
| scipy | `==1.9.3` | |
| librosa | `==0.9.1` | numba は推移的 `>=0.45.1` |
| pyworld | `==0.3.2` | |
| soundfile | `==0.12.1` | |
| ffmpeg-python | `==0.2.0` | |
| pydub | `==0.25.1` | |
| soxr | `==0.3.5` | |
| transformers | `==4.28.1` | |
| torchcrepe | `==0.0.20` | |
| Flask | `==2.3.2` | |

#### 未固定（浮動）依存

| パッケージ | requirements 記載 | PyPI 最新（2026-06-13 確認） |
|------------|-------------------|------------------------------|
| tensorboard | 行のみ、版なし | 2.20.0 |
| tensorboardX | 行のみ、版なし | 2.6.5 |
| requests | 行のみ、版なし | 2.34.2 |

#### launch.py 経由（requirements 外）

| パッケージ | 指定 | 備考 |
|------------|------|------|
| torch | **未固定** | デフォルト cu118 インデックス最新 |
| torchaudio | **未固定** | 同上 |
| torchvision | **含まれない** | macOS のみ `webui-macos-env.sh` で追加 |

#### 推移的だが repo 未固定で影響大

| パッケージ | 親 | リスク |
|------------|-----|--------|
| gradio-client | gradio 3.36.1 | **致命的**（serializing 削除） |
| numba | librosa 0.9.1 | 上限なし。numpy 2.x 非互換の可能性 |
| 各種 gradio 依存 | gradio | aiofiles, fastapi, pydantic 等 |

#### README 記載のテスト環境

- Windows 10, Python 3.10.9, **torch 2.0.0+cu118**
- 出典: `README.md` 32–34 行

---

### 1-3. `torch.load` 使用箇所（リポジトリ内）

| ファイル | 行 | 用途 |
|----------|-----|------|
| `modules/models.py` | 260 | VC チェックポイント (.pth) ロード |
| `modules/tabs/merge.py` | 119–122 | マージ UI: モデルメタ取得 |
| `modules/merge.py` | 28 | マージ処理: weight 抽出 |
| `modules/server/model.py` | 59 | HTTP サーバ: RVC モデル |
| `lib/rvc/utils.py` | 57 | 学習再開: G/D checkpoint |
| `lib/rvc/train.py` | 555 | 事前学習 G モデル |
| `lib/rvc/train.py` | 605, 609 | 事前学習 D モデル |
| `lib/rvc/train.py` | 636 | augment 用モデル |
| `lib/rvc/data_utils.py` | 95, 227 | キャッシュ済み spectrogram (.spec.pt) |

**合計: 9 ファイル / 11 呼び出し**（いずれも `weights_only` 未指定 → torch 2.6+ では `weights_only=True` デフォルト）

**fairseq 内部（site-packages、repo 外）**: `checkpoint_utils.load_checkpoint_to_cpu()` が hubert 等の `.pt` ロード時に `torch.load` 使用。Step 3 でエントリポイントのモンキーパッチ対象。

---

### 1-4. AMP および torch 2.x 非互換が疑われる API

#### AMP（`lib/rvc/train.py` のみ）

| 行 | API |
|----|-----|
| 18 | `from torch.cuda.amp import GradScaler, autocast` |
| 672 | `GradScaler(enabled=config.train.fp16_run)` |
| 772, 811, 830, 840, 843, 941 | `autocast(enabled=…)` |

torch 2.4+ では `torch.amp.GradScaler('cuda', …)` / `torch.amp.autocast('cuda', …)` が推奨だが、旧 API は現時点で警告止まりの可能性が高い。**エラー確認後にのみ修正**（Step 4 方針）。

#### その他の注意 API

| ファイル | 行 | API | 備考 |
|----------|-----|-----|------|
| `lib/rvc/commons.py` | 104 | `@torch.jit.script` | JIT スクリプト。torch 2.7 で要実機確認 |
| `lib/rvc/train.py` | 13–14, 662–663 | `torch.distributed`, `DDP` | マルチ GPU 学習 |
| `lib/rvc/data_utils.py` | 399 | `DistributedBucketSampler` | |
| `lib/rvc/data_utils.py` | 107, 118, 239, 250 | `torch.save(..., _use_new_zipfile_serialization=False)` | 保存形式互換 |
| 各所 | — | `.half()` / `.float()` | 広く使用 |
| `lib/rvc/pipeline.py`, `extract_f0.py` | — | `torch.backends.mps` | Apple Silicon 用 |

**本リポジトリに xformers / torch-directml / torchvision 依存なし**（RVC-Project 本家との差分。Blackwell 対応の障害要因にはならない）。

---

### 1-5. fairseq import と hubert ロード

#### fairseq import 箇所

| ファイル | import |
|----------|--------|
| `modules/models.py` | `checkpoint_utils`, `HubertModel` |
| `modules/server/model.py` | 同上 |
| `lib/rvc/pipeline.py` | `HubertModel`（型/import のみ） |
| `lib/rvc/preprocessing/extract_feature.py` | `checkpoint_utils` |

#### hubert-base-japanese モデル取得

- `modules/core.py` 75–86 行: Hugging Face から `rinna/japanese-hubert-base` の `fairseq/model.pt` を  
  `models/embeddings/rinna_hubert_base_jp.pt` に DL
- `EMBEDDINGS_LIST`（`modules/models.py` 21–28 行）:
  - キー: `"hubert-base-japanese"`
  - ファイル: `rinna_hubert_base_jp.pt`
  - embedder 名: `"hubert-base-japanese"`

#### hubert ロード処理（いずれも `checkpoint_utils.load_model_ensemble_and_task`）

| 用途 | ファイル | 関数 |
|------|----------|------|
| WebUI 推論 | `modules/models.py` | `load_embedder()` 239–255 行 |
| HTTP サーバ | `modules/server/model.py` | `VoiceServerModel.__init__` 92–95 行 |
| 特徴抽出（学習前処理） | `lib/rvc/preprocessing/extract_feature.py` | `load_embedder()` 31–48 行 |
| 学習 augment | `lib/rvc/train.py` | `load_embedder()` 経由 625–631 行 |

fairseq 内部の `torch.load` により、torch 2.6+ では hubert ロード時に `UnpicklingError`（Dictionary 未許可）が発生する見込み。

---

### 1-6. 既存フォーク・関連プロジェクト調査

#### ddPn08/rvc-webui 本体

- **Archived**（最終 push: 2023-12-12）
- README テスト環境: torch 2.0.0+cu118
- **Blackwell / cu128 対応の公式コミットなし**

#### ddPn08 フォーク群

- GitHub API / `gh` が利用不可のため網羅的 fork 一覧は取得できず
- Web 検索でも **ddPn08/rvc-webui 専用の Blackwell 対応 fork は見つからず**
- 本作業フォーク（`m1kitaro/rvc-webui`, branch `feature/blackwell-support`）が対応作業の本体

#### 参考になる RVC 系プロジェクト（コードベースは異なる）

| ソース | 内容 | 本リポジトリへの参考点 |
|--------|------|------------------------|
| [RVC-Project #2574](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI/issues/2574) | RTX 50 系: torch 2.7+cu128、`fairseq/checkpoint_utils.py` に `weights_only=False` | torch 版・fairseq パッチ必要性の裏付け |
| [RVC-Project #2509](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI/issues/2509) | weights_only デフォルト変更 | 自 repo + fairseq 双方の torch.load 対策必要 |
| [RVC-Project PR #2529](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI/pull/2529) | torch <2.6 制約・gradio 更新 | 本 fork は gradio 3.x 維持のため直接適用不可 |
| [RVC-Project #2745](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI/issues/2745) | cu128 nightly 手順 | torch インデックス URL 変更の参考 |
| [Tps-F/RVC weights_only PR](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion/issues/51) | 全 torch.load に weights_only=False | Step 3 方針と一致 |

**注意**: 上記は **RVC-Project 本家**（`infer-web.py` 等）向け。ddPn08 版は構成が異なり（`launch.py` + `webui.py`、hubert-base-japanese 明示対応）、**コードのコピーは不可**。変更箇所の参考に留める。

---

### Step 1 サマリー（Step 2 への入力）

| 項目 | 現状 | Step 2 で必要な対応 |
|------|------|---------------------|
| torch インストール | `launch.py` 97–100 行、cu118・版未固定 | `2.7.1+cu128` 固定、`TORCH_COMMAND` と requirements 整合 |
| gradio-client | 推移的・上限なし | gradio 3.36.1 と整合する `<2.0` 系を明示固定 |
| numpy | `==1.23.5` | `>=1.23.5,<2` への緩和検討 |
| fairseq | `==0.12.2` PyPI | 維持（フォーク差し替え禁止） |
| torch.load | 11 箇所、weights_only 未指定 | Step 3 で全箇所 + fairseq モンキーパッチ |
| 浮動依存 | tensorboard 等 3 件 + 推移的多数 | 起動確認で問題あれば固定 |

---

## Step 2: 依存パッケージとインストール機構の更新

実施日: 2026-06-13

### 2-1. torch / torchaudio（launch.py）

**変更**: `launch.py` 97–100 行の `TORCH_COMMAND` デフォルトを以下に更新。

```
pip install torch==2.7.1 torchaudio==2.7.1 --extra-index-url https://download.pytorch.org/whl/cu128
```

| 項目 | 内容 |
|------|------|
| 採用版 | torch **2.7.1+cu128**, torchaudio **2.7.1+cu128** |
| 出典 | PyTorch cu128 インデックス: `pip index versions torch --index-url https://download.pytorch.org/whl/cu128` → `2.7.1+cu128` 確認（2026-06-13） |
| 出典 | 同上 torchaudio → `2.7.1+cu128` 確認 |
| 上書き | 環境変数 `TORCH_COMMAND` による完全置換は従来どおり維持 |
| fairseq 特殊処理 | `launch.py` 内に fairseq 関連コードなし（grep 確認済み） |

### 2-2. gradio-client 明示固定（requirements/main.txt）

**追加**: `gradio-client==0.2.10`（`gradio==3.36.1` の直後）

#### 選定根拠（一次情報）

| 根拠 | 出典 |
|------|------|
| gradio 3.36.1 リリース日 | PyPI: **2023-07-07**（https://pypi.org/pypi/gradio/3.36.1/json → wheel `upload_time`） |
| gradio 3.36.1 の gradio-client 要件 | `gradio-client>=0.2.7`（同上 `requires_dist`） |
| gradio-client 0.2.10 リリース日 | PyPI: **2023-07-17**（https://pypi.org/pypi/gradio-client/0.2.10/json → wheel `upload_time`） |
| 同時期の gradio 側要件 | gradio **3.37.0**（2023-07-17 同日リリース）が `gradio-client>=0.2.10` を要求 → 0.2.10 が当時の整合ペア |
| `serializing` モジュール存在 | gradio-client 0.2.10 wheel 内に `gradio_client/serializing.py` を確認（pip download + zipfile 検査、2026-06-13） |
| gradio 3.36.1 側の import | `from gradio_client import serializing`（https://github.com/gradio-app/gradio/blob/v3.36.1/gradio/blocks.py#L21） |
| 2.x 系との非互換 | gradio-client 2.0.0 以降 `serializing` 削除（https://github.com/gradio-app/gradio/issues/12844） |

**結論**: 0.2.10 は gradio 3.36.1 リリース直後（10 日以内）に公開され、当時の次版 gradio が下限として採用した版。`serializing` を含み、2026 年時点で pip が解決する gradio-client 2.x による起動破壊を防ぐ。

### 2-3. その他依存（変更なし）

| パッケージ | 方針 | 理由 |
|------------|------|------|
| numpy | `==1.23.5` 維持 | 指示どおり。pip 解決エラーなし（本 Step では未検証、Step 5 で確認） |
| fairseq | `==0.12.2` 維持 | PyPI 無改変版。weights_only 対応は Step 3 のモンキーパッチで行う |
| tensorboard / tensorboardX / requests | 未固定 | Step 5 の pip check / 起動確認で問題が出た場合のみ固定 |

### 2-4. 変更ファイル

| ファイル | 変更内容 |
|----------|----------|
| `launch.py` | `TORCH_COMMAND` デフォルトを torch/torchaudio 2.7.1+cu128 固定 |
| `requirements/main.txt` | `gradio-client==0.2.10` 追加 |
| `WORKLOG.md` | Step 2 記録追記 |

---

## 未着手

- Step 3: weights_only パッチ
- Step 4: 学習パイプライン追従修正
- Step 5: エージェント側検証
- VERIFY.md 作成

---

## 変更ファイル（Step 1）

| ファイル | 操作 |
|----------|------|
| `WORKLOG.md` | 新規作成（Step 1 調査結果） |

**ソースコード変更: なし**
