#!/usr/bin/env python3
"""
Nylasinbox

Auto-refactored by refactorize.py to match gold standard structure.
"""

import sys
import json
import os

import time
import requests
import markdown2


CREDENTIALS_PATH = os.path.join(os.path.dirname(__file__), 'credentials.json')
GRANT_ID = creds['grant_id']
ACCESS_TOKEN = creds['access_token']
FOLDER_ID = creds.get('archive_folder_id', 'Label_4287')


def check_email(page_token=None):
    url = f'https://api.us.nylas.com/v3/grants/{GRANT_ID}/messages'
    headers = {'Authorization': f'Bearer {ACCESS_TOKEN}', 'Content-Type': 'application/json'}
    params = {'limit': 50, 'in': 'INBOX'}
    if page_token:
        params['page_token'] = page_token

    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        return {'status': 'error', 'message': response.text}

    messages = response.json().get('data', [])
    results = []
    for msg in messages:
        results.append({
            'id': msg.get('id'),
            'from': msg.get('from', [{}])[0].get('email', ''),
            'subject': msg.get('subject', ''),
            'date': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(msg.get('date', 0)))
        })
    return {'status': 'success', 'data': results, 'next_cursor': response.json().get('next_cursor')}


def send_email(to, subject, body, is_html=False):
    url = f'https://api.us.nylas.com/v3/grants/{GRANT_ID}/messages/send'
    headers = {'Authorization': f'Bearer {ACCESS_TOKEN}', 'Content-Type': 'application/json'}
    if not is_html:
        body = markdown2.markdown(body.strip())
    payload = {
        'to': [{'email': to}],
        'subject': subject,
        'body': body,
        'content_type': 'text/html'
    }
    response = requests.post(url, headers=headers, json=payload)
    return {'status': 'success' if response.status_code == 200 else 'error', 'data': response.json()}


def open_message(message_id):
    url = f'https://api.us.nylas.com/v3/grants/{GRANT_ID}/messages/{message_id}'
    headers = {'Authorization': f'Bearer {ACCESS_TOKEN}', 'Content-Type': 'application/json'}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return {'status': 'error', 'message': response.text}
    body = response.json().get('data', {}).get('body')
    return {'status': 'success', 'data': body or 'No message body returned.'}


def search_messages(subject=None, from_email=None):
    url = f'https://api.us.nylas.com/v3/grants/{GRANT_ID}/messages'
    headers = {'Authorization': f'Bearer {ACCESS_TOKEN}', 'Content-Type': 'application/json'}
    params = {'limit': 40}
    if subject:
        params['subject'] = subject
    if from_email:
        params['from'] = from_email

    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        return {'status': 'error', 'message': response.text}

    messages = response.json().get('data', [])
    results = []
    for msg in messages:
        results.append({
            'id': msg.get('id'),
            'from': msg.get('from', [{}])[0].get('email', ''),
            'subject': msg.get('subject', ''),
            'date': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(msg.get('date', 0)))
        })
    return {'status': 'success', 'data': results}


def list_folders():
    url = f'https://api.us.nylas.com/v3/grants/{GRANT_ID}/folders'
    headers = {'Authorization': f'Bearer {ACCESS_TOKEN}', 'Content-Type': 'application/json'}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return {'status': 'error', 'message': response.text}
    folders = response.json().get('data', [])
    return {'status': 'success', 'data': [{'id': f.get('id'), 'name': f.get('name')} for f in folders]}


def create_folder(name):
    url = f'https://api.us.nylas.com/v3/grants/{GRANT_ID}/folders'
    headers = {'Authorization': f'Bearer {ACCESS_TOKEN}', 'Content-Type': 'application/json'}
    payload = {'name': name}
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    return {'status': 'success' if response.status_code == 200 else 'error', 'data': response.json()}


def archive_email(message_id):
    url = f'https://api.us.nylas.com/v3/grants/{GRANT_ID}/messages/{message_id}'
    headers = {'Authorization': f'Bearer {ACCESS_TOKEN}', 'Content-Type': 'application/json'}
    payload = {"folders": [FOLDER_ID], "unread": False}
    response = requests.put(url, headers=headers, data=json.dumps(payload))
    return {'status': 'success' if response.status_code == 200 else 'error', 'response_code': response.status_code, 'response_body': response.text}


def batch_archive_emails(message_ids):
    url_base = f'https://api.us.nylas.com/v3/grants/{GRANT_ID}/messages'
    headers = {'Authorization': f'Bearer {ACCESS_TOKEN}', 'Content-Type': 'application/json'}
    success_ids, error_ids = [], []
    for message_id in message_ids:
        url = f'{url_base}/{message_id}'
        payload = {"folders": [FOLDER_ID], "unread": False}
        response = requests.put(url, headers=headers, data=json.dumps(payload))
        (success_ids if response.status_code == 200 else error_ids).append(message_id)
    return {'status': 'success', 'archived': success_ids, 'failed': error_ids, 'count': len(message_ids)}


def main():
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if args.action == 'archive_email':
        result = archive_email(**params)
    elif args.action == 'batch_archive_emails':
        result = batch_archive_emails(**params)
    elif args.action == 'check_email':
        result = check_email(**params)
    elif args.action == 'create_folder':
        result = create_folder(**params)
    elif args.action == 'list_folders':
        result = list_folders()
    elif args.action == 'open_message':
        result = open_message(**params)
    elif args.action == 'search_messages':
        result = search_messages(**params)
    elif args.action == 'send_email':
        result = send_email(**params)
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()