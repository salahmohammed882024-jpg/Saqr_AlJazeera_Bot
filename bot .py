import logging
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from datetime import datetime, timedelta
import json
import os

# إعدادات التسجيل
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# ============================================
# إعدادات البوت
# ============================================
FORBIDDEN_WORDS = []  # الكلمات المحظورة
WARNINGS = {}  # {user_id: {count: number, reasons: []}}
BOT_STATS = {"total_banned": 0, "total_deleted": 0, "total_joined": 0}  # إحصائيات
WELCOME_MESSAGE = "أهلاً بك {name} في المجموعة 👋\nمن فضلك اقرأ القواعد المثبتة"
LINKS_LOCKED = False  # قفل الروابط
MEDIA_LOCKED = False  # قفل الميديا

# ============================================
# تحميل الكلمات المحظورة
# ============================================
def load_forbidden_words(file_path):
    """تحميل الكلمات المحظورة من ملف نصي"""
    global FORBIDDEN_WORDS
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            FORBIDDEN_WORDS = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        logging.info(f"✅ تم تحميل {len(FORBIDDEN_WORDS)} كلمة محظورة")
    except Exception as e:
        logging.error(f"❌ خطأ في تحميل الكلمات: {e}")
        FORBIDDEN_WORDS = ["اشترك", "قناة", "واتساب", "بوت", "سكليف", "إجازة", "عذر طبي", "رابط", "خدمات"]

# ============================================
# دوال المساعدة
# ============================================
def contains_forbidden_word(text):
    """التحقق من وجود كلمات محظورة في النص"""
    if not text:
        return False
    text = text.lower()
    for word in FORBIDDEN_WORDS:
        if word in text:
            return True
    return False

def contains_link(text):
    """التحقق من وجود رابط في النص"""
    if not text:
        return False
    # نمط للكشف عن الروابط
    link_pattern = r'(https?://[^\s]+)|(www\.[^\s]+)|([a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(/[^\s]*)?)'
    return re.search(link_pattern, text) is not None

def check_user_name(user):
    """فحص اسم العضو"""
    if user.first_name and contains_forbidden_word(user.first_name):
        return True
    if user.last_name and contains_forbidden_word(user.last_name):
        return True
    if user.username and contains_forbidden_word(user.username):
        return True
    return False

def is_bot_account(user):
    """كشف الحسابات الوهمية والبوتات"""
    # إذا كان الحساب جديد جداً (أقل من يوم)
    if user.is_bot:
        return True
    # إذا كان بدون صورة وبدون اسم
    if not user.first_name and not user.username:
        return True
    return False

def save_stats():
    """حفظ الإحصائيات في ملف"""
    try:
        with open('stats.json', 'w', encoding='utf-8') as f:
            json.dump(BOT_STATS, f, ensure_ascii=False)
    except:
        pass

def load_stats():
    """تحميل الإحصائيات من ملف"""
    global BOT_STATS
    try:
        with open('stats.json', 'r', encoding='utf-8') as f:
            BOT_STATS = json.load(f)
    except:
        pass

# ============================================
# معالج انضمام الأعضاء الجدد
# ============================================
async def on_user_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يتم استدعاؤها عندما ينضم عضو جديد"""
    try:
        for new_member in update.message.new_chat_members:
            # نتأكد أن العضو الجديد ليس البوت نفسه
            if new_member.id == context.bot.id:
                continue
            
            BOT_STATS["total_joined"] += 1
            save_stats()
            
            # 1️⃣ فحص الاسم المشبوه
            if check_user_name(new_member):
                chat = update.effective_chat
                try:
                    await chat.ban_member(new_member.id)
                    BOT_STATS["total_banned"] += 1
                    save_stats()
                    logging.info(f"🚫 تم حظر {new_member.first_name} لاسمه المشبوه")
                    continue  # ننتقل للعضو التالي
                except Exception as e:
                    logging.error(f"خطأ في حظر العضو الجديد: {e}")
            
            # 2️⃣ فحص البوتات الوهمية
            if is_bot_account(new_member):
                chat = update.effective_chat
                try:
                    await chat.ban_member(new_member.id)
                    BOT_STATS["total_banned"] += 1
                    save_stats()
                    logging.info(f"🤖 تم حظر بوت وهمي: {new_member.first_name}")
                    continue
                except Exception as e:
                    logging.error(f"خطأ في حظر البوت: {e}")
            
            # 3️⃣ إرسال رسالة ترحيب
            welcome_text = WELCOME_MESSAGE.replace("{name}", new_member.first_name)
            
            # إضافة أزرار تفاعلية
            keyboard = [
                [InlineKeyboardButton("📋 القواعد", callback_data="rules")],
                [InlineKeyboardButton("📊 الإحصائيات", callback_data="stats")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                welcome_text,
                reply_markup=reply_markup
            )
            
    except Exception as e:
        logging.error(f"خطأ في معالج الانضمام: {e}")

# ============================================
# معالج الرسائل
# ============================================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """فحص الرسائل وحظر المخالفين"""
    if not update.message or not update.message.text:
        return

    user = update.message.from_user
    chat = update.message.chat
    text = update.message.text

    # 1️⃣ فحص الروابط إذا كانت مقفولة
    if LINKS_LOCKED and contains_link(text):
        try:
            await update.message.delete()
            await context.bot.send_message(
                chat_id=chat.id,
                text=f"@{user.username} الروابط ممنوعة في المجموعة"
            )
            logging.info(f"🔗 تم حذف رابط من {user.first_name}")
            return
        except:
            pass

    # 2️⃣ فحص الكلمات المحظورة
    if contains_forbidden_word(text):
        try:
            # حذف الرسالة
            await update.message.delete()
            BOT_STATS["total_deleted"] += 1
            
            # نظام الإنذارات
            user_id = user.id
            if user_id not in WARNINGS:
                WARNINGS[user_id] = {"count": 1, "reasons": [text[:50]]}
            else:
                WARNINGS[user_id]["count"] += 1
                WARNINGS[user_id]["reasons"].append(text[:50])
            
            # إذا وصل 3 إنذارات → حظر
            if WARNINGS[user_id]["count"] >= 3:
                await chat.ban_member(user_id)
                BOT_STATS["total_banned"] += 1
                del WARNINGS[user_id]  # مسح الإنذارات بعد الحظر
                logging.info(f"🚫 تم حظر {user.first_name} بعد 3 إنذارات")
                
                # إرسال تنبيه
                await context.bot.send_message(
                    chat_id=chat.id,
                    text=f"🚫 تم حظر {user.first_name} لتكرار المخالفات"
                )
            else:
                # إرسال إنذار
                await context.bot.send_message(
                    chat_id=chat.id,
                    text=f"⚠️ إنذار {WARNINGS[user_id]['count']}/3 لـ {user.first_name}\nالرجاء الالتزام بالقواعد"
                )
                logging.info(f"⚠️ إنذار {WARNINGS[user_id]['count']} لـ {user.first_name}")
            
            save_stats()
            
        except Exception as e:
            logging.error(f"خطأ في معالج الرسائل: {e}")

# ============================================
# معالج الأزرار التفاعلية
# ============================================
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الضغط على الأزرار"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "rules":
        rules_text = """📋 **قواعد المجموعة**
1️⃣ ممنوع الإعلانات والروابط الترويجية
2️⃣ ممنوع الكلمات المسيئة والتطرف
3️⃣ ممنوع تكرار الرسائل (سبام)
4️⃣ احترام جميع الأعضاء
5️⃣ الالتزام بموضوع المجموعة

🚫 المخالف يتعرض للإنذار ثم الحظر"""
        await query.edit_message_text(rules_text)
        
    elif query.data == "stats":
        stats_text = f"""📊 **إحصائيات البوت**
👥 الأعضاء الجدد: {BOT_STATS['total_joined']}
🗑️ الرسائل المحذوفة: {BOT_STATS['total_deleted']}
🚫 الأعضاء المحظورون: {BOT_STATS['total_banned']}

🦅 صقر الجزيرة يحمي مجموعتك"""
        await query.edit_message_text(stats_text)

# ============================================
# معالج مغادرة الأعضاء
# ============================================
async def on_user_leave(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """يتم استدعاؤها عندما يغادر عضو"""
    try:
        for left_member in update.message.left_chat_members:
            logging.info(f"👋 غادر العضو: {left_member.first_name}")
    except:
        pass

# ============================================
# معالج الصور والملفات (فحص المحتوى)
# ============================================
async def handle_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """فحص الصور والملفات"""
    if MEDIA_LOCKED:
        try:
            await update.message.delete()
            logging.info(f"🖼️ تم حذف صورة/ملف من {update.message.from_user.first_name}")
        except:
            pass

# ============================================
# الوظيفة الرئيسية
# ============================================
def main():
    # تحميل الكلمات المحظورة
    load_forbidden_words('forbidden_words.txt')
    
    # تحميل الإحصائيات
    load_stats()
    
    # توكن البوت
    TOKEN = "8698757565:AAGB1jXSllO33yK1oqkiKIeZXetLmx-l72U"
    
    # إنشاء التطبيق
    application = ApplicationBuilder().token(TOKEN).build()
    
    # معالج انضمام الأعضاء الجدد
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_user_join))
    
    # معالج مغادرة الأعضاء
    application.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, on_user_leave))
    
    # معالج الرسائل النصية
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    
    # معالج الصور والملفات
    application.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, handle_media))
    
    # معالج الأزرار التفاعلية
    application.add_handler(CallbackQueryHandler(button_callback))

    # تشغيل البوت
    logging.info("🦅 صقر الجزيرة يعمل الآن... (النسخة النهائية)")
    logging.info(f"📊 الإحصائيات: {BOT_STATS['total_banned']} محظور، {BOT_STATS['total_deleted']} محذوف")
    application.run_polling()

if __name__ == '__main__':
    main()