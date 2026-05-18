import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "citizenprint.db"

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()

cur.executescript("""
CREATE TABLE IF NOT EXISTS products (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL UNIQUE,
    emoji        TEXT    NOT NULL,
    description  TEXT    NOT NULL,
    sizes        TEXT    NOT NULL,
    finish       TEXT    NOT NULL,
    best_for     TEXT    NOT NULL,
    min_qty      TEXT    NOT NULL,
    active       INTEGER NOT NULL DEFAULT 1
);
""")

products = [
    ("Visiting Cards",  "💼", "Professional visiting cards to make a lasting first impression.",
     "Standard (3.5x2) | Square (2.5x2.5) | Slim (3.5x1.5)",
     "Matte | Glossy | Soft Touch | UV Spot | Foil",
     "Professionals, freelancers, business networking", "100 cards"),
    ("Business Cards",  "🏢", "Premium business cards with corporate-grade print quality.",
     "Standard (3.5x2) | Premium (3.5x2.5)",
     "Matte | Glossy | Embossed | Foil | Velvet Lamination",
     "Corporate professionals, companies, startups", "100 cards"),
    ("Flyers",          "📄", "Eye-catching single-sheet flyers for promotions and announcements.",
     "A4 | A5 | A6 | DL (1/3 A4)", "Matte | Glossy | Uncoated",
     "Events, sales promotions, product launches, offers", "100 flyers"),
    ("Pamphlets",       "📰", "Folded pamphlets ideal for detailed product or service information.",
     "A4 Bi-fold | A4 Tri-fold | A5 Bi-fold", "Matte | Glossy",
     "Product info, service guides, educational material", "100 pamphlets"),
    ("Brochures",       "📑", "Multi-panel brochures for detailed brand storytelling.",
     "A4 Tri-fold | A4 Z-fold | A4 Bi-fold | A5 Bi-fold",
     "Matte | Glossy | Soft Touch Lamination",
     "Company profiles, product catalogs, tourism, real estate", "50 brochures"),
    ("Banners",         "🎌", "Large-format banners for high-visibility indoor and outdoor use.",
     "2x4 ft | 3x6 ft | 4x8 ft | Custom sizes available",
     "Vinyl (Outdoor) | Fabric (Indoor) | Mesh (Windy areas)",
     "Events, shop fronts, trade shows, outdoor advertising", "1 banner"),
    ("Posters",         "🖼️", "Vibrant full-colour posters to display your message boldly.",
     "A3 | A2 | A1 | A0 | Custom", "Matte | Glossy | Satin",
     "Events, advertising, decor, announcements", "10 posters"),
    ("Stickers",        "🏷️", "Custom-cut stickers in any shape for branding and packaging.",
     "Circle | Square | Rectangle | Custom die-cut shapes",
     "Matte | Glossy | Transparent | Waterproof",
     "Product labels, packaging, branding, giveaways", "100 stickers"),
    ("Letterheads",     "📋", "Branded letterheads for professional correspondence.",
     "A4 (standard)", "Matte | Glossy | Uncoated Bond Paper",
     "Business letters, quotes, invoices, official documents", "100 sheets"),
    ("Envelopes",       "✉️", "Custom-printed envelopes with your logo and return address.",
     "DL | C5 | C4 | A4 Pocket", "White | Brown Kraft | Custom colour",
     "Corporate mailers, invitations, official correspondence", "100 envelopes"),
    ("ID Cards",        "🪪", "Durable PVC ID cards for staff, students, and membership use.",
     "CR80 Standard (3.375x2.125) wallet size",
     "Glossy PVC | Frosted | with or without lamination pouch",
     "Employee IDs, student cards, membership cards, access cards", "25 cards"),
    ("Calendars",       "📅", "Customised wall and desk calendars branded with your logo.",
     "Wall Calendar (A3/A4) | Desk Calendar (A5) | Pocket Calendar",
     "Matte | Glossy | Spiral-bound | Staple-bound",
     "Corporate gifting, brand promotion, offices, year-end gifts", "25 calendars"),
]

cur.executemany("""
    INSERT OR IGNORE INTO products
        (name, emoji, description, sizes, finish, best_for, min_qty)
    VALUES (?, ?, ?, ?, ?, ?, ?)
""", products)

conn.commit()
count = cur.execute("SELECT COUNT(*) FROM products WHERE active=1").fetchone()[0]
print(f"DB ready at {DB_PATH}")
print(f"{count} active products loaded.")
conn.close()