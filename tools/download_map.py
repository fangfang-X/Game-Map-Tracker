from __future__ import annotations

import argparse
import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path
from typing import Iterable

import requests
from PIL import Image

TILE_SIZE = 256

# 旧版 wiki 瓦片源，保留给对比用。
WIKI_BASE_URL = "https://wiki-dev-patch-oss.oss-cn-hangzhou.aliyuncs.com/res/lkwg/map-3.0/7/tile-{x}_{y}.png"

# 17173 页面配置: https://map.17173.com/rocom/maps/shijie
# 前端的 mapMaxzoom 是 13，所以 z=13 是当前 17173 源能拿到的最高清瓦片。
ROCOM_17173_GAME_NAME = "rocom"
ROCOM_17173_MAP_ID = 4010
ROCOM_17173_VERSION = "v3_7f2d9c"
ROCOM_17173_MAX_ZOOM = 13
ROCOM_17173_BOUNDS = (-1.4, 0.0, 0.0, 1.4)  # west, south, east, north
ROCOM_17173_TILE_URL = (
    "https://ue.17173cdn.com/a/terra/tiles/"
    f"{ROCOM_17173_GAME_NAME}/{ROCOM_17173_MAP_ID}_{ROCOM_17173_VERSION}"
    "/{z}/{y}_{x}.png?v1"
)

HEADERS_17173 = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://map.17173.com/rocom/maps/shijie",
    "Origin": "https://map.17173.com",
}


def _lon_to_tile_x(longitude: float, zoom: int) -> int:
    return int(math.floor((longitude + 180.0) / 360.0 * (2**zoom)))


def _lat_to_tile_y(latitude: float, zoom: int) -> int:
    latitude_rad = math.radians(latitude)
    mercator = math.log(math.tan(latitude_rad) + 1.0 / math.cos(latitude_rad))
    return int(math.floor((1.0 - mercator / math.pi) / 2.0 * (2**zoom)))


def _tile_range_from_bounds(
    bounds: tuple[float, float, float, float],
    zoom: int,
) -> tuple[int, int, int, int]:
    west, south, east, north = bounds
    epsilon = 1e-10
    x_min = _lon_to_tile_x(west, zoom)
    x_max = _lon_to_tile_x(east - epsilon, zoom)
    y_min = _lat_to_tile_y(north, zoom)
    y_max = _lat_to_tile_y(south + epsilon, zoom)
    return x_min, x_max, y_min, y_max


def _fetch_tile(
    url: str,
    headers: dict[str, str],
    timeout: int = 20,
    retries: int = 3,
) -> bytes | None:
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
            content_type = response.headers.get("content-type") or ""
            if response.status_code == 200 and content_type.startswith("image/"):
                return response.content
            return None
        except requests.RequestException:
            if attempt == retries - 1:
                return None
            time.sleep(0.5 * (attempt + 1))
    return None


def stitch_tiles(
    *,
    tile_url: str,
    zoom: int,
    x_min: int,
    x_max: int,
    y_min: int,
    y_max: int,
    save_path: str | Path,
    headers: dict[str, str] | None = None,
    max_workers: int = 16,
) -> Path:
    """Download tiles and stitch them into one PNG."""
    headers = headers or HEADERS_17173
    save_path = Path(save_path)
    width = (x_max - x_min + 1) * TILE_SIZE
    height = (y_max - y_min + 1) * TILE_SIZE
    total_tiles = (x_max - x_min + 1) * (y_max - y_min + 1)

    print(f"准备创建 {width} x {height} 画布，共 {total_tiles} 张瓦片...")
    result_image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    coords = [(x, y) for y in range(y_min, y_max + 1) for x in range(x_min, x_max + 1)]
    failures: list[tuple[int, int]] = []

    def download(coord: tuple[int, int]) -> tuple[int, int, bytes | None]:
        x, y = coord
        url = tile_url.format(z=zoom, x=x, y=y)
        return x, y, _fetch_tile(url, headers)

    completed = 0
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(download, coord) for coord in coords]
        for future in as_completed(futures):
            x, y, data = future.result()
            completed += 1
            if data is None:
                failures.append((x, y))
            else:
                tile = Image.open(BytesIO(data)).convert("RGBA")
                paste_x = (x - x_min) * TILE_SIZE
                paste_y = (y - y_min) * TILE_SIZE
                result_image.paste(tile, (paste_x, paste_y))

            if completed % 50 == 0 or completed == total_tiles:
                print(f"进度 {completed}/{total_tiles}")

    save_path.parent.mkdir(parents=True, exist_ok=True)
    result_image.save(save_path)
    print(f"已保存: {save_path.resolve()}")
    if failures:
        print(f"有 {len(failures)} 张瓦片下载失败，前 10 个: {failures[:10]}")
    return save_path


def download_17173_map(
    *,
    zoom: int = ROCOM_17173_MAX_ZOOM,
    save_path: str | Path | None = None,
    max_workers: int = 16,
) -> Path:
    """Download the 17173 RoCom map at the given zoom level."""
    x_min, x_max, y_min, y_max = _tile_range_from_bounds(ROCOM_17173_BOUNDS, zoom)
    if save_path is None:
        save_path = Path(__file__).with_name(f"map_17173_z{zoom}.png")
    return stitch_tiles(
        tile_url=ROCOM_17173_TILE_URL,
        zoom=zoom,
        x_min=x_min,
        x_max=x_max,
        y_min=y_min,
        y_max=y_max,
        save_path=save_path,
        headers=HEADERS_17173,
        max_workers=max_workers,
    )


def download_17173_highres_map(
    save_path: str | Path | None = None,
    *,
    max_workers: int = 16,
) -> Path:
    """Download the highest-resolution 17173 map currently available."""
    if save_path is None:
        save_path = Path(__file__).with_name("map_17173_z13_highres.png")
    return download_17173_map(
        zoom=ROCOM_17173_MAX_ZOOM,
        save_path=save_path,
        max_workers=max_workers,
    )


def download_and_stitch() -> Path:
    """Legacy wiki downloader kept for comparison with the old source."""
    x_min, x_max = -12, 11
    y_min, y_max = -11, 11
    return stitch_tiles(
        tile_url=WIKI_BASE_URL,
        zoom=0,
        x_min=x_min,
        x_max=x_max,
        y_min=y_min,
        y_max=y_max,
        save_path=Path(__file__).with_name("test_map_wiki.png"),
        headers=HEADERS_17173,
        max_workers=8,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="下载并拼接地图瓦片")
    parser.add_argument(
        "--source",
        choices=("17173", "wiki"),
        default="17173",
        help="地图来源，默认下载 17173",
    )
    parser.add_argument(
        "--zoom",
        type=int,
        default=ROCOM_17173_MAX_ZOOM,
        help="17173 瓦片缩放等级，最高为 13",
    )
    parser.add_argument("--out", default=None, help="输出 PNG 路径")
    parser.add_argument("--workers", type=int, default=16, help="并发下载线程数")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    if args.source == "wiki":
        download_and_stitch()
        return 0

    if args.zoom > ROCOM_17173_MAX_ZOOM:
        raise ValueError(f"17173 当前最高 zoom 是 {ROCOM_17173_MAX_ZOOM}")

    if args.zoom == ROCOM_17173_MAX_ZOOM:
        download_17173_highres_map(args.out, max_workers=args.workers)
    else:
        download_17173_map(zoom=args.zoom, save_path=args.out, max_workers=args.workers)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
