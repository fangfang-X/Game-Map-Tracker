"""灵动岛版跟点器主入口。

用法：
    python main_island.py            # SIFT 引擎
    python main_island.py --engine sift  # 兼容旧启动命令
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
from PySide6.QtWidgets import QApplication

import config
from ui_island.state.tracking import BaseTracker, TrackResult, TrackState
from ui_island.services.route_manager import RouteManager
from ui_island import IslandWindow
from ui_island.dialogs.minimap_selector import run_minimap_calibrator


class MissingMapTracker(BaseTracker):
    map_available = False

    def __init__(self, map_path: str | None, error: str = "") -> None:
        self.map_path = map_path or ""
        self.error = error
        self.logic_map_bgr = np.zeros((1024, 1024, 3), dtype=np.uint8)
        self.map_height, self.map_width = self.logic_map_bgr.shape[:2]

    def step(self, minimap_bgr: np.ndarray) -> TrackResult:
        return TrackResult(TrackState.SEARCHING, latency_ms=0.0)

    def set_anchor(self, x: int, y: int) -> None:
        return None


def build_tracker():
    config.ensure_maps_dir()
    if not config.selected_map_exists():
        return MissingMapTracker(config.LOGIC_MAP_PATH)
    from Plan_SIFT import SiftTracker
    try:
        return SiftTracker()
    except FileNotFoundError as exc:
        return MissingMapTracker(config.LOGIC_MAP_PATH, str(exc))


def _minimap_is_configured() -> bool:
    cfg = config.settings.get("MINIMAP") or {}
    try:
        top = int(cfg["top"])
        left = int(cfg["left"])
        width = int(cfg["width"])
        height = int(cfg["height"])
    except (KeyError, TypeError, ValueError):
        return False
    return width > 0 and height > 0 and top >= 0 and left >= 0
        
def main() -> int:
    os.chdir(config.BASE_DIR)
    config.ensure_maps_dir()
    config.ensure_annotations_dir()
    if getattr(sys, "frozen", False):
        config.cleanup_legacy_root_big_map()

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--engine",
        choices=["sift"],
        default="sift",
        help="定位引擎；当前发行版仅保留 SIFT，AI UI 占位待未来接入",
    )
    parser.add_argument(
        "--no-selector",
        action="store_true",
        help="跳过小地图校准（使用 config.json 中已有坐标）",
    )
    parser.add_argument(
        "--force-selector",
        action="store_true",
        help="强制弹出小地图校准器即便已有坐标",
    )
    args = parser.parse_args()

    # Qt 应用必须先于选择器创建 —— 选择器本身就是 Qt 窗口
    app = QApplication(sys.argv)

    if args.force_selector or (
        config.selected_map_exists() and not args.no_selector and not _minimap_is_configured()
    ):
        print(">>> 正在启动小地图选择器...")
        saved = run_minimap_calibrator()
        if not saved:
            print("⚠️ 未保存小地图坐标，程序退出。")
            return 0
        print("<<< 选择器关闭，坐标已更新！")

    tracker = build_tracker()
    route_mgr = RouteManager(config.app_path("routes"))

    window = IslandWindow(tracker, route_mgr)
    window.show()
    return app.exec()


if __name__ == "__main__":
    code = main()
    os._exit(code if code is not None else 0)
