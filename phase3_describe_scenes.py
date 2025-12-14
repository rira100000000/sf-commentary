#!/usr/bin/env python3
"""
Phase 3: イベントごとにフレーム画像を抽出し、VLMで技を解析する

入力:
- phase2_output.csv: イベントタイムライン
- match.mp4: 動画ファイル

出力:
- phase3_output.csv: 技の説明が追加されたタイムライン
"""

import cv2
import csv
import base64
import argparse
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
import google.generativeai as genai
from dotenv import load_dotenv

# .env.localから環境変数を読み込む
load_dotenv('.env.local')

# Gemini API設定
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))


@dataclass
class Event:
    timestamp_ms: int
    time: str
    event_type: str
    target: str
    damage: float
    p1_health: float
    p2_health: float
    description: str = ""
    comment: str = ""


def extract_frames(video_path: str, timestamp_ms: int, offsets: list[int] = [-200, -100, 0, 100, 200]) -> list:
    """
    指定タイムスタンプ付近のフレームを抽出

    Args:
        video_path: 動画ファイルパス
        timestamp_ms: 中心となるタイムスタンプ（ミリ秒）
        offsets: 中心からのオフセット（ミリ秒）のリスト

    Returns:
        抽出されたフレーム画像のリスト（PIL Image形式）
    """
    cap = cv2.VideoCapture(video_path)
    frames = []

    for offset in offsets:
        target_ms = timestamp_ms + offset
        cap.set(cv2.CAP_PROP_POS_MSEC, target_ms)
        ret, frame = cap.read()
        if ret:
            # BGRからRGBに変換
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append(frame_rgb)

    cap.release()
    return frames


def frames_to_base64(frames: list) -> list[str]:
    """フレーム画像をbase64エンコードされたJPEGに変換"""
    encoded = []
    for frame in frames:
        # RGBからBGRに戻してエンコード
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        _, buffer = cv2.imencode('.jpg', frame_bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
        encoded.append(base64.b64encode(buffer).decode('utf-8'))
    return encoded


def analyze_event_with_vlm(
    frames: list,
    event: Event,
    p1_char: str,
    p2_char: str,
    model_name: str = "gemini-2.0-flash"
) -> str:
    """
    VLMを使ってイベントの技を解析

    Args:
        frames: フレーム画像のリスト
        event: イベント情報
        p1_char: P1のキャラクター名
        p2_char: P2のキャラクター名
        model_name: 使用するモデル名

    Returns:
        技の説明文
    """
    model = genai.GenerativeModel(model_name)

    # フレームをbase64エンコード
    encoded_frames = frames_to_base64(frames)

    # CVデータに基づいて攻撃者と被弾者を確定
    if event.event_type == "p1_damage":
        attacker = p2_char
        defender = p1_char
        fact = f"【確定事実】{p2_char}の攻撃が{p1_char}にヒットし、{event.damage}%のダメージを与えた。"
    elif event.event_type == "p2_damage":
        attacker = p1_char
        defender = p2_char
        fact = f"【確定事実】{p1_char}の攻撃が{p2_char}にヒットし、{event.damage}%のダメージを与えた。"
    elif event.event_type == "exchange":
        attacker = "両者"
        defender = "両者"
        fact = f"【確定事実】両者が同時にダメージを受けた（相打ち）。合計ダメージ: {event.damage}%"
    elif event.event_type == "round_start":
        fact = "【確定事実】ラウンド開始の瞬間。"
    elif event.event_type == "ko":
        loser = p1_char if event.target == "p1" else p2_char
        winner = p2_char if event.target == "p1" else p1_char
        fact = f"【確定事実】{loser}がKOされ、{winner}の勝利。"
    else:
        fact = f"【確定事実】{event.event_type}イベント発生。"

    # プロンプト作成
    prompt = f"""あなたは格闘ゲーム「ストリートファイター5」の映像解析エキスパートです。
以下の4枚の連続フレーム画像を見て、**何の技が使われたか**を特定してください。

【キャラクター情報】
- P1（画面左側）: {p1_char}
- P2（画面右側）: {p2_char}

{fact}

この事実はCV（コンピュータビジョン）で体力バーを解析して得られた**絶対的に正しいデータ**です。
あなたのタスクは、画像を見て「何の技がヒットしたか」を特定することです。
攻撃者・被弾者を推測する必要はありません（上記で確定済み）。

【画像の説明】
- 1枚目: イベント発生100ms前
- 2枚目: イベント発生時
- 3枚目: イベント発生100ms後
- 4枚目: イベント発生200ms後

【技の特定ヒント】
- ダメージ量から技の種類を推測:
  - 小ダメージ(2-5%): 通常技単発（立ち弱K、しゃがみ中Pなど）
  - 中ダメージ(6-12%): 必殺技 or 短いコンボ
  - 大ダメージ(13%以上): 長いコンボ or スーパーアーツ(SA)
- 攻撃モーションの形（パンチ、キック、回転技など）
- ヒットエフェクトの色や形

【{p1_char}の主要技】
- 通常技: 立ち弱K、立ち中K、立ち強K、しゃがみ中P、しゃがみ中K
- 必殺技: 烈殲破、無尽脚、天狐
- SA: 神月流・覇道六式

【{p2_char}の主要技】
- 通常技: 立ち弱K、立ち中K、立ち強K、しゃがみ中K
- 必殺技: 百裂脚、スピニングバードキック、気功拳
- SA: 鳳翼扇

【出力形式】
日本語で20-40文字程度で簡潔に記述してください。
確定事実に基づき、技名を含めて説明してください。

出力例:
- "{p1_char}の立ち中Kがヒット。"
- "{p2_char}のEX百裂脚でコンボ継続。"
- "互いの牽制技が交錯し相打ち。"
- "ラウンド開始。両者様子見。"
"""

    # 画像パーツを作成
    image_parts = []
    for i, encoded in enumerate(encoded_frames):
        image_parts.append({
            "mime_type": "image/jpeg",
            "data": encoded
        })

    # コンテンツを構築
    contents = [prompt] + image_parts

    try:
        response = model.generate_content(contents)
        return response.text.strip()
    except Exception as e:
        print(f"  VLM解析エラー: {e}")
        return f"{event.event_type}イベント発生"


def detect_combo_sequences(events: list) -> dict[int, dict]:
    """
    イベント間隔から「コンボ」かどうかを判定

    Returns:
        dict: {event_index: {"is_combo": bool, "combo_position": "start"|"mid"|"end"|None, "combo_hits": int}}
    """
    COMBO_WINDOW_MS = 1500  # この間隔以内の連続ダメージはコンボ

    result = {}
    n = len(events)

    for i, event in enumerate(events):
        result[i] = {"is_combo": False, "combo_position": None, "combo_hits": 1}

    # 同じtargetへの連続ダメージを検出
    i = 0
    while i < n:
        event = events[i]
        if event.event_type not in ["p1_damage", "p2_damage"]:
            i += 1
            continue

        # 連続するダメージを探す
        combo_start = i
        combo_indices = [i]
        current_target = event.target

        j = i + 1
        while j < n:
            next_event = events[j]
            time_gap = next_event.timestamp_ms - events[j-1].timestamp_ms

            # 同じtargetへの連続ダメージで、間隔が短い場合
            if (next_event.event_type in ["p1_damage", "p2_damage"] and
                next_event.target == current_target and
                time_gap <= COMBO_WINDOW_MS):
                combo_indices.append(j)
                j += 1
            else:
                break

        # 3ヒット以上ならコンボ
        if len(combo_indices) >= 3:
            for k, idx in enumerate(combo_indices):
                if k == 0:
                    pos = "start"
                elif k == len(combo_indices) - 1:
                    pos = "end"
                else:
                    pos = "mid"
                result[idx] = {
                    "is_combo": True,
                    "combo_position": pos,
                    "combo_hits": len(combo_indices)
                }

        i = j if j > i + 1 else i + 1

    return result


def analyze_all_events_batch(
    all_frames: list[tuple[Event, list]],
    p1_char: str,
    p2_char: str,
    combo_info: dict[int, dict],
    model_name: str = "gemini-3-pro-preview"
) -> list[dict]:
    """
    全イベントを1回のAPI呼び出しで一括解析
    CVで判定済みの情報（コンボ等）を活用し、VLMは視覚的特徴のみ判断
    """
    model = genai.GenerativeModel(model_name)

    # イベント情報のテキストを構築（CV判定情報を含む）
    events_info = []
    attacker_info = []  # P1が攻撃したか、P2が攻撃したかの情報

    for i, (event, _) in enumerate(all_frames):
        combo = combo_info.get(i, {})
        is_combo = combo.get("is_combo", False)
        combo_pos = combo.get("combo_position")
        combo_hits = combo.get("combo_hits", 1)

        if event.event_type == "p1_damage":
            # P1がダメージを受けた = P2が攻撃した = 実況者にとって悪いこと
            attacker_info.append({"attacker": "p2", "is_p1_attacking": False})
            if is_combo:
                if combo_pos == "start":
                    cv_note = f"【P1被弾・コンボ開始】P2({p2_char})がP1({p1_char})にコンボ開始（{combo_hits}ヒット）"
                elif combo_pos == "end":
                    cv_note = f"【P1被弾・コンボ終了】P2のコンボ締め"
                else:
                    cv_note = f"【P1被弾・コンボ中】P2のコンボ継続"
            else:
                cv_note = f"【P1被弾・単発】P2({p2_char})がP1({p1_char})に単発ヒット（{event.damage}%）"
        elif event.event_type == "p2_damage":
            # P2がダメージを受けた = P1が攻撃した = 実況者にとって良いこと
            attacker_info.append({"attacker": "p1", "is_p1_attacking": True})
            if is_combo:
                if combo_pos == "start":
                    cv_note = f"【P1攻撃・コンボ開始】P1({p1_char})がP2({p2_char})にコンボ開始（{combo_hits}ヒット）"
                elif combo_pos == "end":
                    cv_note = f"【P1攻撃・コンボ終了】P1のコンボ締め"
                else:
                    cv_note = f"【P1攻撃・コンボ中】P1のコンボ継続"
            else:
                cv_note = f"【P1攻撃・単発】P1({p1_char})がP2({p2_char})に単発ヒット（{event.damage}%）"
        elif event.event_type == "exchange":
            # exchangeは短時間で両者がダメージを受けた状況（切り返しや反撃の可能性）
            attacker_info.append({"attacker": "both", "is_p1_attacking": None})
            cv_note = f"【攻防交代】短時間で両者ダメージ（反撃や切り返しの可能性）"
        elif event.event_type == "idle":
            # 様子見イベント：体力に応じた状況を設定
            attacker_info.append({"attacker": None, "is_p1_attacking": None})
            health_diff = event.p1_health - event.p2_health
            if event.p1_health > 70 and health_diff > 20:
                cv_note = f"【様子見・余裕】P1有利（P1:{event.p1_health:.0f}% P2:{event.p2_health:.0f}%）"
            elif event.p1_health < 30:
                cv_note = f"【様子見・危機】P1ピンチ（P1:{event.p1_health:.0f}% P2:{event.p2_health:.0f}%）"
            elif health_diff < -20:
                cv_note = f"【様子見・焦り】P1不利（P1:{event.p1_health:.0f}% P2:{event.p2_health:.0f}%）"
            elif abs(health_diff) < 10:
                cv_note = f"【様子見・接戦】拮抗（P1:{event.p1_health:.0f}% P2:{event.p2_health:.0f}%）"
            else:
                cv_note = f"【様子見・冷静】読み合い（P1:{event.p1_health:.0f}% P2:{event.p2_health:.0f}%）"
        elif event.event_type == "round_start":
            attacker_info.append({"attacker": None, "is_p1_attacking": None})
            cv_note = "【ラウンド開始】"
        elif event.event_type == "ko":
            loser = p1_char if event.target == "p1" else p2_char
            winner = p2_char if event.target == "p1" else p1_char
            is_p1_win = event.target == "p2"
            attacker_info.append({"attacker": "p1" if is_p1_win else "p2", "is_p1_attacking": is_p1_win})
            cv_note = f"【KO】{winner}の勝利"
        else:
            attacker_info.append({"attacker": None, "is_p1_attacking": None})
            cv_note = f"【{event.event_type}】"

        events_info.append(f"イベント{i+1} [{event.time}秒]: {cv_note}")

    # プロンプト作成
    prompt = f"""あなたは格闘ゲームの映像解析アシスタントです。

【キャラクター情報】
- P1（画面左側）: {p1_char} ← 実況者が操作している側
- P2（画面右側）: {p2_char} ← 対戦相手

【CV判定済みイベント一覧】
{chr(10).join(events_info)}

【画像の説明】
各イベントにつき4枚の連続フレーム画像が提供されます。

【あなたのタスク】
各イベントについて、画像から見える特徴を元に：
1. situation: 状況を簡潔に（視覚的特徴があれば追加）
2. emotion: P1目線での感情
3. intensity: 盛り上がり度（high/medium/low）

【重要：P1目線の感情ルール】
- P1({p1_char})がダメージを与えた → 喜び（興奮/歓喜）
- P1({p1_char})がダメージを受けた → 焦り（悔しさ/緊張）
- コンボを決めた → 興奮
- コンボを食らった → 悔しさ

【situationの書き方例】
- 「牽制ヒット」「差し込み」「飛び道具」「投げ」「対空成功」「コンボ開始」
- 画像から判断できない場合は「攻撃ヒット」

【出力形式】
JSON配列:
[
  {{"event_index": 1, "situation": "ラウンド開始", "emotion": "緊張", "intensity": "medium"}},
  {{"event_index": 2, "situation": "牽制ヒット", "emotion": "淡々", "intensity": "low"}},
  ...
]

必ず{len(all_frames)}個の要素を出力してください。
"""

    # 全フレーム画像を結合
    image_parts = []
    for event, frames in all_frames:
        encoded_frames = frames_to_base64(frames)
        for encoded in encoded_frames:
            image_parts.append({
                "mime_type": "image/jpeg",
                "data": encoded
            })

    # コンテンツを構築
    contents = [prompt] + image_parts

    try:
        response = model.generate_content(contents)
        response_text = response.text.strip()

        # JSONをパース
        import json
        import re

        # JSON配列を抽出
        json_match = re.search(r'\[[\s\S]*\]', response_text)
        if json_match:
            results = json.loads(json_match.group())
            parsed = [None] * len(all_frames)
            for item in results:
                idx = item.get("event_index", 0) - 1
                if 0 <= idx < len(parsed):
                    # attacker情報を追加
                    att = attacker_info[idx]
                    parsed[idx] = {
                        "situation": item.get("situation", ""),
                        "emotion": item.get("emotion", "淡々"),
                        "intensity": item.get("intensity", "low"),
                        "attacker": att["attacker"],
                        "is_p1_attacking": att["is_p1_attacking"]
                    }
            # 欠損を埋める
            for i, p in enumerate(parsed):
                if p is None:
                    att = attacker_info[i]
                    parsed[i] = {
                        "situation": "不明",
                        "emotion": "淡々",
                        "intensity": "low",
                        "attacker": att["attacker"],
                        "is_p1_attacking": att["is_p1_attacking"]
                    }
            return parsed
        else:
            print(f"JSONパース失敗: {response_text[:200]}", flush=True)
            return [{
                "situation": e.event_type,
                "emotion": "淡々",
                "intensity": "low",
                "attacker": attacker_info[i]["attacker"],
                "is_p1_attacking": attacker_info[i]["is_p1_attacking"]
            } for i, (e, _) in enumerate(all_frames)]

    except Exception as e:
        print(f"VLM解析エラー: {e}", flush=True)
        return [{
            "situation": e.event_type,
            "emotion": "淡々",
            "intensity": "low",
            "attacker": attacker_info[i]["attacker"],
            "is_p1_attacking": attacker_info[i]["is_p1_attacking"]
        } for i, (e, _) in enumerate(all_frames)]


def insert_idle_events(events: list, min_gap_ms: int = 3000) -> list:
    """
    イベント間の空白時間に「様子見」イベントを挿入

    Args:
        events: 元のイベントリスト
        min_gap_ms: この時間以上空いたら様子見イベントを挿入（デフォルト3秒）

    Returns:
        様子見イベントが挿入されたリスト
    """
    if len(events) < 2:
        return events

    new_events = []
    for i, event in enumerate(events):
        new_events.append(event)

        # 次のイベントとの間隔をチェック
        if i < len(events) - 1:
            next_event = events[i + 1]
            gap = next_event.timestamp_ms - event.timestamp_ms

            # 空白時間が長い場合、中間に様子見イベントを挿入
            if gap >= min_gap_ms:
                # 中間地点の時刻
                mid_time_ms = event.timestamp_ms + gap // 2
                mid_time = f"{mid_time_ms // 1000}.{(mid_time_ms % 1000) // 100}"

                # 体力状況を引き継ぐ
                idle_event = Event(
                    timestamp_ms=mid_time_ms,
                    time=mid_time,
                    event_type="idle",
                    target="-",
                    damage=0.0,
                    p1_health=event.p1_health,
                    p2_health=event.p2_health,
                    description="",
                    comment=""
                )
                new_events.append(idle_event)

    return new_events


def process_events(
    video_path: str,
    events_csv_path: str,
    output_path: str,
    p1_char: str = "カリン",
    p2_char: str = "春麗",
    model_name: str = "gemini-3-pro-preview"
):
    """
    全イベントを処理してシーン説明を生成（バッチ処理版）
    """
    # イベント読み込み
    events = []
    with open(events_csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            events.append(Event(
                timestamp_ms=int(row['timestamp_ms']),
                time=row['time'],
                event_type=row['event_type'],
                target=row['target'],
                damage=float(row['damage']),
                p1_health=float(row['p1_health']),
                p2_health=float(row['p2_health']),
                description=row.get('description', ''),
                comment=row.get('comment', '')
            ))

    # 空白時間に様子見イベントを挿入
    events = insert_idle_events(events, min_gap_ms=3000)

    print(f"イベント数: {len(events)}", flush=True)
    print(f"使用モデル: {model_name}", flush=True)
    print(f"P1: {p1_char}, P2: {p2_char}", flush=True)
    print("-" * 50, flush=True)

    # idleイベントとそれ以外を分離
    idle_events = [(i, e) for i, e in enumerate(events) if e.event_type == "idle"]
    action_events = [(i, e) for i, e in enumerate(events) if e.event_type != "idle"]

    # アクションイベントのフレームを抽出
    print("フレーム抽出中...", flush=True)
    all_frames = []
    for orig_idx, event in action_events:
        frames = extract_frames(video_path, event.timestamp_ms)
        all_frames.append((orig_idx, event, frames))
        print(f"  [{len(all_frames)}/{len(action_events)}] {event.time}秒", flush=True)

    print(f"フレーム抽出完了（合計{len(all_frames) * 4}枚）", flush=True)

    # CVデータからコンボ判定（アクションイベントのみ）
    print("コンボ判定中...", flush=True)
    action_events_only = [e for _, e in action_events]
    combo_info_action = detect_combo_sequences(action_events_only)

    # コンボ判定結果を表示
    for i, (_, event) in enumerate(action_events):
        c = combo_info_action[i]
        if c["is_combo"]:
            print(f"  [{event.time}秒] コンボ({c['combo_position']}, {c['combo_hits']}ヒット)", flush=True)

    print("VLM一括解析中...", flush=True)

    # アクションイベントをVLMで解析
    frames_for_vlm = [(e, f) for _, e, f in all_frames]
    action_results = analyze_all_events_batch(frames_for_vlm, p1_char, p2_char, combo_info_action, model_name)

    # idleイベントの結果を生成（VLM不要）
    idle_results = {}
    for orig_idx, event in idle_events:
        health_diff = event.p1_health - event.p2_health
        if event.p1_health > 70 and health_diff > 20:
            situation, emotion = "様子見（余裕）", "余裕"
        elif event.p1_health < 30:
            situation, emotion = "様子見（ピンチ）", "焦り"
        elif health_diff < -20:
            situation, emotion = "様子見（不利）", "緊張"
        elif abs(health_diff) < 10:
            situation, emotion = "様子見（接戦）", "集中"
        else:
            situation, emotion = "様子見（読み合い）", "冷静"

        idle_results[orig_idx] = {
            "situation": situation,
            "emotion": emotion,
            "intensity": "low",
            "attacker": None,
            "is_p1_attacking": None
        }

    # 結果をマージ（元のイベント順序に戻す）
    results = [None] * len(events)
    for i, (orig_idx, _, _) in enumerate(all_frames):
        results[orig_idx] = action_results[i]
    for orig_idx, result in idle_results.items():
        results[orig_idx] = result

    # 結果表示
    print("-" * 50, flush=True)
    for i, event in enumerate(events):
        r = results[i]
        p1_mark = "→" if r.get('is_p1_attacking') else "←" if r.get('is_p1_attacking') == False else "↔"
        print(f"[{event.time}秒] {p1_mark} {r['situation']} | {r['emotion']} | {r['intensity']}", flush=True)

    # CSV出力
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['timestamp_ms', 'time', 'situation', 'emotion', 'intensity', 'attacker', 'is_p1_attacking'])

        for i, event in enumerate(events):
            r = results[i]
            writer.writerow([
                event.timestamp_ms,
                event.time,
                r['situation'],
                r['emotion'],
                r['intensity'],
                r.get('attacker', ''),
                r.get('is_p1_attacking', '')
            ])

    print("-" * 50, flush=True)
    print(f"出力完了: {output_path}", flush=True)


def main():
    parser = argparse.ArgumentParser(
        description="Phase 3: フレーム画像を抽出してVLMで技を解析"
    )
    parser.add_argument(
        "-v", "--video",
        default="match.mp4",
        help="動画ファイル（デフォルト: match.mp4）"
    )
    parser.add_argument(
        "-i", "--input",
        default="phase2_output.csv",
        help="入力CSV（デフォルト: phase2_output.csv）"
    )
    parser.add_argument(
        "-o", "--output",
        default="phase3_output.csv",
        help="出力CSV（デフォルト: phase3_output.csv）"
    )
    parser.add_argument(
        "--p1",
        default="カリン",
        help="P1キャラクター名（デフォルト: カリン）"
    )
    parser.add_argument(
        "--p2",
        default="春麗",
        help="P2キャラクター名（デフォルト: 春麗）"
    )
    parser.add_argument(
        "-m", "--model",
        default="gemini-3-pro-preview",
        help="使用するGeminiモデル（デフォルト: gemini-3-pro-preview）"
    )

    args = parser.parse_args()

    process_events(
        args.video,
        args.input,
        args.output,
        args.p1,
        args.p2,
        args.model
    )


if __name__ == "__main__":
    main()
