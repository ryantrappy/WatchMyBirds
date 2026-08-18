# config.py
import os
from typing import Any

from dotenv import load_dotenv

from utils.settings import load_settings_yaml, save_settings_yaml

# Load environment variables from .env file once.
load_dotenv()


# Persistence for Secret Key
import secrets


def get_or_create_secret_key(config: dict[str, Any]) -> str:
    """
    Retrieves or generates a persistent secret key.
    Tries to store it in the state directory (/var/lib/watchmybirds/secret.key).
    Falls back to volatile key if filesystem is read-only or permission denied.
    """
    from pathlib import Path

    # Determine safe storage path
    # Priority: 1. OUTPUT_DIR (State Dir), 2. Local File
    output_dir = config.get("OUTPUT_DIR", "./data/output")
    secret_file = Path(output_dir) / "secret.key"

    # 1. Try to load existing
    if secret_file.exists():
        try:
            with open(secret_file) as f:
                key = f.read().strip()
                if len(key) >= 32:
                    return key
        except Exception as e:
            print(f"Warning: Could not read secret key from {secret_file}: {e}")

    # 2. Generate new
    new_key = secrets.token_hex(32)

    # 3. Try to save. Create with mode 0o600 at creation time (O_CREAT |
    # O_EXCL) so there is no window where the file exists with default
    # permissions before a follow-up chmod (TOCTOU). O_EXCL also makes a
    # concurrent first-run race safe: if another process created the file
    # first, fall back to reading theirs.
    try:
        secret_file.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(secret_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(new_key)
        print(f"Generated new persistent secret key at {secret_file}")
    except FileExistsError:
        try:
            existing = secret_file.read_text().strip()
            if len(existing) >= 32:
                return existing
        except Exception as e:
            import sys

            print(
                f"Warning: Could not read existing secret key from {secret_file}: {e}. Using volatile key.",
                file=sys.stderr,
            )
    except Exception as e:
        print(
            f"Warning: Could not save persistent secret key to {secret_file}: {e}. Using volatile key."
        )

    return new_key


_CONFIG = None

DEFAULTS = {
    "DEBUG_MODE": False,
    "OUTPUT_DIR": "./data/output",
    "INGEST_DIR": "./data/ingest",
    "VIDEO_SOURCE": "0",
    "LOCATION_DATA": {"latitude": 52.516, "longitude": 13.377},
    # Human-readable label for this WMB instance. Shown in the
    # appbar LED ticker so operators can tell which station they are
    # looking at when multiple browser tabs are open. Empty by default;
    # set in settings.yaml to e.g. "My Garden" and the marquee
    # picks it up on the next page reload.
    "STATION_NAME": "",
    "DETECTOR_MODEL_CHOICE": "yolo",
    # Detection-confidence floor is now model-owned (read from the active
    # model_metadata.json). CONFIDENCE_THRESHOLD_DETECTION has been retired.
    "SAVE_THRESHOLD": 0.65,
    "SAVE_THRESHOLD_MODE": "auto",  # "auto" (derived from model) or "manual"
    # Non-bird OD-confidence floor for CONFIRMED. Bird detections take a
    # separate track in scoring_pipeline.py (CLS-based) and are unaffected.
    # Tightens the gate against static-bbox night triggers (marten/cat/etc.)
    # without touching long-sitter Tauben/Eichelhäher.
    "NON_BIRD_CONFIRM_THRESHOLD": 0.80,
    # When True (default), non-bird detections below NON_BIRD_CONFIRM_THRESHOLD
    # are dropped pre-persist — no DB row, no crop, no derivative files. Flip
    # to False to keep them as UNCERTAIN rows for Phase-7 static-bbox cluster
    # analysis. Has no effect on bird detections.
    "NON_BIRD_DROP_BELOW_CONFIRM": True,
    # OD class-suppression list (bridge override). When non-empty, the
    # detector drops detections of these classes BEFORE the per-class
    # threshold filter, before NMS, before save / crop / CLS / scoring.
    # Dropped detections are audited to OUTPUT_DIR/logs/suppressed.jsonl
    # one JSON line per detection. The detector loader unions this with
    # the model's `detection.suppressed_classes` YAML block (when
    # present) — both sources are additive, never subtractive. Use this
    # key as the operator-facing knob when you need to suppress a class
    # without waiting for a new HF model release. Empty list = no
    # suppression (byte-identical to pre-suppression behaviour).
    "SUPPRESS_OD_CLASSES": [],
    # Burst-cap (Filter B): max detections persisted within
    # BURST_WINDOW_SECONDS. Protects the review queue from being flooded by
    # flocks of common species (issue #32). Set MAX_DETECTIONS_PER_BURST to
    # 0 to disable.
    "MAX_DETECTIONS_PER_BURST": 100,
    "BURST_WINDOW_SECONDS": 60.0,
    # Same-bird burst suppression (Filter B2): skip persisting a detection
    # when a near-identical bbox + species was already admitted in the last
    # SAME_BIRD_BURST_WINDOW_SECONDS. Targets the "bird sits 30s at feeder,
    # gets detected every 2s, all 15 frames land in DB" pattern that
    # floods the review queue with same-bird-different-frame duplicates.
    # Disable by setting SAME_BIRD_BURST_WINDOW_SECONDS to 0.
    "SAME_BIRD_BURST_IOU": 0.6,
    "SAME_BIRD_BURST_WINDOW_SECONDS": 15.0,
    "DETECTION_INTERVAL_SECONDS": 2.0,
    "MODEL_BASE_PATH": "./data/models",
    "BBOX_QUALITY_THRESHOLD": 0.40,
    "SPECIES_CONF_THRESHOLD": 0.70,
    "UNKNOWN_SCORE_THRESHOLD": 0.60,
    "STREAM_FPS": 5.0,
    "STREAM_FPS_CAPTURE": 5.0,
    "STREAM_WIDTH_OUTPUT_RESIZE": 640,
    "DAY_AND_NIGHT_CAPTURE": True,
    "DAY_AND_NIGHT_CAPTURE_LOCATION": "Berlin",
    # Diagnostic overlay drawn over the live stream (auto-PTZ target box
    # + tracking state). Off by default; gated behind moderator auth.
    "PTZ_TRACKING_OVERLAY_ENABLED": False,
    # OD night-pause offsets (apply when DAY_AND_NIGHT_CAPTURE is False).
    # See utils/sun_times.py for sign convention. Defaults widen the
    # active daytime window past nautical twilight: OD keeps running 30
    # min past nautical dusk (late-active species: blackbird, thrush)
    # and resumes 45 min before nautical dawn (dawn chorus: robin, wren).
    # Mode is "nautical" (sun to -12 deg) rather than "civil" (-6 deg)
    # so the active window covers the maximum useful bird-activity span;
    # IR-capable cameras still resolve birds at that light level.
    "OD_NIGHT_START_OFFSET_MIN": 30,
    "OD_NIGHT_END_OFFSET_MIN": -45,
    "OD_NIGHT_TWILIGHT_MODE": "nautical",
    # Station-adaptive gallery quality floor. The nightly sharpness job
    # hides the bottom GALLERY_QUALITY_BOTTOM_PCT percent of crops (by
    # sharpness_score) from gallery thumbnails, relative to THIS
    # station's own distribution — never a fixed pixel threshold, so it
    # stays portable across cameras/setups. 0 disables the cut entirely.
    # The floor only applies once at least GALLERY_QUALITY_MIN_SCORED
    # crops have a score, so a small/fresh station never hides birds.
    "GALLERY_QUALITY_BOTTOM_PCT": 15,
    "GALLERY_QUALITY_MIN_SCORED": 200,
    "CPU_LIMIT": 0,
    "TELEGRAM_COOLDOWN": 3600.0,
    "EDIT_PASSWORD": "watchmybirds",
    "TELEGRAM_ENABLED": False,
    "GALLERY_DISPLAY_THRESHOLD": 0.1,
    "TELEGRAM_BOT_TOKEN": "",
    "TELEGRAM_CHAT_ID": "",
    "TELEGRAM_REPORT_TIME": "21:00",
    "TELEGRAM_MODE": "off",  # "off", "live", "daily", "interval", "new_species_only"
    "TELEGRAM_REPORT_INTERVAL_HOURS": 1,
    # Drop species from daily / interval reports when fewer than this many
    # CONFIRMED observations exist in the report window. The gallery already
    # hides single-frame uncertain detections; this stops the same low-evidence
    # species from leaking into Telegram via a single accidentally-confirmed
    # frame. 1 = keep all confirmed species; raise to 2 or 3 for stricter
    # rarity filtering.
    "TELEGRAM_MIN_CONFIRMED_OBSERVATIONS": 1,
    # Reserved aesthetic-score floor for future per-photo filtering inside
    # the daily Telegram report. Currently NOT applied (the previous
    # implementation treated it as a species-level gate, which made
    # taggable species vanish on days when none cleared the floor —
    # see utils/daily_report.py:_fetch_species_best_photos for the
    # full rationale). The constant stays so we can re-introduce it as
    # a per-photo floor later (e.g. "use detector_confidence ranking
    # instead of aesthetic_score when no photo of the species clears
    # this threshold"). Today it is purely informational.
    "TELEGRAM_MIN_AESTHETIC_SCORE": 0.10,
    # Nightly aesthetic auto-tagger (CLIP-based). The scheduler in
    # web/services/aesthetic_tag_scheduler.py reads these. Time is HH:MM
    # 24h, default 02:10 (low-traffic). Disable on slim images / low-RAM
    # devices that can't load the CLIP weights (~700 MB transient).
    "AESTHETIC_TAG_ENABLED": True,
    "AESTHETIC_TAG_TIME": "02:10",
    # CPU-friendliness knobs for the in-process aesthetic tagger. Both
    # are read live in web/services/aesthetic_tag_scheduler.py and
    # surfaced to the worker via env vars (WMB_AESTHETIC_NICE,
    # WMB_AESTHETIC_TORCH_THREADS) on each run.
    #
    #   AESTHETIC_TAGGER_NICE — UNIX nice() delta applied at worker
    #     start. 0..19; higher = lower priority. 10 (default) keeps the
    #     live OD pipeline responsive on a Pi 5 with 4 cores. Set to 0
    #     to opt out (default OS scheduling).
    #
    #   AESTHETIC_TAGGER_TORCH_THREADS — caps torch.set_num_threads()
    #     in the worker. 0 = let torch decide (use all cores), 1-2 keeps
    #     headroom for OD at the cost of slower per-image CLIP
    #     inference. Defaults to 2 — on a 4-core Pi this halves CLIP's
    #     CPU footprint, leaving 2 cores for OD/CLS.
    "AESTHETIC_TAGGER_NICE": 10,
    "AESTHETIC_TAGGER_TORCH_THREADS": 2,
    # Pre-Telegram bridge cap: maximum aesthetic-score inferences per CLS
    # species during a bridge run. The bridge fills the gap between the
    # 02:10 nightly tagger and the report send (~21:00) so today's
    # detections have aesthetic scores in time. Without a cap, the bridge
    # has to score every unscored detection of the day — that takes
    # ~1.0s/image on the Pi 5 with live OD competing, which can stretch
    # the bridge run past the report-send window on busy days. Capping
    # per species (ranked by detector score, bbox quality, created_at)
    # keeps the run bounded while still giving the report a fair sample
    # across species. 0 disables the cap (scores everything). Only the
    # bridge path honours this; the nightly run still scores everything.
    "AESTHETIC_BRIDGE_PER_SPECIES_CAP": 8,
    "DEVICE_NAME": "",
    "EXIF_GPS_ENABLED": True,
    "INBOX_REQUIRE_EXIF_DATETIME": True,
    "INBOX_REQUIRE_EXIF_GPS": True,
    # When True, human-facing downloads (detail-modal "Download" and the
    # edit-page batch ZIP) serve a COPY with species/location/provenance
    # burned into XMP at current DB state, never touching the immutable
    # original. Off restores the verbatim-original download. Runtime
    # (live-editable in Settings), not a boot ENV like EXIF_GPS_ENABLED.
    "EXPORT_BURN_IN_METADATA": True,
    # When True, every "Approve event" click in the review queue also
    # marks its detections as pending training-export. Off by default
    # so the export pool only grows deliberately.
    "TRAINING_EXPORT_AUTO_OPT_IN": False,
    # Artifact retention (full-resolution originals only); ships OFF.
    # RETENTION_POSTURE is the authority; the booleans below are derived from
    # it at decision time (resolve_posture_settings) and kept for backcompat.
    "RETENTION_POSTURE": "conservative",
    "RETENTION_ENABLED": False,
    "RETENTION_DAYS": 90,
    "RETENTION_PROTECT_FAVORITES": True,
    "RETENTION_PROTECT_UNREVIEWED": True,
    "MOTION_DETECTION_ENABLED": False,
    "MOTION_SENSITIVITY": 500,
    "CAMERA_URL": "",
    "ENABLE_NIGHTLY_DEEP_SCAN": False,
    "STREAM_SOURCE_MODE": "auto",  # "auto", "relay", "direct"
    "GO2RTC_STREAM_NAME": "camera",
    "GO2RTC_API_BASE": "http://127.0.0.1:1984",
    "GO2RTC_CONFIG_PATH": "./go2rtc.yaml",
    "SPECIES_COMMON_NAME_LOCALE": "DE",
    # --- Companion v1 backend (default OFF) ---
    # Backend-only in v1. All keys default conservative so a fresh
    # install never reaches an LLM runtime by accident.
    #
    # The default backend is `llama_cpp` (in-process GGUF via
    # llama-cpp-python). Ollama remains an alternative for hosts that
    # already serve the model via a local daemon. Switching the backend
    # takes effect on next boot.
    "COMPANION_ENABLED": False,
    "COMPANION_INFERENCE_BACKEND": "llama_cpp",  # "llama_cpp" | "ollama"
    # llama_cpp adapter knobs:
    "COMPANION_LLAMA_CPP_GGUF_PATH": "",  # empty -> auto-pick newest .gguf under <models>/companion/
    "COMPANION_LLAMA_CPP_N_CTX": 4096,
    "COMPANION_LLAMA_CPP_N_THREADS": 0,  # 0 -> library default (typically all cores)
    # ollama adapter knobs:
    "COMPANION_OLLAMA_URL": "http://127.0.0.1:11434",
    "COMPANION_OLLAMA_MODEL_TAG": "wmb-companion:1b-q4",
    # shared:
    "COMPANION_INFERENCE_TIMEOUT_S": 60,
    "COMPANION_PAUSE_DETECTION_DURING_INFERENCE": True,
    "COMPANION_LANGUAGE": "de",
    "COMPANION_TONE": "adult_dry",
    # --- Anonymous opt-in usage heartbeat (default OFF) ---
    # See web/services/telemetry_service.py and docs/PRIVACY.md.
    # The toggle is the ONLY enable surface; there is no banner or
    # popup. Endpoint is overridable for self-hosters / privacy-paranoid
    # operators (point it at /dev/null or a self-hosted Worker).
    "telemetry_enabled": False,
    # Canonical default lives in web/services/telemetry_service.DEFAULT_TELEMETRY_ENDPOINT;
    # kept as a literal here to avoid a config -> web.services import cycle. Keep in sync.
    "telemetry_endpoint": (
        "https://watchmybirds-telemetry.wmb-infra.workers.dev/v1/heartbeat"
    ),
    "telemetry_installation_id": "",  # lazily generated on first opt-in
}

RUNTIME_KEYS = {
    "EXPORT_BURN_IN_METADATA",
    "RETENTION_POSTURE",
    "RETENTION_ENABLED",
    "RETENTION_DAYS",
    "RETENTION_PROTECT_FAVORITES",
    "RETENTION_PROTECT_UNREVIEWED",
    "SAVE_THRESHOLD",
    "SAVE_THRESHOLD_MODE",
    "NON_BIRD_CONFIRM_THRESHOLD",
    "NON_BIRD_DROP_BELOW_CONFIRM",
    "DETECTION_INTERVAL_SECONDS",
    "DAY_AND_NIGHT_CAPTURE",
    "DAY_AND_NIGHT_CAPTURE_LOCATION",
    "PTZ_TRACKING_OVERLAY_ENABLED",
    "STREAM_FPS",
    "STREAM_FPS_CAPTURE",
    "BBOX_QUALITY_THRESHOLD",
    "SPECIES_CONF_THRESHOLD",
    "UNKNOWN_SCORE_THRESHOLD",
    "TELEGRAM_COOLDOWN",
    "EDIT_PASSWORD",
    # TELEGRAM_ENABLED is derived from TELEGRAM_MODE (see _coerce_config_types)
    # and deliberately excluded from RUNTIME_KEYS so form POSTs can't clobber
    # the derived value. The notifier still reads it, and _coerce_config_types
    # keeps it in sync whenever settings change.
    "GALLERY_DISPLAY_THRESHOLD",
    "VIDEO_SOURCE",
    "CAMERA_URL",
    "STREAM_SOURCE_MODE",
    # NEW
    "DEBUG_MODE",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "TELEGRAM_REPORT_TIME",
    "TELEGRAM_MODE",
    "TELEGRAM_REPORT_INTERVAL_HOURS",
    "TELEGRAM_MIN_CONFIRMED_OBSERVATIONS",
    "TELEGRAM_MIN_AESTHETIC_SCORE",
    "AESTHETIC_TAG_ENABLED",
    "AESTHETIC_TAG_TIME",
    "AESTHETIC_TAGGER_NICE",
    "AESTHETIC_TAGGER_TORCH_THREADS",
    "AESTHETIC_BRIDGE_PER_SPECIES_CAP",
    # Companion runtime knobs. Enable / pause / language / tone are
    # safe to flip live; backend, GGUF path, n_ctx, n_threads, the URL
    # and model tag re-bind on next service init (read once when
    # constructing the adapter at process boot, not on every API call),
    # so those changes need a restart — same as the existing telemetry
    # endpoint key.
    "COMPANION_ENABLED",
    "COMPANION_PAUSE_DETECTION_DURING_INFERENCE",
    "COMPANION_LANGUAGE",
    "COMPANION_TONE",
    "COMPANION_INFERENCE_TIMEOUT_S",
    "COMPANION_INFERENCE_BACKEND",
    "COMPANION_LLAMA_CPP_GGUF_PATH",
    "COMPANION_LLAMA_CPP_N_CTX",
    "COMPANION_LLAMA_CPP_N_THREADS",
    "COMPANION_OLLAMA_URL",
    "COMPANION_OLLAMA_MODEL_TAG",
    "DEVICE_NAME",
    "LOCATION_DATA",
    "EXIF_GPS_ENABLED",
    "INBOX_REQUIRE_EXIF_DATETIME",
    "INBOX_REQUIRE_EXIF_GPS",
    "MOTION_DETECTION_ENABLED",
    "MOTION_SENSITIVITY",
    "SPECIES_COMMON_NAME_LOCALE",
    "TRAINING_EXPORT_AUTO_OPT_IN",
    # Burst-cap (Filter B) keys. Both are read live every detection cycle
    # from self.config in DetectionManager._burst_admit(), so UI changes
    # take effect on the next detection — no restart needed.
    "MAX_DETECTIONS_PER_BURST",
    "BURST_WINDOW_SECONDS",
    # STREAM_WIDTH_OUTPUT_RESIZE is read once at mount time in
    # web_interface.py, so changing it here takes effect after the
    # next restart. It's still in RUNTIME_KEYS because the Settings
    # form exposes the field — without this entry, Apply would
    # silently drop the new value even though it was committed to
    # the form. See validator in _validate_value.
    "STREAM_WIDTH_OUTPUT_RESIZE",
}

BOOT_KEYS = set(DEFAULTS.keys()) - RUNTIME_KEYS


def _load_config() -> dict[str, Any]:
    """Loads configuration from environment variables and YAML."""
    config = dict(DEFAULTS)

    # Env overrides
    if os.getenv("DEBUG_MODE") is not None:
        config["DEBUG_MODE"] = os.getenv("DEBUG_MODE")
    if os.getenv("OUTPUT_DIR") is not None:
        config["OUTPUT_DIR"] = os.getenv("OUTPUT_DIR")
    if os.getenv("INGEST_DIR") is not None:
        config["INGEST_DIR"] = os.getenv("INGEST_DIR")
    if os.getenv("VIDEO_SOURCE") is not None:
        config["VIDEO_SOURCE"] = os.getenv("VIDEO_SOURCE")
    if os.getenv("CAMERA_URL") is not None:
        config["CAMERA_URL"] = os.getenv("CAMERA_URL")
    if os.getenv("STREAM_SOURCE_MODE") is not None:
        config["STREAM_SOURCE_MODE"] = os.getenv("STREAM_SOURCE_MODE")
    if os.getenv("GO2RTC_STREAM_NAME") is not None:
        config["GO2RTC_STREAM_NAME"] = os.getenv("GO2RTC_STREAM_NAME")
    if os.getenv("GO2RTC_API_BASE") is not None:
        config["GO2RTC_API_BASE"] = os.getenv("GO2RTC_API_BASE")
    if os.getenv("GO2RTC_CONFIG_PATH") is not None:
        config["GO2RTC_CONFIG_PATH"] = os.getenv("GO2RTC_CONFIG_PATH")

    location_str = os.getenv("LOCATION_DATA")
    if location_str:
        config["LOCATION_DATA"] = location_str

    for key in (
        "DETECTOR_MODEL_CHOICE",
        "MODEL_BASE_PATH",
        "DAY_AND_NIGHT_CAPTURE_LOCATION",
        "EDIT_PASSWORD",
    ):
        if os.getenv(key) is not None:
            config[key] = os.getenv(key)

    if os.getenv("SPECIES_COMMON_NAME_LOCALE") is not None:
        config["SPECIES_COMMON_NAME_LOCALE"] = os.getenv("SPECIES_COMMON_NAME_LOCALE")

    for key in (
        "SAVE_THRESHOLD",
        "NON_BIRD_CONFIRM_THRESHOLD",
        "DETECTION_INTERVAL_SECONDS",
        "BBOX_QUALITY_THRESHOLD",
        "SPECIES_CONF_THRESHOLD",
        "UNKNOWN_SCORE_THRESHOLD",
        "STREAM_FPS",
        "STREAM_FPS_CAPTURE",
        "TELEGRAM_COOLDOWN",
        "GALLERY_DISPLAY_THRESHOLD",
        "MOTION_SENSITIVITY",
    ):
        if os.getenv(key) is not None:
            config[key] = os.getenv(key)

    if os.getenv("STREAM_WIDTH_OUTPUT_RESIZE") is not None:
        config["STREAM_WIDTH_OUTPUT_RESIZE"] = os.getenv("STREAM_WIDTH_OUTPUT_RESIZE")
    if os.getenv("DAY_AND_NIGHT_CAPTURE") is not None:
        config["DAY_AND_NIGHT_CAPTURE"] = os.getenv("DAY_AND_NIGHT_CAPTURE")
    if os.getenv("MOTION_DETECTION_ENABLED") is not None:
        config["MOTION_DETECTION_ENABLED"] = os.getenv("MOTION_DETECTION_ENABLED")
    if os.getenv("EXIF_GPS_ENABLED") is not None:
        config["EXIF_GPS_ENABLED"] = os.getenv("EXIF_GPS_ENABLED")
    if os.getenv("TELEGRAM_ENABLED") is not None:
        config["TELEGRAM_ENABLED"] = os.getenv("TELEGRAM_ENABLED")
    if os.getenv("ENABLE_NIGHTLY_DEEP_SCAN") is not None:
        config["ENABLE_NIGHTLY_DEEP_SCAN"] = os.getenv("ENABLE_NIGHTLY_DEEP_SCAN")
    if os.getenv("CPU_LIMIT") is not None:
        config["CPU_LIMIT"] = os.getenv("CPU_LIMIT")

    # Telegram Credentials from ENV
    if os.getenv("TELEGRAM_BOT_TOKEN") is not None:
        config["TELEGRAM_BOT_TOKEN"] = os.getenv("TELEGRAM_BOT_TOKEN")
    if os.getenv("TELEGRAM_CHAT_ID") is not None:
        config["TELEGRAM_CHAT_ID"] = os.getenv("TELEGRAM_CHAT_ID")
    if os.getenv("TELEGRAM_REPORT_TIME") is not None:
        config["TELEGRAM_REPORT_TIME"] = os.getenv("TELEGRAM_REPORT_TIME")
    if os.getenv("TELEGRAM_MODE") is not None:
        config["TELEGRAM_MODE"] = os.getenv("TELEGRAM_MODE")
    if os.getenv("TELEGRAM_MIN_AESTHETIC_SCORE") is not None:
        config["TELEGRAM_MIN_AESTHETIC_SCORE"] = os.getenv(
            "TELEGRAM_MIN_AESTHETIC_SCORE"
        )
    if os.getenv("AESTHETIC_TAG_ENABLED") is not None:
        config["AESTHETIC_TAG_ENABLED"] = os.getenv("AESTHETIC_TAG_ENABLED")
    if os.getenv("AESTHETIC_TAG_TIME") is not None:
        config["AESTHETIC_TAG_TIME"] = os.getenv("AESTHETIC_TAG_TIME")
    if os.getenv("TELEGRAM_REPORT_INTERVAL_HOURS") is not None:
        config["TELEGRAM_REPORT_INTERVAL_HOURS"] = os.getenv(
            "TELEGRAM_REPORT_INTERVAL_HOURS"
        )
    if os.getenv("TELEGRAM_MIN_CONFIRMED_OBSERVATIONS") is not None:
        config["TELEGRAM_MIN_CONFIRMED_OBSERVATIONS"] = os.getenv(
            "TELEGRAM_MIN_CONFIRMED_OBSERVATIONS"
        )
    if os.getenv("DEVICE_NAME") is not None:
        config["DEVICE_NAME"] = os.getenv("DEVICE_NAME")

    # YAML runtime overrides
    yaml_settings = load_settings_yaml(str(config["OUTPUT_DIR"]))

    if (
        "MAX_FPS_DETECTION" in yaml_settings
        and "DETECTION_INTERVAL_SECONDS" not in yaml_settings
    ):
        try:
            legacy_fps = float(yaml_settings["MAX_FPS_DETECTION"])
            if legacy_fps > 0:
                config["DETECTION_INTERVAL_SECONDS"] = 1.0 / legacy_fps
        except (TypeError, ValueError):
            # Legacy YAML key unparseable; ignore and keep default.
            pass

    for key, value in yaml_settings.items():
        if key in RUNTIME_KEYS:
            config[key] = value

    # Telemetry keys persist via a dedicated endpoint (/api/v1/settings/telemetry)
    # and deliberately bypass RUNTIME_KEYS so the generic Settings form can't
    # touch them. But they MUST be loaded from YAML at boot — otherwise the
    # toggle "on" state is forgotten on every service restart (the loader
    # would silently drop telemetry_enabled=true from YAML, so the scheduler
    # logged "started" but never actually sent).
    for key in ("telemetry_enabled", "telemetry_endpoint", "telemetry_installation_id"):
        if key in yaml_settings:
            config[key] = yaml_settings[key]

    # Legacy migration: users upgrading from pre-TELEGRAM_MODE builds have a
    # bare `TELEGRAM_ENABLED: true/false` in settings.yaml and no mode key.
    # Translate that to the closest equivalent so live alerts don't silently
    # stop after upgrade.
    #
    # Guard: only fire when `TELEGRAM_ENABLED` lives inside the YAML
    # itself. The previous version looked at any source of
    # `TELEGRAM_ENABLED` and would flip the mode to "live" on every
    # Docker rebuild where the compose file set TELEGRAM_ENABLED=True
    # via env — even after the operator had explicitly chosen
    # TELEGRAM_MODE=off in the UI (the choice persisted into YAML but
    # the old save logic dropped default values, so the mode key was
    # absent on the next boot).
    if "TELEGRAM_MODE" not in yaml_settings and "TELEGRAM_ENABLED" in yaml_settings:
        legacy_enabled = yaml_settings.get("TELEGRAM_ENABLED")
        if legacy_enabled is not None:
            config["TELEGRAM_MODE"] = "live" if _coerce_bool(legacy_enabled) else "off"

    if os.getenv("MAX_FPS_DETECTION") and not os.getenv("DETECTION_INTERVAL_SECONDS"):
        try:
            legacy_fps = float(os.getenv("MAX_FPS_DETECTION"))
            if legacy_fps > 0:
                config["DETECTION_INTERVAL_SECONDS"] = 1.0 / legacy_fps
        except (TypeError, ValueError):
            # Legacy env var unparseable; ignore and keep default.
            pass

    # One-time migration: derive CAMERA_URL from legacy VIDEO_SOURCE when needed.
    _migrate_camera_url(config)
    _coerce_config_types(config)
    # Load Persistent Secret Key (Late Binding to use populated config)
    # Allows sessions to survive restarts
    config["SECRET_KEY"] = get_or_create_secret_key(config)

    return config


def ensure_app_directories(config_dict: dict[str, Any] | None = None) -> None:
    """
    Creates necessary directories based on configuration.
    Uses relative paths by default for portability.
    """
    if config_dict is None:
        config_dict = get_config()

    dirs_to_create = [
        config_dict["OUTPUT_DIR"],
        config_dict["INGEST_DIR"],
        config_dict["MODEL_BASE_PATH"],
        os.path.join(config_dict["OUTPUT_DIR"], "logs"),  # Ensure log dir exists
    ]

    for path in dirs_to_create:
        try:
            # path is relative or absolute, makedirs handles both.
            # Convert to absolute for safety/logging
            abs_path = os.path.abspath(path)
            os.makedirs(abs_path, exist_ok=True)
            # update config with absolute path to avoid ambiguity later
            # (optional, but safer if other modules do strictly path manipulations)
            # However, config object is global. Modifying it here is good.
        except Exception as e:
            # We cannot log easily here if logs dir creation fails,
            # so we print to stderr as last resort
            import sys

            print(f"CRITICAL: Failed to create directory {path}: {e}", file=sys.stderr)


def get_config() -> dict[str, Any]:
    """Returns the loaded configuration."""
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = _load_config()
    return _CONFIG


def probe_go2rtc(
    api_base: str = "http://127.0.0.1:1984",
    timeout_sec: float = 2.0,
) -> bool:
    """Return True if go2rtc API responds.

    Default timeout raised to 2.0s to accommodate Docker bridge-network
    DNS resolution which can take 200-500ms on first lookup.
    """
    import logging
    import urllib.request

    url = f"{api_base.rstrip('/')}/api/streams"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            return resp.status == 200
    except Exception as exc:
        logging.getLogger(__name__).debug("probe_go2rtc failed for %s: %s", url, exc)
        return False


def verify_go2rtc_stream_ready(
    api_base: str = "http://127.0.0.1:1984",
    stream_name: str = "camera",
    timeout_sec: float = 2.0,
) -> bool:
    """
    Return True when go2rtc has the stream configured.

    This intentionally checks configuration presence, not active producers.
    """
    import json
    import urllib.request

    url = f"{api_base.rstrip('/')}/api/streams"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
            if resp.status != 200:
                return False
            data = json.loads(resp.read().decode("utf-8"))
            return isinstance(data, dict) and stream_name in data
    except Exception:
        return False


def resolve_effective_sources(config: dict) -> dict:
    """
    Resolve effective runtime source for detection streaming.

    Returns keys: video_source, effective_mode, reason.
    """
    camera_url = config.get("CAMERA_URL", "")
    mode = config.get("STREAM_SOURCE_MODE", "auto")
    stream_name = config.get("GO2RTC_STREAM_NAME", "camera")
    api_base = config.get("GO2RTC_API_BASE", "http://127.0.0.1:1984")

    try:
        from urllib.parse import urlparse

        relay_host = urlparse(api_base).hostname or "127.0.0.1"
    except Exception:
        relay_host = "127.0.0.1"
    relay_url = f"rtsp://{relay_host}:8554/{stream_name}"

    if mode == "relay":
        return {
            "video_source": relay_url,
            "effective_mode": "relay",
            "reason": "mode=relay (forced)",
        }
    if mode == "direct":
        return {
            "video_source": camera_url,
            "effective_mode": "direct",
            "reason": "mode=direct (forced)",
        }

    # auto mode
    if (
        camera_url
        and probe_go2rtc(api_base)
        and verify_go2rtc_stream_ready(api_base, stream_name)
    ):
        return {
            "video_source": relay_url,
            "effective_mode": "relay",
            "reason": "mode=auto, go2rtc healthy + stream configured -> relay",
        }

    if not camera_url:
        reason = "mode=auto, CAMERA_URL empty -> direct (no source)"
    elif not probe_go2rtc(api_base):
        reason = "mode=auto, go2rtc unavailable -> direct"
    else:
        reason = "mode=auto, go2rtc stream not configured -> direct"

    return {
        "video_source": camera_url,
        "effective_mode": "direct",
        "reason": reason,
    }


def ensure_go2rtc_stream_synced(config: dict, *, with_retry: bool = False) -> None:
    """Proactively sync CAMERA_URL into go2rtc before resolving stream sources.

    This breaks the chicken-and-egg problem: ``resolve_effective_sources()``
    needs go2rtc to have the stream configured, but the old post-resolve sync
    only ran when the resolver had *already* chosen relay mode – which it
    never did on a fresh image because go2rtc had an empty source list.

    Safe to call at any point; silently returns when preconditions are not met
    (no camera URL, go2rtc unreachable).

    Drift-protection: this sync also runs when ``STREAM_SOURCE_MODE=direct``.
    Even in direct mode, the browser stream page may still rely on go2rtc, so
    keeping go2rtc's upstream aligned with CAMERA_URL prevents stale sources.

    Args:
        config: The application config dict (must already be loaded/coerced).
        with_retry: If True, use retry logic for the reload call (boot path).
    """
    import logging

    log = logging.getLogger(__name__)

    camera_url = config.get("CAMERA_URL", "")

    # Nothing to sync if there is no camera URL.
    if not camera_url:
        return

    api_base = config.get("GO2RTC_API_BASE", "http://127.0.0.1:1984")

    # Only sync if go2rtc is actually reachable.
    if not probe_go2rtc(api_base):
        log.debug("ensure_go2rtc_stream_synced: go2rtc unreachable, skipping")
        return

    try:
        from utils.go2rtc_config import (
            reload_go2rtc_stream,
            reload_go2rtc_stream_with_retry,
            sync_camera_stream_source,
        )

        go2rtc_path = config.get("GO2RTC_CONFIG_PATH", "./go2rtc.yaml")
        stream_name = config.get("GO2RTC_STREAM_NAME", "camera")

        sync_ok = sync_camera_stream_source(go2rtc_path, camera_url, stream_name)
        if not sync_ok:
            log.warning(
                "go2rtc pre-sync config write returned false (path=%s)",
                go2rtc_path,
            )

        # Push the source into the running go2rtc process.
        if with_retry:
            reload_go2rtc_stream_with_retry(
                api_base=api_base,
                stream_name=stream_name,
                camera_url=camera_url,
            )
        else:
            reload_go2rtc_stream(
                api_base=api_base,
                stream_name=stream_name,
                camera_url=camera_url,
            )
    except Exception as exc:
        log.warning("go2rtc pre-sync failed: %s", exc)


def _migrate_camera_url(config: dict) -> None:
    """Derive CAMERA_URL from legacy VIDEO_SOURCE when CAMERA_URL is empty."""
    camera_url = config.get("CAMERA_URL", "")
    if camera_url:
        return

    video_source = str(config.get("VIDEO_SOURCE", "0")).strip()
    if not video_source or video_source == "0":
        return

    # Legacy relay source; try to read real camera source from go2rtc config.
    if "127.0.0.1:8554" in video_source or "localhost:8554" in video_source:
        try:
            from utils.go2rtc_config import read_camera_stream_source

            go2rtc_path = config.get("GO2RTC_CONFIG_PATH", "./go2rtc.yaml")
            stream_name = config.get("GO2RTC_STREAM_NAME", "camera")
            real_url = read_camera_stream_source(go2rtc_path, stream_name)
            if real_url:
                config["CAMERA_URL"] = real_url
        except (OSError, ImportError, KeyError):
            # go2rtc.yaml missing/unreadable; CAMERA_URL stays as configured.
            pass
        return

    config["CAMERA_URL"] = video_source


def _coerce_config_types(config: dict[str, Any]) -> None:
    """Validates and enforces expected types for core keys."""
    # Booleans
    for key in (
        "DEBUG_MODE",
        "DAY_AND_NIGHT_CAPTURE",
        "TELEGRAM_ENABLED",
        "EXIF_GPS_ENABLED",
        "INBOX_REQUIRE_EXIF_DATETIME",
        "INBOX_REQUIRE_EXIF_GPS",
        "MOTION_DETECTION_ENABLED",
        "ENABLE_NIGHTLY_DEEP_SCAN",
        "NON_BIRD_DROP_BELOW_CONFIRM",
        "RETENTION_ENABLED",
        "RETENTION_PROTECT_FAVORITES",
        "RETENTION_PROTECT_UNREVIEWED",
    ):
        if key in config:
            config[key] = _coerce_bool(config.get(key))

    # RETENTION_DAYS: positive int, capped at 3650 (~10 years).
    try:
        ret_days = int(float(config.get("RETENTION_DAYS", 90)))
    except (TypeError, ValueError):
        ret_days = 90
    config["RETENTION_DAYS"] = max(1, min(3650, ret_days))

    # RETENTION_POSTURE: normalize; unknown -> conservative (safe default).
    posture = str(config.get("RETENTION_POSTURE", "conservative")).strip().lower()
    config["RETENTION_POSTURE"] = (
        posture if posture in ("off", "conservative", "reclaim") else "conservative"
    )

    # LOCATION_DATA: parse "lat, lon" strings into dict
    location_val = config.get("LOCATION_DATA")
    if isinstance(location_val, str):
        try:
            lat_str, lon_str = location_val.split(",")
            config["LOCATION_DATA"] = {
                "latitude": float(lat_str),
                "longitude": float(lon_str),
            }
        except Exception:
            config["LOCATION_DATA"] = DEFAULTS["LOCATION_DATA"]

    # VIDEO_SOURCE: int for webcams, string otherwise (startup-only per locked decision).
    source = config.get("VIDEO_SOURCE", "0")
    try:
        if str(source).isdigit():
            config["VIDEO_SOURCE"] = int(source)
    except Exception:
        config["VIDEO_SOURCE"] = source

    # STREAM_FPS / STREAM_FPS_CAPTURE: Force safe defaults if 0.0 (legacy unthrottled)
    try:
        stream_fps = float(config.get("STREAM_FPS", 5.0))
        # 0.0 is legacy "unlimited" which kills the Pi. Force to 5.0.
        config["STREAM_FPS"] = stream_fps if stream_fps > 0.1 else 5.0
    except Exception:
        config["STREAM_FPS"] = 5.0

    try:
        stream_fps_capture = float(config.get("STREAM_FPS_CAPTURE", 5.0))
        # 0.0 is legacy "unlimited". Force to 5.0.
        config["STREAM_FPS_CAPTURE"] = (
            stream_fps_capture if stream_fps_capture > 0.1 else 5.0
        )
    except Exception:
        config["STREAM_FPS_CAPTURE"] = 5.0

    # CPU_LIMIT: 0 = disabled (no cpu pinning), positive int = limit cores
    try:
        cpu_limit = int(float(config.get("CPU_LIMIT", 0)))
        config["CPU_LIMIT"] = max(0, cpu_limit)
    except Exception:
        config["CPU_LIMIT"] = 0

    # Numeric values
    for key in (
        "SAVE_THRESHOLD",
        "NON_BIRD_CONFIRM_THRESHOLD",
        "BBOX_QUALITY_THRESHOLD",
        "SPECIES_CONF_THRESHOLD",
        "UNKNOWN_SCORE_THRESHOLD",
        "GALLERY_DISPLAY_THRESHOLD",
    ):
        try:
            val = float(config.get(key, DEFAULTS.get(key, 0.55)))
            config[key] = max(0.0, min(1.0, val))
        except Exception:
            config[key] = DEFAULTS.get(key, 0.55)

    # Integer values
    for key in ("MOTION_SENSITIVITY",):
        try:
            val = int(float(config.get(key, DEFAULTS.get(key, 500)))
