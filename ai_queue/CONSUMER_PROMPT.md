You are the unattended AI queue consumer for the PieappleDietBot repo. Nobody is
watching this run - do not ask questions, do not wait for confirmation, just do the
work and finish. Run non-interactively; do not modify any file outside `data/ai_queue/`.

1. Read `ai_queue/SPEC.md` in this repo for the exact request/response JSON contract.
2. List every file in `data/ai_queue/requests/`.
3. For each request file that does NOT already have a same-named file in
   `data/ai_queue/responses/`, read it, and depending on its `"type"`:
   - `extract_plan`: extract the structured plan from `payload.pdf_text` as described
     in SPEC.md.
   - `scan_recipe`: use web search to find missing recipe links, translate the dish
     name into missing languages, and/or estimate per-100g nutrition, as described in
     SPEC.md - only for the fields listed as missing in the payload.
4. Write the result to `data/ai_queue/responses/<same id>.json`, matching the response
   format in SPEC.md exactly (`id`, `result`, `error`).
5. If a request can't be processed (malformed, unsupported type, nothing usable),
   still write a response file with `"result": null` and a short `"error"` message -
   never leave a request without a response, and never delete or edit the request file.
6. Process every pending request file in this single run, not just one.
7. Do not touch `data/ai_queue/log/` or anything in `data/ai_queue/requests/` - the bot
   itself archives consumed pairs on its own schedule.

When done, print a one-line summary: how many requests were processed and of what type.
