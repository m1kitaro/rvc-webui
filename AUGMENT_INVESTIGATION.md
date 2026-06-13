# Augmentation 機能 調査レポート

対象ブランチ: `feature/blackwell-support`  
調査日: 2026-06-13

---

## 1. UI コールバック (`train_all`) での引数の流れ

**出典**: `modules/tabs/training.py`

### 1-1. UI コンポーネント定義（行番号）

| UI コンポーネント | 変数名 | 型 | デフォルト |
|---|---|---|---|
| "Augment" チェックボックス | `augment` | `gr.Checkbox` | `False` (line 388) |
| "Augment From Pretrain" チェックボックス | `augment_from_pretrain` | `gr.Checkbox` | `False` (line 390) |
| "Pre trained generator path (pth)" テキスト | `augment_path` | `gr.Textbox` | `"file is not prepared"` (line 393) |
| "speaker info path (npy)" テキスト | `speaker_info_path` | `gr.Textbox` | `"file is not prepared"` (line 397) |

### 1-2. `train_all` 内での加工ロジック (lines 244–270)

```python
# augment_from_pretrain が False の場合、augment_path と speaker_info_path を None に強制
if not augment_from_pretrain:
    augment_path = None
    speaker_info_path = None

train_model(
    gpu_ids, config, training_dir, model_name, out_dir,
    sampling_rate_str, f0, batch_size,
    augment,           # bool
    augment_path,      # str | None
    speaker_info_path, # str | None
    cache_batch, num_epochs, save_every_epoch, save_wav_with_checkpoint,
    pre_trained_bottom_model_g, pre_trained_bottom_model_d,
    embedder_name, int(embedding_output_layer), save_only_last,
    None if len(gpu_ids) > 1 else device,
)
```

**重要な挙動**:
- `augment=True` かつ `augment_from_pretrain=False` の場合:
  `augment_path=None`, `speaker_info_path=None` で `train_model` が呼ばれる。
  この組み合わせは「自前データから speaker_info を自動計算する」モード（後述）。
- `augment=True` かつ `augment_from_pretrain=True` の場合:
  UI のテキストボックス値がそのまま `augment_path`, `speaker_info_path` に入る。

---

## 2. `train_model` → `training_runner` でのオーグメンテーション処理

### 2-1. シグネチャ伝播

`lib/rvc/train.py`:

- `train_model` (line 306): `augment: bool`, `augment_path: Optional[str]`, `speaker_info_path: Optional[str]` を受け取り、そのまま `training_runner` に渡す (lines 355-357, 382-384)。
- `training_runner` (line 411): 同じ3引数を受け取る (lines 421-423)。

### 2-2. `training_runner` 内のオーグメンテーション処理

**処理タイミング**: 学習ループ開始直前（モデルロード・チェックポイント復元の後、DDP ラップの前）。(lines 626–662)

#### ケース A: `augment=True`, `augment_path is not None`（Augment From Pretrain=True）

```python
# line 638-651
state_dict = torch.load(augment_path, map_location="cpu", weights_only=False)
if state_dict["f0"] == 1:
    augment_net_g = SynthesizerTrnMs256NSFSid(**state_dict["params"], ...)
    augment_speaker_info = np.load(speaker_info_path)   # ← .npy を読む
else:
    augment_net_g = SynthesizerTrnMs256NSFSidNono(**state_dict["params"], ...)

augment_net_g.load_state_dict(state_dict["weight"], strict=False)
augment_net_g.eval().to(device)
```

- `augment_path` (.pth): 多話者事前学習済みジェネレータのチェックポイント。
  キー `"f0"`, `"params"`, `"weight"` を持つ `save()` 形式 (`lib/rvc/checkpoints.py` 参照)。
- `speaker_info_path` (.npy): shape `(N,)` の float 配列。
  各話者のピッチ中央値 [Hz] を格納。`change_speaker()` が話者選択とピッチスケーリングに使用 (lines 176-178)。

#### ケース B: `augment=True`, `augment_path is None`（Augment From Pretrain=False）

```python
# lines 654-662
augment_net_g = net_g   # 学習対象ネットワーク自身を流用
if f0:
    # 自前データの f0nsf ファイルからピッチ中央値を計算
    medians = [[] for _ in range(augment_net_g.spk_embed_dim)]
    for file in training_meta.files.values():
        f0f = np.load(file.f0nsf)
        if np.any(f0f > 0):
            medians[file.speaker_id].append(np.median(f0f[f0f > 0]))
    augment_speaker_info = np.array([np.median(x) if len(x) else 0. for x in medians])
    np.save(os.path.join(training_dir, "speaker_info.npy"), augment_speaker_info)
```

- 外部モデルを使わず、学習データの f0 から `speaker_info` を自動生成して保存する。
- `f0=False` の場合は `augment_speaker_info` は未定義のまま（`change_speaker_nono` が speaker_info を使わないため問題なし）。

#### ケース C: `augment=False`

augment ブロック全体がスキップ。`augment_net_g`, `augment_speaker_info`, `embedder` は定義されない。
学習ループ内の `if augment:` ブロック (line 779) も実行されない。

### 2-3. 学習ループ内でのオーグメンテーション処理 (lines 779–786)

各バッチで実行:

```python
if augment:
    with torch.no_grad():
        if type(augment_net_g) == SynthesizerTrnMs256NSFSid:  # f0 モデル
            new_phone, aug_wave = change_speaker(
                augment_net_g, augment_speaker_info, embedder,
                embedding_output_layer, phone, phone_lengths, pitch, pitchf, spec_lengths
            )
        else:                                                   # nono モデル
            new_phone, aug_wave = change_speaker_nono(
                augment_net_g, embedder, embedding_output_layer,
                phone, phone_lengths, spec_lengths
            )
        # 学習初期は元の phone を重視、徐々に augmented に移行
        weight = np.power(.5, step / len(train_loader))
        phone = phone * weight + new_phone * (1. - weight)
```

**処理内容** (`change_speaker`, lines 154–203):
1. バッチ内の各サンプルについてランダムに別話者を選ぶ
2. その話者のピッチ中央値でピッチをスケール
3. `augment_net_g.infer()` で合成音声を生成（ターゲット話者の声質で）
4. その合成音声を embedder に通して phone 特徴を再計算
5. 元の phone と augmented phone を `weight` で線形補間

**目的**: 話者変換によるデータ拡張 → embedder の声質独立性を向上させる。

### 2-4. augment と embedder の関係

augment ブロック (line 626-636) では、`training_runner` 自身が `get_embedder()` / `load_embedder()` を呼んで **embedder を GPU にロードする**:

```python
embedder_filepath, _, embedder_load_from = get_embedder(embedder_name)
if embedder_load_from == "local":
    embedder_filepath = os.path.join(MODELS_DIR, "embeddings", embedder_filepath)
embedder, _ = load_embedder(embedder_filepath, device)
if not config.train.fp16_run:
    embedder = embedder.float()
```

- `embedder_name` は `training_runner` の引数として渡ってくる（= `train_cli.py` の `args.embedder`）。
- `load_embedder` は `lib/rvc/preprocessing/extract_feature.py` (line 32) からインポート。
  内部では `checkpoint_utils.load_model_ensemble_and_task` (fairseq) を使う。

---

## 3. 現在の `train_cli.py` の状況と差分

**出典**: `train_cli.py` lines 267–292

```python
# 現在の train_model 呼び出し（関連部分）
train_model(
    gpu_ids, config, training_dir, args.model_name, out_dir,
    args.sampling_rate, f0, args.batch_size,
    False,               # augment      ← ハードコード False
    None,                # augment_path ← ハードコード None
    None,                # speaker_info_path ← ハードコード None
    ...
)
```

また `train_cli.py` の `DEFAULTS` 辞書 (lines 35-36) でも augment 関連は明示的に:
```python
"augment": False,
"augment_path": "",
"speaker_info_path": "",
```
となっており、argparse 引数は一切定義されていない。

**UI との差分**:

| 項目 | UI (train_all) | train_cli.py (現在) |
|---|---|---|
| `augment` | チェックボックスの値 | 常に `False` |
| `augment_path` | augment_from_pretrain=True 時に UI 入力値 | 常に `None` |
| `speaker_info_path` | augment_from_pretrain=True 時に UI 入力値 | 常に `None` |

---

## 4. `weights_only` パッチの有効性確認

### augment_path のロード (line 639)

```python
state_dict = torch.load(augment_path, map_location="cpu", weights_only=False)
```

`weights_only=False` が **すでにソースコードに明示**されている（Step 3 パッチ適用済み）。
`torch_compat.py` の monkeypatch に依存せず、直接 `weights_only=False` を指定しているため、
**追加対応は不要**。

### speaker_info_path のロード (line 644)

```python
augment_speaker_info = np.load(speaker_info_path)
```

`numpy.load` であり `torch.load` ではない。`torch_compat.py` の対象外。
numpy の `.npy` 形式はバージョン互換性の問題がないため、**追加対応不要**。

### augment_net_g の embedder ロード (line 634)

```python
embedder, _ = load_embedder(embedder_filepath, device)
```

`load_embedder` の実体は `checkpoint_utils.load_model_ensemble_and_task` (fairseq)。
これは `torch_compat.py` が monkeypatch した `torch.load` 経由でロードするため、
`weights_only=False` が自動適用される。**追加対応不要**。

### 結論

augment に関連するすべてのチェックポイントロードで `weights_only` 問題は発生しない。

---

## 5. 実装方針: `train_cli.py` への追加

### 5-1. 追加する CLI 引数

```
--augment                  : オーグメンテーション有効化 (bool, default: False)
--augment-from-pretrain    : 外部事前学習モデルを使う (bool, default: False)
--augment-pretrain-g PATH  : augment 用 generator .pth のパス (str, default: "")
--speaker-info PATH        : speaker_info.npy のパス (str, default: "")
```

UI の `augment_from_pretrain` フラグが `augment_path` / `speaker_info_path` を
`None` に強制する処理を CLI でも再現する必要がある（UI との等価性）。

### 5-2. `parse_args()` への追加

```python
p.add_argument("--augment", action="store_true",
               help="データオーグメンテーションを有効化")
p.add_argument("--augment-from-pretrain", action="store_true",
               help="外部事前学習モデルを使った augment")
p.add_argument("--augment-pretrain-g", default="",
               dest="augment_pretrain_g",
               help="augment 用 generator .pth のパス")
p.add_argument("--speaker-info", default="",
               dest="speaker_info",
               help="speaker_info.npy のパス (--augment-from-pretrain と併用)")
```

### 5-3. `train_model` 呼び出しへの変更

`train_all` の処理 (lines 244–246) と等価になるよう:

```python
# augment_from_pretrain が False の場合、augment_path と speaker_info_path を None に
if args.augment and args.augment_from_pretrain:
    augment_path = args.augment_pretrain_g or None
    speaker_info_path = args.speaker_info or None
else:
    augment_path = None
    speaker_info_path = None

train_model(
    gpu_ids, config, training_dir, args.model_name, out_dir,
    args.sampling_rate, f0, args.batch_size,
    args.augment,       # bool
    augment_path,       # str | None
    speaker_info_path,  # str | None
    args.cache_batch, args.epochs, args.save_every,
    DEFAULTS["save_wav_with_checkpoint"],
    pretrain_g, pretrain_d,
    args.embedder, args.emb_layer,
    args.save_only_last, device,
)
```

### 5-4. 使用例

```bat
REM ケース A: 外部 augment モデルを使う（Augment From Pretrain=True 相当）
venv\Scripts\python train_cli.py ^
  --model-name MySpeaker ^
  --train-only ^
  --augment ^
  --augment-from-pretrain ^
  --augment-pretrain-g "models\pretrained\vctk_multispeaker_jphubert_augment_f048k768.pth" ^
  --speaker-info "models\pretrained\speaker_info.npy" ^
  --embedder hubert-base-japanese ^
  --emb-channels 768 --emb-layer 12 --epochs 30 --batch-size 4 --gpu 0

REM ケース B: 自前データから speaker_info を自動計算（Augment=True, From Pretrain=False 相当）
venv\Scripts\python train_cli.py ^
  --model-name MySpeaker ^
  --train-only ^
  --augment ^
  --embedder hubert-base-japanese ^
  --emb-channels 768 --emb-layer 12 --epochs 30 --batch-size 4 --gpu 0
```

### 5-5. 注意事項

- `--augment-from-pretrain` なしで `--augment-pretrain-g` を指定しても無視される（UI と同じ挙動）。
- ケース B（`augment_path=None`）では `2b_f0nsf` の `.npy` ファイルが必要。
  `--train-only` 実行前に f0 抽出が完了していることが前提。
- augment 有効時は学習ループ内で毎バッチ `augment_net_g.infer()` が走るため、
  VRAM 使用量が増加する。`augment_net_g` はバッチ推論のみで勾配計算なし（`torch.no_grad()`）。
- 現在の `train_cli.py` の `augment_path` 変数 (line 267) は `args.pretrain_g` を参照しており、
  これは**誤り**（pretrain_g は backbone 事前学習モデル用。augment 用パスは別引数として追加が必要）。
  実装時に削除すること。

---

## まとめ

| 調査項目 | 結論 |
|---|---|
| UI での引数の流れ | `augment` / `augment_from_pretrain` → `augment_path` / `speaker_info_path` の 2 段階加工後に `train_model` へ |
| 学習での使用タイミング | 学習ループ開始直前（モデル初期化後）の embedder/augment_net_g 準備と、各バッチの phone 特徴差し替え |
| CLI との差分 | `augment=False, augment_path=None, speaker_info_path=None` にハードコードされている |
| `weights_only` パッチ | augment_path ロードはすでに `weights_only=False` 明示済み。numpy.load は対象外。追加不要 |
| 実装に必要な変更 | 引数 4 つの追加と `train_model` 呼び出し 1 箇所の変更のみ |
