#!/usr/bin/env python3
"""
parse_thirds.py
===============
Descarga la tabla oficial de asignacion de los 8 mejores terceros del Mundial
2026 (495 combinaciones, Annex C del reglamento) desde la plantilla de Wikipedia
y la guarda en thirds_table.json.

Clave: combinacion de los 8 grupos que aportan tercero (string ordenado, ej.
"BDEFIJKL"). Valor: {match_number: grupo_del_tercero} para los 8 cruces de
"1ro vs mejor 3ro" (M74, M77, M79, M80, M81, M82, M85, M87).
"""
import json
import re
import urllib.request

from prode import paths

URL = ("https://en.wikipedia.org/w/api.php?action=parse"
       "&page=Template:2026_FIFA_World_Cup_third-place_table"
       "&prop=wikitext&format=json&formatversion=2")

# Orden de las columnas de la tabla: 1A, 1B, 1D, 1E, 1G, 1I, 1K, 1L.
# Cada una corresponde al match donde ese 1ro de grupo enfrenta a un 3ro:
#   1A->M79, 1B->M85, 1D->M81, 1E->M74, 1G->M82, 1I->M77, 1K->M87, 1L->M80
SLOTS = [79, 85, 81, 74, 82, 77, 87, 80]


def main():
    req = urllib.request.Request(URL, headers={"User-Agent": "prode/1.0"})
    wt = json.loads(urllib.request.urlopen(req, timeout=40).read())["parse"]["wikitext"]
    table = {}
    for block in wt.split('! scope="row" |')[1:]:
        groups = re.findall(r"'''([A-L])'''", block)
        assigns = re.findall(r"\b3([A-L])\b", block)
        if len(groups) == 8 and len(assigns) >= 8:
            table["".join(sorted(groups))] = {str(m): g for m, g in zip(SLOTS, assigns[:8])}
    print("filas parseadas:", len(table))
    print("67  (BDEFIJKL):", table.get("BDEFIJKL"))
    print("494 (ABCDEFGI):", table.get("ABCDEFGI"))
    with open(paths.THIRDS_JSON, "w", encoding="utf-8") as f:
        json.dump(table, f, ensure_ascii=False)
    print("guardado thirds_table.json con", len(table), "combinaciones")


if __name__ == "__main__":
    main()
