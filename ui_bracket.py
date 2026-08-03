#!/usr/bin/env python3
"""
ui_bracket.py
=============
Las dos ventanas que muestran como va el torneo: la tabla de posiciones de los
12 grupos y el cuadro de eliminacion completo (con los ganadores que ya
avanzaron, los penales y el semaforo de acierto de cada partido).

Son ~180 lineas de armado de widgets que no tienen nada que ver con la pantalla
principal: de todo `App` solo usan `_load_result`, para poder cargar un
resultado con un clic desde el propio cuadro.
"""
from __future__ import annotations

from datetime import datetime

import customtkinter as ctk

import app_data
import bracket
import groups
from teams import abbr, es
from theme import ACCENT, ACCENT2, BAD, BG, CARD, CARD2, F, GOOD, MID, SUB, TXT, WARN


class BracketMixin:
    """Se mezcla en `App`, que aporta la ventana y `_load_result`."""

    def _show_groups(self):
        win = ctk.CTkToplevel(self)
        win.title("Fase de grupos")
        win.geometry("1200x760"); win.configure(fg_color=BG); win.transient(self)
        ctk.CTkLabel(win, text="⚽  FASE DE GRUPOS", font=(F, 20, "bold"), text_color=TXT).pack(anchor="w", padx=20, pady=(14, 2))
        ctk.CTkLabel(win, text="Fondo azul = clasifica (1°/2°)   ·   azul tenue = mejor 3°   ·   "
                              "resultados:  🟢 exacto · 🟡 resultado · 🔴 fallado · gris en juego",
                     font=(F, 12), text_color=SUB).pack(anchor="w", padx=20, pady=(0, 8))
        body = ctk.CTkScrollableFrame(win, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        for i in range(4):
            body.grid_columnconfigure(i, weight=1, uniform="grp")
        fx = app_data.fixture()
        tables = groups.standings(fx)
        status = groups.qualification_status(tables)
        for idx, (g, tt) in enumerate(tables.items()):
            self._group_card(body, g, tt, status, fx, idx)

    def _group_card(self, parent, g, tt, status, fx, idx):
        W, WP = 24, 34
        card = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=12)
        card.grid(row=idx // 4, column=idx % 4, sticky="nsew", padx=4, pady=4)
        ctk.CTkLabel(card, text=f"GRUPO {g}", font=(F, 13, "bold"), text_color=ACCENT).pack(anchor="w", padx=10, pady=(8, 2))
        hrow = ctk.CTkFrame(card, fg_color="transparent")
        hrow.pack(fill="x", padx=7)
        ctk.CTkLabel(hrow, text="Pts", font=(F, 9), text_color=SUB, width=WP).pack(side="right", padx=(4, 0))
        for h in ("DG", "GC", "GF", "PJ"):
            ctk.CTkLabel(hrow, text=h, font=(F, 9), text_color=SUB, width=W).pack(side="right")
        for r in tt:
            stt = status.get(r["team"], "out")
            bg = "#16335c" if stt == "direct" else ("#1b2740" if stt == "third" else CARD2)
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=7, pady=1)
            bar = ctk.CTkFrame(row, fg_color=bg, corner_radius=6)
            bar.pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(bar, image=self.flags.get(r["team"]), text=" " + es(r["team"]), font=(F, 11),
                         text_color=TXT, compound="left", anchor="w").pack(side="left", padx=(5, 0), pady=3)
            for val in (f"{r['dg']:+d}", r["gc"], r["gf"], r["pj"]):
                ctk.CTkLabel(bar, text=str(val), font=(F, 11), text_color=SUB, width=W).pack(side="right")
            ptsbox = ctk.CTkFrame(row, fg_color=bg, corner_radius=6)
            ptsbox.pack(side="right", padx=(4, 0))
            ctk.CTkLabel(ptsbox, text=str(r["pts"]), font=(F, 14, "bold"), text_color=TXT, width=WP).pack(pady=2)
        ctk.CTkFrame(card, fg_color=CARD2, height=1).pack(fill="x", padx=9, pady=(7, 5))
        for m in groups.group_matches(g, fx):
            pf = ctk.CTkFrame(card, fg_color="transparent")
            pf.pack(fill="x", padx=6, pady=1)
            pf.grid_columnconfigure(0, weight=1, uniform="m")
            pf.grid_columnconfigure(2, weight=1, uniform="m")
            state = app_data.match_state(m["kickoff"])
            if m["real"] is not None and state == "done":
                color = {"exact": GOOD, "dir": MID, "miss": BAD}.get(app_data.outcome_type(m["pred"], m["real"]), TXT)
                mid = f" {m['real'][0]}-{m['real'][1]} "
            elif m["real"] is not None:
                color = SUB; mid = f" {m['real'][0]}-{m['real'][1]} "
            else:
                color = SUB; mid = f" {m['kickoff']:%d/%m} "
            ctk.CTkLabel(pf, image=self.flags.get(m["home"]), text=es(m["home"]) + " ", compound="right",
                         font=(F, 10), text_color=TXT).grid(row=0, column=0, sticky="e")
            ctk.CTkLabel(pf, text=mid, font=(F, 11, "bold"), text_color=color).grid(row=0, column=1, padx=1)
            ctk.CTkLabel(pf, image=self.flags.get(m["away"]), text=" " + es(m["away"]), compound="left",
                         font=(F, 10), text_color=TXT).grid(row=0, column=2, sticky="w")
        ctk.CTkFrame(card, fg_color="transparent", height=3).pack()

    def _show_bracket(self):
        old = getattr(self, "_modal", None)
        if old and old.winfo_exists():
            old.destroy()
        win = ctk.CTkToplevel(self)
        self._modal = win; self._modal_reopen = self._show_bracket
        win.title("Llaves de eliminación")
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        win.geometry(f"{min(1500, sw - 30)}x{min(960, sh - 70)}")
        win.configure(fg_color=BG); win.transient(self)
        win.protocol("WM_DELETE_WINDOW", lambda: (setattr(self, "_modal", None), win.destroy()))
        r32 = {m["match"]: m for m in bracket.resolve_r32()}
        self._ko = {m["match"]: m for m in app_data.knockout_fixture()}   # ganadores ya avanzados
        # Lo de "proyección" solo aplica mientras los grupos no cerraron: una vez que los 16avos
        # quedan definidos ya no se proyecta nada, y al terminar todo tampoco queda nada por completar.
        r32_listo = all(self._ko.get(n, {}).get("defined") for n in range(73, 89))
        pendientes = any(not self._ko.get(n, {}).get("defined") for n in bracket.MATCH_DT)
        if not r32_listo:
            titulo = "🏆  LLAVES — proyección según posiciones actuales"
            sub = ("Round of 32 proyectado desde las posiciones de hoy (si se mantuvieran). "
                   "Las rondas siguientes se completan cuando se juegue la eliminación. ")
        else:
            titulo = "🏆  LLAVES — eliminación"
            sub = ("Los 16avos quedaron definidos al cerrar los grupos. "
                   + ("Las rondas siguientes se completan a medida que se juegan. " if pendientes
                      else "Torneo completo. "))
        ctk.CTkLabel(win, text=titulo, font=(F, 18, "bold"),
                     text_color=TXT).pack(anchor="w", padx=20, pady=(12, 2))
        ctk.CTkLabel(win, text=sub + "Fecha y hora de cada partido en horario argentino.",
                     font=(F, 12), text_color=SUB).pack(anchor="w", padx=20, pady=(0, 6))
        body = ctk.CTkFrame(win, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        body.grid_rowconfigure(1, weight=1)
        cols = [("16vos", bracket.LEFT[0]), ("8vos", bracket.LEFT[1]), ("4tos", bracket.LEFT[2]),
                ("Semi", bracket.LEFT[3]), ("FINAL", None), ("Semi", bracket.RIGHT[3]),
                ("4tos", bracket.RIGHT[2]), ("8vos", bracket.RIGHT[1]), ("16vos", bracket.RIGHT[0])]
        for ci, (rname, matches) in enumerate(cols):
            body.grid_columnconfigure(ci, weight=1, uniform="br")
            ctk.CTkLabel(body, text=rname.upper(), font=(F, 11, "bold"), text_color=ACCENT).grid(row=0, column=ci, pady=(0, 4))
            colf = ctk.CTkFrame(body, fg_color="transparent")
            colf.grid(row=1, column=ci, sticky="nsew", padx=2)
            if matches is None:
                self._bracket_center(colf, r32)
            else:
                for mnum in matches:
                    self._bracket_box(colf, mnum, r32.get(mnum))

    def _bracket_center(self, parent, r32):
        ctk.CTkFrame(parent, fg_color="transparent").pack(expand=True)
        ctk.CTkLabel(parent, text="🏆 CAMPEÓN", font=(F, 11, "bold"), text_color=MID).pack(pady=(0, 2))
        self._bracket_box(parent, bracket.FINAL_M, None, expand=False)
        ctk.CTkLabel(parent, text="· 3er puesto ·", font=(F, 10), text_color=SUB).pack(pady=(12, 2))
        self._bracket_box(parent, bracket.THIRD_PLACE, None, expand=False)
        ctk.CTkFrame(parent, fg_color="transparent").pack(expand=True)

    def _bracket_box(self, parent, mnum, info, expand=True):
        box = ctk.CTkFrame(parent, fg_color=CARD2, corner_radius=6)
        box.pack(fill="x", expand=expand, padx=1, pady=1)
        dt = bracket.MATCH_DT.get(mnum)
        if dt:
            d = datetime.strptime(dt, "%Y-%m-%d %H:%M")
            hdr = ctk.CTkFrame(box, fg_color="transparent"); hdr.pack(pady=(1, 0))
            ctk.CTkLabel(hdr, text=f"{d:%d/%m · %H:%M}", font=(F, 9, "bold"), text_color=ACCENT2).pack(side="left")
            km = self._ko.get(mnum, {})
            oc = app_data.outcome_type(km.get("pred"), km.get("real"))
            if oc:                                  # semáforo del acierto: verde exacto / amarillo resultado / rojo fallado
                ctk.CTkLabel(hdr, text=" ●", font=(F, 11),
                             text_color={"exact": GOOD, "dir": MID, "miss": BAD}[oc]).pack(side="left")
            if app_data.needs_pens(km):             # empate de eliminación sin penales -> ⚠ clickeable para cargarlos
                ctk.CTkButton(hdr, text=" ⚠", width=24, height=16, font=(F, 10, "bold"), fg_color="transparent",
                              hover_color=CARD, text_color=WARN, command=lambda mm=km: self._load_result(mm)).pack(side="left")
        self._bracket_team(box, mnum, info, "a")
        ctk.CTkFrame(box, fg_color=CARD, height=1).pack(fill="x", padx=6)
        self._bracket_team(box, mnum, info, "b")

    def _team_chip(self, parent, team, mnum, side):
        km = self._ko.get(mnum, {})
        win = km.get("winner")                          # resalta el que ganó este cruce
        won = win == team
        lost = win is not None and not won
        col = GOOD if won else (SUB if lost else TXT)
        wt = "bold" if won else "normal"
        ctk.CTkLabel(parent, image=self.flags.get(team), text=" " + abbr(team),
                     compound="left", font=(F, 11, wt), text_color=col).pack(side="left")
        real = km.get("real")
        if real is not None:                            # goles a la derecha (+ penales entre paréntesis)
            i = 0 if side == "a" else 1
            txt = str(real[i]) + (f" ({km['pens'][i]})" if km.get("pens") else "")
            ctk.CTkLabel(parent, text=txt, font=(F, 11, wt), text_color=col).pack(side="right")

    def _bracket_team(self, box, mnum, info, side):
        f = ctk.CTkFrame(box, fg_color="transparent")
        f.pack(fill="x", padx=6, pady=1)
        if info is not None:                       # Round of 32 (proyectado)
            team = info["a"] if side == "a" else info["b"]
            if team:
                self._team_chip(f, team, mnum, side)
            else:
                code = info["a_code"] if side == "a" else info["b_code"]
                ctk.CTkLabel(f, text=self._slot_label(code), font=(F, 10), text_color=SUB).pack(side="left")
        elif mnum == bracket.THIRD_PLACE:          # 3er puesto: perdedores de las semis, ya resueltos
            km = self._ko.get(mnum, {})
            team = km.get("home") if side == "a" else km.get("away")
            if team:
                self._team_chip(f, team, mnum, side)
            else:
                ctk.CTkLabel(f, text=f"Perd. M{101 if side == 'a' else 102}", font=(F, 10), text_color=SUB).pack(side="left")
        else:                                      # octavos -> final: el ganador real ya avanzado
            km = self._ko.get(mnum, {})
            team = km.get("home") if side == "a" else km.get("away")
            if team:
                self._team_chip(f, team, mnum, side)
            else:
                sa, sb = bracket.TREE[mnum]
                ctk.CTkLabel(f, text=f"Gan. M{sa if side == 'a' else sb}", font=(F, 10), text_color=SUB).pack(side="left")

    def _slot_label(self, code):
        if code.startswith("3:"):
            return "mejor 3°"
        return f"{code[0]}° {code[1]}"
