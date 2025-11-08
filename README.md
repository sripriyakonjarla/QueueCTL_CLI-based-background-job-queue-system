# QueueCTL - Background Job Queue System

A production-grade CLI-based background job queue system with worker processes, automatic retries with exponential backoff, and Dead Letter Queue (DLQ) support.

## 🚀 Features

- ✅ **Job Management**: Enqueue, list, and track background jobs
- ✅ **Worker Processes**: Run multiple workers in parallel
- ✅ **Automatic Retries**: Exponential backoff retry mechanism
- ✅ **Dead Letter Queue**: Handle permanently failed jobs
- ✅ **Persistent Storage**: SQLite-based storage survives restarts
- ✅ **Graceful Shutdown**: Workers finish current jobs before exiting
- ✅ **Configuration Management**: Configurable retry count and backoff base
- ✅ **Thread-Safe**: Prevents duplicate job processing

## 📦 Installation

### Prerequisites

- Python 3.7 or higher
- pip

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd project
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Install the package:
```bash
pip install -e .
```

## 💻 Usage

### Basic Commands

#### Enqueue a Job

**Works on all platforms (including PowerShell):**

```bash
queuectl enqueue '{"id":"job1","command":"echo Hello World"}'
```

```bash
queuectl enqueue '{"id":"job2","command":"sleep 2"}'
```

#### Start Workers

Start a single worker:
```bash
queuectl worker start
```

Start multiple workers:
```bash
queuectl worker start --count 3
```

#### Stop Workers

```bash
queuectl worker stop
```

#### Check Status

```bash
queuectl status
```

Output:
```
=== Queue Status ===

Active Workers: 3

Job States:
State       Count
---------  ------
Pending         5
Processing      2
Completed      10
Failed         1
Dead (DLQ)      0
```

#### List Jobs

List all jobs:
```bash
queuectl list
```

List jobs by state:
```bash
queuectl list --state pending
queuectl list --state completed
queuectl list --state failed
```

#### Dead Letter Queue

List jobs in DLQ:
```bash
queuectl dlq list
```

Retry a job from DLQ:
```bash
queuectl dlq retry job1
```

#### Configuration

Set configuration:
```bash
queuectl config set max-retries 5
queuectl config set backoff-base 3
```

Get configuration:
```bash
queuectl config get max-retries
queuectl config get
```



### Data Persistence

- **Database**: SQLite database (`queuectl.db` in current directory)
- **Configuration**: `~/.queuectl/config.json`
- **Worker PIDs**: `~/.queuectl/workers.pid` (for cross-invocation management)

### Retry Mechanism

Exponential backoff formula:
```
delay = base ^ attempts seconds
```

Example with `backoff_base = 2`:
- Attempt 1: 2^0 = 1 second
- Attempt 2: 2^1 = 2 seconds
- Attempt 3: 2^2 = 4 seconds
- Attempt 4: 2^3 = 8 seconds

After `max_retries` attempts, the job is moved to DLQ.

## 🧪 Testing

Run the test script to validate core functionality:

```bash
python test_queuectl.py
```

The test script validates:
- ✅ Basic job completion
- ✅ Failed job retries with backoff
- ✅ Multiple workers processing jobs
- ✅ Invalid commands fail gracefully
- ✅ Job persistence across restarts
- ✅ Dead Letter Queue functionality

## 📋 Example Workflows

### Example 1: Simple Job Execution

```bash
# Enqueue a job
queuectl enqueue '{"id":"test1","command":"echo Success"}'

# Start a worker
queuectl worker start

# Wait a moment, then check status
queuectl status

# List completed jobs
queuectl list --state completed
```

### Example 2: Job with Retries

```bash
# Set max retries to 2
queuectl config set max-retries 2

# Enqueue a job that will fail
queuectl enqueue '{"id":"fail1","command":"exit 1"}'

# Start worker
queuectl worker start

# Monitor the job (it will retry and eventually move to DLQ)
queuectl list --state failed
queuectl dlq list
```

### Example 3: Multiple Workers

```bash
# Enqueue multiple jobs
queuectl enqueue '{"id":"job1","command":"sleep 1"}'
queuectl enqueue '{"id":"job2","command":"sleep 1"}'
queuectl enqueue '{"id":"job3","command":"sleep 1"}'

# Start 3 workers
queuectl worker start --count 3

# Check status (should see jobs being processed in parallel)
queuectl status
```

## 🔧 Configuration

Default configuration:
- `max_retries`: 3
- `backoff_base`: 2

Configuration is stored in `~/.queuectl/config.json` and persists across sessions.

## ⚙️ Assumptions & Trade-offs

### Assumptions

1. **Command Execution**: Jobs execute shell commands. Commands that return non-zero exit codes are considered failures.
2. **Timeout**: Jobs have a 5-minute timeout. Longer-running jobs should be split into smaller tasks.
3. **Database Location**: SQLite database is created in the current working directory.
4. **Worker Management**: Workers are managed per CLI invocation. PID files allow stopping workers from different terminal sessions.
5. **Cross-Platform Compatibility**: The CLI automatically handles PowerShell's quote-stripping behavior, making the same syntax work across Windows, Linux, and Mac.

### Trade-offs

1. **SQLite for Persistence**: Chosen for simplicity and zero-configuration. For high-throughput scenarios, consider PostgreSQL or Redis.
2. **Polling vs Event-Driven**: Workers poll for jobs every 0.5 seconds. For lower latency, consider event-driven architecture.
3. **Process-based Workers**: Using multiprocessing for true parallelism. Thread-based workers would be lighter but limited by GIL.
4. **Exponential Backoff**: Simple implementation. More sophisticated backoff strategies (jitter, max delay) could be added.

## 🐛 Troubleshooting

### Workers not processing jobs

1. Check if workers are running: `queuectl status`
2. Verify jobs are in pending state: `queuectl list --state pending`
3. Check for errors in worker processes

### Jobs stuck in processing

If a worker crashes, jobs may remain in `processing` state. You can manually reset them or restart workers.

### Database locked errors

SQLite uses file-level locking. If you see locking errors, ensure only one instance is accessing the database at a time.

## 🎥 Demo Video

A working CLI demo video is available at: [Demo Video Link](https://drive.google.com/your-demo-link)

*Note: Replace the link above with your actual demo video URL after uploading.*





