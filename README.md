<div align="center">
<img width="1200" height="475" alt="GHBanner" src="https://github.com/user-attachments/assets/0aa67016-6eaf-458a-adb2-6e31a0763ed6" />
</div>

# SF6 AI Commentary Generator

ストリートファイター6の試合動画からAI実況コメントを自動生成するツールです。

---

## ワークフロー概要

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AI実況コメント生成パイプライン                          │
└─────────────────────────────────────────────────────────────────────────────┘

Phase 1: 体力ゲージ解析
─────────────────────────────────────────────────────────────────────────────
  入力: 試合動画 (mp4)
  処理: python phase1_health_analyzer.py video.mp4
  出力: phase1_output.csv
        └── 毎フレームの両プレイヤーの体力値を記録


Phase 2: イベント抽出
─────────────────────────────────────────────────────────────────────────────
  入力: phase1_output.csv (← Phase 1の出力)
  処理: python phase2_extract_events.py
  出力: phase2_output.csv
        └── ダメージイベント、ラウンド開始/終了のみを抽出


Phase 3: シーン記述 (VLM)
─────────────────────────────────────────────────────────────────────────────
  入力: 試合動画 + phase2_output.csv (← Phase 2の出力)
  処理: Webアプリ (npm run dev) → Scene Descriptionモード
  出力: phase3_output.csv
        └── 各イベントで何が起きたか（技名、状況）を記述


Phase 4: 実況コメント生成
─────────────────────────────────────────────────────────────────────────────
  入力: phase3_output.csv (← Phase 3の出力)
  処理: python phase4_generate_commentary.py --p1 カリン --p2 春麗
  出力: phase4_output.csv, phase4_output.json
        └── P1目線の実況コメントと感情タグ


Phase 5: 動画再生
─────────────────────────────────────────────────────────────────────────────
  入力: 試合動画 + phase4_output.json (← Phase 4の出力)
  処理: phase5_player.html をブラウザで開く
  出力: コメント付き動画再生
```

---

## 各フェーズの詳細

### Phase 1: 体力ゲージ解析

OpenCVで動画から体力ゲージを解析します。

```bash
python phase1_health_analyzer.py video.mp4 -o phase1_output.csv
```

**オプション:**
- `--all`: 全フレームを出力（デフォルトは変化があったフレームのみ）

**出力例 (phase1_output.csv):**
```csv
timestamp_ms,time,p1_health,p2_health,p1_damage,p2_damage,event
7500,7.5,100.0,100.0,0,0,round_start
11600,11.6,100.0,94.2,0,5.8,p2_damage
```

---

### Phase 2: イベント抽出

体力タイムラインから重要なイベントのみを抽出します。

```bash
python phase2_extract_events.py
# または入力/出力を明示的に指定:
python phase2_extract_events.py phase1_output.csv -o phase2_output.csv
```

**出力例 (phase2_output.csv):**
```csv
timestamp_ms,time,event_type,target,damage,p1_health,p2_health,description,comment
7500,7.5,round_start,,0,100.0,100.0,ラウンド開始,
11600,11.6,damage,P2,5.8,100.0,94.2,P2に5.8ダメージ,
```

---

### Phase 3: シーン記述 (VLM)

Webアプリを使ってVLMで各イベントを詳細に記述します。

```bash
npm run dev
```

1. ブラウザでアプリを開く
2. **Scene Description** モードを選択
3. 動画をアップロード
4. `phase2_output.csv` をアップロード
5. P1/P2のキャラクター名を入力
6. 「Process Video」を実行
7. 結果をCSVでダウンロード → `phase3_output.csv`

**出力例 (phase3_output.csv):**
```csv
timestamp_ms,time,description
7500,7.5,ラウンド開始。互いに様子見。
11600,11.6,カリンの立ち中Kが先端でヒット。
```

---

### Phase 4: 実況コメント生成

Gemini APIを使ってP1目線の実況コメントを生成します。

```bash
python phase4_generate_commentary.py --p1 カリン --p2 春麗
# または入力/出力を明示的に指定:
python phase4_generate_commentary.py phase3_output.csv -o phase4_output --p1 カリン --p2 春麗
```

**必要な環境変数:**
```
GEMINI_API_KEY=your_api_key
```
（`.env.local` に設定）

**出力例 (phase4_output.json):**
```json
[
  {"timestamp_ms": 7500, "time": "7.5", "description": "ラウンド開始。互いに様子見。", "comment": "さあ、いくぞ！", "emotion": "集中"},
  {"timestamp_ms": 11600, "time": "11.6", "description": "カリンの立ち中Kが先端でヒット。", "comment": "よし！", "emotion": "喜び"}
]
```

---

### Phase 5: 動画再生

生成したコメントを動画と同期再生します。

1. `phase5_player.html` をブラウザで開く
2. 「動画を選択」から試合動画を読み込む
3. 「phase4_output.json」を読み込む
4. 再生開始

**機能:**
- タイムスタンプに合わせてコメントをオーバーレイ表示
- 感情に応じた色分け（喜び=緑、焦り=赤、集中=青、勝利=金）
- タイムラインクリックでジャンプ
- キーボードショートカット（Space: 再生/停止, ←→: 5秒スキップ）

---

## ファイル一覧

| ファイル | 種類 | 説明 |
|---------|------|------|
| `phase1_health_analyzer.py` | スクリプト | Phase 1: 体力ゲージ解析 |
| `phase2_extract_events.py` | スクリプト | Phase 2: イベント抽出 |
| `phase4_generate_commentary.py` | スクリプト | Phase 4: 実況コメント生成 |
| `phase5_player.html` | HTML | Phase 5: 動画プレイヤー |
| `phase1_output.csv` | データ | Phase 1の出力 |
| `phase2_output.csv` | データ | Phase 2の出力 |
| `phase3_output.csv` | データ | Phase 3の出力 |
| `phase4_output.csv` | データ | Phase 4の出力 (CSV) |
| `phase4_output.json` | データ | Phase 4の出力 (JSON) |

---

## セットアップ

**Prerequisites:** Node.js, Python 3.8+

```bash
# Node依存関係
npm install

# Python依存関係
pip install opencv-python google-generativeai python-dotenv

# APIキー設定
echo "GEMINI_API_KEY=your_key_here" > .env.local

# Webアプリ起動
npm run dev
```
