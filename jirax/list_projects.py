#!/usr/bin/env python3
"""
Module to list all available projects in your Jira instance.
"""
import sys
import warnings
import toml

# Suppress urllib3 warnings about LibreSSL
warnings.filterwarnings("ignore", category=Warning, module="urllib3")

# Disable all urllib3 warnings at the source
import urllib3
urllib3.disable_warnings()

from jira import JIRA
from rich.console import Console
from rich.table import Table

console = Console()

def get_jira_client(server, token, email=None, auth_type="basic", login=None):
    """Create and return a JIRA client instance."""
    try:
        if auth_type.lower() == "bearer":
            if login:
                console.print(f"[blue]Connecting to Jira as {login} with bearer token...[/blue]")
                # Some Jira instances require both login and token
                # Use standard Authorization header approach
                headers = {"Authorization": f"Bearer {token}"}
                return JIRA(server=server, options={"headers": headers})
            else:
                console.print(f"[blue]Connecting to Jira with bearer token...[/blue]")
                # Standard bearer token auth
                return JIRA(server=server, token_auth=token)
        else:  # Default to basic auth
            if not email:
                console.print(f"[bold red]Error:[/bold red] Email is required for basic authentication.")
                sys.exit(1)
                
            console.print(f"[blue]Connecting to Jira as {email}...[/blue]")
            return JIRA(server=server, basic_auth=(email, token))
    except Exception as e:
        console.print(f"[bold red]Error connecting to Jira:[/bold red] {str(e)}")
        sys.exit(1)

def list_projects(server=None, token=None, email=None, config_path=None, auth_type=None, login=None, verify_ssl=None, timeout=None):
    """List all available projects in Jira."""
    # Load config
    try:
        if config_path:
            config = toml.load(config_path)
        else:
            try:
                config = toml.load("config.toml")
            except:
                # Try loading from user config
                config = toml.load(os.path.expanduser("~/.jirax/config.toml"))
        
        server = server or config.get('jira', {}).get('server', '')
        token = token or config.get('jira', {}).get('token', '')
        email = email or config.get('jira', {}).get('email', '')
        auth_type = auth_type or config.get('jira', {}).get('auth_type', 'basic')
        login = login or config.get('jira', {}).get('login', '')
        verify_ssl = verify_ssl if verify_ssl is not None else config.get('jira', {}).get('verify_ssl', True)
        timeout = timeout or config.get('jira', {}).get('timeout', 30)
        
        if not server or not token:
            console.print("[bold red]Error:[/bold red] Missing configuration. Please ensure your config file has server and token configured.")
            sys.exit(1)
            
    except Exception as e:
        console.print(f"[bold red]Error loading config:[/bold red] {str(e)}")
        sys.exit(1)
    
    # Connect to Jira
    jira = get_jira_client(server, token, email, auth_type, login, verify_ssl, timeout)
    
    # Get all projects
    try:
        projects = jira.projects()
        
        if not projects:
            console.print("[yellow]No projects found in your Jira instance.[/yellow]")
            sys.exit(0)
        
        # Display projects in a table
        table = Table(title="Available Jira Projects", show_lines=True)
        table.add_column("Key", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Lead", style="magenta")
        
        for project in projects:
            table.add_row(
                project.key,
                project.name,
                getattr(project, 'lead', {}).get('displayName', 'Unknown') if hasattr(project, 'lead') else 'Unknown'
            )
        
        console.print(table)
        console.print(f"\n[bold green]Found {len(projects)} projects.[/bold green]")
        
    except Exception as e:
        console.print(f"[bold red]Error fetching projects:[/bold red] {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    list_projects()
