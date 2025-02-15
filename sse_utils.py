import asyncio
import json
from aiohttp import web

from bili_utils import BiliUtils

class Messager:
    response_list: list[web.StreamResponse] = []

    @classmethod
    async def sse_handler(self,request):
        response: web.StreamResponse = web.StreamResponse(
            status = 200,
            reason='OK',
            headers={
                'Content-Type': 'text/event-stream',
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive',
            }
        )

        await response.prepare(request)

        self.response_list.append(response)

        while(True):
            await asyncio.sleep(10)

        return response
    
    @classmethod
    async def send(self,data: dict):
        '''
        发送信息给 SSE 客户端
        '''
        jsoned_data = json.dumps(data)
        jsoned_data = "data:" + jsoned_data + "\n\n"
        for response in self.response_list:
            try:
                await response.write(jsoned_data.encode("utf-8"))
            except:
                try:
                    await response.write(jsoned_data.encode("utf-8"))
                except:
                    self.response_list.remove(response)
        # await asyncio.sleep(0.1)
    
    @classmethod
    async def send_notice(self,state: str,message: str,sender: str = "无名氏"):
        '''
        发送通知信息
        '''
        data = {
            "type": "notice",
            "data": {
                "state": state,
                "message": message,
                "sender": sender
            }
        }
        await self.send(data)

    @classmethod
    async def send_playlist(self,playlist: list):
        '''
        发送新播放列表
        '''
        data = {
            "type": "playlist",
            "data": {
                "playlist": playlist
            }
        }
        await self.send(data)
    
    @classmethod
    async def send_play_info(self,aid: int,sender: str = "无人点播"):
        '''
        发送作品信息
        '''
        infoed = await BiliUtils.get_info(aid)
        infoed.update({"sender": sender})
        data = {
            "type": "playinfo",
            "data": infoed
        }
        await self.send(data)

    @classmethod
    async def send_firework(self,num: int = 1,sender: str = "无名氏"):
        '''
        发送放烟花信息
        '''
        data = {
            "type": "firework",
            "data": {
                "sender": sender,
                "num": num
            }
        }
        await self.send(data)
