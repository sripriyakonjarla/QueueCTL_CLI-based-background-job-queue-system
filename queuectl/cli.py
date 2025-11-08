"""CLI interface for queuectl."""

import json
import uuid
import click
from tabulate import tabulate
from typing import Optional

from queuectl.storage import Storage
from queuectl.job import Job, JobState
from queuectl.config import Config
from queuectl.worker import WorkerManager


# Global instances
_storage = None
_config = None
_worker_manager = None


def get_storage():
    """Get storage instance."""
    global _storage
    if _storage is None:
        _storage = Storage()
    return _storage


def get_config():
    """Get config instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config


def get_worker_manager():
    """Get worker manager instance."""
    global _worker_manager
    if _worker_manager is None:
        _worker_manager = WorkerManager(get_storage(), get_config())
    return _worker_manager


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """QueueCTL - A CLI-based background job queue system."""
    pass


@cli.command()
@click.argument("job_data", required=False)
@click.option("--file", "-f", type=click.Path(exists=True), help="Read job data from a JSON file")
def enqueue(job_data, file):
    """Enqueue a new job.
    
    JOB_DATA: JSON string with job details. Must include 'id' and 'command'.
    Use --file to read from a file instead (recommended for PowerShell).
    
    Example (Linux/Mac): queuectl enqueue '{"id":"job1","command":"sleep 2"}'
    Example (PowerShell): queuectl enqueue --file job.json
    Example (PowerShell variable): $json = '{"id":"job1","command":"echo Hello"}'; queuectl enqueue $json
    """
    try:
        # Read from file if provided
        if file:
            with open(file, 'r', encoding='utf-8') as f:
                job_data = f.read().strip()
        elif not job_data:
            click.echo("Error: Either JOB_DATA argument or --file option is required", err=True)
            return
        
        # Strip any surrounding quotes that might be added by the shell
        job_data = job_data.strip().strip('"').strip("'")
        
        # Try to parse as JSON
        try:
            data = json.loads(job_data)
        except json.JSONDecodeError:
            # PowerShell might have stripped inner quotes, try to fix it
            # Convert {id:job1,command:echo Hello} to {"id":"job1","command":"echo Hello"}
            import re
            # Add quotes around keys and string values
            fixed_data = re.sub(r'(\w+):', r'"\1":', job_data)  # Fix keys
            fixed_data = re.sub(r':([^,}\s][^,}]*)', r':"\1"', fixed_data)  # Fix values
            fixed_data = fixed_data.replace('""', '"')  # Remove double quotes
            try:
                data = json.loads(fixed_data)
            except:
                # If still fails, raise the original error
                data = json.loads(job_data)
        
        # Validate required fields
        if "id" not in data or "command" not in data:
            click.echo("Error: Job must include 'id' and 'command' fields", err=True)
            return
        
        # Get max_retries from config if not provided
        max_retries = data.get("max_retries", get_config().get("max_retries", 3))
        
        job = Job(
            id=data["id"],
            command=data["command"],
            max_retries=max_retries,
        )
        
        storage = get_storage()
        if storage.add_job(job):
            click.echo(f"Job '{job.id}' enqueued successfully")
        else:
            click.echo(f"Error: Job '{job.id}' already exists", err=True)
            
    except json.JSONDecodeError as e:
        click.echo(f"Error: Invalid JSON format - {e}", err=True)
        click.echo(f"Received: {job_data[:100]}...", err=True)
        click.echo("\nPowerShell users - try one of these methods:", err=True)
        click.echo('  1. Use --file option: queuectl enqueue --file job.json', err=True)
        click.echo('  2. Use escaped quotes: queuectl enqueue \'{\"id\":\"job1\",\"command\":\"echo Hello\"}\'', err=True)
        click.echo('  3. Use double single-quotes: queuectl enqueue \'\'{"id":"job1","command":"echo Hello"}\'\'', err=True)
    except Exception as e:
        click.echo(f"Error: {e}", err=True)


@cli.group()
def worker():
    """Manage worker processes."""
    pass


@worker.command()
@click.option("--count", default=1, help="Number of workers to start")
def start(count):
    """Start worker processes.
    
    Example: queuectl worker start --count 3
    """
    try:
        manager = get_worker_manager()
        started = manager.start_workers(count)
        click.echo(f"Started {started} worker(s)")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)


@worker.command()
def stop():
    """Stop all running workers gracefully.
    
    Example: queuectl worker stop
    """
    try:
        manager = get_worker_manager()
        manager.stop_workers()
        click.echo("All workers stopped")
    except Exception as e:
        click.echo(f"Error: {e}", err=True)


@cli.command()
def status():
    """Show summary of all job states and active workers.
    
    Example: queuectl status
    """
    try:
        storage = get_storage()
        stats = storage.get_stats()
        manager = get_worker_manager()
        active_workers = manager.get_active_worker_count()
        
        click.echo("\n=== Queue Status ===\n")
        click.echo(f"Active Workers: {active_workers}")
        click.echo("\nJob States:")
        table = [
            ["Pending", stats["pending"]],
            ["Processing", stats["processing"]],
            ["Completed", stats["completed"]],
            ["Failed", stats["failed"]],
            ["Dead (DLQ)", stats["dead"]],
        ]
        click.echo(tabulate(table, headers=["State", "Count"], tablefmt="simple"))
        click.echo()
        
    except Exception as e:
        click.echo(f"Error: {e}", err=True)


@cli.command()
@click.option("--state", type=click.Choice(["pending", "processing", "completed", "failed", "dead"]), 
              help="Filter jobs by state")
def list(state):
    """List jobs, optionally filtered by state.
    
    Example: queuectl list --state pending
    """
    try:
        storage = get_storage()
        state_enum = JobState(state) if state else None
        jobs = storage.list_jobs(state_enum)
        
        if not jobs:
            click.echo("No jobs found")
            return
        
        table = []
        for job in jobs:
            table.append([
                job.id,
                job.command[:50] + "..." if len(job.command) > 50 else job.command,
                job.state.value,
                job.attempts,
                job.max_retries,
                job.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            ])
        
        click.echo(tabulate(
            table,
            headers=["ID", "Command", "State", "Attempts", "Max Retries", "Created At"],
            tablefmt="simple"
        ))
        
    except Exception as e:
        click.echo(f"Error: {e}", err=True)


@cli.group()
def dlq():
    """Manage Dead Letter Queue."""
    pass


@dlq.command("list")
def dlq_list():
    """List all jobs in the Dead Letter Queue.
    
    Example: queuectl dlq list
    """
    try:
        storage = get_storage()
        dead_jobs = storage.list_jobs(JobState.DEAD)
        
        if not dead_jobs:
            click.echo("No jobs in Dead Letter Queue")
            return
        
        table = []
        for job in dead_jobs:
            table.append([
                job.id,
                job.command[:50] + "..." if len(job.command) > 50 else job.command,
                job.attempts,
                job.max_retries,
                job.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
            ])
        
        click.echo(tabulate(
            table,
            headers=["ID", "Command", "Attempts", "Max Retries", "Failed At"],
            tablefmt="simple"
        ))
        
    except Exception as e:
        click.echo(f"Error: {e}", err=True)


@dlq.command()
@click.argument("job_id")
def retry(job_id):
    """Retry a job from the Dead Letter Queue.
    
    JOB_ID: The ID of the job to retry.
    
    Example: queuectl dlq retry job1
    """
    try:
        storage = get_storage()
        job = storage.get_job(job_id)
        
        if not job:
            click.echo(f"Error: Job '{job_id}' not found", err=True)
            return
        
        if job.state != JobState.DEAD:
            click.echo(f"Error: Job '{job_id}' is not in Dead Letter Queue", err=True)
            return
        
        # Reset job to pending state
        job.state = JobState.PENDING
        job.attempts = 0
        job.next_retry_at = None
        storage.update_job(job)
        
        click.echo(f"Job '{job_id}' moved back to pending queue")
        
    except Exception as e:
        click.echo(f"Error: {e}", err=True)


@cli.group()
def config():
    """Manage configuration."""
    pass


@config.command("set")
@click.argument("key")
@click.argument("value")
def config_set(key, value):
    """Set a configuration value.
    
    KEY: Configuration key (e.g., max-retries, backoff-base)
    VALUE: Configuration value
    
    Example: queuectl config set max-retries 5
    """
    try:
        config = get_config()
        
        # Convert value to appropriate type
        if key == "max-retries" or key == "backoff-base":
            try:
                value = int(value)
            except ValueError:
                click.echo(f"Error: '{value}' is not a valid integer", err=True)
                return
        
        # Map CLI keys to config keys
        key_map = {
            "max-retries": "max_retries",
            "backoff-base": "backoff_base",
        }
        
        config_key = key_map.get(key, key)
        config.set(config_key, value)
        click.echo(f"Configuration '{key}' set to '{value}'")
        
    except Exception as e:
        click.echo(f"Error: {e}", err=True)


@config.command("get")
@click.argument("key", required=False)
def config_get(key):
    """Get configuration value(s).
    
    KEY: Optional configuration key. If omitted, shows all configuration.
    
    Example: queuectl config get max-retries
    """
    try:
        config = get_config()
        
        if key:
            # Map CLI keys to config keys
            key_map = {
                "max-retries": "max_retries",
                "backoff-base": "backoff_base",
            }
            config_key = key_map.get(key, key)
            value = config.get(config_key)
            if value is not None:
                click.echo(f"{key}: {value}")
            else:
                click.echo(f"Configuration '{key}' not found", err=True)
        else:
            all_config = config.get_all()
            click.echo("\n=== Configuration ===\n")
            for k, v in all_config.items():
                # Map back to CLI keys
                cli_key = k.replace("_", "-")
                click.echo(f"{cli_key}: {v}")
            click.echo()
        
    except Exception as e:
        click.echo(f"Error: {e}", err=True)


def main():
    """Entry point for CLI."""
    cli()


if __name__ == "__main__":
    main()

