# -*- coding: utf-8 -*-
"""
demo_scheduler.py
=================
Dependency-Aware Parallel Build Scheduler
==========================================

This scheduler demonstrates that:
  - Tasks with no unmet dependencies are dispatched concurrently.
  - Dependent tasks WAIT until ALL their dependencies have succeeded.
  - A failed dependency immediately marks all downstream tasks as FAILED.

The scheduler is intentionally small and readable -- it is a teaching tool,
not a production build system.
"""

import subprocess
import threading
import time
import sys
import os
from datetime import datetime
from enum import Enum, auto
from typing import List, Dict, Optional


# =============================================================================
# COLOUR HELPERS  (graceful fallback when the terminal does not support ANSI)
# =============================================================================

def _supports_color():
    """Return True if the current terminal can render ANSI escape codes."""
    if sys.platform == "win32":
        try:
            import ctypes
            kernel = ctypes.windll.kernel32          # type: ignore[attr-defined]
            # Enable VIRTUAL_TERMINAL_PROCESSING (flag 0x0004)
            kernel.SetConsoleMode(kernel.GetStdHandle(-11), 7)
            return True
        except Exception:
            return False
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()

_COLOR = _supports_color()

RESET   = "\033[0m"  if _COLOR else ""
BOLD    = "\033[1m"  if _COLOR else ""
CYAN    = "\033[96m" if _COLOR else ""
GREEN   = "\033[92m" if _COLOR else ""
YELLOW  = "\033[93m" if _COLOR else ""
RED     = "\033[91m" if _COLOR else ""
GRAY    = "\033[90m" if _COLOR else ""
BLUE    = "\033[94m" if _COLOR else ""
MAGENTA = "\033[95m" if _COLOR else ""


# =============================================================================
# TASK STATE
# =============================================================================

class State(Enum):
    QUEUED  = auto()   # waiting -- dependencies not yet met
    READY   = auto()   # all dependencies met -- eligible to run
    RUNNING = auto()   # subprocess is currently executing
    DONE    = auto()   # subprocess exited with return-code 0
    FAILED  = auto()   # subprocess exited non-zero, or a dependency failed
    BLOCKED = auto()   # a required dependency has FAILED -- will never run


STATE_COLOR = {
    State.QUEUED:   GRAY,
    State.READY:    CYAN,
    State.RUNNING:  YELLOW,
    State.DONE:     GREEN,
    State.FAILED:   RED,
    State.BLOCKED:  MAGENTA,
}

STATE_LABEL = {
    State.QUEUED:   "QUEUED ",
    State.READY:    "READY  ",
    State.RUNNING:  "RUNNING",
    State.DONE:     "DONE   ",
    State.FAILED:   "FAILED ",
    State.BLOCKED:  "BLOCKED",
}


# =============================================================================
# TASK DEFINITION
# =============================================================================

class Task:
    """
    A single build task.

    Attributes
    ----------
    name         : human-readable identifier
    command      : shell command to execute (list form)
    dependencies : list of task names that must be DONE before this task is READY
    """

    def __init__(self, name, command, dependencies=None):
        self.name         = name
        self.command      = command
        self.dependencies = dependencies or []
        self.state        = State.QUEUED
        self.start_time   = None
        self.end_time     = None
        self.returncode   = None
        self.output       = ""

    @property
    def duration(self):
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None


# =============================================================================
# SCHEDULER
# =============================================================================

class DependencyAwareScheduler:
    """
    A small parallel build scheduler that respects a dependency graph.

    Algorithm
    ---------
    1. Build a dict of tasks.
    2. In a loop:
       a. For every QUEUED task whose dependencies are all DONE -> mark READY.
       b. For every QUEUED/READY task with any FAILED/BLOCKED dependency -> BLOCKED.
       c. Dispatch every READY task as a background thread.
       d. Sleep briefly, then re-evaluate until all tasks are terminal.
    """

    def __init__(self, tasks, work_dir=".", event_callback=None):
        self.tasks            = {t.name: t for t in tasks}
        self.work_dir         = work_dir
        self._lock            = threading.Lock()
        self._event_callback  = event_callback  # optional: called on every state transition

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def run(self):
        """Execute the DAG. Returns True if every task succeeded."""
        self._print_dag()
        self._log_section("SCHEDULER STARTING")

        while True:
            self._tick()

            all_terminal = all(
                t.state in (State.DONE, State.FAILED, State.BLOCKED)
                for t in self.tasks.values()
            )
            if all_terminal:
                break

            time.sleep(0.15)   # re-evaluation interval

        return self._print_summary()

    # -------------------------------------------------------------------------
    # Internal
    # -------------------------------------------------------------------------

    def _tick(self):
        """One scheduling tick: promote tasks and dispatch newly READY ones."""
        with self._lock:
            for task in self.tasks.values():
                if task.state not in (State.QUEUED,):
                    continue

                deps = [self.tasks[d] for d in task.dependencies]

                # If any dependency is FAILED or BLOCKED -> block this task
                if any(d.state in (State.FAILED, State.BLOCKED) for d in deps):
                    self._transition(task, State.BLOCKED,
                                     reason="dependency failed -- will never run")
                    continue

                # If all dependencies are DONE -> ready to dispatch
                if all(d.state == State.DONE for d in deps):
                    self._transition(task, State.READY)
                    thread = threading.Thread(target=self._execute, args=(task,),
                                              daemon=True)
                    thread.start()

    def _execute(self, task):
        """Run a task's command in a subprocess and update its state."""
        with self._lock:
            self._transition(task, State.RUNNING)
        task.start_time = time.time()

        try:
            result = subprocess.run(
                task.command,
                cwd=self.work_dir,
                capture_output=True,
                text=True,
            )
            task.end_time   = time.time()
            task.returncode = result.returncode
            task.output     = (result.stdout + result.stderr).strip()

            with self._lock:
                if result.returncode == 0:
                    self._transition(task, State.DONE,
                                     duration=task.duration,
                                     output=task.output)
                else:
                    self._transition(task, State.FAILED,
                                     duration=task.duration,
                                     output=task.output)

        except FileNotFoundError as exc:
            task.end_time   = time.time()
            task.returncode = -1
            task.output     = str(exc)
            with self._lock:
                self._transition(task, State.FAILED,
                                 duration=task.duration,
                                 output=task.output)

    def _transition(self, task, new_state, reason="", duration=None, output=""):
        """Log a state transition with timestamp."""
        task.state = new_state
        ts    = datetime.now().strftime("%H:%M:%S")
        color = STATE_COLOR[new_state]
        label = STATE_LABEL[new_state]

        line = "  {gray}{ts}{reset}  {color}{bold}[{label}]{reset}  {bold}{name}{reset}".format(
            gray=GRAY, ts=ts, reset=RESET,
            color=color, bold=BOLD, label=label, name=task.name,
        )
        if duration is not None:
            line += "  {gray}({dur:.2f}s){reset}".format(
                gray=GRAY, dur=duration, reset=RESET)
        if reason:
            line += "  {gray}<- {reason}{reset}".format(
                gray=GRAY, reason=reason, reset=RESET)
        print(line)

        if output and new_state == State.FAILED:
            for ln in output.splitlines():
                print("           {red}{ln}{reset}".format(red=RED, ln=ln, reset=RESET))

        if new_state == State.DONE and output:
            for ln in output.splitlines():
                print("           {gray}  {ln}{reset}".format(gray=GRAY, ln=ln, reset=RESET))

        sys.stdout.flush()

        # Fire optional event callback (used by dashboard.py for WebSocket delivery).
        # Called while the lock is held -- callback must be non-blocking (e.g. queue.put).
        if self._event_callback:
            self._event_callback({
                "type":         "task_state",
                "task":         task.name,
                "state":        new_state.name,   # "RUNNING", "DONE", etc.
                "timestamp":    datetime.now().isoformat(),
                "display_time": ts,
                "duration":     round(duration, 3) if duration is not None else None,
                "output":       output,
                "reason":       reason,
            })

    # -------------------------------------------------------------------------
    # Reporting
    # -------------------------------------------------------------------------

    def _print_dag(self):
        """Print a static explanation of the dependency graph."""
        EQ  = "=" * 70
        DAS = "-" * 70
        print()
        print("{bold}{cyan}{eq}{reset}".format(bold=BOLD, cyan=CYAN, eq=EQ, reset=RESET))
        print("{bold}{cyan}  DEPENDENCY GRAPH{reset}".format(bold=BOLD, cyan=CYAN, reset=RESET))
        print("{bold}{cyan}{eq}{reset}".format(bold=BOLD, cyan=CYAN, eq=EQ, reset=RESET))
        print()
        print("{bold}  generate_config.c{reset}".format(bold=BOLD, reset=RESET))
        print("         |")
        print("         v  (compile)")
        print("  {cyan}generate_config{reset}".format(cyan=CYAN, reset=RESET))
        print("         |")
        print("         v  (run -> produces artifact)")
        print("  {green}generated_config.h{reset}    <- BUILD ARTIFACT".format(green=GREEN, reset=RESET))
        print("         |")
        print("         v  (required at compile time)")
        print("  {yellow}consumer.c{reset}".format(yellow=YELLOW, reset=RESET))
        print("         |")
        print("         v  (compile)")
        print("  {green}consumer{reset}".format(green=GREEN, reset=RESET))
        print()
        print("  {bold}INDEPENDENT (no dependencies):{reset}".format(bold=BOLD, reset=RESET))
        print("  {cyan}independent1.c{reset}  -->  {green}independent1{reset}".format(
            cyan=CYAN, green=GREEN, reset=RESET))
        print("  {cyan}independent2.c{reset}  -->  {green}independent2{reset}".format(
            cyan=CYAN, green=GREEN, reset=RESET))
        print("  {cyan}independent3.c{reset}  -->  {green}independent3{reset}".format(
            cyan=CYAN, green=GREEN, reset=RESET))
        print()
        print("{bold}{cyan}  SCHEDULING PLAN{reset}".format(bold=BOLD, cyan=CYAN, reset=RESET))
        print("{bold}{cyan}{das}{reset}".format(bold=BOLD, cyan=CYAN, das=DAS, reset=RESET))
        print()
        print("  {green}INITIALLY READY (no dependencies):{reset}".format(green=GREEN, reset=RESET))
        print("    * generate_config_compile")
        print("    * independent1_compile")
        print("    * independent2_compile")
        print("    * independent3_compile")
        print()
        print("  {yellow}RUN IN PARALLEL:{reset}".format(yellow=YELLOW, reset=RESET))
        print("    * independent1_compile")
        print("    * independent2_compile")
        print("    * independent3_compile")
        print("      (no dependencies between them -- safe to run simultaneously)")
        print()
        print("  {red}WAIT -- dependency chain (cannot run concurrently with producer):{reset}".format(
            red=RED, reset=RESET))
        print("    * generate_config_run    <- waits for generate_config_compile")
        print("    * consumer_compile       <- waits for generate_config_run (needs the header)")
        print("    * consumer_run           <- waits for consumer_compile")
        print()
        print("  {bold}KEY INSIGHT:{reset}".format(bold=BOLD, reset=RESET))
        print("  \"Dependencies do not prevent parallelism;")
        print("   they determine where parallelism is SAFE.\"")
        print()
        print("{bold}{cyan}{eq}{reset}".format(bold=BOLD, cyan=CYAN, eq=EQ, reset=RESET))
        print()

    def _log_section(self, title):
        DAS = "-" * 70
        print()
        print("{bold}{blue}{das}{reset}".format(bold=BOLD, blue=BLUE, das=DAS, reset=RESET))
        print("{bold}{blue}  {title}{reset}".format(bold=BOLD, blue=BLUE, title=title, reset=RESET))
        print("{bold}{blue}{das}{reset}".format(bold=BOLD, blue=BLUE, das=DAS, reset=RESET))
        print()
        sys.stdout.flush()

    def _print_summary(self):
        self._log_section("BUILD SUMMARY")
        all_ok = True
        for task in self.tasks.values():
            color = STATE_COLOR[task.state]
            label = STATE_LABEL[task.state]
            dur   = "  ({:.2f}s)".format(task.duration) if task.duration else ""
            print("  {color}{bold}[{label}]{reset}  {name}{gray}{dur}{reset}".format(
                color=color, bold=BOLD, label=label, reset=RESET,
                name=task.name, gray=GRAY, dur=dur))
            if task.state != State.DONE:
                all_ok = False

        print()
        if all_ok:
            print("  {green}{bold}All tasks completed successfully.{reset}".format(
                green=GREEN, bold=BOLD, reset=RESET))
        else:
            print("  {red}{bold}Some tasks did not complete successfully.{reset}".format(
                red=RED, bold=BOLD, reset=RESET))
        print()
        sys.stdout.flush()
        return all_ok


# =============================================================================
# TASK DEFINITIONS  (Windows-aware)
# =============================================================================

def _exe(name):
    """Return the executable name with .exe suffix on Windows."""
    return name + ".exe" if sys.platform == "win32" else name


def build_tasks():
    """Return the full list of tasks for this demonstration."""
    gen_exe  = _exe("generate_config")
    cons_exe = _exe("consumer")
    ind1_exe = _exe("independent1")
    ind2_exe = _exe("independent2")
    ind3_exe = _exe("independent3")

    # On Windows, run executables directly by name (PATH-resolved)
    # On Unix, use ./name syntax
    def run_cmd(exe_name):
        if sys.platform == "win32":
            return [exe_name]
        return ["./" + exe_name]

    return [
        # -- Dependency chain -------------------------------------------------
        Task(
            name="generate_config_compile",
            command=["gcc", "generate_config.c", "-o", gen_exe],
            dependencies=[],
        ),
        Task(
            name="generate_config_run",
            command=run_cmd(gen_exe),
            dependencies=["generate_config_compile"],
        ),
        Task(
            name="consumer_compile",
            command=["gcc", "consumer.c", "-o", cons_exe],
            dependencies=["generate_config_run"],   # must wait for header
        ),
        Task(
            name="consumer_run",
            command=run_cmd(cons_exe),
            dependencies=["consumer_compile"],
        ),

        # -- Independent tasks (no dependencies -- safe to run concurrently) --
        Task(
            name="independent1_compile",
            command=["gcc", "independent1.c", "-o", ind1_exe],
            dependencies=[],
        ),
        Task(
            name="independent2_compile",
            command=["gcc", "independent2.c", "-o", ind2_exe],
            dependencies=[],
        ),
        Task(
            name="independent3_compile",
            command=["gcc", "independent3.c", "-o", ind3_exe],
            dependencies=[],
        ),
    ]


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    demo_dir  = os.path.dirname(os.path.abspath(__file__))
    tasks     = build_tasks()
    scheduler = DependencyAwareScheduler(tasks, work_dir=demo_dir)
    success   = scheduler.run()
    sys.exit(0 if success else 1)
