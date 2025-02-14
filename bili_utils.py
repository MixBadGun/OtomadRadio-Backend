import asyncio
import os
import logging
import subprocess

import aiohttp

headers = {
    "Accept": "*/*",
    # 'Cookie': raw_cookie,
    "Referer": "https://www.bilibili.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/61.0.3163.79 Safari/537.36 Maxthon/5.0",
}

class BiliUtils:
    async def get_video(aid: int, part=1, cid=None) -> str:
        d_time = 0
        exec = "./lux"
        command = []
        if part > 1:
            p_src = f"?p={part}"
        else:
            p_src = ""
        if os.path.exists(f"./cookie/cookie.txt"):
            command.append("-c")
            command.append("./cookie/cookie.txt")
        if os.path.exists(f"./video/{aid}.mp4"):
            logging.info(f"av{aid} 视频已经存在")
            return f"./video/{aid}.mp4"
        command += ["-o", "./video", "-O", str(aid), f"av{aid}{p_src}"]
        while not os.path.exists(f"./video/{aid}.mp4"):
            d_time += 1
            if d_time <= 5:
                logging.info(f"第 {d_time} 次下载 av{aid} 视频...")
                process = await asyncio.create_subprocess_exec(exec,*command)
                await process.wait()
            # 备用 yt-dlp
            if d_time > 5:
                logging.error(f"av{aid} 下载失败，请手动处理！")
                raise Exception("视频下载失败")
        logging.info(f"av{aid} 视频下载完成")
        return f"./video/{aid}.mp4"
    
    async def format_id(id: str) -> int:
        if(id[0:2] == "av" or id[0:2] == "AV"):
            try:
                return int(id[2:])
            except:
                return -1
        if(id[0:2] == "BV"):
            async with aiohttp.ClientSession() as session:
                url = "https://api.bilibili.com/x/web-interface/view"
                try:
                    async with session.get(url, params={"bvid": id}, headers=headers) as response:
                        result = await response.json()
                        return result["data"]["aid"]
                except:
                    return -1
        return -1
    
    async def get_title(aid: int):
        async with aiohttp.ClientSession() as session:
                url = "https://api.bilibili.com/x/web-interface/view"
                try:
                    async with session.get(url, params={"aid": aid}, headers=headers) as response:
                        result = await response.json()
                        return result["data"]["title"]
                except:
                    return "???"
    
    async def get_info(aid: int):
        async with aiohttp.ClientSession() as session:
                url = "https://api.bilibili.com/x/web-interface/view"
                try:
                    async with session.get(url, params={"aid": aid}, headers=headers) as response:
                        result = await response.json()
                        return result
                except:
                    logging.warning(f"{aid} 信息获取失败！")
                    return {'code': -1, 'data': {}}
                
    async def get_tag(aid: int):
        async with aiohttp.ClientSession() as session:
                url = "https://api.bilibili.com/x/tag/archive/tags"
                try:
                    tag_list = []
                    async with session.get(url, params={"aid": aid}, headers=headers) as response:
                        result = await response.json()
                        for tag in result["data"]:
                            tag_list.append(tag["tag_name"])
                        return tag_list
                except:
                    logging.warning(f"{aid} TAG 获取失败！")
                    return []
    
    async def get_user_level(uid: int):
        async with aiohttp.ClientSession() as session:
                url = "https://api.bilibili.com/x/web-interface/card"
                try:
                    async with session.get(url, params={"mid": uid}, headers=headers) as response:
                        result = await response.json()
                        return result["data"]["card"]["level_info"]["current_level"]
                except:
                    logging.warning("用户信息获取失败！")
                    return 1