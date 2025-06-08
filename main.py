import asyncio
import logging
import sqlite3
import aiohttp
import json
import os

from dotenv import load_dotenv, find_dotenv

from datetime import datetime, timedelta
from typing import Dict, List, Optional

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
ALPHA_VANTAGE_API_KEY = os.getenv('ALPHA_VANTAGE_API_KEY')


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class UserStates(StatesGroup):
    waiting_for_ticker = State()
    setting_alert = State()
    calculator_input = State()

class FinancialBot:
    def __init__(self):
        self.bot = Bot(token=BOT_TOKEN)
        self.dp = Dispatcher(storage=MemoryStorage())
        self.init_database()
        self.register_handlers()
        
    def init_database(self):
        """Ініціалізація бази даних"""
        conn = sqlite3.connect('financial_bot.db')
        cursor = conn.cursor()
        
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS watchlist (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                ticker TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                ticker TEXT,
                target_price REAL,
                alert_type TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        conn.commit()
        conn.close()

    async def get_stock_data(self, ticker: str) -> Optional[Dict]:
        """Отримання даних про акцію через Alpha Vantage API"""
        url = f"https://www.alphavantage.co/query"
        params = {
            'function': 'GLOBAL_QUOTE',
            'symbol': ticker,
            'apikey': ALPHA_VANTAGE_API_KEY
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    data = await response.json()
                    
                    if 'Global Quote' in data:
                        quote = data['Global Quote']
                        return {
                            'symbol': quote.get('01. symbol', ''),
                            'price': float(quote.get('05. price', 0)),
                            'change': float(quote.get('09. change', 0)),
                            'change_percent': quote.get('10. change percent', '0%'),
                            'volume': int(quote.get('06. volume', 0)),
                            'high': float(quote.get('03. high', 0)),
                            'low': float(quote.get('04. low', 0)),
                            'open': float(quote.get('02. open', 0)),
                            'previous_close': float(quote.get('08. previous close', 0))
                        }
        except Exception as e:
            logger.error(f"Помилка отримання даних для {ticker}: {e}")
            return None

    async def get_company_overview(self, ticker: str) -> Optional[Dict]:
        """Отримання детальної інформації про компанію"""
        url = f"https://www.alphavantage.co/query"
        params = {
            'function': 'OVERVIEW',
            'symbol': ticker,
            'apikey': ALPHA_VANTAGE_API_KEY
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params) as response:
                    data = await response.json()
                    if 'Symbol' in data:
                        return data
        except Exception as e:
            logger.error(f"Помилка отримання огляду для {ticker}: {e}")
            return None

    def save_user(self, user_id: int, username: str, first_name: str):
        """Збереження користувача в БД"""
        conn = sqlite3.connect('financial_bot.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO users (user_id, username, first_name)
            VALUES (?, ?, ?)
        ''', (user_id, username, first_name))
        conn.commit()
        conn.close()

    def add_to_watchlist(self, user_id: int, ticker: str):
        """Додавання акції до списку відстеження"""
        conn = sqlite3.connect('financial_bot.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO watchlist (user_id, ticker)
            VALUES (?, ?)
        ''', (user_id, ticker.upper()))
        conn.commit()
        conn.close()

    def get_watchlist(self, user_id: int) -> List[str]:
        """Отримання списку відстеження користувача"""
        conn = sqlite3.connect('financial_bot.db')
        cursor = conn.cursor()
        cursor.execute('SELECT ticker FROM watchlist WHERE user_id = ?', (user_id,))
        result = [row[0] for row in cursor.fetchall()]
        conn.close()
        return result

    def register_handlers(self):
        """Реєстрація обробників повідомлень"""
        
        @self.dp.message(Command("start"))
        async def start_handler(message: types.Message):
            user = message.from_user
            self.save_user(user.id, user.username or "", user.first_name or "")
            
            welcome_text = """
                ``🏦 <b>Вітаю у Фінансовому Консультанті!</b>

                Я допоможу вам з аналізом фондового ринку:

                📊 <b>Мої можливості:</b>
                • Аналіз акцій за тікером
                • Детальна інформація про компанії
                • Калькулятор інвестицій
                • Список відстеження акцій
                • Ринкові новини та поради

                <b>Команди:</b>
                /stock [TICKER] - аналіз акції
                /overview [TICKER] - огляд компанії
                /watchlist - ваш список відстеження
                /calculator - калькулятор інвестицій
                /tips - інвестиційні поради
                /help - допомога

                Введіть тікер акції або скористайтесь меню 👇``
            """
            
           
            kb = ReplyKeyboardBuilder()
            kb.add(KeyboardButton(text="📊 Аналіз акції"))
            kb.add(KeyboardButton(text="🏢 Огляд компанії"))
            kb.add(KeyboardButton(text="📋 Мій список"))
            kb.add(KeyboardButton(text="🧮 Калькулятор"))
            kb.add(KeyboardButton(text="💡 Поради"))
            kb.add(KeyboardButton(text="📈 Топ акції"))
            kb.adjust(2)
            
            await message.answer(welcome_text, parse_mode="HTML", 
                               reply_markup=kb.as_markup(resize_keyboard=True))

        @self.dp.message(Command("stock"))
        async def stock_command(message: types.Message):
            args = message.text.split()
            if len(args) < 2:
                await message.answer("Введіть тікер акції. Приклад: /stock AAPL")
                return
                
            ticker = args[1].upper()
            await self.send_stock_analysis(message, ticker)

        @self.dp.message(Command("overview"))
        async def overview_command(message: types.Message):
            args = message.text.split()
            if len(args) < 2:
                await message.answer("Введіть тікер компанії. Приклад: /overview AAPL")
                return
                
            ticker = args[1].upper()
            await self.send_company_overview(message, ticker)

        @self.dp.message(Command("watchlist"))
        async def watchlist_command(message: types.Message):
            watchlist = self.get_watchlist(message.from_user.id)
            
            if not watchlist:
                await message.answer("📋 Ваш список відстеження порожній.\n"
                                   "Додайте акції командою /stock [TICKER] та натисніть 'Додати до списку'")
                return
            
            text = "📋 <b>Ваш список відстеження:</b>\n\n"
            for ticker in watchlist:
                stock_data = await self.get_stock_data(ticker)
                if stock_data:
                    change_emoji = "📈" if stock_data['change'] > 0 else "📉"
                    text += f"{change_emoji} <b>{ticker}</b>: ${stock_data['price']:.2f} "
                    text += f"({stock_data['change_percent']})\n"
                else:
                    text += f"• <b>{ticker}</b>: Дані недоступні\n"
            
            await message.answer(text, parse_mode="HTML")

        @self.dp.message(Command("calculator"))
        async def calculator_command(message: types.Message, state: FSMContext):
            await message.answer(
                "🧮 <b>Калькулятор інвестицій</b>\n\n"
                "Введіть дані у форматі:\n"
                "<code>TICKER кількість_акцій ціна_покупки</code>\n\n"
                "Приклад: <code>AAPL 10 150.50</code>",
                parse_mode="HTML"
            )
            await state.set_state(UserStates.calculator_input)

        @self.dp.message(Command("tips"))
        async def tips_command(message: types.Message):
            tips = [
                "💡 <b>Диверсифікація</b> - не вкладайте всі гроші в одну акцію",
                "📊 <b>Аналізуйте P/E ratio</b> - показник переоціненості компанії",
                "🎯 <b>Довгострокові інвестиції</b> зазвичай менш ризиковані",
                "📈 <b>Dollar Cost Averaging</b> - купуйте регулярно малими сумами",
                "🔍 <b>Вивчайте компанію</b> перед інвестуванням",
                "⚖️ <b>Ризик та прибуток</b> завжди пов'язані",
                "📰 <b>Слідкуйте за новинami</b> компанії та ринку"
            ]
            
            tip_text = "💡 <b>Інвестиційні поради:</b>\n\n" + "\n\n".join(tips)
            await message.answer(tip_text, parse_mode="HTML")

        @self.dp.message(F.text == "📊 Аналіз акції")
        async def analyze_stock_button(message: types.Message, state: FSMContext):
            await message.answer("Введіть тікер акції для аналізу (наприклад: AAPL, TSLA, MSFT):")
            await state.set_state(UserStates.waiting_for_ticker)

        @self.dp.message(F.text == "🏢 Огляд компанії")
        async def company_overview_button(message: types.Message, state: FSMContext):
            await message.answer("Введіть тікер компанії для детального огляду:")
            await state.set_state(UserStates.waiting_for_ticker)

        @self.dp.message(F.text == "📋 Мій список")
        async def my_watchlist_button(message: types.Message):
            await watchlist_command(message)

        @self.dp.message(F.text == "🧮 Калькулятор")
        async def calculator_button(message: types.Message, state: FSMContext):
            await calculator_command(message, state)

        @self.dp.message(F.text == "💡 Поради")
        async def tips_button(message: types.Message):
            await tips_command(message)

        @self.dp.message(F.text == "📈 Топ акції")
        async def top_stocks_button(message: types.Message):
            top_stocks = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "META", "NVDA", "JPM"]
            
            kb = InlineKeyboardBuilder()
            for stock in top_stocks:
                kb.add(InlineKeyboardButton(text=stock, callback_data=f"analyze_{stock}"))
            kb.adjust(2)
            
            await message.answer(
                "📈 <b>Популярні акції:</b>\n\nОберіть акцію для аналізу:",
                parse_mode="HTML",
                reply_markup=kb.as_markup()
            )

        @self.dp.callback_query(F.data.startswith("analyze_"))
        async def analyze_callback(callback: types.CallbackQuery):
            ticker = callback.data.split("_")[1]
            await self.send_stock_analysis(callback.message, ticker)
            await callback.answer()

        @self.dp.callback_query(F.data.startswith("add_watchlist_"))
        async def add_watchlist_callback(callback: types.CallbackQuery):
            ticker = callback.data.split("_")[2]
            self.add_to_watchlist(callback.from_user.id, ticker)
            await callback.answer(f"✅ {ticker} додано до списку відстеження!")

        @self.dp.callback_query(F.data.startswith("overview_"))
        async def overview_callback(callback: types.CallbackQuery):
            ticker = callback.data.split("_")[1]
            await self.send_company_overview(callback.message, ticker)
            await callback.answer()

        @self.dp.message(StateFilter(UserStates.waiting_for_ticker))
        async def process_ticker(message: types.Message, state: FSMContext):
            ticker = message.text.upper().strip()
            await self.send_stock_analysis(message, ticker)
            await state.clear()

        @self.dp.message(StateFilter(UserStates.calculator_input))
        async def process_calculator(message: types.Message, state: FSMContext):
            try:
                parts = message.text.strip().split()
                if len(parts) != 3:
                    raise ValueError("Неправильний формат")
                
                ticker, shares_str, buy_price_str = parts
                shares = int(shares_str)
                buy_price = float(buy_price_str)
                
                # Отримуємо поточну ціну
                stock_data = await self.get_stock_data(ticker.upper())
                if not stock_data:
                    await message.answer("❌ Не вдалося знайти дані для цієї акції")
                    return
                
                current_price = stock_data['price']
                total_invested = shares * buy_price
                current_value = shares * current_price
                profit_loss = current_value - total_invested
                profit_percent = (profit_loss / total_invested) * 100
                
                profit_emoji = "📈" if profit_loss > 0 else "📉"
                
                result_text = f"""
🧮 <b>Розрахунок інвестицій</b>

📊 <b>Акція:</b> {ticker.upper()}
💰 <b>Поточна ціна:</b> ${current_price:.2f}
🔢 <b>Кількість акцій:</b> {shares}
💵 <b>Ціна покупки:</b> ${buy_price:.2f}

💸 <b>Інвестовано:</b> ${total_invested:.2f}
💰 <b>Поточна вартість:</b> ${current_value:.2f}

{profit_emoji} <b>Прибуток/Збиток:</b> ${profit_loss:.2f} ({profit_percent:+.2f}%)
                """
                
                await message.answer(result_text, parse_mode="HTML")
                
            except Exception as e:
                await message.answer(
                    "❌ Помилка в форматі даних!\n\n"
                    "Використовуйте формат: <code>TICKER кількість ціна</code>\n"
                    "Приклад: <code>AAPL 10 150.50</code>",
                    parse_mode="HTML"
                )
            
            await state.clear()

    async def send_stock_analysis(self, message: types.Message, ticker: str):
        """Відправка аналізу акції"""
        await message.answer("🔍 Шукаю дані...")
        
        stock_data = await self.get_stock_data(ticker)
        if not stock_data:
            await message.answer(f"❌ Не вдалося знайти дані для {ticker}")
            return
        
        change_emoji = "📈" if stock_data['change'] > 0 else "📉"
        change_color = "🟢" if stock_data['change'] > 0 else "🔴"
        
        analysis_text = f"""
📊 <b>Аналіз акції {stock_data['symbol']}</b>

💰 <b>Поточна ціна:</b> ${stock_data['price']:.2f}
{change_emoji} <b>Зміна:</b> {change_color} ${stock_data['change']:+.2f} ({stock_data['change_percent']})

📈 <b>Максимум дня:</b> ${stock_data['high']:.2f}
📉 <b>Мінімум дня:</b> ${stock_data['low']:.2f}
🎯 <b>Ціна відкриття:</b> ${stock_data['open']:.2f}
🔒 <b>Попереднє закриття:</b> ${stock_data['previous_close']:.2f}
📊 <b>Об'єм торгів:</b> {stock_data['volume']:,}

⏰ <b>Оновлено:</b> {datetime.now().strftime('%Y-%m-%d %H:%M')}
        """
        

        kb = InlineKeyboardBuilder()
        kb.add(InlineKeyboardButton(text="➕ Додати до списку", 
                                  callback_data=f"add_watchlist_{ticker}"))
        kb.add(InlineKeyboardButton(text="🏢 Огляд компанії", 
                                  callback_data=f"overview_{ticker}"))
        kb.adjust(1)
        
        await message.answer(analysis_text, parse_mode="HTML", 
                           reply_markup=kb.as_markup())

    async def send_company_overview(self, message: types.Message, ticker: str):
        """Відправка огляду компанії"""
        await message.answer("🔍 Завантажую дані про компанію...")
        
        overview_data = await self.get_company_overview(ticker)
        if not overview_data:
            await message.answer(f"❌ Не вдалося знайти дані про компанію {ticker}")
            return
        
        overview_text = f"""
🏢 <b>Огляд компанії {overview_data.get('Symbol', ticker)}</b>

📝 <b>Назва:</b> {overview_data.get('Name', 'N/A')}
🏭 <b>Сектор:</b> {overview_data.get('Sector', 'N/A')}
🔧 <b>Індустрія:</b> {overview_data.get('Industry', 'N/A')}
🌍 <b>Країна:</b> {overview_data.get('Country', 'N/A')}

💹 <b>Ринкова капіталізація:</b> ${overview_data.get('MarketCapitalization', 'N/A')}
💰 <b>P/E коефіцієнт:</b> {overview_data.get('PERatio', 'N/A')}
📊 <b>EPS:</b> {overview_data.get('EPS', 'N/A')}
💵 <b>Дивіденди:</b> {overview_data.get('DividendYield', 'N/A')}

📈 <b>52-тижневий максимум:</b> ${overview_data.get('52WeekHigh', 'N/A')}
📉 <b>52-тижневий мінімум:</b> ${overview_data.get('52WeekLow', 'N/A')}

📄 <b>Опис:</b> {overview_data.get('Description', 'Опис недоступний')[:500]}...
        """
        
        await message.answer(overview_text, parse_mode="HTML")

    async def start_bot(self):
        """Запуск бота"""
        logger.info("Бот запускається...")
        await self.dp.start_polling(self.bot)


async def main():
    bot = FinancialBot()
    await bot.start_bot()

if __name__ == "__main__":
    asyncio.run(main()) 