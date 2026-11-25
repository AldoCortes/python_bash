from __future__ import annotations

import argparse
import os
import re
import shutil
from datetime import datetime
from pathlib import Path

# Extensiones soportadas (en minúsculas)
IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".heic", ".heif",
    ".webp", ".gif", ".bmp", ".tiff", ".tif", ".raw", ".dng"
}
VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".webm", ".3gp", ".m4v"
}
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS

# Nombres de subcarpetas por tipo de medio dentro de cada año
PHOTOS_SUBDIR = "Fotos"
VIDEOS_SUBDIR = "Videos"

# Patrón para carpetas tipo "Takeout", "Takeout 2", "Takeout 3", etc.
TAKEOUT_DIR_PATTERN = re.compile(r"^Takeout(?:\s+\d+)?$", re.IGNORECASE)

# Valores por defecto
DEFAULT_BASE_DIR = "."
DEFAULT_TARGET_DIR = "./Fotos_Organizadas"

# Intento opcional de usar Pillow para leer fecha EXIF real de la foto
try:
    from PIL import Image, ExifTags
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


def get_media_category(ext: str) -> str | None:
    """Devuelve 'Fotos' o 'Videos' según la extensión, o None si no es multimedia soportada."""
    ext_lower = ext.lower()
    if ext_lower in IMAGE_EXTENSIONS:
        return PHOTOS_SUBDIR
    if ext_lower in VIDEO_EXTENSIONS:
        return VIDEOS_SUBDIR
    return None


def is_valid_year_month(year_str: str, month_str: str) -> bool:
    """Valida que el año y el mes estén dentro de rangos razonables."""
    if not (year_str.isdigit() and month_str.isdigit()):
        return False
    year_int = int(year_str)
    month_int = int(month_str)
    return 1970 <= year_int <= datetime.now().year and 1 <= month_int <= 12


def get_exif_year_month(file_path: Path) -> tuple[str, str] | None:
    """Intenta obtener (año, mes '01'..'12') desde los metadatos EXIF de una imagen."""
    if not HAS_PILLOW or file_path.suffix.lower() not in {".jpg", ".jpeg", ".tiff", ".tif", ".heic", ".heif"}:
        return None

    try:
        with Image.open(file_path) as img:
            exif = img.getexif()
            if not exif:
                return None

            target_tags = {"DateTimeOriginal", "DateTimeDigitized", "DateTime"}
            exif_map = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}

            for tag in target_tags:
                val = exif_map.get(tag)
                if isinstance(val, str) and len(val) >= 10:
                    parts = val[:10].split(":")
                    if len(parts) >= 2:
                        year_str, month_str = parts[0], parts[1].zfill(2)
                        if is_valid_year_month(year_str, month_str):
                            return year_str, month_str
    except Exception:
        pass

    return None


def get_filename_year_month(file_path: Path) -> tuple[str | None, str | None]:
    """
    Busca YYYYMMDD o YYYY-MM / YYYY_MM en el nombre del archivo.
    Devuelve (year_str | None, month_str | None).
    """
    stem = file_path.stem

    compact_match = re.search(r"(?:^|[^0-9])(19[89][0-9]|20[0-3][0-9])(0[1-9]|1[0-2])(0[1-9]|[12][0-9]|3[01])(?:[^0-9]|$)", stem)
    if compact_match:
        year_str, month_str = compact_match.group(1), compact_match.group(2)
        if is_valid_year_month(year_str, month_str):
            return year_str, month_str

    sep_match = re.search(r"(?:^|[^0-9])(19[89][0-9]|20[0-3][0-9])[-_](0[1-9]|1[0-2])(?:[^0-9]|$)", stem)
    if sep_match:
        year_str, month_str = sep_match.group(1), sep_match.group(2)
        if is_valid_year_month(year_str, month_str):
            return year_str, month_str

    year_only_match = re.search(r"(?:^|[^0-9])(19[89][0-9]|20[0-3][0-9])(?:[^0-9]|$)", stem)
    if year_only_match:
        return year_only_match.group(1), None

    return None, None


def get_media_date_parts(file_path: Path, category: str) -> tuple[str, str]:
    """
    Devuelve (year, month) para fotos y videos.
    Prioridad: EXIF (solo fotos) -> Nombre del archivo -> Fecha de modificación del sistema.
    """
    system_dt = datetime.fromtimestamp(file_path.stat().st_mtime)
    fallback_year = str(system_dt.year)
    fallback_month = f"{system_dt.month:02d}"

    if category == PHOTOS_SUBDIR:
        exif_ym = get_exif_year_month(file_path)
        if exif_ym:
            return exif_ym

    name_year, name_month = get_filename_year_month(file_path)
    year = name_year or fallback_year
    month = name_month or fallback_month

    return year, month


def build_destination_folder(target_path: Path, year: str, month: str, category: str) -> Path:
    """
    Construye la carpeta destino:
    - Fotos:  <DESTINO>/<AÑO>/Fotos/<AÑO>-<MES>/
    - Videos: <DESTINO>/<AÑO>/Videos/<AÑO>-<MES>/
    """
    return target_path / year / category / f"{year}-{month}"


def unique_destination_path(dest_dir: Path, filename: str) -> Path:
    """Genera una ruta única si ya existe un archivo con el mismo nombre en destino."""
    target = dest_dir / filename
    if not target.exists():
        return target

    stem = target.stem
    suffix = target.suffix
    counter = 1
    while True:
        candidate = dest_dir / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def find_takeout_folders(base_path: Path, target_path: Path) -> list[Path]:
    """Encuentra carpetas 'Takeout', 'Takeout 2', ..., 'Takeout N' ordenadas de forma natural."""
    def sort_key(p: Path) -> tuple[int, str]:
        match = re.search(r"\d+$", p.name)
        num = int(match.group()) if match else 1
        return (num, p.name.lower())

    folders = [
        entry for entry in base_path.iterdir()
        if entry.is_dir()
        and TAKEOUT_DIR_PATTERN.match(entry.name)
        and entry.resolve() != target_path
    ]
    return sorted(folders, key=sort_key)


def process_single_takeout(source_path: Path, target_path: Path, dry_run: bool = True) -> tuple[int, int, int, int]:
    """
    Procesa una carpeta Takeout específica y devuelve:
    (fotos_movidas, videos_movidos, omitidos, total_procesados)
    """
    photos_moved = 0
    videos_moved = 0
    skipped_count = 0

    for root, _, files in os.walk(source_path):
        root_path = Path(root)

        if target_path in root_path.parents or root_path == target_path:
            continue

        for filename in files:
            file_path = root_path / filename
            ext = file_path.suffix.lower()

            if ext == ".json" or ext not in MEDIA_EXTENSIONS:
                skipped_count += 1
                continue

            category = get_media_category(ext)
            if not category:
                skipped_count += 1
                continue

            year, month = get_media_date_parts(file_path, category)
            dest_folder = build_destination_folder(target_path, year, month, category)
            final_dest = unique_destination_path(dest_folder, filename)
            rel_dest = final_dest.relative_to(target_path)

            if dry_run:
                print(f"  [SIMULACIÓN] {source_path.name}/{filename} -> {rel_dest}")
            else:
                dest_folder.mkdir(parents=True, exist_ok=True)
                shutil.move(str(file_path), str(final_dest))
                print(f"  Movido: {source_path.name}/{filename} -> {rel_dest}")

            if category == PHOTOS_SUBDIR:
                photos_moved += 1
            elif category == VIDEOS_SUBDIR:
                videos_moved += 1

    total_moved = photos_moved + videos_moved
    return photos_moved, videos_moved, skipped_count, total_moved


def organize_all_takeouts(base_dir: str, target_dir: str, dry_run: bool = True) -> None:
    base_path = Path(base_dir).resolve()
    target_path = Path(target_dir).resolve()

    if not base_path.exists() or not base_path.is_dir():
        raise FileNotFoundError(f"El directorio base no existe: {base_path}")

    takeout_folders = find_takeout_folders(base_path, target_path)
    if not takeout_folders:
        print(f"No se encontraron carpetas 'Takeout*' en: {base_path}")
        return

    modo_texto = "SIMULACIÓN (dry_run=True)" if dry_run else "EJECUCIÓN REAL (moviendo archivos)"
    print(f"Modo: {modo_texto}")
    print(f"Carpetas detectadas ({len(takeout_folders)}): {[f.name for f in takeout_folders]}\n")

    total_photos = 0
    total_videos = 0
    total_skipped = 0
    total_moved = 0

    for folder in takeout_folders:
        print(f"Procesando {folder.name}...")
        p_moved, v_moved, skipped, moved = process_single_takeout(folder, target_path, dry_run=dry_run)
        total_photos += p_moved
        total_videos += v_moved
        total_skipped += skipped
        total_moved += moved
        print(f"  -> {folder.name}: {moved} movidos ({p_moved} fotos, {v_moved} videos), {skipped} omitidos.\n")

    print("--- Resumen General ---")
    print(f"Total archivos {'a mover' if dry_run else 'movidos'}: {total_moved}")
    print(f"  - Fotos:  {total_photos}")
    print(f"  - Videos: {total_videos}")
    print(f"Total archivos omitidos (JSON y otros): {total_skipped}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Organiza fotos y videos de carpetas Takeout* por año y mes, ignorando .json."
    )
    parser.add_argument(
        "--base-dir",
        default=DEFAULT_BASE_DIR,
        help=f"Directorio donde están las carpetas Takeout* (por defecto: '{DEFAULT_BASE_DIR}').",
    )
    parser.add_argument(
        "--destino",
        default=DEFAULT_TARGET_DIR,
        help=f"Carpeta destino organizada (por defecto: '{DEFAULT_TARGET_DIR}').",
    )

    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Simula el movimiento sin alterar archivos (es el comportamiento por defecto).",
    )
    mode_group.add_argument(
        "--execute",
        "--no-dry-run",
        dest="dry_run",
        action="store_false",
        help="Ejecuta el movimiento real de archivos.",
    )
    parser.set_defaults(dry_run=True)
    return parser.parse_args()


# INSTRUCTIONS
# Simulación de ejecución
# Corre:
#       python3 ORGANIZE_TAKEOUT.py
# El programa analizará las carpetas, validará y mostrará el contenido que va a mover
# 
# Para mover los archivos
# Corre:
#       python3 ORGANIZE_TAKEOUT.py --execute
# Esto creará las carpetas separadas y moverá los archivos a la carpeta "Fotos_Organizadas"
# 
# Para especificar el directorio
# Corre:
#       python3 ORGANIZE_TAKEOUT.py --execute --destino="NOMBRE_DE_CARPETA_DESTINO"
# Con lo anterior le darás un nombre específico a la carpeta destino para mover los archivos

if __name__ == "__main__":
    args = parse_args()
    organize_all_takeouts(args.base_dir, args.destino, dry_run=args.dry_run)