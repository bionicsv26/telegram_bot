import os
import re
import shutil
from datetime import date, datetime
from typing import Dict, List, Union

from loguru import logger
from telebot.types import InlineKeyboardMarkup, Message, InputMediaPhoto
from telegram_bot_calendar import DetailedTelegramCalendar

from bot_files.botrequests.bot_classes import InlineKeyboard, Request, Session, HistoryQuery, db

way_sorting: Dict = {'PRICE': 'lowprice',
                     'PRICE_HIGHEST_FIRST': 'highprice',
                     'DISTANCE_FROM_LANDMARK': 'bestdeal'}


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
    Проверяет введенное пользователем количество отелей и выбирает следующим обработчиком number_photos (если проверка
    успешная) или производится повторный запрос (если данные не прошли проверку)
    :param bot: бот
    :param message: Полученное в чате сообщение
    """
    amount_hotels: str = message.text
    if not amount_hotels.isdigit() or int(amount_hotels) not in range(2, 11):
        logger.info(f'message {message.from_user.id}: Количество отелей {amount_hotels} введено не корректно')
        msg = bot.send_message(message.chat.id,
                               'Введено не число от 2 до 10\nПопробуйте ввести количество вариантов еще раз:')
        bot.register_next_step_handler(msg, number_hotels, bot)
    else:
        logger.info(f'message {message.from_user.id}: Количество отелей введено корректно')
        update_save(message, 'number_hotels', amount_hotels)
        msg = bot.send_message(message.chat.id,
                               'Сколько фотографий каждого отеля показывать? Прошу выбрать от 2 до 10 фото')
        bot.register_next_step_handler(msg, number_photos, bot)


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

    calendar, step = DetailedTelegramCalendar(locale=locale, min_date=date.today()).build()
    if get_value_from_save(message, 'check_in') == '':
        text_message = 'заезда в отель'
    else:
        text_message = 'выезда из отеля'
    bot.send_message(message.chat.id, 'Введите дату ' + text_message, reply_markup=calendar)


def validation_dates(message: Message) -> bool:
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
    if request_queue['sortOrder'] == 'DISTANCE_FROM_LANDMARK':
        request_queue_addition: Dict = collect_request(message, 'price_start', 'price_stop', 'distance')
        request_queue.update(request_queue_addition)

    number_hotels_for_user: int = int(request_queue['pageSize'])
    hotels: List = object_search(search_hotels.__name__, request_queue, message)

    if len(hotels) == 0:
        logger.info(f'message {message.from_user.id}: Отеля по запросу не обнаружено:')
        bot.send_message(message.chat.id,
                         'Отелей по вашему запросу не найдено.'
                         ' Если хотите повторить запрос или набрать новый,'
                         ' воспользуйтесь, пожалуйста, командой /start')
    else:
        logger.info(f'message {message.from_user.id}: Обнаружено {len(hotels)} вариантов отелей')
        if len(hotels) < number_hotels_for_user:
            text_message = f'По Вашему запросу найдено всего {len(hotels)} вариантов отелей'
            bot.send_message(message.chat.id, text_message)
        photo_from_db = get_value_from_save(message, 'hotel_pics')
        for hotel_id in hotels:
            search_hotel_info(message, hotel_id, photo_from_db, bot)
        save_history_db(message, ' '.join(hotels))


def object_search(func_name: str, request_queue: Dict, message: Message) -> Union[List, str]:
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


def search_hotel_info(message: Message, hotel_id: str, photo_from_db: str, bot):
    """
    Формирует запрос для поиска подробной информации по отелю и отправляет ее затем пользователю.
    Если ответ на запрос на вывод фотографий был положительный, тогда вызывается search_hotel_photos
    :param bot: бот
    :param hotel_id: id запрашиваемого отеля
    :param photo_from_db: количество фотографий запрашиваемого отеля
    :param message: Полученное в чате сообщение
    """
    request_queue: Dict = collect_request(message, 'check_in', 'check_out',
                                          'number_persons', 'locale', 'currency')
    request_queue_hotel_id: Dict = {'id': hotel_id}
    request_queue.update(request_queue_hotel_id)

    hotel_info: str = object_search(search_hotel_info.__name__, request_queue, message)

    if len(hotel_info) == 0:
        logger.info(f'message {message.from_user.id}: Информация об отеле {hotel_id=} отсутствует в базе')
        bot.send_message(message.chat.id, f'Информация об отеле {hotel_id=} отсутствует в базе')
    else:
        logger.info(f'message {message.from_user.id}: Информация об отеле {hotel_id=} отправлена пользователю')
        save_history_txt(message, hotel_id, hotel_info)

        bot.send_message(message.chat.id, hotel_info, disable_web_page_preview=True)
        search_hotel_photos(message, request_queue_hotel_id, photo_from_db, bot)


def create_keyboard(keyboard: List, row: int, question: str, message: Message, bot) -> None:
    """Создает inline клавиатуру по запросу пользователя"""
    this_keyboard = InlineKeyboard(keyboard, row)
    keyboard: InlineKeyboardMarkup = this_keyboard.create_keys()
    bot.send_message(message.chat.id, text=question, reply_markup=keyboard)


def number_photos(message: Message, bot) -> None:
    """
    Проверяет введенное пользователем число фотографий и вызывает следующую функцию number_guests (если проверка
    успешная) или производится повторный запрос (если данные не прошли проверку)
    :param bot: бот
    :param message: Полученное в чате сообщение
    """
    amount_photos: str = message.text
    if not amount_photos.isdigit() or int(amount_photos) not in range(2, 11):
        logger.info(f'message {message.from_user.id}: Количество фотографий не корректное')
        msg = bot.send_message(message.chat.id,
                               'Введено не число от 2 до 10\nПопробуйте ввести количество фотографий еще раз:')
        bot.register_next_step_handler(msg, number_photos, bot)
    else:
        logger.info(f'message {message.from_user.id}: Количество фотографий корректное')
        update_save(message, 'hotel_pics', amount_photos)
        msg = bot.send_message(message.chat.id,
                               'Сколько человек будет проживать в отеле:')
        bot.register_next_step_handler(msg, number_guests, bot)


def set_price_range(message: Message, bot) -> None:
    """
    Проверяет введенные пользователем минимальную и максимальную цены, вызывает следующую функцию set_distance
     (если проверка успешная) или производится повторный запрос (если данные не прошли проверку)
    :param bot: бот
    :param message: Полученное в чате сообщение
    """
    cur_price: str = message.text
    if get_value_from_save(message, 'price_start') == '':
        text = 'минимальная'
    else:
        text = 'максимальная'
    if not cur_price.isdigit() or int(cur_price) < 0:
        logger.info(f'message {message.from_user.id}: Введенная {text} цена {cur_price} не корректна')
        msg = bot.send_message(message.chat.id,
                               f'Введенная {text} цена не корректна\n'
                               f'Цена должна быть положительным и целым числом\n'
                               f'Попробуйте ввести цену еще раз:')
        bot.register_next_step_handler(msg, set_price_range, bot)

    else:
        if get_value_from_save(message, 'price_start') == '':
            update_save(message, 'price_start', cur_price)
            if get_value_from_save(message, 'locale') == 'ru_RU':
                price = 'в рублях'
            else:
                price = 'в долларах'
            msg = bot.send_message(message.chat.id,
                                   f'Введите максимальную цену за сутки проживания в отеле, {price}')
            bot.register_next_step_handler(msg, set_price_range, bot)
        else:
            if cur_price == '0':
                logger.info(f'message {message.from_user.id}: Введенная {text} цена не может быть равна 0')
                msg = bot.send_message(message.chat.id,
                                       f'Введенная {text} цена не может быть равна 0\nПопробуйте ввести цену еще раз:')
                bot.register_next_step_handler(msg, set_price_range, bot)
            else:
                price_start = int(get_value_from_save(message, 'price_start'))
                price_stop = int(cur_price)
                if price_start >= price_stop:
                    logger.info(f'message {message.from_user.id}: максимальная цена должна быть больше минимальной')
                    update_save(message, 'price_start', '')
                    msg = bot.send_message(message.chat.id,
                                           'Максимальная цена должна быть больше минимальной\n'
                                           'Попробуйте ввести минимальную и максимальную цену еще раз:')
                    bot.register_next_step_handler(msg, set_price_range, bot)
                else:
                    update_save(message, 'price_stop', price_stop)
                    logger.info(f'message {message.from_user.id}: Цены диапазона введены корректно')
                    msg = bot.send_message(message.chat.id,
                                           f'Введите максимальное расстояние от центра города для отбора отелей\n'
                                           f'Рекомендация (для получения оперативного ответа):'
                                           f'расстояние вводить не более 10 км')
                    bot.register_next_step_handler(msg, set_distance, bot)


def set_distance(message: Message, bot) -> None:
    """
    Проверяет введенную пользователем удаленность от центра города и вызывает следующую функцию search_hotel_info
    (если проверка успешная) или производится повторный запрос (если данные не прошли проверку)
    :param bot: бот
    :param message: Полученное в чате сообщение
    """
    distance: str = message.text
    distance = re.sub(',', '.', distance)

    def is_float(number: str):
        try:
            float(number)
            return True
        except ValueError:
            return False
    if not is_float(distance) or float(distance) <= 0:
        logger.info(f'message {message.from_user.id}: Введенное расстояние не корректное')
        msg = bot.send_message(message.chat.id,
                               'Введенное расстояние не корректное\nПопробуйте ввести его еще раз:')
        bot.register_next_step_handler(msg, set_distance, bot)
    else:
        logger.info(f'message {message.from_user.id}: Введенное расстояние корректное')
        update_save(message, 'distance', float(distance))
        search_hotels(message, bot)


def search_hotel_photos(message: Message, request_queue_hotel_id: Dict, photo_from_db: str, bot) -> None:
    """
    Формирует запрос для поиска фотографий отеля и отправляет их затем пользователю.
    :param bot: бот
    :param request_queue_hotel_id: словарь с id отеля для запроса фотографий
    :param photo_from_db: количество фотографий запрашиваемого отеля
    :param message: Полученное в чате сообщение
    """
    photo_album: List = object_search(search_hotel_photos.__name__, request_queue_hotel_id, message)

    if int(photo_from_db) <= len(photo_album):
        pics: int = int(photo_from_db)
    else:
        pics: int = len(photo_album)
        bot.send_message(message.chat.id, f'На сайте найдено всего {len(photo_album)} фотографий')
    hotel_id = request_queue_hotel_id['id']
    medias = [InputMediaPhoto(pic) for pic in photo_album[:pics]]
    save_history_photo(message, photo_album[:pics], hotel_id)
    bot.send_media_group(message.chat.id, medias)
    logger.info(f'message {message.from_user.id}:'
                f' {len(photo_album[:pics])} фотографий отеля отправлено пользователю')


def create_database() -> None:
    """Создает таблицы Session и HistoryQuery в базе sqlite"""
    with db:
        db.create_tables([Session, HistoryQuery])
        logger.info(f'message: таблицы Session и HistoryQuery созданы или существуют')


def add_new_save_session(message: Message, sort_order: str) -> None:
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
                                 check_out='checkOut', hotel_pics='pics', price_start='priceMin',
                                 price_stop='priceMax', distance='distance', datetime_query='datetime_query',
                                 root_user_query='root_user_query')
            first_save.save()
            logger.info(f'message {message.from_user.id}: Первая запись таблицы sessions создана')

        session = Session(chat_id=message.chat.id, sort_order=sort_order, query='', city_id='', locale='',
                          currency='', number_hotels='', number_persons='', check_in='', check_out='',
                          hotel_pics='', price_start='', price_stop='', distance='', page_number='1',
                          datetime_query=datetime.now().strftime("%d-%m-%y %H-%M-%S"), root_user_query='')
        session.save()
        logger.info(f'message {message.from_user.id}: Начальная запись текущего  запроса для session создана')


def update_save(message: Message, update_key: str, update_value: Union[str, date, float]) -> None:
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


def get_value_from_save(message: Message, column_from_save: str) -> Union[str, date, float]:
    """
    Получает данные из соответствующей колонки текущего запроса пользователя
    :param column_from_save: Название колонки в таблице Session
    :param message: Полученное в чате сообщение
    :return: value
    """
    with db:
        cur_query = Session.select().where(Session.chat_id == message.chat.id).limit(1).order_by(Session.id.desc())[0]
        value: Union[str, date, float] = eval(f"cur_query.{column_from_save}")
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


def save_history_txt(message: Message, hotel_id: str, hotel_info: str) -> None:
    """
    Создает файл hotel_info.txt с данными по выбранному отелю и сохраняет его в папке соответствующего
     запроса для вызова через history
    :param hotel_id: id отеля
    :param hotel_info: Информация об отеле для сохранения
    :param message: Полученное в чате сообщение
    """
    root_history = os.path.join(os.getcwd(), 'history')
    if not os.path.isdir(root_history):
        os.mkdir(root_history)
    root_telegram_user = os.path.join(root_history, str(message.chat.id))
    if not os.path.isdir(root_telegram_user):
        os.mkdir(root_telegram_user)
    datetime_current_query = get_value_from_save(message, 'datetime_query')
    root_user_query = os.path.join(root_telegram_user, datetime_current_query)
    if not os.path.isdir(root_user_query):
        os.mkdir(root_user_query)
        update_save(message, 'root_user_query', re.escape(root_telegram_user))
    file_name = os.path.join(root_user_query, str(hotel_id) + '_hotel_info.txt')
    if not os.path.isfile(file_name):
        with open(file_name, 'w', encoding='utf-8') as file:
            file.write(hotel_info)


def save_history_db(message: Message, hotels_id: str) -> None:
    """ Создает запись истории последнего запроса для пользователя в таблице HistoryQuery """
    with db:
        history = HistoryQuery(chat_id=message.chat.id,
                               sort_order=way_sorting[get_value_from_save(message, 'sort_order')],
                               datetime_query=get_value_from_save(message, 'datetime_query'),
                               city=get_value_from_save(message, 'query'),
                               hotels_id=hotels_id,
                               root_user_query=get_value_from_save(message, 'root_user_query'))
        history.save()
        logger.info(f'message {message.from_user.id}: Запись сохранения для HistoryQuery создана')
    delete_oldest_files(message)


def save_history_photo(message: Message, photo_album: List[str], hotel_id: str) -> None:
    """
    Создает файл list_pics.txt с данными фотографий по выбранному отелю и сохраняет его и фотографии
    в папке соответствующего запроса для вызова через history
    :param photo_album: Список url фотографий выбранного отеля
    :param hotel_id: id запрашиваемого отеля
    :param message: Полученное в чате сообщение
    """
    current_root = get_value_from_save(message, 'root_user_query')
    datetime_query = get_value_from_save(message, 'datetime_query')
    name_img = os.path.join(current_root, datetime_query, str(hotel_id) + '_pics.txt')
    if not os.path.isfile(name_img):
        with open(name_img, 'a', encoding='utf-8') as out_list:
            out_list.write('\n'.join(photo_album))
        logger.info(f'message {message.from_user.id}: Файл {hotel_id}_pics.txt в {datetime_query} папку сохранен')


def get_value_for_history(message: Message, bot) -> None:
    """
    Создает inline клавиатуру для выбора последних сохраненных запросов в history
    :param bot: бот
    :param message: Полученное в чате сообщение
    """
    with db:
        cur_query = HistoryQuery.select().where(HistoryQuery.chat_id == message.chat.id).limit(3).order_by(
            HistoryQuery.id.desc())
        if len(cur_query) == 3:
            sort_1, datetime_1, = cur_query[0].sort_order, cur_query[0].datetime_query
            city_1, hotel_1 = cur_query[0].city, f'отелей: {len(cur_query[0].hotels_id.split())}'
            sort_2, datetime_2, = cur_query[1].sort_order, cur_query[1].datetime_query
            city_2, hotel_2 = cur_query[1].city, f'отелей: {len(cur_query[1].hotels_id.split())}'
            sort_3, datetime_3, = cur_query[2].sort_order, cur_query[2].datetime_query
            city_3, hotel_3 = cur_query[2].city, f'отелей: {len(cur_query[2].hotels_id.split())}'
            button = [(sort_1 + ' от ' + datetime_1 + ' ' + city_1 + ' ' + hotel_1, datetime_1 + '.his'),
                      (sort_2 + ' от ' + datetime_2 + ' ' + city_2 + ' ' + hotel_2, datetime_2 + '.his'),
                      (sort_3 + ' от ' + datetime_3 + ' ' + city_3 + ' ' + hotel_3, datetime_3 + '.his')]
            create_keyboard(button, 1, 'Выберите один из трех последних запросов', message, bot)
        elif len(cur_query) == 2:
            sort_1, datetime_1, = cur_query[0].sort_order, cur_query[0].datetime_query
            city_1, hotel_1 = cur_query[0].city, f'отелей: {len(cur_query[0].hotels_id.split())}'
            sort_2, datetime_2, = cur_query[1].sort_order, cur_query[1].datetime_query
            city_2, hotel_2 = cur_query[1].city, f'отелей: {len(cur_query[1].hotels_id.split())}'
            button = [(sort_1 + ' от ' + datetime_1 + ' ' + city_1 + ' ' + hotel_1, datetime_1 + '.his'),
                      (sort_2 + ' от ' + datetime_2 + ' ' + city_2 + ' ' + hotel_2, datetime_2 + '.his')]
            create_keyboard(button, 1, 'Выберите один из двух последних запросов', message, bot)
        elif len(cur_query) == 1:
            sort_1, datetime_1, = cur_query[0].sort_order, cur_query[0].datetime_query
            city_1, hotel_1 = cur_query[0].city, f'отелей: {len(cur_query[0].hotels_id.split())}'
            button = [(sort_1 + ' от ' + datetime_1 + ' ' + city_1 + ' ' + hotel_1, datetime_1 + '.his')]
            create_keyboard(button, 1, 'Ваш единственный запрос', message, bot)
        else:
            if not cur_query.exists():
                bot.send_message(message.chat.id, 'История Ваших запросов пока еще пуста,'
                                                  ' скорее всего Вы еще не делали запросов')


def show_history(message: Message, user_query: str, bot) -> None:
    """
    Отправляет выбранный пользователем запрос из HistoryQuery
    :param user_query: Время выбранного запроса
    :param bot: бот
    :param message: Полученное в чате сообщение
    """
    with db:
        cur_query = HistoryQuery.get(HistoryQuery.chat_id == message.chat.id,
                                     HistoryQuery.datetime_query == user_query)

    list_hotels_id: List = cur_query.hotels_id.split()
    root_current_save = os.path.join(cur_query.root_user_query, user_query)
    for hotel_id in list_hotels_id:
        hotel_info = os.path.join(root_current_save, hotel_id + '_hotel_info.txt')
        hotel_pics = os.path.join(root_current_save, hotel_id + '_pics.txt')
        if os.path.isfile(hotel_info):
            with open(hotel_info, 'r', encoding='utf-8') as info:
                bot.send_message(message.chat.id, info.read(), disable_web_page_preview=True)
                logger.info(f'message {message.from_user.id}: Информация по отелю согласно запроса от {user_query} '
                            f'отправлена пользователю')
        if os.path.isfile(hotel_pics):
            with open(hotel_pics, 'r', encoding='utf-8') as pics:
                medias = [InputMediaPhoto(pic) for pic in pics.read().split('\n')]
            bot.send_media_group(message.chat.id, medias)
            logger.info(f'message {message.from_user.id}: фото отеля {hotel_id=} отправлены пользователю')


def delete_oldest_files(message: Message) -> None:
    """
    Удаляет старые запросы пользователя из HistoryQuery и локального диска, оставляя 3 последних запроса пользователя
    :param message: Полученное в чате сообщение
    """
    with db:
        cur_query = HistoryQuery.select().where(HistoryQuery.chat_id == message.chat.id).order_by(
            HistoryQuery.id.desc())
        if len(cur_query) < 4:
            logger.info(f'message {message.from_user.id}: Очистка таблицы HistoryQuery не требуется')
        else:
            root_for_delete = os.path.join(cur_query[3].root_user_query, cur_query[3].datetime_query)
            shutil.rmtree(root_for_delete)
            cur_query[3].delete_instance()
            logger.info(f'message {message.from_user.id}:'
                        f' Запрос от {cur_query[3].datetime_query} из HistoryQuery удален')
