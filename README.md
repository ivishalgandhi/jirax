# Jirax

A simple command-line tool for extracting Jira issues and exporting them to CSV format. Easily retrieve and organize Jira data using project keys or custom JQL queries.

## Features

- Extract Jira issues using project keys or custom JQL queries
- Export data to CSV format
- Preview data before export
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
pip install git+https://github.com/yourusername/jirax.git
```

## Project Structure

```
jirax/
├── jirax/              # Package directory
│   ├── __init__.py    # Package initialization
│   ├── __main__.py    # Module entry point
│   └── jirax.py       # Main functionality
├── jirax.py           # Development script
├── test_jirax.py      # Test script
├── config.example.toml # Example configuration
├── pyproject.toml     # Project metadata and dependencies
└── README.md          # This file
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
token = "your-personal-access-token"
email = "your.email@example.com"

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

### Basic Usage

Extract issues from a project:

```bash
jirax extract --project PROJ
```

Use a custom JQL query:

```bash
jirax extract --query "project = PROJ AND status = 'In Progress'"
```

### Advanced Options

```bash
jirax extract --help
```

```
Options:
  -s, --server TEXT             Jira server URL
  -t, --token TEXT              Jira Personal Access Token
  -e, --email TEXT              Atlassian email address for authentication
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
./test_jirax.py
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
