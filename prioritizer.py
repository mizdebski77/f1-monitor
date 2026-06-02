"""
F1 Monitor - Klasyfikator priorytetów
Ocenia ważność newsa na skali: BREAKING / HIGH / MEDIUM / LOW
Używa podejścia keyword-based (zero dependencies, deterministyczne).
"""

import re
from typing import Dict, Tuple
from loguru import logger

import config


# ============================================================
# SCORING
# ============================================================
def calculate_priority_score(title: str, description: str = "") -> Tuple[str, int]:
    """
    Oblicza priorytet i score numeryczny dla newsa.

    Args:
        title: Tytuł artykułu
        description: Opis/summary artykułu

    Returns:
        (priority_label, score)
        priority_label: "BREAKING" | "HIGH" | "MEDIUM" | "LOW"
        score: numeryczny score (wyższy = ważniejszy)
    """
    # Łączymy tytuł i opis (tytuł ma wagę 3x)
    full_text = f"{title} {title} {title} {description}".lower()

    scores: Dict[str, int] = {
        "BREAKING": 0,
        "HIGH": 0,
        "MEDIUM": 0,
        "LOW": 0,
    }

    # Liczymy wystąpienia słów kluczowych
    for priority, keywords in config.PRIORITY_KEYWORDS.items():
        for keyword in keywords:
            keyword_lower = keyword.lower()
            # Szukamy jako całe słowo (word boundary)
            pattern = r"\b" + re.escape(keyword_lower) + r"\b"
            matches = re.findall(pattern, full_text)
            scores[priority] += len(matches)

    # Determinujemy priorytet na podstawie progów
    # Hierarchia: BREAKING > HIGH > MEDIUM > LOW
    if scores["BREAKING"] >= config.PRIORITY_THRESHOLDS["BREAKING"]:
        priority = "BREAKING"
    elif scores["BREAKING"] >= 1 or scores["HIGH"] >= config.PRIORITY_THRESHOLDS["HIGH"]:
        # Nawet 1 słowo BREAKING + cokolwiek HIGH = HIGH
        priority = "HIGH"
    elif scores["HIGH"] >= 1 or scores["MEDIUM"] >= config.PRIORITY_THRESHOLDS["MEDIUM"]:
        priority = "MEDIUM"
    else:
        priority = "LOW"

    # Numeryczny score (dla sortowania)
    numeric_score = (
        scores["BREAKING"] * 100
        + scores["HIGH"] * 10
        + scores["MEDIUM"] * 2
        + scores["LOW"] * 1
    )

    logger.debug(
        f"Priorytet: {priority} (score={numeric_score}) | "
        f"BREAKING={scores['BREAKING']}, HIGH={scores['HIGH']}, "
        f"MEDIUM={scores['MEDIUM']}, LOW={scores['LOW']} | "
        f"'{title[:60]}'"
    )

    return priority, numeric_score


def classify_article(article: Dict) -> Dict:
    """
    Dodaje pola priority i priority_score do artykułu.
    Uwzględnia priority_boost z konfiguracji źródła.

    Returns:
        Artykuł z dodanymi polami priority i priority_score
    """
    title = article.get("title", "")
    description = article.get("description", "")

    priority, score = calculate_priority_score(title, description)

    # priority_boost z zaufanego źródła (np. FIA, Formula1.com)
    boost = article.get("priority_boost", 0)
    if boost > 0:
        score += boost * 50  # każdy punkt boost = +50 do score
        # Podnosimy priorytet jeśli boost jest duży
        if boost >= 3 and priority == "LOW":
            priority = "MEDIUM"
        elif boost >= 3 and priority == "MEDIUM":
            priority = "HIGH"

    article["priority"] = priority
    article["priority_score"] = score

    return article


def classify_articles(articles) -> list:
    """
    Klasyfikuje listę artykułów.
    Zwraca posortowaną listę (najważniejsze pierwsze).
    """
    classified = [classify_article(a) for a in articles]

    # Sortuj: BREAKING > HIGH > MEDIUM > LOW, potem score
    priority_order = {"BREAKING": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    classified.sort(
        key=lambda x: (
            priority_order.get(x.get("priority", "LOW"), 1),
            x.get("priority_score", 0),
        ),
        reverse=True,
    )

    # Log podsumowania
    by_priority = {}
    for a in classified:
        p = a.get("priority", "LOW")
        by_priority[p] = by_priority.get(p, 0) + 1

    logger.info(f"Klasyfikacja: {by_priority}")
    return classified


def get_priority_description(priority: str) -> str:
    """Zwraca opis kategorii priorytetowej po polsku."""
    descriptions = {
        "BREAKING": "Przełomowa informacja wymagająca natychmiastowej uwagi",
        "HIGH": "Ważna informacja z dużym wpływem na sezon",
        "MEDIUM": "Standardowa informacja z umiarkowaną istotnością",
        "LOW": "Ciekawostka lub informacja uzupełniająca",
    }
    return descriptions.get(priority, "Nieznana kategoria")


if __name__ == "__main__":
    # Test klasyfikatora
    print("🏁 Test klasyfikatora priorytetów F1\n")

    test_articles = [
        {
            "title": "BREAKING: Lewis Hamilton signs new Ferrari contract",
            "description": "Official announcement confirms Hamilton joins Ferrari for 2025 season",
        },
        {
            "title": "Verstappen disqualified from Japanese GP results",
            "description": "FIA penalty after technical infringement found in post-race inspection",
        },
        {
            "title": "Hamilton linked with shock Mercedes return - rumours",
            "description": "Sources claim negotiations ongoing for potential transfer back",
        },
        {
            "title": "F1 2026 regulation changes announced by FIA",
            "description": "New technical rules will fundamentally change car design",
        },
        {
            "title": "Alonso comments on his future in Formula 1",
            "description": "Spanish driver says he still believes he can win",
        },
        {
            "title": "F1 throwback: Best moments from 2004 season",
            "description": "A look back at Schumacher's dominant year",
        },
    ]

    for article in test_articles:
        classified = classify_article(article.copy())
        emoji = config.PRIORITY_EMOJI.get(classified["priority"], "📰")
        print(
            f"{emoji} {classified['priority']:<10} "
            f"(score={classified['priority_score']:3d}) | "
            f"{article['title'][:70]}"
        )
