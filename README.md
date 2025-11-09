# QueueCTL - CLI-Based Background Job Queue System

[![Python](https://img.shields.io/badge/Python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

> **Backend Developer Internship Assignment - Flam**

A production-grade CLI-based background job queue system with parallel worker processes, automatic retry mechanism using exponential backoff, and Dead Letter Queue (DLQ) support for permanently failed jobs.

## Features

- ✅ **Job Queue Management** - Enqueue and manage background jobs via CLI
- ✅ **Parallel Workers** - Run multiple worker processes simultaneously
- ✅ **Automatic Retries** - Exponential backoff retry mechanism for failed jobs
- ✅ **Dead Letter Queue (DLQ)** - Isolate and retry permanently failed jobs
- ✅ **Persistent Storage** - SQLite database ensures data survives restarts
- ✅ **Thread-Safe Operations** - Row-level locking prevents race conditions
- ✅ **Configurable Settings** - Customize retry count and backoff parameters
- ✅ **Graceful Shutdown** - Workers complete current jobs before stopping
- ✅ **Job State Tracking** - Monitor job lifecycle through multiple states
- ✅ **CLI Interface** - User-friendly command-line interface with help texts

## Table of Contents

- [Tech Stack](#-tech-stack)
- [Installation](#-installation)
- [Quick Start](#-quick-start)
- [Usage](#-usage)
- [Architecture](#%EF%B8%8F-architecture)
- [Configuration](#%EF%B8%8F-configuration)
- [Testing](#-testing)
- [Design Decisions](#-design-decisions)
- [Demo Video](#-demo-video)
- [Troubleshooting](#-troubleshooting)

## Tech Stack

- **Language**: Python 3.7+
- **Database**: SQLite (embedded, zero-configuration)
- **CLI Framework**: Click
- **Concurrency**: Multiprocessing (true parallelism)
- **Storage**: File-based persistence (SQLite + JSON config)

## Installation

### Prerequisites

- Python 3.7 or higher
- pip (Python package manager)

### Setup Instructions

```bash
# 1. Clone the repository
git clone https://github.com/sripriyakonjarla/QueueCTL_CLI-based-background-job-queue-system.git
cd QueueCTL_CLI-based-background-job-queue-system

# 2. Install dependencies
pip install -r requirements.txt

# 3. Install the package in development mode
pip install -e .

# 4. Verify installation
queuectl --version
```

### Dependencies

- `click` - CLI framework
- `tabulate` - Pretty table formatting

## Quick Start

```bash
# 1. Enqueue some jobs
queuectl enqueue '{"id":"job1","command":"echo Hello World"}'
queuectl enqueue '{"id":"job2","command":"sleep 2"}'
queuectl enqueue '{"id":"job3","command":"echo Task Complete"}'

# 2. Start workers to process jobs
queuectl worker start --count 2

# 3. Check queue status
queuectl status

# 4. View completed jobs
queuectl list --state completed

# 5. Stop workers when done
queuectl worker stop
```

## Usage

### 1. Enqueue Jobs

Add jobs to the queue with a unique ID and shell command:

```bash
# Basic job
queuectl enqueue '{"id":"job1","command":"echo Hello World"}'

# Job with sleep
queuectl enqueue '{"id":"job2","command":"sleep 2"}'

# Custom max retries
queuectl enqueue '{"id":"job3","command":"python script.py","max_retries":5}'

# PowerShell users - use file input for complex JSON
queuectl enqueue --file job.json
```

**Job Specification:**
```json
{
  "id": "unique-job-id",
  "command": "echo 'Hello World'",
  "max_retries": 3  // Optional, defaults to config value
}
```

### 2. Manage Workers

Start and stop worker processes:

```bash
# Start a single worker
queuectl worker start

# Start multiple workers for parallel processing
queuectl worker start --count 3

# Stop all workers gracefully (completes current jobs)
queuectl worker stop
```

### 3. Monitor Jobs

Check job status and queue statistics:

```bash
# View queue summary and active workers
queuectl status

# List all jobs
queuectl list

# Filter jobs by state
queuectl list --state pending
queuectl list --state processing
queuectl list --state completed
queuectl list --state failed
queuectl list --state dead
```

### 4. Dead Letter Queue (DLQ)

Manage permanently failed jobs:

```bash
# List all jobs in DLQ
queuectl dlq list

# Retry a specific job from DLQ
queuectl dlq retry job1

# Job will be moved back to pending state with reset attempts
```

### 5. Configuration

Customize retry and backoff settings:

```bash
# Set maximum retry attempts
queuectl config set max-retries 5

# Set exponential backoff base
queuectl config set backoff-base 2

# View all configuration
queuectl config get

# View specific config value
queuectl config get max-retries
```

### 6. Help Commands

```bash
# General help
queuectl --help

# Command-specific help
queuectl enqueue --help
queuectl worker --help
queuectl dlq --help
```

## Architecture

![Architecture Diagram](./Architecture_Diagram.png)

### System Overview

```
┌─────────────┐
│   CLI       │  User interacts via command-line
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────┐
│          Storage Layer (SQLite)         │
│  - Job queue with states                │
│  - Row-level locking for concurrency    │
│  - Persistent across restarts           │
└──────┬──────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│       Worker Manager                    │
│  - Spawns multiple worker processes     │
│  - Manages worker lifecycle             │
│  - Graceful shutdown handling           │
└──────┬──────────────────────────────────┘
       │
       ▼
┌─────────────────────────────────────────┐
│    Worker Processes (Parallel)          │
│  - Fetch jobs from queue                │
│  - Execute shell commands               │
│  - Handle retries with backoff          │
│  - Move failed jobs to DLQ              │
└─────────────────────────────────────────┘
```

### Job Lifecycle

```
┌─────────┐
│ PENDING │  ──────────────────┐
└────┬────┘                    │
     │                         │
     │ Worker picks job        │
     ▼                         │
┌────────────┐                 │
│ PROCESSING │                 │
└─────┬──────┘                 │
      │                        │
      ├─── Success ───► ┌───────────┐
      │                 │ COMPLETED │
      │                 └───────────┘
      │
      └─── Failure ───► ┌────────┐
                        │ FAILED │
                        └────┬───┘
                             │
                   ┌─────────┴─────────┐
                   │                   │
            Retry available      Max retries
                   │              exceeded
                   │                   │
                   ▼                   ▼
              ┌─────────┐         ┌──────┐
              │ PENDING │         │ DEAD │ (DLQ)
              └─────────┘         └───┬──┘
                                      │
                              Manual retry via CLI
                                      │
                                      ▼
                                 ┌─────────┐
                                 │ PENDING │
                                 └─────────┘
```

### Job States

| State | Description |
|-------|-------------|
| `pending` | Waiting to be picked up by a worker |
| `processing` | Currently being executed by a worker |
| `completed` | Successfully executed |
| `failed` | Failed but retryable (waiting for backoff) |
| `dead` | Permanently failed, moved to DLQ |

### Retry Mechanism

**Exponential Backoff Formula:**
```
delay = backoff_base ^ attempts (seconds)
```

**Example** (backoff_base = 2, max_retries = 3):

| Attempt | Delay | Total Time |
|---------|-------|------------|
| 1 | 0s (immediate) | 0s |
| 2 | 2¹ = 2s | 2s |
| 3 | 2² = 4s | 6s |
| 4 | 2³ = 8s | 14s |
| After max_retries | → DLQ | - |

### Concurrency & Locking

- **Row-Level Locking**: SQLite `BEGIN IMMEDIATE` transaction ensures only one worker processes a job
- **State Verification**: Double-check job state before processing to prevent race conditions
- **Worker Isolation**: Each worker runs in a separate process (true parallelism)

### Data Persistence

| Component | Location | Purpose |
|-----------|----------|----------|
| **Job Database** | `queuectl.db` | Stores all job data (SQLite) |
| **Configuration** | `~/.queuectl/config.json` | User settings (max_retries, backoff_base) |
| **Worker PIDs** | `~/.queuectl/workers.pid` | Tracks active worker processes |

### Command Execution

- Jobs execute as shell commands using `subprocess`
- Exit code `0` = success, non-zero = failure
- 5-minute timeout per job to prevent hanging
- STDOUT/STDERR captured for debugging

## Configuration

### Default Settings

```json
{
  "max_retries": 3,
  "backoff_base": 2
}
```

### Configuration Options

| Parameter | Description | Default | Valid Range |
|-----------|-------------|---------|-------------|
| `max_retries` | Maximum retry attempts before DLQ | 3 | 0-10 |
| `backoff_base` | Exponential backoff multiplier | 2 | 1-10 |

### Configuration File Location

- **Path**: `~/.queuectl/config.json`
- **Format**: JSON
- **Persistence**: Settings persist across restarts

## Testing

### Automated Test Suite

Run the comprehensive test suite:

```bash
python test_queuectl.py
```

### Test Coverage

| Test | Description | Validates |
|------|-------------|----------|
| **Basic Job Completion** | Simple job executes successfully | Job execution, state transitions |
| **Failed Job Retry & DLQ** | Failed job retries then moves to DLQ | Retry mechanism, exponential backoff, DLQ |
| **Multiple Workers** | Parallel workers process jobs | Concurrency, no duplicate processing |
| **Invalid Command** | Non-existent command fails gracefully | Error handling |
| **Persistence** | Jobs survive restart | Data persistence |
| **DLQ Retry** | Retry job from DLQ | DLQ retry functionality |

### Manual Testing

```bash
# Test 1: Basic job
queuectl enqueue '{"id":"test1","command":"echo Success"}'
queuectl worker start
queuectl list --state completed

# Test 2: Failing job
queuectl config set max-retries 2
queuectl enqueue '{"id":"test2","command":"exit 1"}'
# Wait ~6 seconds for retries
queuectl dlq list

# Test 3: Multiple workers
queuectl enqueue '{"id":"test3","command":"sleep 2"}'
queuectl enqueue '{"id":"test4","command":"sleep 2"}'
queuectl worker start --count 2
queuectl status
```

## Design Decisions & Trade-offs

### Technology Choices

| Decision | Rationale | Trade-off |
|----------|-----------|----------|
| **SQLite** | Zero-configuration, embedded database. No separate server needed. ACID compliance. | Limited to single-machine deployment. Not suitable for distributed systems. |
| **Multiprocessing** | True parallelism (bypasses Python GIL). Each worker is independent. | Higher memory overhead than threading. |
| **Click Framework** | Industry-standard CLI framework. Auto-generates help text. | Adds dependency, but minimal. |
| **Row-Level Locking** | Prevents duplicate job processing. Uses SQLite transactions. | Slight performance overhead for locking. |
| **File-based Config** | Simple JSON file. Easy to edit manually. | No validation on manual edits. |

### Assumptions

1. **Single Machine**: System runs on one machine (not distributed)
2. **Trusted Commands**: Job commands are trusted (no sandboxing)
3. **Moderate Scale**: Designed for 100s-1000s of jobs, not millions
4. **Sequential Execution**: Each job runs once at a time (no parallel execution of same job)
5. **Network Not Required**: All operations are local

### Simplifications

- **No Job Priority**: All jobs processed FIFO (First In, First Out)
- **No Scheduled Jobs**: No `run_at` or delayed execution
- **No Job Dependencies**: Jobs are independent
- **Fixed Timeout**: 5-minute timeout for all jobs
- **No Output Storage**: Job output not persisted (only exit code)

### Security Considerations

- Commands execute with user's permissions
- No input sanitization (assumes trusted input)
- Database file has default file permissions
- No authentication/authorization layer

### Scalability

**Current Limits:**
- Workers: 1-10 recommended
- Jobs: 10,000+ supported
- Throughput: ~100 jobs/minute (depends on job duration)

**Bottlenecks:**
- SQLite write throughput
- Disk I/O for database
- Process spawning overhead

## Demo Video

**[Watch the demo video](https://drive.google.com/file/d/18xKKzVBjWCglWYNHUxclJF1MKNJjA-Rv/view?usp=sharing)**

The demo covers:
1. Enqueuing multiple jobs
2. Starting parallel workers
3. Monitoring job status
4. Handling failed jobs and DLQ
5. Retrying jobs from DLQ
6. Configuration management

## Troubleshooting

### Common Issues

#### Workers not processing jobs

**Symptoms:** Jobs stay in pending state

**Solutions:**
```bash
# Check if workers are running
queuectl status

# Verify pending jobs exist
queuectl list --state pending

# Restart workers
queuectl worker stop
queuectl worker start
```

#### Jobs stuck in processing state

**Symptoms:** Jobs remain in processing after worker crash

**Solutions:**
```bash
# Stop all workers
queuectl worker stop

# Manually reset stuck jobs (requires direct DB access)
# Or delete database and re-enqueue
rm queuectl.db
```

#### Database locked errors

**Symptoms:** `database is locked` error messages

**Cause:** Multiple processes trying to write simultaneously

**Solutions:**
- Ensure only one QueueCTL instance per database
- Reduce number of workers
- Check for zombie worker processes

#### JSON parsing errors (PowerShell)

**Symptoms:** `Invalid JSON format` errors

**Solutions:**
```powershell
# Method 1: Use file input
queuectl enqueue --file job.json

# Method 2: Use proper escaping
queuectl enqueue '{"id":"job1","command":"echo Hello"}'

# Method 3: Use variables
$json = '{"id":"job1","command":"echo Hello"}'
queuectl enqueue $json
```

#### Import errors after installation

**Symptoms:** `ModuleNotFoundError: No module named 'queuectl'`

**Solutions:**
```bash
# Reinstall in development mode
pip install -e .

# Verify installation
pip list | grep queuectl
```

## Additional Resources

### Project Structure

```
QueueCTL/
├── queuectl/
│   ├── __init__.py
│   ├── cli.py           # CLI commands and interface
│   ├── config.py        # Configuration management
│   ├── job.py           # Job model and state management
│   ├── storage.py       # SQLite database operations
│   └── worker.py        # Worker process management
├── test_queuectl.py     # Automated test suite
├── requirements.txt     # Python dependencies
├── setup.py            # Package installation config
└── README.md           # This file
```

### Code Quality

- **Separation of Concerns**: Clear module boundaries
- **Type Hints**: Function signatures include type annotations
- **Docstrings**: All public functions documented
- **Error Handling**: Graceful error messages
- **Thread Safety**: Proper locking mechanisms

## License

MIT License - feel free to use for learning and projects.

## 👤 Author

**Sripriya Konjarla**
- GitHub: [@sripriyakonjarla](https://github.com/sripriyakonjarla)
- Repository: [QueueCTL](https://github.com/sripriyakonjarla/QueueCTL_CLI-based-background-job-queue-system)


---

