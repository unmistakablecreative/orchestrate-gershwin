#!/usr/bin/env python3
"""
Media Manager

Auto-refactored by refactorize.py to match gold standard structure.
"""

import sys
import json
import os
import subprocess

from PIL import Image
import yt_dlp
import onnxruntime


def convert_media(filename):
    input_path = os.path.join('media_raw', filename)
    output_path = os.path.join('media_converted', os.path.splitext(filename
        )[0] + '.mp4')
    os.makedirs('media_converted', exist_ok=True)
    subprocess.run(['ffmpeg', '-i', input_path, output_path], check=True)
    return {'status': 'success', 'message':
        f'Converted {input_path} to {output_path}'}


def remove_background(filename):
    from rembg import remove
    input_path = os.path.join('images_raw', filename)
    output_path = os.path.join('images_cutout', filename)
    os.makedirs('images_cutout', exist_ok=True)
    with open(input_path, 'rb') as i:
        input_data = i.read()
    output_data = remove(input_data)
    with open(output_path, 'wb') as o:
        o.write(output_data)
    return {'status': 'success', 'message':
        f'Removed background from {input_path}'}


def download_youtube(url):
    os.makedirs('youtube_downloads', exist_ok=True)
    output_path = os.path.join('youtube_downloads', '%(title)s.%(ext)s')
    opts = {'outtmpl': output_path, 'merge_output_format': 'mp4'}
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    return {'status': 'success', 'message':
        f'Downloaded YouTube content from {url}'}


def resize_image(filename, width, height):
    input_path = os.path.join('images_raw', filename)
    output_path = os.path.join('images_resized', filename)
    os.makedirs('images_resized', exist_ok=True)
    img = Image.open(input_path)
    resized = img.resize((int(width), int(height)))
    resized.save(output_path)
    return {'status': 'success', 'message':
        f'Resized image to {width}x{height}'}


def compress_image(filename):
    input_path = os.path.join('images_raw', filename)
    output_path = os.path.join('images_compressed', filename)
    os.makedirs('images_compressed', exist_ok=True)
    img = Image.open(input_path)
    img.save(output_path, optimize=True, quality=70)
    return {'status': 'success', 'message':
        f'Compressed image saved to {output_path}'}


def convert_file(filename, from_format, to_format):
    import csv, json, os
    input_dirs = {'txt': 'text_raw', 'md': 'text_raw', 'csv': 'data_raw',
        'json': 'data_raw', 'docx': 'text_raw', 'pdf': 'text_raw'}
    output_dirs = {'txt': 'text_converted', 'md': 'text_converted', 'csv':
        'data_converted', 'json': 'data_converted'}
    in_path = os.path.join(input_dirs[from_format], filename)
    base_name = os.path.splitext(filename)[0]
    out_filename = base_name + '.' + to_format
    out_path = os.path.join(output_dirs[to_format], out_filename)
    os.makedirs(output_dirs[to_format], exist_ok=True)
    if from_format == 'txt' and to_format == 'md':
        with open(in_path, 'r') as f:
            content = f.read()
        with open(out_path, 'w') as f:
            f.write(content)
    elif from_format == 'csv' and to_format == 'json':
        with open(in_path, newline='') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        with open(out_path, 'w') as f:
            json.dump(rows, f, indent=2)
    elif from_format == 'json' and to_format == 'csv':
        with open(in_path) as f:
            data = json.load(f)
        with open(out_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=data[0].keys())
            writer.writeheader()
            writer.writerows(data)
    elif from_format == 'docx' and to_format == 'txt':
        from docx import Document
        doc = Document(in_path)
        text = '\n'.join([p.text for p in doc.paragraphs])
        with open(out_path, 'w') as f:
            f.write(text)
    elif from_format == 'pdf' and to_format in ['txt', 'md']:
        import pdfplumber
        with pdfplumber.open(in_path) as pdf:
            text = '\n'.join(page.extract_text() or '' for page in pdf.pages)
        with open(out_path, 'w') as f:
            f.write(text)
    else:
        return {'status': 'error', 'message':
            f'Conversion {from_format} → {to_format} not supported'}
    return {'status': 'success', 'message': f'Converted to {out_path}'}


def main():
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument('action')
    parser.add_argument('--params')
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if args.action == 'compress_image':
        result = compress_image(**params)
    elif args.action == 'convert_file':
        result = convert_file(**params)
    elif args.action == 'convert_media':
        result = convert_media(**params)
    elif args.action == 'download_youtube':
        result = download_youtube(**params)
    elif args.action == 'remove_background':
        result = remove_background(**params)
    elif args.action == 'resize_image':
        result = resize_image(**params)
    else:
        result = {'status': 'error', 'message': f'Unknown action {args.action}'}

    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()