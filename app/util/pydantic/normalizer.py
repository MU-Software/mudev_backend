import typing

import pydantic

import app.util.mu_string as mu_string


class NormalizerModelMixin(pydantic.BaseModel):
    @pydantic.model_validator(mode="before")
    def normalizer(cls, values: dict[str, typing.Any]) -> dict[str, typing.Any]:
        for k, v in values.items():
            values[k] = mu_string.normalize(v).strip() if isinstance(v, str) else v
        return values
