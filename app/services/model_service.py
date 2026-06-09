
from threading import RLock

from app.models.model import Model


class ModelAlreadyExistsError(Exception):
    pass


class ModelNotFoundError(Exception):
    pass


class ModelService:
    def __init__(self) -> None:
        self._models: dict[str, Model] = {}
        self._lock = RLock()

    def register_model(
        self,
        model: Model,
    ) -> Model:
        with self._lock:
            if model.model_id in self._models:
                raise ModelAlreadyExistsError(
                    f"Model '{model.model_id}' already exists"
                )

            self._models[model.model_id] = model

            return model

    def get_model(
        self,
        model_id: str,
    ) -> Model:
        with self._lock:
            try:
                return self._models[model_id]

            except KeyError as exc:
                raise ModelNotFoundError(
                    f"Model '{model_id}' not found"
                ) from exc

    def list_models(
        self,
    ) -> list[Model]:
        with self._lock:
            return list(self._models.values())