---
name: win-computer-use
description: Core notes for operating this Windows PC through the win-cu MCP server (full-desktop screenshots, mouse, keyboard, window accessibility trees, clicking controls by name, batched actions): coordinate frames, batching, tools, what the server refuses, error messages and configuration. How to operate is already in win-cu's server instructions, so there is no need to read this skill before starting; read it when an action is refused, when an error comes back, or when looking for the configuration.
---

# Windows Computer Use (win-cu)

win-cu lets Claude use this computer's screen, mouse and keyboard as if sitting in front of it. Its mouse and keyboard tools are the 17 actions of Claude's native computer use, with the same names and parameters. The tools are named `mcp__win-cu__*` and load automatically when each session starts.

## Two coordinate frames

- Without `window_id`: the whole desktop. `screenshot` captures the full screen, scaled so the longest edge is at most 2000 px; coordinates are pixels of that image.
- With `window_id`: only that window. It is brought to the front first, and coordinates are pixels of that window's own screenshot; the screenshot is correct even while other windows cover it.
- `zoom` is only for reading small text; afterwards, coordinates still refer to the full screenshot.

## Being quick

- Actions answer with one line of text (what was done, whether the picture changed, whether new windows appeared), not an image.
- Put predictable steps into one `computer_batch`: they run in order, stop at the first step that fails, and end with a screenshot, so no separate screenshot is needed. A batch takes at most 30 steps and 75 seconds, and can mix coordinate actions with `click_element`, `set_value` and `activate_window`.
- Do not batch exploratory steps: if you don't know what a click will bring up, go one step at a time and take a `screenshot` after each single action.
- For standard controls use `click_element` by name, reading names from the `get_window_state` tree. For canvases, 3D viewports and custom-drawn UI, use coordinates.
- The keyboard is faster than hunting for pixels: `key` takes `ctrl+s`, `alt+F4`, `Return`, `Tab`; several combinations separated by spaces are pressed in order, and `repeat` presses repeatedly.
- A line break at the end of `type` text presses Enter; line breaks inside the text stay line breaks (such text, and text over 400 characters, is pasted through the clipboard so a chat box does not send early), and the clipboard's previous text is put back afterwards.
- `set_value`: a text box is clicked, fully selected and typed into; a drop-down is expanded and the option clicked, so the application is notified either way; a slider is set directly.
- Open applications with `open_application` (app ids from `list_apps`); do not click the Start menu.

## Tools

| Purpose | Tools |
| :- | :- |
| Look | `screenshot`, `zoom`, `cursor_position`, `get_window_state` (accessibility tree), `list_windows`, `list_apps` |
| Mouse | `left_click`, `right_click`, `middle_click`, `double_click`, `triple_click`, `left_click_drag`, `mouse_move`, `left_mouse_down`, `left_mouse_up`, `scroll` |
| Keyboard | `type`, `key`, `hold_key` |
| Controls | `click_element`, `set_value`, `perform_secondary_action` |
| Other | `computer_batch`, `wait`, `open_application`, `activate_window`, `read_clipboard`, `write_clipboard` |

## What the server refuses by itself

- Terminals, Windows Security and sign-in prompts, password managers, the Start menu and Windows search, and Claude's own windows: they show as grey blocks in screenshots, cannot be clicked, and keyboard input does not reach them.
- Code editors (VS Code, Cursor, Windsurf, Visual Studio, the JetBrains family and others, which have built-in terminals): only looking, left-clicking and scrolling; typing, key presses, right-clicks, clicks with modifier keys, drags and setting values are all refused. To edit files or run commands, use file tools and the PowerShell tool.
- The Windows key and its combinations.
- While the user is moving the mouse or using the keyboard; while a modifier key is held down.
- While ChatGPT's Computer Use is operating; within 20 seconds after another Claude session last acted.
- Within 12 seconds after the user presses Esc. During operation a banner shows at the top of the screen; Esc works while the banner is showing.
- When the desktop is locked; when the target program runs with higher privileges than Claude Code.

Releasing the mouse button (`left_mouse_up`) and `wait` are never refused. When refused, stop and tell the user why; do not work around it another way.

## When something goes wrong

| Message | What to do |
| :- | :- |
| `is no longer open` | Get the window id again with `list_windows` or `screenshot` |
| `minimized` | `activate_window` |
| `blocked by a modal dialog` | Use the dialog id given in the error |
| `over a non-target window` | `activate_window`, take a new screenshot and try once more; if a dialog is in the way, operate it directly |
| `No element is named …` | Look at the similar names it gives, or call `get_window_state` again |
| `matches several elements` | Pass `element_index` instead |
| `did not answer the accessibility request` | The program is stuck in its own dialog; handle that dialog with a screenshot plus coordinates or the keyboard |
| `changed size since its last screenshot` | Take a new screenshot of the window |
| `Another agent is controlling this desktop` | Wait until ChatGPT is done, or ask the user |
| `Another Claude session is using this computer` | Ask the user which session should continue |
| `The user pressed Esc` / `is using the mouse or keyboard` | Stop, tell the user, and wait until the user says to continue |
| `Keyboard focus moved to another window` | Take a new screenshot to see where the focus is, then decide |
| `is a code editor with a built-in terminal` | Use file tools or the PowerShell tool instead |
| `no "…" to choose. Choices: …` | The drop-down has no such item; pick one of the listed choices |
| `desktop is locked` | Stop and ask the user to unlock it |

If the same action fails twice in a row, stop and tell the user the exact message.

## Configuration and troubleshooting

- `config.json` in the server folder: `max_image_edge` (longest screenshot edge, default 2000), `show_banner`, `yield_to_user`, `banner_linger_s`, `session_hold_s`, `settle_ms`, `settle_max_ms`, `denied_apps`, `denied_window_classes`, `click_only_apps`, `busy_markers`. Changes take effect in a new session.
- Log `logs/win-cu.log`: every call and its result; long typed text is logged as its length only.
- Self-tests, all under `tests/`: `test_unit.py` does not use the mouse or keyboard and can run any time; `test_tools.py`, `test_scaled.py` and `test_tiers.py` take the mouse and keyboard for a little over a minute in total, so run `desk_free.py` first and only continue if its exit code is 0; `e2e_session.py` starts a headless Claude session to solve a small UI task and uses quota.
- If the server process crashes it does not reconnect by itself; run `/mcp reconnect win-cu` in the session.

## Other

Add your own rules here, for example which actions to confirm with the user first and what the agent must never do, and keep refining them for your own setup.
