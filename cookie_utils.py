import asyncio
import logging
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service

class BrowserCookier:
    async def pull_new_cookie():
        final_string = ""
        try:
            try_times = 0

            while(len(final_string) == 0 and try_times < 15):      
                service = Service()

                options = webdriver.EdgeOptions()

                options.add_argument("--user-data-dir=" + os.getenv("BROWSER_DIR",""))

                # 禁用自动化提示
                options.add_experimental_option("useAutomationExtension", False)
                options.add_experimental_option("excludeSwitches", ["enable-automation"])

                browser = webdriver.Edge(service=service, options=options)

                await asyncio.sleep(2)

                browser.get("https://www.bilibili.com/")
                
                await asyncio.sleep(5)

                cookies = browser.get_cookies()
                for cookie in cookies:
                    if(cookie['domain'] == ".bilibili.com"):
                        final_string += f"{cookie['name']}={cookie['value']};"
                try_times += 1

                browser.close()
                browser.quit()
        except Exception as e:
            logging.error(f"获取 Cookie 时遇到了错误！错误类型为 {e}")


        if(len(final_string) != 0):
            logging.info("获取新 Cookie 成功, 已写入")
            with open("./cookie/cookie.txt", "w") as file:
                file.write(final_string)
        else:
            logging.warning("未能获取新 Cookie, 保持先前 Cookie")