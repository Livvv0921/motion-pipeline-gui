from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
from dataclasses import dataclass

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal


@dataclass
class _Job:
    job_id: str
    step: str
    label: str
    process: QProcess
    settings_file: Path
    progress: int | None = None
    buffer: str = ""
    finalized: bool = False


class ProcessRunner(QObject):
    """Run multiple backend scripts concurrently as independent QProcesses.

    Each call to :meth:`run` gets its own QProcess and temporary settings file.
    The GUI can therefore keep working while other stages are still running.
    Progress is aggregated both per stage and across all active jobs.
    """

    output = Signal(str)
    step_progress = Signal(str, int)        # step, percent; -1 means indeterminate
    overall_progress = Signal(int, int)     # percent; -1 indeterminate, active job count
    started = Signal(str, str)              # step, job_id
    finished = Signal(str, str, bool, int)  # step, job_id, success, exit_code
    active_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._jobs: dict[str, _Job] = {}
        self._sequence = 0
        self._step_sequence: dict[str, int] = {}

    @property
    def is_running(self) -> bool:
        return bool(self._jobs)

    @property
    def active_count(self) -> int:
        return len(self._jobs)

    def active_jobs_for_step(self, step: str) -> list[str]:
        return [job_id for job_id, job in self._jobs.items() if job.step == step]

    def job_label(self, job_id: str) -> str:
        job = self._jobs.get(job_id)
        return job.label if job is not None else job_id

    @staticmethod
    def _selected_python_env(python_executable: str) -> Path | None:
        text = (python_executable or "").strip().strip('"')
        if not text or text.lower() in {"python", "python.exe", "python3"}:
            return None
        path = Path(text)
        if path.name.lower() not in {"python.exe", "python", "python3"}:
            return None
        parent = path.parent
        if parent.name.lower() in {"bin", "scripts"}:
            return parent.parent
        return parent

    @staticmethod
    def _looks_like_conda_env_path(path_text: str) -> bool:
        normalized = path_text.replace("/", "\\").lower()
        return "\\envs\\" in normalized

    def _backend_environment(self, python_executable: str) -> tuple[QProcessEnvironment, Path | None]:
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUNBUFFERED", "1")

        selected_root = self._selected_python_env(python_executable)
        if selected_root is None or os.name != "nt":
            return env, selected_root

        root = selected_root.resolve()
        preferred = [
            root,
            root / "Library" / "mingw-w64" / "bin",
            root / "Library" / "usr" / "bin",
            root / "Library" / "bin",
            root / "Scripts",
            root / "bin",
        ]
        preferred = [str(p) for p in preferred if p.exists()]

        old_path = env.value("PATH", "")
        existing = [item for item in old_path.split(os.pathsep) if item]
        root_norm = str(root).rstrip("\\/").lower()

        cleaned: list[str] = []
        for item in existing:
            normalized = item.rstrip("\\/").lower()
            if normalized == root_norm or normalized.startswith(root_norm + "\\"):
                continue
            if self._looks_like_conda_env_path(item):
                continue
            cleaned.append(item)

        env.insert("PATH", os.pathsep.join(preferred + cleaned))
        env.insert("CONDA_PREFIX", str(root))
        env.insert("CONDA_DEFAULT_ENV", root.name)
        env.insert("CONDA_SHLVL", "1")
        return env, root

    def run(
        self,
        step: str,
        python_executable: str,
        runner_script: Path,
        backend_script: Path,
        settings: dict,
    ) -> str:
        self._sequence += 1
        self._step_sequence[step] = self._step_sequence.get(step, 0) + 1
        job_id = f"job-{self._sequence:04d}"
        label = f"{step.upper()} #{self._step_sequence[step]}"

        handle = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", prefix=f"motion_gui_{step}_", delete=False, encoding="utf-8"
        )
        with handle:
            json.dump(settings, handle, indent=2)
        settings_file = Path(handle.name)

        process = QProcess(self)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        env, selected_root = self._backend_environment(python_executable)
        process.setProcessEnvironment(env)
        process.setProgram(python_executable.strip() or "python")
        process.setArguments([
            str(runner_script),
            "--script", str(backend_script),
            "--settings", str(settings_file),
        ])

        job = _Job(job_id, step, label, process, settings_file)
        self._jobs[job_id] = job
        process.readyReadStandardOutput.connect(lambda jid=job_id: self._read_output(jid))
        process.finished.connect(lambda code, status, jid=job_id: self._finished(jid, int(code), status))
        process.errorOccurred.connect(lambda error, jid=job_id: self._error(jid, error))

        self.started.emit(step, job_id)
        self.active_changed.emit(self.active_count)
        self._emit_aggregates(step)
        self.output.emit(f"\n[{label}] STARTING\n")
        if selected_root is not None:
            details = (
                f"Backend Python: {process.program()}\n"
                f"Backend environment: {selected_root}\n"
            )
            if os.name == "nt":
                details += f"Native DLL search begins with: {selected_root / 'Library' / 'bin'}\n"
            else:
                details += "Cross-platform process launch: inherited macOS/Linux runtime paths.\n"
            self._emit_prefixed(job, details)
        process.start()
        return job_id

    def stop(self):
        """Stop all active jobs."""
        for job_id in list(self._jobs):
            self.stop_job(job_id)

    def stop_step(self, step: str):
        for job_id in list(self.active_jobs_for_step(step)):
            self.stop_job(job_id)

    def stop_job(self, job_id: str):
        job = self._jobs.get(job_id)
        if job is None or job.process.state() == QProcess.ProcessState.NotRunning:
            return
        self.output.emit(f"\n[{job.label}] Stop requested. Terminating backend process...\n")
        job.process.terminate()
        QTimer.singleShot(3000, lambda jid=job_id: self._kill_if_running(jid))

    def _kill_if_running(self, job_id: str):
        job = self._jobs.get(job_id)
        if job is not None and job.process.state() != QProcess.ProcessState.NotRunning:
            self.output.emit(f"[{job.label}] Process did not stop cleanly; killing it.\n")
            job.process.kill()

    def _emit_prefixed(self, job: _Job, text: str):
        if not text:
            return
        prefix = f"[{job.label}] "
        parts = text.splitlines(keepends=True)
        rendered = "".join(prefix + part for part in parts)
        if text and not parts:
            rendered = prefix + text
        self.output.emit(rendered)

    def _read_output(self, job_id: str):
        job = self._jobs.get(job_id)
        if job is None:
            return
        text = bytes(job.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        if not text:
            return
        self._emit_prefixed(job, text)
        job.buffer += text
        chunks = re.split(r"[\r\n]+", job.buffer)
        for line in chunks[:-1]:
            self._parse_progress(job, line)
        job.buffer = chunks[-1]

    def _parse_progress(self, job: _Job, line: str):
        value: int | None = None

        match = re.search(r"\[PROGRESS\s+(\d+(?:\.\d+)?)%\]", line, re.IGNORECASE)
        if match:
            value = max(0, min(100, int(float(match.group(1)))))
        else:
            match = re.search(r"\((\d+(?:\.\d+)?)%\)", line)
            if match:
                value = max(0, min(100, int(float(match.group(1)))))
            else:
                match = re.search(r"\[(\d+)\s*/\s*(\d+)\]", line)
                if match and int(match.group(2)) > 0:
                    value = int(int(match.group(1)) / int(match.group(2)) * 100)

        if value is not None and value != job.progress:
            job.progress = value
            self._emit_aggregates(job.step)

    def _emit_aggregates(self, changed_step: str | None = None):
        if changed_step is not None:
            step_jobs = [j for j in self._jobs.values() if j.step == changed_step]
            if step_jobs:
                if all(j.progress is None for j in step_jobs):
                    value = -1
                else:
                    value = round(sum((j.progress or 0) for j in step_jobs) / len(step_jobs))
                self.step_progress.emit(changed_step, value)

        jobs = list(self._jobs.values())
        if not jobs:
            self.overall_progress.emit(100, 0)
            return
        if all(j.progress is None for j in jobs):
            value = -1
        else:
            value = round(sum((j.progress or 0) for j in jobs) / len(jobs))
        self.overall_progress.emit(value, len(jobs))

    def _error(self, job_id: str, error):
        job = self._jobs.get(job_id)
        if job is None or job.finalized:
            return
        if error != QProcess.ProcessError.FailedToStart:
            return
        self._emit_prefixed(job, f"Failed to start Python executable: {job.process.program()}\n")
        self._finalize(job_id, False, -1)

    def _finished(self, job_id: str, exit_code: int, _status):
        job = self._jobs.get(job_id)
        if job is None or job.finalized:
            return
        success = exit_code == 0
        if not success and exit_code < 0:
            unsigned = exit_code & 0xFFFFFFFF
            self._emit_prefixed(
                job,
                f"Native Windows process exit: 0x{unsigned:08X}. "
                "If this repeats, it usually indicates a compiled-library/DLL failure rather than a Python exception.\n",
            )
        self._finalize(job_id, success, exit_code)

    def _finalize(self, job_id: str, success: bool, exit_code: int):
        job = self._jobs.get(job_id)
        if job is None or job.finalized:
            return
        job.finalized = True
        step = job.step
        try:
            job.settings_file.unlink(missing_ok=True)
        except Exception:
            pass

        # Remove before emitting so UI aggregation sees the remaining active jobs.
        self._jobs.pop(job_id, None)
        self.finished.emit(step, job_id, success, exit_code)
        self.active_changed.emit(self.active_count)
        self._emit_aggregates(step)
