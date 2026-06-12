# 実機検証手順（RTX 5090 / Windows）

本ドキュメントは **人間が RTX 5090 搭載 Windows 実機** で行う検証手順です。  
エージェント側では GPU 動作確認はできません。

---

## 前提条件の確認

作業前に以下を確認してください。

| 項目 | 要件 | 確認方法 |
|------|------|----------|
| Python | **3.10.x 固定**（3.11/3.12 不可） | `venv\Scripts\python --version` |
| VS Build Tools | C++ ビルドツール導入済み | fairseq インストール時にビルドエラーが出ないこと |
| NVIDIA ドライバ | **570 系以降** | `nvidia-smi` |
| GPU | RTX 5090 (sm_120) | `nvidia-smi` の Device Name |
| 作業ブランチ | `feature/blackwell-support` | `git branch --show-current` |
| 作業ディレクトリ | 本フォーク（既存の動作中インストールには触れない） | — |

### 初回起動（依存インストール）

1. `webui-user.bat` をダブルクリック（または `webui.bat`）
2. 初回は venv 作成 → torch 2.7.1+cu128 → requirements インストールが走る
3. 完了後 Gradio URL が表示されれば WebUI 起動成功

手動確認（任意）:

```bat
venv\Scripts\python -c "import torch; print(torch.__version__, torch.version.cuda)"
```

期待値: `2.7.1+cu128` と `12.8`

```bat
venv\Scripts\python -m pip check
```

期待値: `No broken requirements found.`

---

## 検証 1: 学習パイプライン完走

**目的**: 前処理 → 特徴抽出（hubert-base-japanese）→ 学習（数エポック）→ index 生成 → モデル保存

1. 音声数分の小規模データセットを用意（WAV、話者 1 名）
2. WebUI の Training タブで:
   - Embedder: **hubert-base-japanese** を選択
   - 前処理（音声分割・F0 抽出・特徴抽出）を実行
   - 学習を **数エポック**（例: 5〜10）実行
   - **Train feature index** を実行
3. 各ステップがエラーなく完走すること

---

## 検証 2: GPU 使用と loss 推移

1. 学習中に別ターミナルで `nvidia-smi` を実行
2. Python プロセスが GPU メモリを使用していること
3. TensorBoard またはコンソールログで **loss が epoch ごとに推移**していること

```bat
venv\Scripts\tensorboard --logdir logs
```

---

## 検証 3: 出力 .pth の互換性

学習完了後、出力された `.pth` を検証します。

```bat
venv\Scripts\python -c "
import torch
p = r'models\checkpoints\YOUR_MODEL.pth'
d = torch.load(p, map_location='cpu', weights_only=False)
print('config_len:', len(d.get('config', [])))
print('embedder_name:', d.get('embedder_name'))
"
```

**期待値**:

| キー | 期待値 |
|------|--------|
| `config_len` | **19** |
| `embedder_name` | **`hubert-base-japanese`** 系（末尾 768 付き含む） |

---

## 検証 4: VCClient v1 との連携

1. 出力 `.pth` を改修済み **VCClient v1** フォークに配置
2. モデルがロード・変換できること
3. 変換後の音質が既存モデル（同一 embedder）と同水準であること

---

## 検証 5: 改修前ベースラインとの比較

| 項目 | 改修前（2026-06-13 ベースライン） | 改修後（期待） |
|------|-----------------------------------|----------------|
| 依存インストール | `gradio_client.serializing` で起動前失敗 | 正常インストール |
| torch | cu118 最新（sm_120 非対応） | 2.7.1+cu128 |
| hubert ロード | torch 2.6+ で UnpicklingError | weights_only パッチで成功 |
| 学習完走 | 未確認（起動不能） | 全工程完走 |

---

## トラブルシュート

### fairseq ビルド失敗

- **症状**: `pip install` 中に C++ コンパイルエラー
- **対処**: [Visual Studio Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/) で「C++ によるデスクトップ開発」をインストール
- **確認**: README Troubleshooting セクション参照

### cuDNN DLL エラー

- **症状**: torch import または CUDA 実行時に cuDNN 関連 DLL not found
- **対処**: torch 2.7.1+cu128 Windows wheel は cuDNN 9 DLL 同梱。`pip show torch` で `2.7.1+cu128` を確認し、別版 torch が混在していれば venv を削除して再インストール

### no kernel image / sm_120 非対応

- **症状**: `CUDA error: no kernel image is available for execution on the device`
- **原因**: cu128 以外の torch が入っている（例: cu118、CPU 版）
- **対処**:
  ```bat
  venv\Scripts\python -m pip install torch==2.7.1 torchaudio==2.7.1 --extra-index-url https://download.pytorch.org/whl/cu128 --force-reinstall
  ```
- **確認**: `torch.version.cuda` が `12.8` であること

### pip install 失敗（omegaconf / fairseq）

- **症状**: `ResolutionImpossible` / `omegaconf has invalid metadata`
- **原因**: pip 24.1 以降が fairseq 0.12.2 の推移的依存 omegaconf メタデータを拒否
- **対処**: `launch.py` が自動的に `pip<24.1` を適用する。手動の場合:
  ```bat
  venv\Scripts\python -m pip install "pip<24.1"
  venv\Scripts\python -m pip install -r requirements.txt
  ```

### gradio_client.serializing エラー

- **症状**: `ModuleNotFoundError: No module named 'gradio_client.serializing'`
- **原因**: gradio-client 2.x が入っている
- **対処**: `requirements/main.txt` の `gradio-client==0.2.10` が適用されている venv か確認。古い venv なら削除して `webui-user.bat` から再作成

### UnpicklingError / weights_only

- **症状**: `Weights only load failed` / `fairseq.data.dictionary.Dictionary was not an allowed global`
- **対処**: `feature/blackwell-support` ブランチの Step 3 パッチが入っているか確認（`modules/torch_compat.py` 存在、`webui.py` 先頭で import）
