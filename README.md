# ONPE-CONSULTA: Electoral Data Crawler Distribuido

Sistema de extracción masiva y distribuida de datos electorales de la ONPE (Perú) diseñado para operar sobre un clúster de alto rendimiento en AWS utilizando Hadoop HDFS para el almacenamiento persistente.

## Arquitectura del Sistema

El proyecto utiliza una arquitectura **Maestro-Worker** automatizada mediante la SDK de AWS (Boto3):

* **Nodo Maestro:** Centraliza la orquestación, realiza el balanceo de carga (LPT - Longest Processing Time) basado en la complejidad de los departamentos y distribuye el código fuente.
* **Nodos Workers:** Instancias dinámicas de EC2 que ejecutan el motor de extracción en paralelo y sincronizan los resultados directamente con el NameNode del clúster Hadoop.
* **Almacenamiento:** Los datos se procesan localmente en *staging* y se cargan de forma masiva en **HDFS** para evitar el problema de archivos pequeños y garantizar la integridad de los datos.

## Estructura del Proyecto

```text
ONPE-CONSULTA/
├── src/
│   ├── config.py             # Configuración centralizada de AWS (AMI, SG, Subnet)
│   ├── levantar_cluster.py   # Gestión de infraestructura (Provisionamiento de EC2)
│   ├── orchestrator.py       # Cerebro del clúster (Descubrimiento y despacho)
│   └── worker_descarga.py    # Motor de crawling y sincronización HDFS
├── data/                     # Carpeta local para resultados temporales (staging)
├── .gitignore
├── requirements.txt          # Dependencias de Python (boto3, requests)
└── README.md
```


## Análisis de Componentes (`src/`)

El núcleo del proyecto reside en la carpeta `src/`, donde la lógica de infraestructura y la de extracción de datos se mantienen completamente desacopladas.

### 1. `config.py` (Configuración de Infraestructura)
Actúa como el registro central de variables del sistema. 
* **Propósito:** Evitar código duro (*hardcoding*) en los scripts principales. 
* **Contenido:** Almacena identificadores críticos de AWS como la Región (`us-east-1`), el ID de la imagen (AMI), el par de llaves SSH, y los identificadores de red (`SECURITY_GROUP_ID` y `SUBNET_ID`) que permiten la comunicación interna del clúster a través de los puertos de Hadoop.

### 2. `levantar_cluster.py` (Gestor de Infraestructura / IaC)
Herramienta de línea de comandos construida con `boto3` y `argparse` para operar la infraestructura de AWS directamente desde la terminal.
* **`--start_nodes <N>`**: Provisiona instancias EC2. Inyecta dinámicamente un *User Data script* (Bash) que actualiza el SO, instala Java, descarga Apache Hadoop, configura los archivos XML (`core-site.xml`, `hdfs-site.xml`) y formatea los directorios del DataNode. También genera e inyecta llaves SSH automáticamente para el *handshake* del clúster.
* **`--check_ssh`**: Realiza un *health check* de la red. Intenta conectarse vía SSH a los nodos recién creados para confirmar que el entorno de software ya terminó de instalarse en segundo plano.
* **`--delete`**: Identifica las instancias mediante etiquetas (`Tag: HadoopWorker`) y las destruye para optimizar el consumo de facturación en AWS.

### 3. `orchestrator.py` (Orquestador Maestro)
Es el componente inteligente del sistema. Se ejecuta únicamente en el Nodo Maestro y coordina todo el trabajo sin intervención manual.
* **Auto-descubrimiento:** Consulta la API de AWS EC2 para listar dinámicamente las IPs privadas de todos los workers activos en ese momento.
* **Balanceo de Carga LPT:** Consume endpoints ligeros de la ONPE para contar la cantidad de distritos por departamento. Utiliza esta métrica para estimar el "peso" computacional y reparte los departamentos equitativamente entre los workers disponibles.
* **Despliegue Dinámico:** Utiliza `subprocess` para ejecutar túneles seguros. Primero envía el código actualizado a cada worker usando `scp`, y luego lanza el proceso de descarga en segundo plano usando `ssh` + `nohup`.

### 4. `worker_descarga.py` (Motor de Crawling Distribuido)
El script de extracción de datos que reside y se ejecuta en cada Nodo Worker.
* **Extracción Jerárquica:** Recibe una lista delimitada por comas de los ubigeos asignados (`--ubigeos`) y recorre el árbol de datos de la ONPE: Provincias -> Distritos -> Locales -> Actas (Listado y Detalle).
* **Tolerancia a Fallos:** Maneja excepciones de red, valida la integridad de los JSON devueltos y respeta un `sleep_time` paramétrico para no ser bloqueado por el servidor de origen.
* **Integración HDFS:** Soporta el flag `--storage hdfs`. Consolida miles de actas en archivos `.jsonl` en el disco local y, como último paso de su ciclo de vida, transfiere todo el bloque de datos al NameNode usando `hdfs dfs -put`.

## Guía de Despliegue y Ejecución

**1. Preparar el Entorno**
Asegúrate de que tu Nodo Maestro tenga asignado el rol de IAM (`LabInstanceProfile` o similar con permisos de EC2) y de configurar tus IDs en `src/config.py`.

**2. Aprovisionar el Clúster**
```bash
python3 src/levantar_cluster.py --start_nodes 4
