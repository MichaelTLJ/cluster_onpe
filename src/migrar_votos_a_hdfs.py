import subprocess
import boto3
import argparse
import os

# Importamos las variables globales de tu entorno
from config import REGION, USUARIO_SSH

def obtener_ips_workers():
    """Consulta a AWS las IPs privadas de las instancias etiquetadas como HadoopWorker"""
    print("Consultando a AWS por los nodos Workers activos...")
    try:
        ec2 = boto3.client('ec2', region_name=REGION) 
        respuesta = ec2.describe_instances(
            Filters=[
                {'Name': 'tag:Rol', 'Values': ['HadoopWorker']},
                {'Name': 'instance-state-name', 'Values': ['running']}
            ]
        )
        
        ips_workers = []
        for reservacion in respuesta['Reservations']:
            for instancia in reservacion['Instances']:
                ips_workers.append(instancia['PrivateIpAddress'])
                
        return ips_workers
    except Exception as e:
        print(f"Error al conectar con AWS: {e}")
        return []

def migrar_votos_especificos(ips, directorio_local, hdfs_base):
    if not ips:
        print("No hay workers activos para migrar.")
        return

    print("\n" + "="*60)
    print("INICIANDO EXTRACCIÓN DE VOTOS HACIA HDFS")
    print("="*60)

    # 1. Crear la carpeta destino centralizada en HDFS
    carpeta_destino_hdfs = f"{hdfs_base}/votos_consolidados"
    print(f"-> Preparando carpeta destino en HDFS: {carpeta_destino_hdfs}")
    subprocess.run(["hdfs", "dfs", "-mkdir", "-p", carpeta_destino_hdfs], check=False)

    for i, ip in enumerate(ips):
        worker_id = f"worker_{i+1}"
        
        print(f"\n[+] Conectando al Worker {worker_id} ({ip})...")
        
        # Copiar el script de limpieza al worker (si existe localmente)
        local_limpiar = os.path.join(os.path.dirname(__file__), "limpiar_actas.py")
        if os.path.exists(local_limpiar):
            scp_cmd = ["scp", "-o", "StrictHostKeyChecking=no", local_limpiar, f"{USUARIO_SSH}@{ip}:/home/{USUARIO_SSH}/limpiar_actas.py"]
            try:
                subprocess.run(scp_cmd, check=False)
                print(f"    Script de limpieza copiado a {ip}")
            except Exception as e:
                print(f"    Advertencia: no se pudo copiar script a {ip}: {e}")

        # El comando que ejecutaremos dentro del Worker hace:
        # 1) Buscar actas (find)
        # 2) Ejecutar el limpiador remoto `limpiar_actas.py` sobre el archivo si existe
        # 3) Subir el archivo limpio a HDFS renombrándolo por worker
        comando_worker = f"""
        source ~/.bashrc &&
        ARCHIVO=$(find {directorio_local} -name "actas_detalle_votos.jsonl" | head -n 1) &&
        if [ ! -z "$ARCHIVO" ]; then
            python3 /home/{USUARIO_SSH}/limpiar_actas.py "$ARCHIVO" && \
            CLEAN="${{ARCHIVO%.jsonl}}_clean.jsonl" && \
            if [ -f "$CLEAN" ]; then
                hdfs dfs -put -f "$CLEAN" "{carpeta_destino_hdfs}/votos_{worker_id}.jsonl" && echo "Exito:$ARCHIVO:$CLEAN" || echo "ErrorHDFS"
            else
                echo "NoClean"
            fi
        else
            echo "Archivo no encontrado"
        fi
        """

        # Ejecutamos el comando remotamente vía SSH
        comando_ssh = ["ssh", "-o", "StrictHostKeyChecking=no", f"{USUARIO_SSH}@{ip}", comando_worker]

        try:
            resultado = subprocess.run(comando_ssh, capture_output=True, text=True)

            if "Exito" in resultado.stdout:
                # Extraemos la ruta real que encontró y la ruta limpia
                parts = resultado.stdout.split("Exito:")[1].strip().split(":")
                ruta_encontrada = parts[0]
                ruta_clean = parts[1] if len(parts) > 1 else ""
                print(f"    Votos encontrados en: {ruta_encontrada}")
                print(f"    Archivo limpio subido a HDFS como: {carpeta_destino_hdfs}/votos_{worker_id}.jsonl")
                print(f"    Ruta limpia en worker: {ruta_clean}")
            elif "Archivo no encontrado" in resultado.stdout:
                print(f"    No se encontró 'actas_detalle_votos.jsonl' en {directorio_local}.")
            elif "NoClean" in resultado.stdout:
                print(f"    Se encontró el archivo pero el limpiador no generó el archivo limpio en {ip}.")
                print(resultado.stdout)
                print(resultado.stderr)
            elif "ErrorHDFS" in resultado.stdout:
                print(f"    Error al subir a HDFS desde {worker_id}:")
                print(resultado.stdout)
                print(resultado.stderr)
            else:
                print(f"    Error procesando datos de {worker_id}:")
                print(resultado.stdout)
                print(resultado.stderr)

        except Exception as e:
            print(f"    Falla de conexión con {worker_id}: {e}")

    print("\n" + "="*60)
    print("MIGRACIÓN FINALIZADA")
    print(f"Puedes verificar ejecutando: hdfs dfs -ls {carpeta_destino_hdfs}")

def main():
    parser = argparse.ArgumentParser(description="Sube SOLO los archivos de votos de los Workers al HDFS")
    
    parser.add_argument(
        "--local-dir", 
        default=f"/home/{USUARIO_SSH}/data_workers", 
        help="La carpeta base en el disco duro del worker (ej: /home/ec2-user/data_workers)"
    )
    
    parser.add_argument(
        "--hdfs-base", 
        default="/onpe", 
        help="La carpeta destino en HDFS (ej: /onpe)"
    )
    
    args = parser.parse_args()
    
    ips = obtener_ips_workers()
    migrar_votos_especificos(ips, args.local_dir, args.hdfs_base)

if __name__ == "__main__":
    main()