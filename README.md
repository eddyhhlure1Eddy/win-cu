# WinCU / Windows Computer Use / Computer Action

About Windows computer use: it is also called Codex Computer Action, but in Claude we have always called it WinCU. Why write it? It is like PiUse, which I released earlier, but PiUse was not open source and runs on Linux, while this version is fully open source.

PiUse is a great project, the one I put a cluster of 8 RTX 6000 Pro cards into. It is on hold for now. As for its DK12, its C kernel optimizations and its other advanced features, I will open-source them step by step someday, because the code is simply too big.

The reason for writing it is simple: Codex's computer use is too hard to use, and it breaks with every update. My quota kept dropping day after day. Our daily work can't be paying the company and then repairing its tool for it, can it? So we wrote our own, and it even surpasses theirs. With ChatGPT 6, it has even surpassed Computer Use. As for why, try it yourself.

It supports all AI models. Most of the testing was done by Anthropic's advanced models, but ChatGPT 6 and Chinese models with vision can use it too; in fact, they all can, and I have tried them all. Because it connects through MCP, it is more direct and freer. But please don't modify it too freely: it is an open-source MCP that is even more industrial-grade than Computer Use, a complete Windows computer-control system for stable use. There are no binaries and no compiled .pyc files, so you can use it directly and freely.

One more point: compared with Computer Use, we have no flashy front end, because I don't think Windows needs that kind of thing, such as that transparent glass overlay, the blue one. It is also written directly in Python, not in C. I will keep optimizing it as I keep using it, but I have been using it for industrial-grade work recently, and I think it is already smooth and stable enough, with no cache buildup at all. The whole computer runs very smoothly, unlike before with Computer Use, which had massive memory leaks, all kinds of bugs, and OpenAI's updates to Sky. That was simply terrible.

## Overview

An MCP server that lets an AI agent operate a Windows PC: screenshots, mouse, keyboard, clipboard, windows and UI Automation accessibility trees. Input is sent with `SendInput`, windows are captured with `PrintWindow`, and accessibility trees are read through UI Automation. Python, stdio transport, version 2.0.0.

## Tools

| Group | Tools |
| --- | --- |
| Screen | `screenshot`, `zoom`, `cursor_position` |
| Pointer | `left_click`, `right_click`, `middle_click`, `double_click`, `triple_click`, `mouse_move`, `left_click_drag`, `left_mouse_down`, `left_mouse_up`, `scroll` |
| Keyboard | `type`, `key`, `hold_key` |
| Timing and batches | `wait`, `computer_batch` |
| Windows and apps | `list_windows`, `list_apps`, `open_application`, `activate_window` |
| Accessibility | `get_window_state`, `click_element`, `set_value`, `perform_secondary_action` |
| Clipboard | `read_clipboard`, `write_clipboard` |

- **Two coordinate frames.** Without `window_id`, an action works on the whole desktop. With `window_id`, the window is brought to the front first, and coordinates are pixels of that window's own screenshot, which is captured correctly even while the window is covered.
- **Screenshots** are scaled down so the longest edge is at most `max_image_edge` (2000 px). The pointer is drawn into desktop screenshots, and off-limits windows are blanked. A screenshot whose PNG is larger than `max_png_bytes` (300,000 bytes) is sent as JPEG (quality 80).
- **Actions answer with one line of text**, not an image. `computer_batch` runs up to 30 steps in order within 75 s, stops at the first step that fails, and ends with a screenshot.
- **`type`** takes text in any language. A line break at the very end presses Enter; text with line breaks inside, or longer than 400 characters, is pasted through the clipboard.
- **Elements** are addressed by accessible name or by index in the latest `get_window_state` tree. `click_element` clicks the element's centre with the real mouse and reports which element it clicked.
- **Time limit.** Each call ends within 100 s. A call stuck in an application that stopped responding is abandoned and its worker thread is replaced.

## Refusals

- **Off-limits windows:** terminals and consoles, Windows security and sign-in prompts, password managers, Start and Windows search, the Run dialog, and Claude's own windows, which are also blanked in screenshots. See `denied_apps` and `denied_window_classes`.
- **The Windows key** is never sent.
- **Code editors** (`click_only_apps`) allow only looking, left-clicking and scrolling, because their built-in terminals run commands.
- **Banner and Esc.** While input is being sent, a banner shows at the top of the screen; it never appears in screenshots. Pressing Esc while it shows refuses input for 12 s.
- **The user comes first.** If the mouse or keyboard was used in the last 0.8 s, input waits up to 4 s and is then refused (`yield_to_user`).
- **One driver at a time.** Input is refused while a window listed in `busy_markers` is visible, and for `session_hold_s` (20 s) after another Claude Code session last sent input through win-cu.
- **No stuck buttons.** A held mouse button is released when Esc is pressed, when a call is cancelled, and when Claude Code exits.

## Requirements

- Windows 11 (tested on version 24H2, build 26100)
- Python 3.13 (tested with 3.13.1)
- `mcp>=1.23,<2`, `comtypes>=1.4`, `pillow>=10` (tested with mcp 1.23.1, comtypes 1.4.16, pillow 12.3.0)

## Install

```
pip install -r requirements.txt
```

Register the server for Claude Code in `~/.claude.json`, under the top-level `mcpServers` (user scope):

```json
"win-cu": {
  "type": "stdio",
  "command": "C:/path/to/python.exe",
  "args": ["-u", "-X", "utf8", "C:/path/to/win-cu/server.py"],
  "timeout": 150000,
  "alwaysLoad": true
}
```

Replace both paths with your own. Each new Claude Code session starts its own server process.

## Skill

`skills/win-computer-use/SKILL.md` is a Claude Code skill with win-cu's core notes: coordinate frames, batching, tools, refusals, error messages and configuration. The server's instructions refer to it. Its Other section is left for your own rules. To install it, copy the `skills/win-computer-use` folder to `~/.claude/skills/`.

## Configuration

Settings are read from `config.json` next to `server.py`, or from the file named by the `WINCU_CONFIG` environment variable. Each key replaces the default from `DEFAULT_CONFIG` in `wincu/core.py`; a list replaces the whole default list. The shipped `config.json` sets `max_image_edge`, `show_banner` and `yield_to_user`.

| Key | Default | Meaning |
| --- | --- | --- |
| `max_image_edge` | `2000` | Longest screenshot edge sent to the model, in pixels |
| `max_png_bytes` | `300000` | Larger screenshots are sent as JPEG |
| `settle_ms`, `settle_max_ms` | `200`, `2500` | After an action, wait `settle_ms`, then until the picture stops changing, at most `settle_max_ms` |
| `launch_wait_s` | `8` | How long `open_application` waits for a started app's window |
| `show_banner` | `true` | Show the banner while sending input |
| `banner_linger_s` | `10` | How long the banner stays after the last action |
| `yield_to_user` | `true` | Hold input back while the user is using the mouse or keyboard |
| `session_hold_s` | `20` | How long another session is refused after one last sent input |
| `max_tree_elements`, `max_tree_tokens`, `max_document_chars` | `1500`, `10000`, `4000` | Size limits of `get_window_state` output |
| `busy_markers` | one window class | Windows whose presence means another agent is driving the desktop |
| `denied_apps` | terminals, security and sign-in, password managers, Start and search, Claude | `.exe` entries match the executable name; other entries match inside the app id |
| `denied_window_classes` | console window classes | Windows of these classes are off limits |
| `click_only_apps` | code editors | Look, left-click and scroll only |

## Logs

- `logs/win-cu.log`: one line per call, with its arguments and outcome. It rotates at 1 MB and keeps 3 old files. Typed text longer than 24 characters is logged as its length only.
- `logs/owner.json`: the session that last sent input.

## Tests

Run each script directly, for example `python tests/test_unit.py`.

| Script | What it checks |
| --- | --- |
| `tests/test_unit.py` | Logic that needs no window: stop and release rules, session ownership, text and key parsing. Sends nothing but button releases, so it can run while the PC is in use. |
| `tests/test_tools.py` | Every tool, through the MCP server, against the test window `TestForm.exe`, checked in its event log. Takes the mouse and keyboard for about a minute. |
| `tests/test_scaled.py` | Coordinate mapping when screenshots are scaled down (`max_image_edge` 500). |
| `tests/test_tiers.py` | The click-only tier for code editors, with the test window standing in for an editor. |
| `tests/e2e_session.py` | A headless Claude Code session gets a small GUI task and only the win-cu tools; reports what happened, model turns, tool calls and time. |
| `tests/calib_server.py` | A test-only MCP server, registered by `tests/calib.mcp.json`, that returns an image with markers at known pixels, to check that screenshots reach the model unscaled. |
| `tests/desk_free.py` | Exits 0 when the PC is free for input tests: nobody has used it for a while, no other agent is driving it, and no other session used win-cu in the last two minutes. |

- `test_tools.py`, `test_scaled.py`, `test_tiers.py` and `e2e_session.py` move the real mouse and keyboard. Run `tests/desk_free.py` first and check its exit code.
- The test windows are C# programs. Build them into `tests/` with the .NET Framework compiler:

  ```
  C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe /nologo /target:winexe /out:tests\TestForm.exe tests\TestForm.cs
  C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe /nologo /target:winexe /out:tests\WebForm.exe tests\WebForm.cs
  ```

- The web page check in `test_tools.py` needs a `WebView2Loader.dll`, which is not part of Windows. Set `WINCU_WEBVIEW2_LOADER` to the path of one; without it the check is skipped.
- `e2e_session.py` runs Claude Code from `%APPDATA%\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe` and uses quota for one short session.
- `tests/calib.mcp.json` has placeholder paths; replace them with yours.
- Test screenshots are written to `tests/out/`.

## Layout

| Path | Contents |
| --- | --- |
| `server.py` | MCP server: tool schemas, worker thread, time limit, logging |
| `config.json` | Settings |
| `wincu/core.py` | Tool logic: targeting, refusal rules, capture, coordinate mapping, the actions |
| `wincu/native.py` | Win32 through ctypes: window enumeration, capture, `SendInput` |
| `wincu/uia.py` | UI Automation: accessibility tree snapshots and pattern actions |
| `wincu/presence.py` | Banner, Esc to stop, yielding to the user's input |
| `wincu/apps.py` | Installed apps (`shell:AppsFolder`), usage statistics, launching |
| `wincu/keys.py` | Key-chord parsing: X keysym names to virtual-key codes |
| `tests/` | Test scripts and the C# test windows |
| `skills/win-computer-use/` | Claude Code skill: core notes for using win-cu |
