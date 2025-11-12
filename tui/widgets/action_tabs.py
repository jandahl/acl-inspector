"""Action tabs widget for drill-down operations."""

from __future__ import annotations

from typing import List, Dict, Any

from textual.widgets import Static, Button
from textual.containers import Horizontal
from textual.message import Message
from textual.reactive import reactive


class ActionTabs(Horizontal):
    """Tab bar showing available actions for selected object."""

    class TabSelected(Message):
        """Posted when a tab is selected."""

        def __init__(self, tab_id: str, tab_label: str) -> None:
            self.tab_id = tab_id
            self.tab_label = tab_label
            super().__init__()

    selected_tab = reactive("details")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.tabs: List[Dict[str, str]] = [
            {"id": "details", "label": "Details"},
            {"id": "inspect", "label": "Inspect"},
            {"id": "compare", "label": "Compare"},
            {"id": "acls", "label": "Used in ACLs"},
            {"id": "path", "label": "Path Check"},
        ]
        self.classes = "action-tabs"
        self.can_focus = True

    def compose(self):
        """Compose tab buttons."""
        for tab in self.tabs:
            is_selected = (tab["id"] == self.selected_tab)
            classes = "action-tab selected" if is_selected else "action-tab"
            btn = Button(tab["label"], id=f"tab-{tab['id']}", classes=classes)
            yield btn

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle tab button clicks."""
        # Extract tab ID from button ID (format: "tab-{id}")
        if event.button.id and event.button.id.startswith("tab-"):
            tab_id = event.button.id[4:]  # Remove "tab-" prefix
            self._select_tab(tab_id)

    def _select_tab(self, tab_id: str) -> None:
        """Select a tab and update visual state."""
        self.selected_tab = tab_id

        # Update button styles
        for btn in self.query(Button):
            if btn.id == f"tab-{tab_id}":
                btn.classes = "action-tab selected"
            else:
                btn.classes = "action-tab"

        # Find tab label
        tab_label = next((t["label"] for t in self.tabs if t["id"] == tab_id), tab_id)

        # Post message
        self.post_message(self.TabSelected(tab_id, tab_label))

    def on_key(self, event) -> None:
        """Handle Left/Right arrow keys for tab navigation."""
        if event.key == "left":
            self._select_previous_tab()
            event.prevent_default()
        elif event.key == "right":
            self._select_next_tab()
            event.prevent_default()

    def _select_previous_tab(self) -> None:
        """Select the previous tab (wrap around)."""
        current_idx = next((i for i, t in enumerate(self.tabs) if t["id"] == self.selected_tab), 0)
        prev_idx = (current_idx - 1) % len(self.tabs)
        self._select_tab(self.tabs[prev_idx]["id"])

    def _select_next_tab(self) -> None:
        """Select the next tab (wrap around)."""
        current_idx = next((i for i, t in enumerate(self.tabs) if t["id"] == self.selected_tab), 0)
        next_idx = (current_idx + 1) % len(self.tabs)
        self._select_tab(self.tabs[next_idx]["id"])

    def watch_selected_tab(self, old_value: str, new_value: str) -> None:
        """Update UI when selected tab changes."""
        # Update button styles
        for btn in self.query(Button):
            btn_id = btn.id
            if btn_id == f"tab-{new_value}":
                btn.classes = "action-tab selected"
            else:
                btn.classes = "action-tab"
