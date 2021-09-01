
from VkSession import VkSession
from Utils import pars, pars_int, logs, DB
import RegExp as RE

import re
try:
    import ujson as json
except ImportError:
    import json
from typing import Coroutine, Union, List, Tuple


async def async_false():
    return False


async def async_true():
    return False


class Like:
    """Константы для like"""
    wall_one = 'wall_one'  # при переходе на страницу поста
    wall_page = 'wall_page'  # на странице сообщества
    feed_recent = 'feed_recent'  # из новостей без умной ленты
    feed_top = 'feed_top'  # из новостей с умной лентой
    photo_viewer = 'photo_viewer'  # фото
    videoview = 'videoview'  # видео

    @classmethod
    def pars_type(cls, id_post):
        if 'wall' in id_post:
            return cls.wall_one
        if 'photo' in id_post:
            return cls.photo_viewer
        if 'video' in id_post:
            return cls.videoview


class CommentPost:
    __slots__ = ('id', 'user_id', 'post_id', 'text', 'like_count', 'content',
                 'comment_id', 'like_comment_hash', 'vk')

    def __init__(self, _id: list, user_id: list, post_id: list, text: str,
                 like_count: list, content: list, comment_id: str,
                 like_comment_hash: str, vk: VkSession):
        self.id: str = pars(_id)
        self.user_id: str = pars(user_id)
        self.post_id: str = pars(post_id)
        self.text: str = text
        self.like_count: int = pars_int(like_count)
        self.content: List[Tuple[str, str]] = content
        self.comment_id: str = comment_id
        self.like_comment_hash: str = like_comment_hash

        self.vk: VkSession = vk

    def __str__(self):
        return self.id

    def like(self) -> Coroutine:
        return self.vk.methods.like(self.id, self.like_comment_hash)


class Post:
    __slots__ = ('id', 'owner_id', 'hash_view', 'orig_post_id', 'text', 'content', 'source',
                 'like_count', 'repost_count', 'view_count', 'comment_count', 'like_hash',
                 'real_len_comment', 'hash_comment', 'is_fix', 'is_vk_ads',
                 'from_feed', 'vk', 'comments', 'is_feed_top')

    def __init__(self, _id: str, hash_view: list, orig_post_id: list,
                 text: list, content: list, source: list, like_count: list,
                 repost_count: list, view_count: list, comment_count: list,
                 like_hash: str, comments: List[CommentPost], vk: VkSession,
                 hash_comment: str, is_vk_ads: bool):

        self.id: str = _id
        owner_id = RE.d.findall(_id)
        self.owner_id: int = int(owner_id[0]) if owner_id else 0
        self.hash_view: str = pars(hash_view)
        self.orig_post_id: str = pars(orig_post_id)
        self.text: str = '\n'.join(text)
        self.content: List[Tuple[str, str]] = content
        self.source: str = pars(source)
        self.like_count = like_count
        self.repost_count: int = pars_int(repost_count)
        self.view_count: str = pars(view_count)
        self.comment_count: int = pars_int(comment_count)
        self.like_hash: str = like_hash
        self.real_len_comment: int = len(comments)

        self.hash_comment: str = hash_comment
        self.is_fix: bool = False
        self.is_vk_ads: bool = is_vk_ads
        self.from_feed: bool = False
        self.is_feed_top: bool = False

        self.vk: VkSession = vk
        self.comments: List[CommentPost] = comments

    def __str__(self):
        return self.id

    def like(self, like_from=Like.wall_one) -> Coroutine:
        _id = self.get_id_for_bd()
        if _id in DB.liked:
            return async_false()
        DB.liked.put(_id, sync=True)

        if like_from in (Like.feed_recent, Like.feed_top) and self.is_feed_top:
            like_from = Like.feed_top

        return self.vk.methods.like(self.id, self.like_hash, like_from)

    def repost(self, msg: str = '') -> Coroutine:
        return self.vk.methods.repost(self.id, msg)

    def comment(self, msg: str, reply_to_user: str = '0',
                reply_to_msg: str = '', attach: list = None) -> Coroutine:
        return self.vk.methods.comment_post(self.id, msg, reply_to_user,
                                            reply_to_msg, self.hash_comment, attach)

    def view(self) -> Coroutine:
        return self.vk.methods.view_post([self.id], [self.id], _hash_view=self.hash_view)

    def get_id_for_bd(self) -> str:
        return f'{self.vk.my_id}_{self.id}'


class User:
    __slots__ = ('vk', 'id', 'url_avatar', 'url_nick', 'name', 'gender',
                 'is_my_friend', 'is_my_subscriber', 'hash_accept', 'hash_decline')

    def __init__(self, vk: VkSession,
                 user_data: list,
                 is_my_friend: bool = False,
                 is_my_subscriber: bool = False):

        self.vk: VkSession = vk

        self.id: int = 0
        self.url_avatar: str = ''
        self.url_nick: str = ''
        self.gender: int = 0
        self.name: str = ''
        self.hash_accept: str = ''
        self.hash_decline: str = ''
        self.is_my_friend: bool = is_my_friend
        self.is_my_subscriber: bool = is_my_subscriber

        self._pars_user_data(user_data)

    def __str__(self):
        return f'{self.id} {self.name}'

    def _pars_user_data(self, user_data: list):
        self.id = user_data[0]
        self.url_avatar = user_data[1]
        self.url_nick = user_data[2]
        self.gender = user_data[3]
        self.name = user_data[5]
        if not self.is_my_friend:
            self.hash_accept = user_data[-1][0]
            self.hash_decline = user_data[-1][1]

    def accept(self) -> Coroutine:
        return self.vk.methods.friend_accept(self)

    def decline(self) -> Coroutine:
        return self.vk.methods.friend_decline(self)

    def del_out_request(self, to_black_list: bool = False) -> Coroutine:
        return self.vk.methods.del_friends_from_out_requests(self, to_black_list)

    def to_black_list(self) -> Coroutine:
        return self.vk.methods.add_user_to_black_list(self)

    def del_friend(self, to_black_list: bool = False) -> Coroutine:
        return self.vk.methods.del_friends(self, to_black_list)


class Group:
    __slots__ = 'vk', 'group_id', 'title', 'member_count', 'hash_group', 'type_group', 'photo'

    def __init__(self,
                 vk: VkSession,
                 group_id: int,
                 title: str = '',
                 member_count: int = -1,
                 hash_group: str = '',
                 type_group: str = '',
                 photo: str = ''):
        self.vk: VkSession = vk
        self.group_id: int = group_id
        self.title: str = title
        self.member_count: int = member_count
        self.hash_group: str = hash_group
        self.type_group: str = type_group
        self.photo: str = photo

    def __str__(self):
        return self.group_id

    def subscribe(self) -> Coroutine:
        return self.vk.methods.subscribe(str(self.group_id)[1:], self.hash_group if self.hash_group else '')


class Comment:
    """
    Объект комментария
    """
    post_reply = 'post_reply'
    comment_photo = 'comment_photo'

    __slots__ = 'id_post', 'reply', 'thread', 'link', 'type', 'from_id', 'onclick'

    def __init__(self, update: dict):
        self.id_post: str = ''
        self.reply: str = ''
        self.thread: str = ''
        self.link: str = ''
        self.type: str = ''
        self.from_id: str = ''
        self.onclick = ''
        self.pars(update)

    def pars(self, update: dict):
        link = update['link']

        link += '&'
        reply = re.findall(r'(?<=reply=).+?(?=&)', link)
        self.reply = reply[0] if reply else ''

        thread = re.findall(r'(?<=thread=).+?(?=&)', link)
        self.thread = thread[0] if thread else ''

        id_post = re.findall(r'(?<=com/).+?(?=\?)', link)
        if id_post:
            self.id_post = id_post[0]
        else:
            id_post = re.findall(r'(?<=com/).+?(?=&)', link)
            if id_post:
                self.id_post = id_post[0]

        from_id = re.findall(r'(?<=tion_id=").+?(?=")', update['title'])
        self.from_id = from_id[0][2:] if from_id else ''

        onclick = update.get('onclick')
        if onclick:
            self.onclick = onclick


class Event:
    """
    Объект событие, long poll, feed long poll
    """
    __slots__ = ('id', 'text', 'text_out', 'message_id', 'from_id', 'flag',
                 'attachments', 'attachments_out', 'time_stamp', 'update',
                 'message_from_user', 'message_from_chat', 'empty', 'from_feed',
                 'comment')

    def __init__(self, my_id: str):
        self.id: str = my_id
        self.text: str = ''
        self.text_out: str = ''
        self.message_id: str = ''
        self.from_id: str = ''
        self.flag: bool = False
        self.attachments: dict = {}
        self.attachments_out: dict = {}
        self.time_stamp: int = 0
        self.update: Union[str, list] = []
        self.message_from_user: bool = False
        self.message_from_chat: bool = False
        self.empty: bool = True
        self.from_feed: bool = False
        self.comment: Union[Comment, None] = None

    @staticmethod
    def clear_message(message: str) -> str:
        """
        Убирает мусор из комментария
        :param message:
        :return:
        """
        if re.findall(r'<b.*&b>', message):
            return ''
        a = re.sub(r'<span.*/span>', '', message)
        a = re.sub(r'&quot;', '"', a)
        return re.sub(r'<.*?>', '', a)

    def _pars_text_from_audio_msg(self, q: list):
        if len(q) >= 8 and q[0] in (4, 5) and not q[6] and q[7]:
            if q[0] == 4:
                q[0] = -1
                return q

            attach_list = self._get_attach_list(q[7])
            if attach_list and self._is_audio_msg(attach_list[0]):
                text = self._get_transcript_audio_msg(attach_list[0])
                if text:
                    q[0] = 4
                    q[6] = text
                    q[7] = {}
        return q

    def _pars_long_poll(self, q: list):
        q = self._pars_text_from_audio_msg(q)

        if q[0] == 4 and len(q) > 5:
            if q[2] > 100 and q[3] > 2000000000:
                self.message_from_chat = True
                self.from_id = q[3]
                self.empty = False
                return self

            if q[6] and q[2] in (33, 49, 2097185, 1, 17):
                self.message_from_user = True
                self.text = q[6]
                self.attachments = q[7]
                self.from_id = q[3]
                self.flag = True
                self.time_stamp = q[4]
                self.message_id = q[1]
                self.empty = False
                return self
        return self

    def _pars_feed(self, q: str):
        self.from_feed = True
        feed_update = json.loads(q)
        update_type = feed_update.get('type', '')
        if update_type in [Comment.post_reply, Comment.comment_photo]:
            self.text = self.clear_message(feed_update['text'])
            if not self.text:
                return self
            comment = Comment(feed_update)
            comment.type = update_type
            self.comment = comment
            self.from_id = comment.from_id
            self.empty = False
        return self

    def pars(self, update: Union[str, list], from_feed: bool = False, vk=None):
        """
        Создаёт события из update
        :param update: dict или str
        :param from_feed:
        :param vk
        :return:
        """
        self.update = update
        self.empty = True

        if not vk is None:
            self.log_update(from_feed, vk)

        return self._pars_feed(update) if from_feed else self._pars_long_poll(update)

    def _get_attach_list(self, q):
        try:
            return json.loads(q.get('attachments'))
        except:
            return []

    def _get_transcript_audio_msg(self, q):
        text = q.get("audio_message", {}).get("transcript")
        return text if text else ''

    def _is_audio_msg(self, q):
        return q.get("type", '') == 'audio_message' if q else False

    def get_audio_msg_url(self):
        attach = self._get_attach_list(self.attachments)
        if not attach:
            return ''

        data = attach[0]

        if self._is_audio_msg(data):
            return data.get("audio_message", {}).get("link_ogg", '')

        return ''

    def log_update(self, from_feed, vk):
        if from_feed:
            vk.logger(self.update, 'feed.txt')
        else:
            vk.logger(self.update, 'long_poll.txt')

    def answer(self, message: str):
        """
        :param message:
        :return:
        """
        self.text_out = message
        return self






