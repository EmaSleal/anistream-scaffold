#!/usr/bin/env bash
#
# compress_backup.sh
# Comprime el backup de sistema en /mnt/data_safe/system_backup a un
# único archivo tar.zst, luego borra el directorio sin comprimir.
#
# Usa zstd en vez de gzip: en este hardware (sin AVX) zstd a nivel
# moderado sigue siendo notablemente más rápido que gzip a compresión
# equivalente, y igual de liviano en RAM.

set -euo pipefail

SOURCE_DIR="/mnt/data_safe/system_backup"
ARCHIVE="/mnt/data_safe/system_backup_$(date +%Y%m%d).tar.zst"

echo "==> Verificando que zstd esté disponible"
if ! command -v zstd &> /dev/null; then
    echo "zstd no está instalado. Instalando..."
    sudo apt update
    sudo apt install -y zstd
fi

echo "==> Tamaño actual sin comprimir:"
sudo du -sh "$SOURCE_DIR"

echo "==> Comprimiendo (nivel 9, balance razonable velocidad/ratio en este hardware)"
echo "Esto puede tardar varios minutos para 54G."
sudo tar -cf - -C "$(dirname "$SOURCE_DIR")" "$(basename "$SOURCE_DIR")" \
    | zstd -9 -T2 -o "$ARCHIVE"

echo ""
echo "==> Verificando que el archivo comprimido sea íntegro antes de borrar el original"
if zstd -t "$ARCHIVE"; then
    echo "Archivo comprimido verificado OK."
else
    echo "ERROR: el archivo comprimido falló la verificación. NO se borra el original."
    exit 1
fi

echo ""
echo "==> Tamaño del archivo comprimido:"
du -sh "$ARCHIVE"

echo ""
read -p "¿Borrar el directorio sin comprimir ($SOURCE_DIR)? (s/N) " confirm
if [[ "$confirm" =~ ^[sS]$ ]]; then
    sudo rm -rf "$SOURCE_DIR"
    echo "Directorio original borrado. Espacio liberado."
else
    echo "Directorio original conservado. Liberá espacio manualmente cuando quieras."
fi

echo ""
echo "==> Espacio resultante en sdb1:"
df -h /mnt/data_safe
