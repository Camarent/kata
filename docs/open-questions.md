# Open questions

1. **Embedding model.** Starting point: a small CPU model plus keyword retrieval. Revisit a
   multilingual model with real non-English questions; re-run the retrieval comparison on
   Postgres full-text search before relying on earlier numbers.
2. **VPN product and reverse proxy** for remote access.
3. **Local event queue** format and retry rules for terminal and editor events.
4. **Backup** of the database to a second disk.
5. **Cloud provider choice**, by tests on the real tasks (tagging, explanation, summary) and
   the provider research: data terms, price, language quality, spend caps.
6. **Platform terms.** Before using a provider or reading a course platform, check the
   platform's own terms on external tools and AI help.
7. **Terminal capture inside SSH.** A spike must confirm it works.
8. **Detection of graded pages**, used to stay silent on tests and exams.
9. **Coverage and quality gates** to add (see [`backlog.md`](backlog.md)).

Critique findings and cut-or-defer items will be added under `design/` in a follow-up.
