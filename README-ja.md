<h1 align="center">RVC-WebUI</h1>
<div align="center">
<p>

[`liujing04/Retrieval-based-Voice-Conversion-WebUI`](https://github.com/liujing04/Retrieval-based-Voice-Conversion-WebUI) の再構築プロジェクト

</p>
</div>

---

<div align="center">
<p>

[日本語](README-ja.md) | [English](README.md)

</p>
</div>

<br >

# 起動

## Windows
`webui-user.bat` をダブルクリックして、webuiを起動します。

## Linux or Mac
`webui.sh` を実行して、webuiを起動します。

<br >

```
動作確認環境: Windows 11, Python 3.10, torch 2.7.1+cu128, RTX 5090 (Blackwell / sm_120)
```

<br >

# このフォークでの変更点

upstream ([ddPn08/rvc-webui](https://github.com/ddPn08/rvc-webui)) に対して以下を追加しています。

- **RMVPE ピッチ抽出対応** — 学習・推論の両方で `rmvpe` を選択可能
- **`train_cli.py`** — Gradio を介さず CLI から学習を実行できるスクリプト

<br >

# train_cli.py の使い方

WebUI を使わずにコマンドラインから学習できます。

```bat
:: 前処理・特徴抽出・学習をすべて実行
venv\Scripts\python train_cli.py ^
  --model-name MySpeaker ^
  --dataset "data\**\*.wav" ^
  --pitch-algo rmvpe ^
  --epochs 100 ^
  --save-every 10

:: 特徴抽出まで完了済み → 学習だけ実行
venv\Scripts\python train_cli.py --model-name MySpeaker --dataset "data\**\*.wav" --train-only

:: 特徴抽出だけ実行して停止（学習・index 作成はしない）
venv\Scripts\python train_cli.py --model-name MySpeaker --dataset "data\**\*.wav" --extract-only
```

主なオプション:

| オプション | デフォルト | 説明 |
|---|---|---|
| `--model-name` | `MySpeaker` | モデル名 |
| `--dataset` | `data/**/*.wav` | 学習データの glob パターン |
| `--sr` | `40k` | サンプリングレート (`32k` / `40k` / `48k`) |
| `--pitch-algo` | `crepe` | ピッチ抽出アルゴリズム (`dio` / `harvest` / `crepe` / `mangio-crepe` / `rmvpe`) |
| `--epochs` | `30` | 学習エポック数 |
| `--batch-size` | `4` | バッチサイズ |
| `--gpu` | `0` | 使用 GPU ID（カンマ区切りで複数指定可） |
| `--train-only` | — | 前処理・特徴抽出をスキップし学習のみ実行 |
| `--extract-only` | — | 特徴抽出まで実行し学習・index 作成をスキップ |
| `--fp16` | — | FP16 学習を有効化 |

全オプションは `venv\Scripts\python train_cli.py --help` で確認できます。

## RMVPE を使う場合の追加準備

[rmvpe.pt](https://huggingface.co/lj1995/VoiceConversionWebUI/blob/main/rmvpe.pt) をダウンロードし、以下に配置してください。

```
models/pretrained/rmvpe.pt
```

<br >

# トラブルシューティング

## `error: Microsoft Visual C++ 14.0 or greater is required.`

Microsoft C++ Build Tools がインストールされている必要があります。

### Step 1: インストーラーをダウンロード
[Download](https://visualstudio.microsoft.com/ja/thank-you-downloading-visual-studio/?sku=BuildTools&rel=16)

### Step 2: `C++ Build Tools` をインストール
インストーラーを実行し、`Workloads` タブで `C++ Build Tools` を選択します。

<br >

# クレジット
- [`liujing04/Retrieval-based-Voice-Conversion-WebUI`](https://github.com/liujing04/Retrieval-based-Voice-Conversion-WebUI)
- [`teftef6220/Voice_Separation_and_Selection`](https://github.com/teftef6220/Voice_Separation_and_Selection)
