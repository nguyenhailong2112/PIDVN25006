def bbox_center(bbox_xyxy: tuple[int, int, int, int]) -> tuple[float, float]:
    x1, y1, x2, y2 = bbox_xyxy
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0


def bbox_corners(bbox_xyxy: tuple[int, int, int, int]) -> list[tuple[float, float]]:
    x1, y1, x2, y2 = bbox_xyxy
    return [
        (x1, y1),
        (x2, y1),
        (x1, y2),
        (x2, y2),
    ]


def normalize_point(point_xy: tuple[float, float], frame_width: int, frame_height: int) -> tuple[float, float]:
    x, y = point_xy
    return x / frame_width, y / frame_height


def is_point_in_polygon(point_xy: tuple[float, float], polygon: list[tuple[float, float]]) -> bool:
    x, y = point_xy
    inside = False
    n = len(polygon)
    if n < 3:
        return False

    x1, y1 = polygon[0]
    for i in range(1, n + 1):
        x2, y2 = polygon[i % n]
        if (y1 > y) != (y2 > y):
            x_intersect = (x2 - x1) * (y - y1) / ((y2 - y1) + 1e-12) + x1
            if x < x_intersect:
                inside = not inside
        x1, y1 = x2, y2
    return inside


def is_bbox_center_in_polygon(
    bbox_xyxy: tuple[int, int, int, int],
    polygon: list[tuple[float, float]],
    frame_width: int,
    frame_height: int,
) -> bool:
    center_px = bbox_center(bbox_xyxy)
    center_norm = normalize_point(center_px, frame_width, frame_height)
    return is_point_in_polygon(center_norm, polygon)


def is_bbox_all_corners_in_polygon(
    bbox_xyxy: tuple[int, int, int, int],
    polygon: list[tuple[float, float]],
    frame_width: int,
    frame_height: int,
) -> bool:
    for corner_px in bbox_corners(bbox_xyxy):
        corner_norm = normalize_point(corner_px, frame_width, frame_height)
        if not is_point_in_polygon(corner_norm, polygon):
            return False
    return True
