import os
import random
import time
import vlc
import logging
import asyncio
import aiohttp
import threading
import aiohttp_cors

from bili_utils import BiliUtils
from sse_utils import Messager

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s@%(funcName)s: %(message)s',encoding="utf-8")
logger = logging.getLogger(__name__)

headers = {
    "Accept": "*/*",
    # 'Cookie': raw_cookie,
    "Referer": "https://www.bilibili.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/61.0.3163.79 Safari/537.36 Maxthon/5.0",
}

class Player:
    instance: vlc.Instance
    player: vlc.MediaPlayer

    def __init__(self):
        self.instance = vlc.Instance('--fullscreen')
        self.player = self.instance.media_player_new()
        logging.debug(f"已实例化 VLC")

    async def play(self, path: str) -> float:
        '''
        播放并返回时长
        '''
        media: vlc.Media = self.instance.media_new(f'file:///{path}')
        self.player.set_media(media)
        self.player.play()
        await asyncio.sleep(5)
        duration = self.player.get_length() / 1000
        logging.info(f"开始播放 {path}，时长 {duration}")
        return duration

class BiliPlayList():
    aid_set: set[int] = set()
    now_list: list[int] = []
    now_list_info: list[dict[int,str]] = []
    favorites: list[int] = []
    cookies: dict[str, str] = {}

    def __init__(self, favorites: list[int]):
        self.load_cookie()
        self.favorites = favorites

    def get_aid_num(self):
        return len(self.aid_set)
    
    def get_now_num(self):
        return len(self.now_list)

    def load_cookie(self):
        if not os.path.exists("./cookie/cookie.txt"):
            logging.warning("未找到 cookie/cookies.txt !")
            return
        with open("./cookie/cookie.txt", "r") as file:
            for cookie_item in file.read().replace(" ","").split(";"):
                cookie_map = cookie_item.split("=")
                self.cookies[cookie_map[0]] = cookie_map[1]

    def pick_now(self):
        picked = self.now_list[0]
        self.now_list.pop(0)
        logging.info(f"播放当前列表 {picked}")
        return picked

    def random_pick(self):
        randomed = random.choice(list(self.aid_set))
        logging.info(f"列表为空，随机播放 {randomed}")
        return randomed

    async def add(self,aid: int):
        if(aid in self.aid_set):
            self.now_list.append(aid)
            logging.info(f"{aid} 被添加至现有列表中")
            return
        path = await BiliUtils.get_video(aid)
        self.aid_set.add(aid)
        self.now_list.append(aid)
        logging.info(f"{aid} 被添加至双列表中")
        async with aiohttp.ClientSession(cookies=self.cookies) as session:
            url = "https://api.bilibili.com/x/v3/fav/resource/deal"
            params = {  "rid": aid,
                        "type": 2,
                        "add_media_ids": self.favorites[-1],
                        "csrf": self.cookies["bili_jct"]    }
            async with session.post(url, params=params, headers=headers) as response:
                result = await response.json()
                if(result["code"] == 0):
                    logging.info(f"{ aid } 已添加至收藏夹中")
                else:
                    logging.error(result)

    async def update_id_list(self):
        async with aiohttp.ClientSession() as session:
            url = "https://api.bilibili.com/x/v3/fav/resource/list"
            all_count = 0
            favor_each_count: list[int] = []
            for favor in self.favorites:
                params = {'media_id': favor, 'ps': 20}
                async with session.get(url, params=params, headers=headers) as response:
                    result = await response.json()
                await asyncio.sleep(1)
                all_count += result["data"]["info"]["media_count"]
                favor_each_count.append(result["data"]["info"]["media_count"])
            if(all_count <= len(self.aid_set)):
                logging.info("数量小于或等于当前列表数，无需更新")
                return
            # 更新列表
            i = 0
            for favor in self.favorites:
                for page in range(favor_each_count[i] // 20 + 1):
                    params = {'media_id': favor, 'ps': 20, 'pn': page + 1}
                    async with session.get(url, params=params, headers=headers) as response:
                        result = await response.json()
                    await asyncio.sleep(1)
                    for video in result["data"]["medias"]:
                        try:
                            path = await BiliUtils.get_video(video["id"])
                            self.aid_set.add(video["id"])
                            logging.info(f"{video["id"]} 已被更新至列表")
                        except:
                            self.aid_set.add(-video["id"])
                            logging.info(f"{video["id"]} 失效，记负数")
                i += 1
    
    async def update_now_playlist_info(self):
        info_list = []
        for vid in self.now_list:
            find_flag = False
            for info in self.now_list_info:
                if vid in info:
                    info_list.append(self.now_list_info)
                    find_flag = True
                    break
            if(not find_flag):
                sinfo = {vid: await BiliUtils.get_title(vid)}
                info_list.append(sinfo)
        self.now_list_info = info_list

def find_latest_log(dir):
    list = os.listdir(dir)
    list.sort(key=lambda fn: os.path.getmtime(dir+fn) if not os.path.isdir(dir+fn) else 0)
    return list[-1]

async def running():
    favorites = [2775060305]
    log_dir = "C:/Users/z1059/Documents/弹幕姬/Plugins/DanmuLog/"

    BILI_PLAY_LIST = BiliPlayList(favorites)
    PLAYER = Player()

    loop = asyncio.get_event_loop()
    loop.create_task(BILI_PLAY_LIST.update_id_list())

    last_check_time = time.perf_counter()
    wait_time = 0
    delta_time = 0

    log_name = find_latest_log(log_dir)
    log_file = open(log_dir + log_name,"r",encoding="utf-8-sig")

    while(True):
        await asyncio.sleep(1)
        delta_time = time.perf_counter() - last_check_time
        # 弹幕检测区域
        new_log = log_file.readline()
        if(new_log):
            if new_log[0:4] == "【弹幕】":
                sender = new_log.split("说：")[0].split(":")[-1].replace(" ","")
                new_damaku = new_log.split("说：")[-1]

                if(new_damaku[0:2]) == "点播":
                    ids = new_damaku.replace("点播","").split(" ")
                    for vid_id in ids:
                        if(len(vid_id) <= 0):
                            continue
                        aid = await BiliUtils.format_id(vid_id)
                        if(aid <= 0):
                            continue
                        loop.create_task(BILI_PLAY_LIST.add(aid))
                        await Messager.send_notice("success",f"{sender} 成功点播 av{aid}")
                        await BILI_PLAY_LIST.update_now_playlist_info()
                        await Messager.send_playlist(BILI_PLAY_LIST.now_list_info)

                if(new_damaku[0:2]) == "烟花":
                    ids = new_damaku.replace("烟花","").replace(" ","")
                    try:
                        fire_num = int(ids)
                        if(fire_num > 100):
                            fire_num = 1
                    except:
                        fire_num = 1
                    Messager.send_firework(fire_num,sender)

        # 切换播放区域
        if(delta_time < wait_time):
            continue
        if(BILI_PLAY_LIST.get_aid_num() <= 0):
            continue
        if(BILI_PLAY_LIST.get_now_num() > 0):
            aid = BILI_PLAY_LIST.pick_now()
        else:
            aid = BILI_PLAY_LIST.random_pick()

        await BILI_PLAY_LIST.update_now_playlist_info()
        await Messager.send_playlist(BILI_PLAY_LIST.now_list_info)
        await Messager.send_play_info(aid)

        wait_time = await PLAYER.play(f"./video/{aid}.mp4")

        last_check_time = time.perf_counter()
              
def messaging():
    app = aiohttp.web.Application()
    cors = aiohttp_cors.setup(app, defaults={
    "*": aiohttp_cors.ResourceOptions(
            allow_credentials=True,
            expose_headers="*",
            allow_headers="*",
        )
    })
    cors.add(app.router.add_get('/sse', Messager.sse_handler))
    aiohttp.web.run_app(app, host='127.0.0.1', port=8080)

def check_dir():
    """
    检查文件夹是否齐全，否则就新建
    """
    dirpaths = ["video","cookie"]
    for dirpath in dirpaths:
        if not os.path.exists(dirpath):
            logging.warning(f"文件夹不齐全，新建了 {dirpath} 文件夹")
            os.mkdir(dirpath)

if __name__ == '__main__':
    check_dir()
    loop = asyncio.get_event_loop()
    loop.create_task(running())
    thread = threading.Thread(target=messaging)
    thread.start()
    loop.run_forever()