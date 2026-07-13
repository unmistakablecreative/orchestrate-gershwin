import requests
import json
import argparse
import os
import time
import re
import subprocess
from PIL import Image
# Full docstrings and function descriptions: data/orchestrate_docstrings.json

CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "credentials.json")
IDEOGRAM_URL = "https://api.ideogram.ai/generate"

def load_api_key():
    if os.path.exists(CREDENTIALS_FILE):
        with open(CREDENTIALS_FILE, "r") as f:
            creds = json.load(f)
        return creds.get("ideogram_api_key")
    return None

def slugify(text):
    slug = re.sub(r'[^a-z0-9\s]+', '', text.lower())
    slug = re.sub(r'\s+', '_', slug.strip())
    return slug[:30]

def generate_image_shell(prompt, filename, save_dir):
    script_path = os.path.join(os.path.dirname(__file__), "ideogram_generate.sh")

    if not os.path.exists(script_path):
        return False, "Shell script not found"

    try:
        result = subprocess.run([
            script_path, prompt, filename, save_dir
        ], capture_output=True, text=True, timeout=30)

        if result.returncode == 0:
            return True, result.stdout.strip()
        else:
            return False, result.stderr.strip() or result.stdout.strip()

    except subprocess.TimeoutExpired:
        return False, "Generation timeout"
    except Exception as e:
        return False, f"Shell execution error: {str(e)}"

def generate(params):
    prompt = params.get("prompt") or params.get("input", "")
    if not prompt:
        return {"status": "error", "message": "Missing 'prompt' parameter"}

    # Support output_path param (full path) or fallback to save_dir + filename
    output_path = params.get("output_path")
    if output_path:
        save_dir = os.path.dirname(output_path)
        filename = os.path.basename(output_path)
    else:
        slug = prompt.lower().strip().replace(" ", "_")[:40]
        slug = "".join(c for c in slug if c.isalnum() or c in "_-")
        ts = int(time.time())
        filename = params.get("filename", f"{slug}_{ts}.png")
        save_dir = params.get("save_dir", "/Users/srinivas/Orchestrate Github/orchestrate-jarvis/semantic_memory/images/")

    # Ensure directory exists
    os.makedirs(save_dir, exist_ok=True)

    success, message = generate_image_shell(prompt, filename, save_dir)

    if success:
        save_path = os.path.join(save_dir, filename)

        # Create thumbnail (400px wide)
        thumb_path = None
        try:
            base, ext = os.path.splitext(save_path)
            thumb_path = f"{base}_thumb{ext}"
            with Image.open(save_path) as img:
                ratio = 400 / img.width
                thumb_height = int(img.height * ratio)
                thumb = img.resize((400, thumb_height), Image.LANCZOS)
                thumb.save(thumb_path, quality=85, optimize=True)
        except Exception as e:
            thumb_path = None

        response = {
            "status": "success",
            "saved_to": save_path,
            "filename": filename,
            "prompt": prompt,
            "message": message
        }
        if thumb_path:
            response["thumb_path"] = thumb_path
        return response
    else:
        return {
            "status": "error",
            "message": f"Generation failed: {message}"
        }

def generate_batch(params):

    campaign_id = params.get("campaign_id")
    if not campaign_id:
        return {
            "status": "error",
            "message": "REQUIRED: campaign_id parameter. This controls ALL filenames. Pattern: {campaign_id}_001.png"
        }

    campaign_id = re.sub(r'[^a-z0-9_-]', '', campaign_id.lower().replace(' ', '-'))
    if not campaign_id:
        return {"status": "error", "message": "campaign_id must contain alphanumeric characters"}

    save_dir = "/Users/srinivas/Orchestrate Github/orchestrate-jarvis/semantic_memory/images/"
    os.makedirs(save_dir, exist_ok=True)

    if "filename" in params:
        filename = params.get("filename")

        if filename and not filename.startswith("/"):
            batch_dir = "/Users/srinivas/Orchestrate Github/orchestrate-jarvis/data/image_batches/"
            filename = os.path.join(batch_dir, filename)

        if not filename:
            return {"status": "error", "message": "Missing batch filename"}

        if not os.path.exists(filename):
            return {
                "status": "already_generated",
                "message": f"BATCH FILE MISSING: Already generated and deleted to prevent duplicates.",
                "hint": "Batch files are deleted after generation. Do not regenerate old batches."
            }

        with open(filename, "r", encoding="utf-8") as f:
            batch = json.load(f)

        prompts = batch.get("prompts", [])
        batch_id = batch.get("batch_id", f"batch_{int(time.time())}")

        if not campaign_id:
            campaign_id = batch.get("campaign_id")
            if campaign_id:
                campaign_id = re.sub(r'[^a-z0-9_-]', '', campaign_id.lower().replace(' ', '-'))
    else:
        prompts = params.get("prompts", [])
        batch_id = f"batch_{int(time.time())}"

        batch_dir = "/Users/srinivas/Orchestrate Github/orchestrate-jarvis/data/image_batches/"
        os.makedirs(batch_dir, exist_ok=True)
        filename = os.path.join(batch_dir, f"{batch_id}.json")

        batch_data = {
            "batch_id": batch_id,
            "prompts": prompts,
            "campaign_id": campaign_id
        }
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(batch_data, f, indent=2)

    if not prompts:
        return {"status": "error", "message": "No prompts found in batch file or params"}

    script_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(script_dir, "ideogram_batch.sh")

    if not os.path.exists(script_path):
        return {"status": "error", "message": "Batch script not found"}

    cmd = [script_path, filename, save_dir, campaign_id]

    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
    except Exception as e:
        return {"status": "error", "message": f"Failed to start batch: {str(e)}"}

    return {
        "status": "started",
        "message": f"Batch generation started for {len(prompts)} images",
        "batch_id": batch_id,
        "total": len(prompts),
        "directory": save_dir,
        "campaign_id": campaign_id,
        "filename_pattern": f"{campaign_id}_001.png, {campaign_id}_002.png, ...",
        "method": "shell_parallel"
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action")
    parser.add_argument("--params", type=str)
    args = parser.parse_args()
    params = json.loads(args.params) if args.params else {}

    if args.action == "generate":
        result = generate(params)
    elif args.action == "generate_batch":
        result = generate_batch(params)
    else:
        result = {"status": "error", "message": f"Unknown action: {args.action}"}

    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()