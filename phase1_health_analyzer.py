#!/usr/bin/env python3
"""
ストリートファイター体力ゲージ測定システム

対戦格闘ゲームの動画から体力ゲージをOpenCVで解析し、
時系列の体力データをCSVとして出力する。
"""

import argparse
import csv
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

import cv2
import numpy as np


# =============================================================================
# 定数定義
# =============================================================================

# HSV閾値設定（OpenCVのHSVはH:0-180, S:0-255, V:0-255）

# 黄金（満タン時）- 発光部分も含める
GOLD_HSV_LOWER = np.array([15, 50, 150])
GOLD_HSV_UPPER = np.array([35, 255, 255])

# 体力（緑〜黄色グラデーション）- 発光部分も含める
HEALTH_HSV_LOWER = np.array([15, 40, 120])
HEALTH_HSV_UPPER = np.array([65, 255, 255])  # H上限を65に拡張（深い緑色もカバー）

# 未確定ダメージ（赤〜オレンジ）- 赤はHue=0付近と180付近の両方
DAMAGE_HSV_LOWER_1 = np.array([0, 80, 100])
DAMAGE_HSV_UPPER_1 = np.array([15, 255, 255])
DAMAGE_HSV_LOWER_2 = np.array([170, 80, 100])
DAMAGE_HSV_UPPER_2 = np.array([180, 255, 255])

# 確定ダメージ（黒〜暗グレー）- V<40でより暗い部分のみ検出
LOST_HSV_LOWER = np.array([0, 0, 0])
LOST_HSV_UPPER = np.array([180, 100, 40])

# デフォルトのバー座標（1920x1080基準）
# 上下6pxずつ削って枠の黒い部分を除外
DEFAULT_P1_BAR = (160, 95, 892, 113)  # x1, y1, x2, y2
DEFAULT_P2_BAR = (1035, 95, 1768, 113)

# ゲージ検出の閾値
MIN_HEALTH_PIXELS_RATIO = 0.05  # バー面積に対する最小ピクセル比率
COLUMN_THRESHOLD_RATIO = 0.30  # 列の高さに対する閾値比率

# 発光検出の閾値
FLASH_BRIGHTNESS_THRESHOLD = 200  # 発光時の平均輝度閾値
FLASH_DIFF_THRESHOLD = 50  # 前フレームとの輝度差閾値

# 異常値フィルタリングの閾値
MAX_HEALTH_DROP_PER_FRAME = 20.0  # 1フレームでの最大減少量（%）
MAX_HEALTH_INCREASE = 3.0  # 通常時の最大増加量（%）- ノイズ許容
ROUND_START_HEALTH_THRESHOLD = 95.0  # ラウンド開始判定の閾値（%）


# =============================================================================
# データクラス
# =============================================================================

class Phase(Enum):
    """試合フェーズ"""
    INTRO = "intro"
    ROUND_START = "round_start"
    BATTLE = "battle"
    KO = "ko"
    ROUND_END = "round_end"
    MATCH_END = "match_end"


@dataclass
class BarPositions:
    """バーの座標情報"""
    p1: tuple[int, int, int, int]  # x1, y1, x2, y2
    p2: tuple[int, int, int, int]


@dataclass
class BarState:
    """1つのバーの状態"""
    health: float  # 現在体力 0-100%
    damage: float  # 未確定ダメージ（赤い部分）0-100%
    confirmed_damage: float  # 確定ダメージ（黒い部分）0-100%
    is_full: bool  # 黄金（満タン）状態か


@dataclass
class HealthReading:
    """1フレームの測定結果"""
    timestamp_ms: int
    round_num: int
    phase: Phase
    p1_health: float
    p1_damage: float
    p2_health: float
    p2_damage: float


@dataclass
class AnalyzerConfig:
    """解析設定"""
    # HSV閾値
    gold_lower: np.ndarray = field(default_factory=lambda: GOLD_HSV_LOWER.copy())
    gold_upper: np.ndarray = field(default_factory=lambda: GOLD_HSV_UPPER.copy())
    health_lower: np.ndarray = field(default_factory=lambda: HEALTH_HSV_LOWER.copy())
    health_upper: np.ndarray = field(default_factory=lambda: HEALTH_HSV_UPPER.copy())
    damage_lower_1: np.ndarray = field(default_factory=lambda: DAMAGE_HSV_LOWER_1.copy())
    damage_upper_1: np.ndarray = field(default_factory=lambda: DAMAGE_HSV_UPPER_1.copy())
    damage_lower_2: np.ndarray = field(default_factory=lambda: DAMAGE_HSV_LOWER_2.copy())
    damage_upper_2: np.ndarray = field(default_factory=lambda: DAMAGE_HSV_UPPER_2.copy())
    lost_lower: np.ndarray = field(default_factory=lambda: LOST_HSV_LOWER.copy())
    lost_upper: np.ndarray = field(default_factory=lambda: LOST_HSV_UPPER.copy())

    # バー座標
    p1_bar: tuple[int, int, int, int] = DEFAULT_P1_BAR
    p2_bar: tuple[int, int, int, int] = DEFAULT_P2_BAR


# =============================================================================
# VideoProcessor
# =============================================================================

class VideoProcessor:
    """動画読み込みとフレーム取得"""

    def __init__(self, video_path: str):
        self.video_path = Path(video_path)
        if not self.video_path.exists():
            raise FileNotFoundError(f"動画ファイルが見つかりません: {video_path}")

        self.cap = cv2.VideoCapture(str(self.video_path))
        if not self.cap.isOpened():
            raise RuntimeError(f"動画を開けませんでした: {video_path}")

        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.duration_ms = int((self.frame_count / self.fps) * 1000) if self.fps > 0 else 0

    def get_frame(self, timestamp_ms: int) -> Optional[np.ndarray]:
        """指定時間のフレームを取得"""
        if timestamp_ms < 0 or timestamp_ms > self.duration_ms:
            return None

        frame_num = int((timestamp_ms / 1000.0) * self.fps)
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = self.cap.read()

        if not ret:
            return None
        return frame

    def get_frame_by_number(self, frame_num: int) -> Optional[np.ndarray]:
        """フレーム番号でフレームを取得"""
        if frame_num < 0 or frame_num >= self.frame_count:
            return None

        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ret, frame = self.cap.read()

        if not ret:
            return None
        return frame

    def iterate_frames(self, interval_ms: int):
        """指定間隔でフレームをイテレート"""
        timestamp_ms = 0
        while timestamp_ms <= self.duration_ms:
            frame = self.get_frame(timestamp_ms)
            if frame is not None:
                yield timestamp_ms, frame
            timestamp_ms += interval_ms

    def close(self):
        """リソース解放"""
        self.cap.release()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# =============================================================================
# GameStateDetector
# =============================================================================

class GameStateDetector:
    """試合状態の検出"""

    def __init__(self, config: AnalyzerConfig):
        self.config = config
        self.prev_brightness: Optional[float] = None

    def is_gauge_visible(self, frame: np.ndarray) -> bool:
        """ゲージ領域が有効かどうかを判定"""
        p1_bar = self._extract_bar(frame, self.config.p1_bar)
        p2_bar = self._extract_bar(frame, self.config.p2_bar)

        if p1_bar is None or p2_bar is None:
            return False

        # 各バーで有効な色が検出できるか
        p1_valid = self._has_valid_colors(p1_bar)
        p2_valid = self._has_valid_colors(p2_bar)

        return p1_valid and p2_valid

    def _extract_bar(self, frame: np.ndarray, coords: tuple) -> Optional[np.ndarray]:
        """バー領域を切り出し"""
        x1, y1, x2, y2 = coords

        # 座標を解像度に合わせてスケーリング
        h, w = frame.shape[:2]
        scale_x = w / 1920
        scale_y = h / 1080

        x1 = int(x1 * scale_x)
        x2 = int(x2 * scale_x)
        y1 = int(y1 * scale_y)
        y2 = int(y2 * scale_y)

        # 範囲チェック
        if x1 < 0 or y1 < 0 or x2 > w or y2 > h:
            return None

        return frame[y1:y2, x1:x2]

    def _has_valid_colors(self, bar_img: np.ndarray) -> bool:
        """バー画像に有効な色（黄金/緑黄/赤）が含まれるか"""
        hsv = cv2.cvtColor(bar_img, cv2.COLOR_BGR2HSV)
        total_pixels = bar_img.shape[0] * bar_img.shape[1]

        # 黄金マスク
        gold_mask = cv2.inRange(hsv, self.config.gold_lower, self.config.gold_upper)
        # 体力マスク
        health_mask = cv2.inRange(hsv, self.config.health_lower, self.config.health_upper)
        # ダメージマスク（赤）
        damage_mask_1 = cv2.inRange(hsv, self.config.damage_lower_1, self.config.damage_upper_1)
        damage_mask_2 = cv2.inRange(hsv, self.config.damage_lower_2, self.config.damage_upper_2)
        damage_mask = cv2.bitwise_or(damage_mask_1, damage_mask_2)

        # 有効な色のピクセル数
        valid_pixels = (
            cv2.countNonZero(gold_mask) +
            cv2.countNonZero(health_mask) +
            cv2.countNonZero(damage_mask)
        )

        return valid_pixels > total_pixels * MIN_HEALTH_PIXELS_RATIO

    def detect_screen_flash(self, frame: np.ndarray) -> bool:
        """画面の発光を検出"""
        # ゲージ周辺領域の平均輝度を計算
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        # 上部1/6の領域（ゲージがある付近）
        top_region = gray[:h // 6, :]
        current_brightness = np.mean(top_region)

        is_flash = False

        # 急激な輝度変化または高輝度
        if self.prev_brightness is not None:
            brightness_diff = abs(current_brightness - self.prev_brightness)
            if brightness_diff > FLASH_DIFF_THRESHOLD or current_brightness > FLASH_BRIGHTNESS_THRESHOLD:
                is_flash = True

        self.prev_brightness = current_brightness
        return is_flash

    def detect_phase(
        self,
        frame: np.ndarray,
        prev_phase: Phase,
        p1_health: float,
        p2_health: float,
        prev_p1_health: float,
        prev_p2_health: float
    ) -> Phase:
        """フェーズを判定"""
        # ゲージが見えない → intro
        if not self.is_gauge_visible(frame):
            return Phase.INTRO

        # 発光中 → round_start
        if self.detect_screen_flash(frame):
            return Phase.ROUND_START

        # 両者100%に戻った → 新ラウンド開始
        if prev_phase in (Phase.KO, Phase.ROUND_END):
            if p1_health >= 99.0 and p2_health >= 99.0:
                return Phase.ROUND_START

        # どちらかが0% → KO
        if p1_health <= 1.0 or p2_health <= 1.0:
            return Phase.KO

        # KO後 → round_end
        if prev_phase == Phase.KO:
            return Phase.ROUND_END

        # それ以外 → battle
        return Phase.BATTLE


# =============================================================================
# HealthBarAnalyzer
# =============================================================================

class HealthBarAnalyzer:
    """体力バーの解析"""

    def __init__(self, config: AnalyzerConfig):
        self.config = config

    def analyze_frame(self, frame: np.ndarray) -> Optional[tuple[BarState, BarState]]:
        """フレームから両プレイヤーの体力を解析"""
        p1_bar = self._extract_bar(frame, self.config.p1_bar)
        p2_bar = self._extract_bar(frame, self.config.p2_bar)

        if p1_bar is None or p2_bar is None:
            return None

        p1_state = self.analyze_bar(p1_bar, is_p1=True)
        p2_state = self.analyze_bar(p2_bar, is_p1=False)

        return p1_state, p2_state

    def _extract_bar(self, frame: np.ndarray, coords: tuple) -> Optional[np.ndarray]:
        """バー領域を切り出し"""
        x1, y1, x2, y2 = coords

        # 座標を解像度に合わせてスケーリング
        h, w = frame.shape[:2]
        scale_x = w / 1920
        scale_y = h / 1080

        x1 = int(x1 * scale_x)
        x2 = int(x2 * scale_x)
        y1 = int(y1 * scale_y)
        y2 = int(y2 * scale_y)

        # 範囲チェック
        if x1 < 0 or y1 < 0 or x2 > w or y2 > h:
            return None

        return frame[y1:y2, x1:x2]

    def analyze_bar(self, bar_img: np.ndarray, is_p1: bool) -> BarState:
        """
        バー画像を解析して体力状態を返す

        ダメージ検出法: 黒（確定ダメージ）と赤（未確定ダメージ）を検出し、
        体力 = 100% - ダメージ として計算する。
        この方法はキャラクターがゲージに重なっても影響を受けにくい。
        """
        hsv = cv2.cvtColor(bar_img, cv2.COLOR_BGR2HSV)
        height, width = bar_img.shape[:2]

        # 黒検出（確定ダメージ: 低彩度・低輝度）
        black_mask = cv2.inRange(hsv, self.config.lost_lower, self.config.lost_upper)

        # 赤検出（未確定ダメージ: H=0-10 または H=170-180）
        red_mask_1 = cv2.inRange(hsv, self.config.damage_lower_1, self.config.damage_upper_1)
        red_mask_2 = cv2.inRange(hsv, self.config.damage_lower_2, self.config.damage_upper_2)
        red_mask = cv2.bitwise_or(red_mask_1, red_mask_2)

        # 黄金検出（満タン判定用）
        gold_mask = cv2.inRange(hsv, self.config.gold_lower, self.config.gold_upper)

        # 列ごとに色の存在を判定
        threshold = int(height * COLUMN_THRESHOLD_RATIO)

        black_columns = []
        red_columns = []
        gold_columns = []

        for col in range(width):
            black_col = black_mask[:, col]
            red_col = red_mask[:, col]
            gold_col = gold_mask[:, col]

            black_count = cv2.countNonZero(black_col)
            red_count = cv2.countNonZero(red_col)
            gold_count = cv2.countNonZero(gold_col)

            black_columns.append(black_count >= threshold)
            red_columns.append(red_count >= threshold)
            gold_columns.append(gold_count >= threshold)

        # 列数の計算
        black_column_count = sum(black_columns)
        red_column_count = sum(red_columns)
        gold_column_count = sum(gold_columns)
        total_columns = width

        # 確定ダメージ（黒）の割合
        confirmed_damage_pct = (black_column_count / total_columns) * 100 if total_columns > 0 else 0

        # 未確定ダメージ（赤）の割合
        uncommitted_damage_pct = (red_column_count / total_columns) * 100 if total_columns > 0 else 0

        # 体力 = 100% - 確定ダメージ - 未確定ダメージ
        health_pct = 100.0 - confirmed_damage_pct - uncommitted_damage_pct

        is_full = gold_column_count > (total_columns * 0.8)  # 80%以上が黄金なら満タン

        # 値を0-100の範囲にクランプ
        health_pct = max(0.0, min(100.0, health_pct))
        confirmed_damage_pct = max(0.0, min(100.0, confirmed_damage_pct))
        uncommitted_damage_pct = max(0.0, min(100.0, uncommitted_damage_pct))

        return BarState(
            health=health_pct,
            damage=uncommitted_damage_pct,
            confirmed_damage=confirmed_damage_pct,
            is_full=is_full
        )

    def is_ko(self, p1_state: BarState, p2_state: BarState) -> Optional[str]:
        """KO判定"""
        if p1_state.health <= 1.0:
            return "P1"
        if p2_state.health <= 1.0:
            return "P2"
        return None

    def debug_frame(self, frame: np.ndarray, output_dir: str = "."):
        """デバッグ用の画像を出力"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # 元フレームにバー領域をハイライト
        debug_frame = frame.copy()
        h, w = frame.shape[:2]
        scale_x = w / 1920
        scale_y = h / 1080

        for name, coords in [("P1", self.config.p1_bar), ("P2", self.config.p2_bar)]:
            x1, y1, x2, y2 = coords
            x1 = int(x1 * scale_x)
            x2 = int(x2 * scale_x)
            y1 = int(y1 * scale_y)
            y2 = int(y2 * scale_y)
            color = (0, 255, 0) if name == "P1" else (255, 0, 0)
            cv2.rectangle(debug_frame, (x1, y1), (x2, y2), color, 2)

        cv2.imwrite(str(output_path / "debug_original.png"), debug_frame)

        # 各バーとマスクを出力
        for name, coords, is_p1 in [
            ("p1", self.config.p1_bar, True),
            ("p2", self.config.p2_bar, False)
        ]:
            bar_img = self._extract_bar(frame, coords)
            if bar_img is None:
                continue

            cv2.imwrite(str(output_path / f"debug_{name}_bar.png"), bar_img)

            hsv = cv2.cvtColor(bar_img, cv2.COLOR_BGR2HSV)

            # 各マスクを保存
            gold_mask = cv2.inRange(hsv, self.config.gold_lower, self.config.gold_upper)
            health_mask = cv2.inRange(hsv, self.config.health_lower, self.config.health_upper)
            damage_mask_1 = cv2.inRange(hsv, self.config.damage_lower_1, self.config.damage_upper_1)
            damage_mask_2 = cv2.inRange(hsv, self.config.damage_lower_2, self.config.damage_upper_2)
            damage_mask = cv2.bitwise_or(damage_mask_1, damage_mask_2)

            cv2.imwrite(str(output_path / f"debug_{name}_gold_mask.png"), gold_mask)
            cv2.imwrite(str(output_path / f"debug_{name}_health_mask.png"), health_mask)
            cv2.imwrite(str(output_path / f"debug_{name}_damage_mask.png"), damage_mask)


# =============================================================================
# HSV調整GUI
# =============================================================================

def tune_hsv(video_path: str, frame_num: int = 0):
    """HSV調整用のGUIを起動"""
    with VideoProcessor(video_path) as vp:
        frame = vp.get_frame_by_number(frame_num)
        if frame is None:
            print(f"フレーム {frame_num} を取得できませんでした")
            return

        config = AnalyzerConfig()
        analyzer = HealthBarAnalyzer(config)

        # P1バーを取得
        bar_img = analyzer._extract_bar(frame, config.p1_bar)
        if bar_img is None:
            print("バー領域を取得できませんでした")
            return

        hsv = cv2.cvtColor(bar_img, cv2.COLOR_BGR2HSV)

        window_name = "HSV Tuner"
        cv2.namedWindow(window_name)

        # トラックバー作成
        cv2.createTrackbar("H Low", window_name, 0, 180, lambda x: None)
        cv2.createTrackbar("H High", window_name, 180, 180, lambda x: None)
        cv2.createTrackbar("S Low", window_name, 0, 255, lambda x: None)
        cv2.createTrackbar("S High", window_name, 255, 255, lambda x: None)
        cv2.createTrackbar("V Low", window_name, 0, 255, lambda x: None)
        cv2.createTrackbar("V High", window_name, 255, 255, lambda x: None)

        print("キー操作:")
        print("  q: 終了")
        print("  1: 黄金プリセット")
        print("  2: 体力プリセット")
        print("  3: ダメージプリセット")
        print("  s: 現在の値を表示")

        while True:
            h_low = cv2.getTrackbarPos("H Low", window_name)
            h_high = cv2.getTrackbarPos("H High", window_name)
            s_low = cv2.getTrackbarPos("S Low", window_name)
            s_high = cv2.getTrackbarPos("S High", window_name)
            v_low = cv2.getTrackbarPos("V Low", window_name)
            v_high = cv2.getTrackbarPos("V High", window_name)

            lower = np.array([h_low, s_low, v_low])
            upper = np.array([h_high, s_high, v_high])

            mask = cv2.inRange(hsv, lower, upper)
            result = cv2.bitwise_and(bar_img, bar_img, mask=mask)

            # 表示用に拡大
            scale = 4
            bar_large = cv2.resize(bar_img, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
            mask_large = cv2.resize(mask, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)
            result_large = cv2.resize(result, None, fx=scale, fy=scale, interpolation=cv2.INTER_NEAREST)

            combined = np.vstack([bar_large, cv2.cvtColor(mask_large, cv2.COLOR_GRAY2BGR), result_large])
            cv2.imshow(window_name, combined)

            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('1'):  # 黄金
                cv2.setTrackbarPos("H Low", window_name, 15)
                cv2.setTrackbarPos("H High", window_name, 30)
                cv2.setTrackbarPos("S Low", window_name, 150)
                cv2.setTrackbarPos("S High", window_name, 255)
                cv2.setTrackbarPos("V Low", window_name, 200)
                cv2.setTrackbarPos("V High", window_name, 255)
            elif key == ord('2'):  # 体力
                cv2.setTrackbarPos("H Low", window_name, 25)
                cv2.setTrackbarPos("H High", window_name, 80)
                cv2.setTrackbarPos("S Low", window_name, 100)
                cv2.setTrackbarPos("S High", window_name, 255)
                cv2.setTrackbarPos("V Low", window_name, 150)
                cv2.setTrackbarPos("V High", window_name, 255)
            elif key == ord('3'):  # ダメージ
                cv2.setTrackbarPos("H Low", window_name, 0)
                cv2.setTrackbarPos("H High", window_name, 10)
                cv2.setTrackbarPos("S Low", window_name, 150)
                cv2.setTrackbarPos("S High", window_name, 255)
                cv2.setTrackbarPos("V Low", window_name, 150)
                cv2.setTrackbarPos("V High", window_name, 255)
            elif key == ord('s'):
                print(f"\n現在のHSV範囲:")
                print(f"  lower = np.array([{h_low}, {s_low}, {v_low}])")
                print(f"  upper = np.array([{h_high}, {s_high}, {v_high}])")

        cv2.destroyAllWindows()


# =============================================================================
# メイン処理
# =============================================================================

def process_video(
    video_path: str,
    output_path: str,
    interval_ms: int,
    config: AnalyzerConfig
) -> list[HealthReading]:
    """動画を処理してCSVを出力"""
    results: list[HealthReading] = []

    with VideoProcessor(video_path) as vp:
        print(f"動画情報:")
        print(f"  解像度: {vp.width}x{vp.height}")
        print(f"  FPS: {vp.fps:.2f}")
        print(f"  長さ: {vp.duration_ms / 1000:.2f}秒")
        print(f"  フレーム数: {vp.frame_count}")
        print()

        analyzer = HealthBarAnalyzer(config)
        detector = GameStateDetector(config)

        current_round = 0
        current_phase = Phase.INTRO
        prev_p1_health = 0.0
        prev_p2_health = 0.0
        # 確定ダメージの追跡（単調増加性の保証）
        prev_p1_confirmed = 0.0
        prev_p2_confirmed = 0.0
        # 暗転検出用
        after_blackout = True  # 最初はラウンド開始待ち状態

        frame_count = 0
        for timestamp_ms, frame in vp.iterate_frames(interval_ms):
            frame_count += 1

            # 体力解析
            bar_states = analyzer.analyze_frame(frame)
            if bar_states is None:
                # ゲージが見えない場合
                reading = HealthReading(
                    timestamp_ms=timestamp_ms,
                    round_num=current_round,
                    phase=Phase.INTRO,
                    p1_health=0.0,
                    p1_damage=0.0,
                    p2_health=0.0,
                    p2_damage=0.0
                )
                results.append(reading)
                continue

            p1_state, p2_state = bar_states

            # 暗転検出（画面全体の平均輝度が非常に低い）
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            avg_brightness = np.mean(gray)
            is_blackout = avg_brightness < 30  # 暗転判定

            if is_blackout:
                after_blackout = True

            # ラウンド開始判定（暗転後に両者が100%）
            both_full = (p1_state.health >= 99.5 and p2_state.health >= 99.5)
            if after_blackout and both_full:
                # ラウンド開始 → 確定ダメージ追跡をリセット
                prev_p1_confirmed = 0.0
                prev_p2_confirmed = 0.0
                after_blackout = False

            # 暗転後はまだラウンド開始していないので、確定ダメージは0とする
            if after_blackout:
                prev_p1_confirmed = 0.0
                prev_p2_confirmed = 0.0

            # 確定ダメージの妥当性チェック
            # ルール: 確定ダメージは赤（未確定ダメージ）を経由してのみ増加する
            # - 減少 → 誤検知なので前の値を維持
            # - 赤がないのに増加 → 誤検知なので前の値を維持

            p1_confirmed = p1_state.confirmed_damage
            p2_confirmed = p2_state.confirmed_damage

            # P1: 確定ダメージは減らない、赤を経由しない増加も無視
            if p1_confirmed < prev_p1_confirmed:
                p1_confirmed = prev_p1_confirmed
            elif p1_confirmed > prev_p1_confirmed and p1_state.damage == 0:
                # 赤がないのに増加 → 誤検知
                p1_confirmed = prev_p1_confirmed

            # P2: 同様
            if p2_confirmed < prev_p2_confirmed:
                p2_confirmed = prev_p2_confirmed
            elif p2_confirmed > prev_p2_confirmed and p2_state.damage == 0:
                p2_confirmed = prev_p2_confirmed

            # 追跡値を更新
            prev_p1_confirmed = p1_confirmed
            prev_p2_confirmed = p2_confirmed

            # 体力を計算
            p1_health = 100.0 - p1_confirmed - p1_state.damage
            p2_health = 100.0 - p2_confirmed - p2_state.damage

            # 体力単調減少ルール: 体力は増加しない（誤検出防止）
            # ただし、ラウンド開始時（暗転後）は除外
            if not after_blackout:
                if prev_p1_health > 0 and p1_health > prev_p1_health:
                    p1_health = prev_p1_health
                if prev_p2_health > 0 and p2_health > prev_p2_health:
                    p2_health = prev_p2_health

            # 値を0-100の範囲にクランプ
            p1_health = max(0.0, min(100.0, p1_health))
            p2_health = max(0.0, min(100.0, p2_health))

            # フィルタリング後の値でBarStateを更新
            p1_state = BarState(
                health=p1_health,
                damage=p1_state.damage,
                confirmed_damage=p1_confirmed,
                is_full=p1_state.is_full
            )
            p2_state = BarState(
                health=p2_health,
                damage=p2_state.damage,
                confirmed_damage=p2_confirmed,
                is_full=p2_state.is_full
            )

            # フェーズ判定
            new_phase = detector.detect_phase(
                frame, current_phase,
                p1_state.health, p2_state.health,
                prev_p1_health, prev_p2_health
            )

            # ラウンド遷移チェック
            if current_phase in (Phase.KO, Phase.ROUND_END) and new_phase == Phase.ROUND_START:
                current_round += 1

            current_phase = new_phase

            # KO判定
            ko_player = analyzer.is_ko(p1_state, p2_state)
            if ko_player:
                current_phase = Phase.KO

            # 記録
            reading = HealthReading(
                timestamp_ms=timestamp_ms,
                round_num=current_round,
                phase=current_phase,
                p1_health=p1_state.health,
                p1_damage=p1_state.damage,
                p2_health=p2_state.health,
                p2_damage=p2_state.damage
            )
            results.append(reading)

            prev_p1_health = p1_state.health
            prev_p2_health = p2_state.health

            # 進捗表示
            if frame_count % 100 == 0:
                progress = (timestamp_ms / vp.duration_ms) * 100
                print(f"\r処理中: {progress:.1f}% ({timestamp_ms / 1000:.1f}秒)", end="", flush=True)

        print(f"\r処理完了: 100%                    ")

    # CSV出力
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['timestamp_ms', 'round', 'phase', 'p1_health', 'p1_damage', 'p2_health', 'p2_damage'])

        for r in results:
            writer.writerow([
                r.timestamp_ms,
                r.round_num,
                r.phase.value,
                f"{r.p1_health:.1f}",
                f"{r.p1_damage:.1f}",
                f"{r.p2_health:.1f}",
                f"{r.p2_damage:.1f}"
            ])

    print(f"CSV出力: {output_path}")
    print(f"レコード数: {len(results)}")

    return results


def debug_frame_at_time(video_path: str, time_sec: float, config: AnalyzerConfig):
    """指定時間のフレームをデバッグ出力"""
    timestamp_ms = int(time_sec * 1000)

    with VideoProcessor(video_path) as vp:
        frame = vp.get_frame(timestamp_ms)
        if frame is None:
            print(f"時間 {time_sec}秒 のフレームを取得できませんでした")
            return

        analyzer = HealthBarAnalyzer(config)
        detector = GameStateDetector(config)

        # デバッグ画像出力
        analyzer.debug_frame(frame)

        # 解析結果
        bar_states = analyzer.analyze_frame(frame)
        gauge_visible = detector.is_gauge_visible(frame)
        screen_flash = detector.detect_screen_flash(frame)

        print(f"\nTime: {time_sec}s ({timestamp_ms}ms)")
        print(f"Gauge visible: {gauge_visible}")
        print(f"Screen flash: {screen_flash}")

        if bar_states:
            p1, p2 = bar_states
            print(f"P1: health={p1.health:.1f}%, damage={p1.damage:.1f}%, is_full={p1.is_full}")
            print(f"P2: health={p2.health:.1f}%, damage={p2.damage:.1f}%, is_full={p2.is_full}")
        else:
            print("バー解析失敗")

        print(f"\nデバッグ画像を出力しました:")
        print("  debug_original.png")
        print("  debug_p1_bar.png, debug_p2_bar.png")
        print("  debug_p1_gold_mask.png, debug_p1_health_mask.png, debug_p1_damage_mask.png")
        print("  debug_p2_gold_mask.png, debug_p2_health_mask.png, debug_p2_damage_mask.png")


def debug_frame_at_number(video_path: str, frame_num: int, config: AnalyzerConfig):
    """指定フレーム番号のフレームをデバッグ出力"""
    with VideoProcessor(video_path) as vp:
        time_sec = frame_num / vp.fps if vp.fps > 0 else 0
        debug_frame_at_time(video_path, time_sec, config)


def parse_bar_coords(s: str) -> tuple[int, int, int, int]:
    """バー座標文字列をパース"""
    parts = s.split(',')
    if len(parts) != 4:
        raise ValueError(f"座標は x1,y1,x2,y2 の形式で指定してください: {s}")
    return tuple(int(p.strip()) for p in parts)


def main():
    parser = argparse.ArgumentParser(
        description="ストリートファイター体力ゲージ測定システム",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  python health_analyzer.py match.mp4
  python health_analyzer.py match.mp4 -o result.csv -i 50
  python health_analyzer.py match.mp4 --debug-time 10.0
  python health_analyzer.py match.mp4 --tune-hsv 0
        """
    )

    parser.add_argument("video_path", help="入力動画ファイルのパス")
    parser.add_argument("-o", "--output", default="health_timeline.csv", help="出力CSVパス")
    parser.add_argument("-i", "--interval", type=int, default=100, help="サンプリング間隔（ミリ秒）")
    parser.add_argument("--debug-frame", type=int, metavar="N", help="指定フレーム番号をデバッグ出力")
    parser.add_argument("--debug-time", type=float, metavar="T", help="指定時間（秒）をデバッグ出力")
    parser.add_argument("--tune-hsv", type=int, metavar="N", nargs='?', const=0, help="HSV調整GUIを起動")
    parser.add_argument("--p1-bar", type=str, help="P1バー座標 x1,y1,x2,y2")
    parser.add_argument("--p2-bar", type=str, help="P2バー座標 x1,y1,x2,y2")

    args = parser.parse_args()

    # 設定
    config = AnalyzerConfig()

    if args.p1_bar:
        config.p1_bar = parse_bar_coords(args.p1_bar)
    if args.p2_bar:
        config.p2_bar = parse_bar_coords(args.p2_bar)

    # モード分岐
    if args.tune_hsv is not None:
        tune_hsv(args.video_path, args.tune_hsv)
    elif args.debug_time is not None:
        debug_frame_at_time(args.video_path, args.debug_time, config)
    elif args.debug_frame is not None:
        debug_frame_at_number(args.video_path, args.debug_frame, config)
    else:
        process_video(args.video_path, args.output, args.interval, config)


if __name__ == "__main__":
    main()
