import os
import re
import requests
import io
import urllib.parse
from PIL import Image, ImageDraw, ImageFont
import json
from datetime import datetime, timezone, timedelta

# --- CONFIGURATION ---
SCRAPE_DO_TOKEN = os.environ.get("SCRAPE_DO_TOKEN")
WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

if not all([WEBHOOK_URL, SCRAPE_DO_TOKEN]):
    print("Critical Error: Missing SCRAPE_DO_TOKEN or DISCORD_WEBHOOK_URL.")
    exit(1)

# --- IMAGE PROCESSING UTILITIES ---
def clean_text(text):
    return re.sub(r'\s+', ' ', text).strip() if text else ""

def get_wrapped_text(text, font, max_width):
    if not text: return []
    lines, words = [], text.split(' ')
    current_line = words[0]
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    for word in words[1:]:
        test = current_line + " " + word
        if draw.textbbox((0, 0), test, font=font)[2] <= max_width:
            current_line = test
        else:
            lines.append(current_line)
            current_line = word
    lines.append(current_line)
    return lines

def load_scalable_font(font_size, bold=False):
    if bold:
        font_paths = [
            "arialbd.ttf",                                                 # Windows
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",        # Ubuntu/Linux
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf", # Linux Alt
            "/System/Library/Fonts/Helvetica-Bold.ttf"                     # macOS
        ]
        fallback_url = "https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Bold.ttf"
    else:
        font_paths = [
            "arial.ttf",                                                      # Windows
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",               # Ubuntu/Linux
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", # Linux Alt
            "/System/Library/Fonts/Helvetica.ttc"                             # macOS
        ]
        fallback_url = "https://github.com/google/fonts/raw/main/apache/roboto/Roboto-Regular.ttf"

    for path in font_paths:
        try:
            return ImageFont.truetype(path, font_size)
        except IOError:
            continue

    try:
        font_res = requests.get(fallback_url, timeout=5)
        if font_res.status_code == 200:
            return ImageFont.truetype(io.BytesIO(font_res.content), font_size)
    except:
        pass

    return ImageFont.load_default()

def process_image(image_bytes, sub, score, title, body, gallery_label=None):
    """
    Processes both static images and multi-frame animated GIFs.
    Returns a tuple: (bytes_buffer, file_extension, mime_type)
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        width, height = img.size
        
        f_size = max(24, int(width / 35))
        font = load_scalable_font(f_size, bold=False)
        bold_font = load_scalable_font(f_size, bold=True)

        header_str = f"{sub} | {score:,} | {f'[{gallery_label}] | ' if gallery_label else ''}{clean_text(title)}"
        header_lines = get_wrapped_text(header_str, bold_font, width * 0.92)
        footer_lines = get_wrapped_text(clean_text(body), font, width * 0.92) if body else []

        temp_draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
        try:
            bbox = temp_draw.textbbox((0, 0), "Ag", font=font)
            line_h = bbox[3] - bbox[1]
        except:
            line_h = f_size

        total_step = line_h + int(line_h * 0.35)
        padding_vertical = int(f_size * 0.8)  
        x_margin = int(width * 0.04)          

        top_bar_h = (len(header_lines) * total_step) + (padding_vertical * 2)
        bottom_bar_h = (len(footer_lines) * total_step) + (padding_vertical * 2) if footer_lines else 0
        
        is_animated = getattr(img, "is_animated", False) and img.n_frames > 1

        if is_animated:
            processed_frames = []
            durations = []
            
            # Cap maximum frames to prevent extreme processing times or giant files
            max_frames = min(img.n_frames, 120) 

            for frame_idx in range(max_frames):
                img.seek(frame_idx)
                
                frame_canvas = img.convert("RGB")
                
                new_frame = Image.new("RGB", (width, height + top_bar_h + bottom_bar_h), (0, 0, 0))
                new_frame.paste(frame_canvas, (0, top_bar_h))
                draw = ImageDraw.Draw(new_frame)
                
                y = padding_vertical
                for line in header_lines:
                    draw.text((x_margin, y), line, font=bold_font, fill=(255, 255, 255))
                    y += total_step
                    
                if footer_lines:
                    y = height + top_bar_h + padding_vertical
                    for line in footer_lines:
                        draw.text((x_margin, y), line, font=font, fill=(210, 210, 210))
                        y += total_step
                
                processed_frames.append(new_frame)
                durations.append(img.info.get('duration', 100))

            buf = io.BytesIO()
            processed_frames[0].save(
                buf, 
                format="GIF", 
                save_all=True, 
                append_images=processed_frames[1:], 
                duration=durations, 
                loop=0
            )
            buf.seek(0)
            return buf, "gif", "image/gif"

        else:
            img_clean = img.convert("RGB")
            new_img = Image.new("RGB", (width, height + top_bar_h + bottom_bar_h), (0, 0, 0))
            new_img.paste(img_clean, (0, top_bar_h))
            draw = ImageDraw.Draw(new_img)
            
            y = padding_vertical
            for line in header_lines:
                draw.text((x_margin, y), line, font=bold_font, fill=(255, 255, 255))
                y += total_step
                
            if footer_lines:
                y = height + top_bar_h + padding_vertical
                for line in footer_lines:
                    draw.text((x_margin, y), line, font=font, fill=(210, 210, 210))
                    y += total_step
                
            buf = io.BytesIO()
            new_img.save(buf, format="JPEG", quality=85)
            buf.seek(0)
            return buf, "jpg", "image/jpeg"

    except Exception as e:
        print(f"Error processing image asset: {e}")
        return None

def extract_urls(post_data):
    urls = []
    if post_data.get('is_gallery'):
        items = post_data.get('gallery_data', {}).get('items', [])
        for item in items:
            m_id = item.get('media_id')
            meta = post_data.get('media_metadata', {}).get(m_id)
            if meta and meta.get('e') == 'Image':
                url = meta.get('s', {}).get('u')
                if url: urls.append(url.replace('&amp;', '&'))
    else:
        url = post_data.get('url', '')
        if any(url.lower().endswith(ext) for ext in ['.jpg', '.png', '.jpeg', '.gif']):
            urls.append(url)
    return urls

# --- MAIN EXECUTION ---
def main():
    config_path = "config.json"
    if not os.path.exists(config_path):
        print(f"Critical Error: '{config_path}' file not found in the root workspace.")
        return
        
    with open(config_path, "r") as f:
        subreddit_schedule = json.load(f)

    ist_timezone = timezone(timedelta(hours=5, minutes=30))
    current_ist_time = datetime.now(ist_timezone)
    current_day = current_ist_time.strftime("%A")
    
    today_config = subreddit_schedule.get(current_day, {})
    
    target_subs = today_config.get("subreddits", [])
    threshold = today_config.get("threshold", 2000)
    
    print(f"Execution Time (IST): {current_ist_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Today is {current_day}.")
    print(f"Target Subreddits: {target_subs}")
    print(f"Minimum Upvote Threshold: {threshold:,}")

    if not target_subs:
        print(f"No subreddits configured for {current_day}. Exiting pipeline.")
        return
    
    sub_links = ", ".join([f"r/{sub}" for sub in target_subs])
    status_content = (
        f"**Starting Harvest for {current_day} (IST)**\n"
        f"**Targeting:** {sub_links}\n"
        f"**Minimum Threshold:** `{threshold:,}` upvotes\n"
        f"---"
    )
    try:
        requests.post(WEBHOOK_URL, json={"content": status_content})
    except Exception as e:
        print(f"Failed to send status text to Discord Webhook: {e}")

    all_files = []

    for sub in target_subs:
        target_reddit_url = f"https://www.reddit.com/r/{sub}/top/.json?t=week&limit=30"
        encoded_url = urllib.parse.quote_plus(target_reddit_url)
        proxy_gateway = f"http://api.scrape.do?token={SCRAPE_DO_TOKEN}&url={encoded_url}"
        
        try:
            print(f"Requesting r/{sub} via Scrape.do Proxy...")
            response = requests.get(proxy_gateway, timeout=20)
            response.raise_for_status() 
            
            posts = response.json().get('data', {}).get('children', [])
            print(f" Successfully fetched data for r/{sub}!")
            
            for post in posts:
                p = post['data']
                if p['score'] >= threshold:
                    urls = extract_urls(p)
                    for idx, img_url in enumerate(urls, 1):
                        res = requests.get(img_url)
                        if res.status_code == 200:
                            label = f"{idx} of {len(urls)}" if len(urls) > 1 else None
                            result = process_image(res.content, p['subreddit'], p['score'], p['title'], p.get('selftext', ""), label)
                            
                            if result:
                                img_buf, ext, mime_type = result
                                filename = f"img_{p['id']}_{idx}.{ext}"
                                all_files.append((filename, img_buf.read(), mime_type))
                                
        except Exception as e:
            print(f"Proxy failed on r/{sub}: {e}")

    if all_files:
        print(f"Found {len(all_files)} total assets matching today's criteria. Uploading to Discord...")
        for i in range(0, len(all_files), 9):
            batch = all_files[i : i + 9]
            files_payload = {}
            for index, (fname, fbytes, mime) in enumerate(batch):
                files_payload[f"file{index}"] = (fname, fbytes, mime)
                
            requests.post(WEBHOOK_URL, files=files_payload)
        print("✅ Delivery finished!")
    else:
        print(f"No posts in today's subreddits crossed the required score of {threshold:,}.")

if __name__ == "__main__":
    main()
