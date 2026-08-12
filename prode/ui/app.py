#!/usr/bin/env python3
"""
prode/ui/app.py
===============
Centro de Comando del Prode Mundial 2026. App de escritorio (dark), TRES columnas:
  1) proximo partido con cuenta regresiva (banderas) + puntos de los dos prodes
  2) PARTIDOS DE HOY: antes de jugarse, ficha con el pronostico sugerido y el
     "por que"; en curso o terminado, el resultado (gris mientras no termina, en
     verde/amarillo/rojo cuando suma puntaje) con boton para cargar/editar el
     resultado a mano
  3) MANANA (o "SIGUIENTE FECHA" si manana no hay partidos)
El "dia" cambia a las 4 AM. Aviso 3 h antes del primer partido, bip largo (1.5 s)
10 min antes, recalcular, cambiar pronostico (hasta 1h10 antes) y confirmar carga.

Correr:  python prode_app.py   (el atajo de la raiz)
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime, timedelta

import customtkinter as ctk

from prode import clock, paths
from prode.data import app_data
from prode.tournament import bracket
from prode.tournament.teams import es          # padron unico de las 48 selecciones
from prode.ui.bracket_window import BracketMixin   # ventanas de grupos y de llaves
from prode.ui.single_instance import check_single_instance
from prode.ui.theme import (ACCENT, ACCENT2, BAD, BG, CARD, CARD2, F, GOOD, MID,
                            SUB, TXT, WARN)
from prode.ui.tray import TrayMixin                # bandeja, bips e instancia unica

try:
    from PIL import Image as PILImage   # banderas; sin PIL la app anda sin ellas
except Exception:
    PILImage = None

BASE = paths.ROOT

REMIND_HOURS = 3
BEEP_MIN = 10

ERROR_LOG = paths.ERROR_LOG


def log_error(que: str, detalle: str = "") -> None:
    """Anota un error en prode_error.log sin interrumpir a la app.

    La GUI no puede permitirse morir porque falle una tarea de fondo, pero
    tragarse el error hace que un recalculo que nunca anda parezca que anda.
    El archivo se abre en modo append: interesa la historia, no el ultimo."""
    detalle = detalle or traceback.format_exc()
    try:
        with ERROR_LOG.open("a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}] {que}\n{detalle.rstrip()}\n")
    except OSError:
        pass            # si ni el log se puede escribir, no queda nada por hacer

METHOD_TEXT = (
    "¿Cómo se calculan los pronósticos?\n\n"
    "El modelo estima la fuerza de ataque y defensa de cada selección a partir "
    "de ~50.000 partidos (goles, ajustados por la calidad del rival), combinada "
    "con un rating Elo. Con eso arma la probabilidad de CADA marcador posible.\n\n"
    "El marcador sugerido no es siempre el más probable: es el que maximiza el "
    "PUNTAJE ESPERADO del prode. A veces conviene un resultado que combina mejor "
    "acertar el ganador con pegar el marcador exacto.\n\n"
    "Los partidos recientes pesan más y los amistosos la mitad. Se recalcula "
    "todos los días con los resultados nuevos. Validado en Mundiales, Eurocopas "
    "y Copas América pasadas (2016-2024): 0,91 puntos por partido, contra 0,83 "
    "de tirar siempre 1-0 al favorito."
)




def load_detalle():
    p = paths.PRONOSTICOS_JSON
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []






class App(BracketMixin, TrayMixin, ctk.CTk):
    """La ventana principal. Los mixins aportan las pantallas que no
    comparten nada con esta: las llaves y la bandeja del sistema."""
    def __init__(self, single_srv=None):
        super().__init__()
        self._single_srv = single_srv
        ctk.set_appearance_mode("dark")
        self.title("Centro de Comando · Prode Mundial 2026")
        self.geometry("1380x780")
        self.minsize(1120, 660)
        self.configure(fg_color=BG)
        self._set_window_icon()
        self.after(250, self._set_window_icon)   # CTk a veces pisa el icono al iniciar

        self.fx = []
        self.ko = []
        self.allm = []
        self.nxt = None
        self.detalle = []
        self.beeped = set()
        self.reminded_day = None
        self._last_refresh = 0.0
        self._last_sig = None
        self._shown_match = "init"

        self.flags = {}
        self._load_flags()

        self._build()
        self.refresh_data()
        self.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self._setup_tray()
        if self._single_srv is not None:
            threading.Thread(target=self._single_listen, daemon=True).start()
        # tick() tambien lee datos: si falta data/ (un clon recien bajado, antes de
        # `run.py setup`) reventaba ACA, fuera del try de refresh_data, y con
        # pythonw el usuario no veia ni ventana ni traceback.
        self.tick()

    def _load_flags(self):
        if PILImage is None:
            return
        fdir = paths.FLAGS
        for team, iso in app_data.FLAG_ISO.items():
            p = fdir / f"{iso}.png"
            if not p.exists():
                continue
            try:
                im = PILImage.open(p)
                self.flags[team] = ctk.CTkImage(light_image=im, dark_image=im, size=(30, 20))
            except Exception:
                pass

    def _set_window_icon(self):
        try:
            ico = paths.ICO
            if ico.exists():
                self.iconbitmap(str(ico))
        except Exception:
            pass

    # ---------------- helpers ----------------
    def _team_lbl(self, parent, team, font, color=TXT):
        return ctk.CTkLabel(parent, image=self.flags.get(team), text="  " + es(team),
                            font=font, text_color=color, compound="left")

    def _vs_frame(self, parent, home, away, font):
        f = ctk.CTkFrame(parent, fg_color="transparent")
        self._team_lbl(f, home, font).pack(side="left")
        ctk.CTkLabel(f, text="   vs   ", font=font, text_color=SUB).pack(side="left")
        self._team_lbl(f, away, font).pack(side="left")
        return f

    def _can_change(self, kickoff):
        return (kickoff - clock.now()).total_seconds() > app_data.CHANGE_LIMIT_MIN * 60

    def _fully_loaded(self, m):
        return bool(m["load"][0]) and bool(m["load"][1])   # cargado en AMBOS prodes (también en eliminación)

    def _change_btn(self, parent, m, current):
        if self._can_change(m["kickoff"]):
            ctk.CTkButton(parent, text="✏ cambiar", width=92, height=28, font=(F, 12),
                          fg_color=CARD, hover_color=BG, text_color=ACCENT2,
                          command=lambda: self._edit_pred(m["home"], m["away"], current)).pack(side="left", padx=4)
        else:
            ctk.CTkLabel(parent, text="🔒 cerrado", font=(F, 11), text_color=SUB).pack(side="left", padx=4)

    def _result_btn(self, parent, m):
        txt = "✏ editar resultado" if m["real"] is not None else "📥 cargar resultado"
        ctk.CTkButton(parent, text=txt, width=156, height=28, font=(F, 12),
                      fg_color=CARD, hover_color=BG, text_color=MID,
                      command=lambda: self._load_result(m)).pack(side="right")

    # ---------------- popups ----------------
    def _stepper(self, parent, value, size=24):
        col = ctk.CTkFrame(parent, fg_color="transparent")
        entry = ctk.CTkEntry(col, width=66, height=48, font=(F, size, "bold"), justify="center")

        def step(d):
            try:
                v = int(entry.get())
            except Exception:
                v = 0
            v = max(0, min(40, v + d))
            entry.delete(0, "end"); entry.insert(0, str(v))

        ctk.CTkButton(col, text="+", width=66, height=26, font=(F, 15, "bold"),
                      fg_color=CARD, hover_color=BG, text_color=TXT, command=lambda: step(1)).pack()
        entry.pack(pady=3)
        ctk.CTkButton(col, text="–", width=66, height=26, font=(F, 15, "bold"),
                      fg_color=CARD, hover_color=BG, text_color=TXT, command=lambda: step(-1)).pack()
        entry.insert(0, str(value))
        return col, entry

    def _num_popup(self, title, subtitle, accent, default, on_save, allow_pens=False, pens_default=None):
        modal = getattr(self, "_modal", None)
        modal = modal if (modal and modal.winfo_exists()) else None
        win = ctk.CTkToplevel(self)
        win.title(title)
        win.geometry("400x350" if allow_pens else "400x300")
        win.configure(fg_color=BG); win.transient(modal or self)
        win.lift()
        win.after(60, lambda: (win.grab_set(), win.lift(), win.focus_force()))
        ctk.CTkLabel(win, text=title.upper(), font=(F, 12, "bold"), text_color=accent).pack(pady=(18, 2))
        ctk.CTkLabel(win, text=subtitle, font=(F, 15, "bold"), text_color=TXT).pack(pady=(0, 10))
        row = ctk.CTkFrame(win, fg_color="transparent"); row.pack()
        ch, e_h = self._stepper(row, default[0] if default else 0)
        ch.pack(side="left", padx=10)
        ctk.CTkLabel(row, text="–", font=(F, 24, "bold"), text_color=SUB).pack(side="left")
        ca, e_a = self._stepper(row, default[1] if default else 0)
        ca.pack(side="left", padx=10)
        msg = ctk.CTkLabel(win, text="", font=(F, 11), text_color=BAD); msg.pack(pady=(6, 0))

        pen_e = {}
        sw = prow = None
        if allow_pens:
            sw = ctk.CTkSwitch(win, text="Se definió por penales", font=(F, 12), progress_color=accent)
            sw.pack(pady=(6, 2))
            prow = ctk.CTkFrame(win, fg_color="transparent")
            ctk.CTkLabel(prow, text="penales", font=(F, 10), text_color=SUB).pack()
            pin = ctk.CTkFrame(prow, fg_color="transparent"); pin.pack()
            cph, e_ph = self._stepper(pin, pens_default[0] if pens_default else 0, size=20)
            cph.pack(side="left", padx=8)
            ctk.CTkLabel(pin, text="–", font=(F, 18, "bold"), text_color=SUB).pack(side="left")
            cpa, e_pa = self._stepper(pin, pens_default[1] if pens_default else 0, size=20)
            cpa.pack(side="left", padx=8)
            pen_e = {"sw": sw, "h": e_ph, "a": e_pa}

        def save():
            try:
                h, a = int(e_h.get()), int(e_a.get())
                assert 0 <= h <= 40 and 0 <= a <= 40
            except Exception:
                msg.configure(text="Poné números válidos."); return
            pens = None
            if pen_e and pen_e["sw"].get():
                try:
                    pens = (int(pen_e["h"].get()), int(pen_e["a"].get()))
                except Exception:
                    msg.configure(text="Penales inválidos."); return
            on_save(h, a, pens)
            win.destroy(); self.refresh_data()
            reopen = getattr(self, "_modal_reopen", None)
            if modal and reopen:                   # veníamos de un modal (jornada anterior / llaves) -> recrearlo
                reopen()

        btn = ctk.CTkButton(win, text="Guardar", font=(F, 13, "bold"), fg_color=accent,
                            text_color="#08130d", hover_color="#27c993", command=save)
        btn.pack(pady=14)

        if allow_pens:
            def _toggle_pens():                    # penales SIEMPRE arriba del botón; la ventana crece/encoge
                if sw.get():
                    prow.pack(pady=(4, 0), before=btn)
                    win.geometry("400x510")
                else:
                    prow.pack_forget()
                    win.geometry("400x350")
            sw.configure(command=_toggle_pens)
            if pens_default:
                sw.select(); _toggle_pens()

    def _edit_pred(self, home, away, default=None):
        self._num_popup("Cambiar pronóstico", f"{es(home)}   vs   {es(away)}", ACCENT,
                        default, lambda h, a, pens: app_data.set_prediction(home, away, h, a))

    def _load_result(self, m):
        self._num_popup("Resultado final", f"{es(m['home'])}   vs   {es(m['away'])}", MID,
                        m["real"], lambda h, a, pens: app_data.set_result(m["home"], m["away"], h, a, pens),
                        allow_pens=True, pens_default=m.get("pens"))

    def _mark_finished(self, m):
        app_data.set_finished(m["home"], m["away"], True)
        self.refresh_data()

    def _confirm_load(self, m, pred):
        win = ctk.CTkToplevel(self)
        win.title("Confirmar carga")
        win.geometry("400x290"); win.configure(fg_color=BG); win.transient(self)
        win.after(60, win.grab_set)
        ctk.CTkLabel(win, text="¿YA LO CARGASTE EN LAS WEBS?", font=(F, 12, "bold"), text_color=ACCENT).pack(pady=(20, 2))
        ctk.CTkLabel(win, text=f"{es(m['home'])}   vs   {es(m['away'])}", font=(F, 15, "bold"), text_color=TXT).pack(pady=(0, 4))
        if pred:
            ctk.CTkLabel(win, text=f"pronóstico {pred[0]}-{pred[1]}", font=(F, 12), text_color=SUB).pack(pady=(0, 12))
        sw_gel = ctk.CTkSwitch(win, text=f"Cargado en {app_data.PRODE_NAMES[0]}", font=(F, 13), progress_color=ACCENT)
        sw_gel.pack(pady=6, padx=40, anchor="w")
        if m["load"][0]:
            sw_gel.select()
        sw_meli = ctk.CTkSwitch(win, text=f"Cargado en {app_data.PRODE_NAMES[1]}", font=(F, 13), progress_color=ACCENT2)
        sw_meli.pack(pady=6, padx=40, anchor="w")
        if m["load"][1]:
            sw_meli.select()

        def save():
            app_data.set_confirmation(m["home"], m["away"], gel=bool(sw_gel.get()), meli=bool(sw_meli.get()), pred=pred)
            win.destroy(); self.refresh_data()

        ctk.CTkButton(win, text="Guardar", font=(F, 13, "bold"), fg_color=ACCENT,
                      text_color="#08130d", hover_color="#27c993", command=save).pack(pady=18)

    # ---------------- layout ----------------
    def _build(self):
        pad = 16
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=pad, pady=(pad, 2))
        ctk.CTkLabel(head, text="⚽  CENTRO DE COMANDO", font=(F, 24, "bold"), text_color=TXT).pack(side="left")
        self.recalc_btn = ctk.CTkButton(head, text="🔄 recalcular", width=120, height=30, font=(F, 12),
                                        fg_color=CARD, hover_color=CARD2, text_color=ACCENT, command=self._recalc)
        self.recalc_btn.pack(side="right")
        ctk.CTkButton(head, text="ℹ ¿cómo se calcula?", width=150, height=30, font=(F, 12),
                      fg_color=CARD, hover_color=CARD2, text_color=ACCENT2,
                      command=self._show_method).pack(side="right", padx=8)
        self.prev_btn = ctk.CTkButton(head, text="📋 jornada anterior", width=170, height=30, font=(F, 12),
                                      fg_color=CARD, hover_color=CARD2, text_color=MID,
                                      command=self._show_prev_day)
        self.prev_btn.pack(side="right", padx=(0, 8))
        self.clock = ctk.CTkLabel(self, text="", font=(F, 13), text_color=SUB)
        self.clock.pack(anchor="w", padx=pad + 2)

        self.banner = ctk.CTkFrame(self, fg_color=WARN, corner_radius=12)
        self.banner_lbl = ctk.CTkLabel(self.banner, text="", font=(F, 14, "bold"),
                                       text_color="#1a1300", wraplength=1200, justify="left")
        self.banner_lbl.pack(padx=14, pady=10)

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=pad, pady=(6, pad))
        body.grid_columnconfigure(0, minsize=420, weight=0)
        body.grid_columnconfigure(1, weight=1, uniform="cols")
        body.grid_columnconfigure(2, weight=1, uniform="cols")
        body.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(body, fg_color="transparent")
        left.grid(row=0, column=0, sticky="ns", padx=(0, 10))
        self._build_left(left)

        c1 = ctk.CTkFrame(body, fg_color="transparent")
        c1.grid(row=0, column=1, sticky="nsew", padx=(0, 8))
        ctk.CTkLabel(c1, text="PARTIDOS DE HOY", font=(F, 14, "bold"), text_color=TXT).pack(anchor="w", pady=(0, 4))
        self.col_hoy = ctk.CTkScrollableFrame(c1, fg_color="transparent")
        self.col_hoy.pack(fill="both", expand=True)

        c2 = ctk.CTkFrame(body, fg_color="transparent")
        c2.grid(row=0, column=2, sticky="nsew")
        self.title_man = ctk.CTkLabel(c2, text="MAÑANA", font=(F, 14, "bold"), text_color=TXT)
        self.title_man.pack(anchor="w", pady=(0, 4))
        self.col_man = ctk.CTkScrollableFrame(c2, fg_color="transparent")
        self.col_man.pack(fill="both", expand=True)

    def _build_left(self, left):
        card = ctk.CTkFrame(left, fg_color=CARD, corner_radius=18)
        card.pack(fill="x")
        ctk.CTkLabel(card, text="PRÓXIMO PARTIDO", font=(F, 13, "bold"), text_color=ACCENT).pack(anchor="w", padx=20, pady=(18, 6))
        self.match_holder = ctk.CTkFrame(card, fg_color="transparent")
        self.match_holder.pack(anchor="w", padx=20)
        self.when_lbl = ctk.CTkLabel(card, text="", font=(F, 14), text_color=SUB)
        self.when_lbl.pack(anchor="w", padx=20, pady=(4, 8))
        self.count_lbl = ctk.CTkLabel(card, text="--:--:--", font=("Consolas", 56, "bold"), text_color=ACCENT2)
        self.count_lbl.pack(padx=20, pady=(0, 4))
        self.pred_lbl = ctk.CTkLabel(card, text="", font=(F, 15), text_color=TXT)
        self.pred_lbl.pack(padx=20, pady=(0, 18))

        scores = ctk.CTkFrame(left, fg_color="transparent")
        scores.pack(fill="x", pady=(12, 0))
        scores.grid_columnconfigure((0, 1), weight=1, uniform="s")

        # PRIMER PRODE: dos torneos separados (grupos congela el 28/06; eliminación desde cero)
        cg = ctk.CTkFrame(scores, fg_color=CARD, corner_radius=18)
        cg.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        ctk.CTkLabel(cg, text=app_data.PRODE_NAMES[0].upper(), font=(F, 13, "bold"), text_color=ACCENT).pack(anchor="w", padx=16, pady=(16, 2))
        self.gel_cards = {}
        for stage, lbl in (("grupos", "GRUPOS"), ("elim", "ELIMINACIÓN")):
            ctk.CTkLabel(cg, text=lbl, font=(F, 10, "bold"), text_color=SUB).pack(anchor="w", padx=16, pady=(7, 0))
            tot = ctk.CTkLabel(cg, text="0", font=(F, 30, "bold"), text_color=TXT)
            tot.pack(anchor="w", padx=16)
            det = ctk.CTkLabel(cg, text="", font=(F, 11), text_color=SUB, justify="left")
            det.pack(anchor="w", padx=16, pady=(0, 2))
            self.gel_cards[stage] = (tot, det)
        ctk.CTkFrame(cg, fg_color="transparent", height=10).pack()

        # SEGUNDO PRODE: una sola tabla continua (grupos + eliminación juntos)
        cm = ctk.CTkFrame(scores, fg_color=CARD, corner_radius=18)
        cm.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        ctk.CTkLabel(cm, text=app_data.PRODE_NAMES[1].upper(), font=(F, 13, "bold"), text_color=ACCENT2).pack(anchor="w", padx=16, pady=(16, 0))
        self.meli_total = ctk.CTkLabel(cm, text="0", font=(F, 46, "bold"), text_color=TXT)
        self.meli_total.pack(anchor="w", padx=16)
        ctk.CTkLabel(cm, text="puntos", font=(F, 12), text_color=SUB).pack(anchor="w", padx=16)
        self.meli_detail = ctk.CTkLabel(cm, text="", font=(F, 12), text_color=SUB, justify="left")
        self.meli_detail.pack(anchor="w", padx=16, pady=(8, 16))

        btns = ctk.CTkFrame(left, fg_color="transparent")
        btns.pack(fill="x", pady=(14, 0))
        btns.grid_columnconfigure((0, 1), weight=1, uniform="b")
        ctk.CTkButton(btns, text="📊 ver fixture grupos", height=40, font=(F, 13, "bold"),
                      fg_color=CARD, hover_color=CARD2, text_color=TXT,
                      command=self._show_groups).grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(btns, text="🏆 ver llaves", height=40, font=(F, 13, "bold"),
                      fg_color=CARD, hover_color=CARD2, text_color=TXT,
                      command=self._show_bracket).grid(row=0, column=1, sticky="ew", padx=(6, 0))

    # ---------------- data ----------------
    def refresh_data(self):
        try:
            now = clock.now()
            self.fx = app_data.fixture()
            self.ko = app_data.knockout_fixture()
            self.allm = self.fx + self.ko
            self.nxt = app_data.next_match(fx=self.allm)
            self.detalle = load_detalle()
            sig = self._data_signature(now)
            if sig != self._last_sig:        # solo recrea la pantalla si de verdad cambio algo
                self._last_sig = sig
                self._update_scores()
                self._update_columns()
        except FileNotFoundError as e:
            # El caso mas comun de todos: un clon recien bajado, antes de correr
            # el setup. Decirle QUE hacer vale mas que mostrarle la ruta.
            self.when_lbl.configure(text="faltan los datos — corré:  python run.py setup")
            log_error(f"refresh_data: falta {e.filename or e}")
        except Exception as e:
            # En pantalla entra el mensaje corto; el traceback va al log, que es
            # lo unico que sirve para saber que dato lo rompio.
            self.when_lbl.configure(text=f"error: {e}")
            log_error("refresh_data")
        self._last_refresh = time.time()

    def _data_signature(self, now):
        """Firma de lo visible; si no cambia entre refrescos no se recrea ningún
        widget (evita que CustomTkinter acumule handles/memoria con las horas)."""
        sig = [app_data.logical_today(now).isoformat()]
        for m in self.allm:
            sig.append((m.get("home"), m.get("away"), m.get("a_label"), m.get("b_label"),
                        m["real"], m.get("pens"), m["pred"], tuple(m["load"]),
                        app_data.match_state(m["kickoff"], now, m.get("home"), m.get("away"))))
        for o in self.detalle:
            sig.append((o.get("home"), o.get("away"), tuple(o.get("best", ()))))
        return repr(sig)

    def _update_scores(self):
        board = app_data.scoreboard(self.allm)
        gb = board.get(app_data.PRODE_NAMES[0], {})
        for stage, (tot, det) in self.gel_cards.items():
            s = gb.get(stage, {})
            tot.configure(text=str(s.get("total", 0)))
            if stage == "elim" and s.get("n", 0) == 0:
                det.configure(text="arranca el 28/06")
            else:
                det.configure(text=f"{s.get('n', 0)} jug · {s.get('exact', 0)} ex · {s.get('dir', 0)} dir · {s.get('fail', 0)} fall")
        mpe, mpdir = app_data.PRODES[app_data.PRODE_NAMES[1]]
        mb = board.get(app_data.PRODE_NAMES[1], {})
        self.meli_total.configure(text=str(mb.get("total", 0)))
        self.meli_detail.configure(text=f"{mb.get('n', 0)} jugados\n{mb.get('exact', 0)} exactos (+{mpe})\n"
                                        f"{mb.get('dir', 0)} resultado (+{mpdir})\n{mb.get('fail', 0)} fallados")

    def _next_day_after(self, day):
        days = sorted({app_data.logical_date(m["kickoff"]) for m in self.allm
                       if app_data.logical_date(m["kickoff"]) > day})
        return days[0] if days else None

    def _update_columns(self):
        for w in self.col_hoy.winfo_children():
            w.destroy()
        for w in self.col_man.winfo_children():
            w.destroy()
        today = app_data.logical_today()
        det = {(o["home"], o["away"]): o for o in self.detalle}

        todays = sorted([m for m in self.allm if app_data.logical_date(m["kickoff"]) == today], key=lambda m: m["kickoff"])
        if not todays:
            self._muted(self.col_hoy, "No hay partidos hoy.")
        for m in todays:
            self._match_card(self.col_hoy, m, det, today_col=True)

        # Aviso en el boton de "jornada anterior" si hay partidos ya pasados sin
        # resultado cargado. Sobre `allm` y no `fx`: fx son solo los 72 de grupos,
        # asi que desde que empezo la eliminacion el aviso no avisaba nada. El
        # `defined` saltea las llaves sin rival todavia, igual que hace el modal.
        falta = sum(1 for m in self.allm
                    if m.get("defined", True)
                    and app_data.logical_date(m["kickoff"]) < today and m["real"] is None)
        self.prev_btn.configure(
            text=f"📋 jornada anterior  ⚠{falta}" if falta else "📋 jornada anterior",
            text_color=WARN if falta else MID)

        tomorrow = today + timedelta(days=1)
        if any(app_data.logical_date(m["kickoff"]) == tomorrow for m in self.allm):
            day3 = tomorrow
            self.title_man.configure(text="MAÑANA")
        else:
            day3 = self._next_day_after(today)
            self.title_man.configure(text=f"SIGUIENTE FECHA · {day3:%d/%m}" if day3 else "SIGUIENTE FECHA")
        day3_matches = sorted([m for m in self.allm if day3 and app_data.logical_date(m["kickoff"]) == day3],
                              key=lambda m: m["kickoff"])
        if not day3_matches:
            self._muted(self.col_man, "No hay más partidos cargados.")
        for m in day3_matches:
            self._match_card(self.col_man, m, det, today_col=False)

    def _muted(self, parent, text):
        ctk.CTkLabel(parent, text=text, font=(F, 13), text_color=SUB).pack(anchor="w", padx=8, pady=4)

    def _match_card(self, parent, m, det, today_col):
        if m.get("stage") == "ko" and not m.get("defined"):
            self._ko_placeholder(parent, m)             # cruce de eliminación sin equipos -> placeholder
            return
        o = det.get((m.get("home"), m.get("away")))
        state = app_data.match_state(m["kickoff"], home=m.get("home"), away=m.get("away"))
        if today_col and state == "done" and m["real"] is not None:
            self._result_row(parent, m, state)          # terminado -> fila compacta
        else:
            self._pred_card(parent, m, o, live=(today_col and state != "pre"))

    def _round_name(self, mnum):
        if mnum == bracket.THIRD_PLACE:
            return "3er puesto"
        for name, nums in bracket.ROUNDS:
            if mnum in nums:
                return name
        return "eliminación"

    def _ko_placeholder(self, parent, m):
        c = ctk.CTkFrame(parent, fg_color=CARD2, corner_radius=12)
        c.pack(fill="x", padx=4, pady=4)
        head = ctk.CTkFrame(c, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(10, 2))
        ctk.CTkLabel(head, text=f"{m['kickoff']:%d/%m · %H:%M}", font=(F, 13, "bold"), text_color=SUB).pack(side="left")
        ctk.CTkLabel(head, text=f"M{m['match']} · {self._round_name(m['match'])}", font=(F, 10),
                     text_color=ACCENT2).pack(side="right")
        self._ko_side(c, m["home"], m["a_label"])
        ctk.CTkLabel(c, text="vs", font=(F, 10), text_color=SUB).pack(anchor="w", padx=20)
        self._ko_side(c, m["away"], m["b_label"])
        pend = ("se define al cerrar los grupos" if m["match"] <= 88
                else "se define cuando se jueguen los cruces previos")
        ctk.CTkLabel(c, text=pend, font=(F, 10, "italic"),
                     text_color=SUB).pack(anchor="w", padx=14, pady=(2, 10))

    def _ko_side(self, parent, team, label):
        if team:
            self._team_lbl(parent, team, (F, 14, "bold")).pack(anchor="w", padx=14, pady=1)
        else:
            ctk.CTkLabel(parent, text=label, font=(F, 13), text_color=TXT,
                         wraplength=380, justify="left").pack(anchor="w", padx=14, pady=1)

    def _result_row(self, parent, m, state="done"):
        row = ctk.CTkFrame(parent, fg_color=CARD2, corner_radius=10)
        row.pack(fill="x", padx=4, pady=4)
        line = ctk.CTkFrame(row, fg_color="transparent")
        line.pack(fill="x", padx=14, pady=(10, 2))
        left = ctk.CTkFrame(line, fg_color="transparent")
        left.pack(side="left")
        ctk.CTkLabel(left, text=f"{m['kickoff']:%H:%M}", font=(F, 13, "bold"), text_color=SUB).pack(side="left", padx=(0, 10))
        self._team_lbl(left, m["home"], (F, 14, "bold")).pack(side="left")
        ctk.CTkLabel(left, text=" vs ", font=(F, 13), text_color=SUB).pack(side="left")
        self._team_lbl(left, m["away"], (F, 14, "bold")).pack(side="left")
        if state == "done":
            color = {"exact": GOOD, "dir": MID, "miss": BAD}.get(app_data.outcome_type(m["pred"], m["real"]), TXT)
            sub = f"pronostiqué {m['pred'][0]}-{m['pred'][1]}" if m["pred"] else "sin pronóstico"
        else:
            color = SUB                       # gris: en curso, todavia no suma
            sub = "en juego · todavía no suma"
        rbox = ctk.CTkFrame(line, fg_color="transparent")
        rbox.pack(side="right")
        ctk.CTkLabel(rbox, text=f"{m['real'][0]}-{m['real'][1]}", font=(F, 20, "bold"), text_color=color).pack(anchor="e")
        if m.get("pens"):
            ctk.CTkLabel(rbox, text=f"pen {m['pens'][0]}-{m['pens'][1]}", font=(F, 10, "bold"), text_color=ACCENT2).pack(anchor="e")
        foot = ctk.CTkFrame(row, fg_color="transparent")
        foot.pack(fill="x", padx=14, pady=(0, 8))
        ctk.CTkLabel(foot, text=sub, font=(F, 11), text_color=SUB).pack(side="left")
        self._result_btn(foot, m)
        if app_data.needs_pens(m):                 # empate de eliminación sin penales -> avisar + permitir cargarlos
            ctk.CTkButton(foot, text="⚠ definir penales", width=142, height=28, font=(F, 12, "bold"),
                          fg_color=CARD, hover_color=BG, text_color=WARN,
                          command=lambda: self._load_result(m)).pack(side="right", padx=(0, 6))

    def _pending_row(self, parent, m):
        """Partido de una jornada anterior que todavía no tiene resultado cargado."""
        row = ctk.CTkFrame(parent, fg_color=CARD2, corner_radius=10)
        row.pack(fill="x", padx=4, pady=4)
        line = ctk.CTkFrame(row, fg_color="transparent")
        line.pack(fill="x", padx=14, pady=(10, 2))
        left = ctk.CTkFrame(line, fg_color="transparent")
        left.pack(side="left")
        ctk.CTkLabel(left, text=f"{m['kickoff']:%d/%m %H:%M}", font=(F, 12, "bold"), text_color=WARN).pack(side="left", padx=(0, 10))
        self._team_lbl(left, m["home"], (F, 14, "bold")).pack(side="left")
        ctk.CTkLabel(left, text=" vs ", font=(F, 13), text_color=SUB).pack(side="left")
        self._team_lbl(left, m["away"], (F, 14, "bold")).pack(side="left")
        foot = ctk.CTkFrame(row, fg_color="transparent")
        foot.pack(fill="x", padx=14, pady=(0, 8))
        pred_txt = f"pronostiqué {m['pred'][0]}-{m['pred'][1]}" if m["pred"] else "sin pronóstico"
        ctk.CTkLabel(foot, text=f"ya se jugó · {pred_txt}", font=(F, 11), text_color=SUB).pack(side="left")
        self._result_btn(foot, m)

    def _pred_card(self, parent, m, o, live=False):
        c = ctk.CTkFrame(parent, fg_color=CARD2, corner_radius=12)
        c.pack(fill="x", padx=4, pady=4)
        head = ctk.CTkFrame(c, fg_color="transparent")
        head.pack(fill="x", padx=14, pady=(10, 0))
        left = ctk.CTkFrame(head, fg_color="transparent")
        left.pack(side="left")
        ctk.CTkLabel(left, text=f"{m['kickoff']:%H:%M}", font=(F, 13, "bold"), text_color=SUB).pack(side="left", padx=(0, 10))
        self._team_lbl(left, m["home"], (F, 14, "bold")).pack(side="left")
        ctk.CTkLabel(left, text=" vs ", font=(F, 13), text_color=SUB).pack(side="left")
        self._team_lbl(left, m["away"], (F, 14, "bold")).pack(side="left")
        if live and m["real"] is not None:                 # resultado en curso (gris)
            rb = ctk.CTkFrame(head, fg_color="transparent")
            rb.pack(side="right")
            ctk.CTkLabel(rb, text="en juego", font=(F, 10), text_color=SUB).pack(anchor="e")
            ctk.CTkLabel(rb, text=f"{m['real'][0]}-{m['real'][1]}", font=(F, 20, "bold"), text_color=SUB).pack(anchor="e")
            if m.get("pens"):
                ctk.CTkLabel(rb, text=f"pen {m['pens'][0]}-{m['pens'][1]}", font=(F, 10, "bold"), text_color=ACCENT2).pack(anchor="e")
        elif o:                                            # marcador sugerido (gris)
            sg = ctk.CTkFrame(head, fg_color="transparent")
            sg.pack(side="right")
            ctk.CTkLabel(sg, text="sugerido", font=(F, 10), text_color=SUB).pack(anchor="e")
            ctk.CTkLabel(sg, text=f"{o['best'][0]}-{o['best'][1]}", font=(F, 20, "bold"), text_color=SUB).pack(anchor="e")

        if o:
            x12 = (f"Gana {es(m['home'])} {o['p_home']:.0f}%   ·   empate {o['p_draw']:.0f}%"
                   f"   ·   gana {es(m['away'])} {o['p_away']:.0f}%")
            ctk.CTkLabel(c, text=x12, font=(F, 12), text_color=SUB, wraplength=430, justify="left").pack(anchor="w", padx=14, pady=(4, 0))
            ctk.CTkLabel(c, text=f"Goles esperados {o['lh']:.1f}–{o['la']:.1f}    ·    Elo {o['elo_home']}–{o['elo_away']}",
                         font=(F, 12), text_color=SUB).pack(anchor="w", padx=14)
            tops = "   ·   ".join(f"{t[0]}-{t[1]} ({t[2]:.0f}%)" for t in o["top"][:4])
            ctk.CTkLabel(c, text=f"Más probables:  {tops}", font=(F, 12), text_color=SUB,
                         wraplength=430, justify="left").pack(anchor="w", padx=14, pady=(0, 2))
            if list(o["best"]) != o["top"][0][:2]:
                t0 = o["top"][0]
                ctk.CTkLabel(c, text=f"💡 Sugiere {o['best'][0]}-{o['best'][1]} y no el más probable ({t0[0]}-{t0[1]}).",
                             font=(F, 11, "italic"), text_color=ACCENT2, wraplength=430, justify="left").pack(anchor="w", padx=14, pady=(0, 2))

        pred = m["pred"] or (tuple(o["best"]) if o else None)

        f1 = ctk.CTkFrame(c, fg_color="transparent")
        f1.pack(fill="x", padx=14, pady=(6, 0))
        if m["pred"]:
            ctk.CTkLabel(f1, text=f"Tu pronóstico: {m['pred'][0]}-{m['pred'][1]}", font=(F, 12, "bold"), text_color=TXT).pack(side="left")
        else:
            ctk.CTkLabel(f1, text="Tu pronóstico: sin cargar", font=(F, 12), text_color=WARN).pack(side="left")
        if not live:
            self._change_btn(f1, m, pred)
        if live and m["real"] is not None:
            ctk.CTkLabel(c, text="todavía no suma puntaje", font=(F, 11), text_color=SUB).pack(anchor="w", padx=14, pady=(2, 0))

        f2 = ctk.CTkFrame(c, fg_color="transparent")
        f2.pack(fill="x", padx=14, pady=(4, 10))
        if live:
            if m["real"] is None:
                ctk.CTkLabel(f2, text="¿ya terminó?", font=(F, 12), text_color=SUB).pack(side="left")
            else:
                ctk.CTkButton(f2, text="✓ terminó el partido", width=170, height=28, font=(F, 12),
                              fg_color=CARD, hover_color=BG, text_color=GOOD,
                              command=lambda: self._mark_finished(m)).pack(side="left")
            self._result_btn(f2, m)
        else:
            st = ctk.CTkFrame(f2, fg_color="transparent")
            st.pack(side="left")
            ctk.CTkLabel(st, text=f"{app_data.PRODE_SHORT[0]} " + ("✓" if m["load"][0] else "○"), font=(F, 12),
                         text_color=GOOD if m["load"][0] else SUB).pack(side="left", padx=(0, 10))
            ctk.CTkLabel(st, text=f"{app_data.PRODE_SHORT[1]} " + ("✓" if m["load"][1] else "○"), font=(F, 12),
                         text_color=GOOD if m["load"][1] else SUB).pack(side="left")
            if self._fully_loaded(m):
                ctk.CTkLabel(f2, text="✓ cargado", font=(F, 12, "bold"), text_color=GOOD).pack(side="right")
            else:
                ctk.CTkButton(f2, text="✓ confirmar carga", width=140, height=28, font=(F, 12),
                              fg_color=CARD, hover_color=BG, text_color=ACCENT,
                              command=lambda: self._confirm_load(m, pred)).pack(side="right")

    # ---------------- loop ----------------
    def tick(self):
        now = clock.now()
        reloj = now.strftime("%A %d/%m · %H:%M:%S").capitalize()
        if clock.simulado():
            # Que se note: una captura del modo demo no puede pasar por una real.
            self.clock.configure(text=f"{reloj}   ·   ⏱ MODO DEMO", text_color=WARN)
        else:
            self.clock.configure(text=reloj)
        try:
            if time.time() - self._last_refresh > 300:   # auto-refresh cada 5 min (y solo recrea si cambió)
                self.refresh_data()
            self._update_countdown(now)
            self._check_reminder(now)
        except Exception:
            # El reloj tiene que seguir andando pase lo que pase: si esto se
            # propaga, muere el bucle de after() y la ventana queda congelada.
            log_error("tick")
        self.after(1000, self.tick)

    def _update_countdown(self, now):
        m = self.nxt
        key = (m.get("match"), m["home"], m["away"]) if m else None
        if key != self._shown_match:
            self._shown_match = key
            for w in self.match_holder.winfo_children():
                w.destroy()
            if m and m["home"]:
                self._vs_frame(self.match_holder, m["home"], m["away"], (F, 23, "bold")).pack(anchor="w")
            elif m:                                       # cruce de eliminación sin equipos todavía
                ctk.CTkLabel(self.match_holder, text=f"{m['a_label']}\nvs  {m['b_label']}", font=(F, 15, "bold"),
                             text_color=TXT, justify="left").pack(anchor="w")
            else:
                ctk.CTkLabel(self.match_holder, text="Fin del Mundial", font=(F, 22, "bold"), text_color=TXT).pack(anchor="w")
        if not m:
            self.when_lbl.configure(text=""); self.count_lbl.configure(text="--:--:--"); self.pred_lbl.configure(text="")
            return
        when = "Hoy" if app_data.logical_date(m["kickoff"]) == app_data.logical_today(now) else m["kickoff"].strftime("%a %d/%m")
        host = "   · local" if m["host"] else ""
        self.when_lbl.configure(text=f"{when} {m['kickoff']:%H:%M} (Arg){host}")
        self.pred_lbl.configure(text=f"Tu pronóstico:  {m['pred'][0]}-{m['pred'][1]}" if m["pred"] else "Tu pronóstico:  (sin cargar)")
        secs = int((m["kickoff"] - now).total_seconds())
        if secs < 0:
            self.count_lbl.configure(text="¡EN JUEGO!", text_color=ACCENT)
            self.refresh_data(); return
        h, r = divmod(secs, 3600)
        mi, se = divmod(r, 60)
        self.count_lbl.configure(text=f"{h:02d}:{mi:02d}:{se:02d}", text_color=ACCENT2)
        if 0 < secs <= BEEP_MIN * 60 and m["home"] and key not in self.beeped:
            self.beeped.add(key)
            self.beep_long()
            self._show_banner(f"⏰ ¡{es(m['home'])} vs {es(m['away'])} en {BEEP_MIN} minutos!", 60)

    def _check_reminder(self, now):
        lday = app_data.logical_today(now)
        first = app_data.first_match_on(lday, fx=self.allm)
        if not first:
            return
        start = first["kickoff"] - timedelta(hours=REMIND_HOURS)
        if start <= now < first["kickoff"] and self.reminded_day != lday:
            faltan = [m for m in self.allm if app_data.logical_date(m["kickoff"]) == lday
                      and not m["pred"] and m.get("home")]
            if faltan:
                self.reminded_day = lday
                self.beep_reminder()
                self._show_banner(f"📋 ¡Cargá el prode! Primer partido {first['kickoff']:%H:%M} — te faltan {len(faltan)} pronóstico(s)")
                try:
                    self.deiconify(); self.lift()
                except Exception:
                    pass

    # ---------------- banner / popup / recalc ----------------
    def _show_banner(self, text, auto_hide=None):
        self.banner_lbl.configure(text=text)
        self.banner.pack(fill="x", padx=16, pady=(0, 4), after=self.clock)
        if auto_hide:
            self.after(auto_hide * 1000, self.banner.pack_forget)

    def _show_prev_day(self):
        old = getattr(self, "_modal", None)
        if old and old.winfo_exists():
            old.destroy()
        win = ctk.CTkToplevel(self)
        self._modal = win; self._modal_reopen = self._show_prev_day
        win.title("Jornada anterior")
        win.geometry("580x660"); win.configure(fg_color=BG); win.transient(self)
        win.protocol("WM_DELETE_WINDOW", lambda: (setattr(self, "_modal", None), win.destroy()))
        win.after(60, win.grab_set)
        today = app_data.logical_today()
        yest = today - timedelta(days=1)
        fx = self.allm or app_data.fixture()
        prev = sorted([m for m in fx
                       if m.get("defined", True)
                       and (app_data.logical_date(m["kickoff"]) == yest
                            or (app_data.logical_date(m["kickoff"]) < today and m["real"] is None))],
                      key=lambda m: m["kickoff"])
        falta = sum(1 for m in prev if m["real"] is None)
        ctk.CTkLabel(win, text="📋  JORNADA ANTERIOR", font=(F, 20, "bold"), text_color=TXT).pack(anchor="w", padx=20, pady=(14, 2))
        sub = f"{yest:%d/%m}" + (f"   ·   ⚠ faltan {falta} por cargar" if falta else "   ·   todo cargado ✓")
        ctk.CTkLabel(win, text=sub, font=(F, 13), text_color=WARN if falta else SUB).pack(anchor="w", padx=20, pady=(0, 8))
        body = ctk.CTkScrollableFrame(win, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        if not prev:
            self._muted(body, "No hay partidos en la jornada anterior.")
        for m in prev:
            if m["real"] is not None:
                self._result_row(body, m)
            else:
                self._pending_row(body, m)









    def _show_method(self):
        win = ctk.CTkToplevel(self)
        win.title("¿Cómo se calculan?")
        win.geometry("480x400"); win.configure(fg_color=BG); win.transient(self)
        ctk.CTkLabel(win, text=METHOD_TEXT, justify="left", wraplength=440, font=(F, 13), text_color=TXT).pack(padx=20, pady=20, anchor="w")

    def _recalc(self):
        self.recalc_btn.configure(text="recalculando…", state="disabled")
        def run():
            # El error se anota y se avisa en el boton: antes se tragaba entero,
            # asi que un recalculo que fallaba siempre se veia igual que uno que
            # andaba, y los pronosticos quedaban viejos sin que nada lo dijera.
            ok = False
            try:
                p = subprocess.run([sys.executable, "-m", "scripts.build_pronosticos"],
                                   cwd=str(BASE), capture_output=True, timeout=180, text=True)
                ok = p.returncode == 0
                if not ok:
                    log_error(f"build_pronosticos.py salio con codigo {p.returncode}",
                              (p.stderr or p.stdout or "").strip())
            except subprocess.TimeoutExpired:
                log_error("build_pronosticos.py no termino en 180 s", "timeout")
            except OSError:
                log_error("no se pudo lanzar build_pronosticos.py")
            self.after(0, lambda: self._recalc_done(ok))
        threading.Thread(target=run, daemon=True).start()

    def _recalc_done(self, ok=True):
        self.refresh_data()
        try:
            self.recalc_btn.configure(
                text="🔄 recalcular" if ok else "⚠ falló — ver prode_error.log",
                state="normal")
        except Exception:
            pass











def main():
    """Abre la app. Lo llama el atajo `prode_app.py` de la raiz (y Prode.bat)."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("prode.mundial.2026")
        except Exception:
            pass
    srv = check_single_instance()
    if srv is None:
        sys.exit(0)            # ya hay una instancia viva; le pedimos que se muestre
    try:
        app = App(srv if srv else None)   # srv == False -> puerto colgado, abrir sin lock
        if "--minimized" in sys.argv:
            app.after(300, app.hide_to_tray)
        app.mainloop()
    except SystemExit:
        raise
    except Exception:
        log_error("la app se cerro con un error")
        raise


if __name__ == "__main__":
    main()
