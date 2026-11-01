"""Clean Windows installation smoke: import JSON, save, restart, and restore.

Uses a wholly synthetic sample profile, an isolated user-data directory, and no
network calls. The packaged executable is also checked independently by CI.
"""
import json
import tempfile
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

from jobscout import __version__
from jobscout.config import default_config, validate_config
from jobscout.desktop import Desktop
from jobscout.profiles import blank_profile


with tempfile.TemporaryDirectory(prefix="jobscout-first-use-") as directory:
    temp = Path(directory)
    app_home = temp / "first_time_user" / "JobScout"
    profile_source = temp / "example_search_profile.json"

    profile = blank_profile()
    profile.update(
        name="Synthetic Windows handoff", title_terms=["Senior Program Manager"],
        adjacent_title_terms=["Sales Operations Manager"], home_state="Washington",
        remote_only=True, require_full_time=True, exclude_people_management=True,
        capability_evidence={"ethics_compliance": "unassessed"},
    )
    config = default_config()
    config.update(
        profile=profile,
        boards=[{"company": "Example", "source": "greenhouse",
                 "board": "synthetic-board", "enabled": True}],
        local_regions=[], salary_floor=150000, salary_target=165000,
    )
    assert not validate_config(config)
    profile_source.write_text(json.dumps(config, indent=2), encoding="utf-8")
    assert not app_home.exists()

    root = tk.Tk()
    root.withdraw()
    app = Desktop(root, app_home)
    root.update()
    assert app.config["profile"]["name"] == "My search"
    assert not (app_home / "settings.json").exists()
    with patch("jobscout.desktop.filedialog.askopenfilename", return_value=str(profile_source)), \
         patch("jobscout.desktop.messagebox.askyesno", return_value=True), \
         patch("jobscout.desktop.messagebox.showerror", side_effect=AssertionError("Invalid import")):
        app.import_profile()
    assert app.config["profile"]["name"] == "Synthetic Windows handoff"
    assert app.config["profile"]["capability_evidence"]["ethics_compliance"] == "unassessed"
    assert app.path.is_file()
    assert app.path != profile_source
    assert app.path.parent.parent == app_home / "profiles"
    assert (app_home / "settings.json").is_file()
    assert app.save()
    stored_config = json.loads(app.path.read_text(encoding="utf-8"))
    assert stored_config["profile"]["remote_only"]
    assert stored_config["profile"]["home_state"] == "Washington"
    assert stored_config["salary_floor"] == 150000
    assert json.loads(profile_source.read_text(encoding="utf-8")) == config
    saved_path = app.path
    app.close()

    root = tk.Tk()
    root.withdraw()
    restored = Desktop(root, app_home)
    root.update()
    assert restored.path.resolve() == saved_path.resolve()
    assert restored.fields["name"].get() == "Synthetic Windows handoff"
    assert restored.config["profile"]["capability_evidence"]["ethics_compliance"] == "unassessed"
    assert restored.config["profile"]["adjacent_title_terms"] == ["Sales Operations Manager"]
    restored.close()

print(f"JobScout v{__version__}: clean installation/import/save/restart passed")
