"""
F1 Monitor - Warstwa bazy danych (SQLite)
Obsługuje wszystkie operacje CRUD dla newsów i wygenerowanych treści.
"""

import sqlite3
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from loguru import logger

import config


# ============================================================
# SCHEMAT BAZY DANYCH
# ============================================================
CREATE_TABLES_SQL = """
-- Tabela newsów
CREATE TABLE IF NOT EXISTS news (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url_hash        TEXT    UNIQUE NOT NULL,     -- MD5 z URL (szybkie lookup)
    url             TEXT    NOT NULL,
    title           TEXT    NOT NULL,
    description     TEXT    DEFAULT '',
    source_name     TEXT    NOT NULL,
    source_category TEXT    DEFAULT 'media',
    published_at    TEXT,                         -- ISO 8601
    fetched_at      TEXT    NOT NULL,             -- kiedy my pobraliśmy
    priority        TEXT    DEFAULT 'LOW',        -- BREAKING/HIGH/MEDIUM/LOW
    priority_score  INTEGER DEFAULT 0,
    is_duplicate    INTEGER DEFAULT 0,            -- 0=nie, 1=tak
    duplicate_of_id INTEGER,                      -- ID oryginału
    notified        INTEGER DEFAULT 0,            -- 0=nie, 1=tak
    content_generated INTEGER DEFAULT 0,          -- 0=nie, 1=tak
    FOREIGN KEY (duplicate_of_id) REFERENCES news(id)
);

-- Tabela wygenerowanych treści
CREATE TABLE IF NOT EXISTS generated_content (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    news_id         INTEGER NOT NULL UNIQUE,
    tiktok_script   TEXT    DEFAULT '',
    instagram_post  TEXT    DEFAULT '',
    facebook_post   TEXT    DEFAULT '',
    twitter_post    TEXT    DEFAULT '',
    seo_title       TEXT    DEFAULT '',
    hashtags        TEXT    DEFAULT '',
    graphic_idea    TEXT    DEFAULT '',
    model_used      TEXT    DEFAULT '',
    generated_at    TEXT    NOT NULL,
    FOREIGN KEY (news_id) REFERENCES news(id)
);

-- Tabela statystyk/metadanych (klucz-wartość)
CREATE TABLE IF NOT EXISTS metadata (
    key     TEXT PRIMARY KEY,
    value   TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Indeksy dla szybkich zapytań
CREATE INDEX IF NOT EXISTS idx_news_fetched_at    ON news(fetched_at);
CREATE INDEX IF NOT EXISTS idx_news_priority      ON news(priority);
CREATE INDEX IF NOT EXISTS idx_news_notified      ON news(notified);
CREATE INDEX IF NOT EXISTS idx_news_is_duplicate  ON news(is_duplicate);
CREATE INDEX IF NOT EXISTS idx_news_published_at  ON news(published_at);
"""


# ============================================================
# ZARZĄDZANIE POŁĄCZENIEM
# ============================================================
@contextmanager
def get_connection():
    """Context manager dla połączeń SQLite."""
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row  # dostęp przez nazwy kolumn
    conn.execute("PRAGMA journal_mode=WAL")   # lepsza wydajność
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        raise  # cicho przekazujemy do insert_news który to obsługuje
    except Exception as e:
        conn.rollback()
        logger.error(f"Błąd bazy danych: {e}")
        raise
    finally:
        conn.close()


def init_db() -> None:
    """Inicjalizuje bazę danych i tworzy tabele."""
    import os
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)

    with get_connection() as conn:
        conn.executescript(CREATE_TABLES_SQL)

    logger.info(f"Baza danych zainicjalizowana: {config.DB_PATH}")


# ============================================================
# OPERACJE NA NEWSACH
# ============================================================
def url_to_hash(url: str) -> str:
    """Zamienia URL na MD5 hash (szybkie sprawdzenie duplikatów)."""
    return hashlib.md5(url.strip().encode()).hexdigest()


def news_exists(url: str) -> bool:
    """Sprawdza czy news z tym URL już istnieje w bazie."""
    url_hash = url_to_hash(url)
    with get_connection() as conn:
        row = conn.execute(
            "SELECT id FROM news WHERE url_hash = ?", (url_hash,)
        ).fetchone()
        return row is not None


def insert_news(article: Dict[str, Any]) -> Optional[int]:
    """
    Wstawia nowy artykuł do bazy.
    Zwraca ID nowego rekordu lub None jeśli już istnieje.
    """
    url_hash = url_to_hash(article["url"])

    try:
        with get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO news
                    (url_hash, url, title, description, source_name,
                     source_category, published_at, fetched_at,
                     priority, priority_score, is_duplicate)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    url_hash,
                    article["url"],
                    article["title"],
                    article.get("description", ""),
                    article["source_name"],
                    article.get("source_category", "media"),
                    article.get("published_at", ""),
                    datetime.utcnow().isoformat(),
                    article.get("priority", "LOW"),
                    article.get("priority_score", 0),
                    int(article.get("is_duplicate", False)),
                ),
            )
            news_id = cursor.lastrowid
            logger.debug(f"Wstawiono news ID={news_id}: {article['title'][:60]}...")
            return news_id
    except sqlite3.IntegrityError:
        logger.debug(f"News już istnieje: {article['url'][:80]}")
        return None


def mark_as_duplicate(news_id: int, original_id: int) -> None:
    """Oznacza artykuł jako duplikat."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE news SET is_duplicate = 1, duplicate_of_id = ? WHERE id = ?",
            (original_id, news_id),
        )


def mark_as_notified(news_id: int) -> None:
    """Oznacza news jako wysłany w powiadomieniu."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE news SET notified = 1 WHERE id = ?",
            (news_id,),
        )


def mark_content_generated(news_id: int) -> None:
    """Oznacza news jako przetworzony przez generator treści."""
    with get_connection() as conn:
        conn.execute(
            "UPDATE news SET content_generated = 1 WHERE id = ?",
            (news_id,),
        )


def get_recent_titles(hours: int = 24) -> List[Dict]:
    """
    Pobiera tytuły i opisy newsów z ostatnich N godzin.
    Używane do deduplikacji semantycznej.
    """
    cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, title, description
            FROM news
            WHERE fetched_at > ? AND is_duplicate = 0
            ORDER BY fetched_at DESC
            LIMIT 200
            """,
            (cutoff,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_unnotified_news() -> List[Dict]:
    """Pobiera newsy które nie zostały jeszcze zgłoszone."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM news
            WHERE notified = 0 AND is_duplicate = 0
            ORDER BY priority_score DESC, fetched_at ASC
            LIMIT 50
            """,
        ).fetchall()
        return [dict(row) for row in rows]


def get_news_without_content() -> List[Dict]:
    """Pobiera newsy dla których nie wygenerowano jeszcze treści social media."""
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM news
            WHERE content_generated = 0
              AND is_duplicate = 0
              AND notified = 1
            ORDER BY priority_score DESC, fetched_at ASC
            LIMIT 10
            """,
        ).fetchall()
        return [dict(row) for row in rows]


def get_news_by_id(news_id: int) -> Optional[Dict]:
    """Pobiera artykuł po ID."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM news WHERE id = ?", (news_id,)
        ).fetchone()
        return dict(row) if row else None


# ============================================================
# OPERACJE NA WYGENEROWANYCH TREŚCIACH
# ============================================================
def save_generated_content(news_id: int, content: Dict[str, str], model: str = "") -> None:
    """Zapisuje wygenerowane treści social media."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO generated_content
                (news_id, tiktok_script, instagram_post, facebook_post,
                 twitter_post, seo_title, hashtags, graphic_idea,
                 model_used, generated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                news_id,
                content.get("tiktok_script", ""),
                content.get("instagram_post", ""),
                content.get("facebook_post", ""),
                content.get("twitter_post", ""),
                content.get("seo_title", ""),
                content.get("hashtags", ""),
                content.get("graphic_idea", ""),
                model,
                datetime.utcnow().isoformat(),
            ),
        )
    logger.debug(f"Zapisano treści dla news_id={news_id}")


def get_generated_content(news_id: int) -> Optional[Dict]:
    """Pobiera wygenerowane treści dla danego newsa."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM generated_content WHERE news_id = ?",
            (news_id,),
        ).fetchone()
        return dict(row) if row else None


# ============================================================
# STATYSTYKI I METADANE
# ============================================================
def get_stats() -> Dict[str, Any]:
    """Pobiera statystyki systemu."""
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM news").fetchone()[0]
        duplicates = conn.execute(
            "SELECT COUNT(*) FROM news WHERE is_duplicate = 1"
        ).fetchone()[0]
        by_priority = conn.execute(
            """
            SELECT priority, COUNT(*) as cnt
            FROM news WHERE is_duplicate = 0
            GROUP BY priority
            """
        ).fetchall()
        today_cutoff = datetime.utcnow().replace(
            hour=0, minute=0, second=0
        ).isoformat()
        today = conn.execute(
            "SELECT COUNT(*) FROM news WHERE fetched_at > ?",
            (today_cutoff,),
        ).fetchone()[0]

    stats = {
        "total": total,
        "duplicates": duplicates,
        "today": today,
        "by_priority": {row["priority"]: row["cnt"] for row in by_priority},
    }
    return stats


def set_metadata(key: str, value: str) -> None:
    """Zapisuje metadaną (klucz-wartość)."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO metadata (key, value, updated_at)
            VALUES (?, ?, ?)
            """,
            (key, value, datetime.utcnow().isoformat()),
        )


def get_metadata(key: str, default: str = "") -> str:
    """Pobiera metadaną."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM metadata WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default


def count_recent_notifications(hours: int = 1) -> int:
    """Liczy powiadomienia z ostatnich N godzin (anti-spam)."""
    cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    with get_connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM news WHERE notified = 1 AND fetched_at > ?",
            (cutoff,),
        ).fetchone()[0]
        return count


def count_recent_generations(hours: int = 1) -> int:
    """Liczy generowania treści z ostatnich N godzin."""
    cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    with get_connection() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM generated_content WHERE generated_at > ?",
            (cutoff,),
        ).fetchone()[0]
        return count


if __name__ == "__main__":
    init_db()
    stats = get_stats()
    print("📊 Statystyki bazy danych:")
    print(f"  Łącznie newsów: {stats['total']}")
    print(f"  Dziś: {stats['today']}")
    print(f"  Duplikatów: {stats['duplicates']}")
    print(f"  Według priorytetu: {stats['by_priority']}")
