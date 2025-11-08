"""Worker process management."""

import subprocess
import sys
import time
import multiprocessing
import os
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Signal handling (Unix only)
try:
    import signal
except ImportError:
    signal = None

from queuectl.storage import Storage
from queuectl.job import Job, JobState
from queuectl.config import Config


class Worker:
    """Worker process that executes jobs."""
    
    def __init__(self, worker_id: str, storage: Storage, config: Config, stop_event: multiprocessing.Event):
        self.worker_id = worker_id
        self.storage = storage
        self.config = config
        self.stop_event = stop_event
        self.current_job: Optional[Job] = None
    
    def run(self):
        """Main worker loop."""
        if signal:
            signal.signal(signal.SIGTERM, self._handle_signal)
            signal.signal(signal.SIGINT, self._handle_signal)
        
        while not self.stop_event.is_set():
            try:
                job = self.storage.get_pending_job(self.worker_id)
                
                if not job:
                    time.sleep(0.5)  # Poll interval
                    continue
                
                self.current_job = job
                self._process_job(job)
                self.current_job = None
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"Worker {self.worker_id} error: {e}", file=sys.stderr)
                if self.current_job:
                    try:
                        self.current_job.state = JobState.FAILED
                        self.storage.update_job(self.current_job, self.worker_id)
                    except:
                        pass
                time.sleep(1)
    
    def _process_job(self, job: Job):
        """Process a single job."""
        try:
            # Execute the command
            result = subprocess.run(
                job.command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
            )
            
            if result.returncode == 0:
                # Success
                job.mark_completed()
                self.storage.update_job(job, self.worker_id)
            else:
                # Failure - handle retry
                self._handle_failure(job)
                
        except subprocess.TimeoutExpired:
            # Timeout - treat as failure
            self._handle_failure(job)
        except FileNotFoundError:
            # Command not found - treat as failure
            self._handle_failure(job)
        except Exception as e:
            # Unexpected error - treat as failure
            print(f"Error executing job {job.id}: {e}", file=sys.stderr)
            self._handle_failure(job)
    
    def _handle_failure(self, job: Job):
        """Handle job failure with retry logic."""
        if job.should_retry():
            # Calculate exponential backoff
            backoff_base = self.config.get("backoff_base", 2)
            delay_seconds = backoff_base ** job.attempts
            next_retry_at = datetime.utcnow() + timedelta(seconds=delay_seconds)
            
            job.mark_failed(next_retry_at)
            self.storage.update_job(job, self.worker_id)
        else:
            # Max retries exceeded - move to DLQ
            job.mark_dead()
            self.storage.update_job(job, self.worker_id)
    
    def _handle_signal(self, signum, frame):
        """Handle shutdown signals gracefully."""
        if self.current_job:
            # Wait for current job to finish (with timeout)
            timeout = 30
            start = time.time()
            while self.current_job and (time.time() - start) < timeout:
                time.sleep(0.1)
        
        self.stop_event.set()


def worker_process(worker_id: str, db_path: str, config_path: str, stop_event: multiprocessing.Event):
    """Worker process entry point (runs in separate process)."""
    storage = Storage(db_path)
    config = Config()
    config.config_file = Path(config_path)
    config._config = config._load_config()
    
    worker = Worker(worker_id, storage, config, stop_event)
    worker.run()


class WorkerManager:
    """Manages multiple worker processes."""
    
    def __init__(self, storage: Storage, config: Config):
        self.storage = storage
        self.config = config
        self.pid_file = Path.home() / ".queuectl" / "workers.pid"
        self.pid_file.parent.mkdir(exist_ok=True)
        self.processes: list = []
        self.stop_event = multiprocessing.Event()
    
    def _load_pids(self) -> list:
        """Load worker PIDs from file."""
        if not self.pid_file.exists():
            return []
        try:
            with open(self.pid_file, "r") as f:
                data = json.load(f)
                return data.get("pids", [])
        except:
            return []
    
    def _save_pids(self, pids: list):
        """Save worker PIDs to file."""
        with open(self.pid_file, "w") as f:
            json.dump({"pids": pids}, f)
    
    def _clear_pids(self):
        """Clear PID file."""
        if self.pid_file.exists():
            self.pid_file.unlink()
    
    def start_workers(self, count: int = 1):
        """Start worker processes."""
        # Stop existing workers first
        self.stop_workers()
        
        self.stop_event = multiprocessing.Event()
        self.processes = []
        pids = []
        
        db_path = self.storage.db_path
        config_path = str(self.config.config_file)
        
        for i in range(count):
            worker_id = f"worker-{os.getpid()}-{i}"
            process = multiprocessing.Process(
                target=worker_process,
                args=(worker_id, db_path, config_path, self.stop_event),
                name=worker_id
            )
            process.start()
            self.processes.append(process)
            pids.append(process.pid)
        
        self._save_pids(pids)
        return len(self.processes)
    
    def stop_workers(self):
        """Stop all worker processes gracefully."""
        # Stop processes we know about
        if self.stop_event:
            self.stop_event.set()
        
        for process in self.processes:
            if process.is_alive():
                process.join(timeout=5)
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=2)
                    if process.is_alive():
                        process.kill()
        
        # Also stop any processes from PID file (from previous invocations)
        pids = self._load_pids()
        for pid in pids:
            try:
                if signal:
                    os.kill(pid, signal.SIGTERM)
                else:
                    # Windows: use terminate
                    import subprocess
                    proc = subprocess.Popen(['taskkill', '/F', '/PID', str(pid)], 
                                           stdout=subprocess.DEVNULL, 
                                           stderr=subprocess.DEVNULL)
                    proc.wait()
                # Wait a bit
                time.sleep(1)
                # Force kill if still alive
                try:
                    os.kill(pid, 0)  # Check if process exists
                    if signal:
                        os.kill(pid, signal.SIGKILL)
                    else:
                        import subprocess
                        subprocess.Popen(['taskkill', '/F', '/PID', str(pid)], 
                                        stdout=subprocess.DEVNULL, 
                                        stderr=subprocess.DEVNULL)
                except (ProcessLookupError, OSError):
                    pass  # Process already dead
            except (ProcessLookupError, OSError):
                pass  # Process doesn't exist
            except PermissionError:
                pass  # Can't kill process
        
        self.processes = []
        self._clear_pids()
    
    def get_active_worker_count(self) -> int:
        """Get count of active worker processes."""
        count = sum(1 for p in self.processes if p.is_alive())
        
        # Also check PID file
        pids = self._load_pids()
        for pid in pids:
            try:
                if sys.platform == "win32":
                    # Windows: use tasklist to check
                    proc = subprocess.run(
                        ['tasklist', '/FI', f'PID eq {pid}'],
                        capture_output=True,
                        timeout=1
                    )
                    if proc.returncode == 0 and str(pid) in proc.stdout.decode():
                        if pid not in [p.pid for p in self.processes]:
                            count += 1
                else:
                    os.kill(pid, 0)  # Check if process exists
                    if pid not in [p.pid for p in self.processes]:
                        count += 1
            except (ProcessLookupError, OSError, subprocess.TimeoutExpired):
                pass
        
        return count

