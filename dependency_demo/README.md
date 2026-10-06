# Dependency-Aware Parallel Build Demonstration

This project is a minimal, practical demonstration of how a build system's task scheduler handles dependencies and parallelism.

**Core Concept:**
*"Dependencies don't prevent parallelism; they determine where parallelism is safe."*

---

## 1. What the Demo Proves
The demo proves that blindly running all build tasks simultaneously is unsafe when dependencies exist. However, by understanding the dependency graph (DAG), a scheduler can run independent tasks concurrently in parallel, while safely forcing dependent tasks to wait for their required inputs.

## 2. What a Dependency Is
A dependency is a strict requirement where Task B cannot start until Task A has completed, usually because Task B requires an **artifact** (a file) produced by Task A.

## 3. Producer → Artifact → Consumer
This project demonstrates the classic producer-consumer dependency chain:
1. **Producer (`generate_config.c`)**: Compiled and run to *produce* an artifact.
2. **Artifact (`generated_config.h`)**: The header file created by the producer.
3. **Consumer (`consumer.c`)**: Requires `#include "generated_config.h"` to compile.

## 4. Why `consumer.c` Fails Without the Artifact
If you attempt to compile `consumer.c` before `generated_config.h` exists, the C preprocessor immediately crashes with a fatal error (`No such file or directory`). This is a real, hard file-system requirement, not a logical suggestion.

## 5. Why Independent Tasks Can Run Concurrently
The demo includes `independent1.c`, `independent2.c`, and `independent3.c`. None of these rely on `generated_config.h`, and they do not share any outputs. Therefore, it is 100% safe for the scheduler to compile all three at the exact same time.

## 6. Why Blindly Running Everything Concurrently is Unsafe
If a naïve scheduler simply threw all tasks into background threads simultaneously, `consumer_compile` would likely execute before `generate_config_run` finishes creating the header. This results in a race condition and a failed build.

## 7. How the Dependency-Aware Scheduler Solves the Problem
The included Python scheduler (`demo_scheduler.py`) maps out the Directed Acyclic Graph (DAG) before execution. Every tick, it evaluates the state of all tasks:
* If a task has no dependencies (or all dependencies are `DONE`), it is dispatched immediately.
* If a task has unfinished dependencies, it remains `QUEUED`.
This guarantees `consumer_compile` waits until `generated_config.h` exists, while still allowing the independent tasks to execute concurrently alongside the producer chain.

## 8. DAG Representation
```text
generate_config_compile
        |
generate_config_run
        |
generated_config.h  <-- The generated artifact
        |
consumer_compile
        |
consumer_run

independent1_compile ----> (Concurrent)
independent2_compile ----> (Concurrent)
independent3_compile ----> (Concurrent)
```

## 9. SQLite Reference (A Real-World Analogy)
This producer-artifact-consumer pattern is extremely common in large projects. For example, in the **SQLite** database build process:
`lemon.c` is compiled to an executable → it runs and parses `parse.y` to produce `parse.h` → `tokenize.c` includes `parse.h`. 
*Note: Our demo uses this conceptual pattern to explain dependencies, but is entirely standalone and not copied from SQLite.*

---

## 10. Dashboard Architecture
The project includes a web UI to visualize the build process in real time.
* **Scheduler (`demo_scheduler.py`)**: The source of truth that makes all topological sorting and execution decisions.
* **Executor**: `subprocess` standard library executing real GCC commands.
* **FastAPI (`dashboard.py`)**: The backend communication layer that bridges the scheduler's events to the web. (It does not perform task scheduling).
* **WebSocket**: The real-time event transport that streams state changes to the browser.
* **Dashboard (`index.html`)**: The visualization layer that receives WebSocket events and renders the live state graph.

---

## 11. Prerequisites & Installation

### Prerequisites
* **Python 3.7+**
* **GCC compiler** installed and available on your system `PATH`. (On Windows, this is typically MinGW-w64).

### Install Requirements
The core scheduler uses only Python standard libraries. However, to run the Dashboard UI, you must install its communication dependencies:
```bash
pip install -r requirements.txt
```

---

## 12. Running the Dashboard
Start the FastAPI server:
```bash
python dashboard.py
```
Then open your web browser and navigate to: **http://127.0.0.1:8000**

*(Note: If you receive a `[Errno 10048] port 8000 already in use` error, it means another dashboard or application is already running on port 8000. You can check this on Windows by running `netstat -ano | findstr :8000` and killing the existing process, or simply use a different terminal where it's already running).*

## 13. How to Run the Wrong-Order Demo
1. Open the dashboard in your browser.
2. Click **Run Wrong-Order Demo**.
3. The UI will instantly show `consumer_compile` failing with a real GCC error because the required header does not exist yet.

## 14. How to Run the Dependency-Aware Demo
1. Click **Run Dependency-Aware Demo** in the dashboard.
2. Watch the dependency graph. The independent tasks will immediately start executing simultaneously. `consumer_compile` will safely wait in the QUEUED state until the producer generates the header, proving that the scheduler dynamically respects order without sacrificing safe parallelism.

## 15. How to Clean the Project
To remove all generated executables and headers, restoring a clean state:
```bash
python clean_demo.py
```
*(You can also use the "Clean" button in the Dashboard).*
