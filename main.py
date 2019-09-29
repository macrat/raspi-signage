import asyncio
import pathlib

from aiohttp import web

from api import Controller
from player import Playlist, Player
import config


app = web.Application()
app["player"] = Player(pathlib.Path(config.DEFAULT_FILE))
app["playlist"] = Playlist(pathlib.Path(config.BASE_DIR))


async def favicon(req: web.Request) -> web.FileResponse:
    return web.FileResponse("./assets/icon.ico")


async def index_html(req: web.Request) -> web.FileResponse:
    return web.FileResponse("./index.html")


app.add_routes([web.get("/", index_html), web.get("/favicon.ico", favicon)])
app.add_routes(Controller(app["playlist"], app["player"]).route())


@app.on_startup.append
async def on_start(app: web.Application) -> None:
    asyncio.create_task(app["player"].run())


if __name__ == "__main__":
    web.run_app(app, host=config.HOST, port=config.PORT)
