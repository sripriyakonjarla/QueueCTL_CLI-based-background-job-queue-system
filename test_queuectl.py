#!/usr/bin/env python3
"""Test script to validate QueueCTL core functionality."""

import time
import subprocess
import sys
import os
from pathlib import Path

# Colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

def run_command(cmd, timeout=30):
    """Run a command and return output."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)

def run_command_async(cmd):
    """Run a command asynchronously (non-blocking)."""
    try:
        if sys.platform == "win32":
            subprocess.Popen(
                cmd, shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
            )
        else:
            subprocess.Popen(
                cmd, shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        return True
    except Exception as e:
        return False

def test(name, test_func):
    """Run a test and report results."""
    print(f"\n{YELLOW}Testing: {name}{RESET}")
    try:
        result = test_func()
        if result:
            print(f"{GREEN}✓ PASS: {name}{RESET}")
            return True
        else:
            print(f"{RED}✗ FAIL: {name}{RESET}")
            return False
    except Exception as e:
        print(f"{RED}✗ ERROR: {name} - {e}{RESET}")
        return False

def cleanup():
    """Clean up test artifacts."""
    print(f"\n{YELLOW}Cleaning up...{RESET}")
    # Stop workers
    run_command("queuectl worker stop")
    # Remove database
    db_file = Path("queuectl.db")
    if db_file.exists():
        db_file.unlink()
    # Remove config
    config_file = Path.home() / ".queuectl" / "config.json"
    if config_file.exists():
        config_file.unlink()
    print(f"{GREEN}Cleanup complete{RESET}")

def test_basic_job_completion():
    """Test 1: Basic job completes successfully."""
    # Enqueue a simple job
    success, _, _ = run_command('queuectl enqueue \'{"id":"test1","command":"echo Hello"}\'')
    if not success:
        return False
    
    # Start worker
    run_command_async("queuectl worker start")
    time.sleep(0.5)  # Give worker time to start
    
    # Wait for job to complete
    time.sleep(2)
    
    # Check if job is completed
    success, output, _ = run_command("queuectl list --state completed")
    if not success:
        return False
    
    return "test1" in output

def test_failed_job_retry():
    """Test 2: Failed job retries with backoff and moves to DLQ."""
    # Set max retries to 2
    run_command("queuectl config set max-retries 2")
    
    # Enqueue a job that will fail
    run_command('queuectl enqueue \'{"id":"fail1","command":"exit 1"}\'')
    
    # Start worker
    run_command_async("queuectl worker start")
    time.sleep(0.5)
    
    # Wait for retries (with backoff: 1s, 2s = ~3s minimum)
    time.sleep(4)
    
    # Check if job moved to DLQ
    success, output, _ = run_command("queuectl dlq list")
    if not success:
        return False
    
    return "fail1" in output

def test_multiple_workers():
    """Test 3: Multiple workers process jobs without overlap."""
    # Stop existing workers
    run_command("queuectl worker stop")
    time.sleep(1)
    
    # Enqueue multiple jobs
    for i in range(3):
        run_command(f'queuectl enqueue \'{{"id":"multi{i}","command":"timeout /t 1"}}\'')
    
    # Start 2 workers
    run_command_async("queuectl worker start --count 2")
    time.sleep(1)
    
    # Wait for jobs to complete (3 jobs with 2 workers = 2 batches)
    time.sleep(3)
    
    # Check if all jobs completed
    success, output, _ = run_command("queuectl list --state completed")
    if not success:
        return False
    
    return all(f"multi{i}" in output for i in range(3))

def test_invalid_command():
    """Test 4: Invalid commands fail gracefully."""
    # Enqueue a job with invalid command
    run_command('queuectl enqueue \'{"id":"invalid1","command":"nonexistent_command_xyz"}\'')
    
    # Start worker
    run_command_async("queuectl worker start")
    time.sleep(1)
    
    # Wait a bit
    time.sleep(1)
    
    # Job should be in failed state (or DLQ if retries exhausted)
    success, output, _ = run_command("queuectl list --state failed")
    if success and "invalid1" in output:
        return True
    
    # Or in DLQ
    success, output, _ = run_command("queuectl dlq list")
    if success and "invalid1" in output:
        return True
    
    return False

def test_persistence():
    """Test 5: Job data survives restart."""
    # Enqueue a job
    run_command('queuectl enqueue \'{"id":"persist1","command":"echo Persisted"}\'')
    
    # Stop workers (simulating restart)
    run_command("queuectl worker stop")
    time.sleep(1)
    
    # Check job still exists
    success, output, _ = run_command("queuectl list")
    if not success or "persist1" not in output:
        return False
    
    # Start worker again
    run_command_async("queuectl worker start")
    time.sleep(1)
    time.sleep(2)
    
    # Job should complete
    success, output, _ = run_command("queuectl list --state completed")
    return success and "persist1" in output

def test_dlq_retry():
    """Test 6: DLQ retry functionality."""
    # Stop any existing workers first
    run_command("queuectl worker stop")
    time.sleep(1)
    
    # Ensure we have a job in DLQ
    run_command("queuectl config set max-retries 1")
    run_command('queuectl enqueue \'{"id":"dlqtest1","command":"exit 1"}\'')
    run_command_async("queuectl worker start")
    time.sleep(1)
    
    # Wait for initial attempt + 1 retry with backoff (1s) + processing time
    time.sleep(4)
    
    # Verify job is in DLQ
    success, output, _ = run_command("queuectl dlq list")
    if not success or "dlqtest1" not in output:
        return False
    
    # Stop workers before retrying
    run_command("queuectl worker stop")
    time.sleep(1)
    
    # Retry the job
    success, _, _ = run_command("queuectl dlq retry dlqtest1")
    if not success:
        return False
    
    # Job should be back in pending
    success, output, _ = run_command("queuectl list --state pending")
    return success and "dlqtest1" in output

def main():
    """Run all tests."""
    print(f"{YELLOW}{'='*60}")
    print("QueueCTL Test Suite")
    print(f"{'='*60}{RESET}")
    
    # Cleanup first
    cleanup()
    time.sleep(1)
    
    tests = [
        ("Basic Job Completion", test_basic_job_completion),
        ("Failed Job Retry & DLQ", test_failed_job_retry),
        ("Multiple Workers", test_multiple_workers),
        ("Invalid Command Handling", test_invalid_command),
        ("Persistence", test_persistence),
        ("DLQ Retry", test_dlq_retry),
    ]
    
    results = []
    for name, test_func in tests:
        result = test(name, test_func)
        results.append((name, result))
        # Stop workers between tests to avoid interference
        run_command("queuectl worker stop")
        time.sleep(1)  # Brief pause between tests
    
    # Summary
    print(f"\n{YELLOW}{'='*60}")
    print("Test Summary")
    print(f"{'='*60}{RESET}\n")
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = f"{GREEN}PASS{RESET}" if result else f"{RED}FAIL{RESET}"
        print(f"{status}: {name}")
    
    print(f"\n{YELLOW}Total: {passed}/{total} tests passed{RESET}")
    
    # Cleanup
    cleanup()
    
    return 0 if passed == total else 1

if __name__ == "__main__":
    sys.exit(main())

