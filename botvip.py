import logging
import requests
import telebot
from telebot import types
import threading
import pyotp
import re
import time
import queue
from telebot.apihelper import ApiException
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from threading import Thread

TELEGRAM_TOKEN = '7531541663:AAEUw-Bo89DTzpoTDANgneqO68LnFzNRljo'
bot = telebot.TeleBot(TELEGRAM_TOKEN, threaded=True)
logging.basicConfig(level=logging.INFO)


# Hàm gửi tin nhắn với retry khi gặp lỗi 429
def send_message_with_retry(chat_id, text, retries=3, delay=3):
    for attempt in range(retries):
        try:
            bot.send_message(chat_id, text)
            break  # Nếu gửi thành công thì thoát khỏi vòng lặp
        except ApiException as e:
            if e.result.status_code == 429:
                print(f"Lỗi 429: Đang đợi {delay} giây trước khi thử lại...")
                time.sleep(delay)
            else:
                raise e

def can_send_message(chat_id, delay=7):
    current_time = time.time()
    if chat_id not in last_sent_time or current_time - last_sent_time[chat_id] >= delay:
        last_sent_time[chat_id] = current_time
        return True
    return False

def send_message(chat_id, text):
    if can_send_message(chat_id):
        send_message_with_retry(chat_id, text)
    else:
        print(f"Đợi {delay} giây trước khi gửi tin nhắn cho {chat_id}")

# Hàng đợi và luồng gửi tin nhắn với độ trễ 7 giây
message_queue = queue.Queue()

def message_sender():
    while True:
        chat_id, text = message_queue.get()
        try:
            bot.send_message(chat_id, text)
        except Exception as e:
            logging.warning(f"Lỗi gửi tin nhắn tới {chat_id}: {e}")
        time.sleep(7)  # Đảm bảo gửi tin nhắn với độ trễ 7 giây

# Tạo luồng gửi tin nhắn
threading.Thread(target=message_sender, daemon=True).start()

def check_uid_batch(batch_uid_list, user_id, message_id):
    for uid in batch_uid_list:
        try:
            result = check_uid(uid, chat_id)  # Đúng  # Gọi hàm check UID của bạn
            text = f"✅ {uid}: {result}"
        except Exception as e:
            text = f"❌ {uid}: Lỗi - {e}"
        send_text(user_id, text)
    time.sleep(7)  # Nghỉ sau mỗi batch

def check_uid_multithreaded(uid_list, user_id, message_id):
    batch_size = 20
    delay_between_batches = 10  # giây
    total_batches = (len(uid_list) + batch_size - 1) // batch_size

    for i in range(total_batches):
        start = i * batch_size
        end = min((i + 1) * batch_size, len(uid_list))
        batch = uid_list[start:end]
        thread = threading.Thread(target=check_uid_batch, args=(batch, user_id, message_id))
        thread.start()
        time.sleep(delay_between_batches)  # Giãn cách tạo luồng

def send_delayed(chat_id, text):
    message_queue.put((chat_id, text))

user_checking_flags = {}
user_settime_flags = {}
settime_loops = {}
user_auto_flags = {}  # Lưu trạng thái AUTO cho từng người dùng
user_tiktok_flags = {}
settime_threads = {}  # user_id: thread
settime_stop_flags = {}  # user_id: threading.Event
last_sent_time = {}
acc_lock = Lock()
executor = ThreadPoolExecutor(max_workers=10)
user_result_messages = {}

# ---------------------- Quản lý luồng phụ ----------------------
MAX_HELPER_THREADS = 5
helper_threads = []
helper_locks = []

def create_helper_worker():
    lock = threading.Lock()
    helper_locks.append(lock)

    def worker():
        while True:
            with lock:
                pass  # Chờ được gán nhiệm vụ thực tế

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    return thread

def ensure_helper_threads():
    global helper_threads
    while len(helper_threads) < MAX_HELPER_THREADS:
        t = create_helper_worker()
        helper_threads.append(t)

# Tạo lại helper nếu có lỗi

def replace_dead_helpers():
    global helper_threads
    for i, thread in enumerate(helper_threads):
        if not thread.is_alive():
            logging.warning(f"Phát hiện helper thread {i} lỗi, tạo lại...")
            helper_threads[i] = create_helper_worker()

# Khởi tạo
ensure_helper_threads()

# ---------------------- Hàm gửi tin nhắn với độ trễ ----------------------
def send_message_with_delay(chat_id, message):
    time.sleep(7)
    bot.send_message(chat_id, message)

# ---------------------- Hàm CheckUID ----------------------

def check_uid(uid, chat_id):
    avatar_url = f"https://graph.facebook.com/{uid}/picture?type=normal"
    profile_url = f"https://m.facebook.com/profile.php?id={uid}"
    try:
        resp = requests.get(avatar_url, allow_redirects=True, timeout=5)
        final_url = resp.url
        if "static" in final_url or "facebook.com/images/deprecated" in final_url:
            status = "❌ DIE"
        elif resp.status_code == 200:
            status = "✅ LIVE"
        else:
            status = "⚠️ UNKNOWN"
        bot.send_message(chat_id, f"UID: {uid}\nTrạng thái: {status}\nLink: {profile_url}")
    except Exception as e:
        bot.send_message(chat_id, f"{uid} => ⚠️ ERROR: {str(e)}")

# ---------------------- Hàm Check UID đa luồng ----------------------

def check_uid_multithreaded(uid_list, chat_id, max_threads=100):
    def worker(uid):
        try:
            check_uid(uid, chat_id)
        except Exception as e:
            logging.warning(f"Lỗi trong worker UID: {uid} - {str(e)}")
            replace_dead_helpers()

    threads = []
    for uid in uid_list:
        if uid:
            t = threading.Thread(target=worker, args=(uid,))
            threads.append(t)
            t.start()
            if len(threads) >= max_threads:
                for t in threads:
                    t.join()
                threads.clear()

    for t in threads:
        t.join()

# ---------------------- Xử lý lệnh /start ----------------------

@bot.message_handler(commands=['start'])
def start_command(message):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("Checkuid", callback_data="checkuid"),
        types.InlineKeyboardButton("2favamakhoiphuc", callback_data="2favamakhoiphuc"),
        types.InlineKeyboardButton("Checkacctik", callback_data="checkacctik"),  # Đổi thành checkacctik
        types.InlineKeyboardButton("Bangxutds", callback_data="bangxutds")
    )
    bot.send_message(message.chat.id, "Chào bạn! Chọn một lệnh để thực hiện:", reply_markup=markup)

# ---------------------- Xử lý các lệnh từ nút inline ----------------------

@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    if call.data == "checkuid":
        handle_checkuid(call.message)
    elif call.data == "2favamakhoiphuc":
        handle_2favamakhoiphuc(call.message)
    elif call.data == "checkacctik":  # Đổi thành checkacctik
        handle_checkacctik(call.message)
    elif call.data == "bangxutds":
        handle_bangxutds(call.message)

    bot.answer_callback_query(call.id)

# ---------------------- Các hàm xử lý lệnh ----------------------

def handle_checkuid(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("▶️ Bắt đầu kiểm tra"),
               types.KeyboardButton("SetTime"),
               types.KeyboardButton("⛔ Kết thúc kiểm tra"))
    bot.send_message(message.chat.id, "Chọn hành động:", reply_markup=markup)

def handle_2favamakhoiphuc(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("AUTO"))
    bot.send_message(message.chat.id, "Vui lòng gửi key 2FA (chuỗi ≥ 16 ký tự) để bot tự động gửi mã OTP.", reply_markup=markup)

def handle_checkacctik(message):  # Thêm xử lý cho checkacctik
    bot.send_message(message.chat.id, "Chức năng CheckAcctik sẽ được triển khai sau.")

def handle_bangxutds(message):
    bot.send_message(message.chat.id, "Chức năng Bangxutds sẽ được triển khai sau.")

# ---------------------- Xử lý lệnh Checkuid ----------------------

@bot.message_handler(func=lambda m: m.text == "▶️ Bắt đầu kiểm tra")
def handle_start_checking(message):
    user_checking_flags[message.chat.id] = True
    bot.send_message(message.chat.id, "Đã bật chế độ kiểm tra. Gửi UID hoặc file .txt.")

@bot.message_handler(func=lambda m: m.text == "⛔ Kết thúc kiểm tra")
def handle_stop_checking(message):
    user_checking_flags.pop(message.chat.id, None)
    bot.send_message(message.chat.id, "Đã tắt chế độ kiểm tra.")


# ---------------------- Xử lý lệnh SetTime ----------------------

# Command "SetTime"
user_settime_flags = {}

import time
import threading
from telebot import types

settime_loops = {}  # Quản lý trạng thái SetTime cho từng người dùng

@bot.message_handler(func=lambda m: m.text == "SetTime")
def settime_command(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("Giây"), types.KeyboardButton("Phút"), types.KeyboardButton("Tiếng"))
    bot.send_message(message.chat.id, "Chọn đơn vị thời gian:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text in ["Giây", "Phút", "Tiếng"])
def handle_time_unit(message):
    chat_id = message.chat.id
    user_settime_flags[chat_id] = {'unit': message.text}
    bot.send_message(chat_id, "Nhập thời gian (chỉ số):")

@bot.message_handler(func=lambda m: m.text.isdigit(), content_types=['text'])
def handle_time_input(message):
    chat_id = message.chat.id
    if chat_id in user_settime_flags and 'unit' in user_settime_flags[chat_id]:
        user_settime_flags[chat_id]['time'] = int(message.text)
        unit = user_settime_flags[chat_id]['unit']
        bot.send_message(chat_id, f"Thời gian đã chọn: {message.text} {unit}. Gửi file .txt để bắt đầu.")

# Hệ thống đa luồng & hàng đợi gửi tin nhắn
executor = ThreadPoolExecutor(max_workers=100)
send_queue = queue.Queue()

def send_message_queue_worker():
    while True:
        chat_id, text = send_queue.get()
        try:
            bot.send_message(chat_id, text)
        except Exception:
            pass
        time.sleep(0.7)  # delay để tránh 429

# Khởi động luồng gửi tin nhắn
threading.Thread(target=send_message_queue_worker, daemon=True).start()

# Hàm gửi kết quả với số lượng live/die và tự động xóa sau 30s
def send_result_with_delete(chat_id, live_count, die_count):
    # Tạo văn bản kết quả
    text = f"✅ Đã kiểm tra xong:\n- Số UID Live: {live_count}\n- Số UID Die: {die_count}"

    # Tạo nút xóa kết quả
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("❌ Xóa kết quả", callback_data="delete_result"))

    # Gửi tin nhắn và tạo luồng xóa tự động sau 30 giây
    msg = bot.send_message(chat_id, text, reply_markup=markup)

    def auto_delete():
        time.sleep(30)
        try:
            bot.delete_message(chat_id, msg.message_id)
        except Exception as e:
            print(f"Không thể tự xóa tin nhắn: {e}")

    threading.Thread(target=auto_delete).start()

# Xử lý khi nhận file từ người dùng

settime_loops = {}
user_settime_flags = {}

# Đoạn xử lý file (cả thủ công và định kỳ)
@bot.message_handler(content_types=['document'])
def handle_file(message):
    chat_id = message.chat.id

    if message.document.mime_type != 'text/plain':
        send_queue.put((chat_id, "Chỉ nhận file .txt."))
        return

    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    text = downloaded_file.decode('utf-8', errors='ignore')
    lines = text.splitlines()

    # Parse UID
    uid_list = []
    for line in lines:
        parts = line.split('|')
        if parts and parts[0].strip().isdigit():
            uid_list.append(parts[0].strip())

    # Nếu có cờ SetTime thì chạy chế độ lặp
    if chat_id in user_settime_flags and 'time' in user_settime_flags[chat_id]:
        unit = user_settime_flags[chat_id]['unit']
        time_value = user_settime_flags[chat_id]['time']
        interval = time_value * {"Giây": 1, "Phút": 60, "Tiếng": 3600}[unit]

        def loop_check():
            settime_loops[chat_id] = True

            markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.add(types.KeyboardButton("⛔ DỪNG KIỂM TRA NGAY"))

            send_queue.put((chat_id, f"Đã nhận file. Bắt đầu kiểm tra mỗi {time_value} {unit}."))
            try:
                bot.send_message(chat_id, f"⏳ Đếm ngược bắt đầu...", reply_markup=markup)
            except Exception as e:
                print(f"Lỗi gửi tin nhắn đếm ngược: {e}")
                return

            # Kiểm tra UID lần đầu ngay lập tức
            send_queue.put((chat_id, "🔍 Đang kiểm tra UID..."))

            def worker(uid_chunk):
                if settime_loops.get(chat_id):
                    check_uid_multithreaded(uid_chunk, chat_id)

            chunks = [uid_list[i:i+5] for i in range(0, len(uid_list), 5)]
            for chunk in chunks:
                executor.submit(worker, chunk)

            send_queue.put((chat_id, "✅ Đã kiểm tra xong. Chờ lượt tiếp theo..."))

            # Gửi countdown ban đầu
            try:
                countdown_msg = bot.send_message(chat_id, f"⏳ Còn {interval} giây")
            except Exception as e:
                print(f"Lỗi gửi tin nhắn countdown: {e}")
                countdown_msg = None

            # Bắt đầu lặp
            while settime_loops.get(chat_id):
                waited = 0
                sleep_step = 1
                while waited < interval:
                    if not settime_loops.get(chat_id):
                        break
                    waited += sleep_step
                    if countdown_msg:
                        try:
                            bot.edit_message_text(chat_id=chat_id, message_id=countdown_msg.message_id,
                                                  text=f"⏳ Còn {interval - waited} giây")
                        except Exception as e:
                            print(f"Lỗi update countdown: {e}")
                    time.sleep(sleep_step)

                if not settime_loops.get(chat_id):
                    break

                send_queue.put((chat_id, "🔍 Đang kiểm tra UID..."))
                for chunk in chunks:
                    executor.submit(worker, chunk)
                send_queue.put((chat_id, "✅ Đã kiểm tra xong. Chờ lượt tiếp theo..."))

            send_queue.put((chat_id, "⛔ Đã DỪNG kiểm tra UID."))
            try:
                bot.send_message(chat_id, ".", reply_markup=types.ReplyKeyboardRemove())
            except Exception as e:
                print(f"Lỗi xóa bàn phím: {e}")

            user_settime_flags.pop(chat_id, None)

        threading.Thread(target=loop_check).start()

    # Nếu không có SetTime thì kiểm tra thủ công luôn
    else:
        send_queue.put((chat_id, "✅ Đã nhận file. Đang kiểm tra UID..."))

        def worker(uid_chunk):
            check_uid_multithreaded(uid_chunk, chat_id)

        chunks = [uid_list[i:i+5] for i in range(0, len(uid_list), 5)]
        for chunk in chunks:
            executor.submit(worker, chunk)

        send_queue.put((chat_id, "✅ Đã kiểm tra xong."))

# Nút StopSetTime để dừng quá trình
from telebot import types

# Biến toàn cục lưu message_id kết quả
user_result_messages = {}

# Gửi kết quả và lưu message_id
def send_result_message(chat_id, text):
    try:
        msg = bot.send_message(chat_id, text)
        user_result_messages.setdefault(chat_id, []).append(msg.message_id)
    except Exception as e:
        print(f"Lỗi khi gửi/lưu message_id kết quả: {e}")

# Xử lý dừng kiểm tra định kỳ
@bot.message_handler(func=lambda message: message.text == "⛔ DỪNG KIỂM TRA NGAY")
def handle_stop_settime_button(message):
    chat_id = message.chat.id
    if chat_id in settime_loops:
        settime_loops[chat_id] = False
        send_queue.put((chat_id, "⛔ Đã dừng quá trình kiểm tra định kỳ."))

        try:
            bot.send_message(chat_id, ".", reply_markup=types.ReplyKeyboardRemove())
        except Exception as e:
            print(f"Lỗi xóa bàn phím: {e}")

        # Gửi câu hỏi có xóa kết quả không (dạng nút dưới bàn phím)
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.add("✅ Có", "❌ Không")
        bot.send_message(chat_id, "Bạn có muốn xóa toàn bộ tin nhắn kết quả không?", reply_markup=markup)

# Xử lý nút trả lời dưới bàn phím
@bot.message_handler(func=lambda msg: msg.text in ["✅ Có", "❌ Không"])
def handle_delete_choice(msg):
    chat_id = msg.chat.id
    user_choice = msg.text

    try:
        bot.send_message(chat_id, ".", reply_markup=types.ReplyKeyboardRemove())
    except Exception as e:
        print(f"Lỗi khi ẩn bàn phím: {e}")

    if user_choice == "✅ Có":
        for msg_id in user_result_messages.get(chat_id, []):
            try:
                bot.delete_message(chat_id, msg_id)
            except:
                pass
        user_result_messages.pop(chat_id, None)
        bot.send_message(chat_id, "✅ Đã xóa toàn bộ tin nhắn kết quả.")
    else:
        bot.send_message(chat_id, "Đã giữ lại các tin nhắn kết quả.")

# Xử lý callback "✅ Có"
@bot.callback_query_handler(func=lambda call: call.data == "confirm_delete_all")
def confirm_delete_all(call):
    chat_id = call.message.chat.id
    message_id = call.message.message_id

    try:
        bot.delete_message(chat_id, message_id)
        for msg_id in user_result_messages.get(chat_id, []):
            try:
                bot.delete_message(chat_id, msg_id)
            except:
                pass
        bot.send_message(chat_id, "✅ Đã xóa toàn bộ tin nhắn kết quả.")
        user_result_messages.pop(chat_id, None)
    except Exception as e:
        print(f"Lỗi khi xóa kết quả: {e}")

# Xử lý callback "❌ Không"
@bot.callback_query_handler(func=lambda call: call.data == "cancel_delete")
def cancel_delete(call):
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    try:
        bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="Đã giữ lại các tin nhắn kết quả.")
    except Exception as e:
        print(f"Lỗi khi giữ lại tin nhắn: {e}")

# ---------------------- Xử lý key tạo mã OTP ----------------------

# Nhận dạng key 2FA
def is_2fa_key(text):
    cleaned = re.sub(r"[^\w]", "", text).upper()
    return len(cleaned) >= 16 and cleaned.isalnum()

@bot.message_handler(func=lambda msg: is_2fa_key(msg.text))
def handle_2fa(msg):
    key = re.sub(r"[^\w]", "", msg.text).upper()
    try:
        otp = pyotp.TOTP(key).now()
        bot.send_message(msg.chat.id, f"Đã nhận dạng là *key 2FA*:\nOTP: `{otp}`", parse_mode="Markdown")
    except Exception as e:
        bot.send_message(msg.chat.id, "Key không hợp lệ hoặc lỗi khi tạo mã OTP.")

# ---------------------- AUTO: BẬT / TẮT ----------------------

@bot.message_handler(func=lambda m: m.text == "AUTO")
def handle_auto(message):
    chat_id = message.chat.id
    user_auto_flags[chat_id] = True
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("OFFAUTO"))
    bot.send_message(chat_id, "Đã *bật AUTO*. Gửi key 2FA hoặc mã khôi phục để xử lý.", reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == "OFFAUTO")
def handle_offauto(message):
    chat_id = message.chat.id
    user_auto_flags[chat_id] = False
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("AUTO"))
    bot.send_message(chat_id, "Đã *tắt AUTO*. Mọi xử lý đã dừng.", reply_markup=markup, parse_mode="Markdown")

# ---------------------- Xử lý khi người dùng gửi tin nhắn ----------------------

@bot.message_handler(func=lambda m: True)
def handle_auto_input(message):
    chat_id = message.chat.id
    if not user_auto_flags.get(chat_id):
        return  # Nếu chưa bật AUTO thì bỏ qua

    text = message.text.strip()
    if is_recovery_code(text):
        handle_recovery_code(message)
    elif is_2fa_key(text):
        handle_2fa(message)
    else:
        bot.send_message(chat_id, "Không nhận dạng được định dạng. Gửi đúng key 2FA hoặc mã khôi phục.")


def safe_send_message(chat_id, text, **kwargs):
    for attempt in range(3):
        try:
            return bot.send_message(chat_id, text, **kwargs)
        except Exception as e:
            print(f"Lỗi gửi tin nhắn (lần {attempt+1}): {e}")
            time.sleep(3)
    print("Gửi tin nhắn thất bại sau 3 lần.")
    return None

def safe_edit_message(chat_id, message_id, text):
    for attempt in range(3):
        try:
            bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text)
            return
        except Exception as e:
            print(f"Lỗi chỉnh sửa tin nhắn (lần {attempt+1}): {e}")
            time.sleep(3)


# ---------------------- Chạy bot ----------------------

if __name__ == '__main__':
    print("ĐANG ĐỘ KIẾP SẮP HÓA THẦN ⚡⚡⚡...")
    bot.polling(non_stop=True)