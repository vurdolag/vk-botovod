
import RegExp as RE
from VkSession import VkSession
from ObjClass import Post, CommentPost
from Utils import pars, pars_int, async_timer

import re
try:
    import ujson as json
except ImportError:
    import json
from lxml import etree
import lxml.html
from aiohttp import ClientSession
from typing import List


def _get_tree(el):
    x = etree.tostring(el[0])
    return lxml.html.fromstring(x)


def _get_div(i):
    return '' if i == 0 else f'div[{i}]/'


def _get_post(page_data):
    tree = lxml.html.fromstring(page_data)
    return tree.xpath("//div[starts-with(@id, 'post')]")


def _pars_js_photo(data_js: str) -> dict:
    js_obj = re.findall(r'{.*}', data_js)
    if not js_obj:
        return {}
    try:
        return json.loads(js_obj[0].replace('&quot;', '"').replace('&amp;', '&'))
    except ValueError:
        return {}


async def _get_content_url(_id: str, data: str) -> str:
    if 'photo' in _id:
        js = _pars_js_photo(data)
        if js:
            return js['temp']['x']

    elif 'doc' in _id:
        if _id[0] != '/':
            _id = f'/{_id}'

        async with ClientSession() as session:
            async with await session.get(f'https://vk.com{_id}', timeout=20) as res:
                resp = await res.text()
        tree = lxml.html.fromstring(resp)
        url_doc = tree.xpath('//center//@src')
        return url_doc[0] if url_doc else ''

    elif 'video' in _id:
        return data

    else:
        return "i don't know"


async def _pars_content(tree, path: str = '') -> list:
    if not path:
        path = f'//*[@class="wall_text"]'

    content_js = tree.xpath(f'{path}//@onclick')
    content_href = tree.xpath(f'{path}//@href')

    content_href = [x for x in content_href if 'video' in x or 'doc' in x]

    content = []
    for js in content_js:
        if 'return showPhoto' in js:
            _id = pars(re.findall(r"(?<=showPhoto\().*?(?=,)", js))
            _id = pars(re.findall(r'-*\d+_\d+', _id))
            content.append(('photo' + _id, js))

        elif 'return showVideo' in js:
            _id = pars(re.findall(r"(?<=showVideo\().*?(?=,)", js))
            _id = pars(re.findall(r'-*\d+_\d+', _id))
            for href in content_href:
                if _id in href:
                    content.append(('video' + _id, href))
                    break

        elif 'Page.showGifBox' in js:
            i = RE.d.findall(js)
            _id = f'{i[1]}_{i[0]}'
            for href in content_href:
                if _id in href:
                    content.append(('doc' + _id, href))
                    break

    return [(x[0], await _get_content_url(*x)) for x in content]


async def _pars_comments(orig_tree, vk):
    c = orig_tree.xpath('//*[@class="replies"]')
    if not c:
        return []

    tree = _get_post(etree.tostring(c[0]))

    if not tree:
        return []

    comments = []
    tree = [lxml.html.fromstring(etree.tostring(x)) for x in tree]

    for tree in tree:
        _id = tree.xpath(f'//@id')
        user_id = tree.xpath(f'//@data-answering-id')
        post_id = tree.xpath(f'//@data-post-id')

        text = "\n".join(tree.xpath(f'//*[@class="wall_reply_text"]//text()'))

        like_count = tree.xpath(f'//@data-count')

        js_like_comment = ''
        for i in tree.xpath(f'//@onclick'):
            if 'Likes.toggle' in i:
                js_like_comment = str(i)

        comment_id = re.findall(r"wall_reply-*[\d_]+", js_like_comment)
        comment_id = comment_id[0] if comment_id else ''

        like_comment_hash = re.findall(r"[\d\w]{18,19}", js_like_comment)
        like_comment_hash = like_comment_hash[0] if like_comment_hash else ''

        content = await _pars_content(tree, '//*[@class="reply_text"]')

        comments.append(CommentPost(_id, user_id, post_id, text, like_count,
                                    content, comment_id, like_comment_hash, vk))

    return [x for x in comments if x.id]


# TODO delete
def _pars_like_and_id_NOT_reaction(tree):
    m = tree.xpath('//@id')
    _id = str(m[0]).replace('post', 'wall') if m else ''
    s = str(etree.tostring(tree))
    h = re.findall(r"(?<=Likes.toggle\().*?(?=\);)", s)
    h = re.findall(r'\w{18,19}', h[0] if h else '')
    _hash = h[0] if h else ''
    return _id, _hash


def _pars_like_and_id(tree):
    m = tree.xpath('//@id')
    h = tree.xpath('//@data-reaction-hash')

    like_hash = ''

    _id = m[0].replace('post', 'wall') if m else ''
    if h:
        like_hash = str(h[0])
    else:
        _id = ''

    return _id, like_hash


def _pars_counters(tree):
    like_count = tree.xpath(f'//@data-reaction-counts')
    if like_count:
        like_count = json.loads(like_count[0])

    comment_count = tree.xpath(f'//*[@data-like-button-type="comment"]/@data-count')
    repost_count = tree.xpath(f'//*[@data-like-button-type="share"]/@data-count')
    view_count = []
    return like_count, comment_count, repost_count, view_count


def _pars_hash_comment(page_data):
    hc = RE.get_hash_post_comment.findall(page_data)
    return hc[0] if hc else ''


def _pars_text_and_any(tree):
    hash_view = tree.xpath(f'//@post_view_hash')
    orig_post_id = tree.xpath(f'//@data-copy')

    is_vk_ads = True if tree.xpath(f'//@data-ad') else False

    text = tree.xpath(f'//*[@class="wall_post_text"]//text()')
    source = tree.xpath(f'//*[@class="Post__copyright"]//@href')
    return text, hash_view, orig_post_id, source, is_vk_ads


async def _post_parser(tree, vk=None, hash_comment='') -> Post:
    content = await _pars_content(tree)

    # TODO del else
    if vk.use_reaction:
        _id, like_hash = _pars_like_and_id(tree)
    else:
        _id, like_hash = _pars_like_and_id_NOT_reaction(tree)

    text, hash_view, orig_post_id, source, is_vk_ads = _pars_text_and_any(tree)
    like_count, comment_count, repost_count, view_count = _pars_counters(tree)
    comment = await _pars_comments(tree, vk)

    return Post(_id, hash_view, orig_post_id, text, content,
                source, like_count, repost_count, view_count,
                comment_count, like_hash, comment, vk, hash_comment,
                is_vk_ads)


async def _pars_fix_post(tree, vk, hash_comment):
    t = tree.xpath('//*[@id="wall_fixed"]/div/div')
    if not t:
        return None

    fix_post = await _post_parser(_get_tree(t), vk, hash_comment)
    if fix_post:
        fix_post.is_fix = True

    return fix_post


async def main_post_parser(page_data: str, vk: VkSession, from_feed=False) -> List[Post]:
    hash_comment = _pars_hash_comment(page_data)
    is_feed_top = len(RE.check_is_feed_top.findall(page_data)) > 0

    posts = []
    for i in _get_post(page_data):
        post_data_as_str = str(etree.tostring(i))
        if RE.is_post.findall(post_data_as_str):
            post_tree = lxml.html.fromstring(post_data_as_str)
            post = await _post_parser(post_tree, vk, hash_comment)
            if post.id:
                post.from_feed = from_feed
                post.is_feed_top = is_feed_top
                posts.append(post)

    return posts


#@async_timer
async def wall_post_parser(page_data: str, vk: VkSession, is_full_page=True) -> List[Post]:
    posts = []
    hash_comment = _pars_hash_comment(page_data)
    tree = lxml.html.fromstring(page_data)
    if is_full_page:
        fix_post = await _pars_fix_post(tree, vk, hash_comment)
        if fix_post:
            posts.append(fix_post)

    [posts.append(i) for i in await main_post_parser(page_data, vk) if i not in posts]

    return posts


#@async_timer
async def feed_post_parser(page_data: str, vk: VkSession) -> List[Post]:
    return await main_post_parser(page_data, vk, True)

