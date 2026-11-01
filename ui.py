import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import json
import threading
import os
import pandas as pd

import candidate_store as cs
import knowledge as kb
import pipeline
from database import (init_db, get_all_recruiters, get_recruiter, get_report, delete_all_recruiters,
                      insert_recruiters_bulk, update_record, get_send_history, get_today_sent_by_candidate)
from email_composer import ctc_line, signature_block
from filters import ELIGIBLE, FilterConfig
from jd_analyzer import analyze_jd, format_jd_analysis, parse_experience
from resume_parser import format_profile
from send_pipeline import send_eligible
from settings import load_settings, save_settings

GREEN, RED, ORANGE, BLUE, GRAY = "#10b981", "#ef4444", "#f59e0b", "#2563eb", "#6b7280"
INDIGO = "#4f46e5"


class AppUI(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"{kb.APP_NAME} — {kb.APP_TAGLINE}")
        self.geometry("1420x900")
        self.minsize(1180, 760)
        init_db()
        self.settings = load_settings()
        self.cid = cs.get_active_candidate_id()
        if self.cid is not None and self.settings.get("active_candidate_id") != self.cid:
            cs.set_active_candidate(self.cid)
            self.settings = load_settings()
        ctk.set_appearance_mode("Light")
        self.configure(fg_color="#ffffff")
        self.counts = {}
        # background send jobs, one per candidate: cid -> {name, kind, total, done, sent, failed, skipped,
        # current, running, stop}.  Switching the selected candidate never touches a running job.
        self.jobs = {}
        self._ticking = False
        self._build()
        self.load_data()

    # ── helpers ──────────────────────────────────────────────────────────
    def _top(self, title, geometry):
        top = ctk.CTkToplevel(self)
        top.title(title)
        top.geometry(geometry)
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
        return top

    def _ctx(self):
        return pipeline.load_context(self.cid) if self.cid is not None else None

    def _filter_cfg(self) -> FilterConfig:
        return FilterConfig.from_settings(self.settings.get("send_filters"))

    def _set_status(self, text, color="#4b5563"):
        self.after(0, lambda: self.status_lbl.configure(text=text, text_color=color))

    def _section(self, parent, text):
        ctk.CTkLabel(parent, text=f"── {text} ──", text_color="#9ca3af", font=ctk.CTkFont(size=10)).pack(pady=(8, 2))

    def _btn(self, parent, text, cmd, primary=None, height=28, **kw):
        if primary:
            b = ctk.CTkButton(parent, text=text, height=height, command=cmd, fg_color=primary[0],
                              hover_color=primary[1], **kw)
        else:
            b = ctk.CTkButton(parent, text=text, height=height, command=cmd, fg_color="#e5e7eb",
                              hover_color="#d1d5db", text_color="#1f2937", **kw)
        b.pack(fill="x", padx=14, pady=3)
        return b

    # ── layout ───────────────────────────────────────────────────────────
    def _build(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # ── SIDEBAR ──
        sb = ctk.CTkScrollableFrame(self, width=230, corner_radius=0, fg_color="#f3f4f6")
        sb.grid(row=0, column=0, sticky="nsew")

        ctk.CTkLabel(sb, text=f"✈ {kb.APP_NAME}", font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=INDIGO).pack(pady=(14, 0), padx=14)
        ctk.CTkLabel(sb, text=kb.APP_TAGLINE, font=ctk.CTkFont(size=10), text_color="#4b5563").pack(pady=(0, 6))

        # Candidate
        self._section(sb, "Candidate")
        self.cand_var = tk.StringVar(value="")
        self.cand_menu = ctk.CTkOptionMenu(sb, values=["—"], variable=self.cand_var, command=self._on_candidate_pick,
                                           fg_color="#ffffff", text_color="#1f2937", button_color="#c7d2fe",
                                           button_hover_color="#a5b4fc", dynamic_resizing=False, width=200)
        self.cand_menu.pack(fill="x", padx=14, pady=3)
        self.cand_status_btn = ctk.CTkButton(sb, text="🔴 CANDIDATE NOT READY", height=30,
                                             command=self.show_candidate_status, fg_color="#fee2e2",
                                             hover_color="#fecaca", text_color="#991b1b",
                                             font=ctk.CTkFont(size=11, weight="bold"))
        self.cand_status_btn.pack(fill="x", padx=14, pady=3)
        self._btn(sb, "👤 Candidate Setup", self.open_candidate_setup, (INDIGO, "#6366f1"), 32)
        self._btn(sb, "🧩 Template Library", self.open_template_library, ("#7c3aed", "#8b5cf6"), 30)

        # Gmail
        self._section(sb, "Gmail")
        self.gmail_lbl = ctk.CTkLabel(sb, text="● Not Connected", text_color=RED, font=ctk.CTkFont(size=11),
                                      wraplength=200)
        self.gmail_lbl.pack(pady=3)
        self._btn(sb, "Connect & Test Gmail", self.connect_gmail, ("#059669", GREEN), 30)

        # Resume
        self._section(sb, "Resume")
        self.resume_lbl = ctk.CTkLabel(sb, text="No resume", text_color="#4b5563", font=ctk.CTkFont(size=10),
                                       wraplength=200)
        self.resume_lbl.pack(pady=2)
        self._btn(sb, "Upload Resume", self.upload_resume)

        # Actions
        self._section(sb, "Actions")
        self._btn(sb, "📋 Paste LinkedIn Jobs", self.open_paste_window, (INDIGO, "#6366f1"), 32)
        self._btn(sb, "📁 Upload CSV File", self.upload_file, ("#1e40af", "#3b82f6"))
        self._btn(sb, "♻ Regenerate Drafts", self.regenerate_drafts)

        # Send
        self._section(sb, "Send")
        self.side_send_btn = ctk.CTkButton(sb, text="🚀 SEND ELIGIBLE EMAILS", height=36, command=self.send_all,
                                           fg_color="#dc2626", hover_color=RED,
                                           font=ctk.CTkFont(size=12, weight="bold"))
        self.side_send_btn.pack(fill="x", padx=14, pady=6)
        self._btn(sb, "Retry Failed", self.retry_failed, height=26)

        # History
        self._section(sb, "Send History")
        self.today_lbl = ctk.CTkLabel(sb, text="", text_color="#047857", font=ctk.CTkFont(size=10),
                                      justify="left", wraplength=200)
        self.today_lbl.pack(pady=2)
        self._btn(sb, "📅 Daily History (all candidates)", self.show_candidate_history, ("#0f766e", "#14b8a6"), 28)

        # Other
        self._section(sb, "Other")
        self._btn(sb, "Settings", self.open_settings, height=26)
        self._btn(sb, "Clear All", self.clear_data, height=26)
        self.status_lbl = ctk.CTkLabel(sb, text="Ready", text_color="#4b5563", font=ctk.CTkFont(size=10),
                                       wraplength=200)
        self.status_lbl.pack(pady=10)

        # ── MAIN ──
        main = ctk.CTkFrame(self, fg_color="#ffffff")
        main.grid(row=0, column=1, sticky="nsew", padx=12, pady=10)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=1)
        self.main = main

        # Who am I sending as?
        self.identity_frame = ctk.CTkFrame(main, fg_color="#eef2ff", corner_radius=10)
        self.identity_frame.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self.identity_lbl = ctk.CTkLabel(self.identity_frame, text="", justify="left", anchor="w",
                                         font=ctk.CTkFont(size=12), text_color="#1e1b4b")
        self.identity_lbl.pack(side="left", padx=12, pady=8, fill="x", expand=True)

        # Stats
        self.stats_frame = ctk.CTkFrame(main, fg_color="#f9fafb", corner_radius=10, border_color="#e5e7eb",
                                        border_width=1)
        self.stats_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 8))

        # Table
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("E.Treeview", background="#ffffff", foreground="#1f2937",
                        fieldbackground="#ffffff", rowheight=28, borderwidth=0, font=("Segoe UI", 9))
        style.configure("E.Treeview.Heading", background="#f3f4f6", foreground=INDIGO,
                        borderwidth=0, font=("Segoe UI", 9, "bold"))
        style.map("E.Treeview", background=[("selected", "#e0e7ff")])

        cols = ("ID", "Recruiter", "Company", "Role", "Location", "Experience", "Email", "Template", "Match",
                "Filter Status", "Quality", "Send Status")
        self.tree = ttk.Treeview(main, columns=cols, show="headings", style="E.Treeview", selectmode="extended")
        widths = {"ID": 40, "Recruiter": 105, "Company": 120, "Role": 160, "Location": 95, "Experience": 75,
                  "Email": 170, "Template": 120, "Match": 55, "Filter Status": 185, "Quality": 105,
                  "Send Status": 80}
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=widths.get(c, 100), minwidth=35)
        self.tree.tag_configure("ready", foreground="#047857")
        self.tree.tag_configure("filtered", foreground="#9ca3af")
        self.tree.tag_configure("review", foreground="#b45309")
        self.tree.tag_configure("sent", foreground="#1d4ed8")
        self.tree.tag_configure("failed", foreground="#b91c1c")
        self.tree.grid(row=2, column=0, sticky="nsew")
        self.tree.bind("<Double-1>", self._on_double_click)

        self.sb2 = ctk.CTkScrollbar(main, command=self.tree.yview)
        self.sb2.grid(row=2, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=self.sb2.set)

        self.preview_frame = ctk.CTkFrame(main, fg_color="#ffffff")
        # Grid layout will be dynamically toggled during bulk outreach confirmation

        self.paste_frame = ctk.CTkFrame(main, fg_color="#ffffff")
        # Grid layout will be dynamically toggled during paste LinkedIn jobs

        # SEND FILTERS (always above the send action)
        self.filter_frame = ctk.CTkFrame(main, fg_color="#f9fafb", corner_radius=10, border_color="#e5e7eb",
                                         border_width=1)
        self.filter_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self._build_filters()

        bot = ctk.CTkFrame(main, fg_color="transparent")
        bot.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        ctk.CTkLabel(bot, text="Double-click a row to preview / edit  |  Paste LinkedIn → auto-match template → "
                               "Apply Filters → SEND ELIGIBLE EMAILS",
                     text_color=GRAY, font=ctk.CTkFont(size=10)).pack(side="left", padx=4)

    def _show_table(self):
        self.paste_frame.grid_remove()
        self.preview_frame.grid_remove()
        self.tree.grid(row=2, column=0, sticky="nsew")
        self.sb2.grid(row=2, column=1, sticky="ns")
        self.filter_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))

    def _hide_table(self):
        self.tree.grid_remove()
        self.sb2.grid_remove()
        self.filter_frame.grid_remove()

    # ── SEND FILTERS ─────────────────────────────────────────────────────
    def _build_filters(self):
        f = self.filter_frame
        for w in f.winfo_children():
            w.destroy()
        cfg = self._filter_cfg()
        ctk.CTkLabel(f, text="SEND FILTERS", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=INDIGO).grid(row=0, column=0, sticky="w", padx=12, pady=(8, 2))

        # Location
        loc = ctk.CTkFrame(f, fg_color="transparent")
        loc.grid(row=1, column=0, sticky="nw", padx=12)
        ctk.CTkLabel(loc, text="Location:", font=ctk.CTkFont(size=11, weight="bold")).grid(row=0, column=0, sticky="w")
        self.all_cities_var = tk.BooleanVar(value=cfg.all_cities)
        ctk.CTkCheckBox(loc, text="All Cities", variable=self.all_cities_var, command=self._on_all_cities,
                        checkbox_width=16, checkbox_height=16, font=ctk.CTkFont(size=11)).grid(
            row=0, column=1, sticky="w", padx=4, pady=2)
        cities = list(kb.DEFAULT_FILTER_CITIES)
        if self.cid is not None:
            from filters import job_cities
            for r in get_all_recruiters(self.cid):
                for c in job_cities(r):
                    if c not in cities:
                        cities.append(c)
        for c in cfg.cities:
            if c not in cities:
                cities.append(c)
        self.city_vars = {}
        per_row = 8
        for i, c in enumerate(cities):
            var = tk.BooleanVar(value=c in cfg.cities)
            self.city_vars[c] = var
            ctk.CTkCheckBox(loc, text=c, variable=var, command=self._on_city, checkbox_width=16, width=100,
                            checkbox_height=16, font=ctk.CTkFont(size=11)).grid(
                row=(i + 1) // per_row, column=(i + 1) % per_row + 1, sticky="w", padx=2, pady=2)

        # Experience
        exp = ctk.CTkFrame(f, fg_color="transparent")
        exp.grid(row=2, column=0, sticky="nw", padx=12, pady=(4, 8))
        ctk.CTkLabel(exp, text="Experience:", font=ctk.CTkFont(size=11, weight="bold")).grid(row=0, column=0, sticky="w")
        self.exp_mode_var = tk.StringVar(value=cfg.exp_mode if cfg.exp_mode else "All Experience")
        labels = [b[0] for b in kb.EXPERIENCE_BUCKETS] + ["Custom"]
        for i, label in enumerate(labels):
            ctk.CTkRadioButton(exp, text=label, variable=self.exp_mode_var, value=label, radiobutton_width=14,
                               width=100, radiobutton_height=14, font=ctk.CTkFont(size=11)).grid(
                row=0, column=i + 1, sticky="w", padx=2, pady=2)
        cust = ctk.CTkFrame(exp, fg_color="transparent")
        cust.grid(row=1, column=1, columnspan=7, sticky="w")
        ctk.CTkLabel(cust, text="Custom  Min", font=ctk.CTkFont(size=11)).pack(side="left")
        self.exp_min_e = ctk.CTkEntry(cust, width=50, height=24)
        self.exp_min_e.pack(side="left", padx=4)
        ctk.CTkLabel(cust, text="Max", font=ctk.CTkFont(size=11)).pack(side="left")
        self.exp_max_e = ctk.CTkEntry(cust, width=50, height=24)
        self.exp_max_e.pack(side="left", padx=4)
        ctk.CTkLabel(cust, text="years (blank max = no limit)", font=ctk.CTkFont(size=10),
                     text_color=GRAY).pack(side="left")
        if cfg.exp_mode == "Custom":
            if cfg.exp_min is not None:
                self.exp_min_e.insert(0, f"{cfg.exp_min:g}")
            if cfg.exp_max is not None:
                self.exp_max_e.insert(0, f"{cfg.exp_max:g}")

        # Counters + actions
        act = ctk.CTkFrame(f, fg_color="#eef2ff", corner_radius=8)
        act.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 8))
        f.grid_columnconfigure(0, weight=1)
        ctk.CTkButton(act, text="Apply Filters", command=self.apply_filters, width=130, height=34,
                      fg_color=INDIGO, hover_color="#6366f1").pack(side="left", padx=8, pady=6)
        self.counts_lbl = ctk.CTkLabel(act, text="", justify="left", font=ctk.CTkFont(size=12),
                                       text_color="#1f2937")
        self.counts_lbl.pack(side="left", padx=8)
        self.send_btn = ctk.CTkButton(act, text="🚀 SEND ELIGIBLE EMAILS (0)", command=self.send_all, width=260,
                                      height=38, fg_color="#dc2626", hover_color=RED,
                                      font=ctk.CTkFont(size=13, weight="bold"))
        self.send_btn.pack(side="right", padx=8, pady=6)

    def _on_all_cities(self):
        if self.all_cities_var.get():
            for v in self.city_vars.values():
                v.set(False)
        elif not any(v.get() for v in self.city_vars.values()):
            self.all_cities_var.set(True)

    def _on_city(self):
        self.all_cities_var.set(not any(v.get() for v in self.city_vars.values()))

    def _read_filters(self) -> FilterConfig | None:
        cities = [] if self.all_cities_var.get() else [c for c, v in self.city_vars.items() if v.get()]
        mode = self.exp_mode_var.get()
        if mode == "Custom":
            try:
                lo = float(self.exp_min_e.get()) if self.exp_min_e.get().strip() else 0.0
                hi = float(self.exp_max_e.get()) if self.exp_max_e.get().strip() else None
            except ValueError:
                messagebox.showerror("Experience Filter", "Custom min / max must be numbers (years).")
                return None
            if hi is not None and hi < lo:
                messagebox.showerror("Experience Filter", "Maximum must be greater than minimum.")
                return None
            return FilterConfig(cities=cities, exp_min=lo, exp_max=hi, exp_mode="Custom")
        return FilterConfig.from_settings({"cities": cities, "exp_mode": mode})

    def apply_filters(self, quiet=False):
        cfg = self._read_filters()
        if cfg is None:
            return None
        self.settings["send_filters"] = cfg.to_settings()
        save_settings(self.settings)
        self.load_data()
        if not quiet:
            self._set_status(f"Filters applied — {cfg.describe()}", BLUE)
        return cfg

    # ── data refresh ─────────────────────────────────────────────────────
    def _build_stats(self):
        for w in self.stats_frame.winfo_children():
            w.destroy()
        r = get_report(self.cid) if self.cid is not None else get_report(-1)
        items = [("Total", r["total"], "#1f2937"), ("Pending", r["pending"], ORANGE),
                 ("Generated", r["generated"], "#a78bfa"), ("Sent", r["sent"], GREEN),
                 ("Failed", r["failed"], RED), ("Sending", r["sending"], "#60a5fa")]

        # Left container for stats
        left_f = ctk.CTkFrame(self.stats_frame, fg_color="transparent")
        left_f.pack(side="left", fill="y", padx=10)

        for label, val, color in items:
            f = ctk.CTkFrame(left_f, fg_color="transparent")
            f.pack(side="left", padx=14, pady=6)
            ctk.CTkLabel(f, text=str(val), font=ctk.CTkFont(size=20, weight="bold"), text_color=color).pack()
            ctk.CTkLabel(f, text=label, font=ctk.CTkFont(size=10), text_color="#4b5563").pack()
            if label == "Failed" and val > 0:
                ctk.CTkButton(f, text="🔄 Retry", font=ctk.CTkFont(size=9, weight="bold"),
                              width=45, height=16, fg_color=RED, hover_color="#dc2626", text_color="#ffffff",
                              command=self.retry_failed).pack(pady=(2, 0))

        # Right container for operations (History, Refresh & Reset)
        right_f = ctk.CTkFrame(self.stats_frame, fg_color="transparent")
        right_f.pack(side="right", fill="y", padx=16, pady=6)

        # live sending progress (filled by _render_progress)
        self.progress_box = ctk.CTkFrame(right_f, fg_color="transparent")
        self.progress_box.pack(side="left", padx=(0, 16))
        self._render_progress()

        hist_f = ctk.CTkFrame(right_f, fg_color="transparent")
        hist_f.pack(side="left", padx=(0, 16))
        ctk.CTkLabel(hist_f, text=f"Today: {r.get('today_sent', 0)}", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#047857").pack(anchor="e")
        ctk.CTkLabel(hist_f, text=f"This Week: {r.get('weekly_sent', 0)}", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#4338ca").pack(anchor="e")
        ctk.CTkButton(hist_f, text="📊 View History", font=ctk.CTkFont(size=9, weight="bold", underline=True),
                      width=90, height=20, fg_color="transparent", text_color=BLUE, hover_color="#f3f4f6",
                      command=self.show_sent_history).pack(anchor="e", pady=(2, 0))

        ctk.CTkButton(right_f, text="🔄 Refresh", font=ctk.CTkFont(size=11, weight="bold"),
                      width=90, height=30, fg_color="#e5e7eb", hover_color="#d1d5db", text_color="#1f2937",
                      command=self.load_data).pack(side="left", padx=6)
        ctk.CTkButton(right_f, text="🧹 Reset All", font=ctk.CTkFont(size=11, weight="bold"),
                      width=90, height=30, fg_color="#dc2626", hover_color=RED,
                      command=self.clear_data).pack(side="left", padx=6)

    def _refresh_sidebar(self, ctx):
        cands = cs.list_candidates()
        labels = [f"#{c['id']}  {c['name'] or 'Unnamed'}" for c in cands] or ["— No candidate —"]
        self.cand_menu.configure(values=labels + ["➕ New Candidate…"])
        cur = next((l for l, c in zip(labels, cands) if c["id"] == self.cid), labels[0])
        self.cand_var.set(cur)

        if ctx is None:
            self.cand_status_btn.configure(text="🔴 NO CANDIDATE — SET UP", fg_color="#fee2e2", text_color="#991b1b")
            self.gmail_lbl.configure(text="● Not Connected", text_color=RED)
            self.resume_lbl.configure(text="No resume", text_color="#4b5563")
            self.identity_lbl.configure(text="No candidate configured.  Click “👤 Candidate Setup” to create one "
                                             "(resume, Gmail App Password, CTC and 5 example templates).")
            return
        c, rd = ctx.candidate, ctx.readiness
        if rd["ready"]:
            self.cand_status_btn.configure(text="🟢 CANDIDATE READY TO SEND", fg_color="#d1fae5",
                                           hover_color="#a7f3d0", text_color="#065f46")
        else:
            self.cand_status_btn.configure(text=f"🔴 NOT READY ({len(rd['missing'])} missing)", fg_color="#fee2e2",
                                           hover_color="#fecaca", text_color="#991b1b")
        gm = c.get("gmail_address") or ""
        if rd["gmail_connected"]:
            self.gmail_lbl.configure(text=f"🟢 Gmail Connected\n{gm}", text_color="#047857")
        else:
            self.gmail_lbl.configure(text=f"● Not Connected{(chr(10) + gm) if gm else ''}", text_color=RED)
        resume = c.get("resume_path") or ""
        n_tpl_res = sum(cs.template_has_resume(t) for t in cs.get_templates(c["id"]))
        tpl_note = f"\n📎 Template resumes: {n_tpl_res}/5" if n_tpl_res else ""
        if resume and os.path.exists(resume):
            self.resume_lbl.configure(text=f"🟢 Resume Ready\n📎 {c.get('resume_original_name') or os.path.basename(resume)}"
                                           f"{tpl_note}", text_color="#047857")
        elif n_tpl_res:
            self.resume_lbl.configure(text=f"🟢 Per-template resumes{tpl_note}", text_color="#047857")
        else:
            self.resume_lbl.configure(text="No resume", text_color="#4b5563")
        self.identity_lbl.configure(text=(
            f"Sending as: {c.get('name') or '—'}  <{gm or 'Gmail not set'}>  "
            f"{'🟢 Gmail Connected' if rd['gmail_connected'] else '🔴 Gmail not connected'}"
            f"      Status: {'🟢 CANDIDATE READY TO SEND' if rd['ready'] else '🔴 CANDIDATE NOT READY'}\n"
            f"Resume: 📎 {c.get('resume_original_name') or '—'}      Templates: {rd['templates_configured']}/5"
            f"      {ctc_line(c)}"))

    def load_data(self):
        self.settings = load_settings()
        ctx = self._ctx()
        cfg = self._filter_cfg()
        self.counts = pipeline.refresh_statuses(ctx, cfg) if ctx else {}
        for row in self.tree.get_children():
            self.tree.delete(row)
        if ctx:
            for r in get_all_recruiters(self.cid):
                send = pipeline.send_status_label(r)
                if r["status"] == "Sent":
                    tag = "sent"
                elif r["status"] == "Failed":
                    tag = "failed"
                elif r.get("filter_status") != ELIGIBLE:
                    tag = "filtered"
                elif (r.get("quality_status") or "").startswith("Ready"):
                    tag = "ready"
                else:
                    tag = "review"
                q = r.get("quality_status") or ""
                q = ("🟢 " + q) if q.startswith("Ready") else (("🟠 " + q) if q else "")
                exp = r.get("experience") or "—"
                self.tree.insert("", "end", iid=str(r["id"]), tags=(tag,), values=(
                    r["id"], r["recruiter_name"] or "Hiring Team", r["company"] or "—", r["job_title"] or "—",
                    r["location"] or "—", exp, r["email"] or "(no email)", r.get("template_name") or "—",
                    f"{r['template_match_score']}%" if r.get("template_match_score") is not None else "—",
                    r.get("filter_status") or "—", q, send))
        self._build_stats()
        self._refresh_sidebar(ctx)
        today = get_today_sent_by_candidate()
        self.today_lbl.configure(text=("Today sent:\n" + "\n".join(f"• {t['name']}: {t['sent']}" for t in today))
                                 if today else "No emails sent today")
        k = self.counts
        if hasattr(self, "counts_lbl"):
            self.counts_lbl.configure(text=(
                f"Total Jobs: {k.get('total', 0)}   Location Eligible: {k.get('location_eligible', 0)}   "
                f"Experience Eligible: {k.get('experience_eligible', 0)}\n"
                f"Ready to Send: {k.get('ready', 0)}   Filtered Out: {k.get('filtered', 0)}   "
                f"Needs Review: {k.get('needs_review', 0)}   Sent: {k.get('sent', 0)}"))
            self.send_btn.configure(text=f"🚀 SEND ELIGIBLE EMAILS ({k.get('ready', 0)})")
        self.side_send_btn.configure(text=f"🚀 SEND ELIGIBLE ({k.get('ready', 0)})")

    # ── CANDIDATE SELECTION ──────────────────────────────────────────────
    def _on_candidate_pick(self, label):
        if label.startswith("➕"):
            self.open_candidate_setup(new=True)
            return
        if label.startswith("#"):
            self.cid = int(label[1:].split()[0])
            cs.set_active_candidate(self.cid)
            self._build_filters()
            self.load_data()

    def _require_candidate(self) -> bool:
        if self.cid is None:
            messagebox.showwarning("Candidate", "Create a candidate first (👤 Candidate Setup).")
            return False
        return True

    def show_candidate_status(self):
        ctx = self._ctx()
        rd = cs.readiness(ctx.candidate if ctx else None)
        lines = [("✅ " if ok else "❌ ") + label + ("" if ok else f"  →  {hint}") for label, ok, hint in rd["items"]]
        head = "🟢 CANDIDATE READY TO SEND" if rd["ready"] else "🔴 CANDIDATE NOT READY"
        messagebox.showinfo("Candidate Status", head + "\n\n" + "\n".join(lines))

    # ── CANDIDATE SETUP ──────────────────────────────────────────────────
    def open_candidate_setup(self, new=False):
        if new or self.cid is None:
            self.cid = cs.create_candidate()
            cs.set_active_candidate(self.cid)
            self.load_data()
        cid = self.cid
        c = cs.get_candidate(cid)
        top = self._top(f"Candidate Setup — {c.get('name')}", "1120x820")

        hdr = ctk.CTkFrame(top, fg_color="transparent")
        hdr.pack(fill="x", padx=14, pady=(10, 4))
        ctk.CTkLabel(hdr, text="👤 Candidate Setup", font=ctk.CTkFont(size=17, weight="bold"),
                     text_color=INDIGO).pack(side="left")
        status_chip = ctk.CTkLabel(hdr, text="", font=ctk.CTkFont(size=12, weight="bold"))
        status_chip.pack(side="left", padx=16)

        def delete_candidate():
            if messagebox.askyesno("Delete Candidate", f"Delete candidate “{c.get('name')}”, their templates and "
                                   "unsent drafts?  (Sent history is kept.)", parent=top):
                cs.delete_candidate(cid)
                self.cid = cs.get_active_candidate_id()
                if self.cid is not None:
                    cs.set_active_candidate(self.cid)
                top.destroy()
                self._build_filters()
                self.load_data()

        def new_candidate():
            top.destroy()
            self.open_candidate_setup(new=True)

        ctk.CTkButton(hdr, text="🗑 Delete", width=90, command=delete_candidate, fg_color="#fee2e2",
                      hover_color="#fecaca", text_color="#991b1b").pack(side="right", padx=4)
        ctk.CTkButton(hdr, text="➕ New Candidate", width=130, command=new_candidate, fg_color="#e5e7eb",
                      hover_color="#d1d5db", text_color="#1f2937").pack(side="right", padx=4)

        tabs = ctk.CTkTabview(top, fg_color="#f9fafb", segmented_button_selected_color=INDIGO)
        tabs.pack(fill="both", expand=True, padx=14, pady=(0, 12))
        t_det = tabs.add("1. Details & Gmail")
        t_res = tabs.add("2. Resume & Profile")
        t_stat = tabs.add("3. Candidate Status")

        # ---------- Details & Gmail ----------
        det = ctk.CTkScrollableFrame(t_det, fg_color="transparent")
        det.pack(fill="both", expand=True)
        det.grid_columnconfigure(1, weight=1)
        det.grid_columnconfigure(3, weight=1)
        entries = {}

        def row_entry(r, col, label, key, placeholder="", show=None):
            ctk.CTkLabel(det, text=label, text_color="#1f2937").grid(row=r, column=col, sticky="w", padx=6, pady=5)
            e = ctk.CTkEntry(det, placeholder_text=placeholder, show=show, fg_color="#ffffff",
                             border_color="#d1d5db", text_color="#1f2937")
            e.grid(row=r, column=col + 1, sticky="ew", padx=6, pady=5)
            if key and c.get(key):
                e.insert(0, str(c.get(key)))
            entries[key or label] = e
            return e

        row_entry(0, 0, "Candidate Name *", "name")
        row_entry(0, 2, "Candidate Email *", "email")
        row_entry(1, 0, "Phone Number *", "phone", "+91 …")
        ctk.CTkLabel(det, text="Gmail (sender)", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=INDIGO).grid(row=2, column=0, sticky="w", padx=6, pady=(12, 2))
        row_entry(3, 0, "Gmail Address *", "gmail_address", "name@gmail.com")
        has_pw = bool(cs.get_app_password(cid))
        pw_e = row_entry(3, 2, "Gmail App Password *", None,
                         "Saved — leave blank to keep" if has_pw else "16-character App Password", show="•")
        show_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(det, text="Show", variable=show_var, width=60,
                        command=lambda: pw_e.configure(show="" if show_var.get() else "•")).grid(
            row=4, column=3, sticky="w", padx=6)
        ctk.CTkLabel(det, text="Use the 16-character Google App Password (myaccount.google.com/apppasswords) — "
                               "never your normal Gmail password.", text_color=GRAY,
                     font=ctk.CTkFont(size=10)).grid(row=4, column=0, columnspan=3, sticky="w", padx=6)
        gmail_status = ctk.CTkLabel(det, text="", font=ctk.CTkFont(size=12, weight="bold"))
        gmail_status.grid(row=5, column=1, sticky="w", padx=6)

        ctk.CTkLabel(det, text="Compensation & Availability", font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=INDIGO).grid(row=6, column=0, sticky="w", padx=6, pady=(12, 2))
        row_entry(7, 0, "Expected CTC *", "expected_ctc", "Negotiable")
        row_entry(7, 2, "Availability *", "availability", "Immediate Joiner")
        row_entry(8, 0, "Current CTC (optional)", "current_ctc")
        inc_var = tk.BooleanVar(value=bool(c.get("include_current_ctc")))
        ctk.CTkCheckBox(det, text="Include Current CTC in emails", variable=inc_var).grid(
            row=8, column=2, columnspan=2, sticky="w", padx=6)

        ctk.CTkLabel(det, text="Additional signature text (optional)", text_color="#1f2937").grid(
            row=9, column=0, sticky="nw", padx=6, pady=5)
        sig_t = ctk.CTkTextbox(det, height=60, fg_color="#ffffff", border_color="#d1d5db", border_width=1)
        sig_t.grid(row=9, column=1, sticky="ew", padx=6, pady=5)
        sig_t.insert("1.0", c.get("extra_signature") or "")
        ctk.CTkLabel(det, text="Drafting instructions (optional,\nused by AI drafting)", text_color="#1f2937",
                     justify="left").grid(row=9, column=2, sticky="nw", padx=6, pady=5)
        instr_t = ctk.CTkTextbox(det, height=60, fg_color="#ffffff", border_color="#d1d5db", border_width=1)
        instr_t.grid(row=9, column=3, sticky="ew", padx=6, pady=5)
        instr_t.insert("1.0", c.get("drafting_instructions") or "")

        ctk.CTkLabel(det, text="Email closing preview:", text_color="#1f2937").grid(
            row=10, column=0, sticky="nw", padx=6, pady=5)
        preview_lbl = ctk.CTkLabel(det, text="", justify="left", anchor="w", fg_color="#ffffff", corner_radius=6,
                                   text_color="#1f2937", font=ctk.CTkFont(family="Consolas", size=11))
        preview_lbl.grid(row=10, column=1, columnspan=3, sticky="ew", padx=6, pady=5)

        def current_data():
            return {"name": entries["name"].get().strip(), "email": entries["email"].get().strip(),
                    "phone": entries["phone"].get().strip(), "gmail_address": entries["gmail_address"].get().strip(),
                    "expected_ctc": entries["expected_ctc"].get().strip() or "Negotiable",
                    "availability": entries["availability"].get().strip() or "Immediate Joiner",
                    "current_ctc": entries["current_ctc"].get().strip(), "include_current_ctc": inc_var.get(),
                    "extra_signature": sig_t.get("1.0", "end-1c").strip(),
                    "drafting_instructions": instr_t.get("1.0", "end-1c").strip()}

        def update_preview(*_):
            from email_composer import CLOSING_SENTENCE
            preview_lbl.configure(text=CLOSING_SENTENCE + "\n\n" + signature_block(current_data()))

        for e in entries.values():
            e.bind("<KeyRelease>", update_preview)
        sig_t.bind("<KeyRelease>", update_preview)
        inc_var.trace_add("write", update_preview)
        update_preview()

        def refresh_status_views():
            cand = cs.get_candidate(cid)
            rd = cs.readiness(cand)
            status_chip.configure(text="🟢 CANDIDATE READY TO SEND" if rd["ready"] else "🔴 CANDIDATE NOT READY",
                                  text_color="#047857" if rd["ready"] else "#b91c1c")
            gmail_status.configure(text="🟢 Gmail Connected" if rd["gmail_connected"] else "● Not connected",
                                   text_color="#047857" if rd["gmail_connected"] else RED)
            for w in t_stat.winfo_children():
                w.destroy()
            box = ctk.CTkFrame(t_stat, fg_color="#ffffff", corner_radius=10)
            box.pack(fill="both", expand=True, padx=20, pady=16)
            ctk.CTkLabel(box, text="CANDIDATE STATUS", font=ctk.CTkFont(size=15, weight="bold"),
                         text_color=INDIGO).pack(anchor="w", padx=20, pady=(16, 8))
            for label, ok, hint in rd["items"]:
                ctk.CTkLabel(box, text=("✅  " if ok else "❌  ") + label + ("" if ok else f"   →  {hint}"),
                             anchor="w", text_color="#065f46" if ok else "#991b1b",
                             font=ctk.CTkFont(size=12)).pack(anchor="w", padx=28, pady=2)
            ctk.CTkLabel(box, text="🟢 CANDIDATE READY TO SEND" if rd["ready"] else "🔴 CANDIDATE NOT READY",
                         font=ctk.CTkFont(size=16, weight="bold"),
                         text_color="#047857" if rd["ready"] else "#b91c1c").pack(anchor="w", padx=20, pady=16)
            ctk.CTkButton(box, text="🧩 Open Template Library", command=lambda: (top.destroy(),
                                                                                self.open_template_library()),
                          fg_color="#7c3aed", hover_color="#8b5cf6").pack(anchor="w", padx=20)

        def save_details(ask_regen=True):
            data = current_data()
            if not data["name"]:
                messagebox.showerror("Candidate", "Candidate name is required.", parent=top)
                return False
            pw = pw_e.get().strip()
            if pw and not cs.secret_store.is_valid_app_password(pw):
                messagebox.showerror("App Password", "The App Password must be exactly 16 characters "
                                     "(spaces are ignored). Do not use your normal Gmail password.", parent=top)
                return False
            before = ctc_line(c) + signature_block(c)
            cs.update_candidate(cid, data, app_password=pw if pw else None)
            refresh_status_views()
            self.load_data()
            after = cs.get_candidate(cid)
            if ask_regen and before != ctc_line(after) + signature_block(after):
                self._offer_regenerate(top)
            return True

        def connect():
            if not save_details(ask_regen=False):
                return
            gmail_status.configure(text="⏳ Testing…", text_color=BLUE)

            def task():
                ok, msg = cs.connect_and_test_gmail(cid)

                def done():
                    refresh_status_views()
                    self.load_data()
                    (messagebox.showinfo if ok else messagebox.showerror)("Gmail", msg, parent=top)
                self.after(0, done)
            threading.Thread(target=task, daemon=True).start()

        ctk.CTkButton(det, text="🔌 Connect & Test Gmail", command=connect, fg_color="#059669",
                      hover_color=GREEN).grid(row=5, column=0, sticky="w", padx=6, pady=4)
        ctk.CTkButton(det, text="💾 Save Details", command=save_details, fg_color=INDIGO, hover_color="#6366f1",
                      height=36).grid(row=11, column=3, sticky="e", padx=6, pady=12)

        # ---------- Resume & Profile ----------
        res_top = ctk.CTkFrame(t_res, fg_color="transparent")
        res_top.pack(fill="x", pady=(4, 4))
        resume_state = ctk.CTkLabel(res_top, text="", font=ctk.CTkFont(size=12, weight="bold"))
        body = ctk.CTkFrame(t_res, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)
        summary_box = ctk.CTkTextbox(body, fg_color="#ffffff", border_color="#e5e7eb", border_width=1,
                                     font=ctk.CTkFont(size=11), wrap="word")
        summary_box.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        edit = ctk.CTkScrollableFrame(body, fg_color="#ffffff", label_text="Review / edit extracted profile")
        edit.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        prof_widgets = {}

        list_fields = [("Core Skills (one per line)", "skills", 90),
                       ("Achievements (one per line)", "achievements", 90),
                       ("Experience evidence used for highlights (one per line)", "evidence", 160),
                       ("Education", "education", 50), ("Certifications", "certifications", 50),
                       ("Languages", "languages", 40), ("Industry Experience", "industries", 40)]
        str_fields = [("Location", "location"), ("Total Experience (e.g. 4.9+ years)", "total_experience"),
                      ("Current / Recent Role", "current_role")]

        def fill_profile_views():
            cand = cs.get_candidate(cid)
            prof = cand.get("profile") or {}
            if cand.get("resume_path") and os.path.exists(cand["resume_path"]):
                resume_state.configure(text=f"🟢 Resume Ready: 📎 {cand.get('resume_original_name')}"
                                            f"   (analyzed {cand.get('resume_analyzed_at') or '—'})",
                                       text_color="#047857")
            else:
                resume_state.configure(text="● No resume uploaded", text_color=RED)
            summary_box.configure(state="normal")
            summary_box.delete("1.0", "end")
            if prof:
                ready = "🟢 Candidate Profile Ready" if cs.profile_ready(prof) else "🟠 Profile needs review"
                summary_box.insert("1.0", ready + ("  (reviewed)" if cand.get("profile_status") == "confirmed" else
                                                   "") + "\n\n" + format_profile(prof))
            else:
                summary_box.insert("1.0", "Upload the candidate's resume — it is analysed end-to-end "
                                          "(every page and section) to build the candidate profile.")
            summary_box.configure(state="disabled")
            for w in edit.winfo_children():
                w.destroy()
            prof_widgets.clear()
            for label, key in str_fields:
                ctk.CTkLabel(edit, text=label, text_color="#1f2937").pack(anchor="w", padx=6)
                e = ctk.CTkEntry(edit, fg_color="#ffffff", border_color="#d1d5db")
                e.pack(fill="x", padx=6, pady=(0, 6))
                e.insert(0, prof.get(key) or "")
                prof_widgets[key] = e
            for label, key, h in list_fields:
                ctk.CTkLabel(edit, text=label, text_color="#1f2937").pack(anchor="w", padx=6)
                t = ctk.CTkTextbox(edit, height=h, fg_color="#ffffff", border_color="#d1d5db", border_width=1,
                                   wrap="word")
                t.pack(fill="x", padx=6, pady=(0, 6))
                t.insert("1.0", "\n".join(prof.get(key) or []))
                prof_widgets[key] = t

        def upload():
            path = filedialog.askopenfilename(parent=top, filetypes=[("Resume", "*.pdf *.docx *.txt")])
            if not path:
                return
            resume_state.configure(text="⏳ Analyzing resume end-to-end…", text_color=BLUE)

            def task():
                try:
                    prof = cs.store_resume(cid, path)
                    err = None
                except Exception as ex:
                    prof, err = {}, str(ex)

                def done():
                    if err:
                        messagebox.showerror("Resume", f"Could not read the resume: {err}", parent=top)
                    fill_profile_views()
                    refresh_status_views()
                    for key in ("name", "email", "phone"):
                        if not entries[key].get().strip() and prof.get(key):
                            entries[key].insert(0, prof[key])
                    update_preview()
                    self.load_data()
                    if not err:
                        messagebox.showinfo("Resume", "🟢 Resume Ready\n🟢 Candidate Profile created.\n\n"
                                            "Please review the extracted profile on the right and click "
                                            "“Save Profile”.", parent=top)
                self.after(0, done)
            threading.Thread(target=task, daemon=True).start()

        def reanalyze():
            cand = cs.get_candidate(cid)
            if not cand.get("resume_path") or not os.path.exists(cand["resume_path"]):
                messagebox.showwarning("Resume", "Upload a resume first.", parent=top)
                return
            if messagebox.askyesno("Re-analyze", "Re-analyze the resume? Manual profile edits will be replaced.",
                                   parent=top):
                cs.store_resume(cid, cand["resume_path"])
                fill_profile_views()
                refresh_status_views()

        def save_profile():
            cand = cs.get_candidate(cid)
            prof = dict(cand.get("profile") or {})
            if not prof and not cand.get("resume_path"):
                messagebox.showwarning("Profile", "Upload a resume first.", parent=top)
                return
            for _label, key in str_fields:
                prof[key] = prof_widgets[key].get().strip()
            for _label, key, _h in list_fields:
                prof[key] = [l.strip() for l in prof_widgets[key].get("1.0", "end-1c").splitlines() if l.strip()]
            cs.save_profile(cid, prof, confirmed=True)
            fill_profile_views()
            refresh_status_views()
            self.load_data()
            self._offer_regenerate(top)

        resume_state.pack(side="left", padx=4)
        ctk.CTkButton(res_top, text="💾 Save Profile", command=save_profile, fg_color=INDIGO,
                      hover_color="#6366f1").pack(side="right", padx=4)
        ctk.CTkButton(res_top, text="🔍 Re-analyze", command=reanalyze, fg_color="#e5e7eb", hover_color="#d1d5db",
                      text_color="#1f2937").pack(side="right", padx=4)
        ctk.CTkButton(res_top, text="📄 Upload Resume", command=upload, fg_color="#059669",
                      hover_color=GREEN).pack(side="right", padx=4)

        fill_profile_views()
        refresh_status_views()
        if not c.get("resume_path"):
            tabs.set("2. Resume & Profile")

    def _offer_regenerate(self, parent=None):
        pending = [r for r in get_all_recruiters(self.cid) if r["status"] not in ("Sent", "Sending")]
        if pending and messagebox.askyesno(
                "Regenerate drafts", f"Regenerate the {len(pending)} unsent draft(s) for this candidate with the "
                "updated details?", parent=parent):
            self.regenerate_drafts(confirm=False)

    # ── TEMPLATE LIBRARY ─────────────────────────────────────────────────
    def open_template_library(self):
        if not self._require_candidate():
            return
        cid = self.cid
        c = cs.get_candidate(cid)
        top = self._top(f"Template Library — {c.get('name')}", "1040x800")
        hdr = ctk.CTkFrame(top, fg_color="transparent")
        hdr.pack(fill="x", padx=14, pady=(10, 0))
        ctk.CTkLabel(hdr, text=f"🧩 Template Library — {c.get('name')}", font=ctk.CTkFont(size=17, weight="bold"),
                     text_color="#7c3aed").pack(side="left")
        count_lbl = ctk.CTkLabel(hdr, text="", font=ctk.CTkFont(size=12, weight="bold"))
        count_lbl.pack(side="left", padx=14)
        ctk.CTkLabel(top, text=("Paste 5 example emails (subject + Gmail draft).  They are STYLE references — tone, "
                                "structure, opening, highlight format, subject style.  Facts always come from the "
                                "candidate's resume; every job is matched to the best of the 5 templates.\n"
                                "Optional placeholders in examples: [Job Title], [Company], [Recruiter Name], "
                                "[Experience], [Availability].\n"
                                "📎 Each template can have its own resume for its job category — jobs matched to that "
                                "template attach it and draw facts from it.  Without one, the main resume is used."),
                     text_color=GRAY, font=ctk.CTkFont(size=11), justify="left", wraplength=1000).pack(
            anchor="w", padx=16, pady=(2, 4))
        tabs = ctk.CTkTabview(top, fg_color="#f9fafb", segmented_button_selected_color="#7c3aed")
        tabs.pack(fill="both", expand=True, padx=14, pady=(0, 6))
        widgets = []

        def show_template_resume(slot, lbl, rm_btn):
            t = next(x for x in cs.get_templates(cid) if x["slot"] == slot)
            if cs.template_has_resume(t):
                lbl.configure(text=f"🟢 Template resume: 📎 {t.get('resume_original_name')}", text_color="#047857")
                rm_btn.configure(state="normal")
            else:
                main = cs.get_candidate(cid).get("resume_original_name")
                lbl.configure(text=f"● No template resume — uses main resume ({main})" if main else
                              "● No resume — upload one for this template", text_color="#b45309" if main else RED)
                rm_btn.configure(state="disabled")

        def upload_template_resume(slot, lbl, rm_btn):
            path = filedialog.askopenfilename(parent=top, filetypes=[("Resume", "*.pdf *.docx *.txt")])
            if not path:
                return
            lbl.configure(text="⏳ Analyzing resume…", text_color=BLUE)

            def task():
                try:
                    cs.store_template_resume(cid, slot, path)
                    err = None
                except Exception as ex:
                    err = str(ex)

                def done():
                    if err:
                        messagebox.showerror("Resume", f"Could not read the resume: {err}", parent=top)
                    show_template_resume(slot, lbl, rm_btn)
                    self.load_data()
                    if not err:
                        self._offer_regenerate(top)
                self.after(0, done)
            threading.Thread(target=task, daemon=True).start()

        def remove_template_resume(slot, lbl, rm_btn):
            if messagebox.askyesno("Remove resume", f"Remove the resume from Template {slot}? Jobs matched to this "
                                   "template will use the main resume.", parent=top):
                cs.remove_template_resume(cid, slot)
                show_template_resume(slot, lbl, rm_btn)
                self.load_data()
                self._offer_regenerate(top)
        for t in cs.get_templates(cid):
            tab = tabs.add(f"Template {t['slot']}")
            tab.grid_columnconfigure(1, weight=1)
            tab.grid_columnconfigure(3, weight=1)
            tab.grid_rowconfigure(4, weight=1)
            ctk.CTkLabel(tab, text="Template Name").grid(row=0, column=0, sticky="w", padx=6, pady=4)
            name_e = ctk.CTkEntry(tab, placeholder_text="e.g. Business Development", fg_color="#ffffff")
            name_e.grid(row=0, column=1, sticky="ew", padx=6, pady=4)
            name_e.insert(0, t.get("name") or "")
            ctk.CTkLabel(tab, text="Role Category").grid(row=0, column=2, sticky="w", padx=6, pady=4)
            cat_e = ctk.CTkEntry(tab, placeholder_text="e.g. Sales / BD", fg_color="#ffffff")
            cat_e.grid(row=0, column=3, sticky="ew", padx=6, pady=4)
            cat_e.insert(0, t.get("role_category") or "")
            ctk.CTkLabel(tab, text="Example Subject").grid(row=1, column=0, sticky="w", padx=6, pady=4)
            subj_e = ctk.CTkEntry(tab, placeholder_text="Paste the example subject line", fg_color="#ffffff")
            subj_e.grid(row=1, column=1, columnspan=3, sticky="ew", padx=6, pady=4)
            subj_e.insert(0, t.get("example_subject") or "")
            res_f = ctk.CTkFrame(tab, fg_color="#eef2ff", corner_radius=6)
            res_f.grid(row=2, column=0, columnspan=4, sticky="ew", padx=6, pady=4)
            res_lbl = ctk.CTkLabel(res_f, text="", font=ctk.CTkFont(size=12, weight="bold"))
            res_lbl.pack(side="left", padx=8, pady=6)
            rm_btn = ctk.CTkButton(res_f, text="✖ Remove", width=90, fg_color="#e5e7eb", hover_color="#d1d5db",
                                   text_color="#1f2937")
            rm_btn.pack(side="right", padx=6, pady=6)
            up_btn = ctk.CTkButton(res_f, text="📄 Upload Resume for this Template", fg_color="#059669",
                                   hover_color=GREEN)
            up_btn.pack(side="right", padx=6, pady=6)
            show_template_resume(t["slot"], res_lbl, rm_btn)
            up_btn.configure(command=lambda s=t["slot"], l=res_lbl, b=rm_btn: upload_template_resume(s, l, b))
            rm_btn.configure(command=lambda s=t["slot"], l=res_lbl, b=rm_btn: remove_template_resume(s, l, b))
            ctk.CTkLabel(tab, text="Example Gmail Draft / Email Body").grid(row=3, column=0, columnspan=2,
                                                                           sticky="w", padx=6)
            body_t = ctk.CTkTextbox(tab, fg_color="#ffffff", border_color="#d1d5db", border_width=1, wrap="word")
            body_t.grid(row=4, column=0, columnspan=4, sticky="nsew", padx=6, pady=4)
            body_t.insert("1.0", t.get("example_body") or "")
            widgets.append((t["slot"], name_e, cat_e, subj_e, body_t))

        def update_count():
            n = sum(cs.template_configured(t) for t in cs.get_templates(cid))
            count_lbl.configure(text=f"{'🟢' if n == 5 else '🟠'} {n}/5 configured",
                                text_color="#047857" if n == 5 else "#b45309")

        def save_all():
            for slot, name_e, cat_e, subj_e, body_t in widgets:
                cs.save_template(cid, slot, name_e.get(), cat_e.get(), subj_e.get(), body_t.get("1.0", "end-1c"))
            update_count()
            self.load_data()
            missing = [str(s) for s, n, _c, sj, b in widgets
                       if not (n.get().strip() and sj.get().strip() and b.get("1.0", "end-1c").strip())]
            if missing:
                messagebox.showwarning("Templates saved", "Saved. Still incomplete: template " + ", ".join(missing) +
                                       " (needs name, subject and Gmail draft).", parent=top)
            else:
                messagebox.showinfo("Templates saved", "🟢 All 5 templates configured.", parent=top)
            self._offer_regenerate(top)

        bf = ctk.CTkFrame(top, fg_color="transparent")
        bf.pack(fill="x", padx=14, pady=(0, 12))
        ctk.CTkButton(bf, text="💾 Save All Templates", command=save_all, fg_color="#7c3aed", hover_color="#8b5cf6",
                      height=36).pack(side="right", padx=4)
        ctk.CTkButton(bf, text="Close", command=top.destroy, fg_color="#e5e7eb", hover_color="#d1d5db",
                      text_color="#1f2937", height=36, width=90).pack(side="right", padx=4)
        update_count()

    # ── PASTE LINKEDIN JOBS ──
    def open_paste_window(self):
        if not self._require_candidate():
            return
        ctx = self._ctx()
        if not ctx.templates:
            messagebox.showwarning("Templates", "Add your example templates first (🧩 Template Library).")
            return
        if not ctx.profile:
            messagebox.showwarning("Resume", "Upload and analyze the candidate's resume first (👤 Candidate Setup).")
            return
        self._hide_table()
        self.preview_frame.grid_remove()

        # Clear any existing widgets in the paste frame
        for w in self.paste_frame.winfo_children():
            w.destroy()

        # Display the paste frame in the exact location of the table
        self.paste_frame.grid(row=2, column=0, columnspan=2, rowspan=2, sticky="nsew")

        # Header Row
        hdr = ctk.CTkFrame(self.paste_frame, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=(6, 4))

        ctk.CTkLabel(hdr, text="📋 Paste LinkedIn Job Posts (bulk)",
                     font=ctk.CTkFont(size=15, weight="bold"), text_color=INDIGO).pack(side="left")
        ctk.CTkLabel(hdr, text="• Paste many posts at once. Separate them with lines like  ========== JOB 1 ==========  "
                               "(raw LinkedIn feed copies also work). Every job is analysed independently.",
                     font=ctk.CTkFont(size=11), text_color="#4b5563").pack(side="left", padx=12)

        # Paste Textbox
        self.paste_textbox = ctk.CTkTextbox(self.paste_frame, fg_color="#ffffff", border_color="#e5e7eb",
                                            border_width=1, text_color="#1f2937", font=ctk.CTkFont(size=12))
        self.paste_textbox.pack(fill="both", expand=True, padx=10, pady=5)

        # Controls/Buttons
        self.paste_buttons_frame = ctk.CTkFrame(self.paste_frame, fg_color="transparent")
        self.paste_buttons_frame.pack(fill="x", padx=10, pady=(6, 10))

        ctk.CTkButton(self.paste_buttons_frame, text="⚡ Analyze, Match Templates & Generate",
                      command=self.process_paste_and_preview, fg_color="#059669", hover_color=GREEN, height=38,
                      font=ctk.CTkFont(size=13, weight="bold")).pack(side="right", padx=6)
        ctk.CTkButton(self.paste_buttons_frame, text="Cancel", command=self._show_table,
                      fg_color="#e5e7eb", hover_color="#d1d5db", text_color="#1f2937", height=38,
                      width=100).pack(side="right", padx=6)

    def process_paste_and_preview(self):
        raw = self.paste_textbox.get("1.0", "end-1c")
        if len(raw.strip()) < 10:
            messagebox.showwarning("Empty", "Please paste some text first.")
            return

        self._set_status("Analyzing & generating...", BLUE)
        self.generation_cancelled = False

        # Hide textbox and buttons to show clean progress overlay
        self.paste_textbox.pack_forget()
        self.paste_buttons_frame.pack_forget()

        prog_container = ctk.CTkFrame(self.paste_frame, fg_color="transparent")
        prog_container.pack(fill="both", expand=True, pady=60)
        prog_lbl = ctk.CTkLabel(prog_container, text="🔍 Splitting job posts... (10%)",
                                font=ctk.CTkFont(size=14, weight="bold"), text_color=INDIGO)
        prog_lbl.pack(pady=10)
        prog_bar = ctk.CTkProgressBar(prog_container, width=380, height=12, progress_color=GREEN)
        prog_bar.set(0.1)
        prog_bar.pack(pady=10)

        def restore_input():
            prog_container.destroy()
            self.paste_textbox.pack(fill="both", expand=True, padx=10, pady=5)
            self.paste_buttons_frame.pack(fill="x", padx=10, pady=(6, 10))

        def cancel_generation():
            self.generation_cancelled = True
            restore_input()
            self._set_status("Ready")

        ctk.CTkButton(prog_container, text="Cancel", command=cancel_generation, fg_color=RED, hover_color="#dc2626",
                      width=100, height=28, font=ctk.CTkFont(size=12, weight="bold")).pack(pady=15)

        def progress(frac, text):
            if not self.generation_cancelled:
                self.after(0, lambda: (prog_lbl.configure(text=f"{text} ({int(frac * 100)}%)"), prog_bar.set(frac)))

        def task():
            try:
                ctx = self._ctx()
                res = pipeline.ingest_bulk_text(raw, ctx, self.settings.get("openai_api_key", ""),
                                                bool(self.settings.get("use_openai_drafting")), progress,
                                                lambda: self.generation_cancelled)
                if self.generation_cancelled:
                    return

                def done():
                    if self.generation_cancelled:
                        return
                    if not res["parsed"]:
                        restore_input()
                        self._set_status("Ready")
                        messagebox.showwarning("No Results", "Could not find any job posts in the text.")
                        return
                    prog_container.destroy()
                    self._show_table()
                    self._build_filters()
                    self.load_data()
                    self._set_status("Ready")
                    k = self.counts
                    messagebox.showinfo("Jobs processed", (
                        f"Analyzed {res['parsed']} job(s) — {res['new']} new, "
                        f"{res['parsed'] - res['new']} already in the list.\n\n"
                        f"🟢 Ready to Send: {k.get('ready', 0)}\n🟠 Needs Review: {k.get('needs_review', 0)}\n"
                        f"⚪ Filtered Out: {k.get('filtered', 0)}\n\n"
                        "Next: choose Location / Experience filters → Apply Filters → review → "
                        "SEND ELIGIBLE EMAILS."))
                self.after(0, done)
            except Exception as e:
                print(f"Extraction error: {e}")

                def error_done():
                    if self.generation_cancelled:
                        return
                    self._set_status("Ready")
                    restore_input()
                    messagebox.showerror("Error", f"An error occurred during processing: {e}")
                self.after(0, error_done)

        threading.Thread(target=task, daemon=True).start()

    # ── GMAIL ──
    def connect_gmail(self):
        if not self._require_candidate():
            return
        c = cs.get_candidate(self.cid)
        if not c.get("gmail_address") or not cs.get_app_password(self.cid):
            messagebox.showwarning("Setup", "Open 👤 Candidate Setup → enter the candidate's Gmail + 16-character "
                                            "App Password.")
            return
        self.gmail_lbl.configure(text="⏳ Testing…", text_color=BLUE)

        def task():
            ok, msg = cs.connect_and_test_gmail(self.cid)

            def done():
                self.load_data()
                (messagebox.showinfo if ok else messagebox.showerror)("Gmail", ("🟢 Gmail Connected\n" if ok else "") + msg)
            self.after(0, done)
        threading.Thread(target=task, daemon=True).start()

    def upload_resume(self):
        if not self._require_candidate():
            return
        path = filedialog.askopenfilename(filetypes=[("Resume", "*.pdf *.docx *.txt")])
        if not path:
            return
        self._set_status("Analyzing resume…", BLUE)

        def task():
            try:
                cs.store_resume(self.cid, path)
                err = None
            except Exception as ex:
                err = str(ex)

            def done():
                self._set_status("Ready")
                self.load_data()
                if err:
                    messagebox.showerror("Resume", f"Could not read the resume: {err}")
                else:
                    messagebox.showinfo("Resume", "🟢 Resume Ready — analyzed end-to-end.\nReview the profile in "
                                                  "👤 Candidate Setup → Resume & Profile.")
                    self._offer_regenerate()
            self.after(0, done)
        threading.Thread(target=task, daemon=True).start()

    def upload_file(self):
        if not self._require_candidate():
            return
        ctx = self._ctx()
        if not ctx.templates or not ctx.profile:
            messagebox.showwarning("Setup", "Configure the resume and templates first.")
            return
        path = filedialog.askopenfilename(filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            df = pd.read_csv(path).fillna("")
            records = []
            for _, row in df.iterrows():
                jd_text = str(row.get('JD', ''))
                a = analyze_jd(jd_text)
                overrides = {'recruiter_name': str(row.get('Recruiter Name', '')), 'company': str(row.get('Company', '')),
                             'email': str(row.get('Email', '')).strip(), 'job_title': str(row.get('Job Title', '')),
                             'location': str(row.get('Location', '')), 'experience': str(row.get('Experience', ''))}
                for k, v in overrides.items():
                    if v:
                        a[k] = v
                if overrides['location']:
                    a['cities'] = kb.detect_cities(overrides['location'])
                if overrides['experience']:
                    a['exp_min'], a['exp_max'], _ = parse_experience("Experience: " + overrides['experience'])
                rec = pipeline.record_from_analysis(a, self.cid)
                if row.get('Skills Required'):
                    rec['skills_required'] = str(row.get('Skills Required'))
                records.append(rec)
            ids, flags = insert_recruiters_bulk(records, return_new_flags=True)
            new_ids = [i for i, n in zip(ids, flags) if n]
            self._set_status("Generating emails…", BLUE)

            def task():
                pipeline.regenerate(self._ctx(), new_ids, self.settings.get("openai_api_key", ""),
                                    bool(self.settings.get("use_openai_drafting")))

                def done():
                    self._build_filters()
                    self.load_data()
                    self._set_status("Ready")
                    messagebox.showinfo("Done", f"Loaded {len(df)} rows from CSV ({len(new_ids)} new) and generated "
                                                "emails.")
                self.after(0, done)
            threading.Thread(target=task, daemon=True).start()
        except Exception as ex:
            messagebox.showerror("Error", str(ex))

    # ── GENERATE ──
    def regenerate_drafts(self, confirm=True):
        if not self._require_candidate():
            return
        ctx = self._ctx()
        if not ctx.templates:
            messagebox.showwarning("Templates", "Configure templates first.")
            return
        unsent = [r for r in get_all_recruiters(self.cid) if r["status"] not in ("Sent", "Sending")]
        if not unsent:
            if confirm:
                messagebox.showinfo("Regenerate", "No unsent drafts.")
            return
        if confirm and not messagebox.askyesno("Regenerate", f"Re-match templates and regenerate {len(unsent)} unsent "
                                               "draft(s)? Manual edits to those drafts will be replaced."):
            return
        self._set_status("Regenerating drafts…", BLUE)

        def task():
            n = pipeline.regenerate(self._ctx(), None, self.settings.get("openai_api_key", ""),
                                    bool(self.settings.get("use_openai_drafting")))
            self.after(0, lambda: (self.load_data(), self._set_status(f"Regenerated {n} drafts")))
        threading.Thread(target=task, daemon=True).start()

    # ── SEND ELIGIBLE ──
    def send_all(self):
        """SEND ELIGIBLE EMAILS — never 'every row'."""
        if not self._require_candidate():
            return
        if self._job_running(self.cid):
            messagebox.showinfo("Already sending", "Emails are already being sent for this candidate — see the "
                                                   "progress bar next to Refresh.")
            return
        cfg = self.apply_filters(quiet=True)
        if cfg is None:
            return
        ctx = self._ctx()
        if not ctx.readiness["ready"]:
            messagebox.showerror("🔴 Candidate not ready", "Fix these before sending:\n\n• " +
                                 "\n• ".join(ctx.readiness["missing"]))
            return
        recs = get_all_recruiters(self.cid)
        evals = {r["id"]: pipeline.evaluate_record(r, ctx, cfg) for r in recs}
        recruits = [r for r in recs if evals[r["id"]]["eligible"]]
        k = self.counts
        if not recruits:
            messagebox.showinfo("Nothing eligible", (
                f"No emails are eligible to send.\n\nFiltered Out: {k.get('filtered', 0)}   "
                f"Needs Review: {k.get('needs_review', 0)}   Sent: {k.get('sent', 0)}\n\n{cfg.describe()}"))
            return
        recruits.sort(key=lambda r: r["id"])

        self._hide_table()
        for w in self.preview_frame.winfo_children():
            w.destroy()
        self.preview_frame.grid(row=2, column=0, columnspan=2, rowspan=2, sticky="nsew")

        c = ctx.candidate
        delay = int(self.settings.get("delay_between_emails", 3) or 0)
        res_names = {ctx.resume_for(ctx.template_by_id(r.get("template_id")))["name"] for r in recruits}
        res_name = next(iter(res_names)) if len(res_names) == 1 else f"{len(res_names)} resumes (per template)"

        def close_preview():
            self._show_table()
            self.load_data()

        def on_confirm():
            close_preview()
            ids = [r["id"] for r in recruits]
            self._start_send_job(ctx.id, c.get("name") or f"#{ctx.id}", "Sending", lambda kw: send_eligible(
                ctx.id, cfg, record_ids=ids, **kw))

        # Header Row
        hdr = ctk.CTkFrame(self.preview_frame, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=(6, 2))
        ctk.CTkLabel(hdr, text="🚀 Send Eligible Emails — Confirmation", font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=INDIGO).pack(side="left")
        ctk.CTkLabel(hdr, text=f"• {len(recruits)} eligible email(s). Select a row to inspect.",
                     font=ctk.CTkFont(size=11), text_color="#4b5563").pack(side="left", padx=12)
        info = ctk.CTkLabel(self.preview_frame, justify="left", anchor="w", font=ctk.CTkFont(size=11),
                            text_color="#1e1b4b", fg_color="#eef2ff", corner_radius=8, text=(
                                f"Sending as: {c.get('name')} <{c.get('gmail_address')}>    📎 Resume: {res_name}    "
                                f"Delay: {delay}s\n{cfg.describe()}    |    Not sent: {k.get('filtered', 0)} filtered out, "
                                f"{k.get('needs_review', 0)} need review, {k.get('sent', 0)} already sent"))
        info.pack(fill="x", padx=10, pady=(0, 4))

        btn_f = ctk.CTkFrame(self.preview_frame, fg_color="transparent")
        btn_f.pack(side="bottom", fill="x", padx=10, pady=(4, 8))
        ctk.CTkButton(btn_f, text="Cancel", command=close_preview, fg_color="#e5e7eb", hover_color="#d1d5db",
                      text_color="#1f2937", height=38, width=100).pack(side="right", padx=6)
        ctk.CTkButton(btn_f, text=f"🚀 Confirm & Send Eligible ({len(recruits)})", command=on_confirm,
                      fg_color="#dc2626", hover_color=RED, height=38,
                      font=ctk.CTkFont(size=13, weight="bold")).pack(side="right", padx=6)

        card = ctk.CTkFrame(self.preview_frame, fg_color="#f9fafb", border_color="#e5e7eb", border_width=1,
                            corner_radius=8)
        card.pack(side="bottom", fill="x", padx=10, pady=5)
        to_lbl = ctk.CTkLabel(card, text="To: Select a row to preview", font=ctk.CTkFont(size=11, weight="bold"),
                              text_color="#1f2937")
        to_lbl.pack(anchor="w", padx=14, pady=(8, 2))
        sub_lbl = ctk.CTkLabel(card, text="Subject: —", font=ctk.CTkFont(size=11), text_color="#4b5563")
        sub_lbl.pack(anchor="w", padx=14, pady=2)
        body_box = ctk.CTkTextbox(card, height=150, fg_color="#ffffff", border_color="#e5e7eb", border_width=1,
                                  text_color="#1f2937")
        body_box.pack(fill="x", padx=14, pady=4)

        tbl_frame = ctk.CTkFrame(self.preview_frame, fg_color="transparent")
        tbl_frame.pack(fill="both", expand=True, padx=10, pady=4)
        style = ttk.Style()
        style.configure("Outbox.Treeview", background="#ffffff", foreground="#1f2937",
                        fieldbackground="#ffffff", rowheight=24, borderwidth=0)
        style.configure("Outbox.Treeview.Heading", background="#f3f4f6", foreground=INDIGO,
                        borderwidth=0, font=("Segoe UI", 9, "bold"))
        style.map("Outbox.Treeview", background=[("selected", "#e0e7ff")])
        columns = ("num", "recipient", "company", "role", "location", "template", "resume", "subject")
        outbox_tree = ttk.Treeview(tbl_frame, columns=columns, show="headings", style="Outbox.Treeview", height=6)
        for col, text, w in (("num", "#", 40), ("recipient", "Recipient", 200), ("company", "Company", 130),
                             ("role", "Role", 170), ("location", "Location", 100), ("template", "Template", 130),
                             ("resume", "📎 Resume", 150), ("subject", "Subject", 300)):
            outbox_tree.heading(col, text=text)
            outbox_tree.column(col, width=w, anchor="w" if col != "num" else "center")
        outbox_tree.pack(side="left", fill="both", expand=True)
        sb = ctk.CTkScrollbar(tbl_frame, command=outbox_tree.yview)
        sb.pack(side="right", fill="y")
        outbox_tree.configure(yscrollcommand=sb.set)
        for idx, r in enumerate(recruits):
            outbox_tree.insert("", "end", iid=str(r['id']), values=(
                idx + 1, r.get('email', ''), r.get('company', ''), r.get('job_title', ''), r.get('location', ''),
                f"{r.get('template_name')} ({r.get('template_match_score')}%)",
                ctx.resume_for(ctx.template_by_id(r.get("template_id")))["name"], r.get('generated_subject', '')))

        def on_select(event):
            selected = outbox_tree.selection()
            if not selected:
                return
            r = next((x for x in recruits if str(x['id']) == selected[0]), None)
            if r:
                to_lbl.configure(text=f"To: {r.get('recruiter_name') or 'Hiring Team'} <{r.get('email')}> "
                                      f"({r.get('company')})")
                sub_lbl.configure(text=f"Subject: {r.get('generated_subject')}")
                body_box.configure(state="normal")
                body_box.delete("1.0", "end")
                body_box.insert("1.0", r.get('generated_body') or "")
                body_box.configure(state="disabled")
        outbox_tree.bind("<<TreeviewSelect>>", on_select)
        outbox_tree.selection_set(str(recruits[0]['id']))
        on_select(None)

    # ── background send jobs (one per candidate) ─────────────────────────
    def _job_running(self, cid) -> bool:
        return bool(self.jobs.get(cid, {}).get("running"))

    def _start_send_job(self, cid, name, kind, run):
        """run(kw) performs the send with kw = {on_update, on_progress, should_stop} and returns a summary.
        It runs in its own thread for candidate `cid` and keeps going if another candidate is selected."""
        job = {"name": name, "kind": kind, "total": 0, "done": 0, "sent": 0, "failed": 0, "current": "",
               "running": True, "stop": threading.Event()}
        self.jobs[cid] = job
        base_sent, base_failed = self._candidate_send_counts(cid)

        def on_progress(done, total, current):
            job.update(done=done, total=total, current=current)

        def on_update():
            # cheap counter refresh from the DB; the full table reload only for the visible candidate
            s, f = self._candidate_send_counts(cid)
            job.update(sent=max(0, s - base_sent), failed=max(0, f - base_failed))
            if cid == self.cid:
                self.after(0, self.load_data)

        def task():
            summary = {"sent": 0, "failed": 0, "skipped": [], "attempted": 0, "error": ""}
            try:
                summary = run({"on_update": on_update, "on_progress": on_progress,
                               "should_stop": job["stop"].is_set})
            except Exception as e:  # never leave a job stuck in "running"
                summary["error"] = str(e)[:300]
            job.update(running=False, current="")
            self.after(0, lambda: self._show_send_summary(summary, name, cid))

        threading.Thread(target=task, daemon=True).start()
        self._set_status(f"{kind} emails for {name}…", RED)
        self._render_progress()
        if not self._ticking:
            self._ticking = True
            self.after(700, self._progress_tick)

    @staticmethod
    def _candidate_send_counts(cid):
        r = get_report(cid)
        return r["sent"], r["failed"]

    def _progress_tick(self):
        self._render_progress()
        if any(j["running"] for j in self.jobs.values()):
            self.after(700, self._progress_tick)
        else:
            self._ticking = False

    def _render_progress(self):
        box = getattr(self, "progress_box", None)
        if box is None or not box.winfo_exists():
            return
        for w in box.winfo_children():
            w.destroy()
        job = self.jobs.get(self.cid)
        others = [(cid, j) for cid, j in self.jobs.items() if j["running"] and cid != self.cid]
        if job:
            total, done = job["total"], job["done"]
            waiting = max(0, total - done - (1 if job["current"] else 0))
            head = (f"📤 {job['kind']} {min(done + (1 if job['current'] else 0), total)} of {total}"
                    if job["running"] else f"✅ Finished — {done} of {total} processed")
            ctk.CTkLabel(box, text=head, font=ctk.CTkFont(size=11, weight="bold"),
                         text_color=RED if job["running"] else "#047857").pack(anchor="w")
            bar = ctk.CTkProgressBar(box, width=240, height=10, progress_color=GREEN)
            bar.set(done / total if total else 0)
            bar.pack(anchor="w", pady=2)
            ctk.CTkLabel(box, text=f"✅ Sent {job['sent']}   ❌ Failed {job['failed']}   ⏳ Waiting {waiting}",
                         font=ctk.CTkFont(size=10), text_color="#1f2937").pack(anchor="w")
            if job["running"]:
                line = ctk.CTkFrame(box, fg_color="transparent")
                line.pack(anchor="w", fill="x")
                ctk.CTkLabel(line, text=f"Now: {job['current'] or 'waiting (delay)…'}"[:42],
                             font=ctk.CTkFont(size=9), text_color=GRAY).pack(side="left")
                ctk.CTkButton(line, text="⏹ Stop", width=46, height=16, font=ctk.CTkFont(size=9, weight="bold"),
                              fg_color="#fee2e2", hover_color="#fecaca", text_color="#991b1b",
                              command=lambda j=job: (j["stop"].set(), self._set_status(
                                  f"Stopping after the current email for {j['name']}…", ORANGE))).pack(side="left",
                                                                                                         padx=6)
        if others:
            ctk.CTkLabel(box, text="Also sending: " + ",  ".join(
                f"{j['name']} {j['done']}/{j['total']}" for _cid, j in others),
                         font=ctk.CTkFont(size=9, weight="bold"), text_color=INDIGO).pack(anchor="w")

    def _show_send_summary(self, summary, name="", cid=None):
        if cid is None or cid == self.cid:
            self.load_data()
        else:
            self._render_progress()
        if not any(j["running"] for j in self.jobs.values()):
            self._set_status("Ready")
        title = f"Done — {name}" if name else "Done"
        if summary.get("error") and not summary["attempted"]:
            messagebox.showerror(f"Not sent — {name}" if name else "Not sent", summary["error"])
            return
        msg = f"Sent: {summary['sent']}    Failed: {summary['failed']}    Skipped: {len(summary['skipped'])}"
        if summary.get("error"):
            msg += f"\n\n⚠ {summary['error']}"
        if summary["skipped"]:
            msg += "\n\nSkipped (not eligible at send time):\n" + "\n".join(
                f"#{rid}: {reason[:120]}" for rid, reason in summary["skipped"][:10])
        messagebox.showinfo(title, msg)

    def retry_failed(self):
        if not self._require_candidate():
            return
        if self._job_running(self.cid):
            messagebox.showinfo("Already sending", "Emails are already being sent for this candidate.")
            return
        failed = [r for r in get_all_recruiters(self.cid) if r['status'] == 'Failed']
        if not failed:
            messagebox.showinfo("Nothing", "No failed emails.")
            return
        cfg = self.apply_filters(quiet=True)
        if cfg is None:
            return
        if not messagebox.askyesno("Retry Failed", f"Retry {len(failed)} failed email(s)?  Only those that are still "
                                   "eligible (filters + quality) will be sent."):
            return
        retries = max(1, int(self.settings.get("retry_count", 1) or 1))
        cid = self.cid
        name = (cs.get_candidate(cid) or {}).get("name") or f"#{cid}"

        def run(kw):
            total = {"sent": 0, "failed": 0, "skipped": [], "attempted": 0, "error": ""}
            for _ in range(retries):
                s = send_eligible(cid, cfg, only_statuses={"Failed"}, **kw)
                total["sent"] += s["sent"]
                total["attempted"] += s["attempted"]
                total["skipped"] = s["skipped"]
                total["error"] = s["error"]
                total["failed"] = s["failed"]
                if not s["failed"] or s["error"]:
                    break
            return total
        self._start_send_job(cid, name, "Retrying", run)

    def show_candidate_history(self):
        """Per-day, per-candidate send counts for all candidates."""
        top = self._top("Daily Send History", "760x560")
        ctk.CTkLabel(top, text="📅 Daily Send History — All Candidates", font=ctk.CTkFont(size=16, weight="bold"),
                     text_color="#0f766e").pack(pady=(14, 4))

        cands = cs.list_candidates()
        choices = ["All candidates"] + [f"#{c['id']}  {c['name'] or 'Unnamed'}" for c in cands]
        bar = ctk.CTkFrame(top, fg_color="transparent")
        bar.pack(fill="x", padx=14, pady=4)
        ctk.CTkLabel(bar, text="Candidate:", text_color="#1f2937").pack(side="left")
        pick = tk.StringVar(value=choices[0])
        ctk.CTkOptionMenu(bar, values=choices, variable=pick, command=lambda _v: load(), fg_color="#ffffff",
                          text_color="#1f2937", button_color="#99f6e4", width=220).pack(side="left", padx=8)
        ctk.CTkButton(bar, text="🔄 Refresh", width=80, command=lambda: load(), fg_color="#e5e7eb",
                      hover_color="#d1d5db", text_color="#1f2937").pack(side="left")

        tf = ctk.CTkFrame(top, fg_color="transparent")
        tf.pack(fill="both", expand=True, padx=14, pady=6)
        cols = ("date", "candidate", "sent", "failed")
        tree = ttk.Treeview(tf, columns=cols, show="headings", style="E.Treeview")
        for col, text, w in (("date", "Date", 140), ("candidate", "Candidate", 260), ("sent", "Emails Sent", 120),
                             ("failed", "Failed", 100)):
            tree.heading(col, text=text)
            tree.column(col, width=w, anchor="w" if col == "candidate" else "center")
        tree.tag_configure("day", background="#f0fdfa", foreground="#0f766e")
        tree.pack(side="left", fill="both", expand=True)
        sbar = ctk.CTkScrollbar(tf, command=tree.yview)
        sbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=sbar.set)

        totals_lbl = ctk.CTkLabel(top, text="", font=ctk.CTkFont(size=12, weight="bold"), text_color="#1f2937",
                                  justify="left")
        totals_lbl.pack(anchor="w", padx=14, pady=(0, 12))

        def load():
            v = pick.get()
            cid = int(v[1:].split()[0]) if v.startswith("#") else None
            rows = get_send_history(cid)
            for r in tree.get_children():
                tree.delete(r)
            by_day, per_cand = {}, {}
            for r in rows:
                by_day.setdefault(r["date"], []).append(r)
                per_cand[r["name"]] = per_cand.get(r["name"], 0) + (r["sent"] or 0)
            for day, items in by_day.items():
                day_sent = sum(i["sent"] or 0 for i in items)
                day_failed = sum(i["failed"] or 0 for i in items)
                tree.insert("", "end", tags=("day",), values=(
                    day, f"{len(items)} candidate(s)", day_sent, day_failed))
                for i in items:
                    tree.insert("", "end", values=("", f"   {i['name']}", i["sent"] or 0, i["failed"] or 0))
            totals_lbl.configure(text=("Total sent:  " + "   |   ".join(f"{n}: {s}" for n, s in per_cand.items()))
                                 if per_cand else "No emails sent yet.")
        load()

    def show_sent_history(self):
        top = self._top("Sent Email History", "900x640")

        ctk.CTkLabel(top, text="📊 Sent Email History",
                     font=ctk.CTkFont(size=16, weight="bold"), text_color=BLUE).pack(pady=(14, 4))

        top_f = ctk.CTkFrame(top, fg_color="transparent")
        top_f.pack(fill="x", padx=14, pady=5)

        style = ttk.Style()
        style.configure("History.Treeview", background="#ffffff", foreground="#1f2937",
                        fieldbackground="#ffffff", rowheight=24, borderwidth=0)
        style.configure("History.Treeview.Heading", background="#f3f4f6", foreground=INDIGO,
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

        ctk.CTkLabel(bot_f, text="Sent Details for Selected Date:", font=ctk.CTkFont(size=11, weight="bold"),
                     text_color="#4b5563").pack(anchor="w", pady=(0, 4))

        detail_columns = ("time", "recipient", "company", "job", "template", "sender", "subject")
        d_tree = ttk.Treeview(bot_f, columns=detail_columns, show="headings", style="History.Treeview", height=7)
        for col, text, w in (("time", "Time", 70), ("recipient", "Recipient Email", 170), ("company", "Company", 110),
                             ("job", "Job", 130), ("template", "Template", 110), ("sender", "Sent From", 150),
                             ("subject", "Subject", 220)):
            d_tree.heading(col, text=text)
            d_tree.column(col, width=w, anchor="center" if col == "time" else "w")
        d_tree.pack(side="left", fill="both", expand=True)

        d_sb = ctk.CTkScrollbar(bot_f, command=d_tree.yview)
        d_sb.pack(side="right", fill="y")
        d_tree.configure(yscrollcommand=d_sb.set)

        act_f = ctk.CTkFrame(top, fg_color="transparent")
        act_f.pack(fill="x", padx=14, pady=(5, 14))

        from database import get_db

        def get_formatted_list(date_val):
            conn = get_db()
            rows = conn.execute('''
                SELECT recipient, subject, job_title
                FROM logs
                WHERE status='Sent' AND date=?
                ORDER BY time DESC
            ''', (date_val,)).fetchall()
            conn.close()

            lines = []
            for r in rows:
                email_addr, subj, job = r[0], r[1], r[2]
                if job:
                    role_val = job
                else:
                    parts = [p.strip() for p in (subj or "").split("|")]
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
                      fg_color=BLUE, hover_color="#1d4ed8", font=ctk.CTkFont(size=12, weight="bold"),
                      height=36).pack(side="left", padx=5)
        ctk.CTkButton(act_f, text="💾 Export to Text File", command=export_emails,
                      fg_color=GREEN, hover_color="#059669", font=ctk.CTkFont(size=12, weight="bold"),
                      height=36).pack(side="left", padx=5)

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
                SELECT time, recipient, company, job_title, template_name, sender, subject
                FROM logs
                WHERE status='Sent' AND date=?
                ORDER BY time DESC
            ''', (date_val,)).fetchall()
            conn.close()
            for r in rows:
                d_tree.insert("", "end", values=tuple("" if v is None else v for v in r))

        h_tree.bind("<<TreeviewSelect>>", on_date_select)
        load_history()

        children = h_tree.get_children()
        if children:
            h_tree.selection_set(children[0])

    # ── PREVIEW / EDIT ──
    def _on_double_click(self, event):
        sel = self.tree.selection()
        if not sel:
            return
        self.open_preview_modal(sel[0])

    def open_preview_modal(self, r_id):
        r = get_recruiter(int(r_id))
        if not r:
            return
        ctx = self._ctx()
        top = self._top(f"Email Preview / Edit — {r['recruiter_name'] or 'Hiring Team'} @ {r['company'] or 'Company'}",
                        "1240x840")
        top.grid_columnconfigure(0, weight=2)
        top.grid_columnconfigure(1, weight=3)
        top.grid_rowconfigure(0, weight=1)

        # Left: analysis
        info = ctk.CTkTextbox(top, fg_color="#f9fafb", border_color="#e5e7eb", border_width=1, wrap="word",
                              font=ctk.CTkFont(size=11))
        info.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=12)

        # Right: editable email
        right = ctk.CTkFrame(top, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)
        right.grid_columnconfigure(1, weight=1)
        right.grid_columnconfigure(3, weight=1)
        right.grid_rowconfigure(6, weight=1)

        def entry(row, col, label, value):
            ctk.CTkLabel(right, text=label, text_color="#1f2937").grid(row=row, column=col, sticky="w", padx=5, pady=3)
            e = ctk.CTkEntry(right, fg_color="#ffffff", border_color="#d1d5db", text_color="#1f2937")
            e.grid(row=row, column=col + 1, sticky="ew", padx=5, pady=3)
            e.insert(0, value or "")
            return e

        email_e = entry(0, 0, "Recruiter Email:", r['email'])
        name_e = entry(0, 2, "Recruiter Name:", r['recruiter_name'])
        title_e = entry(1, 0, "Job Title:", r['job_title'])
        company_e = entry(1, 2, "Company:", r['company'])
        loc_e = entry(2, 0, "Location:", r['location'])
        exp_e = entry(2, 2, "Experience:", r['experience'])

        tmpl_names = {f"{t['slot']}. {t['name']}": t["id"] for t in (ctx.templates if ctx else [])}
        cur_tmpl = next((k for k, v in tmpl_names.items() if v == r.get("template_id")), "—")
        ctk.CTkLabel(right, text="Template:", text_color="#1f2937").grid(row=3, column=0, sticky="w", padx=5, pady=3)
        tmpl_var = tk.StringVar(value=cur_tmpl)
        ctk.CTkOptionMenu(right, values=list(tmpl_names) or ["—"], variable=tmpl_var, fg_color="#ffffff",
                          text_color="#1f2937", button_color="#c7d2fe").grid(row=3, column=1, sticky="ew", padx=5)
        tmpl_score_lbl = ctk.CTkLabel(right, text="", text_color=GRAY)
        tmpl_score_lbl.grid(row=3, column=2, columnspan=2, sticky="w", padx=5)

        ctk.CTkLabel(right, text="Subject:", text_color="#1f2937").grid(row=4, column=0, sticky="w", padx=5, pady=3)
        sub_e = ctk.CTkEntry(right, fg_color="#ffffff", border_color="#d1d5db", text_color="#1f2937")
        sub_e.grid(row=4, column=1, columnspan=3, sticky="ew", padx=5, pady=3)
        ctk.CTkLabel(right, text="Email Body:", text_color="#1f2937").grid(row=5, column=0, sticky="w", padx=5)
        body_b = ctk.CTkTextbox(right, fg_color="#ffffff", border_color="#d1d5db", border_width=1,
                                text_color="#1f2937", wrap="word")
        body_b.grid(row=6, column=0, columnspan=4, sticky="nsew", padx=5, pady=3)

        c = ctx.candidate if ctx else {}
        ctk.CTkLabel(right, text=(f"{ctc_line(c)}     📎 Attachment: {c.get('resume_original_name') or 'None'}     "
                                  f"Sending as: {c.get('gmail_address') or '—'}"),
                     text_color="#4b5563").grid(row=7, column=0, columnspan=4, sticky="w", padx=5, pady=2)
        approve_var = tk.BooleanVar(value=bool(r.get("review_approved")))
        approve_cb = ctk.CTkCheckBox(right, text="I reviewed this email — approve it for sending despite soft "
                                                 "(non-blocking) review notes", variable=approve_var)
        approve_cb.grid(row=8, column=0, columnspan=4, sticky="w", padx=5, pady=2)
        quality_lbl = ctk.CTkLabel(right, text="", font=ctk.CTkFont(size=13, weight="bold"))
        quality_lbl.grid(row=9, column=0, columnspan=2, sticky="w", padx=5)

        def fill(rec):
            sub_e.delete(0, "end")
            sub_e.insert(0, rec.get('generated_subject') or "")
            body_b.delete("1.0", "end")
            body_b.insert("1.0", rec.get('generated_body') or "")
            render_info(rec)

        def render_info(rec):
            ev = pipeline.evaluate_record(rec, ctx, self._filter_cfg()) if ctx else None
            tmpl_score_lbl.configure(text=f"Match {rec.get('template_match_score') or 0}%  •  "
                                          f"Candidate match {rec.get('match_percentage') or 0}%")
            out = []
            if ev:
                ok = ev["quality_status"].startswith("Ready")
                quality_lbl.configure(text=("🟢 READY TO SEND" if ok else "🟠 NEEDS REVIEW") +
                                      ("" if ev["filter_status"] == ELIGIBLE else f"   •   {ev['filter_status']}"),
                                      text_color="#047857" if ok and ev["filter_status"] == ELIGIBLE else "#b45309")
                out.append("QUALITY CHECK\n" + ("  ✅ All checks passed\n" if not ev["issues"] else "".join(
                    f"  {'⛔' if i['severity'] == 'hard' else '⚠'} {i['message']}\n" for i in ev["issues"])))
                out.append(f"FILTER STATUS: {ev['filter_status']}\n" +
                           "".join(f"  • {x}\n" for x in ev["filter_reasons"]))
            out.append(f"SELECTED TEMPLATE: {rec.get('template_name') or '—'} ({rec.get('template_match_score') or 0}%)\n"
                       f"  {rec.get('template_reason') or ''}\n")
            scores = json.loads(rec["template_scores"]) if rec.get("template_scores") else []
            for s in scores:
                p = s.get("parts", {})
                out.append(f"  {s['slot']}. {s['name']}: {s['score']}%   (title {p.get('title')}, resp "
                           f"{p.get('responsibilities')}, skills {p.get('skills')}, domain {p.get('domain')}, "
                           f"keywords {p.get('keywords')}, candidate {p.get('candidate')})\n")
            cm = json.loads(rec["candidate_match"]) if rec.get("candidate_match") else {}
            out.append(f"\nCANDIDATE MATCH: {cm.get('match_percentage', '—')}%\n"
                       f"  Matched: {', '.join(cm.get('matched_skills', [])) or '—'}\n"
                       f"  Not in resume (never claimed in email): {', '.join(cm.get('missing_skills', [])) or '—'}\n")
            hl = json.loads(rec["highlights"]) if rec.get("highlights") else []
            if hl:
                out.append("\nHIGHLIGHTS SELECTED FOR THIS JD (from resume)\n" + "".join(
                    f"  {i + 1}. [{h.get('label') or '—'} · relevance {h.get('relevance')}] {h['text']}\n"
                    for i, h in enumerate(hl)))
            out.append("\nJD ANALYSIS\n" + format_jd_analysis(pipeline.jd_for_record(rec)) + "\n")
            info.configure(state="normal")
            info.delete("1.0", "end")
            info.insert("1.0", "\n".join(out))
            info.configure(state="disabled")

        def save(silent=False):
            loc, exp = loc_e.get().strip(), exp_e.get().strip()
            lo, hi, _ = parse_experience("Experience: " + exp) if exp else (None, None, "")
            update_record(r['id'], recruiter_name=name_e.get().strip(), company=company_e.get().strip(),
                          email=email_e.get().strip(), job_title=title_e.get().strip(),
                          generated_subject=sub_e.get().strip(), generated_body=body_b.get("1.0", "end-1c").strip(),
                          location=loc, location_cities=kb.detect_cities(loc), experience=exp, exp_min=lo, exp_max=hi,
                          review_approved=1 if approve_var.get() else 0)
            fresh = get_recruiter(r['id'])
            if fresh["status"] == "Pending" and fresh.get("generated_body"):
                update_record(r['id'], status="Generated")
                fresh = get_recruiter(r['id'])
            render_info(fresh)
            self.load_data()
            if not silent:
                self._set_status("Saved", GREEN)
            return fresh

        def regenerate():
            save(silent=True)
            tid = tmpl_names.get(tmpl_var.get())
            pipeline.regenerate(self._ctx(), [r['id']], self.settings.get("openai_api_key", ""),
                                bool(self.settings.get("use_openai_drafting")), template_id=tid)
            fresh = get_recruiter(r['id'])
            approve_var.set(False)
            fill(fresh)
            self.load_data()

        def send_one():
            save(silent=True)
            cfg = self._filter_cfg()

            def task():
                summary = send_eligible(self.cid, cfg, record_ids=[r['id']], delay=0)

                def done():
                    self.load_data()
                    fresh = get_recruiter(r['id'])
                    render_info(fresh)
                    if summary["sent"]:
                        messagebox.showinfo("Result", "Sent!", parent=top)
                    elif summary["failed"]:
                        messagebox.showerror("Result", "Failed — see Sent History / logs.", parent=top)
                    else:
                        reason = summary["error"] or (summary["skipped"][0][1] if summary["skipped"] else "Not eligible")
                        messagebox.showwarning("Not sent", f"This email is not eligible to send:\n\n{reason}",
                                               parent=top)
                self.after(0, done)
            threading.Thread(target=task, daemon=True).start()

        bf = ctk.CTkFrame(right, fg_color="transparent")
        bf.grid(row=9, column=2, columnspan=2, sticky="e", pady=(4, 0))
        ctk.CTkButton(bf, text="Save Details", command=save, fg_color="#e5e7eb", hover_color="#d1d5db",
                      text_color="#1f2937", width=110, height=35).pack(side="left", padx=4)
        ctk.CTkButton(bf, text="♻ Regenerate", command=regenerate, fg_color="#ede9fe", hover_color="#ddd6fe",
                      text_color="#5b21b6", width=110, height=35).pack(side="left", padx=4)
        ctk.CTkButton(bf, text="🚀 Send Email", command=send_one, fg_color="#dc2626", hover_color="#b91c1c",
                      text_color="#ffffff", width=110, height=35).pack(side="left", padx=4)
        fill(r)

    def clear_data(self):
        if not self._require_candidate():
            return
        if self._job_running(self.cid):
            messagebox.showwarning("Sending", "Emails are still being sent for this candidate. Stop or wait for "
                                              "the send to finish before clearing.")
            return
        name = (cs.get_candidate(self.cid) or {}).get("name")
        if messagebox.askyesno("Clear", f"Delete ALL job records for {name}?  (Sent history logs are kept.)"):
            delete_all_recruiters(self.cid)
            self.load_data()

    def open_settings(self):
        top = self._top("Settings", "520x470")
        ctk.CTkLabel(top, text="Gmail, App Password, resume, signature and CTC are configured per candidate in "
                               "👤 Candidate Setup.", text_color=GRAY, wraplength=480, justify="left").pack(
            anchor="w", padx=14, pady=(12, 4))
        fields = [
            ("OpenAI API Key (optional):", "openai_api_key"),
            ("Delay Between Emails (sec):", "delay_between_emails"),
            ("Max Emails Per Day (per sender):", "max_daily_emails"),
            ("Retry Attempts for Failed:", "retry_count"),
        ]
        entries = {}
        for label, key in fields:
            ctk.CTkLabel(top, text=label, text_color="#1f2937").pack(anchor="w", padx=14, pady=(8, 0))
            e = ctk.CTkEntry(top, width=490, fg_color="#ffffff", border_color="#d1d5db", text_color="#1f2937",
                             show="•" if key == "openai_api_key" else None)
            e.pack(padx=14, pady=2)
            e.insert(0, str(self.settings.get(key, "")))
            entries[key] = e
        ai_var = tk.BooleanVar(value=bool(self.settings.get("use_openai_drafting")))
        ctk.CTkCheckBox(top, text="Use OpenAI to draft emails (falls back to the local generator if the AI draft "
                                  "fails any fact check)", variable=ai_var).pack(anchor="w", padx=14, pady=8)
        auto_var = tk.BooleanVar(value=bool(self.settings.get("auto_approve_soft_review")))
        ctk.CTkCheckBox(top, text="Auto-approve: send every email that has a recruiter email address (skip manual "
                                  "review of soft notes)", variable=auto_var).pack(anchor="w", padx=14, pady=(0, 8))

        def save():
            for k, w in entries.items():
                val = w.get().strip()
                if k in ("delay_between_emails", "max_daily_emails", "retry_count"):
                    try:
                        val = int(val)
                    except ValueError:
                        messagebox.showerror("Settings", f"{k} must be a whole number.", parent=top)
                        return
                self.settings[k] = val
            self.settings["use_openai_drafting"] = ai_var.get()
            self.settings["auto_approve_soft_review"] = auto_var.get()
            save_settings(self.settings)
            top.destroy()
            self.load_data()
            messagebox.showinfo("Saved", "Settings saved.")

        ctk.CTkButton(top, text="Save Settings", command=save, fg_color="#059669", hover_color=GREEN).pack(pady=14)
