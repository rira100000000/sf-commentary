# SF5 AI Commentary Generator

ストリートファイター5の試合動画からAI実況コメントを自動生成するツールです。

## セットアップ

```bash
# Python依存関係
pip install -r requirements.txt

# APIキー設定
echo "GEMINI_API_KEY=your_key_here" > .env.local
```

## パイプライン

```
試合動画 (.mp4)
    ↓
Phase 1: 体力ゲージ解析 (OpenCV)
    ↓
Phase 2: イベント抽出 (ルールベース)
    ↓
Phase 3: シーン記述 (VLM: Gemini)
    ↓
Phase 4: コメント生成 (LLM: Gemini)
    ↓
Phase 5: 動画再生 (HTML)
```

## 使い方

### Phase 1: 体力ゲージ解析

```bash
python phase1_health_analyzer.py video.mp4 -o phase1_output.csv
```

### Phase 2: イベント抽出

```bash
python phase2_extract_events.py phase1_output.csv -o phase2_output.csv
```

### Phase 3: シーン記述 (VLM)

```bash
python phase3_describe_scenes.py -v video.mp4 -i phase2_output.csv -o phase3_output.csv --p1 カリン --p2 春麗
```

**処理内容:**
- 各イベントの前後5フレーム（-200ms〜+200ms）を抽出
- コンボ判定（3ヒット以上、1500ms以内）
- 様子見イベント挿入（3秒以上の空白時間）
- 1回のAPI呼び出しで全イベントを一括処理

### Phase 4: コメント生成 (LLM)

```bash
python phase4_generate_commentary.py phase3_output.csv -o phase4_output --p1 カリン --p2 春麗
```

**キャラクター設定:**
`phase4_generate_commentary.py`内のプロンプトを編集してキャラクター設定を変更できます（お嬢様、LLM専門用語、体育会系など）。

### Phase 5: 動画再生

1. `phase5_player.html` をブラウザで開く
2. 動画ファイルを選択
3. `phase4_output.json` を読み込む
4. 再生開始

## ファイル一覧

| ファイル | 説明 |
|---------|------|
| `phase1_health_analyzer.py` | 体力ゲージ解析 |
| `phase2_extract_events.py` | イベント抽出 |
| `phase3_describe_scenes.py` | シーン記述（VLM） |
| `phase4_generate_commentary.py` | コメント生成（LLM） |
| `phase5_player.html` | 動画プレイヤー |
| `requirements.txt` | 依存関係 |
