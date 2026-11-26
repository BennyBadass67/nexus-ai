# NEXUS AI v1.0 plan (feature + quality release)
Rule: every feature gets backend tests + a headless-Chrome screenshot. Nothing ships without both. Tag only after previous Actions run finished.

Done so far (uncommitted->committed in 1.0 branch of main, not tagged): context trimming (fit_messages), SQLite WAL, tests 97.

Features (order of work):
1. Søk overalt: full-text search across conversations, memory, agents, activity (SQLite FTS5 or LIKE), Ctrl+K palette shows hits.
2. Samtaler: export to Markdown, pin, delete-all-confirm, copy answer, edit title; token/s stats kept.
3. Vedlegg i chat: text/code/markdown files (read locally) and images (described by local vision model).
4. Kunnskap (lokal dokumentsøk): index chosen folders (txt, md, code, pdf text if pdftotext absent -> skip), BM25 in pure Python, agent tool `search_knowledge`, UI page tab in Workspace.
5. Notater/oppgaver: agent tools `add_note`/`list_notes`, notes UI; reminders shown in Home.
6. Systemmonitor på Home: live CPU/RAM (Windows via ctypes, Linux /proc for tests), Ollama loaded model.
7. Sikkerhetskopi: export/import all data (zip of db) in Settings.
8. Prompt-maler: saved prompts, one click into chat.
Quality: full audit list kept in CHANGELOG-1.0.md (found/fixed).
