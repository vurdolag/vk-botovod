import sys
from typing import List, Dict


DEBUG: bool = False


class Url:
    like = 'https://vk.com/like.php'
    im = 'https://vk.com/al_im.php'
    group = 'https://vk.com/al_groups.php'
    public = 'https://vk.com/al_public.php'
    photo = 'https://vk.com/al_photos.php'
    wall = 'https://vk.com/al_wall.php'
    wkview = 'https://vk.com/wkview.php'
    hints = 'https://vk.com/hints.php'
    reports = 'https://vk.com/reports.php'
    page = 'https://vk.com/al_page.php'
    friends = 'https://vk.com/friends'
    al_friends = 'https://vk.com/al_friends.php'
    settings = 'https://vk.com/al_settings.php'
    search = 'https://vk.com/al_search.php'
    docs = 'https://vk.com/docs.php'
    al_photos = 'https://vk.com/al_photos.php'


# group can't delete
ignore_group: List[int] = [

]

path_cookies: str = 'cookies/'
ok: str = '{"payload":[0'

# vk token
token_service: str = ''
token_group: str = ''

# vk user_id for critical event
admin_alarm: str = ''

# yandex.ru token for moderation image
ya_token: str = ''

# sms-activate.ru token for unblock account
sms_activate_token: str = ''

# login:password@ip:port
proxy: List[str] = [

]

bd_path: str = ''

bd_tabs: Dict[str, str] = {
    "already_add_user": 'CREATE TABLE "already_add_user" ("id" INTEGER UNIQUE);',
    "max_answer": 'CREATE TABLE "max_answer" ("id" VARCHAR(30) UNIQUE, "count" INTEGER);',
    "new_repost": 'CREATE TABLE "new_repost" ("id" VARCHAR(30) UNIQUE);',
    "is_english": 'CREATE TABLE "is_english" ("id" INTEGER UNIQUE);',
    "akkinfo": 'CREATE TABLE "akkinfo" ("id" INTEGER UNIQUE, "user_id" INTEGER, "name" VARCHAR(30));',
    "moderation": 'CREATE TABLE "moderation" ("id" INTEGER UNIQUE);',
    "group_joined": 'CREATE TABLE "group_joined" ("id" INTEGER UNIQUE);',
    "liked": 'CREATE TABLE "liked" ("id" VARCHAR(30) UNIQUE);',
    "bot_sleep": 'CREATE TABLE "bot_sleep" ("id" INTEGER UNIQUE, "start_sleep" INTEGER, "end_sleep" INTEGER)'
        }

# server
encode_key: bytes = b''
server_key_api: str = ''


sleep_bot_min: int = 60*15
sleep_bot_max: int = 60*60

sleep_bot_iter_min: int = 60*90
sleep_bot_iter_max: int = 60*60*4




