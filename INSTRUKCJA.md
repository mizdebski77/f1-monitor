# 🏎️ F1 Monitor — Instrukcja instalacji i uruchomienia

## Co robi ten system?

Automatycznie monitoruje 12+ źródeł F1 (RSS + scraping), wykrywa duplikaty semantycznie, klasyfikuje priorytet newsów (BREAKING/HIGH/MEDIUM/LOW) i wysyła Ci powiadomienie na Telegram z gotowymi treściami social media wygenerowanymi przez AI.

---

## Wymagania wstępne

- **Python 3.10 lub nowszy** (sprawdź: `python --version`)
- **Połączenie z internetem**
- **Konto Telegram** (do odbierania powiadomień)
- **Konto HuggingFace** (darmowe, do generowania treści AI)

---

## KROK 1 — Pobierz pliki projektu

Skopiuj folder `f1_monitor` gdzieś na swój komputer, np.:
```
C:\Users\TwojaNazwa\f1_monitor\
```
lub na Linux/Mac:
```
~/f1_monitor/
```

---

## KROK 2 — Zainstaluj Python (jeśli nie masz)

### Windows:
1. Wejdź na https://www.python.org/downloads/
2. Pobierz Python 3.11+ i zainstaluj
3. **WAŻNE**: zaznacz "Add Python to PATH" podczas instalacji

### Mac:
```bash
brew install python3
```

### Linux (Ubuntu/Debian):
```bash
sudo apt update && sudo apt install python3 python3-pip
```

---

## KROK 3 — Zainstaluj zależności

Otwórz terminal/wiersz poleceń **w folderze f1_monitor** i wpisz:

```bash
pip install -r requirements.txt
```

Jeśli masz błąd z `pip`, spróbuj:
```bash
pip3 install -r requirements.txt
# lub
python -m pip install -r requirements.txt
```

Instalacja zajmie 1-2 minuty. Pobierze:
- `feedparser` — czytanie RSS
- `beautifulsoup4` — scraping stron
- `requests` — połączenia HTTP
- `schedule` — harmonogram zadań
- `loguru` — ładne logi
- `scikit-learn` — deduplikacja semantyczna
- `python-dotenv` — plik .env

---

## KROK 4 — Utwórz Telegram Bota

To jest jednorazowa konfiguracja, zajmuje ~3 minuty.

### 4a. Utwórz bota przez BotFather:
1. Otwórz Telegram i wyszukaj **@BotFather**
2. Wyślij: `/start`
3. Wyślij: `/newbot`
4. Podaj nazwę bota (np. `Mój F1 Monitor`)
5. Podaj username bota (musi kończyć się na `bot`, np. `moj_f1_monitor_bot`)
6. BotFather wyśle Ci **TOKEN** — wygląda tak:
   ```
   1234567890:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
7. **Skopiuj ten token** — będzie potrzebny za chwilę

### 4b. Pobierz swoje Chat ID:
1. Wyślij **jakąkolwiek wiadomość** do swojego nowego bota
2. Otwórz Telegram i wyszukaj **@userinfobot**
3. Wyślij: `/start`
4. Bot wyśle Ci Twoje **ID** — to liczba, np. `123456789`
5. **Skopiuj to ID**

---

## KROK 5 — Pobierz token HuggingFace (AI)

1. Wejdź na https://huggingface.co/join i zarejestruj się (darmowe)
2. Po rejestracji wejdź na: https://huggingface.co/settings/tokens
3. Kliknij "New token"
4. Nazwa: np. `f1-monitor`
5. Typ: **Read**
6. Kliknij "Generate a token"
7. **Skopiuj token** — zaczyna się od `hf_`

> **Uwaga**: Bez tokenu HuggingFace system działa, ale używa prostych szablonów zamiast AI do generowania treści.

---

## KROK 6 — Skonfiguruj plik .env

W folderze `f1_monitor` skopiuj plik konfiguracyjny:

### Windows:
```cmd
copy .env.example .env
```

### Mac/Linux:
```bash
cp .env.example .env
```

Otwórz plik `.env` dowolnym edytorem tekstu (np. Notatnik, VS Code, Notepad++) i uzupełnij:

```env
# Wklej token od @BotFather:
TELEGRAM_BOT_TOKEN=1234567890:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Wklej swoje Chat ID od @userinfobot:
TELEGRAM_CHAT_ID=123456789

# Wklej token HuggingFace:
HUGGINGFACE_API_TOKEN=hf_twoj_token_tutaj
```

**Zapisz plik.**

---

## KROK 7 — Test wszystkich komponentów

Przed uruchomieniem sprawdź czy wszystko działa:

```bash
python main.py --mode test
```

Powinieneś zobaczyć:
```
1. Konfiguracja:    ✅ OK
2. Baza danych:     ✅ OK
3. Telegram:        ✅ OK
4. RSS Sources:     [lista źródeł z liczbą artykułów]
5. Klasyfikator:    ✅ OK
```

Jeśli Telegram ✅ OK — sprawdź swój Telegram, powinieneś otrzymać wiadomość testową!

---

## KROK 8 — Uruchom system!

```bash
python main.py
```

System wypisze:
```
🏎️  F1 MONITOR - System monitorowania newsów F1
✅ Telegram połączony
✅ Aktywnych źródeł RSS: 12
✅ Interwał sprawdzania: 3 minuty
🚀 System uruchomiony! Wciśnij Ctrl+C aby zatrzymać.
```

Na Telegramie otrzymasz wiadomość potwierdzającą start, a następnie pierwsze powiadomienia o newsach F1.

---

## Jak zatrzymać system?

Wciśnij **Ctrl+C** w terminalu. System gracefully się zamknie.

---

## Uruchamianie w tle (opcjonalnie)

### Windows — Task Scheduler:
1. Wyszukaj "Harmonogram zadań" w Start
2. Utwórz zadanie podstawowe
3. Akcja: `python C:\ścieżka\do\f1_monitor\main.py`
4. Ustaw "Uruchom niezależnie czy użytkownik jest zalogowany"

### Windows — prosta alternatywa (skrypt .bat):
Utwórz plik `start_f1.bat` na Pulpicie:
```bat
@echo off
cd /d C:\Users\TwojaNazwa\f1_monitor
python main.py
pause
```

### Mac/Linux — nohup (działa po zamknięciu terminala):
```bash
nohup python main.py > logs/nohup.log 2>&1 &
echo "PID: $!" > logs/pid.txt
```

Aby zatrzymać:
```bash
kill $(cat logs/pid.txt)
```

### Mac/Linux — cron (uruchamia po restarcie):
```bash
crontab -e
```
Dodaj linię:
```
@reboot cd /home/twoja_nazwa/f1_monitor && python main.py >> logs/cron.log 2>&1
```

---

## Tryby uruchamiania

```bash
# Normalne ciągłe monitorowanie (domyślne):
python main.py

# Jeden cykl i koniec (do testów):
python main.py --mode once

# Pokaż statystyki z bazy danych:
python main.py --mode stats

# Testuj wszystkie komponenty:
python main.py --mode test
```

---

## Dostosowanie systemu

### Zmień interwał sprawdzania:
W pliku `.env`:
```env
CHECK_INTERVAL_MINUTES=5   # co 5 minut (domyślnie 3)
```

### Dodaj nowe źródło RSS:
W pliku `config.py`, w sekcji `RSS_SOURCES`, dodaj:
```python
{
    "name": "Nazwa Źródła",
    "url": "https://przyklad.com/feed/rss",
    "category": "media",
    "priority_boost": 0,
    "enabled": True,
},
```

### Zmień próg duplikatów:
W `.env`:
```env
DUPLICATE_THRESHOLD=0.80   # bardziej restrykcyjny (0.0-1.0)
```

### Wyłącz konkretne źródło:
W `config.py`, zmień `"enabled": True` na `"enabled": False`.

### Zmień model AI HuggingFace:
W `.env`:
```env
# Szybszy, lżejszy model:
HF_MODEL=HuggingFaceH4/zephyr-7b-beta

# Domyślny (dobry jakościowo):
HF_MODEL=mistralai/Mistral-7B-Instruct-v0.2
```

---

## Rozwiązywanie problemów

### ❌ "TELEGRAM_BOT_TOKEN nie jest ustawiony"
→ Sprawdź czy plik `.env` istnieje (nie `.env.example`)
→ Sprawdź czy token jest wklejony bez spacji

### ❌ "Nie można połączyć z Telegram API"
→ Sprawdź połączenie internetowe
→ Sprawdź czy token bota jest poprawny
→ Upewnij się że wysłałeś wiadomość do bota zanim sprawdziłeś Chat ID

### ❌ "ModuleNotFoundError"
→ Uruchom: `pip install -r requirements.txt`
→ Jeśli nadal błąd: `python -m pip install -r requirements.txt`

### ❌ Brak artykułów z niektórych źródeł
→ Niektóre RSS feedy mogą być tymczasowo niedostępne
→ Uruchom: `python monitor.py` żeby zobaczyć status każdego źródła

### ❌ HuggingFace API timeout
→ Modele HF na darmowym tierze "zasypiają" — pierwsze żądanie może trwać 20-30 sekund
→ System automatycznie czeka i ponawia próbę
→ Możesz przełączyć na szybszy model `HuggingFaceH4/zephyr-7b-beta`

### ⚠️ Dużo duplikatów
→ Obniż próg: `DUPLICATE_THRESHOLD=0.70` w `.env`

### ⚠️ Za mało duplikatów (ten sam news wielokrotnie)
→ Podwyższ próg: `DUPLICATE_THRESHOLD=0.85` w `.env`

---

## Struktura plików

```
f1_monitor/
├── .env                    ← TWOJE KLUCZE (nie udostępniaj!)
├── .env.example            ← Szablon konfiguracji
├── requirements.txt        ← Zależności Python
├── config.py              ← Ustawienia systemu
├── database.py            ← Baza danych SQLite
├── monitor.py             ← Pobieranie RSS i scraping
├── deduplicator.py        ← Wykrywanie duplikatów
├── prioritizer.py         ← Klasyfikacja BREAKING/HIGH/MEDIUM/LOW
├── content_generator.py   ← Generator treści AI (HuggingFace)
├── notifier.py            ← Powiadomienia Telegram
├── main.py                ← Główny plik uruchamiający
├── data/
│   └── f1_monitor.db      ← Baza danych (tworzy się automatycznie)
└── logs/
    └── f1_monitor.log     ← Logi systemu
```

---

## Plany na przyszłość (rozbudowa)

Gdy system będzie działać, możesz dodać:

1. **Automatyczne grafiki AI** — integracja z DALL-E 3 API (darmowy tier) lub Stable Diffusion lokalnie przez Automatic1111
2. **Auto-posting na social media** — Buffer API (darmowy tier), lub bezpośrednie API platform (wymaga weryfikacji biznesowej)
3. **Dashboard statystyk** — Streamlit (darmowy) lub Grafana + SQLite
4. **Analiza trendów** — analiza słów kluczowych z SQLite + matplotlib/plotly
5. **Więcej źródeł** — Twitter/X (wymaga płatnego API v2), ale można używać RSS bridge przez nitter.net instancje

---

## Szybki start (TL;DR)

```bash
# 1. Zainstaluj zależności
pip install -r requirements.txt

# 2. Skonfiguruj (uzupełnij tokeny)
cp .env.example .env
notepad .env   # Windows
# lub: nano .env   # Mac/Linux

# 3. Przetestuj
python main.py --mode test

# 4. Uruchom!
python main.py
```

---

*F1 Monitor — darmowy, otwarty system monitorowania newsów F1 🏎️💨*
