# masterbuilder-bot

An approval-first, local-first research + content bot for **masterbuilder.ai**.
It reads AI/construction/robotics sources daily, drafts posts in the
Masterbuilder voice, and gives you a local dashboard to review everything.

**It never posts without your approval.** It starts (and stays) in
`draft_only` mode. X posting is a dry-run stub until you explicitly ask for
the live version.

```
research/YYYY-MM-DD.json  ->  drafts/YYYY-MM-DD/*.md  ->  approved/  ->  (someday) posted/
                                                      \->  memory/rejected/
```

Draft first. Approval second. Posting last.

---

## 1. Fresh local setup (your Mac)

```bash
cd masterbuilder-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and add an API key (any ONE of these is enough — or none, and
you'll get rough template drafts instead of AI-written ones):

| You want | Set |
|---|---|
| Claude (Anthropic) | `ANTHROPIC_API_KEY=sk-ant-...` |
| OpenAI | `OPENAI_API_KEY=sk-...` |
| Local model (Ollama/LM Studio on the Mac mini) | `LLM_BASE_URL=http://localhost:11434/v1` and `LLM_MODEL=llama3.1` |

The provider is auto-detected; force one with `LLM_PROVIDER=` if you set
multiple keys.

Then:

```bash
python scripts/setup_macmini.py    # sanity check — fixes nothing, reports everything
python scripts/daily_research.py   # pull today's sources -> research/YYYY-MM-DD.json
python scripts/draft_posts.py      # research + brand voice -> drafts/YYYY-MM-DD/
python scripts/review_queue.py     # approve/reject/edit in the terminal
python scripts/run_dashboard.py    # or do all of it in the browser
```

`python scripts/run_daily.py` does research + drafts in one shot.
`python scripts/smoke_test.py` verifies the wiring and the safety rails
(safe to run anytime; it writes only to a temp folder).

## 2. Mac mini setup

```bash
ssh youruser@macmini.local
# copy the repo over (either):
git clone <your-repo-url> ~/masterbuilder-bot     # if you push it to git
# or from your Mac:  rsync -av --exclude .venv masterbuilder-bot/ macmini.local:~/masterbuilder-bot/

cd ~/masterbuilder-bot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && nano .env    # add your key(s)
python scripts/setup_macmini.py
python scripts/run_daily.py          # run the bot manually once
python scripts/run_dashboard.py      # dashboard, manually
```

Tip: the Mac mini is a great place to run a local model. Install
[Ollama](https://ollama.com), `ollama pull llama3.1`, then set
`LLM_BASE_URL=http://localhost:11434/v1` in `.env` — free drafts, no cloud.

## 3. Dashboard

```bash
source .venv/bin/activate
pip install -r requirements.txt   # first time only
python scripts/run_dashboard.py
```

Open the URL it prints (http://localhost:8501). Pages:

- **Command Center** — status cards + Run Research / Generate Drafts / Full Pipeline buttons
- **Research** — table of today's items, mark useful/maybe/ignore, regenerate drafts
- **Drafts** — edit markdown, approve → `approved/`, reject → `memory/rejected/`
- **Approved** — dry-run posting preview (never posts live in this version)
- **Settings** — edit brand voice/topics/rules + sources.yaml, toggle BOT_MODE (with confirmation), env status without secrets
- **Logs** — `memory/runs.log`, newest first, filter by category

## 4. Mac mini dashboard notes (remote access)

**Safest default:** the dashboard binds to `localhost` only. Nothing else on
your network can reach it. To use it from your Mac, tunnel over SSH:

```bash
ssh -L 8501:localhost:8501 youruser@macmini.local
# then open http://localhost:8501 on your Mac
```

**Tailscale (recommended for regular use):** install Tailscale on both
machines, then on the Mac mini run Streamlit bound to the Tailscale interface:

```bash
# find your tailscale IP first: tailscale ip -4   (looks like 100.x.y.z)
.venv/bin/python -m streamlit run dashboard/app.py \
  --server.address 100.x.y.z --server.port 8501 \
  --browser.gatherUsageStats false
```

Only devices on your tailnet can reach that address.

**Do NOT expose this dashboard to the public internet.** It has no
authentication and it can edit your config and (someday) trigger posting.
Localhost or Tailscale only.

## 5. Scheduling (launchd, macOS)

Run the daily pipeline at 6:00 AM Eastern. Save this as
`~/Library/LaunchAgents/ai.masterbuilder.bot.plist` **on the Mac mini**
(adjust the two paths for your username):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>ai.masterbuilder.bot</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/YOURUSER/masterbuilder-bot/.venv/bin/python</string>
    <string>/Users/YOURUSER/masterbuilder-bot/scripts/run_daily.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/Users/YOURUSER/masterbuilder-bot</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>6</integer>
    <key>Minute</key><integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>/Users/YOURUSER/masterbuilder-bot/memory/launchd.out.log</string>
  <key>StandardErrorPath</key>
  <string>/Users/YOURUSER/masterbuilder-bot/memory/launchd.err.log</string>
</dict>
</plist>
```

`StartCalendarInterval` uses the machine's local clock — make sure the Mac
mini's timezone is set to Eastern (System Settings → General → Date & Time),
or adjust the hour.

```bash
launchctl load ~/Library/LaunchAgents/ai.masterbuilder.bot.plist    # enable
launchctl start ai.masterbuilder.bot                                # test now
launchctl unload ~/Library/LaunchAgents/ai.masterbuilder.bot.plist  # disable
```

**Where logs go:** the bot's own log is `memory/runs.log` (also visible on the
dashboard Logs page). launchd's stdout/stderr go to `memory/launchd.out.log`
and `memory/launchd.err.log`.

## 6. Safe posting upgrade (later)

Keep `BOT_MODE=draft_only` until the review queue feels good — until the
drafts consistently sound like you and the sources check out.

**How approved posting will work when you're ready:**

1. You flip `BOT_MODE=approved_posting` (Settings page, with a confirmation
   checkbox — or edit `.env`).
2. Only files in `approved/` can be posted. `drafts/` is hard-blocked by
   `masterbuilder_bot/safety.py`, along with unsourced content, banned
   phrases, and more than 5 posts/day (1 per run).
3. `scripts/post_x.py --file approved/...` runs every check and does a
   dry-run. Posted items move to `posted/YYYY-MM-DD/`.

**Keys you'll need later** (X developer account, not needed now):
`X_API_KEY`, `X_API_SECRET`, `X_ACCESS_TOKEN`, `X_ACCESS_TOKEN_SECRET` — the
slots already exist in `.env.example`.

**Live posting stays a stub** — `posting.post_to_x_live()` raises
`NotImplementedError` on purpose. It gets implemented only when you
explicitly ask for it.

## Project layout

```
brand/               voice.md, rules.md, topics.md — the Masterbuilder voice
config/sources.yaml  what the bot reads every day (edit freely)
research/            YYYY-MM-DD.json research dumps
drafts/              YYYY-MM-DD/ draft markdown (frontmatter: scores + sources)
approved/            what you've blessed
posted/              what's actually been posted (empty until live posting exists)
memory/runs.log      every run, every error
memory/rejected/     rejected drafts (kept, not deleted)
masterbuilder_bot/   the library: research, drafting, review, posting, safety, llm
scripts/             thin CLI wrappers around the library
dashboard/           Masterbuilder Command Center (Streamlit, localhost-only)
```

## Safety rails (masterbuilder_bot/safety.py)

No posting unless `BOT_MODE=approved_posting` · no posting from `drafts/` ·
no mass posting (1/run, 5/day) · no DMs (no DM code exists) · no file ops
outside the repo's data folders · no unsourced claims · no impersonating a
human · no engagement farming / ragebait phrases · secrets redacted from all
logs · secrets never displayed in the dashboard.
