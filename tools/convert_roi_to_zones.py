import json
from pathlib import Path

from core.path_utils import ensure_exists, resolve_project_path


def convert_pixel_roi_to_normalized(
    input_path: str,
    output_path: str,
    image_width: int,
    image_height: int,
    target_object: str,
):
    input_file = ensure_exists(input_path, "ROI input file")
    output_file = resolve_project_path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    data = json.loads(input_file.read_text(encoding="utf-8"))

    zones = []
    for zone_id, points in data.items():
        polygon = []
        for x, y in points:
            polygon.append([round(x / image_width, 6), round(y / image_height, 6)])

        zones.append(
            {
                "zone_id": zone_id.replace("ROI_", ""),
                "target_object": target_object,
                "polygon": polygon,
            }
        )

    output = {
        "source": str(input_file),
        "target_object": target_object,
        "zones": zones,
    }
    output_file.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved normalized zones to: {output_file}")


if __name__ == "__main__":
    convert_pixel_roi_to_normalized(
        input_path="ROI_Cam101.json",
        output_path="configs/zones_cam101.json",
        image_width=1920,
        image_height=1080,
        target_object="trolley",
    )
