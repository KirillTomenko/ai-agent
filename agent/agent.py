"""
agent.py — ядро агента: цикл «думай → вызови инструмент → ответь»
"""

import json
import logging
import os
from openai import OpenAI
from dotenv import load_dotenv
from pathlib import Path

from .tools import TOOLS_SCHEMA, TOOLS_MAP, save_to_memory, read_memory

load_dotenv()

# ─── Логирование ──────────────────────────────────────────────────────────────
LOG_PATH = Path(__file__).parent / "agent.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("agent")

# ─── Клиент OpenAI (поддержка прокси через base_url) ─────────────────────────
client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY", "sk-..."),
    base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
)
MODEL = os.getenv("MODEL_NAME", "gpt-4o-mini")

SYSTEM_PROMPT = """Ты — умный AI-агент с набором инструментов. Отвечай на русском языке.

Твои возможности:
1. 🔍 web_search — поиск в интернете (DuckDuckGo)
2. 🌤 get_weather — погода для любого города
3. 💰 get_crypto_price — курс криптовалют
4. 📂 file_read / file_write / file_list — работа с файлами
5. 🧠 save_to_memory / read_memory — долговременная память
6. 💻 run_command — выполнение терминальных команд
7. 📰 get_news — свежие новости (lenta, ria, habr, techcrunch, bbc, coindesk)
8. 📷 generate_qr — генерация QR-кодов (сохраняет PNG)
9. 🎭 analyze_sentiment — анализ тональности любого текста

Правила работы:
- Всегда используй инструменты для получения актуальных данных
- Если запрос неоднозначен — уточни
- После каждого 5-го обмена сохраняй резюме диалога в память
- Давай структурированные, понятные ответы
- Если инструмент вернул ошибку — честно сообщи об этом и предложи альтернативу
"""


def run_agent(user_message: str, conversation_history: list) -> tuple[str, list]:
    """
    Запуск одного цикла агента.
    
    Args:
        user_message: сообщение пользователя
        conversation_history: история диалога (список dict role/content)
    
    Returns:
        (ответ агента, обновлённая история)
    """
    conversation_history.append({"role": "user", "content": user_message})
    log.info(f"[USER] {user_message[:100]}")

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + conversation_history

    # Цикл агента: LLM → инструмент → LLM → ... → финальный ответ
    max_iterations = 10
    for iteration in range(max_iterations):
        log.info(f"[AGENT] Итерация {iteration + 1}/{max_iterations}")

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS_SCHEMA,
            tool_choice="auto",
        )

        msg = response.choices[0].message
        finish_reason = response.choices[0].finish_reason
        log.info(f"[AGENT] finish_reason={finish_reason}")

        # Агент решил завершить — финальный ответ
        if finish_reason == "stop" or not msg.tool_calls:
            final_answer = msg.content or "(нет ответа)"
            log.info(f"[AGENT] Финальный ответ: {final_answer[:100]}")
            conversation_history.append({"role": "assistant", "content": final_answer})

            # Автосохранение памяти каждые 5 ходов
            if len(conversation_history) % 10 == 0:
                summary = f"Диалог из {len(conversation_history)} сообщений. Последнее: {user_message[:80]}"
                save_to_memory(summary)
                log.info("[MEMORY] Автосохранение резюме диалога")

            return final_answer, conversation_history

        # Агент хочет вызвать инструмент(ы)
        messages.append(msg)

        for tool_call in msg.tool_calls:
            tool_name = tool_call.function.name
            try:
                tool_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                tool_args = {}

            log.info(f"[TOOL] {tool_name}({tool_args})")

            if tool_name in TOOLS_MAP:
                try:
                    result = TOOLS_MAP[tool_name](**tool_args)
                    log.info(f"[TOOL] OK: {str(result)[:120]}")
                except Exception as e:
                    result = f"Ошибка выполнения {tool_name}: {e}"
                    log.error(f"[TOOL] ERROR: {e}")
            else:
                result = f"Инструмент '{tool_name}' не найден"
                log.warning(f"[TOOL] Неизвестный инструмент: {tool_name}")

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(result),
            })

    # Защита от бесконечного цикла
    fallback = "Достигнут лимит итераций. Попробуй переформулировать запрос."
    conversation_history.append({"role": "assistant", "content": fallback})
    return fallback, conversation_history
