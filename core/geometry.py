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


def _orientation(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(a: tuple[float, float], b: tuple[float, float], p: tuple[float, float]) -> bool:
    eps = 1e-9
    return (
        min(a[0], b[0]) - eps <= p[0] <= max(a[0], b[0]) + eps
        and min(a[1], b[1]) - eps <= p[1] <= max(a[1], b[1]) + eps
    )


def _segments_intersect(
    p1: tuple[float, float],
    p2: tuple[float, float],
    q1: tuple[float, float],
    q2: tuple[float, float],
) -> bool:
    o1 = _orientation(p1, p2, q1)
    o2 = _orientation(p1, p2, q2)
    o3 = _orientation(q1, q2, p1)
    o4 = _orientation(q1, q2, p2)
    eps = 1e-9

    if ((o1 > eps and o2 < -eps) or (o1 < -eps and o2 > eps)) and ((o3 > eps and o4 < -eps) or (o3 < -eps and o4 > eps)):
        return True

    if abs(o1) <= eps and _on_segment(p1, p2, q1):
        return True
    if abs(o2) <= eps and _on_segment(p1, p2, q2):
        return True
    if abs(o3) <= eps and _on_segment(q1, q2, p1):
        return True
    if abs(o4) <= eps and _on_segment(q1, q2, p2):
        return True
    return False


def is_bbox_intersects_polygon(
    bbox_xyxy: tuple[int, int, int, int],
    polygon: list[tuple[float, float]],
    frame_width: int,
    frame_height: int,
) -> bool:
    if is_bbox_all_corners_in_polygon(bbox_xyxy, polygon, frame_width, frame_height):
        return True

    x1, y1, x2, y2 = bbox_xyxy
    bbox_polygon = [
        normalize_point((x1, y1), frame_width, frame_height),
        normalize_point((x2, y1), frame_width, frame_height),
        normalize_point((x2, y2), frame_width, frame_height),
        normalize_point((x1, y2), frame_width, frame_height),
    ]

    for point in bbox_polygon:
        if is_point_in_polygon(point, polygon):
            return True

    min_x = min(point[0] for point in bbox_polygon)
    max_x = max(point[0] for point in bbox_polygon)
    min_y = min(point[1] for point in bbox_polygon)
    max_y = max(point[1] for point in bbox_polygon)
    for px, py in polygon:
        if min_x <= px <= max_x and min_y <= py <= max_y:
            return True

    bbox_edges = list(zip(bbox_polygon, bbox_polygon[1:] + bbox_polygon[:1]))
    polygon_edges = list(zip(polygon, polygon[1:] + polygon[:1]))
    for bbox_edge in bbox_edges:
        for polygon_edge in polygon_edges:
            if _segments_intersect(bbox_edge[0], bbox_edge[1], polygon_edge[0], polygon_edge[1]):
                return True
    return False
