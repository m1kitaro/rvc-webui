"""
train_cli.py — gradio を一切経由せず train_model を直接呼ぶ CLI。

使い方:
  # 前処理・特徴抽出・学習をすべて実行
  venv\Scripts\python train_cli.py --model-name MySpeaker --dataset "data/**/*.wav"

  # 特徴抽出まで完了済み → 学習だけ実行（切り分け用）
  venv\Scripts\python train_cli.py --model-name MySpeaker --dataset "data/**/*.wav" --train-only

引数は下部「デフォルト値」セクションで直接書き換えることもできる。
"""

import argparse
import os
import sys

# webui.py を介さず直接起動するため sys.path にリポジトリ直下を追加
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# bin/ffmpeg.exe（install_ffmpeg が配置）を PATH 先頭に追加
# lib/rvc/utils.py の _ffmpeg_cmd() が絶対パスで解決するが、
# ffmpeg-python の内部呼び出し等に備えて PATH にも登録しておく
_bin_dir = os.path.join(ROOT_DIR, "bin")
os.environ["PATH"] = _bin_dir + os.pathsep + os.environ.get("PATH", "")

# torch_compat を最初に適用（weights_only=False パッチ）
import modules.torch_compat  # noqa: F401

# ── デフォルト値（CLI 引数で上書き可能） ─────────────────────────────
DEFAULTS = {
    "model_name": "MySpeaker",
    "dataset_glob": "data/**/*.wav",
    "version": "v2",
    "sampling_rate": "40k",       # "32k" / "40k" / "48k"
    "f0": True,
    "speaker_id": 0,
    "multiple_speakers": False,
    "recursive": True,
    "gpu_id": "0",                # カンマ区切りで複数指定可: "0,1"
    "num_cpu_process": 4,
    "norm_audio": True,
    "pitch_algo": "crepe",        # "dio" / "harvest" / "crepe" / "mangio-crepe"
    "batch_size": 4,
    "num_epochs": 30,
    "save_every_epoch": 10,
    "save_wav_with_checkpoint": False,
    "fp16": False,
    "save_only_last": False,
    "cache_batch": True,
    "augment": False,
    "augment_from_pretrain": False,
    "augment_pretrain_g": "",
    "speaker_info": "",
    "embedder_name": "hubert-base-japanese",
    "embedding_channels": 768,    # 256 / 768
    "embedding_output_layer": 12, # 9 / 12
    "run_train_index": True,
    "reduce_index_size": False,
    "maximum_index_size": 10000,
    "ignore_cache": False,
    "pretrain_g": "",             # 空文字 = モデルディレクトリ既定値を使う
    "pretrain_d": "",
}
# ─────────────────────────────────────────────────────────────────────


def parse_args():
    p = argparse.ArgumentParser(description="RVC training CLI (no gradio)")
    p.add_argument("--model-name", default=DEFAULTS["model_name"])
    p.add_argument("--dataset", default=DEFAULTS["dataset_glob"], dest="dataset_glob")
    p.add_argument("--version", default=DEFAULTS["version"], choices=["v1", "v2"])
    p.add_argument("--sr", default=DEFAULTS["sampling_rate"], choices=["32k", "40k", "48k"],
                   dest="sampling_rate")
    p.add_argument("--no-f0", action="store_true", help="Disable f0 model")
    p.add_argument("--speaker-id", type=int, default=DEFAULTS["speaker_id"])
    p.add_argument("--multiple-speakers", action="store_true",
                   default=DEFAULTS["multiple_speakers"])
    p.add_argument("--no-recursive", action="store_false", dest="recursive",
                   help="Disable recursive glob (recursive=True by default)")
    p.add_argument("--gpu", default=DEFAULTS["gpu_id"], dest="gpu_id",
                   help="GPU ID(s), comma separated")
    p.add_argument("--num-cpu", type=int, default=DEFAULTS["num_cpu_process"])
    p.add_argument("--pitch-algo", default=DEFAULTS["pitch_algo"],
                   choices=["dio", "harvest", "crepe", "mangio-crepe"])
    p.add_argument("--batch-size", type=int, default=DEFAULTS["batch_size"])
    p.add_argument("--epochs", type=int, default=DEFAULTS["num_epochs"])
    p.add_argument("--save-every", type=int, default=DEFAULTS["save_every_epoch"])
    p.add_argument("--embedder", default=DEFAULTS["embedder_name"])
    p.add_argument("--emb-channels", type=int, default=DEFAULTS["embedding_channels"],
                   choices=[256, 768])
    p.add_argument("--emb-layer", type=int, default=DEFAULTS["embedding_output_layer"],
                   choices=[9, 12])
    p.add_argument("--fp16", action="store_true")
    p.add_argument("--save-only-last", action="store_true")
    p.add_argument("--cache-batch", action="store_true", default=DEFAULTS["cache_batch"])
    p.add_argument("--no-train-index", action="store_true")
    p.add_argument("--ignore-cache", action="store_true")
    p.add_argument("--pretrain-g", default=DEFAULTS["pretrain_g"])
    p.add_argument("--pretrain-d", default=DEFAULTS["pretrain_d"])
    p.add_argument(
        "--train-only",
        action="store_true",
        help="前処理・特徴抽出をスキップし train_model だけ実行する（切り分け用）",
    )
    p.add_argument(
        "--force-extract",
        action="store_true",
        help="前回の失敗で残った空の抽出ディレクトリを削除して再抽出を強制する",
    )
    p.add_argument(
        "--augment",
        action="store_true",
        help="学習ループ内でのデータオーグメンテーションを有効化する",
    )
    p.add_argument(
        "--augment-from-pretrain",
        action="store_true",
        help="外部の多話者事前学習済みジェネレータを augment に使う（--augment と併用）",
    )
    p.add_argument(
        "--augment-pretrain-g",
        default=DEFAULTS["augment_pretrain_g"],
        dest="augment_pretrain_g",
        metavar="PATH",
        help="augment 用ジェネレータ .pth のパス（--augment-from-pretrain 時に有効）",
    )
    p.add_argument(
        "--speaker-info",
        default=DEFAULTS["speaker_info"],
        dest="speaker_info",
        metavar="PATH",
        help="speaker_info.npy のパス（--augment-from-pretrain 時に有効）",
    )
    p.set_defaults(recursive=DEFAULTS["recursive"])
    return p.parse_args()


SR_DICT = {"32k": 32000, "40k": 40000, "48k": 48000}


def main():
    args = parse_args()

    from modules.models import get_embedder, MODELS_DIR
    from modules.utils import load_config
    from lib.rvc.train import (
        create_dataset_meta,
        glob_dataset,
        train_index,
        train_model,
    )
    from lib.rvc.preprocessing import extract_f0, extract_feature, split

    f0 = not args.no_f0
    gpu_ids = [int(x.strip()) for x in args.gpu_id.split(",") if x.strip()]
    training_dir = os.path.join(MODELS_DIR, "training", "models", args.model_name)
    out_dir = os.path.join(MODELS_DIR, "checkpoints")

    # device は shared から（cuda:0 または cpu/mps）
    from modules.shared import device as shared_device
    device = None if len(gpu_ids) > 1 else shared_device

    # pretrain パス: 空文字のときは標準ディレクトリの既定ファイルを使う
    def default_pretrain(kind):
        base = os.path.join(MODELS_DIR, "pretrained", args.version)
        prefix = "f0" if f0 else ""
        return os.path.join(base, f"{prefix}{kind}{args.sampling_rate}.pth")

    pretrain_g = args.pretrain_g or default_pretrain("G")
    pretrain_d = args.pretrain_d or default_pretrain("D")

    os.makedirs(training_dir, exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)

    # ── embedder 解決 ───────────────────────────────────────────────
    embedder_filepath, _, embedder_load_from = get_embedder(args.embedder)
    if embedder_load_from == "local":
        embedder_filepath = os.path.join(MODELS_DIR, "embeddings", embedder_filepath)

    def count_npy(directory):
        n = sum(1 for _, _, fs in os.walk(directory) for f in fs if f.endswith(".npy"))
        return n

    def count_wav(directory):
        n = sum(1 for _, _, fs in os.walk(directory) for f in fs if f.endswith(".wav"))
        return n

    def force_remove_if_empty(directory):
        """前回の失敗で残った空ディレクトリを削除して再抽出ガードをリセットする。"""
        import shutil
        if os.path.exists(directory) and count_npy(directory) == 0:
            print(f"[force-extract] 空ディレクトリを削除: {directory}", flush=True)
            shutil.rmtree(directory)

    # ── --train-only: 前処理・特徴抽出をスキップ ──────────────────
    if args.train_only:
        print("=== --train-only: 前処理・特徴抽出をスキップ ===", flush=True)
        print(f"training_dir: {training_dir}", flush=True)
        # 抽出結果の件数を表示して空かどうか確認
        f0_dir = os.path.join(training_dir, "2a_f0")
        feat_dir = os.path.join(training_dir, "3_feature256")
        print(f"  2a_f0       : {count_npy(f0_dir)} files", flush=True)
        print(f"  3_feature256: {count_npy(feat_dir)} files", flush=True)
        if count_npy(feat_dir) == 0:
            print("WARNING: 3_feature256 が空です。--force-extract なしで再抽出するには"
                  " --train-only を外してください。", flush=True)
    else:
        # ── --force-extract: 空の抽出ディレクトリを削除 ──────────
        if args.force_extract:
            for d in ["2a_f0", "2b_f0nsf", "3_feature256"]:
                force_remove_if_empty(os.path.join(training_dir, d))

        # ── 前処理 ────────────────────────────────────────────────
        print("=== 前処理 (split/preprocess_audio) ===", flush=True)
        datasets = glob_dataset(
            args.dataset_glob,
            args.speaker_id,
            multiple_speakers=args.multiple_speakers,
            recursive=args.recursive,
            training_dir=training_dir,
        )
        if len(datasets) == 0:
            print("ERROR: データセットが見つかりません:", args.dataset_glob)
            sys.exit(1)

        split.preprocess_audio(
            datasets,
            SR_DICT[args.sampling_rate],
            args.num_cpu,
            training_dir,
            DEFAULTS["norm_audio"],
            os.path.join(
                MODELS_DIR, "training", "mute", "0_gt_wavs",
                f"mute{args.sampling_rate}.wav",
            ),
        )
        print(f"  0_gt_wavs: {count_wav(os.path.join(training_dir, '0_gt_wavs'))} files", flush=True)
        print(f"  1_16k_wavs: {count_wav(os.path.join(training_dir, '1_16k_wavs'))} files", flush=True)

        if f0:
            print("=== f0 抽出 ===", flush=True)
            try:
                extract_f0.run(training_dir, args.num_cpu, args.pitch_algo)
            except Exception as e:
                print(f"ERROR: f0 抽出で例外が発生しました: {e}", flush=True)
                import traceback; traceback.print_exc()
                sys.exit(1)
            n_f0 = count_npy(os.path.join(training_dir, "2a_f0"))
            print(f"  2a_f0: {n_f0} files after extraction", flush=True)
            if n_f0 == 0:
                print("ERROR: f0 抽出の出力が 0 件です。上記ログを確認してください。", flush=True)
                sys.exit(1)

        print("=== 特徴抽出 ===", flush=True)
        print(f"  embedder: {args.embedder}  path: {embedder_filepath}", flush=True)
        try:
            extract_feature.run(
                training_dir,
                embedder_filepath,
                embedder_load_from,
                args.emb_channels,
                args.emb_layer,
                gpu_ids,
                device,
            )
        except Exception as e:
            print(f"ERROR: 特徴抽出で例外が発生しました: {e}", flush=True)
            import traceback; traceback.print_exc()
            sys.exit(1)
        n_feat = count_npy(os.path.join(training_dir, "3_feature256"))
        print(f"  3_feature256: {n_feat} files after extraction", flush=True)
        if n_feat == 0:
            print("ERROR: 特徴抽出の出力が 0 件です。上記ログを確認してください。", flush=True)
            sys.exit(1)

        create_dataset_meta(training_dir, f0)

    # ── 学習 ──────────────────────────────────────────────────────
    print("=== train_model 開始 ===", flush=True)

    config = load_config(
        args.version,
        training_dir,
        args.sampling_rate,
        args.emb_channels,
        args.fp16,
    )

    # augment_from_pretrain=True のときだけ外部パスを使う（UI の train_all と等価）
    if args.augment and args.augment_from_pretrain:
        augment_path = args.augment_pretrain_g or None
        speaker_info_path = args.speaker_info or None
    else:
        augment_path = None
        speaker_info_path = None

    if args.augment:
        print(f"  augment=True  from_pretrain={args.augment_from_pretrain}", flush=True)
        if augment_path:
            print(f"  augment_pretrain_g: {augment_path}", flush=True)
            print(f"  speaker_info: {speaker_info_path}", flush=True)
        else:
            print("  augment_path=None: 自前データから speaker_info を自動計算", flush=True)

    train_model(
        gpu_ids,
        config,
        training_dir,
        args.model_name,
        out_dir,
        args.sampling_rate,
        f0,
        args.batch_size,
        args.augment,        # bool（--augment 指定時のみ True）
        augment_path,        # str | None
        speaker_info_path,   # str | None
        args.cache_batch,
        args.epochs,
        args.save_every,
        DEFAULTS["save_wav_with_checkpoint"],
        pretrain_g,
        pretrain_d,
        args.embedder,
        args.emb_layer,
        args.save_only_last,
        device,
    )

    # ── index 作成 ────────────────────────────────────────────────
    if not args.no_train_index:
        print("=== train_index ===", flush=True)
        train_index(
            training_dir,
            args.model_name,
            out_dir,
            args.emb_channels,
            args.num_cpu,
            DEFAULTS["maximum_index_size"] if not DEFAULTS["reduce_index_size"] else None,
        )

    print("=== 完了 ===", flush=True)


if __name__ == "__main__":
    main()
