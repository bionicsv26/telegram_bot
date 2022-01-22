import re
from datetime import date
from typing import Dict, List, Tuple, Union

from loguru import logger
from telebot.types import InlineKeyboardMarkup, Message
from telegram_bot_calendar import DetailedTelegramCalendar

from Bot_files.botrequests.bot_classes import InlineKeyboard, Request, Session, HistoryQuery, db


def search_city(message: Message, bot) -> None:
    """
    Формирует запрос для поиска города по названию и на основе полученных данных создается
    inline клавиатура с вариантами городов (если поиск успешный) или производится повторный запрос
    у пользователя (если данных на сайте не найдено). В зависимости от языка вводимого сообщения выбирается
    локализация и валюта для поиска и отображения результатов текущего запроса пользователя
    :param bot: бот
    :param message: Полученное в чате сообщение
    """
    city: str = message.text
    if re.match(r'[А-Яа-яЁё]+', city):
        locale: str = 'ru_RU'
        currency: str = 'RUB'
    else:
        locale: str = 'en_US'
        currency: str = 'USD'

    for value in (('query', city), ('locale', locale), ('currency', currency)):
        update_save(message, value[0], value[1])

    request_queue: Dict = collect_request(message, 'query', 'locale', 'currency')

    cities: List = object_search(search_city.__name__, request_queue, message)
    if len(cities) == 0:
        logger.info(f'message {message.from_user.id}: Города с названием {message.text} не обнаружено:')
        msg = bot.send_message(message.chat.id,
                               'Города с таким названием не обнаружено\nПопробуйте ввести название еще раз:')
        bot.register_next_step_handler(msg, search_city, bot)

    else:
        logger.info(f'message {message.from_user.id}: Найдено {len(cities)} вариантов названия города на выбор')
        create_keyboard(cities, 1, 'Найдено несколько городов. Выберите подходящий:', message, bot)


def number_hotels(message: Message, bot):
    """
    Проверяет введенное пользователем количество отелей и выбирает следующим обработчиком number_guests (если проверка
    успешная) или производится повторный запрос (если данные не прошли проверку)
    :param bot: бот
    :param message: Полученное в чате сообщение
    """
    amount_hotels: str = message.text
    if not amount_hotels.isdigit() or int(amount_hotels) > 25 or 0 >= int(amount_hotels):
        logger.info(f'message {message.from_user.id}: Количество отелей {amount_hotels} введено не корректно')
        msg = bot.send_message(message.chat.id,
                               'Введено не число от 1 до 25\nПопробуйте ввести количество вариантов еще раз:')
        bot.register_next_step_handler(msg, number_hotels, bot)
    else:
        logger.info(f'message {message.from_user.id}: Количество отелей введено корректно')
        update_save(message, 'number_hotels', amount_hotels)
        msg = bot.send_message(message.chat.id,
                               'Сколько человек будет проживать в отеле:')
        bot.register_next_step_handler(msg, number_guests, bot)


def number_guests(message: Message, bot):
    """
    Проверяет введенное пользователем число гостей и вызывает следующую функцию check_dates (если проверка
    успешная) или производится повторный запрос (если данные не прошли проверку)
    :param bot: бот
    :param message: Полученное в чате сообщение
    """
    amount_guests: str = message.text
    if not amount_guests.isdigit() or int(amount_guests) not in range(1, 11):
        logger.info(f'message {message.from_user.id}: Количество гостей {amount_guests} введено не корректно')
        msg = bot.send_message(message.chat.id,
                               'Введено не число от 1 до 10\nПопробуйте ввести количество гостей еще раз:')
        bot.register_next_step_handler(msg, number_guests, bot)
    else:
        logger.info(f'message {message.from_user.id}: Количество гостей введено корректно')
        update_save(message, 'number_persons', amount_guests)
        check_dates(message, bot)


def check_dates(message: Message, bot):
    """Формирует календарь для ввода дат заезда-выезда"""
    locale: str = get_value_from_save(message, 'locale')[:2]

    calendar, step = DetailedTelegramCalendar(locale=locale).build()
    if get_value_from_save(message, 'check_in') == '':
        text_message = 'заезда в отель'
    else:
        text_message = 'выезда из отеля'
    bot.send_message(message.chat.id, 'Введите дату ' + text_message, reply_markup=calendar)


def validation_dates(message: Message, bot) -> bool:
    """Проверка вводимых дат на корректность"""
    check_in: date = get_value_from_save(message, 'check_in')
    check_out: date = get_value_from_save(message, 'check_out')
    if check_out.year > check_in.year:
        return True
    elif check_out.year == check_in.year:
        if check_out.month > check_in.month:
            return True
        elif check_out.month == check_in.month:
            if check_out.day > check_in.day:
                return True
    logger.info(f'message {message.from_user.id}: Даты {check_in} и {check_out} введены не корректно')
    return False


def search_hotels(message: Message, bot):
    """
    Формирует запрос для поиска отелей и на основе полученных данных создается inline клавиатура с вариантами отелей
    (если поиск успешный) или производится повторный запрос у пользователя (если данных на сайте не найдено)
    :param bot: бот
    :param message: Полученное в чате сообщение
    """
    bot.send_message(message.chat.id, 'Идет поиск отелей...:')
    request_queue: Dict = collect_request(message, 'city_id', 'page_number', 'number_hotels', 'check_in', 'check_out',
                                          'number_persons', 'sort_order', 'locale', 'currency')
    hotels: List = object_search(search_hotels.__name__, request_queue, message)

    if len(hotels) == 0:
        logger.info(f'message {message.from_user.id}: Отеля по запросу не обнаружено:')
        bot.send_message(message.chat.id,
                         'Отелей по вашему запросу не найдено.'
                         ' Если хотите повторить запрос или набрать новый,'
                         ' воспользуйтесь, пожалуйста, командой /start')
    else:
        logger.info(f'message {message.from_user.id}: Обнаружено {len(hotels)} вариантов отелей')
        text_message = 'Найдено несколько отелей. Выберите подходящий:'
        create_keyboard(hotels, 1, text_message, message, bot)


def object_search(func_name: str, request_queue: Dict, message: Message) -> Union[List[Tuple], str]:
    """
    Создает объект класса Request, вызывает метод в зависимости от функции отправителя.
     Возвращает искомые данные в функцию отправителя.
    :param func_name: Название функции - отправителя запроса
    :param request_queue: Запрос пользователя
    :param message: Полученное в чате сообщение
    :return: Список кортежей, содержащих объекты поиска, либо текстовые данные в виде строки
    """
    searched_objects = Request(request_queue)
    way_search: Dict = {'search_hotels': searched_objects.get_hotels,
                        'search_city': searched_objects.get_city,
                        'search_hotel_info': searched_objects.get_hotel_info,
                        'search_hotel_photos': searched_objects.get_hotel_pics}
    objects: Union[List, str] = way_search[func_name]()
    logger.info(f'message {message.from_user.id}: Запрос от {func_name} отработан')
    return objects


def search_hotel_info(message: Message, bot):
    """
    Формирует запрос для поиска подробной информации по отелю и отправляет ее затем пользователю.
    Если ответ на запрос на вывод фотографий был положительный, тогда вызывается search_hotel_photos
    :param bot: бот
    :param message: Полученное в чате сообщение
    """
    request_queue: Dict = collect_request(message, 'hotel_id', 'check_in', 'check_out',
                                          'number_persons', 'locale', 'currency')
    hotel_info: str = object_search(search_hotel_info.__name__, request_queue, message)

    if len(hotel_info) == 0:
        logger.info(f'message {message.from_user.id}: Информация об отеле отсутствует в базе')
        bot.send_message(message.chat.id, 'Информация об отеле отсутствует в базе')
    else:
        logger.info(f'message {message.from_user.id}: Информация об отеле отправлена пользователю')
        bot.send_message(message.chat.id, hotel_info)
    if get_value_from_save(message, 'hotel_pics').isdigit():
        search_hotel_photos(message, bot)


def check_photo(message: Message, bot) -> None:
    """Создает inline клавиатуру с вопросом о необходимости вывода фотографий отеля"""
    button = [('Yes', 'Yes.photo'), ('No', 'No.photo')]
    create_keyboard(button, 2, 'Для выбранного отеля будем выводить фото?', message, bot)


def create_keyboard(keyboard: List, row: int, question: str, message: Message, bot) -> None:
    """Создает inline клавиатуру по запросу пользователя"""
    this_keyboard = InlineKeyboard(keyboard, row)
    keyboard: InlineKeyboardMarkup = this_keyboard.create_keys()
    bot.send_message(message.chat.id, text=question, reply_markup=keyboard)


def number_photos(message: Message, bot) -> None:
    """
    Проверяет введенное пользователем число фотографий и вызывает следующую функцию search_hotel_info (если проверка
    успешная) или производится повторный запрос (если данные не прошли проверку)
    :param bot: бот
    :param message: Полученное в чате сообщение
    """
    amount_photos: str = message.text
    if not amount_photos.isdigit() or int(amount_photos) not in range(1, 16):
        logger.info(f'message {message.from_user.id}: Количество фотографий не корректное')
        msg = bot.send_message(message.chat.id,
                               'Введено не число от 1 до 15\nПопробуйте ввести количество фотографий еще раз:')
        bot.register_next_step_handler(msg, number_photos, bot)
    else:
        logger.info(f'message {message.from_user.id}: Количество фотографий корректное')
        update_save(message, 'hotel_pics', amount_photos)
        search_hotel_info(message, bot)


def search_hotel_photos(message: Message, bot) -> None:
    """
    Формирует запрос для поиска фотографий отеля и отправляет их затем пользователю.
    :param bot: бот
    :param message: Полученное в чате сообщение
    """
    request_queue: Dict = collect_request(message, 'hotel_id')
    photo_album: List = object_search(search_hotel_photos.__name__, request_queue, message)
    photo_from_db = get_value_from_save(message, 'hotel_pics')

    if int(photo_from_db) <= len(photo_album):
        pics: int = int(photo_from_db)
    else:
        pics: int = len(photo_album)
        bot.send_message(message.chat.id, f'На сайте найдено всего {photo_album} фотографий')
    for pic in photo_album[:pics]:
        bot.send_photo(message.chat.id, pic)
    logger.info(f'message {message.from_user.id}: {pics} фотографий отправлено пользователю')


def create_database() -> None:
    """Создает таблицы Session и HistoryQuery в базе sqlite"""
    with db:
        db.create_tables([Session, HistoryQuery])
        logger.info(f'message: таблицы Session и HistoryQuery созданы или существуют')


def add_new_save(message: Message, sort_order: str) -> None:
    """
    Создает первую строку в таблице Session со значениями, соответствующими ключам в запросах к API hotels.com,
    если она еще не создана. Создает начальную запись текущего запроса пользователя
    """
    with db:
        first_save = Session.select().where(Session.id == 1)
        if not first_save.exists():
            first_save = Session(chat_id='chat.id', sort_order='sortOrder', query='query', city_id='destinationId',
                                 locale='locale', currency='currency', number_hotels='pageSize',
                                 number_persons='adults1', page_number='pageNumber', check_in='checkIn',
                                 check_out='checkOut', hotel_id='id', hotel_pics='pics', price_start='price_start',
                                 price_stop='price_stop', distance='distance')
            first_save.save()
            logger.info(f'message {message.from_user.id}: Первая запись создана')

        session = Session(chat_id=message.chat.id, sort_order=sort_order, query='', city_id='', locale='',
                          currency='', number_hotels='', number_persons='', check_in='', check_out='',
                          hotel_id='', hotel_pics='', price_start='', price_stop='', distance='', page_number='1')
        session.save()
        logger.info(f'message {message.from_user.id}: Начальная запись текущего запроса создана')


def update_save(message: Message, update_key: str, update_value: Union[str, date]) -> None:
    """
    Обновляет данные текущего запроса пользователя
    :param update_key: Название колонки в таблице Session
    :param update_value: Значение, сохраняемое в базе
    :param message: Полученное в чате сообщение
    """
    with db:
        session = eval(f"Session({update_key}='{update_value}')")
        session.id = Session.select().where(Session.chat_id == message.chat.id).limit(1).order_by(Session.id.desc())[0]
        session.save()
        logger.info(f'message {message.from_user.id}: Обновление в базе: {update_key} = {update_value}')


def get_value_from_save(message: Message, column_from_save: str) -> Union[str, date]:
    """
    Получает данные из соответствующей колонки текущего запроса пользователя
    :param column_from_save: Название колонки в таблице Session
    :param message: Полученное в чате сообщение
    :return: value
    """
    with db:
        cur_query = Session.select().where(Session.chat_id == message.chat.id).limit(1).order_by(Session.id.desc())[0]
        value: Union[str, date] = eval(f"cur_query.{column_from_save}")
        logger.info(f'message {message.from_user.id}: Запрос значения из базы: {column_from_save} = {value}')
        return value


def get_key_from_save(column_from_save: str) -> str:
    """
    Получает ключ для создания запроса к API hotels.com из первой строки таблицы Session,
    соответствующей колонки текущего запроса пользователя
    :param column_from_save: Название колонки в таблице Session
    :return: key
    """
    with db:
        cur_query = Session.get(Session.id == 1)
        key: str = eval(f"cur_query.{column_from_save}")
        logger.info(f'message: Запрос ключа из базы: {column_from_save} = {key}')
        return key


def collect_request(message: Message, *args: Union[str, date, float, int]) -> Dict:
    """
    создает запрос к API hotels.com из соответствующих колонок текущего запроса пользователя
    :param args: Название колонки в таблице Session
    :param message: Полученное в чате сообщение
    :return: запрос в виде словаря
    """
    collected_request: Dict = dict()
    for arg in args:
        key = get_key_from_save(arg)
        value = get_value_from_save(message, arg)
        collected_request[key] = value
    return collected_request
