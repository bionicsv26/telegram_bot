import os
from typing import Dict

import telebot
from dotenv import load_dotenv
from loguru import logger
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, Message, CallbackQuery
from telegram_bot_calendar import DetailedTelegramCalendar

import botrequests.bot_func as bf

load_dotenv()

bot = telebot.TeleBot(os.getenv('TOKEN_TELEGRAM'))

service_messages: Dict = {'/lowprice': 'PRICE',
                          '/highprice': 'PRICE_HIGHEST_FIRST',
                          '/bestdeal': 'DISTANCE_FROM_LANDMARK'}


@bot.message_handler(commands=['start'])
def start_handler(message: Message):
    """ Обработчик команды start"""
    bot.send_message(message.chat.id, f'Приветствую, {message.from_user.first_name}!\n'
                                      f'Я бот-помощник и постараюсь помочь Вам в поиске лучших вариантов отелей\n'
                                      f'Для помощи по командам наберите /help)')


@bot.message_handler(commands=['help'])
def help_handler(message: Message):
    """ Обработчик команды help"""
    keyboard_menu = ReplyKeyboardMarkup(row_width=2, one_time_keyboard=True, resize_keyboard=True)
    keyboard_menu.add(KeyboardButton('/lowprice'), KeyboardButton('/highprice'),
                      KeyboardButton('/bestdeal'), KeyboardButton('/history'))
    bot.send_message(message.chat.id, 'В меню используйте следующие команды:\n'
                                      '/lowprice - Поиск отелей с демократическими ценами\n'
                                      '/highprice - Поиск отелей с максимальными ценами\n'
                                      '/bestdeal - Поиск доступных отелей по удаленности от центра города\n'
                                      '/history - Просмотр результатов последнего запроса', reply_markup=keyboard_menu)


@bot.message_handler(commands=['lowprice', 'highprice', 'bestdeal'])
def request_handler(message: Message):
    """ Обработчик команд lowprice, highprice, bestdeal """
    logger.info(f'message {message.from_user.id}{message.text}')
    bf.add_new_save(message, service_messages[message.text])
    msg = bot.send_message(message.chat.id, 'В каком городе ищем отели? ')
    bot.register_next_step_handler(msg, bf.search_city, bot)


@bot.callback_query_handler(func=DetailedTelegramCalendar.func())
def calendar(call: CallbackQuery):
    """ Обработчик inline callback запросов для ввода дат"""
    locale: str = bf.get_value_from_save(call.message, 'locale')[:2]
    result, key, step = DetailedTelegramCalendar(locale=locale).process(call.data)
    if not result and key:
        if bf.get_value_from_save(call.message, 'check_in') == '':
            text_message = 'заезда в отель'
        else:
            text_message = 'выезда из отеля'
        bot.edit_message_text('Введите дату ' + text_message,
                              call.message.chat.id,
                              call.message.message_id,
                              reply_markup=key)
    elif result:
        bot.edit_message_text(f"Вы выбрали {result}",
                              call.message.chat.id,
                              call.message.message_id)
        logger.info(f'call chat_id {call.from_user.id}: {call.data}')
        if bf.get_value_from_save(call.message, 'check_in') == '':
            bf.update_save(call.message, 'check_in', result)
        else:
            bf.update_save(call.message, 'check_out', result)

        if bf.get_value_from_save(call.message, 'check_out') == '':
            bf.check_dates(call.message, bot)
        else:
            if bf.validation_dates(call.message, bot):
                logger.info(f'message {call.message.from_user.id}: Даты введены корректно')
                bf.search_hotels(call.message, bot)

            else:
                bot.send_message(call.message.chat.id, 'Возможно Вы ошиблись при вводе данных.'
                                                       ' Дата выезда не может быть раньше или равна дате въезда.'
                                                       'Попробуйте ввести их еще раз')
                bf.update_save(call.message, 'check_in', '')
                bf.update_save(call.message, 'check_out', '')
                bf.check_dates(call.message, bot)


@bot.callback_query_handler(func=lambda call: True)
def callback_inline(call: CallbackQuery):
    """Обработчик callback inline  запросов """
    logger.info(f'call chat_id {call.from_user.id}: {call.data}')
    data_sep = call.data.split('.')
    if data_sep[1] == 'city_id':
        bf.update_save(call.message, 'city_id', data_sep[0])
        msg = bot.send_message(call.message.chat.id, 'Сколько вариантов отелей показывать? Прошу ограничится 25')
        bot.register_next_step_handler(msg, bf.number_hotels, bot)
    elif data_sep[1] == 'hotel_id':
        bf.update_save(call.message, 'hotel_id', data_sep[0])
        bf.check_photo(call.message, bot)
    elif data_sep[1] == 'photo':
        if data_sep[0] == 'No':
            bf.update_save(call.message, 'hotel_pics', '0')
            bf.search_hotel_info(call.message, bot)
        else:
            msg = bot.send_message(call.message.chat.id,
                                   'Сколько фотографий данного отеля показывать? Прошу ограничится 15')
            bot.register_next_step_handler(msg, bf.number_photos, bot)


@bot.message_handler(content_types=['text'])
def text_handler(message):
    """ Обработчик текстовых сообщений"""
    logger.info(f'message chat_id {message.from_user.id}: {message.text}')
    bot.send_message(message.chat.id, 'Если в меню определены кнопки для выбора,'
                                      ' прошу их использовать, а не вводить данные руками.\n'
                                      'В случае ошибки, попробуйте повторить ввод данных с начала,'
                                      ' используя команду /start')


if __name__ == '__main__':
    logger.add('botrequests/logs.log', rotation="50 MB", encoding='utf-8')
    logger.info('Bot is starting')
    bf.create_database()
    bot.polling(none_stop=True)
