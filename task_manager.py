import sqlite3
import datetime
import os

# Database path is absolute, relative to this file
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(PROJECT_ROOT, "tasks.db")

def dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            description TEXT NOT NULL,
            raw_input TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            next_prompt_time TIMESTAMP
        )
    ''')
    try:
        cursor.execute('ALTER TABLE tasks ADD COLUMN raw_input TEXT')
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()

def add_task(description: str, raw_input: str = None, status: str = 'pending'):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.datetime.now()
    # Default next prompt: 15 minutes for all new tasks
    next_prompt = now + datetime.timedelta(minutes=15)
    cursor.execute('''
        INSERT INTO tasks (description, raw_input, status, next_prompt_time)
        VALUES (?, ?, ?, ?)
    ''', (description, raw_input, status, next_prompt))
    conn.commit()
    task_id = cursor.lastrowid
    conn.close()
    return task_id

def append_notes_to_task(task_id: int, notes: str):
    """Appends timestamped notes to the raw_input field of a task."""
    if not notes:
        return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT raw_input FROM tasks WHERE id = ?', (task_id,))
    row = cursor.fetchone()
    existing = (row[0] or "") if row else ""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    separator = "\n" if existing else ""
    updated = f"{existing}{separator}[{timestamp}] {notes}"
    cursor.execute('UPDATE tasks SET raw_input = ? WHERE id = ?', (updated, task_id))
    conn.commit()
    conn.close()

def set_raw_input(task_id: int, text: str):
    """Overwrites the raw_input field of a task."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('UPDATE tasks SET raw_input = ? WHERE id = ?', (text, task_id))
    conn.commit()
    conn.close()

def get_completed_tasks():
    """Returns all completed tasks, most recently updated first."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = dict_factory
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM tasks
        WHERE status = 'completed'
        ORDER BY updated_at DESC
    ''')
    tasks = cursor.fetchall()
    conn.close()
    return tasks

def reopen_task(task_id: int):
    """Sets a completed task back to pending with a fresh 15-minute prompt."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.datetime.now()
    next_prompt = now + datetime.timedelta(minutes=15)
    cursor.execute('''
        UPDATE tasks SET status = 'pending', updated_at = ?, next_prompt_time = ?
        WHERE id = ?
    ''', (now, next_prompt, task_id))
    conn.commit()
    conn.close()

def defer_all_to_datetime(target_dt: "datetime.datetime"):
    """Defers all active tasks to the given datetime."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.datetime.now()
    cursor.execute('''
        UPDATE tasks SET next_prompt_time = ?, updated_at = ?
        WHERE status != 'completed'
    ''', (target_dt, now))
    conn.commit()
    conn.close()

def defer_task_to_datetime(task_id: int, target_dt: "datetime.datetime"):
    """Defers a specific task to the given datetime."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.datetime.now()
    cursor.execute('''
        UPDATE tasks SET next_prompt_time = ?, updated_at = ?
        WHERE id = ?
    ''', (target_dt, now, task_id))
    conn.commit()
    conn.close()

def defer_all_to_next_workday(workday_hour: int = 10, workday_minute: int = 30):
    """
    Defers all active (non-completed) tasks to next workday at the given time.
    Skips weekends: if today is Fri/Sat/Sun, rolls forward to Monday.
    Returns the datetime that tasks were deferred to.
    """
    now = datetime.datetime.now()
    today = now.date()

    # Find next workday (Mon=0 ... Fri=4, Sat=5, Sun=6)
    days_ahead = 1
    candidate = today + datetime.timedelta(days=days_ahead)
    while candidate.weekday() >= 5:  # skip Sat/Sun
        days_ahead += 1
        candidate = today + datetime.timedelta(days=days_ahead)

    next_workday_dt = datetime.datetime(
        candidate.year, candidate.month, candidate.day,
        workday_hour, workday_minute, 0
    )

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE tasks SET next_prompt_time = ?, updated_at = ?
        WHERE status != 'completed'
    ''', (next_workday_dt, now))
    conn.commit()
    conn.close()
    return next_workday_dt

def get_tasks_due_for_prompt():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = dict_factory
    cursor = conn.cursor()
    now = datetime.datetime.now()
    cursor.execute('''
        SELECT * FROM tasks 
        WHERE status != 'completed' AND next_prompt_time <= ?
    ''', (now,))
    tasks = cursor.fetchall()
    conn.close()
    return tasks

def update_task_status_and_prompt(task_id: int, status: str, next_prompt_delta_minutes: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.datetime.now()
    next_prompt = now + datetime.timedelta(minutes=next_prompt_delta_minutes)
    cursor.execute('''
        UPDATE tasks 
        SET status = ?, updated_at = ?, next_prompt_time = ?
        WHERE id = ?
    ''', (status, now, next_prompt, task_id))
    conn.commit()
    conn.close()

def complete_task(task_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.datetime.now()
    cursor.execute('''
        UPDATE tasks 
        SET status = 'completed', updated_at = ?
        WHERE id = ?
    ''', (now, task_id))
    conn.commit()
    conn.close()

def delete_task(task_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('DELETE FROM tasks WHERE id = ?', (task_id,))
    conn.commit()
    conn.close()

def get_all_active_tasks():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = dict_factory
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM tasks 
        WHERE status != 'completed'
    ''')
    tasks = cursor.fetchall()
    conn.close()
    return tasks
