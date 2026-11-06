#!/usr/bin/env bash
#
# setup_storage.sh
# Prepara /mnt/data_safe/storage como raíz de almacenamiento de la API.
#
# Contexto: sdb1 (VB0250EAVER, 250GB) ya está montado en /mnt/data_safe.
# sda es el disco de sistema (ST500LM021) y NO se toca.
#
# Si en el futuro se agrega un segundo disco de datos, este es el punto
# donde se reemplazaría el directorio simple por un pool MergerFS:
#
#   sudo mergerfs -o defaults,allow_other,use_ino,category.create=mfs \
#       /mnt/data_safe/storage:/mnt/disk2_nuevo/storage \
#       /mnt/storage_pool
#
# y se actualizaría STORAGE_ROOT en app/routers/files.py acorde.

set -euo pipefail

STORAGE_DIR="/mnt/data_safe/storage"

echo "==> Verificando que /mnt/data_safe esté montado"
if ! mountpoint -q /mnt/data_safe; then
    echo "ERROR: /mnt/data_safe no está montado."
    echo "Montalo primero: sudo mount /dev/sdb1 /mnt/data_safe"
    exit 1
fi

echo "==> Creando $STORAGE_DIR"
sudo mkdir -p "$STORAGE_DIR"
sudo chown "$(whoami):$(whoami)" "$STORAGE_DIR"

echo "==> Listo."
df -h /mnt/data_safe
echo ""
echo "Espacio disponible para la API:"
df -h --output=avail /mnt/data_safe | tail -1
