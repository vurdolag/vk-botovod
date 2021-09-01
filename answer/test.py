import pickle
import re
import random
from memory_profiler import memory_usage




def open_data():
    with open('text.txt', 'r', encoding='utf-8') as f:
        data = f.read()

    a = data.split('\n')

    bot = []

    for i in a:
        if i:
            i = i.split('||')
            q = i[0].split(',,')
            a = i[1].split(',,')
            bot.append([q, a])

    return bot




while True:
    i = input('> ').lower()
    all_ans = []

    for j in open_data():
        if j[0][0] == '#':
            pat = r'(' + r'|'.join(j[0][1:]) + r')'
        else:
            pat = r'(\b' + r'\b|\b'.join(j[0]) + r'\b)'

        r = re.findall(pat.lower(), i)
        if r:
            all_ans.append(j)

    if all_ans:
        print(all_ans)
        print(random.choice(all_ans[0][1]))
    else:
        print('None')