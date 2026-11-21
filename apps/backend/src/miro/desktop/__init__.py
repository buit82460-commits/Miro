"""Miro desktop automation — unified pilot (Notepad)."""
from miro.desktop.gate import init_job, transfer_job, gate, owner_path
from miro.desktop.dispatch import dispatch, dispatch_window
from miro.desktop.watcher import Watcher, WatchEvent

__all__ = ["init_job", "transfer_job", "gate", "owner_path",
           "dispatch", "dispatch_window", "Watcher", "WatchEvent"]
