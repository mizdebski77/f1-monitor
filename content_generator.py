"""
F1 Monitor - Generator treści social media
Używa HuggingFace Inference API do generowania treści.
Fallback: szablony (gdy API niedostępne lub limit wyczerpany).
"""

import json
import re
import time
from typing import Dict, Optional
import requests
from loguru import logger

import config


# ============================================================
# HUGGINGFACE API
# ============================================================
def _call_huggingface_api(prompt: str, max_retries: int = 3) -> Optional[str]:
    """
    Wywołuje HuggingFace Inference API.
    Obsługuje retry z exponential backoff.
    Zwraca wygenerowany tekst lub None w razie błędu.
    """
    if not config.HUGGINGFACE_API_TOKEN:
        logger.warning("Brak HUGGINGFACE_API_TOKEN - używam szablonów")
        return None

    headers = {
        "Authorization": f"Bearer {config.HUGGINGFACE_API_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": config.HF_MAX_TOKENS,
            "temperature": config.HF_TEMPERATURE,
            "do_sample": True,
            "return_full_text": False,
            "stop": ["---END---", "===END==="],
        },
        "options": {
            "wait_for_model": True,  # czekaj jeśli model się ładuje
            "use_cache": False,
        },
    }

    for attempt in range(max_retries):
        try:
            response = requests.post(
                config.HF_API_URL,
                headers=headers,
                json=payload,
                timeout=config.HF_TIMEOUT,
            )

            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and data:
                    text = data[0].get("generated_text", "")
                    if text:
                        return text
                elif isinstance(data, dict):
                    text = data.get("generated_text", "")
                    if text:
                        return text
                logger.warning(f"Pusta odpowiedź z HF API: {data}")
                return None

            elif response.status_code == 503:
                # Model się ładuje - czekamy
                wait_time = 20 * (attempt + 1)
                logger.info(f"Model się ładuje, czekam {wait_time}s... (próba {attempt+1})")
                time.sleep(wait_time)
                continue

            elif response.status_code == 429:
                # Rate limit
                wait_time = 60 * (attempt + 1)
                logger.warning(f"Rate limit HF API, czekam {wait_time}s...")
                time.sleep(wait_time)
                continue

            elif response.status_code == 401:
                logger.error("Błędny HUGGINGFACE_API_TOKEN - sprawdź .env")
                return None

            else:
                logger.error(
                    f"HF API błąd {response.status_code}: {response.text[:200]}"
                )
                if attempt < max_retries - 1:
                    time.sleep(5 * (attempt + 1))

        except requests.Timeout:
            logger.warning(f"HF API timeout (próba {attempt+1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(10)
        except Exception as e:
            logger.error(f"HF API nieoczekiwany błąd: {e}")
            if attempt < max_retries - 1:
                time.sleep(5)

    logger.error("HF API - wszystkie próby wyczerpane, używam szablonów")
    return None


# ============================================================
# BUDOWANIE PROMPTU
# ============================================================
def _build_content_prompt(article: Dict) -> str:
    """
    Buduje prompt do generowania treści social media.
    Zwraca dobrze ustrukturyzowany prompt dla modelu Mistral/Zephyr.
    """
    title = article.get("title", "")
    description = article.get("description", "")
    source = article.get("source_name", "")
    priority = article.get("priority", "LOW")
    url = article.get("url", "")

    urgency = {
        "BREAKING": "To jest BREAKING NEWS - pilna, przełomowa informacja!",
        "HIGH": "To jest ważny news z dużym wpływem na Formułę 1.",
        "MEDIUM": "To jest standardowy news F1.",
        "LOW": "To jest ciekawostka/informacja uzupełniająca z F1.",
    }.get(priority, "To jest news F1.")

    prompt = f"""<s>[INST] You are a social media expert specializing in Formula 1 content. Create engaging social media posts in POLISH language for the following F1 news.

NEWS INFO:
Title: {title}
Description: {description}
Source: {source}
Priority: {priority}
{urgency}

Generate ALL of the following content in POLISH. Use JSON format EXACTLY as shown:

{{
  "tiktok_script": "HOOK (pierwsze 2 sekundy, max 10 słów)\\n\\nTreść (30-60 sekund, dynamiczna, angażująca)\\n\\nCTA (wezwanie do działania)",
  "instagram_post": "Dynamiczny post z emoji, max 150 słów, angażujący",
  "facebook_post": "Rozbudowany post, 150-300 słów, kontekst i analiza",
  "twitter_post": "Max 270 znaków z emoji i 2-3 hashtagami",
  "seo_title": "SEO tytuł max 60 znaków",
  "hashtags": "#F1 #Formula1 [8-12 relevantnych hashtagów]",
  "graphic_idea": "Opis grafiki: tło, elementy, kolory, tekst na grafice"
}}

REQUIREMENTS:
- ALL content in POLISH
- TikTok hook must be shocking/intriguing (max 10 words)
- Twitter post exactly under 280 characters
- Hashtags mix Polish and English F1 tags
- Graphic idea should be vivid and specific

[/INST]"""

    return prompt


# ============================================================
# PARSOWANIE ODPOWIEDZI
# ============================================================
def _parse_generated_content(raw_text: str) -> Optional[Dict[str, str]]:
    """
    Parsuje wygenerowany tekst i wyciąga poszczególne pola.
    Próbuje JSON, a jeśli nie wychodzi - parsuje sekcjami.
    """
    if not raw_text:
        return None

    # Próba 1: Wyciągnij JSON z odpowiedzi
    json_match = re.search(r"\{[\s\S]*\}", raw_text)
    if json_match:
        try:
            data = json.loads(json_match.group())
            # Walidacja że mamy wymagane pola
            required = [
                "tiktok_script", "instagram_post", "facebook_post",
                "twitter_post", "seo_title", "hashtags", "graphic_idea"
            ]
            if all(k in data for k in required):
                # Obetnij Twitter do 280 znaków
                if len(data.get("twitter_post", "")) > 280:
                    data["twitter_post"] = data["twitter_post"][:277] + "..."
                return data
        except json.JSONDecodeError:
            pass

    # Próba 2: Parsowanie sekcjami (jeśli model nie zwrócił JSON)
    logger.warning("Nie można sparsować JSON - próbuję parsowanie sekcyjne")
    return _parse_by_sections(raw_text)


def _parse_by_sections(text: str) -> Optional[Dict[str, str]]:
    """Parsuje tekst szukając sekcji po słowach kluczowych."""
    result = {
        "tiktok_script": "",
        "instagram_post": "",
        "facebook_post": "",
        "twitter_post": "",
        "seo_title": "",
        "hashtags": "",
        "graphic_idea": "",
    }

    patterns = {
        "tiktok_script": r"(?:tiktok|tik.tok)[:\s]+(.+?)(?=instagram|facebook|twitter|seo|hashtag|graphic|$)",
        "instagram_post": r"(?:instagram)[:\s]+(.+?)(?=facebook|twitter|seo|hashtag|graphic|$)",
        "facebook_post": r"(?:facebook)[:\s]+(.+?)(?=twitter|seo|hashtag|graphic|$)",
        "twitter_post": r"(?:twitter|x\.com|tweet)[:\s]+(.+?)(?=seo|hashtag|graphic|$)",
        "seo_title": r"(?:seo)[:\s]+(.+?)(?=hashtag|graphic|$)",
        "hashtags": r"(?:hashtag)[s]?[:\s]+(.+?)(?=graphic|$)",
        "graphic_idea": r"(?:graphic|grafika|image)[:\s]+(.+?)$",
    }

    text_lower = text.lower()
    for field, pattern in patterns.items():
        match = re.search(pattern, text_lower, re.DOTALL | re.IGNORECASE)
        if match:
            content = match.group(1).strip()
            # Znajdź rzeczywistą treść (nie lowercase)
            start = text_lower.find(content[:20])
            if start != -1:
                result[field] = text[start: start + len(content)].strip()

    # Sprawdź czy cokolwiek wyciągnęliśmy
    if any(result.values()):
        return result

    return None


# ============================================================
# SZABLONY FALLBACK
# ============================================================
def _translate_title(title: str) -> str:
    """
    Próbuje przetłumaczyć najczęstsze angielskie zwroty F1 na polski.
    Prosta podmiana słów kluczowych.
    """
    translations = {
        "signs": "podpisuje kontrakt",
        "signed": "podpisał kontrakt",
        "contract": "kontrakt",
        "transfer": "transfer",
        "joins": "dołącza do",
        "leaves": "odchodzi z",
        "fired": "zwolniony",
        "sacked": "zwolniony",
        "penalty": "kara",
        "disqualified": "zdyskwalifikowany",
        "banned": "zawieszony",
        "crash": "wypadek",
        "accident": "kolizja",
        "injury": "kontuzja",
        "injured": "kontuzjowany",
        "wins": "wygrywa",
        "victory": "zwycięstwo",
        "pole position": "pole position",
        "champion": "mistrz",
        "championship": "mistrzostwo",
        "confirms": "potwierdza",
        "revealed": "ujawniony",
        "reveals": "ujawnia",
        "upgrade": "ulepszenie",
        "testing": "testy",
        "rumour": "plotka",
        "rumor": "plotka",
        "exclusive": "ekskluzywnie",
        "says": "mówi",
        "admits": "przyznaje",
        "believes": "uważa",
        "could": "może",
        "will": "będzie",
        "new": "nowy",
        "race": "wyścig",
        "team": "zespół",
        "driver": "kierowca",
        "season": "sezon",
        "car": "bolid",
        "engine": "silnik",
        "fastest": "najszybszy",
        "lap": "okrążenie",
        "Grand Prix": "Grand Prix",
        "Formula 1": "Formuła 1",
        "Formula1": "Formuła 1",
        "F1": "F1",
    }
    result = title
    for eng, pl in translations.items():
        result = result.replace(eng, pl)
    return result


def _generate_template_content(article: Dict) -> Dict[str, str]:
    """
    Generuje treści po polsku na podstawie szablonów (bez AI).
    Używane jako fallback gdy HF API jest niedostępne.
    """
    title = article.get("title", "Nowy news F1")
    description = article.get("description", "")
    source = article.get("source_name", "")
    priority = article.get("priority", "LOW")
    url = article.get("url", "")

    emoji_map = {
        "BREAKING": "🚨🔴",
        "HIGH": "🔥⚡",
        "MEDIUM": "📰🏎️",
        "LOW": "ℹ️🏁",
    }
    emoji = emoji_map.get(priority, "🏎️")

    # Opis do użycia w postach - pełny tekst bez limitu
    desc = description if description else ""

    # Hashtagi
    hashtags = _generate_hashtags(title, priority)

    # Etykieta priorytetu po polsku
    priority_pl = {
        "BREAKING": "PILNE",
        "HIGH": "WAŻNE",
        "MEDIUM": "NOWOŚĆ",
        "LOW": "F1 INFO",
    }.get(priority, "F1 INFO")

    # Kontekst do postów
    context = desc if desc else "Sprawdź szczegóły pod linkiem."

    # ── TikTok ──────────────────────────────────────────────
    hook_options = {
        "BREAKING": f"🚨 To właśnie zmieniło Formułę 1...",
        "HIGH": f"⚡ Tego się nie spodziewałeś w F1...",
        "MEDIUM": f"🏎️ Świeże info ze świata F1...",
        "LOW": f"🏁 Wiesz co właśnie wydarzyło się w F1?",
    }
    hook = hook_options.get(priority, "🏎️ Nowy news z F1!")

    tiktok = (
        f"HOOK (pierwsze 2 sekundy):\n"
        f'"{hook}"\n\n'
        f"TREŚĆ:\n"
        f"{title}\n\n"
        f"{context}\n\n"
        f"Źródło: {source}\n\n"
        f"CTA:\n"
        f"Obserwuj żeby być na bieżąco z F1! "
        f"Linkuję w bio 🏎️💨\n\n"
        f"{hashtags}"
    )

    # ── Instagram ───────────────────────────────────────────
    instagram = (
        f"{emoji} {priority_pl}: {title}\n\n"
        f"{'─' * 30}\n\n"
        f"{context}\n\n"
        f"{'─' * 30}\n\n"
        f"📡 Źródło: {source}\n"
        f"🔗 Link w bio!\n\n"
        f"Co o tym myślisz? Napisz w komentarzu! 👇\n\n"
        f"{hashtags}"
    )

    # ── Facebook ────────────────────────────────────────────
    facebook = (
        f"{emoji} {priority_pl} — {title}\n\n"
        f"{context}\n\n"
        f"Więcej szczegółów znajdziesz tutaj:\n"
        f"👉 {url}\n\n"
        f"{'─' * 30}\n"
        f"📡 Źródło: {source}\n\n"
        f"Podziel się z innymi fanami F1! 🏎️🔥\n"
        f"Obserwuj stronę żeby nie przegapić żadnego newsa!\n\n"
        f"{hashtags}"
    )

    # ── Twitter/X (max 280 znaków) ──────────────────────────
    tw_base = f"{emoji} {priority_pl}: {title}"
    if len(tw_base) > 230:
        tw_base = tw_base[:227] + "..."
    tw_tags = " ".join(hashtags.split()[:3])
    twitter_post = f"{tw_base}\n\n{tw_tags}"
    if len(twitter_post) > 280:
        twitter_post = twitter_post[:277] + "..."

    # ── SEO ─────────────────────────────────────────────────
    seo = f"F1: {title}"
    if len(seo) > 60:
        seo = seo[:57] + "..."

    # ── Grafika ─────────────────────────────────────────────
    graphic_styles = {
        "BREAKING": (
            f"Intensywne czerwone tło z efektem rozmycia ruchu. "
            f"Duży napis '🚨 PILNE' u góry białymi literami z czerwoną obwódką. "
            f"Pośrodku zdjęcie bolidu lub kierowcy (jeśli dotyczy). "
            f"Na dole czarny pasek z białym tekstem: '{title[:60]}'. "
            f"Logo F1 w prawym górnym rogu."
        ),
        "HIGH": (
            f"Ciemnogranatowe tło z pomarańczowymi akcentami. "
            f"Napis '⚡ WAŻNE' u góry. "
            f"Centralnie: nazwa zespołu lub kierowcy (duże litery). "
            f"Na dole: '{title[:60]}'. "
            f"Logo F1 w rogu."
        ),
        "MEDIUM": (
            f"Szare tło z czerwonymi paskami (styl F1). "
            f"Napis '🏎️ F1 NEWS' u góry. "
            f"Treść newsa pośrodku. "
            f"Na dole nazwa źródła i logo F1."
        ),
        "LOW": (
            f"Białe tło z czarnymi i czerwonymi detalami. "
            f"Napis 'F1 INFO' u góry. "
            f"Treść newsa pośrodku czarną czcionką. "
            f"Logo F1 w rogu."
        ),
    }
    graphic = graphic_styles.get(priority, graphic_styles["LOW"])

    return {
        "tiktok_script": tiktok,
        "instagram_post": instagram,
        "facebook_post": facebook,
        "twitter_post": twitter_post,
        "seo_title": seo,
        "hashtags": hashtags,
        "graphic_idea": graphic,
    }


def _generate_hashtags(title: str, priority: str) -> str:
    """Generuje relevantne hashtagi na podstawie tytułu."""
    base_tags = ["#F1", "#Formula1", "#FormulaOne"]

    # Tagi priorytetu
    if priority == "BREAKING":
        base_tags.extend(["#BreakingNews", "#F1News"])
    elif priority == "HIGH":
        base_tags.extend(["#F1News", "#F1Update"])

    # Tagi team/kierowca na podstawie tytułu
    team_tags = {
        "ferrari": ["#Ferrari", "#ScuderiaFerrari", "#Forza Ferrari"],
        "mercedes": ["#Mercedes", "#MercedesAMG", "#WeLead"],
        "redbull": ["#RedBull", "#RedBullRacing", "#GivesYouWings"],
        "red bull": ["#RedBull", "#RedBullRacing"],
        "mclaren": ["#McLaren", "#McLarenF1"],
        "alpine": ["#Alpine", "#AlpineF1"],
        "aston martin": ["#AstonMartin", "#AstonMartinF1"],
        "williams": ["#Williams", "#WilliamsRacing"],
        "haas": ["#HaasF1", "#HaasTeam"],
        "sauber": ["#Sauber", "#AudiF1"],
        "rb": ["#VisaCashApp", "#RBF1"],
    }
    driver_tags = {
        "hamilton": ["#Hamilton", "#LH44"],
        "verstappen": ["#Verstappen", "#MV1", "#MaxVerstappen"],
        "leclerc": ["#Leclerc", "#CL16", "#CharlesLeclerc"],
        "norris": ["#Norris", "#LN4", "#LandoNorris"],
        "sainz": ["#Sainz", "#CS55", "#CarlosSainz"],
        "alonso": ["#Alonso", "#FA14", "#FernandoAlonso"],
        "russell": ["#Russell", "#GR63", "#GeorgeRussell"],
        "piastri": ["#Piastri", "#OP81", "#OscarPiastri"],
        "perez": ["#Perez", "#SP11", "#SergioPerez"],
    }

    title_lower = title.lower()

    for keyword, tags in {**team_tags, **driver_tags}.items():
        if keyword in title_lower:
            base_tags.extend(tags[:2])  # max 2 tagi per keyword

    # Polskie tagi
    base_tags.extend(["#F1Polska", "#F1PL"])

    # Deduplikacja i limit
    seen = set()
    unique_tags = []
    for tag in base_tags:
        tag_lower = tag.lower()
        if tag_lower not in seen:
            seen.add(tag_lower)
            unique_tags.append(tag)

    return " ".join(unique_tags[:12])  # max 12 tagów


# ============================================================
# GŁÓWNA FUNKCJA
# ============================================================
def generate_content(article: Dict) -> Dict[str, str]:
    """
    Generuje kompletne treści social media dla artykułu.
    Próbuje HuggingFace API, fallback do szablonów.

    Args:
        article: Dict z polami: title, description, source_name, priority, url

    Returns:
        Dict z polami: tiktok_script, instagram_post, facebook_post,
                       twitter_post, seo_title, hashtags, graphic_idea
    """
    title = article.get("title", "")[:100]
    logger.info(f"Generuję treści dla: {title}...")

    # Spróbuj HuggingFace API
    if config.HUGGINGFACE_API_TOKEN:
        try:
            prompt = _build_content_prompt(article)
            raw_response = _call_huggingface_api(prompt)

            if raw_response:
                parsed = _parse_generated_content(raw_response)
                if parsed:
                    logger.info(f"✅ Treści wygenerowane przez HuggingFace AI")
                    return parsed
                else:
                    logger.warning("Nie można sparsować odpowiedzi HF - fallback do szablonów")
            else:
                logger.warning("Brak odpowiedzi z HF API - fallback do szablonów")

        except Exception as e:
            logger.error(f"Błąd generowania HF: {e} - fallback do szablonów")

    # Fallback: szablony
    logger.info("Używam szablonów (fallback)")
    content = _generate_template_content(article)
    return content


def format_content_for_telegram(article: Dict, content: Dict[str, str]) -> str:
    """
    Formatuje wygenerowane treści do wysłania przez Telegram.
    Jeden zwarty post: emoji + priorytet + tytuł + opis + źródło + hashtagi + link.
    """
    title = article.get("title", "")
    priority = article.get("priority", "LOW")
    source = article.get("source_name", "")
    url = article.get("url", "")
    emoji = config.PRIORITY_EMOJI.get(priority, "📰")
    sep = "─" * 35

    priority_pl = {
        "BREAKING": "🔴 PILNE",
        "HIGH": "🟠 WAŻNE",
        "MEDIUM": "🟡 NOWOŚĆ",
        "LOW": "🟢 F1 INFO",
    }.get(priority, "F1 INFO")

    # Użyj opisu bezpośrednio z artykułu
    description = article.get("description", "")

    hashtags = content.get("hashtags", "")
    graphic = content.get("graphic_idea", "")

    parts = [
        f"{emoji} {priority_pl}",
        f"",
        f"📌 {title}",
        f"",
        f"{sep}",
        f"",
        f"{description}",
        f"",
        f"{sep}",
        f"",
    ]

    if source:
        parts.append(f"📡 Źródło: {source}")
    if url:
        parts.append(f"🔗 {url}")

    parts.append("")

    if hashtags:
        parts.append(hashtags)

    if graphic:
        parts.extend([
            f"",
            f"{sep}",
            f"🖼️ Pomysł na grafikę: {graphic}",
        ])

    parts.extend([
        f"",
        f"{sep}",
        f"🏎️ F1 Monitor Bot",
    ])

    return "\n".join(parts)


if __name__ == "__main__":
    import os
    from dotenv import load_dotenv
    load_dotenv()

    test_article = {
        "title": "Lewis Hamilton signs shock Ferrari contract extension",
        "description": "Ferrari officially confirms Hamilton will continue with the team",
        "source_name": "Motorsport.com",
        "priority": "BREAKING",
        "url": "https://example.com/test",
    }

    print("🤖 Test generatora treści F1\n")
    print(f"News: {test_article['title']}\n")

    content = generate_content(test_article)

    for key, value in content.items():
        print(f"\n{'='*50}")
        print(f"📌 {key.upper()}:")
        print(f"{'='*50}")
        print(value[:300])
