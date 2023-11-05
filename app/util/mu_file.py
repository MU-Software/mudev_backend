import hashlib
import os
import typing


def fileobj_md5(fp: typing.BinaryIO, usedforsecurity: bool = False) -> str:
    hash_md5 = hashlib.md5(usedforsecurity=usedforsecurity)
    fp.seek(0)
    for chunk in iter(lambda: fp.read(4096), b""):
        hash_md5.update(chunk)
    fp.seek(0)
    return hash_md5.hexdigest()


def file_md5(fname: os.PathLike, usedforsecurity: bool = False) -> str:
    return fileobj_md5(open(fname, "rb"), usedforsecurity=usedforsecurity)
