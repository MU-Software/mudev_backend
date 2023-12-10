import asyncio
import dataclasses
import subprocess as sp  # nosec B404


@dataclasses.dataclass(frozen=True)
class SubProcessResult:
    stdout: str
    stderr: str
    returncode: int


def run(cmdline: list[str], *, check: bool = True) -> SubProcessResult:
    process = sp.run(cmdline, stdout=sp.PIPE, stderr=sp.PIPE, check=check)  # nosec B603
    stdout, stderr = map(lambda x: x.decode().strip(), [process.stdout, process.stderr])
    return SubProcessResult(stdout=stdout, stderr=stderr, returncode=process.returncode)


async def async_run(cmdline: list[str], *, check: bool = True) -> SubProcessResult:
    process = await asyncio.create_subprocess_exec(*cmdline, stdout=sp.PIPE, stderr=sp.PIPE)
    stdout, stderr = map(lambda x: x.decode().strip(), await process.communicate())
    if process.returncode and check:
        raise sp.CalledProcessError(process.returncode, cmdline, output=stdout, stderr=stderr)
    return SubProcessResult(stdout=stdout, stderr=stderr, returncode=process.returncode)
