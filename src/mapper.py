#!/usr/bin/env python3
import sys
import json

for linea in sys.stdin:
    linea = linea.strip()
    if not linea:
        continue

    try:
        registro = json.loads(linea)
        
        departamento = registro.get("nombre_departamento", "DESCONOCIDO").strip()
        partido = registro.get("nagrupacion_politica")
        
        if not partido:
            partido = registro.get("descripcion", "VOTOS BLANCOS/NULOS").strip()
            
        try:
            votos = int(registro.get("nvotos", 0))
        except ValueError:
            votos = 0
            
        # Emitimos: DEPARTAMENTO|PARTIDO [tab] VOTOS
        print(f"{departamento}|{partido}\t{votos}")
        
    except json.JSONDecodeError:
        pass