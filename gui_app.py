import customtkinter as ctk
import asyncio
import threading
from datetime import datetime
from houzz_pro_scraper import run_scraper

# Set appearance and theme
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class LogWindow(ctk.CTkTextbox):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.configure(state="disabled", font=("Consolas", 12))

    def log(self, message):
        self.configure(state="normal")
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.insert("end", f"[{timestamp}] {message}\n")
        self.see("end")
        self.configure(state="disabled")

class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("STONIX - Web Lead Scraper Pro")
        self.geometry("1100x700")

        # Grid configuration
        self.grid_columnconfigure(0, weight=0)  # Sidebar
        self.grid_columnconfigure(1, weight=1)  # Main Area
        self.grid_rowconfigure(0, weight=1)

        # --- Sidebar (Settings) ---
        self.sidebar = ctk.CTkFrame(self, width=300, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        self.sidebar.grid_rowconfigure(15, weight=1)

        self.logo_label = ctk.CTkLabel(self.sidebar, text="💎 STONIX PRO", font=ctk.CTkFont(size=24, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.subtitle_label = ctk.CTkLabel(self.sidebar, text="PREMIUM LEAD SCRAPER", font=ctk.CTkFont(size=11, slant="italic"))
        self.subtitle_label.grid(row=1, column=0, padx=20, pady=(0, 20))

        # URL Input
        self.url_label = ctk.CTkLabel(self.sidebar, text="🔗 Search URL:", anchor="w")
        self.url_label.grid(row=2, column=0, padx=20, pady=(10, 0), sticky="w")
        self.url_entry = ctk.CTkEntry(self.sidebar, placeholder_text="Paste Houzz/BBB URL here...", width=260, border_width=1)
        self.url_entry.grid(row=3, column=0, padx=20, pady=(5, 15))

        # Source Selection (Segmented Button for more premium feel)
        self.source_label = ctk.CTkLabel(self.sidebar, text="🌐 Platform Source:", anchor="w")
        self.source_label.grid(row=4, column=0, padx=20, pady=(10, 0), sticky="w")
        self.source_seg_btn = ctk.CTkSegmentedButton(self.sidebar, values=["Houzz", "BBB"], width=260)
        self.source_seg_btn.set("Houzz")
        self.source_seg_btn.grid(row=5, column=0, padx=20, pady=(5, 15))

        # Limits
        self.limit_label = ctk.CTkLabel(self.sidebar, text="⚙️ Scraping Limits:", anchor="w")
        self.limit_label.grid(row=6, column=0, padx=20, pady=(10, 0), sticky="w")
        self.limit_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.limit_frame.grid(row=7, column=0, padx=20, pady=(5, 15))

        self.max_pages_entry = ctk.CTkEntry(self.limit_frame, placeholder_text="Max Pages", width=125)
        self.max_pages_entry.grid(row=0, column=0, padx=(0, 5))
        
        self.max_profiles_entry = ctk.CTkEntry(self.limit_frame, placeholder_text="Max Profiles", width=125)
        self.max_profiles_entry.grid(row=0, column=1, padx=(5, 0))

        # Toggles
        self.headless_var = ctk.BooleanVar(value=False)
        self.headless_cb = ctk.CTkCheckBox(self.sidebar, text="Run Headless (Hidden Browser)", variable=self.headless_var)
        self.headless_cb.grid(row=7, column=0, padx=20, pady=5, sticky="w")

        self.skip_fb_var = ctk.BooleanVar(value=False)
        self.skip_fb_cb = ctk.CTkCheckBox(self.sidebar, text="Skip Facebook Scraping", variable=self.skip_fb_var)
        self.skip_fb_cb.grid(row=8, column=0, padx=20, pady=5, sticky="w")

        self.skip_google_var = ctk.BooleanVar(value=False)
        self.skip_google_cb = ctk.CTkCheckBox(self.sidebar, text="Skip Google Fallback", variable=self.skip_google_var)
        self.skip_google_cb.grid(row=9, column=0, padx=20, pady=5, sticky="w")

        self.retry_no_email_var = ctk.BooleanVar(value=False)
        self.retry_no_email_cb = ctk.CTkCheckBox(self.sidebar, text="Retry 'No Email' Profiles", variable=self.retry_no_email_var)
        self.retry_no_email_cb.grid(row=10, column=0, padx=20, pady=5, sticky="w")

        # Country
        self.country_label = ctk.CTkLabel(self.sidebar, text="🏳️ Target Country (Fallback):", anchor="w")
        self.country_label.grid(row=11, column=0, padx=20, pady=(10, 0), sticky="w")
        self.country_entry = ctk.CTkEntry(self.sidebar, placeholder_text="e.g. USA, UK", width=260)
        self.country_entry.grid(row=12, column=0, padx=20, pady=(5, 20))

        # Start Button
        self.start_button = ctk.CTkButton(self.sidebar, text="▶ START SCRAPER", font=ctk.CTkFont(size=14, weight="bold"), 
                                        fg_color="#2ECC71", hover_color="#27AE60",
                                        height=45, command=self.start_scraping)
        self.start_button.grid(row=13, column=0, padx=20, pady=(10, 10))

        self.stop_button = ctk.CTkButton(self.sidebar, text="⏹ STOP PROCESS", font=ctk.CTkFont(size=14, weight="bold"),
                                       fg_color="#E74C3C", hover_color="#C0392B", 
                                       state="disabled", height=40, command=self.stop_scraping)
        self.stop_button.grid(row=14, column=0, padx=20, pady=10)

        self.export_button = ctk.CTkButton(self.sidebar, text="📥 EXPORT FINAL CSV", font=ctk.CTkFont(size=14),
                                         fg_color="#3498DB", hover_color="#2980B9",
                                         height=40, command=self.export_only)
        self.export_button.grid(row=15, column=0, padx=20, pady=10)

        # --- Main Area (Logs) ---
        self.main_frame = ctk.CTkFrame(self, corner_radius=10)
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.main_frame.grid_rowconfigure(1, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=1)

        self.log_header = ctk.CTkLabel(self.main_frame, text="Activity Logs", font=ctk.CTkFont(size=16, weight="bold"))
        self.log_header.grid(row=0, column=0, padx=20, pady=(15, 5), sticky="w")

        self.log_textbox = LogWindow(self.main_frame)
        self.log_textbox.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")

        # --- Status Bar ---
        self.status_bar = ctk.CTkFrame(self, height=30, corner_radius=0)
        self.status_bar.grid(row=1, column=0, columnspan=2, sticky="ew")
        
        self.status_label = ctk.CTkLabel(self.status_bar, text="Status: Ready", font=ctk.CTkFont(size=11))
        self.status_label.pack(side="left", padx=20)

        # Scraper Threading variables
        self.scraper_thread = None
        self.stop_event = None

    def start_scraping(self):
        url = self.url_entry.get().strip()
        if not url:
            self.log_textbox.log("Error: Please provide a Search URL.")
            return

        # Disable UI
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.export_button.configure(state="disabled")
        self.status_label.configure(text="Status: Working...")

        # Get settings
        source = self.source_seg_btn.get().lower()
        try:
            max_pages = int(self.max_pages_entry.get()) if self.max_pages_entry.get() else None
        except ValueError:
            max_pages = None
            
        try:
            max_profiles = int(self.max_profiles_entry.get()) if self.max_profiles_entry.get() else None
        except ValueError:
            max_profiles = None

        headless = self.headless_var.get()
        skip_fb = self.skip_fb_var.get()
        skip_google = self.skip_google_var.get()
        retry_no_email = self.retry_no_email_var.get()
        country = self.country_entry.get().strip()

        # Run in thread
        self.scraper_thread = threading.Thread(
            target=self.run_async_scraper,
            args=(url, source, max_pages, max_profiles, headless, skip_fb, country, skip_google, retry_no_email),
            daemon=True
        )
        self.scraper_thread.start()

    def run_async_scraper(self, url, source, max_pages, max_profiles, headless, skip_fb, country, skip_google, retry_no_email):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        self.stop_event = asyncio.Event()

        def gui_logger(msg):
            self.after(0, lambda: self.log_textbox.log(msg))

        try:
            loop.run_until_complete(
                run_scraper(
                    url,
                    source=source,
                    max_pages=max_pages,
                    max_profiles=max_profiles,
                    headless=headless,
                    skip_facebook=skip_fb,
                    country=country,
                    skip_google_fallback=skip_google,
                    retry_no_email=retry_no_email,
                    logger=gui_logger,
                    stop_event=self.stop_event
                )
            )
            self.after(0, lambda: self.log_textbox.log("[SYSTEM] Scraping session completed."))
        except Exception as e:
            err_msg = str(e)
            self.after(0, lambda: self.log_textbox.log(f"[ERROR] {err_msg}"))
        finally:
            self.after(0, self.reset_ui)
            loop.close()

    def stop_scraping(self):
        if self.stop_event:
            self.log_textbox.log("[SYSTEM] Stop requested (Process will finish current profile)...")
            self.stop_event.set()

    def reset_ui(self):
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        self.export_button.configure(state="normal")
        self.status_label.configure(text="Status: Ready")

    def export_only(self):
        source = self.source_seg_btn.get().lower()
        self.log_textbox.log(f"[SYSTEM] Starting export for {source}...")
        
        from houzz_pro_scraper import export_final_for_source
        try:
            export_final_for_source(source)
            self.log_textbox.log("[SYSTEM] Export completed. Check output folder.")
        except Exception as e:
            err_msg = str(e)
            self.log_textbox.log(f"[ERROR] Export failed: {err_msg}")

if __name__ == "__main__":
    app = App()
    app.mainloop()
