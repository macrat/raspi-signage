import asyncio
import functools
import logging
import pathlib
import typing

from aiohttp import web


VIDEOS_PATH = pathlib.Path("videos/")
PLAY_COMMAND = "omxplayer --loop --no-osd"


app = web.Application()
route = web.RouteTableDef()


class VideoPlaylist(typing.Sequence[pathlib.Path]):
    def __init__(self, path: pathlib.Path = VIDEOS_PATH) -> None:
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
        await self.restart()

    async def resume(self) -> None:
        self.playing = True

    async def pause(self) -> None:
        self.playing = False

    async def stop(self) -> None:
        await self.play(self.default_file)

    async def restart(self) -> None:
        await self._command.put("restart")

    async def command_loop(self, proc: asyncio.subprocess.Process) -> None:
        commands = {"play-pause": b" ", "restart": b"q"}

        while True:
            cmd = commands.get(await self._command.get())

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
                f"{PLAY_COMMAND} '{self.current}'",
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


def api_endpoint(
    handler: typing.Callable[[web.Request], typing.Awaitable[web.Response]]
) -> typing.Callable[[web.Request], typing.Awaitable[web.Response]]:
    @functools.wraps(handler)
    async def wrap(request: web.Request) -> web.Response:
        try:
            response = await handler(request)
            return response
        except web.HTTPException as ex:
            raise
        except Exception as e:
            logging.error(f'"{request.url}": {repr(e)}')
            return web.json_response(
                {"error": "500: internal server error"}, status=500
            )

    return wrap


class Controller:
    def __init__(self, playlist: VideoPlaylist, player: VideoPlayer) -> None:
        self.playlist = playlist
        self.player = player

    def _bad_request(self, message: str = "bad request") -> web.Response:
        return web.json_response({"error": f"400: {message}"}, status=400)

    def _current_index(self) -> typing.Optional[int]:
        if self.player.current == self.player.default_file:
            return None
        else:
            return self.playlist.index(self.player.current)

    async def status(self, req: web.Request) -> web.Response:
        if self.player.current == self.player.default_file:
            current = None
            status = "stop"
        else:
            current = {
                "path": str(self.player.current),
                "index": self.playlist.index(self.player.current),
            }
            status = "play" if self.player.playing else "pause"

        return web.json_response(
            {
                "error": "",
                "playlist": [str(x) for x in self.playlist],
                "current": current,
                "status": status,
            }
        )

    async def go_next(self, req: web.Request) -> web.Response:
        index = self._current_index()
        if index is None:
            await self.player.play(self.playlist[0])
        else:
            await self.player.play(self.playlist[(index + 1) % len(self.playlist)])
        return web.json_response({"error": ""})

    async def go_prev(self, req: web.Request) -> web.Response:
        index = self._current_index()
        if index is None:
            await self.player.play(self.playlist[-1])
        else:
            await self.player.play(self.playlist[(index - 1) % len(self.playlist)])

        return web.json_response({"error": ""})

    async def resume(self, req: web.Request) -> web.Response:
        await self.player.resume()
        return web.json_response({"error": ""})

    async def pause(self, req: web.Request) -> web.Response:
        await self.player.pause()
        return web.json_response({"error": ""})

    async def stop(self, req: web.Request) -> web.Response:
        await self.player.stop()
        return web.json_response({"error": ""})

    async def play(self, req: web.Request) -> web.Response:
        try:
            query = await req.json()
        except Exception as e:
            logging.error(f"bad request: {e}")
            return self._bad_request("invalid json")

        path = pathlib.Path(query.get("path"))
        try:
            index = int(query["index"]) if query.get("index") is not None else None
        except ValueError:
            return self._bad_request("index is must be int")

        if (
            path is not None
            and index is not None
            and pathlib.Path(path) != self.playlist[index]
        ):
            return self._bad_request("inconsistent index and path")

        try:
            if path is not None:
                await self.player.play(path)
            elif index is not None:
                await self.player.play(self.playlist[index])
            return web.json_response({"error": ""})
        except (KeyError, IndexError):
            return self._bad_request(f'no such video (path: "{path}", index: {index})')

        return self._bad_request("must be set index or path")

    def route(self, path: str = "/api") -> typing.List[web.RouteDef]:
        return [
            web.route(x[1], f"{path}{x[0]}", api_endpoint(x[2]))
            for x in [
                ("", "GET", self.status),
                ("/next", "POST", self.go_next),
                ("/prev", "POST", self.go_prev),
                ("/resume", "POST", self.resume),
                ("/pause", "POST", self.pause),
                ("/stop", "POST", self.stop),
                ("/play", "POST", self.play),
            ]
        ]


async def index_html(req: web.Request) -> web.FileResponse:
    return web.FileResponse("./index.html")


@app.on_startup.append
async def on_start(app: web.Application) -> None:
    asyncio.create_task(app["player"].run())


app["player"] = VideoPlayer(pathlib.Path("./blank.mp4"))
app["playlist"] = VideoPlaylist()
app.add_routes([web.get("/", index_html)])
app.add_routes(Controller(app["playlist"], app["player"]).route())


if __name__ == "__main__":
    web.run_app(app, host="127.0.0.1")
