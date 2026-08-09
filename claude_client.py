"""Tutte le chiamate all'API Claude: estrazione piano, ricerca ricetta,
sostituzioni, stime nutrizionali e riconoscimento pasto consumato."""

import re

try:
    import anthropic
except ImportError:  # pragma: no cover
    anthropic = None

from config import ANTHROPIC_API_KEY, CLAUDE_MODEL

_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if anthropic is not None else None

_URL_RE = re.compile(r"https?://\S+")

_PLAN_TOOL = {
    "name": "record_plan",
    "description": "Registra il piano alimentare strutturato estratto dal documento PDF.",
    "input_schema": {
        "type": "object",
        "properties": {
            "language": {
                "type": "string",
                "enum": ["it", "es", "en"],
                "description": "Lingua dominante del documento sorgente",
            },
            "plan_type": {
                "type": "string",
                "enum": ["weekly_plan", "single_recipe"],
            },
            "days": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "day_label": {
                            "type": "string",
                            "description": "Giorno cosi' come scritto nel documento (es. 'Lunedi', 'Lunes', 'Monday') oppure una data esplicita se presente",
                        },
                        "meals": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "meal_type": {
                                        "type": "string",
                                        "enum": ["breakfast", "lunch", "dinner"],
                                    },
                                    "dish_name": {"type": "string"},
                                    "description": {"type": "string"},
                                    "ingredients": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                    },
                                    "instructions": {"type": "string"},
                                    "recipe_link": {"type": "string"},
                                    "calories": {"type": "integer"},
                                    "macros": {
                                        "type": "object",
                                        "properties": {
                                            "protein_g": {"type": "number"},
                                            "carbs_g": {"type": "number"},
                                            "fat_g": {"type": "number"},
                                        },
                                    },
                                },
                                "required": ["meal_type", "dish_name"],
                            },
                        },
                    },
                    "required": ["day_label", "meals"],
                },
            },
        },
        "required": ["language", "plan_type", "days"],
    },
}

_SUBSTITUTION_TOOL = {
    "name": "record_substitution",
    "description": "Registra un piatto alternativo per sostituire un pasto pianificato.",
    "input_schema": {
        "type": "object",
        "properties": {
            "dish_name": {"type": "string"},
            "description": {"type": "string"},
            "ingredients": {"type": "array", "items": {"type": "string"}},
            "instructions": {"type": "string"},
            "recipe_link": {"type": "string"},
            "calories": {"type": "integer"},
            "macros": {
                "type": "object",
                "properties": {
                    "protein_g": {"type": "number"},
                    "carbs_g": {"type": "number"},
                    "fat_g": {"type": "number"},
                },
            },
        },
        "required": ["dish_name", "ingredients", "instructions"],
    },
}

_NUTRITION_TOOL = {
    "name": "record_nutrition",
    "description": "Registra la stima nutrizionale di un piatto.",
    "input_schema": {
        "type": "object",
        "properties": {
            "calories": {"type": "integer"},
            "protein_g": {"type": "number"},
            "carbs_g": {"type": "number"},
            "fat_g": {"type": "number"},
        },
        "required": ["calories", "protein_g", "carbs_g", "fat_g"],
    },
}

_RECIPE_DETAIL_TOOL = {
    "name": "record_recipe",
    "description": "Registra ingredienti e istruzioni per un piatto.",
    "input_schema": {
        "type": "object",
        "properties": {
            "ingredients": {"type": "array", "items": {"type": "string"}},
            "instructions": {"type": "string"},
        },
        "required": ["ingredients", "instructions"],
    },
}

_URL_RECIPE_TOOL = {
    "name": "record_url_recipe",
    "description": "Registra la ricetta estratta dal testo di una pagina web.",
    "input_schema": {
        "type": "object",
        "properties": {
            "language": {
                "type": "string",
                "enum": ["it", "es", "en"],
                "description": "Lingua della ricetta, solo se sei ragionevolmente sicuro",
            },
            "dish_name": {"type": "string"},
            "ingredients": {"type": "array", "items": {"type": "string"}},
            "instructions": {"type": "string"},
            "calories": {"type": "integer"},
            "macros": {
                "type": "object",
                "properties": {
                    "protein_g": {"type": "number"},
                    "carbs_g": {"type": "number"},
                    "fat_g": {"type": "number"},
                },
            },
        },
        "required": ["dish_name", "ingredients", "instructions"],
    },
}

_MATCH_TOOL = {
    "name": "record_match",
    "description": "Registra a quale pasto pianificato corrisponde cio' che l'utente dice di aver mangiato.",
    "input_schema": {
        "type": "object",
        "properties": {
            "matched_meal_id": {
                "type": ["integer", "null"],
                "description": "Id del pasto pianificato corrispondente, oppure null se nessuno corrisponde",
            },
            "status": {
                "type": "string",
                "enum": ["eaten_as_planned", "eaten_different", "skipped"],
            },
            "note": {"type": "string"},
        },
        "required": ["matched_meal_id", "status"],
    },
}


def _call_tool(prompt: str, tool: dict, max_tokens: int = 4096) -> dict:
    if anthropic is None:
        raise RuntimeError(
            "Claude integration is unavailable because the 'anthropic' package is not installed. "
            "Install it with 'pip install anthropic'."
        )

    response = _client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        tools=[tool],
        tool_choice={"type": "tool", "name": tool["name"]},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in response.content:
        if block.type == "tool_use":
            return block.input
    raise RuntimeError("Claude non ha restituito un tool_use come atteso")


def extract_plan(pdf_text: str) -> dict:
    prompt = (
        "Il testo seguente e' stato estratto da un PDF che contiene un piano alimentare "
        "settimanale oppure una singola ricetta. Il documento puo' essere in italiano, "
        "spagnolo o inglese. Analizzalo e registra la struttura tramite lo strumento "
        "record_plan. Se e' una singola ricetta, restituisci un solo giorno con un solo "
        "pasto (usa meal_type piu' plausibile). Mantieni i nomi dei piatti e gli "
        "ingredienti nella lingua originale del documento. Se il documento riporta un "
        "link a una ricetta, includilo in recipe_link.\n\n"
        f"--- TESTO PDF ---\n{pdf_text}"
    )
    return _call_tool(prompt, _PLAN_TOOL)


def extract_recipe_from_text(page_text: str) -> dict:
    prompt = (
        "Il testo seguente e' stato estratto da una pagina web che contiene una ricetta. "
        "Puo' essere in italiano, spagnolo o inglese. Estrai il nome del piatto, gli "
        "ingredienti (con quantita' se presenti), le istruzioni di preparazione e, se "
        "disponibili, le informazioni nutrizionali. Imposta 'language' solo se sei "
        "ragionevolmente sicuro della lingua della ricetta; lascialo non impostato se "
        "e' ambiguo. Registra tramite lo strumento record_url_recipe.\n\n"
        f"--- TESTO PAGINA ---\n{page_text}"
    )
    return _call_tool(prompt, _URL_RECIPE_TOOL)


def find_recipe_link(dish_name: str, language: str) -> str | None:
    lang_names = {"it": "italiano", "es": "spagnolo", "en": "inglese"}
    prompt = (
        f"Cerca sul web una pagina con la ricetta per il piatto '{dish_name}' in "
        f"{lang_names.get(language, 'italiano')}. Rispondi SOLO con l'URL trovato, "
        "senza altro testo."
    )
    try:
        response = _client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1024,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception:
        return None

    text = "".join(block.text for block in response.content if block.type == "text")
    match = _URL_RE.search(text)
    return match.group(0).rstrip(").,") if match else None


def find_recipe_links_multilang(dish_name: str) -> dict:
    """Cerca un link alla ricetta in italiano, spagnolo e inglese. Se il piatto e' in
    un'altra lingua, il modello lo traduce implicitamente prima di cercare."""
    return {lang: find_recipe_link(dish_name, lang) for lang in ("it", "es", "en")}


def suggest_substitution(original_dish: str, plan_language: str, constraints: str) -> dict:
    lang_names = {"it": "italiano", "es": "spagnolo", "en": "inglese"}
    prompt = (
        f"Nel piano alimentare dell'utente c'e' il piatto '{original_dish}', ma "
        f"all'utente non piace. Proponi un'alternativa equivalente dal punto di vista "
        f"nutrizionale ({constraints}), rispettando lo stesso pasto della giornata. "
        f"Scrivi la risposta in {lang_names.get(plan_language, 'italiano')} e registrala "
        "tramite lo strumento record_substitution."
    )
    return _call_tool(prompt, _SUBSTITUTION_TOOL)


def estimate_nutrition(dish_name: str, ingredients: list[str] | None) -> dict:
    ingredients_text = ", ".join(ingredients) if ingredients else "non specificati"
    prompt = (
        f"Stima calorie e macronutrienti per il piatto '{dish_name}' "
        f"(ingredienti: {ingredients_text}). Registra la stima tramite lo strumento "
        "record_nutrition."
    )
    return _call_tool(prompt, _NUTRITION_TOOL, max_tokens=512)


def generate_recipe_details(dish_name: str, language: str = "en") -> dict:
    lang_names = {"it": "italiano", "es": "spagnolo", "en": "inglese"}
    prompt = (
        f"Fornisci gli ingredienti (con quantita' precise per una porzione) e le istruzioni "
        f"di preparazione per il piatto '{dish_name}', in {lang_names.get(language, 'inglese')}. "
        "Registra la risposta tramite lo strumento record_recipe."
    )
    return _call_tool(prompt, _RECIPE_DETAIL_TOOL)


def match_eaten_meal(free_text: str, candidate_meals: list[dict]) -> dict:
    meals_desc = "\n".join(f"id={m['id']}: {m['meal_type']} - {m['dish_name']}" for m in candidate_meals)
    prompt = (
        "L'utente ha scritto questo messaggio per raccontare cosa ha mangiato:\n"
        f"\"{free_text}\"\n\n"
        "Questi sono i pasti pianificati per oggi:\n"
        f"{meals_desc}\n\n"
        "Determina a quale pasto pianificato si riferisce (matched_meal_id), se ha "
        "mangiato esattamente quello (eaten_as_planned) o qualcosa di diverso "
        "(eaten_different), oppure se dice di averlo saltato (skipped). Se il messaggio "
        "non sembra riguardare un pasto, imposta matched_meal_id a null e status a "
        "'eaten_different'. Registra tramite lo strumento record_match."
    )
    return _call_tool(prompt, _MATCH_TOOL, max_tokens=512)
