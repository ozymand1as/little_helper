> *This is my ToDo app. There are many like it, but this one is mine.*

# Ozy's Little Helper

A local task assistant with a terminal UI, macOS desktop notifications, and LLM-powered text summarisation.

## Features
- **Interactive TUI** built with [Textual](https://github.com/Textualize/textual)
- **Task management**: add, start, complete, delete, reopen from history
- **Smart notifications**: macOS dialogs with Complete / Later buttons; notes are saved back to the task
- **LLM summarisation**: raw input is cleaned into a short task title using a local llama.cpp model
- **Live countdown** to the next prompt for each task
- **End-of-day deferral**: one keypress postpones all tasks to a selectable date and time (default - tomorrow at 10:30)

## Keyboard shortcuts
| Key | Action |
|-----|--------|
| `a` | Focus input box (add task) |
| `s` | Start selected task |
| `c` | Complete selected task |
| `d` | Delete selected task |
| `v` / `Enter` | View / edit task details & notes |
| `i` | Cycle prompt interval (5m → 15m → 30m → 1h) |
| `h` | Task history (completed tasks) |
| `e` | End the day — defer all prompts to next workday 10:30 |
| `r` | Force refresh from DB |
| `Esc` | Return focus to task list |
| `q` | Quit |

## Requirements
- Python 3.11+
- A running [llama.cpp](https://github.com/ggerganov/llama.cpp) server (default: `http://localhost:8080/v1`)
- macOS (for desktop notifications via `osascript`)

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Configuration

Set environment variables before running:

```bash
export LLAMA_CPP_URL="http://localhost:8080/v1"   # default
export LLAMA_CPP_API_KEY="sk-no-key-required"     # default
```

## Run

```bash
source venv/bin/activate
python main.py
```

The SQLite database (`tasks.db`) is created automatically on first run.

## Project structure

| File | Purpose |
|------|---------|
| `main.py` | Textual TUI application |
| `task_manager.py` | SQLite CRUD layer |
| `llm_integration.py` | LLM summarisation via litellm |
| `notifier.py` | macOS notification dialogs |
| `requirements.txt` | Python dependencies |
