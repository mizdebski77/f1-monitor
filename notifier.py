"""
F1 Monitor - Moduł powiadomień Telegram
Wysyła sformatowane powiadomienia przez Telegram Bot API.
Używa bezpośrednich requestów HTTP (bez zewnętrznych bibliotek bota).
"""

import time
from typing import Dict, Optional
import requests
from loguru import logger

import config


# ============================================================
# TELEGRAM API
# ============================================================
TELEGRAM_API_BASE = "https://api.telegram.org/bot{token}/{method}"


def _telegram_request(method: str, payload: Dict, retries: int = 3) -> Optional[Dict]:
    """
    Wykonuje request do Telegram Bot API.
    Obsługuje retry z exponential backoff.
    """
    url = TELEGRAM_API_BASE.format(
        token=config.TELEGRAM_BOT_TOKEN,
        method=method,
    )

    for attempt in range(retries):
        try:
            response = requests.post(
                url,
                json=payload,
                timeout=15,
            )
            data = response.json()

            if data.get("ok"):
                return data.get("result")
            else:
                error_code = data.get("error_code", 0)
                description = data.get("description", "Unknown error")

                if error_code == 429:
                    # Rate limit - czekamy
                    retry_after = data.get("parameters", {}).get("retry_after", 30)
                    logger.warning(f"Telegram rate limit - czekam {retry_after}s")
                    time.sleep(retry_after)
                    continue

                elif error_code == 400:
                    logger.error(f"Telegram błąd 400: {description}")
                    # Nie retry dla złego requesta
                    return None

                else:
                    logger.error(f"Telegram API błąd {error_code}: {description}")
                    if attempt < retries - 1:
                        time.sleep(5 * (attempt + 1))

        except requests.Timeout:
            logger.warning(f"Telegram timeout (próba {attempt+1}/{retries})")
            if attempt < retries - 1:
                time.sleep(10)
        except requests.RequestException as e:
            logger.error(f"Telegram network błąd: {e}")
            if attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
        except Exception as e:
            logger.error(f"Telegram nieoczekiwany błąd: {e}")
            return None

    return None


def send_message(text: str, parse_mode: str = None) -> bool:
    """
    Wysyła wiadomość tekstową na Telegram.
    Automatycznie dzieli długie wiadomości (limit 4096 znaków).
    """
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        logger.error("Brak konfiguracji Telegram (BOT_TOKEN lub CHAT_ID)")
        return False

    # Telegram limit: 4096 znaków
    MAX_MSG_LEN = 4096

    # Podziel długą wiadomość
    chunks = []
    if len(text) > MAX_MSG_LEN:
        # Dziel po liniach żeby nie ciąć w środku słowa
        lines = text.split("\n")
        current_chunk = []
        current_len = 0

        for line in lines:
            line_len = len(line) + 1
            if current_len + line_len > MAX_MSG_LEN:
                if current_chunk:
                    chunks.append("\n".join(current_chunk))
                current_chunk = [line]
                current_len = line_len
            else:
                current_chunk.append(line)
                current_len += line_len

        if current_chunk:
            chunks.append("\n".join(current_chunk))
    else:
        chunks = [text]

    success = True
    for i, chunk in enumerate(chunks):
        payload = {
            "chat_id": config.TELEGRAM_CHAT_ID,
            "text": chunk,
            "disable_web_page_preview": True,
        }

        result = _telegram_request("sendMessage", payload)
        if result:
            logger.debug(f"Telegram: wiadomość wysłana (część {i+1}/{len(chunks)})")
        else:
            logger.error(f"Telegram: nie udało się wysłać części {i+1}")
            success = False

        # Małe opóźnienie między częściami
        if i < len(chunks) - 1:
            time.sleep(0.5)

    return success


# ============================================================
# FORMATOWANIE POWIADOMIEŃ
# ============================================================
def format_news_notification(article: Dict) -> str:
    """
    Formatuje powiadomienie o nowym newsie F1.
    Format zgodny z wymaganiem z briefu.
    """
    priority = article.get("priority", "LOW")
    emoji = config.PRIORITY_EMOJI.get(priority, "📰")

    title = article.get("title", "Brak tytułu")
    source = article.get("source_name", "Nieznane")
    url = article.get("url", "")
    description = article.get("description", "")
    published_at = article.get("published_at", "")

    # Formatowanie daty
    date_str = ""
    if published_at:
        try:
            from datetime import datetime
            if "T" in published_at:
                dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                date_str = dt.strftime("%d.%m.%Y %H:%M UTC")
            else:
                date_str = published_at[:16]
        except Exception:
            date_str = published_at[:16]

    # Skrócony opis (max 200 znaków)
    short_desc = description[:197] + "..." if len(description) > 200 else description
    if not short_desc:
        short_desc = "Brak opisu"

    # Priorytet po polsku
    priority_pl = {
        "BREAKING": "🔴 BREAKING - Przełomowa informacja",
        "HIGH": "🟠 HIGH - Ważna informacja",
        "MEDIUM": "🟡 MEDIUM - Standardowa informacja",
        "LOW": "🟢 LOW - Ciekawostka",
    }.get(priority, priority)

    message = f"""{emoji} NOWY NEWS F1 {emoji}

📌 Tytuł: {title}

📡 Źródło: {source}

🏷️ Priorytet: {priority_pl}

📝 Krótki opis:
{short_desc}"""

    if date_str:
        message += f"\n\n⏰ Data: {date_str}"

    if url:
        message += f"\n\n🔗 Link: {url}"

    message += "\n\n─────────────────────"
    message += "\n🏎️ F1 Monitor Bot"

    return message


def format_startup_message() -> str:
    """Wiadomość startowa systemu."""
    enabled_sources = len([s for s in config.RSS_SOURCES if s.get("enabled", True)])

    return f"""🚀 *F1 Monitor uruchomiony!*

✅ System monitorowania F1 newsów jest aktywny.

⚙️ *Konfiguracja:*
• 📡 Źródeł RSS: {enabled_sources}
• ⏱️ Sprawdzanie co: {config.CHECK_INTERVAL_MINUTES} min
• 🎯 Próg duplikatów: {config.DUPLICATE_THRESHOLD:.0%}
• 🤖 Model AI: {config.HF_MODEL.split('/')[-1] if '/' in config.HF_MODEL else config.HF_MODEL}

🏁 Monitoruję: Motorsport, The Race, Autosport, Sky Sports, BBC F1, RaceFans i więcej...

_Otrzymasz powiadomienie gdy pojawi się nowy news!_
🏎️💨"""


def format_stats_message(stats: Dict) -> str:
    """Wiadomość ze statystykami."""
    by_priority = stats.get("by_priority", {})
    breaking = by_priority.get("BREAKING", 0)
    high = by_priority.get("HIGH", 0)
    medium = by_priority.get("MEDIUM", 0)
    low = by_priority.get("LOW", 0)

    return f"""📊 *Statystyki F1 Monitor*

📰 *Newsy dzisiaj:* {stats.get('today', 0)}
📚 *Łącznie w bazie:* {stats.get('total', 0)}
🔄 *Odfiltrowane duplikaty:* {stats.get('duplicates', 0)}

*Według priorytetu (unikalne):*
🚨 BREAKING: {breaking}
🔥 HIGH: {high}
📰 MEDIUM: {medium}
ℹ️ LOW: {low}

🏎️ _F1 Monitor Bot_"""


def _escape_markdown(text: str) -> str:
    """
    Escapes special Markdown characters.
    Zapobiega błędom parsowania Telegram Markdown.
    """
    if not text:
        return ""
    # Escapeujemy: _ * [ ] ( ) ~ ` > # + - = | { } . !
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    # Dla MarkdownV1 (prostszy) escapeujemy mniej
    # Używamy apostrofu dla MarkdownV1 - tylko te znaki są specjalne:
    # * _ ` [
    for char in ['*', '_', '`', '[']:
        text = text.replace(char, f'\\{char}')
    return text


# ============================================================
# TESTY POŁĄCZENIA
# ============================================================
def test_connection() -> bool:
    """
    Testuje połączenie z Telegram Bot API.
    Zwraca True jeśli OK.
    """
    if not config.TELEGRAM_BOT_TOKEN:
        logger.error("Brak TELEGRAM_BOT_TOKEN")
        return False

    result = _telegram_request("getMe", {})
    if result:
        bot_name = result.get("username", "unknown")
        logger.info(f"Telegram bot połączony: @{bot_name}")
        return True
    else:
        logger.error("Nie można połączyć z Telegram API")
        return False


def send_startup_notification() -> bool:
    """Wysyła powiadomienie o uruchomieniu systemu."""
    msg = format_startup_message()
    return send_message(msg)


def send_news_notification(article: Dict) -> bool:
    """Wysyła powiadomienie o nowym newsie."""
    msg = format_news_notification(article)
    success = send_message(msg)
    if success:
        logger.info(
            f"Telegram: wysłano [{article.get('priority')}] "
            f"{article.get('title', '')[:60]}"
        )
    return success


def send_stats_notification(stats: Dict) -> bool:
    """Wysyła statystyki do Telegrama."""
    msg = format_stats_message(stats)
    return send_message(msg)


def send_content_notification(article: Dict, content: Dict[str, str]) -> bool:
    """Wysyła wygenerowane treści social media do Telegrama."""
    from content_generator import format_content_for_telegram
    msg = format_content_for_telegram(article, content)
    return send_message(msg)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    print("🔍 Test połączenia Telegram...\n")

    if test_connection():
        print("✅ Połączenie OK!")

        print("\nWysyłam testową wiadomość...")
        test_article = {
            "title": "TEST: Hamilton signs new Ferrari contract extension",
            "source_name": "Motorsport.com",
            "priority": "BREAKING",
            "description": "This is a test message from F1 Monitor system",
            "url": "https://example.com/test",
            "published_at": "2025-01-01T12:00:00",
        }

        success = send_news_notification(test_article)
        print(f"Wysłanie: {'✅ OK' if success else '❌ BŁĄD'}")
    else:
        print("❌ Błąd połączenia - sprawdź TELEGRAM_BOT_TOKEN i TELEGRAM_CHAT_ID w .env")
