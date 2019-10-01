import asyncio
import itertools
import logging
import pathlib
import signal
import typing

import config


logger = logging.getLogger(__name__)


class UntiloFirstComplete:
    async def __aenter__(self) -> "UntiloFirstComplete":
        self.tasks: typing.Set[asyncio.Task] = set()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        _, pending = await asyncio.wait(self.tasks, return_when=asyncio.FIRST_COMPLETED)

        for x in pending:
            x.cancel()
            try:
                await x
            except asyncio.CancelledError:
                pass

        return True

    def start(self, awaitable: typing.Awaitable) -> None:
        self.tasks.add(asyncio.create_task(awaitable))


class Playlist(typing.Sequence[pathlib.Path]):
    def __init__(self, path: pathlib.Path) -> None:
        self._path = path
        self.patterns = [*config.VIDEO_PATTERNS, *config.IMAGE_PATTERNS]

    @property
    def path(self) -> pathlib.Path:
        return self._path

    def __iter__(self) -> typing.Iterator[pathlib.Path]:
        return iter(
            sorted(
                itertools.chain.from_iterable(
                    self._path.glob("**/" + pattern) for pattern in self.patterns
                ),
                key=lambda x: str(x),
            )
        )

    def is_included(self, path: pathlib.Path) -> bool:
        for pattern in self.patterns:
            if path.match(pattern):
                return True
        return False

    @typing.overload
    def __getitem__(self, idx: int) -> pathlib.Path:
        pass

    @typing.overload
    def __getitem__(self, idx: slice) -> typing.Tuple[pathlib.Path]:
        pass

    def __getitem__(self, idx):
        if isinstance(idx, slice):
            return list(self).__getitem__(idx)

        for i, x in enumerate(self):
            if i == idx:
                return x
        raise IndexError(idx)

    def __len__(self) -> int:
        return sum(1 for _ in self)

    def index(self, path: pathlib.Path, start: int = 0, stop: int = None) -> int:
        for i, x in enumerate(self[start:stop]):
            if x == path:
                return i + start
        raise KeyError(path)


class Player:
    def __init__(
        self, default_file: pathlib.Path, initial_file: pathlib.Path = None
    ) -> None:
        self.default_file = default_file
        self._current = initial_file if initial_file is not None else default_file
        self._playing = False

        self._command: asyncio.Queue = asyncio.Queue()

    @property
    def current(self) -> pathlib.Path:
        return self._current

    @property
    def playing(self) -> bool:
        return self._playing

    async def play(self, path: pathlib.Path) -> None:
        self._current = path
        await self._command.put("kill")

    async def resume(self) -> None:
        if not self._playing:
            await self._command.put("play-pause")
            self._playing = True

    async def pause(self) -> None:
        if self._playing:
            await self._command.put("play-pause")
            self._playing = False

    async def stop(self) -> None:
        await self.play(self.default_file)

    def _type_of(self, path: pathlib.Path) -> str:
        for pattern in config.VIDEO_PATTERNS:
            if path.match(pattern):
                return "video"

        for pattern in config.IMAGE_PATTERNS:
            if path.match(pattern):
                return "image"

        return "unknown"

    def _decide_command(
        self, path: pathlib.Path
    ) -> typing.Tuple[str, typing.Mapping[str, bytes]]:
        type_ = self._type_of(self.current)

        if type_ == "video":
            return config.VIDEO_COMMAND, config.VIDEO_SHORTCUTS
        elif type_ == "image":
            return config.IMAGE_COMMAND, config.IMAGE_SHORTCUTS
        else:
            raise TypeError("unknown type", path)

    async def _command_loop(
        self, proc: asyncio.subprocess.Process, shortcuts: typing.Mapping[str, bytes]
    ) -> None:
        while True:
            command = await self._command.get()
            shortcut = shortcuts.get(command)

            if shortcut is not None and proc.stdin is not None:
                try:
                    proc.stdin.write(shortcut)
                except ProcessLookupError as e:
                    logger.error(f"process missing: {e}")
                    break

            if command == "kill":
                try:
                    proc.terminate()
                except ProcessLookupError as e:
                    logger.info(f"process missing when killing: {e}")
                    break
                break

        self._playing = False

    async def run(self) -> typing.NoReturn:
        while True:
            command, shortcuts = self._decide_command(self.current)

            logger.info(f"exec: {command} '{self.current}'")
            proc = await asyncio.create_subprocess_shell(
                f"{command} '{self.current}'",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
            )
            self._playing = True

            async with UntiloFirstComplete() as nursery:
                nursery.start(self._command_loop(proc, shortcuts))
                nursery.start(proc.wait())
