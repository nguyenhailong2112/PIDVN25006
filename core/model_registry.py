from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from ultralytics import YOLO

from core.logger_config import get_logger


logger = get_logger(__name__)

@dataclass
class ModelBundle:
    model: YOLO
    lock: Lock


class ModelRegistry:
    _lock = Lock()
    _models: dict[str, ModelBundle] = {}

    @classmethod
    def get(cls, model_path: str) -> ModelBundle:
        with cls._lock:
            bundle = cls._models.get(model_path)
            if bundle is not None:
                return bundle

            model = YOLO(model_path)
            try:
                model.fuse()
            except Exception:
                # Some model variants do not support fuse; keep running.
                logger.debug("Model fuse not supported for %s", model_path)

            bundle = ModelBundle(model=model, lock=Lock())
            cls._models[model_path] = bundle
            return bundle
