from cryptography.fernet import Fernet
try:
    import ujson as json
except ImportError:
    import json
import time, re, base64, random as rnd
from aiohttp import ClientSession
from asyncio import create_task, gather, run, sleep
from Utils import logs
import config


CIPHER = Fernet(config.encode_key)
API_KEY = config.server_key_api


BASE_URL_SERVER = config.url_server
BASE_URL_LOCAL = f'http://localhost:{config.port}/'


class Client:
    def __init__(self, base_url, api_key, _cipher):
        self.base_url = base_url
        self.api_key = api_key
        self.cipher = _cipher

    def dec(self, resp: str):
        resp = json.loads(resp)
        for i in ['response', 'log', 'error']:
            res = resp.get(i, '')
            if res:
                a = self.cipher.decrypt(res.encode())
                try:
                    s = json.loads(a.decode())
                    return i, s
                except:
                    return i, a.decode()

        return '', ''

    async def GET(self, url, params=None) -> (str, str):
        param = {'key': self.api_key}
        if params:
            param.update(params)

        async with ClientSession() as session:
            async with await session.get(self.base_url + url, params=param, timeout=30) as res:
                response = await res.text()

        return self.dec(response)

    async def POST(self, url, params=None, data=None):
        param = {'key': self.api_key}
        if params:
            param.update(params)

        async with ClientSession() as session:
            for _ in range(10):
                try:
                    async with await session.post(self.base_url + url,
                                                  params=param,
                                                  data=data,
                                                  timeout=30
                                                  ) as res:
                        response = await res.text()
                        break

                except TimeoutError:
                    pass

        return self.dec(response)

    async def get_list_akk(self):
        _, accounts = await self.GET('action/list')
        for j, i in enumerate(accounts):
            print(f'[{j + 1}]', f'??????????: {i[0]}, id: {i[1]}, ??????: {i[2]}')
        return accounts

    async def get_loop(self):
        _, data = await self.GET('getlooptask')
        for i in data:
            print(i)

    async def action(self, params: dict, timer: int = 0, wait=5):
        if not params.get('method') or not params.get('login'):
            print('error params')
            return '', ''

        login = params['login']
        print(login, 'action start', params)

        data = json.dumps(params)
        data = self.cipher.encrypt(data.encode()).decode()

        if wait:
            await sleep(wait)

        event, result = await self.POST('action', data=data)

        if timer and event != 'error':
            print(f'{login} ???????????? ?????????????? ?????????????? ?? ???????????? ?? ?????????? ?????????????????? ?????????? {timer} ????????????')
            return True

        if event == 'error':
            print(login, 'error', result)
            logs.client_error(f'{login} {result}')
            return {'error': result}

        name = str(result)

        for _ in range(90):
            await sleep(5)
            event, result = await self.GET('action/check', {'name': name})

            if event == 'error':
                print(login, 'error', result)
                logs.client_error(f'{login} {result}')
                return {'error': result}

            if result != name and event == 'response':
                print(login, 'vk_res =', result)
                return {'response': result}

        return {'error': 'not server response'}


def check_link_post(link=''):
    if not link:
        link = input("???????????? ???? ????????\n"
                     ">>> ").lower()
    post = re.findall(r'[(wall|photo|video)]+-*\d+?_\d+', link)
    reply = re.findall(r'reply=\d+', link)
    if reply and post:
        p = re.findall(r'-*\d+', post[0].split('_')[0])
        r = re.findall(r'\d+', reply[0])
        if p and r:
            return f'wall_reply{p[0]}_{r[0]}'.strip()

    if not post:
        raise Exception('???????????????????????? ???????????? ???? ????????!!!')
    return post[0].strip()


def check_link_group(link=''):
    if not link:
        link = input("???????????? ???? ????????????\n"
                     ">>> ").lower()

    post = re.findall(r'(club\d+|public\d+)', link)
    if not post:
        raise Exception(f'???????????????????????? ???????????? ???? ????????????!!! {link}')

    p = re.findall(r'[\d+?]+', post[0])
    if not p:
        raise Exception(f'???????????????????????? ???????????? ???? ????????????!!!  {link}')

    return p[0].strip()


def check_link_user(link=''):
    if not link:
        link = input("???????????? ???? ??????????\n"
                     ">>> ").lower()

    post = re.findall(r'[\d+?]+', link)
    if not post:
        raise Exception('???????????????????????? ???????????? ???? ??????????!!!')
    return post[0].strip()


def choose_login(akk):
    try:
        index = int(input('>>> '))
    except:
        raise Exception('???????????? ???????? ??????????!')

    if index > len(akk):
        raise Exception(f'???????????????? ?? ?????????? [{index}] ?????????????? ????????...')

    if index == 0:
        return [i[0] for i in akk]

    else:
        return [akk[index - 1][0]]


if input('[0] SERVER\n[1] LOCAL\n>>> ') == '0':
    client = Client(BASE_URL_SERVER, API_KEY, CIPHER)
else:
    client = Client(BASE_URL_LOCAL, API_KEY, CIPHER)


async def choose_ation():
    a = input("[0] ???????? ?????????? ???? ??????????\n"
              "[1] ???????????? ?????????? ???? ??????????\n"
              "[2] ?????????????????????? ???? ????????????\n"
              "[3] ?????????????????? ??????????????????\n"
              "[4] ?????????????????????? ?????????? ???? ??????????\n"
              ">>> ")

    act = False
    method = ''
    param = {}
    stop = False

    if a == '0':
        method = 'methods.like'
        param = {"post_id": check_link_post()}

    elif a == '1':
        method = 'methods.repost'
        msg = input('message >>> ')
        param = {"post_id": check_link_post(), 'msg': msg}

    elif a == '2':
        method = 'methods.subscribe'
        param = {"owner_id": check_link_group()}

    elif a == '3':
        method = 'methods.send'
        param = {'user_id': check_link_user(), 'msg': input('message >>> ')}

    elif a == '4':
        method = 'methods.comment_post'
        param = {'post_id': check_link_post(), 'msg': input('message >>> ')}

    elif a == '5':
        method = 'methods.post_wall'
        param = {'owner_id': '-174587092',
                 'msg': '???????????? ??????!',
                 'atta': [['photo', '449046_457239171']]}

    elif a == '6':
        method = 'upload.video.add'
        param = {'owner_id': '-174587092', 'path': 'C:/py/_vk/master/1.mp4', 'name': 'video',
                 'disc': 'dict', 'act_link': 'https://vk.com/club174587092'}

    elif a == '7':
        act = True
        method = 'random_like_feed'
        param = {'target_post_id': check_link_post()}

    elif a == '8':
        await client.get_loop()
        stop = True

    elif a == '9':
        method = 'methods.add_friend'
        param = {'user_id': check_link_user()}

    elif a == '10':
        method = 'check'
        param = {}

    else:
        exit('lox')

    try:
        timer = int(input('?????????????????? ?????????? ????????????'
                          '[0] ??????\n'
                          '>>> '))
    except:
        timer = 0

    return method, param, act, stop, timer


async def main():
    while True:
        print(f'start on = {client.base_url}')

        print('?????????????????? ????????????????:')
        akk = await client.get_list_akk()
        print('[0] ??????...')

        login_all = choose_login(akk)

        method, param, act, stop, timer = await choose_ation()
        if stop:
            continue

        tasks = []
        for login in login_all:
            params = {
                'login': login,
                'method': method,
                'timer': timer,
                'params': param,
                'act': act
            }
            t = 5 #int(rnd.random() * 300 + 60)
            tasks.append(create_task(client.action(params, timer, t)))

        for task in await gather(*tasks):
            print(task)

        print('END')
        time.sleep(3)


if __name__ == '__main__':
    run(main())

