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
        ("I", "app.defer_task", "Defer To..."),
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


class DeferScreen(ModalScreen):
    """Modal to configure the deferral time for a task (or all tasks)."""
    BINDINGS = [
        ("escape", "app.pop_screen", "Cancel"),
        ("up", "increment", "Increment"),
        ("down", "decrement", "Decrement"),
        ("left", "prev_field", "Previous Field"),
        ("right", "next_field", "Next Field"),
        ("tab", "next_field", "Next Field"),
        ("enter", "confirm", "Confirm"),
    ]

    def __init__(self, task_id: int = None):
        super().__init__()
        # Default to tomorrow at 10:30
        now = datetime.datetime.now()
        self.target_date = now.date() + datetime.timedelta(days=1)
        self.hour = 10
        self.minute = 30
        self.focus_index = 0  # 0: Day, 1: Hour, 2: Minute
        self.task_id = task_id

    def compose(self) -> ComposeResult:
        with Container(id="end-day-container"):
            title = "Defer All Tasks To:" if self.task_id is None else f"Defer Task [{self.task_id}] To:"
            yield Static(title, classes="modal-title")
            with Horizontal(id="spinner-container"):
                with Vertical(classes="spinner-col", id="col-day"):
                    yield Static("▲", classes="arrow up")
                    yield Static("", id="day-val", classes="val")
                    yield Static("▼", classes="arrow down")
                
                with Vertical(classes="spinner-col", id="col-hour"):
                    yield Static("▲", classes="arrow up")
                    yield Static("", id="hour-val", classes="val")
                    yield Static("▼", classes="arrow down")
                
                with Vertical(classes="spinner-col-sep"):
                    yield Static(" ")
                    yield Static(":", classes="sep")
                    yield Static(" ")

                with Vertical(classes="spinner-col", id="col-min"):
                    yield Static("▲", classes="arrow up")
                    yield Static("", id="min-val", classes="val")
                    yield Static("▼", classes="arrow down")
            
            yield Static("Arrows to adjust • Enter to confirm", classes="modal-hint")
            with Horizontal(id="modal-buttons"):
                yield Button("Confirm [Enter]", variant="success", id="confirm-btn")
                yield Button("Cancel [Esc]", variant="primary", id="cancel-btn")

    def on_mount(self) -> None:
        self._update_display()

    def _update_display(self) -> None:
        day_str = self.target_date.strftime("%A")
        # If it's more than 7 days away, show the date too
        if (self.target_date - datetime.date.today()).days > 6:
             day_str = self.target_date.strftime("%a %d %b")
        elif self.target_date == datetime.date.today() + datetime.timedelta(days=1):
            day_str = "Tomorrow"
        elif self.target_date == datetime.date.today():
            day_str = "Today"

        self.query_one("#day-val").update(day_str)
        self.query_one("#hour-val").update(f"{self.hour:02d}")
        self.query_one("#min-val").update(f"{self.minute:02d}")

        # Update focus classes
        for i, col_id in enumerate(["#col-day", "#col-hour", "#col-min"]):
            col = self.query_one(col_id)
            if i == self.focus_index:
                col.add_class("focused")
            else:
                col.remove_class("focused")

    def action_increment(self) -> None:
        if self.focus_index == 0:
            self.target_date += datetime.timedelta(days=1)
        elif self.focus_index == 1:
            self.hour = (self.hour + 1) % 24
        elif self.focus_index == 2:
            self.minute = (self.minute + 15) % 60
        self._update_display()

    def action_decrement(self) -> None:
        if self.focus_index == 0:
            # Don't allow deferring to the past
            new_date = self.target_date - datetime.timedelta(days=1)
            if new_date >= datetime.date.today():
                self.target_date = new_date
        elif self.focus_index == 1:
            self.hour = (self.hour - 1) % 24
        elif self.focus_index == 2:
            self.minute = (self.minute - 15) % 60
        self._update_display()

    def action_next_field(self) -> None:
        self.focus_index = (self.focus_index + 1) % 3
        self._update_display()

    def action_prev_field(self) -> None:
        self.focus_index = (self.focus_index - 1) % 3
        self._update_display()

    def action_confirm(self) -> None:
        dt = datetime.datetime(
            self.target_date.year, self.target_date.month, self.target_date.day,
            self.hour, self.minute
        )
        if self.task_id is None:
            task_manager.defer_all_to_datetime(dt)
            self.app.query_one(Log).write_line(f"All tasks deferred to {dt.strftime('%Y-%m-%d %H:%M')}")
        else:
            task_manager.defer_task_to_datetime(self.task_id, dt)
            self.app.query_one(Log).write_line(f"Task {self.task_id} deferred to {dt.strftime('%Y-%m-%d %H:%M')}")
        
        self.app.action_refresh_tasks()
        self.dismiss(True)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-btn":
            self.action_confirm()
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
    #end-day-container {
        border: thick $primary;
        background: $surface;
        width: 60;
        height: 18;
        padding: 1 2;
        align: center middle;
    }
    .modal-title {
        text-align: center;
        text-style: bold;
        margin-bottom: 1;
    }
    .modal-hint {
        text-align: center;
        color: $text-muted;
        margin-top: 1;
    }
    #spinner-container {
        height: 7;
        align: center middle;
        margin: 1 0;
    }
    .spinner-col {
        width: 16;
        height: 7;
        align: center middle;
        border: solid $secondary;
        margin: 0 1;
    }
    .spinner-col-sep {
        width: 3;
        height: 7;
        align: center middle;
    }
    .sep {
        text-style: bold;
    }
    .spinner-col.focused {
        border: double $accent;
        background: $accent 10%;
        color: $accent;
    }
    .spinner-col .arrow {
        color: $text-muted;
        text-align: center;
    }
    .spinner-col.focused .arrow {
        color: $accent;
        text-style: bold;
    }
    .spinner-col .val {
        text-align: center;
        text-style: bold;
    }
    .spinner-col.focused .val {
        text-style: bold;
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
        """Opens modal to defer all active task prompts."""
        self.push_screen(DeferScreen(task_id=None))

    def action_defer_task(self) -> None:
        """Opens modal to defer the selected task."""
        t_id = self.get_selected_id()
        if t_id:
            self.push_screen(DeferScreen(task_id=t_id))
        else:
            self.query_one(Log).write_line("Select a task first.")

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
