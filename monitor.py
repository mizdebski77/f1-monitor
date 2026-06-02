"""
F1 Monitor - Moduł pobierania newsów
Obsługuje RSS feedy + web scraping ze wszystkich źródeł F1.
"""

import time
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any
import feedparser
import requests
from bs4 import BeautifulSoup
from dateutil import parser as dateutil_parser
from loguru import logger

import config


# ============================================================
# POBIERANIE RSS
# ============================================================
def fetch_rss_feed(source: Dict) -> List[Dict[str, Any]]:
    """
    Pobiera artykuły z jednego RSS feeda.
    Zwraca listę znormalizowanych artykułów.
    """
    articles = []
    url = source["url"]
    source_name = source["name"]

    try:
        logger.debug(f"Pobieranie RSS: {source_name}")

        # feedparser obsługuje parsowanie + pobieranie
        feed = feedparser.parse(
            url,
            request_headers=config.HTTP_HEADERS,
            agent=config.HTTP_HEADERS["User-Agent"],
        )

        if feed.bozo and feed.bozo_exception:
            # bozo = feedparser napotkał problemy z parserem
            # Często to tylko ostrzeżenie, nie błąd krytyczny
            logger.warning(
                f"RSS bozo error dla {source_name}: {feed.bozo_exception}"
            )

        entries = feed.entries[: config.MAX_ARTICLES_PER_SOURCE]
        logger.debug(f"  Znaleziono {len(entries)} artykułów z {source_name}")

        for entry in entries:
            article = _normalize_rss_entry(entry, source)
            if article:
                articles.append(article)

    except Exception as e:
        logger.error(f"Błąd pobierania RSS {source_name}: {e}")

    return articles


def _normalize_rss_entry(entry: Any, source: Dict) -> Optional[Dict[str, Any]]:
    """
    Normalizuje wpis RSS do wspólnego formatu.
    Obsługuje różne struktury feedów.
    """
    try:
        # URL - sprawdzamy kilka możliwych pól
        url = (
            getattr(entry, "link", None)
            or getattr(entry, "id", None)
            or ""
        )
        if not url or not url.startswith("http"):
            return None

        # Tytuł
        title = getattr(entry, "title", "").strip()
        if not title or len(title) < 5:
            return None

        # Opis/summary - czyścimy HTML tagi
        raw_description = (
            getattr(entry, "summary", "")
            or getattr(entry, "description", "")
            or ""
        )
        description = _clean_html(raw_description)[:500]  # max 500 znaków

        # Data publikacji
        published_at = _parse_date(entry)

        return {
            "url": url.strip(),
            "title": title,
            "description": description,
            "source_name": source["name"],
            "source_category": source.get("category", "media"),
            "published_at": published_at,
            "priority_boost": source.get("priority_boost", 0),
        }

    except Exception as e:
        logger.warning(f"Błąd normalizacji wpisu RSS: {e}")
        return None


def _parse_date(entry: Any) -> str:
    """Parsuje datę z RSS wpisu do ISO 8601."""
    # feedparser często parsuje datę do struct_time
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            dt = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            return dt.isoformat()
        except Exception:
            pass

    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        try:
            dt = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)
            return dt.isoformat()
        except Exception:
            pass

    # Fallback: parsuj string daty
    for attr in ["published", "updated", "created"]:
        date_str = getattr(entry, attr, "")
        if date_str:
            try:
                dt = dateutil_parser.parse(date_str)
                return dt.isoformat()
            except Exception:
                pass

    # Jeśli nic nie zadziała - obecny czas
    return datetime.utcnow().isoformat()


def _clean_html(html_text: str) -> str:
    """Usuwa tagi HTML z tekstu."""
    if not html_text:
        return ""
    try:
        soup = BeautifulSoup(html_text, "html.parser")
        text = soup.get_text(separator=" ", strip=True)
        # Usuń nadmiarowe spacje
        import re
        text = re.sub(r"\s+", " ", text).strip()
        return text
    except Exception:
        return html_text


# ============================================================
# WEB SCRAPING (backup dla źródeł bez RSS)
# ============================================================
def scrape_formula1_com() -> List[Dict[str, Any]]:
    """
    Scraper dla Formula1.com - oficjalna strona.
    Używamy jako backup gdy RSS nie działa.
    """
    articles = []
    url = "https://www.formula1.com/en/latest/all"

    try:
        logger.debug("Scrapowanie Formula1.com...")
        response = requests.get(
            url,
            headers=config.HTTP_HEADERS,
            timeout=config.REQUEST_TIMEOUT,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Szukamy kart artykułów (selektory mogą się zmienić)
        article_cards = (
            soup.select("article.f1-article")
            or soup.select("[data-testid='article-card']")
            or soup.select(".article-card")
            or soup.select("a[href*='/en/latest/article']")
        )

        logger.debug(f"  Formula1.com: znaleziono {len(article_cards)} kart")

        for card in article_cards[: config.MAX_ARTICLES_PER_SOURCE]:
            try:
                # Link do artykułu
                link = card.get("href", "") or ""
                if not link:
                    a_tag = card.find("a")
                    link = a_tag.get("href", "") if a_tag else ""

                if link and not link.startswith("http"):
                    link = "https://www.formula1.com" + link

                # Tytuł
                title_el = (
                    card.find("h2")
                    or card.find("h3")
                    or card.find("[class*='title']")
                )
                title = title_el.get_text(strip=True) if title_el else ""

                if link and title and len(title) > 5:
                    articles.append({
                        "url": link,
                        "title": title,
                        "description": "",
                        "source_name": "Formula1.com",
                        "source_category": "official",
                        "published_at": datetime.utcnow().isoformat(),
                        "priority_boost": 2,  # oficjalne źródło = wyższy priorytet
                    })

            except Exception as e:
                logger.warning(f"Błąd parsowania karty F1.com: {e}")
                continue

    except requests.RequestException as e:
        logger.error(f"Błąd scrapowania Formula1.com: {e}")

    return articles


def scrape_fia_news() -> List[Dict[str, Any]]:
    """
    Scraper dla FIA.com - oficjalne komunikaty.
    Najważniejsze źródło dla kar, dyrektyw technicznych itd.
    """
    articles = []
    url = "https://www.fia.com/news"

    try:
        logger.debug("Scrapowanie FIA.com...")
        response = requests.get(
            url,
            headers=config.HTTP_HEADERS,
            timeout=config.REQUEST_TIMEOUT,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # FIA używa różnych selektorów - próbujemy kilka
        news_items = (
            soup.select(".view-content .views-row")
            or soup.select("article.news-article")
            or soup.select(".news-list-item")
        )

        logger.debug(f"  FIA.com: znaleziono {len(news_items)} newsów")

        for item in news_items[: config.MAX_ARTICLES_PER_SOURCE]:
            try:
                a_tag = item.find("a")
                if not a_tag:
                    continue

                href = a_tag.get("href", "")
                if not href.startswith("http"):
                    href = "https://www.fia.com" + href

                title = a_tag.get_text(strip=True) or item.get_text(strip=True)
                title = title[:200].strip()

                if href and len(title) > 5:
                    articles.append({
                        "url": href,
                        "title": title,
                        "description": "",
                        "source_name": "FIA Official",
                        "source_category": "official",
                        "published_at": datetime.utcnow().isoformat(),
                        "priority_boost": 3,  # FIA = najwyższy priorytet
                    })

            except Exception as e:
                logger.warning(f"Błąd parsowania FIA item: {e}")
                continue

    except requests.RequestException as e:
        logger.error(f"Błąd scrapowania FIA.com: {e}")

    return articles


# ============================================================
# GŁÓWNA FUNKCJA POBIERANIA
# ============================================================
def fetch_all_news() -> List[Dict[str, Any]]:
    """
    Pobiera wszystkie newsy ze wszystkich źródeł.
    Zwraca połączoną listę artykułów.
    """
    all_articles = []

    # 1. RSS feedy
    enabled_sources = [s for s in config.RSS_SOURCES if s.get("enabled", True)]
    logger.info(f"Sprawdzam {len(enabled_sources)} źródeł RSS...")

    for source in enabled_sources:
        articles = fetch_rss_feed(source)
        all_articles.extend(articles)
        logger.debug(f"  {source['name']}: {len(articles)} artykułów")

        # Opóźnienie między requestami (grzeczne scrapowanie)
        time.sleep(config.REQUEST_DELAY)

    # 2. Scrapery dla źródeł bez RSS
    logger.info("Sprawdzam źródła przez scraping...")

    f1_scraped = scrape_formula1_com()
    all_articles.extend(f1_scraped)
    logger.debug(f"  Formula1.com scraper: {len(f1_scraped)} artykułów")
    time.sleep(config.REQUEST_DELAY)

    fia_scraped = scrape_fia_news()
    all_articles.extend(fia_scraped)
    logger.debug(f"  FIA.com scraper: {len(fia_scraped)} artykułów")

    # Usuń artykuły bez URL lub tytułu
    valid_articles = [
        a for a in all_articles
        if a.get("url") and a.get("title") and len(a["title"]) > 5
    ]

    logger.info(
        f"Łącznie pobrano: {len(valid_articles)} artykułów "
        f"({len(all_articles) - len(valid_articles)} odrzuconych)"
    )

    return valid_articles


def test_sources() -> None:
    """
    Testuje wszystkie źródła i wyświetla ich status.
    Uruchom: python monitor.py
    """
    print("\n🔍 Testowanie źródeł RSS...\n")
    print(f"{'Źródło':<30} {'Status':<10} {'Artykuły':<10}")
    print("-" * 55)

    for source in config.RSS_SOURCES:
        if not source.get("enabled", True):
            print(f"{source['name']:<30} {'WYŁĄCZONE':<10}")
            continue

        try:
            feed = feedparser.parse(
                source["url"],
                request_headers=config.HTTP_HEADERS,
            )
            count = len(feed.entries)
            status = "✅ OK" if count > 0 else "⚠️ PUSTY"
            print(f"{source['name']:<30} {status:<10} {count:<10}")
        except Exception as e:
            print(f"{source['name']:<30} {'❌ BŁĄD':<10} {str(e)[:20]}")

        time.sleep(0.5)

    print("\n🌐 Testowanie scraperów...")
    print("Formula1.com...", end=" ")
    f1 = scrape_formula1_com()
    print(f"{'✅ ' + str(len(f1)) + ' artykułów' if f1 else '⚠️ brak artykułów'}")

    print("FIA.com...", end=" ")
    fia = scrape_fia_news()
    print(f"{'✅ ' + str(len(fia)) + ' artykułów' if fia else '⚠️ brak artykułów'}")


if __name__ == "__main__":
    from loguru import logger
    logger.remove()
    logger.add(lambda msg: print(msg), level="DEBUG")
    test_sources()
