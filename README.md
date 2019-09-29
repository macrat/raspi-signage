![RasPi Signage](./logo.png
)
A video player for use raspberry pi as digital signage.


## Usage

### 1. Download and Install

``` shell
$ git clone https://github.com/macrat/raspi-signage.git && cd raspi-signage
$ pipenv install
```

### 2. Edit settings

Please edit `config.py`.
Maybe, least you have to edit `VIDEO_DIR`.

### 3. Run

``` shell
$ pipenv run start
```

And, access to `http://{your raspberry pi address}:8080/`.

### Ansible: Another install option

[raspi-signage-ansible](https://github.com/macrat/raspi-signage-ansible) is the best way to make digital signage from scratch.
that includes all settings such as auto startup or automounting USB memory.


## Control by curl command

``` shell
$ curl -X GET  http://{address}:8080/api/  # get status

$ curl -X POST http://{address}:8080/api/next  # play next video
$ curl -X POST http://{address}:8080/api/prev  # play previous video

$ curl -X POST http://{address}:8080/api/pause   # pause video play
$ curl -X POST http://{address}:8080/api/resume  # resume paused video play

$ curl -X POST http://{address}:8080/api/stop  # stop video

$ curl -X POST http://{address}:8080/api/play -d '{"path": "/path/to/file.mp4"}'  # play specific video
$ curl -X POST http://{address}:8080/api/play -d '{"index": 7}'                   # play 7th video in the playlist (you can get playlist with /api/ )
```
