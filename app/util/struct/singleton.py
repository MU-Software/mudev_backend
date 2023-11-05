import typing


class Singleton(type):
    """
    from: https://stackoverflow.com/a/6798042/5702135
    usage:
        class Logger(metaclass=Singleton):
            pass
    """

    _instances: dict[str, typing.Type["Singleton"]] = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]
