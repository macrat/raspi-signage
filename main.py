import asyncio
import pathlib

from aiohttp import web

from api import Controller
from player import Playlist, Player
import config


app = web.Application()
app["player"] = Player(
    pathlib.Path(config.DEFAULT_FILE), pathlib.Path(config.INITIAL_FILE)
)
app["playlist"] = Playlist(pathlib.Path(config.BASE_DIR))
app["controller"] = Controller(app["playlist"], app["player"])


async def index_html(req: web.Request) -> web.FileResponse:
    return web.FileResponse("./index.html")


app.add_routes(app["controller"].route())
app.add_routes([web.get("/", index_html), web.static("/", "./assets")])


@app.on_startup.append
async def on_start(app: web.Application) -> None:
    asyncio.create_task(app["player"].run())

    if config.AUTO_PLAY:
        asyncio.create_task(app["controller"].auto_play())


if __name__ == "__main__":
    web.run_app(app, host=config.HOST, port=config.PORT)
