<!-- Copilot bootstrap instructions for PROJECT_MARIA -->
# Copilot Chat — Repository Bootstrap

Purpose: help Copilot Chat quickly understand and act in this repository.

Quick run commands
- Start server: `python server.py`
- Start client: `python client.py`
- Create DB tables (idempotent): `python create_tables.py`
- Run multi-client load/demo: `python multi_run.py`

High-level architecture
- `server.py`: server listener, Tkinter dashboard, authentication, session management
- `client.py`: client agent (parent/child modes), keylogger, GUI
- `db_manager.py`: MySQL wrapper (clients, keylogs)
- `encrypt.py`: AES-GCM helpers used for socket messaging
- `multi_run.py`: headless client harness for load testing

Project conventions & notes
- Message protocol: `COMMAND|ARG|ARG…` over encrypted sockets
- Keylogs are stored in `keylogs/` and mirrored to DB
- DB credentials and AES key are currently hard-coded in `constants.py` — consider rotation
- Security: passwords hashed (SHA256) without salt; AES uses fixed nonce. Treat production usage cautiously.

Files to reference first
- `create_tables.py`, `server.py`, `client.py`, `db_manager.py`, `encrypt.py`, `constants.py`, `multi_run.py`

What Copilot Chat should do first
- Link to these key files when asked about architecture or run steps.
- Prefer safe, minimal edits: avoid changing crypto/auth without review.
- When asked to harden security, propose incremental migrations (add salt/bcrypt, rotate keys, use env vars).

Example prompts
- "Show me where the DB credentials are defined and suggest safer handling." 
- "Add bcrypt password hashing and migrate existing users in `db_manager.py`."

Next recommended customizations
- Add `AGENTS.md` for area-specific instructions (UI vs. backend).
- Create `requirements.txt` listing runtime dependencies.

-- End of bootstrap
