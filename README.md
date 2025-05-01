# py-mcp-google-toolbox
[![smithery badge](https://smithery.ai/badge/@jikime/py-mcp-google-toolbox)](https://smithery.ai/server/@jikime/py-mcp-google-toolbox) ![](https://badge.mcpx.dev?type=server 'MCP Server') ![Version](https://img.shields.io/badge/version-1.1.10-green) ![License](https://img.shields.io/badge/license-MIT-blue)

An MCP server that provides AI assistants with powerful tools to interact with Google services, including Gmail, Google Calendar, Google Drive, and Google Search.

<a href="https://glama.ai/mcp/servers/@jikime/py-mcp-google-toolbox">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/@jikime/py-mcp-google-toolbox/badge" alt="Google Toolbox MCP server" />
</a>

## Overview

py-mcp-google-toolbox provides the following Google-related functionalities:

- Gmail operations (read, search, send, modify)
- Google Calendar management (events creation, listing, updating, deletion)
- Google Drive interactions (search, read files)
- Google Search integration (search web)

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configure MCP Settings](#configure-mcp-settings)
- [Tools Documentation](#tools-documentation)
  - [Gmail Tools](#gmail-tools)
  - [Calendar Tools](#calendar-tools)
  - [Drive Tools](#drive-tools)
  - [Search Tools](#search-tools)
- [Development](#development)
- [License](#license)

## Prerequisites
1. **Python**: Install Python 3.12 or higher
2. **Google Cloud Console Setup**:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select an existing one
   - Enable the Service API:
     1. Go to "APIs & Services" > "Library"
     2. Search for and enable "Gmail API"
     3. Search for and enable "Google Calendar API"
     4. Search for and enable "Google Drive API"
     5. Search formand enable "Custom Search API"
   - Set up OAuth 2.0 credentials from GCP:
     1. Go to "APIs & Services" > "Credentials"
     2. Click "Create Credentials" > "OAuth client ID"
     3. Choose "Web application"
     4. Note down the Client ID and Client Secret
        - Client ID
        - Client Secret 
     5. download secret json and rename to credentials.json
   - Generate an API key
3. Go to [Custom Search Engine](https://cse.google.com/cse/all) and get its ID

## Installation
#### Git Clone
```bash
git clone https://github.com/jikime/py-mcp-google-toolbox.git
cd py-mcp-google-toolbox
```

#### Configuration 
1. Install UV package manager:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

2. Create and activate virtual environment:
```bash
uv venv -p 3.12
source .venv/bin/activate  # On MacOS/Linux
# or
.venv\Scripts\activate  # On Windows
```

3. Install dependencies:
```bash
uv pip install -r requirements.txt
```

4. Get refresh token (if token is expired, you can run this)
```bash
uv run get_refresh_token.py
```
This will:
- Open your browser for Google OAuth authentication
- Request the following permissions:
  - `https://www.googleapis.com/auth/gmail.modify`
  - `https://www.googleapis.com/auth/calendar`
  - `https://www.googleapis.com/auth/gmail.send`
  - `https://www.googleapis.com/auth/gmail.readonly`
  - `https://www.googleapis.com/auth/drive`
  - `https://www.googleapis.com/auth/drive.file`
  - `https://www.googleapis.com/auth/drive.readonly`
- Save the credentials to `token.json`
- Display the refresh token in the console

5. Environment variables:
```bash
cp env.example .env
vi .env
# change with your key
GOOGLE_API_KEY=your_google_api_key
GOOGLE_CSE_ID=your_custom_search_engine_id
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REFRESH_TOKEN=your_google_refresh_token
```
6. copy credentials.json to project root folder (py-mcp-google-toolbox)


#### Using Docker

1. Build the Docker image:
```bash
docker build -t py-mcp-google-toolbox .
```

2. Run the container:
```bash
docker run py-mcp-google-toolbox
```

#### Using Local

1. Run the server:
```bash
mcp dev server.py
```

## Configure MCP Settings
Add the server configuration to your MCP settings file:

#### Claude desktop app 
1. To install automatically via [Smithery](https://smithery.ai/server/py-mcp-google-toolbox):

```bash
npx -y @smithery/cli install py-mcp-google-toolbox --client claude
```

2. To install manually
open `~/Library/Application Support/Claude/claude_desktop_config.json`

Add this to the `mcpServers` object:
```json
{
  "mcpServers": {
    "Google Toolbox": {
      "command": "/path/to/bin/uv",
      "args": [
        "--directory",
        "/path/to/py-mcp-google-toolbox",
        "run",
        "server.py"
      ]
    }
  }
}
```

#### Cursor IDE 
open `~/.cursor/mcp.json`

Add this to the `mcpServers` object:
```json
{
  "mcpServers": {
    "Google Toolbox": {
      "command": "/path/to/bin/uv",
      "args": [
        "--directory",
        "/path/to/py-mcp-google-toolbox",
        "run",
        "server.py"
      ]
    }
  }
}
```

#### for Docker
```json
{
  "mcpServers": {
    "Google Toolbox": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "py-mcp-google-toolbox"
      ]
    }
  }
}
```

## Tools Documentation

### Gmail Tools

- `list_emails`: Lists recent emails from Gmail inbox with filtering options
- `search_emails`: Performs advanced Gmail searches with detailed email content retrieval
- `send_email`: Composes and sends emails with support for CC, BCC recipients
- `modify_email`: Changes email states (read/unread, archived, trashed) by modifying labels

### Calendar Tools

- `list_events`: Retrieves upcoming calendar events within specified time ranges
- `create_event`: Creates new calendar events with attendees, location, and description
- `update_event`: Modifies existing calendar events with flexible parameter updating
- `delete_event`: Removes calendar events by event ID

### Drive Tools

- `read_gdrive_file`: Reads and retrieves content from Google Drive files
- `search_gdrive`: Searches Google Drive for files with customizable queries

### Search Tools

- `search_google`: Performs Google searches and returns formatted results

## Development

For local testing, you can use the included client script:

```bash
# Example: List emails
uv run client.py list_emails max_results=5 query="is:unread"

# Example: Search emails
uv run client.py search_emails query="from:test@example.com"

# Example: Send email
uv run client.py send_email to="test@example.com" subject="test mail" body="Hello"

# Example: Modify email
uv run client.py modify_email id=MESSAGE_ID remove_labels=INBOX add_labels=ARCHIVED

# Example: List events
uv run client.py list_events time_min=2025-05-01T00:00:00+09:00 time_max=2025-05-02T23:59:59+09:00 max_results=5

# Example: Create event
uv run client.py create_event summary="new event" start=2025-05-02T10:00:00+09:00 end=2025-05-02T11:00:00+09:00 attendees="user1@example.com,user2@example.com"

# Example: Update event
uv run client.py update_event event_id=EVENT_ID summary="update event" start=2025-05-02T10:00:00+09:00 end=2025-05-02T11:00:00+09:00 attendees="user1@example.com,user2@example.com"

# Example Delete event
uv run client.py delete_event event_id=EVENT_ID

# Example: Search Google
uv run client.py search_google query="what is the MCP?"

# Example: Search Google Drive
uv run client.py search_gdrive query=mcp

# Example: Read file
uv run client.py read_gdrive_file file_id=1234567890
```

## License

MIT License
