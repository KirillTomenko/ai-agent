"""
run.py — точка входа: красивый CLI-интерфейс агента
"""

import sys
import os
from colorama import init, Fore, Style
from agent import run_agent

init(autoreset=True)  # colorama

BANNER = f"""
{Fore.CYAN}╔══════════════════════════════════════════════════════╗
║          🤖  AI-АГЕНТ  —  Portfolio Edition          ║
║                                                      ║
║  Инструменты:                                        ║
║  🔍 Поиск  🌤 Погода  💰 Крипта  📂 Файлы           ║
║  📰 Новости  📷 QR-коды  🎭 Тональность             ║
║                                                      ║
║  Команды: /help  /memory  /clear  /exit              ║
╚══════════════════════════════════════════════════════╝{Style.RESET_ALL}
"""

HELP_TEXT = f"""
{Fore.YELLOW}━━━ ДОСТУПНЫЕ КОМАНДЫ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  /help     — показать это сообщение
  /memory   — показать историю памяти агента
  /clear    — очистить историю текущего диалога
  /exit     — выйти из агента

━━━ ПРИМЕРЫ ЗАПРОСОВ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  🔍  «Найди информацию о FastAPI»
  🌤  «Какая погода в Москве завтра?»
  💰  «Сколько стоит биткоин в рублях?»
  📰  «Последние новости с Habr»
  📷  «Создай QR-код для https://github.com/myrepo»
  🎭  «Проанализируй тональность: Этот продукт ужасен!»
  📂  «Создай файл notes.txt с текстом про Python»
  💡  «Найди курс ETH и сохрани его в файл crypto.txt»

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}
"""

def print_agent(text: str):
    print(f"\n{Fore.GREEN}🤖 Агент:{Style.RESET_ALL}")
    print(f"{text}\n")
    print(f"{Fore.CYAN}{'─' * 55}{Style.RESET_ALL}")

def print_error(text: str):
    print(f"\n{Fore.RED}❌ Ошибка: {text}{Style.RESET_ALL}\n")

def main():
    print(BANNER)
    print(f"{Fore.WHITE}Введи запрос или /help для справки.{Style.RESET_ALL}\n")

    conversation_history = []

    while True:
        try:
            user_input = input(f"{Fore.BLUE}Вы:{Style.RESET_ALL} ").strip()
        except (KeyboardInterrupt, EOFError):
            print(f"\n{Fore.YELLOW}До свидания!{Style.RESET_ALL}")
            sys.exit(0)

        if not user_input:
            continue

        # Встроенные команды
        if user_input.lower() == "/exit":
            print(f"\n{Fore.YELLOW}До свидания!{Style.RESET_ALL}")
            break

        if user_input.lower() == "/help":
            print(HELP_TEXT)
            continue

        if user_input.lower() == "/clear":
            conversation_history = []
            print(f"\n{Fore.YELLOW}История диалога очищена.{Style.RESET_ALL}\n")
            continue

        if user_input.lower() == "/memory":
            from agent.tools import read_memory
            print_agent(read_memory(10))
            continue

        # Запрос к агенту
        print(f"\n{Fore.YELLOW}⏳ Обрабатываю...{Style.RESET_ALL}")
        try:
            answer, conversation_history = run_agent(user_input, conversation_history)
            print_agent(answer)
        except Exception as e:
            print_error(str(e))
            if "api_key" in str(e).lower() or "authentication" in str(e).lower():
                print(f"{Fore.RED}💡 Проверь OPENAI_API_KEY и OPENAI_BASE_URL в файле .env{Style.RESET_ALL}\n")

if __name__ == "__main__":
    main()
