import lxml.html
from time import time, time_ns
import re

try:
    import ujson as json
except ImportError:
    import json
import random as rnd
from aiohttp import ClientSession, CookieJar, client_exceptions as ex, FormData
from asyncio import sleep, create_task, TimeoutError, CancelledError
import io
import os
from base64 import b64decode

from Utils import (Global, save_info, rnd_sleep, sleeper, rand, cover, time_buffer,
                   is_random, Response, VkApi, logs, Cookie, VkMethodsError,
                   SmsActivate, convert_base, random_password)
import RegExp as RE
import config
from config import Url
from typing import List, Dict, Coroutine, Union, Tuple, Optional

FROM_FEED = 0
FROM_WALL = 1

_api = VkApi()


def post_twik(func):
    def wrapper(self, url: str, params, ref=None, data=None):
        if isinstance(params, dict):
            add_url = params.get('act')
            if add_url:
                url += f'?act={add_url}'
        return func(self, url, params, ref, data)

    return wrapper


class VkSession:
    __slots__ = ('_session', 'heads', 'proxy', 'login', 'password', 'my_id', 'my_name',
                 'use_reaction', 'api', 'all_session', 'methods', 'upload', 'is_auth',
                 'cookie', '_two_factor_auth_call', 'last_check')

    def __init__(self, login: str = '', password: str = '', headers: str = '',
                 proxy: str = '', account: dict = None):
        self._session: Optional[ClientSession] = None
        self.heads: str = headers
        self.proxy: str = self._get_proxy(proxy)
        self.login: str = login
        self.password: str = password
        self.my_id: str = ''
        self.my_name: str = ''
        self.api = _api
        self.is_auth: bool = False

        self.cookie: Optional[Cookie] = None

        self._account_pars(account)

        self.upload: Upload = Upload(self)
        self.methods: Methods = Methods(self)
        self.all_session: Dict[str, VkSession] = Global.AllVkSession
        self._two_factor_auth_call = None
        self.use_reaction: bool = False

    def _account_pars(self, akk):
        if akk:
            self.login = akk["login"]
            self.password = akk["password"]
            self.heads = akk["user-agent"]
            self.proxy = self._get_proxy(akk["proxy"])

    async def auth(self, check: bool = True, two_factor_auth_call=None) -> bool:
        self._two_factor_auth_call = two_factor_auth_call

        if not await self._check_proxy():
            self.print('Proxy error', self.proxy)
            self.logger(f'Proxy {self.proxy} не работает...')
            return False

        self.api.start_loop()

        self.all_session[self.login] = self
        self._session = ClientSession(cookie_jar=CookieJar(unsafe=True))
        self.cookie = Cookie(self._session, f'{config.path_cookies}{self.login}.json')
        self.cookie.load_and_set()

        c = False
        if check:
            c = await self.check()
            if c:
                self.is_auth = True
                save_info(self)

        self.print('AUTH ->', c)

        return c

    @staticmethod
    def _get_headers(headers: str = '', req_type: str = 'POST', ref: Dict[str, str] = None
                     ) -> Dict[str, str]:
        head = {
            'User-Agent': headers,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ru-ru,ru;q=0.8,en-us;q=0.5,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'DNT': '1',
            'content-type': 'application/x-www-form-urlencoded',
            'x-requested-with': 'XMLHttpRequest'}

        if req_type == 'GET':
            del head['x-requested-with'], head['content-type']

        if ref:
            head.update(ref)

        return head

    @staticmethod
    def _get_proxy(proxy: str = '') -> str:
        if proxy:
            return proxy if 'http://' in proxy else f'http://{proxy}'
        return proxy

    async def _check_proxy(self):
        try:
            async with ClientSession() as session:
                async with await session.post('https://google.com',
                                              timeout=20,
                                              proxy=self.proxy) as res:
                    await res.read()
            return True

        except:
            return False

    @cover
    async def _two_factor_auth(self) -> bool:
        while True:
            res = await self.GET('https://vk.com//login?act=authcheck')
            if self._two_factor_auth_call is None:
                code = input(f'{self.login} Enter code <<< ')
            else:
                code = self._two_factor_auth_call()

            await sleeper(1, 9)

            _hash = res.find_first(RE.two_factor_auth_hash)
            params = {
                'act': 'a_authcheck_code',
                'al': 1,
                'code': code,
                'hash': _hash,
                'remember': 1
            }
            res = await self.POST('https://vk.com/al_login.php', params)

            if '"payload":[0' in res:
                self.print('Неверный код!')
                await sleeper(0.3, 1)
            else:
                break

        assert r'{"payload":["4",["\"\\\/login.php?act=slogin' in res, 'two factor auth error'

        await sleeper(3, 9)
        if await self.check():
            self.cookie.save()
            return True

        else:
            return False

    @cover
    async def _enter_vk(self) -> bool:
        self.print('Авторизация...')
        await sleeper(3, 10)
        data = await self.GET('https://vk.com/')
        data.check()

        page = lxml.html.fromstring(data.body)
        form = None
        for form in page.forms:
            try:
                form.fields['email'] = self.login
                form.fields['pass'] = self.password
                break

            except KeyError:
                pass

        assert not form is None
        params = dict(form.form_values())
        assert params

        await sleeper(3, 16)

        resp = await self.POST(form.action, params)
        if not resp.body:
            return False

        await sleeper(1, 6)

        self.cookie.save()

        if 'parent.onLoginReCaptcha' in resp:
            self.print('Требуется ввод капчи!')
            return False

        elif 'parent.onLoginDone' in resp:
            return await self.check()

        elif 'parent.onLoginFailed' in resp:
            return await self.check()

        elif 'act=authcheck' in resp:
            return await self._two_factor_auth()

        else:
            self.print('Неизвестное поведение при авторизации!')
            return False

    async def _req(self, func, url, params=None, data=None, resp_type='POST', ref=None):
        for _ in range(3):
            try:
                async with await func(url, data=params if data is None else data,
                                      headers=self._get_headers(self.heads, resp_type, ref=ref),
                                      timeout=60, proxy=self.proxy) as res:
                    assert res.status == 200
                    response = await res.text()

                return Response(response, url=url, params=params, resp_type=resp_type, session=self)

            except (ex.ClientProxyConnectionError, ex.ClientHttpProxyError) as e:
                logs.get_error(f'ProxyError {self.proxy} url = {url}, {e}')
                self.methods.error_count += 1
                await sleep(60)

            except (ex.ServerTimeoutError, TimeoutError) as e:
                logs.get_error(f'TimeoutError url = {url}, {e}')
                self.methods.error_count += 1
                await sleep(60)

            except CancelledError as e:
                logs.get_error(f'CancelledError url = {url}, {e}')
                await sleep(60)

            except AssertionError:
                logs.get_error(f'Status code != 200, url = {url}')
                await sleep(60)

            except:
                self.methods.error_count += 1
                logs.get_error()
                await sleep(60)

        return Response(url=url, params=params, resp_type=resp_type, session=self)

    # @async_timer
    async def GET(self, url: str) -> Response:
        return await self._req(self._session.get, url, resp_type='GET')

    # @async_timer
    @post_twik
    async def POST(self, url: str, params: Dict[str, Union[int, str]], ref: dict = None,
                   data: FormData = None) -> Response:
        return await self._req(self._session.post, url, params=params, data=data, ref=ref)

    def _get_user_name(self, response: Response):
        if not self.my_name:
            name = response.find(RE.check_name)
            if name:
                self.my_name = name[0].strip()
            else:
                self.print("error get name")

    async def _get_user_id_and_check_auth(self, response: Response) -> bool:
        if not self.my_id or self.my_id == '0':
            user_id = response.find_first(RE.check_user_id)
            self.my_id = user_id.strip() if user_id else '0'

        if self.my_id == "0":
            self.logger('Требуется авторизация...')
            return await self._enter_vk()

        return True

    async def check(self) -> bool:
        try:
            response = await self.GET('https://vk.com/feed')

            if not response:
                self.print("not check data")
                return False

            if not await self._get_user_id_and_check_auth(response):
                return False

            if not self.methods.check_status(response):
                return False

            self._get_user_name(response)

            if 'data-reaction-hash' in response:
                self.use_reaction = True

            return True

        except:
            logs()
            self.methods.working = self.is_auth = False
            return False

    def print(self, log_message: str, *args):
        s = f'{self.login:<12} {self.my_name:<15} {self.my_id:<12}'
        print(s, log_message, *args)

    def logger(self, msg, name=''):
        if not name:
            logs.log(f"{self.login} {msg}")
        else:
            logs.log(f"{self.login} {self.my_name} {self.my_id} {msg}", name)


from ObjClass import Post, Event, Like, Group, User
from HtmlParser import wall_post_parser, feed_post_parser


class Methods:
    __slots__ = ('already_view_posts', 'vk', '_hash_send_msg', '_hash_del_friends', 'log',
                 'ok', 'post_from_target_group', 'feed_session', 'meta_view', 'print',
                 'hash_view_post', 'status', 'error_count', 'working', 'list_tasks',
                 'ignored_user_send', 'buff_send', '_time_hash_del_friends')

    def __init__(self, vk: VkSession):
        self.vk: VkSession = vk
        self._hash_send_msg: Dict[str, Tuple[str, int]] = {}  # {user_id: (hash time), ...}
        self._hash_del_friends: str = ''
        self._time_hash_del_friends: int = 0

        self.post_from_target_group: List[str] = []
        self.feed_session: str = ''
        self.hash_view_post: str = ''
        self.error_count: int = 0
        self.working: bool = True
        self.list_tasks: list = []
        self.already_view_posts: List[str] = []
        self.meta_view: int = rnd.randint(255, 925)
        self.ignored_user_send = set()
        self.buff_send = {}

        self.print = vk.print
        self.log = vk.logger

        self.add(self.error_checker())

    def _buff_sleep(self, min_time, max_time, key='') -> Coroutine:
        return time_buffer(f'{key}{self.vk.login}', rand(max_time - min_time, min_time))

    @cover
    async def simple_method(self, url: str, params: dict, msg_error: str) -> bool:
        response = await self.vk.POST(url, params)
        response.check(msg_error)
        return True

    @cover
    async def error_checker(self):
        while self.working:
            await sleep(180)

            if not self.vk.cookie is None:
                self.vk.cookie.save()

            [self.list_tasks.remove(task) for task in self.list_tasks if task.done()]

            max_err_count = 20
            msg_err = f'{self.vk.login} Слишком много ошибок, > {max_err_count}'

            if self.error_count > max_err_count:
                await self.vk.api.send_message(config.admin_alarm, msg_err)
                if not await self.vk.check():
                    await self.vk.api.send_message(config.admin_alarm, msg_err + ' завершение работы')
                    self.log('Слишком много ошибок завершение работы')
                    self.working = False
                    [task.cancel() for task in self.list_tasks]

    def add(self, task: Coroutine):
        self.list_tasks.append(create_task(task))
        [self.list_tasks.remove(task) for task in self.list_tasks if task.done()]

    def check_status(self, res: Response):
        """
        Проверка не заблокирован ли аккаунт, если да отправляет сообщение админу
        :param res: ответ вк
        :return: bool
        """
        if 'id="index_login_form"' in res and res.url != 'https://vk.com/':
            self.log(f'Аккаунт не авторизован!!!')
            self.vk.is_auth = self.working = False
            return False

        if 'login?act=blocked' in res or 'blockedHash' in res:
            self.vk.is_auth = self.working = False
            self.add(self.vk.api.send_message(
                config.admin_alarm,
                f'{self.vk.login} {self.vk.my_name} аккаунт заблокирован!!!'))
            self.log(f'Аккаунт заблокирован!!!')
            self.print("AKK BLOCKED!!!")
            # self.add(self.unblock())
            return False
        else:
            self.vk.is_auth = True
            return True

    async def long_poll(self, event_processing):
        """
        Для работы сообщений
        :param event_processing: функция обработчик сообщений
        """
        while self.working:
            self.print('long poll start')

            if not await self.vk.check():
                break

            try:
                params = {
                    'act': 'a_get_key',
                    'al': 1,
                    'gid': 0,
                    'im_v': 3,
                    'uid': self.vk.my_id}
                response = await self.vk.POST(Url.im, params)
                res = response.check('error get long poll key').json()["payload"][1]

                while self.working:
                    url = (f'{res[1]}/{res[2]}?act=a_check&key={res[0]}&'
                           f'mode=1226&ts={res[3]}version=14&wait=25')

                    response = await self.vk.GET(url)
                    new_event = response.check('error get response from long poll').json()

                    if new_event.get('failed'):
                        break

                    res[3] = new_event['ts']
                    updates = new_event.get('updates')

                    if updates:
                        for update in updates:
                            event = Event(self.vk.my_id).pars(update, vk=self.vk)
                            if not event.empty:
                                self.add(event_processing(event))

                    self.error_count = 0

                    await sleep(0.3)

            except (KeyError, ValueError, IndexError):
                self.error_count += 1
                self.print('long poll error')
                await sleep(30)

            except:
                logs()
                self.error_count += 1
                self.print('long poll error')
                await sleep(180)

    async def long_poll_feed(self, event_processing):
        """
        Для работы с уведомлениями и событиями вк
        :param event_processing: Оброботчик уведомлений
        """
        await rnd_sleep()
        response = None
        while self.working:
            try:
                self.print('long poll feed start')
                response = await self.vk.GET(f'https://vk.com/id{self.vk.my_id}')
                response.check()

                key1 = response.find_first(RE.long_poll_feed_key1)
                # key2 = response.find_first(RE.long_poll_feed_key2)
                ts1 = response.find_first(RE.long_poll_feed_ts1)
                # ts2 = response.find_first(RE.long_poll_feed_ts2)

                server_url = response.find_first(RE.long_poll_feed_server_url)
                server_url = RE.two_slash.sub('', server_url)
                fin_key = key1  # + key2  # + key3['key']

                assert server_url and fin_key and ts1

                while self.working:
                    ts = f'{ts1}'
                    params = {
                        'act': 'a_check',
                        'id': self.vk.my_id,
                        'key': fin_key,
                        'ts': ts,
                        'wait': 25
                    }
                    response = await self.vk.POST(server_url, params)
                    js = response.json()

                    if js.get('failed'):
                        raise IndexError

                    ts1 = js['ts']

                    updates = js['events']

                    if updates:
                        for update in updates:
                            event = Event(self.vk.my_id).pars(update, True, vk=self.vk)
                            if not event.empty:
                                self.add(event_processing(event))

                    self.error_count = 0

            except (IndexError, ValueError, KeyError):
                self.error_count += 1
                self.print('feed error')
                if not response is None:
                    self.log(response.body, name='err_feed')

                await sleep(30)

            except:
                self.error_count += 1
                logs()
                await sleep(180)

    async def set_online(self) -> bool:
        return await self.simple_method(Url.im,
                                        {'act': 'a_onlines', 'al': 1,  'peer': ''},
                                        'error set online')

    @cover
    async def edit_msg(self, user_id, msg: str, attach: List[List[str]],
                       msg_id: int, hash_msg: str = '') -> bool:
        """
        Редактирует сообщение
        :param user_id:
        :param msg: новое сообщение
        :param attach: новое вложение
        :param msg_id:
        :param hash_msg: хеш
        :return:
        """
        params = {
            'act': 'a_edit_message',
            'al': 1,
            'gid': 0,
            'hash': await self._get_hash_send(user_id, hash_msg),
            'id': msg_id,
            'im_v': 3,
            'media': attach if attach else '',
            'msg': msg,
            'peerId': user_id,
        }
        return await self.simple_method(Url.im, params, 'error edit message')

    @cover
    async def read_msg(self, user_id, msg_id: str, hash_msg: str = '') -> bool:
        params = {'act': 'a_mark_read',
                  'al': 1,
                  'gid': 0,
                  'hash': await self._get_hash_send(user_id, hash_msg),
                  'ids[0]': msg_id,
                  'im_v': 3,
                  'peer': user_id}
        return await self.simple_method(Url.im, params, 'error read msg')

    @cover
    async def set_typing(self, user_id, hash_msg: str = '') -> bool:
        params = {'act': 'a_activity',
                  'al': '1',
                  'gid': '0',
                  'hash': await self._get_hash_send(user_id, hash_msg),
                  'im_v': '3',
                  'peer': user_id,
                  'type': 'typing'}
        return await self.simple_method(Url.im, params, 'error set typing')

    async def _get_hash_send(self, user_id, _hash_msg='') -> str:
        """
        Получает хеш для работы с сообщениями
        :param user_id:
        :param _hash_msg:
        :return:
        """
        if _hash_msg:
            return _hash_msg

        hash_msg = self._hash_send_msg.get(user_id)

        if not hash_msg or time() - hash_msg[1] > 3600:
            params = {'act': 'a_start',
                      'al': 1,
                      'block': 'true',
                      'gid': 0,
                      'history': 'true',
                      'im_v': 3,
                      'msgid': 'false',
                      'peer': user_id,
                      'prevpeer': 0}
            response = await self.vk.POST(Url.im, params)
            hash_msg = response.check(f'error get hash for send {user_id}').payload()['hash']

            #hash_msg = response.check(f'error get IM').find_first(RE.get_hash_for_send_msg)
            if not hash_msg:
                raise VkMethodsError('not hash send msg', session=self.vk, user_id=user_id)

            self._hash_send_msg[user_id] = (hash_msg, int(time()))
            await sleeper(1, 10)
            return hash_msg

        return hash_msg[0]

    @cover
    async def set_send(self, user_id, msg: str, attachment: List[List[str]], hash_msg: str = ''
                       ) -> dict:
        params = {'act': 'a_send',
                  'al': 1,
                  'entrypoint': 'list_all',
                  'gid': 0,
                  'guid': str(time_ns())[:-4],
                  'hash': await self._get_hash_send(user_id, hash_msg),
                  'im_v': 3,
                  'media': '',
                  'module': 'im',
                  'msg': msg,
                  'random_id': rnd.randint(10000000, 100000000),
                  'to': user_id}
        if attachment:
            params['media'] = ','.join([f'{content[0]}:{content[1]}:undefined' for content in attachment])

        response = await self.vk.POST(Url.im, params)
        return response.check('Error send message').payload()

    def _brok_msg(self, msg: str):
        m = list(msg)
        l = len(m)
        count = int(l / 15) + 1
        s = 'йцукенгшщзхъэждлорпавыфячсмитьбю'
        p = [rnd.randint(0, l) for _ in range(count)]

        if not m:
            return msg

        for i in p:
            try:
                m[i] = rnd.choice(s)
            except IndexError:
                pass

        return ''.join(m)

    async def _send_msg_buffer(self, user_id, timer, time_w=30):
        t = self.buff_send.get(user_id)
        w = (timer, timer * 2) if t is None or time() - t > time_w else (1, 5)
        await self._buff_sleep(*w, 'send')
        self.buff_send[user_id] = time()

    @cover
    async def send(self,
                   user_id, msg: str, attachment: List[List[str]] = None,
                   msg_id: str = '', timer: int = 15, read_msg: bool = True,
                   typing: bool = True, rnd_edit_msg: int = 20
                   ) -> Dict[str, Union[str, int]]:
        try:
            if user_id in self.ignored_user_send:
                raise VkMethodsError('last send ended with error, new send abort',
                                     _locals=locals())

            await self._send_msg_buffer(user_id, timer, 180)

            hash_msg = await self._get_hash_send(user_id)

            if read_msg and msg_id:
                await self.read_msg(user_id, msg_id, hash_msg)
                await sleeper(3, 16)

            if msg or attachment:
                if typing:
                    for _ in range(len(msg) // 15 + 1):
                        await self.set_typing(user_id, hash_msg)
                        await sleeper(5, 10)

                is_edit_msg = is_random(rnd_edit_msg)
                brok_msg = ''
                if is_edit_msg:
                    brok_msg = self._brok_msg(msg)

                send_msg_data = await self.set_send(user_id, brok_msg or msg, attachment, hash_msg)
                if is_edit_msg and send_msg_data:
                    await sleeper(10, 30)
                    await self.edit_msg(user_id, msg, attachment, send_msg_data['msg_id'], hash_msg)

                return send_msg_data

            else:
                raise VkMethodsError('not content for send')

        except VkMethodsError as vk_ex:
            if vk_ex.msg != 'not content for send':
                self.ignored_user_send.add(user_id)
            raise vk_ex.add_session(self.vk)

    @cover
    async def voice_to_text(self, msg_id, user_id):
        resp = await self.vk.GET(f'https://m.vk.com/mail?act=show&peer={user_id}')

        msg = re.findall(f'data-msg="{msg_id}".*?' +
                         r"<div class=\"audio-msg-track__transcriptionText.*?</div>",
                         resp.body, flags=re.DOTALL)

        if not msg:
            return False

        msg = re.findall(r"(?<=\d\">).*?(?=</div>)", msg[0], flags=re.DOTALL)

        return msg[-1].lower().strip() if msg else False

    @cover
    async def subscribe(self, owner_id, _hash: str = '') -> bool:
        group = False

        response = await self.vk.GET(f'https://vk.com/club{owner_id}')
        response.check()

        await self._buff_sleep(3, 15)

        if not _hash:
            _hash = response.find_first(RE.subscribe_enterHash)

        if not _hash:
            _hash = response.find_first(RE.subscribe_groups_enter,
                                        lambda x: RE.word_dig_.findall(x))
            if _hash:
                group = True

        if not _hash:
            raise VkMethodsError('probably already signed', session=self.vk, owner_id=owner_id)

        if group:
            if len(_hash) != 2:
                raise VkMethodsError('hash_group need len == 2', session=self.vk,
                                     hash_group=_hash, owner_id=owner_id)
            params = {
                'act': 'enter',
                'al': '1',
                'gid': owner_id,
                'hash': _hash[1]}
            response = await self.vk.POST(Url.group, params)
            response.check('error set subscribe group')
            if 'Groups.leave(' not in response:
                raise VkMethodsError('Error subscribe group', session=self.vk,
                                     hash_group=_hash, owner_id=owner_id)
        else:
            params = {
                'act': 'a_enter',
                'al': '1',
                'pid': owner_id,
                'hash': _hash}
            await self.simple_method(Url.public, params, 'error set subscribe public')

        self.log(f'Вступил в сообщество: {owner_id}')

        return True

    @cover
    async def leave(self, owner_id, _hash: str = '') -> bool:
        await self._buff_sleep(3, 15)

        if not _hash:
            resp = await self.vk.GET(f'https://vk.com/club{owner_id}')
            _hash = resp.check().find_first(RE.leave_hash)

            await rnd_sleep(5, 3)

            if not _hash:
                _hash = resp.find_first(RE.leave_group,
                                        lambda x: RE.word_dig_.findall(x))
                url = Url.group
                params = {
                    'act': 'leave',
                    'al': '1',
                    'gid': owner_id,
                    'hash': _hash}

            else:
                url = Url.public
                params = {
                    'act': 'a_leave',
                    'al': '1',
                    'pid': owner_id,
                    'hash': _hash}

            if not _hash:
                raise VkMethodsError('probably already left the community',
                                     session=self.vk, owner_id=owner_id)

        else:
            url = Url.group
            params = {
                'act': 'list_leave',
                'al': '1',
                'gid': owner_id,
                'hash': _hash}

        resp = await self.vk.POST(url, params)
        resp.check('error leave group')

        if 'Это закрытая группа' in resp:
            await rnd_sleep(5, 5)
            params = {"act": "list_leave",
                      "al": "1",
                      "confirm": "1",
                      "gid": owner_id,
                      "hash": _hash}
            await self.simple_method(url, params, 'error leave closed group')

        self.log(f'покинул сообщество: {owner_id}')

        return True

    async def get_hash_post(self, id_post: str) -> dict:
        try:
            response = await self.vk.GET(f'https://vk.com/{id_post.replace("_reply", "")}')
            response.check()

            hash_like = [x for x in response.find(RE.get_hash_post_likes) if id_post in x]
            hash_like = RE.word_dig_.findall(hash_like[0]) if hash_like else []

            hash_comment = response.find_first(RE.get_hash_post_comment)

            comment_id_list = response.find(RE.get_hash_post_comment_id_list)

            hash_spam = response.find_first(RE.get_hash_post_spam)
            hash_spam = RE.word_dig_.findall(hash_spam) if hash_spam else []

            return {'like': hash_like, 'comment': hash_comment,
                    'comment_ids': comment_id_list, 'spam': hash_spam}
        except:
            logs()
            return {}

    async def get_info_view(self, id_post: str) -> int:
        """
        Получает количество просмотров поста
        :param id_post:
        :return:
        """
        if RE.like_type.findall(id_post) or 'reply' in id_post:
            return -1
        params = {
            'act': 'a_get_stats',
            'al': 1,
            'object': id_post,
            'views': 1}
        response = await self.vk.POST(Url.like, params)
        res = response.check('error get views').json()['payload'][1][1]
        res = RE.dig_.findall(res)[0]

        await sleeper(0.1, 1)

        return int(res)

    def pars_response(self, res: str, type_pars: str = 'like') -> dict:
        if type_pars == 'like':
            res = RE.pars_response_like.findall(res)[0]
            res = RE.figure_scope.findall(res)[0]
            res = RE.two_slash.sub('', res)

            try:
                return json.loads(res)
            except:
                return json.loads(res + '}')

    async def get_info_like(self, id_post) -> (int, bool):
        if RE.like_type.findall(id_post):
            return -1, 0
        params = {'act': 'a_get_stats',
                  'al': 1,
                  'has_share': 1,
                  'object': id_post}
        response = await self.vk.POST(Url.like, params)
        resp = self.pars_response(response.check('error get info like').body)
        await sleeper(0.1, 1)
        return resp['like_num'], resp['like_my']

    async def get_info_repost(self, id_post) -> (int, bool):
        if RE.like_type.findall(id_post):
            return -1, 0
        params = {
            'act': 'a_get_stats',
            'al': 1,
            'has_share': 1,
            'object': id_post,
            'published': 1}
        response = await self.vk.POST(Url.like, params)
        resp = self.pars_response(response.check('error repost get stat').body)
        await sleeper(0.1, 1)
        return resp['share_num'], resp['share_my']

    def _get_hash_repost_box(self):
        t_str = str(time_ns())
        return convert_base(t_str[:13], 36)

    async def _open_repost_box(self, id_post) -> str:
        params = {
            'act': 'publish_box',
            'al': 1,
            'boxhash': self._get_hash_repost_box(),
            'from_widget': 0,
            'object': id_post}
        response = await self.vk.POST(Url.like, params)
        _hash = response.check('error repost publish_box').find_first(RE.open_repost_box_hash)

        if not _hash:
            raise VkMethodsError('error not hash repost', session=self.vk, id_post=id_post)

        params = {
            'act': 'a_json_friends',
            'al': '1',
            'from': 'imwrite',
            'str': ''}
        await self.simple_method(Url.hints, params, 'error repost a_json_friends')
        await rnd_sleep(1, 5)

        return _hash

    async def set_repost(self, id_post, _hash: str, msg: str) -> bool:
        assert _hash
        params = {
            'Message': msg,
            'act': 'a_do_publish',
            'al': 1,
            'close_comments': 0,
            'friends_only': 0,
            'from': 'box',
            'hash': _hash,
            'list': '',
            'mark_as_ads': 0,
            'mute_notifications': 0,
            'object': id_post,
            'ret_data': 1,
            'to': 0}
        return await self.simple_method(Url.like, params, 'error repost')

    async def set_reaction(self, id_post, _hash: str, like_type: str, reaction_id: int = 0):
        assert _hash
        params = {'act': 'a_set_reaction',
                  'al': '1',
                  'from': like_type,  # 'wall_one', wall_page, feed_recent, photo_viewer
                  'hash': _hash,
                  'object': id_post,
                  'reaction_id': reaction_id,
                  'wall': 2}
        return await self.simple_method(Url.like, params, 'error set reaction')

    async def set_like(self, id_post, _hash: str, like_type: str) -> bool:
        assert _hash
        params = {'act': 'a_do_like',
                  'al': '1',
                  'from': like_type,  # 'wall_one', wall_page, feed_recent, photo_viewer
                  'hash': _hash,
                  'object': id_post,
                  'wall': 2}
        return await self.simple_method(Url.like, params, 'error set like')

    async def get_hash_like(self, id_post):
        like_type = Like.pars_type(id_post)
        _h = await self.get_hash_post(id_post)
        _h = _h.get('like')
        if not _h:
            raise VkMethodsError('not hash like', session=self.vk,
                                 id_post=id_post, like_from=like_type)
        _hash = _h[1]
        await self._buff_sleep(2, 10)

    @cover
    async def like(self, id_post, _hash: str = '', like_type: str = Like.wall_one, reaction_id: int = 0
                   ) -> bool:
        self.print('start like', id_post)
        try:
            if not _hash:
                _hash = await self.get_hash_like(id_post)

            # проверка кроличества просмотров
            await self.get_info_view(id_post)

            # проверка кроличества лайков
            _, like_my = await self.get_info_like(id_post)

            if not like_my:
                # like_type -> 'wall_one', wall_page, feed_recent, feed_top, photo_viewer
                if self.vk.use_reaction:
                    if not reaction_id:
                        reaction_id = 0 if is_random(75) else rnd.randint(0, 5)
                    result = await self.set_reaction(id_post, _hash, like_type, reaction_id)

                else:
                    result = await self.set_like(id_post, _hash, like_type)

                if result:
                    self.log(f'Лайк поставлен: {id_post}')

                else:
                    self.log(f'Неудалось поставить лайк: {id_post}')

                return result

            else:
                self.log(f'Лайк уже был выставлен: {id_post}')
                return False

        except VkMethodsError as vk_ex:
            self.log(f'Ошибка выставления лайка: {id_post}')
            raise vk_ex.add_session(self.vk)

    async def get_more_feed_post(self, post_data: Response, count: int) -> List[Post]:
        url = 'https://vk.com/al_feed.php?sm_news='

        feed_info = post_data.find_first(RE.feed_info)
        feed_info = json.loads('{' + feed_info + '}')

        posts = []

        params = {
            "al": "1",
            "al_ad": "0",
            "from": feed_info['from'],
            "more": "1",
            "offset": "10",
            "part": "1",
            "section": feed_info['section'],
            "subsection": feed_info['subsection']}

        for num in range(0, 101, 10):
            if num > count - 10:
                break
            res = await self.vk.POST(url, params)
            feed = res.check('error get more from feed').json()['payload'][1]

            # parser
            posts.extend(await feed_post_parser(feed[1], self.vk))

            feed_params = feed[0]
            params = {
                "al": "1",
                "al_ad": "0",
                "from": feed_params['from'],
                "more": "1",
                "offset": feed_params['offset'],
                "part": "1",
                "section": feed_params['section'],
                "subsection": feed_params['subsection']}

            await sleeper(5, 20)

        return posts

    async def get_wall_post(self, owner_id, offset):
        params = {
            'act': 'get_wall',
            'al': 1,
            'fixed': '',
            'offset': offset,
            'onlyCache': 'false',
            'owner_id': owner_id,
            'type': 'own',
            'wall_start_from': 10}
        resp = await self.vk.POST(Url.wall, params)
        return resp.check('error get more wall').payload()

    async def get_more_post(self, owner_id: int, count: int, post_from: int,
                            response: Response = None) -> List[Post]:
        add_posts = []
        if post_from == FROM_WALL and response is None:
            for offset in range(10, count, 10):
                data = await self.get_wall_post(owner_id, offset)
                posts = await wall_post_parser(data, self.vk, is_full_page=False)
                add_posts.extend(posts)
                await sleeper(5, 16)
        elif post_from == FROM_FEED and not response is None:
            posts = await self.get_more_feed_post(response, count)
            add_posts.extend(posts)

        else:
            raise VkMethodsError('get_more_post error', _locals=locals(), session=self.vk)

        return add_posts

    @cover
    async def get_post(self, owner_id: int = FROM_FEED, count: int = 10,
                       response: Response = None, ads=False, fix_post=False) -> List[Post]:

        if owner_id != 0 and isinstance(owner_id, int):
            if response is None:
                o = f'club{abs(owner_id)}' if owner_id < 0 else f'id{owner_id}'
                response = await self.vk.GET(f'https://vk.com/{o}')
                response.check()
            posts = await wall_post_parser(response.body, self.vk)

        elif owner_id == FROM_FEED:
            if response is None:
                response = await self.vk.GET(f'https://vk.com/feed')
                response.check()
            posts = await feed_post_parser(response.body, self.vk)

        else:
            raise VkMethodsError('owner id error', _locals=locals(), session=self.vk)

        if count == len(posts):
            return posts
        elif count < len(posts):
            return posts[:count]
        else:
            if owner_id != 0:
                add_posts = await self.get_more_post(owner_id, count, FROM_WALL)
            else:
                add_posts = await self.get_more_post(owner_id, count, FROM_FEED, response)

            posts.extend(add_posts)

            temp = []
            p = []

            [(temp.append(x.id), p.append(x)) for x in posts
             if x.id not in temp
             and (not x.is_vk_ads or ads)
             and (not x.is_fix or fix_post)]

            posts = p

            if not posts:
                return []

            hash_comment = posts[0].hash_comment
            for x in posts:
                x.hash_comment = hash_comment

            return posts[:count]

    @cover
    async def get_wall_post_body(self, post_id: str, reply: str):
        params = {
            'act': 'show',
            'al': 1,
            'dmcah': '',
            'from': 'notify_feed',
            'loc': 'feed',
            'location_owner_id': self.vk.my_id,
            'ref': 'feed_news_recent',
            'reply': reply,
            'w': post_id,  # wall566489438_34
            'zoomText': 'true'}
        res = await self.vk.POST(Url.wkview, params)
        return res.check('error get comment').json()

    @cover
    async def repost(self, id_post, msg: str = '') -> bool:
        self.print('repost', id_post)
        try:
            response = await self.vk.GET(f'https://vk.com/{id_post}')
            response.check()

            await self._buff_sleep(3, 16)

            # проверка кроличества репостов
            _, share_my = await self.get_info_repost(id_post)
            if share_my:
                self.log(f'уже делал репост этого поста: {id_post}')
                raise VkMethodsError(f'already reposted {id_post}')

            if is_random(25):
                # проверка кроличества просмотров
                await self.get_info_like(id_post)

            # получение хеша для репоста
            hash_repost = await self._open_repost_box(id_post)

            await self.set_repost(id_post, hash_repost, msg)
            self.log(f'Репост: {id_post}')
            return True

        except VkMethodsError as vk_ex:
            self.log(f'Ошибка репоста: {id_post}')
            raise vk_ex.add_session(self.vk)

    @cover
    async def del_comment(self, post_id: str, reply: str, hash_del: str) -> bool:
        await self._buff_sleep(1, 10)
        comment_id = RE.sub_id.sub('', post_id).split('_')[0] + '_' + reply  # magic
        params = {
            'act': 'delete',
            'al': 1,
            'confirm': 0,
            'from': 'wall',
            'hash': hash_del,
            'post': comment_id,
            'root': 0}
        s = await self.simple_method(Url.wall, params, 'error del comment')
        if s:
            self.log(f'Удалил комментарий: {post_id}, {reply}')
        return s

    @cover
    async def open_photo(self, photo_id: str, _hash: str):
        params = {
            "act": "show",
            "al": "1",
            "al_ad": "0",
            "dmcah": "",
            "list": _hash,
            "module": "profile",
            "photo": photo_id.replace('photo', '')
        }
        resp = await self.vk.POST(Url.al_photos, params)
        return resp.check('error open photo').json()

    async def get_image_comment_photo(self, photo_id: str, reply: str, _hash: str):
        # TODO
        data = await self.open_photo(photo_id, _hash)

        comments_data = ''

        if data:
            _id = photo_id.replace('photo', '')
            photos = data['payload'][3]
            for photo in photos:
                if photo.get('id') == _id:
                    comments_data = photo.get('comments', '')
                    break

        # comments = self.pars_comment(data=comments_data)

    async def get_image_comment_wall(self, post_id: str, reply: str) -> (List[str], str):
        try:
            post = await self.get_wall_post_body(post_id, reply)
            if not post:
                return [], ''

            comment_id = RE.sub_id.sub('', post_id).split('_')[0] + '_' + reply

            comment_data = post['payload'][1][1]
            comment_image = re.findall(f"(?<=<div id=\"wpt{comment_id}).*?(?=id=\"wpe_bottom{comment_id})",
                                       comment_data, flags=re.DOTALL)

            hash_del = re.findall(f"(?<=deletePost\(this, '{comment_id}', ').*?(?='\))", comment_data)
            hash_del = hash_del[0] if hash_del else ''

            if comment_image:
                images = []
                for img in RE.js_obj.findall(comment_image[0]):
                    img = RE.quot.sub('"', img)
                    img = RE.amp.sub('&', img)
                    img = json.loads(img)['temp']
                    img = img.get('x') or img.get('z')
                    if img:
                        images.append(img)

                return images, hash_del

            else:
                return [], hash_del

        except:
            logs()
            return [], ''

    async def comment_post(self,
                           id_post,
                           msg: str,
                           reply_to_user: str = '0',
                           reply_to_msg: str = '',
                           hash_comment: str = '',
                           attachment: List[List[str]] = None
                           ) -> Dict[str, str]:
        self.print('comment', id_post, msg)
        try:
            assert msg or attachment, 'not message text and attachment'

            if not hash_comment:
                hash_comment = await self.get_hash_post(id_post)
                hash_comment = hash_comment['comment']

            if not hash_comment:
                raise VkMethodsError('not hash comment', session=self.vk, id_post=id_post)

            params = {'Message': msg,
                      'act': 'post',
                      'al': 1,
                      'from': '',
                      'from_oid': self.vk.my_id,
                      'hash': hash_comment,
                      'need_last': 0,
                      'only_new': 1,
                      'order': 'asc',
                      'ref': 'wall_page',
                      'reply_to': RE.sub_d.sub('', id_post),
                      'reply_to_msg': reply_to_msg,
                      'reply_to_user': reply_to_user,
                      'timestamp': str(time_ns())[:-6],
                      'type': 'own'}

            if attachment:
                attach = {}
                for number, content in enumerate(attachment):
                    attach[f'attach{number + 1}_type'] = content[0]
                    attach[f'attach{number + 1}'] = content[1]
                params.update(attach)

            res = await self.vk.POST(Url.wall, params)
            _id = res.check('error comment').find(RE.id_new_comment)
            id_new_comment = _id[-1] if _id else -1

            self.log(f'Новый комментарий: {id_post}, {id_new_comment}, {msg}')
            return {'comment': id_new_comment}

        except Exception as ex:
            logs()
            return {'error_comment': str(ex)}

    @cover
    async def comment_photo(self,
                            id_photo,
                            msg: str,
                            from_id: str,
                            hash_comment: str = ''
                            ) -> bool:
        self.print('comment photo', id_photo, msg)
        reply_to_msg = []

        if not hash_comment:
            resp = await self.vk.GET(f'https://vk.com/{id_photo}')
            resp.check()
            pattern = f"{id_photo}', '"
            hash_comment = re.findall(r"(?<=" + pattern + r").*?(?=')", resp.body)
            assert hash_comment, 'not hash_comment_photo'
            pattern1 = self.vk.my_id + "_photo" + id_photo.split('_')[-1]
            pattern = f"(?<=" + pattern1 + r").{,20}(?=" + from_id + r")"
            reply_to_msg = re.findall(pattern, resp.body)
            assert reply_to_msg, 'not reply_to_msg'
            reply_to_msg = re.sub(r'[^0-9]', '', reply_to_msg[0])
            assert reply_to_msg, 'not reply_to_msg sub'

        params = {
            'Message': msg,
            'act': 'post_comment',
            'al': 1,
            'from_group': '',
            'hash': hash_comment[0],
            'photo': RE.sub_d.sub('', id_photo),
            'reply_to': reply_to_msg}

        await self.simple_method(Url.photo, params, f'error create comment photo {id_photo}')
        self.log(f'Новый комментарий под фото: {id_photo}, {0}, {msg}')
        return True

    @cover
    async def spam(self, id_post, url_spam_post) -> bool:
        hash_spam = await self.get_hash_post(id_post)
        hash_spam = hash_spam['spam']

        params = {'act': 'spam',
                  'al': '1',
                  'from': '',
                  'hash': hash_spam[1],
                  'post': hash_spam[0]}
        resp = await self.vk.POST(Url.wall, params)
        resp.check('error spam 1')

        hash_spam = resp.find(RE.spam_hash, lambda x: RE.word_dig_.findall(x))
        assert hash_spam, 'not hash spam'

        a = RE.d.findall(id_post)

        params = {'act': 'new_copyright_report',
                  'al': '1',
                  'hash': hash_spam[0][-1],
                  'object_id': a[1],
                  'object_owner_id': a[0],
                  'object_type': '1',
                  'source_link': f'vk.com%2F{url_spam_post}'}
        resp = await self.vk.POST(Url.reports, params)
        resp.check('error spam 2')

        return True

    @cover
    async def post_wall(self,
                        owner_id: str,
                        msg: str = '',
                        attachment: List[Tuple[str, str]] = None,
                        params: Dict[str, Union[int, str]] = None,
                        topic_id: int = 0,
                        copyright_url: str = '',
                        **kwargs
                        ) -> str:
        """
        topic_id -> 32 юмор, 26 кино, 21 наука, 19 фото, 1 арт
        """
        link = f'club{owner_id[1:]}' if '-' in owner_id else f'id{owner_id}'
        resp = await self.vk.GET(f'https://vk.com/{link}')
        hash_post = resp.check().find_first(RE.get_hash_post_comment)
        assert hash_post, 'error not have hash_post'
        await sleeper(1, 5)

        # возможность установить кастомные параметры
        if not params:
            params = {'act': 'post',
                      'to_id': owner_id,
                      'type': 'own',
                      'friends_only': '',
                      'best_friends_only': '',
                      'close_comments': 0,
                      'mute_notifications': 0,
                      'mark_as_ads': 0,
                      'official': 1,
                      'signed': '',
                      'from': '',
                      'fixed': '',
                      'update_admin_tips': 0,
                      'Message': msg,
                      'al': 1,
                      }

        params.update({'hash': hash_post})

        # вложения
        if attachment:
            atta = {}
            for number, content in enumerate(attachment):
                atta[f'attach{number + 1}_type'] = content[0]
                atta[f'attach{number + 1}'] = content[1]
            params.update(atta)

        # котегория поста - юмор, арт, и т.д.
        if topic_id:
            params.update({'topic_id': topic_id})

        if copyright_url:
            params.update({'copyright': copyright_url})

        if kwargs:
            params.update(kwargs)

        assert msg or attachment, 'not content for post'

        resp = await self.vk.POST(Url.wall, params)
        return resp.check('error create post').find_first(RE.info_post).strip()

    @cover
    async def view_posts(self, posts: List[Post], target_post_id: str = '', random_view: int = 40):
        if not posts:
            return False

        if not isinstance(posts, list) and isinstance(posts[0], Post):
            raise VkMethodsError('error posts type need "List[Post]"',
                                 _locals=locals(), session=self.vk)
        if target_post_id:
            target_post_id = [target_post_id]
        return await self.view_post([p.id for p in posts], target_post_id, random_view)

    @cover
    async def view_post(self, id_posts: List[str], target: List[str] = None,
                        random_view: int = 40, _hash_view: str = '') -> bool:
        await rnd_sleep(10, 5)

        if not target:
            target = []

        # выборка случайных постов, целевых и постов, которых еще не просматривал в текущей сессии
        id_posts = [post for post in id_posts
                    if (is_random(random_view) or post in target)
                    and post not in self.already_view_posts]

        # добавляет в просмотренные
        [self.already_view_posts.append(post) for post in id_posts]

        if not id_posts:
            return False

        data = ''
        meta = ''
        pref = rnd.choice(['_rf', '_tf']) if self.feed_session != 'na' else '_c'
        for j, i in enumerate(id_posts):
            a = RE.d.findall(i)
            if len(a) < 2:
                self.print('error view post id = ', i)
                continue
            data += f'{a[0]}{pref}{a[1]}:{rnd.choice([-1, 2298, -1, 1384, -1, 3065, -1])}:{j}:{self.feed_session};'
            meta += f'{i}:{rand(300, 900)}:{self.meta_view};'

        # очставляет только 300 последних просмотренных постов
        if len(self.already_view_posts) > 300:
            self.already_view_posts = self.already_view_posts[150:]

        params = {
            'act': 'seen',
            'al': 1,
            'data': data,
            'hash': self.hash_view_post if not _hash_view else _hash_view,
            'meta': meta}
        return await self.simple_method(Url.page, params, 'error view')

    @cover
    async def get_new_friend_list(self, offset: int = 0, count: int = 60) -> List[User]:
        try:
            response = await self.vk.GET('https://vk.com/friends?section=requests')
            response.check()
            await sleeper(1, 10)

            out = []
            for _ in range(rnd.randint(2, 6)):
                params = {
                    'act': "get_section_friends",
                    'al': 1,
                    'gid': 0,
                    'id': self.vk.my_id,
                    'offset': offset,
                    'section': 'requests'}
                res = await self.vk.POST(Url.friends, params)
                res = res.check('error get more new friends').payload()
                res = json.loads(res)['requests']

                if not res:
                    break

                for i in res:
                    out.append(User(self.vk, i))

                if offset >= count:
                    break

                offset += len(res)

                await self._buff_sleep(3, 16)

            return out[:count]

        except:
            logs()
            return []

    @cover
    async def get_subscriber_list(self, offset: int = 0, count: int = 100) -> List[User]:
        try:
            response = await self.vk.GET('https://vk.com/friends?section=all_requests')
            response.check()
            await sleeper(1, 10)

            out = []
            while True:
                params = {
                    'act': "get_section_friends",
                    'al': 1,
                    'gid': 0,
                    'id': self.vk.my_id,
                    'offset': offset,
                    'section': 'all_requests'}
                res = await self.vk.POST(Url.friends, params)
                res = res.check('error get more new friends').payload()
                res = json.loads(res)['all_requests']

                if not res:
                    break

                for i in res:
                    out.append(User(self.vk, i, is_my_subscriber=True))

                if offset >= count:
                    break

                offset += len(res)

                await self._buff_sleep(3, 16)

            return out[:count]

        except:
            logs()
            return []

    @cover
    async def get_out_request_friends(self, offset: int = 0) -> List[User]:
        response = await self.vk.GET('https://vk.com/friends')
        response.check()
        await sleeper(1, 10)

        params = {'act': 'get_section_friends',
                  'al': 1,
                  'gid': 0,
                  'id': self.vk.my_id,
                  'offset': offset,
                  'section': 'out_requests'}
        res = await self.vk.POST(Url.friends, params)
        res = res.check('error get more').payload()
        out_requests = json.loads(res)['out_requests']

        return [User(self.vk, out_request) for out_request in out_requests]

    @cover
    async def friend_decline(self, user: User) -> bool:
        await self._buff_sleep(0.1, 5)
        params = {'act': 'remove',
                  'al': 1,
                  'from_section': 'requests',
                  'hash': user.hash_decline,
                  'mid': user.id,
                  'report_spam': 1}
        if await self.simple_method(Url.al_friends, params, 'error friend_decline'):
            self.log(f'Заявка в друзья отклонена: {user}')
            return True
        else:
            self.log(f'Неудалось отклонить заявку в друзья: {user}')
            return False

    @cover
    async def friend_accept(self, user: User) -> bool:
        await self._buff_sleep(0.1, 5)
        params = {'act': 'add',
                  'al': 1,
                  'hash': user.hash_accept,
                  'mid': user.id,
                  'request': 1,
                  'select_list': 1}
        if await self.simple_method(Url.al_friends, params, 'error friend_accept'):
            self.log(f'Заявка в друзья принята: {user}')
            return True
        else:
            self.log(f'Неудалось принять заявку в друзья: {user}')
            return False

    @cover
    async def get_hash_del_friends(self) -> str:
        if not self._hash_del_friends or self._time_hash_del_friends < 3600:
            self._time_hash_del_friends = time()
            res = await self.vk.GET(Url.friends)
            _hash = res.check().find_first(RE.user_hash)
            if not _hash:
                raise VkMethodsError('not hash del friends', session=self.vk)

            self._hash_del_friends = _hash
            await self._buff_sleep(1, 8)

        return self._hash_del_friends

    @cover
    async def del_friends(self, user: User, to_black_list: bool = False) -> bool:
        hash_del_friends = await self.get_hash_del_friends()
        params = {'act': 'remove',
                  'al': 1,
                  'from': 'profile',
                  'hash': hash_del_friends,
                  'mid': user.id}
        if await self.simple_method(Url.al_friends, params, 'error del friend'):
            self.log(f'Удалил друга: {user}')

            if to_black_list:
                await self.add_user_to_black_list(user)

            return True

        else:
            self.log(f'Неудалось удалить друга: {user}')
            return False

    @cover
    async def del_friends_from_out_requests(self, user: User, to_black_list: bool = False) -> bool:
        params = {'act': 'remove',
                  'al': 1,
                  'from_section': 'out_requests',
                  'hash': user.hash_decline,
                  'mid': user.id}
        if await self.simple_method(Url.al_friends, params, 'error del out request friend'):
            self.log(f'Удалил исходящюю заявку в друзья к: {user}')

            if to_black_list:
                await self.add_user_to_black_list(user)

            return True

        else:
            self.log(f'Неудалось удалить исходящюю заявку в друзья к: {user}')
            return False

    @cover
    async def add_user_to_black_list(self, user: User) -> bool:
        await self._buff_sleep(3, 10)

        # дополнительная проверка не состоитли человек в друзьях
        if user.is_my_friend:
            await self.del_friends(user)

        res = await self.vk.GET(f'https://vk.com{user.url_nick}')
        res.check()

        tree = lxml.html.fromstring(res.body)

        block_status = tree.xpath('//*[@data-task-click="ProfileAction/toggle_blacklist"]//text()')
        if block_status and not 'Заблокировать' in block_status[0]:
            self.log(f'Юзер уже добавлен в ЧС: {user}')
            return False

        list_hash = tree.xpath('//*[@data-task-click="ProfileAction/toggle_blacklist"]/@data-hash')

        if list_hash:
            hash_black_list = list_hash[0]
        else:
            raise VkMethodsError('error get hash for add to black list', session=self.vk)

        await sleeper()
        params = {'act': 'a_add_to_bl',
                  'al': 1,
                  'from': 'profile',
                  'hash': hash_black_list,
                  'id': user.id}

        if await self.simple_method(Url.settings, params, 'err add bl list'):
            self.log(f'Добавил в ЧС: {user}')
            return True

        else:
            self.log(f'Неудалось добавил в ЧС: {user}')
            return False

    @cover
    async def del_dialog(self, peer_id: str, del_history: bool = False) -> bool:
        self.print('del dialog', peer_id)

        res = await self.vk.GET('https://vk.com/im')
        im_init = res.check().find_first(RE.get_im)

        res = json.loads('{' + im_init + '}').get('tabs', {}).get(str(peer_id))

        assert res, 'error, not tabs list dialog'

        hash_dialog = res['hash']
        chat_url = res.get('href', '')

        if chat_url:
            chat_id = chat_url.split('=c')[-1]

            params = {
                '_smt': 'im:22',
                'act': 'a_leave_chat',
                'al': 1,
                'chat': chat_id,
                'gid': 0,
                'hash': hash_dialog,
                'im_v': 3}
            if await self.simple_method(Url.im, params, 'error leave chat'):
                self.log(f'Вышел из чата: {peer_id}')
            else:
                self.log(f'Неудалось выйти из чата: {peer_id}')
        else:
            params = {
                "act": "a_delete_dialog",
                "al": 1,
                "gid": 0,
                "hash": hash_dialog,
                "im_v": 3,
                "peer": peer_id}
            if await self.simple_method(Url.im, params, 'error del dialog'):
                self.log(f'Удалил диалог: {peer_id}')
            else:
                self.log(f'Неудалось удалить диалог: {peer_id}')

        if del_history:
            params = {
                "act": "a_flush_history",
                "al": "1",
                "from": "im",
                "gid": "0",
                "hash": hash_dialog,
                "id": peer_id,
                "im_v": "3"}
            if await self.simple_method(Url.im, params, 'error del history'):
                self.log(f'Удалил историю чата: {peer_id}')
            else:
                self.log(f'Неудалось удалить историю чата: {peer_id}')

        return True

    async def get_list_group(self, user_id: str = '') -> dict:
        try:
            response = await self.vk.GET('https://vk.com/groups')
            response.check()
            await sleeper()

            params = {'act': 'get_list',
                      'al': 1,
                      'mid': self.vk.my_id if not user_id else user_id,
                      'tab': 'groups'}
            res = await self.vk.POST(Url.group, params)
            return res.check('error get list group').payload()

        except:
            logs()
            return {}

    async def get_list_friends(self, user_id: str = '') -> List[User]:
        try:
            url = f'https://vk.com/friends?id={user_id}&section=all' \
                if user_id else 'https://vk.com/friends?section=all'
            response = await self.vk.GET(url)
            response.check()
            await sleeper(1, 10)

            params = {
                "act": "load_friends_silent",
                "al": "1",
                "gid": "0",
                "id": self.vk.my_id if not user_id else user_id}
            res = await self.vk.POST(Url.al_friends, params)
            friends_list = res.check('error get friend list').payload()['all']
            return [User(self.vk, friend, True) for friend in friends_list]

        except:
            logs()
            return []

    async def pars_search_groups(self, params) -> (List[Group], int, int, int):
        res = await self.vk.POST(Url.search, params)
        json_res = res.check('error get search groups').json()['payload'][1]

        query_id = json_res[0]['query_id']
        offset = json_res[0]['offset']
        real_offset = json_res[0]['real_offset']

        res = Response(json_res[1])

        group_id_and_hash = res.find(RE.search_group_id, lambda x: RE.word_dig_.findall(x))
        title = res.find(RE.search_group_title)
        photo = res.find(RE.search_group_photo)
        type_group = res.find(RE.search_group_type)
        member_count = res.find(RE.search_group_member_count, lambda x: ''.join(RE.dig_.findall(x)))

        groups = [
            Group(self.vk,
                  int(group_id_and_hash[i][0]),
                  title[i], int(member_count[i]),
                  group_id_and_hash[i][1],
                  type_group[i], photo[i])
            for i in range(len(group_id_and_hash))
        ]

        return groups, query_id, offset, real_offset

    async def search_groups(self, query: str, count: int = 40) -> List[Group]:
        try:
            groups = []

            params = {
                'act': 'search_request',
                'al': 1,
                'c[like_hints]': 1,
                'c[not_safe]': 1,
                'c[q]': query,
                'c[section]': 'communities',
                'change': 1,
                'search_loc': 'groups?act = catalog'}
            groups_list, query_id, offset, real_offset = await self.pars_search_groups(params)
            groups.extend(groups_list)

            for _ in range(25):
                if len(groups) < count:
                    await rnd_sleep(1, 1)

                    params = {
                        'act': 'show_more',
                        'al': 1,
                        'al_ad': 0,
                        'c[like_hints]': 1,
                        'c[not_safe]': 1,
                        'c[q]': query,
                        'c[sort]': 6,  # по количеству участников
                        'c[section]': 'communities',
                        'offset': offset,
                        'query_id': query_id,
                        'real_offset': real_offset}
                    groups_list, query_id, offset, real_offset = await self.pars_search_groups(params)
                    groups.extend(groups_list)

                else:
                    return groups[:count]
        except:
            logs()
            return []

    @cover
    async def add_friend(self, user_id, _hash=''):
        await self._buff_sleep(1, 10)

        if not _hash:
            res = await self.vk.GET(f'https://vk.com/id{user_id}')
            _hash = res.check().find_first(RE.add_friend)

        if not _hash:
            raise VkMethodsError('Not hash add_friend', session=self.vk, user_id=user_id)
        params = {
            'act': 'add',
            'al': 1,
            'from': 'profile',
            'hash': _hash,
            'mid': user_id  # '7845356'
        }
        return await self.simple_method(Url.al_friends, params, f'error add friend = {user_id}')

    async def castom(self, url: str,
                     params: Dict[str, Union[int, str]] = None,
                     req_type: str = 'post') -> str:
        try:
            res = await self.vk.POST(url, params) if req_type == 'post' else await self.vk.GET(url)
            return res.body

        except Exception as ex:
            logs()
            return str(ex)

    async def unblock(self):
        self.print('Unblock start...')

        u = 'https://vk.com/al_login.php'
        _hash = ''
        phone = ''
        new_password = ''
        id_action = ''
        code = ''
        sms = SmsActivate(config.sms_activate_token)
        try:
            # check can unblock
            res = await self.vk.GET('https://m.vk.com')
            assert 'Login.showUnblockForm' in res or 'login?act=blocked' in res

            for _ in range(3):
                await sleeper(5, 10)

                # open unblock form
                params = {
                    'act': 'get_unblock_process_status',
                    'al': 1
                }
                res = await self.vk.POST(u, params)
                payload = res.check('error open unblock form').payload()
                _hash = payload.get('process_hash')
                can_edit_number = payload.get('can_edit_phone')

                assert _hash and can_edit_number

                # get number
                for _ in range(20):
                    phone, id_action = await sms.get_number()
                    self.print(f'New number for login: {phone}')
                    if not id_action is None:
                        break
                    await sleeper(15, 10)

                assert phone and id_action

                # change number
                params = {
                    'act': 'send_unblock_code',
                    'al': 1,
                    'hash': _hash,
                    'phone': phone if '+' in phone else f'+{phone}',
                    'sure': 1
                }
                res = await self.vk.POST(u, params)
                code_sent = res.payload().get('code_sent')
                if not code_sent:
                    self.print('Error set new phone for login')
                    await sms.number_action(id_action, 8)
                    continue

                await sleeper(121, 300)

                # sent code as sms
                params = {
                    'act': 'resend_unblock_code',
                    'al': 1,
                    'hash': _hash
                }
                res = await self.vk.POST(u, params)
                code_sent = res.check('error send sms').payload().get('code_sent')

                assert code_sent

                # get code
                for _ in range(30):
                    await sleeper(20, 25)
                    code = await sms.check_number_status(id_action)
                    if not code is None:
                        break

                if not code:
                    await sms.number_action(id_action, 8)
                    continue

                else:
                    code = re.sub(r'[^\d]', '', code)
                    break

            assert code and _hash

            logs.code_unblock(f'{self.vk.login} {phone} {code}')

            # send code
            params = {
                'act': 'check_unblock_code',
                'al': 1,
                'code': code,
                'hash': _hash
            }
            res = await self.vk.POST(u, params)
            _hash_unblock = res.check('error code').payload().get('unblock_hash')

            assert _hash_unblock

            await sleeper(5, 16)

            # send new password
            new_password = random_password()
            params = {
                'act': 'unblock',
                'al': 1,
                'hash': _hash_unblock,
                'pass': new_password,
            }
            res = await self.vk.POST(u, params)
            text = res.check('error send new password').payload().get('delayed_unblock_explanation')

            assert text

            logs.unblock(f'Unblock ok!'
                         f'\n\told_login: {self.vk.login}'
                         f'\n\tnew_login: {phone}'
                         f'\n\told_pass: {self.vk.password}'
                         f'\n\tnew_pass: {new_password}'
                         f'\n\tmsg: {text}\n\n')

            self.add(self.vk.api.send_message(config.admin_alarm,
                                              f'{self.vk.login} '
                                              f'{self.vk.my_name} '
                                              f'аккаунт разблокирован!'))

            self.print('Unblock ok!')
            return True

        except Exception as ex:
            logs()
            if id_action:
                await sms.number_action(id_action, 8)

            logs.unblock(f'Unblock failed! ex = {ex}'
                         f'\n\told_login: {self.vk.login}'
                         f'\n\tnew_login: {phone}'
                         f'\n\told_pass: {self.vk.password}'
                         f'\n\tnew_pass: {new_password}\n\n')

            self.add(
                self.vk.api.send_message(config.admin_alarm,
                                         f'{self.vk.login} {self.vk.my_name}'
                                         f' аккаунт НЕ разблокирован!\n'
                                         f'причина: {ex}'))
            return False

    # ----
    '''
    def transliteration(self, text, f=True):
        cyrillic = 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя'
        latin = 'a|b|v|g|d|e|e|zh|z|i|i|k|l|m|n|o|p|r|s|t|u|f|kh|tc|ch|sh|shch||y||e|iu|ia'.split('|')
        trantab = {k: v for k, v in zip(cyrillic, latin)}
        newtext = ''
        for ch in text:
            casefunc = str.capitalize if ch.isupper() else str.lower
            newtext += casefunc(trantab.get(ch.lower(), ch))
        return re.sub(r' ', '-', newtext) if f else newtext

    def text_to_article(self, el: dict) -> list:
        header = el.get('head', '')
        txt = el.get('text', '')

        out = [{"type": 2, "lines": [{"text": header}]}]
        for i in txt.split('\n'):
            out.append({"lines": [{"text": i}]})
        return out

    async def create_articles(self, owner_id: str, el: str, head='test'):
        try:
            article_id = '0'
            url = f'club{owner_id[1:]}' if owner_id[0] == '-' else f'id{owner_id}'

            # переход в группу
            data = await self.req(f'https://vk.com/{url}')
            hash_post = re.findall(r"(?<=\"post_hash\":\").*?(?=\",\")", data)[0]
            assert hash_post, 'error not have hash_post'
            await sleep(rnd.random() * 5 + 1)

            # окрытие редактора статей
            params = {'act': 'open_editor',
                      'al': '1',
                      'article_owner_id': owner_id,
                      'from_post_convert': '0',
                      'post_data_medias': ''}
            session_duration = int(time())
            resp = await self.req_post('https://vk.com/al_articles.php', params)

            assert self.ok in resp, 'error start articles'

            cooc = ''
            for key, cookie in self.session.cookie_jar._cookies.items():
                for j, i in cookie.items():
                    cooc += f'{j}={i.value}; '

            print(cooc)

            name = re.findall(r"(?<=\"ownerAlias\":\").*?(?=\",\")", resp)[0]
            hash_articles = re.findall(r"(?<=\"saveDraftHash\":\").*?(?=\",\")", resp)[0]
            assert hash_articles, 'error not have hash_articles'

            await sleep(rnd.random() * 10 + 1)

            #  сохранение массива строк в статью
            ref = {'referer': f'https://vk.com/{name}?z=article_edit{owner_id}_0'}
            params = {'Article_text': el,
                      'act': 'save',
                      'al': '1',
                      'article_id': article_id,
                      'article_owner_id': owner_id,
                      'chunks_count': '0',
                      'cover_photo_id': '',
                      'hash': hash_articles,
                      'is_published': '0',
                      'name': head,
                      'session_duration': int(time()) - session_duration}
            resp = await self.req_post('https://vk.com/al_articles.php', params, ref)
            assert self.ok in resp, 'error save articles'
            await sleep(rnd.random() * 5 + 1)

            # получение id статьи
            article_id = re.findall(r"(?<=\"id\":).*?(?=,\"o)", resp)
            assert article_id, 'error get article id'

            #  сохранение массива строк в статью для публикации
            params = {'Article_text': el,
                      'act': 'save',
                      'al': '1',
                      'article_id': article_id[0],
                      'article_owner_id': owner_id,
                      'chunks_count': 0,
                      'cover_photo_id': '',
                      'donut': 0,
                      'hash': hash_articles,
                      'is_published': 1,
                      'monetization': 0,
                      'name': head,
                      'ofm': 0,
                      'show_author': 0,
                      'session_duration': int(time()) - session_duration}
            resp = await self.req_post('https://vk.com/al_articles.php', params)
            assert self.ok in resp, 'error save articles'
            await sleep(rnd.random() * 5 + 1)

            # закрытие редактора статьи
            params = {
                'act': 'editor_closed',
                'al': 1,
                'article_id': article_id,
                'article_is_saved': 1,
                'article_owner_id': owner_id,
                'session_duration': int(time()) - session_duration}
            resp = await self.req_post('https://vk.com/al_articles.php', params)
            assert self.ok in resp, 'error close article'
            await sleep(rnd.random() * 5 + 1)

            # имитация просмотра получившейся статьи
            params = {
                'act': 'view',
                'al': 1,
                'context': 'public',
                'layer': 1,
                'ref': '',
                'url': f'@{name}-{head}',
                'wall_owner_id': owner_id}
            resp = await self.req_post('https://vk.com/al_articles.php', params)
            assert self.ok in resp, 'error view article'
            await sleep(rnd.random() * 5 + 1)

            # создать пост
            params = {'act': 'post',
                      'to_id': owner_id,
                      'type': 'own',
                      'friends_only': '',
                      'status_export': '',
                      'close_comments': 0,
                      'mute_notifications': 0,
                      'mark_as_ads': 0,
                      'official': 1,
                      'signed': '',
                      'anonymous': '',
                      'hash': hash_post,
                      'from': '',
                      'fixed': '',
                      'attach1_type': 'article',
                      'attach1': f'/@{name}-{head}',
                      'update_admin_tips': 0,
                      'Message': '',
                      'al': 1}
            resp = await self.req_post('https://vk.com/al_wall.php', params)
            assert self.ok in resp, 'error post article'

            return True

        except:
            logs()
            return False
    '''


class Upload:
    __slots__ = 'photo', 'doc', 'video'

    def __init__(self, vk: VkSession):
        self.photo: UploadPhoto = UploadPhoto(vk)
        self.doc: UploadDoc = UploadDoc(vk)
        self.video: UploadVideo = UploadVideo(vk)


class UploadPhoto:
    __slots__ = 'vk'

    def __init__(self, vk: VkSession):
        self.vk: VkSession = vk

    async def wall(self, owner_id, *data_list_photo, arg=None):
        params = {"act": "choose_photo",
                  "al": "1",
                  "al_ad": "0",
                  "from": "post",
                  "mail_add": "",
                  "max_files": "10",
                  "no_album_select": "",
                  "to_id": owner_id}
        return await self._up(data_list_photo[:10] if not arg else arg[:10], params)

    async def message(self, *list_photo, arg=None):
        params = {
            'act': 'choose_photo',
            'al': 1,
            'al_ad': 0,
            'blockPersonal': 0,
            'from': 'message',
            'mail_add': 1,
            'max_files': 10,
            'no_album_select': ''
        }
        return await self._up(list_photo[:10] if not arg else arg[:10], params)

    async def album(self, album_id, *list_photo):
        res = await self.vk.GET(f'https://vk.com/albums{self.vk.my_id}')
        url = re.findall(r"(?<=cur.html5LiteUrl = ').*?(?=';)", res.body)
        assert url, 'not upload url album photo'
        var = re.findall(r"(?<=cur.html5LiteVars =).*?(?=;)", res.body)
        assert var, 'not upload vars'
        var = json.loads(var[0].strip())

        for data_photo in list_photo:
            pass

    async def _up(self, list_photo, params):
        try:
            res = await self.vk.POST(Url.photo, params)
            res.check('error get upload form photo message')
            url, var = self._pars_upload(res.body)
            return [await self._upload(photo, url, var) for photo in list_photo]

        except:
            logs()
            return []

    async def _upload(self, data_photo, url, var):
        await sleep(rnd.random())

        data = FormData()

        if data_photo[-1] == '=' and isinstance(data_photo, str):
            data_photo = b64decode(data_photo)

        if not isinstance(data_photo, bytes):
            async with ClientSession() as session:
                async with await session.get(data_photo) as res:
                    data_photo = await res.read()

        data.add_field('file',
                       io.BytesIO(data_photo),
                       filename='file.png',
                       content_type='image/png')

        params = {
            '_origin': var['_origin'],
            'act': var['act'],
            'aid': var['aid'],
            'ajx': 1,
            'gid': 0,
            'hash': var['hash'],
            'jpeg_quality': 89,
            'mid': self.vk.my_id,
            'rhash': var['rhash']}
        async with await self.vk._session.post(
                url,
                headers=self.vk._get_headers(self.vk.heads, 'GET'),
                params=params,
                data=data,
                timeout=60,
                proxy=self.vk.proxy) as res:
            res = await res.json()

        assert res.get('code', 1), f'error upload photo = {str(res)}'

        params = {
            "act": "choose_uploaded",
            "aid": var['aid'],
            "al": 1,
            "gid": 0,
            "hash": res['hash'],
            "is_reply": 0,
            "mid": self.vk.my_id,
            "server": res['server'],
            "photos": res['photos']
        }
        res = await self.vk.POST(Url.photo, params)
        return 'photo', res.check('error save photo').json()["payload"][1][0]

    def _pars_upload(self, res: str) -> (str, dict):
        url = RE.upload_url.findall(res)

        assert url, 'not url upload'

        url = RE.two_slash.sub('', f'https{url[0]}.php')
        var = RE.upload_vars.findall(res)

        assert var, 'not data vars'

        var = RE.two_slash.sub('', var[0].strip()) + "}"
        var = json.loads(var)

        return url, var

    async def avatar(self, data_photo):
        try:
            params = {
                'act': 'owner_photo_box',
                'al': 1,
                'oid': self.vk.my_id
            }
            res = await self.vk.POST(Url.page, params)
            var = res.check('error get upload avatar box').find(RE.uoload_avatar)
            assert var, 'error get vars'

            var = json.loads(var[0])

            data = FormData()
            if not isinstance(data_photo, bytes):
                async with ClientSession() as session:
                    async with await session.get(data_photo) as res:
                        data_photo = await res.read()

            data.add_field('file',
                           io.BytesIO(data_photo),
                           filename='file.png',
                           content_type='image/png')

            async with await self.vk.session.post(
                    var['url'],
                    headers=self.vk.get_headers(self.vk.heads, 'GET'),
                    params=params,
                    data=data,
                    timeout=60,
                    proxy=self.vk.proxy) as res:
                res = await res.text()

            params = {
                '_query': res,
                'act': 'owner_photo_save',
                'al': 1,
                'from': 'profile'
            }
            res = await self.vk.POST(Url.page, params)
            res.check('error upload avatar')

            return True

        except:
            logs()
            return False


class UploadDoc:
    __slots__ = 'vk'

    def __init__(self, vk: VkSession):
        self.vk: VkSession = vk

    async def add(self, *data_list_doc):
        params = {
            'blockPersonal': 0,
            'from': 'message',
            'mail_add': 1,
        }
        return await self._up(data_list_doc[:10], params)

    async def _up(self, list_doc, params):
        params.update({'act': 'a_choose_doc_box', 'al': 1})
        try:
            res = await self.vk.POST(Url.docs, params)
            res.check('error get upload form doc message')
            url, var = self._pars_upload(res.body)
            return [await self._upload(doc, url, var) for doc in list_doc]

        except:
            logs()
            return []

    async def _upload(self, data_doc, url, var):
        data = FormData()

        if data_doc[-1] == '=' and isinstance(data_doc, str):
            data_doc = b64decode(data_doc)

        if not isinstance(data_doc, bytes):
            async with ClientSession() as session:
                async with await session.get(data_doc) as res:
                    data_doc = await res.read()

        data.add_field('file',
                       io.BytesIO(data_doc),
                       filename='file.gif',
                       content_type='image/gif')

        params = {
            'act': var['act'],
            'aid': var['aid'],
            'ajx': 1,
            'gid': 0,
            'hash': var['hash'],
            'mid': self.vk.my_id,
            'rhash': var['rhash'],
            'upldr': var['upldr'],
            'vk': var['vk']
        }
        async with await self.vk._session.post(
                url,
                headers=self.vk._get_headers(self.vk.heads, 'GET'),
                params=params,
                data=data,
                timeout=60,
                proxy=self.vk.proxy) as res:
            res = await res.json()

        params = {
            'act': 'a_save_doc',
            'al': 1,
            'blockPersonal': 0,
            'file': res['file'],
            'from': 'choose',
            'from_place': '',
            'imhash': '',
            'mail_add': 0,
        }
        res = await self.vk.POST(Url.docs, params)
        return 'doc', '_'.join(res.check('error save doc').json()["payload"][1][0:2])

    def _pars_upload(self, res: str) -> (str, dict):
        url = re.findall(r"(?<=Upload, 'https).*?(?=upload_doc.php)", res)
        assert url, 'not url upload'
        url = re.sub(r'\\', '', f'https{url[0]}upload_doc.php')

        var = re.findall(r"(?<=php', \{).*?(?=},)", res)
        assert var, 'not data vars'

        var = re.sub(r'\\', '', '{' + var[0].strip()) + "}"
        var = json.loads(var)

        return url, var


class UploadVideo:
    __slots__ = '_vk'

    def __init__(self, vk: VkSession):
        self._vk = vk

    def __call__(self, *args, **kwargs) -> Coroutine:
        return self.add(*args, **kwargs)

    async def _get_upload_box(self, owner_id):
        await sleeper(1, 2)
        params = {
            'aid': 0,
            'al': 1,
            'from': 'video',
            'ocl': 0,
            'oid': owner_id,  # -174587092
        }
        res = await self._vk.POST('https://vk.com/al_video.php?act=upload_box', params)
        random_tag = res.check('error get upload box').find_first(RE.video_random_tag)
        _hash_save = res.find_first(RE.video_up_hash)

        return random_tag, _hash_save

    async def _get_upload_url(self, file_size, owner_id, tag):
        await sleeper(1, 3)
        params = {
            'al': 1,
            'file_size': file_size,
            'from': 'video',
            'owner_id': owner_id,
            'tag': tag,
            'user_agent': self._vk.heads,
        }
        res = await self._vk.POST('https://vk.com/al_video.php?act=get_upload_url', params)
        return res.check('error get upload url').payload()['upload_url']

    async def _up(self, url, path):
        await sleeper(1, 3)
        data = FormData()
        with open(path, 'rb') as file:
            data.add_field('file', file, filename=f'{time()}.mp4', content_type='video/mp4')

            head = {
                'Accept': '*/*',
                'Accept-Encoding': 'gzip, deflate, br',
                'Accept-Language': 'en-US,en;q=0.9,ru;q=0.8,ja;q=0.7',
                'Connection': 'keep-alive',
                'DNT': '1',
                "User-Agent": self._vk.heads}
            async with ClientSession() as session:
                async with await session.post(url, data=data, headers=head, timeout=90) as res:
                    resp = await res.text()
            info = json.loads(resp)
        return info

    @cover
    async def _save(self, owner_id, name, disc, video_id, tag, _hash, action_link, **kwargs):
        await sleeper(1, 3)
        params = {
            'action_link': action_link,
            'al': 1,
            'album_id': '',
            'desc': disc,
            'hash': _hash,
            'monetized': '',
            'no_comments': '',
            'oid': owner_id,
            'publish_later': '',
            'repeat': 0,
            'status_export': '',
            'tag': tag,
            'thumb_hash': '',
            'thumb_id': '',  # united:4_-174587092
            'title': name,
            'vid': video_id
        }

        if kwargs:
            params.update(kwargs)

        res = await self._vk.POST('https://vk.com/al_video.php?act=save_video_params', params)
        res.check('error save video')
        return True

    @cover
    async def _encode_progress(self, owner_id, video_id, _hash):
        params = {
            'al': 1,
            'hash': _hash,
            'need_tc': -1,
            'need_thumb': '',
            'oid': owner_id,
            'vid': video_id
        }
        for _ in range(60):
            await sleeper(2, 3)
            res = await self._vk.POST('https://vk.com/al_video.php?act=encode_progress', params)
            percents = res.check('error get progress video encode').payload()['percents']
            self._vk.print('video encode process =', percents)
            if percents == 100:
                break

        return True

    @cover
    async def add(self, owner_id, path, name='video', disc='', act_link='', **kwargs
                  ) -> List[Tuple[str, str]]:
        tag, _hash_save = await self._get_upload_box(owner_id)
        size = os.path.getsize(path)

        url = await self._get_upload_url(size, owner_id, tag)

        v = await self._up(url, path)
        video_id = v["video_id"]
        video_hash = v["video_hash"]

        if await self._encode_progress(owner_id, video_id, video_hash):
            await self._save(owner_id, name, disc, video_id, tag, _hash_save, act_link, **kwargs)
            return [('video', f'{owner_id}_{video_id}')]

        else:
            return []
