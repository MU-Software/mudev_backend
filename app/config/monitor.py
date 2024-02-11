import typing

import pydantic
import pydantic_settings

SENTRY_MODE = typing.Literal["api", "celery"]


class SentrySetting(pydantic_settings.BaseSettings):
    api_dsn: pydantic.HttpUrl | None = None
    api_enable_tracing: bool = True
    api_traces_sample_rate: float = 1.0
    api_profiles_sample_rate: float = 1.0

    celery_dsn: pydantic.HttpUrl | None = None
    celery_enable_tracing: bool = True
    celery_traces_sample_rate: float = 1.0
    celery_profiles_sample_rate: float = 1.0

    MODE_LIST: typing.ClassVar[set[SENTRY_MODE]] = {"api", "celery"}
    ATTR_LIST: typing.ClassVar[set[str]] = {
        "dsn",
        "enable_tracing",
        "traces_sample_rate",
        "profiles_sample_rate",
    }

    @pydantic.model_validator(mode="after")
    def validate_fields(self) -> typing.Self:
        for mode in self.MODE_LIST:
            if not hasattr(self, f"{mode}_dsn"):
                raise ValueError(f"Missing {mode}_dsn")
            if not getattr(self, f"{mode}_dsn"):
                continue

            for attr in self.ATTR_LIST:
                if not hasattr(self, f"{mode}_{attr}"):
                    raise ValueError(f"Missing {mode}_{attr}")

        return self

    def is_sentry_available(self, mode: SENTRY_MODE) -> bool:
        if mode not in self.MODE_LIST:
            raise ValueError(f"Invalid mode: {mode}")

        return bool(getattr(self, f"{mode}_dsn"))

    def build_config(self, mode: SENTRY_MODE) -> dict[str, str | float | bool]:
        if mode not in self.MODE_LIST:
            raise ValueError(f"Invalid mode: {mode}")

        return {attr: getattr(self, f"{mode}_{attr}") for attr in self.ATTR_LIST for mode in self.MODE_LIST}
