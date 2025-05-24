#!/usr/bin/env python3
"""
Jirax - A tool for extracting Jira issues to CSV format.
"""
import os
import sys
import csv
import json
import pathlib
import toml
import time
import logging
import warnings
from typing import List, Dict, Any, Optional, Union, Tuple
from datetime import datetime

# Import list_projects functionality
from jirax.list_projects import list_projects as list_jira_projects

# Suppress urllib3 warnings about LibreSSL
warnings.filterwarnings("ignore", category=Warning, module="urllib3")

# Disable all urllib3 warnings at the source
import urllib3
urllib3.disable_warnings()

import click
import toml
from jira import JIRA
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.table import Table

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Rich console for nice output
console = Console()

# Default config file path
CONFIG_PATH = pathlib.Path(os.path.expanduser("~/.jirax/config.toml"))

# Local config file path
LOCAL_CONFIG_PATH = pathlib.Path("./config.toml")

def load_config():
    """Load configuration from TOML file."""
    config = {
        "jira": {"server": "", "token": "", "email": "", "auth_type": "basic", "login": ""},
        "extraction": {
            "default_project": "",
            "max_results": 1000,
            "output_directory": "./exports"
        },
        "display": {"preview": True, "preview_rows": 5},
        "columns": {
            "Key": "Key",
            "Summary": "Summary",
            "Issue_Type": "Issue Type",
            "Status": "Status",
            "Priority": "Priority",
            "Assignee": "Assignee",
            "Reporter": "Reporter",
            "Resolution": "Resolution",
            "Updated": "Updated",
            "Sprint": "Sprint",
            "Epic_Key": "Epic Key",
            "Epic_Name": "Epic Name",
            "Labels": "Labels",
            "Extract_Date": "Extract Date"
        }
    }
    
    # Check local config first
    if LOCAL_CONFIG_PATH.exists():
        try:
            local_config = toml.load(LOCAL_CONFIG_PATH)
            config = update_nested_dict(config, local_config)
        except Exception as e:
            console.print(f"[bold yellow]Warning: Error loading local config file: {e}[/bold yellow]")
    
    # Then check user config
    elif CONFIG_PATH.exists():
        try:
            user_config = toml.load(CONFIG_PATH)
            config = update_nested_dict(config, user_config)
        except Exception as e:
            console.print(f"[bold yellow]Warning: Error loading user config file: {e}[/bold yellow]")
    
    return config

def update_nested_dict(d, u):
    """Recursively update a nested dictionary."""
    for k, v in u.items():
        if isinstance(v, dict):
            d[k] = update_nested_dict(d.get(k, {}), v)
        else:
            d[k] = v
    return d

def get_jira_client(server: str, token: str, email: str = None, auth_type: str = "basic", login: str = None, verify_ssl: bool = True, timeout: int = 30) -> JIRA:
    """Create and return a JIRA client instance.
    
    Args:
        server: Jira server URL
        token: Personal Access Token or Bearer token
        email: Email address (required for basic auth)
        auth_type: Authentication type ("basic" or "bearer")
        login: Username for bearer token authentication (if required)
        verify_ssl: Whether to verify SSL certificates (disable for self-signed certs)
        timeout: Connection timeout in seconds
    """
    # Suppress InsecureRequestWarning when verify_ssl is False
    if not verify_ssl:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    try:
        if auth_type.lower() == "bearer":
            if login:
                console.print(f"[blue]Connecting to Jira as {login} with bearer token...[/blue]")
                # Some Jira instances require both login and token
                # Use standard Authorization header approach
                headers = {"Authorization": f"Bearer {token}"}
                return JIRA(server=server, options={"headers": headers, "verify": verify_ssl, "timeout": timeout})
            else:
                console.print(f"[blue]Connecting to Jira with bearer token...[/blue]")
                # Standard bearer token auth
                return JIRA(server=server, token_auth=token, validate=verify_ssl, timeout=timeout)
        else:  # Default to basic auth
            # Use email from config or prompt if not available
            if not email:
                email = click.prompt("Enter your Atlassian email address", type=str)
            
            console.print(f"[blue]Connecting to Jira as {email}...[/blue]")
            return JIRA(server=server, basic_auth=(email, token), validate=verify_ssl, timeout=timeout)
    except Exception as e:
        console.print(f"[bold red]Error connecting to Jira:[/bold red] {str(e)}")
        sys.exit(1)

def fetch_issues(jira: JIRA, query: str, max_results: int = 1000) -> List[Dict[str, Any]]:
    """
    Fetch issues from Jira based on the provided JQL query.
    
    Args:
        jira: JIRA client instance
        query: JQL query string
        max_results: Maximum number of results to return
        
    Returns:
        List of issue dictionaries
    """
    issues = []
    start_at = 0
    chunk_size = 50  # Reduced from 100 to improve reliability
    total = None
    
    # Create a progress bar that shows the actual progress
    with Progress(
        "[progress.description]{task.description}",
        BarColumn(),
        "[progress.percentage]{task.percentage:>3.0f}%",
        "•",
        "[bold blue]{task.completed}/{task.total}",
        "•",
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("[bold blue]Fetching Jira issues...", total=None)
        
        try:
            # First query to get total count
            initial_chunk = jira.search_issues(query, startAt=0, maxResults=1)
            if hasattr(initial_chunk, 'total'):
                total = min(max_results, initial_chunk.total)
                progress.update(task, total=total)
            
            while True:
                try:
                    console.print(f"[dim]Fetching issues {start_at} to {start_at + chunk_size}...[/dim]")
                    chunk = jira.search_issues(query, startAt=start_at, maxResults=chunk_size, 
                                             expand='changelog')
                    
                    if not chunk:
                        break
                        
                    chunk_length = len(chunk)
                    issues.extend(chunk)
                    start_at += chunk_length
                    
                    # Update progress
                    progress.update(task, completed=min(len(issues), total or len(issues)))
                    
                    if chunk_length < chunk_size or len(issues) >= max_results:
                        break
                        
                except Exception as e:
                    console.print(f"[yellow]Warning: Error fetching chunk, retrying: {str(e)}[/yellow]")
                    # Wait a bit before retrying
                    time.sleep(2)
                    continue
            
            return issues[:max_results]  # Ensure we don't exceed max_results
            
        except Exception as e:
            console.print(f"[bold red]Error fetching issues:[/bold red] {str(e)}")
            if issues:  # Return any issues we've managed to fetch so far
                console.print(f"[yellow]Returning {len(issues)} issues fetched before error occurred.[/yellow]")
                return issues
            sys.exit(1)

def extract_issue_data(issues: List, jira: JIRA, config=None) -> List[Dict[str, Any]]:
    """
    Extract relevant fields from Jira issues.
    
    Args:
        issues: List of Jira issue objects
        jira: JIRA client instance
        config: Configuration dictionary containing column definitions
        
    Returns:
        List of dictionaries containing extracted issue data
    """
    if config is None:
        config = load_config()
    
    # Get column definitions from config
    columns = config.get("columns", {})
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]Extracting issue data..."),
        transient=True,
    ) as progress:
        progress.add_task("extract", total=None)
        
        data = []
        run_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        for issue in issues:
            # Extract sprint from custom field
            sprint = None
            for field_name, field_value in issue.raw['fields'].items():
                if field_name.startswith('customfield_') and field_value and isinstance(field_value, list):
                    # Try to identify sprint field by checking if any item contains 'name=' and 'Sprint'
                    for item in field_value:
                        if isinstance(item, str) and 'name=' in item and 'Sprint' in item:
                            sprint_info = item.split(',')
                            for info in sprint_info:
                                if info.startswith('name='):
                                    sprint = info.replace('name=', '').strip()
                                    break
                            if sprint:
                                break
            
            # Extract epic link
            epic_key = None
            epic_name = None
            for field_name, field_value in issue.raw['fields'].items():
                if field_name.startswith('customfield_') and field_value:
                    if isinstance(field_value, str) and field_name.lower().endswith('epic link'):
                        epic_key = field_value
                    elif isinstance(field_value, str) and field_name.lower().endswith('epic name'):
                        epic_name = field_value
            
            # Extract labels
            labels = ", ".join(issue.fields.labels) if hasattr(issue.fields, 'labels') and issue.fields.labels else None
            
            # Basic issue data using column names from config
            issue_data = {}
            
            # Map fields to their configured column names
            field_mappings = {
                "Key": issue.key,
                "Summary": issue.fields.summary,
                "Issue_Type": getattr(issue.fields.issuetype, 'name', None) if hasattr(issue.fields, 'issuetype') and issue.fields.issuetype else None,
                "Status": getattr(issue.fields.status, 'name', None),
                "Priority": getattr(issue.fields.priority, 'name', None) if hasattr(issue.fields, 'priority') and issue.fields.priority else None,
                "Assignee": getattr(issue.fields.assignee, 'displayName', None) if hasattr(issue.fields, 'assignee') and issue.fields.assignee else None,
                "Reporter": getattr(issue.fields.reporter, 'displayName', None) if hasattr(issue.fields, 'reporter') and issue.fields.reporter else None,
                "Resolution": getattr(issue.fields.resolution, 'name', None) if hasattr(issue.fields, 'resolution') and issue.fields.resolution else None,
                "Updated": issue.fields.updated if hasattr(issue.fields, 'updated') else None,
                "Sprint": sprint,
                "Epic_Key": epic_key,
                "Epic_Name": epic_name,
                "Labels": labels,
                "Extract_Date": run_date
            }
            
            # Create the issue data dictionary using configured column names
            for field_key, field_value in field_mappings.items():
                column_name = columns.get(field_key, field_key)
                issue_data[column_name] = field_value
            
            data.append(issue_data)
        
        return data

def export_to_csv(data: List[Dict[str, Any]], output_path: str) -> None:
    """Export data to CSV file."""
    if not data:
        console.print("[bold yellow]No data to export.[/bold yellow]")
        return
        
    # Get all unique field names from the data
    fieldnames = set()
    for item in data:
        fieldnames.update(item.keys())
    
    # Convert to list and ensure Extract_Date is the last column
    fieldnames = sorted(list(fieldnames))
    if 'Extract_Date' in fieldnames:
        fieldnames.remove('Extract_Date')
        fieldnames.append('Extract_Date')
    
    with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, quoting=csv.QUOTE_NONNUMERIC)
        writer.writeheader()
        writer.writerows(data)
    
    console.print(f"[bold green]Data exported to CSV:[/bold green] {output_path}")

def display_preview(data: List[Dict[str, Any]], num_rows: int = 5) -> None:
    """Display a preview of the data in a rich table."""
    if not data:
        console.print("[bold yellow]No data to display.[/bold yellow]")
        return
    
    # Create table with line separators for better readability
    table = Table(show_header=True, header_style="bold magenta", show_lines=True)
    
    # Get all field names
    field_names = set()
    for item in data:
        field_names.update(item.keys())
    field_names = sorted(list(field_names))
    
    # Add columns
    for column in field_names:
        table.add_column(column)
    
    # Add rows (limited to num_rows)
    for i, row in enumerate(data):
        if i >= num_rows:
            break
        # Fill in values for each column, using empty string for missing values
        values = [str(row.get(field, "")) if row.get(field) is not None else "" for field in field_names]
        table.add_row(*values)
    
    console.print("\n[bold]Data Preview:[/bold]")
    console.print(table)
    console.print(f"\nTotal records: {len(data)}")

@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def cli():
    """Jirax - Extract Jira issues to CSV format.

    Examples:
        # Configure Jirax
        jirax configure

        # Extract issues from a project
        jirax extract --project PROJ

        # Extract using custom JQL query
        jirax extract --query "project = PROJ AND type = Story"

        # Extract to a specific file
        jirax extract --project PROJ --output-path ./exports/issues.csv
    """
    pass

@cli.command()
@click.option('-s', '--server', help='Jira server URL')
@click.option('-t', '--token', help='Jira Personal Access Token or Bearer token')
@click.option('-e', '--email', help='Atlassian email address for authentication (basic auth)')
@click.option('-a', '--auth-type', help='Authentication type: "basic" or "bearer"')
@click.option('-l', '--login', help='Username for bearer token authentication (if required)')
@click.option('-p', '--project', help='Jira project key')
@click.option('-q', '--query', help='Custom JQL query (overrides project if provided)')
@click.option('-m', '--max-results', type=int, help='Maximum number of results to return')
@click.option('-o', '--output-path', help='Output file path (with .csv extension)', default=None)
@click.option('--preview/--no-preview', default=None, help='Preview results before export')
@click.option('--verify-ssl/--no-verify-ssl', default=None, help='Verify SSL certificates (disable for self-signed certificates)')
@click.option('--timeout', type=int, default=None, help='Connection timeout in seconds')
@click.option('-c', '--config', help='Path to config file')
def extract(server, token, project, query, max_results, output_path, preview, verify_ssl, timeout, config, email=None, auth_type=None, login=None):
    """Extract Jira issues based on project or custom query.

    Examples:
        # Extract issues from a project
        jirax extract --project PROJ

        # Extract using custom JQL query
        jirax extract --query "project = PROJ AND type = Story"

        # Extract with issue type filter
        jirax extract --query "project = PROJ AND issuetype = Epic"

        # Extract to a specific file
        jirax extract --project PROJ --output-path ./exports/issues.csv

        # Extract recent issues
        jirax extract --query "project = PROJ AND updated >= -7d"
    """
    # Load config from file
    config_path = pathlib.Path(config) if config else None
    if config_path and config_path.exists():
        try:
            config_data = toml.load(config_path)
        except Exception as e:
            console.print(f"[bold red]Error loading config file:[/bold red] {str(e)}")
            sys.exit(1)
    else:
        config_data = load_config()
    
    # Use config values as defaults if not provided in command line
    server = server or config_data.get('jira', {}).get('server', '')
    token = token or config_data.get('jira', {}).get('token', '')
    email = email or config_data.get('jira', {}).get('email', '')
    auth_type = auth_type or config_data.get('jira', {}).get('auth_type', 'basic')
    login = login or config_data.get('jira', {}).get('login', '')
    max_results = max_results or config_data.get('extraction', {}).get('max_results', 1000)
    preview = preview if preview is not None else config_data.get('display', {}).get('preview', True)
    verify_ssl = verify_ssl if verify_ssl is not None else config_data.get('jira', {}).get('verify_ssl', True)
    timeout = timeout or config_data.get('jira', {}).get('timeout', 30)
    
    # Use default project from config if not provided in command line
    if not project and not query:
        project = config_data.get('extraction', {}).get('default_project', '')
    
    # Handle output path with configured directory
    if not output_path:
        output_dir = config_data.get('extraction', {}).get('output_directory', './exports')
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        # Generate filename with timestamp
        filename = f"jira_extract_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        output_path = os.path.join(output_dir, filename)
    
    # Validate inputs
    if not server:
        console.print("[bold red]Error:[/bold red] Jira server URL is required. Provide via --server or config file.")
        sys.exit(1)
    
    if not token:
        console.print("[bold red]Error:[/bold red] Jira token is required. Provide via --token or config file.")
        sys.exit(1)
    
    # Create Jira client
    jira = get_jira_client(server, token, email, auth_type, login, verify_ssl, timeout)
    
    # Prepare JQL query
    if query:
        jql_query = query
    else:
        if not project:
            console.print("[bold red]Error:[/bold red] Either project or query must be provided. Set a default project in your config file or specify with --project.")
            sys.exit(1)
        jql_query = f"project = {project} ORDER BY updated DESC"
    
    console.print(f"[bold]Using JQL query:[/bold] {jql_query}")
    
    # Fetch issues
    issues = fetch_issues(jira, jql_query, max_results)
    
    if not issues:
        console.print("[bold yellow]No issues found with the given query.[/bold yellow]")
        sys.exit(0)
    
    console.print(f"[bold green]Found {len(issues)} issues.[/bold green]")
    
    # Extract data
    data = extract_issue_data(issues, jira, config_data)
    
    # Preview data if requested
    if preview:
        preview_rows = config_data.get('display', {}).get('preview_rows', 5)
        display_preview(data, preview_rows)
        
        if not click.confirm("Continue with export?", default=True):
            sys.exit(0)
    
    # Export data to CSV
    export_to_csv(data, output_path)
    
    console.print("[bold green]Export completed successfully![/bold green]")

@cli.command()
@click.option('--global/--local', '-g/-l', default=False, help='Save to global (~/.jirax) or local config')
def configure(global_):
    """Configure Jira connection settings."""
    console.print("[bold]Configure Jira Connection[/bold]")
    
    # Load existing config if available
    config_path = CONFIG_PATH if global_ else LOCAL_CONFIG_PATH
    
    if config_path.exists():
        try:
            config = toml.load(config_path)
        except Exception:
            config = {}
    else:
        config = {}
    
    # Ensure the structure exists
    if 'jira' not in config:
        config['jira'] = {}
    if 'extraction' not in config:
        config['extraction'] = {}
    if 'display' not in config:
        config['display'] = {}
    if 'columns' not in config:
        config['columns'] = {}
    
    # Get Jira connection details
    server = click.prompt("Enter Jira server URL", 
                         default=config.get('jira', {}).get('server', ''),
                         type=str)
    
    auth_type = click.prompt("Authentication type",
                            default=config.get('jira', {}).get('auth_type', 'basic'),
                            type=click.Choice(['basic', 'bearer'], case_sensitive=False))
    
    token = click.prompt("Enter Jira " + ("Personal Access Token" if auth_type.lower() == "basic" else "Bearer Token"), 
                        default=config.get('jira', {}).get('token', ''),
                        hide_input=True,
                        type=str)
    
    email = ""
    login = ""
    
    if auth_type.lower() == "basic":
        email = click.prompt("Enter your Atlassian email address", 
                            default=config.get('jira', {}).get('email', ''),
                            type=str)
    else:  # Bearer token authentication
        login = click.prompt("Enter your Jira username (if required for bearer auth, otherwise leave empty)",
                           default=config.get('jira', {}).get('login', ''),
                           type=str,
                           show_default=True)
    
    # Get additional settings
    default_project = click.prompt("Default project (optional)", 
                                  default=config.get('extraction', {}).get('default_project', ''),
                                  type=str, show_default=True)
    
    max_results = click.prompt("Default max results", 
                             default=config.get('extraction', {}).get('max_results', 1000),
                             type=int, show_default=True)
    
    # Update config
    config['jira']['server'] = server
    config['jira']['token'] = token
    config['jira']['auth_type'] = auth_type.lower()
    config['jira']['email'] = email
    config['jira']['login'] = login
    config['extraction']['default_project'] = default_project
    config['extraction']['max_results'] = max_results
    
    # Ensure directory exists
    os.makedirs(config_path.parent, exist_ok=True)
    
    # Write config file
    with open(config_path, 'w') as f:
        toml.dump(config, f)
    
    # Secure file permissions
    os.chmod(config_path, 0o600)
    
    location = "global" if global_ else "local"
    console.print(f"[bold green]Configuration saved to {location} config file: {config_path}[/bold green]")

@cli.command('list-projects')
@click.option('-s', '--server', help='Jira server URL')
@click.option('-t', '--token', help='Jira Personal Access Token or Bearer token')
@click.option('-e', '--email', help='Atlassian email address for authentication (basic auth)')
@click.option('-a', '--auth-type', help='Authentication type: "basic" or "bearer"')
@click.option('-l', '--login', help='Username for bearer token authentication (if required)')
@click.option('--verify-ssl/--no-verify-ssl', default=None, help='Verify SSL certificates (disable for self-signed certificates)')
@click.option('--timeout', type=int, default=None, help='Connection timeout in seconds')
@click.option('-c', '--config', help='Path to config file')
def list_projects_command(server, token, email, config, auth_type=None, login=None, verify_ssl=None, timeout=None):
    """List all available projects in your Jira instance.
    
    Examples:
        # List all projects using config file settings
        jirax list-projects
        
        # List projects with SSL verification disabled (for self-signed certificates)
        jirax list-projects --no-verify-ssl
    """
    from .list_projects import list_projects
    list_projects(server, token, email, config, auth_type, login, verify_ssl, timeout)

if __name__ == "__main__":
    cli()
