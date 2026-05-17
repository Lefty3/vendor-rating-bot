# Vendor Rating Bot

Anonymous vendor rating system for Discord. Members submit 1–10 scores; a live pinned embed auto-updates with tier labels.

**Tiers**
| Score | Label |
|-------|-------|
| 8–10 | 🟢 APPROVED |
| 4–7 | 🟡 USE WITH CAUTION |
| 1–3 | 🔴 DO NOT USE |

---

## Setup

### 1. Install dependencies
```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Create your bot
1. Go to https://discord.com/developers/applications and create a new application.
2. Under **Bot**, enable **Server Members Intent**.
3. Copy the bot token.

### 3. Configure environment
```bash
cp .env.example .env
# paste your token into .env
```

### 4. Invite the bot
Generate an invite URL with these scopes/permissions:
- Scopes: `bot`, `applications.commands`
- Permissions: `Send Messages`, `Embed Links`, `Manage Messages` (for pinning), `Read Message History`

### 5. Run
```bash
python bot.py
```

### 6. Configure the server
In Discord, run:
```
/setup live_channel:#vendor-ratings admin_channel:#admin-review
```

---

## Commands

| Command | Who | Description |
|---------|-----|-------------|
| `/rate <vendor>` | Anyone | Opens a private form to submit a score (1–10) + optional comment |
| `/suggest <name>` | Anyone | Suggests a new vendor for admin approval |
| `/vendors` | Anyone | Shows the current vendor ratings list |
| `/approve <name>` | Admin | Approves a pending vendor |
| `/reject <name>` | Admin | Rejects a pending vendor |
| `/pending` | Admin | Lists vendors awaiting approval |
| `/remove_rating <id>` | Admin | Removes a rating by ID |
| `/refresh` | Admin | Force-refreshes the pinned embed |
| `/setup` | Admin | Configures channels, admin role, and cooldown |

---

## Free Hosting

**Railway** (recommended)
1. Push this repo to GitHub.
2. Create a new project at https://railway.app.
3. Add a `DISCORD_TOKEN` environment variable.
4. Deploy — Railway runs `python bot.py` automatically.

**Fly.io**
1. Install the Fly CLI and run `fly launch`.
2. Set `fly secrets set DISCORD_TOKEN=your_token`.
3. Run `fly deploy`.

The SQLite database (`vendor_ratings.db`) is created automatically on first run.
For Railway/Fly you may want to attach a persistent volume so the DB survives redeploys.
