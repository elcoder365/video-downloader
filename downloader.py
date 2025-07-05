import customtkinter as ctk
from tkinter import filedialog, messagebox
import yt_dlp
import threading
import os

# Set the appearance mode and default color theme
ctk.set_appearance_mode("System")  # Can be "System", "Dark", "Light"
ctk.set_default_color_theme("blue")  # Can be "blue", "dark-blue", "green"

class VideoDownloaderApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Configure window
        self.title("برنامج تنزيل الفيديو") # Video Downloader Program
        self.geometry("700x500")
        self.resizable(False, False)

        # Configure grid layout (4x2)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=1) # Added for quality column
        self.grid_rowconfigure((0, 1, 2, 3, 4, 5, 6, 7), weight=1) # Adjusted row count

        # Create sidebar frame with widgets
        self.sidebar_frame = ctk.CTkFrame(self, width=140, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, rowspan=8, sticky="nsew") # Adjusted rowspan
        self.sidebar_frame.grid_rowconfigure(4, weight=1)

        self.logo_label = ctk.CTkLabel(self.sidebar_frame, text="تنزيل الفيديو", font=ctk.CTkFont(size=20, weight="bold")) # Video Download
        self.logo_label.grid(row=0, column=0, padx=20, pady=20)

        self.appearance_mode_label = ctk.CTkLabel(self.sidebar_frame, text="وضع المظهر:", anchor="e") # Appearance Mode:
        self.appearance_mode_label.grid(row=5, column=0, padx=20, pady=(10, 0), sticky="ew") # Changed sticky to ew for better alignment
        self.appearance_mode_optionemenu = ctk.CTkOptionMenu(self.sidebar_frame, values=["System", "Dark", "Light"],
                                                               command=self.change_appearance_mode_event)
        self.appearance_mode_optionemenu.grid(row=6, column=0, padx=20, pady=(10, 20), sticky="ew") # Changed sticky to ew

        # Create main entry and button
        self.url_label = ctk.CTkLabel(self, text="رابط الفيديو:", font=ctk.CTkFont(size=15)) # Video Link:
        self.url_label.grid(row=0, column=1, padx=(20, 20), pady=(20, 0), sticky="e") # Changed sticky to e

        self.url_entry = ctk.CTkEntry(self, placeholder_text="أدخل رابط الفيديو هنا...") # Enter video link here...
        self.url_entry.grid(row=1, column=1, columnspan=2, padx=(20, 20), pady=(0, 10), sticky="ew")

        self.fetch_button = ctk.CTkButton(self, text="جلب المعلومات", command=self.fetch_video_info) # Fetch Info
        self.fetch_button.grid(row=2, column=1, columnspan=2, padx=(20, 20), pady=(0, 10), sticky="ew")

        # Format and Quality selection
        self.format_label = ctk.CTkLabel(self, text="الصيغة:", font=ctk.CTkFont(size=15)) # Format:
        self.format_label.grid(row=3, column=1, padx=(20, 20), pady=(0, 0), sticky="e") # Changed sticky to e
        self.format_optionmenu = ctk.CTkOptionMenu(self, values=["لا توجد صيغ متاحة"], state="disabled",
                                                    command=self.update_quality_options) # No formats available, added command
        self.format_optionmenu.grid(row=4, column=1, padx=(20, 20), pady=(0, 10), sticky="ew")

        self.quality_label = ctk.CTkLabel(self, text="الجودة:", font=ctk.CTkFont(size=15)) # Quality:
        self.quality_label.grid(row=3, column=2, padx=(0, 20), pady=(0, 0), sticky="e") # Changed sticky to e
        self.quality_optionmenu = ctk.CTkOptionMenu(self, values=["لا توجد جودات متاحة"], state="disabled") # No qualities available
        self.quality_optionmenu.grid(row=4, column=2, padx=(0, 20), pady=(0, 10), sticky="ew")

        # Download button
        self.download_button = ctk.CTkButton(self, text="تنزيل", command=self.start_download, state="disabled") # Download
        self.download_button.grid(row=5, column=1, columnspan=2, padx=(20, 20), pady=(10, 10), sticky="ew")

        # Progress bar and status label
        self.progress_bar = ctk.CTkProgressBar(self, orientation="horizontal")
        self.progress_bar.grid(row=6, column=1, columnspan=2, padx=(20, 20), pady=(0, 10), sticky="ew")
        self.progress_bar.set(0)

        self.status_label = ctk.CTkLabel(self, text="الرجاء إدخال رابط الفيديو...", wraplength=400, anchor="e") # Please enter video link..., changed anchor
        self.status_label.grid(row=7, column=1, columnspan=2, padx=(20, 20), pady=(0, 20), sticky="ew") # Changed sticky to ew

        self.video_info = None
        # Store available qualities per type (combined, video_only, audio_only)
        # {type_string: {quality_value: [list_of_exts_for_this_quality_and_type]}}
        self.available_qualities_by_type = {
            "فيديو + صوت": {},
            "فيديو فقط": {},
            "صوت فقط": {}
        }

    def change_appearance_mode_event(self, new_appearance_mode: str):
        ctk.set_appearance_mode(new_appearance_mode)

    def fetch_video_info(self):
        url = self.url_entry.get()
        if not url:
            self.status_label.configure(text="الرجاء إدخال رابط فيديو صالح.") # Please enter a valid video link.
            return

        self.status_label.configure(text="جلب معلومات الفيديو...") # Fetching video information...
        self.fetch_button.configure(state="disabled")
        self.download_button.configure(state="disabled")
        self.format_optionmenu.configure(state="disabled", values=["جاري التحميل..."]) # Loading...
        self.quality_optionmenu.configure(state="disabled", values=["جاري التحميل..."]) # Loading...
        self.progress_bar.set(0)

        # Run fetching in a separate thread to keep GUI responsive
        threading.Thread(target=self._fetch_video_info_thread, args=(url,)).start()

    def _fetch_video_info_thread(self, url):
        try:
            ydl_opts = {
                'quiet': True,
                'simulate': True,
                'force_generic_extractor': True,
                'skip_download': True, # Only fetch info, not download
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=False)
                self.video_info = info_dict

            # Reset available qualities
            self.available_qualities_by_type = {
                "فيديو + صوت": {},
                "فيديو فقط": {},
                "صوت فقط": {}
            }

            for f in self.video_info.get('formats', []):
                ext = f.get('ext')
                vcodec = f.get('vcodec')
                acodec = f.get('acodec')
                height = f.get('height')
                abr = f.get('abr') # Average bitrate for audio
                format_id = f.get('format_id')
                format_note = f.get('format_note') # e.g., 'DASH video' or '480p'
                resolution_str = f.get('resolution') # e.g., '1920x1080'

                if not ext or not format_id:
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

                # Populate "فيديو + صوت" with all available video qualities (even if video-only)
                if vcodec != 'none' and display_quality:
                    if display_quality not in self.available_qualities_by_type["فيديو + صوت"]:
                        self.available_qualities_by_type["فيديو + صوت"][display_quality] = []
                    if ext not in self.available_qualities_by_type["فيديو + صوت"][display_quality]:
                        self.available_qualities_by_type["فيديو + صوت"][display_quality].append(ext)

                # Populate "فيديو فقط" for explicit video-only streams
                if vcodec != 'none' and acodec == 'none' and display_quality:
                    if display_quality not in self.available_qualities_by_type["فيديو فقط"]:
                        self.available_qualities_by_type["فيديو فقط"][display_quality] = []
                    if ext not in self.available_qualities_by_type["فيديو فقط"][display_quality]:
                        self.available_qualities_by_type["فيديو فقط"][display_quality].append(ext)
                
                # Populate "صوت فقط" for explicit audio-only streams
                if vcodec == 'none' and acodec != 'none' and abr:
                    if int(abr) not in self.available_qualities_by_type["صوت فقط"]:
                        self.available_qualities_by_type["صوت فقط"][int(abr)] = []
                    if ext not in self.available_qualities_by_type["صوت فقط"][int(abr)]:
                        self.available_qualities_by_type["صوت فقط"][int(abr)].append(ext)

            # Populate format options based on what's available
            format_options = []
            if self.available_qualities_by_type["فيديو + صوت"]:
                format_options.append("فيديو + صوت")
            if self.available_qualities_by_type["فيديو فقط"]:
                format_options.append("فيديو فقط")
            if self.available_qualities_by_type["صوت فقط"]:
                format_options.append("صوت فقط")

            if not format_options:
                self.after(0, lambda: self.status_label.configure(text="لم يتم العثور على صيغ فيديو/صوت صالحة لهذا الرابط.")) # No valid video/audio formats found for this link.
                self.after(0, lambda: self.reset_ui_after_fetch())
                return

            self.after(0, lambda: self.format_optionmenu.configure(values=format_options, state="normal"))
            self.after(0, lambda: self.format_optionmenu.set(format_options[0]))
            self.after(0, lambda: self.update_quality_options(format_options[0])) # Update quality for the first format
            self.after(0, lambda: self.download_button.configure(state="normal"))
            self.after(0, lambda: self.status_label.configure(text="تم جلب المعلومات بنجاح. اختر الصيغة والجودة.")) # Info fetched successfully. Choose format and quality.

        except yt_dlp.utils.DownloadError as e:
            self.after(0, lambda: self.status_label.configure(text=f"خطأ في جلب المعلومات: {e}")) # Error fetching info:
            messagebox.showerror("خطأ", f"تعذر جلب معلومات الفيديو: {e}\nتأكد من صحة الرابط.") # Error, Could not fetch video information: Make sure the link is correct.
        except Exception as e:
            self.after(0, lambda: self.status_label.configure(text=f"حدث خطأ غير متوقع: {e}")) # An unexpected error occurred:
            messagebox.showerror("خطأ", f"حدث خطأ غير متوقع: {e}") # Error, An unexpected error occurred:
        finally:
            self.after(0, lambda: self.fetch_button.configure(state="normal"))

    def update_quality_options(self, selected_format_text: str):
        quality_options = []
        
        if selected_format_text in self.available_qualities_by_type:
            qualities = sorted(self.available_qualities_by_type[selected_format_text].keys(), reverse=True)
            for q in qualities:
                if selected_format_text == "صوت فقط":
                    quality_options.append(f"{q}k") # e.g., 128k
                else:
                    quality_options.append(f"{q}p") # e.g., 1080p
        
        if not quality_options:
            quality_options = ["لا توجد جودات متاحة"] # No qualities available
            self.quality_optionmenu.configure(state="disabled")
        else:
            self.quality_optionmenu.configure(state="normal")

        self.quality_optionmenu.configure(values=quality_options)
        self.quality_optionmenu.set(quality_options[0])


    def reset_ui_after_fetch(self):
        self.format_optionmenu.configure(values=["لا توجد صيغ متاحة"], state="disabled") # No formats available
        self.quality_optionmenu.configure(values=["لا توجد جودات متاحة"], state="disabled") # No qualities available
        self.download_button.configure(state="disabled")
        self.fetch_button.configure(state="normal")

    def start_download(self):
        selected_format_text = self.format_optionmenu.get()
        selected_quality_text = self.quality_optionmenu.get()
        url = self.url_entry.get()

        if not self.video_info or not selected_format_text or not selected_quality_text or not url or selected_quality_text == "لا توجد جودات متاحة":
            self.status_label.configure(text="الرجاء جلب معلومات الفيديو أولاً واختيار الصيغة والجودة.") # Please fetch video info first and select format and quality.
            return

        format_string = ""
        quality_value = None
        try:
            quality_value = int(''.join(filter(str.isdigit, selected_quality_text)))
        except ValueError:
            pass

        if selected_format_text == "فيديو + صوت":
            if quality_value:
                # Prioritize best video and best audio up to the selected quality
                format_string = f"bestvideo[height<={quality_value}]+bestaudio/best[height<={quality_value}]"
            else:
                format_string = "bestvideo+bestaudio/best" # Get best overall if quality not specified
        elif selected_format_text == "فيديو فقط":
            if quality_value:
                format_string = f"bestvideo[height<={quality_value}]"
            else:
                format_string = "bestvideo" # Get best video only
        elif selected_format_text == "صوت فقط":
            if quality_value:
                format_string = f"bestaudio[abr<={quality_value}]"
            else:
                format_string = "bestaudio" # Get best audio only
        else:
            self.status_label.configure(text="خطأ في تحديد الصيغة.") # Error determining format.
            messagebox.showerror("خطأ", "لم يتم تحديد صيغة تنزيل صالحة.") # Error, No valid download format specified.
            return

        # Ask user for download location
        download_path = filedialog.askdirectory(title="اختر مجلد الحفظ") # Choose Save Folder
        if not download_path:
            self.status_label.configure(text="تم إلغاء التنزيل.") # Download cancelled.
            return

        self.status_label.configure(text="بدء التنزيل...") # Starting download...
        self.download_button.configure(state="disabled")
        self.fetch_button.configure(state="disabled")
        self.progress_bar.set(0)

        # Run download in a separate thread
        threading.Thread(target=self._download_video_thread, args=(url, format_string, download_path)).start()

    def _download_video_thread(self, url, format_string, download_path):
        try:
            ydl_opts = {
                'format': format_string,
                'outtmpl': os.path.join(download_path, '%(title)s.%(ext)s'),
                'progress_hooks': [self.download_progress_hook],
                'quiet': False, # Set to False to see yt-dlp output in console for debugging
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            self.after(0, lambda: self.status_label.configure(text=f"تم التنزيل بنجاح إلى: {download_path}")) # Downloaded successfully to:
            messagebox.showinfo("نجاح", f"تم تنزيل الفيديو بنجاح إلى:\n{download_path}") # Success, Video downloaded successfully to:
        except yt_dlp.utils.DownloadError as e:
            self.after(0, lambda: self.status_label.configure(text=f"خطأ في التنزيل: {e}")) # Download error:
            messagebox.showerror("خطأ", f"تعذر تنزيل الفيديو: {e}\nتأكد من تثبيت ffmpeg إذا كنت تقوم بتنزيل فيديو وصوت معًا.") # Error, Could not download video: Make sure ffmpeg is installed if you are downloading video and audio together.
        except Exception as e:
            self.after(0, lambda: self.status_label.configure(text=f"حدث خطأ غير متوقع أثناء التنزيل: {e}")) # An unexpected error occurred during download:
            messagebox.showerror("خطأ", f"حدث خطأ غير متوقع أثناء التنزيل: {e}") # Error, An unexpected error occurred during download:
        finally:
            self.after(0, lambda: self.download_button.configure(state="normal"))
            self.after(0, lambda: self.fetch_button.configure(state="normal"))
            self.after(0, lambda: self.progress_bar.set(0))

    def download_progress_hook(self, d):
        if d['status'] == 'downloading':
            total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate')
            downloaded_bytes = d.get('downloaded_bytes')
            if total_bytes and downloaded_bytes:
                progress = downloaded_bytes / total_bytes
                self.after(0, lambda: self.progress_bar.set(progress))
                speed = d.get('speed')
                eta = d.get('eta')
                status_text = f"جاري التنزيل: {progress:.1%} - السرعة: {speed/1024:.1f} KiB/s - الوقت المتبقي: {eta} ثانية" if speed and eta else f"جاري التنزيل: {progress:.1%}" # Downloading: - Speed: KiB/s - ETA: seconds
                self.after(0, lambda: self.status_label.configure(text=status_text))
        elif d['status'] == 'finished':
            self.after(0, lambda: self.progress_bar.set(1))
            self.after(0, lambda: self.status_label.configure(text="اكتمل التنزيل!")) # Download complete!
        elif d['status'] == 'error':
            self.after(0, lambda: self.status_label.configure(text="خطأ في التنزيل.")) # Download error.

if __name__ == "__main__":
    app = VideoDownloaderApp()
    app.mainloop()
