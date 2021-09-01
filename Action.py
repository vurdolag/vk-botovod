try:
    import ujson as json
except ImportError:
    import json
import random as rnd
import re
import RegExp as RE
import config
from time import time
from typing import List

from VkSession import VkSession
from Utils import (Logger, open_data_answer, Utils, is_random, rnd_sleep,
                   rand, cover, DB, loop, Global, sleeper, del_key, BotSleep, VkMethodsError)
from ObjClass import Like, Event, Comment, User

logs = Logger()


def _get_rnd_time_sleep_bot():
    t = int(time())
    t_i = t + rnd.randint(config.sleep_bot_iter_min, config.sleep_bot_iter_max)
    t_s = t_i + rnd.randint(config.sleep_bot_min, config.sleep_bot_max)
    return t_i, t_s


async def random_sleep_bot(user_id, _time) -> int:
    ans: List[BotSleep] = await DB.bot_sleep.get(user_id)
    if not ans:
        await DB.bot_sleep.put(user_id, *_get_rnd_time_sleep_bot())
        return int(_time)

    else:
        t = int(time())

        _t = t + _time

        t_s = ans[0].start_sleep
        t_e = ans[0].end_sleep

        if t > t_e:
            start_sleep, end_sleep = _get_rnd_time_sleep_bot()
            await DB.bot_sleep.up(user_id, start_sleep=start_sleep, end_sleep=end_sleep)

        if t_s < _t < t_e:
            return t_e - t + _time // 10
        else:
            return int(_time)


def account_status_check(func):
    @cover
    async def inner(cls, *args, **kwargs):
        await sleeper(1, 5)
        if not await cls.vk.check():
            cls.do.working = cls.vk.is_auth = False
            raise VkMethodsError("This is problem!", session=cls.vk)
        return await func(cls, *args, **kwargs)

    return inner


def recursions(**dec_kwargs):
    """@time: tuple(random_time, fix_time)"""
    t = dec_kwargs.get('time', (180, 180))

    def wrapper(func):
        async def inner(cls, *args, **kwargs):
            """
            cls Action
            @random_time: int(random_time)
            @fix_time: int(fix_time)
            """
            if kwargs.get('recursion', True) and cls.do.working:
                rnd_time = kwargs.get('random_time', t[0])
                fix_time = kwargs.get('fix_time', t[1])
                r = rand(rnd_time, fix_time)
                r = await random_sleep_bot(cls.vk.my_id, r)
                loop.add(inner(cls, *args, **kwargs), r)

            del_key(kwargs, 'recursion', 'random_time', 'fix_time')

            if not cls.do.working:
                return False

            return await func(cls, *args, **kwargs)

        return inner

    return wrapper


utils = Utils


class Action:
    """
    Коллекция методов действий бота, проверка новых друзей,
    случайные лайки репосты или определённых групп и пользователей и т.д.
    :param vk: VkSession, сессия бота
    :argument bot: BotAnswer, обработчик новых сообщений и комментариев
    """
    __slots__ = 'vk', 'bot', 'my_group_list', 'bd', 'already_del_dialog', 'log', 'print', 'do'

    def __init__(self, vk: VkSession, bd: DB = None):
        self.vk: VkSession = vk
        self.bot: BotAnswer = BotAnswer(vk)
        self.bd = DB if bd is None else bd

        self.my_group_list: list = []
        self.already_del_dialog: list = []

        self.do = vk.methods

        self.log = vk.logger
        self.print = vk.print

        Global.AllActionVk[vk.login] = self

    async def event_processing(self,
                               event: Event,
                               is_answer_message: bool = True,
                               is_answer_comment: bool = True,
                               is_leave_chat: bool = True
                               ) -> Event:
        """
        Оброботчик событий - сообщения, комментарии, выход из чатов
        :param event: Event, новое событие
        :param is_answer_message: bool, отвечать ли на новые сообщения
        :param is_answer_comment: bool, отвечать ли на новые комментарии
        :param is_leave_chat: bool, выходить ли из чатов если бота пригласят
        :return event: Event
        """
        if event.comment and is_answer_comment:
            # ответ на комментарии
            await self.bot.comment_answer(event)

        elif event.message_from_chat and event.from_id not in self.already_del_dialog and is_leave_chat:
            # выходит из новых чатов куда пригласили бота и удаляет историю
            self.already_del_dialog.append(event.from_id)
            await self.do.del_dialog(event.from_id)

        elif event.message_from_user and is_answer_message:
            # ответ на сообщения
            await self.bot.answer(event)
            if not event.empty:
                await self.do.send(event.from_id, event.text_out, msg_id=event.message_id)

        return event

    async def long_poll(self, feed: bool = True) -> bool:
        """Запуск обработчиков новых сообщений, комментариев и иных событий"""
        loop.add(self.do.long_poll(self.event_processing))
        if feed:
            loop.add(self.do.long_poll_feed(self.event_processing), 15)

        return True

    @recursions(time=(140, 200))
    @cover
    async def online(self):
        """симуляция активности для установки статуса онлайн"""
        url = rnd.choice([f'https://vk.com/id{self.vk.my_id}',
                          'https://vk.com/feed',
                          'https://vk.com/im',
                          'https://vk.com/groups',
                          'https://vk.com/friends',
                          f'https://vk.com/albums{self.vk.my_id}',
                          f'https://vk.com/club{rnd.randint(139674464, 199674464)}',
                          f'https://vk.com/audios{self.vk.my_id}',
                          'https://vk.com/video',
                          f'https://vk.com/id{rnd.randint(101626759, 591626759)}'])

        if is_random(50):
            resp = await self.vk.GET(url)
            resp.check()
            await sleeper(1, 10)

        return await self.do.set_online()

    async def _is_already_add_user(self, user_id):
        if user_id in self.bd.already_add_user:
            return True
        else:
            await self.bd.already_add_user.put(user_id)
            return False

    @cover
    async def _friend_is_ok(self,
                            user: User,
                            last_seen: int = 0,
                            moderation: bool = False,
                            has_avatar: bool = True
                            ) -> bool:

        info = await self.vk.api.get_user_info(user.id)
        user_last_seen = int(time() - info.get("last_seen", {'time': time()})['time'])

        if info.get("deactivated", 0):
            self.log(f'Юзер заблокирован или удалён: {user}')
            return False

        if has_avatar and RE.check_avatar.search(user.url_avatar):
            self.log(f'Без аватара: {user}')
            return False

        if last_seen and user_last_seen > last_seen:
            self.log(f'Слишком давно не заходил: {user}, {user_last_seen} > {last_seen}')
            return False

        if moderation and user.id not in self.bd.is_moderation:
            if await utils.check_adult(user.url_avatar):
                self.log(f"Неприемлимый аватар: {user}, {user.url_avatar}")
                return False

            else:
                await self.bd.is_moderation.put(user.id)

        return True

    @cover
    async def _check_new_friend(self,
                                user: User,
                                moderation: bool = True,
                                has_avatar: bool = True
                                ) -> bool:
        self.print('>', user)
        if await self._is_already_add_user(user.id):
            self.log(f'Юзер уже был: {user}')
            return False
        return await self._friend_is_ok(user, moderation=moderation, has_avatar=has_avatar)

    @cover
    async def _accept_or_decline_new_friend(self,
                                            all_decline: bool = False,
                                            moderation: bool = True,
                                            has_avatar: bool = True
                                            ) -> bool:
        await sleeper()
        self.log('Запуск проверки новых друзей')
        new_friends = await self.do.get_new_friend_list()

        count_friend = len(new_friends)

        if count_friend > 0:
            self.log(f'Новых друзей найдено: {count_friend}')

        else:
            self.log('Нет новых друзей')
            return False

        add = 0
        not_add = 0
        for friend in new_friends:
            if not all_decline and await self._check_new_friend(friend, moderation, has_avatar):
                add += 1
                await friend.accept()

            else:
                not_add += 1
                await friend.decline()

            await sleeper(5, 45)

        self.log(f'Друзей добавил: {add} из: {add + not_add}')

        return True

    @recursions(time=(7200, 2400))
    @account_status_check
    async def check_friend(self,
                           all_decline: bool = False,
                           moderation: bool = True,
                           has_avatar: bool = True):
        """
        В цикле проверяет новых друзей, добавляет или
        нет в зависимости от настроек
        all_decline - если истина отказывать всем
        moderation - проверка аватара на пошлятину
        has_avatar - должен быть аватар
        """
        await sleeper()
        return await self._accept_or_decline_new_friend(all_decline, moderation, has_avatar)

    @recursions(time=(18400, 7200))
    @account_status_check
    async def del_out_requests(self, to_black_list: bool = False) -> bool:
        """
        Удаляет исходящие заявки в друзья, может добавить в black_list
        """
        await sleeper()

        out_friends = await self.do.get_out_request_friends()

        offset, count_action = 0, 0

        if not out_friends:
            self.log('Нет исходящих заявок в друзья')
            return False

        for _ in range(5):
            offset += len(out_friends)

            for user in out_friends:
                await self._is_already_add_user(user.id)
                if await user.del_out_request(to_black_list):
                    count_action += 1

                await sleeper(3, 16)

                if to_black_list:
                    await user.to_black_list()

            await sleeper(3, 16)

            out_friends = await self.do.get_out_request_friends(offset)

            if not out_friends:
                break

        self.log(f'Удалил исходящих заявок в друзья: {count_action}')

        return True

    @recursions(time=(6400, 1200))
    @account_status_check
    async def reposter(self,
                       owner_ids: List[int],
                       msg: str = '',
                       is_group_user: bool = False,
                       random_repost: int = 10,
                       random_like: int = 10,
                       target: int = 0,
                       random_target: int = 66) -> bool:
        """
        Проверяет новые посты в целевой группе и делает репост
        :param random_target: вероятность для целевых групп в процентах
        :param target: id целевой группы (id < 0) или юзера (id > 0)
        :param random_like: вероятность лайка в процентах
        :param random_repost: вероятность репоста в процентах
        :param is_group_user: парсить посты из всех групп юзера если нет постов, из owner_id
        :param owner_ids: list, id-групп
        :param msg: str, подпись
        """
        await sleeper(5, 16)
        like_from = Like.feed_recent
        try:
            if is_group_user:
                like_from = Like.wall_page

                if not self.my_group_list:
                    groups = await self.do.get_list_group(self.vk.my_id)

                    for i in groups:
                        if len(i) >= 2:
                            self.my_group_list.append(i[2])

                owner_id = rnd.choice(self.my_group_list)
                await sleeper()

            else:
                owner_id = rnd.choice(owner_ids)

            posts = await self.do.get_post(owner_id)

            await sleeper(5, 16)

            if posts:
                for post in posts:
                    post_id_bd = post.get_id_for_bd()
                    if post_id_bd in self.bd.new_repost:
                        continue

                    await self.bd.new_repost.put(post_id_bd)

                    await self.do.view_posts(posts, post.id)

                    if is_random(random_repost):
                        await post.repost(msg)

                    else:
                        target_q = target and target == owner_id and is_random(random_target)
                        if is_random(random_like) or target_q:
                            await post.like(like_from)

                    break

        except:
            logs()

        return True

    @recursions(time=(4000, 1200))
    @account_status_check
    async def random_like_feed(self, target_post_id: str = '', target: int = 0) -> bool:
        """
        Лайк случайного поста из новостей
        :param target_post_id: str, если есть такой пост будет пролайкан в первую очередь
        :param target: str, если есть пост этой группа будет пролайкан в первую очередь
        """
        await sleeper(5, 16)
        try:
            self.print(f'random like feed start {target_post_id} {target}')

            posts = await self.do.get_post(count=10 if not target_post_id else 45)

            if not posts:
                raise VkMethodsError('not feed post', session=self.vk)

            await sleeper(1, 16)
            await self.do.view_posts(posts, random_view=10)
            await sleeper(1, 16)

            count = 0

            for post in posts:
                # лайк постов только из выбраной группы или юзера в ленте
                # или лайк только определенного поста
                if target == post.owner_id or target_post_id == post.id:
                    await self.do.view_posts(posts, post.id, 10)
                    await sleeper(5, 30)
                    await post.like(Like.feed_recent)
                    count += 1

            if not count and (target or target_post_id):
                self.print(f'not target post {target_post_id} or target_owner {target} in feed')

            if not count:
                # без опций, лайк одного случайного поста из лены, и просмотр случайных постов
                post = rnd.choice(posts)
                await self.do.view_posts(posts, post.id, 33)
                if is_random(40):
                    await sleeper(5, 30)
                    await post.like(Like.feed_recent)

            return True

        except:
            logs()
            return False

    @recursions(time=(21600, 3600))
    @account_status_check
    async def del_bad_friends(self, moderation: bool = True,
                              last_seen: int = 3600 * 24 * 14) -> bool:
        """
        Удаляет заблокированных друзей или тех кто давно не заходил
        :param moderation: bool, проверять на порн аватары друзей
        :param last_seen: int, количество секунд с последнего онлайна друга
        :return:
        """
        await sleeper(1, 10)
        try:
            self.log(f"Запуск удаления плохих друзей")
            friend_list = await self.do.get_list_friends()
            if not friend_list:
                self.log('Нет друзей')
                return False

            rnd.shuffle(friend_list)

            ind = 0
            self.log(f"Найдено друзей: {len(friend_list)}")

            for friend in friend_list:
                if not await self._friend_is_ok(friend, last_seen, moderation):
                    await friend.del_friend()
                    await self._is_already_add_user(friend.id)
                    ind += 1

                    await sleeper(10, 30)

            self.log(f"Удалено друзей: {ind} из {len(friend_list)}")

        except:
            logs()

        return True

    async def del_bad_group(self, ignore_group: List[str] = None,
                            is_del_bad_group: bool = False) -> bool:
        """
        удаляет группы: заблокированые, с закрытой статистикой,
        если ид бота не входит в 100 первых юзеров группы
        """
        if not ignore_group:
            ignore_group = config.ignore_group

        log_name = f'groups/check_group{self.vk.login}.txt'

        await sleeper(5, 20)

        groups = await self.do.get_list_group()

        if not groups or not isinstance(groups, list):
            return False

        rnd.shuffle(groups)

        ind = 0
        for group in groups:
            if group[2] in ignore_group:
                continue

            if 'deactivated' in group[4]:
                resp = await self.do.leave(group[2], group[7])
                self.print('del deactivated group', resp, group[2])
                self.log(f'Deactivated group: {group[2]}', name=log_name)
                ind += 1
                await sleeper(5, 20)
                continue

            try:
                res = await self.vk.api.get_members_group(group[2])
                res = json.loads(res)

                if res.get('error', 0):
                    if res['error'].get('error_code') == 15:
                        self.print(res['error'].get("error_msg", 'non'), group[2])
                        resp = await self.do.leave(group[2], group[7])
                        self.print('del group', resp)
                        self.log(f"Close members group: {group[2]}", name=log_name)
                        ind += 1
                        await sleeper(5, 20)
                        continue

                res = res["response"]['items']

                data: List[int] = [j["id"] for j in res if not j.get("deactivated")]

                if is_del_bad_group and int(self.vk.my_id) not in data[:101]:
                    resp = await self.do.leave(group[2], group[7])
                    self.print('del bad group', resp, group[2])
                    self.log(f'Bad group: {group[2]}', name=log_name)
                    ind += 1
                    await sleeper(5, 20)
                    continue

                self.log(f'Good group: {group[2]}', name=log_name)

            except:
                logs(f'err -> {group}')
                logs()

        self.print('END')
        self.log(f'Final {ind} // {len(groups)}', name=log_name)

        return True

    @recursions(time=(5000, 600))
    @account_status_check
    async def rand_group_join(self, groups: List[int]):
        """вступает в случайные группы из списка"""

        rnd.shuffle(groups)
        for group in groups:
            g = f'{self.vk.my_id}_{group}'
            if g in self.bd.group_joined:
                continue
            await self.bd.group_joined.put(g)

            self.print('random sub group start', group)

            if await self.do.subscribe(group):
                self.log(f"sub Ok {group}", name='JGroup.txt')
                break
            self.log(f"sub None {group}", name='JGroup.txt')

            await sleeper(120, 180)

        return True


class DataAnswer:
    """
    общий класс для экземпляров BotAnswer
    """
    base, end = open_data_answer()

    __slots__ = ()


data_answer = DataAnswer()


class BotAnswer:
    """
    Обработчик сообщений, основной метод answer и comment_answer
    :param vk: VkSession сессия бота
    :argument max_answer_count: максимальное количество ответов, которое даёт бот, далее никак не реагирует
    """
    __slots__ = 'vk', 'max_answer_count', 'bd', 'data', 'log', 'do'

    def __init__(self, vk: VkSession):
        self.vk: VkSession = vk
        self.max_answer_count = 10

        self.bd = DB
        self.data = data_answer

        self.do = vk.methods

    async def answer(self, event: Event) -> Event:
        """
        Метод позволяющий отвечать на события сообщения и комментарии
        :param event:
        :return event:
        """
        # подготавливает текст сообщения, получает из базы значения счетчика ответов - max_answer
        message_text, max_answer, max_flag = await self.preparation(event)

        # если превышен лимит ответов возращается пустой Event
        if max_answer > self.max_answer_count:
            if is_random(85):
                event.empty = True
                return event

        # если есть вложение и это аудио сообщение, конвертируется техт
        if event.attachments:
            message_text = await self.voice_message_processing(event, message_text, max_answer)

        # проверяет является ли сообщение на английском и переводит
        message_text, english = await self.is_english(message_text, event.from_id)

        # генерирует ответ, возращает ответ и шаблон на котором сработал
        target_answer, target_pattern = await self.get_answer(message_text.lower())

        # если есть *fname* меняет на имя юзера
        target_answer = await self.insert_name(event.from_id, target_answer)

        # если счетчик ответов max_answer > self.max_answer_count возращает фразу с окончание диалога,
        # бот больше не отвечает и не читает сообщения
        target_answer = self.get_end_answer(target_answer, max_answer)

        # если сообщение было на английском переводит ответ на русском на английский
        if english and target_answer:
            # проверяет правильность исходящего сообщения для правильного перевода
            target_answer = await utils.checker_text(target_answer)
            # перевод
            target_answer = await utils.translate(target_answer, 'ru-en')

        # записыват ключевые переменные в различные логи
        self.log_stat(event, message_text, target_answer, max_flag)

        return event.answer(target_answer)

    async def comment_answer(self, event: Event) -> Event:
        """
        Метод обрабатывает новые комментарии
        :param event:
        :return event:
        """
        id_post = event.comment.id_post
        from_id = event.comment.from_id
        reply = event.comment.reply

        max_answer = (await self.get_max_answer(from_id))[0]

        if event.from_feed and await self.comment_moderation(event):
            return event

        if RE.comment_check.findall(event.text):
            return event

        if max_answer > 3:
            return event

        await self.put_max_answer(from_id, max_answer)

        await self.answer(event)

        if not event.text_out:
            return event

        await sleeper(90, 240)

        if event.comment.type == Comment.post_reply:
            await self.do.comment_post(id_post, event.text_out, from_id, reply)

        elif event.comment.type == Comment.comment_photo:
            await self.do.comment_photo(id_post, event.text_out, from_id)

        return event

    async def comment_moderation(self, event: Event) -> bool:
        await rnd_sleep(30, 30)

        if 'photo' in event.comment.id_post:
            return False
        else:
            comment_images, hash_del = await self.do.get_image_comment_wall(event.comment.id_post,
                                                                            event.comment.reply)
        await rnd_sleep(1, 6)

        if hash_del and re.findall(r"h.*?t.*?t.*?p.*?s*.*?:.*?/.*?/*.*?", event.text.lower()):
            await rnd_sleep(30, 30)
            await self.do.del_comment(event.comment.id_post,
                                      event.comment.reply, hash_del)
            return True

        if comment_images and hash_del:
            for img_url in comment_images:
                await rnd_sleep(30, 30)
                if await utils.check_adult(img_url):
                    await self.do.del_comment(event.comment.id_post,
                                              event.comment.reply, hash_del)
                    return True

        return False

    async def voice_message_processing(self, event: Event, message_text: str, max_answer: int) -> str:
        """
        обработка голосовых сообщений
        :param event: событие
        :param message_text: подготовленный текст
        :param max_answer: счетчик ответов бота
        :return message_text: аудио сообщение в текст или неизменённое входящие сообщение
        """
        audio_url = event.get_audio_msg_url()

        if not message_text and audio_url and max_answer < 7:
            for _ in range(3):
                await sleeper(3, 16)
                voice_text = await self.do.voice_to_text(event.message_id, event.from_id)
                if voice_text:
                    break
            else:
                voice_text = await utils.voice_to_text(audio_url)

            message_text = voice_text.lower()

        return message_text

    async def get_answer(self, message_text: str) -> (str, List[str]):
        """
        Ищет с помощью регулярных выражений ответ базе answer/text.txt
        :param message_text:
        :return ответ, шаблон: (str, list)
        """
        message = message_text[:140]
        answers = []
        for _ in range(2):
            for answer in self.data.base:
                try:
                    found_answer = answer[0].findall(message)
                except:
                    logs()
                    continue

                if found_answer:
                    answers.append([answer[0], rnd.choice(answer[1]), found_answer])

            if answers:
                break
            else:
                message = await utils.checker_text(message)

        # логирует все найденые варианты ответа
        self.vk.logger(f'{message} -> {answers}', name='msg/all_var_answer.txt')

        try:
            target_answer = answers[0][1]
            target_pattern = answers[0][0]

        except IndexError:
            target_answer = ''
            target_pattern = []

        return target_answer, target_pattern

    def get_end_answer(self, target_answer: str, max_answer: int) -> str:
        """
        Возвращает сообщение для завершения диалога если max_answer ==  self.max_answer_count
        :param target_answer: str
        :param max_answer: int
        :return: str
        """
        return rnd.choice(self.data.end) if max_answer == self.max_answer_count else target_answer

    async def is_english(self, message_text: str, user_id: str) -> (str, bool):
        """
        Проверяет является ли строка на английском и переводит
        :param user_id:
        :param message_text:
        :return: (str, bool)
        """
        english = False

        msg = re.sub(r'[^А-ЯЁа-яёA-Za-z]', '', message_text)
        check_on_english = re.findall(r'[^А-ЯЁа-яё]', msg)
        if len(check_on_english) == len(msg) and msg and check_on_english:
            await self.bd.is_english.put(user_id)
            message_text = await utils.translate(message_text)
            english = True

        return message_text, english

    async def insert_name(self, user_id: str, message_text: str) -> str:
        """
        вставка имени в шаблон *fname*
        :param user_id:
        :param message_text:
        :return:
        """
        if '*fname*' in message_text:
            name = await self.vk.api.get_user_info(user_id)
            message_text = re.sub(r'\*fname\*', name['first_name'], message_text)

        return message_text

    async def preparation(self, event: Event) -> (str, int, str):
        """
        Обработка сообщения, получение счетчика ответов max_answer из базы
        :param event:
        :return:
        """
        message_text = re.sub(r' {2,}', ' ', event.text).lower().strip()
        max_answer, max_flag = await self.get_max_answer(event.from_id)
        await self.put_max_answer(event.from_id, max_answer)
        return message_text, max_answer, max_flag

    def log_stat(self, event: Event, message_text: str, target_answer: str, max_flag: str):
        """
        Логер сообщений
        :param event:
        :param message_text:
        :param target_answer:
        :param target_pattern:
        :param max_flag:
        """
        info = f', {event.from_id}, {max_flag}'
        msg_path = f'msg/{self.vk.login}.txt'

        self.vk.print(event.from_id, max_flag, 'msg <-', message_text)
        self.vk.logger(f'{info} <- {message_text}', name=msg_path)

        if not target_answer and message_text:
            self.vk.logger(f'{info} <- {message_text}', name='msg_not_answer.txt')
        else:
            self.vk.print(event.from_id, max_flag, 'msg ->', target_answer)
            self.vk.logger(f'{info} -> {target_answer}', name=msg_path)

        if event.attachments:
            self.vk.logger(f'{info} <- {event.attachments}', name='msg_atta.txt')

    async def get_max_answer(self, user_id: str) -> (int, str):
        q = f'{self.vk.my_id}_{user_id}'
        max_answer = await self.bd.max_answer.get(q, 'count')

        if max_answer:
            max_answer = max_answer[0][0]
            max_flag = max_answer if max_answer <= self.max_answer_count else "max"
        else:
            max_answer = 0
            max_flag = 0

        return max_answer, max_flag

    async def put_max_answer(self, user_id: str, max_answer: int) -> None:
        q = f'{self.vk.my_id}_{user_id}'
        if max_answer == 0:
            await self.bd.max_answer.put(q, 1)
        else:
            await self.bd.max_answer.up(q, count=max_answer + 1)
