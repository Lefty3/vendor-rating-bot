import aiosqlite

import os
DB_PATH = os.environ.get("DB_PATH", "vendor_ratings.db")


class Database:
    def __init__(self):
        self.path = DB_PATH

    async def init(self):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS vendors (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    name_lower TEXT NOT NULL,
                    guild_id INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    suggested_by INTEGER NOT NULL,
                    suggested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    approved_by INTEGER,
                    approved_at TIMESTAMP,
                    UNIQUE(name_lower, guild_id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS ratings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    vendor_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    guild_id INTEGER NOT NULL,
                    score INTEGER NOT NULL,
                    comment TEXT,
                    submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (vendor_id) REFERENCES vendors(id) ON DELETE CASCADE
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS cooldowns (
                    user_id INTEGER NOT NULL,
                    vendor_id INTEGER NOT NULL,
                    last_rating TIMESTAMP NOT NULL,
                    PRIMARY KEY (user_id, vendor_id)
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS config (
                    guild_id INTEGER NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT,
                    PRIMARY KEY (guild_id, key)
                )
            """)
            await db.commit()

    # ── Config ────────────────────────────────────────────────────────────────

    async def get_config(self, guild_id: int, key: str) -> str | None:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                "SELECT value FROM config WHERE guild_id = ? AND key = ?",
                (guild_id, key),
            ) as cur:
                row = await cur.fetchone()
                return row[0] if row else None

    async def set_config(self, guild_id: int, key: str, value: str):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR REPLACE INTO config (guild_id, key, value) VALUES (?, ?, ?)",
                (guild_id, key, value),
            )
            await db.commit()

    # ── Vendors ───────────────────────────────────────────────────────────────

    async def suggest_vendor(self, name: str, suggested_by: int, guild_id: int) -> bool:
        """Returns False if vendor name already exists in this guild."""
        async with aiosqlite.connect(self.path) as db:
            try:
                await db.execute(
                    "INSERT INTO vendors (name, name_lower, guild_id, suggested_by) VALUES (?, ?, ?, ?)",
                    (name.strip(), name.strip().lower(), guild_id, suggested_by),
                )
                await db.commit()
                return True
            except aiosqlite.IntegrityError:
                return False

    async def get_vendor_by_id(self, vendor_id: int):
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM vendors WHERE id = ?", (vendor_id,)
            ) as cur:
                return await cur.fetchone()

    async def get_vendor_by_name(self, name: str, guild_id: int):
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM vendors WHERE name_lower = ? AND guild_id = ?",
                (name.strip().lower(), guild_id),
            ) as cur:
                return await cur.fetchone()

    async def get_approved_vendors(self, guild_id: int) -> list:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM vendors WHERE status = 'approved' AND guild_id = ? ORDER BY name ASC",
                (guild_id,),
            ) as cur:
                return await cur.fetchall()

    async def get_pending_vendors(self, guild_id: int) -> list:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM vendors WHERE status = 'pending' AND guild_id = ? ORDER BY suggested_at ASC",
                (guild_id,),
            ) as cur:
                return await cur.fetchall()

    async def update_vendor_status(self, vendor_id: int, status: str, admin_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                """UPDATE vendors
                   SET status = ?, approved_by = ?, approved_at = CURRENT_TIMESTAMP
                   WHERE id = ?""",
                (status, admin_id, vendor_id),
            )
            await db.commit()

    # ── Ratings ───────────────────────────────────────────────────────────────

    async def add_rating(
        self,
        vendor_id: int,
        user_id: int,
        guild_id: int,
        score: int,
        comment: str | None,
        cooldown_days: int,
    ):
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT INTO ratings (vendor_id, user_id, guild_id, score, comment) VALUES (?, ?, ?, ?, ?)",
                (vendor_id, user_id, guild_id, score, comment),
            )
            if cooldown_days > 0:
                await db.execute(
                    "INSERT OR REPLACE INTO cooldowns (user_id, vendor_id, last_rating) VALUES (?, ?, CURRENT_TIMESTAMP)",
                    (user_id, vendor_id),
                )
            await db.commit()

    async def get_rating(self, rating_id: int, guild_id: int):
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM ratings WHERE id = ? AND guild_id = ?",
                (rating_id, guild_id),
            ) as cur:
                return await cur.fetchone()

    async def delete_rating(self, rating_id: int):
        async with aiosqlite.connect(self.path) as db:
            await db.execute("DELETE FROM ratings WHERE id = ?", (rating_id,))
            await db.commit()

    async def on_cooldown(self, user_id: int, vendor_id: int, cooldown_days: int) -> bool:
        if cooldown_days <= 0:
            return False
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                """SELECT 1 FROM cooldowns
                   WHERE user_id = ? AND vendor_id = ?
                   AND datetime(last_rating, '+' || ? || ' days') > datetime('now')""",
                (user_id, vendor_id, cooldown_days),
            ) as cur:
                return await cur.fetchone() is not None

    async def cooldown_hours_remaining(self, user_id: int, vendor_id: int, cooldown_days: int) -> int:
        async with aiosqlite.connect(self.path) as db:
            async with db.execute(
                """SELECT CAST(
                       (julianday(datetime(last_rating, '+' || ? || ' days')) - julianday('now')) * 24
                   AS INTEGER)
                   FROM cooldowns WHERE user_id = ? AND vendor_id = ?""",
                (cooldown_days, user_id, vendor_id),
            ) as cur:
                row = await cur.fetchone()
                return max(0, row[0]) if row and row[0] else 0

    async def get_vendor_reviews(self, vendor_id: int, guild_id: int) -> list:
        """Returns all ratings for a vendor, newest first."""
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT id, score, comment, submitted_at
                   FROM ratings
                   WHERE vendor_id = ? AND guild_id = ?
                   ORDER BY submitted_at DESC""",
                (vendor_id, guild_id),
            ) as cur:
                return await cur.fetchall()

    async def get_vendor_stats(self, guild_id: int) -> list:
        """Returns (id, name, avg_score, rating_count) for all approved vendors."""
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT v.id, v.name,
                          COALESCE(AVG(r.score), 0) AS avg_score,
                          COUNT(r.id) AS rating_count
                   FROM vendors v
                   LEFT JOIN ratings r ON v.id = r.vendor_id
                   WHERE v.status = 'approved' AND v.guild_id = ?
                   GROUP BY v.id
                   ORDER BY avg_score DESC, v.name ASC""",
                (guild_id,),
            ) as cur:
                return await cur.fetchall()
