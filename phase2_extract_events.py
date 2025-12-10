#!/usr/bin/env python3
"""
health_timeline.csv からダメージイベントを抽出してタイムラインを生成する

出力形式:
- timestamp_ms: イベント発生時刻
- event_type: イベント種別 (p1_damage, p2_damage, round_start, ko)
- target: ダメージを受けた側 (p1, p2, both, -)
- damage: ダメージ量
- p1_health: P1の残り体力
- p2_health: P2の残り体力
- description: イベントの説明（VLMが埋める用）
- comment: 実況コメント（後で埋める用）
"""

import csv
import argparse
from dataclasses import dataclass
from typing import Optional


@dataclass
class Event:
    timestamp_ms: int
    event_type: str
    target: str
    damage: float
    p1_health: float
    p2_health: float
    description: str = ""
    comment: str = ""


def extract_events(
    input_path: str,
    output_path: str,
    min_damage: float = 2.0,
    merge_window_ms: int = 500
):
    """
    CSVからダメージイベントを抽出

    Args:
        input_path: 入力CSV（health_timeline.csv）
        output_path: 出力CSV（events_timeline.csv）
        min_damage: 記録する最小ダメージ量（デフォルト2%）
        merge_window_ms: この時間内の連続ダメージは1イベントにまとめる
    """
    events: list[Event] = []

    with open(input_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        print("データがありません")
        return

    prev_p1_health = None
    prev_p2_health = None
    prev_round = None

    # 連続ダメージをまとめるための一時変数
    pending_p1_damage = 0.0
    pending_p2_damage = 0.0
    pending_start_ms = 0
    pending_p1_health = 0.0
    pending_p2_health = 0.0

    def flush_pending():
        """保留中のダメージイベントを確定"""
        nonlocal pending_p1_damage, pending_p2_damage, pending_start_ms

        if pending_p1_damage >= min_damage or pending_p2_damage >= min_damage:
            # どちらにダメージが入ったか判定
            if pending_p1_damage >= min_damage and pending_p2_damage >= min_damage:
                target = "both"
                damage = max(pending_p1_damage, pending_p2_damage)
                event_type = "exchange"
            elif pending_p1_damage >= min_damage:
                target = "p1"
                damage = pending_p1_damage
                event_type = "p1_damage"
            else:
                target = "p2"
                damage = pending_p2_damage
                event_type = "p2_damage"

            events.append(Event(
                timestamp_ms=pending_start_ms,
                event_type=event_type,
                target=target,
                damage=round(damage, 1),
                p1_health=pending_p1_health,
                p2_health=pending_p2_health
            ))

        pending_p1_damage = 0.0
        pending_p2_damage = 0.0

    for i, row in enumerate(rows):
        ts = int(row['timestamp_ms'])
        round_num = int(row['round'])
        p1_health = float(row['p1_health'])
        p2_health = float(row['p2_health'])

        # ラウンド開始検出
        if prev_round is not None and prev_p1_health is not None:
            # 両者が100%になった = ラウンド開始
            if p1_health >= 99.5 and p2_health >= 99.5 and (prev_p1_health < 90 or prev_p2_health < 90):
                flush_pending()
                events.append(Event(
                    timestamp_ms=ts,
                    event_type="round_start",
                    target="-",
                    damage=0.0,
                    p1_health=p1_health,
                    p2_health=p2_health
                ))
                prev_p1_health = p1_health
                prev_p2_health = p2_health
                prev_round = round_num
                continue

        # ダメージ検出
        if prev_p1_health is not None:
            p1_took = prev_p1_health - p1_health
            p2_took = prev_p2_health - p2_health

            # ダメージがあった場合
            if p1_took > 0 or p2_took > 0:
                # 前のイベントから時間が経っていたらflush
                if pending_start_ms > 0 and ts - pending_start_ms > merge_window_ms:
                    flush_pending()

                # 新しいイベント開始
                if pending_p1_damage == 0 and pending_p2_damage == 0:
                    pending_start_ms = ts

                pending_p1_damage += max(0, p1_took)
                pending_p2_damage += max(0, p2_took)
                pending_p1_health = p1_health
                pending_p2_health = p2_health

            # KO検出
            if p1_health <= 1.0 and prev_p1_health > 1.0:
                flush_pending()
                events.append(Event(
                    timestamp_ms=ts,
                    event_type="ko",
                    target="p1",
                    damage=0.0,
                    p1_health=p1_health,
                    p2_health=p2_health
                ))
            elif p2_health <= 1.0 and prev_p2_health > 1.0:
                flush_pending()
                events.append(Event(
                    timestamp_ms=ts,
                    event_type="ko",
                    target="p2",
                    damage=0.0,
                    p1_health=p1_health,
                    p2_health=p2_health
                ))

        prev_p1_health = p1_health
        prev_p2_health = p2_health
        prev_round = round_num

    # 最後の保留イベントをflush
    flush_pending()

    # 最初のラウンド開始前のイベントを除外
    first_round_start_idx = None
    for i, e in enumerate(events):
        if e.event_type == "round_start":
            first_round_start_idx = i
            break

    if first_round_start_idx is not None:
        events = events[first_round_start_idx:]

    # CSV出力
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            'timestamp_ms', 'time', 'event_type', 'target', 'damage',
            'p1_health', 'p2_health', 'description', 'comment'
        ])

        for e in events:
            # 時間を読みやすい形式に
            time_str = f"{e.timestamp_ms // 1000}.{(e.timestamp_ms % 1000) // 100}"

            writer.writerow([
                e.timestamp_ms,
                time_str,
                e.event_type,
                e.target,
                e.damage,
                e.p1_health,
                e.p2_health,
                e.description,
                e.comment
            ])

    print(f"イベント抽出完了: {output_path}")
    print(f"イベント数: {len(events)}")

    # サマリー表示
    print("\n--- イベントサマリー ---")
    for e in events:
        time_str = f"{e.timestamp_ms // 1000}.{(e.timestamp_ms % 1000) // 100}秒"
        if e.event_type == "round_start":
            print(f"[{time_str}] ラウンド開始")
        elif e.event_type == "ko":
            winner = "P1" if e.target == "p2" else "P2"
            print(f"[{time_str}] KO! {winner}の勝利")
        elif e.event_type == "exchange":
            print(f"[{time_str}] 相打ち P1:{e.p1_health:.0f}% / P2:{e.p2_health:.0f}%")
        elif e.target == "p1":
            print(f"[{time_str}] P1に{e.damage:.0f}%ダメージ → P1:{e.p1_health:.0f}%")
        elif e.target == "p2":
            print(f"[{time_str}] P2に{e.damage:.0f}%ダメージ → P2:{e.p2_health:.0f}%")


def main():
    parser = argparse.ArgumentParser(
        description="health_timeline.csvからダメージイベントを抽出"
    )
    parser.add_argument(
        "input",
        nargs="?",
        default="phase1_output.csv",
        help="入力CSV（デフォルト: phase1_output.csv）"
    )
    parser.add_argument(
        "-o", "--output",
        default="phase2_output.csv",
        help="出力CSV（デフォルト: phase2_output.csv）"
    )
    parser.add_argument(
        "-m", "--min-damage",
        type=float,
        default=2.0,
        help="記録する最小ダメージ量（デフォルト: 2.0%%）"
    )
    parser.add_argument(
        "-w", "--merge-window",
        type=int,
        default=500,
        help="連続ダメージをまとめる時間窓（ミリ秒、デフォルト: 500）"
    )

    args = parser.parse_args()

    extract_events(
        args.input,
        args.output,
        args.min_damage,
        args.merge_window
    )


if __name__ == "__main__":
    main()
