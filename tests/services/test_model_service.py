import pytest

from app.models.agent import RiskTier
from app.models.model import Model, ModelStatus
from app.services.model_service import (
    ModelAlreadyExistsError,
    ModelNotFoundError,
    ModelService,
)


def create_model(model_id: str = "gpt-4") -> Model:
    return Model(
        model_id=model_id,
        provider="OpenAI",
        version="4.0",
        owner="security-team",
        description="Enterprise assistant model",
        status=ModelStatus.APPROVED,
        risk_tier=RiskTier.MEDIUM,
    )


def test_register_model():
    service = ModelService()

    model = create_model()

    result = service.register_model(model)

    assert result == model


def test_duplicate_model_rejected():
    service = ModelService()

    model = create_model()

    service.register_model(model)

    with pytest.raises(ModelAlreadyExistsError):
        service.register_model(model)


def test_get_unknown_model():
    service = ModelService()

    with pytest.raises(ModelNotFoundError):
        service.get_model("unknown-model")



def test_list_models():
    service = ModelService()

    model_1 = create_model("gpt-4")
    model_2 = create_model("claude-4")

    service.register_model(model_1)
    service.register_model(model_2)

    models = service.list_models()

    assert len(models) == 2
    assert model_1 in models
    assert model_2 in models
