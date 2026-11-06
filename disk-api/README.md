# Disk API — astro1

API minimalista en FastAPI + SQLite para gestionar archivos sobre el
disco de datos disponible (`sdb1`), con estructura preparada para migrar
a un pool MergerFS si se agrega un segundo disco a futuro. Diseñada
específicamente para correr en hardware limitado (Athlon II Neo N36L,
sin AVX, ~3.8GB RAM).

## Por qué este stack y no otro

- **Un solo directorio de datos sobre `sdb1`** en vez de MergerFS: con un
  único disco de datos disponible, un pool no aporta nada — es complejidad
  sin beneficio. La estructura está preparada para migrar a MergerFS el
  día que haya un segundo disco real, sin reescribir la API.
- **FastAPI + Uvicorn** en vez de Django o una JVM: arranca con decenas
  de MB en reposo, no cientos.
- **SQLite** en vez de Postgres/MySQL: cero proceso de servidor de BD
  corriendo en background consumiendo RAM 24/7.

## Setup

### 0. Estado real del hardware (astro1)

- `sda` (ST500LM021, 500GB) → disco de **sistema**, montado en `/` vía LVM.
  No tocar. SMART auditado: sin sectores reasignados, pero con desgaste
  mecánico documentado (Load_Cycle_Count alto, Reallocated_Event_Count en
  el piso de su rango). Hay backup completo verificado en
  `/mnt/data_safe/system_backup_<fecha>.tar.zst` — repetirlo periódicamente.
- `sdb` (VB0250EAVER, 250GB) → único disco de **datos** disponible,
  partición `sdb1` montada en `/mnt/data_safe`. Es donde vive el storage
  de esta API.

No hay segundo disco de datos todavía, así que **no se usa MergerFS** en
esta iteración — sería over-engineering para un solo disco. Si en el
futuro se agrega un segundo disco, `setup_storage.sh` documenta cómo
migrar a un pool MergerFS sin tener que tocar el resto de la API.

### 1. Preparar el directorio de storage

```bash
sudo mount /dev/sdb1 /mnt/data_safe   # si no está montado
./setup_storage.sh
```

Esto crea `/mnt/data_safe/storage`, que es donde la API escribe los
archivos.

### 2. Instalar la API

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Levantar el servidor

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

`--workers 1` es intencional: con 2 núcleos y RAM limitada, más workers
significa más copias del proceso en memoria sin beneficio real de
paralelismo a este volumen de tráfico.

Para que sobreviva reinicios, conviene un servicio systemd (no incluido
en este esqueleto — avisame si lo querés y te lo armo).

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Healthcheck |
| POST | `/api/upload` | Sube un archivo (multipart/form-data, campo `file`) |
| GET | `/api/files` | Lista archivos. Query params: `category`, `limit`, `offset` |
| GET | `/api/files/{id}` | Metadata de un archivo |
| GET | `/api/files/{id}/download` | Descarga el archivo físico |
| DELETE | `/api/files/{id}` | Borra archivo físico + registro |

Documentación interactiva autogenerada en `/docs` (Swagger UI).

## Ejemplo de uso desde un script cliente

```bash
curl -X POST http://astro1:8000/api/upload -F "file=@foto.jpg"
curl http://astro1:8000/api/files?category=photos
curl -O http://astro1:8000/api/files/5/download
```

## Pendiente para siguiente iteración

- Autenticación (API Key) cuando se exponga fuera de la red local.
- Servicio systemd para arranque automático y reinicio ante fallos.
- Generación de thumbnails para fotos/videos (cuidado: cualquier
  procesamiento de imagen/video consume CPU real en este hardware,
  evaluar antes de implementar).
