"""
F1 Monitor - Centralna konfiguracja systemu
Wszystkie ustawienia w jednym miejscu.
"""

import os
from dataclasses import dataclass, field
from typing import List, Dict
from dotenv import load_dotenv

load_dotenv()


# ============================================================
# TELEGRAM
# ============================================================
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")


# ============================================================
# HUGGINGFACE
# ============================================================
HUGGINGFACE_API_TOKEN: str = os.getenv("HUGGINGFACE_API_TOKEN", "")
HF_MODEL: str = os.getenv("HF_MODEL", "HuggingFaceH4/zephyr-7b-beta")
HF_API_URL: str = f"https://api-inference.huggingface.co/models/{HF_MODEL}"
HF_MAX_TOKENS: int = 800
HF_TEMPERATURE: float = 0.7
HF_TIMEOUT: int = 10  # sekundy (krótszy timeout)


# ============================================================
# X (TWITTER)
# ============================================================
X_API_KEY: str = os.getenv("X_API_KEY", "")
X_API_SECRET: str = os.getenv("X_API_SECRET", "")
X_ACCESS_TOKEN: str = os.getenv("X_ACCESS_TOKEN", "")
X_ACCESS_TOKEN_SECRET: str = os.getenv("X_ACCESS_TOKEN_SECRET", "")
X_POSTING_ENABLED: bool = os.getenv("X_POSTING_ENABLED", "true").lower() == "true"


# ============================================================
# BAZA DANYCH
# ============================================================
DB_PATH: str = os.getenv("DB_PATH", "data/f1_monitor.db")


# ============================================================
# SCHEDULER
# ============================================================
CHECK_INTERVAL_MINUTES: int = int(os.getenv("CHECK_INTERVAL_MINUTES", "3"))


# ============================================================
# LOGOWANIE
# ============================================================
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE: str = os.getenv("LOG_FILE", "logs/f1_monitor.log")
LOG_ROTATION: str = "10 MB"
LOG_RETENTION: str = "7 days"


# ============================================================
# LIMITY I BEZPIECZEŃSTWO
# ============================================================
MAX_ARTICLES_PER_SOURCE: int = int(os.getenv("MAX_ARTICLES_PER_SOURCE", "10"))
DUPLICATE_THRESHOLD: float = float(os.getenv("DUPLICATE_THRESHOLD", "0.75"))
DUPLICATE_WINDOW_HOURS: int = int(os.getenv("DUPLICATE_WINDOW_HOURS", "24"))
REQUEST_DELAY: float = float(os.getenv("REQUEST_DELAY", "1.0"))
REQUEST_TIMEOUT: int = int(os.getenv("REQUEST_TIMEOUT", "15"))

# Maksymalna liczba powiadomień na godzinę (anti-spam)
MAX_NOTIFICATIONS_PER_HOUR: int = 20

# Maksymalna liczba generowań treści na godzinę (oszczędność API)
MAX_CONTENT_GENERATIONS_PER_HOUR: int = 10


# ============================================================
# ŹRÓDŁA RSS - lista feedów do monitorowania
# Łatwe dodawanie nowych: wystarczy dodać słownik do listy
# ============================================================
RSS_SOURCES: List[Dict] = [
    {
        "name": "Motorsport.com F1",
        "url": "https://www.motorsport.com/rss/f1/news/",
        "category": "official",
        "priority_boost": 1,  # dodatkowe punkty priorytetu
        "enabled": True,
    },
    {
        "name": "The Race",
        "url": "https://the-race.com/feed/",
        "category": "media",
        "priority_boost": 0,
        "enabled": True,
    },
    {
        "name": "Autosport",
        "url": "https://www.autosport.com/rss/f1/news/",
        "category": "media",
        "priority_boost": 0,
        "enabled": True,
    },
    {
        "name": "Sky Sports F1",
        "url": "https://www.skysports.com/rss/12433",
        "category": "media",
        "priority_boost": 0,
        "enabled": True,
    },
    {
        "name": "BBC Sport F1",
        "url": "https://feeds.bbci.co.uk/sport/formula1/rss.xml",
        "category": "media",
        "priority_boost": 0,
        "enabled": True,
    },
    {
        "name": "RaceFans",
        "url": "https://racefans.net/feed/",
        "category": "media",
        "priority_boost": 0,
        "enabled": True,
    },
    {
        "name": "GPFans",
        "url": "https://www.gpfans.com/en/rss/",
        "category": "media",
        "priority_boost": 0,
        "enabled": True,
    },
    {
        "name": "PlanetF1",
        "url": "https://www.planetf1.com/feed/",
        "category": "media",
        "priority_boost": 0,
        "enabled": True,
    },
    {
        "name": "F1i.com",
        "url": "https://en.f1i.com/feed",
        "category": "media",
        "priority_boost": 0,
        "enabled": True,
    },
    {
        "name": "WTF1",
        "url": "https://wtf1.com/feed/",
        "category": "media",
        "priority_boost": 0,
        "enabled": True,
    },
    {
        "name": "Crash.net F1",
        "url": "https://www.crash.net/rss/f1",
        "category": "media",
        "priority_boost": 0,
        "enabled": True,
    },
    {
        "name": "Grandprix247",
        "url": "https://www.grandprix247.com/feed/",
        "category": "media",
        "priority_boost": 0,
        "enabled": True,
    },
]


# ============================================================
# KLASYFIKACJA PRIORYTETÓW
# Słowa kluczowe do wykrywania ważności newsów
# ============================================================
PRIORITY_KEYWORDS: Dict[str, List[str]] = {
    "BREAKING": [
        # Transfery i kontrakty
        "signs", "signed", "contract", "transfer", "joins", "leaves",
        "fired", "sacked", "dismissed", "replacement", "replaced",
        "podpisał", "transfer", "odszedł", "zwolniony",
        # Wypadki i incydenty
        "crash", "accident", "injury", "injured", "hospital",
        "wypadek", "kolizja", "kontuzja", "szpital",
        # FIA i regulacje
        "penalty", "disqualified", "banned", "excluded", "DQ",
        "kara", "dyskwalifikacja", "ban",
        # Oficjalne oświadczenia
        "breaking", "official", "confirmed", "announcement",
        "łamiące", "oficjalnie", "potwierdzone", "ogłoszenie",
        # Wyniki i osiągnięcia
        "world champion", "championship", "wins race", "pole position",
        "pole", "victory", "wins",
    ],
    "HIGH": [
        # Plotki transferowe
        "rumour", "rumor", "linked", "target", "considering",
        "plotki", "spekulacje", "rozważany",
        # Nowe regulacje
        "regulation", "rule change", "technical directive",
        "regulamin", "dyrektywa techniczna",
        # Wyniki testów
        "testing", "test results", "development",
        # Kontrowersje
        "controversy", "protest", "appeal", "complaint",
        "kontrowersje", "protest", "apelacja",
        # Ważne wywiady
        "exclusive", "interview", "reveals", "admits", "confirms",
        "ekskluzywny", "wywiad", "ujawnia",
        # Strategia i car development
        "upgrade", "update", "new car", "launch",
        "ulepszenie", "nowy bolid", "prezentacja",
    ],
    "MEDIUM": [
        # Standardowe wywiady
        "says", "believes", "thinks", "comments",
        "mówi", "uważa", "komentarz",
        # Sesje treningowe
        "practice", "qualifying", "FP1", "FP2", "FP3", "Q1", "Q2", "Q3",
        "trening", "kwalifikacje",
        # Wyniki wyścigów
        "race result", "podium", "points",
        "wyniki wyścigu", "podium", "punkty",
        # Aktualności techniczne
        "technical", "aerodynamic", "engine", "power unit",
        "techniczny", "aerodynamika", "silnik",
    ],
    "LOW": [
        # Ciekawostki
        "fun fact", "did you know", "throwback", "history",
        "ciekawostka", "czy wiesz", "historia",
        # Opinie i analizy
        "opinion", "analysis", "preview", "review",
        "opinia", "analiza", "zapowiedź", "przegląd",
        # Social media i lifestyle
        "photo", "video", "behind the scenes", "lifestyle",
        "zdjęcie", "wideo", "kulisy",
    ],
}

# Progi punktowe dla priorytetów
PRIORITY_THRESHOLDS: Dict[str, int] = {
    "BREAKING": 3,   # 3+ słów kluczowych BREAKING
    "HIGH": 2,       # 2+ słów kluczowych HIGH
    "MEDIUM": 1,     # 1+ słów kluczowych MEDIUM
    "LOW": 0,        # domyślny
}

# Emoji dla priorytetów w powiadomieniach
PRIORITY_EMOJI: Dict[str, str] = {
    "BREAKING": "🚨🔴",
    "HIGH": "🔥⚡",
    "MEDIUM": "📰🏎️",
    "LOW": "ℹ️📋",
}


# ============================================================
# HTTP HEADERS - wyglądamy jak przeglądarka
# ============================================================
HTTP_HEADERS: Dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}


# ============================================================
# WALIDACJA KONFIGURACJI
# ============================================================
def validate_config() -> List[str]:
    """Sprawdza czy wszystkie wymagane zmienne są ustawione."""
    errors = []

    if not TELEGRAM_BOT_TOKEN:
        errors.append("TELEGRAM_BOT_TOKEN nie jest ustawiony w .env")
    if not TELEGRAM_CHAT_ID:
        errors.append("TELEGRAM_CHAT_ID nie jest ustawiony w .env")
    if not HUGGINGFACE_API_TOKEN:
        errors.append("HUGGINGFACE_API_TOKEN nie jest ustawiony (generowanie treści wyłączone)")

    return errors


if __name__ == "__main__":
    errors = validate_config()
    if errors:
        print("⚠️  Problemy z konfiguracją:")
        for e in errors:
            print(f"  - {e}")
    else:
        print("✅ Konfiguracja poprawna!")

    enabled_sources = [s for s in RSS_SOURCES if s["enabled"]]
    print(f"\n📡 Aktywne źródła RSS: {len(enabled_sources)}")
    for source in enabled_sources:
        print(f"  - {source['name']}")
