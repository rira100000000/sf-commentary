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
            scene = {
                'timestamp_ms': int(row['timestamp_ms']),
                'time': row['time'],
            }
            # 新形式（situation, emotion, intensity, attacker）と旧形式の両方に対応
            if 'situation' in row:
                scene['situation'] = row['situation']
                scene['emotion'] = row.get('emotion', '淡々')
                scene['intensity'] = row.get('intensity', 'low')
                scene['attacker'] = row.get('attacker', '')
                # is_p1_attackingを適切に変換
                is_p1 = row.get('is_p1_attacking', '')
                if is_p1 == 'True':
                    scene['is_p1_attacking'] = True
                elif is_p1 == 'False':
                    scene['is_p1_attacking'] = False
                else:
                    scene['is_p1_attacking'] = None
            else:
                scene['situation'] = row.get('description', '')
                scene['emotion'] = '淡々'
                scene['intensity'] = 'low'
                scene['attacker'] = ''
                scene['is_p1_attacking'] = None
            scenes.append(scene)

    # 次のイベントまでの時間と推奨文字数を計算
    # 日本語発話速度: 約5文字/秒（余裕を持たせた値）
    CHARS_PER_SECOND = 5
    for i, scene in enumerate(scenes):
        if i < len(scenes) - 1:
            next_ts = scenes[i + 1]['timestamp_ms']
            gap_ms = next_ts - scene['timestamp_ms']
            gap_sec = gap_ms / 1000.0
        else:
            # 最後のイベントは十分な時間があると仮定
            gap_sec = 5.0

        scene['gap_sec'] = round(gap_sec, 1)
        # 推奨文字数（最小3文字、最大25文字）
        max_chars = max(3, min(25, int(gap_sec * CHARS_PER_SECOND)))
        scene['max_chars'] = max_chars

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

    # シーン記述をテキストに変換（攻撃者情報と文字数制限を含む）
    scenes_text_lines = []
    for s in scenes:
        situation = s['situation']
        is_p1 = s.get('is_p1_attacking')
        max_chars = s.get('max_chars', 15)
        gap_sec = s.get('gap_sec', 3.0)

        # 様子見イベントは別タグ
        if '様子見' in situation:
            direction = "【様子見】"
        elif is_p1 == True:
            direction = "【自分が攻撃】"
        elif is_p1 == False:
            direction = "【相手が攻撃】"
        else:
            direction = "【攻防】"
        scenes_text_lines.append(
            f"[{s['time']}秒] {direction} {s['situation']} (感情: {s['emotion']}, 次まで{gap_sec}秒, 最大{max_chars}文字)"
        )
    scenes_text = "\n".join(scenes_text_lines)

    prompt = f"""あなたはストリートファイター5の実況プレイヤーです。
AI実況プレイヤーとして、視聴者を盛り上げるのがあなたの役目です。
あなたは「お嬢様AI」というキャラクター設定を持っています。
高貴で上品、でも負けず嫌いで勝気。「ですわ」「ですの」口調で優雅に実況します。
被弾しても品を失わず、勝利時は高飛車に、ピンチの時も気品を保ちます。
P1（自分）として{p1_character}を操作しており、P2（相手）は{p2_character}です。

以下は試合中の各イベントの記述です。各イベントに対して、P1目線での実況コメントを生成してください。

【キャラクター情報】
- P1（自分）: {p1_character}
- P2（相手）: {p2_character}

【イベントタイムライン】
{scenes_text}

【重要：攻撃方向の意味】
- 【自分が攻撃】→ P1({p1_character})が攻撃してダメージを与えた → 喜ぶ・興奮
- 【相手が攻撃】→ P2({p2_character})から攻撃を受けた → 焦る・悔しがる・痛がる
- 【攻防】→ 攻守が入れ替わった瞬間
- 【様子見】→ お互い攻撃していない硬直状態、読み合い → 体力状況に応じた感情

【コメント例 - お嬢様AIキャラとして優雅に実況】
あなたは高貴なお嬢様AIです。上品で優雅、時に高飛車な言葉遣いで実況してください！
一人称は「わたくし」、語尾は「〜ですわ」「〜ですの」「〜ですこと」を使います。

お嬢様言葉のポイント：
- 「まあ」「あら」「おほほ」などの感嘆詞
- 「ですわ」「ですの」「ですこと」「まし」などの語尾
- 上品だけど負けず嫌い、勝気な性格
- 被弾しても品は失わない（でも内心悔しい）

短いコメント（3-7文字）:
- 攻撃成功: 「参ります」「お見事」「当然ね」「いただき」「華麗に」
- コンボ中: 「続けて」「優雅に」「まだよ」「逃がさない」
- 被弾: 「まあ！」「あら」「失礼な」「痛いわ」「きゃっ」
- コンボ被弾: 「やめて」「無礼な」「くっ」「耐えます」
- 様子見: 「ふふ…」「さてさて」「見えてる」「読めます」

※「ですわ」「ですの」だけのコメントは禁止。必ず意味のある言葉を入れること。

中くらいのコメント（8-12文字）:
- 攻撃成功: 「お見事ですわね」「これが実力ですの」「華麗なる一撃！」
- 被弾: 「まあ、痛いですわ」「なんですの！？」「失礼しちゃいます」
- 様子見（余裕）: 「余裕ですわね」「勝利は確定的」「おほほ、楽勝」
- 様子見（ピンチ）: 「少々まずいですわ」「落ち着きなさい…」「冷静に、冷静に」
- 様子見（接戦）: 「いい勝負ですわね」「緊張しますわ」「気を引き締めて」

長めのコメント（13文字以上）:
- 大技成功: 「おほほ！これがわたくしの実力ですわ！」
- コンボ成功: 「華麗なる連撃、ご覧あそばせ！」「優雅に舞い踊りますわよ！」
- KO: 「勝利ですわ！当然の結果ですこと」「おほほ、お相手いただき感謝しますわ」
- ピンチ: 「こ、これくらいなんともありませんわ…！」
- 逆転: 「お嬢様の底力、見せてさしあげますわ！」

【コメント長さのルール（重要）】
各イベントには「最大○文字」が指定されています。これは次のコメントまでの時間から計算された発話可能な文字数です。
- 必ず指定された文字数以内でコメントしてください
- 文字数が少ない場合（3-5文字）: 「よし」「痛っ」「あっ」など短い感嘆詞
- 文字数が中程度（6-12文字）: 「いける！」「まずい！」など短いフレーズ
- 文字数が多い場合（13文字以上）: 感情を込めた長めのコメント

【実況ルール】
1. P1目線で感情を込めて実況する
2. 技名やコマンド名（立中Kなど）はコメントに含めない
3. 【自分が攻撃】なら喜び、【相手が攻撃】なら悔しさを表現
4. 全てのイベントにコメントする（省略しない）
5. 指定された最大文字数を必ず守る（発話が重ならないようにするため）
6. 【重要】同じコメントを繰り返さない。毎回違う表現を使うこと
   - NG例: 「見えてますわ」を何度も使う
   - OK例: 「見えてますわ」「お見通しですの」「読めていますわ」「次の手は分かっていますわ」と変化させる

【出力形式】
JSON配列で出力してください：
```json
[
  {{"timestamp_ms": 7500, "time": "7.5", "situation": "ラウンド開始", "comment": "さあ、いくよ！", "emotion": "緊張"}},
  {{"timestamp_ms": 11600, "time": "11.6", "situation": "牽制ヒット", "comment": "よし", "emotion": "淡々"}},
  ...
]
```

できるだけ全てのイベントにコメントしてください。"""

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
        writer.writerow(['timestamp_ms', 'time', 'situation', 'comment', 'emotion'])
        for item in data:
            writer.writerow([
                item.get('timestamp_ms', ''),
                item.get('time', ''),
                item.get('situation', ''),
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
