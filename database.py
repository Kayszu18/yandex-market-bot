import sqlite3
import datetime
import json
import logging
import threading
from pathlib import Path
from contextlib import contextmanager
from typing import List, Dict, Optional, Any, Iterator
from config import Config

logger = logging.getLogger(__name__)

# Ma'lumotlar bazasi yo'lini config.py dan olish
DB_FILE = Path(Config.database.DB_PATH)
DB_FILE.parent.mkdir(parents=True, exist_ok=True)

# Thread-safe connection lock
_connection_lock = threading.Lock()

@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """
    Provides a context-managed database connection with timeout and retry.
    Yields:
        SQLite connection object.
    """
    import time
    max_retries = 3
    retry_delay = 0.1
    
    with _connection_lock:  # Thread-safe connection
        for attempt in range(max_retries):
            try:
                conn = sqlite3.connect(
                    DB_FILE, 
                    isolation_level=None,  # Autocommit mode
                    timeout=30.0,  # 30 second timeout
                    check_same_thread=False
                )
                conn.row_factory = sqlite3.Row
                # WAL mode ni yoqish (concurrent read/write uchun)
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute("PRAGMA cache_size=1000")
                conn.execute("PRAGMA temp_store=MEMORY")
                conn.execute("PRAGMA busy_timeout=30000")  # 30 second busy timeout
                yield conn
                break
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    logger.warning(f"Database locked, retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                    continue
                else:
                    logger.error(f"Database error: {e}")
                    raise
            except sqlite3.Error as e:
                logger.error(f"Database error: {e}")
                raise
            finally:
                if 'conn' in locals():
                    conn.close()

def init_db() -> None:
    """
    Initializes the database with required tables and indexes.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        
        # Database optimization settings
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.execute("PRAGMA cache_size=1000")
        cur.execute("PRAGMA temp_store=MEMORY")
        cur.execute("PRAGMA busy_timeout=30000")

        # Users table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                phone TEXT,
                referred_by INTEGER,
                balance REAL DEFAULT 0.0,
                is_blocked INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (referred_by) REFERENCES users(user_id)
            )
        """)

        # Orders table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                product_url TEXT,
                photo_id TEXT,
                status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        # Withdraw requests table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS withdraw_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                wallet TEXT NOT NULL,
                withdraw_type TEXT NOT NULL CHECK (withdraw_type IN ('card', 'phone')),
                status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)

        # Referrals table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referred_id INTEGER NOT NULL,
                bonus REAL DEFAULT 0.0,
                level INTEGER DEFAULT 1 CHECK (level >= 1),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (referrer_id) REFERENCES users(user_id),
                FOREIGN KEY (referred_id) REFERENCES users(user_id),
                UNIQUE (referrer_id, referred_id)
            )
        """)

        # Settings table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        # Support messages table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS support_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                support_id TEXT UNIQUE NOT NULL,
                user_id INTEGER NOT NULL,
                text TEXT,
                file_id TEXT,
                file_type TEXT CHECK (file_type IN ('photo', 'document') OR file_type IS NULL),
                reply_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                replied_at TIMESTAMP
            )
        """)

        # Exports table (excel_export.py uchun)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS exports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_id INTEGER NOT NULL,
                export_type TEXT NOT NULL CHECK (export_type IN ('orders', 'withdraws', 'referrals')),
                file_path TEXT NOT NULL,
                file_format TEXT NOT NULL CHECK (file_format IN ('xlsx', 'csv', 'json')),
                sent_messages INTEGER DEFAULT 0,
                failed_messages INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Indexes for performance
        cur.execute("CREATE INDEX IF NOT EXISTS idx_user_id ON users(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_order_user_id ON orders(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_withdraw_user_id ON withdraw_requests(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_referral_referrer_id ON referrals(referrer_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_referral_referred_id ON referrals(referred_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_support_user_id ON support_messages(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_support_support_id ON support_messages(support_id)")

        conn.commit()
        logger.info("Database initialized successfully")

def run_migrations() -> None:
    """
    Runs database migrations to ensure schema is up-to-date.
    Currently a placeholder for future migrations (e.g., using Alembic).
    """
    logger.info("Running database migrations")
    init_db()  # Hozircha faqat init_db chaqiriladi
    logger.info("Database migrations completed")

# -------- SETTINGS --------
def set_setting(key: str, value: Any) -> None:
    """
    Sets or updates a setting in the settings table.
    Args:
        key: Setting key.
        value: Setting value (auto-converted to JSON string if not str).
    """
    value = json.dumps(value) if not isinstance(value, str) else value
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (key, value))
        conn.commit()
        logger.debug(f"Setting updated: {key} = {value}")

def update_setting(key: str, value: str) -> None:
    """Alias for set_setting (for admin.py compatibility)."""
    set_setting(key, value)

def get_setting(key: str, default: Any = None) -> Any:
    """
    Retrieves a setting from the settings table.
    Args:
        key: Setting key.
        default: Default value if key not found.
    Returns:
        Setting value (parsed from JSON if possible) or default.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cur.fetchone()
        if row:
            try:
                return json.loads(row[0])
            except json.JSONDecodeError:
                return row[0]
        return default

# -------- TUTORIAL STEPS --------
def get_tutorial_steps() -> List[Dict]:
    """
    Retrieves tutorial steps from settings.
    Returns:
        List of tutorial steps (parsed from JSON).
    """
    steps_json = get_setting("tutorial_steps", "[]")
    try:
        return json.loads(steps_json)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse tutorial_steps: {e}")
        return []

# -------- HELP VIDEO FILE ID --------
def get_help_video_file_id() -> str:
    """
    Retrieves the help video file ID from settings.
    Returns:
        File ID or empty string if not set.
    """
    return get_setting("help_video_file_id", "")

# -------- USERS --------
def upsert_user(user_id: int, username: Optional[str] = None, referrer_id: Optional[int] = None) -> None:
    """
    Inserts or updates a user in the users table.
    Args:
        user_id: Telegram user ID.
        username: Telegram username (optional).
        referrer_id: Referrer user ID (optional).
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("BEGIN EXCLUSIVE")
        try:
            cur.execute("""
                INSERT INTO users (user_id, username, referred_by)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username
            """, (user_id, username, referrer_id))
            if referrer_id is not None:
                cur.execute("""
                    UPDATE users
                    SET referred_by = ?
                    WHERE user_id = ? AND (referred_by IS NULL OR referred_by = 0)
                """, (referrer_id, user_id))
            conn.commit()
            logger.debug(f"User upserted: {user_id}, username={username}, referrer_id={referrer_id}")
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Failed to upsert user {user_id}: {e}")
            raise

def user_exists(user_id: int) -> bool:
    """
    Checks if a user exists in the database.
    Args:
        user_id: Telegram user ID.
    Returns:
        True if user exists, False otherwise.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
        return cur.fetchone() is not None

def get_user(user_id: int) -> Optional[Dict]:
    """
    Retrieves a user by ID.
    Args:
        user_id: Telegram user ID.
    Returns:
        User dictionary or None if not found.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cur.fetchone()
        return dict(user) if user else None

def get_user_by_id(user_id: int) -> Optional[Dict]:
    """Alias for get_user (for compatibility)."""
    return get_user(user_id)

def get_user_balance(user_id: int) -> float:
    """
    Retrieves a user's balance.
    Args:
        user_id: Telegram user ID.
    Returns:
        User's balance in so'm.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        return float(row[0]) if row else 0.0

def update_user_balance(user_id: int, delta: float) -> None:
    """
    Updates a user's balance with transaction safety.
    Args:
        user_id: Telegram user ID.
        delta: Amount to add (positive) or subtract (negative).
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("BEGIN EXCLUSIVE")
        try:
            # Joriy balansni olish - bir xil connection ichida
            cur.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
            balance_row = cur.fetchone()
            if not balance_row:
                raise ValueError(f"User {user_id} not found")
            
            current = float(balance_row[0])
            new_balance = max(0.0, current + delta)  # Balans salbiy bo'lmasligi uchun
            cur.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, user_id))
            conn.commit()
            logger.debug(f"Balance updated for user {user_id}: {current} -> {new_balance}")
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Failed to update balance for user {user_id}: {e}")
            raise

def save_phone(user_id: int, phone: str) -> None:
    """
    Saves a user's phone number.
    Args:
        user_id: Telegram user ID.
        phone: Phone number to save.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET phone = ? WHERE user_id = ?", (phone, user_id))
        conn.commit()
        logger.debug(f"Phone number saved for user {user_id}: {phone}")

def block_user(user_id: int) -> None:
    """
    Blocks a user.
    Args:
        user_id: Telegram user ID.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET is_blocked = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        logger.debug(f"User {user_id} blocked")

def unblock_user(user_id: int) -> None:
    """
    Unblocks a user.
    Args:
        user_id: Telegram user ID.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET is_blocked = 0 WHERE user_id = ?", (user_id,))
        conn.commit()
        logger.debug(f"User {user_id} unblocked")

def is_user_blocked(user_id: int) -> bool:
    """
    Checks if a user is blocked.
    Args:
        user_id: Telegram user ID.
    Returns:
        True if user is blocked, False otherwise.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT is_blocked FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
        return bool(row and row[0] == 1)

def get_or_create_user(user_id: int, username: Optional[str] = None, referrer_id: Optional[int] = None) -> Dict:
    """
    Gets or creates a user in the database.
    Args:
        user_id: Telegram user ID.
        username: Telegram username (optional).
        referrer_id: Referrer user ID (optional).
    Returns:
        User dictionary.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cur.fetchone()
        if user:
            return dict(user)
        cur.execute("INSERT INTO users (user_id, username, referred_by) VALUES (?, ?, ?)", (user_id, username, referrer_id))
        conn.commit()
        cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cur.fetchone()
        logger.debug(f"User created: {user_id}, username={username}, referrer_id={referrer_id}")
        return dict(user)

# -------- ORDERS --------
def create_order(user_id: int, product_url: str, photo_id: str) -> int:
    """
    Creates a new order.
    Args:
        user_id: Telegram user ID.
        product_url: Product URL.
        photo_id: Screenshot file ID.
    Returns:
        Created order ID.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO orders (user_id, product_url, photo_id) VALUES (?, ?, ?)",
            (user_id, product_url, photo_id)
        )
        conn.commit()
        order_id = cur.lastrowid
        logger.debug(f"Order created: id={order_id}, user_id={user_id}")
        return order_id

def get_user_orders(user_id: int) -> List[Dict]:
    """
    Retrieves all orders for a user.
    Args:
        user_id: Telegram user ID.
    Returns:
        List of order dictionaries.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
        rows = cur.fetchall()
        return [dict(r) for r in rows]

def get_all_orders(start_date: Optional[datetime.date] = None, end_date: Optional[datetime.date] = None, user_id: Optional[int] = None) -> List[Dict]:
    """
    Retrieves all orders with optional filters.
    Args:
        start_date: Filter orders after this date (optional).
        end_date: Filter orders before this date (optional).
        user_id: Filter orders by user ID (optional).
    Returns:
        List of order dictionaries.
    """
    query = """
        SELECT o.*, u.username
        FROM orders o
        LEFT JOIN users u ON o.user_id = u.user_id
        WHERE 1=1
    """
    params = []
    if user_id:
        query += " AND o.user_id = ?"
        params.append(user_id)
    if start_date:
        query += " AND DATE(o.created_at) >= ?"
        params.append(start_date.strftime("%Y-%m-%d"))
    if end_date:
        query += " AND DATE(o.created_at) <= ?"
        params.append(end_date.strftime("%Y-%m-%d"))
    query += " ORDER BY o.created_at DESC"

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall()
        return [dict(r) for r in rows]

def cancel_order(user_id: int, order_id: int) -> None:
    """
    Cancels an order.
    Args:
        user_id: Telegram user ID.
        order_id: Order ID to cancel.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE orders SET status = 'rejected' WHERE id = ? AND user_id = ?", (order_id, user_id))
        conn.commit()
        logger.debug(f"Order {order_id} cancelled for user {user_id}")

def update_order_status(order_id: int, status: str) -> None:
    """
    Updates an order's status.
    Args:
        order_id: Order ID to update.
        status: New status ('pending', 'approved', 'rejected').
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
        conn.commit()
        logger.debug(f"Order {order_id} status updated to {status}")

def add_user_balance(user_id: int, amount: float) -> None:
    """
    Adds balance to user account.
    Args:
        user_id: Telegram user ID.
        amount: Amount to add.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        conn.commit()
        logger.debug(f"Added {amount} to user {user_id} balance")

def get_pending_withdraw_requests() -> list:
    """
    Gets all pending withdraw requests.
    Returns:
        List of pending withdraw requests.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT wr.*, u.username 
            FROM withdraw_requests wr 
            LEFT JOIN users u ON wr.user_id = u.user_id 
            WHERE wr.status = 'pending' 
            ORDER BY wr.created_at DESC
        """)
        rows = cur.fetchall()
        return [dict(r) for r in rows]

def update_withdraw_request_status(request_id: int, status: str) -> None:
    """
    Updates withdraw request status.
    Args:
        request_id: Withdraw request ID.
        status: New status ('pending', 'approved', 'rejected').
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE withdraw_requests SET status = ? WHERE id = ?", (status, request_id))
        conn.commit()
        logger.debug(f"Withdraw request {request_id} status updated to {status}")

def reject_withdraw_request_and_refund(request_id: int) -> None:
    """
    Rejects a withdraw request and refunds the amount to user balance.
    Args:
        request_id: Withdraw request ID.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("BEGIN EXCLUSIVE")
        try:
            # Withdraw request ma'lumotlarini olish
            cur.execute("SELECT user_id, amount FROM withdraw_requests WHERE id = ?", (request_id,))
            req_row = cur.fetchone()
            if not req_row:
                raise ValueError(f"Withdraw request {request_id} not found")
            
            user_id = req_row[0]
            amount = float(req_row[1])
            
            # Status ni yangilash
            cur.execute("UPDATE withdraw_requests SET status = 'rejected' WHERE id = ?", (request_id,))
            
            # Balansni qaytarish
            cur.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
            balance_row = cur.fetchone()
            if not balance_row:
                raise ValueError(f"User {user_id} not found")
            
            current_balance = float(balance_row[0])
            new_balance = current_balance + amount
            cur.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, user_id))
            
            conn.commit()
            logger.debug(f"Withdraw request {request_id} rejected and {amount} refunded to user {user_id}, balance: {current_balance} -> {new_balance}")
        except (sqlite3.Error, ValueError) as e:
            conn.rollback()
            logger.error(f"Failed to reject withdraw request {request_id}: {e}")
            raise

# -------- WITHDRAW REQUESTS --------
def create_withdraw_request(user_id: int, amount: float, wallet: str, withdraw_type: str = "card") -> int:
    """
    Creates a new withdraw request.
    Args:
        user_id: Telegram user ID.
        amount: Withdrawal amount.
        wallet: Wallet address or payment details.
        withdraw_type: Withdrawal type ('card', 'phone').
    Returns:
        Created withdraw request ID.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("BEGIN EXCLUSIVE")
        try:
            # Balansni tekshirish - bir xil connection ichida
            cur.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
            balance_row = cur.fetchone()
            if not balance_row:
                raise ValueError(f"User {user_id} not found")
            
            current_balance = float(balance_row[0])
            if current_balance < amount:
                raise ValueError(f"Insufficient balance for user {user_id}: {current_balance} < {amount}")
            
            # Withdraw request yaratish
            cur.execute(
                "INSERT INTO withdraw_requests (user_id, amount, wallet, withdraw_type) VALUES (?, ?, ?, ?)",
                (user_id, amount, wallet, withdraw_type)
            )
            withdraw_id = cur.lastrowid
            
            # Balansni yangilash - bir xil connection ichida
            new_balance = max(0.0, current_balance - amount)
            cur.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, user_id))
            
            conn.commit()
            logger.debug(f"Withdraw request created: id={withdraw_id}, user_id={user_id}, amount={amount}, type={withdraw_type}, balance: {current_balance} -> {new_balance}")
            return withdraw_id
        except (sqlite3.Error, ValueError) as e:
            conn.rollback()
            logger.error(f"Failed to create withdraw request for user {user_id}: {e}")
            raise

def get_pending_withdraws() -> List[Dict]:
    """
    Retrieves all pending withdraw requests.
    Returns:
        List of withdraw request dictionaries.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM withdraw_requests WHERE status = 'pending'")
        rows = cur.fetchall()
        return [dict(r) for r in rows]

def get_all_withdraws(start_date: Optional[datetime.date] = None, end_date: Optional[datetime.date] = None) -> List[Dict]:
    """
    Retrieves all withdraw requests with optional date filters.
    Args:
        start_date: Filter withdraws after this date (optional).
        end_date: Filter withdraws before this date (optional).
    Returns:
        List of withdraw request dictionaries.
    """
    query = """
        SELECT w.*, u.username, u.phone
        FROM withdraw_requests w
        LEFT JOIN users u ON w.user_id = u.user_id
        WHERE 1=1
    """
    params = []
    if start_date:
        query += " AND DATE(w.created_at) >= ?"
        params.append(start_date.strftime("%Y-%m-%d"))
    if end_date:
        query += " AND DATE(w.created_at) <= ?"
        params.append(end_date.strftime("%Y-%m-%d"))
    query += " ORDER BY w.created_at DESC"

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall()
        return [dict(r) for r in rows]

def set_withdraw_status(withdraw_id: int, status: str) -> None:
    """
    Updates the status of a withdraw request.
    Args:
        withdraw_id: Withdraw request ID.
        status: New status ('pending', 'approved', 'rejected').
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("BEGIN EXCLUSIVE")
        try:
            cur.execute("SELECT user_id, amount FROM withdraw_requests WHERE id = ?", (withdraw_id,))
            row = cur.fetchone()
            if row and status == "rejected":
                update_user_balance(row["user_id"], row["amount"])  # Balansni qaytarish
            cur.execute("UPDATE withdraw_requests SET status = ? WHERE id = ?", (status, withdraw_id))
            conn.commit()
            logger.debug(f"Withdraw request {withdraw_id} status updated to {status}")
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Failed to update withdraw status for {withdraw_id}: {e}")
            raise

def get_user_withdraw_history(user_id: int) -> List[Dict]:
    """
    Retrieves withdraw history for a specific user.
    Args:
        user_id: Telegram user ID.
    Returns:
        List of withdraw request dictionaries ordered by creation date descending.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT *
            FROM withdraw_requests
            WHERE user_id = ?
            ORDER BY created_at DESC
            """,
            (user_id,)
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]

# -------- REFERRALS --------
def add_referral(referrer_id: int, referred_id: int, bonus: float = 0.0, level: int = 1) -> None:
    """
    Adds a referral relationship.
    Args:
        referrer_id: Referrer's user ID.
        referred_id: Referred user's ID.
        bonus: Referral bonus amount.
        level: Referral level (default 1).
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("BEGIN EXCLUSIVE")
        try:
            cur.execute("""
                INSERT OR IGNORE INTO referrals (referrer_id, referred_id, bonus, level)
                VALUES (?, ?, ?, ?)
            """, (referrer_id, referred_id, bonus, level))
            if bonus > 0:
                update_user_balance(referrer_id, bonus)
            conn.commit()
            logger.debug(f"Referral added: referrer_id={referrer_id}, referred_id={referred_id}, bonus={bonus}, level={level}")
        except sqlite3.Error as e:
            conn.rollback()
            logger.error(f"Failed to add referral for {referrer_id} -> {referred_id}: {e}")
            raise

def get_user_referrals(user_id: int) -> List[Dict]:
    """
    Retrieves all referrals for a user.
    Args:
        user_id: Referrer's user ID.
    Returns:
        List of referral dictionaries.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM referrals WHERE referrer_id = ? ORDER BY created_at DESC", (user_id,))
        rows = cur.fetchall()
        return [dict(r) for r in rows]

def get_all_referrals(start_date: Optional[datetime.date] = None, end_date: Optional[datetime.date] = None) -> List[Dict]:
    """
    Retrieves all referrals with optional date filters.
    Args:
        start_date: Filter referrals after this date (optional).
        end_date: Filter referrals before this date (optional).
    Returns:
        List of referral dictionaries.
    """
    query = """
        SELECT r.*, u1.username AS referrer_username, u2.username AS referred_username
        FROM referrals r
        LEFT JOIN users u1 ON r.referrer_id = u1.user_id
        LEFT JOIN users u2 ON r.referred_id = u2.user_id
        WHERE 1=1
    """
    params = []
    if start_date:
        query += " AND DATE(r.created_at) >= ?"
        params.append(start_date.strftime("%Y-%m-%d"))
    if end_date:
        query += " AND DATE(r.created_at) <= ?"
        params.append(end_date.strftime("%Y-%m-%d"))
    query += " ORDER BY r.created_at DESC"

    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall()
        return [dict(r) for r in rows]

def get_referrals_count(user_id: int) -> int:
    """
    Counts the number of referrals for a user.
    Args:
        user_id: Referrer's user ID.
    Returns:
        Number of referrals.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
        row = cur.fetchone()
        return row[0] if row else 0

# -------- EXPORTS --------
def save_export(admin_id: int, export_type: str, file_path: str, file_format: str) -> int:
    """
    Saves export metadata to the exports table.
    Args:
        admin_id: Admin's user ID.
        export_type: Type of export ('orders', 'withdraws', 'referrals').
        file_path: Path to the exported file.
        file_format: File format ('xlsx', 'csv', 'json').
    Returns:
        Export ID.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO exports (admin_id, export_type, file_path, file_format)
            VALUES (?, ?, ?, ?)
        """, (admin_id, export_type, file_path, file_format))
        conn.commit()
        export_id = cur.lastrowid
        logger.debug(f"Export saved: id={export_id}, admin_id={admin_id}, type={export_type}")
        return export_id

def update_export_message_stats(export_id: int, sent: int, failed: int) -> None:
    """
    Updates message sending statistics in the exports table.
    Args:
        export_id: Export ID.
        sent: Number of successfully sent messages.
        failed: Number of failed messages.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE exports
            SET sent_messages = sent_messages + ?, failed_messages = failed_messages + ?
            WHERE id = ?
        """, (sent, failed, export_id))
        conn.commit()
        logger.debug(f"Export {export_id} message stats updated: sent={sent}, failed={failed}")

# -------- ADMINS --------
def is_admin(user_id: int) -> bool:
    """
    Checks if a user is an admin.
    Args:
        user_id: Telegram user ID.
    Returns:
        True if user is an admin, False otherwise.
    """
    admin_ids = get_setting("admin_ids")
    if admin_ids:
        try:
            return user_id in [int(a) for a in admin_ids.split(",") if a.strip()]
        except ValueError as e:
            logger.error(f"Failed to parse admin_ids from settings: {e}")
    return user_id in Config.admin.ADMIN_IDS

def get_admin_list() -> List[int]:
    """
    Retrieves the list of admin user IDs from settings or config.
    Returns:
        List of admin user IDs.
    """
    admin_ids = get_setting("admin_ids")
    if admin_ids:
        try:
            return [int(a) for a in admin_ids.split(",") if a.strip()]
        except ValueError as e:
            logger.error(f"Failed to parse admin_ids from settings: {e}")
    return Config.admin.ADMIN_IDS

# -------- STATS --------
def get_stats() -> Dict[str, Any]:
    """
    Retrieves general statistics for the bot.
    Returns:
        Dictionary with statistics.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM users")
        total_users = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users WHERE is_blocked = 1")
        blocked_users = cur.fetchone()[0]
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        cur.execute("SELECT COUNT(*) FROM orders WHERE DATE(created_at) = ?", (today,))
        today_orders = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM withdraw_requests WHERE status = 'pending'")
        pending_withdraws = cur.fetchone()[0]
        cur.execute("SELECT SUM(bonus) FROM referrals")
        total_referral_bonus = cur.fetchone()[0] or 0.0
        return {
            "total_users": total_users,
            "blocked_users": blocked_users,
            "today_orders": today_orders,
            "pending_withdraws": pending_withdraws,
            "total_referral_bonus": float(total_referral_bonus)
        }

# -------- SUPPORT --------
def insert_support_message(user_id: int, support_id: str, text: str, file_id: Optional[str], file_type: Optional[str]) -> None:
    """
    Inserts a support message initiated by a user.
    Args:
        user_id: Telegram user ID.
        support_id: External support conversation ID for correlation.
        text: Message text.
        file_id: Optional file id if any.
        file_type: Optional file type ('photo'|'document').
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO support_messages (support_id, user_id, text, file_id, file_type)
            VALUES (?, ?, ?, ?, ?)
            """,
            (support_id, user_id, text, file_id, file_type)
        )
        conn.commit()
        logger.debug(f"Support message saved: support_id={support_id}, user_id={user_id}")

def update_support_reply(support_id: str, reply_text: str) -> None:
    """
    Updates support message with admin reply.
    Args:
        support_id: Support conversation ID.
        reply_text: Admin reply text.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE support_messages
            SET reply_text = ?, replied_at = CURRENT_TIMESTAMP
            WHERE support_id = ?
            """,
            (reply_text, support_id)
        )
        conn.commit()
        logger.debug(f"Support reply updated: support_id={support_id}")

def get_support_message(support_id: str) -> Optional[Dict]:
    """
    Retrieves a support message by its support_id.
    Args:
        support_id: Support conversation ID.
    Returns:
        Support message dict or None.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM support_messages WHERE support_id = ?",
            (support_id,)
        )
        row = cur.fetchone()
        return dict(row) if row else None

def get_user_support_history(user_id: int) -> List[Dict]:
    """
    Retrieves support history for a specific user.
    Args:
        user_id: Telegram user ID.
    Returns:
        List of support message dictionaries ordered by creation date descending.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT *
            FROM support_messages
            WHERE user_id = ?
            ORDER BY created_at DESC
            """,
            (user_id,)
        )
        rows = cur.fetchall()
        return [dict(r) for r in rows]

# -------- GET ALL USERS --------
def get_all_users() -> List[int]:
    """
    Retrieves all user IDs.
    Returns:
        List of user IDs.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM users WHERE is_blocked = 0")
        rows = cur.fetchall()
        return [r[0] for r in rows]

def get_all_users_detailed() -> List[Dict]:
    """
    Retrieves all users with detailed information.
    Returns:
        List of user dictionaries with full information.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT user_id, username, phone, referred_by, balance, is_blocked, created_at
            FROM users 
            ORDER BY created_at DESC
        """)
        rows = cur.fetchall()
        return [dict(row) for row in rows]

def get_users_by_date_range(start_date: Optional[datetime.date] = None, end_date: Optional[datetime.date] = None) -> List[Dict]:
    """
    Retrieves users registered within a date range.
    Args:
        start_date: Start date (optional).
        end_date: End date (optional).
    Returns:
        List of user dictionaries.
    """
    with get_connection() as conn:
        cur = conn.cursor()
        query = """
            SELECT user_id, username, phone, referred_by, balance, is_blocked, created_at
            FROM users 
            WHERE 1=1
        """
        params = []
        
        if start_date:
            query += " AND DATE(created_at) >= ?"
            params.append(start_date.strftime("%Y-%m-%d"))
        
        if end_date:
            query += " AND DATE(created_at) <= ?"
            params.append(end_date.strftime("%Y-%m-%d"))
        
        query += " ORDER BY created_at DESC"
        
        cur.execute(query, params)
        rows = cur.fetchall()
        return [dict(row) for row in rows]