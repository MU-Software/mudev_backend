# mypy: disable-error-code="no-untyped-def"
# TODO: Set proper type hints


class hybridmethod:
    """
    This can make us to write classmethod and instancemethod with same name
    From https://stackoverflow.com/a/28238047
    """

    def __init__(self, fclass, finstance=None, doc=None) -> None:
        self.fclass = fclass
        self.finstance = finstance
        self.__doc__ = doc or fclass.__doc__
        # support use on abstract base classes
        self.__isabstractmethod__ = bool(getattr(fclass, "__isabstractmethod__", False))

    def classmethod(self, fclass):
        return type(self)(fclass, self.finstance, None)

    def instancemethod(self, finstance):
        return type(self)(self.fclass, finstance, self.__doc__)

    def __get__(self, instance, cls):
        if instance is None or self.finstance is None:
            # either bound to the class, or no instance method available
            return self.fclass.__get__(cls, None)
        return self.finstance.__get__(instance, cls)


class class_or_instancemethod(classmethod):
    """
    This can make us to write classmethod and instancemethod on same method object.
    From https://stackoverflow.com/a/28238047
    """

    def __get__(self, instance, type_):
        descr_get = super().__get__ if instance is None else self.__func__.__get__
        return descr_get(instance, type_)
