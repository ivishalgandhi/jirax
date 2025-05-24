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
from collections import OrderedDict

# Import list_projects functionality
from jirax.list_projects import list_projects as list_jira_projects

# Suppress urllib3 warnings about LibreSSL
warnings.filterwarnings("ignore", category=Warning, module="urllib3")

# Disable all urllib3 warnings at the source
import urllib3
urllib3.disable_warnings()

import click
from jira import JIRA
from jira.resources import Issue
from rich.console import Console
from rich.table import Table
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

def _get_nested_attr(obj: Any, attr_path: str, default: Any = None) -> Any:
    """
    Safely retrieve a nested attribute from an object using a dot-separated path.
    Example: _get_nested_attr(issue, "fields.reporter.displayName")
    """
    attrs = attr_path.split('.')
    current_obj = obj
    for attr in attrs:
        if isinstance(current_obj, dict): # For raw dicts from API sometimes
            current_obj = current_obj.get(attr)
        elif hasattr(current_obj, 'raw') and isinstance(current_obj.raw, dict) and attr in current_obj.raw:
            # jira-python often stores raw data in .raw
            current_obj = current_obj.raw[attr]
        elif hasattr(current_obj, attr): # For Issue objects and their fields
            current_obj = getattr(current_obj, attr)
        else: # Attribute not found
            return default
        
        if current_obj is None: # If at any point we get None, return default
            return default
    return current_obj

def _get_computed_value(issue: Issue, source_key: str, config: Dict, run_date_str: str, jira_client: JIRA) -> Any:
    """
    Compute values for special fields that require more complex logic.
    'source_key' is the part after "_computed.", e.g., "sprint", "epicname".
    """
    field_name = source_key # source_key is already the part after _computed.

    jira_opts = config.get("jira_options", {})

    if field_name == "sprint":
        sprint_custom_field_id = jira_opts.get("sprint_custom_field", "customfield_10020")
        sprints_data = _get_nested_attr(issue, f"fields.{sprint_custom_field_id}", [])
        if sprints_data and isinstance(sprints_data, list):
            sprint_names = []
            for sprint_entry_text in sprints_data:
                # Sprint field often contains strings like:
                # "com.atlassian.greenhopper.service.sprint.Sprint@...[id=123,rapidViewId=45,state=CLOSED,name=My Sprint Name,startDate=...,endDate=...]"
                if isinstance(sprint_entry_text, str):
                    name_match = next((part for part in sprint_entry_text.split(',') if 'name=' in part), None)
                    if name_match:
                        sprint_names.append(name_match.split('name=')[1].split(',')[0]) # Extract name
                # Sometimes it might be an object if fetched differently (less common with *all fields)
                elif hasattr(sprint_entry_text, 'name'):
                     sprint_names.append(sprint_entry_text.name)
            return ", ".join(sprint_names) if sprint_names else None
        return None
    elif field_name == "epickey":
        epic_link_field_id = jira_opts.get("epic_link_custom_field", "customfield_10014")
        return _get_nested_attr(issue, f"fields.{epic_link_field_id}")
    elif field_name == "epicname":
        epic_link_field_id = jira_opts.get("epic_link_custom_field", "customfield_10014")
        epic_name_field_id = jira_opts.get("epic_name_custom_field", "customfield_10010") # Often the Epic's summary
        epic_key = _get_nested_attr(issue, f"fields.{epic_link_field_id}")
        if epic_key:
            try:
                # Fetch the epic issue itself to get its name/summary
                epic_issue = jira_client.issue(epic_key, fields=epic_name_field_id) # Only fetch the name field
                return _get_nested_attr(epic_issue, f"fields.{epic_name_field_id}")
            except Exception as e:
                logger.warning(f"Could not retrieve epic name for epic key {epic_key}: {e}")
                return epic_key # Fallback to epic key if name fetch fails
        return None
    elif field_name == "labels":
        return ", ".join(_get_nested_attr(issue, "fields.labels", []))
    elif field_name == "components":
        return ", ".join([c.name for c in _get_nested_attr(issue, "fields.components", []) if hasattr(c, 'name')])
    elif field_name == "fixversions":
        return ", ".join([v.name for v in _get_nested_attr(issue, "fields.fixVersions", []) if hasattr(v, 'name')])
    elif field_name == "affectsversions":
        return ", ".join([v.name for v in _get_nested_attr(issue, "fields.versions", []) if hasattr(v, 'name')]) # Affects versions
    elif field_name == "subtasks":
        return ", ".join([s.key for s in _get_nested_attr(issue, "fields.subtasks", []) if hasattr(s, 'key')])
    elif field_name == "watchers":
        return _get_nested_attr(issue, "fields.watches.watchCount")
    elif field_name == "votes":
        return _get_nested_attr(issue, "fields.votes.votes")
    elif field_name == "attachments":
        return ", ".join([a.filename for a in _get_nested_attr(issue, "fields.attachment", []) if hasattr(a, 'filename')])
    elif field_name == "commentscount":
        comments_data = _get_nested_attr(issue, "fields.comment")
        return comments_data.total if hasattr(comments_data, 'total') else (len(comments_data.comments) if hasattr(comments_data, 'comments') else 0)
    elif field_name == "extractdate":
        return run_date_str
    # Placeholder for user-defined computed fields, e.g., from config: "_computed.custom_multiselect_12348"
    # User would need to add logic here if they define such a source.
    elif field_name.startswith("custom_multiselect_"): # Example custom computed handler
        custom_field_id = field_name.replace("custom_multiselect_", "")
        values = _get_nested_attr(issue, f"fields.{custom_field_id}", [])
        return ", ".join([v.value for v in values if hasattr(v, 'value')])

    logger.warning(f"Unknown computed field source key: _computed.{field_name}")
    return None

def load_config():
    """Load configuration from TOML file, prioritizing local, then user, then defaults.
    The 'fields_setup' section from the config file, if present, entirely replaces the default.
    """
    default_config = {
        "jira": {"server": "", "token": "", "email": "", "auth_type": "basic", "login": "", "verify_ssl": True, "timeout": 30},
        "extraction": {"default_project": "", "max_results": 1000, "output_directory": "./exports"},
        "display": {"preview": True, "preview_rows": 5},
        "jira_options": {
            "sprint_custom_field": "customfield_10020",
            "epic_link_custom_field": "customfield_10014",
            "epic_name_custom_field": "customfield_10010"
        },
        "fields_setup": OrderedDict([
            ("IssueKey", {"display_name": "Key", "source": "key"}),
            ("IssueSummary", {"display_name": "Summary", "source": "fields.summary"}),
            ("IssueType", {"display_name": "Issue Type", "source": "fields.issuetype.name"}),
            ("Status", {"display_name": "Status", "source": "fields.status.name"}),
            ("Priority", {"display_name": "Priority", "source": "fields.priority.name"}),
            ("Assignee", {"display_name": "Assignee", "source": "fields.assignee.displayName"}),
            ("Reporter", {"display_name": "Reporter", "source": "fields.reporter.displayName"}),
            ("CreatedDate", {"display_name": "Created", "source": "fields.created"}),
            ("UpdatedDate", {"display_name": "Updated", "source": "fields.updated"}),
            ("Labels", {"display_name": "Labels", "source": "_computed.labels"}),
            ("Sprint", {"display_name": "Sprint", "source": "_computed.sprint"}),
            ("ExtractDate", {"display_name": "Extract Date", "source": "_computed.extractdate"})
        ])
    }

    final_config = {
        "jira": default_config["jira"].copy(),
        "extraction": default_config["extraction"].copy(),
        "display": default_config["display"].copy(),
        "jira_options": default_config["jira_options"].copy(),
        "fields_setup": default_config["fields_setup"].copy() # This will be fully replaced if 'fields_setup' is in user config.
    }

    config_file_to_load = None
    if LOCAL_CONFIG_PATH.exists():
        config_file_to_load = LOCAL_CONFIG_PATH
        logger.info(f"Loading local configuration from: {LOCAL_CONFIG_PATH}")
    elif CONFIG_PATH.exists():
        config_file_to_load = CONFIG_PATH
        logger.info(f"Loading user configuration from: {CONFIG_PATH}")
    else:
        logger.info("No local or user config file found. Using default configuration.")

    if config_file_to_load:
        try:
            loaded_from_file = toml.load(config_file_to_load)
            logger.info(f"Successfully parsed configuration from: {config_file_to_load}")

            for key, value_from_file in loaded_from_file.items():
                if key == "fields_setup" and isinstance(value_from_file, dict):
                    final_config["fields_setup"] = OrderedDict(value_from_file.items()) # Preserve order from file
                    logger.info(f"Overriding 'fields_setup' with content from {config_file_to_load}")
                elif key in final_config and isinstance(final_config[key], dict) and isinstance(value_from_file, dict):
                    update_nested_dict(final_config[key], value_from_file) # Merge other dict sections
                else:
                    final_config[key] = value_from_file # Assign new or non-dict top-level items
        except Exception as e:
            console.print(f"[bold yellow]Warning: Error loading config file '{config_file_to_load}': {e}. Using defaults or previously loaded values.[/bold yellow]")
            logger.error(f"Config loading error for {config_file_to_load}: {e}", exc_info=True)


    return final_config

def update_nested_dict(base_dict, updates_dict):
    for key, value in updates_dict.items():
        if isinstance(value, dict) and isinstance(base_dict.get(key), dict):
            update_nested_dict(base_dict[key], value)
        else:
            base_dict[key] = value
    return base_dict

def get_jira_client(server: str, token: str, email: str = None, auth_type: str = "basic", login: str = None, verify_ssl: bool = True, timeout: int = 30) -> Optional[JIRA]:
    if not verify_ssl:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    try:
        options = {'server': server, 'verify': verify_ssl, 'timeout': timeout}
        if auth_type.lower() == "bearer":
            console.print(f"[blue]Connecting to Jira{' as ' + login if login else ''} with bearer token...[/blue]")
            return JIRA(options=options, token_auth=token)
        elif auth_type.lower() == "basic":
            console.print(f"[blue]Connecting to Jira as {email} with basic auth (PAT)...[/blue]")
            return JIRA(options=options, basic_auth=(email, token))
        else:
            console.print(f"[bold red]Unsupported authentication type: {auth_type}[/bold red]")
            return None
    except Exception as e:
        console.print(f"[bold red]Failed to connect to Jira: {e}[/bold red]")
        logger.error(f"Jira connection failed: {e}", exc_info=True)
        return None

def fetch_issues(jira: JIRA, query: str, max_results: int = 1000) -> List[Issue]:
    issues_list = []
    block_size = 50 # Recommended block size for Jira Cloud REST API
    block_num = 0
    
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), BarColumn(), TextColumn("[progress.percentage]{task.percentage:>3.0f}%"), TimeElapsedColumn(), console=console, transient=True) as progress:
        task_description = "Fetching Jira issues..."
        try:
            # Fields to fetch: "*navigable" fetches all fields viewable on the issue navigator.
            # Alternatively, could try to dynamically build a field list from config['fields_setup'] sources,
            # but "*navigable" or "*all" is simpler for now and ensures data for _computed fields.
            # Using specific fields can be much faster if known. For now, fetch broadly.
            initial_search = jira.search_issues(query, startAt=0, maxResults=0, fields="key", json_result=True)
            total_issues = initial_search.get('total', 0)

            if total_issues == 0:
                console.print("No issues found for the given JQL query.")
                return []
            
            effective_max_results = min(total_issues, max_results)
            if total_issues > max_results:
                console.print(f"[yellow]Warning: Query matches {total_issues} issues, but will fetch a maximum of {effective_max_results}.[/yellow]")
            
            task = progress.add_task(task_description, total=effective_max_results)
        except Exception as e:
            logger.error(f"Could not get total issue count: {e}. Progress bar may be inaccurate.", exc_info=True)
            task = progress.add_task(task_description, total=None) # Indeterminate

        while True:
            start_idx = block_num * block_size
            if start_idx >= effective_max_results and task.total is not None : # Check against effective_max_results
                 break
            if len(issues_list) >= max_results : # Overall safety break
                 break


            current_block_fetch_size = min(block_size, max_results - len(issues_list))
            if current_block_fetch_size <= 0:
                break
            
            progress.update(task, description=f"Fetching issues {start_idx} to {start_idx + current_block_fetch_size -1}...")
            try:
                # Fetch all fields to ensure computed fields and user-defined sources have data
                chunk = jira.search_issues(query, startAt=start_idx, maxResults=current_block_fetch_size, fields="*all")
            except Exception as e:
                console.print(f"[bold red]Error fetching issues block: {e}[/bold red]")
                logger.error(f"Issue fetching block error: {e}", exc_info=True)
                break

            if not chunk: break
            issues_list.extend(chunk)
            progress.update(task, advance=len(chunk))
            block_num += 1
            if len(chunk) < current_block_fetch_size: break # Last page

    console.print(f"Fetched {len(issues_list)} issues.")
    return issues_list[:max_results] # Ensure final list respects max_results

def extract_issue_data(issues: List[Issue], jira: JIRA, config: Dict) -> List[OrderedDict[str, Any]]:
    extracted_data: List[OrderedDict[str, Any]] = []
    run_date_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fields_setup = config.get("fields_setup", OrderedDict())

    if not fields_setup:
        console.print("[yellow]Warning: 'fields_setup' is empty in configuration. Extracted data will be empty.[/yellow]")
        return []

    for issue in issues:
        row_data = OrderedDict()
        for internal_id, field_props in fields_setup.items():
            source_path = field_props.get("source")
            value = None
            if not source_path:
                logger.warning(f"No 'source' defined for field '{internal_id}' in 'fields_setup'. It will be empty.")
            elif source_path.startswith("_computed."):
                computed_key = source_path.split("_computed.", 1)[1]
                value = _get_computed_value(issue, computed_key, config, run_date_str, jira)
            else:
                value = _get_nested_attr(issue, source_path)
            
            if isinstance(value, datetime): # Ensure datetimes are ISO strings
                value = value.isoformat()
            elif isinstance(value, list) or isinstance(value, tuple): # Naive join for lists/tuples if not handled by _computed
                try:
                    value = ", ".join(map(str,value))
                except TypeError: # If list contains non-stringables without a specific _computed handler
                    logger.warning(f"Could not automatically join list/tuple for field '{internal_id}' source '{source_path}'. Value: {value}")
                    value = str(value) # Fallback to string representation
            
            row_data[internal_id] = value
        extracted_data.append(row_data)
    return extracted_data

def reorder_data_for_output(data: List[Dict[str, Any]], config: Dict) -> List[OrderedDict[str, Any]]:
    """Ensures data dictionaries are OrderedDicts with keys matching 'fields_setup' order."""
    if not data: return []
    fields_setup = config.get("fields_setup", OrderedDict())
    ordered_internal_ids = list(fields_setup.keys())
    
    reordered_data_list = []
    for raw_row_dict in data:
        ordered_row = OrderedDict()
        for internal_id in ordered_internal_ids:
            ordered_row[internal_id] = raw_row_dict.get(internal_id) # Value should exist from extract_issue_data
        reordered_data_list.append(ordered_row)
    return reordered_data_list

def export_to_csv(data: List[OrderedDict[str, Any]], output_path: str, config: Dict) -> None:
    if not data:
        console.print("[bold yellow]No data to export.[/bold yellow]")
        return
    
    fields_setup = config.get("fields_setup", OrderedDict())
    if not fields_setup:
        console.print("[bold red]Error: 'fields_setup' is not defined in configuration for CSV export.[/bold red]")
        return

    csv_header_names = [props.get("display_name", internal_id) for internal_id, props in fields_setup.items()]
    internal_ids_ordered = list(fields_setup.keys())

    pathlib.Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile, quoting=csv.QUOTE_NONNUMERIC)
        writer.writerow(csv_header_names)
        for ordered_row_dict in data:
            row_values = [ordered_row_dict.get(internal_id) for internal_id in internal_ids_ordered]
            writer.writerow(row_values)
    console.print(f"[bold green]Data exported to CSV:[/bold green] {output_path}")

def display_preview(data: List[OrderedDict[str, Any]], num_rows: int, config: Dict) -> None:
    if not data:
        console.print("[bold yellow]No data to display.[/bold yellow]")
        return
        
    fields_setup = config.get("fields_setup", OrderedDict())
    if not fields_setup:
        console.print("[bold red]Error: 'fields_setup' is not defined in configuration for preview.[/bold red]")
        return

    display_header_names = [props.get("display_name", internal_id) for internal_id, props in fields_setup.items()]
    internal_ids_ordered = list(fields_setup.keys())
    
    table = Table(show_header=True, header_style="bold magenta", show_lines=True)
    for header_name in display_header_names: table.add_column(header_name)
    
    for row_dict in data[:num_rows]:
        row_values_for_table = [str(row_dict.get(internal_id, "")) for internal_id in internal_ids_ordered]
        table.add_row(*row_values_for_table)
    
    console.print("\n[bold]Data Preview:[/bold]")
    console.print(table)
    console.print(f"\nTotal records: {len(data)}")

def discover_jira_fields(jira_client: JIRA, console: Console):
    """Fetches and displays all available fields from the Jira instance."""
    try:
        console.print("Discovering fields from Jira... This may take a moment.")
        fields_data = jira_client.fields()
    except Exception as e:
        console.print(f"[bold red]Error fetching fields from Jira: {e}[/bold red]")
        console.print("Please check your Jira connection, credentials, and permissions.")
        return

    if not fields_data:
        console.print("[yellow]No fields found or an error occurred.[/yellow]")
        return

    table = Table(title="Discovered Jira Fields", show_lines=True, highlight=True)
    table.add_column("ID", style="dim", overflow="fold", min_width=15)
    table.add_column("Name", style="bold cyan", overflow="fold", min_width=20)
    table.add_column("Custom?", style="magenta", min_width=7)
    table.add_column("Schema Type", style="green", overflow="fold", min_width=15)
    table.add_column("Schema Custom Type", style="blue", overflow="fold", min_width=20)

    # Sort fields: standard fields first, then custom fields, then by name.
    fields_data.sort(key=lambda x: (x.get('custom', True), x.get('name', '').lower()))

    for field in fields_data:
        field_id = field.get('id', 'N/A')
        name = field.get('name', 'N/A')
        is_custom = "Yes" if field.get('custom', False) else "No"
        
        schema = field.get('schema', {})
        schema_type = schema.get('type', '')
        schema_custom = schema.get('custom', '') # Default to empty string if not present

        table.add_row(field_id, name, is_custom, schema_type, schema_custom)

    console.print(table)
    console.print("\n[bold]How to use this information:[/bold]")
    console.print("1. Identify the fields you need (e.g., 'Sprint', 'Epic Link', 'Epic Name', 'Story Points').")
    console.print("2. Note their 'ID' (e.g., 'customfield_10020').")
    console.print("3. Update your `config.toml` file:")
    console.print("   - For `[jira_options]`, use the ID directly:")
    console.print("     Example: `sprint_custom_field = \"customfield_XXXXX\"`")
    console.print("   - For `[fields_setup]`, the `source` can be:")
    console.print("     - `fields.ID` (e.g., `fields.customfield_10020`)")
    console.print("     - `fields.Name` for standard fields (e.g., `fields.summary`)")
    console.print("     - `_computed.fieldname` for fields requiring special handling (e.g., `_computed.sprint`)")
    console.print("\nFor `_computed.sprint`, `_computed.epic_name`, etc., `jirax` uses the IDs you set in `[jira_options]` (like `sprint_custom_field`).")

@click.group(context_settings=dict(help_option_names=['-h', '--help']))
def cli():
    """Jirax - Extract Jira issues to CSV format based on flexible TOML configuration."""
    pass

@cli.command('extract')
@click.option('-s', '--server', help='Jira server URL (overrides config)')
@click.option('-t', '--token', help='Jira PAT or Bearer token (overrides config)')
@click.option('-e', '--email', help='Atlassian email for basic auth (overrides config)')
@click.option('-a', '--auth-type', help='Auth type: "basic" or "bearer" (overrides config)')
@click.option('-l', '--login', help='Jira username for bearer auth (overrides config)')
@click.option('-p', '--project', help='Jira project key (e.g., PROJ)')
@click.option('-q', '--query', help='Custom JQL query (overrides project option)')
@click.option('-m', '--max-results', type=int, help='Max issues to extract (overrides config)')
@click.option('-o', '--output-path', help='Output CSV file path')
@click.option('--preview/--no-preview', 'user_preview_choice', default=None, help='Show preview (overrides config)')
@click.option('--verify-ssl/--no-verify-ssl', 'user_verify_ssl', default=None, help='Verify SSL (overrides config)')
@click.option('--timeout', type=int, help='Connection timeout seconds (overrides config)')
@click.option('-c', '--config-path', 'config_path_override', type=click.Path(exists=True, dir_okay=False, resolve_path=True), help='Path to a custom config.toml file')
def extract(server, token, project, query, max_results, output_path, user_preview_choice, user_verify_ssl, timeout, config_path_override, email=None, auth_type=None, login=None):
    """Extract Jira issues to CSV using settings from config or CLI overrides."""
    global CONFIG_PATH, LOCAL_CONFIG_PATH # Allow modification by config_path_override
    if config_path_override:
        LOCAL_CONFIG_PATH = pathlib.Path(config_path_override)
        CONFIG_PATH = pathlib.Path() # Effectively disable default user config path
        logger.info(f"Using custom configuration file: {LOCAL_CONFIG_PATH}")

    config = load_config()
    
    # Override config with CLI options
    cfg_jira = config['jira']
    cfg_ext = config['extraction']
    cfg_disp = config['display']

    j_server = server or cfg_jira.get('server')
    j_token = token or cfg_jira.get('token')
    j_email = email or cfg_jira.get('email')
    j_auth_type = auth_type or cfg_jira.get('auth_type', 'basic')
    j_login = login or cfg_jira.get('login')
    j_verify_ssl = cfg_jira.get('verify_ssl', True) if user_verify_ssl is None else user_verify_ssl
    j_timeout = timeout or cfg_jira.get('timeout', 30)
    
    jql_project_key = project or cfg_ext.get('default_project')
    jql_query_str = query
    max_res_count = max_results or cfg_ext.get('max_results', 1000)
    show_preview_flag = cfg_disp.get('preview', True) if user_preview_choice is None else user_preview_choice

    if not j_server or not j_token:
        console.print("[bold red]Jira server and token must be configured or provided.[/bold red] Try 'jirax configure'.")
        return
    if j_auth_type.lower() == "basic" and not j_email:
        console.print("[bold red]Email must be provided for basic authentication.[/bold red] Try 'jirax configure'.")
        return

    jira = get_jira_client(j_server, j_token, j_email, j_auth_type, j_login, j_verify_ssl, j_timeout)
    if not jira: return

    if not jql_query_str:
        if not jql_project_key:
            console.print("[bold red]Either --project or --query must be specified.[/bold red]")
            return
        jql_query_str = f"project = {jql_project_key.upper()} ORDER BY updated DESC"
    console.print(f"Using JQL query: {jql_query_str}")

    issues = fetch_issues(jira, jql_query_str, max_res_count)
    if not issues: return

    extracted_data = extract_issue_data(issues, jira, config)
    # reorder_data_for_output is now mostly for ensuring OrderedDict type and strict key presence
    # extract_issue_data should already produce data in the correct order based on fields_setup
    final_ordered_data = reorder_data_for_output(extracted_data, config) 

    if not final_ordered_data:
        console.print("[bold yellow]No data extracted based on the current field setup in configuration.[/bold yellow]")
        return

    if show_preview_flag:
        display_preview(final_ordered_data, cfg_disp.get('preview_rows', 5), config)
        if not click.confirm("Continue with export?", default=True):
            console.print("Export cancelled by user.")
            return
            
    if not output_path:
        output_dir = pathlib.Path(cfg_ext.get('output_directory', './exports'))
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = output_dir / f"jira_extract_{timestamp}.csv"
    else: # Ensure output_path is a Path object if provided as string
        output_path = pathlib.Path(output_path)

    export_to_csv(final_ordered_data, str(output_path), config)

@cli.command('configure')
@click.option('--global', 'global_', is_flag=True, help='Configure global settings (~/.jirax/config.toml)')
def configure(global_):
    """Configure Jira connection, default extraction, and display settings."""
    config_path = CONFIG_PATH if global_ else LOCAL_CONFIG_PATH
    
    existing_config = {}
    if config_path.exists():
        try:
            existing_config = toml.load(config_path)
        except Exception as e:
            console.print(f"[yellow]Warning: Could not load existing config at {config_path}: {e}[/yellow]")

    # Get current values or provide defaults for prompts
    cfg_jira = existing_config.get('jira', {})
    cfg_ext = existing_config.get('extraction', {})
    cfg_disp = existing_config.get('display', {}) # Keep existing display settings

    server_url = click.prompt("Enter Jira server URL", default=cfg_jira.get('server', ''), type=str)
    auth_choice = click.prompt("Authentication type", default=cfg_jira.get('auth_type', 'basic'), type=click.Choice(['basic', 'bearer'], case_sensitive=False))
    token_val = click.prompt(f"Enter Jira {'PAT (for basic auth)' if auth_choice.lower() == 'basic' else 'Bearer Token'}", default=cfg_jira.get('token', ''), hide_input=True, type=str)
    
    email_addr = ""
    login_user = ""
    if auth_choice.lower() == "basic":
        email_addr = click.prompt("Enter Atlassian email (for basic auth)", default=cfg_jira.get('email', ''), type=str)
    else:
        login_user = click.prompt("Enter Jira username (optional for some bearer auth)", default=cfg_jira.get('login', ''), type=str, show_default=True)

    verify_ssl_choice = click.confirm("Verify SSL certificates?", default=cfg_jira.get('verify_ssl', True))
    timeout_val = click.prompt("Connection timeout (seconds)", default=cfg_jira.get('timeout', 30), type=int)
    
    default_proj_key = click.prompt("Default project key (optional)", default=cfg_ext.get('default_project', ''), type=str, show_default=True)
    max_res_val = click.prompt("Default max results", default=cfg_ext.get('max_results', 1000), type=int, show_default=True)
    output_dir_val = click.prompt("Default output directory", default=cfg_ext.get('output_directory', './exports'), type=str, show_default=True)
    
    # Preserve existing sections not explicitly configured here, especially 'fields_setup' and 'jira_options'
    config_to_save = existing_config.copy() 

    config_to_save['jira'] = {
        'server': server_url, 'token': token_val, 'auth_type': auth_choice.lower(),
        'email': email_addr, 'login': login_user, 'verify_ssl': verify_ssl_choice, 'timeout': timeout_val
    }
    config_to_save['extraction'] = {
        'default_project': default_proj_key, 'max_results': max_res_val, 'output_directory': output_dir_val
    }
    # Ensure display section exists, but don't overwrite if it has more than defaults
    if 'display' not in config_to_save:
        config_to_save['display'] = {'preview': True, 'preview_rows': 5}
    else: # Merge to ensure preview and preview_rows are there if user deleted them from an existing file
        config_to_save['display'].setdefault('preview', True)
        config_to_save['display'].setdefault('preview_rows', 5)


    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, 'w') as f:
        toml.dump(config_to_save, f)
    
    os.chmod(config_path, 0o600)
    location_str = "global (~/.jirax/config.toml)" if global_ else f"local ({config_path.resolve()})"
    console.print(f"[bold green]Configuration saved to {location_str}[/bold green]")

@cli.command('list-projects')
@click.option('-s', '--server', help='Jira server URL')
@click.option('-t', '--token', help='Jira PAT or Bearer token')
# ... (other options similar to extract command for overriding config) ...
@click.option('-c', '--config-path', 'config_path_override', type=click.Path(exists=True, dir_okay=False, resolve_path=True), help='Path to a custom config.toml file')
def list_projects_command(server, token, email=None, auth_type=None, login=None, verify_ssl=None, timeout=None, config_path_override=None):
    """List all available projects in your Jira instance."""
    global CONFIG_PATH, LOCAL_CONFIG_PATH
    if config_path_override:
        LOCAL_CONFIG_PATH = pathlib.Path(config_path_override)
        CONFIG_PATH = pathlib.Path()
    
    # list_jira_projects is imported, it will handle its own config loading and CLI overrides
    list_jira_projects(
        cli_server=server, cli_token=token, cli_email=email, 
        cli_auth_type=auth_type, cli_login=login, 
        cli_verify_ssl=verify_ssl, cli_timeout=timeout
    )


@cli.command('discover-fields')
@click.option('-s', '--server', help='Jira server URL (overrides config)')
@click.option('-t', '--token', help='Jira PAT or Bearer token (overrides config)')
@click.option('-e', '--email', help='Jira email for basic auth (overrides config)')
@click.option('-a', '--auth-type', type=click.Choice(['basic', 'pat', 'bearer'], case_sensitive=False), help='Authentication type (overrides config)')
@click.option('-l', '--login', help='Jira username/login for basic auth (overrides config)')
@click.option('--verify-ssl/--no-verify-ssl', 'verify_ssl', default=None, help='Verify SSL certificate (overrides config)')
@click.option('--timeout', type=int, help='Request timeout in seconds (overrides config)')
@click.option('-c', '--config-path', 'config_path_override', type=click.Path(exists=True, dir_okay=False, resolve_path=True), help='Path to a custom config.toml file')

def discover_fields_command(server, token, email, auth_type, login, verify_ssl, timeout, config_path_override):
    """Discover all available fields in your Jira instance to help configure config.toml."""
    global CONFIG_PATH, LOCAL_CONFIG_PATH, console
    
    if config_path_override:
        LOCAL_CONFIG_PATH = pathlib.Path(config_path_override)
        CONFIG_PATH = pathlib.Path() 
    
    try:
        current_config = load_config()
        cfg_jira = current_config.get('jira', {})

        # Override config with CLI options for Jira connection
        if server: cfg_jira['server'] = server
        if token: cfg_jira['token'] = token
        if email: cfg_jira['email'] = email
        if auth_type: cfg_jira['auth_type'] = auth_type.lower()
        if login: cfg_jira['login'] = login
        if verify_ssl is not None: cfg_jira['verify_ssl'] = verify_ssl
        if timeout is not None: cfg_jira['timeout'] = timeout
        
        # Ensure the updated jira section is part of the current_config
        current_config['jira'] = cfg_jira

        jira = get_jira_client(
            server=cfg_jira.get('server'),
            token=cfg_jira.get('token'),
            email=cfg_jira.get('email'),
            auth_type=cfg_jira.get('auth_type', 'basic'),
            login=cfg_jira.get('login'),
            verify_ssl=cfg_jira.get('verify_ssl', True),
            timeout=cfg_jira.get('timeout', 30)
        )
        
        if jira:
            discover_jira_fields(jira, console)
        else:
            console.print("[bold red]Failed to initialize Jira client. Please check your configuration and credentials.[/bold red]")
            
    except FileNotFoundError:
        console.print(f"[bold red]Configuration file not found. Please run 'jirax configure' or provide connection details via CLI options.[/bold red]")
    except Exception as e:
        console.print(f"[bold red]An error occurred: {e}[/bold red]")


if __name__ == "__main__":
    cli()