import time
import datetime
from textual.app import App, ComposeResult
from textual.coordinate import Coordinate
from textual.widgets import Header, Footer, DataTable, Input, Log, Static, Button, TextArea
from textual.containers import Vertical, Container, Horizontal
from textual.screen import ModalScreen
from textual import work

import task_manager
import notifier
import llm_integration


def format_created_time(created_str: str) -> str:
    if not created_str:
        return "-"
    try:
        fmt = "%Y-%m-%d %H:%M:%S.%f" if "." in created_str else "%Y-%m-%d %H:%M:%S"
        dt = datetime.datetime.strptime(created_str, fmt)
        now = datetime.datetime.now()
        return dt.strftime("%H:%M") if dt.date() == now.date() else dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(created_str)


def get_time_remaining(next_prompt_str: str) -> str:
    if not next_prompt_str:
        return "-"
    try:
        fmt = "%Y-%m-%d %H:%M:%S.%f" if "." in next_prompt_str else "%Y-%m-%d %H:%M:%S"
        diff = datetime.datetime.strptime(next_prompt_str, fmt) - datetime.datetime.now()
        if diff.total_seconds() <= 0:
            return "DUE"
        m, s = divmod(int(diff.total_seconds()), 60)
        if m > 60:
            h, m = divmod(m, 60)
            return f"{h}h {m}m"
        return f"{m}m {s}s"
    except Exception:
        return "?"


class TaskTable(DataTable):
    """DataTable subclass whose bindings are only active when focused."""
    BINDINGS = [
        ("s", "app.start_task", "Start"),
        ("c", "app.complete_task", "Complete"),
        ("d", "app.delete_task", "Delete"),
        ("v", "app.view_details", ""),
        ("i", "app.cycle_interval", "Interval"),
        ("enter", "app.view_details", ""),
    ]


class TaskDetailScreen(ModalScreen):
    BINDINGS = [("escape", "app.pop_screen", "Close")]

    def __init__(self, task: dict):
        super().__init__()
        self._task_data = task

    def compose(self) -> ComposeResult:
        t = self._task_data
        with Container(id="modal-container"):
            yield Static(f"[{t['id']}] {t['description']}", classes="detail-header")
            yield Static(f"Status: {t['status']}  |  Created: {t['created_at']}", classes="detail-meta")
            yield Static("Notes / Raw Input (editable):", classes="detail-label")
            yield TextArea(t.get("raw_input") or "", id="notes-area")
            with Horizontal(id="modal-buttons"):
                yield Button("Save Notes", variant="success", id="save-btn")
                yield Button("Close [Esc]", variant="primary", id="close-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-btn":
            notes = self.query_one("#notes-area", TextArea).text
            task_manager.set_raw_input(self._task_data["id"], notes)
            self.app.query_one(Log).write_line(f"Notes saved for task {self._task_data['id']}.")
            self.app.pop_screen()
        else:
            self.app.pop_screen()


class HistoryScreen(ModalScreen):
    """Modal showing all completed tasks with option to reopen."""
    BINDINGS = [("escape", "app.pop_screen", "Close")]

    def compose(self) -> ComposeResult:
        with Container(id="modal-container"):
            yield Static("Completed Tasks", classes="detail-header")
            yield DataTable(id="history-table")
            with Horizontal(id="modal-buttons"):
                yield Button("Reopen Selected", variant="warning", id="reopen-btn")
                yield Button("Close [Esc]", variant="primary", id="close-btn")

    def on_mount(self) -> None:
        table = self.query_one("#history-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("ID", "Description", "Completed")
        table.focus()
        self._refresh_history()

    def _refresh_history(self) -> None:
        table = self.query_one("#history-table", DataTable)
        table.clear()
        for t in task_manager.get_completed_tasks():
            desc = t["description"]
            if len(desc) > 50:
                desc = desc[:47] + "…"
            table.add_row(
                str(t["id"]),
                desc,
                format_created_time(t["updated_at"]),
                key=str(t["id"]),
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "reopen-btn":
            table = self.query_one("#history-table", DataTable)
            try:
                t_id = int(table.get_cell_at(Coordinate(table.cursor_row, 0)))
                task_manager.reopen_task(t_id)
                self.app.query_one(Log).write_line(f"Task {t_id} reopened.")
                self._refresh_history()
                self.app.action_refresh_tasks()
            except Exception as e:
                self.app.query_one(Log).write_line(f"Error reopening: {e}")
        else:
            self.app.pop_screen()


class OzyHelperApp(App):
    CSS = """
    TaskTable { height: 1fr; }
    #status-log { height: 5; dock: bottom; background: $surface; border-top: solid $secondary; }
    .detail-header { text-style: bold; color: $accent; }
    .detail-meta { color: $text-muted; }

    TaskDetailScreen {
        align: center middle;
    }
    #modal-container {
        border: thick $primary;
        background: $surface;
        width: 80%;
        height: 75%;
        padding: 1 2;
    }
    #notes-area {
        height: 1fr;
        border: solid $accent;
        margin: 1 0;
    }
    #modal-buttons {
        height: auto;
        align: right middle;
    }
    #modal-buttons Button {
        margin-left: 1;
    }
    #raw-input-scroll {
        border: solid $accent;
        height: 1fr;
        overflow-y: scroll;
    }
    """

    BINDINGS = [
        ("q", "quit", ""),
        ("r", "refresh_tasks", "Refresh"),
        ("a", "focus_input", ""),
        ("h", "show_history", "History"),
        ("e", "end_day", "End Day"),
        ("escape", "focus_table", ""),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield TaskTable(id="task-table")
        yield Log(id="status-log")
        yield Input(
            placeholder="Press 'a' or click here to add a task. Press Esc to go back to list.",
            id="input-area",
        )
        yield Footer()

    def on_mount(self) -> None:
        task_manager.init_db()
        table = self.query_one(TaskTable)
        table.add_columns("ID", "Description", "Status", "Created", "Next Prompt")
        table.cursor_type = "row"
        table.focus()

        self.tasks_cache: dict = {}
        self.action_refresh_tasks()

        self.set_interval(1.0, self.update_ui)
        self.set_interval(10.0, self.check_due_tasks)

    # ------------------------------------------------------------------ #
    # Timers                                                               #
    # ------------------------------------------------------------------ #

    def update_ui(self) -> None:
        table = self.query_one(TaskTable)
        for t_id, t in self.tasks_cache.items():
            try:
                table.update_cell(str(t_id), "Next Prompt", get_time_remaining(t["next_prompt_time"]))
            except Exception:
                pass

        if not hasattr(self, "_tick"):
            self._tick = 0
        self._tick += 1
        if self._tick >= 5:
            self._tick = 0
            self.action_refresh_tasks()

    # ------------------------------------------------------------------ #
    # Data                                                                 #
    # ------------------------------------------------------------------ #

    def action_refresh_tasks(self) -> None:
        table = self.query_one(TaskTable)
        coord = table.cursor_coordinate

        db_tasks = task_manager.get_all_active_tasks()
        self.tasks_cache = {t["id"]: t for t in db_tasks}

        table.clear()
        for t_id, t in self.tasks_cache.items():
            desc = t["description"]
            if len(desc) > 50:
                desc = desc[:47] + "…"
            table.add_row(
                str(t_id),
                desc,
                t["status"],
                format_created_time(t["created_at"]),
                get_time_remaining(t["next_prompt_time"]),
                key=str(t_id),
            )

        if len(table.rows) > 0:
            table.move_cursor(row=min(coord.row, len(table.rows) - 1))

    def get_selected_id(self) -> int | None:
        table = self.query_one(TaskTable)
        try:
            return int(table.get_cell_at(Coordinate(table.cursor_row, 0)))
        except Exception as e:
            self.query_one(Log).write_line(f"[debug] selection failed: {e}")
            return None

    # ------------------------------------------------------------------ #
    # Focus helpers                                                        #
    # ------------------------------------------------------------------ #

    def action_focus_input(self) -> None:
        self.query_one("#input-area").focus()

    def action_focus_table(self) -> None:
        self.query_one(TaskTable).focus()

    def action_show_history(self) -> None:
        self.push_screen(HistoryScreen())

    def action_end_day(self) -> None:
        """Defers all active task prompts to next workday at 10:30."""
        next_dt = task_manager.defer_all_to_next_workday(workday_hour=10, workday_minute=30)
        day_name = next_dt.strftime("%A %d %b")
        self.query_one(Log).write_line(
            f"End of day: all tasks deferred to {day_name} at 10:30."
        )
        self.action_refresh_tasks()

    # ------------------------------------------------------------------ #
    # Task actions (called from both App and TaskTable bindings)          #
    # ------------------------------------------------------------------ #

    def action_view_details(self) -> None:
        t_id = self.get_selected_id()
        if t_id and t_id in self.tasks_cache:
            self.push_screen(TaskDetailScreen(self.tasks_cache[t_id]))
        else:
            self.query_one(Log).write_line("Select a task first.")

    def action_start_task(self) -> None:
        t_id = self.get_selected_id()
        if t_id:
            task_manager.update_task_status_and_prompt(t_id, "started", 15)
            self.query_one(Log).write_line(f"Started task {t_id}.")
            self.action_refresh_tasks()

    def action_complete_task(self) -> None:
        t_id = self.get_selected_id()
        if t_id:
            task_manager.complete_task(t_id)
            self.query_one(Log).write_line(f"Completed task {t_id}.")
            self.action_refresh_tasks()

    def action_delete_task(self) -> None:
        t_id = self.get_selected_id()
        if t_id:
            task_manager.delete_task(t_id)
            self.query_one(Log).write_line(f"Deleted task {t_id}.")
            self.action_refresh_tasks()

    def action_cycle_interval(self) -> None:
        t_id = self.get_selected_id()
        if not t_id:
            return
        t = self.tasks_cache[t_id]
        intervals = [5, 15, 30, 60]
        attr = f"iv_{t_id}"
        curr = getattr(self, attr, 1)
        nxt = (curr + 1) % len(intervals)
        setattr(self, attr, nxt)
        task_manager.update_task_status_and_prompt(t_id, t["status"], intervals[nxt])
        self.query_one(Log).write_line(f"Task {t_id} interval: {intervals[nxt]}m")
        self.action_refresh_tasks()

    # ------------------------------------------------------------------ #
    # Input                                                                #
    # ------------------------------------------------------------------ #

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        text = event.value.strip()
        if not text:
            self.action_focus_table()
            return
        event.input.value = ""
        self.query_one(Log).write_line(f"Adding: {text}…")
        self.handle_add(text)
        self.action_focus_table()

    @work(thread=True)
    def handle_add(self, text: str) -> None:
        clean = llm_integration.summarize_task(text)
        t_id = task_manager.add_task(clean, raw_input=text)
        self.call_from_thread(self._post_add, t_id, clean)

    def _post_add(self, t_id: int, desc: str) -> None:
        self.query_one(Log).write_line(f"Added [{t_id}] {desc}")
        self.action_refresh_tasks()

    # ------------------------------------------------------------------ #
    # Background: due-task notifications                                   #
    # ------------------------------------------------------------------ #

    @work(thread=True)
    def check_due_tasks(self) -> None:
        for t in task_manager.get_tasks_due_for_prompt():
            # Lock the task for 5 min so it won't fire again immediately
            task_manager.update_task_status_and_prompt(t["id"], t["status"], 5)
            result = notifier.prompt_for_update(t["description"])
            action = result["action"]
            notes = result["notes"]

            if notes:
                task_manager.append_notes_to_task(t["id"], notes)

            if action == "complete":
                task_manager.complete_task(t["id"])
                self.call_from_thread(
                    self.query_one(Log).write_line, f"Task {t['id']} marked complete."
                )
            else:
                # "later" or "dismissed" — snooze with default interval
                snooze = notifier.DEFAULT_SNOOZE_MINUTES
                task_manager.update_task_status_and_prompt(t["id"], t["status"], snooze)

            self.call_from_thread(self.action_refresh_tasks)


if __name__ == "__main__":
    OzyHelperApp().run()
