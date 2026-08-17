# AI queue: request/response file contract

The bot no longer calls the Anthropic API directly (no `ANTHROPIC_API_KEY` exists
anywhere in this project anymore). Instead, two AI-dependent features - PDF plan
upload and recipe Scan (`/scan`, `/scan_week`, `/scan_all`, and `/edit_recipe`'s Scan
button) - write a **request** JSON file and later read back a **response** JSON file,
both under `data/ai_queue/` (gitignored, created automatically on first use):

```
data/ai_queue/
  requests/<id>.json    written by the bot (ai_queue_service.enqueue)
  responses/<id>.json   written by the external consumer - THIS is what you produce
  log/                  archived request+response pairs after the bot consumes them
```

- The bot side polls `responses/` every minute (`bot.py`'s `poll_ai_queue` job) and
  archives both files to `log/` once consumed. It never deletes a `requests/*.json`
  file itself, so it's still there when you (the consumer) look for it.
- **The consumer's job**: for every file in `requests/` that does not yet have a
  matching file (same filename) in `responses/`, do the work described below and write
  `responses/<id>.json`. Never touch `requests/` or `log/`.
- `<id>` is an opaque string (e.g. `1737012345_a1b2c3d4`) - always copy it verbatim from
  the request's `"id"` field into the response's `"id"` field and use it as the
  response filename.

## Request format (both types)

```json
{
  "id": "1737012345_a1b2c3d4",
  "type": "extract_plan",
  "chat_id": 123456789,
  "created_at": "2026-08-15T12:34:56",
  "payload": { "...": "type-specific, see below" }
}
```

## Response format (both types)

On success:

```json
{ "id": "1737012345_a1b2c3d4", "result": { "...": "type-specific, see below" }, "error": null }
```

On failure (malformed input, nothing usable extracted, etc.) - never crash or skip a
file silently, always write a response:

```json
{ "id": "1737012345_a1b2c3d4", "result": null, "error": "short human-readable reason" }
```

---

## Type: `extract_plan`

Source: PDF plan upload (`handlers/upload.py`). The PDF's text has already been
extracted locally (no OCR/vision needed) and handed to you as plain text.

**`payload`:**

```json
{ "pdf_text": "<raw text extracted from the PDF>", "source_filename": "diet-week12.pdf" }
```

**Task:** `pdf_text` is the text of a PDF that contains either a weekly meal plan or a
single recipe. It may be in Italian, Spanish, or English - keep dish names and
ingredients in the document's original language (do not translate them). If it's a
single recipe, return one day with one meal (pick the most plausible `meal_type`). If
the document links to a recipe online, include it in `recipe_link`.

**`result`:**

```json
{
  "language": "it",
  "plan_type": "weekly_plan",
  "days": [
    {
      "day_label": "Lunedi",
      "meals": [
        {
          "meal_type": "breakfast",
          "dish_name": "Yogurt con muesli",
          "description": "optional short description",
          "ingredients": ["150g yogurt greco", "30g muesli"],
          "instructions": "optional prep steps",
          "recipe_link": "optional URL if the document gave one",
          "calories": 320,
          "macros": { "protein_g": 18, "carbs_g": 40, "fat_g": 9 }
        }
      ]
    }
  ]
}
```

Rules:
- `language` is one of `it`/`es`/`en`.
- `plan_type` is `weekly_plan` or `single_recipe`.
- `day_label` should be written as it appears in the document (e.g. "Lunedi", "Lunes",
  "Monday"), or an explicit date if that's what's given.
- `meal_type` must be exactly `breakfast`, `lunch`, or `dinner` - if a document meal
  doesn't map cleanly, pick the closest one rather than inventing a new value.
- Every field except `meal_type` and `dish_name` is optional - omit fields you can't
  determine rather than guessing.
- If the extracted text doesn't actually contain a usable plan/recipe, write a failure
  response with `error` set instead of a mostly-empty `result`.

---

## Type: `scan_recipe`

Source: recipe Scan (`handlers/recipe_library.py`). Fills in whatever a saved recipe is
still missing: a recipe link per language, a translated display name per language, and
per-100g nutrition. Only fill in what's actually listed as missing - other fields are
already populated and must not be touched.

**`payload`:**

```json
{
  "recipe_id": 42,
  "name": "Pollo al limone",
  "ingredients": ["600g petto di pollo", "2 limoni", "olio extravergine"],
  "missing_links": ["es", "en"],
  "missing_names": ["en"],
  "needs_nutrition": true,
  "link_it": "https://...",
  "needs_ingredients_it": true
}
```

- `ingredients` may be `null` if none are saved yet.
- `missing_links` / `missing_names` are subsets of `["it", "es", "en"]` - only these
  language codes need a value in the response; skip the rest.
- `needs_nutrition` is `true` only if per-100g nutrition is still unset.
- `link_it` is the recipe's saved Italian link, or `null` if none is saved.
- `needs_ingredients_it` is `true` only if the recipe has an Italian link but no
  Italian ingredient list saved yet.

**Task:**
- For each language in `missing_links`: search the web for a page with the recipe for
  `name` in that language, and return its URL. Skip a language rather than guessing if
  nothing suitable turns up.
- For each language in `missing_names`: translate `name` into that language (a concise
  name as it would appear in a cookbook); if it's already in that language, return it
  unchanged, possibly with more natural spelling.
- If `needs_nutrition` is true: estimate calories and macros per 100g of the finished
  dish, using `ingredients` as a guide when available.
- If `needs_ingredients_it` is true: fetch `link_it` and extract its ingredient list in
  Italian as `{name, quantity}` pairs - `name` normalized (no quantity baked in, no
  leading bullet/dash), `quantity` as free text as it would appear in a recipe (e.g.
  `"200 g"`, `"2 uova"`, `"q.b."`). If the page has no clear ingredient list, that's
  still a success response with `ingredients_it` omitted/empty - don't guess.

**`result`:**

```json
{
  "links": { "es": "https://...", "en": "https://..." },
  "names": { "en": "Lemon Chicken" },
  "nutrition": { "calories": 165, "protein_g": 21.0, "carbs_g": 3.5, "fat_g": 7.2 },
  "ingredients_it": [
    { "name": "Petto di pollo", "quantity": "600 g" },
    { "name": "Limoni", "quantity": "2" }
  ]
}
```

- `links` and `names` are objects keyed only by the languages you actually found a
  value for (a subset of what was requested is fine - omit what you couldn't find).
- `nutrition` is `null` (or the key omitted) if `needs_nutrition` was `false`, or if you
  couldn't produce a reasonable estimate.
- `ingredients_it` is a list of `{name, quantity}` objects (Italian), included only if
  `needs_ingredients_it` was `true` and something was found - omit the key or send an
  empty list otherwise.
- If literally nothing could be filled in, that's still a success response with empty
  `links`/`names`/`ingredients_it` and `nutrition: null` - only use `error` for a
  request you couldn't process at all (e.g. `recipe_id`/`name` missing).

---

## See also

- `ai_queue/CONSUMER_PROMPT.md` - the exact prompt run by the scheduled consumer.
- `deploy/run_ai_consumer.sh`, `deploy/pieapple-ai-consumer.service`,
  `deploy/pieapple-ai-consumer.timer` - how the consumer is scheduled on the Pi.
- `ai_queue_service.py` - the bot-side request writer / response poller.
