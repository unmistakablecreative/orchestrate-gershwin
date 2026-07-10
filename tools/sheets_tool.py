#!/usr/bin/env python3
"""
OrchestrateOS Sheets Tool
SQLite-backed spreadsheet engine with typed columns.
"""

import sqlite3
import json
import csv
import os
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "data", "sheets.db")
CONFIG_PATH = os.path.join(BASE_DIR, "data", "sheets_config.json")
EXPORT_DIR = os.path.join(BASE_DIR, "data", "exports")

VALID_TYPES = ["text", "number", "date", "boolean", "select", "url", "email", "long_text", "multi_select"]


def init_db():
    """Create _tables_meta table if it does not exist."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS _tables_meta (
            table_name TEXT PRIMARY KEY,
            display_name TEXT,
            columns_json TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def get_db():
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    return {"tables": {}}


def save_config(config):
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=2)


def sanitize_table_name(name):
    """Convert display name to safe SQLite table name."""
    return "sheet_" + "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_")


def sanitize_column_name(name):
    """Convert column name to safe SQLite column name."""
    return "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_")


def type_to_sqlite(col_type):
    """Map column type to SQLite type."""
    mapping = {
        "text": "TEXT",
        "number": "REAL",
        "date": "TEXT",
        "boolean": "INTEGER",
        "select": "TEXT",
        "url": "TEXT",
        "email": "TEXT",
        "long_text": "TEXT",
        "multi_select": "TEXT"
    }
    return mapping.get(col_type, "TEXT")


def create_table(params):
    """Create new table with specified columns."""
    name = params.get("name")
    columns = params.get("columns", [])

    if not name:
        return {"status": "error", "message": "Table name required"}
    if not columns:
        return {"status": "error", "message": "At least one column required"}

    # Validate columns
    for col in columns:
        if not col.get("name"):
            return {"status": "error", "message": "Column name required"}
        if col.get("type") not in VALID_TYPES:
            return {"status": "error", "message": f"Invalid column type: {col.get('type')}. Valid: {VALID_TYPES}"}
        if col.get("type") == "select" and not col.get("options"):
            return {"status": "error", "message": f"Select column '{col['name']}' requires options array"}
        if col.get("type") == "multi_select" and not col.get("options"):
            return {"status": "error", "message": f"Multi-select column '{col['name']}' requires options array"}

    table_name = sanitize_table_name(name)
    config = load_config()

    if table_name in config["tables"]:
        return {"status": "error", "message": f"Table '{name}' already exists"}

    # Build column definitions
    col_defs = ["_id INTEGER PRIMARY KEY AUTOINCREMENT", "_created_at TEXT", "_updated_at TEXT"]
    column_meta = []

    for col in columns:
        safe_name = sanitize_column_name(col["name"])
        sqlite_type = type_to_sqlite(col["type"])
        col_defs.append(f"{safe_name} {sqlite_type}")
        column_meta.append({
            "name": safe_name,
            "display_name": col["name"],
            "type": col["type"],
            "options": col.get("options", [])
        })

    # Create table in SQLite
    conn = get_db()
    try:
        sql = f"CREATE TABLE {table_name} ({', '.join(col_defs)})"
        conn.execute(sql)

        # Register in _tables_meta
        now = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO _tables_meta (table_name, display_name, columns_json, created_at) VALUES (?, ?, ?, ?)",
            (table_name, name, json.dumps(column_meta), now)
        )
        conn.commit()

        # Update config
        config["tables"][table_name] = {
            "display_name": name,
            "columns": column_meta,
            "created_at": now
        }
        save_config(config)

        return {"status": "success", "table_name": table_name, "display_name": name, "columns": column_meta}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


def add_row(params):
    """Insert new row into table."""
    table = params.get("table")
    data = params.get("data", {})

    if not table:
        return {"status": "error", "message": "Table name required"}
    if not data:
        return {"status": "error", "message": "Data required"}

    config = load_config()
    table_name = table if table.startswith("sheet_") else sanitize_table_name(table)

    if table_name not in config["tables"]:
        return {"status": "error", "message": f"Table '{table}' not found"}

    # Get column metadata for validation
    columns_meta = {c["name"]: c for c in config["tables"][table_name]["columns"]}

    # Sanitize and validate data
    insert_data = {}
    for key, value in data.items():
        safe_key = sanitize_column_name(key)
        if safe_key not in columns_meta:
            continue  # Skip unknown columns
        insert_data[safe_key] = value

    if not insert_data:
        return {"status": "error", "message": "No valid columns in data"}

    now = datetime.now().isoformat()
    insert_data["_created_at"] = now
    insert_data["_updated_at"] = now

    cols = ", ".join(insert_data.keys())
    placeholders = ", ".join(["?" for _ in insert_data])
    values = list(insert_data.values())

    conn = get_db()
    try:
        cursor = conn.execute(f"INSERT INTO {table_name} ({cols}) VALUES ({placeholders})", values)
        conn.commit()
        row_id = cursor.lastrowid
        return {"status": "success", "row_id": row_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


def update_row(params):
    """Update existing row by ID."""
    table = params.get("table")
    row_id = params.get("id")
    data = params.get("data", {})

    if not table:
        return {"status": "error", "message": "Table name required"}
    if row_id is None:
        return {"status": "error", "message": "Row ID required"}
    if not data:
        return {"status": "error", "message": "Data required"}

    config = load_config()
    table_name = table if table.startswith("sheet_") else sanitize_table_name(table)

    if table_name not in config["tables"]:
        return {"status": "error", "message": f"Table '{table}' not found"}

    # Get column metadata
    columns_meta = {c["name"]: c for c in config["tables"][table_name]["columns"]}

    # Sanitize and validate data
    update_data = {}
    for key, value in data.items():
        safe_key = sanitize_column_name(key)
        if safe_key not in columns_meta:
            continue
        update_data[safe_key] = value

    if not update_data:
        return {"status": "error", "message": "No valid columns in data"}

    update_data["_updated_at"] = datetime.now().isoformat()

    set_clause = ", ".join([f"{k} = ?" for k in update_data.keys()])
    values = list(update_data.values()) + [row_id]

    conn = get_db()
    try:
        cursor = conn.execute(f"UPDATE {table_name} SET {set_clause} WHERE _id = ?", values)
        conn.commit()
        if cursor.rowcount == 0:
            return {"status": "error", "message": f"Row {row_id} not found"}
        return {"status": "success", "rows_affected": cursor.rowcount}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


def delete_row(params):
    """Remove row from table by ID."""
    table = params.get("table")
    row_id = params.get("id")

    if not table:
        return {"status": "error", "message": "Table name required"}
    if row_id is None:
        return {"status": "error", "message": "Row ID required"}

    config = load_config()
    table_name = table if table.startswith("sheet_") else sanitize_table_name(table)

    if table_name not in config["tables"]:
        return {"status": "error", "message": f"Table '{table}' not found"}

    conn = get_db()
    try:
        cursor = conn.execute(f"DELETE FROM {table_name} WHERE _id = ?", (row_id,))
        conn.commit()
        if cursor.rowcount == 0:
            return {"status": "error", "message": f"Row {row_id} not found"}
        return {"status": "success", "rows_deleted": cursor.rowcount}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


def query(params):
    """Query table with optional filters, sort, and limit."""
    table = params.get("table")
    filters = params.get("filters", [])
    sort = params.get("sort")
    limit = params.get("limit")

    if not table:
        return {"status": "error", "message": "Table name required"}

    config = load_config()
    table_name = table if table.startswith("sheet_") else sanitize_table_name(table)

    if table_name not in config["tables"]:
        return {"status": "error", "message": f"Table '{table}' not found"}

    sql = f"SELECT * FROM {table_name}"
    params_list = []

    # Build WHERE clause
    if filters:
        where_clauses = []
        for f in filters:
            col = sanitize_column_name(f.get("column", ""))
            op = f.get("operator", "=")
            val = f.get("value")

            # Validate operator
            valid_ops = ["=", "!=", ">", "<", ">=", "<=", "LIKE", "like"]
            if op not in valid_ops:
                op = "="

            where_clauses.append(f"{col} {op} ?")
            params_list.append(val)

        if where_clauses:
            sql += " WHERE " + " AND ".join(where_clauses)

    # Add ORDER BY
    if sort:
        sort_col = sanitize_column_name(sort.get("column", "_id"))
        sort_dir = "DESC" if sort.get("direction", "asc").lower() == "desc" else "ASC"
        sql += f" ORDER BY {sort_col} {sort_dir}"

    # Add LIMIT
    if limit:
        sql += f" LIMIT {int(limit)}"

    conn = get_db()
    try:
        cursor = conn.execute(sql, params_list)
        rows = [dict(row) for row in cursor.fetchall()]
        return {
            "status": "success",
            "table": table_name,
            "rows": rows,
            "count": len(rows),
            "columns": config["tables"][table_name]["columns"]
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


def list_tables(params=None):
    """Return all tables with column definitions and row counts."""
    config = load_config()
    conn = get_db()

    tables = []
    try:
        for table_name, table_info in config["tables"].items():
            cursor = conn.execute(f"SELECT COUNT(*) as count FROM {table_name}")
            row_count = cursor.fetchone()["count"]
            tables.append({
                "table_name": table_name,
                "display_name": table_info["display_name"],
                "columns": table_info["columns"],
                "row_count": row_count,
                "created_at": table_info.get("created_at")
            })
        return {"status": "success", "tables": tables}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


def delete_table(params):
    """Drop table from SQLite and remove from config."""
    table = params.get("table")

    if not table:
        return {"status": "error", "message": "Table name required"}

    config = load_config()
    table_name = table if table.startswith("sheet_") else sanitize_table_name(table)

    if table_name not in config["tables"]:
        return {"status": "error", "message": f"Table '{table}' not found"}

    conn = get_db()
    try:
        conn.execute(f"DROP TABLE IF EXISTS {table_name}")
        conn.execute("DELETE FROM _tables_meta WHERE table_name = ?", (table_name,))
        conn.commit()

        del config["tables"][table_name]
        save_config(config)

        return {"status": "success", "message": f"Table '{table}' deleted"}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


def export_csv(params):
    """Export table to CSV file, returns file path."""
    table = params.get("table")

    if not table:
        return {"status": "error", "message": "Table name required"}

    config = load_config()
    table_name = table if table.startswith("sheet_") else sanitize_table_name(table)

    if table_name not in config["tables"]:
        return {"status": "error", "message": f"Table '{table}' not found"}

    # Ensure export directory exists
    os.makedirs(EXPORT_DIR, exist_ok=True)

    conn = get_db()
    try:
        cursor = conn.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()

        if not rows:
            return {"status": "error", "message": "Table is empty"}

        # Get column names
        col_names = [description[0] for description in cursor.description]

        # Generate filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        display_name = config["tables"][table_name]["display_name"]
        safe_display = "".join(c if c.isalnum() else "_" for c in display_name)
        filename = f"{safe_display}_{timestamp}.csv"
        filepath = os.path.join(EXPORT_DIR, filename)

        # Write CSV
        with open(filepath, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(col_names)
            for row in rows:
                writer.writerow(row)

        return {"status": "success", "file_path": filepath, "rows_exported": len(rows)}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


def add_column(params):
    """Add a new column to an existing table."""
    table = params.get("table")
    name = params.get("name")
    col_type = params.get("type")
    options = params.get("options", [])

    if not table:
        return {"status": "error", "message": "Table name required"}
    if not name:
        return {"status": "error", "message": "Column name required"}
    if col_type not in VALID_TYPES:
        return {"status": "error", "message": f"Invalid column type: {col_type}. Valid: {VALID_TYPES}"}
    if col_type == "select" and not options:
        return {"status": "error", "message": f"Select column '{name}' requires options array"}
    if col_type == "multi_select" and not options:
        return {"status": "error", "message": f"Multi-select column '{name}' requires options array"}

    config = load_config()
    table_name = table if table.startswith("sheet_") else sanitize_table_name(table)

    if table_name not in config["tables"]:
        return {"status": "error", "message": f"Table '{table}' not found"}

    safe_name = sanitize_column_name(name)

    # Check if column already exists
    existing_cols = [c["name"] for c in config["tables"][table_name]["columns"]]
    if safe_name in existing_cols:
        return {"status": "error", "message": f"Column '{name}' already exists"}

    conn = get_db()
    try:
        # Add column to SQLite table
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {safe_name} TEXT")
        conn.commit()

        # Build column metadata
        column_meta = {
            "name": safe_name,
            "display_name": name,
            "type": col_type,
            "options": options
        }

        # Update _tables_meta
        cursor = conn.execute("SELECT columns_json FROM _tables_meta WHERE table_name = ?", (table_name,))
        row = cursor.fetchone()
        if row:
            columns_list = json.loads(row["columns_json"])
            columns_list.append(column_meta)
            conn.execute(
                "UPDATE _tables_meta SET columns_json = ? WHERE table_name = ?",
                (json.dumps(columns_list), table_name)
            )
            conn.commit()

        # Update config
        config["tables"][table_name]["columns"].append(column_meta)
        save_config(config)

        return {"status": "success", "table_name": table_name, "column": column_meta}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


def update_column_name(params):
    """Update display name of a column (does not rename SQLite column)."""
    table = params.get("table")
    column = params.get("column")
    display_name = params.get("display_name")

    if not table:
        return {"status": "error", "message": "Table name required"}
    if not column:
        return {"status": "error", "message": "Column name required"}
    if not display_name:
        return {"status": "error", "message": "Display name required"}

    config = load_config()
    table_name = table if table.startswith("sheet_") else sanitize_table_name(table)

    if table_name not in config["tables"]:
        return {"status": "error", "message": f"Table '{table}' not found"}

    # Find column in config
    col_found = False
    for col in config["tables"][table_name]["columns"]:
        if col["name"] == column:
            col["display_name"] = display_name
            col_found = True
            break

    if not col_found:
        return {"status": "error", "message": f"Column '{column}' not found in table"}

    # Update _tables_meta in database
    conn = get_db()
    try:
        cursor = conn.execute("SELECT columns_json FROM _tables_meta WHERE table_name = ?", (table_name,))
        row = cursor.fetchone()
        if row:
            columns_list = json.loads(row["columns_json"])
            for col in columns_list:
                if col["name"] == column:
                    col["display_name"] = display_name
                    break
            conn.execute(
                "UPDATE _tables_meta SET columns_json = ? WHERE table_name = ?",
                (json.dumps(columns_list), table_name)
            )
            conn.commit()

        # Update config file
        save_config(config)

        return {"status": "success", "table_name": table_name, "column": column, "display_name": display_name}
    except Exception as e:
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()


def execute(action, params=None):
    """Main entry point for execution_hub."""
    if params is None:
        params = {}

    if action == "create_table":
        result = create_table(params)
    elif action == "add_row":
        result = add_row(params)
    elif action == "update_row":
        result = update_row(params)
    elif action == "delete_row":
        result = delete_row(params)
    elif action == "query":
        result = query(params)
    elif action == "list_tables":
        result = list_tables(params)
    elif action == "delete_table":
        result = delete_table(params)
    elif action == "export_csv":
        result = export_csv(params)
    elif action == "add_column":
        result = add_column(params)
    elif action == "update_column_name":
        result = update_column_name(params)
    else:
        result = {"status": "error", "message": f"Unknown action: {action}"}

    return result


if __name__ == "__main__":
    import sys
    import argparse

    if len(sys.argv) < 2:
        print(json.dumps({"status": "error", "message": "Usage: sheets_tool.py <action> --params '{...}'"}))
        sys.exit(1)

    action = sys.argv[1]

    # Parse --params argument (execution_hub style)
    parser = argparse.ArgumentParser()
    parser.add_argument("action", nargs="?")
    parser.add_argument("--params", type=str, default="{}")
    args = parser.parse_args()

    params = json.loads(args.params) if args.params else {}

    result = execute(action, params)
    print(json.dumps(result, indent=2))
