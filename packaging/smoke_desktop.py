"""Fresh Windows profile: save, scan, salary correction, restart, and folder action."""
import json
import tempfile
import tkinter as tk
from pathlib import Path
from unittest.mock import patch

from jobscout.app import run_once
from jobscout.desktop import Desktop
from jobscout.paths import RuntimePaths

with tempfile.TemporaryDirectory() as tmp:
    home = Path(tmp)
    root = tk.Tk()
    app = Desktop(root, home)
    root.update()
    assert app.tabs.tab(app.tabs.select(), 'text') == 'Start here'
    app.fields['name'].set('Synthetic smoke test')
    app.fields['title_terms'].set('Research Director')
    app.fields['local_regions'].set('Example City')
    app.config['boards'] = [dict(company='Example', source='greenhouse', board='example')]
    assert app.save()
    saved_path = app.path
    with patch.dict('jobscout.sources.SOURCE_FUNCS', greenhouse=lambda *a: []):
        run_once(RuntimePaths(saved_path.parent), quiet=True)
    app.refresh_review()
    assert 'UTC' in app.last_scan.get()
    app.salary_url.set('https://example.org/jobs/1')
    app.salary_mode.set('Use confirmed annual USD base range')
    app.salary_min.set('210000')
    app.salary_max.set('230000')
    app.save_salary()
    assert app.config['profile']['salary_overrides']['https://example.org/jobs/1']['annual_min'] == 210000
    with patch('os.startfile') as opener:
        app.results_folder()
        opener.assert_called_once()
    # At the minimum size, long forms remain reachable by their scrollbars.
    root.geometry('850x650')
    for index in [1, 4]:
        app.tabs.select(index)
        root.update()
        page = app.tabs.nametowidget(app.tabs.select())
        canvas = next(w for w in page.winfo_children() if isinstance(w, tk.Canvas))
        assert canvas.cget('scrollregion')
        canvas.yview_moveto(1.0)
        root.update()
        assert canvas.yview()[1] > 0.99
    app.close()
    root = tk.Tk()
    restored = Desktop(root, home)
    root.update()
    assert restored.path.samefile(saved_path), f'Restored {restored.path} differs from {saved_path}'
    assert restored.fields['name'].get() == 'Synthetic smoke test'
    assert restored.config['profile']['salary_overrides']['https://example.org/jobs/1']['annual_max'] == 230000
    assert 'UTC' in restored.last_scan.get()
    restored.salary_url.set('https://example.org/jobs/1')
    restored.salary_mode.set('Ignore annual-period inference')
    restored.save_salary()
    assert json.loads(saved_path.read_text())['profile']['salary_overrides']['https://example.org/jobs/1'] == {'ignore_inference': True}
    restored.close()
print('Fresh-profile handoff checks passed')
