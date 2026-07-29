"""
F1 Monitor - Moduł deduplikacji
Wykrywa duplikaty na dwóch poziomach:
  1. Dokładny match URL (instant, hash w DB)
  2. Podobieństwo semantyczne tytułów (TF-IDF cosine similarity)
"""

import re
from typing import List, Dict, Optional, Tuple, Set
from loguru import logger

import config
import database

# Lazy imports - ładujemy sklearn tylko gdy potrzebne
_vectorizer = None
_tfidf_matrix = None
_cached_titles: List[str] = []
_cached_ids: List[int] = []


# ============================================================
# ROZPOZNAWANIE TEGO SAMEGO TEMATU (kierowcy/zespoły + tekst)
# ============================================================
# Same wydarzenie opisane przez różne portale prawie nigdy nie ma podobnych
# tytułów słowo w słowo (każda redakcja pisze inaczej), więc samo podobieństwo
# TF-IDF tytułów prawie nigdy nie przekracza wysokiego progu. Dlatego oprócz
# podobieństwa tekstu (tytuł+opis) sprawdzamy też, czy oba artykuły wspominają
# tych samych kierowców/zespoły - to dużo mocniejszy sygnał, że chodzi o ten
# sam temat, i pozwala obniżyć wymagany próg podobieństwa tekstu.
DRIVER_NAMES = [
    "hamilton", "verstappen", "leclerc", "norris", "sainz", "alonso",
    "russell", "piastri", "perez", "bottas", "ocon", "gasly", "stroll",
    "albon", "tsunoda", "hulkenberg", "magnussen", "zhou", "sargeant",
    "ricciardo", "antonelli", "bearman", "colapinto", "lawson", "doohan",
    "hadjar",
]
TEAM_NAMES = [
    "ferrari", "mercedes", "red bull", "redbull", "mclaren", "alpine",
    "aston martin", "williams", "haas", "sauber", "rb", "audi",
]

# Minimalne podobieństwo tekstu (tytuł+opis) wymagane, gdy wspólny kierowca/
# zespół już potwierdza, że to ten sam temat - dużo niższe niż standardowy
# DUPLICATE_THRESHOLD, bo entity match sam w sobie jest mocnym sygnałem.
DRIVER_MATCH_MIN_SIMILARITY = 0.05
TEAM_MATCH_MIN_SIMILARITY = 0.25


def _combined_text(article: Dict) -> str:
    """Tytuł (liczony podwójnie - najważniejszy) + fragment opisu."""
    title = article.get("title", "") or ""
    description = article.get("description", "") or ""
    desc_short = " ".join(description.split()[:40])
    return f"{title} {title} {desc_short}"


def _extract_entities(text: str) -> Tuple[Set[str], Set[str]]:
    """Zwraca (zbiór kierowców, zbiór zespołów) wspomnianych w tekście."""
    t = text.lower()
    drivers = {d for d in DRIVER_NAMES if d in t}
    teams = {tm for tm in TEAM_NAMES if tm in t}
    return drivers, teams


def _is_same_topic(similarity: float, entities_a: Tuple[Set, Set], entities_b: Tuple[Set, Set]) -> bool:
    """
    Decyduje czy dwa artykuły opisują ten sam temat, łącząc podobieństwo
    tekstu z tym, czy wspominają tych samych kierowców/zespoły.
    """
    drivers_a, teams_a = entities_a
    drivers_b, teams_b = entities_b

    if drivers_a & drivers_b and similarity >= DRIVER_MATCH_MIN_SIMILARITY:
        return True
    if teams_a & teams_b and similarity >= TEAM_MATCH_MIN_SIMILARITY:
        return True
    return similarity >= config.DUPLICATE_THRESHOLD


# ============================================================
# NORMALIZACJA TEKSTU
# ============================================================
def _normalize_text(text: str) -> str:
    """
    Normalizuje tekst do porównywania:
    - lowercase
    - usuwa znaki specjalne
    - usuwa nadmiarowe spacje
    """
    text = text.lower().strip()
    # Usuń znaki specjalne (zostaw litery, cyfry, spacje)
    text = re.sub(r"[^\w\s]", " ", text)
    # Usuń nadmiarowe spacje
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_key_words(title: str) -> str:
    """
    Wyciąga kluczowe słowa z tytułu.
    Usuwa stopwords po angielsku i polsku.
    """
    stopwords_en = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to",
        "for", "of", "with", "by", "from", "is", "was", "are", "were",
        "be", "been", "being", "have", "has", "had", "do", "does", "did",
        "will", "would", "could", "should", "may", "might", "shall",
        "can", "this", "that", "these", "those", "i", "you", "he", "she",
        "it", "we", "they", "as", "into", "after", "before", "about",
        "up", "out", "not", "no", "so", "if", "its",
    }
    stopwords_pl = {
        "w", "z", "i", "na", "do", "po", "od", "o", "przez", "za",
        "się", "nie", "że", "jak", "ale", "czy", "już", "tak", "to",
        "co", "gdy", "jest", "są", "być", "ma", "go", "mu",
    }

    all_stopwords = stopwords_en | stopwords_pl
    words = _normalize_text(title).split()
    key_words = [w for w in words if w not in all_stopwords and len(w) > 2]
    return " ".join(key_words)


# ============================================================
# SZYBKIE SPRAWDZANIE (URL Hash)
# ============================================================
def is_url_duplicate(url: str) -> bool:
    """
    Najszybszy check - czy URL już istnieje w bazie.
    O(1) - sprawdzenie MD5 hasha.
    """
    return database.news_exists(url)


# ============================================================
# SPRAWDZANIE SEMANTYCZNE (TF-IDF)
# ============================================================
def _get_tfidf_similarity(new_title: str, existing_titles: List[str]) -> List[float]:
    """
    Oblicza podobieństwo cosinusowe nowego tytułu do istniejących.
    Używa TF-IDF wektoryzacji.
    Zwraca listę score'ów (0.0 - 1.0).
    """
    if not existing_titles:
        return []

    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np

        # Normalizujemy wszystkie teksty
        all_texts = [_extract_key_words(t) for t in [new_title] + existing_titles]

        # Wektoryzacja TF-IDF
        vectorizer = TfidfVectorizer(
            analyzer="word",
            ngram_range=(1, 2),  # unigramy i bigramy
            min_df=1,
            sublinear_tf=True,
        )

        # Sprawdź czy mamy wystarczająco treści
        non_empty = [t for t in all_texts if t.strip()]
        if len(non_empty) < 2:
            return [0.0] * len(existing_titles)

        tfidf_matrix = vectorizer.fit_transform(all_texts)

        # Podobieństwo nowego tytułu do każdego istniejącego
        new_vector = tfidf_matrix[0]
        existing_matrix = tfidf_matrix[1:]

        similarities = cosine_similarity(new_vector, existing_matrix)[0]
        return similarities.tolist()

    except ImportError:
        logger.warning("sklearn nie zainstalowany - używam prostego porównania")
        return _simple_similarity(new_title, existing_titles)
    except Exception as e:
        logger.warning(f"Błąd TF-IDF: {e} - używam prostego porównania")
        return _simple_similarity(new_title, existing_titles)


def _simple_similarity(new_title: str, existing_titles: List[str]) -> List[float]:
    """
    Prosta deduplikacja bez sklearn.
    Używa Jaccard similarity na zbiorach słów.
    """
    new_words = set(_extract_key_words(new_title).split())
    if not new_words:
        return [0.0] * len(existing_titles)

    scores = []
    for title in existing_titles:
        existing_words = set(_extract_key_words(title).split())
        if not existing_words:
            scores.append(0.0)
            continue

        intersection = len(new_words & existing_words)
        union = len(new_words | existing_words)
        jaccard = intersection / union if union > 0 else 0.0
        scores.append(jaccard)

    return scores


# ============================================================
# GŁÓWNA FUNKCJA DEDUPLIKACJI
# ============================================================
def find_duplicate(
    article: Dict,
    recent_news: List[Dict],
) -> Tuple[bool, Optional[int]]:
    """
    Sprawdza czy artykuł jest duplikatem.

    Args:
        article: Nowy artykuł (dict z url, title, description)
        recent_news: Lista ostatnich newsów z bazy (z ostatnich 24h)

    Returns:
        (is_duplicate, original_id)
        - is_duplicate: True jeśli duplikat
        - original_id: ID oryginału lub None
    """
    # Krok 1: Sprawdź URL (najszybsze)
    if is_url_duplicate(article["url"]):
        logger.debug(f"URL duplikat: {article['url'][:60]}...")
        return True, None

    # Krok 2: Sprawdź podobieństwo tematu (tytuł+opis, wspomniani kierowcy/zespoły)
    if not recent_news:
        return False, None

    new_title = article.get("title", "")
    if not new_title or len(new_title) < 10:
        return False, None

    new_text = _combined_text(article)
    existing_texts = [_combined_text(n) for n in recent_news]
    existing_ids = [n["id"] for n in recent_news]

    # Oblicz podobieństwo
    similarities = _get_tfidf_similarity(new_text, existing_texts)

    if not similarities:
        return False, None

    new_entities = _extract_entities(new_text)

    # Wybierz najlepszego kandydata spośród tych, które spełniają próg
    # (podobieństwo tekstu + ewentualnie wspólny kierowca/zespół - patrz
    # _is_same_topic)
    best_id: Optional[int] = None
    best_score = 0.0
    for idx, similarity in enumerate(similarities):
        candidate_entities = _extract_entities(existing_texts[idx])
        if _is_same_topic(similarity, new_entities, candidate_entities) and similarity > best_score:
            best_score = similarity
            best_id = existing_ids[idx]

    max_similarity = max(similarities)
    max_idx = similarities.index(max_similarity)
    logger.debug(
        f"Max similarity {max_similarity:.2f} dla: "
        f"'{new_title[:50]}' vs '{recent_news[max_idx]['title'][:50]}'"
    )

    if best_id is not None:
        logger.info(
            f"Ten sam temat ({best_score:.0%}): "
            f"'{new_title[:60]}' = ID {best_id}"
        )
        return True, best_id

    return False, None


def process_deduplication(
    articles: List[Dict],
    recent_news: List[Dict],
) -> List[Dict]:
    """
    Przetwarza listę artykułów - usuwa duplikaty i oznacza oryginały.
    Obsługuje również duplikaty wewnątrz tej samej partii.

    Gdy artykuł okazuje się być duplikatem (z bazy albo z tej samej partii),
    artykuł dostaje pole "merge_into_article" - referencję do obiektu-dict
    oryginału z TEJ partii (jeśli dotyczy), żeby main.py mogło później
    dopisać jego opis jako dodatkowe źródło do oryginału (zamiast po prostu
    go wyrzucać). Dla duplikatów z bazy (duplicate_of_id) merge odbywa się
    bezpośrednio po ID, bez potrzeby referencji do obiektu.

    Args:
        articles: Lista nowych artykułów
        recent_news: Lista ostatnich newsów z bazy

    Returns:
        Lista artykułów z dodanymi polami is_duplicate, duplicate_of_id
        i merge_into_article
    """
    processed = []
    # Artykuły z tej samej partii które uznaliśmy za oryginały
    batch_originals: List[Dict] = []

    for article in articles:
        article["merge_into_article"] = None

        # Sprawdź duplikat w bazie
        is_dup, original_id = find_duplicate(article, recent_news)

        if is_dup and original_id:
            article["is_duplicate"] = True
            article["duplicate_of_id"] = original_id
            logger.debug(f"Duplikat DB: {article['title'][:60]} -> łączę z ID {original_id}")
            processed.append(article)
            continue

        # URL już istnieje w bazie (is_dup=True ale brak original_id)
        if is_dup:
            article["is_duplicate"] = True
            article["duplicate_of_id"] = None
            processed.append(article)
            continue

        # Sprawdź duplikat w tej partii (te same news z wielu źródeł)
        batch_dup = False
        batch_match: Optional[Dict] = None
        if batch_originals:
            new_text = _combined_text(article)
            batch_texts = [_combined_text(b) for b in batch_originals]
            sims = _get_tfidf_similarity(new_text, batch_texts)
            if sims:
                new_entities = _extract_entities(new_text)
                best_idx = None
                best_score = 0.0
                for idx, sim in enumerate(sims):
                    cand_entities = _extract_entities(batch_texts[idx])
                    if _is_same_topic(sim, new_entities, cand_entities) and sim > best_score:
                        best_score = sim
                        best_idx = idx
                if best_idx is not None:
                    batch_dup = True
                    batch_match = batch_originals[best_idx]
                    logger.debug(
                        f"Duplikat w partii ({best_score:.0%}): {article['title'][:60]} "
                        f"-> łączę z '{batch_match['title'][:60]}'"
                    )

        if batch_dup:
            article["is_duplicate"] = True
            article["duplicate_of_id"] = None
            article["merge_into_article"] = batch_match
        elif not is_dup:
            article["is_duplicate"] = False
            article["duplicate_of_id"] = None
            # Dodaj do "oryginałów" tej partii tylko jeśli nie ma URL dup
            if not is_url_duplicate(article["url"]):
                batch_originals.append(article)

        processed.append(article)

    unique_count = sum(1 for a in processed if not a["is_duplicate"])
    dup_count = len(processed) - unique_count
    logger.info(
        f"Deduplikacja: {unique_count} unikalnych, {dup_count} duplikatów "
        f"z {len(articles)} artykułów"
    )

    return processed


if __name__ == "__main__":
    # Test deduplikacji
    print("🔍 Test deduplikacji\n")

    test_titles = [
        "Lewis Hamilton signs new contract with Ferrari",
        "Hamilton signs new deal with Ferrari for 2025",
        "Max Verstappen wins Japanese Grand Prix",
        "Verstappen dominates Japan GP to claim victory",
        "F1 2025 car reveals: all the new designs",
    ]

    print("Testowanie podobieństwa tytułów:")
    for i, t1 in enumerate(test_titles):
        for j, t2 in enumerate(test_titles):
            if i < j:
                sims = _get_tfidf_similarity(t1, [t2])
                sim = sims[0] if sims else 0
                dup = "🔴 DUPLIKAT" if sim >= config.DUPLICATE_THRESHOLD else "✅ UNIKALNY"
                print(f"  {dup} ({sim:.0%}): '{t1[:40]}' vs '{t2[:40]}'")
