import base64
import json
import logging
import random
import requests
import threading
import time
import zlib
from dataclasses import dataclass, field

import anki.collection
from anki.notes import Note
from aqt import mw, gui_hooks
from aqt.operations import QueryOp
from aqt.utils import showInfo
from aqt.qt import QAction, qconnect

from . import schedule

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
logging.basicConfig(level=logging.INFO)


@dataclass
class TRMNLPluginConfig:
    visible_fields: list = field(default_factory=list)
    webhook: str = ""
    search_query: str = "deck:current"
    enabled: bool = True


@dataclass
class Config:
    plugins: list[TRMNLPluginConfig]
    refresh_rate: int = 600

    def __init__(self, plugins=None, refresh_rate=600):
        self.plugins = [
            TRMNLPluginConfig(**plugin) if isinstance(plugin, dict) else plugin
            for plugin in (plugins or [])
        ]
        self.refresh_rate = max(int(refresh_rate), 310)


def get_config() -> Config:
    config = mw.addonManager.getConfig(__name__)
    return Config(**(config or {}))


def compress_text(text):
    """
    Compresses a text string (including non-ASCII characters) and returns a compressed string.
    Yoinked from https://github.com/albert7617/trmnl-japanese/

    Args:
        text (str): The input text to compress

    Returns:
        str: The compressed text as a base64-encoded string
    """
    # Convert text to bytes (UTF-8 encoding handles all Unicode characters)
    text_bytes = text.encode('utf-8')

    # Compress the bytes using zlib
    compressed_bytes = zlib.compress(text_bytes, level=zlib.Z_BEST_COMPRESSION)

    # Encode the compressed bytes as base64 for safe string representation
    compressed_text = base64.b64encode(compressed_bytes).decode('ascii')

    return compressed_text


class TRMNLPlugin:
    config: TRMNLPluginConfig

    def __init__(self, config: TRMNLPluginConfig):
        self.config = config
        logger.info("Initializing TRMNLPlugin with config: %s", self.config)

    def get_new_note(self, col: anki.collection.Collection) -> Note:
        notes = col.find_notes(query=self.config.search_query)
        if not notes:
            raise Exception("TRMNL Anki: No notes found with the search query: " + self.config.search_query)

        note = col.get_note(random.choice(notes))
        logger.info("Selected note: %s", note.id)

        return note

    def call_webhook(self, note: Note) -> requests.Response:
        note_data = dict(note.items())

        populated_kwargs = {
            visible_field: note_data[visible_field]
            for visible_field in self.config.visible_fields
            if visible_field in note_data.keys()
        }

        logger.info("Finalized note data: %s", populated_kwargs)

        # TODO: Check payload size before sending? (Max 2kb for TRMNL's servers)
        payload = {"compressed": compress_text(json.dumps(populated_kwargs))}

        # Example webhook call
        # curl "https://usetrmnl.com/api/custom_plugins/asdfqwerty1234" \
        #   -H "Content-Type: application/json" \
        #   -d '{"merge_variables": {"term":"foobar"}}' \
        #   -X POST
        response = requests.post(
            self.config.webhook, json={'merge_variables': {'note_id': note.id, **payload}}
        )
        logger.info(f"{response.status_code}: {response.reason} {response.text}")
        return response

    def refresh_trmnl_plugin(self) -> requests.Response:
        """
        Returns:
            requests.Response: Response from the webhook call
        """
        if not mw.col:
            raise Exception(f"TRMNL Anki: Anki collection is not initialized (how did you get here?)")

        note = self.get_new_note(mw.col)
        if not self.config.webhook:
            raise Exception(f"TRMNL Anki: No webhook url given to TRMNL")
        return self.call_webhook(note)


class TRMNLAnki:
    config: Config
    trmnl_plugins: list[TRMNLPlugin] = []
    trmnl_job: schedule.Job
    cease_continuous_run: threading.Event
    initialized: bool = False

    def __init__(self):
        self.config = get_config()
        logger.info("Initializing TRMNLAnki with config: %s", self.config)
        for plugin_config in self.config.plugins:
            self.trmnl_plugins.append(TRMNLPlugin(plugin_config))

    def start(self):
        self.trmnl_job = schedule.every(int(self.config.refresh_rate)).seconds.do(self.refresh_trmnl)

        # Start background thread
        self.cease_continuous_run = threading.Event()

        def background_task():
            while not self.cease_continuous_run.is_set():
                schedule.run_pending()
                time.sleep(1)

        logger.info(f"{__name__}: Starting thread")
        continuous_thread = threading.Thread(target=background_task, daemon=True)
        continuous_thread.start()
        self.initialized = True

    def refresh_config(self, text: str, addon: str) -> str:
        if addon != __name__:
            return text
        try:
            json_config = json.loads(text)
        except json.JSONDecodeError:
            # If the user inputs invalid JSON, just pass through to Anki since it will handle it
            return text

        self.config = Config(**json_config)
        logger.info("Config changed: %s", self.config)

        trmnl_plugins = []
        for plugin_config in self.config.plugins:
            trmnl_plugins.append(TRMNLPlugin(plugin_config))
        self.trmnl_plugins = trmnl_plugins

        schedule.cancel_job(self.trmnl_job)
        self.trmnl_job = schedule.every(int(self.config.refresh_rate)).seconds.do(self.refresh_trmnl)
        return text

    def refresh_trmnl(self):
        logger.info("Refreshing TRMNL")
        responses = []
        for plugin in self.trmnl_plugins:
            if plugin.config.enabled:
                responses.append(plugin.refresh_trmnl_plugin())
        return responses

    def refresh_trmnl_async(self) -> None:
        """
        Refreshes TRMNL using a background operation. Can only be called in the main thread.
        """

        def on_success(responses: list[requests.Response]):
            for response in responses:
                if not response.ok:
                    showInfo(f"Refreshing failed. "
                             f"{response.status_code}: {response.reason} {response.text}")

        op = QueryOp(
            parent=mw,
            op=lambda col: self.refresh_trmnl(),
            success=on_success
        )
        op.run_in_background()

    def shutdown(self) -> None:
        self.cease_continuous_run.set()
        self.initialized = False


trmnl_anki = TRMNLAnki()

# Add menu item to refresh TRMNL
action = QAction("Refresh TRMNL", mw)
qconnect(action.triggered, trmnl_anki.refresh_trmnl_async)
mw.form.menuTools.addAction(action)

# Refresh config on change
gui_hooks.addon_config_editor_will_update_json.append(trmnl_anki.refresh_config)
# Start plugin when fully loaded
gui_hooks.main_window_did_init.append(trmnl_anki.start)
# Shutdown on exit
gui_hooks.profile_will_close.append(trmnl_anki.shutdown)

logger.info(f"{__name__} loaded")
