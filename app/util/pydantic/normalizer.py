import json
import typing

import pydantic

import app.util.mu_string as mu_string


class NormalizerModelMixin(pydantic.BaseModel):
    @pydantic.model_validator(mode="before")
    def normalizer(cls, values: dict[str, typing.Any] | str | bytes) -> dict[str, typing.Any]:
        if not isinstance(parsed_values := values if isinstance(values, dict) else json.loads(values), dict):
            raise ValueError(f"이해할 수 없는 유형의 데이터를 받았어요. [NotDict|{type(values)}]")

        for k, v in parsed_values.items():
            parsed_values[k] = mu_string.normalize(v).strip() if isinstance(v, str) else v
        return parsed_values
