"""
F1 Monitor - Główny orchestrator
Łączy wszystkie moduły w działający system.
Uruchomienie: python main.py
"""

import sys
import signal
import time
from datetime import datetime
from typing import List, Dict
import schedule
from loguru import logger

import config
import database
import monitor
import deduplicator
import prioritizer
import content_generator
import notifier


# ============================================================
# KONFIGURACJA LOGOWANIA
# ============================================================
def setup_logging():
    """Konfiguruje system logowania."""
    import os
    os.makedirs("logs", exist_ok=True)

    logger.remove()  # Usuń domyślny handler

    # Konsola - czytelny format
    logger.add(
        sys.stdout,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level:<8}</level> | "
            "<cyan>{name}</cyan> | "
            "{message}"
        ),
        level=config.LOG_LEVEL,
        colorize=True,
    )

    # Plik - pełny format z rotacją
    logger.add(
        config.LOG_FILE,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{function}:{line} | {message}",
        level="DEBUG",
        rotation=config.LOG_ROTATION,
        retention=config.LOG_RETENTION,
        encoding="utf-8",
    )

    logger.info("System logowania zainicjalizowany")


# ============================================================
# GŁÓWNA PĘTLA MONITOROWANIA
# ============================================================
def run_monitor_cycle():
    """
    Jeden cykl monitorowania:
    1. Pobierz newsy z wszystkich źródeł
    2. Deduplikacja
    3. Klasyfikacja priorytetów
    4. Zapis do bazy
    5. Wysyłka powiadomień
    6. Generowanie treści social media
    """
    cycle_start = datetime.utcnow()
    logger.info(f"{'='*50}")
    logger.info(f"Nowy cykl: {cycle_start.strftime('%Y-%m-%d %H:%M:%S UTC')}")

    # ── Krok 1: Pobierz newsy ────────────────────────────
    logger.info("📡 Krok 1: Pobieranie newsów...")
    try:
        raw_articles = monitor.fetch_all_news()
        logger.info(f"   Pobrano {len(raw_articles)} artykułów")
    except Exception as e:
        logger.error(f"Błąd pobierania newsów: {e}")
        return

    if not raw_articles:
        logger.info("Brak nowych artykułów w tym cyklu")
        return

    # ── Krok 2: Klasyfikacja priorytetów ─────────────────
    logger.info("🏷️  Krok 2: Klasyfikacja priorytetów...")
    try:
        classified = prioritizer.classify_articles(raw_articles)
    except Exception as e:
        logger.error(f"Błąd klasyfikacji: {e}")
        classified = raw_articles

    # ── Krok 3: Deduplikacja ──────────────────────────────
    logger.info("🔍 Krok 3: Deduplikacja...")
    try:
        recent_news = database.get_recent_titles(
            hours=config.DUPLICATE_WINDOW_HOURS
        )
        deduplicated = deduplicator.process_deduplication(
            classified, recent_news
        )
    except Exception as e:
        logger.error(f"Błąd deduplikacji: {e}")
        deduplicated = [{**a, "is_duplicate": False} for a in classified]

    # ── Krok 4: Zapis do bazy ─────────────────────────────
    logger.info("💾 Krok 4: Zapis do bazy danych...")
    saved_ids = []
    new_unique_count = 0

    for article in deduplicated:
        try:
            news_id = database.insert_news(article)
            if news_id:
                saved_ids.append((news_id, article))
                if not article.get("is_duplicate"):
                    new_unique_count += 1
        except Exception as e:
            logger.error(f"Błąd zapisu artykułu: {e}")

    logger.info(
        f"   Zapisano {len(saved_ids)} nowych, "
        f"{new_unique_count} unikalnych"
    )

    if new_unique_count == 0:
        logger.info("Brak nowych unikalnych newsów - cykl zakończony")
        return

    # ── Krok 5: Powiadomienia Telegram ───────────────────
    logger.info("📱 Krok 5: Wysyłanie powiadomień...")

    # Sprawdź anti-spam
    recent_notifications = database.count_recent_notifications(hours=1)
    if recent_notifications >= config.MAX_NOTIFICATIONS_PER_HOUR:
        logger.warning(
            f"Anti-spam: {recent_notifications} powiadomień w ostatniej godzinie "
            f"(limit: {config.MAX_NOTIFICATIONS_PER_HOUR}). Pomijam."
        )
    else:
        notification_count = 0
        for news_id, article in saved_ids:
            if article.get("is_duplicate"):
                continue

            # Limit powiadomień
            if notification_count >= 5:  # max 5 na raz
                logger.debug("Limit 5 powiadomień na cykl - pomijam resztę")
                break

            try:
                success = notifier.send_news_notification(article)
                if success:
                    database.mark_as_notified(news_id)
                    notification_count += 1
                    # Opóźnienie między powiadomieniami (anti-spam)
                    time.sleep(1)
                else:
                    logger.warning(f"Nie wysłano powiadomienia dla ID={news_id}")
            except Exception as e:
                logger.error(f"Błąd powiadomienia dla ID={news_id}: {e}")

        logger.info(f"   Wysłano {notification_count} powiadomień")

    # ── Krok 6: Generowanie treści social media ───────────
    logger.info("🤖 Krok 6: Generowanie treści social media...")

    # Sprawdź limit generowań
    recent_generations = database.count_recent_generations(hours=1)
    if recent_generations >= config.MAX_CONTENT_GENERATIONS_PER_HOUR:
        logger.warning(
            f"Limit generowań ({config.MAX_CONTENT_GENERATIONS_PER_HOUR}/h) wyczerpany - pomijam"
        )
    else:
        to_generate = database.get_news_without_content()
        gen_count = 0

        for news_article in to_generate:
            if gen_count >= 3:  # max 3 generowania na cykl
                break

            try:
                content = content_generator.generate_content(news_article)
                if content:
                    database.save_generated_content(
                        news_article["id"],
                        content,
                        model=config.HF_MODEL,
                    )
                    database.mark_content_generated(news_article["id"])

                    # Wyślij treści do Telegram
                    notifier.send_content_notification(news_article, content)
                    gen_count += 1
                    time.sleep(2)  # opóźnienie między generowaniami

            except Exception as e:
                logger.error(f"Błąd generowania treści dla ID={news_article['id']}: {e}")

        logger.info(f"   Wygenerowano treści dla {gen_count} newsów")

    # ── Podsumowanie cyklu ────────────────────────────────
    duration = (datetime.utcnow() - cycle_start).total_seconds()
    logger.info(f"✅ Cykl zakończony w {duration:.1f}s")


# ============================================================
# ZADANIA POMOCNICZE
# ============================================================
def run_daily_stats():
    """Wysyła codzienne statystyki do Telegrama (raz dziennie)."""
    try:
        stats = database.get_stats()
        notifier.send_stats_notification(stats)
        logger.info("Wysłano codzienne statystyki")
    except Exception as e:
        logger.error(f"Błąd wysyłania statystyk: {e}")


# ============================================================
# INICJALIZACJA
# ============================================================
def initialize():
    """
    Sprawdza konfigurację i inicjalizuje system.
    Zwraca True jeśli wszystko OK.
    """
    print("\n" + "="*60)
    print("  🏎️  F1 MONITOR - System monitorowania newsów F1")
    print("="*60 + "\n")

    # Sprawdź konfigurację
    errors = config.validate_config()
    warnings = [e for e in errors if "HuggingFace" in e]
    critical_errors = [e for e in errors if "TELEGRAM" in e]

    if warnings:
        for w in warnings:
            logger.warning(f"⚠️  {w}")
        logger.warning("Generator treści AI wyłączony - będą używane szablony")

    if critical_errors:
        for e in critical_errors:
            logger.critical(f"❌ {e}")
        print("\n❌ BŁĄD KRYTYCZNY: Brak konfiguracji Telegram!")
        print("   Uzupełnij .env plik (skopiuj z .env.example)")
        print("\n📖 Instrukcja:")
        print("   1. cp .env.example .env")
        print("   2. Utwórz bota przez @BotFather na Telegramie")
        print("   3. Wpisz token do .env")
        print("   4. Wyślij /start do bota i pobierz Chat ID przez @userinfobot")
        return False

    # Inicjalizuj bazę danych
    logger.info("Inicjalizuję bazę danych...")
    database.init_db()

    # Test połączenia Telegram
    logger.info("Testuję połączenie Telegram...")
    if not notifier.test_connection():
        logger.critical("❌ Nie można połączyć z Telegram! Sprawdź BOT_TOKEN.")
        return False

    logger.info("✅ Telegram połączony")

    # Wyślij powiadomienie startowe
    notifier.send_startup_notification()

    # Pokaż konfigurację
    enabled_sources = len([s for s in config.RSS_SOURCES if s.get("enabled", True)])
    logger.info(f"✅ Aktywnych źródeł RSS: {enabled_sources}")
    logger.info(f"✅ Interwał sprawdzania: {config.CHECK_INTERVAL_MINUTES} minut")
    logger.info(f"✅ Próg duplikatów: {config.DUPLICATE_THRESHOLD:.0%}")

    hf_status = "✅ AKTYWNY" if config.HUGGINGFACE_API_TOKEN else "⚠️ WYŁĄCZONY (brak tokenu)"
    logger.info(f"{'✅' if config.HUGGINGFACE_API_TOKEN else '⚠️'} Generator AI: {hf_status}")

    return True


# ============================================================
# GRACEFUL SHUTDOWN
# ============================================================
_running = True


def handle_shutdown(signum, frame):
    """Obsługuje sygnały zatrzymania (Ctrl+C, SIGTERM)."""
    global _running
    logger.info("\n⏹️  Otrzymano sygnał zatrzymania. Kończę gracefully...")
    _running = False


# ============================================================
# PUNKT WEJŚCIA
# ============================================================
def main():
    global _running

    # Setup logowania
    setup_logging()

    # Obsługa Ctrl+C
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    # Inicjalizacja
    if not initialize():
        sys.exit(1)

    # ── Konfiguracja harmonogramu ─────────────────────────
    logger.info(f"\n📅 Harmonogram:")
    logger.info(f"   Monitoring newsów: co {config.CHECK_INTERVAL_MINUTES} min")
    logger.info(f"   Statystyki dzienne: codziennie o 08:00")
    logger.info(f"\n🚀 System uruchomiony! Wciśnij Ctrl+C aby zatrzymać.\n")

    # Ustaw harmonogram
    schedule.every(config.CHECK_INTERVAL_MINUTES).minutes.do(run_monitor_cycle)
    schedule.every().day.at("08:00").do(run_daily_stats)

    # Uruchom pierwszy cykl od razu
    logger.info("Uruchamiam pierwszy cykl monitorowania...")
    run_monitor_cycle()

    # Główna pętla
    while _running:
        try:
            schedule.run_pending()
            time.sleep(10)  # sprawdzaj harmonogram co 10 sekund

        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"Nieoczekiwany błąd w głównej pętli: {e}")
            # Nie wychodź - próbuj dalej
            time.sleep(30)

    logger.info("👋 F1 Monitor zatrzymany. Do zobaczenia!")


# ============================================================
# CLI KOMENDY POMOCNICZE
# ============================================================
def run_once():
    """Uruchamia jeden cykl monitorowania bez schedulera."""
    setup_logging()
    database.init_db()
    run_monitor_cycle()


def show_stats():
    """Wyświetla statystyki z bazy danych."""
    setup_logging()
    database.init_db()
    stats = database.get_stats()

    print("\n📊 STATYSTYKI F1 MONITOR")
    print("=" * 40)
    print(f"Łącznie newsów:    {stats['total']}")
    print(f"Dzisiaj:           {stats['today']}")
    print(f"Duplikaty:         {stats['duplicates']}")
    print("\nWedług priorytetu:")
    for priority, count in sorted(stats['by_priority'].items()):
        emoji = config.PRIORITY_EMOJI.get(priority, "📰")
        print(f"  {emoji} {priority:<10}: {count}")


def test_all():
    """Testuje wszystkie komponenty systemu."""
    setup_logging()
    print("\n🔧 TEST WSZYSTKICH KOMPONENTÓW\n")

    # Test konfiguracji
    print("1. Konfiguracja:")
    errors = config.validate_config()
    if not errors:
        print("   ✅ OK")
    else:
        for e in errors:
            print(f"   ⚠️  {e}")

    # Test bazy danych
    print("\n2. Baza danych:")
    try:
        database.init_db()
        print("   ✅ OK")
    except Exception as e:
        print(f"   ❌ {e}")

    # Test Telegram
    print("\n3. Telegram:")
    if notifier.test_connection():
        print("   ✅ OK")
    else:
        print("   ❌ Błąd połączenia")

    # Test źródeł RSS
    print("\n4. RSS Sources:")
    monitor.test_sources()

    # Test klasyfikatora
    print("\n5. Klasyfikator priorytetów:")
    test_article = {
        "title": "Hamilton signs new Ferrari contract",
        "description": "Official announcement",
    }
    classified = prioritizer.classify_article(test_article.copy())
    print(f"   ✅ '{test_article['title']}' → {classified['priority']}")

    print("\n✅ Testy zakończone!")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="F1 Monitor - System monitorowania newsów F1")
    parser.add_argument(
        "--mode",
        choices=["run", "once", "stats", "test"],
        default="run",
        help=(
            "run: uruchom ciągłe monitorowanie (domyślnie) | "
            "once: jeden cykl | "
            "stats: pokaż statystyki | "
            "test: testuj wszystkie komponenty"
        ),
    )

    args = parser.parse_args()

    if args.mode == "run":
        main()
    elif args.mode == "once":
        run_once()
    elif args.mode == "stats":
        show_stats()
    elif args.mode == "test":
        test_all()
