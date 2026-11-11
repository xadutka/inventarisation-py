                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 #!/usr/bin/env python3
"""Учет оборудования: что где стоит и по какому адресу.

Хранение: SQLite (файл inventory.db рядом со скриптом).
Сканер штрихкодов/QR работает как обычная клавиатура: он «вводит» код
и нажимает Enter, поэтому достаточно курсора в строке ввода.
Запуск: python inventory.py
"""
import csv
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).with_name("inventory.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS locations (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT NOT NULL UNIQUE,      -- например: «Серверная, шкаф 2»
    address TEXT NOT NULL DEFAULT ''   -- например: «г. Москва, ул. Ленина 1, к. 305»
);
CREATE TABLE IF NOT EXISTS equipment (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT NOT NULL UNIQUE,  -- инвентарный номер / штрихкод
    name        TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT '',
    serial      TEXT NOT NULL DEFAULT '',
    note        TEXT NOT NULL DEFAULT '',
    location_id INTEGER REFERENCES locations(id),
    last_check  TEXT                   -- дата последней инвентаризации
);
CREATE TABLE IF NOT EXISTS movements (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    equipment_id INTEGER NOT NULL REFERENCES equipment(id),
    from_loc    INTEGER REFERENCES locations(id),
    to_loc      INTEGER REFERENCES locations(id),
    moved_at    TEXT NOT NULL
);
"""

BASE_SELECT = """
SELECT e.id, e.code, e.name, e.category, e.serial, e.note, e.last_check,
       l.id AS loc_id, COALESCE(l.name, '— не назначено —') AS loc_name,
       COALESCE(l.address, '') AS address
FROM equipment e LEFT JOIN locations l ON l.id = e.location_id
"""


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def connect():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def ask(prompt, default=""):
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


# ---------- места ----------

def pick_location(db, prompt="Номер места"):
    rows = db.execute("SELECT * FROM locations ORDER BY name").fetchall()
    if not rows:
        print("Мест пока нет. Сначала добавьте место (пункт 1).")
        return None
    for r in rows:
        print(f"  {r['id']:>3}. {r['name']}  ({r['address'] or 'адрес не указан'})")
    value = ask(prompt)
    if not value.isdigit():
        return None
    return db.execute("SELECT * FROM locations WHERE id=?", (int(value),)).fetchone()


def add_location(db):
    name = ask("Название места (кабинет, шкаф, склад)")
    if not name:
        return
    address = ask("Адрес (город, улица, здание, этаж, кабинет)")
    try:
        db.execute("INSERT INTO locations(name, address) VALUES(?,?)", (name, address))
        db.commit()
        print("Место добавлено.")
    except sqlite3.IntegrityError:
        print("Место с таким названием уже есть.")


# ---------- оборудование ----------

def find_by_code(db, code):
    return db.execute(BASE_SELECT + " WHERE e.code = ?", (code,)).fetchone()


def show(row):
    print(f"\n  Код:        {row['code']}")
    print(f"  Название:   {row['name']}")
    if row["category"]:
        print(f"  Категория:  {row['category']}")
    if row["serial"]:
        print(f"  Серийный №: {row['serial']}")
    print(f"  Где стоит:  {row['loc_name']}")
    if row["address"]:
        print(f"  Адрес:      {row['address']}")
    if row["note"]:
        print(f"  Заметка:    {row['note']}")
    if row["last_check"]:
        print(f"  Проверено:  {row['last_check']}")
    print()


def add_equipment(db):
    print("Отсканируйте штрихкод (или введите инв. номер). Пустая строка — выход.")
    while True:
        code = ask("Код")
        if not code:
            return
        if find_by_code(db, code):
            print("Такой код уже есть в базе.")
            continue
        name = ask("Название")
        if not name:
            continue
        category = ask("Категория (ПК, принтер, сервер...)")
        serial = ask("Серийный номер")
        note = ask("Заметка")
        loc = pick_location(db, "Номер места (Enter — пропустить)")
        loc_id = loc["id"] if loc else None
        cur = db.execute(
            "INSERT INTO equipment(code,name,category,serial,note,location_id,last_check)"
            " VALUES(?,?,?,?,?,?,?)",
            (code, name, category, serial, note, loc_id, now() if loc_id else None),
        )
        if loc_id:
            db.execute(
                "INSERT INTO movements(equipment_id,from_loc,to_loc,moved_at) VALUES(?,?,?,?)",
                (cur.lastrowid, None, loc_id, now()),
            )
        db.commit()
        print("Добавлено.\n")


def lookup(db):
    print("Сканируйте или вводите код/часть названия. Пустая строка — выход.")
    while True:
        q = ask("Поиск")
        if not q:
            return
        row = find_by_code(db, q)
        if row:
            show(row)
            continue
        like = f"%{q}%"
        rows = db.execute(
            BASE_SELECT + " WHERE e.name LIKE ? OR e.serial LIKE ? OR e.code LIKE ? "
            "OR e.category LIKE ? ORDER BY e.name", (like,) * 4).fetchall()
        if not rows:
            print("Ничего не найдено.\n")
        for r in rows:
            print(f"  {r['code']:<14} {r['name']:<28} → {r['loc_name']} ({r['address']})")
        print()


def move_mode(db):
    loc = pick_location(db, "Куда перемещаем? Номер места")
    if not loc:
        return
    print(f"Сканируйте оборудование — оно будет перемещено в «{loc['name']}». "
          "Пустая строка — выход.")
    while True:
        code = ask("Код")
        if not code:
            return
        row = find_by_code(db, code)
        if not row:
            print("  Код не найден. Добавьте его через пункт 2.")
            continue
        if row["loc_id"] == loc["id"]:
            print(f"  {row['name']}: уже здесь.")
            continue
        db.execute("UPDATE equipment SET location_id=?, last_check=? WHERE id=?",
                   (loc["id"], now(), row["id"]))
        db.execute("INSERT INTO movements(equipment_id,from_loc,to_loc,moved_at) VALUES(?,?,?,?)",
                   (row["id"], row["loc_id"], loc["id"], now()))
        db.commit()
        print(f"  ✓ {row['name']}: {row['loc_name']} → {loc['name']}")


def audit(db):
    """Инвентаризация: сканируем всё, что видим в месте, и сверяем с базой."""
    loc = pick_location(db, "Какое место проверяем? Номер")
    if not loc:
        return
    expected = {r["code"]: r for r in db.execute(
        BASE_SELECT + " WHERE e.location_id=?", (loc["id"],))}
    seen, foreign, unknown = set(), [], []
    print(f"Сканируйте всё оборудование в «{loc['name']}». Пустая строка — завершить.")
    while True:
        code = ask("Код")
        if not code:
            break
        if code in expected:
            seen.add(code)
            print(f"  ✓ {expected[code]['name']}")
            continue
        row = find_by_code(db, code)
        if row:
            foreign.append(row)
            print(f"  ! {row['name']} числится в «{row['loc_name']}»")
        else:
            unknown.append(code)
            print("  ? Код не найден в базе")

    ts = now()
    for code in seen:
        db.execute("UPDATE equipment SET last_check=? WHERE code=?", (ts, code))
    db.commit()

    missing = [r for c, r in expected.items() if c not in seen]
    print(f"\n=== Итог: {loc['name']} ===")
    print(f"Найдено на месте: {len(seen)} из {len(expected)}")
    if missing:
        print("Не найдено (числится здесь):")
        for r in missing:
            print(f"  - {r['code']}  {r['name']}")
    if foreign:
        print("Чужое оборудование здесь:")
        for r in foreign:
            print(f"  - {r['code']}  {r['name']} (числится: {r['loc_name']})")
        if ask("Переместить их в это место в базе? (д/н)", "н").lower().startswith(("д", "y")):
            for r in foreign:
                db.execute("UPDATE equipment SET location_id=?, last_check=? WHERE id=?",
                           (loc["id"], ts, r["id"]))
                db.execute("INSERT INTO movements(equipment_id,from_loc,to_loc,moved_at)"
                           " VALUES(?,?,?,?)", (r["id"], r["loc_id"], loc["id"], ts))
            db.commit()
            print("База обновлена.")
    if unknown:
        print("Неизвестные коды:", ", ".join(unknown))
    print()


def list_all(db):
    rows = db.execute(BASE_SELECT + " ORDER BY loc_name, e.name").fetchall()
    current = None
    for r in rows:
        if r["loc_name"] != current:
            current = r["loc_name"]
            print(f"\n{current}  [{r['address'] or 'адрес не указан'}]")
        print(f"   {r['code']:<14} {r['name']:<30} {r['category']}")
    print(f"\nВсего единиц: {len(rows)}\n")


def history(db):
    code = ask("Код оборудования")
    row = find_by_code(db, code)
    if not row:
        print("Не найдено.")
        return
    show(row)
    for m in db.execute("""
        SELECT m.moved_at, COALESCE(a.name,'—') AS src, COALESCE(b.name,'—') AS dst
        FROM movements m LEFT JOIN locations a ON a.id=m.from_loc
        LEFT JOIN locations b ON b.id=m.to_loc
        WHERE m.equipment_id=? ORDER BY m.id""", (row["id"],)):
        print(f"  {m['moved_at']}  {m['src']} → {m['dst']}")
    print()


def export_csv(db):
    path = Path(ask("Имя файла", "inventory_export.csv"))
    rows = db.execute(BASE_SELECT + " ORDER BY loc_name, e.name").fetchall()
    with path.open("w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig — чтобы Excel читал кириллицу
        w = csv.writer(f, delimiter=";")
        w.writerow(["Код", "Название", "Категория", "Серийный №", "Место", "Адрес",
                    "Заметка", "Последняя проверка"])
        for r in rows:
            w.writerow([r["code"], r["name"], r["category"], r["serial"], r["loc_name"],
                        r["address"], r["note"], r["last_check"] or ""])
    print(f"Сохранено: {path.resolve()}\n")


MENU = """
===== Учет оборудования =====
 1. Добавить место (кабинет/склад + адрес)
 2. Добавить оборудование (сканером)
 3. Найти / посмотреть (сканером)
 4. Переместить оборудование (сканером)
 5. Инвентаризация места
 6. Список всего оборудования
 7. История перемещений
 8. Экспорт в CSV (Excel)
 0. Выход
"""

ACTIONS = {"1": add_location, "2": add_equipment, "3": lookup, "4": move_mode,
           "5": audit, "6": list_all, "7": history, "8": export_csv}


def main():
    db = connect()
    while True:
        print(MENU)
        try:
            choice = ask("Выбор")
        except EOFError:
            break
        if choice == "0":
            break
        action = ACTIONS.get(choice)
        if not action:
            continue
        try:
            action(db)
        except (KeyboardInterrupt, EOFError):
            print("\nОтменено.")
    db.close()


if __name__ == "__main__":
    sys.exit(main())
