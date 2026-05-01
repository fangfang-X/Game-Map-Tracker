"""SIFT + FLANN + RANSAC tracking engine."""
from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np

import config
from ui_island.services.image_io import imread_unicode
from ui_island.state.tracking import BaseTracker, TrackResult, TrackState

# Debug capture: when GMT_SIFT_DEBUG=1, every INERTIAL/LOST frame dumps the
# raw minimap and a small json trace under <project>/debug/sift_failures/.
# Throttled to <= 1 capture per second per state to avoid disk floods.
_DEBUG_DUMP_ENABLED = os.environ.get("GMT_SIFT_DEBUG", "").strip() in ("1", "true", "TRUE")
_DEBUG_DUMP_DIR = Path(__file__).resolve().parent.parent / "debug" / "sift_failures"
_DEBUG_THROTTLE_SECONDS = 1.0

# Base map descriptor cache: avoids re-running 8192² SIFT on every startup.
# Cache is keyed by map filename + file size + mtime — any change to the
# base map automatically invalidates the cache. The CACHE_VERSION below
# should be bumped whenever the cached structure (kp fields, dtype, CLAHE
# pipeline) changes so old caches are ignored.
_CACHE_VERSION = 2  # bumped: descriptors now stored as RootSIFT (Hellinger) — old v1 caches must be rejected
_CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache" / "sift"


_EDGE_GUARD_PX = 24
_EDGE_CONFIRM_DISTANCE_PX = 45.0
_EDGE_CONFIRM_HITS = 2
_MIN_INLIER_RATIO = 0.45
_EDGE_MIN_INLIER_COUNT = 10
_EDGE_MIN_INLIER_RATIO = 0.60
_HIGH_CONF_INLIER_COUNT = 14
_HIGH_CONF_INLIER_RATIO = 0.65
_LARGE_JUMP_RADIUS_FACTOR = 1.8

_STRICT_MATCH_RATIO_STEPS = (0.78, 0.86)
_MINIMAP_SCALE_TARGET = 220
_MINIMAP_MAX_SCALE = 2.0
_MINIMAP_CIRCLE_RATIO = 0.48
_MINIMAP_CENTER_MASK_RATIO = 0.13  # 盖住玩家箭头与视野扇形根部（约 30 px @ 220 短边）
_GLOBAL_RETRY_INTERVAL_FRAMES = 5

# 方案 3：空间先验过滤（仅在已有 last_x/y 且短时间内丢失时启用）
_SPATIAL_PRIOR_MAX_LOST_FRAMES = 5    # _lost_frames <= 此值时才信任 last 位置作先验
_SPATIAL_PRIOR_RADIUS_FACTOR = 1.5    # 允许的 dst 半径 = _local_radius * 此因子
_SPATIAL_PRIOR_MIN_KEPT = 6           # 过滤后保留的 match 数若少于此值则回退原 match

# 方案 Y：response 高通过滤（自适应砍掉低对比度噪声 keypoint）
# 草原/海面这种均匀纹理上 SIFT 会被迫挖出大量"刚通过 contrastThreshold"的低质量
# keypoint，这些 descriptor 在 base map 上分布散乱，污染 ratio test 结果。
# 阈值按 kp_count 分级：特征少时不动，特征多时砍掉低 response 那一半。
_RESPONSE_FILTER_LOW_KP = 60          # ≤ 此值不过滤
_RESPONSE_FILTER_MED_KP = 150         # ≤ 此值用保守阈值（p25），超过用激进阈值（p50）
_RESPONSE_FILTER_PCT_CONSERVATIVE = 0.25
_RESPONSE_FILTER_PCT_AGGRESSIVE = 0.50

# 运动预测：跟丢时按速度推进位置（对玩家持续移动场景救草原大色块）
_MOTION_EMA_ALPHA = 0.6              # 速度 EMA 平滑系数（保留 60% 旧 + 40% 新）
_MOTION_RESET_FACTOR = 0.5           # 新观测速度与平滑速度差 > local_radius * 此因子 → 视为传送，清零
_MOTION_CONFIDENCE_INC = 0.15        # 每次成功 LOCKED 信心增加
_MOTION_CONFIDENCE_DEC = 0.20        # 跟丢/重锁时信心衰减
_INERTIAL_VEL_DECAY = 0.85           # 每丢 1 帧速度衰减系数（5 帧 ≈ 0.44，10 帧 ≈ 0.20）


def _root_sift(des: np.ndarray | None) -> np.ndarray | None:
    """Apply the Hellinger kernel transform to SIFT descriptors (RootSIFT).

    L1-normalize each descriptor row then take the elementwise sqrt. This
    makes Euclidean distance behave like Hellinger distance on the original
    histograms, which is empirically more discriminative for texture matching
    (Arandjelović & Zisserman, CVPR 2012). Same shape & dtype as input.
    """
    if des is None or des.size == 0:
        return des
    des = des.astype(np.float32, copy=False)
    # eps prevents 0/0 on rare all-zero descriptors
    norms = np.linalg.norm(des, ord=1, axis=1, keepdims=True) + 1e-7
    return np.sqrt(des / norms).astype(np.float32, copy=False)


def _cache_signature(map_path: str) -> dict | None:
    """Identifying tuple for the base map file. None when path is unreadable."""
    try:
        st = os.stat(map_path)
    except OSError:
        return None
    return {
        "version": _CACHE_VERSION,
        "path": os.path.abspath(map_path),
        "size": int(st.st_size),
        "mtime_ns": int(st.st_mtime_ns),
        "clahe": float(config.SIFT_CLAHE_LIMIT),
    }


def _cache_path_for(map_path: str) -> Path:
    base = Path(map_path).name
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in base)
    return _CACHE_DIR / f"{safe}.v{_CACHE_VERSION}.npz"


def _cache_signature_matches(sig: dict, npz) -> bool:
    stored_path = str(npz["sig_path"])
    stored_size = int(npz["sig_size"])
    stored_mtime = int(npz["sig_mtime_ns"])
    stored_version = int(npz["sig_version"])
    stored_clahe = float(npz["sig_clahe"])
    return (
        stored_version == sig["version"]
        and stored_path == sig["path"]
        and stored_size == sig["size"]
        and stored_mtime == sig["mtime_ns"]
        and abs(stored_clahe - sig["clahe"]) <= 1e-9
    )


def has_valid_descriptor_cache(map_path: str | None = None) -> bool:
    """Return True when the base-map descriptor cache exists and matches."""
    map_path = map_path or config.selected_map_path_from_settings()
    if not map_path:
        return False
    sig = _cache_signature(map_path)
    if sig is None:
        return False
    cache_file = _cache_path_for(map_path)
    if not cache_file.is_file():
        return False
    try:
        with np.load(str(cache_file), allow_pickle=False) as npz:
            if not {"kp_fields", "des"}.issubset(npz.files):
                return False
            return _cache_signature_matches(sig, npz)
    except (OSError, ValueError, KeyError, EOFError):
        return False


def _load_descriptor_cache(
    map_path: str,
) -> tuple[list[cv2.KeyPoint], np.ndarray] | None:
    """Return (keypoints, descriptors) if a valid cache exists, else None."""
    sig = _cache_signature(map_path)
    if sig is None:
        return None
    cache_file = _cache_path_for(map_path)
    if not cache_file.is_file():
        return None
    try:
        with np.load(str(cache_file), allow_pickle=False) as npz:
            if not _cache_signature_matches(sig, npz):
                return None
            kp_fields = npz["kp_fields"]  # (N, 7) float32
            des = npz["des"]              # (N, 128) float32
    except (OSError, ValueError, KeyError, EOFError):
        return None

    keypoints: list[cv2.KeyPoint] = []
    for x, y, size, angle, response, octave, class_id in kp_fields:
        keypoints.append(
            cv2.KeyPoint(
                x=float(x),
                y=float(y),
                size=float(size),
                angle=float(angle),
                response=float(response),
                octave=int(octave),
                class_id=int(class_id),
            )
        )
    return keypoints, des


def _save_descriptor_cache(
    map_path: str,
    keypoints: list[cv2.KeyPoint],
    descriptors: np.ndarray,
) -> None:
    """Persist keypoints+descriptors. Failures are non-fatal (logged only)."""
    sig = _cache_signature(map_path)
    if sig is None:
        return
    cache_file = _cache_path_for(map_path)
    # np.savez auto-appends ".npz" to the path argument, so write to a sibling
    # tmp path then atomically rename. Track the actual produced filename so
    # any partial output gets cleaned up on failure.
    tmp_base = cache_file.with_suffix("")  # strips ".npz"
    tmp_target = tmp_base.with_name(tmp_base.name + ".tmp")
    produced = Path(str(tmp_target) + ".npz")
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        kp_fields = np.array(
            [
                (kp.pt[0], kp.pt[1], kp.size, kp.angle, kp.response, kp.octave, kp.class_id)
                for kp in keypoints
            ],
            dtype=np.float32,
        )
        np.savez(
            str(tmp_target),
            kp_fields=kp_fields,
            des=descriptors.astype(np.float32, copy=False),
            sig_path=np.array(sig["path"]),
            sig_size=np.array(sig["size"], dtype=np.int64),
            sig_mtime_ns=np.array(sig["mtime_ns"], dtype=np.int64),
            sig_version=np.array(sig["version"], dtype=np.int32),
            sig_clahe=np.array(sig["clahe"], dtype=np.float64),
        )
        os.replace(str(produced), str(cache_file))
    except OSError as exc:
        print(f"[SiftTracker] descriptor cache save failed: {exc}")
        # Clean up any partial tmp file so the cache dir doesn't accumulate junk.
        try:
            if produced.exists():
                produced.unlink()
        except OSError:
            pass


class SiftTracker(BaseTracker):
    def __init__(self) -> None:
        map_path = config.selected_map_path_from_settings()
        self.logic_map_bgr = imread_unicode(map_path)
        if self.logic_map_bgr is None:
            raise FileNotFoundError(f"Could not load logic map: {map_path}")

        self.map_height, self.map_width = self.logic_map_bgr.shape[:2]

        self.clahe = cv2.createCLAHE(clipLimit=config.SIFT_CLAHE_LIMIT, tileGridSize=(8, 8))
        self.sift = cv2.SIFT_create()

        self.kp_big, self.des_big = self._load_or_compute_base_descriptors()
        if self.des_big is None:
            self.des_big = np.empty((0, 128), dtype=np.float32)
        self._kp_big_pts = np.array([kp.pt for kp in self.kp_big], dtype=np.float32)

        FLANN_INDEX_KDTREE = 1
        self.flann = cv2.FlannBasedMatcher(
            dict(algorithm=FLANN_INDEX_KDTREE, trees=5),
            dict(checks=50),
        )
        # Pre-build the FLANN KDTREE once. Without this, every knnMatch call
        # rebuilds the index against des_big (~1.3s for 130k descriptors),
        # which dominated step() latency.
        if self.des_big.size > 0:
            t_train = time.time()
            self.flann.add([self.des_big])
            self.flann.train()
            print(
                f"[SiftTracker] FLANN KDTREE trained on {self.des_big.shape[0]} "
                f"descriptors in {(time.time() - t_train) * 1000:.0f}ms"
            )
        self.bf = cv2.BFMatcher(cv2.NORM_L2)

        self._global_train_idx = np.arange(len(self.kp_big), dtype=np.int64)
        self._local_radius = float(getattr(config, "SIFT_LOCAL_SEARCH_RADIUS", 400) or 400)
        self._last_x: int | None = None
        self._last_y: int | None = None
        self._lost_frames = 0
        self._max_lost = config.MAX_LOST_FRAMES
        self._pending_edge_xy: tuple[int, int] | None = None
        self._pending_edge_hits = 0
        # 运动预测：连续 LOCKED 时累积速度先验，INERTIAL 时按速度推进位置
        self._last_vx = 0.0                  # 像素/帧
        self._last_vy = 0.0
        self._velocity_confidence = 0.0      # 0..1，连续 LOCKED 多帧后涨上来
        # Debug capture state (only used when _DEBUG_DUMP_ENABLED is True)
        self._dbg_last_dump_t: dict[str, float] = {"inertial": 0.0, "lost": 0.0}
        self._dbg_best_inlier_count = 0
        self._dbg_best_inlier_ratio = 0.0
        self._dbg_best_good = 0

    def _load_or_compute_base_descriptors(
        self,
    ) -> tuple[list[cv2.KeyPoint], np.ndarray]:
        """Try cache first, fall back to recomputation. Always logs timing."""
        map_path = config.selected_map_path_from_settings()
        t_start = time.time()

        cached = _load_descriptor_cache(map_path)
        if cached is not None:
            keypoints, descriptors = cached
            elapsed = (time.time() - t_start) * 1000.0
            print(
                f"[SiftTracker] base descriptors loaded from cache: "
                f"{len(keypoints)} keypoints in {elapsed:.0f}ms"
            )
            return keypoints, descriptors

        logic_gray = cv2.cvtColor(self.logic_map_bgr, cv2.COLOR_BGR2GRAY)
        logic_gray = self.clahe.apply(logic_gray)
        keypoints, descriptors = self.sift.detectAndCompute(logic_gray, None)
        if descriptors is None:
            descriptors = np.empty((0, 128), dtype=np.float32)
            keypoints = list(keypoints) if keypoints is not None else []
        else:
            keypoints = list(keypoints)
        # Apply RootSIFT (Hellinger kernel) before caching — every subsequent
        # match expects descriptors in RootSIFT space. Cached file stores the
        # transformed values so we don't redo this on every launch.
        descriptors = _root_sift(descriptors)
        elapsed = (time.time() - t_start) * 1000.0
        print(
            f"[SiftTracker] base descriptors computed (RootSIFT): "
            f"{len(keypoints)} keypoints in {elapsed:.0f}ms (caching for next launch)"
        )
        _save_descriptor_cache(map_path, keypoints, descriptors)
        return keypoints, descriptors

    def set_anchor(self, x: int, y: int) -> None:
        self._last_x, self._last_y = int(x), int(y)
        self._lost_frames = 0
        self._pending_edge_xy = None
        self._pending_edge_hits = 0
        # 手动重新锚定 = 运动先验失效
        self._last_vx = 0.0
        self._last_vy = 0.0
        self._velocity_confidence = 0.0

    def _predicted_position(self) -> tuple[float, float] | None:
        """LOCKED + 连续无丢失时的预测位置（last + 衰减后的速度）。"""
        if self._last_x is None or self._last_y is None:
            return None
        decay = _INERTIAL_VEL_DECAY ** self._lost_frames
        scale = self._velocity_confidence * decay
        return (
            self._last_x + self._last_vx * scale,
            self._last_y + self._last_vy * scale,
        )

    def _update_motion_prior(self, new_x: int, new_y: int) -> None:
        """LOCKED 帧调用：用旧位置和新位置算速度并 EMA 平滑。

        仅在 _lost_frames == 0 时才视为可信连续帧；从 INERTIAL 恢复时不更新速度，
        避免一次大跳跃污染未来预测。
        """
        if self._last_x is None or self._last_y is None or self._lost_frames != 0:
            # 首次 LOCKED 或刚从 INERTIAL 恢复 — 信心衰减但不更新速度
            self._velocity_confidence = max(0.0, self._velocity_confidence - _MOTION_CONFIDENCE_DEC)
            return
        vx_obs = float(new_x - self._last_x)
        vy_obs = float(new_y - self._last_y)
        # 跳变检测：观测速度与平滑速度偏差过大 → 视为传送
        reset_thresh = self._local_radius * _MOTION_RESET_FACTOR
        if (
            abs(vx_obs - self._last_vx) > reset_thresh
            or abs(vy_obs - self._last_vy) > reset_thresh
        ):
            self._last_vx = 0.0
            self._last_vy = 0.0
            self._velocity_confidence = 0.0
            return
        a = _MOTION_EMA_ALPHA
        self._last_vx = a * self._last_vx + (1.0 - a) * vx_obs
        self._last_vy = a * self._last_vy + (1.0 - a) * vy_obs
        self._velocity_confidence = min(1.0, self._velocity_confidence + _MOTION_CONFIDENCE_INC)

    @staticmethod
    def _homography_quality(mask: np.ndarray | None, good_count: int) -> tuple[int, float]:
        if mask is None or good_count <= 0:
            return 0, 0.0
        inlier_count = int(np.count_nonzero(mask.ravel()))
        return inlier_count, inlier_count / float(good_count)

    def _near_map_edge(self, x: int, y: int) -> bool:
        return (
            x < _EDGE_GUARD_PX
            or y < _EDGE_GUARD_PX
            or x >= self.map_width - _EDGE_GUARD_PX
            or y >= self.map_height - _EDGE_GUARD_PX
        )

    def _is_large_jump(self, x: int, y: int) -> bool:
        if self._last_x is None or self._last_y is None:
            return False
        dist = float(np.hypot(x - self._last_x, y - self._last_y))
        return dist > self._local_radius * _LARGE_JUMP_RADIUS_FACTOR

    @staticmethod
    def _is_high_confidence(inlier_count: int, inlier_ratio: float) -> bool:
        return inlier_count >= _HIGH_CONF_INLIER_COUNT and inlier_ratio >= _HIGH_CONF_INLIER_RATIO

    def _accept_edge_candidate(self, x: int, y: int) -> bool:
        if self._pending_edge_xy is None:
            self._pending_edge_xy = (x, y)
            self._pending_edge_hits = 1
            return False

        dist = float(np.hypot(x - self._pending_edge_xy[0], y - self._pending_edge_xy[1]))
        if dist <= _EDGE_CONFIRM_DISTANCE_PX:
            self._pending_edge_xy = (x, y)
            self._pending_edge_hits += 1
        else:
            self._pending_edge_xy = (x, y)
            self._pending_edge_hits = 1
        return self._pending_edge_hits >= _EDGE_CONFIRM_HITS

    def _reset_edge_candidate(self) -> None:
        self._pending_edge_xy = None
        self._pending_edge_hits = 0

    @staticmethod
    def _ratio_steps() -> list[float]:
        try:
            user_ratio = float(config.SIFT_MATCH_RATIO)
        except (TypeError, ValueError):
            user_ratio = 0.9
        user_ratio = max(0.01, min(0.99, user_ratio))

        steps = [ratio for ratio in _STRICT_MATCH_RATIO_STEPS if ratio < user_ratio]
        steps.append(user_ratio)

        unique: list[float] = []
        for ratio in steps:
            if not unique or abs(unique[-1] - ratio) > 1e-6:
                unique.append(ratio)
        return unique

    @staticmethod
    def _good_matches(matches: tuple | list, ratio: float) -> list:
        return [
            m for pair in matches if len(pair) == 2
            for m, n in [pair]
            if m.distance < ratio * n.distance
        ]

    @staticmethod
    def _minimap_feature_mask(shape: tuple[int, int]) -> np.ndarray:
        h, w = shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        if h <= 0 or w <= 0:
            return mask

        cx, cy = w // 2, h // 2
        radius = max(1, int(min(w, h) * _MINIMAP_CIRCLE_RATIO))
        cv2.circle(mask, (cx, cy), radius, 255, -1)

        half = max(8, int(min(w, h) * _MINIMAP_CENTER_MASK_RATIO))
        cv2.rectangle(
            mask,
            (max(0, cx - half), max(0, cy - half)),
            (min(w - 1, cx + half), min(h - 1, cy + half)),
            0,
            -1,
        )
        return mask

    def _preprocess_minimap(self, minimap_bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        gray = cv2.cvtColor(minimap_bgr, cv2.COLOR_BGR2GRAY)
        short_side = min(gray.shape[:2])
        if 0 < short_side < _MINIMAP_SCALE_TARGET:
            scale = min(_MINIMAP_MAX_SCALE, _MINIMAP_SCALE_TARGET / float(short_side))
            gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

        gray = self.clahe.apply(gray)
        return gray, self._minimap_feature_mask(gray.shape)

    @staticmethod
    def _filter_low_response(
        kp_mini: tuple | list | None,
        des_mini: np.ndarray | None,
    ) -> tuple[list, np.ndarray | None]:
        """方案 Y：按 SIFT response 自适应砍掉低对比度 keypoint。

        草原/海面纹理均匀，SIFT 会挖出大量勉强通过 contrastThreshold 的低质量
        keypoint，descriptor 在 base map 各处都有"似是而非"的匹配，污染 ratio
        test。按 kp_count 分级阈值：特征少时不动避免误伤，特征多时按百分位过滤。
        """
        if kp_mini is None or des_mini is None or len(kp_mini) <= _RESPONSE_FILTER_LOW_KP:
            return list(kp_mini) if kp_mini is not None else [], des_mini

        n = len(kp_mini)
        if n <= _RESPONSE_FILTER_MED_KP:
            pct = _RESPONSE_FILTER_PCT_CONSERVATIVE
        else:
            pct = _RESPONSE_FILTER_PCT_AGGRESSIVE

        responses = np.fromiter((kp.response for kp in kp_mini), dtype=np.float32, count=n)
        threshold = float(np.quantile(responses, pct))
        keep = responses >= threshold
        # 兜底：如果数值化精度问题导致 keep 太少，直接保留原样
        if int(keep.sum()) < _RESPONSE_FILTER_LOW_KP:
            return list(kp_mini), des_mini
        kept_kp = [kp for kp, k in zip(kp_mini, keep) if k]
        kept_des = des_mini[keep]
        return kept_kp, kept_des

    def _local_train_indices(self) -> np.ndarray | None:
        if (
            self._last_x is None
            or self._last_y is None
            or self._kp_big_pts.size <= 0
        ):
            return None

        dx = self._kp_big_pts[:, 0] - self._last_x
        dy = self._kp_big_pts[:, 1] - self._last_y
        mask = (dx * dx + dy * dy) <= (self._local_radius * self._local_radius)
        local_idx = np.nonzero(mask)[0]
        if local_idx.size < config.SIFT_MIN_MATCH_COUNT * 2:
            return None
        return local_idx

    def _should_run_global_match(self) -> bool:
        if self._last_x is None or self._last_y is None:
            return True
        return self._lost_frames % _GLOBAL_RETRY_INTERVAL_FRAMES == 0

    def _match_candidates(self, des_mini: np.ndarray) -> Iterator[tuple[list, np.ndarray]]:
        """Return local/global candidates from strict to user-allowed ratio."""
        if len(self.kp_big) <= 0 or self.des_big.size <= 0:
            return

        local_threshold = max(config.SIFT_MIN_MATCH_COUNT + 3, 8)
        global_threshold = max(config.SIFT_MIN_MATCH_COUNT, 6)
        local_idx = self._local_train_indices()

        local_matches = None
        if local_idx is not None:
            local_matches = self.bf.knnMatch(des_mini, self.des_big[local_idx], k=2)

        for ratio in self._ratio_steps():
            if local_matches is not None and local_idx is not None:
                good = self._good_matches(local_matches, ratio)
                if len(good) >= local_threshold:
                    yield good, local_idx

        if not self._should_run_global_match():
            return

        # Use pre-trained KDTREE: omit the train arg so FLANN reuses the
        # index built once in __init__ instead of rebuilding it every call.
        global_matches = self.flann.knnMatch(des_mini, k=2)
        for ratio in self._ratio_steps():
            good = self._good_matches(global_matches, ratio)
            if len(good) >= global_threshold:
                yield good, self._global_train_idx

    def _candidate_position(
        self,
        kp_mini: tuple | list,
        good: list,
        train_idx_map: np.ndarray,
        gray_shape: tuple[int, int],
    ) -> tuple[int, int, int, int, float, bool] | None:
        src = np.float32([kp_mini[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst = np.float32(
            [self.kp_big[train_idx_map[m.trainIdx]].pt for m in good]
        ).reshape(-1, 1, 2)

        # 方案 3：空间先验过滤 — 在自相似纹理（草原/海面）上，假匹配的 dst 散布在
        # base map 各处，会让 RANSAC 找不到一致的 homography。当上一帧成功 LOCKED
        # 时，玩家短时间内不会跑很远，因此 dst 必须落在 last_x/y 周边，否则一定
        # 是假匹配。直接把这些扔掉再交给 RANSAC，inlier 比例会显著回升。
        if (
            self._last_x is not None
            and self._last_y is not None
            and self._lost_frames <= _SPATIAL_PRIOR_MAX_LOST_FRAMES
        ):
            radius = self._local_radius * _SPATIAL_PRIOR_RADIUS_FACTOR
            # 用预测位置（last + v*conf*decay）作搜索圆心 — 让圆跟着玩家走
            pred = self._predicted_position()
            cx_search, cy_search = pred if pred is not None else (self._last_x, self._last_y)
            dst_xy = dst.reshape(-1, 2)
            dx = dst_xy[:, 0] - cx_search
            dy = dst_xy[:, 1] - cy_search
            keep = (dx * dx + dy * dy) <= (radius * radius)
            if int(keep.sum()) >= _SPATIAL_PRIOR_MIN_KEPT:
                src = src[keep]
                dst = dst[keep]
                good = [m for m, k in zip(good, keep) if k]

        M, mask = cv2.findHomography(src, dst, cv2.RANSAC, config.SIFT_RANSAC_THRESHOLD)
        if M is None:
            return None

        good_count = len(good)
        inlier_count, inlier_ratio = self._homography_quality(mask, good_count)
        if _DEBUG_DUMP_ENABLED and inlier_count > self._dbg_best_inlier_count:
            self._dbg_best_inlier_count = inlier_count
            self._dbg_best_inlier_ratio = inlier_ratio
        min_inliers = max(config.SIFT_MIN_MATCH_COUNT, 6)
        if inlier_count < min_inliers or inlier_ratio < _MIN_INLIER_RATIO:
            return None

        h, w = gray_shape
        center = cv2.perspectiveTransform(np.float32([[[w / 2, h / 2]]]), M)
        tx, ty = int(center[0][0][0]), int(center[0][0][1])
        if not (0 <= tx < self.map_width and 0 <= ty < self.map_height):
            return None

        near_edge = self._near_map_edge(tx, ty)
        high_conf = self._is_high_confidence(inlier_count, inlier_ratio)
        edge_quality_ok = (
            inlier_count >= _EDGE_MIN_INLIER_COUNT
            and inlier_ratio >= _EDGE_MIN_INLIER_RATIO
        )
        large_jump_ok = (not self._is_large_jump(tx, ty)) or high_conf
        if not large_jump_ok or (near_edge and not edge_quality_ok):
            return None

        return tx, ty, good_count, inlier_count, inlier_ratio, near_edge

    def step(self, minimap_bgr: np.ndarray) -> TrackResult:
        t0 = time.time()
        if _DEBUG_DUMP_ENABLED:
            self._dbg_best_inlier_count = 0
            self._dbg_best_inlier_ratio = 0.0
            self._dbg_best_good = 0
        gray, feature_mask = self._preprocess_minimap(minimap_bgr)

        kp_mini, des_mini = self.sift.detectAndCompute(gray, feature_mask)
        # RootSIFT transform — must mirror what was applied to des_big at cache time.
        des_mini = _root_sift(des_mini)
        # 方案 Y：自适应 response 过滤 — 砍掉低对比度的草纹/水纹噪声 keypoint
        kp_mini, des_mini = self._filter_low_response(kp_mini, des_mini)
        locked = False
        cx = cy = None
        good_count = 0
        accepted = None

        if des_mini is not None and len(kp_mini) >= 2:
            for good, train_idx_map in self._match_candidates(des_mini):
                good_count = max(good_count, len(good))
                if _DEBUG_DUMP_ENABLED:
                    self._dbg_best_good = max(self._dbg_best_good, len(good))
                candidate = self._candidate_position(
                    kp_mini,
                    good,
                    train_idx_map,
                    gray.shape,
                )
                if candidate is not None:
                    accepted = candidate
                    break

        if accepted is not None:
            tx, ty, accepted_good_count, _inlier_count, _inlier_ratio, near_edge = accepted
            edge_confirmed = (not near_edge) or self._accept_edge_candidate(tx, ty)
            if edge_confirmed:
                locked = True
                cx, cy = tx, ty
                good_count = accepted_good_count
                # 在更新 last_x/y 之前算速度（用旧 last 作起点）
                self._update_motion_prior(tx, ty)
                self._last_x, self._last_y = tx, ty
                self._lost_frames = 0
                self._reset_edge_candidate()

        latency = (time.time() - t0) * 1000.0

        if locked:
            return TrackResult(TrackState.LOCKED, cx, cy, good_count, latency)

        if self._last_x is not None and self._lost_frames < self._max_lost:
            self._lost_frames += 1
            if _DEBUG_DUMP_ENABLED:
                self._dump_failure(
                    "inertial", minimap_bgr, kp_mini, good_count, latency
                )
            # 按速度推进位置（_predicted_position 已含衰减 + 信心权重）
            pred = self._predicted_position()
            if pred is not None:
                pred_x = int(max(0, min(self.map_width - 1, pred[0])))
                pred_y = int(max(0, min(self.map_height - 1, pred[1])))
            else:
                pred_x, pred_y = self._last_x, self._last_y
            return TrackResult(
                TrackState.INERTIAL, pred_x, pred_y, good_count, latency
            )

        if _DEBUG_DUMP_ENABLED:
            self._dump_failure("lost", minimap_bgr, kp_mini, good_count, latency)
        self._last_x = None
        self._last_y = None
        self._last_vx = 0.0
        self._last_vy = 0.0
        self._velocity_confidence = 0.0
        self._reset_edge_candidate()
        return TrackResult(TrackState.LOST, latency_ms=latency)

    def _dump_failure(
        self,
        state: str,
        minimap_bgr: np.ndarray,
        kp_mini: tuple | list | None,
        good_count: int,
        latency_ms: float,
    ) -> None:
        """Write minimap + diagnostic json under debug/sift_failures/. Throttled."""
        now = time.time()
        last = self._dbg_last_dump_t.get(state, 0.0)
        if now - last < _DEBUG_THROTTLE_SECONDS:
            return
        self._dbg_last_dump_t[state] = now
        try:
            _DEBUG_DUMP_DIR.mkdir(parents=True, exist_ok=True)
            stamp = time.strftime("%Y%m%d_%H%M%S", time.localtime(now))
            ms = int((now - int(now)) * 1000)
            stem = f"{stamp}_{ms:03d}_{state}"
            png_path = _DEBUG_DUMP_DIR / f"{stem}.png"
            json_path = _DEBUG_DUMP_DIR / f"{stem}.json"
            ok, buf = cv2.imencode(".png", minimap_bgr)
            if ok:
                png_path.write_bytes(buf.tobytes())
            payload = {
                "state": state,
                "kp_count": 0 if kp_mini is None else len(kp_mini),
                "best_good": int(self._dbg_best_good),
                "best_inlier_count": int(self._dbg_best_inlier_count),
                "best_inlier_ratio": round(float(self._dbg_best_inlier_ratio), 3),
                "good_count_step": int(good_count),
                "last_x": self._last_x,
                "last_y": self._last_y,
                "lost_frames": self._lost_frames,
                "latency_ms": round(float(latency_ms), 1),
                "minimap_shape": list(minimap_bgr.shape),
            }
            json_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            print(f"[SiftTracker] debug dump failed: {exc}")
