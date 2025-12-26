#!/usr/bin/env python3
"""
File Ops Tool

Auto-refactored by refactorize.py to match gold standard structure.
"""

import os
import sys
import json
import subprocess

import pdfplumber
import docx
import pandas as pd
from bs4 import BeautifulSoup


BASE_DIRECTORIES = [
    "/orchestrate_user/dropzone",
    "/opt/orchestrate-core-runtime/system_docs"
]


def find_file(filename_fragment):
    matches = []

    for base_path in BASE_DIRECTORIES:
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


def extract_pdf(path):
    try:
        with pdfplumber.open(path) as pdf:
            return '\n'.join(page.extract_text() or '' for page in pdf.pages)
    except Exception as e:
        return f"❌ PDF read error: {str(e)}"


def extract_docx(path):
    try:
        doc = docx.Document(path)
        return '\n'.join([para.text for para in doc.paragraphs])
    except Exception as e:
        return f"❌ DOCX read error: {str(e)}"


def extract_csv(path):
    try:
        df = pd.read_csv(path)
        return df.to_string(index=False)
    except Exception as e:
        return f"❌ CSV read error: {str(e)}"


def extract_html(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'html.parser')
            return soup.get_text()
    except Exception as e:
        return f"❌ HTML read error: {str(e)}"


def extract_text(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"❌ Text read error: {str(e)}"


def read_file(filename_fragment):
    match = find_file(filename_fragment)

    if match.get("status") == "error":
        return match

    path = match.get("selected")
    if not path:
        return {"status": "error", "message": "No matching file found to read."}

    ext = os.path.splitext(path)[1].lower()

    if ext == '.pdf':
        content = extract_pdf(path)
    elif ext == '.docx':
        content = extract_docx(path)
    elif ext in ['.csv', '.tsv']:
        content = extract_csv(path)
    elif ext == '.html':
        content = extract_html(path)
    else:
        content = extract_text(path)

    return {
        "status": "success",
        "filename": os.path.basename(path),
        "extension": ext,
        "content": content
    }


def main():
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if args.action == 'extract_csv':
        result = extract_csv(**params)
    elif args.action == 'extract_docx':
        result = extract_docx(**params)
    elif args.action == 'extract_html':
        result = extract_html(**params)
    elif args.action == 'extract_pdf':
        result = extract_pdf(**params)
    elif args.action == 'extract_text':
        result = extract_text(**params)
    elif args.action == 'find_file':
        result = find_file(**params)
    elif args.action == 'read_file':
        result = read_file(**params)
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()