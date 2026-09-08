from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class RuntimePaths:
    home: Path

    @classmethod
    def from_home(cls, home: str | Path) -> "RuntimePaths":
        return cls(Path(home).expanduser().resolve())

    @property
    def config(self) -> Path: return self.home / "config.json"
    @property
    def data_dir(self) -> Path: return self.home / "data"
    @property
    def state(self) -> Path: return self.data_dir / "state.json"
    @property
    def cache(self) -> Path: return self.data_dir / "detail_cache.json"
    @property
    def output_dir(self) -> Path: return self.home / "output"
    @property
    def dashboard(self) -> Path: return self.output_dir / "jobs.html"
    @property
    def jobs_csv(self) -> Path: return self.output_dir / "jobs.csv"
    @property
    def eligible_csv(self) -> Path: return self.output_dir / "eligible_all.csv"
    @property
    def rejected_csv(self) -> Path: return self.output_dir / "rejected.csv"
    @property
    def near_miss_csv(self) -> Path: return self.output_dir / "near_miss.csv"
    @property
    def alerts(self) -> Path: return self.output_dir / "new_matches.json"
    @property
    def log(self) -> Path: return self.output_dir / "last_run.log"

    def ensure(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
