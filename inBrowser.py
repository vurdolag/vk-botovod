import random
from threading import Thread
from account import account
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver import ActionChains
from time import sleep, time
import random as rnd
import re
import zipfile
from Utils import sqlbd, logs
import json


class Selen:
    def __init__(self, login='', password='', user_agent='', proxy='', target: list = None,
                 headless=False, set_proxy=True):
        self.login = login
        self.password = password
        self.user_agent = user_agent
        self.proxy = proxy
        self.target = target
        self.driver = self.draiv(headless, set_proxy)
        self.max_like = 10
        self.like_count = 0

    def myprint(self, *args, **kwargs):
        print('>>>', self.login, *args, **kwargs)

    def draiv(self, bool, set_proxy):
        options = webdriver.ChromeOptions()
        if set_proxy:
            proxy = re.findall(r'(?<=@).*?(?=:)', self.proxy)[0]
            options.add_extension('proxy/' + proxy + ".zip")
        options.add_argument("user-agent=" + self.user_agent)
        options.add_argument('window-size=1280x900')
        if bool:
            options.add_argument('headless')
            options.add_argument('window-size=1280x900')
        return webdriver.Chrome(chrome_options=options)

    def chek(self):
        self.myprint('check start', end=' ')
        self.driver.get("https://google.com/")
        sleep(3)
        try:
            self.myprint("open cookie")
            with open(f'cookies/{self.login}_.json') as f:
                cookies = json.load(f)

            for key, val in cookies.items():
                cookie = {'name': key, 'value': val}
                self.driver.add_cookie(cookie)

            self.myprint("cookie ok")

        except Exception as ex:
            self.myprint('=======' * 5)
            self.myprint("error open cookie")
            self.myprint(ex)
            self.myprint('=======' * 5)
            self.avtor()

        self.driver.get("https://vk.com/feed")
        self.myprint("check cookie")
        sleep(3)

        if self.driver.current_url != 'https://vk.com/feed':
            self.myprint('enter feed')
            self.driver.get("https://vk.com/feed")
            self.driver.implicitly_wait(2)

        try:
            self.driver.find_element_by_id("index_email")
            self.myprint('error cookie, auth start')
            self.avtor()
        except:
            self.myprint('cookie ok')

    def avtor(self):
        self.myprint("start auth")
        self.driver.get("https://vk.com")
        sleep(3)
        self.driver.find_element_by_id("index_email").send_keys(self.login)
        pwd = self.driver.find_element_by_id("index_pass")
        pwd.send_keys(self.password)
        sleep(3)
        pwd.send_keys(Keys.ENTER)
        sleep(12)
        if self.driver.current_url != "https://vk.com/feed":
            self.myprint('not_auth rep')
            return self.avtor()

        self.myprint('auth ok')

        cook = self.driver.get_cookies()
        cookies = {}
        for i in cook:
            cookies[i['name']] = i['value']

        c = json.dumps(cookies)

        with open(f'cookies/{self.login}_.json', 'w') as f:
            f.write(c)

        self.myprint("cookie save")
        return cook[0]

    def act_PD(self, *args):
        count = rnd.randint(*args[:2])
        self.myprint('P_D', count)
        for _ in range(count):
            try:
                act = ActionChains(self.driver)
                act.send_keys(Keys.PAGE_DOWN).perform()
                self.rand_sleep(0.5)
                e = self.driver.find_element_by_css_selector('#show_more_link')
                if e:
                    act.move_to_element(e).perform()
                    self.rand_sleep(0.5)
                    act.click(e).perform()
                    self.rand_sleep(0.5)
                    print('click show_more_link')
            except:
                pass
        self.myprint('P_D OK')

    def act_esc(self):
        try:
            act = ActionChains(self.driver)
            act.send_keys(Keys.ESCAPE).perform()
            self.rand_sleep(0.3)
        except:
            pass

    def rand(self, count=2):
        return rnd.randint(0, 1000) % count == 0

    def rand_sleep(self, b=0.5, a=1):
        sleep(rnd.random() * a + b)

    def like(self, id_post):
        try:
            act = ActionChains(self.driver)
            e = self.driver.find_element_by_xpath(f"//div[@id='post{id_post}']/div/div[2]/div/div[2]/div/div/a/div")
            act.move_to_element(e).perform()
            self.rand_sleep(1, 3)
            act.click(e).perform()
            self.rand_sleep(1, 3)
            self.myprint('like ok', id_post)
            self.like_count += 1

        except Exception as ex:
            self.myprint('erorr like', ex)

    def move_xpath(self, xpath):
        try:
            act = ActionChains(self.driver)
            e = self.driver.find_element_by_xpath(xpath)
            act.move_to_element(e).perform()
            self.rand_sleep(0.3)
        except Exception as ex:
            self.myprint('move xpath error', ex)

    def move_css(self, css):
        try:
            act = ActionChains(self.driver)
            e = self.driver.find_element_by_css_selector(css)
            act.move_to_element(e).perform()
            self.rand_sleep(0.3)
        except Exception as ex:
            self.myprint('move css error', ex)

    @staticmethod
    def create_proxy_zip(prox: str):
        with open('proxy/background.js') as f:
            text_js = f.read()

        val0, val1 = prox.split('@')

        username, password = val0.split(':')
        proxy, port = val1.split(':')

        result_text_js = text_js.replace('%proxy%', proxy).replace('%port%', port)
        result_text_js = result_text_js.replace('%username%', username).replace('%password%', password)

        with open('proxy/temp/background.js', 'w') as f:
            f.write(result_text_js)

        a = zipfile.ZipFile(f'proxy/{proxy}.zip', 'w')

        a.write('proxy/temp/manifest.json', 'manifest.json')
        a.write('proxy/temp/background.js', 'background.js')
        a.close()


def mainapp(go):
    try:
        proxy = go.get('proxy', '')
        if proxy:
            prox = re.findall(r'(?<=@).*?(?=:)', proxy)[0]
            try:
                with open('proxy/' + prox + ".zip") as f:
                    proxy = f.read()

            except:
                Selen.create_proxy_zip(proxy)

        selen = Selen(go['login'], go['password'], go['user-agent'], go['proxy'],
                      [], set_proxy=True if proxy else False)
        selen.chek()
        sleep(3600*2)
        selen.myprint('END ITER')
        selen.driver.close()
        selen.myprint('--prog ok--')
    except:
        logs()
        print('err')


def worker():
    print('open all akks start')
    random.shuffle(account)
    for i in account:
        Thread(target=mainapp, args=(i,)).start()
        sleep(5)
        print('next')
    print('open all akks end')


if __name__ == '__main__':
    bd = sqlbd('akkinfo')
    while True:
        print('##### AKKS #####')
        for ind, akk in enumerate(account):
            ind += 1
            try:
                info = bd.get(akk['login'], sync=True)
            except:
                info = []

            if info:
                info = info[0]
                i = f'login: {info[0]}, id: {info[1]}, name: {info[2]}'
            else:
                i = f"login: {akk['login']}"
            print(f'[{ind}]', i)
        print('################')
        print(f'open? 1 - {len(account)} or [0] for all')

        try:
            inp = int(input('>>> ').lower())

            if inp == 0:
                worker()

            else:
                a = account[inp-1]
                print(f'akk "{a["login"]}" start open\n')
                Thread(target=mainapp, args=(a,)).start()

        except Exception as ex:
            print('ERROR =>', ex, '\n')

        sleep(2)

