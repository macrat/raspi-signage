import asyncio
import functools
import logging
import pathlib
import typing

from aiohttp import web


VIDEOS_PATH = pathlib.Path("videos/")
PLAY_COMMAND = "mplayer"


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
    def __init__(
        self, playlist: VideoPlaylist, play_command: str = PLAY_COMMAND
    ) -> None:
        self.playlist = playlist
        self.play_command = play_command

        self.cur_ = playlist[0]
        self.command: asyncio.Queue = asyncio.Queue()

    @property
    def current_path(self) -> pathlib.Path:
        return self.cur_

    @current_path.setter
    def current_path(self, path: pathlib.Path) -> None:
        self.cur_ = path
        asyncio.create_task(self.command.put("re-play"))

    @property
    def current_index(self) -> int:
        return self.playlist.index(self.current_path)

    @current_index.setter
    def current_index(self, index: int) -> None:
        self.current_path = self.playlist[index]

    def prev(self) -> None:
        try:
            self.current_index -= 1
        except IndexError:
            self.current_index = len(self.playlist) - 1

    def next(self) -> None:
        try:
            self.current_index += 1
        except IndexError:
            self.current_index = 0

    async def play(self) -> asyncio.subprocess.Process:
        return await asyncio.create_subprocess_shell(
            f"{PLAY_COMMAND} '{player.current_path}'",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    async def play_loop(self) -> None:
        while True:
            proc = await self.play()

            async def wait_cmd():
                cmd = await self.command.get()
                if cmd == "re-play":
                    try:
                        proc.terminate()
                    except ProcessLookupError:
                        pass

            async def wait_video():
                if await proc.wait() == 0:
                    self.next()

            await asyncio.wait(
                [wait_cmd(), wait_video()], return_when=asyncio.FIRST_COMPLETED
            )


player = VideoPlayer(VideoPlaylist())


@web.middleware
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


def status_response(error: str = ""):
    return web.json_response(
        {
            "error": error,
            "playlist": [str(x) for x in player.playlist],
            "current": {
                "index": player.current_index,
                "path": str(player.current_path),
            },
        }
    )


def video_response(index: int) -> web.Response:
    return web.json_response({"index": index, "path": str(player.playlist[index])})


@route.get("/")
async def index(request: web.Request) -> web.FileResponse:
    return web.FileResponse("./index.html")


@route.get("/status")
@api_endpoint
async def status(req: web.Request) -> web.Response:
    return status_response()


@route.get("/next")
@api_endpoint
async def get_next(req: web.Request) -> web.Response:
    return video_response((player.current_index + 1) % len(player.playlist))


@route.post("/next")
@api_endpoint
async def go_next(req: web.Request) -> web.Response:
    player.next()
    return status_response()


@route.get("/prev")
@api_endpoint
async def get_prev(req: web.Request) -> web.Response:
    return video_response((player.current_index - 1) % len(player.playlist))


@route.post("/prev")
@api_endpoint
async def go_prev(req: web.Request) -> web.Response:
    player.prev()
    return status_response()


@route.get("/current")
@api_endpoint
async def current_info(req: web.Request) -> web.Response:
    return video_response(player.current_index)


@route.post("/current")
@api_endpoint
async def play_video(req: web.Request) -> web.Response:
    try:
        query = await req.json()
    except Exception as e:
        logging.error(f"bad rqeust: {e}")
        return web.json_response({"error": "400: invalid json"}, status=400)

    path = pathlib.Path(query.get("path"))
    try:
        index = int(query["index"]) if query.get("index") is not None else None
    except ValueError:
        return web.json_response({"error": "400: index is must be int"}, status=400)

    if (
        path is not None
        and index is not None
        and pathlib.Path(path) != player.playlist[index]
    ):
        return web.json_response(
            {"error": "400: inconsistent index and path"}, status=400
        )

    if path is not None:
        try:
            player.current_path = path
            return video_response(player.current_index)
        except KeyError:
            return web.json_response(
                {"error": f"400: no such video ({path})"}, status=400
            )

    if index is not None:
        try:
            player.current_index = index
            return video_response(player.current_index)
        except IndexError:
            return web.json_response(
                {"error": f"400: index {index} is out of bounds the playlist"},
                status=400,
            )

    return web.json_response({"error": f"400: must be set index or path"}, status=400)


@app.on_startup.append
async def on_start(app: web.Application) -> None:
    asyncio.create_task(player.play_loop())


app.add_routes(route)


if __name__ == "__main__":
    web.run_app(app, host="127.0.0.1")
