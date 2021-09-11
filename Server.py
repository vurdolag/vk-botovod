from cryptography.fernet import Fernet
from aiohttp import web
try:
    import ujson as json
except ImportError:
    import json

from time import time, time_ns
from Action import Action
from Utils import Utils, Global, logs, loop, VkMethodsError
from VkSession import VkSession


class Data:
    __slots__ = 'data_json', 'query', 'request'

    def __init__(self, data_json, query, request: web.Request = None):
        self.data_json = data_json
        self.query = query
        self.request: web.Request = request

    def __getattr__(self, item):
        res = self.data_json.get(item)
        if not res:
            res = self.query.get(item, '')
        return res


def get_data(func):
    async def wrapper(self, request: web.Request):
        #t1 = time()
        try:
            data = await request.content.read()
            data_json = {}
            if data:
                data = self.decript(data)
                data_json = json.loads(data.decode())

        except Exception as ex:
            logs.server_error()
            return self.error(f'error pars json data: {ex}')

        query = request.rel_url.query

        if self.key_api == query.get('key', ''):
            data = Data(data_json, query, request)
            try:
                res = await func(self, data)
                #print(time()-t1)
                return res
            except Exception as ex:
                logs.server_error()
                return self.error(f'Server error: {ex}')
        else:
            return self.error('error api key')

    return wrapper


class Server:
    __slots__ = 'key_api', 'app', 'temp', 'cipher', 'port'

    def __init__(self, key_api, encode_key, port=8080):
        self.key_api = key_api
        self.app = self.app_create()
        self.cipher = Fernet(encode_key)
        self.port = port

        self.temp = {}

    def encrypt(self, data: bytes) -> bytes:
        return self.cipher.encrypt(data)

    def decript(self, data: bytes) -> bytes:
        return self.cipher.decrypt(data)

    def toencjson(self, obj):
        try:
            return self.encrypt(json.dumps(obj).encode()).decode()
        except Exception as ex:
            logs.server_error()
            return self.encrypt(str(ex).encode()).decode()

    def __getattr__(self, item):
        return lambda obj: web.json_response({item: self.toencjson(obj)})

    def app_create(self):
        app = web.Application()
        app.add_routes(self.routes())
        return app

    def routes(self):
        return [
            web.get('/getlooptask', self.get_loop_tasks),
            web.get('/action/list', self.list_akk),
            web.get('/action/check', self.check_result),
            web.post('/action/add', self.add_account),
            web.post('/action', self.do_action),
            web.get('/getlog', self.getLog),
            web.get('/{logs:.*?.txt}', self.log_share)
        ]

    def run(self):
        web.run_app(self.app, port=self.port)

    def add(self, *args):
        [self.app.on_startup.append(startup) for startup in args]
        return self

    @get_data
    async def log_share(self, data: Data):
        path = data.request.path
        with open(path[1:], encoding="utf-8") as f:
            file = f.read()
        return self.response(file)

    @get_data
    async def getLog(self, data: Data):
        log_data = Utils.log_list[-30:]
        Utils.log_list = []
        return self.log(log_data)

    def get_session(self, login, act, params):
        if not act:
            session = Global.AllVkSession.get(login)

        else:
            session = Global.AllActionVk.get(login)
            if not params.get('recursion') is None:
                params.update({'recursion': False})

        return session

    def pars_action_func(self, method: str, session):
        m = method.split('.')
        if len(m) > 1:
            for i in m[:-1]:
                session = getattr(session, i)

        return getattr(session, m[-1])

    @get_data
    async def do_action(self, data: Data):
        login = data.login
        method = data.method
        params = data.params
        t = data.timer
        timer = t if t else 0

        if params:
            assert isinstance(params, dict)

        assert method, 'error method'
        assert login, 'error login'

        if method.startswith('_'):
            return self.error(f'This method is not supported: {method}')

        session = self.get_session(login, data.act, params)

        if not session:
            return self.error(f'Not have session for this login: {login}')

        name = f'{login}{time_ns()}'
        func = self.pars_action_func(method, session)

        loop.add(self.server_task(name, func, params, method), timer)

        return self.response(name)

    @get_data
    async def get_loop_tasks(self, data: Data):
        temp = []
        for task in loop.task:
            t = task[0].cr_frame.f_locals.get('self', '')
            if isinstance(t, Action):
                l = str(task[0].cr_frame)
                l = l[l.rindex('\\\\')+2:-1]
                t = (l, t.vk.login, t.vk.id, t.vk.name, task[1])
                temp.append(t)

        return self.response(temp)

    @get_data
    async def check_result(self, data: Data):
        name = data.name
        if not name:
            return self.error('not have target name')

        resp = self.temp.get(name)
        if not resp is None:
            del self.temp[name]
            return self.response(resp[1]) if resp[0] == 'response' else self.error(resp[1])

        else:
            return self.response(name)

    @get_data
    async def add_account(self, data: Data):
        session = VkSession(data.login, data.password, data.user_agent, data.proxy)

        if data.params:
            result = await session.auth(**data.params)
        else:
            result = await session.auth()

        return result


    @get_data
    async def list_akk(self, data: Data):
        return self.response([[x.login, x.id, x.name]
                              for x in Global.AllVkSession.values()
                              if x.methods.working and x.is_auth])

    async def server_task(self, name: str, func, params: dict, method: str = '') -> bool:
        try:
            if func.__name__ == 'cover_inner':
                params['from_server'] = True

            if params:
                resp = await func(**params)

            else:
                resp = await func()

            self.temp[name] = ('response', resp)
            return True

        except Exception as ex:
            logs.server_error()

            if isinstance(ex, VkMethodsError):
                ex_dict = ex.as_dict()
                ex_dict['method'] = method
                self.temp[name] = ('error', ex_dict)

            else:
                self.temp[name] = ('error', str(ex))

            return False



