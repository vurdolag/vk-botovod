from re import compile, DOTALL

enter_vk_user_id = compile(r'(?<="uid":").*?(?=",")')
enter_vk_user_id2 = compile(r'(?<=/id).*?(?=\',)')

check_user_id = compile(r"(?<=id:).*?(?=,)")
check_name = compile(r"(?<=\"TopNavBtn__profileName\">).*?(?=</div>)")

long_poll_feed_key1 = compile(r'(?<=\d\d\d,\"key\":\").+?(?=\",\"uid\":\d)', flags=DOTALL)
long_poll_feed_key2 = compile(r'(?<=\[\{\"key\":\").+?(?=\",\"ts\":)', flags=DOTALL)
long_poll_feed_ts1 = compile(r'(?<="timestamp":).+?(?=,"key")', flags=DOTALL)
long_poll_feed_ts2 = compile(r'(?<=,"ts":)\d+?(?=})', flags=DOTALL)
long_poll_feed_server_url = compile(r'(?<=\"server_url\":\").+?(?=\",\"frame)', flags=DOTALL)

get_hash_for_send_msg = compile(r"(?<=\"hash\":\").*?(?=\",)")

subscribe_enterHash = compile(r"(?<=\"enterHash\":\").*?(?=\",)")
subscribe_groups_enter = compile(r'(?<=Groups.enter\(this, ).*?(?=\',)')

word_dig_ = compile(r'[a-z\d_-]+')

leave_hash = compile(r"(?<=\"enterHash\":\").*?(?=\",)")
leave_group = compile(r"(?<=Groups.leave\('page_actions_btn',).*?(?='\))")

get_hash_post_likes = compile(r"(?<=Likes\.toggle\(this, event, ').*?(?='\);)")
get_hash_post_comment = compile(r"(?<=\"post_hash\":\").*?(?=\")")
get_hash_post_comment_id_list = compile(r"(?<=<div id=\"wpt)[-_0-9]*?(?=\">)")
get_hash_post_spam = compile(r"(?<=wall\.markAsSpam\(this,).*?(?='\);)")

pars_response_like = compile(r"(?<=Likes.update\().*?(?=\);)")
stat_get_like = compile(r"(?<=like_num\":)\d*?(?=,)")
stat_get_is_my_like = compile(r"(?<=like_my\":)\d*?(?=,)")

figure_scope = compile(r'\{.+?\}')
sqr_scope = compile(r'<.*?>')

two_slash = compile(r"\\")

open_repost_box_hash = compile(r"(?<=shHash: ').*?(?=',)")

get_post_from_session = compile(r"(?<=feed_session_id\":).*?(?=,\"feedba)")
get_post_from_view = compile(r"(?<=post_view_hash=\").*?(?=\")")
get_post_from_like = compile(r"(?<=Likes\.toggle\(this, event, ').*?(?='\);)")
get_post_from_ads = compile(r"(?<=promoted_post post_link\" href=\"/).*?(?=\" onclick)", flags=DOTALL)
get_post_from_ads_group = compile(r"(?<=class=\"post_content\").*?(?=class=\"replies\")",
                                  flags=DOTALL)
get_post_from_fix = compile(r"(?<=id=\"post).*?(?=\" class=\"_post post all own post_fixed)", flags=DOTALL)

post_id = compile(r'wall-*?\d+?_\d+')
sub_id = compile(r'[^\d_-]+')
id_ = compile(r'[\d_-]+')

dq = compile(r'"')

js_obj = compile(r'\{.*?\{.*?\}.*?\}')

quot = compile(r'&quot;')
amp = compile(r'&amp;')

sub_d = compile(r'[^0-9_-]')
d = compile(r'[\d-]+')
dig = compile(r'\d+?')
dig_ = compile(r'\d+')
is_post = compile(r'post-*\d+_\d')

id_new_comment = compile(r'(?<=\(this, \'wall_reply).*?(?=\', {\}\))')

spam_hash = compile(r"(?<=showReportCopyrightForm\(event,).*?(?='\))")

info_post = compile(r"(?<=_post_author_data_).*?(?=\")")

friend_check = compile(r"(?<=section=requests\" class=\").*?(?=\"onclick=\"return Friends)")
friend_accept = compile(r"(?<=\d\" onclick=\"Friends\.acceptRequest\().*?(?=', this\)\">)")
friend_decline = compile(r"(?<=\d\" onclick=\"Friends\.declineRequest\().*?(?=', this\)\">)")

out_requests_hash = compile(r"(?<=\d\" onclick=\"Friends\.declineRequest\().*?(?=', this\)\">)")

user_hash = compile(r"(?<=\"userHash\":\").*?(?=\",\")")

black_list_hash = compile(r"(?<=toggle_blacklist\").*?(?=', event)")

get_im = compile(r"(?<=IM\.init\(\{).*?(?=}\))")

search_group_id = compile(r'(?<=searcher.subscribe\(this, ).*?(?=\', true)')
search_group_title = compile(r'(?<=alt=\").*?(?=\")')
search_group_photo = compile(r'(?<=search_item_img\" src=\").*?(?=\" alt)')
search_group_type = compile(r'(?<=labeled \">).*?(?=<\/div><)')
search_group_member_count = compile(r'(?<=<\/div><div class=\"labeled \">).*?(?=<\/div>\n)')

upload_vars = compile(r"(?<=vars:).*?(?=})")
upload_url = compile(r"(?<=url: 'https).*?(?=.php)")

upload_avatar = compile(r"(?<=uploadInit\().*?(?=\);)")

feed_info = compile(r"(?<=feed\.init\(\{).*?(?=,\"all_shown_text\")")

add_friend = compile(r"(?<=Profile.toggleFriend\(this, ').*?(?=', 1, event)")

like_type = compile(r'(photo|video|group)')

comment_check = compile('ответила* на стене')

video_up_hash = compile(r'(?<=\\"update_db_hash\\":\\").*?(?=\\")')
video_random_tag = compile(r'(?<=\\"random_tag\\":\\").*?(?=\\")')

two_factor_auth_hash = compile(f'(?<=Authcheck\.init\(\')[\d\w_]+(?=\')')

check_is_feed_top = compile(r'_ui_toggler +?ui_toggler +?on')

check_avatar = compile(r'camera_\d+\.png')


