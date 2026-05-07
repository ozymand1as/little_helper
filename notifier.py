import subprocess
from typing import Optional

DEFAULT_SNOOZE_MINUTES = 15

def escape_applescript_string(s: str) -> str:
    """Escapes backslashes and double quotes for AppleScript strings."""
    return s.replace('\\', '\\\\').replace('"', '\\"')

def send_notification(title: str, text: str):
    """Sends a standard macOS notification."""
    safe_title = escape_applescript_string(title)
    safe_text = escape_applescript_string(text)
    script = f'display notification "{safe_text}" with title "{safe_title}"'
    subprocess.run(['osascript', '-e', script])

def prompt_for_update(task_description: str) -> dict:
    """
    Shows a dialog box with "Complete" and "Later" buttons, plus a text input for notes.
    
    Returns a dict:
      {
        "action": "complete" | "later" | "dismissed",
        "notes": str   # text the user typed (may be empty)
      }
    """
    safe_desc = escape_applescript_string(task_description)
    prompt_text = f"Task: {safe_desc}\\n\\nAdd a note (optional):"

    script = f'''
    try
        set dialogResult to display dialog "{prompt_text}" ¬
            default answer "" ¬
            buttons {{"Complete", "Later"}} ¬
            default button "Later"
        set btn to button returned of dialogResult
        set notes to text returned of dialogResult
        if btn is "Complete" then
            return "complete|" & notes
        else
            return "later|" & notes
        end if
    on error
        return "dismissed|"
    end try
    '''

    result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
    raw = result.stdout.strip()

    if "|" in raw:
        action, _, notes = raw.partition("|")
    else:
        action, notes = "dismissed", ""

    return {"action": action.strip(), "notes": notes.strip()}
