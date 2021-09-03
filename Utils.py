try:
    import ujson as json
except ImportError:
    import json
from aiohttp import ClientSession
import base64
import sys
import traceback
import re
import sqlite3
from time import strftime, time, time_ns, localtime
import random
from asyncio import sleep, create_task, Task, CancelledError, gather, get_event_loop
from typing import List, Tuple, Coroutine, Union
from fake_useragent import UserAgent
from typing import Dict
import os
from datetime import datetime
from tzlocal import get_localzone
import config
from RegExp import dq


def get_local_time_offset(time_zone_offset=3600 * 3):
    tz = get_localzone()
    d = datetime.now(tz)
    utc_offset = d.utcoffset().total_seconds()
    if utc_offset != tz:
        return time_zone_offset - utc_offset
    else:
        return time_zone_offset


TIME_OFFSET = get_local_time_offset()


class TimeBuffer:
    __slots__ = '_time_buffer_dict', 'key_prefix'

    def __init__(self, key_prefix: str = ''):
        self.key_prefix = key_prefix
        self._time_buffer_dict = {}

    async def _time_buffer(self, key, time_s):
        key = self.key_prefix + key
        val = self._time_buffer_dict.get(key)
        if not val:
            count, acc_time = 0, 0
        else:
            count, acc_time = self._time_buffer_dict.get(key)

        count += 1
        acc_time += round(time_s, 2)

        self._time_buffer_dict[key] = (count, acc_time)

        '''
        m = ''
        for i in self._time_buffer_dict.items():
            if i[1] != (0, 0):
                m += f' {i[0]:<12} = {i[1][0]:<4} {i[1][1]:<8}| '

        logs.time_buffer(f'{round(acc_time, 2):<5} ={m}')
        '''

        await sleep(acc_time)

        count, acc_time = self._time_buffer_dict[key]

        count -= 1
        if count - 1 < 0:
            acc_time = 0
            count = 0

        self._time_buffer_dict[key] = (count, acc_time)

    def __call__(self, key, time_s) -> Coroutine:
        return self._time_buffer(key, time_s)

    def __getattr__(self, item):
        return lambda time_s: self._time_buffer(item, time_s)


time_buffer = TimeBuffer()


def async_timer(func):
    async def wrapper(*args, **kwargs):
        t1 = time()
        r = await func(*args, **kwargs)
        print(func.__name__, round(time() - t1, 8), args[1] if len(args) >= 2 else '')
        return r

    return wrapper


def timer(func):
    def wrapper(*args, **kwargs):
        t1 = time()
        r = func(*args, **kwargs)
        print(func.__name__, round(time() - t1, 8))
        return r

    return wrapper


class VkMethodsError(Exception):
    __slots__ = 'msg', 'session', 'kwargs', 'locals'

    def __init__(self, msg: str, session=None, _locals=None, **kwargs):
        self.msg = msg
        self.session = session
        self.kwargs = kwargs
        self.locals: Dict[str, str] = _locals

    def __str__(self):
        s, t = '', ''
        if self.locals:
            for key, val in self.locals.items():
                if key.startswith('__'):
                    continue
                self.kwargs[key] = str(val)

        for key, val in self.kwargs.items():
            s += f'\t{key} -> {val}\n'

        if not self.session is None:
            t = (f'\tlogin -> {self.session.login}\n'
                 f'\tid -> {self.session.id}\n'
                 f'\tname -> {self.session.name}\n')

        return f'{self.msg.upper()}\n{t}{s}'

    def as_dict(self):
        if self.locals:
            for key, val in self.locals.items():
                if key.startswith('_'):
                    continue
                self.kwargs[key] = str(val)

        out_json = {'error_msg': self.msg}
        if not self.session is None:
            out_json.update({
                'login': self.session.login,
                'id': self.session.id,
                'name': self.session.name,
            })

        if self.kwargs:
            out_json.update(self.kwargs)

        return out_json

    def add_session(self, session):
        self.session = session
        return self


class Logger:
    """
    logging errors with full traceback

    logs = Logger()

    try:
        your code
    except:
        logs() # write error path ./logs/log.txt
        logs.name_log_file()  # write error path ./logs/name_log_file.txt

    logs("any_msg")  # write msg path ./logs/log.txt
    logs.name_log_file("any_msg")  # write msg path ./logs/name_log_file.txt
    """

    __slots__ = 'level', '_path'

    def __init__(self, _level=None, path='logs'):
        self.level = _level
        self._path = path

    def __getattr__(self, item):
        return lambda string='': self._logs(string, item + '.txt')

    def __call__(self, *args, **kwargs):
        self._logs(*args, **kwargs)

    def cool_trace(self, trace):
        t = trace.split('\n')
        out = []
        temp = ''
        path = sys.path[0].replace('\\', '/')
        for i in t:
            i = i.replace('\\', '/')
            if 'Traceback (most recent call last)' in i:
                continue
            if 'File "' in i and '", line ' in i:
                if path in i:
                    i = re.findall(r'/\w+\.py.+line \d+', i)[0]
                    i = re.sub(r'[^\w\d._ ]', '', i)
                temp += i + ' ->'
            else:
                temp += ' ' + i.strip()
                out.append(temp.strip())
                temp = ''

        return '\n\t'.join(out)

    def get_title(self):
        return f'> {strftime("%y-%m-%d %H:%M:%S", localtime(time() + TIME_OFFSET))} =>'

    def _logs(self, strings: str = '', name: str = 'logs_error.txt'):
        """
        Логер и отлов ошибок, печатает полный трейсбек
        :param strings:
        :param name:
        """
        path = f'{self._path}/{name}'
        log_string = ''

        if strings:
            log_string = f'{self.get_title()} {strings}\n'

        else:
            a = sys.exc_info()
            if a and a[0] is VkMethodsError:
                log_string = f'{self.get_title()} VkMethodsError {str(a[1])}'
                path = f'{self._path}/VkMethodsError.txt'
                #print(log_string)

            elif a and a[0] is KeyboardInterrupt or a[0] is CancelledError:
                pass

            else:
                trace = f'ERROR!\n\t{self.cool_trace(traceback.format_exc())}\n'
                log_string = f'{self.get_title()} {trace}'
                print(trace)

        if log_string:
            Utils.log_list.append(log_string)
        if len(Utils.log_list) > 30:
            Utils.log_list = Utils.log_list[-30:]

        with open(path, 'a', encoding='utf-8') as f:
            f.write(log_string)

    def log(self, string, name='log.txt'):
        self._logs(string, name)


logs = Logger()


def cover(func):
    async def cover_inner(*args, **kwargs) -> bool:
        from_server = kwargs.get('from_server')

        if from_server:
            del kwargs['from_server']


        try:
            return await func(*args, **kwargs)

        except VkMethodsError as ex:
            if from_server:
                raise ex
            logs()

        except:
            logs()

        return False
    return cover_inner


def save_info(vk):
    bd = sqlbd('akkinfo')
    info = bd.get(vk.login, sync=True)
    if not info:
        bd.put(vk.login, vk.id, vk.name, sync=True)

    if info and info[0] != (vk.login, int(vk.id), vk.name):
        bd.up(vk.login, user_id=vk.id, name=vk.name, sync=True)


_alphabet = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ".lower()


def convert_base(num, to_base=10, from_base=10) -> str:
    if isinstance(num, str):
        n = int(num, from_base)
    else:
        n = int(num)
    if n < to_base:
        return _alphabet[n]
    else:
        return convert_base(n // to_base, to_base) + _alphabet[n % to_base]


def get_time_hash():
    t_str = str(time_ns())
    return convert_base(t_str[:13], 36)


def brok_msg(msg: str):
    m = list(msg)
    l = len(m)
    count = int(l / 15) + 1
    s = 'йцукенгшщзхъэждлорпавыфячсмитьбю'
    p = [random.randint(0, l) for _ in range(count)]

    if not m:
        return msg

    for i in p:
        try:
            m[i] = random.choice(s)
        except IndexError:
            pass

    return ''.join(m)


def is_random(r: int) -> bool:
    # r = 0, 100 %
    return random.random() * 100 <= r


def rand(t=5, n=0) -> float:
    return random.random() * t + n


def find(string_data: str, string_start: str, string_end) -> List[str]:
    return re.findall(f"(?<={string_start}).*?(?={string_end})", string_data)


def pars(val: List[str]) -> str:
    return str(val[0]) if val else ''


def pars_int(val: List[str]) -> int:
    try:
        return int(pars(val))
    except ValueError:
        return 0


async def rnd_sleep(t=15, n=0):
    await sleep(rand(t, n))


async def sleeper(min_t=0, max_t=15):
    t = max_t - min_t
    await sleep(rand(t, min_t))


def open_data_answer():
    """
    Открывает базу для автоответчика
    :return:
    """
    with open('answer/EndPhrase.txt', encoding='utf-8') as f:
        end_answer_list = f.read().split(',,')

    with open('answer/text.txt', encoding='utf-8') as f:
        data = f.readlines()

    bot_data_base = []
    for x in data:
        if x.strip():
            dat = x.split('||')
            dat_q = dat[0].lower().split(',,')
            dat_q = f'({"|".join(dat_q[1:])})' if dat_q[0][0] == '#' else '(\\b' + '\\b|\\b'.join(dat_q) + '\\b)'
            bot_data_base.append((re.compile(dat_q), tuple(dat[1].split(',,'))))

    return tuple(bot_data_base), tuple(end_answer_list)


def del_key(_dict: dict, *keys: str):
    for key in keys:
        if not _dict.get(key) is None:
            del _dict[key]


class Cookie:
    __slots__ = '_session', 'path'

    def __init__(self, session, path):
        self._session = session
        self.path = path

    def update_all(self, cookies):
        self._session.cookie_jar.update_cookies(cookies)

    def load_and_set(self):
        cookie = self.load()
        self._session.cookie_jar.update_cookies(cookie)

    def load(self) -> dict:
        try:
            with open(self.path) as f:
                cookie = json.load(f)
            return cookie

        except FileNotFoundError:
            print(f"cookies error {self.path}")
            return {}

    def save(self):
        c = self.as_dict()
        if c.get('ref_page'):
            del c['ref_page']
        with open(self.path, 'w') as f:
            json.dump(c, f)

    def as_dict(self):
        cookie_dict = {}
        for key, cookie in self._session.cookie_jar._cookies.items():
            for j, i in cookie.items():
                cookie_dict[j] = i.value
        return cookie_dict

    def add(self, key_val_dict: dict):
        cookies = self.as_dict()
        cookies.update(key_val_dict)
        self.update_all(cookies)

    def delete(self, key):
        cookies = self.as_dict()
        if cookies.get(key):
            del cookies[key]
            self.update_all(cookies)


class Response:
    __slots__ = ('body', 'type', 'params', 'url', 'session')

    def __init__(self, data_str: str = '', url: str = '',
                 params: Dict[str, Union[str, int]] = None,
                 resp_type: str = 'POST',
                 session=None):
        self.body = data_str
        self.type = resp_type
        self.params = params
        self.url = url
        self.session = session
        self.log_resp()

    def __contains__(self, item):
        return item in self.body

    def __len__(self):
        return len(self.body)

    def check(self, msg: str = ''):
        params = f'{str(self.params)}' if self.params else ''

        if not self.session.methods.check_status(self):
            raise VkMethodsError('ACCOUNT IS BLOCKED OR NOT AUTH!!!',
                                 session=self.session,
                                 url=self.url,
                                 params=params,
                                 payload=self.body[:100])

        if self.type == 'POST':
            if not self.body.startswith(config.ok):
                try:
                    payload = self.payload()

                except:
                    payload = self.body[:100]

                raise VkMethodsError(msg,
                                     session=self.session,
                                     url=self.url,
                                     params=params,
                                     payload=payload)

        else:
            if not self.body:
                if not msg:
                    msg = f'error open url: {self.url}'

                raise VkMethodsError(msg,
                                     session=self.session,
                                     url=self.url)

        return self

    def find(self, reg_exp, func=None) -> List[str]:
        resp = reg_exp.findall(self.body)
        if func:
            resp = list(map(func, resp))

        return resp

    def find_first(self, reg_exp, func=None) -> str:
        resp = self.find(reg_exp, func)
        return resp[0] if resp else ''

    def json(self):
        return json.loads(self.body)

    def payload(self):
        return self.json()['payload'][1][0]

    def log_resp(self):
        if config.DEBUG:
            body = self.body
            if '{"payload":[' in self.body:
                body = str(json.loads(self.body)['payload'][1])

            t = (f'type = {self.type}\n\n'
                 f'url = {self.url}\n\n' 
                 f'params = {str(self.params)}\n\n'
                 f'body:\n{body}')

            n = self.url.split('/')[-1]
            n = re.sub(r'[\\/\?:]', '', n)

            if not self.session.login in os.listdir('logs/response/'):
                os.mkdir(f'logs/response/{self.session.login}/')

            with open(f'logs/response/{self.session.login}/{time_ns()}_{n}.txt', 'w') as f:
                f.write(t)


class VkApi:
    __slots__ = '_start', '_tasks', '_response', '_name', '_token_service', '_token_group', 'loop_task'

    def __init__(self):
        self._start: bool = False
        self._tasks: list = []
        self._response = {}
        self._name = 0
        self._token_service: str = config.token_service
        self._token_group: str = config.token_group
        self.loop_task = None

    @cover
    async def _execute_task(self, task: list):
        async with ClientSession() as session:
            async with await session.post('https://api.vk.com/method/' + task[1],
                                          params=task[2], timeout=30) as res:
                res = await res.read()
        self._response[task[0]] = res

        return True

    async def _get_response(self, url: str, params: dict) -> bytes:
        name = self._name
        self._name += 1
        self._tasks.append([name, url, params])
        for _ in range(150):
            await sleep(0.5)
            res = self._response.get(name, b'')
            if res:
                return res

        return b''

    async def send_message(self, user_id, msg):
        return await self._get_response('messages.send',
                                        {'random_id': random.randint(0, 100000000),
                                         'peer_id': user_id,
                                         'message': msg, 'v': '5.103',
                                         'access_token': self._token_group})

    async def get_friend_user(self, user_id: str) -> list:
        try:
            out = []
            for i in [0, 5000]:
                params = {
                    'user_id': user_id,
                    'count': 5000,
                    'offset': i,
                    'v': '5.103',
                    'fields': 'photo_200,last_seen',
                    'access_token': self._token_service
                }
                res = await self._get_response('friends.get', params)
                res = json.loads(res)['response']
                out.extend(res['items'])

                if res.get('count', 0) < 5000:
                    break

            return out

        except:
            return []

    async def get_user_info(self, user_id: int) -> dict:
        try:
            await sleep(random.random() + 0.5)
            params = {
                'user_ids': user_id,
                'v': '5.122',
                'fields': 'photo_200,last_seen',
                'access_token': self._token_group
            }
            res = await self._get_response('users.get', params)
            res = json.loads(res)

            if res.get('error'):
                logs.get_user_info_log(f'{user_id} {res}')

            return res['response'][0]

        except KeyError:
            return {'first_name': '', 'deactivated': 1}

    async def get_users_info(self, user_ids: list) -> list:
        try:
            users = []
            for i in range(0, len(user_ids), 300):
                await sleep(0.1)
                params = {
                    'user_ids': ','.join([str(x) for x in user_ids[i:i + 300]]),
                    'v': '5.122',
                    'fields': 'photo_200,last_seen',
                    'access_token': self._token_group
                }
                res = await self._get_response('users.get', params)
                res = json.loads(res)
                if res.get('error'):
                    logs.get_user_info_log(f'{res["error"]}')
                    continue

                users.extend(res['response'])

            return users

        except KeyError:
            return []

    async def get_members_group(self, owner_id, count=300):
        res = await self._get_response('groups.getMembers',
                                       {'group_id': owner_id, 'count': count, 'fields': 'photo_200',
                                        'v': '5.103', 'access_token': self._token_service})
        return res.decode()

    async def _loop(self):
        while True:
            if self._tasks:
                create_task(self._execute_task(self._tasks.pop(0)))
            await sleep(0.4)

    def start_loop(self):
        if not self._start:
            self._start = True
            self.loop_task = create_task(self._loop())


class Global:
    AllVkSession = {}
    AllActionVk = {}

    __slots__ = ()


class Loop:
    __slots__ = 'tasks', 'task_in_progress'

    def __init__(self):
        self.tasks: List[Tuple[Coroutine, Union[int, float]]] = []
        self.task_in_progress: List[Task] = []

    def add(self, func: Coroutine, time_waite: Union[int, float] = 0):
        if not time_waite:
            time_waite = time()
        else:
            time_waite += time()

        for index, task in enumerate(self.tasks):
            if task[1] < time_waite:
                self.tasks.insert(index, (func, time_waite))
                return

        self.tasks.append((func, time_waite))

    async def worker(self):
        while True:
            t1 = time()
            while self.tasks and self.tasks[-1][1] < t1:
                task = self.tasks.pop()
                self.task_in_progress.append(create_task(task[0]))
                self.del_done_tasks()

            await sleep(1)

    def del_done_tasks(self):
        [self.task_in_progress.remove(task) for task in self.task_in_progress if task.done()]

    def start(self):
        self.task_in_progress.append(create_task(self.worker()))
        return gather(*self.task_in_progress)


loop = Loop()


class Utils:
    """
    сборник полезных методов
    """
    log_list = []

    iam_token = ''
    token_time = 0

    _last_time = time()

    @staticmethod
    async def get_iam_token():
        """
        записывает Яндекс iam_token в переменную Utils.iam_token
        :return:
        """
        try:
            if not Utils.iam_token or time() - Utils.token_time > 3600*6:
                Utils.token_time = time()
                params = {"yandexPassportOauthToken": config.ya_token}
                async with ClientSession() as session:
                    async with await session.post('https://iam.api.cloud.yandex.net/iam/v1/tokens',
                                                  params=params, timeout=30) as res:
                        res = await res.read()

                json_data = json.loads(res.decode('utf-8'))
                Utils.iam_token = json_data.get('iamToken', '')

            return Utils.iam_token

        except:
            Utils.iam_token = ''
            logs()
            return ''

    @staticmethod
    async def moderation_img(url_img: str, r: bool = True):
        """
        модерация фото: порн, кровь-кишки, текст, водяной знак
        :param url_img: str, ссылка на фото
        :param r: выход из рекурсии
        :return:
        """
        await time_buffer('moderation', random.random() * 2 + 1)  # вызов не раньше чем через N секутд

        try:
            logs(url_img, name='log_moder_img.txt')
            async with ClientSession() as session:
                async with await session.get(url_img) as res:
                    img = await res.read()

            img = base64.b64encode(img).decode('utf-8')
            data = {
                "folderId": "b1gb9k5cliueoqc4sg0t",
                "analyze_specs": [{
                    "content": img,
                    "features": [{
                        "type": "CLASSIFICATION",
                        "classificationConfig": {
                            "model": "moderation"
                        }
                    }]
                }]
            }
            data = json.dumps(data)

            iam_token = await Utils.get_iam_token()

            headers = {"Authorization": f"Bearer {iam_token}"}
            async with ClientSession() as session:
                async with await session.post('https://vision.api.cloud.yandex.net/vision/v1/batchAnalyze',
                                              data=data, headers=headers, timeout=30) as res:
                    res = await res.read()
            res = json.loads(res.decode('utf-8'))
            res = res['results'][0]['results'][0]['classification']['properties']
            d = {}
            for i in res:
                d[i['name']] = i['probability']

            logs(str(d), name='log_moder_img.txt')
            return d

        except:
            logs()
            await Utils.get_iam_token()
            if r:
                return await Utils.moderation_img(url_img, False)

            return {}

    @staticmethod
    async def voice_to_text(voice: str) -> str:
        """
        Аудио сообщение в текст
        :param voice: str, ссылка на аудио файл
        :return:
        """
        logs(voice, name='log_voice_to_text.txt')
        try:
            async with ClientSession() as session:
                async with await session.get(voice) as res:
                    voice = await res.read()

            iam_token = await Utils.get_iam_token()

            params = {
                'topic': 'general',
                "folderId": "b1gb9k5cliueoqc4sg0t",
                'lang': 'ru-RU'}
            headers = {"Authorization": f"Bearer {iam_token}"}
            async with ClientSession() as session:
                async with await session.post('https://stt.api.cloud.yandex.net/speech/v1/stt:recognize',
                                              data=voice, headers=headers, params=params, timeout=30) as res:
                    res = await res.read()
            res = json.loads(res.decode('utf-8'))

            result = res.get('result', '')
            logs(result, name='log_voice_to_text.txt')
            return result
        except:
            logs()
            return ''

    @staticmethod
    async def checker_text(text: str) -> str:
        """
        проверка текста на ошибки и замена
        :param text:
        :return:
        """
        await time_buffer('check', 1)
        url = f'https://speller.yandex.net/services/spellservice.json/checkText?text={text}'
        try:
            async with ClientSession() as session:
                async with await session.get(url, timeout=30) as res:
                    res = await res.read()

            result = json.loads(res.decode())
            if result:
                ind = 0
                tmp = ''
                for word in result:
                    tmp += text[ind:word['pos']] + word['s'][0]
                    ind = word['pos'] + word['len']
                tmp += text[ind:]
                return tmp

            else:
                return text
        except:
            logs()
            return text

    @staticmethod
    async def check_adult(img_url: str) -> bool:
        score = await Utils.moderation_img(img_url)
        return score.get('adult', 0) > 0.9 or score.get('gruesome', 0) > 0.9

    @staticmethod
    async def _translate(txt: str, lang='en-ru') -> str:
        print('\tyandex translate', txt)

        url = 'https://translate.api.cloud.yandex.net/translate/v2/translate'

        if not Utils.iam_token:
            Utils.iam_token = await Utils.get_iam_token()

        lang = lang.split('-')

        data = {
            "sourceLanguageCode": lang[0],
            "targetLanguageCode": lang[1],
            "texts": [txt],
            "folderId": "b1gb9k5cliueoqc4sg0t",
        }
        data = json.dumps(data)

        headers = {"Authorization": f"Bearer {Utils.iam_token}"}
        try:
            async with ClientSession() as session:
                async with await session.post(url, headers=headers, data=data, timeout=30) as res:
                    response = await res.read()

            response = json.loads(response.decode('utf-8'))

            out = ''
            for i in response.get('translations', []):
                out += i.get('text', '') + ' '

            return re.sub(r' {2,}', ' ', out).lower().capitalize()

        except:
            logs()
            return txt

    @staticmethod
    async def translate(txt: str, lang='en-ru') -> str:
        try:
            await time_buffer('translate', 30)

            head = {
                'User-Agent': UserAgent().chrome,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'ru-ru,ru;q=0.8,en-us;q=0.5,en;q=0.3',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'DNT': '1'}
            proxy = random.choice(config.proxy)

            async with ClientSession() as session:
                async with await session.post('https://fasttranslator.herokuapp.com/api/v1/text/to/text',
                                              params={'source': txt, 'lang': lang},
                                              headers=head, proxy=proxy,
                                              timeout=30) as res:
                    assert res.status == 200
                    resp = await res.json()

            msg = resp.get('data')
            assert resp.get('status') == 200 and msg
            return msg

        except:
            return await Utils._translate(txt, lang)


def async_cover_bd(func):
    def wrapper(self, *args, **kwargs):
        if kwargs.get('sync'):
            del kwargs['sync']
            return func(self, *args, **kwargs)

        event_loop = get_event_loop()
        return event_loop.run_in_executor(None, func, self, *args, kwargs)

    return wrapper


def cover_bd(func):
    @async_cover_bd
    def wrapper(self, *args, **kwargs):
        if isinstance(args, dict):
            kwargs = args
            args = ()
        if args and isinstance(args[-1], dict):
            kwargs = args[-1]
            args = args[:-1]

        connection = sqlite3.connect(self.path)
        result = False
        try:
            result = func(self, connection, *args, **kwargs)
            if isinstance(result, list) and not self.return_obj is None:
                result = [self.return_obj(*i) for i in result]

        except sqlite3.IntegrityError as ex:
            print(ex, func.__name__, *args)
        except:
            logs.bd()
        connection.close()
        return result

    return wrapper


class sqlbd:
    __slots__ = 'tabs', 'path', 'connection', 'return_obj'

    def __init__(self, tabs='userdata', return_obj=None):
        self.connection = None
        self.tabs = tabs
        self.return_obj = return_obj
        self.path = config.bd_path

        if self._check(self.tabs, sync=True):
            self.create_tabs(sync=True)

    def __contains__(self, item):
        ans = self.get(item, sync=True)
        if ans:
            a = ans[0][0]
            if isinstance(a, str) and not isinstance(item, str):
                item = str(item)
            if not isinstance(a, str) and isinstance(item, str):
                a = str(a)

            return item == a
        else:
            return False

    def _commit(self, conn, q):
        cursor = conn.cursor()
        cursor.execute(q)
        conn.commit()
        return cursor

    def _get(self, conn, q):
        cursor = conn.cursor()
        cursor.execute(q)
        return cursor

    @cover_bd
    def _check(self, conn, tabs):
        try:
            self._get(conn, f'SELECT * FROM {tabs}')
            return False
        except:
            return True

    @cover_bd
    def create_tabs(self, conn):
        q = config.bd_tabs.get(self.tabs)

        if q:
            self._commit(conn, q)
            print('Create tab', self.tabs)
            return True

        raise Exception(f'Create tab ERROR {self.tabs}')

    @cover_bd
    def get(self, conn, _id, item=None):
        select = '*' if item is None else item
        q = f'SELECT {select} FROM {self.tabs} where id = "{_id}";'
        return self._get(conn, q).fetchall()

    @cover_bd
    def get_all(self, conn, key=None, val=None):
        v = '' if key is None and val is None else f'where {key} = "{val}"'
        q = f'SELECT * FROM {self.tabs} {v};'
        return self._get(conn, q).fetchall()

    @cover_bd
    def get_between(self, conn, key, val1, val2):
        v = f'WHERE {key} BETWEEN {val1} AND {val2}'
        q = f'SELECT * FROM {self.tabs} {v};'
        return self._get(conn, q).fetchall()

    @cover_bd
    def put(self, conn, *args):
        x = '('
        for i in args:
            if isinstance(i, str):
                i = dq.sub("'", i)
                x += f'"{i}", '
            else:
                x += f'{i}, '
        x = x[:-2] + ')'

        q = f"INSERT INTO {self.tabs} VALUES {x};"
        self._commit(conn, q)
        return True

    @cover_bd
    def up(self, conn, _id, param='', **kwargs):
        if param and isinstance(param, dict):
            kwargs = param

        k = []
        for key, val in kwargs.items():
            val = dq.sub("'", str(val))
            k.append(f'{key} = "{val}"')

        q = f'UPDATE {self.tabs} SET {",".join(k)} WHERE id = "{_id}"'
        self._commit(conn, q)
        return True

    @cover_bd
    def delete(self, conn, command):
        q = f'DELETE FROM {self.tabs} WHERE {command};'
        return self._commit(conn, q).rowcount

    @cover_bd
    def castom(self, conn, code):
        return self._commit(conn, code)


class BotSleep:
    __slots__ = ('id', 'start_sleep', 'end_sleep')

    def __init__(self, _id, start_sleep, end_sleep):
        self.id = _id
        self.start_sleep = start_sleep
        self.end_sleep = end_sleep


class DataBase:
    already_add_user = sqlbd('already_add_user')
    max_answer = sqlbd('max_answer')
    new_repost = sqlbd('new_repost')
    is_english = sqlbd('is_english')
    is_moderation = sqlbd('moderation')
    group_joined = sqlbd('group_joined')
    liked = sqlbd('liked')
    bot_sleep = sqlbd('bot_sleep', BotSleep)

    __slots__ = ()


DB = DataBase()


class SmsActivate:
    def __init__(self, token: str):
        self.key = token

    async def get(self, url):
        try:
            async with ClientSession() as session:
                async with await session.get(url, timeout=25) as res:
                    r = await res.text()
            return r

        except:
            print('err get')
            return ''

    async def check_number_status(self, id_action):
        url = (f'https://sms-activate.ru/stubs/handler_api.php?api_key={self.key}&'
               f'action=getFullSms&'
               f'id={id_action}')
        r = await self.get(url)
        if 'FULL_SMS' in r:
            return r.split(':')[-1]
        return None

    async def number_action(self, id_action, status=8):
        url = (f'https://sms-activate.ru/stubs/handler_api.php?api_key={self.key}&'
               f'action=setStatus&'
               f'status={status}&'
               f'id={id_action}')
        return await self.get(url)

    async def get_number(self):
        url = (f'https://sms-activate.ru/stubs/handler_api.php?api_key={self.key}&'
               f'action=getNumber&'
               f'service=_vk&'
               'country=0')
        r = await self.get(url)
        if 'ACCESS_NUMBER' in r:
            r = r.split(':')
            return r[2], r[1]
        else:
            return None, None


def random_password():
    pattern = '0123456789qwertyuiopasdfghjklzxcvbnm@'

    password = ''
    for _ in range(random.randint(10, 20)):
        c = random.choice(pattern)
        if random.random() > 0.5:
            c = c.upper()
        password += c

    return password


class NotAnswerMsg:
    def __init__(self):
        pass

    async def create_new_answer(self, text):
        async with ClientSession() as session:
            admin_id = 0
            params = {
                'text': '',
                'user_id': admin_id,
                'group_id': 178894882,
                'send_in_api': 0,


            }
            await session.post('https://localhost/event')



