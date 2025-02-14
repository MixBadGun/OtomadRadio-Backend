import asyncio
import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service

class BrowserCookier:
    async def pull_new_cookie():
        service = Service()

        options = webdriver.EdgeOptions()

        options.add_argument("--user-data-dir=" + os.getenv("BROWSER_DIR",""))

        # 禁用自动化提示
        options.add_experimental_option("useAutomationExtension", False)
        options.add_experimental_option("excludeSwitches", ["enable-automation"])

        browser = webdriver.Edge(service=service, options=options)

        browser.get("https://www.bilibili.com")

        await asyncio.sleep(10)

        final_string = ""

        cookies = browser.get_cookies()
        for cookie in cookies:
            if(cookie['domain'] == ".bilibili.com"):
                final_string += f"{cookie['name']}={cookie['value']};"

        with open("./cookie/cookie.txt", "w") as file:
            file.write(final_string)

        browser.close()