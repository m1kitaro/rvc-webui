# 作業指示書: rvc-webui (ddPn08版) の RTX 50xx (Blackwell) 対応

## 0. この文書について

- 対象リポジトリ: https://github.com/ddPn08/rvc-webui のフォーク
- 作業ブランチ: `feature/blackwell-support`(フォーク時点の main/master HEAD 起点)
- このブランチ上でのみ作業すること。ブランチの切り替え・他ブランチへのコミットは禁止
- 作業者: AIコーディングエージェント
- レビュー: 別のAIエージェントが実施
- 最終動作検証: **人間が RTX 5090 搭載の Windows 実機で行う。エージェント側では GPU 動作確認はできない前提で作業すること**
- 本タスクは学習ツールの改修である。利用者はこのツールで hubert-base-japanese (rinna) を embedder とした RVC モデルを学習し、別途改修済みの VCClient v1 で推論する

## 1. 背景

- rvc-webui は2023年で更新が停止しており、torch 2.0 世代(CUDA 11.x)を前提としている
- RTX 5090 (Blackwell, compute capability sm_120) には CUDA 11.x 世代のビルドのカーネルが存在せず、エラー(no kernel image)または極端に遅い PTX JIT になる
- 同一の問題系を VCClient v1 で解決済み(参照: voice-changer フォークの INSTRUCTIONS_blackwell.md / WORKLOG.md)。確定済みの知見:
  - torch 2.7.1+cu128 が sm_120 をネイティブサポート(Windows wheel は cuDNN 9 DLL 同梱)
  - Python 3.10 必須(fairseq 0.12.2 が 3.11+ でビルド不可)
  - torch 2.6+ の `torch.load` デフォルト変更(`weights_only=True`)により fairseq チェックポイントのロードが
    `UnpicklingError: ... fairseq.data.dictionary.Dictionary was not an allowed global` で失敗する
    (本家 RVC 系でも同一報告あり)。対処は `weights_only=False` の明示
  - numpy は `<2` に固定が安全
  - Windows での fairseq ビルドには VS Build Tools (C++) が必要(利用者の実機には導入済み)
- 改修前のベースライン(利用者が実機で採取・2026-06-13): **起動不能**。launch 時の依存インストールで
  固定されていない推移的依存が最新版に解決され、
  `ModuleNotFoundError: No module named 'gradio_client.serializing'` で WebUI 起動前に失敗
  (gradio 3.x 時代の API が新しい gradio_client に存在しないため)。GPU 以前に依存解決が
  経年劣化している。つまり本改修は Blackwell 対応に加え、**浮動依存の固定**も必要

## 2. ゴール

1. Python 3.10 + torch 2.7.1+cu128 で、前処理 → 特徴抽出(hubert-base-japanese) → 学習 → index 生成 → モデル保存、の全工程が RTX 5090 上でエラーなく完走する
2. 出力された .pth が従来と互換であること: `config_len == 19`、`embedder_name == "hubert-base-japanese"`(末尾768付き含む)が保存され、VCClient v1 でロード・変換できること
3. 既存機能を壊さない。**ゴールに関係しないリファクタリングは一切行わない**

## 3. 作業環境の前提

- Python: **3.10 固定**(3.11/3.12 への変更禁止)
- 最終ターゲット: Windows + RTX 5090 + NVIDIA ドライバ 570 系以降
- 利用者の既存インストール(現在動作中のフォルダ)には触れない。フォークは別ディレクトリで作業

## 4. 作業内容

### Step 1: 現状把握(コード変更なし)

1. **起動・インストール機構の解明(最重要)**: webui.bat からの起動フローを追い、依存パッケージが
   どこで・どのように決定されるかを特定せよ:
   - bat → launch.py 等のチェーン
   - torch のバージョン/インストールコマンドがハードコードされている箇所(環境変数による上書きの可否も)
   - requirements ファイルの場所と読み込みタイミング
   - venv の作成場所と再利用条件
2. 依存の現状記録: torch / torchaudio / fairseq / numpy / faiss / pyworld / librosa / numba 等の指定バージョン
3. `torch.load` の全使用箇所(ファイル名・行番号)を grep で列挙(学習側は pretrained の D/G モデル、
   hubert、再開用チェックポイント等、推論側より読み込み箇所が多い想定)
4. AMP の使用箇所(`torch.cuda.amp`, `GradScaler`, `autocast`)と、`torch.load` 以外の
   torch 2.x 非互換が疑われる API の使用箇所を列挙
5. fairseq の import 箇所と hubert ロード処理の特定
6. **既存の対応フォークの調査**: GitHub 上で ddPn08/rvc-webui のフォーク群や RVC 系プロジェクトに、
   新しい torch / Blackwell 対応を済ませたものがないか検索し、あれば差分を参考情報として記録
   (コードのコピーではなく、変更箇所の特定の参考とする)
7. 結果を WORKLOG.md に記録

### Step 2: 依存パッケージとインストール機構の更新

1. torch / torchaudio: **2.7.1+cu128 に固定**(`--extra-index-url https://download.pytorch.org/whl/cu128`)。
   Step 1-1 で特定したハードコード箇所(launch.py 等)と requirements の両方を整合させること
2. numpy: `>=既存の下限,<2`
3. fairseq: 0.12.2(PyPI 版、無改変)。フォーク版への差し替えは禁止(weights_only 対応は Step 3 で
   エントリポイントパッチとして行う。理由: サプライチェーンリスク回避。WORKLOG に方針を記載)
4. **浮動依存の固定(ベースライン障害の根本対応)**: requirements で固定されていない推移的依存が
   2026 年の最新版に解決されて壊れる(実例: gradio_client)。少なくとも gradio / gradio_client の
   組み合わせを、当時の整合するバージョンペアで明示的に固定すること。他にも import エラーを起こす
   浮動依存があれば同様に固定し、選定根拠(そのバージョンペアが整合する一次情報)を WORKLOG に記録
5. その他は torch 更新で壊れたもの以外バージョンを変えない。削除も変更とみなす(VCClient 側で
   requirements から行を削除されて実機障害になった前例あり)
6. バージョン選定は一次情報(PyPI、公式互換表)を確認し、出典を WORKLOG.md に記録。推測禁止

### Step 3: torch 2.6+ 互換パッチ(weights_only)

1. 自リポジトリ内の `torch.load`(モデル/チェックポイントのロード)全箇所に `weights_only=False` を
   機械的に追加(全数・一律。個別判断不要)
2. fairseq ライブラリ内部の `torch.load` 失敗には、起動エントリポイント1箇所に集約した
   モンキーパッチで対応(site-packages の直接書き換え禁止、フォーク版 fairseq への差し替え禁止)。
   呼び出し元が明示した weights_only 指定は上書きしない実装とし、
   「ローカルの信頼済みモデルのみを読む前提」をコメントに明記
3. 保存側(`torch.save`)は変更しない(形式互換維持のため)

### Step 4: 学習パイプラインの追従修正

- AMP / autocast / GradScaler は**エラーになる場合のみ**修正(警告止まりなら触らない)
- DataLoader、faiss の index 生成、TensorBoard 等で実行時エラーが出た場合のみ最小修正
- 各修正は「実際のエラーメッセージ」を WORKLOG.md に記録した上で行うこと(念のための修正は禁止)

### Step 5: エージェント側で可能な検証

1. クリーンな Python 3.10 venv で依存インストールが成功すること(Step 1 で解明した正規の
   インストールフローに従うこと)、`pip check` が通ること
2. `python -c "import torch; print(torch.__version__, torch.version.cuda)"` → 2.7.1 / 12.8
3. WebUI がimportエラーなしで起動すること(GPU 不在エラーは許容)
4. 変更ファイル一覧と理由を WORKLOG.md に記録

## 5. 人間が実機で行う検証(VERIFY.md を作成)

前提条件(Python 3.10 / VS Build Tools / ドライバ)の確認手順を冒頭に含め、以下を手順化:

1. 小規模データセット(音声数分)で 前処理 → 特徴抽出 → 学習 数エポック → index 生成 が完走すること
2. 学習中に `nvidia-smi` で GPU 使用を確認、TensorBoard か ログで loss が推移していること
3. 出力 .pth の検証(コマンド付きで記載):
   `config_len == 19`、`embedder_name == "hubert-base-japanese"` 系の値であること
4. 出力モデルを VCClient v1(改修済みフォーク)に配置して変換できること、音質が既存モデルと
   同水準であること
5. 改修前ベースライン(セクション1記載)との比較
6. トラブルシュート欄: fairseq ビルド失敗、cuDNN DLL、no kernel image(cu128 でない torch が
   入った場合)、の対処

## 6. 禁止事項・注意事項

- ブランチを切り替えない。Python 3.10 を変えない
- fairseq のフォーク版への差し替え禁止(Step 3 の方式で対応)
- 確定バージョン(torch 2.7.1+cu128)を独自判断で変更しない。変更が必要なら作業を止めて人間に確認
- 目的外のリファクタリング・フォーマット変更・import 並べ替え禁止
- バージョン番号の推測禁止(一次情報+出典を WORKLOG.md へ)
- 1論理変更=1コミット
- 行き詰まったら大規模書き換えにエスカレートせず、WORKLOG.md に状況をまとめて停止し人間の判断を仰ぐ

## 7. 成果物

1. 更新された依存定義(requirements / 起動スクリプトのインストールロジック)
2. weights_only パッチ等の最小限のソース変更
3. WORKLOG.md(調査結果、採用バージョンと出典、変更理由、未解決事項)
4. VERIFY.md(実機検証手順、前提条件、トラブルシュート)
