"""Exercise Tk construction and save on Windows without network or real user data."""
import tempfile
import tkinter as tk
from pathlib import Path

from jobscout.desktop import Desktop

with tempfile.TemporaryDirectory() as tmp:
    root = tk.Tk()
    app = Desktop(root, Path(tmp))
    root.update()
    app.fields['name'].set('Synthetic smoke test')
    app.fields['title_terms'].set('Research Director')
    app.fields['local_regions'].set('Example City')
    assert app.save()
    assert app.path.exists()
    root.update()
    root.destroy()
