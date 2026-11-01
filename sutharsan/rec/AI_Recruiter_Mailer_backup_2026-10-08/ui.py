import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
import os
import time
import pandas as pd
from database import (init_db, get_all_recruiters, insert_recruiter, update_email_content,
                      update_status, get_report, delete_all_recruiters, log_event, update_recruiter_details,
                      insert_recruiters_bulk, update_emails_bulk)
from settings import load_settings, save_settings
from gmail_smtp import test_connection, send_email
from text_parser import parse_linkedin_posts
from free_generator import generate_template_email


class AppUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("AI Recruiter Mailer — Santhosh B")
        self.geometry("1320x830")
        self.minsize(1100, 700)
        init_db()
        self.settings = load_settings()
        ctk.set_appearance_mode("Light")
        self.configure(fg_color="#ffffff")
        self._build()
        self.load_data()

    def _build(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ── SIDEBAR ──
        sb = ctk.CTkFrame(self, width=220, corner_radius=0, fg_color="#f3f4f6")
        sb.grid(row=0, column=0, sticky="nsew")
        sb.grid_propagate(False)
        p = {"padx": 14, "pady": 4}

        ctk.CTkLabel(sb, text="✉ AI Recruiter Mailer", font=ctk.CTkFont(size=14, weight="bold"),
                     text_color="#4f46e5").pack(pady=(18, 2), padx=14)
        ctk.CTkLabel(sb, text="Santhosh B", font=ctk.CTkFont(size=11), text_color="#4b5563").pack(pady=(0, 10))

        # Gmail
        ctk.CTkLabel(sb, text="── Gmail ──", text_color="#9ca3af", font=ctk.CTkFont(size=10)).pack(pady=(6, 2))
        self.gmail_lbl = ctk.CTkLabel(sb, text="● Not Connected", text_color="#ef4444", font=ctk.CTkFont(size=11))
        self.gmail_lbl.pack(pady=3)
        ctk.CTkButton(sb, text="Connect Gmail", height=30, command=self.connect_gmail,
                      fg_color="#059669", hover_color="#10b981").pack(fill="x", **p)

        # Resume
        ctk.CTkLabel(sb, text="── Resume ──", text_color="#9ca3af", font=ctk.CTkFont(size=10)).pack(pady=(8, 2))
        self.resume_lbl = ctk.CTkLabel(sb, text="No resume", text_color="#4b5563", font=ctk.CTkFont(size=10))
        self.resume_lbl.pack(pady=2)
        ctk.CTkButton(sb, text="Upload Resume", height=28, command=self.upload_resume,
                      fg_color="#e5e7eb", hover_color="#d1d5db", text_color="#1f2937").pack(fill="x", **p)

        # Actions
        ctk.CTkLabel(sb, text="── Actions ──", text_color="#9ca3af", font=ctk.CTkFont(size=10)).pack(pady=(8, 2))
        ctk.CTkButton(sb, text="📋 Paste LinkedIn Jobs", height=32, command=self.open_paste_window,
                      fg_color="#4f46e5", hover_color="#6366f1").pack(fill="x", **p)
        ctk.CTkButton(sb, text="📁 Upload CSV File", height=28, command=self.upload_file,
                      fg_color="#1e40af", hover_color="#3b82f6").pack(fill="x", **p)

        # Send
        ctk.CTkLabel(sb, text="── Send ──", text_color="#9ca3af", font=ctk.CTkFont(size=10)).pack(pady=(8, 2))
        ctk.CTkButton(sb, text="🚀 SEND ALL", height=36, command=self.send_all,
                      fg_color="#dc2626", hover_color="#ef4444",
                      font=ctk.CTkFont(size=13, weight="bold")).pack(fill="x", padx=14, pady=6)
        ctk.CTkButton(sb, text="Retry Failed", height=26, command=self.retry_failed,
                      fg_color="#e5e7eb", hover_color="#d1d5db", text_color="#1f2937").pack(fill="x", **p)

        # Other
        ctk.CTkLabel(sb, text="── Other ──", text_color="#9ca3af", font=ctk.CTkFont(size=10)).pack(pady=(8, 2))
        ctk.CTkButton(sb, text="Settings", height=26, command=self.open_settings,
                      fg_color="#e5e7eb", hover_color="#d1d5db", text_color="#1f2937").pack(fill="x", **p)
        ctk.CTkButton(sb, text="Clear All", height=26, command=self.clear_data,
                      fg_color="#e5e7eb", hover_color="#d1d5db", text_color="#1f2937").pack(fill="x", **p)
        self.status_lbl = ctk.CTkLabel(sb, text="Ready", text_color="#4b5563", font=ctk.CTkFont(size=10))
        self.status_lbl.pack(side="bottom", pady=10)

        # Resume loaded check
        resume = self.settings.get("resume_path", "")
        if resume and os.path.exists(resume):
            self.resume_lbl.configure(text=f"📎 {os.path.basename(resume)}", text_color="#10b981")

        # ── MAIN ──
        main = ctk.CTkFrame(self, fg_color="#ffffff")
        main.grid(row=0, column=1, sticky="nsew", padx=12, pady=12)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)

        # Stats
        self.stats_frame = ctk.CTkFrame(main, fg_color="#f9fafb", corner_radius=10, border_color="#e5e7eb", border_width=1)
        self.stats_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self._build_stats()

        # Table
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("E.Treeview", background="#ffffff", foreground="#1f2937",
                        fieldbackground="#ffffff", rowheight=30, borderwidth=0)
        style.configure("E.Treeview.Heading", background="#f3f4f6", foreground="#4f46e5",
                        borderwidth=0, font=("Segoe UI", 10, "bold"))
        style.map("E.Treeview", background=[("selected", "#e0e7ff")])

        cols = ("ID", "Name", "Company", "Role", "Email", "Match%", "Status")
        self.tree = ttk.Treeview(main, columns=cols, show="headings", style="E.Treeview", selectmode="extended")
        widths = {"ID": 35, "Name": 120, "Company": 140, "Role": 170, "Email": 200, "Match%": 55, "Status": 95}
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=widths.get(c, 100), minwidth=35)
        self.tree.grid(row=1, column=0, sticky="nsew")
        self.tree.bind("<Double-1>", self._on_double_click)

        self.sb2 = ctk.CTkScrollbar(main, command=self.tree.yview)
        self.sb2.grid(row=1, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=self.sb2.set)

        self.preview_frame = ctk.CTkFrame(main, fg_color="#ffffff")
        # Grid layout will be dynamically toggled during bulk outreach confirmation

        self.paste_frame = ctk.CTkFrame(main, fg_color="#ffffff")
        # Grid layout will be dynamically toggled during paste LinkedIn jobs

        bot = ctk.CTkFrame(main, fg_color="#f9fafb", corner_radius=8, border_color="#e5e7eb", border_width=1)
        bot.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ctk.CTkLabel(bot, text="Double-click row to preview/edit email  |  Paste LinkedIn → Auto Preview & Send",
                     text_color="#6b7280", font=ctk.CTkFont(size=10)).pack(side="left", padx=12, pady=8)

    def _build_stats(self):
        for w in self.stats_frame.winfo_children():
            w.destroy()
        r = get_report()
        items = [("Total", r["total"], "#1f2937"), ("Pending", r["pending"], "#f59e0b"),
                 ("Generated", r["generated"], "#a78bfa"), ("Sent", r["sent"], "#10b981"),
                 ("Failed", r["failed"], "#ef4444"), ("Sending", r["sending"], "#60a5fa")]
        
        # Left container for stats
        left_f = ctk.CTkFrame(self.stats_frame, fg_color="transparent")
        left_f.pack(side="left", fill="y", padx=10)
        
        for label, val, color in items:
            f = ctk.CTkFrame(left_f, fg_color="transparent")
            f.pack(side="left", padx=16, pady=10)
            ctk.CTkLabel(f, text=str(val), font=ctk.CTkFont(size=22, weight="bold"), text_color=color).pack()
            if label == "Failed" and val > 0:
                ctk.CTkLabel(f, text=label, font=ctk.CTkFont(size=10), text_color="#4b5563").pack()
                ctk.CTkButton(f, text="🔄 Retry", font=ctk.CTkFont(size=9, weight="bold"),
                              width=45, height=16, fg_color="#ef4444", hover_color="#dc2626", text_color="#ffffff",
                              command=self.retry_failed).pack(pady=(2, 0))
            else:
                ctk.CTkLabel(f, text=label, font=ctk.CTkFont(size=10), text_color="#4b5563").pack()
            
        # Right container for operations (History, Refresh & Reset)
        right_f = ctk.CTkFrame(self.stats_frame, fg_color="transparent")
        right_f.pack(side="right", fill="y", padx=16, pady=10)
        
        # History Stats
        hist_f = ctk.CTkFrame(right_f, fg_color="transparent")
        hist_f.pack(side="left", padx=(0, 16))
        
        ctk.CTkLabel(hist_f, text=f"Today: {r.get('today_sent', 0)}", font=ctk.CTkFont(size=11, weight="bold"), text_color="#047857").pack(anchor="e")
        ctk.CTkLabel(hist_f, text=f"This Week: {r.get('weekly_sent', 0)}", font=ctk.CTkFont(size=11, weight="bold"), text_color="#4338ca").pack(anchor="e")
        
        # Clickable View History
        ctk.CTkButton(hist_f, text="📊 View History", font=ctk.CTkFont(size=9, weight="bold", underline=True),
                      width=90, height=20, fg_color="transparent", text_color="#2563eb", hover_color="#f3f4f6",
                      command=self.show_sent_history).pack(anchor="e", pady=(2, 0))
        
        # Refresh button
        ctk.CTkButton(right_f, text="🔄 Refresh", font=ctk.CTkFont(size=11, weight="bold"),
                      width=90, height=30, fg_color="#e5e7eb", hover_color="#d1d5db", text_color="#1f2937",
                      command=self.load_data).pack(side="left", padx=6)
                      
        # Reset button (turns numbers to 0 by clearing db)
        ctk.CTkButton(right_f, text="🧹 Reset All", font=ctk.CTkFont(size=11, weight="bold"),
                      width=90, height=30, fg_color="#dc2626", hover_color="#ef4444",
                      command=self.clear_data).pack(side="left", padx=6)

    def load_data(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        for r in get_all_recruiters():
            m = f"{r['match_percentage']}%" if r['match_percentage'] is not None else "—"
            self.tree.insert("", "end", iid=str(r['id']),
                             values=(r['id'], r['recruiter_name'], r['company'],
                                     r['job_title'], r['email'], m, r['status']))
        self._build_stats()

    # ── PASTE LINKEDIN JOBS ──
    def open_paste_window(self):
        # Hide the table, scrollbar and preview frame
        self.tree.grid_remove()
        self.sb2.grid_remove()
        self.preview_frame.grid_remove()
        
        # Clear any existing widgets in the paste frame
        for w in self.paste_frame.winfo_children():
            w.destroy()
            
        # Display the paste frame in the exact location of the table
        self.paste_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")
        
        # Header Row
        hdr = ctk.CTkFrame(self.paste_frame, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=(6, 4))
        
        ctk.CTkLabel(hdr, text="📋 Paste LinkedIn Job Posts",
                     font=ctk.CTkFont(size=15, weight="bold"), text_color="#4f46e5").pack(side="left")
        ctk.CTkLabel(hdr, text="• Copy search results, paste below. AI extracts and generates emails instantly.",
                     font=ctk.CTkFont(size=11), text_color="#4b5563").pack(side="left", padx=12)
                     
        # Paste Textbox
        self.paste_textbox = ctk.CTkTextbox(self.paste_frame, fg_color="#ffffff", border_color="#e5e7eb",
                                           border_width=1, text_color="#1f2937", font=ctk.CTkFont(size=12))
        self.paste_textbox.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Controls/Buttons
        self.paste_buttons_frame = ctk.CTkFrame(self.paste_frame, fg_color="transparent")
        self.paste_buttons_frame.pack(fill="x", padx=10, pady=(6, 10))
        
        def close_paste():
            self.paste_frame.grid_remove()
            self.tree.grid(row=1, column=0, sticky="nsew")
            self.sb2.grid(row=1, column=1, sticky="ns")
            
        ctk.CTkButton(self.paste_buttons_frame, text="⚡ Extract, Generate & Preview", command=self.process_paste_and_preview,
                      fg_color="#059669", hover_color="#10b981", height=38,
                      font=ctk.CTkFont(size=13, weight="bold")).pack(side="right", padx=6)
                      
        ctk.CTkButton(self.paste_buttons_frame, text="Cancel", command=close_paste,
                      fg_color="#e5e7eb", hover_color="#d1d5db", text_color="#1f2937", height=38, width=100).pack(side="right", padx=6)

    def process_paste_and_preview(self):
        raw = self.paste_textbox.get("1.0", "end-1c")
        if len(raw.strip()) < 10:
            messagebox.showwarning("Empty", "Please paste some text first.")
            return
            
        self.status_lbl.configure(text="Extracting & generating...", text_color="#2563eb")
        self.generation_cancelled = False
        
        # Hide textbox and buttons to show clean progress overlay
        self.paste_textbox.pack_forget()
        self.paste_buttons_frame.pack_forget()
        
        # Build premium progress overlay
        prog_container = ctk.CTkFrame(self.paste_frame, fg_color="transparent")
        prog_container.pack(fill="both", expand=True, pady=60)
        
        prog_lbl = ctk.CTkLabel(prog_container, text="⚡ Extracting recruiter details... (10%)",
                                font=ctk.CTkFont(size=14, weight="bold"), text_color="#4f46e5")
        prog_lbl.pack(pady=10)
        
        prog_bar = ctk.CTkProgressBar(prog_container, width=350, height=12, progress_color="#10b981")
        prog_bar.set(0.1)
        prog_bar.pack(pady=10)
        
        def cancel_generation():
            self.generation_cancelled = True
            prog_container.destroy()
            self.status_lbl.configure(text="Ready", text_color="#4b5563")
            self.paste_textbox.pack(fill="both", expand=True, padx=10, pady=5)
            self.paste_buttons_frame.pack(fill="x", padx=10, pady=(6, 10))
            
        cancel_btn = ctk.CTkButton(prog_container, text="Cancel", command=cancel_generation,
                                   fg_color="#ef4444", hover_color="#dc2626", text_color="#ffffff",
                                   width=100, height=28, font=ctk.CTkFont(size=12, weight="bold"))
        cancel_btn.pack(pady=15)
        
        def task():
            try:
                # Update progress to 15%
                if self.generation_cancelled: return
                self.after(0, lambda: (prog_lbl.configure(text="🔍 Parsing LinkedIn text... (15%)"), prog_bar.set(0.15)))
                
                parsed = parse_linkedin_posts(raw)
                if self.generation_cancelled: return
                if not parsed:
                    def no_results():
                        if self.generation_cancelled: return
                        self.status_lbl.configure(text="Ready", text_color="#4b5563")
                        prog_container.destroy()
                        self.paste_textbox.pack(fill="both", expand=True, padx=10, pady=5)
                        self.paste_buttons_frame.pack(fill="x", padx=10, pady=(6, 10))
                        messagebox.showwarning("No Results", "Could not find any recruiter postings in the text.")
                    self.after(0, no_results)
                    return
                    
                N = len(parsed)
                if self.generation_cancelled: return
                self.after(0, lambda: (prog_lbl.configure(text=f"📂 Inserting {N} recruiters... (30%)"), prog_bar.set(0.30)))
                
                # Bulk insert all recruiters in a single fast transaction
                inserted_ids = insert_recruiters_bulk(parsed)
                if self.generation_cancelled: return
                
                if not inserted_ids:
                    def no_unique():
                        if self.generation_cancelled: return
                        self.status_lbl.configure(text="Ready", text_color="#4b5563")
                        prog_container.destroy()
                        self.paste_textbox.pack(fill="both", expand=True, padx=10, pady=5)
                        self.paste_buttons_frame.pack(fill="x", padx=10, pady=(6, 10))
                        messagebox.showinfo("Done", "No new unique recruiters added.")
                        self.paste_frame.grid_remove()
                        self.tree.grid(row=1, column=0, sticky="nsew")
                        self.sb2.grid(row=1, column=1, sticky="ns")
                    self.after(0, no_unique)
                    return
                    
                self.after(0, lambda: (prog_lbl.configure(text="⚡ Generating customized templates... (60%)"), prog_bar.set(0.60)))
                
                # Cache signature
                sig = self.settings.get("signature", "Best regards,\nSanthosh B")
                updates = []
                
                # Generate emails locally and instantly (bypass OpenAI for bulk paste)
                for r_id, r in zip(inserted_ids, parsed):
                    if self.generation_cancelled: return
                    subject, body = generate_template_email(r, sig) # No api_key parameter to bypass OpenAI
                    updates.append({
                        'id': r_id,
                        'subject': subject,
                        'body': body
                    })
                    
                self.after(0, lambda: (prog_lbl.configure(text="💾 Saving to database... (85%)"), prog_bar.set(0.85)))
                
                # Bulk update all generated email contents in a single transaction
                update_emails_bulk(updates)
                if self.generation_cancelled: return
                
                # Done! Update to 100%
                self.after(0, lambda: (prog_lbl.configure(text="✨ Done! Opening preview... (100%)"), prog_bar.set(1.0)))
                time.sleep(0.05)
                
                def done():
                    if self.generation_cancelled: return
                    prog_container.destroy()
                    self.load_data()
                    self.status_lbl.configure(text="Ready", text_color="#4b5563")
                    self.paste_frame.grid_remove()
                    
                    recruits = [r for r in get_all_recruiters() if r['status'] == 'Generated']
                    if recruits:
                        self.send_all()
                    else:
                        self.tree.grid(row=1, column=0, sticky="nsew")
                        self.sb2.grid(row=1, column=1, sticky="ns")
                        self.update_idletasks()
                    
                self.after(0, done)
            except Exception as e:
                print(f"Extraction error: {e}")
                def error_done():
                    if self.generation_cancelled: return
                    self.status_lbl.configure(text="Ready", text_color="#4b5563")
                    prog_container.destroy()
                    self.paste_textbox.pack(fill="both", expand=True, padx=10, pady=5)
                    self.paste_buttons_frame.pack(fill="x", padx=10, pady=(6, 10))
                    messagebox.showerror("Error", f"An error occurred during extraction: {e}")
                self.after(0, error_done)
                
        threading.Thread(target=task, daemon=True).start()

    # ── GMAIL ──
    def connect_gmail(self):
        email = self.settings.get("gmail_email", "")
        pw = self.settings.get("gmail_app_password", "")
        if not email or not pw:
            messagebox.showwarning("Setup", "Go to Settings → enter Gmail + App Password.")
            return
        ok, msg = test_connection(email, pw)
        if ok:
            self.gmail_lbl.configure(text=f"● {email}", text_color="#10b981")
            messagebox.showinfo("Connected", msg)
        else:
            self.gmail_lbl.configure(text="● Failed", text_color="#ef4444")
            messagebox.showerror("Failed", msg)

    def upload_resume(self):
        path = filedialog.askopenfilename(filetypes=[("Resume", "*.pdf *.docx")])
        if path:
            self.settings["resume_path"] = path
            save_settings(self.settings)
            self.resume_lbl.configure(text=f"📎 {os.path.basename(path)}", text_color="#10b981")

    def upload_file(self):
        path = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            df = pd.read_csv(path)
            inserted_ids = []
            for _, row in df.iterrows():
                r_id = insert_recruiter({
                    'recruiter_name': str(row.get('Recruiter Name', '')),
                    'company': str(row.get('Company', '')),
                    'email': str(row.get('Email', '')),
                    'job_title': str(row.get('Job Title', '')),
                    'location': str(row.get('Location', '')),
                    'experience': str(row.get('Experience', '')),
                    'skills_required': str(row.get('Skills Required', '')),
                    'jd': str(row.get('JD', ''))
                })
                if r_id:
                    inserted_ids.append(r_id)
            
            def on_done():
                messagebox.showinfo("Done", f"Loaded and generated emails for {len(df)} recruiters from CSV.")
                
            self.generate_emails_for_ids(inserted_ids, on_done)
        except Exception as ex:
            messagebox.showerror("Error", str(ex))

    # ── GENERATE ──
    def generate_free(self):
        recruits = [r for r in get_all_recruiters() if r['status'] == 'Pending']
        if not recruits:
            messagebox.showinfo("Done", "No pending recruiters.")
            return
        sig = self.settings.get("signature", "Best regards,\nSanthosh B")
        for r in recruits:
            subject, body = generate_template_email(r, sig)
            update_email_content(r['id'], subject, body)
        self.load_data()
        messagebox.showinfo("Done", f"Generated {len(recruits)} personalized emails (free).")

    # ── SEND ALL ──
    def send_all(self):
        email = self.settings.get("gmail_email", "")
        pw = self.settings.get("gmail_app_password", "")
        resume = self.settings.get("resume_path", "")
        if not email or not pw:
            messagebox.showerror("Not Connected", "Set Gmail in Settings first.")
            return
        recruits = [r for r in get_all_recruiters() if r['status'] == 'Generated']
        if not recruits:
            messagebox.showinfo("Nothing", "No generated emails to send.")
            return
        
        # Hide the main table and scrollbar
        self.tree.grid_remove()
        self.sb2.grid_remove()
        
        # Clear any existing widgets in the preview frame
        for w in self.preview_frame.winfo_children():
            w.destroy()
            
        # Display the preview frame in the exact location of the table
        self.preview_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")
        
        delay = int(self.settings.get("delay_between_emails", 3))
        res_name = os.path.basename(resume) if resume else "None"
        
        # Define actions first so button commands can resolve them
        def close_preview():
            self.preview_frame.grid_remove()
            self.tree.grid(row=1, column=0, sticky="nsew")
            self.sb2.grid(row=1, column=1, sticky="ns")
            self.load_data()
            
        def on_confirm():
            close_preview()
            def task():
                self.status_lbl.configure(text="Sending...")
                attachments = [resume] if resume and os.path.exists(resume) else []
                sent = 0
                for r in recruits:
                    recipient = r.get('email', '').strip()
                    # Skip placeholder or invalid emails
                    if not recipient or "enter-email" in recipient.lower() or "@" not in recipient or "." not in recipient:
                        update_status(r['id'], 'Failed')
                        log_event(recipient, r['company'], r['generated_subject'], 'Failed', 'Skipped: No valid recruiter email found')
                        self.after(0, self.load_data)
                        continue
                        
                    update_status(r['id'], 'Sending')
                    self.after(0, self.load_data)
                    ok, msg = send_email(email, pw, recipient, r['generated_subject'],
                                         r['generated_body'], "plain", attachments)
                    if ok:
                        update_status(r['id'], 'Sent')
                        log_event(recipient, r['company'], r['generated_subject'], 'Sent')
                        sent += 1
                    else:
                        update_status(r['id'], 'Failed')
                        log_event(recipient, r['company'], r['generated_subject'], 'Failed', msg)
                    self.after(0, self.load_data)
                    time.sleep(delay)
                self.after(0, lambda: self.status_lbl.configure(text="Ready"))
                self.after(0, lambda: messagebox.showinfo("Done", f"Sent {sent}/{len(recruits)} emails."))
            threading.Thread(target=task, daemon=True).start()

        # Header Row
        hdr = ctk.CTkFrame(self.preview_frame, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=(6, 4))
        
        ctk.CTkLabel(hdr, text="🚀 Bulk Outreach Outbox & Confirmation",
                     font=ctk.CTkFont(size=15, weight="bold"), text_color="#4f46e5").pack(side="left")
        ctk.CTkLabel(hdr, text=f"• Review all {len(recruits)} drafts. Select any row to inspect.",
                     font=ctk.CTkFont(size=11), text_color="#4b5563").pack(side="left", padx=12)
                     
        # 3. Controls / Buttons Frame (PACK FIRST AT BOTTOM TO GUARANTEE VISIBILITY)
        btn_f = ctk.CTkFrame(self.preview_frame, fg_color="transparent")
        btn_f.pack(side="bottom", fill="x", padx=10, pady=(4, 8))
        
        ctk.CTkLabel(btn_f, text=f"• Delay: {delay}s | Attachment: 📎 {res_name}",
                     font=ctk.CTkFont(size=11), text_color="#4b5563").pack(side="left", padx=10)
                     
        ctk.CTkButton(btn_f, text="Cancel", command=close_preview,
                      fg_color="#e5e7eb", hover_color="#d1d5db", text_color="#1f2937", height=38, width=100).pack(side="right", padx=6)
                      
        ctk.CTkButton(btn_f, text=f"🚀 Confirm & Send All ({len(recruits)})", command=on_confirm,
                      fg_color="#dc2626", hover_color="#ef4444", height=38,
                      font=ctk.CTkFont(size=13, weight="bold")).pack(side="right", padx=6)

        # 2. Detailed Inspect Card (PACK SECOND AT BOTTOM)
        card = ctk.CTkFrame(self.preview_frame, fg_color="#f9fafb", border_color="#e5e7eb", border_width=1, corner_radius=8)
        card.pack(side="bottom", fill="x", padx=10, pady=5)
        
        detail_header = ctk.CTkFrame(card, fg_color="transparent")
        detail_header.pack(fill="x", padx=14, pady=(8, 4))
        
        # To Label
        to_lbl = ctk.CTkLabel(detail_header, text="To: Select a row to preview", font=ctk.CTkFont(size=11, weight="bold"), text_color="#1f2937")
        to_lbl.pack(side="left")
        
        # Subject Label
        sub_f = ctk.CTkFrame(card, fg_color="transparent")
        sub_f.pack(fill="x", padx=14, pady=2)
        sub_lbl = ctk.CTkLabel(sub_f, text="Subject: —", font=ctk.CTkFont(size=11), text_color="#4b5563")
        sub_lbl.pack(side="left")
        
        # Scrollable textbox for body inspection
        body_box = ctk.CTkTextbox(card, height=120, fg_color="#ffffff", border_color="#e5e7eb", border_width=1, text_color="#1f2937")
        body_box.pack(fill="x", padx=14, pady=4)
        body_box.insert("1.0", "Double-click or click any row in the table above to view the full email draft content here.")
        body_box.configure(state="disabled")
        
        # 1. Outbox Table Frame (PACK LAST TO OCCUPY REMAINING TOP SPACE)
        tbl_frame = ctk.CTkFrame(self.preview_frame, fg_color="transparent")
        tbl_frame.pack(fill="both", expand=True, padx=10, pady=4)
        
        # Style outbox table
        style = ttk.Style()
        style.configure("Outbox.Treeview", background="#ffffff", foreground="#1f2937", 
                        fieldbackground="#ffffff", rowheight=24, borderwidth=0)
        style.configure("Outbox.Treeview.Heading", background="#f3f4f6", foreground="#4f46e5",
                        borderwidth=0, font=("Segoe UI", 9, "bold"))
        style.map("Outbox.Treeview", background=[("selected", "#e0e7ff")])
        
        columns = ("num", "recipient", "company", "role", "subject", "preview")
        outbox_tree = ttk.Treeview(tbl_frame, columns=columns, show="headings", style="Outbox.Treeview", height=6)
        outbox_tree.heading("num", text="#")
        outbox_tree.heading("recipient", text="Recipient")
        outbox_tree.heading("company", text="Company")
        outbox_tree.heading("role", text="Role")
        outbox_tree.heading("subject", text="Subject")
        outbox_tree.heading("preview", text="Body Preview")
        
        outbox_tree.column("num", width=40, anchor="center")
        outbox_tree.column("recipient", width=200, anchor="w")
        outbox_tree.column("company", width=120, anchor="w")
        outbox_tree.column("role", width=150, anchor="w")
        outbox_tree.column("subject", width=220, anchor="w")
        outbox_tree.column("preview", width=350, anchor="w")
        
        outbox_tree.pack(side="left", fill="both", expand=True)
        
        sb = ctk.CTkScrollbar(tbl_frame, command=outbox_tree.yview)
        sb.pack(side="right", fill="y")
        outbox_tree.configure(yscrollcommand=sb.set)
        
        # Populate the table
        for idx, r in enumerate(recruits):
            body_clean = " ".join((r.get('generated_body') or "").split())
            body_snippet = body_clean[:80] + "..." if len(body_clean) > 80 else body_clean
            outbox_tree.insert("", "end", iid=str(r['id']), values=(
                idx + 1,
                r.get('email', ''),
                r.get('company', ''),
                r.get('job_title', ''),
                r.get('generated_subject', ''),
                body_snippet
            ))
            
        # Selection event handler
        def on_select(event):
            selected = outbox_tree.selection()
            if not selected:
                return
            rid = selected[0]
            # Find the recruit details
            r = next((x for x in recruits if str(x['id']) == rid), None)
            if r:
                to_lbl.configure(text=f"To: {r.get('recruiter_name')} <{r.get('email')}> ({r.get('company')})")
                sub_lbl.configure(text=f"Subject: {r.get('generated_subject')}")
                body_box.configure(state="normal")
                body_box.delete("1.0", "end")
                body_box.insert("1.0", r.get('generated_body') or "")
                body_box.configure(state="disabled")
                
        outbox_tree.bind("<<TreeviewSelect>>", on_select)
        
        # Select first row by default
        if recruits:
            first_iid = str(recruits[0]['id'])
            outbox_tree.selection_set(first_iid)
            on_select(None)

    def retry_failed(self):
        email = self.settings.get("gmail_email", "")
        pw = self.settings.get("gmail_app_password", "")
        resume = self.settings.get("resume_path", "")
        if not email or not pw:
            messagebox.showerror("Error", "Set Gmail in Settings.")
            return
        failed = [r for r in get_all_recruiters() if r['status'] == 'Failed']
        if not failed:
            messagebox.showinfo("Nothing", "No failed emails.")
            return
        def task():
            self.status_lbl.configure(text="Retrying Failed...", text_color="#ef4444")
            attachments = [resume] if resume and os.path.exists(resume) else []
            for r in failed:
                recipient = r.get('email', '').strip()
                # Skip placeholder or invalid emails
                if not recipient or "enter-email" in recipient.lower() or "@" not in recipient or "." not in recipient:
                    update_status(r['id'], 'Failed')
                    log_event(recipient, r['company'], r['generated_subject'], 'Failed', 'Skipped: No valid recruiter email found')
                    self.after(0, self.load_data)
                    continue
                    
                ok, msg = send_email(email, pw, recipient, r['generated_subject'],
                                   r['generated_body'], "plain", attachments)
                update_status(r['id'], 'Sent' if ok else 'Failed')
                log_event(recipient, r['company'], r['generated_subject'], 'Sent' if ok else 'Failed', "" if ok else msg)
                self.after(0, self.load_data)
                time.sleep(3)
            self.status_lbl.configure(text="Ready", text_color="#4b5563")
        threading.Thread(target=task, daemon=True).start()

    def generate_emails_for_ids(self, ids, on_complete):
        self.status_lbl.configure(text="Generating emails...", text_color="#2563eb")
        def task():
            sig = self.settings.get("signature", "Best regards,\nSanthosh B")
            api_key = self.settings.get("openai_api_key", "")
            for r_id in ids:
                r_dict = next((x for x in get_all_recruiters() if x['id'] == r_id), None)
                if r_dict:
                    subject, body = generate_template_email(r_dict, sig, api_key=api_key)
                    update_email_content(r_id, subject, body)
            def done():
                self.load_data()
                self.status_lbl.configure(text="Ready", text_color="#4b5563")
                on_complete()
            self.after(0, done)
        threading.Thread(target=task, daemon=True).start()

    def show_sent_history(self):
        top = ctk.CTkToplevel(self)
        top.title("Sent Email History")
        top.geometry("720x620")
        top.configure(fg_color="#ffffff")
        
        # Prevent focus issue tracebacks
        def safe_focus_set():
            try:
                tk.Toplevel.focus_set(top)
            except Exception:
                pass
        top.focus_set = safe_focus_set
        top.grab_set()

        ctk.CTkLabel(top, text="📊 Sent Email History",
                     font=ctk.CTkFont(size=16, weight="bold"), text_color="#2563eb").pack(pady=(14, 4))
                      
        top_f = ctk.CTkFrame(top, fg_color="transparent")
        top_f.pack(fill="x", padx=14, pady=5)
        
        style = ttk.Style()
        style.configure("History.Treeview", background="#ffffff", foreground="#1f2937", 
                        fieldbackground="#ffffff", rowheight=24, borderwidth=0)
        style.configure("History.Treeview.Heading", background="#f3f4f6", foreground="#4f46e5",
                        borderwidth=0, font=("Segoe UI", 9, "bold"))
        style.map("History.Treeview", background=[("selected", "#e0e7ff")])
        
        tree_frame = ctk.CTkFrame(top_f, fg_color="transparent")
        tree_frame.pack(fill="both", expand=True)
        
        columns = ("date", "count")
        h_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", style="History.Treeview", height=5)
        h_tree.heading("date", text="Sent Date")
        h_tree.heading("count", text="Total Emails Sent")
        h_tree.column("date", width=250, anchor="center")
        h_tree.column("count", width=200, anchor="center")
        
        h_tree.pack(side="left", fill="both", expand=True)
        
        sb = ctk.CTkScrollbar(tree_frame, command=h_tree.yview)
        sb.pack(side="right", fill="y")
        h_tree.configure(yscrollcommand=sb.set)
        
        bot_f = ctk.CTkFrame(top, fg_color="transparent")
        bot_f.pack(fill="both", expand=True, padx=14, pady=(10, 10))
        
        ctk.CTkLabel(bot_f, text="Sent Details for Selected Date:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#4b5563").pack(anchor="w", pady=(0, 4))
        
        detail_columns = ("time", "recipient", "company", "subject")
        d_tree = ttk.Treeview(bot_f, columns=detail_columns, show="headings", style="History.Treeview", height=7)
        d_tree.heading("time", text="Time")
        d_tree.heading("recipient", text="Recipient Email")
        d_tree.heading("company", text="Company")
        d_tree.heading("subject", text="Subject")
        
        d_tree.column("time", width=80, anchor="center")
        d_tree.column("recipient", width=180, anchor="w")
        d_tree.column("company", width=120, anchor="w")
        d_tree.column("subject", width=240, anchor="w")
        
        d_tree.pack(side="left", fill="both", expand=True)
        
        d_sb = ctk.CTkScrollbar(bot_f, command=d_tree.yview)
        d_sb.pack(side="right", fill="y")
        d_tree.configure(yscrollcommand=d_sb.set)
        
        # Action controls for selected day
        act_f = ctk.CTkFrame(top, fg_color="transparent")
        act_f.pack(fill="x", padx=14, pady=(5, 14))
        
        from database import get_db
        from tkinter import filedialog
        
        def get_formatted_list(date_val):
            conn = get_db()
            rows = conn.execute('''
                SELECT recipient, subject 
                FROM logs 
                WHERE status='Sent' AND date=? 
                ORDER BY time DESC
            ''', (date_val,)).fetchall()
            conn.close()
            
            lines = []
            for r in rows:
                email_addr = r[0]
                subj = r[1]
                parts = [p.strip() for p in subj.split("|")]
                role_val = parts[1] if len(parts) >= 2 else subj
                lines.append(f"{email_addr} - {role_val}")
            return lines

        def copy_emails():
            selected = h_tree.selection()
            if not selected:
                messagebox.showwarning("Select Date", "Please select a date from the top table.")
                return
            date_val = h_tree.item(selected[0])['values'][0]
            lines = get_formatted_list(date_val)
            if not lines:
                messagebox.showinfo("No Data", f"No emails sent on {date_val}.")
                return
            
            top.clipboard_clear()
            top.clipboard_append("\n".join(lines))
            top.update()
            messagebox.showinfo("Copied", f"📋 Copied {len(lines)} emails and roles to clipboard!")

        def export_emails():
            selected = h_tree.selection()
            if not selected:
                messagebox.showwarning("Select Date", "Please select a date from the top table.")
                return
            date_val = h_tree.item(selected[0])['values'][0]
            lines = get_formatted_list(date_val)
            if not lines:
                messagebox.showinfo("No Data", f"No emails sent on {date_val}.")
                return
                
            file_path = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
                initialfile=f"sent_emails_{date_val}.txt",
                title="Export Sent Emails & Roles"
            )
            if file_path:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write("\n".join(lines))
                messagebox.showinfo("Exported", f"💾 Successfully exported list to {os.path.basename(file_path)}!")

        ctk.CTkButton(act_f, text="📋 Copy Emails & Roles", command=copy_emails,
                      fg_color="#2563eb", hover_color="#1d4ed8", font=ctk.CTkFont(size=12, weight="bold"), height=36).pack(side="left", padx=5)
                      
        ctk.CTkButton(act_f, text="💾 Export to Text File", command=export_emails,
                      fg_color="#10b981", hover_color="#059669", font=ctk.CTkFont(size=12, weight="bold"), height=36).pack(side="left", padx=5)

        def load_history():
            for row in h_tree.get_children():
                h_tree.delete(row)
            conn = get_db()
            rows = conn.execute('''
                SELECT date, COUNT(*) as count 
                FROM logs 
                WHERE status='Sent' 
                GROUP BY date 
                ORDER BY date DESC
            ''').fetchall()
            conn.close()
            for r in rows:
                h_tree.insert("", "end", values=(r[0], r[1]))
                
        def on_date_select(event):
            selected = h_tree.selection()
            if not selected:
                return
            date_val = h_tree.item(selected[0])['values'][0]
            
            for row in d_tree.get_children():
                d_tree.delete(row)
            conn = get_db()
            rows = conn.execute('''
                SELECT time, recipient, company, subject 
                FROM logs 
                WHERE status='Sent' AND date=? 
                ORDER BY time DESC
            ''', (date_val,)).fetchall()
            conn.close()
            for r in rows:
                d_tree.insert("", "end", values=(r[0], r[1], r[2], r[3]))
                
        h_tree.bind("<<TreeviewSelect>>", on_date_select)
        load_history()
        
        children = h_tree.get_children()
        if children:
            h_tree.selection_set(children[0])

    # ── PREVIEW ──
    def _on_double_click(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        self.open_preview_modal(sel[0])

    def open_preview_modal(self, r_id):
        all_r = {str(r['id']): r for r in get_all_recruiters()}
        r = all_r.get(str(r_id))
        if not r:
            return
            
        top = ctk.CTkToplevel(self)
        top.title(f"Preview & Edit — {r['recruiter_name'] or 'Hiring Team'} @ {r['company'] or 'Company'}")
        top.geometry("740x690")
        top.configure(fg_color="#ffffff")
        
        # Prevent TclError tracebacks when CustomTkinter's internal focus timers fire after window destruction
        def safe_focus_set():
            try:
                tk.Toplevel.focus_set(top)
            except Exception:
                pass
        top.focus_set = safe_focus_set
        
        top.grab_set()
        top.lift()
        top.focus_force()

        # Let's add grid/frame for recruiter details edit fields!
        det_f = ctk.CTkFrame(top, fg_color="transparent")
        det_f.pack(fill="x", padx=16, pady=(14, 5))
        
        # Row 1: Email & Name
        ctk.CTkLabel(det_f, text="Recruiter Email:", text_color="#1f2937").grid(row=0, column=0, sticky="w", padx=5, pady=4)
        email_e = ctk.CTkEntry(det_f, width=220, fg_color="#ffffff", border_color="#d1d5db", text_color="#1f2937")
        email_e.grid(row=0, column=1, sticky="w", padx=5, pady=4)
        email_e.insert(0, r['email'] or "")
        
        ctk.CTkLabel(det_f, text="Recruiter Name:", text_color="#1f2937").grid(row=0, column=2, sticky="w", padx=5, pady=4)
        name_e = ctk.CTkEntry(det_f, width=220, fg_color="#ffffff", border_color="#d1d5db", text_color="#1f2937")
        name_e.grid(row=0, column=3, sticky="w", padx=5, pady=4)
        name_e.insert(0, r['recruiter_name'] or "")

        # Row 2: Job Title & Company
        ctk.CTkLabel(det_f, text="Job Title:", text_color="#1f2937").grid(row=1, column=0, sticky="w", padx=5, pady=4)
        title_e = ctk.CTkEntry(det_f, width=220, fg_color="#ffffff", border_color="#d1d5db", text_color="#1f2937")
        title_e.grid(row=1, column=1, sticky="w", padx=5, pady=4)
        title_e.insert(0, r['job_title'] or "")
        
        ctk.CTkLabel(det_f, text="Company Name:", text_color="#1f2937").grid(row=1, column=2, sticky="w", padx=5, pady=4)
        company_e = ctk.CTkEntry(det_f, width=220, fg_color="#ffffff", border_color="#d1d5db", text_color="#1f2937")
        company_e.grid(row=1, column=3, sticky="w", padx=5, pady=4)
        company_e.insert(0, r['company'] or "")

        # Subject Line
        ctk.CTkLabel(top, text="Subject Line:", text_color="#1f2937").pack(padx=21, anchor="w")
        sub_e = ctk.CTkEntry(top, width=695, fg_color="#ffffff", border_color="#d1d5db", text_color="#1f2937")
        sub_e.pack(padx=21, pady=3)
        sub_e.insert(0, r.get('generated_subject') or "")

        # Email Body Textbox
        ctk.CTkLabel(top, text="Email Body:", text_color="#1f2937").pack(padx=21, anchor="w")
        body_b = ctk.CTkTextbox(top, width=695, height=360, fg_color="#ffffff",
                                border_color="#d1d5db", text_color="#1f2937")
        body_b.pack(padx=21, pady=3)
        body_b.insert("1.0", r.get('generated_body') or "")

        # Resume Display
        resume = self.settings.get("resume_path", "")
        ctk.CTkLabel(top, text=f"📎 Attachment: {os.path.basename(resume) if resume else 'None'}",
                      text_color="#4b5563").pack(padx=21, anchor="w", pady=2)

        # Action Buttons Frame
        bf = ctk.CTkFrame(top, fg_color="transparent")
        bf.pack(pady=(5, 12))

        def save():
            update_recruiter_details(
                r['id'],
                name_e.get().strip(),
                company_e.get().strip(),
                email_e.get().strip(),
                title_e.get().strip(),
                sub_e.get().strip(),
                body_b.get("1.0", "end-1c").strip()
            )
            self.load_data()
            top.destroy()

        def send_one():
            save()
            em = self.settings.get("gmail_email", "")
            pw2 = self.settings.get("gmail_app_password", "")
            if not em or not pw2:
                messagebox.showerror("Error", "Set Gmail in Settings.")
                return
            
            # Fetch latest edited fields to send
            fresh = {str(x['id']): x for x in get_all_recruiters()}.get(str(r['id']))
            if not fresh:
                return
                
            att = [resume] if resume and os.path.exists(resume) else []
            ok, msg = send_email(em, pw2, fresh['email'], fresh['generated_subject'],
                                 fresh['generated_body'], "plain", att)
            update_status(r['id'], 'Sent' if ok else 'Failed')
            self.load_data()
            messagebox.showinfo("Result", f"{'Sent!' if ok else 'Failed: ' + msg}")

        ctk.CTkButton(bf, text="Save Details", command=save, fg_color="#e5e7eb", hover_color="#d1d5db", text_color="#1f2937", width=120, height=35).pack(side="left", padx=6)
        ctk.CTkButton(bf, text="🚀 Send Email", command=send_one, fg_color="#dc2626", hover_color="#b91c1c", text_color="#ffffff", width=120, height=35).pack(side="left", padx=6)

    def clear_data(self):
        if messagebox.askyesno("Clear", "Delete ALL data?"):
            delete_all_recruiters()
            self.load_data()

    def open_settings(self):
        top = ctk.CTkToplevel(self)
        top.title("Settings")
        top.geometry("500x460")
        top.configure(fg_color="#ffffff")
        
        # Prevent TclError tracebacks when CustomTkinter's internal focus timers fire after window destruction
        def safe_focus_set():
            try:
                tk.Toplevel.focus_set(top)
            except Exception:
                pass
        top.focus_set = safe_focus_set
        
        top.grab_set()
        top.lift()
        top.focus_force()

        fields = [
            ("Gmail Email:", "gmail_email"),
            ("Gmail App Password:", "gmail_app_password"),
            ("OpenAI API Key (optional):", "openai_api_key"),
            ("Signature:", "signature"),
            ("Delay Between Emails (sec):", "delay_between_emails"),
        ]
        entries = {}
        for label, key in fields:
            ctk.CTkLabel(top, text=label, text_color="#1f2937").pack(anchor="w", padx=14, pady=(8, 0))
            e = ctk.CTkEntry(top, width=470, fg_color="#ffffff", border_color="#d1d5db", text_color="#1f2937")
            e.pack(padx=14, pady=2)
            e.insert(0, str(self.settings.get(key, "")))
            entries[key] = e

        def save():
            for k, w in entries.items():
                self.settings[k] = w.get()
            save_settings(self.settings)
            top.destroy()
            messagebox.showinfo("Saved", "Settings saved.")

        ctk.CTkButton(top, text="Save Settings", command=save, fg_color="#059669", hover_color="#10b981").pack(pady=14)
