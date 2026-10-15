"""
TOOLS: Python functions the model is allowed to call.

HOW TOOL CALLING WORKS
  1. The name, description and inputs of every switched-on tool are shown to
     the model, hidden in the prompt.
  2. When a question needs one, the model writes a tool request instead of an
     answer, e.g. "call get_weather with city = Copenhagen".
  3. The app runs the Python function below and gives the model what it
     returned (always plain text).
  4. The model writes its answer using that result.
  The model never runs code itself; it can only ask. In the chat window, a
  "Used tool" box shows exactly what it asked for and what it got back.

SWITCHING TOOLS ON AND OFF
  All tools are off by default. Turn them on in config.toml under [tools]
  (e.g. weather = true) and restart LocalChat.
  Tip: small models (like the default 0.6B) sometimes forget to use a tool or
  pass wrong inputs. Qwen3 4B (Models button in the app) is much more reliable.

ADD YOUR OWN TOOL (3 steps)
  1. Write a normal Python function below that returns text (a str).
  2. Put @tool("what it does", params={"input": "what this input means"}) above
     it. The model ONLY sees these descriptions and the function name, so write
     them like instructions: say when to use the tool and what to pass.
  3. Add it to TOOLS at the bottom of this file, add `my_name = true` under
     [tools] in config.toml, and restart LocalChat.

  Example:
      @tool("Roll a dice and return the number", params={"sides": "Number of sides, e.g. 6"})
      def roll_dice(sides: int) -> str:
          import random
          return str(random.randint(1, sides))
"""
import json
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import nobodywho

from .config import ROOT
from .tool_support import tool


# ============================================================================
#  Helper: fetch JSON from a web API
# ============================================================================

def get_json(url: str, params: dict | None = None) -> dict:
    if params:
        url += "?" + urllib.parse.urlencode(params)
    # Wikipedia asks API users to identify themselves with a User-Agent.
    request = urllib.request.Request(url, headers={"User-Agent": "LocalChat/1.0 (workshop demo)"})
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def find_place(city: str) -> dict:
    """Look up a city with the free Open-Meteo geocoding API (no API key)."""
    data = get_json(
        "https://geocoding-api.open-meteo.com/v1/search",
        {"name": city, "count": 1, "language": "en"},
    )
    if not data.get("results"):
        raise ValueError(f"Could not find a place called '{city}'.")
    return data["results"][0]  # includes name, country, latitude, longitude, timezone


# ============================================================================
#  Tool: time
# ============================================================================

@tool(
    "Get the current date and time. Call it with an empty city for the user's "
    "own local time, or with a city name for the time in that city.",
    params={"city": "A city name like 'Tokyo', or empty for the user's local time"},
)
def get_current_time(city: str = "") -> str:
    if not city.strip():
        now = datetime.now().astimezone()
        return f"Local time: {now:%A %d %B %Y, %H:%M}"
    place = find_place(city)
    now = datetime.now(ZoneInfo(place["timezone"]))
    return f"Time in {place['name']}, {place.get('country', '')}: {now:%A %d %B %Y, %H:%M}"


# ============================================================================
#  Tool: weather (Open-Meteo, free, no API key)
# ============================================================================

# Open-Meteo describes the weather with a number (WMO weather code).
WEATHER_CODES = {
    0: "clear sky", 1: "mainly clear", 2: "partly cloudy", 3: "overcast",
    45: "fog", 48: "freezing fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    66: "freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "light rain showers", 81: "rain showers", 82: "violent rain showers",
    85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with heavy hail",
}


@tool(
    "Get the current weather and today's forecast for a city.",
    params={"city": "The city name, e.g. 'Copenhagen'"},
)
def get_weather(city: str) -> str:
    place = find_place(city)
    data = get_json(
        "https://api.open-meteo.com/v1/forecast",
        {
            "latitude": place["latitude"],
            "longitude": place["longitude"],
            "current": "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "forecast_days": 1,
            "timezone": "auto",
        },
    )
    now, today = data["current"], data["daily"]
    return (
        f"Weather in {place['name']}, {place.get('country', '')} right now: "
        f"{WEATHER_CODES.get(now['weather_code'], 'unknown conditions')}, "
        f"{now['temperature_2m']} °C (feels like {now['apparent_temperature']} °C), "
        f"humidity {now['relative_humidity_2m']} %, wind {now['wind_speed_10m']} km/h. "
        f"Today: {today['temperature_2m_min'][0]} to {today['temperature_2m_max'][0]} °C, "
        f"{today['precipitation_probability_max'][0]} % chance of rain."
    )


# ============================================================================
#  Tool: Wikipedia
# ============================================================================

WIKIPEDIA_LANGUAGE = "en"  # try "da" for Danish Wikipedia


@tool(
    "Look up a topic on Wikipedia and return the introduction of the best "
    "matching article. Use it for facts about people, places, events and concepts.",
    params={"topic": "What to look up, e.g. 'Niels Bohr'"},
)
def search_wikipedia(topic: str) -> str:
    data = get_json(
        f"https://{WIKIPEDIA_LANGUAGE}.wikipedia.org/w/api.php",
        {
            "action": "query", "format": "json",
            "generator": "search", "gsrsearch": topic, "gsrlimit": 1,
            "prop": "extracts|info", "exintro": 1, "explaintext": 1, "inprop": "url",
        },
    )
    pages = data.get("query", {}).get("pages", {})
    if not pages:
        return f"No Wikipedia article found for '{topic}'."
    page = next(iter(pages.values()))
    intro = page.get("extract", "")[:3000]
    return f"{page['title']}\n\n{intro}\n\nSource: {page.get('fullurl', '')}"


# ============================================================================
#  Tools: spreadsheets with pandas (files in the `data` folder)
# ============================================================================
# Put CSV or Excel files in the `data` folder next to the app. An example,
# sales_2025.csv, is included. The model gets exact numbers from pandas
# instead of trying to do the maths in its head.

DATA_FOLDER = ROOT / "data"
SPREADSHEET_TYPES = (".csv", ".xlsx", ".xls")


def spreadsheet_names() -> str:
    files = sorted(p.name for p in DATA_FOLDER.glob("*") if p.suffix.lower() in SPREADSHEET_TYPES)
    return ", ".join(files) if files else "The data folder is empty."


def load_table(file_name: str):
    import pandas as pd  # imported here so the app starts fast when this tool is off

    path = DATA_FOLDER / Path(file_name).name  # .name keeps it inside the data folder
    if not path.exists():
        raise FileNotFoundError(f"No file called '{file_name}'. Available files: {spreadsheet_names()}")
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return pd.read_excel(path)


@tool("List the spreadsheet files (CSV or Excel) that are available for analysis.")
def list_data_files() -> str:
    return spreadsheet_names()


@tool(
    "Show the columns, number of rows and the first rows of a spreadsheet. "
    "Call this first to learn the exact column names.",
    params={"file_name": "The file name, e.g. 'sales_2025.csv'"},
)
def describe_table(file_name: str) -> str:
    df = load_table(file_name)
    columns = ", ".join(f"{name} ({dtype})" for name, dtype in df.dtypes.items())
    return f"{len(df)} rows.\nColumns: {columns}\n\nFirst rows:\n{df.head().to_string(index=False)}"


@tool(
    "Calculate an exact number from a spreadsheet column, optionally split into "
    "groups. Always use this for numbers instead of calculating yourself. "
    "If you don't know the exact column names, call describe_table first. "
    "For one product or region, group by that column and read its row.",
    params={
        "file_name": "The file name, e.g. 'sales_2025.csv'",
        "column": "The column to calculate on, e.g. 'revenue'",
        "operation": "sum (total), mean (average), median, min or max (the single "
        "smallest/largest row), or count (number of rows). For 'highest total' use sum.",
        "group_by": "Optional column to split the result by, e.g. 'region'. Empty for one overall number.",
    },
)
def calculate(file_name: str, column: str, operation: str, group_by: str = "") -> str:
    df = load_table(file_name)
    operation = operation.strip().lower()
    if operation not in ("sum", "mean", "median", "min", "max", "count"):
        raise ValueError("operation must be one of: sum, mean, median, min, max, count")
    for name in [column, group_by]:
        if name and name not in df.columns:
            raise ValueError(f"No column '{name}'. The columns are: {', '.join(df.columns)}. Call calculate again with one of these.")

    if group_by:
        result = df.groupby(group_by)[column].agg(operation).sort_values(ascending=False)
        return f"{operation} of {column} per {group_by}:\n{result.round(2).to_string()}"
    value = df[column].agg(operation)
    return f"{operation} of {column}: {round(float(value), 2)}"


# ============================================================================
#  Tool: RAG, search your own documents in the `rag` folder
# ============================================================================
# RAG = "retrieval-augmented generation": find the relevant passages first,
# then let the model answer from them. Three steps:
#
#  1. CHUNK:  every document in the `rag` folder is split into pieces of
#             about 200 words (a whole document wouldn't fit in the prompt).
#  2. EMBED:  a small embedding model turns each piece into 384 numbers that
#             describe its meaning. Texts that mean similar things get similar
#             numbers, even with different words ("refund" ~ "money back").
#  3. SEARCH: the question gets its 384 numbers too, and the pieces whose
#             numbers are closest (cosine similarity: 1 = same meaning,
#             0 = unrelated) are handed to the chat model.
#
# Embeddings are kept in memory and only recomputed for new or changed files,
# so you can drop documents into the folder while the app is running.

RAG_FOLDER = ROOT / "rag"
DOCUMENT_TYPES = (".pdf", ".docx", ".txt", ".md")
# A 35 MB embedding model, downloaded the first time a search runs.
EMBEDDING_MODEL = "huggingface:CompendiumLabs/bge-small-en-v1.5-gguf/bge-small-en-v1.5-q8_0.gguf"
CHUNK_WORDS = 200    # words per piece
OVERLAP_WORDS = 40   # repeated between neighbouring pieces, so no sentence is lost at a cut
TOP_RESULTS = 3      # how many pieces the model gets

encoder = None  # loaded on first use
index = {}      # file -> (last modified time, [(piece of text, its 384 numbers), ...])


def read_document(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader
        return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
    if path.suffix.lower() == ".docx":
        import docx
        return "\n".join(paragraph.text for paragraph in docx.Document(path).paragraphs)
    return path.read_text(encoding="utf-8", errors="replace")  # .txt / .md


def split_into_chunks(text: str) -> list[str]:
    words = text.split()
    step = CHUNK_WORDS - OVERLAP_WORDS
    return [" ".join(words[i:i + CHUNK_WORDS]) for i in range(0, len(words), step)]


def update_index() -> None:
    global encoder
    if encoder is None:
        encoder = nobodywho.Encoder(EMBEDDING_MODEL)
    files = [p for p in RAG_FOLDER.glob("*") if p.suffix.lower() in DOCUMENT_TYPES]
    for path in list(index):
        if path not in files:
            del index[path]  # the file was deleted
    for path in files:
        modified = path.stat().st_mtime
        if path in index and index[path][0] == modified:
            continue  # already embedded and unchanged
        chunks = split_into_chunks(read_document(path))
        index[path] = (modified, list(zip(chunks, encoder.encode_batch(chunks))))


@tool(
    "Search the user's own documents (company handbooks, policies, procedures, "
    "notes, reports) for passages that answer a question. Call this FIRST for "
    "any question about the user's work, company, rules, travel, expenses, "
    "leave or what to do in a situation, even if no document is mentioned. "
    "Base your answer on the passages found.",
    # No example query here: small models tend to copy an example word for word.
    params={"question": "The user's question, in the user's own words"},
)
def search_documents(question: str) -> str:
    update_index()
    question_numbers = encoder.encode(question)
    scored = [
        (nobodywho.cosine_similarity(question_numbers, numbers), path.name, text)
        for path, (_, chunks) in index.items()
        for text, numbers in chunks
    ]
    if not scored:
        return "The rag folder contains no documents."
    best = sorted(scored, reverse=True)[:TOP_RESULTS]
    return "\n\n".join(f"[{name}, similarity {score:.2f}]\n{text}" for score, name, text in best)


# ============================================================================
#  The list of tools. The names on the left are the switches in config.toml.
# ============================================================================

TOOLS = {
    "time": [get_current_time],
    "weather": [get_weather],
    "wikipedia": [search_wikipedia],
    "pandas": [list_data_files, describe_table, calculate],
    "rag": [search_documents],
}
