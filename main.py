import os
import shutil
import uuid
import asyncio
import platform
import json

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import yt_dlp
from pydantic import BaseModel

# تهيئة تطبيق FastAPI
app = FastAPI(
    title="Video Downloader Web App",
    description="تطبيق ويب بسيط لتنزيل الفيديوهات باستخدام FastAPI و yt-dlp.",
    version="1.0.0"
)

# دليل مؤقت للتنزيلات داخل مجلد المشروع
PROJECT_DOWNLOAD_DIR = "downloads"
# دليل الملفات الثابتة (لواجهة المستخدم HTML/CSS/JS)
STATIC_DIR = "static"
# اسم المجلد المخصص لتنزيل الفيديوهات داخله (في مجلد تنزيلات المستخدم)
APP_DOWNLOAD_FOLDER_NAME = "MyVideoDownloads"

# التأكد من وجود أدلة المشروع المؤقتة والملفات الثابتة
os.makedirs(PROJECT_DOWNLOAD_DIR, exist_ok=True)
os.makedirs(STATIC_DIR, exist_ok=True)

# تهيئة Jinja2Templates لخدمة ملفات HTML
templates = Jinja2Templates(directory=STATIC_DIR)

# خدمة الملفات الثابتة (مثل ملف index.html)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# قاموس لتخزين اتصالات WebSocket النشطة
active_websockets: dict[str, WebSocket] = {}

# منطق جلب معلومات الفيديو
def get_video_info_core(url: str) -> dict:
    print(f"Attempting to fetch info for URL: {url}")
    ydl_opts = {
        'quiet': False,
        'simulate': True,
        'force_generic_extractor': True,
        'skip_download': True,
        'allow_playlist_skiplinks': True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=False)
        print(f"Successfully fetched info for URL: {url}")

        available_formats_by_type = {
            "فيديو + صوت": {},
            "فيديو فقط": {},
            "صوت فقط": {}
        }

        for f in info_dict.get('formats', []):
            ext = f.get('ext')
            vcodec = f.get('vcodec')
            acodec = f.get('acodec')
            height = f.get('height')
            abr = f.get('abr')
            format_note = f.get('format_note')
            resolution_str = f.get('resolution')

            if not ext:
                continue

            display_quality = None
            if height:
                display_quality = height
            elif resolution_str and 'x' in resolution_str:
                try:
                    display_quality = int(resolution_str.split('x')[1])
                except ValueError:
                    pass
            elif format_note and 'p' in format_note:
                try:
                    display_quality = int(''.join(filter(str.isdigit, format_note)))
                except ValueError:
                    pass

            if vcodec != 'none' and display_quality:
                if display_quality not in available_formats_by_type["فيديو + صوت"]:
                    available_formats_by_type["فيديو + صوت"][display_quality] = []
                if ext not in available_formats_by_type["فيديو + صوت"][display_quality]:
                    available_formats_by_type["فيديو + صوت"][display_quality].append(ext)

            if vcodec != 'none' and acodec == 'none' and display_quality:
                if display_quality not in available_formats_by_type["فيديو فقط"]:
                    available_formats_by_type["فيديو فقط"][display_quality] = []
                if ext not in available_formats_by_type["فيديو فقط"][display_quality]:
                    available_formats_by_type["فيديو فقط"][display_quality].append(ext)

            if vcodec == 'none' and acodec != 'none' and abr:
                quality_kbps = int(abr)
                if quality_kbps not in available_formats_by_type["صوت فقط"]:
                    available_formats_by_type["صوت فقط"][quality_kbps] = []
                if ext not in available_formats_by_type["صوت فقط"][quality_kbps]:
                    available_formats_by_type["صوت فقط"][quality_kbps].append(ext)

        formatted_formats = {}
        if available_formats_by_type.get("فيديو + صوت"):
            formatted_formats["فيديو + صوت"] = sorted([f"{q}p" for q in available_formats_by_type["فيديو + صوت"].keys()], reverse=False)
        if available_formats_by_type.get("فيديو فقط"):
            formatted_formats["فيديو فقط"] = sorted([f"{q}p" for q in available_formats_by_type["فيديو فقط"].keys()], reverse=False)
        if available_formats_by_type.get("صوت فقط"):
            formatted_formats["صوت فقط"] = sorted([f"{q}k" for q in available_formats_by_type["صوت فقط"].keys()], reverse=False)

        return {
            "title": info_dict.get('title', 'عنوان غير متاح'),
            "thumbnail": info_dict.get('thumbnail', None),
            "duration": info_dict.get('duration', None),
            "duration_string": info_dict.get('duration_string', None),
            "available_formats": formatted_formats,
            "original_filename": info_dict.get('title', 'video')
        }
    except yt_dlp.utils.DownloadError as e:
        print(f"yt-dlp DownloadError in get_video_info_core: {e}")
        raise ValueError(f"خطأ في جلب معلومات الفيديو: {e}. تأكد من صحة الرابط.")
    except Exception as e:
        print(f"Unexpected error in get_video_info_core: {e}")
        raise Exception(f"حدث خطأ غير متوقع أثناء جلب المعلومات: {e}")

async def download_video_core(url: str, format_string: str, download_path: str, websocket: WebSocket = None):
    main_event_loop = asyncio.get_event_loop()

    async def _progress_hook_async(d):
        if websocket:
            try:
                if d['status'] == 'downloading':
                    total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate')
                    downloaded_bytes = d.get('downloaded_bytes')
                    progress = (downloaded_bytes / total_bytes * 100) if total_bytes else 0
                    speed = d.get('speed')
                    eta = d.get('eta')

                    if total_bytes and total_bytes >= (1024 * 1024 * 1000):
                        total_size_display = f"{total_bytes/(1024*1024*1024):.1f} GiB"
                    elif total_bytes:
                        total_size_display = f"{total_bytes/(1024*1024):.1f} MiB"
                    else:
                        total_size_display = "N/A"

                    speed_mib_s = f"{speed/(1024*1024):.1f} MiB/s" if speed else "N/A"

                    await websocket.send_json({
                        "status": "downloading",
                        "progress": round(progress, 1),
                        "speed": speed_mib_s,
                        "total_size": total_size_display,
                        "eta": eta
                    })
                elif d['status'] == 'finished':
                    pass
                elif d['status'] == 'error':
                    await websocket.send_json({"status": "error", "message": d.get('error', "خطأ في التنزيل.")})
            except RuntimeError as e:
                print(f"WebSocket closed by client during progress update: {e}")
            except Exception as e:
                print(f"Error sending WebSocket progress: {e}")

    def progress_hook_sync(d):
        asyncio.run_coroutine_threadsafe(_progress_hook_async(d), main_event_loop)

    ydl_opts = {
        'format': format_string,
        'outtmpl': os.path.join(download_path, '%(title)s.%(ext)s'),
        'quiet': True,
        'noplaylist': True,
        'progress_hooks': [progress_hook_sync],
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            await asyncio.to_thread(ydl.download, [url])
        return True
    except yt_dlp.utils.DownloadError as e:
        print(f"yt-dlp DownloadError: {e}")
        raise ValueError(f"خطأ في التنزيل: {e}. تأكد من تثبيت ffmpeg إذا كنت تقوم بتنزيل فيديو وصوت معًا.")
    except Exception as e:
        print(f"Unexpected error during download: {e}")
        raise Exception(f"حدث خطأ غير متوقع أثناء التنزيل: {e}")

# --- نماذج Pydantic لطلبات API ---
class InfoRequest(BaseModel):
    url: str

class DownloadRequest(BaseModel):
    url: str
    format_type: str
    quality: str
    client_id: str
    use_custom_folder: bool = False
    file_name: str = "video"

class ChatRequest(BaseModel):
    message: str
    chat_history: list[dict] # لتمرير سجل الدردشة

# --- نقاط نهاية التطبيق الرئيسية ---

@app.get("/", response_class=HTMLResponse, summary="عرض صفحة تنزيل الفيديو")
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.websocket("/ws/progress/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    active_websockets[client_id] = websocket
    print(f"WebSocket connected for client: {client_id}")
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        print(f"WebSocket disconnected for client: {client_id}")
    except Exception as e:
        print(f"WebSocket error for client {client_id}: {e}")
    finally:
        if client_id in active_websockets:
            del active_websockets[client_id]

# نقطة نهاية جلب المعلومات
@app.post("/api/info", summary="جلب معلومات الفيديو المتاحة")
async def get_info_endpoint(request: InfoRequest):
    try:
        info = await asyncio.to_thread(get_video_info_core, request.url)
        return info
    except ValueError as e:
        print(f"Error in API info endpoint (ValueError): {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        print(f"Error in API info endpoint (Unexpected Exception): {e}")
        raise HTTPException(status_code=500, detail=f"خطأ داخلي في الخادم: {e}")

# نقطة نهاية تنزيل الفيديو
@app.post("/api/download", summary="بدء تنزيل الفيديو")
async def start_download_endpoint(request: DownloadRequest):
    final_download_dir = ""
    temp_download_path = "" # هذا يمثل المجلد الفريد الذي تم إنشاؤه لهذا التنزيل

    if request.use_custom_folder:
        if platform.system() == "Windows":
            downloads_folder = os.path.join(os.path.expanduser("~"), "Downloads")
        elif platform.system() == "Darwin": # macOS
            downloads_folder = os.path.join(os.path.expanduser("~"), "Downloads")
        else: # For Linux and other OS
            downloads_folder = os.path.join(os.path.expanduser("~"), "Downloads")

        final_download_dir = os.path.join(downloads_folder, APP_DOWNLOAD_FOLDER_NAME)
        os.makedirs(final_download_dir, exist_ok=True)
        print(f"Custom download folder path: {final_download_dir}")
        temp_download_path = final_download_dir # هنا يكون المجلد المخصص هو نفسه المسار النهائي
    else:
        unique_download_id = str(uuid.uuid4())
        temp_download_path = os.path.join(PROJECT_DOWNLOAD_DIR, unique_download_id)
        os.makedirs(temp_download_path, exist_ok=True)
        final_download_dir = temp_download_path
        print(f"Temporary download folder path: {final_download_dir}")

    format_string = ""
    quality_value = None

    websocket_connection = active_websockets.get(request.client_id)
    if not websocket_connection:
        print(f"Error: WebSocket connection not found for client_id: {request.client_id}")
        raise HTTPException(status_code=400, detail="WebSocket connection not found for this client_id.")

    try:
        if request.quality:
            try:
                quality_value = int(''.join(filter(str.isdigit, request.quality)))
            except ValueError:
                pass

        if request.format_type == "فيديو + صوت":
            if quality_value:
                format_string = f"bestvideo[height<={quality_value}]+bestaudio/best"
            else:
                format_string = "bestvideo+bestaudio/best"
        elif request.format_type == "فيديو فقط":
            if quality_value:
                format_string = f"bestvideo[height<={quality_value}]"
            else:
                format_string = "bestvideo"
        elif request.format_type == "صوت فقط":
            if quality_value:
                format_string = f"bestaudio[abr<={quality_value}]"
            else:
                format_string = "bestaudio"
        else:
            raise HTTPException(status_code=400, detail="نوع صيغة غير صالح.")

        await download_video_core(request.url, format_string, final_download_dir, websocket_connection)

        downloaded_files = os.listdir(final_download_dir)
        
        actual_downloaded_files = [
            f for f in downloaded_files
            if not f.endswith(('.part', '.ytdl')) and os.path.isfile(os.path.join(final_download_dir, f))
        ]

        if actual_downloaded_files:
            file_name = actual_downloaded_files[0]
            file_path = os.path.join(final_download_dir, file_name)

            if request.use_custom_folder:
                # إذا كان المجلد المخصص قيد الاستخدام، فلا يتم إرسال الملف مباشرة
                # يتم إرسال إشعار الانتهاء عبر WebSocket
                if websocket_connection:
                    await websocket_connection.send_json({"status": "finished", "progress": 100, "file_name": file_name})
                return {"message": f"تم تنزيل الفيديو بنجاح إلى مجلد '{APP_DOWNLOAD_FOLDER_NAME}' في تنزيلات جهازك."}
            else:
                # إذا لم يتم استخدام مجلد مخصص، يتم إرسال الملف مباشرة للمتصفح
                # أرسل إشعار الانتهاء عبر WebSocket هنا قبل إرجاع FileResponse
                if websocket_connection:
                    await websocket_connection.send_json({"status": "finished", "progress": 100, "file_name": file_name})
                
                response = FileResponse(path=file_path, filename=file_name, media_type="application/octet-stream")
                return response
        else:
            if websocket_connection:
                await websocket_connection.send_json({"status": "error", "message": "اكتمل التنزيل ولكن لم يتم العثور على ملف نهائي في المجلد."})
            raise HTTPException(status_code=500, detail="اكتمل التنزيل ولكن لم يتم العثور على ملف نهائي في المجلد.")

    except ValueError as e:
        if websocket_connection:
            await websocket_connection.send_json({"status": "error", "message": str(e)})
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        if websocket_connection:
            await websocket_connection.send_json({"status": "error", "message": f"حدث خطأ غير متوقع: {e}"})
        raise HTTPException(status_code=500, detail=f"خطأ داخلي في الخادم أثناء التنزيل: {e}")
    finally:
        # هذا الجزء مسؤول عن تنظيف المجلدات المؤقتة.
        # المنطق الحالي يقوم بحذف المجلد الفريد الذي تم إنشاؤه لكل تنزيل
        # عندما لا يتم استخدام مجلد مخصص.
        if not request.use_custom_folder and os.path.exists(temp_download_path):
            async def cleanup_temp_folder():
                # إعطاء مهلة قصيرة لضمان إرسال الملف بالكامل للمتصفح قبل الحذف
                # هذه المهلة ضرورية لأن FileResponse قد لا تكون قد أتمت إرسال الملف
                # بالكامل عندما يتم استدعاء finally.
                await asyncio.sleep(3) # زيادة المهلة قليلاً للتأكد
                try:
                    shutil.rmtree(temp_download_path)
                    print(f"Cleaned up temporary folder: {temp_download_path}")
                except OSError as e:
                    print(f"Error removing temporary folder {temp_download_path}: {e}")
            asyncio.create_task(cleanup_temp_folder())

        # **تحذير: الكود أدناه سيقوم بحذف مجلد PROJECT_DOWNLOAD_DIR بالكامل**
        # **(أي المجلد "downloads" الرئيسي في مشروعك) بعد كل عملية تنزيل.**
        # **هذا السلوك غير موصى به بشدة لأنه قد يؤدي إلى:**
        # 1.  **فقدان بيانات:** إذا كان هناك أي ملفات أخرى غير مرتبطة بالتنزيل الحالي في هذا المجلد.
        # 2.  **تعارض مع تنزيلات متزامنة:** إذا كان هناك أكثر من عملية تنزيل تحدث في نفس الوقت، فقد يقوم بحذف ملفات تنزيلات أخرى جارية.
        # 3.  **مشاكل في الأداء:** إعادة إنشاء المجلد مرارًا وتكرارًا.
        # **استخدم هذا الكود على مسؤوليتك الخاصة إذا كنت تفهم المخاطر وتتحملها.**
        #
        # if os.path.exists(PROJECT_DOWNLOAD_DIR):
        #     async def cleanup_main_download_dir_contents():
        #         # مهلة أطول للتأكد من انتهاء جميع العمليات
        #         await asyncio.sleep(5) 
        #         try:
        #             for item in os.listdir(PROJECT_DOWNLOAD_DIR):
        #                 item_path = os.path.join(PROJECT_DOWNLOAD_DIR, item)
        #                 if os.path.isfile(item_path):
        #                     os.remove(item_path)
        #                     print(f"Removed file: {item_path}")
        #                 elif os.path.isdir(item_path):
        #                     shutil.rmtree(item_path)
        #                     print(f"Removed directory: {item_path}")
        #             print(f"Cleaned up all contents of PROJECT_DOWNLOAD_DIR: {PROJECT_DOWNLOAD_DIR}")
        #         except OSError as e:
        #             print(f"Error cleaning PROJECT_DOWNLOAD_DIR {PROJECT_DOWNLOAD_DIR}: {e}")
        #     asyncio.create_task(cleanup_main_download_dir_contents())


# --- نقطة نهاية الدردشة مع الذكاء الاصطناعي ---
@app.post("/api/chat", summary="الدردشة مع نموذج Gemini AI")
async def chat_with_gemini(chat_request: ChatRequest):
    try:
        # بناء سجل الدردشة للنموذج
        # النموذج يتوقع تنسيق: [{role: "user", parts: [{text: "..."}]}, {role: "model", parts: [{text: "..."}]}]
        formatted_history = []
        for msg in chat_request.chat_history:
            formatted_history.append({"role": msg["role"], "parts": [{"text": msg["text"]}]})
        
        # إضافة رسالة المستخدم الحالية
        formatted_history.append({"role": "user", "parts": [{"text": chat_request.message}]})

        payload = {
            "contents": formatted_history
        }
        # مفتاح Gemini API - تم تضمينه هنا
        api_key = "AIzaSyDWqs8Fxw--ciyrFyR9XPzFikn7rQPqD5k" 
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"

        # استخدام httpx لإجراء طلب غير متزامن
        # يجب تثبيت httpx: pip install httpx
        import httpx
        async with httpx.AsyncClient() as client:
            response = await client.post(
                api_url,
                headers={'Content-Type': 'application/json'},
                json=payload,
                timeout=60.0 # زيادة المهلة لطلبات LLM
            )
        response.raise_for_status() # رفع استثناء لأكواد الحالة 4xx/5xx

        result = response.json()
        
        if result.get('candidates') and result['candidates'][0].get('content') and result['candidates'][0]['content'].get('parts'):
            ai_response_text = result['candidates'][0]['content']['parts'][0]['text']
            return {"response": ai_response_text}
        else:
            print(f"Unexpected AI response structure: {result}")
            raise HTTPException(status_code=500, detail="تنسيق رد الذكاء الاصطناعي غير متوقع.")

    except httpx.HTTPStatusError as e:
        print(f"HTTP error with Gemini API: {e.response.status_code} - {e.response.text}")
        raise HTTPException(status_code=e.response.status_code, detail=f"خطأ في الاتصال بنموذج الذكاء الاصطناعي: {e.response.text}")
    except httpx.RequestError as e:
        print(f"Request error with Gemini API: {e}")
        raise HTTPException(status_code=500, detail=f"خطأ في طلب الذكاء الاصطناعي: {e}")
    except Exception as e:
        print(f"Unexpected error in chat_with_gemini: {e}")
        raise HTTPException(status_code=500, detail=f"حدث خطأ غير متوقع أثناء الدردشة مع الذكاء الاصطناعي: {e}")
