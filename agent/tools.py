"""
tools.py — все инструменты агента
"""

import os
import json
import requests
import feedparser
import qrcode
import subprocess
from pathlib import Path
from datetime import datetime
from ddgs import DDGS

MEMORY_PATH = Path(__file__).parent / "memory.json"
FILES_DIR = Path(__file__).parent / "files"
QR_DIR = Path(__file__).parent / "qr_codes"

FILES_DIR.mkdir(exist_ok=True)
QR_DIR.mkdir(exist_ok=True)


# ─── 1. WEB SEARCH ────────────────────────────────────────────────────────────

def web_search(query: str, max_results: int = 5) -> str:
    """Поиск в интернете через DuckDuckGo."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return "Ничего не найдено."
        output = []
        for i, r in enumerate(results, 1):
            output.append(f"{i}. {r['title']}\n   {r['body']}\n   Источник: {r['href']}")
        return "\n\n".join(output)
    except Exception as e:
        return f"Ошибка поиска: {e}"


# ─── 2. WEATHER ───────────────────────────────────────────────────────────────

CITY_COORDS = {
    "москва": (55.7558, 37.6173), "moscow": (55.7558, 37.6173),
    "санкт-петербург": (59.9311, 30.3609), "питер": (59.9311, 30.3609), "spb": (59.9311, 30.3609),
    "новосибирск": (54.9833, 82.8964), "екатеринбург": (56.8519, 60.6122),
    "казань": (55.7887, 49.1221), "нижний новгород": (56.2965, 43.9361),
    "самара": (53.2038, 50.1619), "омск": (54.9885, 73.3242),
    "краснодар": (45.0353, 38.9753), "ростов-на-дону": (47.2357, 39.7015),
    "сочи": (43.6028, 39.7342), "владивосток": (43.1056, 131.8735),
    "минск": (53.9006, 27.5590), "киев": (50.4501, 30.5234),
    "алматы": (43.2551, 76.9126), "ташкент": (41.2995, 69.2401),
    "london": (51.5074, -0.1278), "berlin": (52.5200, 13.4050),
    "paris": (48.8566, 2.3522), "new york": (40.7128, -74.0060),
    "tokyo": (35.6762, 139.6503), "beijing": (39.9042, 116.4074),
}

def _geocode_city(city: str) -> tuple[float, float]:
    """Координаты города: сначала кэш, потом API."""
    city_key = city.lower().strip()
    if city_key in CITY_COORDS:
        return CITY_COORDS[city_key]
    # Пробуем Open-Meteo geocoding
    try:
        url = "https://geocoding-api.open-meteo.com/v1/search"
        resp = requests.get(url, params={"name": city, "count": 1, "language": "ru"}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("results"):
            r = data["results"][0]
            return r["latitude"], r["longitude"]
    except Exception:
        pass
    # Пробуем Nominatim (OpenStreetMap)
    try:
        url = "https://nominatim.openstreetmap.org/search"
        resp = requests.get(
            url, params={"q": city, "format": "json", "limit": 1},
            headers={"User-Agent": "ai-agent/1.0"}, timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception:
        pass
    raise ValueError(f"Город '{city}' не найден. Попробуй: Москва, Питер, Сочи, Краснодар...")

def get_weather(city: str) -> str:
    """Текущая погода и прогноз на сегодня для указанного города."""
    try:
        lat, lon = _geocode_city(city)
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "current_weather": True,
            "hourly": "temperature_2m,precipitation_probability,windspeed_10m",
            "forecast_days": 1,
            "timezone": "auto",
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        cw = data["current_weather"]
        wmo_codes = {
            0: "ясно", 1: "почти ясно", 2: "переменная облачность", 3: "пасмурно",
            45: "туман", 48: "изморозь", 51: "лёгкая морось", 53: "морось", 55: "сильная морось",
            61: "небольшой дождь", 63: "умеренный дождь", 65: "сильный дождь",
            71: "небольшой снег", 73: "умеренный снег", 75: "сильный снег",
            80: "ливневый дождь", 95: "гроза", 99: "гроза с градом",
        }
        condition = wmo_codes.get(int(cw.get("weathercode", 0)), "неизвестно")
        result = (
            f"🌤 Погода в {city}:\n"
            f"  Температура: {cw['temperature']}°C\n"
            f"  Ветер: {cw['windspeed']} км/ч\n"
            f"  Условия: {condition}\n"
            f"  Время замера: {cw['time']}"
        )
        # Ближайшие часы
        hourly = data.get("hourly", {})
        times = hourly.get("time", [])[:6]
        temps = hourly.get("temperature_2m", [])[:6]
        precip = hourly.get("precipitation_probability", [])[:6]
        if times:
            result += "\n\n📅 Прогноз по часам:"
            for t, temp, pr in zip(times, temps, precip):
                hour = t.split("T")[1]
                result += f"\n  {hour} — {temp}°C, осадки {pr}%"
        return result
    except Exception as e:
        return f"Ошибка получения погоды: {e}"


# ─── 3. CRYPTO PRICE ──────────────────────────────────────────────────────────

COIN_ALIASES = {
    "биткоин": "bitcoin", "btc": "bitcoin",
    "эфир": "ethereum", "eth": "ethereum", "эфириум": "ethereum",
    "solana": "solana", "sol": "solana",
    "litecoin": "litecoin", "ltc": "litecoin",
    "dogecoin": "dogecoin", "doge": "dogecoin",
    "toncoin": "the-open-network", "ton": "the-open-network",
    "usdt": "tether", "tether": "tether",
}

def get_crypto_price(coin: str, currency: str = "usd") -> str:
    """Курс криптовалюты через CoinGecko (без API-ключа)."""
    try:
        coin_id = COIN_ALIASES.get(coin.lower(), coin.lower())
        currency = currency.lower()
        url = "https://api.coingecko.com/api/v3/simple/price"
        params = {"ids": coin_id, "vs_currencies": currency, "include_24hr_change": "true"}
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if coin_id not in data:
            return f"Монета '{coin}' не найдена. Попробуй: bitcoin, ethereum, solana, litecoin, dogecoin"
        price = data[coin_id][currency]
        change = data[coin_id].get(f"{currency}_24h_change", 0)
        sign = "📈" if change >= 0 else "📉"
        return (
            f"{sign} {coin_id.upper()} / {currency.upper()}\n"
            f"  Цена: {price:,.2f} {currency.upper()}\n"
            f"  Изменение за 24ч: {change:+.2f}%"
        )
    except Exception as e:
        return f"Ошибка получения курса: {e}"


# ─── 4. FILE READ / WRITE ─────────────────────────────────────────────────────

def file_read(filename: str) -> str:
    """Чтение файла из папки files/."""
    try:
        path = FILES_DIR / filename
        if not path.exists():
            return f"Файл '{filename}' не найден в {FILES_DIR}"
        return path.read_text(encoding="utf-8")
    except Exception as e:
        return f"Ошибка чтения файла: {e}"

def file_write(filename: str, content: str) -> str:
    """Запись текста в файл в папке files/."""
    try:
        path = FILES_DIR / filename
        path.write_text(content, encoding="utf-8")
        return f"✅ Файл '{filename}' сохранён ({len(content)} символов) → {path}"
    except Exception as e:
        return f"Ошибка записи файла: {e}"

def file_list() -> str:
    """Список файлов в папке files/."""
    files = list(FILES_DIR.iterdir())
    if not files:
        return "Папка files/ пуста."
    lines = [f"📁 Файлы в {FILES_DIR}:"]
    for f in sorted(files):
        size = f.stat().st_size
        lines.append(f"  - {f.name} ({size} байт)")
    return "\n".join(lines)


# ─── 5. MEMORY ────────────────────────────────────────────────────────────────

def save_to_memory(summary: str) -> str:
    """Сохранение резюме диалога в memory.json."""
    try:
        memory = []
        if MEMORY_PATH.exists():
            memory = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
        entry = {"timestamp": datetime.now().isoformat(), "summary": summary}
        memory.append(entry)
        # Храним последние 50 записей
        memory = memory[-50:]
        MEMORY_PATH.write_text(json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8")
        return f"✅ Резюме сохранено в память ({len(memory)} записей)"
    except Exception as e:
        return f"Ошибка сохранения памяти: {e}"

def read_memory(last_n: int = 5) -> str:
    """Чтение последних N записей из памяти."""
    try:
        if not MEMORY_PATH.exists():
            return "Память пуста."
        memory = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
        if not memory:
            return "Память пуста."
        recent = memory[-last_n:]
        lines = [f"🧠 Последние {len(recent)} записей из памяти:"]
        for e in recent:
            lines.append(f"\n[{e['timestamp'][:16]}]\n{e['summary']}")
        return "\n".join(lines)
    except Exception as e:
        return f"Ошибка чтения памяти: {e}"


# ─── 6. TERMINAL ──────────────────────────────────────────────────────────────

ALLOWED_COMMANDS = {"ls", "pwd", "echo", "cat", "date", "python", "pip", "dir", "type"}

def run_command(command: str) -> str:
    """Безопасное выполнение терминальных команд (ограниченный список)."""
    try:
        first_word = command.strip().split()[0].lower()
        if first_word not in ALLOWED_COMMANDS:
            return (
                f"⛔ Команда '{first_word}' заблокирована из соображений безопасности.\n"
                f"Разрешены: {', '.join(sorted(ALLOWED_COMMANDS))}"
            )
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=15
        )
        output = result.stdout or result.stderr or "(нет вывода)"
        return f"$ {command}\n{output}"
    except subprocess.TimeoutExpired:
        return "Команда прервана по таймауту (15 сек)"
    except Exception as e:
        return f"Ошибка выполнения команды: {e}"


# ─── 7. RSS NEWS PARSER (бонусный инструмент) ─────────────────────────────────

RSS_FEEDS = {
    "lenta": "https://lenta.ru/rss/news",
    "ria": "https://ria.ru/export/rss2/archive/index.xml",
    "habr": "https://habr.com/ru/rss/news/",
    "techcrunch": "https://techcrunch.com/feed/",
    "bbc": "http://feeds.bbci.co.uk/news/rss.xml",
    "coindesk": "https://www.coindesk.com/arc/outboundfeeds/rss/",
}

def get_news(source: str = "lenta", count: int = 5) -> str:
    """
    Парсинг RSS-лент новостей.
    Доступные источники: lenta, ria, habr, techcrunch, bbc, coindesk.
    Или передай прямой URL RSS-ленты.
    """
    try:
        url = RSS_FEEDS.get(source.lower(), source)
        feed = feedparser.parse(url)
        if not feed.entries:
            return f"Не удалось получить новости из '{source}'"
        items = feed.entries[:count]
        news_name = feed.feed.get("title", source)
        lines = [f"📰 {news_name} — последние {len(items)} новостей:\n"]
        for i, entry in enumerate(items, 1):
            title = entry.get("title", "Без заголовка")
            summary = entry.get("summary", "")[:150].replace("\n", " ")
            link = entry.get("link", "")
            published = entry.get("published", "")[:16] if entry.get("published") else ""
            lines.append(f"{i}. {title}")
            if published:
                lines.append(f"   🕐 {published}")
            if summary:
                lines.append(f"   {summary}...")
            lines.append(f"   🔗 {link}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"Ошибка получения новостей: {e}"


# ─── 8. QR-CODE GENERATOR (бонусный инструмент) ──────────────────────────────

def generate_qr(data: str, filename: str = None) -> str:
    """
    Генерация QR-кода для любого текста, ссылки или данных.
    Сохраняет PNG-файл в папку qr_codes/.
    """
    try:
        if not filename:
            safe = "".join(c if c.isalnum() else "_" for c in data[:20])
            filename = f"qr_{safe}_{datetime.now().strftime('%H%M%S')}.png"
        if not filename.endswith(".png"):
            filename += ".png"
        path = QR_DIR / filename

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        img.save(path)
        return (
            f"✅ QR-код создан!\n"
            f"   Данные: {data[:60]}{'...' if len(data) > 60 else ''}\n"
            f"   Файл: {path}\n"
            f"   Размер: {path.stat().st_size} байт"
        )
    except Exception as e:
        return f"Ошибка генерации QR-кода: {e}"


# ─── 9. SENTIMENT ANALYZER (бонусный инструмент) ─────────────────────────────

def analyze_sentiment(text: str) -> str:
    """
    Анализ тональности текста без внешних API.
    Использует расширенные словари позитивных/негативных слов (RU + EN).
    Возвращает: оценку, уверенность и ключевые маркеры.
    """
    text_lower = text.lower()
    words = text_lower.split()

    positive_ru = {
        "хорошо", "отлично", "прекрасно", "замечательно", "великолепно",
        "люблю", "нравится", "рад", "счастлив", "доволен", "успех",
        "победа", "выгода", "польза", "спасибо", "благодарю", "класс",
        "супер", "круто", "молодец", "браво", "интересно", "красиво",
        "удобно", "быстро", "надёжно", "профессионально", "эффективно",
        "рост", "прибыль", "доход", "позитивно", "оптимизм",
    }
    negative_ru = {
        "плохо", "ужасно", "отвратительно", "ненавижу", "злой", "грустно",
        "печально", "проблема", "ошибка", "сбой", "медленно", "неудобно",
        "разочарован", "недоволен", "жалко", "ужас", "кошмар", "провал",
        "убыток", "потеря", "риск", "опасно", "сложно", "дорого",
        "некачественно", "неэффективно", "негативно", "пессимизм", "скучно",
    }
    positive_en = {
        "good", "great", "excellent", "amazing", "awesome", "love", "like",
        "happy", "glad", "success", "profit", "fast", "easy", "nice",
        "beautiful", "fantastic", "wonderful", "brilliant", "perfect",
    }
    negative_en = {
        "bad", "terrible", "awful", "hate", "sad", "problem", "error",
        "slow", "difficult", "expensive", "fail", "loss", "risk", "ugly",
        "boring", "useless", "broken", "worst", "horrible", "annoying",
    }

    pos_words = positive_ru | positive_en
    neg_words = negative_ru | negative_en

    found_pos = [w for w in words if w in pos_words]
    found_neg = [w for w in words if w in neg_words]

    pos_score = len(found_pos)
    neg_score = len(found_neg)
    total = pos_score + neg_score

    # Простая нормализация по длине текста
    normalized_pos = pos_score / max(len(words), 1) * 100
    normalized_neg = neg_score / max(len(words), 1) * 100

    if total == 0:
        label = "😐 Нейтральный"
        confidence = 50
        emoji = "⚪"
    elif pos_score > neg_score * 1.5:
        label = "😊 Позитивный"
        confidence = min(95, 50 + int(normalized_pos * 3))
        emoji = "🟢"
    elif neg_score > pos_score * 1.5:
        label = "😠 Негативный"
        confidence = min(95, 50 + int(normalized_neg * 3))
        emoji = "🔴"
    else:
        label = "😐 Смешанный / Нейтральный"
        confidence = 40
        emoji = "🟡"

    result = (
        f"{emoji} Тональность: {label}\n"
        f"   Уверенность: ~{confidence}%\n"
        f"   Позитивных маркеров: {pos_score} {found_pos[:5]}\n"
        f"   Негативных маркеров: {neg_score} {found_neg[:5]}\n"
        f"   Слов проанализировано: {len(words)}\n"
        f"   Позитивность: {normalized_pos:.1f}% | Негативность: {normalized_neg:.1f}%"
    )
    return result


# ─── РЕЕСТР ИНСТРУМЕНТОВ ──────────────────────────────────────────────────────

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Поиск информации в интернете через DuckDuckGo",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Поисковый запрос"},
                    "max_results": {"type": "integer", "description": "Кол-во результатов (1-10)", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Текущая погода и почасовой прогноз для любого города",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "Название города на русском или английском"},
                },
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_crypto_price",
            "description": "Курс криптовалюты в реальном времени с изменением за 24 часа",
            "parameters": {
                "type": "object",
                "properties": {
                    "coin": {"type": "string", "description": "Название монеты: bitcoin, ethereum, solana, litecoin, dogecoin, ton..."},
                    "currency": {"type": "string", "description": "Валюта: usd, eur, rub", "default": "usd"},
                },
                "required": ["coin"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_read",
            "description": "Чтение содержимого файла из папки files/",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Имя файла"},
                },
                "required": ["filename"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_write",
            "description": "Запись текста в файл в папку files/",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "Имя файла"},
                    "content": {"type": "string", "description": "Содержимое файла"},
                },
                "required": ["filename", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "file_list",
            "description": "Список всех файлов в папке files/",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_to_memory",
            "description": "Сохранить резюме текущего диалога в долговременную память (memory.json)",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Краткое резюме того, что обсуждалось"},
                },
                "required": ["summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_memory",
            "description": "Прочитать последние записи из долговременной памяти",
            "parameters": {
                "type": "object",
                "properties": {
                    "last_n": {"type": "integer", "description": "Сколько последних записей показать", "default": 5},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_command",
            "description": "Выполнить простую терминальную команду (ls, pwd, echo, date...)",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Команда для выполнения"},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_news",
            "description": "Получить последние новости из RSS-ленты. Источники: lenta, ria, habr, techcrunch, bbc, coindesk",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Источник новостей или URL RSS-ленты", "default": "lenta"},
                    "count": {"type": "integer", "description": "Количество новостей (1-10)", "default": 5},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_qr",
            "description": "Создать QR-код для любого текста, ссылки или данных. Сохраняет PNG-файл.",
            "parameters": {
                "type": "object",
                "properties": {
                    "data": {"type": "string", "description": "Данные для кодирования в QR"},
                    "filename": {"type": "string", "description": "Имя файла (необязательно)"},
                },
                "required": ["data"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_sentiment",
            "description": "Анализ тональности текста: позитивный, негативный или нейтральный",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Текст для анализа"},
                },
                "required": ["text"],
            },
        },
    },
]

TOOLS_MAP = {
    "web_search": web_search,
    "get_weather": get_weather,
    "get_crypto_price": get_crypto_price,
    "file_read": file_read,
    "file_write": file_write,
    "file_list": file_list,
    "save_to_memory": save_to_memory,
    "read_memory": read_memory,
    "run_command": run_command,
    "get_news": get_news,
    "generate_qr": generate_qr,
    "analyze_sentiment": analyze_sentiment,
}
