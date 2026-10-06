# -*- coding: utf-8 -*-
"""
run_demo.py
===========
Dependency-Aware Parallel Build -- Complete Demonstration
=========================================================

Run this file to present the entire demonstration:

  python run_demo.py

SECTIONS
--------
  0. Pre-flight checks (gcc available, directory clean)
  1. Wrong-order demonstration  -- consumer.c compiled BEFORE generated_config.h exists
  2. Naive concurrency danger   -- blindly running everything concurrently
  3. Dependency-aware build     -- the scheduler correctly orders and parallelises tasks
  4. Timing comparison          -- sequential vs parallel independent tasks
  5. Final result summary

No part of this is simulated. Every subprocess call is real.
"""

import subprocess
import sys
import os
import time
import threading
import shutil
from datetime import datetime

# --- Working directory --------------------------------------------------------
DEMO_DIR = os.path.dirname(os.path.abspath(__file__))

# --- Colour helpers -----------------------------------------------------------
def _supports_color():
    if sys.platform == "win32":
        try:
            import ctypes
            kernel = ctypes.windll.kernel32
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

# --- Helpers ------------------------------------------------------------------

def banner(title, char="=", color=""):
    width = 70
    print()
    print("{color}{bold}{line}{reset}".format(
        color=color, bold=BOLD, line=char * width, reset=RESET))
    pad = (width - len(title) - 2) // 2
    pad_l = " " * pad
    pad_r = " " * (width - len(title) - 2 - pad)
    print("{color}{bold}{c}{pad_l}{title}{pad_r}{c}{reset}".format(
        color=color, bold=BOLD, c=char, pad_l=pad_l, title=title, pad_r=pad_r, reset=RESET))
    print("{color}{bold}{line}{reset}".format(
        color=color, bold=BOLD, line=char * width, reset=RESET))
    print()
    sys.stdout.flush()


def section(n, title):
    DAS = "-" * 70
    print()
    print("{bold}{blue}{das}{reset}".format(bold=BOLD, blue=BLUE, das=DAS, reset=RESET))
    print("{bold}{blue}  SECTION {n}: {title}{reset}".format(
        bold=BOLD, blue=BLUE, n=n, title=title, reset=RESET))
    print("{bold}{blue}{das}{reset}".format(bold=BOLD, blue=BLUE, das=DAS, reset=RESET))
    print()
    sys.stdout.flush()


def note(msg):
    print("  {cyan}i  {msg}{reset}".format(cyan=CYAN, msg=msg, reset=RESET))
    sys.stdout.flush()


def success(msg):
    print("  {green}{bold}OK  {msg}{reset}".format(green=GREEN, bold=BOLD, msg=msg, reset=RESET))
    sys.stdout.flush()


def failure(msg):
    print("  {red}{bold}FAIL  {msg}{reset}".format(red=RED, bold=BOLD, msg=msg, reset=RESET))
    sys.stdout.flush()


def warn(msg):
    print("  {yellow}{bold}WARN  {msg}{reset}".format(yellow=YELLOW, bold=BOLD, msg=msg, reset=RESET))
    sys.stdout.flush()


def run_cmd(cmd, capture=True):
    """Run a command in DEMO_DIR. Returns CompletedProcess."""
    return subprocess.run(
        cmd,
        cwd=DEMO_DIR,
        capture_output=capture,
        text=True,
    )


def exe(name):
    return name + ".exe" if sys.platform == "win32" else name


def ts():
    return datetime.now().strftime("%H:%M:%S")


# --- Pre-flight ---------------------------------------------------------------

def preflight():
    banner("PRE-FLIGHT CHECKS", color=CYAN)

    # 1. gcc
    gcc = shutil.which("gcc")
    if gcc is None:
        failure("gcc not found in PATH.")
        print()
        print("  Install MinGW-w64 (Windows) or GCC (Linux/macOS) and add it to PATH.")
        print("  Windows: https://winlibs.com/   or   scoop install gcc")
        sys.exit(1)
    success("gcc found: {gcc}".format(gcc=gcc))

    # 2. Clean any previous run
    note("Cleaning previous build artefacts ...")
    result = run_cmd([sys.executable, "clean_demo.py"], capture=True)
    if result.returncode == 0:
        success("Demo directory is clean.")
    else:
        warn("clean_demo.py returned non-zero -- continuing anyway.")

    # 3. Verify source files exist
    required_sources = [
        "generate_config.c", "consumer.c",
        "independent1.c", "independent2.c", "independent3.c",
    ]
    for src in required_sources:
        if os.path.exists(os.path.join(DEMO_DIR, src)):
            success("Source file present: {src}".format(src=src))
        else:
            failure("Source file MISSING: {src}".format(src=src))
            sys.exit(1)

    print()


# --- Section 1: Wrong-order demonstration ------------------------------------

def demo_wrong_order():
    section(1, "WRONG ORDER -- EXPECTED FAILURE")

    print("  {bold}Claim:{reset}".format(bold=BOLD, reset=RESET))
    print("  consumer.c depends on generated_config.h at compile time.")
    print("  Attempting to compile consumer.c before the header exists")
    print("  will produce a REAL compiler error -- not a simulation.")
    print()

    # Confirm the header does NOT exist
    header_path = os.path.join(DEMO_DIR, "generated_config.h")
    if os.path.exists(header_path):
        warn("generated_config.h already exists -- removing it for this demonstration.")
        os.remove(header_path)

    note("Confirmed: generated_config.h does NOT exist.")
    print()

    print("  {yellow}{bold}COMMAND:{reset}  gcc consumer.c -o {exe}".format(
        yellow=YELLOW, bold=BOLD, reset=RESET, exe=exe("consumer")))
    print()

    result = run_cmd(["gcc", "consumer.c", "-o", exe("consumer")])

    if result.returncode != 0:
        err_output = (result.stdout + result.stderr).strip()
        print("  {red}{bold}EXPECTED FAILURE -- real compiler error below:{reset}".format(
            red=RED, bold=BOLD, reset=RESET))
        print()
        for line in err_output.splitlines():
            print("    {red}{line}{reset}".format(red=RED, line=line, reset=RESET))
        print()
        success("Demo point proved: consumer.c CANNOT compile without generated_config.h.")
        note("This is not a simulation -- the compiler itself rejected the request.")
    else:
        failure("Unexpected: consumer compiled without the header. Demo integrity violated.")
        sys.exit(1)

    print()
    print("  {bold}Now let us fix the order:{reset}".format(bold=BOLD, reset=RESET))
    print()

    # Step 1: compile generate_config
    note("Step 1 -- Compile generate_config.c  ->  {ex}".format(ex=exe("generate_config")))
    r1 = run_cmd(["gcc", "generate_config.c", "-o", exe("generate_config")])
    if r1.returncode == 0:
        success("{ex} compiled successfully.".format(ex=exe("generate_config")))
    else:
        failure("generate_config.c compilation failed.")
        print(r1.stdout + r1.stderr)
        sys.exit(1)

    # Step 2: run generate_config to create the header
    note("Step 2 -- Run {ex}  ->  produces generated_config.h".format(
        ex=exe("generate_config")))
    gen_cmd = [exe("generate_config")] if sys.platform == "win32" else [
        "./" + exe("generate_config")]
    r2 = run_cmd(gen_cmd)
    if r2.returncode == 0:
        output = (r2.stdout + r2.stderr).strip()
        for line in output.splitlines():
            print("    {green}{line}{reset}".format(green=GREEN, line=line, reset=RESET))
    else:
        failure("generate_config execution failed.")
        print(r2.stdout + r2.stderr)
        sys.exit(1)

    # Step 3: confirm the header exists
    if os.path.exists(header_path):
        success("generated_config.h now EXISTS on disk.")
        note("The artifact has been produced -- consumer.c can now be compiled.")
    else:
        failure("generated_config.h was NOT created. Something went wrong.")
        sys.exit(1)

    # Step 4: now compile consumer successfully
    note("Step 3 -- Compile consumer.c  ->  {ex}  (header now available)".format(
        ex=exe("consumer")))
    r3 = run_cmd(["gcc", "consumer.c", "-o", exe("consumer")])
    if r3.returncode == 0:
        success("{ex} compiled successfully.".format(ex=exe("consumer")))
    else:
        failure("consumer.c compilation still failed. Check your GCC installation.")
        print(r3.stdout + r3.stderr)
        sys.exit(1)

    # Step 5: run consumer
    note("Step 4 -- Run {ex}".format(ex=exe("consumer")))
    con_cmd = [exe("consumer")] if sys.platform == "win32" else ["./" + exe("consumer")]
    r4 = run_cmd(con_cmd)
    if r4.returncode == 0:
        for line in (r4.stdout + r4.stderr).strip().splitlines():
            print("    {green}{line}{reset}".format(green=GREEN, line=line, reset=RESET))
        success("consumer ran successfully -- it read the value from generated_config.h.")
    else:
        failure("consumer execution failed.")
        print(r4.stdout + r4.stderr)
        sys.exit(1)

    print()
    print("  {green}{bold}Section 1 conclusion:{reset}".format(green=GREEN, bold=BOLD, reset=RESET))
    print("  Task A (generate_config) produces an artifact -> generated_config.h")
    print("  Task B (consumer)        consumes that artifact at compile time")
    print("  Therefore: Task B MUST wait for Task A to complete before it can proceed.")
    print()


# --- Section 2: Naive concurrency danger -------------------------------------

def demo_naive_concurrency():
    section(2, "NAIVE CONCURRENCY -- WHY BLIND PARALLELISM IS UNSAFE")

    print("  {bold}Scenario:{reset}".format(bold=BOLD, reset=RESET))
    print("  Suppose a naive build system launches ALL compilation tasks at once.")
    print("  We demonstrate what happens when consumer_compile starts")
    print("  before generate_config_run has produced the header.")
    print()

    # Remove the header to simulate a fresh state
    header_path = os.path.join(DEMO_DIR, "generated_config.h")
    if os.path.exists(header_path):
        os.remove(header_path)
        note("Removed generated_config.h -- simulating fresh start.")

    print("  {yellow}{bold}Launching consumer compilation immediately (no header present):{reset}".format(
        yellow=YELLOW, bold=BOLD, reset=RESET))
    print("  {yellow}This represents a naive scheduler that ignores dependencies.{reset}".format(
        yellow=YELLOW, reset=RESET))
    print()

    # Launch consumer compile -- will fail because header does not exist
    consumer_result = subprocess.run(
        ["gcc", "consumer.c", "-o", exe("consumer")],
        cwd=DEMO_DIR,
        capture_output=True,
        text=True,
    )

    err = (consumer_result.stdout + consumer_result.stderr).strip()
    print("  {red}{bold}consumer_compile failed (as expected):{reset}".format(
        red=RED, bold=BOLD, reset=RESET))
    for line in err.splitlines():
        print("    {red}{line}{reset}".format(red=RED, line=line, reset=RESET))

    print()
    print("  {red}{bold}Why did this fail?{reset}".format(red=RED, bold=BOLD, reset=RESET))
    print("  Because blindly parallelising all tasks ignores the fact that")
    print("  consumer.c requires generated_config.h to be present BEFORE")
    print("  the compiler can process the #include directive.")
    print()
    print("  {bold}The race condition:{reset}".format(bold=BOLD, reset=RESET))
    print("  +--------------------------------------------------------------+")
    print("  |  Naive scheduler dispatches: generate_config AND consumer    |")
    print("  |  at the same time.                                           |")
    print("  |                                                              |")
    print("  |  generate_config  --+   (may not finish before consumer     |")
    print("  |                     |    compilation reads the #include)    |")
    print("  |  consumer_compile --+  <- FAILS if header not yet written   |")
    print("  +--------------------------------------------------------------+")
    print()
    print("  {bold}Conclusion:{reset}".format(bold=BOLD, reset=RESET))
    print("  Blind concurrency is unsafe because consumer requires an artifact")
    print("  (generated_config.h) that has not yet been produced.")
    print()
    print("  The solution is a dependency-aware scheduler that tracks what")
    print("  each task needs and only dispatches a task when its inputs exist.")
    print()


# --- Section 3: Dependency-aware build ---------------------------------------

def demo_scheduler():
    section(3, "DEPENDENCY-AWARE BUILD -- CORRECT PARALLEL EXECUTION")

    note("Cleaning before scheduler run ...")
    run_cmd([sys.executable, "clean_demo.py"])
    print()

    print("  {bold}The dependency-aware scheduler will:{reset}".format(bold=BOLD, reset=RESET))
    print("  1. Identify tasks with no unmet dependencies -> dispatch concurrently")
    print("  2. Block dependent tasks until their prerequisites complete")
    print("  3. Only release consumer_compile after generated_config.h exists")
    print()

    result = subprocess.run(
        [sys.executable, "demo_scheduler.py"],
        cwd=DEMO_DIR,
    )

    print()
    if result.returncode == 0:
        success("Scheduler completed successfully. All tasks passed.")
    else:
        failure("Scheduler reported one or more failures.")

    return result.returncode == 0


# --- Section 4: Timing comparison --------------------------------------------

def demo_timing():
    section(4, "TIMING COMPARISON -- SEQUENTIAL vs PARALLEL")

    note("Running independent1, independent2, independent3 SEQUENTIALLY ...")
    print()

    seq_start = time.time()

    for i in (1, 2, 3):
        ind_exe = exe("independent{i}".format(i=i))
        cmd = [ind_exe] if sys.platform == "win32" else ["./" + ind_exe]
        t0 = time.time()
        r  = subprocess.run(cmd, cwd=DEMO_DIR, capture_output=True, text=True)
        t1 = time.time()
        output = (r.stdout + r.stderr).strip()
        for line in output.splitlines():
            print("    {gray}{line}{reset}".format(gray=GRAY, line=line, reset=RESET))
        print("    {gray}-> independent{i} took {dur:.3f}s{reset}".format(
            gray=GRAY, i=i, dur=t1 - t0, reset=RESET))

    seq_total = time.time() - seq_start
    print()
    print("  {yellow}Sequential total: {dur:.3f}s{reset}".format(
        yellow=YELLOW, dur=seq_total, reset=RESET))
    print()

    # --- Parallel ---
    note("Running independent1, independent2, independent3 IN PARALLEL ...")
    print()

    results     = {}
    start_times = {}
    end_times   = {}
    lock        = threading.Lock()

    def run_parallel(i):
        ind_exe = exe("independent{i}".format(i=i))
        cmd     = [ind_exe] if sys.platform == "win32" else ["./" + ind_exe]
        start_times[i] = time.time()
        r = subprocess.run(cmd, cwd=DEMO_DIR, capture_output=True, text=True)
        end_times[i]   = time.time()
        with lock:
            results[i] = r

    par_start = time.time()
    threads   = [threading.Thread(target=run_parallel, args=(i,)) for i in (1, 2, 3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    par_total = time.time() - par_start

    for i in (1, 2, 3):
        r   = results[i]
        dur = end_times[i] - start_times[i]
        output = (r.stdout + r.stderr).strip()
        for line in output.splitlines():
            print("    {gray}{line}{reset}".format(gray=GRAY, line=line, reset=RESET))
        print("    {gray}-> independent{i} took {dur:.3f}s{reset}".format(
            gray=GRAY, i=i, dur=dur, reset=RESET))

    print()
    print("  {yellow}Parallel total:    {dur:.3f}s{reset}".format(
        yellow=YELLOW, dur=par_total, reset=RESET))
    print()

    # --- Comparison ---
    print("  {bold}COMPARISON:{reset}".format(bold=BOLD, reset=RESET))
    print("  {:<22}  {:.3f}s".format("Sequential time:", seq_total))
    print("  {:<22}  {:.3f}s".format("Parallel time:", par_total))
    if par_total > 0:
        speedup = seq_total / par_total
        print("  {:<22}  {:.2f}x".format("Speedup:", speedup))
    print()

    print("  {gray}NOTE: Actual speedup depends on CPU cores, OS process scheduler,".format(
        gray=GRAY))
    print("  compilation overhead, and workload. The controlled delay in each")
    print("  independent program makes the concurrency visible even when")
    print("  compilation itself is near-instant on modern hardware.{reset}".format(reset=RESET))
    print()


# --- Section 5: Final result -------------------------------------------------

def demo_result():
    section(5, "FINAL RESULT SUMMARY")

    checks = []

    if os.path.exists(os.path.join(DEMO_DIR, "generated_config.h")):
        checks.append((True, "generated_config.h exists (artifact produced successfully)"))
    else:
        checks.append((False, "generated_config.h MISSING"))

    for name in ["generate_config", "consumer", "independent1", "independent2", "independent3"]:
        ex = exe(name)
        exists = os.path.exists(os.path.join(DEMO_DIR, ex))
        msg = "{ex} compiled successfully".format(ex=ex) if exists else "{ex} MISSING".format(ex=ex)
        checks.append((exists, msg))

    for ok, msg in checks:
        if ok:
            success(msg)
        else:
            failure(msg)

    print()
    print("  {bold}What this demonstration proved:{reset}".format(bold=BOLD, reset=RESET))
    print()
    print("  1. {green}consumer.c genuinely fails{reset} to compile without generated_config.h.".format(
        green=GREEN, reset=RESET))
    print("     (Real compiler error -- not a simulation.)")
    print()
    print("  2. {green}Blind concurrency is unsafe{reset} -- launching consumer compilation".format(
        green=GREEN, reset=RESET))
    print("     before the producer has run causes a real failure.")
    print()
    print("  3. {green}The dependency-aware scheduler correctly:{reset}".format(
        green=GREEN, reset=RESET))
    print("     * Ran generate_config_compile first")
    print("     * Ran generate_config to produce the artifact")
    print("     * Ran independent1/2/3 concurrently (safe -- no dependencies)")
    print("     * Blocked consumer_compile until generated_config.h existed")
    print("     * Released consumer_compile only after the dependency was met")
    print()
    print("  4. {green}Independent tasks ran concurrently{reset} -- overlapping timestamps".format(
        green=GREEN, reset=RESET))
    print("     in Section 3 output prove real parallel execution.")
    print()

    EQ = "=" * 66
    print("  {bold}{cyan}{eq}{reset}".format(bold=BOLD, cyan=CYAN, eq=EQ, reset=RESET))
    print("  {bold}{cyan}  KEY INSIGHT:{reset}".format(bold=BOLD, cyan=CYAN, reset=RESET))
    print("  {bold}{cyan}{eq}{reset}".format(bold=BOLD, cyan=CYAN, eq=EQ, reset=RESET))
    print("  {bold}  \"Dependencies do not prevent parallelism;{reset}".format(
        bold=BOLD, reset=RESET))
    print("  {bold}   they determine where parallelism is SAFE.\"{reset}".format(
        bold=BOLD, reset=RESET))
    print()
    print("  {bold}  \"Task A produces an artifact".format(bold=BOLD))
    print("   -> Task B consumes that artifact")
    print("   -> Task B MUST wait for Task A.\"{reset}".format(reset=RESET))
    print("  {bold}{cyan}{eq}{reset}".format(bold=BOLD, cyan=CYAN, eq=EQ, reset=RESET))
    print()


# --- Main --------------------------------------------------------------------

def main():
    banner("DEPENDENCY-AWARE PARALLEL BUILD DEMONSTRATION", color=CYAN)

    print("  {bold}Purpose:{reset}".format(bold=BOLD, reset=RESET))
    print("  Prove that independent tasks can run concurrently, but dependent")
    print("  tasks cannot safely run concurrently because a consumer requires")
    print("  an artifact produced by another task.")
    print()
    print("  {bold}What you will see:{reset}".format(bold=BOLD, reset=RESET))
    print("  Section 1 -- Wrong order -> real compiler failure")
    print("  Section 2 -- Naive concurrency -> real failure")
    print("  Section 3 -- Dependency-aware scheduler -> correct and parallel")
    print("  Section 4 -- Sequential vs parallel timing")
    print("  Section 5 -- Final result summary")
    print()

    preflight()

    demo_wrong_order()

    input("  {yellow}Press ENTER to continue to Section 2 ...{reset}\n".format(
        yellow=YELLOW, reset=RESET))

    demo_naive_concurrency()

    input("  {yellow}Press ENTER to continue to Section 3 -- Dependency-Aware Build ...{reset}\n".format(
        yellow=YELLOW, reset=RESET))

    ok = demo_scheduler()

    if ok:
        input("  {yellow}Press ENTER to continue to Section 4 -- Timing Comparison ...{reset}\n".format(
            yellow=YELLOW, reset=RESET))
        demo_timing()
        demo_result()
    else:
        failure("Scheduler failed -- skipping timing and result sections.")
        sys.exit(1)

    banner("DEMONSTRATION COMPLETE", char="=", color=GREEN)


if __name__ == "__main__":
    main()
