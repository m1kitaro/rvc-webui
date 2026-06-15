<h1 align="center">RVC-WebUI</h1>
<div align="center">
<p>

[`liujing04/Retrieval-based-Voice-Conversion-WebUI`](https://github.com/liujing04/Retrieval-based-Voice-Conversion-WebUI) reconstruction project

</p>
</div>

---

<div align="center">
<p>

[日本語](README-ja.md) | [English](README.md)

</p>
</div>

<br >

# Launch

## Windows
Double click `webui-user.bat` to start the webui.

## Linux or Mac
Run `webui.sh` to start the webui.

<br >

```
Tested environment: Windows 11, Python 3.10, torch 2.7.1+cu128, RTX 5090 (Blackwell / sm_120)
```

<br >

# Changes in this fork

The following features are added on top of upstream ([ddPn08/rvc-webui](https://github.com/ddPn08/rvc-webui)):

- **RMVPE pitch extraction** — available in both training and inference tabs
- **`train_cli.py`** — train models directly from the command line without Gradio

<br >

# train_cli.py usage

Train models from the command line without the WebUI.

```bat
:: Full pipeline: preprocess → extract → train
venv\Scripts\python train_cli.py ^
  --model-name MySpeaker ^
  --dataset "data\**\*.wav" ^
  --pitch-algo rmvpe ^
  --epochs 100 ^
  --save-every 10

:: Skip preprocessing/extraction, run training only
venv\Scripts\python train_cli.py --model-name MySpeaker --dataset "data\**\*.wav" --train-only

:: Run extraction only, skip training and index creation
venv\Scripts\python train_cli.py --model-name MySpeaker --dataset "data\**\*.wav" --extract-only
```

Key options:

| Option | Default | Description |
|---|---|---|
| `--model-name` | `MySpeaker` | Model name |
| `--dataset` | `data/**/*.wav` | Glob pattern for training data |
| `--sr` | `40k` | Sample rate (`32k` / `40k` / `48k`) |
| `--pitch-algo` | `crepe` | Pitch algorithm (`dio` / `harvest` / `crepe` / `mangio-crepe` / `rmvpe`) |
| `--epochs` | `30` | Number of training epochs |
| `--batch-size` | `4` | Batch size |
| `--gpu` | `0` | GPU ID(s), comma-separated for multi-GPU |
| `--train-only` | — | Skip preprocessing/extraction, run training only |
| `--extract-only` | — | Run extraction only, skip training and index creation |
| `--fp16` | — | Enable FP16 training |
| `--no-cache-batch` | — | Disable batch VRAM cache (prevents VRAM exhaustion on large datasets) |

Run `venv\Scripts\python train_cli.py --help` for all options.

## Additional setup for RMVPE

Download [rmvpe.pt](https://huggingface.co/lj1995/VoiceConversionWebUI/blob/main/rmvpe.pt) and place it at:

```
models/pretrained/rmvpe.pt
```

<br >

# Troubleshooting

## `error: Microsoft Visual C++ 14.0 or greater is required.`

Microsoft C++ Build Tools must be installed.

### Step 1: Download the installer
[Download](https://visualstudio.microsoft.com/ja/thank-you-downloading-visual-studio/?sku=BuildTools&rel=16)

### Step 2: Install `C++ Build Tools`
Run the installer and select `C++ Build Tools` in the `Workloads` tab.

<br >

# Credits
- [`liujing04/Retrieval-based-Voice-Conversion-WebUI`](https://github.com/liujing04/Retrieval-based-Voice-Conversion-WebUI)
- [`teftef6220/Voice_Separation_and_Selection`](https://github.com/teftef6220/Voice_Separation_and_Selection)
