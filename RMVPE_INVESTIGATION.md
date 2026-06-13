# RMVPE f0 抽出 追加調査レポート

対象ブランチ: `feature/blackwell-support`  
調査日: 2026-06-13

---

## 1. 現状の f0 抽出フロー

### 1-1. 学習時の前処理 (`extract_f0.py`)

**`lib/rvc/preprocessing/extract_f0.py`**

| 要素 | 内容 |
|---|---|
| エントリポイント | `run(training_dir, num_processes, f0_method)` (line 189) |
| 実処理 | `processor(paths, f0_method, samplerate=16000, hop_size=160)` (line 147) |
| 内部分岐 | `compute_f0(path, f0_method, fs, hop, f0_max, f0_min)` (line 96) |

**`compute_f0` 内の分岐** (lines 105–127):
```python
if f0_method == "harvest":    # pyworld.harvest → stonemask
elif f0_method == "dio":      # pyworld.dio → stonemask
elif f0_method == "mangio-crepe":  # get_f0_crepe_computation(hop_length=160)
elif f0_method == "crepe":    # get_f0_official_crepe_computation
```

**出力仕様**:
- `compute_f0` は生の f0 配列 `(N,)` を返す（単位: Hz、無声区間は 0）
- hop_size = 160 samples @ 16kHz = 10ms/frame
- `processor` が `coarse_f0()` で量子化 (0–255) → `2a_f0/` に保存
- 元の連続 f0 → `2b_f0nsf/` に保存

**入力**:
- 16kHz wav ファイル（`1_16k_wavs/` 以下）
- `load_audio(path, sr=16000)` で読み込み → `np.float32` 1次元配列

### 1-2. 推論時 (`pipeline.py`)

**`lib/rvc/pipeline.py`**

| 要素 | 内容 |
|---|---|
| エントリポイント | `VocalConvertPipeline.__call__()` (line 313) |
| f0 計算 | `self.get_f0(audio_pad, p_len, transpose, f0_method, inp_f0)` (line 373) |

**`get_f0` 内の分岐** (lines 147–170):
```python
if f0_method == "harvest":
elif f0_method == "dio":
elif f0_method == "mangio-crepe":
elif f0_method == "crepe":
```

**出力仕様**:
- `(f0_coarse, f0bak)` のタプルを返す
  - `f0_coarse`: 量子化済み int 配列 (1–255、無声=0 or 1)
  - `f0bak`: 連続 Hz 値 float 配列
- hop_size = `self.window = 160` samples @ `self.sr = 16000` → 10ms/frame

**入力**:
- `x: np.ndarray` — 16kHz float32 音声（padding 済み）
- `p_len: int` — フレーム数

### 1-3. UI の選択肢

**学習タブ** (`modules/tabs/training.py` line 360):
```python
pitch_extraction_algo = gr.Radio(
    choices=["dio", "harvest", "mangio-crepe", "crepe"],
    value="crepe",
)
```

**推論タブ** (`modules/tabs/inference.py` line 24):
```python
pitch_extraction_algo = gr.Radio(
    choices=["dio", "harvest", "mangio-crepe", "crepe"],
    value="crepe",
)
```

**train_cli.py** (`parse_args()` line 85):
```python
p.add_argument("--pitch-algo", choices=["dio", "harvest", "crepe", "mangio-crepe"])
```

### 1-4. 共通インターフェース

rmvpe を組み込む際に満たすべき仕様:

| 箇所 | 期待する入力 | 期待する出力 |
|---|---|---|
| 学習前処理 `compute_f0()` | `path: str`（16kHz wav）, `f0_method="rmvpe"` | `f0: np.ndarray (N,)` Hz, hop=160 |
| 推論 `get_f0()` | `x: np.ndarray` 16kHz float32, `f0_method="rmvpe"` | `(f0_coarse, f0bak)` 同上 |

---

## 2. 推論側の f0 抽出箇所（完全一覧）

rmvpe を追加する必要がある箇所を漏れなく列挙する。

| # | ファイル | 関数 | 行 | 対応要否 |
|---|---|---|---|---|
| 1 | `lib/rvc/preprocessing/extract_f0.py` | `compute_f0()` | 96–127 | **必須**（学習前処理） |
| 2 | `lib/rvc/pipeline.py` | `VocalConvertPipeline.get_f0()` | 134–194 | **必須**（推論） |
| 3 | `modules/tabs/training.py` | `pitch_extraction_algo` Radio | 360 | **必須**（UI 選択肢追加） |
| 4 | `modules/tabs/inference.py` | `pitch_extraction_algo` Radio | 24 | **必須**（UI 選択肢追加） |
| 5 | `train_cli.py` | `--pitch-algo` choices | 85 | **必須**（CLI 選択肢追加） |

**注意**:
- 箇所 3, 4 は gradio UI を使っている場合にのみ関係する。現在は Train ボタンが動作しないため
  学習側は CLI 経由（箇所 5 のみ実運用で使われる）。推論 UI は使用可能なので箇所 4 も重要。
- `modules/models.py` の `VcModel.single()` (line 107) は `f0_method` を
  `VocalConvertPipeline.__call__()` に渡すだけで分岐なし。変更不要。
- `lib/rvc/train.py` の `change_speaker()` / `change_speaker_nono()` は
  augment 用の推論であり、f0_method を使わない（embedder 経由のみ）。変更不要。

---

## 3. rmvpe 実装の入手元と組み込み方法

### 3-1. 参照実装

#### VCClient (w-okada) の実装（ローカルに存在・確認済み）

| ファイル | 役割 |
|---|---|
| `C:\tools\voice-changer\server\voice_changer\DiffusionSVC\pitchExtractor\rmvpe\rmvpe.py` | コアクラス `RMVPE`, `E2E`, `MelSpectrogram` |
| `C:\tools\voice-changer\server\voice_changer\RVC\pitchExtractor\RMVPEPitchExtractor.py` | PyTorch 版ラッパー |
| `C:\tools\voice-changer\server\voice_changer\RVC\pitchExtractor\RMVPEOnnxPitchExtractor.py` | ONNX 版ラッパー |

**コアの `RMVPE` クラス** (`rmvpe.py` lines 335–426):
- `__init__(model_path, is_half, device)`: `torch.load(model_path, weights_only=False)` → `E2E` モデルにロード
- `infer_from_audio(audio: np.ndarray, thred=0.03) → np.ndarray (N,)`: メインの推論 API
  - 入力: 16kHz float32 1次元 numpy 配列
  - 出力: Hz 値 1次元 numpy 配列（無声=0、長さ = `len(audio)//hop_length`）
  - hop_length = 160（MelSpectrogram 固定、10ms/frame @16kHz）
- `infer_from_audio_t(audio: Tensor)`: PyTorch Tensor 版（VCClient RVC 用）
- 外部依存: `librosa.filters.mel`（`librosa` パッケージが必要）

**VCClient 独自の依存を除外する必要がある**:
```python
from mods.log_control import VoiceChangaerLogger  # ← VCClient 固有、除去が必要
logger = VoiceChangaerLogger.get_instance().getLogger()
```
この logger は `MelSpectrogram.forward()` の1行 (line 326) でのみ使われるため、
`import logging; logger = logging.getLogger(__name__)` に差し替えれば移植可能。

#### 本家 RVC (RVC-Project) の実装

出典: https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI  
参照ファイル: `infer/lib/rmvpe.py`（`RMVPE` クラス）

VCClient 版と実質同一コード。本家 RVC に同等実装が存在することを確認。  
（推測: どちらも共通の研究実装を元にしている）

### 3-2. モデルファイル

| ファイル | サイズ | 形式 | 備考 |
|---|---|---|---|
| `C:\tools\voice-changer\server\pretrain\rmvpe.pt` | 172 MB | PyTorch state_dict | `E2E(4, 1, (2, 2))` のパラメータ |
| `C:\tools\voice-changer\server\pretrain\rmvpe.onnx` | 345 MB | ONNX | PyTorch 版の約2倍サイズ |

### 3-3. PyTorch 版 vs ONNX 版 比較

| 観点 | PyTorch 版 (`rmvpe.pt`) | ONNX 版 (`rmvpe.onnx`) |
|---|---|---|
| 実装複雑度 | モデル定義クラス (~430行) が必要 | セッション1行でロード |
| 依存追加 | `librosa` のみ（既存依存の可能性あり） | `onnxruntime-gpu` が必要（現在未インストール） |
| onnxruntime | 不要 | **現在 venv に未インストール**（`pip list` で確認済み、requirements にも不在） |
| ファイルサイズ | 172 MB | 345 MB（2倍） |
| sm_120 対応 | torch 2.7.1+cu128 が完全対応 → **問題なし** | onnxruntime-gpu 1.22.0 の CUDAExecutionProvider に sm_120 JIT 警告の既知問題あり（後述） |
| 実績 | VCClient, 本家 RVC で広く使用 | VCClient RVC 版で使用（限定的） |

**結論: PyTorch 版 (`rmvpe.pt`) を推奨**

---

## 4. RTX 5090 / Blackwell 固有の考慮

### 4-1. PyTorch 版 (`rmvpe.pt`)

**確認済み**: torch 2.7.1+cu128 は sm_120 (RTX 5090) に完全対応。  
`E2E` モデルは Conv2d, GRU, BatchNorm2d などの標準演算のみ使用。  
すべて `torch.nn` 標準モジュールであり、sm_120 に固有の問題は発生しない。  
**追加対応不要。**

### 4-2. ONNX 版 (`rmvpe.onnx`)

**問題**: onnxruntime-gpu 1.22.0（現行 PyPI 最新）は sm_120 (Blackwell) の  
CUDAExecutionProvider が JIT コンパイルを必要とし、初回推論時に数十秒の  
`WARN: Failed to find PTX for sm_120` ログが出ることがある。  
（本ブランチの既知制約と同じ問題。Step 1 で把握済み。）

加えて、**onnxruntime-gpu は現在 venv に未インストール**であり、  
`requirements/main.txt` にも含まれていない。ONNX 版を採用する場合は  
インストール・検証コストが追加で発生する。

**結論: PyTorch 版を選択すれば ONNX 由来の問題はすべて回避できる。**

### 4-3. `weights_only` パッチ (`torch_compat.py`) との関係

`RMVPE.__init__()` (rmvpe.py line 339):
```python
ckpt = torch.load(model_path, map_location="cpu", weights_only=False)
```

**すでに `weights_only=False` が明示されている**（augment_path と同じパターン）。  
`torch_compat.py` の monkeypatch に依存せず直接指定するため、**追加対応不要**。

---

## 5. 実装方針

### 5-1. 新規ファイル: `lib/rvc/rmvpe.py`

VCClient の `rmvpe.py` から VCClient 固有依存を除去して移植。

**変更点**:
```python
# 除去
from mods.log_control import VoiceChangaerLogger
logger = VoiceChangaerLogger.get_instance().getLogger()

# 置換
import logging
logger = logging.getLogger(__name__)
```

変更はこの2行分のみ。それ以外のクラス定義・ロジックはそのまま移植。

**配置先**: `lib/rvc/rmvpe.py`  
**追加依存**: `librosa`（`librosa.filters.mel` を使用）  
→ **確認済み**: `requirements/main.txt` に `librosa==0.9.1` が既に存在。追加不要。

### 5-2. モデルファイルの配置

`models/pretrained/` 以下に配置することを推奨（既存 pretrain モデルと同じ場所）:
```
models/pretrained/rmvpe.pt
```

または `models/` 直下でも可。  
リポジトリへのコミットは行わない（172 MB は大きすぎる）。  
利用者が事前に入手して配置する運用（`VERIFY.md` に手順を追記）。

### 5-3. 変更が必要なファイルと内容

#### `lib/rvc/preprocessing/extract_f0.py`

1. import 追加: `from lib.rvc.rmvpe import RMVPE`（遅延 import が望ましい）
2. `compute_f0()` に分岐追加:
```python
elif f0_method == "rmvpe":
    rmvpe = RMVPE(model_path=RMVPE_MODEL_PATH, is_half=False, device=get_optimal_torch_device())
    f0 = rmvpe.infer_from_audio(x, thred=0.03)
    f0 = f0[1:]  # 他手法と同様に先頭フレームを除去
```
- `RMVPE_MODEL_PATH` は定数化するか引数で渡す（`processor` → `compute_f0` の引数を拡張）
- `rmvpe` インスタンスはファイルごとに再生成は非効率 → `processor` レベルで1回だけ生成して使い回す設計が適切

3. `run()` の選択肢制約は特になし（呼び出し元が文字列を渡すだけ）

4. `--pitch-algo` の `choices` 追加:
```python
# train_cli.py
p.add_argument("--pitch-algo", choices=["dio", "harvest", "crepe", "mangio-crepe", "rmvpe"])
```

#### `lib/rvc/pipeline.py`

`VocalConvertPipeline.get_f0()` に分岐追加:
```python
elif f0_method == "rmvpe":
    if not hasattr(self, '_rmvpe'):
        from lib.rvc.rmvpe import RMVPE
        self._rmvpe = RMVPE(model_path=RMVPE_MODEL_PATH, is_half=self.is_half, device=self.device)
    f0 = self._rmvpe.infer_from_audio(x.astype(np.float32), thred=0.03)
    f0 = f0 * pow(2, f0_up_key / 12)
    # 以降の量子化処理は harvest/dio と同じ（共通化可能）
```

- `RMVPE_MODEL_PATH` の解決: `VocalConvertPipeline.__init__()` で受け取るか、
  定数として `models/pretrained/rmvpe.pt` を参照

#### UI ファイル

```python
# modules/tabs/training.py line 360
choices=["dio", "harvest", "mangio-crepe", "crepe", "rmvpe"]

# modules/tabs/inference.py line 24-27
choices=["dio", "harvest", "mangio-crepe", "crepe", "rmvpe"]
```

### 5-4. 実装規模感

| 作業 | 新規/変更 | 目安行数 |
|---|---|---|
| `lib/rvc/rmvpe.py` 作成（移植） | 新規 | ~425行（ほぼコピー） |
| `lib/rvc/preprocessing/extract_f0.py` | 変更 | +15〜25行（分岐と RMVPE 生成） |
| `lib/rvc/pipeline.py` | 変更 | +10〜15行（分岐と遅延ロード） |
| `modules/tabs/training.py` | 変更 | +1行（choices に追加） |
| `modules/tabs/inference.py` | 変更 | +1行（choices に追加） |
| `train_cli.py` | 変更 | +1行（choices に追加） |
| `requirements/main.txt` | 変更不要 | librosa==0.9.1 が既に含まれている |
| `VERIFY.md` | 変更 | +数行（rmvpe.pt 配置手順） |

**合計**: 新規1ファイル + 7ファイル変更。実装難度は低い（rmvpe の核心は移植済みコード）。

### 5-5. リスク

| リスク | 内容 | 対処 |
|---|---|---|
| librosa 依存 | `requirements/main.txt` に `librosa==0.9.1` が確認済み | **対応不要** |
| RMVPE_MODEL_PATH の解決 | rmvpe.pt の配置先をどう参照するか | `models/pretrained/rmvpe.pt` を既定パスにし、なければスキップ or エラー |
| インスタンスの再生成コスト | 学習前処理でファイルごとに RMVPE をロードすると非常に遅い | `processor()` レベルで1回ロードして全ファイルに使い回す設計が必須 |
| `f0 = f0[1:]` の整合性 | VCClient では先頭フレーム除去なし、extract_f0 の他手法は除去あり | 学習/推論で統一する必要あり（extract_f0.py:52 参照） |
| ProcessPoolExecutor との相性 | extract_f0 が spawn workers を使う場合、RMVPE(172MB) を各ワーカーが再ロード | `num_processes=0` または rmvpe 専用パスで main thread 処理が安全 |

---

## まとめ

| 調査項目 | 結論 |
|---|---|
| f0 抽出の分岐箇所 | `compute_f0()` (extract_f0.py:96) と `get_f0()` (pipeline.py:134) の2箇所が核心 |
| 追加が必要な箇所（全体） | 上記2箇所 + UI 2タブ + train_cli.py + choices 更新の計5〜8ファイル |
| 推奨実装形式 | PyTorch 版 (`rmvpe.pt`)。ONNX は依存追加・sm_120 問題あり |
| weights_only 追加対応 | 不要（コード上 `weights_only=False` 明示済み） |
| Blackwell 固有問題 | PyTorch 版なら発生しない |
| 実装規模 | 新規1ファイル (rmvpe.py 移植) + 数ファイル小変更。難度低 |
| 主なリスク | RMVPE インスタンスの使い回し設計、librosa 依存確認 |
