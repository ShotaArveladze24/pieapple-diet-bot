-- Schema database per PieappleDietBot

CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_filename TEXT NOT NULL,
    source_language TEXT NOT NULL,
    week_start_date TEXT NOT NULL,
    uploaded_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS meals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    plan_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    meal_type TEXT NOT NULL CHECK (meal_type IN ('breakfast', 'lunch', 'dinner')),
    dish_name TEXT NOT NULL,
    description TEXT,
    ingredients TEXT,
    instructions TEXT,
    recipe_link TEXT,
    calories INTEGER,
    macros_json TEXT,
    calendar_event_id TEXT,
    is_substitution INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (plan_id) REFERENCES plans(id)
);

CREATE TABLE IF NOT EXISTS consumption_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meal_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('eaten_as_planned', 'eaten_different', 'skipped')),
    note TEXT,
    logged_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (meal_id) REFERENCES meals(id)
);

CREATE TABLE IF NOT EXISTS recipes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    ingredients TEXT,
    instructions TEXT,
    calories INTEGER,
    macros_json TEXT,
    link_it TEXT,
    link_es TEXT,
    link_en TEXT,
    name_it TEXT,
    name_es TEXT,
    name_en TEXT,
    notes TEXT,
    calories_per_100g INTEGER,
    protein_per_100g_g REAL,
    carbs_per_100g_g REAL,
    fat_per_100g_g REAL,
    difficulty INTEGER,
    prep_time_minutes INTEGER,
    cook_time_minutes INTEGER,
    oven_temperature_c INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_recipes_name ON recipes(name COLLATE NOCASE);

CREATE TABLE IF NOT EXISTS days_off (
    date TEXT PRIMARY KEY,
    note TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_meals_plan_date ON meals(plan_id, date);
CREATE INDEX IF NOT EXISTS idx_consumption_meal ON consumption_log(meal_id);
