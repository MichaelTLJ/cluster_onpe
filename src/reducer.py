#!/usr/bin/env python3
import sys

llave_actual = None
suma_votos = 0

for linea in sys.stdin:
    linea = linea.strip()
    if not linea:
        continue

    try:
        llave, votos_str = linea.split('\t', 1)
        votos = int(votos_str)
    except ValueError:
        continue

    if llave_actual == llave:
        suma_votos += votos
    else:
        if llave_actual is not None:
            dep, part = llave_actual.split('|', 1)
            print(f"{dep}\t{part}\t{suma_votos}")
        
        llave_actual = llave
        suma_votos = votos

# Imprimir el último registro
if llave_actual is not None:
    dep, part = llave_actual.split('|', 1)
    print(f"{dep}\t{part}\t{suma_votos}")