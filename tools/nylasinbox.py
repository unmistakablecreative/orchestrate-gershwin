#!/usr/bin/env python3
"""
nylasinbox.py - Generic Nylas Email Tool

Universal email tool providing list/read/send/reply/search/archive/label operations
via unified API backed by local SQLite cache (inbox.db). Works with any Nylas account.

17 Actions:
- list_threads, read_thread, read_message, send_email, reply
- search, search_local, archive, unarchive, delete
- label, batch_archive, batch_label, sync, get_stats
- list_attachments, download_attachment
"""

import json
import os
import sqlite3
import time
import requests
from datetime import datetime
from system_settings import load_credential
from response_helper import get_success_message, get_error_message


# =============================================================================
# DATABASE SETUP
# =============================================================================

INBOX_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'inbox.db')


def get_db():
    """Returns db connection, creates tables if needed."""
    conn = sqlite3.connect(INBOX_DB_PATH)
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def init_db(conn=None):
    """Creates all tables with schema if they don't exist."""
    should_close = False
    if conn is None:
        conn = sqlite3.connect(INBOX_DB_PATH)
        should_close = True

    cursor = conn.cursor()

    # threads table - stores email threads (conversation containers)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS threads (
            thread_id TEXT PRIMARY KEY,
            subject TEXT,
            sender TEXT,
            sender_name TEXT,
            date TEXT,
            message_count INTEGER DEFAULT 1,
            category TEXT,
            status TEXT DEFAULT 'active',
            snippet TEXT,
            unread INTEGER DEFAULT 1,
            created_at TEXT,
            updated_at TEXT
        )
    ''')

    # messages table - stores individual email messages
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            message_id TEXT PRIMARY KEY,
            thread_id TEXT,
            subject TEXT,
            sender TEXT,
            sender_name TEXT,
            recipients TEXT,
            date TEXT,
            body TEXT,
            body_raw TEXT,
            category TEXT,
            is_sent INTEGER DEFAULT 0,
            created_at TEXT,
            FOREIGN KEY (thread_id) REFERENCES threads(thread_id)
        )
    ''')

    # attachments table - stores email attachment metadata
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attachments (
            attachment_id TEXT PRIMARY KEY,
            message_id TEXT,
            filename TEXT,
            content_type TEXT,
            size INTEGER,
            saved_path TEXT,
            created_at TEXT,
            FOREIGN KEY (message_id) REFERENCES messages(message_id)
        )
    ''')

    # sent_emails table - tracks all outbound emails
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sent_emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id TEXT,
            thread_id TEXT,
            to_email TEXT,
            subject TEXT,
            body_preview TEXT,
            sent_at TEXT,
            send_type TEXT,
            context_key TEXT
        )
    ''')

    # Create indexes for common queries
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_threads_status ON threads(status)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_threads_category ON threads(category)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_threads_date ON threads(date)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_messages_thread_id ON messages(thread_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_attachments_message_id ON attachments(message_id)')

    conn.commit()

    if should_close:
        conn.close()


# =============================================================================
# DATABASE HELPERS
# =============================================================================

def add_thread(thread_id, subject, sender, sender_name, date, category=None, snippet=None, message_count=1):
    """Insert or update a thread."""
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    cursor.execute('''
        INSERT INTO threads (thread_id, subject, sender, sender_name, date, category, snippet, message_count, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(thread_id) DO UPDATE SET
            subject = excluded.subject,
            sender = excluded.sender,
            sender_name = excluded.sender_name,
            date = excluded.date,
            category = COALESCE(excluded.category, threads.category),
            snippet = excluded.snippet,
            message_count = excluded.message_count,
            updated_at = ?
    ''', (thread_id, subject, sender, sender_name, date, category, snippet, message_count, now, now, now))

    conn.commit()
    conn.close()


def add_message(message_id, thread_id, subject, sender, sender_name, recipients, date, body, body_raw=None, category=None, is_sent=0):
    """Insert or update a message."""
    conn = get_db()
    cursor = conn.cursor()
    now = datetime.now().isoformat()

    cursor.execute('''
        INSERT INTO messages (message_id, thread_id, subject, sender, sender_name, recipients, date, body, body_raw, category, is_sent, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(message_id) DO UPDATE SET
            body = excluded.body,
            body_raw = excluded.body_raw,
            category = COALESCE(excluded.category, messages.category)
    ''', (message_id, thread_id, subject, sender, sender_name, recipients, date, body, body_raw, category, is_sent, now))

    conn.commit()
    conn.close()


def update_thread_status(thread_id, status):
    """Update thread status (active, archived, deleted)."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE threads SET status = ?, updated_at = ? WHERE thread_id = ?',
                   (status, datetime.now().isoformat(), thread_id))
    conn.commit()
    conn.close()


def update_thread_category(thread_id, category):
    """Update thread category/label."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE threads SET category = ?, updated_at = ? WHERE thread_id = ?',
                   (category, datetime.now().isoformat(), thread_id))
    conn.commit()
    conn.close()


def record_sent(message_id, thread_id, to_email, subject, body_preview, send_type='send'):
    """Record a sent email."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO sent_emails (message_id, thread_id, to_email, subject, body_preview, sent_at, send_type)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (message_id, thread_id, to_email, subject, body_preview[:200] if body_preview else '', datetime.now().isoformat(), send_type))
    conn.commit()
    conn.close()


def add_attachment_record(attachment_id, message_id, filename, content_type, size, saved_path=None):
    """Record an attachment."""
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO attachments (attachment_id, message_id, filename, content_type, size, saved_path, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (attachment_id, message_id, filename, content_type, size, saved_path, datetime.now().isoformat()))
    conn.commit()
    conn.close()


# =============================================================================
# HELPERS
# =============================================================================

def get_nylas_creds():
    """Load Nylas credentials from system_settings."""
    creds = load_credential("nylas_inbox")
    return creds['grant_id'], creds['access_token']


def clean_email_content(raw_content):
    """Clean email content by stripping HTML and formatting while preserving structure."""
    if not raw_content:
        return "(No content)"

    import re
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        # Fallback if BeautifulSoup not available
        content = re.sub(r'<[^>]+>', '', raw_content)
        return content.strip() or "(No content)"

    content = raw_content
    # Remove script, style, and comments first
    content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)

    # Parse with BeautifulSoup
    soup = BeautifulSoup(content, 'html.parser')

    # Preserve link hrefs inline before extracting text
    for a_tag in soup.find_all('a', href=True):
        href = a_tag.get('href', '')
        if href and not href.startswith('#') and not href.startswith('mailto:'):
            a_tag.append(f' ({href})')

    # Extract text with newlines between elements
    text = soup.get_text(separator='\n')

    # Collapse runs of 3+ newlines to 2 (preserve paragraph breaks)
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Filter out unsubscribe/privacy footer lines
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        line = line.strip()
        if line and not any(skip in line.lower() for skip in [
            'unsubscribe', 'privacy policy', 'copyright', 'all rights reserved',
            'this email was sent', 'update your preferences', 'click here to'
        ]):
            cleaned_lines.append(line)

    final_content = '\n'.join(cleaned_lines).strip()
    return final_content if final_content else "(No content)"


# =============================================================================
# ACTION 1: list_threads
# =============================================================================

def list_threads(params):
    """Get inbox threads with optional filters.

    Optional params:
        limit: Max results (default 50)
        category: Filter by category
        status: Filter by status (default 'active')
    """
    limit = params.get('limit', 50)
    category = params.get('category')
    status = params.get('status', 'active')

    conn = get_db()
    cursor = conn.cursor()

    query = 'SELECT * FROM threads WHERE status = ?'
    query_params = [status]

    if category:
        query += ' AND category = ?'
        query_params.append(category)

    query += ' ORDER BY date DESC LIMIT ?'
    query_params.append(limit)

    cursor.execute(query, query_params)
    rows = cursor.fetchall()
    conn.close()

    threads = [dict(row) for row in rows]
    return {'status': 'success', 'threads': threads, 'count': len(threads)}


# =============================================================================
# ACTION 2: read_thread
# =============================================================================

def read_thread(params):
    """Get all messages in a thread.

    Required: thread_id or message_id
    """
    thread_id = params.get('thread_id')
    message_id = params.get('message_id')

    if not thread_id and not message_id:
        return {'status': 'error', 'message': 'Missing thread_id or message_id parameter'}

    grant_id, access_token = get_nylas_creds()
    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}

    # If only message_id provided, get thread_id from it
    if not thread_id and message_id:
        msg_url = f'https://api.us.nylas.com/v3/grants/{grant_id}/messages/{message_id}'
        msg_resp = requests.get(msg_url, headers=headers)
        if msg_resp.status_code != 200:
            return {'status': 'error', 'message': f'Failed to fetch message: {msg_resp.text}'}
        thread_id = msg_resp.json().get('data', {}).get('thread_id')
        if not thread_id:
            return {'status': 'error', 'message': 'Message has no thread_id'}

    # Get thread messages
    url = f'https://api.us.nylas.com/v3/grants/{grant_id}/messages'
    api_params = {'thread_id': thread_id, 'limit': 50}

    response = requests.get(url, headers=headers, params=api_params)
    if response.status_code != 200:
        return {'status': 'error', 'message': response.text}

    messages = response.json().get('data', [])
    result_messages = []

    for msg in messages:
        clean_body = clean_email_content(msg.get('body', '') or msg.get('snippet', ''))
        result_messages.append({
            'message_id': msg.get('id'),
            'thread_id': thread_id,
            'subject': msg.get('subject', ''),
            'sender': msg.get('from', [{}])[0].get('email', ''),
            'sender_name': msg.get('from', [{}])[0].get('name', ''),
            'date': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(msg.get('date', 0))),
            'body': clean_body
        })

    return {'status': 'success', 'thread_id': thread_id, 'messages': result_messages, 'count': len(result_messages)}


# =============================================================================
# ACTION 3: read_message
# =============================================================================

def read_message(params):
    """Get single message content.

    Required: message_id
    """
    message_id = params.get('message_id')
    if not message_id:
        return {'status': 'error', 'message': 'Missing message_id parameter'}

    grant_id, access_token = get_nylas_creds()
    url = f'https://api.us.nylas.com/v3/grants/{grant_id}/messages/{message_id}'
    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return {'status': 'error', 'message': response.text}

    msg = response.json().get('data', {})
    clean_body = clean_email_content(msg.get('body', '') or msg.get('snippet', ''))

    return {
        'status': 'success',
        'message_id': msg.get('id'),
        'thread_id': msg.get('thread_id'),
        'subject': msg.get('subject', ''),
        'sender': msg.get('from', [{}])[0].get('email', ''),
        'sender_name': msg.get('from', [{}])[0].get('name', ''),
        'date': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(msg.get('date', 0))),
        'body': clean_body,
        'body_raw': msg.get('body', '')
    }


# =============================================================================
# ACTION 4: send_email
# =============================================================================

def send_email(params):
    """Send a new email.

    Required: to, subject, body
    Optional: cc, bcc, reply_to, schedule_at
    """
    to = params.get('to')
    subject = params.get('subject')
    body = params.get('body')
    cc = params.get('cc')
    bcc = params.get('bcc')
    reply_to = params.get('reply_to')
    schedule_at = params.get('schedule_at')

    if not all([to, subject, body]):
        return {'status': 'error', 'message': 'Missing required parameters: to, subject, body'}

    grant_id, access_token = get_nylas_creds()
    url = f'https://api.us.nylas.com/v3/grants/{grant_id}/messages/send'
    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}

    # Auto-detect if body is already HTML
    is_html = body.strip().lower().startswith(('<!doctype', '<html', '<body', '<div', '<p'))

    if not is_html:
        # Convert markdown-style to basic HTML
        import re
        formatted = body
        formatted = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', formatted)
        formatted = re.sub(r'\*(.+?)\*', r'<em>\1</em>', formatted)
        formatted = re.sub(r'\n', '<br>', formatted)
        html_body = f'''<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
{formatted}
</body>
</html>'''
    else:
        html_body = body

    payload = {
        'to': [{'email': to}],
        'subject': subject,
        'body': html_body,
        'content_type': 'text/html'
    }

    if cc:
        payload['cc'] = [{'email': cc}] if isinstance(cc, str) else [{'email': e} for e in cc]
    if bcc:
        payload['bcc'] = [{'email': bcc}] if isinstance(bcc, str) else [{'email': e} for e in bcc]
    if reply_to:
        payload['reply_to'] = [{'email': reply_to}]
    if schedule_at:
        payload['send_at'] = int(schedule_at)

    response = requests.post(url, headers=headers, json=payload)

    if response.status_code == 200:
        data = response.json().get('data', {})
        message_id = data.get('id')
        thread_id = data.get('thread_id')

        record_sent(message_id, thread_id, to, subject, body[:200], 'send')

        result = {
            'status': 'success',
            'message': 'Email sent successfully',
            'message_id': message_id,
            'thread_id': thread_id
        }
        if schedule_at:
            result['scheduled_at'] = datetime.fromtimestamp(int(schedule_at)).isoformat()
        return result
    else:
        return {'status': 'error', 'message': response.text}


# =============================================================================
# ACTION 5: reply
# =============================================================================

def reply(params):
    """Reply to existing thread.

    Required: message_id, body
    Optional: cc, bcc
    """
    message_id = params.get('message_id')
    body = params.get('body')
    cc = params.get('cc')
    bcc = params.get('bcc')

    if not message_id or not body:
        return {'status': 'error', 'message': 'Missing message_id or body parameters'}

    # Get original message
    msg_result = read_message({'message_id': message_id})
    if msg_result.get('status') != 'success':
        return {'status': 'error', 'message': 'Failed to fetch original message'}

    original_sender = msg_result.get('sender')
    original_subject = msg_result.get('subject')
    thread_id = msg_result.get('thread_id')

    reply_subject = original_subject if original_subject.startswith('Re:') else f'Re: {original_subject}'

    grant_id, access_token = get_nylas_creds()
    url = f'https://api.us.nylas.com/v3/grants/{grant_id}/messages/send'
    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}

    try:
        import markdown2
        html_body = markdown2.markdown(body.strip())
    except ImportError:
        html_body = body.replace('\n', '<br>')

    payload = {
        'to': [{'email': original_sender}],
        'subject': reply_subject,
        'body': html_body,
        'reply_to_message_id': message_id,
        'content_type': 'text/html'
    }

    if cc:
        payload['cc'] = [{'email': cc}] if isinstance(cc, str) else [{'email': e} for e in cc]
    if bcc:
        payload['bcc'] = [{'email': bcc}] if isinstance(bcc, str) else [{'email': e} for e in bcc]

    response = requests.post(url, headers=headers, json=payload)

    if response.status_code == 200:
        data = response.json().get('data', {})
        sent_message_id = data.get('id')

        record_sent(sent_message_id, thread_id, original_sender, reply_subject, body[:200], 'reply')

        return {
            'status': 'success',
            'message': 'Reply sent successfully',
            'message_id': sent_message_id,
            'thread_id': thread_id
        }
    else:
        return {'status': 'error', 'message': response.text}


# =============================================================================
# ACTION 6: search
# =============================================================================

def search(params):
    """Search emails via Nylas/Gmail query.

    Required: query
    Optional: limit (default 10)
    """
    query = params.get('query')
    limit = params.get('limit', 10)

    if not query:
        return {'status': 'error', 'message': 'Missing query parameter'}

    grant_id, access_token = get_nylas_creds()
    url = f'https://api.us.nylas.com/v3/grants/{grant_id}/messages'
    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}
    api_params = {'limit': limit, 'search_query_native': query}

    response = requests.get(url, headers=headers, params=api_params)
    if response.status_code != 200:
        return {'status': 'error', 'message': response.text}

    messages = response.json().get('data', [])
    results = []

    for msg in messages:
        clean_body = clean_email_content(msg.get('body', '') or msg.get('snippet', ''))
        results.append({
            'message_id': msg.get('id'),
            'thread_id': msg.get('thread_id'),
            'subject': msg.get('subject', ''),
            'sender': msg.get('from', [{}])[0].get('email', ''),
            'date': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(msg.get('date', 0))),
            'body': clean_body[:500] if clean_body else ''
        })

    return {'status': 'success', 'results': results, 'count': len(results), 'query': query}


# =============================================================================
# ACTION 7: search_local
# =============================================================================

def search_local(params):
    """Search cached emails in db.

    Required: query
    Optional: field (sender/subject/category), limit (default 50)
    """
    query = params.get('query')
    field = params.get('field')  # sender, subject, or category
    limit = params.get('limit', 50)

    if not query:
        return {'status': 'error', 'message': get_error_message('nylas_inbox', 'search_local', 'Missing query parameter')}

    conn = get_db()
    cursor = conn.cursor()

    search_term = f'%{query}%'

    if field == 'sender':
        cursor.execute('SELECT * FROM threads WHERE sender LIKE ? OR sender_name LIKE ? ORDER BY date DESC LIMIT ?',
                       (search_term, search_term, limit))
    elif field == 'subject':
        cursor.execute('SELECT * FROM threads WHERE subject LIKE ? ORDER BY date DESC LIMIT ?',
                       (search_term, limit))
    elif field == 'category':
        cursor.execute('SELECT * FROM threads WHERE category = ? ORDER BY date DESC LIMIT ?',
                       (query, limit))
    else:
        # Search all fields
        cursor.execute('''SELECT * FROM threads
                          WHERE subject LIKE ? OR sender LIKE ? OR sender_name LIKE ?
                          ORDER BY date DESC LIMIT ?''',
                       (search_term, search_term, search_term, limit))

    rows = cursor.fetchall()
    conn.close()

    results = [dict(row) for row in rows]
    return {
        'status': 'success',
        'message': get_success_message('nylas_inbox', 'search_local', {'count': len(results)}),
        'results': results,
        'count': len(results)
    }


# =============================================================================
# ACTION 8: archive
# =============================================================================

def archive(params):
    """Archive a thread.

    Required: thread_id
    """
    thread_id = params.get('thread_id')
    if not thread_id:
        return {'status': 'error', 'message': 'Missing thread_id parameter'}

    grant_id, access_token = get_nylas_creds()
    url = f'https://api.us.nylas.com/v3/grants/{grant_id}/threads/{thread_id}'
    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}

    # Remove from INBOX (Gmail's archive behavior)
    payload = {'remove_folders': ['INBOX']}

    response = requests.put(url, headers=headers, json=payload)

    if response.status_code == 200:
        update_thread_status(thread_id, 'archived')
        return {'status': 'success', 'message': 'Thread archived', 'thread_id': thread_id}
    else:
        return {'status': 'error', 'message': response.text}


# =============================================================================
# ACTION 9: unarchive
# =============================================================================

def unarchive(params):
    """Restore thread to inbox.

    Required: thread_id
    """
    thread_id = params.get('thread_id')
    if not thread_id:
        return {'status': 'error', 'message': 'Missing thread_id parameter'}

    grant_id, access_token = get_nylas_creds()
    url = f'https://api.us.nylas.com/v3/grants/{grant_id}/threads/{thread_id}'
    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}

    # Add back to INBOX
    payload = {'folders': ['INBOX']}

    response = requests.put(url, headers=headers, json=payload)

    if response.status_code == 200:
        update_thread_status(thread_id, 'active')
        return {'status': 'success', 'message': 'Thread restored to inbox', 'thread_id': thread_id}
    else:
        return {'status': 'error', 'message': response.text}


# =============================================================================
# ACTION 10: delete
# =============================================================================

def delete(params):
    """Permanently delete thread/message.

    Required: thread_id or message_id
    """
    thread_id = params.get('thread_id')
    message_id = params.get('message_id')

    if not thread_id and not message_id:
        return {'status': 'error', 'message': 'Missing thread_id or message_id parameter'}

    grant_id, access_token = get_nylas_creds()
    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}

    if thread_id:
        url = f'https://api.us.nylas.com/v3/grants/{grant_id}/threads/{thread_id}'
    else:
        url = f'https://api.us.nylas.com/v3/grants/{grant_id}/messages/{message_id}'

    response = requests.delete(url, headers=headers)

    if response.status_code in [200, 204]:
        if thread_id:
            update_thread_status(thread_id, 'deleted')
        return {'status': 'success', 'message': 'Deleted successfully'}
    else:
        return {'status': 'error', 'message': response.text}


# =============================================================================
# ACTION 11: label
# =============================================================================

def label(params):
    """Apply category/label to thread.

    Required: thread_id, category
    """
    thread_id = params.get('thread_id')
    category = params.get('category')

    if not thread_id or not category:
        return {'status': 'error', 'message': 'Missing thread_id or category parameter'}

    update_thread_category(thread_id, category)
    return {'status': 'success', 'message': f'Thread labeled as {category}', 'thread_id': thread_id, 'category': category}


# =============================================================================
# ACTION 12: batch_archive
# =============================================================================

def batch_archive(params):
    """Archive multiple threads.

    Required: thread_ids (list)
    """
    thread_ids = params.get('thread_ids', [])

    if not thread_ids:
        return {'status': 'error', 'message': 'Missing thread_ids parameter'}

    success = []
    errors = []

    for tid in thread_ids:
        result = archive({'thread_id': tid})
        if result.get('status') == 'success':
            success.append(tid)
        else:
            errors.append({'thread_id': tid, 'error': result.get('message')})

    return {
        'status': 'success',
        'archived': success,
        'errors': errors if errors else None,
        'archived_count': len(success)
    }


# =============================================================================
# ACTION 13: batch_label
# =============================================================================

def batch_label(params):
    """Label multiple threads.

    Required: thread_ids (list), category
    """
    thread_ids = params.get('thread_ids', [])
    category = params.get('category')

    if not thread_ids or not category:
        return {'status': 'error', 'message': 'Missing thread_ids or category parameter'}

    for tid in thread_ids:
        update_thread_category(tid, category)

    return {
        'status': 'success',
        'message': f'{len(thread_ids)} threads labeled as {category}',
        'category': category
    }


# =============================================================================
# ACTION 14: sync
# =============================================================================

def sync(params):
    """Sync inbox from Nylas API to local db.

    Optional: limit (default 100), force_full (default False)
    """
    limit = params.get('limit', 100)
    force_full = params.get('force_full', False)

    grant_id, access_token = get_nylas_creds()
    url = f'https://api.us.nylas.com/v3/grants/{grant_id}/messages'
    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}

    all_messages = []
    page_token = None
    pages_fetched = 0

    while len(all_messages) < limit:
        api_params = {'limit': min(50, limit - len(all_messages)), 'in': 'INBOX'}
        if page_token:
            api_params['page_token'] = page_token

        response = requests.get(url, headers=headers, params=api_params)
        if response.status_code != 200:
            return {'status': 'error', 'message': response.text}

        data = response.json()
        messages = data.get('data', [])
        all_messages.extend(messages)
        pages_fetched += 1

        page_token = data.get('next_cursor')
        if not page_token or not messages:
            break

    # Store to db
    threads_added = 0
    messages_added = 0

    for msg in all_messages:
        thread_id = msg.get('thread_id')
        message_id = msg.get('id')

        # Add thread
        add_thread(
            thread_id=thread_id,
            subject=msg.get('subject', ''),
            sender=msg.get('from', [{}])[0].get('email', ''),
            sender_name=msg.get('from', [{}])[0].get('name', ''),
            date=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(msg.get('date', 0))),
            snippet=msg.get('snippet', '')[:200] if msg.get('snippet') else None
        )
        threads_added += 1

        # Add message
        clean_body = clean_email_content(msg.get('body', '') or msg.get('snippet', ''))
        add_message(
            message_id=message_id,
            thread_id=thread_id,
            subject=msg.get('subject', ''),
            sender=msg.get('from', [{}])[0].get('email', ''),
            sender_name=msg.get('from', [{}])[0].get('name', ''),
            recipients=json.dumps(msg.get('to', [])),
            date=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(msg.get('date', 0))),
            body=clean_body,
            body_raw=msg.get('body', '')
        )
        messages_added += 1

    return {
        'status': 'success',
        'message': f'Synced {messages_added} messages across {threads_added} threads',
        'pages_fetched': pages_fetched,
        'messages_synced': messages_added
    }


# =============================================================================
# ACTION 15: get_stats
# =============================================================================

def get_stats(params=None):
    """Get inbox statistics."""
    conn = get_db()
    cursor = conn.cursor()

    stats = {}

    # Total threads by status
    cursor.execute('SELECT status, COUNT(*) as count FROM threads GROUP BY status')
    for row in cursor.fetchall():
        stats[f'threads_{row["status"]}'] = row['count']

    # Total threads by category
    cursor.execute('SELECT category, COUNT(*) as count FROM threads WHERE category IS NOT NULL GROUP BY category')
    categories = {}
    for row in cursor.fetchall():
        categories[row['category'] or 'uncategorized'] = row['count']
    stats['by_category'] = categories

    # Total messages
    cursor.execute('SELECT COUNT(*) as count FROM messages')
    stats['total_messages'] = cursor.fetchone()['count']

    # Total sent
    cursor.execute('SELECT COUNT(*) as count FROM sent_emails')
    stats['total_sent'] = cursor.fetchone()['count']

    # Unread threads
    cursor.execute('SELECT COUNT(*) as count FROM threads WHERE unread = 1 AND status = "active"')
    unread_count = cursor.fetchone()['count']
    stats['unread_threads'] = unread_count

    conn.close()

    # Get total for message template
    total_count = stats.get('total_messages', 0)

    return {
        'status': 'success',
        'message': get_success_message('nylas_inbox', 'get_stats', {'unread': unread_count, 'total': total_count}),
        'stats': stats
    }


# =============================================================================
# ACTION 16: list_attachments
# =============================================================================

def list_attachments(params):
    """List attachments for a message.

    Required: message_id
    """
    message_id = params.get('message_id')
    if not message_id:
        return {'status': 'error', 'message': 'Missing message_id parameter'}

    grant_id, access_token = get_nylas_creds()
    url = f'https://api.us.nylas.com/v3/grants/{grant_id}/messages/{message_id}'
    headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return {'status': 'error', 'message': response.text}

    msg = response.json().get('data', {})
    attachments = msg.get('attachments', [])

    result = []
    for att in attachments:
        attachment_info = {
            'attachment_id': att.get('id'),
            'filename': att.get('filename'),
            'content_type': att.get('content_type'),
            'size': att.get('size')
        }
        result.append(attachment_info)

        # Store in db
        add_attachment_record(
            att.get('id'), message_id, att.get('filename'),
            att.get('content_type'), att.get('size')
        )

    return {'status': 'success', 'attachments': result, 'count': len(result)}


# =============================================================================
# ACTION 17: download_attachment
# =============================================================================

def download_attachment(params):
    """Download attachment to local path.

    Required: attachment_id, message_id
    Optional: output_path
    """
    attachment_id = params.get('attachment_id')
    message_id = params.get('message_id')
    output_path = params.get('output_path')

    if not attachment_id or not message_id:
        return {'status': 'error', 'message': 'Missing attachment_id or message_id parameter'}

    grant_id, access_token = get_nylas_creds()
    url = f'https://api.us.nylas.com/v3/grants/{grant_id}/attachments/{attachment_id}/download'
    headers = {'Authorization': f'Bearer {access_token}'}
    api_params = {'message_id': message_id}

    response = requests.get(url, headers=headers, params=api_params)
    if response.status_code != 200:
        return {'status': 'error', 'message': response.text}

    # Determine output path
    if not output_path:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        attachments_dir = os.path.join(base_dir, 'data', 'attachments')
        os.makedirs(attachments_dir, exist_ok=True)

        # Get filename from db or use attachment_id
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT filename FROM attachments WHERE attachment_id = ?', (attachment_id,))
        row = cursor.fetchone()
        conn.close()

        filename = row['filename'] if row else f'{attachment_id}.bin'
        output_path = os.path.join(attachments_dir, filename)

    # Write file
    with open(output_path, 'wb') as f:
        f.write(response.content)

    # Update db
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE attachments SET saved_path = ? WHERE attachment_id = ?', (output_path, attachment_id))
    conn.commit()
    conn.close()

    return {
        'status': 'success',
        'message': 'Attachment downloaded',
        'path': output_path,
        'size': len(response.content)
    }


# =============================================================================
# MAIN
# =============================================================================

def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if args.action == 'list_threads':
        result = list_threads(params)
    elif args.action == 'read_thread':
        result = read_thread(params)
    elif args.action == 'read_message':
        result = read_message(params)
    elif args.action == 'send_email':
        result = send_email(params)
    elif args.action == 'reply':
        result = reply(params)
    elif args.action == 'search':
        result = search(params)
    elif args.action == 'search_local':
        result = search_local(params)
    elif args.action == 'archive':
        result = archive(params)
    elif args.action == 'unarchive':
        result = unarchive(params)
    elif args.action == 'delete':
        result = delete(params)
    elif args.action == 'label':
        result = label(params)
    elif args.action == 'batch_archive':
        result = batch_archive(params)
    elif args.action == 'batch_label':
        result = batch_label(params)
    elif args.action == 'sync':
        result = sync(params)
    elif args.action == 'get_stats':
        result = get_stats(params)
    elif args.action == 'list_attachments':
        result = list_attachments(params)
    elif args.action == 'download_attachment':
        result = download_attachment(params)
    else:
        result = {'status': 'error', 'message': f'Unknown action: {args.action}'}

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
