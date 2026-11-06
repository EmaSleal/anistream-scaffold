#!/usr/bin/env bash
#
# backup_system.sh
# Backup del filesystem raíz (sda, vía LVM) hacia sdb (DATA_SAFE).
#
# Medida de CONTENCIÓN inmediata, no reemplaza un backup off-site.
# sdb1 ya está montado en /mnt/data_safe según tu lsblk (label DATA_SAFE).
#
# Usa rsync por resiliencia ante sectores marginales — a diferencia de dd,
# si encuentra un archivo ilegible lo reporta y sigue, no aborta todo el proceso.

set -euo pipefail

BACKUP_ROOT="/mnt/data_safe/system_backup"
LOG_FILE="/var/log/system_backup_$(date +%Y%m%d_%H%M%S).log"

echo "==> Verificando que sdb1 esté montado"
if ! mountpoint -q /mnt/data_safe 2>/dev/null; then
    echo "ERROR: /mnt/data_safe no está montado."
    echo "Montalo primero: sudo mount /dev/sdb1 /mnt/data_safe"
    echo "(creá el punto de montaje si no existe: sudo mkdir -p /mnt/data_safe)"
    exit 1
fi

echo "==> Verificando espacio disponible en destino"
AVAIL_GB=$(df --output=avail -BG /mnt/data_safe | tail -1 | tr -dc '0-9')
echo "Espacio disponible en sdb1: ${AVAIL_GB}G"

if [ "$AVAIL_GB" -lt 50 ]; then
    echo "ADVERTENCIA: menos de 50GB libres. Tu uso actual de / es ~41.3G."
    echo "Verificá que alcance antes de continuar."
    read -p "¿Continuar de todas formas? (s/N) " confirm
    [[ "$confirm" =~ ^[sS]$ ]] || exit 1
fi

sudo mkdir -p "$BACKUP_ROOT"

echo "==> Iniciando rsync de / hacia $BACKUP_ROOT"
echo "Esto puede tardar según el volumen de datos. Log en: $LOG_FILE"

sudo rsync -aAXv \
    --exclude={"/dev/*","/proc/*","/sys/*","/tmp/*","/run/*","/mnt/*","/media/*","/lost+found","/var/log/*","/var/cache/apt/archives/*"} \
    --info=progress2 \
    / "$BACKUP_ROOT/" 2>&1 | tee "$LOG_FILE"

echo ""
echo "==> Backup completado."
echo "Revisá el log para archivos que rsync no pudo copiar (señal de sectores problemáticos):"
echo "grep -i 'error\\|failed\\|cannot' $LOG_FILE"
echo ""
echo "Tamaño final del backup:"
sudo du -sh "$BACKUP_ROOT"
