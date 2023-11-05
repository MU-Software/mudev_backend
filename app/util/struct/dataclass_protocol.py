import dataclasses
import typing

if typing.TYPE_CHECKING:

    class DataclassProtocol(typing.Protocol):
        """
        Protocol for dataclasses, use this as a type hint for dataclasses.dataclass.
        """

        __dataclass_fields__: dict[str, dataclasses.Field]
        __dataclass_params__: dict
        __post_init__: typing.Callable | None

else:

    class DataclassProtocol:
        """
        Protocol for dataclasses, use this as a type hint for dataclasses.dataclass.
        """

        ...
