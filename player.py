import asyncio
import pathlib
import typing

import config


class VideoPlaylist(typing.Sequence[pathlib.Path]):
    def __init__(self, path: pathlib.Path = pathlib.Path(config.VIDEOS_DIR)) -> None:
        self._path = path

    @property
    def path(self) -> pathlib.Path:
        return self._path

    def __iter__(self) -> typing.Iterator[pathlib.Path]:
        return iter(sorted(self._path.glob("**/*.mp4"), key=lambda x: str(x)))

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


class VideoPlayer:
    def __init__(self, default_file: pathlib.Path) -> None:
        self.default_file = default_file
        self._current = default_file
        self._playing = False

        self._command: asyncio.Queue = asyncio.Queue()

    @property
    def current(self) -> pathlib.Path:
        return self._current

    @property
    def playing(self) -> bool:
        return self._playing

    @playing.setter
    def playing(self, play: bool) -> None:
        if self._playing == play:
            return
        else:
            self._playing = play
            asyncio.create_task(self._command.put("play-pause"))

    async def play(self, path: pathlib.Path) -> None:
        self._current = path
        await self._command.put("kill")

    async def resume(self) -> None:
        self.playing = True

    async def pause(self) -> None:
        self.playing = False

    async def stop(self) -> None:
        await self.play(self.default_file)

    async def command_loop(self, proc: asyncio.subprocess.Process) -> None:
        while True:
            cmd = config.PLAYER_SHORTCUTS.get(await self._command.get())

            if cmd is not None and proc.stdin is not None:
                try:
                    proc.stdin.write(cmd)
                except ProcessLookupError:
                    break

            if cmd == b"q":
                break

        self._playing = False

    async def run(self) -> typing.NoReturn:
        while True:
            proc = await asyncio.create_subprocess_shell(
                f"{config.PLAY_COMMAND} '{self.current}'",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self._playing = self._current != self.default_file

            await asyncio.wait(
                [
                    asyncio.create_task(self.command_loop(proc)),
                    asyncio.create_task(proc.wait()),
                ],
                return_when=asyncio.FIRST_COMPLETED,
            )
