#!/usr/bin/env python3
"""
scene_descriptions.csv を読み込み、Gemini APIを使って実況コメントを生成する

出力:
- commentary_timeline.csv: タイムスタンプ付きの実況コメント
- commentary_timeline.json: 動画プレイヤー用のJSON形式
"""

import csv
import json
import argparse
import os
from typing import Optional

try:
    import google.generativeai as genai
except ImportError:
    print("google-generativeai パッケージが必要です")
    print("pip install google-generativeai")
    exit(1)

try:
    from dotenv import load_dotenv
    # .env.local を読み込む
    load_dotenv('.env.local')
    load_dotenv()  # .env もフォールバックとして
except ImportError:
    pass  # dotenvがなくても環境変数から読めればOK


def load_scene_descriptions(input_path: str) -> list[dict]:
    """CSVからシーン記述を読み込む"""
    scenes = []
    with open(input_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            scenes.append({
                'timestamp_ms': int(row['timestamp_ms']),
                'time': row['time'],
                'description': row['description']
            })
    return scenes


def generate_commentary(
    scenes: list[dict],
    p1_character: str,
    p2_character: str,
    api_key: Optional[str] = None
) -> list[dict]:
    """Gemini APIを使って実況コメントを生成"""

    # APIキー設定
    if api_key:
        genai.configure(api_key=api_key)
    elif os.environ.get('GEMINI_API_KEY'):
        genai.configure(api_key=os.environ['GEMINI_API_KEY'])
    else:
        raise ValueError("GEMINI_API_KEY環境変数またはapi_keyを指定してください")

    # シーン記述をテキストに変換
    scenes_text = "\n".join([
        f"[{s['time']}秒] {s['description']}"
        for s in scenes
    ])

    prompt = f"""あなたはストリートファイター5の実況プレイヤーです。
AI実況プレイヤーとして、視聴者を盛り上げるのがあなたの役目です。
あなたは女性AI実況プレイヤーというキャラクター設定を持っています。
AIならではの人間らしからぬ視点、コメントをする、かわいらしいという特徴があります。
P1（自分）として{p1_character}を操作しており、P2（相手）は{p2_character}です。

以下は試合中の各イベントの記述です。各イベントに対して、P1目線での実況コメントを生成してください。

【キャラクター情報】
- P1（自分）: {p1_character}
- P2（相手）: {p2_character}

【イベント記述】
{scenes_text}

【実況ルール】
1. P1目線で感情を込めて実況する
2. ダメージを与えた時は喜び（「よし！」「いける！」「決まった！」など）
3. ダメージを受けた時は焦りや痛み（「痛い！」「やばい！」「まずい！」など）
4. 技名でないコマンド名はコメントに含めない(立中kなどはコメント禁止)
5. コメントは基本的に10文字以内。
6. コメント間の時間を考慮し、無理に長いコメントはしない。
7. コメント間の時間が短すぎてしゃべり切れない場合など、すべてのイベントについてコメントする必要はない。
8. 逆にイベントのない時間が発生していたら、牽制している、考えているようなコメントをしてください。
9. 大技が発動したり、バトルの流れが大きく変わった時はテンション高く、長めのコメントをする
10. 試合の流れに合わせてテンションを変える

【出力形式】
各イベントに対して、以下のJSON形式で出力してください：
```json
[
  {{"timestamp_ms": 7500, "time": "7.5", "description": "ラウンド開始...", "comment": "さあ、いくぞ！", "emotion": "集中"}},
  ...
]
```

全てのイベントに対してコメントを生成してください。"""

    model = genai.GenerativeModel('gemini-2.5-flash')
    response = model.generate_content(prompt)

    # レスポンスからJSONを抽出
    response_text = response.text

    # JSON部分を抽出
    import re
    json_match = re.search(r'\[[\s\S]*\]', response_text)
    if json_match:
        try:
            result = json.loads(json_match.group())
            return result
        except json.JSONDecodeError as e:
            print(f"JSON解析エラー: {e}")
            print(f"レスポンス: {response_text}")
            return []
    else:
        print(f"JSONが見つかりません: {response_text}")
        return []


def save_csv(data: list[dict], output_path: str):
    """CSVとして保存"""
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['timestamp_ms', 'time', 'description', 'comment', 'emotion'])
        for item in data:
            writer.writerow([
                item.get('timestamp_ms', ''),
                item.get('time', ''),
                item.get('description', ''),
                item.get('comment', ''),
                item.get('emotion', '')
            ])
    print(f"CSV保存: {output_path}")


def save_json(data: list[dict], output_path: str):
    """JSONとして保存（動画プレイヤー用）"""
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"JSON保存: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description="シーン記述から実況コメントを生成"
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="phase3_output.csv",
        help="入力CSV（デフォルト: phase3_output.csv）"
    )
    parser.add_argument(
        "-o", "--output",
        default="phase4_output",
        help="出力ファイル名（拡張子なし、デフォルト: phase4_output）"
    )
    parser.add_argument(
        "--p1", "--p1-character",
        default="カリン",
        help="P1のキャラクター名（デフォルト: カリン）"
    )
    parser.add_argument(
        "--p2", "--p2-character",
        default="春麗",
        help="P2のキャラクター名（デフォルト: 春麗）"
    )
    parser.add_argument(
        "--api-key",
        help="Gemini APIキー（未指定時は環境変数GEMINI_API_KEYを使用）"
    )

    args = parser.parse_args()

    # シーン記述を読み込み
    print(f"読み込み: {args.input}")
    scenes = load_scene_descriptions(args.input)
    print(f"シーン数: {len(scenes)}")

    # 実況コメント生成
    print(f"\nGemini APIで実況コメントを生成中...")
    print(f"P1: {args.p1} vs P2: {args.p2}")

    commentary = generate_commentary(
        scenes,
        args.p1,
        args.p2,
        args.api_key
    )

    if not commentary:
        print("コメント生成に失敗しました")
        return

    print(f"生成完了: {len(commentary)}件")

    # 保存
    save_csv(commentary, f"{args.output}.csv")
    save_json(commentary, f"{args.output}.json")

    # プレビュー
    print("\n--- コメントプレビュー ---")
    for item in commentary[:10]:
        print(f"[{item.get('time', '?')}秒] {item.get('comment', '')} ({item.get('emotion', '')})")
    if len(commentary) > 10:
        print(f"... 他{len(commentary) - 10}件")


if __name__ == "__main__":
    main()
