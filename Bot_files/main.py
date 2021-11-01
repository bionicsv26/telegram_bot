import os
from dotenv import load_dotenv
import telebot

load_dotenv()

bot = telebot.TeleBot(os.getenv('TOKEN_TELEGRAM'))
print('Bot is starting...')


@bot.message_handler(commands=['start'])
def start_handler(message):
    bot.send_message(message.chat.id, 'Приветствую, я постараюсь помочь Вам в поиске')


@bot.message_handler(commands=['hello-world'])
def commands_handler(message):
    bot.send_sticker(message.chat.id, 'CAACAgIAAxkBAAEDIzthdCfdrJynvKgP8LyIvQbVCzVOowACpBMAAvB-oEthm8UuvuFx7iEE')


@bot.message_handler(content_types=['text'])
def text_handler(message):
    bot.send_message(message.chat.id, message.text)


bot.polling(non_stop=True)
