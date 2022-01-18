from typing import List, Dict
import json
import os
import re

from dotenv import load_dotenv
from loguru import logger
from peewee import *
import requests

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton


load_dotenv()

db = SqliteDatabase('botrequests/sqlite_bot.db')


class BaseModel(Model):
    """Класс, реализующий через peewee работу с базой sqlite"""
    class Meta:
        database = db


class Session(BaseModel):
    """Класс, реализующий таблицу Session"""
    id = PrimaryKeyField(unique=True)
    chat_id = CharField()
    sort_order = CharField()
    query = CharField()
    city_id = CharField()
    locale = CharField()
    currency = CharField()
    page_number = CharField()
    number_hotels = CharField()
    number_persons = CharField()
    check_in = DateField()
    check_out = DateField()
    hotel_id = CharField()
    hotel_pics = CharField()
    price_start = FloatField()
    price_stop = FloatField()
    distance = FloatField()

    class Meta:
        db_table = 'sessions'
        order_by = 'id'


class HistoryQuery(BaseModel):
    """Класс, реализующий таблицу HistoryQuery"""
    chat_id = CharField()
    saved_query = CharField()

    class Meta:
        db_table = 'history_queries'


class InlineKeyboard:
    """Класс, реализующий inline keyboard"""

    def __init__(self, keys: List[Tuple], rows: int):
        """
        первичная инициализация класса
        :param keys: список, содержащий названия и возвращаемые значения кнопок
        """
        self.keys: List = keys
        self.rows: int = rows
        self.key_list: List = []

    @property
    def keys(self) -> List:
        """
        Возвращает список кнопок
        :return: список кнопок
        """
        return self._keys

    @keys.setter
    def keys(self, keys: List) -> None:
        """
        Инициализирует переменную, содержащую список кнопок
        :param keys: список кнопок
        """
        self._keys = keys[:]

    @property
    def rows(self) -> int:
        """
        Возвращает количество столбцов клавиатуры
        :return: количество столбцов клавиатуры
        """
        return self._rows

    @rows.setter
    def rows(self, rows: int) -> None:
        """
        Инициализирует переменную, содержащую количество столбцов
        :param rows: количество столбцов клавиатуры
        """
        self._rows = rows

    def create_keys(self) -> InlineKeyboardMarkup:
        """
        Создает и возвращает inline-клавиатуру
        :return: клавиатура
        """
        bot_keyboard = InlineKeyboardMarkup(row_width=self.rows)
        for every_key in self.keys:
            self.key_list.append(InlineKeyboardButton(every_key[0], callback_data=every_key[1]))
        for all_keys in self.key_list:
            bot_keyboard.add(all_keys)
        return bot_keyboard


class Request:
    """
    Класс работы с rapidapi.com
    """

    def __init__(self, current_request: Dict, rapidapi_key: str = os.getenv('x-rapidapi-key')):
        """
        Инициализация переменных класса. Используются сеттеры ниже.
        :param токен подключения к rapidapi.com:
        """
        self.rapidapi_key = rapidapi_key
        self.this_query = current_request
        self._headers = {'x-rapidapi-key': self._rapidapi_key, 'x-rapidapi-host': "hotels4.p.rapidapi.com"}
        self._city_url = "https://hotels4.p.rapidapi.com/locations/v2/search"
        self._hotels_url = "https://hotels4.p.rapidapi.com/properties/list"
        self._hotel_info_url = "https://hotels4.p.rapidapi.com/properties/get-details"
        self._hotel_pics_url = "https://hotels4.p.rapidapi.com/properties/get-hotel-photos"

    @property
    def rapidapi_key(self) -> str:
        return self._rapidapi_key

    @rapidapi_key.setter
    def rapidapi_key(self, rapidapi_key: str):
        self._rapidapi_key: str = rapidapi_key

    @property
    def this_query(self) -> Dict:
        return self._this_query

    @this_query.setter
    def this_query(self, current_request: Dict):
        self._this_query: Dict = current_request

    def get_response(self, url: str, current_request: Dict) -> Dict:
        """
        Получает, сериализует и возвращает ответ от API
        В случае ошибки при получении ответа, возвращает пустой словарь
        :param url: url, по которому производится запрос
        :param current_request: словарь, содержащий переменные, участвующие в запросе
        :return: Dict
        """

        response = requests.request("GET", url, headers=self._headers, params=current_request)
        data = json.loads(response.text)
        return data

    def get_city(self) -> List[Tuple]:
        """
        Получает список id городов, имя которых совпадает с введенным пользователем
        В случае ошибки возвращает пустой список
        :return: список кортежей, содержащих имя города с географической привязкой и его id
        """
        try:
            variants_cities = self.get_response(self._city_url, self.this_query)
            cities = [(re.sub(r'<.+?>', '', elem.get('caption')), elem.get('destinationId') + '.city_id')
                      for elem in variants_cities.get('suggestions', [])[0].get('entities')
                      if elem.get('type') == 'CITY' and self.this_query["query"].lower() in elem.get('name').lower()]
        except IndexError:
            cities = []
            logger.info('Получен неправильный ответ от сайта при запросе города.')
        return cities

    def get_hotels(self) -> List[Tuple]:
        """
        Получает список отелей, подходящих под критерии, введенные пользователем.
        В случае ошибки возвращает пустой список
        :return: список кортежей, содержащих информацию об отелях
        """
        hotels = []
        try:
            variants_hotels = self.get_response(self._hotels_url, self.this_query)
            hotels = [(f"{hotel.get('name')} {'⭐️' * int(hotel.get('starRating', 0))}  "
                       f"{hotel.get('address').get('streetAddress')}. "
                       f"{str(hotel.get('ratePlan').get('price').get('current')).lower()} "
                       f"{hotel.get('landmarks')[0].get('distance').split(sep=' ')[0]} до центра",
                       str(hotel.get('id')) + '.hotel_id')
                      for hotel in variants_hotels['data']['body']['searchResults']['results']]

        except IndexError as err:
            logger.info(f'Получен неправильный ответ от сайта при запросе отелей: {err}')
        return hotels

    def get_hotel_info(self) -> str:
        """
        Получает от API и возвращает информацию об одном отеле.
        :return: строка, содержащая полную информацию об отеле
        """
        try:
            this_hotel = self.get_response(self._hotel_info_url, self.this_query)
            if this_hotel.get('result') != 'OK':
                hotel_info = 'Произошла ошибка при обращении к сайту.'
            else:
                name = this_hotel.get('data').get('body').get('propertyDescription').get('name')
                latitude = this_hotel.get('data').get('body').get('pdpHeader') \
                    .get('hotelLocation').get('coordinates').get('latitude')
                longitude = this_hotel.get('data').get('body').get('pdpHeader') \
                    .get('hotelLocation').get('coordinates').get('longitude')

                short_path = this_hotel.get('data').get('body').get('overview').get('overviewSections')
                header_overview = [short_path[num].get('title') for num in range(len(short_path))
                                   if short_path[num].get('type') == 'HOTEL_FEATURE']
                this_overview = [short_path[num].get('content') for num in range(len(short_path))
                                 if short_path[num].get('type') == 'HOTEL_FEATURE']
                header_around = [short_path[num].get('title') for num in range(len(short_path))
                                 if short_path[num].get('type') == 'LOCATION_SECTION']
                this_around = [short_path[num].get('content') for num in range(len(short_path))
                               if short_path[num].get('type') == 'LOCATION_SECTION']

                this_address = this_hotel.get('data').get('body').get('propertyDescription').get(
                    'address').get('fullAddress')
                this_price = str(this_hotel.get('data').get('body').get('propertyDescription').get(
                    'featuredPrice').get('currentPrice').get('formatted')) + ' ' + str(this_hotel.get('data').get(
                     'body').get('propertyDescription').get('featuredPrice').get('priceInfo', ''))
                this_map_widget = this_hotel.get('data').get('body').get('propertyDescription').get('mapWidget').\
                    get('staticMapUrl', '')

                dict_locale: dict = {'en_US': '', 'ru_RU': 'ru.'}
                box = dict_locale[self.this_query['locale']]
                hotel_url = f'https://www.{box}hotels.com/ho' + self.this_query['id']

                hotel_info = ''
                hotel_info += name + '\n\n'
                hotel_info += f'Адрес отеля: {this_address}\n'
                hotel_info += this_map_widget + '\n'
                hotel_info += f'Координаты отеля: {latitude}, {longitude}\n\n'
                hotel_info += '\n'.join(header_overview) + '\n\n'
                hotel_info += '\n'.join(*this_overview)
                hotel_info += '\n\n'
                hotel_info += '\n'.join(header_around) + '\n\n'
                hotel_info += '\n'.join(*this_around)
                hotel_info += '\n\n'
                hotel_info += this_price + '\n\n'
                hotel_info += f'Ссылка на страницу отеля на сайте hotels.com: {hotel_url}\n'

        except IndexError:
            hotel_info = 'Запрос составлен неверно, обратитесь к администратору.'
        return hotel_info

    def get_hotel_pics(self) -> List[str]:
        """
        Возвращает список url изображений отеля
        :return: список url изображений
        """
        pics: List = []
        try:
            pictures = self.get_response(self._hotel_pics_url, self.this_query)
            photo_hotel = pictures.get('hotelImages')
            if photo_hotel:
                for photo in photo_hotel:
                    pics.append(photo.get("baseUrl").replace('{size}', 'z'))
            return pics
        except IndexError:
            logger.info('Произошла ошибка при получении изображений отеля с id {}'.format(self.this_query['id']))
            return pics
