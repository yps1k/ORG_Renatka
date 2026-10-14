import asyncio
import logging
import os
import random
from html import escape
from pathlib import Path

import aiohttp
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
                           BufferedInputFile, FSInputFile, BotCommand, LinkPreviewOptions)

from content import PLACES, ROUTES, ABOUT, map_url, reviews_url, route_url
from storage import Store
from photos import Photos

ROOT = Path(__file__).resolve().parent
router = Router()
store = None
photos = None
ADMIN_ID = 0

class Review(StatesGroup):
    stars = State()
    text = State()

def kb(rows):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=text, url=value) if value.startswith('https://')
        else InlineKeyboardButton(text=text, callback_data=value)
        for text, value in row] for row in rows])

MENU = kb([[('🏰 Что посмотреть','menu:places'),('🍽 Где поесть','menu:food')],
           [('🗺 Маршруты на день','menu:routes')],
           [('💛 Избранное','menu:favorites'),('🎲 Удиви меня','menu:random')],
           [('🌍 О Казани','menu:about'),('📍 Карта всех мест','menu:map')],
           [('🔎 Поиск','menu:search'),('🎒 Советы','menu:tips')]])

async def say(message, text, keyboard=None):
    return await message.answer(text, reply_markup=keyboard,
         link_preview_options=LinkPreviewOptions(is_disabled=True))

async def home(message, state):
    await state.clear()
    await say(message, '✨ <b>Казань рядом</b>\n<i>Город двух культур, вкусной выпечки и прогулок у воды.</i>\n\n'
        'Выберите маршрут или соберите свой день из любимых мест. '
        'В карточках — фото, карта, источники и отзывы.\n\n'
        'Сәлам! Добро пожаловать 🌙', MENU)

@router.message(CommandStart())
@router.message(Command('menu','cancel'))
async def start(message: Message, state: FSMContext):
    await home(message, state)

@router.message(Command('delete_me'))
async def delete_me(message: Message, state: FSMContext):
    store.delete_user(message.from_user.id)
    await state.clear()
    await say(message, 'Ваши избранные места и отзывы удалены из базы бота.', MENU)

@router.message(Command('help'))
async def help_message(message: Message):
    await say(message, '🔎 Напишите название места или слово: «мечеть», «музей», «чай».\n'
        '/menu — меню\n/cancel — отменить отзыв\n/delete_me — удалить свои данные\n\n'
        'Отзывы публикуются после модерации и подписываются «Гость», без имени. '
        'Для избранного и отзывов бот хранит ваш числовой Telegram ID. '
        'Не включайте контакты и личные данные в текст отзыва.', MENU)

async def listing(message, keys, title):
    rows = [[(PLACES[k]['emoji']+' '+PLACES[k]['name'], 'place:'+k)] for k in keys if k in PLACES]
    await say(message, title, kb(rows+[[('⬅️ Главное меню','menu:home')]]))

async def card(message, key):
    p = PLACES.get(key)
    if p is None:
        await say(message, 'Место не найдено. Откройте меню.', MENU)
        return
    photo = await photos.get(key, p['wiki'])
    if photo:
        data, credit = photo
        label = '🍽 Иллюстрация татарской кухни, не фото заведения' if p['kind']=='food' else '📷 '+p['name']
        caption = (f"{escape(label)}\nАвтор: {escape(credit['author'][:180])}\n"
                   f"Лицензия: {escape(credit['license'][:100])}\n"
                   f"<a href=\"{escape(credit['url'], quote=True)}\">Источник и полные условия</a>")
        try:
            await message.answer_photo(BufferedInputFile(data, filename=key+'.jpg'), caption=caption)
        except TelegramBadRequest:
            logging.warning('Telegram не принял фото %s', key)
    rating, count = store.rating(key)
    rating_text = f'⭐ {rating:.1f}/5 · {count} отзывов гостей бота' if count else '💬 Отзывов гостей бота пока нет'
    text = f"{p['emoji']} <b>{escape(p['name'])}</b>\n\n{escape(p['description'])}\n\n💡 {escape(p['tip'])}"
    if p['address']:
        text += '\n\n📍 '+escape(p['address'])+'\n🥄 '+escape(p['dish'])
    if not photo:
        text += '\n\n📷 Фото сейчас недоступно. Фотографии можно посмотреть по ссылкам ниже.'
    text += '\n\n'+rating_text
    await say(message, text, kb([
        [('📍 Карта / фото посетителей',map_url(p)),('💬 Отзывы в 2ГИС',reviews_url(p))],
        [('🌐 Сайт / источник',p['source'])],
        [('💛 Сохранить / убрать','fav:'+key),('✍️ Написать отзыв','review:'+key)],
        [('⭐ Отзывы гостей бота','reviews:'+key)], [('⬅️ Главное меню','menu:home')]]))

@router.callback_query(F.data.startswith('menu:'))
async def menus(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if not isinstance(call.message, Message): return
    await state.clear()
    section = call.data.split(':',1)[1]
    if section=='home': await home(call.message,state)
    elif section in ('places','food'):
        kind = 'food' if section=='food' else 'place'
        await listing(call.message,[k for k,p in PLACES.items() if p['kind']==kind],
                      '🍽 <b>Татарская кухня: выбираем паузу</b>' if kind=='food' else '🏰 <b>Коллекция впечатлений</b>')
    elif section=='routes':
        await say(call.message, '🗺 <b>Какой будет ваша Казань?</b>\nВремя примерное. Кафе и музеи проверяйте перед выходом.',
            kb([[(r['name'],'route:'+k)] for k,r in ROUTES.items()]+[[('⬅️ Меню','menu:home')]]))
    elif section=='favorites':
        keys=store.favorites(call.from_user.id)
        await listing(call.message,keys,'💛 <b>Ваши места</b>' if keys else 'Пока пусто. Откройте карточку и нажмите 💛.')
    elif section=='random': await card(call.message,random.choice(list(PLACES)))
    elif section=='about':
        await say(call.message,ABOUT,kb([[('🌐 Туристический портал', 'https://go.kzn.ru/')],[('⬅️ Меню','menu:home')]]))
    elif section=='search': await say(call.message,'🔎 Напишите слово или название места. Например: «Кабан», «театр», «мечеть».')
    elif section=='map':
        url=os.getenv('MAP_URL','').strip()
        await call.message.answer_document(FSInputFile(ROOT/'map.html'),caption='📍 Карта с остановками и выбором маршрута. Скачайте и откройте в браузере; для подложки нужен интернет.')
        if url.startswith('https://'):
            await say(call.message,'Открыть опубликованную карту:',kb([[('🗺 Карта',url)]]))
    elif section=='tips':
        await say(call.message,'🎒 <b>Перед прогулкой</b>\n\n'
          '• У Казанки бывает ветрено: возьмите дополнительный слой одежды.\n'
          '• Музеи и смотровые площадки проверяйте по графику на дату поездки.\n'
          '• В мечетях и храмах соблюдайте правила одежды и фотосъёмки.\n'
          '• Большой маршрут насыщенный: выберите короткий музейный обзор или разделите его на два дня.\n'
          '• В «Тюбетее» выберите конкретный филиал на официальном сайте.\n'
          '• Уточняйте состав блюд, если у вас есть аллергия.\n\n'
          'Полезные слова: сәлам — привет; рәхмәт — спасибо.',MENU)

@router.callback_query(F.data.startswith('place:'))
async def show_place(call: CallbackQuery, state: FSMContext):
    await call.answer('Открываю карточку…')
    await state.clear()
    if isinstance(call.message, Message): await card(call.message,call.data.split(':',1)[1])

@router.callback_query(F.data.startswith('route:'))
async def show_route(call: CallbackQuery, state: FSMContext):
    await call.answer()
    await state.clear()
    if not isinstance(call.message, Message): return
    r=ROUTES.get(call.data.split(':',1)[1])
    if r is None: return
    text=f"<b>{escape(r['name'])}</b>\n⏱ {escape(r['duration'])}\n\n{escape(r['intro'])}\n\n"
    rows=[]
    for n,(hour,key) in enumerate(r['stops'],1):
        p=PLACES[key]
        text+=f"{n}. <b>{hour}</b> {p['emoji']} {escape(p['name'])}\n"
        rows.append([(f"{n}. {p['name']}",'place:'+key)])
    if 'heritage' in call.data:
        text+='\n🍽 Обед: Дом чая после колокольни; ужин: Татарская усадьба у Кабана. В плане оставлены паузы на еду.'
    text+='\n\nПорядок остановок задан планом. Навигатор рассчитает переходы; часы здесь не являются бронированием.'
    await say(call.message,text,kb([[('🗺 Проложить пеший маршрут',route_url(r))]]+rows+[[('📍 Карта всех маршрутов','menu:map'),('⬅️ Маршруты','menu:routes')]]))

@router.callback_query(F.data.startswith('fav:'))
async def favorite(call: CallbackQuery):
    key=call.data.split(':',1)[1]
    if key not in PLACES: return await call.answer('Место не найдено')
    saved=store.toggle(call.from_user.id,key)
    await call.answer('💛 Сохранено' if saved else 'Убрано из избранного')

@router.callback_query(F.data.startswith('reviews:'))
async def show_reviews(call: CallbackQuery):
    await call.answer()
    if not isinstance(call.message, Message): return
    key=call.data.split(':',1)[1]
    if key not in PLACES: return
    entries=store.reviews(key)
    text='💬 <b>Последние отзывы гостей бота</b>\n\n'
    text+='\n\n'.join(f"{'⭐'*stars} · Гость · {date[:10]}\n{escape(body)}" for stars,body,date in entries) if entries else 'Здесь пока нет опубликованных отзывов. Внешние отзывы доступны в карточке.'
    await say(call.message,text,kb([[('✍️ Написать','review:'+key),('⬅️ Карточка','place:'+key)]]))

@router.callback_query(F.data.startswith('review:'))
async def review_start(call: CallbackQuery, state: FSMContext):
    await call.answer()
    if not isinstance(call.message, Message): return
    key=call.data.split(':',1)[1]
    if key not in PLACES: return
    if not ADMIN_ID:
        return await say(call.message,'Отзывы в боте пока отключены: владелец не назначил модератора. Читайте отзывы в 2ГИС по кнопке в карточке.')
    await state.set_state(Review.stars)
    await state.set_data({'place':key})
    await say(call.message,'⭐ Как вам место? Оцените от 1 до 5. /cancel — отмена.',
              kb([[(str(n)+' ⭐','stars:'+str(n)) for n in range(1,6)]]))

@router.callback_query(Review.stars, F.data.startswith('stars:'))
async def review_stars(call: CallbackQuery, state: FSMContext):
    value=call.data.split(':',1)[1]
    if value not in ('1','2','3','4','5'): return await call.answer('Выберите 1–5')
    await call.answer()
    await state.update_data(stars=int(value))
    await state.set_state(Review.text)
    if isinstance(call.message, Message):
        await say(call.message,'✍️ Напишите отзыв, от 5 до 500 символов. Он станет доступен всем после модерации с подписью «Гость». Не указывайте личные данные.')

@router.message(Review.text)
async def review_text(message: Message, state: FSMContext):
    body=(message.text or '').strip()
    if not 5<=len(body)<=500:
        return await say(message,'Нужен текст от 5 до 500 символов. /cancel — отмена.')
    data=await state.get_data()
    rid=store.add_review(message.from_user.id,data['place'],data['stars'],body)
    await state.clear()
    await say(message,'✅ Отзыв сохранён и отправлен на модерацию. Повторный отзыв на это место заменит предыдущий.',MENU)
    try:
        await message.bot.send_message(ADMIN_ID,f"Новый отзыв #{rid} · {escape(PLACES[data['place']]['name'])}\n"
          f"Оценка: {data['stars']}/5\n{escape(body)}",reply_markup=moderation_kb(rid))
    except Exception:
        # База хранит очередь; /pending позволяет обработать её после сбоя доставки.
        logging.warning('Не удалось уведомить модератора; отзыв в очереди')

def moderation_kb(rid):
    return kb([[('✅ Опубликовать',f'mod:yes:{rid}'),('🗑 Отклонить',f'mod:no:{rid}')]])

@router.message(Command('pending'))
async def pending(message: Message):
    if message.from_user.id != ADMIN_ID: return
    entries=store.pending()
    if not entries: await say(message,'Очередь пуста.')
    for rid,key,stars,body in entries:
        await say(message,f"#{rid} · {escape(PLACES[key]['name'])}\n{stars}/5\n{escape(body)}",moderation_kb(rid))

@router.callback_query(F.data.startswith('mod:'))
async def moderate(call: CallbackQuery):
    if call.from_user.id != ADMIN_ID: return await call.answer('Только для модератора',show_alert=True)
    parts=call.data.split(':')
    if len(parts)!=3 or not parts[2].isdigit(): return await call.answer('Некорректная кнопка')
    store.moderate(int(parts[2]),parts[1]=='yes')
    await call.answer('Готово')
    if isinstance(call.message,Message): await call.message.edit_reply_markup(reply_markup=None)

@router.message(Review.stars)
async def ask_stars(message: Message):
    await say(message,'Выберите оценку кнопкой выше или нажмите /cancel.')

@router.callback_query()
async def expired(call: CallbackQuery):
    await call.answer('Эта кнопка устарела. Откройте /menu.',show_alert=True)

@router.message()
async def search(message: Message):
    query=(message.text or '').strip().casefold()
    if not query: return await say(message,'Напишите название места или откройте /menu.')
    keys=[k for k,p in PLACES.items() if query in (p['name']+' '+p['description']+' '+p['dish']).casefold()]
    await listing(message,keys,'🔎 <b>Нашлось в путеводителе</b>' if keys else 'Ничего не нашлось. Попробуйте «музей», «Кабан» или «чай».')

async def main():
    global store, photos, ADMIN_ID
    load_dotenv(ROOT/'.env')
    token=os.getenv('BOT_TOKEN','').strip()
    if not token or token=='PASTE_TOKEN_FROM_BOTFATHER':
        raise SystemExit('Создайте .env из .env.example и заполните BOT_TOKEN токеном от @BotFather.')
    ADMIN_ID=int(os.getenv('ADMIN_ID','0'))
    store=Store(ROOT/'guide.db')
    bot=Bot(token,default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp=Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12),
             headers={'User-Agent':'KazanNearbyGuide/1.0 (educational Telegram city guide)'}) as session:
            photos=Photos(ROOT,session)
            await bot.set_my_commands([BotCommand(command='start',description='Открыть Казань'),
                BotCommand(command='menu',description='Главное меню'),
                BotCommand(command='help',description='Помощь и данные'),
                BotCommand(command='cancel',description='Отменить отзыв'),
                BotCommand(command='delete_me',description='Удалить мои данные')])
            await bot.delete_webhook(drop_pending_updates=False)
            await dp.start_polling(bot)
    finally:
        await bot.session.close()
        store.db.close()

if __name__=='__main__':
    # Не логируем URL Telegram API: в них может находиться токен.
    logging.basicConfig(level=logging.WARNING,format='%(levelname)s: %(message)s')
    asyncio.run(main())
