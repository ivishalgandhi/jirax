# Jirax

A simple command-line tool for extracting Jira issues and exporting them to CSV format. Easily retrieve and organize Jira data using project keys or custom JQL queries.

## Features

- Extract Jira issues using project keys or custom JQL queries
- Export data to CSV format
- Preview data before export
- Supports both basic and bearer token authentication methods
- Secure handling of authentication via TOML configuration files
- Rich console output with progress indicators

## Installation

1. Ensure you have Python 3.8+ installed
2. Clone this repository
3. Install the package:

```bash
# Development installation (from the repository root directory)
pip install -e .

# OR install directly from GitHub
pip install git+https://github.com/ivishalgandhi/jirax.git
```

## Project Structure

```
jirax/
├── jirax/                  # Package directory
│   ├── __init__.py        # Package initialization
│   ├── __main__.py        # Module entry point
│   ├── jirax.py           # Main functionality
│   └── list_projects.py   # Project listing utility
├── tests/                 # Test directory
│   └── test_jirax.py      # Test script
├── jirax.py               # Development script
├── config.example.toml    # Example configuration
├── pyproject.toml         # Project metadata and dependencies
└── README.md              # This file
```

## Configuration

You can configure your Jira connection using a TOML configuration file. The tool looks for configuration in the following locations (in order of precedence):

1. Custom config file specified with the `--config` option
2. Local config file in the current directory (`./config.toml`)
3. Global config file in your home directory (`~/.jirax/config.toml`)

**Important:** The `config.toml` file contains sensitive information like your Jira PAT and URL, so it's included in `.gitignore` to prevent accidental exposure.

### Using the configuration command

The easiest way to create or update your configuration is with the configure command:

```bash
# For a local config file in the current directory
jirax configure --local

# For a global config file in ~/.jirax/
jirax configure --global
```

This will prompt you for your Jira server URL, Personal Access Token (PAT), and other default settings.

### Manual configuration

You can also create or edit the TOML config file manually. Here's an example configuration:

```toml
# Jira Extractor Configuration File

[jira]
server = "https://your-instance.atlassian.net"
# Authentication type: "basic" (default) or "bearer" for Personal Access Tokens
auth_type = "basic"
# Your token (PAT for basic auth or Bearer token for bearer auth)
token = "your-personal-access-token"
# Email (required for basic auth)
email = "your.email@example.com"
# Login (only required for some Jira instances with bearer auth)
# login = "your-jira-username"

[extraction]
# Default project to extract from if no project is specified
default_project = "PROJ"
# Default max results to fetch
max_results = 1000
# Default output directory for extractions
output_directory = "./exports"

[display]
# Show preview before exporting
preview = true
# Number of rows to show in preview
preview_rows = 5
```

## Usage

### Available Commands

Jirax provides the following commands:

- `extract` - Extract Jira issues to CSV
- `configure` - Set up your Jira connection details
- `list-projects` - View all available projects in your Jira instance

### Basic Usage

Extract issues from a project:

```bash
jirax extract --project PROJ
```

Use a custom JQL query:

```bash
jirax extract --query "project = PROJ AND status = 'In Progress'"
```

List all available projects in your Jira instance:

```bash
jirax list-projects
```

### Authentication Options

Jirax supports two authentication methods:

#### Basic Authentication

Used with email and Personal Access Token (PAT):

```bash
jirax extract --email your.email@example.com --token your-pat --project PROJ
```

#### Bearer Token Authentication

Used with a bearer token (some Jira instances require this):

```bash
jirax extract --auth-type bearer --token your-bearer-token --project PROJ
```

Some Jira instances also require a username with bearer authentication:

```bash
jirax extract --auth-type bearer --token your-bearer-token --login your-username --project PROJ
```

### Advanced Options

```bash
jirax extract --help
```

```
Options:
  -s, --server TEXT             Jira server URL
  -t, --token TEXT              Jira Personal Access Token or Bearer token
  -e, --email TEXT              Atlassian email address for authentication (basic auth)
  -a, --auth-type TEXT          Authentication type: "basic" or "bearer"
  -l, --login TEXT              Username for bearer token authentication (if required)
  -p, --project TEXT            Jira project key
  -q, --query TEXT              Custom JQL query (overrides project if provided)
  -m, --max-results INTEGER     Maximum number of results to return
  -o, --output-path TEXT        Output file path (with .csv extension)
  --preview / --no-preview      Preview results before export
  -c, --config TEXT             Path to config file
  --help                        Show this message and exit.
```

## Examples

### Export to CSV with default options

```bash
# Using config file settings
jirax extract

# Or specifying a project
jirax extract --project MYPROJ
```

### Use a custom JQL query

```bash
jirax extract --query "project = MYPROJ AND status = 'In Progress'"
```

### Using a specific config file

```bash
jirax extract --config /path/to/my/config.toml
```

### Specify output path

```bash
jirax extract --project MYPROJ --output-path ./exports/my_extract.csv
```

## Extracted Fields

The tool extracts the following fields from Jira issues:

- Key
- Summary
- Issue_Type (Epic, Story, Task, Bug, etc.)
- Status
- Priority
- Assignee
- Reporter
- Resolution
- Updated
- Sprint
- Epic_Key
- Epic_Name
- Labels
- Extract_Date (date/time when the extraction was performed, always the last column)

### Identifying Epics and Stories

You can easily identify the issue type in your exported data:

- **Epics** will have `Issue_Type = "Epic"` and blank `Epic_Key` fields
- **Stories** will have `Issue_Type = "Story"` and populated `Epic_Key` fields showing which epic they belong to
- **Tasks** and other issue types will be similarly identified in the `Issue_Type` field

## Running Tests

The project includes a comprehensive test suite that validates functionality with various query scenarios:

```bash
./tests/test_jirax.py
```

This will run tests for:
- Basic project extraction
- JQL queries with various filters
- Error handling for invalid inputs
- Issue type filtering

Test results are saved to the `test_results` directory for inspection.

## Development

To contribute to this project:

1. Fork the repository
2. Create a new branch for your feature
3. Make your changes
4. Run the tests to ensure everything works
5. Submit a pull request

## License

MIT
