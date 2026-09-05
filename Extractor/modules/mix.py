import asyncio
import aiohttp
import json
import os
import re
import time
import random
import logging
from datetime import datetime
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from base64 import b64decode
import base64
import pytz

from config import PREMIUM_LOGS, join, BOT_TEXT
import config

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

join = config.join
india_timezone = pytz.timezone('Asia/Kolkata')


def decrypt(enc):
    """Decrypt AES encrypted content."""
    try:
        if not enc:
            return ""
        enc = b64decode(enc.split(':')[0])
        key = '638udh3829162018'.encode('utf-8')
        iv = 'fedcba9876543210'.encode('utf-8')
        if len(enc) == 0:
            return ""
        cipher = AES.new(key, AES.MODE_CBC, iv)
        plaintext = unpad(cipher.decrypt(enc), AES.block_size)
        return plaintext.decode('utf-8')
    except Exception:
        return ""


def decode_base64(encoded_str):
    """Decode base64 encoded string."""
    try:
        decoded_bytes = base64.b64decode(encoded_str)
        return decoded_bytes.decode('utf-8')
    except Exception:
        return ""


async def safe_api_get(session, url, headers, semaphore, max_retries=5):
    """Safe API GET request with rate limiting semaphore and exponential backoff retry on HTTP 429/5xx."""
    for attempt in range(max_retries):
        try:
            async with semaphore:
                # Polite delay between requests to avoid burst rate-limits
                await asyncio.sleep(0.08)
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 429:
                        retry_after = response.headers.get("Retry-After")
                        if retry_after and retry_after.strip().isdigit():
                            wait_time = float(retry_after.strip())
                        else:
                            wait_time = min((2 ** (attempt + 1)) + random.uniform(0.5, 1.5), 15.0)
                        logger.warning(f"Rate limited (429) on {url}. Backing off for {wait_time:.1f}s (Attempt {attempt + 1}/{max_retries})")
                        await asyncio.sleep(wait_time)
                        continue

                    if response.status in (500, 502, 503, 504):
                        wait_time = min((2 ** attempt) + 1.0, 10.0)
                        logger.warning(f"Server error ({response.status}) on {url}. Retrying in {wait_time:.1f}s...")
                        await asyncio.sleep(wait_time)
                        continue

                    text = await response.text()
                    if not text or not text.strip():
                        return None

                    # Try standard JSON decoding
                    try:
                        return json.loads(text)
                    except Exception:
                        # Fallback: extract JSON substring if wrapped in HTML or text
                        match = re.search(r'\{.*\}', text, re.DOTALL)
                        if match:
                            try:
                                return json.loads(match.group(0))
                            except Exception:
                                pass
                        logger.error(f"Failed to parse JSON response (Status {response.status}) from {url}")
                        return None

        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            wait_time = min((2 ** attempt) + 1.0, 10.0)
            logger.warning(f"Network error on {url}: {e}. Retrying in {wait_time:.1f}s...")
            await asyncio.sleep(wait_time)
        except Exception as e:
            logger.error(f"Unexpected error fetching {url}: {e}")
            return None

    logger.error(f"Max retries exceeded for {url}")
    return None


def format_resource_line(title: str, url: str, key: str = "", res_type: str = ""):
    """Format resource line with appropriate emoji and clean title:url format."""
    title = (title or "Untitled").strip()
    url = (url or "").strip()
    key = (key or "").strip()
    if not url:
        return None

    # Determine icon based on explicit type or URL extension
    url_lower = url.lower()
    if res_type == "pdf" or ".pdf" in url_lower:
        icon = "📄"
    elif res_type == "image" or any(ext in url_lower for ext in ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg']):
        icon = "🖼️"
    elif res_type == "test" or "/test" in url_lower or "/quiz" in url_lower:
        icon = "📝"
    elif res_type == "video" or any(ext in url_lower for ext in ['.mp4', '.m3u8', '.mpd', '.mkv']) or "youtu" in url_lower:
        icon = "🎥"
    else:
        if "pdf" in title.lower() or "notes" in title.lower():
            icon = "📄"
        elif "image" in title.lower() or "photo" in title.lower():
            icon = "🖼️"
        elif "test" in title.lower() or "quiz" in title.lower():
            icon = "📝"
        else:
            icon = "🎥"

    # Clean existing icons from title to avoid duplication
    clean_title = title
    for existing_icon in ["🎥", "🎬", "📄", "📕", "🖼️", "🖼", "📝", "📁", "🔗"]:
        if clean_title.startswith(existing_icon):
            clean_title = clean_title[len(existing_icon):].strip()

    line_title = f"{icon} {clean_title}"
    if key:
        return f"{line_title}:{url}*{key}"
    return f"{line_title}:{url}"


async def fetch_item_details(session, api_base, course_id, item, headers, semaphore):
    """Fetch details for a single content item (video/pdf/image) with proper error handling and emojis."""
    material_type = str(item.get("material_type", "")).upper()

    # Never process folders as video details
    if material_type == "FOLDER":
        return []

    item_id = item.get("id")
    raw_title = item.get("Title", "Untitled")
    outputs = []

    try:
        # Handle direct PDF or TEST items
        if material_type in ("PDF", "TEST"):
            pdf_link = item.get("pdf_link", "")
            is_enc = item.get("is_pdf_encrypted", 0)
            pdf_key = item.get("pdf_encryption_key", "")

            if pdf_link:
                dp = decrypt(pdf_link)
                if dp:
                    key_val = ""
                    if is_enc and pdf_key:
                        dpk = decrypt(pdf_key)
                        if dpk and dpk != "abcdefg":
                            key_val = dpk
                    formatted = format_resource_line(raw_title, dp, key=key_val, res_type="pdf")
                    if formatted:
                        outputs.append(formatted)

            # Secondary PDF link
            pdf_link2 = item.get("pdf_link2", "")
            is_enc2 = item.get("is_pdf2_encrypted", 0)
            pdf_key2 = item.get("pdf2_encryption_key", "")

            if pdf_link2:
                dp2 = decrypt(pdf_link2)
                if dp2:
                    key_val2 = ""
                    if is_enc2 and pdf_key2:
                        dpk2 = decrypt(pdf_key2)
                        if dpk2 and dpk2 != "abcdefg":
                            key_val2 = dpk2
                    formatted2 = format_resource_line(f"{raw_title} (Part 2)", dp2, key=key_val2, res_type="pdf")
                    if formatted2:
                        outputs.append(formatted2)

            # If download_link is available and no link extracted yet
            if not outputs and item.get("download_link"):
                dp = decrypt(item.get("download_link"))
                if dp:
                    formatted = format_resource_line(raw_title, dp, res_type="pdf")
                    if formatted:
                        outputs.append(formatted)

            if outputs:
                return outputs

        # Handle direct IMAGE items
        if material_type == "IMAGE":
            img_url = item.get("thumbnail") or item.get("image") or item.get("image_url") or item.get("download_link")
            if img_url:
                formatted = format_resource_line(raw_title, img_url, res_type="image")
                if formatted:
                    outputs.append(formatted)
                    return outputs

        # Video / UHLS / YouTube details
        ytflag = item.get("ytFlag", 0)
        url = f"{api_base}/get/fetchVideoDetailsById?course_id={course_id}&folder_wise_course=1&ytflag={ytflag}&video_id={item_id}"
        r4 = await safe_api_get(session, url, headers, semaphore)

        if not r4 or not isinstance(r4, dict):
            return []

        data = r4.get("data")
        if not data or not isinstance(data, dict):
            return []

        vt = data.get("Title") or raw_title
        vl = data.get("download_link", "")
        vid_encrypted = data.get("video_id", "")

        # Check YouTube link
        if vid_encrypted:
            dfl = decrypt(vid_encrypted)
            if dfl:
                youtube_url = f"https://youtu.be/{dfl}"
                formatted = format_resource_line(vt, youtube_url, res_type="video")
                if formatted:
                    outputs.append(formatted)

        # Process main video download link
        if vl:
            dvl = decrypt(vl)
            if dvl:
                formatted = format_resource_line(vt, dvl)
                if formatted:
                    outputs.append(formatted)
        else:
            # Process encrypted links
            for link in data.get("encrypted_links", []):
                a = link.get("path")
                k = link.get("key")
                if a and k:
                    k1 = decrypt(k)
                    k2 = decode_base64(k1)
                    da = decrypt(a)
                    if da and k2:
                        formatted = format_resource_line(vt, da, key=k2, res_type="video")
                        if formatted:
                            outputs.append(formatted)
                        break
                elif a:
                    da = decrypt(a)
                    if da:
                        formatted = format_resource_line(vt, da, res_type="video")
                        if formatted:
                            outputs.append(formatted)
                        break

        # Fallback: Check DRM MPD links if video link still not found
        if not outputs:
            drm_url = f"{api_base}/get/get_mpd_drm_links?videoid={item_id}&folder_wise_course=1"
            drm_res = await safe_api_get(session, drm_url, headers, semaphore)
            if drm_res and isinstance(drm_res, dict) and "data" in drm_res:
                drm_data = drm_res.get("data", [])
                if isinstance(drm_data, list) and drm_data:
                    path = decrypt(drm_data[0].get("path", "")) if drm_data[0].get("path") else None
                    if path:
                        formatted = format_resource_line(vt, path, res_type="video")
                        if formatted:
                            outputs.append(formatted)

        # Process PDF notes attached to video
        for pdf_num in range(1, 4):
            suffix = "" if pdf_num == 1 else str(pdf_num)
            pdf_link = data.get(f"pdf_link{suffix}", "")
            pdf_key = data.get(f"pdf{'_' if pdf_num == 1 else str(pdf_num)}_encryption_key", "")

            if pdf_link:
                dp = decrypt(pdf_link)
                if dp:
                    pdf_title = f"{vt} (Notes {pdf_num})" if pdf_num > 1 else f"{vt} (Notes)"
                    key_val = ""
                    if pdf_key:
                        dpk = decrypt(pdf_key)
                        if dpk and dpk != "abcdefg":
                            key_val = dpk
                    formatted_pdf = format_resource_line(pdf_title, dp, key=key_val, res_type="pdf")
                    if formatted_pdf:
                        outputs.append(formatted_pdf)

        return outputs

    except Exception as e:
        logger.error(f"Error fetching item details for ID {item_id}: {e}")
        return []


async def fetch_folder_recursive(session, api_base, course_id, folder_id, folder_path, headers, semaphore, progress_state):
    """Recursively fetch contents of folders down to arbitrary depth, returning structured lines with folder headers."""
    url = f"{api_base}/get/folder_contentsv2?course_id={course_id}&parent_id={folder_id}"
    j = await safe_api_get(session, url, headers, semaphore)

    if not j or not isinstance(j, dict) or "data" not in j:
        return []

    data = j.get("data", [])
    if not isinstance(data, list):
        return []

    folder_items = []
    content_items = []

    for item in data:
        if item.get("material_type") == "FOLDER":
            folder_items.append(item)
        else:
            content_items.append(item)

    all_section_lines = []

    # Process content items for current folder level
    if content_items:
        tasks = [fetch_item_details(session, api_base, course_id, item, headers, semaphore) for item in content_items]
        item_results = await asyncio.gather(*tasks)

        current_folder_lines = []
        for res in item_results:
            if res:
                current_folder_lines.extend(res)

        if current_folder_lines:
            # Build folder header with breadcrumb
            breadcrumb = " » ".join(folder_path) if folder_path else "General"
            header = f"\n📁 {breadcrumb}\n" + "─" * min(max(len(breadcrumb) + 4, 30), 60)
            all_section_lines.append(header)
            all_section_lines.extend(current_folder_lines)

            # Update progress tracking
            progress_state["extracted_links"] += len(current_folder_lines)
            progress_state["folders_found"] += 1

            # Throttle progress message update (every ~3-4 seconds)
            current_clock = time.time()
            if current_clock - progress_state["last_edit_time"] > 3.5:
                progress_state["last_edit_time"] = current_clock
                try:
                    await progress_state["progress_msg"].edit_text(
                        "🔄 <b>Processing Course Folders</b>\n"
                        f"├─ Current: <code>{breadcrumb}</code>\n"
                        f"├─ Folders Processed: <b>{progress_state['folders_found']}</b>\n"
                        f"└─ Links Extracted: <b>{progress_state['extracted_links']}</b>"
                    )
                except Exception:
                    pass

    # Recursively process all subfolders
    for subfolder in folder_items:
        sub_title = (subfolder.get("Title") or f"Folder {subfolder.get('id', '')}").strip()
        sub_id = subfolder.get("id")
        new_path = folder_path + [sub_title]

        sub_lines = await fetch_folder_recursive(session, api_base, course_id, sub_id, new_path, headers, semaphore, progress_state)
        if sub_lines:
            all_section_lines.extend(sub_lines)

    return all_section_lines


async def v2_new(app, message, token, userid, hdr1, app_name, raw_text2, api_base, sanitized_course_name, start_time, start, end, pricing, input2, m1, m2):
    """Process and recursively extract course content with detailed folder hierarchy and emojis."""
    try:
        progress_msg = await message.reply_text(
            "🔄 <b>Initializing Course Extraction</b>\n"
            f"└─ Batch: <code>{sanitized_course_name}</code>\n"
            "⏳ <i>Recursively scanning all folders...</i>"
        )

        semaphore = asyncio.Semaphore(3)

        progress_state = {
            "progress_msg": progress_msg,
            "last_edit_time": time.time(),
            "extracted_links": 0,
            "folders_found": 0
        }

        async with aiohttp.ClientSession() as session:
            # Recursively fetch everything starting from root (parent_id = -1)
            all_lines = await fetch_folder_recursive(
                session, api_base, raw_text2, -1, [], hdr1, semaphore, progress_state
            )

            if not all_lines:
                await progress_msg.edit_text("❌ <b>No content found in this batch.</b>")
                return

            # Count link statistics (ignoring folder header lines)
            link_lines = [line for line in all_lines if ":" in line and not line.strip().startswith("📁") and not line.strip().startswith("─")]
            total_links = len(link_lines)

            video_count = sum(1 for line in link_lines if line.startswith("🎥") or any(ext in line.lower() for ext in ['.mp4', '.m3u8', '.mpd', 'youtu']))
            pdf_count = sum(1 for line in link_lines if line.startswith("📄") or '.pdf' in line.lower())
            image_count = sum(1 for line in link_lines if line.startswith("🖼️") or any(ext in line.lower() for ext in ['.png', '.jpg', '.jpeg', '.webp']))
            encrypted_count = sum(1 for line in link_lines if '*' in line)

            # Write formatted content to file with UTF-8 encoding
            file_name = f"{app_name}_{sanitized_course_name}_{int(datetime.now().timestamp())}.txt"
            with open(file_name, 'w', encoding='utf-8') as f:
                f.write('\n'.join(all_lines).strip() + '\n')

            # Calculate duration
            end_time = datetime.now()
            duration = end_time - datetime.fromtimestamp(start_time)
            minutes, seconds = divmod(duration.total_seconds(), 60)

            # Prepare caption
            caption = (
                f"🎓 <b>COURSE EXTRACTED</b> 🎓\n\n"
                f"📱 <b>APP:</b> {app_name}\n"
                f"📚 <b>BATCH:</b> {sanitized_course_name}\n"
                f"⏱ <b>EXTRACTION TIME:</b> {int(minutes):02d}:{int(seconds):02d}\n"
                f"📅 <b>DATE:</b> {datetime.now(india_timezone).strftime('%d-%m-%Y %I:%M:%S %p')} IST\n\n"
                f"📊 <b>CONTENT STATS</b>\n"
                f"├─ 📁 Folders: {progress_state['folders_found']}\n"
                f"├─ 🎬 Videos: {video_count}\n"
                f"├─ 📄 PDFs: {pdf_count}\n"
                f"├─ 🖼️ Images: {image_count}\n"
                f"├─ 🔐 Encrypted: {encrypted_count}\n"
                f"└─ 🔗 Total Links: {total_links}\n\n"
                f"🚀 <b>Extracted by:</b> @{(await app.get_me()).username}\n\n"
                f"<code>╾───• {BOT_TEXT} •───╼</code>"
            )

            # Send document to user and logs channel
            await message.reply_document(
                document=file_name,
                caption=caption
            )
            if PREMIUM_LOGS:
                try:
                    await app.send_document(PREMIUM_LOGS, file_name, caption=caption)
                except Exception as log_err:
                    logger.error(f"Failed to forward document to logs channel: {log_err}")

            # Cleanup local temporary file
            try:
                if os.path.exists(file_name):
                    os.remove(file_name)
            except Exception:
                pass

            # Delete temporary input/prompt messages if provided
            for msg in [input2, m1, m2]:
                if msg:
                    try:
                        await msg.delete()
                    except Exception:
                        pass

            await progress_msg.edit_text(
                "✅ <b>Extraction completed successfully!</b>\n\n"
                f"📊 <b>Final Status:</b>\n"
                f"📁 Folders: {progress_state['folders_found']}\n"
                f"🔗 Links Extracted: {total_links}\n"
                f"📤 File has been uploaded.\n\n"
                f"Thank you for using <b>{BOT_TEXT}</b>! 🌟"
            )

    except Exception as e:
        logger.error(f"Error in v2_new: {e}", exc_info=True)
        await message.reply_text(
            "❌ <b>An error occurred during extraction</b>\n\n"
            f"Error: <code>{str(e)}</code>\n\n"
            "Please try again or contact support."
        )
                              
