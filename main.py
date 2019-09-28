import asyncio
import pathlib

from aiohttp import web

from api import Controller
from player import VideoPlaylist, VideoPlayer
import config


app = web.Application()
app["player"] = VideoPlayer(pathlib.Path(config.DEFAULT_VIDEO))
app["playlist"] = VideoPlaylist()


async def index_html(req: web.Request) -> web.FileResponse:
    return web.FileResponse("./index.html")


app.add_routes([web.get("/", index_html)])
app.add_routes(Controller(app["playlist"], app["player"]).route())


@app.on_startup.append
async def on_start(app: web.Application) -> None:
    asyncio.create_task(app["player"].run())


if __name__ == "__main__":
    web.run_app(app, host=config.HOST, port=config.PORT)
