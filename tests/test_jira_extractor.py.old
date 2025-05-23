#!/usr/bin/env python3
"""
Test cases for Jirax CLI
This script runs several test cases to verify the functionality of the Jira extractor
"""
import os
import sys
import subprocess
import csv
from datetime import datetime
import toml
from rich.console import Console
from rich.table import Table

console = Console()

# Output directory for test results
TEST_OUTPUT_DIR = "./test_results"

def run_test(name, command, expected_success=True):
    """Run a test case and report results"""
    console.print(f"\n[bold cyan]Running test:[/bold cyan] {name}")
    console.print(f"[dim]Command:[/dim] {command}")
    
    try:
        # Run the command
        process = subprocess.run(
            command,
            shell=True,
            check=False,
            capture_output=True,
            text=True
        )
        
        # Check exit code
        success = (process.returncode == 0) == expected_success
        
        if success:
            console.print(f"[bold green]✓ Test passed[/bold green]")
        else:
            console.print(f"[bold red]✗ Test failed[/bold red]")
            console.print(f"[red]Exit code: {process.returncode}[/red]")
        
        # Print output
        if process.stdout:
            console.print("[dim]--- Output ---[/dim]")
            console.print(process.stdout)
        
        # Print errors
        if process.stderr:
            console.print("[dim]--- Errors ---[/dim]")
            console.print(f"[red]{process.stderr}[/red]")
        
        return {
            "name": name,
            "command": command,
            "success": success,
            "exit_code": process.returncode,
            "stdout": process.stdout,
            "stderr": process.stderr
        }
    
    except Exception as e:
        console.print(f"[bold red]✗ Test error:[/bold red] {str(e)}")
        return {
            "name": name,
            "command": command,
            "success": False,
            "error": str(e)
        }

def analyze_csv(file_path):
    """Analyze a CSV file and return basic stats"""
    try:
        with open(file_path, 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)
            rows = list(reader)
            
            if not rows:
                return {"row_count": 0, "columns": []}
            
            return {
                "row_count": len(rows),
                "columns": list(rows[0].keys()),
                "sample": rows[0] if rows else None
            }
    except Exception as e:
        return {"error": str(e)}

def main():
    """Run test cases for Jira extractor"""
    # Ensure we have the environment set up
    os.makedirs(TEST_OUTPUT_DIR, exist_ok=True)
    
    # Verify config exists
    if not os.path.exists("config.toml"):
        console.print("[bold red]Error:[/bold red] config.toml not found. Please create configuration file first.")
        sys.exit(1)
    
    # Load config to get project information
    try:
        config = toml.load("config.toml")
        default_project = config.get('extraction', {}).get('default_project', '')
    except Exception:
        default_project = "LEARNJIRA"  # Default fallback
    
    # Use LEARNJIRA if default project not set
    test_project = default_project or "LEARNJIRA"
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results = []
    
    # Test case 1: Basic extraction with project
    cmd1 = f"source .venv/bin/activate && PYTHONPATH=. python jirax.py extract --project {test_project} --output-path {TEST_OUTPUT_DIR}/test1_{timestamp}.csv --no-preview"
    results.append(run_test("Basic project extraction", cmd1))
    
    # Test case 2: Extraction with simple JQL query
    cmd2 = f"source .venv/bin/activate && PYTHONPATH=. python jirax.py extract --query \"project = {test_project} ORDER BY created DESC\" --output-path {TEST_OUTPUT_DIR}/test2_{timestamp}.csv --no-preview"
    results.append(run_test("Simple JQL query", cmd2))
    
    # Test case 3: Extract with priority filter
    cmd3 = f"source .venv/bin/activate && PYTHONPATH=. python jirax.py extract --query \"project = {test_project} AND priority = Medium\" --output-path {TEST_OUTPUT_DIR}/test3_{timestamp}.csv --no-preview"
    results.append(run_test("Query with priority filter", cmd3))
    
    # Test case 4: Extract with status filter
    cmd4 = f"source .venv/bin/activate && PYTHONPATH=. python jirax.py extract --query \"project = {test_project} AND status = 'To Do'\" --output-path {TEST_OUTPUT_DIR}/test4_{timestamp}.csv --no-preview"
    results.append(run_test("Query with status filter", cmd4))
    
    # Test case 5: Invalid project (should fail)
    cmd5 = "source .venv/bin/activate && PYTHONPATH=. python jirax.py extract --project INVALID_PROJECT --output-path /dev/null"
    results.append(run_test("Invalid project", cmd5, expected_success=False))
    
    # Test case 6: Invalid JQL (should fail)
    cmd6 = "source .venv/bin/activate && PYTHONPATH=. python jirax.py extract --query \"project = INVALID_PROJECT AND invalid_field = 'value'\" --output-path /dev/null"
    results.append(run_test("Invalid JQL query", cmd6, expected_success=False))
    
    # Test case 7: No arguments with default config
    cmd7 = f"source .venv/bin/activate && PYTHONPATH=. python jirax.py extract --output-path {TEST_OUTPUT_DIR}/test7_{timestamp}.csv --no-preview"
    results.append(run_test("No arguments (using config defaults)", cmd7))
    
    # Analyze CSV files
    console.print("\n[bold]CSV Analysis:[/bold]")
    csv_files = [
        f"{TEST_OUTPUT_DIR}/test1_{timestamp}.csv",
        f"{TEST_OUTPUT_DIR}/test2_{timestamp}.csv",
        f"{TEST_OUTPUT_DIR}/test3_{timestamp}.csv",
        f"{TEST_OUTPUT_DIR}/test4_{timestamp}.csv",
        f"{TEST_OUTPUT_DIR}/test7_{timestamp}.csv"
    ]
    
    for file_path in csv_files:
        if os.path.exists(file_path):
            stats = analyze_csv(file_path)
            console.print(f"\n[cyan]File:[/cyan] {file_path}")
            
            if "error" in stats:
                console.print(f"[red]Error analyzing file: {stats['error']}[/red]")
                continue
                
            console.print(f"[green]Row count:[/green] {stats['row_count']}")
            console.print(f"[green]Columns:[/green] {', '.join(stats['columns'])}")
    
    # Summary
    success_count = sum(1 for r in results if r.get("success", False))
    console.print(f"\n[bold]Test Summary:[/bold] {success_count}/{len(results)} tests passed")
    
    # Print failed tests
    failed = [r for r in results if not r.get("success", False)]
    if failed:
        console.print("[bold red]Failed tests:[/bold red]")
        for test in failed:
            console.print(f"- {test['name']}")

if __name__ == "__main__":
    main()
