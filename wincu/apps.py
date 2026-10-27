from __future__ import annotations

import codecs
import datetime
import os
import shutil
import struct
import time
import winreg
from dataclasses import dataclass

import comtypes.client

from . import native

_NOT_APPS = (".html", ".htm", ".chm", ".pdf", ".txt", ".url", ".msi", ".rtf", ".md")
_APP_PATHS = r"Software\Microsoft\Windows\CurrentVersion\App Paths"
_USERASSIST = r"Software\Microsoft\Windows\CurrentVersion\Explorer\UserAssist"
_USERASSIST_GUIDS = ("{CEBFF5CD-ACE2-4F4F-9178-9926F41749EA}", "{F4E57C4B-2036-45F0-A9AB-443BCFE33D9F}")


@dataclass
class InstalledApp:
    id: str
    name: str
    target: str


class AppCatalog:
    def __init__(self, ttl: float = 300.0) -> None:
        self._ttl = ttl
        self._apps: list[InstalledApp] = []
        self._loaded = 0.0

    def installed(self, refresh: bool = False) -> list[InstalledApp]:
        if refresh or not self._apps or time.monotonic() - self._loaded > self._ttl:
            self._apps = self._enumerate()
            self._loaded = time.monotonic()
        return self._apps

    @staticmethod
    def _enumerate() -> list[InstalledApp]:
        shell = comtypes.client.CreateObject("Shell.Application", dynamic=True)
        items = shell.NameSpace("shell:AppsFolder").Items()
        out = []
        for i in range(items.Count):
            item = items.Item(i)
            try:
                name, app_id = item.Name, item.Path
                target = item.ExtendedProperty("System.Link.TargetParsingPath") or ""
            except Exception:
                continue
            if not app_id or (target or app_id).lower().endswith(_NOT_APPS):
                continue
            if os.path.basename(target).lower().startswith(("unins", "uninstall")):
                continue
            out.append(InstalledApp(app_id, name or app_id, target))
        return out

    def find(self, app_id: str) -> InstalledApp | None:
        key = app_id.lower()
        for refresh in (False, True):
            for app in self.installed(refresh):
                if app.id.lower() == key:
                    return app
        return None

    @staticmethod
    def usage() -> dict[str, tuple[int, str]]:
        stats: dict[str, tuple[int, str]] = {}
        for guid in _USERASSIST_GUIDS:
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, f"{_USERASSIST}\\{guid}\\Count")
            except OSError:
                continue
            with key:
                i = 0
                while True:
                    try:
                        name, data, _ = winreg.EnumValue(key, i)
                    except OSError:
                        break
                    i += 1
                    if not isinstance(data, bytes) or len(data) < 68:
                        continue
                    count = struct.unpack_from("<I", data, 4)[0]
                    filetime = struct.unpack_from("<Q", data, 60)[0]
                    if not count and not filetime:
                        continue
                    when = ""
                    if filetime:
                        try:
                            stamp = datetime.datetime(1601, 1, 1) + datetime.timedelta(microseconds=filetime // 10)
                            when = stamp.replace(microsecond=0).isoformat() + "Z"
                        except OverflowError:
                            pass
                    stats[codecs.decode(name, "rot13").lower()] = (count, when)
        return stats


def find_executable(name: str) -> str:
    found = shutil.which(name)
    if found:
        return os.path.abspath(found)
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, f"{_APP_PATHS}\\{name}") as key:
                path = os.path.expandvars(str(winreg.QueryValueEx(key, "")[0]).strip().strip('"'))
        except OSError:
            continue
        if os.path.isfile(path):
            return path
    return ""


def launch(target: str) -> None:
    if os.path.isfile(target):
        verb_target, cwd = target, os.path.dirname(target)
    else:
        verb_target, cwd = "shell:AppsFolder\\" + target, None
    rc = native.ShellExecuteW(None, "open", verb_target, None, cwd, 1)
    if (rc or 0) <= 32:
        raise OSError(f"ShellExecute failed with code {rc}")
