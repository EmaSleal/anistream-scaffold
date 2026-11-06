#!/usr/bin/env bash
#
# verify_backup.sh
# Verifica integridad del backup comparando contra el origen.
# Usa rsync en modo --dry-run + checksum: no copia nada, solo reporta
# diferencias. Si hay archivos que rsync no pudo leer del origen (sda)
# durante el backup original, esto los va a exponer como discrepancias.

set -uo pipefail  # sin -e: queremos ver el resultado aunque algo falle

BACKUP_ROOT="/mnt/data_safe/system_backup"
LOG_FILE="/var/log/verify_backup_$(date +%Y%m%d_%H%M%S).log"

echo "==> Verificando backup en $BACKUP_ROOT contra origen /"
echo "Esto compara checksums reales (más lento que comparar tamaños, pero confiable)."
echo "Log: $LOG_FILE"
echo ""

sudo rsync -aAXc \
    --dry-run \
    --itemize-changes \
    --exclude={"/dev/*","/proc/*","/sys/*","/tmp/*","/run/*","/mnt/*","/media/*","/lost+found","/var/log/*","/var/cache/apt/archives/*"} \
    / "$BACKUP_ROOT/" 2>&1 | sudo tee "$LOG_FILE"

echo ""
echo "==> Resultado:"
DIFF_COUNT=$(grep -c '^[<>]' "$LOG_FILE" 2>/dev/null || echo 0)
ERROR_COUNT=$(grep -ci 'error\|failed\|cannot\|permission denied' "$LOG_FILE" 2>/dev/null || echo 0)

echo "Diferencias de contenido encontradas: $DIFF_COUNT"
echo "Líneas de error/falla: $ERROR_COUNT"

if [ "$ERROR_COUNT" -gt 0 ]; then
    echo ""
    echo "ADVERTENCIA: hay errores. Revisalos con:"
    echo "grep -i 'error\\|failed\\|cannot\\|permission denied' $LOG_FILE"
fi

if [ "$DIFF_COUNT" -eq 0 ] && [ "$ERROR_COUNT" -eq 0 ]; then
    echo ""
    echo "Backup verificado: contenido idéntico al origen, sin errores de lectura."
fi
