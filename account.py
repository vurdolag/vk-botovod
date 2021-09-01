import random as rnd
from typing import List, Dict

account: List[Dict[str, str]] = [

    {   # example
        "login": "79991234567",
        "password": "qwerty",
        "user-agent": ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) '
                       'Chrome/88.0.4324.150 Safari/537.36'),
        "proxy": "login:password@ip:port"  # or empty string "" if not proxy
    }

]

rnd.shuffle(account)

