# Dataset collection sources

## EverySpec (checked 2026-10-20)

Terms of Use (`https://everyspec.com/terms_of_use.php`), section 2: "You may not use any automated process or software program to view, download, print or otherwise use Site Content." Downloads are allowed only "in limited quantities as required to evaluate" the content. Section 3 forbids republishing or distributing any Specification. Permission requests go to `webmaster@everyspec.com`. `robots.txt` blocks nothing, but the Terms prohibit automated access regardless.

Conclusion: crawling the `/FSC-CODE/` index or downloading PDFs with a script is not allowed without written permission from the site owner. Decision: EverySpec is not used as a data source; the team reuses the ASSIST QuickSearch collection instead.

## ASSIST QuickSearch (checked 2026-10-20)

`https://quicksearch.dla.mil/qsPrivacy.aspx`: "Information presented on the ASSIST Quick Search website is considered public information and may be distributed or copied." The page does not address scraping, crawling or automated downloading, and there is no `robots.txt` (404). It says traffic is monitored to keep the service available to all users, and it prohibits unauthorized uploads or changes. Questions go to the ASSIST service desk (215-737-8000) or the feedback form.

Conclusion: the collection scripts in this folder may keep running, with the existing safeguards: one request every 1.5 s, no parallel requests, resumable runs, and a User-Agent without personal data (set `QUICKSEARCH_CONTACT` only with a non-personal address).

## Dataset build order

1. `python -m scripts.dataset.details --per-group 80 --include-standards-and-handbooks` fetches metadata (resumable, 1.5 s between requests).
2. `python -m scripts.dataset.download` downloads the public PDFs (resumable).
3. `python -m scripts.dataset.build_csv` writes `training_export/quicksearch/dataset_unlabeled.csv` (type and discipline by rule, empty area).
4. `python -m scripts.dataset.label_areas` fills the area with an LLM (Ollama by default, `--provider groq` as a stopgap) and writes `dataset.csv` with `area`, `area_stage` and `area_model`.
5. `python -m scripts.dataset.area_review sample`, fill the `human_stage` column (a person, or a reference model named with `--reviewer`), then `python -m scripts.dataset.area_review agreement`.
6. `python -m classifier.vectorize` stores the TF-IDF vectors in MongoDB; training and comparison commands are in the backend `README.md`.

## Area labeling with Ollama

The area is labeled by an LLM running in Ollama on a machine owned by the team, so the document text never leaves its infrastructure.

Environment variables read by `label_areas`:

- `OLLAMA_MODEL` (required): model name exactly as `ollama list` shows it.
- `OLLAMA_URL` (default `http://localhost:11434`).
- `OLLAMA_API_TOKEN` (optional): sent as a bearer token, for a reverse proxy in front of Ollama.

Ollama has no authentication of its own. Keep it listening on `127.0.0.1` on the VM and reach it through an SSH tunnel (`ssh -N -L 11434:127.0.0.1:11434 <user>@<vm>`) instead of opening port 11434 in the cloud firewall.

The answer is constrained to the stages in `classifier/catalog.json`, with `temperature` 0 and `num_ctx` 8192. Labels are cached in `training_export/quicksearch/area_labels.jsonl` by text, model and criteria version (`area_criteria_v<version>.md`), so a rerun only calls the model for new documents. Use `--max-chars` to send less text per document if the VM is slow.

## Groq provider

`python -m scripts.dataset.label_areas --provider groq` uses `GROQ_API_KEY` and `GROQ_MODEL` from the environment (the backend `.env` already has them) with the same criteria, temperature 0 and JSON answer. The cache key includes the model name, so Groq and Ollama labels never collide. Groq is a stopgap to unblock training; the metrics reported to the professor and the client come from an Ollama run on the team's own machine.
