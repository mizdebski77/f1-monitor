"""
F1 Monitor - Moduł postowania na X (Twitter)
Publikuje posty przez X API v2 (OAuth 1.0a User Context).
Używa requests + requests-oauthlib (bez Tweepy).
"""

import time
from typing import Optional
import requests
from requests_oauthlib import OAuth1
from loguru import logger

import config


X_API_BASE = "https://api.twitter.com/2"


def _get_oauth() -> Optional[OAuth1]:
    """Zwraca obiekt OAuth1 do podpisywania requestów, albo None jeśli brak konfiguracji."""
    if not all([
        config.X_API_KEY,
        config.X_API_SECRET,
        config.X_ACCESS_TOKEN,
        config.X_ACCESS_TOKEN_SECRET,
    ]):
        return None

    return OAuth1(
        config.X_API_KEY,
        config.X_API_SECRET,
        config.X_ACCESS_TOKEN,
        config.X_ACCESS_TOKEN_SECRET,
    )


def is_configured() -> bool:
    """Sprawdza czy postowanie na X jest skonfigurowane (dane API) i włączone (.env)."""
    return _get_oauth() is not None and config.X_POSTING_ENABLED


def post_tweet(text: str, retries: int = 2) -> bool:
    """
    Publikuje tweet o podanej treści (max 280 znaków) przez X API v2.
    Zwraca True jeśli sukces, False w przypadku błędu.
    """
    if not config.X_POSTING_ENABLED:
        logger.debug("Postowanie na X wyłączone (X_POSTING_ENABLED=false) - pomijam")
        return False

    auth = _get_oauth()
    if not auth:
        logger.warning("Brak pełnej konfiguracji X (Twitter) API - nie można opublikować tweeta")
        return False

    if not text or not text.strip():
        logger.warning("Pusta treść tweeta - pomijam")
        return False

    # X API limit: 280 znaków (na wszelki wypadek przycinamy jeszcze raz)
    if len(text) > 280:
        logger.warning(f"Tweet zbyt długi ({len(text)} znaków) - przycinam do 280")
        text = text[:277] + "..."

    for attempt in range(retries):
        try:
            response = requests.post(
                f"{X_API_BASE}/tweets",
                auth=auth,
                json={"text": text},
                timeout=15,
            )

            if response.status_code == 201:
                data = response.json()
                tweet_id = data.get("data", {}).get("id")
                logger.info(f"✅ Tweet opublikowany na X (ID: {tweet_id})")
                return True

            elif response.status_code == 429:
                retry_after = int(response.headers.get("retry-after", 30))
                logger.warning(f"X API rate limit - czekam {retry_after}s")
                if attempt < retries - 1:
                    time.sleep(retry_after)
                    continue
                return False

            elif response.status_code in (401, 403):
                logger.error(
                    f"X API odmowa dostępu ({response.status_code}): {response.text[:300]} "
                    f"- sprawdź uprawnienia tokenu (Read and Write) i billing konta"
                )
                return False

            else:
                logger.error(
                    f"Błąd publikacji tweeta ({response.status_code}): {response.text[:300]}"
                )
                if attempt < retries - 1:
                    time.sleep(2)
                    continue
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"Błąd połączenia z X API: {e}")
            if attempt < retries - 1:
                time.sleep(2)
                continue
            return False
        except Exception as e:
            logger.error(f"Nieoczekiwany błąd podczas postowania na X: {e}")
            return False

    return False


def test_connection() -> bool:
    """Testuje połączenie z X API (GET /2/users/me) bez wysyłania tweeta."""
    auth = _get_oauth()
    if not auth:
        logger.warning("Brak pełnej konfiguracji X (Twitter) API w .env")
        return False

    try:
        response = requests.get(
            f"{X_API_BASE}/users/me",
            auth=auth,
            timeout=15,
        )
        if response.status_code == 200:
            data = response.json().get("data", {})
            username = data.get("username", "?")
            logger.info(f"✅ Połączono z X jako @{username}")
            return True
        elif response.status_code == 403:
            # UWAGA: darmowy / pay-per-use plan X API często NIE ma dostępu
            # do endpointów GET (np. /users/me), nawet jeśli POST /tweets działa.
            # Błąd 403 tutaj NIE musi oznaczać, że samo postowanie nie zadziała.
            logger.warning(
                "GET /2/users/me zwrócił 403 - to może być tylko ograniczenie "
                "odczytu na Twoim planie X API. Samo postowanie (POST /2/tweets) "
                "może mimo to działać - przetestuj realnym tweetem, żeby sprawdzić."
            )
            return False
        else:
            logger.error(
                f"Błąd połączenia z X API ({response.status_code}): {response.text[:300]}"
            )
            return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Błąd połączenia z X API: {e}")
        return False


if __name__ == "__main__":
    # Szybki test lokalny: py twitter_poster.py
    print("\n🔧 TEST POŁĄCZENIA Z X (TWITTER)\n")

    if not is_configured():
        print("⚠️  X_POSTING_ENABLED=false albo brak danych w .env - postowanie wyłączone")

    if test_connection():
        print("\n✅ Połączenie z X API działa (odczyt i najpewniej też zapis).")
    else:
        print(
            "\n⚠️  Test odczytu (GET /2/users/me) nie przeszedł. To może być normalne "
            "na darmowym/pay-per-use planie X - sam odczyt bywa zablokowany, mimo że "
            "postowanie (POST /2/tweets) działa. Sprawdź to realnym tweetem:"
        )
    print('\n   py -c "import twitter_poster; print(twitter_poster.post_tweet(\'Test F1 Monitor \\U0001F3CE\'))"')
