import os
import datetime
import pandas as pd
import logging
import zipfile
from pathlib import Path
from database import get_all_orders, get_all_withdraws, get_all_referrals, save_export, get_user, get_all_users_detailed, get_users_by_date_range

logger = logging.getLogger(__name__)
EXPORT_DIR = Path("exports")
MAX_FILE_AGE_DAYS = 7  # Eski fayllarni o‘chirish uchun limit

def _sanitize_filename(filename: str) -> str:
    """
    Sanitizes a filename to prevent path injection.
    """
    return "".join(c for c in filename if c.isalnum() or c in ('.', '_', '-')).strip()

def _clean_old_files() -> None:
    """
    Deletes export files older than MAX_FILE_AGE_DAYS.
    """
    try:
        cutoff = datetime.datetime.now() - datetime.timedelta(days=MAX_FILE_AGE_DAYS)
        for file in EXPORT_DIR.glob("*.*"):
            if file.is_file() and file.stat().st_mtime < cutoff.timestamp():
                file.unlink()
                logger.info(f"Deleted old export file: {file}")
    except Exception as e:
        logger.error(f"Failed to clean old files: {e}")

def _format_excel(df: pd.DataFrame, writer: pd.ExcelWriter) -> None:
    """
    Formats the Excel file (column widths, header styles).
    Args:
        df: DataFrame to format.
        writer: Excel writer object.
    """
    worksheet = writer.sheets['Sheet1']
    for idx, col in enumerate(df.columns):
        max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
        worksheet.set_column(idx, idx, max_len)
    header_format = writer.book.add_format({'bold': True, 'bg_color': '#D3D3D3'})
    for col_num, value in enumerate(df.columns.values):
        worksheet.write(0, col_num, value, header_format)

def export_orders_excel(
    admin_id: int,
    start_date: datetime.date = None,
    end_date: datetime.date = None,
    user_id: int = None,
    file_format: str = "xlsx"
) -> str:
    """
    Exports orders to Excel, CSV, or JSON with optional filters.
    Args:
        admin_id: ID of the admin requesting the export.
        start_date: Optional start date for filtering.
        end_date: Optional end date for filtering.
        user_id: Optional user ID for filtering.
        file_format: Output format ('xlsx', 'csv', 'json').
    Returns:
        Path to the exported file.
    """
    try:
        EXPORT_DIR.mkdir(exist_ok=True)
        _clean_old_files()

        orders = get_all_orders(start_date, end_date, user_id)
        if not orders:
            logger.warning("No orders found for export.")
            raise ValueError("Eksport qilish uchun zakazlar topilmadi.")

        df = pd.DataFrame([
            {
                "ID": o["id"],
                "Foydalanuvchi ID": o["user_id"],
                "Username": o.get("username", "Noma'lum"),
                "Telefon": get_user(o["user_id"]).get("phone", "Yo‘q"),
                "Rasm ID": o.get("photo_id", "Yo‘q"),
                "Status": o["status"],
                "Sana": o["created_at"].strftime("%Y-%m-%d %H:%M:%S")
            } for o in orders
        ])

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = _sanitize_filename(f"orders_{timestamp}_{admin_id}")
        file_path = EXPORT_DIR / f"{file_name}.{file_format}"

        if file_format == "xlsx":
            with pd.ExcelWriter(file_path, engine="xlsxwriter") as writer:
                df.to_excel(writer, index=False, sheet_name="Sheet1")
                _format_excel(df, writer)
        elif file_format == "csv":
            df.to_csv(file_path, index=False, encoding="utf-8")
        elif file_format == "json":
            df.to_json(file_path, orient="records", force_ascii=False)
        else:
            raise ValueError(f"Unsupported file format: {file_format}")

        save_export(admin_id, "orders", str(file_path), file_format)
        logger.info(f"Exported orders to {file_path}")
        return str(file_path)

    except Exception as e:
        logger.error(f"Failed to export orders: {e}")
        raise

def export_withdraws_excel(
    admin_id: int,
    start_date: datetime.date = None,
    end_date: datetime.date = None,
    file_format: str = "xlsx"
) -> str:
    """
    Exports withdraw requests to Excel, CSV, or JSON with optional date filters.
    Args:
        admin_id: ID of the admin requesting the export.
        start_date: Optional start date for filtering.
        end_date: Optional end date for filtering.
        file_format: Output format ('xlsx', 'csv', 'json').
    Returns:
        Path to the exported file.
    """
    try:
        EXPORT_DIR.mkdir(exist_ok=True)
        _clean_old_files()

        withdraws = get_all_withdraws(start_date, end_date)
        if not withdraws:
            logger.warning("No withdraw requests found for export.")
            raise ValueError("Eksport qilish uchun yechib olish so‘rovlari topilmadi.")

        df = pd.DataFrame([
            {
                "ID": w["id"],
                "Foydalanuvchi ID": w["user_id"],
                "Username": get_user(w["user_id"]).get("username", "Noma'lum"),
                "Telefon": get_user(w["user_id"]).get("phone", "Yo‘q"),
                "Miqdor": f"{w['amount']:.2f} USDT",
                "Usul": w.get("withdraw_type", "trc20").capitalize(),
                "Hamyon/Karta/Telefon": w["wallet"],
                "Status": w["status"],
                "Sana": w["created_at"].strftime("%Y-%m-%d %H:%M:%S")
            } for w in withdraws
        ])

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = _sanitize_filename(f"withdraws_{timestamp}_{admin_id}")
        file_path = EXPORT_DIR / f"{file_name}.{file_format}"

        if file_format == "xlsx":
            with pd.ExcelWriter(file_path, engine="xlsxwriter") as writer:
                df.to_excel(writer, index=False, sheet_name="Sheet1")
                _format_excel(df, writer)
        elif file_format == "csv":
            df.to_csv(file_path, index=False, encoding="utf-8")
        elif file_format == "json":
            df.to_json(file_path, orient="records", force_ascii=False)
        else:
            raise ValueError(f"Unsupported file format: {file_format}")

        save_export(admin_id, "withdraws", str(file_path), file_format)
        logger.info(f"Exported withdraws to {file_path}")
        return str(file_path)

    except Exception as e:
        logger.error(f"Failed to export withdraws: {e}")
        raise

def export_referrals_excel(
    admin_id: int,
    start_date: datetime.date = None,
    end_date: datetime.date = None,
    file_format: str = "xlsx"
) -> str:
    """
    Exports referrals to Excel, CSV, or JSON with optional date filters.
    Args:
        admin_id: ID of the admin requesting the export.
        start_date: Optional start date for filtering.
        end_date: Optional end date for filtering.
        file_format: Output format ('xlsx', 'csv', 'json').
    Returns:
        Path to the exported file.
    """
    try:
        EXPORT_DIR.mkdir(exist_ok=True)
        _clean_old_files()

        referrals = get_all_referrals(start_date, end_date)
        if not referrals:
            logger.warning("No referrals found for export.")
            raise ValueError("Eksport qilish uchun referallar topilmadi.")

        df = pd.DataFrame([
            {
                "Referrer ID": r["referrer_id"],
                "Referrer Username": get_user(r["referrer_id"]).get("username", "Noma'lum"),
                "Referrer Telefon": get_user(r["referrer_id"]).get("phone", "Yo‘q"),
                "Referred ID": r["referred_id"],
                "Referred Username": get_user(r["referred_id"]).get("username", "Noma'lum"),
                "Bonus": f"{r['bonus']:.2f} USDT",
                "Daraja": r.get("level", 1),
                "Sana": r["created_at"].strftime("%Y-%m-%d %H:%M:%S")
            } for r in referrals
        ])

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = _sanitize_filename(f"referrals_{timestamp}_{admin_id}")
        file_path = EXPORT_DIR / f"{file_name}.{file_format}"

        if file_format == "xlsx":
            with pd.ExcelWriter(file_path, engine="xlsxwriter") as writer:
                df.to_excel(writer, index=False, sheet_name="Sheet1")
                _format_excel(df, writer)
        elif file_format == "csv":
            df.to_csv(file_path, index=False, encoding="utf-8")
        elif file_format == "json":
            df.to_json(file_path, orient="records", force_ascii=False)
        else:
            raise ValueError(f"Unsupported file format: {file_format}")

        save_export(admin_id, "referrals", str(file_path), file_format)
        logger.info(f"Exported referrals to {file_path}")
        return str(file_path)

    except Exception as e:
        logger.error(f"Failed to export referrals: {e}")
        raise

def export_to_zip(admin_id: int, file_paths: list[str], password: str = None) -> str:
    """
    Creates a password-protected ZIP archive of exported files.
    Args:
        admin_id: ID of the admin requesting the export.
        file_paths: List of file paths to include in the ZIP.
        password: Optional password for the ZIP archive.
    Returns:
        Path to the ZIP file.
    """
    try:
        EXPORT_DIR.mkdir(exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_name = _sanitize_filename(f"export_{timestamp}_{admin_id}.zip")
        zip_path = EXPORT_DIR / zip_name

        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            if password:
                zf.setpassword(password.encode("utf-8"))
            for file_path in file_paths:
                zf.write(file_path, os.path.basename(file_path))

        logger.info(f"Created ZIP archive: {zip_path}")
        return str(zip_path)

    except Exception as e:
        logger.error(f"Failed to create ZIP archive: {e}")
        raise

def export_users_excel(
    admin_id: int,
    start_date: datetime.date = None,
    end_date: datetime.date = None,
    file_format: str = "xlsx"
) -> str:
    """
    Exports users to Excel, CSV, or JSON with optional date filters.
    Args:
        admin_id: ID of the admin requesting the export.
        start_date: Optional start date for filtering.
        end_date: Optional end date for filtering.
        file_format: Output format ('xlsx', 'csv', 'json').
    Returns:
        Path to the exported file.
    """
    try:
        EXPORT_DIR.mkdir(exist_ok=True)
        _clean_old_files()

        if start_date or end_date:
            users = get_users_by_date_range(start_date, end_date)
        else:
            users = get_all_users_detailed()
            
        if not users:
            logger.warning("No users found for export.")
            raise ValueError("Eksport qilish uchun foydalanuvchilar topilmadi.")

        df = pd.DataFrame([
            {
                "ID": u["user_id"],
                "Username": u.get("username", "Yo'q"),
                "Telefon": u.get("phone", "Yo'q"),
                "Balans": f"{u['balance']:.2f} so'm",
                "Status": "Bloklangan" if u['is_blocked'] else "Faol",
                "Referrer ID": u.get("referred_by", "Yo'q"),
                "Ro'yxatdan o'tgan sana": u["created_at"].strftime("%Y-%m-%d %H:%M:%S")
            } for u in users
        ])

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = _sanitize_filename(f"users_{timestamp}_{admin_id}")
        file_path = EXPORT_DIR / f"{file_name}.{file_format}"

        if file_format == "xlsx":
            with pd.ExcelWriter(file_path, engine="xlsxwriter") as writer:
                df.to_excel(writer, index=False, sheet_name="Sheet1")
                _format_excel(df, writer)
        elif file_format == "csv":
            df.to_csv(file_path, index=False, encoding="utf-8")
        elif file_format == "json":
            df.to_json(file_path, orient="records", force_ascii=False)
        else:
            raise ValueError(f"Unsupported file format: {file_format}")

        save_export(admin_id, "users", str(file_path), file_format)
        logger.info(f"Exported users to {file_path}")
        return str(file_path)

    except Exception as e:
        logger.error(f"Failed to export users: {e}")
        raise