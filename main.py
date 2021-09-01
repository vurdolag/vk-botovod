from VkSession import VkSession
from Action import Action
from Server import Server
from Utils import rand, rnd_sleep, loop
from asyncio import create_task, set_event_loop_policy
from account import account
import config

try:
    import uvloop
    set_event_loop_policy(uvloop.EventLoopPolicy())
except ImportError:
    pass


def wait_start():
    return rand(1200, 300)


async def mainapp(vk: VkSession, wait=300) -> bool:
    await rnd_sleep(wait, 5)

    if not await vk.auth():
        return False

    act = Action(vk)

    tasks = [
        [act.long_poll()],
        [act.online()],
        [act.check_friend(), wait_start()],
        [act.random_like_feed(target=-30688695), wait_start()],
        [act.del_out_requests(to_black_list=True), wait_start()],
        [act.del_bad_friends(last_seen=3600 * 24 * 7), wait_start()],
        [act.reposter([30688695], random_repost=25,
                      random_like=15, target=-30688695), wait_start()],
    ]

    [loop.add(*task) for task in tasks]

    return True


async def multiakk():
    [loop.add(mainapp(VkSession(account=acc))) for acc in account]

    await loop.start()


async def start(_):
    create_task(multiakk())

if __name__ == '__main__':
    Server(config.server_key_api, config.encode_key).add(start).run()
