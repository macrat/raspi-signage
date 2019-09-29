import functools
import logging
import pathlib
import typing

from aiohttp import web

from player import Playlist, Player


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
    def __init__(self, playlist: Playlist, player: Player) -> None:
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
