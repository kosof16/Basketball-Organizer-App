"""Database connection and table management"""
import logging
from typing import Optional, Tuple, Any

logger = logging.getLogger(__name__)

# Try to import database drivers
DB_AVAILABLE = False
SQLITE_AVAILABLE = False

try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    DB_AVAILABLE = True
    logger.info("PostgreSQL driver loaded successfully")
except ImportError:
    logger.warning("PostgreSQL driver not available")
    try:
        import sqlite3
        SQLITE_AVAILABLE = True
        logger.info("SQLite available as fallback")
    except ImportError:
        logger.error("No database drivers available")


def get_connection(db_config: Optional[dict] = None) -> Tuple[Any, str]:
    """
    Get a database connection

    Args:
        db_config: Database configuration dictionary

    Returns:
        Tuple of (connection, db_type)
    """
    if DB_AVAILABLE and db_config:
        try:
            conn = psycopg2.connect(**db_config)
            return conn, "postgresql"
        except Exception as e:
            logger.error(f"PostgreSQL connection failed: {e}")

    # Fallback to SQLite
    if SQLITE_AVAILABLE:
        try:
            import sqlite3
            conn = sqlite3.connect(':memory:', check_same_thread=False)
            conn.row_factory = sqlite3.Row
            return conn, "sqlite"
        except Exception as e:
            logger.error(f"SQLite connection failed: {e}")

    logger.warning("Using session state storage")
    return None, "session"


def release_connection(conn: Any, db_type: str) -> None:
    """Release database connection"""
    if conn and db_type == "postgresql":
        try:
            conn.close()
        except Exception as e:
            logger.error(f"Error releasing connection: {e}")


def create_tables(conn: Any, db_type: str) -> bool:
    """
    Create necessary database tables

    Args:
        conn: Database connection
        db_type: Type of database (postgresql, sqlite, session)

    Returns:
        True if tables created successfully, False otherwise
    """
    if db_type == "session":
        logger.info("Using session state storage - no tables to create")
        return True

    try:
        cur = conn.cursor()

        if db_type == "postgresql":
            # Create games table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS games (
                    id SERIAL PRIMARY KEY,
                    game_date DATE NOT NULL,
                    start_time TIME NOT NULL,
                    end_time TIME NOT NULL,
                    location VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE
                )
            """)

            # Create responses table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS responses (
                    id SERIAL PRIMARY KEY,
                    game_id INTEGER REFERENCES games(id),
                    name VARCHAR(255) NOT NULL,
                    others TEXT,
                    status VARCHAR(50) DEFAULT '',
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Add unique constraint if it doesn't exist
            cur.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'unique_game_name'
                    ) THEN
                        ALTER TABLE responses
                        ADD CONSTRAINT unique_game_name
                        UNIQUE (game_id, name);
                    END IF;
                END $$;
            """)

            # Create indexes
            cur.execute("CREATE INDEX IF NOT EXISTS idx_responses_game_id ON responses(game_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_responses_status ON responses(status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_games_active ON games(is_active)")

        else:  # SQLite
            cur.execute("""
                CREATE TABLE IF NOT EXISTS games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_date DATE NOT NULL,
                    start_time TIME NOT NULL,
                    end_time TIME NOT NULL,
                    location TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS responses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    game_id INTEGER,
                    name TEXT NOT NULL,
                    others TEXT,
                    status TEXT DEFAULT '',
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (game_id) REFERENCES games(id),
                    UNIQUE(game_id, name)
                )
            """)

            # Create indexes
            cur.execute("CREATE INDEX IF NOT EXISTS idx_responses_game_id ON responses(game_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_responses_status ON responses(status)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_games_active ON games(is_active)")

        conn.commit()
        cur.close()
        logger.info(f"Database tables created successfully ({db_type})")
        return True

    except Exception as e:
        logger.error(f"Error creating tables: {e}")
        if conn:
            try:
                conn.rollback()
            except:
                pass
        return False
