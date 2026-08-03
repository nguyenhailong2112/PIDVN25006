from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np


DEFAULT_ROI_RATIOS = np.array(
    [
        [0.2, 0.30],
        [0.8, 0.30],
        [0.8, 1.00],
        [0.2, 1.00],
    ],
    dtype=np.float32,
)

DEFAULT_SUBSETS = (
    Path("hi") / "hiii",
    Path("hi") / "hiii"
)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def ratio_points_to_pixels(ratio_points: np.ndarray, width: int, height: int) -> np.ndarray:
    points = ratio_points.copy()
    points[:, 0] *= width
    points[:, 1] *= height
    points[:, 0] = np.clip(points[:, 0], 0, width - 1)
    points[:, 1] = np.clip(points[:, 1], 0, height - 1)
    return np.rint(points).astype(np.int32)


def crop_polygon(image: np.ndarray, points: np.ndarray) -> np.ndarray:
    x, y, w, h = cv2.boundingRect(points)
    cropped = image[y : y + h, x : x + w].copy()

    local_points = points - np.array([x, y], dtype=np.int32)
    mask = np.zeros(cropped.shape[:2], dtype=np.uint8)
    cv2.fillPoly(mask, [local_points], 255)

    return cv2.bitwise_and(cropped, cropped, mask=mask)


def crop_bbox(image: np.ndarray, points: np.ndarray) -> np.ndarray:
    x, y, w, h = cv2.boundingRect(points)
    return image[y : y + h, x : x + w].copy()


def crop_warp(image: np.ndarray, points: np.ndarray) -> np.ndarray:
    top_width = np.linalg.norm(points[1] - points[0])
    bottom_width = np.linalg.norm(points[2] - points[3])
    left_height = np.linalg.norm(points[3] - points[0])
    right_height = np.linalg.norm(points[2] - points[1])

    out_width = max(1, int(round(max(top_width, bottom_width))))
    out_height = max(1, int(round(max(left_height, right_height))))

    dst = np.array(
        [
            [0, 0],
            [out_width - 1, 0],
            [out_width - 1, out_height - 1],
            [0, out_height - 1],
        ],
        dtype=np.float32,
    )
    matrix = cv2.getPerspectiveTransform(points.astype(np.float32), dst)
    return cv2.warpPerspective(image, matrix, (out_width, out_height))


def iter_images(input_root: Path, subsets: tuple[Path, ...]) -> list[Path]:
    image_paths: list[Path] = []
    for subset in subsets:
        subset_dir = input_root / subset
        if not subset_dir.exists():
            print(f"[WARN] Missing subset: {subset_dir}")
            continue

        image_paths.extend(
            sorted(
                path
                for path in subset_dir.iterdir()
                if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
            )
        )
    return image_paths


def save_crop(
    image_path: Path,
    input_root: Path,
    output_root: Path,
    mode: str,
    overwrite: bool,
) -> bool:
    relative_path = image_path.relative_to(input_root)
    output_path = output_root / relative_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.exists() and not overwrite:
        return False

    image = cv2.imread(str(image_path), cv2.IMREAD_UNCHANGED)
    if image is None:
        print(f"[WARN] Cannot read image: {image_path}")
        return False

    height, width = image.shape[:2]
    points = ratio_points_to_pixels(DEFAULT_ROI_RATIOS, width, height)

    if mode == "polygon":
        cropped = crop_polygon(image, points)
    elif mode == "bbox":
        cropped = crop_bbox(image, points)
    elif mode == "warp":
        cropped = crop_warp(image, points)
    else:
        raise ValueError(f"Unsupported crop mode: {mode}")

    ok = cv2.imwrite(str(output_path), cropped)
    if not ok:
        print(f"[WARN] Cannot write output: {output_path}")
    return ok


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Crop raw images from dataTest/data1 and dataTest/data2 train/valid subsets. "
            "Dataset metadata and labels are ignored."
        )
    )
    parser.add_argument(
        "--input-root",
        type=Path,
        default=Path("dataTest"),
        help="Root folder containing data1 and data2. Default: dataTest",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("dataTest_raw_crop"),
        help="Output folder for cropped raw images. Default: dataTest_raw_crop",
    )
    parser.add_argument(
        "--mode",
        choices=("polygon", "bbox", "warp"),
        default="polygon",
        help=(
            "polygon: crop bounding area and mask outside the ROI; "
            "bbox: simple rectangle crop around the ROI; "
            "warp: perspective-transform the ROI into a rectangle. Default: polygon"
        ),
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite output images that already exist.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_root = args.input_root.resolve()
    output_root = args.output_root.resolve()

    image_paths = iter_images(input_root, DEFAULT_SUBSETS)
    if not image_paths:
        raise SystemExit(f"No input images found under {input_root}")

    written = 0
    skipped = 0
    for image_path in image_paths:
        if save_crop(image_path, input_root, output_root, args.mode, args.overwrite):
            written += 1
        else:
            skipped += 1

    print(f"Input root : {input_root}")
    print(f"Output root: {output_root}")
    print(f"Crop mode  : {args.mode}")
    print(f"Written    : {written}")
    print(f"Skipped    : {skipped}")


if __name__ == "__main__":
    main()
