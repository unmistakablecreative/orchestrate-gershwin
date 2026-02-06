#!/usr/bin/env python3
"""
Terminal - Shell commands and file operations including document parsing.
"""

import sys
import json
import os
import subprocess
from pathlib import Path

# Document parsing imports
try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    import docx
except ImportError:
    docx = None

try:
    import pandas as pd
except ImportError:
    pd = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None


BASE_DIRECTORIES = [
    os.path.expanduser("~/Documents/Orchestrate/dropzone"),
    "/Applications/OrchestrateOS.app/Contents/Resources/orchestrate/system_docs",
    "/Applications/OrchestrateOS.app/Contents/Resources/orchestrate/data",
    "/Applications/OrchestrateOS.app/Contents/Resources/orchestrate/tools"
]


def run_terminal_command(params):
    """Execute a shell command."""
    command = params.get("command") if isinstance(params, dict) else params
    if not command:
        return {"status": "error", "message": "Missing 'command' parameter"}
    try:
        result = subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT, text=True)
        return {"status": "success", "output": result}
    except subprocess.CalledProcessError as e:
        return {"status": "error", "message": e.output.strip()}


def run_script_file(params):
    """Run a script file."""
    path = params.get("path") if isinstance(params, dict) else params
    if not path:
        return {"status": "error", "message": "Missing 'path' parameter"}
    if not os.path.exists(path):
        return {"status": "error", "message": f"File not found: {path}"}

    try:
        result = subprocess.check_output(path, shell=True, stderr=subprocess.STDOUT, text=True)
        return {"status": "success", "output": result}
    except subprocess.CalledProcessError as e:
        return {"status": "error", "message": e.output.strip()}


def stream_terminal_output(params):
    """Run command and stream output."""
    command = params.get("command") if isinstance(params, dict) else params
    if not command:
        return {"status": "error", "message": "Missing 'command' parameter"}
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    output = ""
    for line in process.stdout:
        output += line
    process.wait()
    return {"status": "success", "output": output.strip()}


def sanitize_command(params):
    """Check if command is safe to run."""
    command = params.get("command") if isinstance(params, dict) else params
    dangerous = ["rm -rf", "shutdown", "reboot", ":(){:|:&};:", "mkfs"]
    if any(d in command for d in dangerous):
        return {"status": "error", "message": "Unsafe command blocked."}
    return {"status": "success", "message": "Command is safe."}


def get_last_n_lines_of_output(params):
    """Get last N lines from command output."""
    command = params.get("command")
    n = params.get("n", 10)
    if not command:
        return {"status": "error", "message": "Missing 'command' parameter"}
    try:
        output = subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT, text=True)
        lines = output.strip().splitlines()
        return {"status": "success", "output": "\n".join(lines[-int(n):])}
    except subprocess.CalledProcessError as e:
        return {"status": "error", "message": e.output.strip()}


def list_directory_contents(params):
    """List contents of a directory."""
    path = params.get("path", ".") if isinstance(params, dict) else params
    if not os.path.exists(path):
        return {"status": "error", "message": f"Path not found: {path}"}
    try:
        items = os.listdir(path)
        return {"status": "success", "items": items}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def list_files(params):
    """List files in a directory with optional recursion."""
    path = params.get("path", ".")
    recursive = params.get("recursive", False)
    try:
        if recursive:
            files = [str(p) for p in Path(path).rglob("*") if p.is_file()]
        else:
            files = [f for f in os.listdir(path) if os.path.isfile(os.path.join(path, f))]
        return {"status": "success", "files": files}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ===== FILE OPERATIONS =====

def find_file(params):
    """Search for files in known directories."""
    keyword = params.get("keyword") or params.get("filename_fragment") or params.get("filename")
    if not keyword:
        return {"status": "error", "message": "Missing 'keyword' parameter"}

    matches = []
    keyword_lower = keyword.lower()

    for base_path in BASE_DIRECTORIES:
        if not os.path.exists(base_path):
            continue
        result = subprocess.run(
            ['find', base_path, '-iname', f'*{keyword}*'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if result.stdout:
            lines = result.stdout.strip().splitlines()
            matches.extend(lines)

    if matches:
        return {
            "status": "success",
            "query": keyword,
            "count": len(matches),
            "matches": matches,
            "selected": matches[0]
        }
    else:
        return {
            "status": "error",
            "message": f"No file matching '{keyword}' found in known directories."
        }


def read_file(params):
    """Read file with auto-detection for PDF, DOCX, CSV, HTML, or plain text.

    Can pass either:
    - path/filename: direct file path
    - filename_fragment: search term to find file first
    """
    path = params.get("path") or params.get("filename")
    filename_fragment = params.get("filename_fragment")

    # If filename_fragment provided, search for file first
    if filename_fragment and not path:
        match = find_file({"keyword": filename_fragment})
        if match.get("status") == "error":
            return match
        path = match.get("selected")

    if not path:
        return {"status": "error", "message": "No path or filename_fragment provided."}

    if not os.path.exists(path):
        return {"status": "error", "message": f"File not found: {path}"}

    ext = os.path.splitext(path)[1].lower()

    try:
        if ext == '.pdf':
            content = _extract_pdf(path)
        elif ext == '.docx':
            content = _extract_docx(path)
        elif ext in ['.csv', '.tsv']:
            content = _extract_csv(path)
        elif ext == '.html':
            content = _extract_html(path)
        else:
            content = _extract_text(path)

        return {
            "status": "success",
            "filename": os.path.basename(path),
            "path": path,
            "extension": ext,
            "content": content
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}


def _extract_pdf(path):
    if not pdfplumber:
        return "Error: pdfplumber not installed. Run: pip install pdfplumber"
    with pdfplumber.open(path) as pdf:
        return '\n'.join(page.extract_text() or '' for page in pdf.pages)


def _extract_docx(path):
    if not docx:
        return "Error: python-docx not installed. Run: pip install python-docx"
    doc = docx.Document(path)
    return '\n'.join([para.text for para in doc.paragraphs])


def _extract_csv(path):
    if not pd:
        return "Error: pandas not installed. Run: pip install pandas"
    df = pd.read_csv(path)
    return df.to_string(index=False)


def _extract_html(path):
    if not BeautifulSoup:
        return "Error: beautifulsoup4 not installed. Run: pip install beautifulsoup4"
    with open(path, 'r', encoding='utf-8') as f:
        soup = BeautifulSoup(f, 'html.parser')
        return soup.get_text()


def _extract_text(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def write_file(params):
    """Write content to a file."""
    path = params.get("path") or params.get("filename")
    content = params.get("content") or params.get("text", "")

    if not path:
        return {"status": "error", "message": "Missing 'path' parameter"}

    try:
        parent_dir = os.path.dirname(path)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return {"status": "success", "message": f"Written to {path}", "path": path}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def append_file(params):
    """Append content to a file."""
    path = params.get("path") or params.get("filename")
    content = params.get("content") or params.get("text", "")

    if not path:
        return {"status": "error", "message": "Missing 'path' parameter"}

    try:
        with open(path, 'a', encoding='utf-8') as f:
            f.write(content)
        return {"status": "success", "message": f"Appended to {path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def move_file(params):
    """Move or rename a file."""
    source = params.get("source") or params.get("from")
    destination = params.get("destination") or params.get("to")

    if not source or not destination:
        return {"status": "error", "message": "Missing 'source' or 'destination'"}

    try:
        import shutil
        parent_dir = os.path.dirname(destination)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        shutil.move(source, destination)
        return {"status": "success", "message": f"Moved {source} to {destination}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def copy_file(params):
    """Copy a file."""
    source = params.get("source") or params.get("from")
    destination = params.get("destination") or params.get("to")

    if not source or not destination:
        return {"status": "error", "message": "Missing 'source' or 'destination'"}

    try:
        import shutil
        parent_dir = os.path.dirname(destination)
        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)
        shutil.copy2(source, destination)
        return {"status": "success", "message": f"Copied {source} to {destination}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def delete_file(params):
    """Delete a file."""
    path = params.get("path") or params.get("filename")

    if not path:
        return {"status": "error", "message": "Missing 'path' parameter"}

    try:
        os.remove(path)
        return {"status": "success", "message": f"Deleted {path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def replace_lines(params):
    """Replace a range of lines in a file."""
    path = params.get("path") or params.get("filename")
    start_line = params.get("start_line")
    end_line = params.get("end_line")
    new_content = params.get("new_content", "")

    if not path or start_line is None:
        return {"status": "error", "message": "path and start_line are required"}

    if end_line is None:
        end_line = start_line

    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.read().split("\n")

        # Convert to 0-indexed
        start_idx = int(start_line) - 1
        end_idx = int(end_line)

        # Replace the lines
        new_lines = lines[:start_idx] + new_content.split("\n") + lines[end_idx:]

        with open(path, 'w', encoding='utf-8') as f:
            f.write("\n".join(new_lines))

        return {"status": "success", "message": f"Replaced lines {start_line}-{end_line} in {path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def grep_content(params):
    """Search file contents for a pattern. Uses ripgrep if available, falls back to grep."""
    pattern = params.get("pattern")
    path = params.get("path", ".")
    file_type = params.get("type")  # e.g., "py", "json"
    max_results = params.get("max_results", 100)
    case_insensitive = params.get("case_insensitive", False)

    if not pattern:
        return {"status": "error", "message": "Missing 'pattern' parameter"}

    # Try ripgrep first, fall back to grep
    rg_paths = [
        "/opt/homebrew/bin/rg",
        "/usr/local/bin/rg",
        "rg"  # In PATH
    ]

    rg_path = None
    for candidate in rg_paths:
        try:
            subprocess.run([candidate, "--version"], capture_output=True, check=True)
            rg_path = candidate
            break
        except:
            continue

    if rg_path:
        # Use ripgrep
        cmd = [rg_path, "--json", pattern]
        if case_insensitive:
            cmd.append("-i")
        if file_type:
            cmd.extend(["--type", file_type])
        cmd.append(path)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            matches = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    if data.get("type") == "match":
                        match_data = data.get("data", {})
                        matches.append({
                            "file": match_data.get("path", {}).get("text"),
                            "line_number": match_data.get("line_number"),
                            "text": match_data.get("lines", {}).get("text", "").strip()
                        })
                except:
                    continue

            return {
                "status": "success",
                "pattern": pattern,
                "count": len(matches),
                "matches": matches[:max_results]
            }
        except subprocess.TimeoutExpired:
            return {"status": "error", "message": "Search timed out after 30s"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    else:
        # Fall back to grep
        cmd = ["grep", "-rn"]
        if case_insensitive:
            cmd.append("-i")
        if file_type:
            cmd.extend(["--include", f"*.{file_type}"])
        cmd.extend([pattern, path])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            matches = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                # grep output format: file:line_number:text
                parts = line.split(":", 2)
                if len(parts) >= 3:
                    matches.append({
                        "file": parts[0],
                        "line_number": int(parts[1]) if parts[1].isdigit() else None,
                        "text": parts[2].strip()
                    })

            return {
                "status": "success",
                "pattern": pattern,
                "count": len(matches),
                "matches": matches[:max_results]
            }
        except subprocess.TimeoutExpired:
            return {"status": "error", "message": "Search timed out after 30s"}
        except Exception as e:
            return {"status": "error", "message": str(e)}


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    actions = {
        # Terminal commands
        'run_terminal_command': run_terminal_command,
        'run_script_file': run_script_file,
        'stream_terminal_output': stream_terminal_output,
        'sanitize_command': sanitize_command,
        'get_last_n_lines_of_output': get_last_n_lines_of_output,
        'list_directory_contents': list_directory_contents,
        'list_files': list_files,
        # File operations
        'find_file': find_file,
        'read_file': read_file,
        'write_file': write_file,
        'append_file': append_file,
        'move_file': move_file,
        'copy_file': copy_file,
        'delete_file': delete_file,
        'replace_lines': replace_lines,
        'grep_content': grep_content,
    }

    if args.action in actions:
        result = actions[args.action](params)
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
