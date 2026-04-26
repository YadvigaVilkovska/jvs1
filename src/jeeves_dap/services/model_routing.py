"""Contract: model role routing config and environment overrides without any network calls."""

from __future__ import annotations

from collections.abc import Mapping

from jeeves_dap.domain.models import ModelRoute, ModelRoutePair, ModelRoutingConfig

INTAKE_PRIMARY_PROVIDER_ENV = "INTAKE_PRIMARY_PROVIDER"
INTAKE_PRIMARY_MODEL_ENV = "INTAKE_PRIMARY_MODEL"
INTAKE_FALLBACK_PROVIDER_ENV = "INTAKE_FALLBACK_PROVIDER"
INTAKE_FALLBACK_MODEL_ENV = "INTAKE_FALLBACK_MODEL"
WORK_PRIMARY_PROVIDER_ENV = "WORK_PRIMARY_PROVIDER"
WORK_PRIMARY_MODEL_ENV = "WORK_PRIMARY_MODEL"
WORK_FALLBACK_PROVIDER_ENV = "WORK_FALLBACK_PROVIDER"
WORK_FALLBACK_MODEL_ENV = "WORK_FALLBACK_MODEL"

DEFAULT_MODEL_ROUTING_CONFIG = ModelRoutingConfig(
    intake=ModelRoutePair(
        primary=ModelRoute(provider="openai", model="gpt-4o-mini"),
        fallback=ModelRoute(provider="deepseek", model="deepseek-chat"),
    ),
    work=ModelRoutePair(
        primary=ModelRoute(provider="deepseek", model="deepseek-reasoner"),
        fallback=ModelRoute(provider="openai", model="gpt-5.5"),
    ),
)

VALID_PROVIDERS = frozenset({"openai", "deepseek"})


def build_default_model_routing_config() -> ModelRoutingConfig:
    """Contract: return the immutable default routing config for all model roles."""

    return DEFAULT_MODEL_ROUTING_CONFIG


def build_model_routing_config_from_env(env: Mapping[str, str] | None = None) -> ModelRoutingConfig:
    """Contract: build routing config from environment-like values with strict provider validation."""

    values = env or {}
    defaults = build_default_model_routing_config()
    return ModelRoutingConfig(
        intake=ModelRoutePair(
            primary=ModelRoute(
                provider=_read_provider(
                    values,
                    INTAKE_PRIMARY_PROVIDER_ENV,
                    defaults.intake.primary.provider,
                ),
                model=values.get(INTAKE_PRIMARY_MODEL_ENV, defaults.intake.primary.model),
            ),
            fallback=ModelRoute(
                provider=_read_provider(
                    values,
                    INTAKE_FALLBACK_PROVIDER_ENV,
                    defaults.intake.fallback.provider,
                ),
                model=values.get(INTAKE_FALLBACK_MODEL_ENV, defaults.intake.fallback.model),
            ),
        ),
        work=ModelRoutePair(
            primary=ModelRoute(
                provider=_read_provider(
                    values,
                    WORK_PRIMARY_PROVIDER_ENV,
                    defaults.work.primary.provider,
                ),
                model=values.get(WORK_PRIMARY_MODEL_ENV, defaults.work.primary.model),
            ),
            fallback=ModelRoute(
                provider=_read_provider(
                    values,
                    WORK_FALLBACK_PROVIDER_ENV,
                    defaults.work.fallback.provider,
                ),
                model=values.get(WORK_FALLBACK_MODEL_ENV, defaults.work.fallback.model),
            ),
        ),
    )


class ModelRouter:
    """Contract: return configured primary and fallback routes for a model role only."""

    def __init__(self, config: ModelRoutingConfig) -> None:
        self._config = config

    def get_route(self, role: str) -> ModelRoutePair:
        """Contract: resolve a role to one configured route pair and reject unknown roles."""

        if role == "intake":
            return self._config.intake
        if role == "work":
            return self._config.work
        raise ValueError(f"Unknown model role: {role}")


def _read_provider(values: Mapping[str, str], key: str, default: str) -> str:
    """Contract: return one validated provider name from environment-like values."""

    provider = values.get(key, default)
    if provider not in VALID_PROVIDERS:
        raise ValueError(f"Unsupported provider for {key}: {provider}")
    return provider
