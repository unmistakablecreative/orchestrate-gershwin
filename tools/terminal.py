#!/usr/bin/env python3
"""
Terminal - Shell commands and file operations including document parsing.
"""

import sys
import json
import os
import subprocess

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
    "/Applications/OrchestrateOS.app/Contents/Resources/orchestrate/data"
]


def run_terminal_command(command):
    try:
        result = subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT, text=True)
        return {"status": "success", "output": result}
    except subprocess.CalledProcessError as e:
        return {"status": "error", "message": e.output.strip()}


def run_script_file(path):
    if not os.path.exists(path):
        return {"status": "error", "message": f"File not found: {path}"}

    try:
        result = subprocess.check_output(path, shell=True, stderr=subprocess.STDOUT, text=True)
        return {"status": "success", "output": result}
    except subprocess.CalledProcessError as e:
        return {"status": "error", "message": e.output.strip()}


def stream_terminal_output(command):
    process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    output = ""
    for line in process.stdout:
        output += line
    process.wait()

    return {"status": "success", "output": output.strip()}


def sanitize_command(command):
    dangerous = ["rm -rf", "shutdown", "reboot", ":(){:|:&};:", "mkfs"]

    if any(d in command for d in dangerous):
        return {"status": "error", "message": "Unsafe command blocked."}

    return {"status": "success", "message": "Command is safe."}


def get_last_n_lines_of_output(command, n):
    try:
        output = subprocess.check_output(command, shell=True, stderr=subprocess.STDOUT, text=True)
        lines = output.strip().splitlines()
        return {"status": "success", "output": "\n".join(lines[-int(n):])}
    except subprocess.CalledProcessError as e:
        return {"status": "error", "message": e.output.strip()}


def list_directory_contents(path):
    if not os.path.exists(path):
        return {"status": "error", "message": f"Path not found: {path}"}

    try:
        items = os.listdir(path)
        return {"status": "success", "items": items}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ===== FILE OPERATIONS =====

def find_file(filename_fragment):
    """Search for files in known directories."""
    matches = []

    for base_path in BASE_DIRECTORIES:
        if not os.path.exists(base_path):
            continue
        result = subprocess.run(
            ['find', base_path, '-iname', f'*{filename_fragment}*'],
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
            "match_count": len(matches),
            "matches": matches,
            "selected": matches[0]
        }
    else:
        return {
            "status": "error",
            "message": f"No file matching '{filename_fragment}' found in known directories."
        }


def read_file(path=None, filename_fragment=None):
    """Read file with auto-detection for PDF, DOCX, CSV, HTML, or plain text.

    Can pass either:
    - path: direct file path
    - filename_fragment: search term to find file first
    """
    # If filename_fragment provided, search for file first
    if filename_fragment and not path:
        match = find_file(filename_fragment)
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


def write_file(path, content):
    """Write content to a file."""
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return {"status": "success", "message": f"Written to {path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def append_file(path, content):
    """Append content to a file."""
    try:
        with open(path, 'a', encoding='utf-8') as f:
            f.write(content)
        return {"status": "success", "message": f"Appended to {path}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def move_file(source, destination):
    """Move or rename a file."""
    try:
        import shutil
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.move(source, destination)
        return {"status": "success", "message": f"Moved {source} to {destination}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def copy_file(source, destination):
    """Copy a file."""
    try:
        import shutil
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        shutil.copy2(source, destination)
        return {"status": "success", "message": f"Copied {source} to {destination}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def delete_file(path):
    """Delete a file."""
    try:
        os.remove(path)
        return {"status": "success", "message": f"Deleted {path}"}
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
        'get_last_n_lines_of_output': get_last_n_lines_of_output,
        'list_directory_contents': list_directory_contents,
        'run_script_file': run_script_file,
        'run_terminal_command': run_terminal_command,
        'sanitize_command': sanitize_command,
        'stream_terminal_output': stream_terminal_output,
        # File operations
        'find_file': find_file,
        'read_file': read_file,
        'write_file': write_file,
        'append_file': append_file,
        'move_file': move_file,
        'copy_file': copy_file,
        'delete_file': delete_file,
    }

    if args.action in actions:
        result = actions[args.action](**params)
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
