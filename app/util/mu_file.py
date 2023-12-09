import hashlib
import os
import pathlib as pt
import typing

import aiofiles


def fileobj_md5(fp: typing.BinaryIO, usedforsecurity: bool = False) -> str:
    hash_md5 = hashlib.md5(usedforsecurity=usedforsecurity)
    fp.seek(0)
    for chunk in iter(lambda: fp.read(4096), b""):
        hash_md5.update(chunk)
    fp.seek(0)
    return hash_md5.hexdigest()


def file_md5(fname: os.PathLike, usedforsecurity: bool = False) -> str:
    return fileobj_md5(open(fname, "rb"), usedforsecurity=usedforsecurity)


def save_tempfile(fp: typing.IO[bytes], save_path: pt.Path, *, chunk_size: int = 4096) -> pt.Path:
    if not save_path.exists():
        save_path.mkdir(parents=True, exist_ok=True)

    with save_path.open("wb") as f:
        while chunk := fp.read(chunk_size):
            f.write(chunk)
    return save_path


async def async_save_tempfile(fp: typing.IO[bytes], save_path: pt.Path, *, chunk_size: int = 4096) -> pt.Path:
    if not save_path.exists():
        save_path.mkdir(parents=True, exist_ok=True)

    async with aiofiles.open(save_path, "wb") as f:
        while chunk := fp.read(chunk_size):
            await f.write(chunk)
    return save_path
