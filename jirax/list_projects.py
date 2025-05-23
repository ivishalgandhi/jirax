#!/usr/bin/env python3
"""
Module to list all available projects in your Jira instance.
"""
import sys
import toml
from jira import JIRA
from rich.console import Console
from rich.table import Table

console = Console()

def get_jira_client(server, token, email):
    """Create and return a JIRA client instance."""
    try:
        console.print(f"[blue]Connecting to Jira as {email}...[/blue]")
        return JIRA(server=server, basic_auth=(email, token))
    except Exception as e:
        console.print(f"[bold red]Error connecting to Jira:[/bold red] {str(e)}")
        sys.exit(1)

def list_projects(server=None, token=None, email=None, config_path=None):
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
        
        if not server or not token:
            console.print("[bold red]Error:[/bold red] Missing configuration. Please ensure your config file has server and token configured.")
            sys.exit(1)
            
    except Exception as e:
        console.print(f"[bold red]Error loading config:[/bold red] {str(e)}")
        sys.exit(1)
    
    # Connect to Jira
    jira = get_jira_client(server, token, email)
    
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
