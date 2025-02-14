import csv
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

logging.basicConfig(level=logging.DEBUG, format='[%(asctime)s] %(levelname)s@%(funcName)s: %(message)s',encoding="utf-8")
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
        self.player.set_fullscreen(True)
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
    now_list_info: list = []
    favorites: list[int] = []
    sender_record: dict = {}
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

    async def judge_by_aid(self,aid: int) -> tuple[bool,bool]:
        '''
        判断作品是否达标
        '''

        ### 硬性标准

        # 黑名单不点
        with open("./option/blacklist.csv","r", encoding="utf-8-sig") as csvfile:
            lists = csv.DictReader(csvfile)
            for single in lists:
                if(aid == int(single["aid"])):
                    return False,False

        ## 获取作品信息
        info = await BiliUtils.get_info(aid)
        # 失效不点
        if(info["code"] < 0):
            return False, False
        # 超过时长不点
        MAX_DURATION = float(os.getenv("MAX_DURATION",10)) * 60
        if(info["data"]["duration"] > MAX_DURATION):
            return False, False
        # 时间太久远不点
        if(info["data"]["pubdate"] < time.mktime(time.strptime(os.getenv("OLDEST_YEAR","2015"), "%Y"))):
            return False, False
        # 评论数太少不点
        if(info["data"]["stat"]["reply"] < int(os.getenv("LEAST_COMMENT",2))):
            return False, False
        # 特殊标题不点
        forbidden_keywords = [
            "补档", "猎奇", "精神污染", "高精", "流出", "视听禁止", "検索", "检索",
            "武器A", "武器a", "10492", "10388"
        ]
        for forbid in forbidden_keywords:
            if(forbid in info["data"]["title"]):
                return False, False
        ## 获取 TAG
        tag_list = await BiliUtils.get_tag(aid)
        # 不含硬性标签或不在指定分区内不点
        r_id_list = os.getenv("REQUIRED_ID","26").split(",")
        if (str(info["data"]["tid"]) not in r_id_list):
            r_tag_list = os.getenv("REQUIRED_TAG","音mad,音MAD,YTPMV,ytpmv,音 MAD").split(",")
            find_flag = False
            for tag in tag_list:
                if(tag in r_tag_list):
                    find_flag = True
            if(not find_flag):
                return False, False
        # 标签含有特殊词不点
        for tag in tag_list:
            for forbid in forbidden_keywords:
                if forbid in tag:
                    return False, False
            
        ### 软性标准
        # 仅 YTPMV 可收录
        if("YTPMV" not in tag_list and "ytpmv" not in tag_list):
            return True,False
        restrict_words = ["哈基米","电棍","叮咚鸡","ccb","踩踩背","胖宝宝"]
        for restrict in restrict_words:
            if(restrict in info["data"]["title"]):
                return True, False
        for tag in tag_list:
            for restrict in restrict_words:
                if restrict in tag:
                    return True, False

        return True,True


    def record_sender(self,sender: str = "无名氏") -> bool:
        '''记录发送者'''
        REFRESH_DURATION = float(os.getenv("REFRESH_DURATION",60)) * 60 * 1000
        if(sender not in self.sender_record):
            self.sender_record[sender] = {
                "record_start": time.perf_counter(),
                "num": 1
            }
        else:
            if(time.perf_counter() - self.sender_record[sender]["record_start"] >= REFRESH_DURATION):
                self.sender_record[sender]["record_start"] = time.perf_counter()
                self.sender_record[sender]["num"] = 0
            self.sender_record[sender]["num"] += 1
    
    def judge_can_pick(self,sender: str = "无名氏") -> bool:
        '''判断发送者'''
        MAX_TIMES = int(os.getenv("PICK_MAX_TIMES",2))
        REFRESH_DURATION = float(os.getenv("REFRESH_DURATION",60)) * 60 * 1000
        if(sender not in self.sender_record):
            return True
        else:
            if(time.perf_counter() - self.sender_record[sender]["record_start"] >= REFRESH_DURATION):
                return True
            else:
                if(self.sender_record[sender]["num"] >= MAX_TIMES):
                    return False
                else:
                    return True

        

    async def add(self,aid: int,sender: str = "无名氏"):
        '''添加视频'''
        # 判断点播上限
        if(not self.judge_can_pick(sender)):
            logging.info(f"{sender} 达到最大点播上限，点播失败！")
            await Messager.send_notice("error",f"{sender} 达到点播次数上限，点播失败！")
            return
        if(aid in self.aid_set):
            self.now_list.append(aid)
            logging.info(f"{aid} 被添加至现有列表中")
            self.record_sender(sender)
            await Messager.send_notice("success",f"{sender} 成功点播 av{aid}")
            return
        # 判断是否达到播放标准
        checked_1 , checked_2 = await self.judge_by_aid(aid)
        if(not checked_1):
            logging.info(f"av{aid} 未达准入标准，{sender} 点播失败！")
            await Messager.send_notice("error",f"av{aid} 未达准入标准，{sender} 点播失败！")
            return
        path = await BiliUtils.get_video(aid)
        self.now_list.append(aid)
        if(checked_2):
            self.aid_set.add(aid)
            await self.add_to_fav(aid)
            logging.info(f"{aid} 被添加至双列表中")
        self.record_sender(sender)
        await Messager.send_notice("success",f"{sender} 成功点播 av{aid}")

    async def add_to_fav(self,aid: int):
        '''添加至收藏夹'''
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
                if vid == info["aid"]:
                    info_list.append(info)
                    find_flag = True
                    break
            if(not find_flag):
                sinfo = {
                    "aid": vid,
                    "title": await BiliUtils.get_title(vid)
                }
                info_list.append(sinfo)
        self.now_list_info = info_list

def find_latest_log(dir):
    list = os.listdir(dir)
    list.sort(key=lambda fn: os.path.getmtime(dir+fn) if not os.path.isdir(dir+fn) else 0)
    return list[-1]

async def running():
    favorites = os.getenv("FAVORITES", "").split(",")
    log_dir = os.getenv("LOG_DIR", "")

    BILI_PLAY_LIST = BiliPlayList(favorites)
    PLAYER = Player()

    loop = asyncio.get_event_loop()
    loop.create_task(BILI_PLAY_LIST.update_id_list())

    last_check_time = time.perf_counter()
    wait_time = 0
    delta_time = 0

    log_name = find_latest_log(log_dir)
    log_file = open(log_dir + log_name,"r",encoding="utf-8-sig")
    line = log_file.readline()
    while(line):
        line = log_file.readline()

    while(True):
        await asyncio.sleep(1)
        delta_time = time.perf_counter() - last_check_time

        new_log_name = find_latest_log(log_dir)
        if(new_log_name != log_name):
            log_file.close()
            log_name = new_log_name
            log_file = open(log_dir + log_name,"r",encoding="utf-8-sig")

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
                        vid_id = vid_id.replace("\n","")
                        aid = await BiliUtils.format_id(vid_id)
                        if(aid <= 0):
                            continue
                        loop.create_task(BILI_PLAY_LIST.add(aid,sender))
                        await BILI_PLAY_LIST.update_now_playlist_info()
                        await Messager.send_playlist(BILI_PLAY_LIST.now_list_info)

                if(new_damaku[0:2]) == "烟花":
                    ids = new_damaku.replace("烟花","").replace(" ","").replace("\n","")
                    try:
                        fire_num = int(ids)
                        if(fire_num > 100):
                            fire_num = 1
                    except:
                        fire_num = 1
                    await Messager.send_firework(fire_num,sender)

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
    aiohttp.web.run_app(app, host='127.0.0.1', port=int(os.getenv("PORT", "8080")))

def check_dir():
    """
    检查文件夹是否齐全，否则就新建
    """
    dirpaths = ["video","cookie","option"]
    for dirpath in dirpaths:
        if not os.path.exists(dirpath):
            logging.warning(f"文件夹不齐全，新建了 {dirpath} 文件夹")
            os.mkdir(dirpath)

    if not os.path.exists("./option/blacklist.csv"):
        # 预先黑名单
        with open(
            "option/blacklist.csv", "w", encoding="utf-8-sig", newline=""
        ) as blackfile:
            header = ["aid", "title"]
            blackInfo = csv.DictWriter(blackfile, header)
            blackInfo.writeheader()

if __name__ == '__main__':
    check_dir()
    loop = asyncio.get_event_loop()
    loop.create_task(running())
    thread = threading.Thread(target=messaging)
    thread.start()
    loop.run_forever()