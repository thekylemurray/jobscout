"""Native desktop launcher. User data lives outside the executable directory."""
from __future__ import annotations

import json
import os
import queue
import sys
import threading
import tkinter as tk
import uuid
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .app import render_html, run_once
from .config import default_config, validate_config
from .models import Job
from .paths import RuntimePaths
from .profiles import LIST_FIELDS, blank_profile
from .scoring import apply_freshness, score_job
from .sources import SOURCE_FUNCS
from .utils import iso_now


def desktop_home() -> Path:
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local' / 'share'))) / 'JobScout'


def write_config(path: Path, config: dict) -> None:
    errors = validate_config(config)
    if errors:
        raise ValueError('\n'.join(errors))
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(config, indent=2) + '\n', encoding='utf-8')
    temp.replace(path)


class Desktop:
    def __init__(self, root: tk.Tk, home: Path):
        self.root, self.home = root, home
        self.busy = False
        self.messages = queue.Queue()
        root.title('JobScout — Your job search')
        root.geometry('1000x800')
        root.minsize(850, 650)
        self.config = default_config()
        self.config.update(profile=blank_profile(), boards=[], local_regions=[])
        self.path = home / 'profiles' / uuid.uuid4().hex / 'config.json'
        top = ttk.Frame(root, padding=12)
        top.pack(fill='x')
        ttk.Label(top, text='JobScout', font=('Segoe UI', 20, 'bold')).pack(side='left')
        for label, command in [('New profile', self.new), ('Import profile', self.import_profile),
                               ('Open saved profile', self.open_profile), ('Save', self.save)]:
            ttk.Button(top, text=label, command=command).pack(side='left', padx=5)
        self.tabs = ttk.Notebook(root)
        self.tabs.pack(fill='both', expand=True, padx=12)
        self.fields = {}
        form = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(form, text='Search preferences')
        labels = {'name': 'Profile name', 'title_terms': 'Target titles (separate with semicolons)',
                  'seniority_terms': 'Seniority (semicolons; blank allows all)',
                  'core_skills': 'Core skills / experience (semicolons)', 'industry_terms': 'Industry signals (semicolons)',
                  'excluded_title_terms': 'Excluded job functions (semicolons)',
                  'excluded_companies': 'Excluded employers (semicolons)',
                  'preferred_companies': 'Preferred employers (semicolons)',
                  'review_terms': 'Qualifications to flag for review (semicolons)',
                  'local_regions': 'Acceptable cities (semicolons; avoid whole states)',
                  'salary_floor': 'Minimum annual USD base salary', 'salary_target': 'Target annual USD base salary'}
        for i, (key, label) in enumerate(labels.items()):
            ttk.Label(form, text=label).grid(row=i, column=0, sticky='w', pady=6)
            var = tk.StringVar()
            self.fields[key] = var
            ttk.Entry(form, textvariable=var).grid(row=i, column=1, sticky='ew', padx=12)
        form.columnconfigure(1, weight=1)
        self.remote, self.contract = tk.BooleanVar(), tk.BooleanVar()
        ttk.Checkbutton(form, text='Consider remote roles (verify state eligibility)', variable=self.remote).grid(row=12, column=0, columnspan=2, sticky='w')
        ttk.Checkbutton(form, text='Consider contract / temporary roles', variable=self.contract).grid(row=13, column=0, columnspan=2, sticky='w')
        ttk.Label(form, text='Scores are keyword-based review aids, not hiring probabilities.\nMissing salary, degree alternatives, benefits and location restrictions need human review.', wraplength=800).grid(row=14, column=0, columnspan=2, sticky='w', pady=12)
        sources = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(sources, text='Job sources')
        ttk.Label(sources, text='Search covers only these configured feeds. It does not search all of LinkedIn or the web.\nYou can also evaluate a posting copied from any job site in the next tab.', wraplength=850).pack(anchor='w')
        self.source_list = tk.Listbox(sources, height=12)
        self.source_list.pack(fill='both', expand=True, pady=10)
        self.company, self.source, self.board = tk.StringVar(), tk.StringVar(value='workday'), tk.StringVar()
        for label, var in [('Employer', self.company), ('Board URL or board token', self.board)]:
            ttk.Label(sources, text=label).pack(anchor='w')
            ttk.Entry(sources, textvariable=var).pack(fill='x')
        ttk.Combobox(sources, textvariable=self.source, values=sorted(SOURCE_FUNCS), state='readonly').pack(anchor='w', pady=6)
        ttk.Button(sources, text='Add source', command=self.add_source).pack(side='left')
        ttk.Button(sources, text='Remove selected source', command=self.remove_source).pack(side='left', padx=8)
        manual = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(manual, text='Check a posting')
        self.job_fields = {}
        for row, (key, label) in enumerate([('company','Employer'),('title','Job title'),('location','Location'),
                ('workplace','Work arrangement: Remote / Hybrid / On-site'), ('employment_type','Employment type'),
                ('compensation','Salary, e.g. USD 200000–250000 annual base'), ('apply_url','Application URL (https://)')]):
            ttk.Label(manual, text=label).grid(row=row, column=0, sticky='w', pady=3)
            var = tk.StringVar()
            self.job_fields[key] = var
            ttk.Entry(manual, textvariable=var).grid(row=row, column=1, sticky='ew')
        ttk.Label(manual, text='Full job description').grid(row=7, column=0, sticky='nw')
        self.description = tk.Text(manual, height=12, wrap='word')
        self.description.grid(row=7, column=1, sticky='nsew', pady=6)
        manual.columnconfigure(1, weight=1)
        manual.rowconfigure(7, weight=1)
        ttk.Button(manual, text='Evaluate posting', command=self.evaluate).grid(row=8, column=1, sticky='w')
        bottom = ttk.Frame(root, padding=12)
        bottom.pack(fill='x')
        self.scan_button = ttk.Button(bottom, text='Search configured sources', command=self.scan)
        self.scan_button.pack(side='left')
        ttk.Button(bottom, text='Open results', command=self.results).pack(side='left', padx=8)
        ttk.Button(bottom, text='View scan log', command=self.log).pack(side='left')
        self.status = tk.StringVar(value='Import a search profile, or fill in preferences and save.')
        ttk.Label(root, textvariable=self.status, wraplength=950, padding=12).pack(fill='x')
        self.populate()
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(200, self.poll)

    def available(self):
        if self.busy:
            messagebox.showinfo('Search in progress', 'Wait for this search to finish before changing profiles or saving.')
            return False
        return True

    def populate(self):
        p = self.config['profile']
        for key, var in self.fields.items():
            val = p.get(key, self.config.get(key, ''))
            var.set('; '.join(val) if isinstance(val, list) else str(val))
        self.remote.set(p['allow_remote'])
        self.contract.set(p['allow_contract'])
        self.refresh_sources()

    def refresh_sources(self):
        self.source_list.delete(0, 'end')
        for b in self.config['boards']:
            self.source_list.insert('end', f"{b['company']} — {b['source']} — {b['board']}" + (' (disabled)' if not b.get('enabled', True) else ''))

    def collect(self):
        c = json.loads(json.dumps(self.config))
        for key, var in self.fields.items():
            text = var.get().strip()
            if key in LIST_FIELDS:
                c['profile'][key] = [x.strip() for x in text.split(';') if x.strip()]
            elif key == 'local_regions':
                c[key] = [x.strip() for x in text.split(';') if x.strip()]
            elif key.startswith('salary_'):
                c[key] = float(text.replace(',', '').replace('$', ''))
            else:
                c['profile'][key] = text
        c['profile']['allow_remote'], c['profile']['allow_contract'] = self.remote.get(), self.contract.get()
        errors = validate_config(c)
        if errors:
            raise ValueError('\n'.join(errors))
        return c

    def save(self):
        if not self.available():
            return False
        try:
            self.config = self.collect()
            write_config(self.path, self.config)
            self.status.set(f"Saved {self.config['profile']['name']} on this computer.")
            return True
        except (ValueError, OSError, TypeError) as exc:
            messagebox.showerror('Check preferences', str(exc))
            return False

    def new(self):
        if not self.available():
            return
        if not messagebox.askyesno('New profile', 'Start a blank profile? Unsaved edits will be discarded.'):
            return
        self.config = default_config()
        self.config.update(profile=blank_profile(), boards=[], local_regions=[])
        self.path = self.home / 'profiles' / uuid.uuid4().hex / 'config.json'
        self.populate()

    def import_profile(self):
        self.load_profile(False)

    def open_profile(self):
        self.load_profile(True)

    def load_profile(self, existing):
        if not self.available():
            return
        filename = filedialog.askopenfilename(title='Choose JobScout profile', filetypes=[('JobScout profile', '*.json')],
                                              initialdir=str(self.home / 'profiles') if existing else None)
        if not filename:
            return
        try:
            candidate = json.loads(Path(filename).read_text(encoding='utf-8-sig'))
            errors = validate_config(candidate)
            if not candidate.get('profile'):
                errors.append('This desktop version requires a portable search profile.')
            if errors:
                raise ValueError('\n'.join(errors))
            if not messagebox.askyesno('Load profile', 'Load this profile? Unsaved edits will be discarded.'):
                return
            path = Path(filename).resolve() if existing else self.home / 'profiles' / uuid.uuid4().hex / 'config.json'
            write_config(path, candidate)
            self.path, self.config = path, candidate
            self.populate()
            self.status.set('Profile loaded. Review preferences, then search or check a posting.')
        except (OSError, ValueError, TypeError, KeyError) as exc:
            messagebox.showerror('Could not load profile', str(exc))

    def add_source(self):
        if not self.available():
            return
        b = dict(company=self.company.get().strip(), source=self.source.get(), board=self.board.get().strip(), enabled=True)
        if not b['company'] or not b['board']:
            messagebox.showerror('Source details', 'Enter an employer and board URL/token.')
            return
        self.config['boards'].append(b)
        self.refresh_sources()

    def remove_source(self):
        if self.available() and self.source_list.curselection():
            del self.config['boards'][self.source_list.curselection()[0]]
            self.refresh_sources()

    def scan(self):
        if not self.save():
            return
        if not any(b.get('enabled', True) for b in self.config['boards']):
            messagebox.showinfo('No sources', 'Add a supported job source, or use Check a posting.')
            return
        paths = RuntimePaths.from_home(self.path.parent)
        self.busy = True
        self.scan_button.state(['disabled'])
        self.status.set('Searching configured feeds. Large employer boards can take several minutes…')
        def worker():
            try:
                run_once(paths, quiet=True)
                self.messages.put(('done', paths.log.read_text(encoding='utf-8')))
            except Exception as exc:
                self.messages.put(('error', str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            kind, detail = self.messages.get_nowait()
            self.busy = False
            self.scan_button.state(['!disabled'])
            if kind == 'error':
                self.status.set('Search failed. Your saved preferences are intact.')
                messagebox.showerror('Search failed', detail)
            else:
                summary = [x for x in detail.splitlines() if x.startswith(('ELIGIBLE ', 'SOURCE_HEALTH '))]
                self.status.set(' | '.join(summary) + '. Open results and check the scan log for feed failures.')
        except queue.Empty:
            pass
        self.root.after(200, self.poll)

    def results(self):
        self.open_file(RuntimePaths.from_home(self.path.parent).dashboard)

    def log(self):
        self.open_file(RuntimePaths.from_home(self.path.parent).log)

    def open_file(self, path):
        if path.exists():
            webbrowser.open(path.resolve().as_uri())
        else:
            messagebox.showinfo('No results yet', 'Run a search first.')

    def evaluate(self):
        if not self.save():
            return
        values = {key: var.get().strip() for key, var in self.job_fields.items()}
        if not values['title'] or not self.description.get('1.0', 'end').strip():
            messagebox.showerror('Posting details', 'Enter a job title and description.')
            return
        if values['apply_url'] and not values['apply_url'].startswith(('https://', 'http://')):
            messagebox.showerror('Application URL', 'Use an http:// or https:// link.')
            return
        job = Job(uid='manual', source='manual', description=self.description.get('1.0', 'end'),
                  job_url=values['apply_url'], published_at=None, first_seen_at=iso_now(), **values)
        score_job(job, self.config)
        apply_freshness(job, self.config, board_initialized=False, is_new=True)
        if not job.eligible:
            messagebox.showinfo('Excluded by profile', job.veto_reason)
            return
        path = self.path.parent / 'output' / 'manual-review.html'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_html([job]), encoding='utf-8')
        self.open_file(path)

    def close(self):
        if self.busy:
            messagebox.showinfo('Search in progress', 'Please wait for the search to finish before closing.')
            return
        self.root.destroy()


def main():
    home = desktop_home()
    home.mkdir(parents=True, exist_ok=True)
    # A windowed Windows executable has no stdout/stderr. Existing CLI logging
    # must have a valid stream when the scanner emits notifications or diagnostics.
    if sys.stdout is None:
        sys.stdout = (home / 'desktop.log').open('a', encoding='utf-8')
    if sys.stderr is None:
        sys.stderr = sys.stdout
    root = tk.Tk()
    Desktop(root, home)
    root.mainloop()


if __name__ == '__main__':
    main()
