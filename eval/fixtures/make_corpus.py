"""Deterministic DE+EN synthetic eval corpus for golden_v2.jsonl (Phase 0).

Generates the fixture documents that every question in eval/golden_v2.jsonl is
grounded in. All facts live in the constants below; the golden set references
the SAME constants (file, page, wording), so regeneration never invalidates
ground truth. Do not edit facts without updating golden_v2.jsonl.

Documents (into ./corpus, or argv[1]):
  it_richtlinie_de.pdf          6-page German IT security policy   -> text (de)
  employee_handbook_en.pdf      5-page English employee handbook   -> text (en)
  reisekosten_mixed.pdf         4-page mixed DE/EN travel policy   -> text (mixed)
  onboarding_leitfaden.docx     German onboarding guide w/ table   -> text+table (de)
  quartalsbericht_tabellen.pdf  3 pages of ruled tables (merged
                                headers on p.2)                    -> table (de)
  personal_budget.xlsx          2 sheets (Personal, Sachkosten)    -> table (de)
  kennzahlen_charts.pdf         bar/line/pie charts, values only
                                inside the images                  -> chart (de)
  systemarchitektur_diagramm.pdf labeled box-and-arrow diagram,
                                text only inside the image         -> diagram (de)
  betriebsanweisung_scan.pdf    2 image-only (rasterized) German
                                pages                              -> scanned (de)

Chart/diagram values appear ONLY inside rendered images (captions carry no
numbers), so text-only extraction cannot answer the visual questions — that is
the point of the visual baseline.

Run inside the backend image (all deps present):
  docker compose -f docker-compose.dev.yml run --rm --no-deps \
      -v "<repo>:/srv" backend python eval/fixtures/make_corpus.py
"""

from __future__ import annotations

import io
import os
import sys

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "corpus")
os.makedirs(OUT, exist_ok=True)

PAGE_W, PAGE_H = 595, 842  # A4 points
MARGIN = 60
LINE_H = 16


def _p(name: str) -> str:
    return os.path.join(OUT, name)


# --------------------------------------------------------------------------
# Shared text-PDF writer: one section per page => deterministic page refs.
# --------------------------------------------------------------------------

def write_text_pdf(name: str, title: str, pages: list[tuple[str, list[str]]]) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(_p(name), pagesize=A4)
    for heading, lines in pages:
        c.setFont("Helvetica-Bold", 14)
        c.drawString(MARGIN, PAGE_H - MARGIN, title)
        c.setFont("Helvetica-Bold", 12)
        c.drawString(MARGIN, PAGE_H - MARGIN - 28, heading)
        text = c.beginText(MARGIN, PAGE_H - MARGIN - 56)
        text.setFont("Helvetica", 11)
        for line in lines:
            text.textLine(line)
        c.drawText(text)
        c.showPage()
    c.save()


# --------------------------------------------------------------------------
# 1. it_richtlinie_de.pdf — German IT security policy (6 pages)
# --------------------------------------------------------------------------

IT_RICHTLINIE = [
    ("§ 1 Passwörter", [
        "Passwörter müssen mindestens 14 Zeichen lang sein und Groß-, Kleinbuchstaben,",
        "Ziffern sowie Sonderzeichen enthalten.",
        "Passwörter sind spätestens alle 180 Tage zu wechseln.",
        "Die Wiederverwendung der letzten 10 Passwörter ist untersagt.",
        "Als Passwort-Manager ist ausschließlich KeePassXC zugelassen.",
        "Die Weitergabe von Passwörtern, auch an Kolleginnen und Kollegen, ist verboten.",
    ]),
    ("§ 2 Zwei-Faktor-Authentifizierung", [
        "Die Zwei-Faktor-Authentifizierung ist für alle Unternehmenskonten verpflichtend.",
        "Als TOTP-Anwendung wird privacyIDEA Authenticator eingesetzt.",
        "Administratorkonten erhalten zusätzlich einen Hardware-Token vom Typ YubiKey 5.",
        "Ersatz-Token sind beim IT-Servicedesk (Ticketkategorie SEC-2FA) zu beantragen.",
        "Der Verlust eines Tokens ist unverzüglich, spätestens binnen 24 Stunden, zu melden.",
    ]),
    ("§ 3 VPN und Fernzugriff", [
        "Der Fernzugriff auf das Unternehmensnetz erfolgt ausschließlich über WireGuard-VPN.",
        "Split-Tunneling ist deaktiviert und darf nicht umgangen werden.",
        "VPN-Sitzungen werden nach 12 Stunden automatisch getrennt.",
        "Der Zugriff ist nur von verwalteten Firmengeräten zulässig.",
        "Zugriffe aus Ländern außerhalb der EU erfordern eine vorherige Genehmigung des CISO.",
    ]),
    ("§ 4 Datensicherung", [
        "Inkrementelle Sicherungen laufen täglich um 22:00 Uhr.",
        "Eine Vollsicherung erfolgt jeden Sonntag.",
        "Sicherungen werden 90 Tage aufbewahrt.",
        "Wiederherstellungstests finden quartalsweise statt.",
        "Es gelten ein RPO von 24 Stunden und ein RTO von 8 Stunden.",
    ]),
    ("§ 5 Meldung von Sicherheitsvorfällen", [
        "Sicherheitsvorfälle sind innerhalb von 4 Stunden an sicherheit@muster-industrie.de",
        "oder telefonisch über die Durchwahl -555 zu melden.",
        "Vorfälle werden in vier Schweregrade eingestuft: KRITISCH, HOCH, MITTEL, NIEDRIG.",
        "Bei Einstufung KRITISCH ist die Geschäftsführung binnen 1 Stunde zu informieren.",
        "Die Meldung eines Vorfalls hat niemals arbeitsrechtliche Nachteile für Meldende.",
    ]),
    ("§ 6 Geräte und Software", [
        "Softwareinstallationen sind nur aus dem internen Software-Portal zulässig.",
        "USB-Datenträger müssen mit BitLocker verschlüsselt sein.",
        "Die Nutzung privater Geräte für dienstliche Zwecke ist untersagt.",
        "Ausnahmeanträge sind an die CISO, Frau Dr. Lehmann, zu richten.",
        "Über Ausnahmeanträge wird innerhalb von höchstens 10 Arbeitstagen entschieden.",
    ]),
]


# --------------------------------------------------------------------------
# 2. employee_handbook_en.pdf — English handbook (5 pages)
#    Page 2 and 4 deliberately carry the golden-v1 facts (remote days, MFA).
# --------------------------------------------------------------------------

HANDBOOK = [
    ("Section 1: Working Hours", [
        "The standard working week is 38.5 hours.",
        "Core hours are 10:00 to 15:00; flextime is permitted between 06:00 and 20:00.",
        "Working time is recorded in TimeTrack Pro.",
        "Overtime above 10 hours per month requires prior manager approval.",
    ]),
    ("Section 2: Remote Work", [
        "Employees may work remotely up to three days per week with manager approval.",
        "Equipment is provided by the IT department upon request.",
        "A home-office allowance of EUR 25 per month is paid automatically.",
        "A one-time ergonomic chair subsidy of EUR 200 can be claimed via the HR portal.",
    ]),
    ("Section 3: Leave", [
        "Employees receive 30 vacation days per calendar year.",
        "Unused vacation may be carried over until 31 March of the following year.",
        "A doctor's note is required from the third consecutive sick day.",
        "Two days of special leave are granted for your own relocation.",
    ]),
    ("Section 4: Security", [
        "All staff must enable multi-factor authentication on company accounts.",
        "Confidential documents must not be shared outside the organization.",
        "A clean-desk policy applies in all open-plan offices.",
        "Visitors must wear a visitor badge and be accompanied at all times.",
    ]),
    ("Section 5: Benefits", [
        "The public-transport Jobticket is subsidized at 100 percent.",
        "The gym subsidy is EUR 30 per month.",
        "The company matches pension contributions up to 4 percent of gross salary.",
        "The employee referral bonus is EUR 1500, paid after the probation period.",
    ]),
]


# --------------------------------------------------------------------------
# 3. reisekosten_mixed.pdf — mixed DE/EN travel policy (4 pages)
# --------------------------------------------------------------------------

REISEKOSTEN = [
    ("Abschnitt 1: Verpflegung (DE)", [
        "Die Verpflegungspauschale beträgt 28 EUR pro vollem Reisetag.",
        "An An- und Abreisetagen beträgt die Pauschale 14 EUR.",
        "Dienstreisen sind vor der Buchung durch die oder den Vorgesetzten zu genehmigen.",
    ]),
    ("Section 2: Accommodation (EN)", [
        "The hotel cost cap is EUR 120 per night for domestic trips.",
        "For international trips the cap is EUR 160 per night.",
        "All bookings must be made through the TravelHub platform.",
    ]),
    ("Abschnitt 3: Verkehrsmittel (DE)", [
        "Bahnfahrten ab 2 Stunden Fahrzeit dürfen in der 1. Klasse gebucht werden.",
        "Flüge unter 6 Stunden sind in der Economy Class zu buchen.",
        "Business Class ist ab 6 Stunden Flugzeit mit Genehmigung der Bereichsleitung zulässig.",
    ]),
    ("Section 4: Reimbursement (EN)", [
        "Expense reports must be submitted within 30 days after the end of the trip.",
        "Expenses are submitted via the Rydoo app.",
        "The mileage rate for private cars is EUR 0.30 per kilometre.",
    ]),
]


# --------------------------------------------------------------------------
# 4. onboarding_leitfaden.docx — German onboarding guide with a table
# --------------------------------------------------------------------------

def make_onboarding_docx() -> None:
    import docx

    d = docx.Document()
    d.add_heading("Onboarding-Leitfaden", level=1)
    d.add_paragraph(
        "Willkommen bei der Muster Industrie GmbH. Dieser Leitfaden begleitet Sie "
        "durch Ihre ersten Wochen."
    )
    d.add_heading("Erste Woche", level=2)
    d.add_paragraph(
        "Der IT-Zugang wird über ein Ticket der Kategorie ONBOARD-IT beantragt. "
        "Ihren Laptop erhalten Sie am ersten Arbeitstag von der IT-Abteilung. "
        "Die Sicherheitsunterweisung findet verpflichtend in der ersten Woche statt."
    )
    d.add_heading("Rahmenbedingungen", level=2)
    d.add_paragraph(
        "Die Probezeit beträgt 6 Monate. Jede neue Mitarbeiterin und jeder neue "
        "Mitarbeiter nimmt für 3 Monate am Mentorenprogramm teil. Das erste "
        "Feedbackgespräch findet nach 6 Wochen statt."
    )
    d.add_heading("Checkliste", level=2)
    table = d.add_table(rows=5, cols=2)
    rows = [
        ("Aufgabe", "Zuständig"),
        ("Laptop-Ausgabe", "IT-Abteilung"),
        ("Zugangskarte", "Empfang"),
        ("Sicherheitsunterweisung", "CISO-Team"),
        ("Mentor-Zuordnung", "Personalabteilung"),
    ]
    for i, (a, b) in enumerate(rows):
        table.rows[i].cells[0].text = a
        table.rows[i].cells[1].text = b
    d.save(_p("onboarding_leitfaden.docx"))


# --------------------------------------------------------------------------
# 5. quartalsbericht_tabellen.pdf — ruled tables; merged headers on page 2
# --------------------------------------------------------------------------

UMSATZ_REGION = [
    ["Region", "Q1", "Q2", "Q3", "Q4", "Gesamt"],
    ["Nord", "3,2", "3,8", "4,1", "4,9", "16,0"],
    ["Süd", "2,9", "3,1", "3,6", "4,2", "13,8"],
    ["West", "4,4", "4,6", "5,0", "5,8", "19,8"],
    ["Ost", "1,5", "1,7", "2,1", "2,6", "7,9"],
]

PERSONALBESTAND = [  # merged header: 2024 / 2025 each span (Plan, Ist)
    ["Abteilung", "2024 Plan", "2024 Ist", "2025 Plan", "2025 Ist"],
    ["Produktion", "120", "118", "132", "135"],
    ["Vertrieb", "45", "47", "52", "50"],
    ["IT", "30", "28", "38", "40"],
    ["Verwaltung", "25", "25", "26", "27"],
]

PROJEKTBUDGET = [
    ["Projekt", "Budget (TEUR)", "Verbraucht (TEUR)", "Rest (TEUR)", "Status"],
    ["Phoenix", "850", "610", "240", "im Plan"],
    ["Atlas", "1200", "1310", "-110", "überzogen"],
    ["Merkur", "400", "150", "250", "im Plan"],
    ["Saturn", "600", "600", "0", "abgeschlossen"],
]


def make_tables_pdf() -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import (
        PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
    )
    from reportlab.lib.styles import getSampleStyleSheet

    styles = getSampleStyleSheet()
    grid = TableStyle([
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ])

    # Page 2 table with a genuinely merged header row (SPAN).
    merged_data = [
        ["Abteilung", "2024", "", "2025", ""],
        ["", "Plan", "Ist", "Plan", "Ist"],
        *[row[0:5] for row in PERSONALBESTAND[1:]],
    ]
    merged_style = TableStyle([
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ("BACKGROUND", (0, 0), (-1, 1), colors.lightgrey),
        ("FONTNAME", (0, 0), (-1, 1), "Helvetica-Bold"),
        ("SPAN", (1, 0), (2, 0)),   # "2024" spans Plan+Ist
        ("SPAN", (3, 0), (4, 0)),   # "2025" spans Plan+Ist
        ("SPAN", (0, 0), (0, 1)),   # "Abteilung" spans both header rows
        ("ALIGN", (1, 0), (-1, 0), "CENTER"),
    ])

    story = [
        Paragraph("Quartalsbericht 2025 — Muster Industrie GmbH", styles["Title"]),
        Paragraph("Tabelle 1: Umsatz nach Region (Mio. EUR)", styles["Heading2"]),
        Table(UMSATZ_REGION, style=grid),
        PageBreak(),
        Paragraph("Tabelle 2: Personalbestand nach Abteilung (Plan/Ist)", styles["Heading2"]),
        Table(merged_data, style=merged_style),
        PageBreak(),
        Paragraph("Tabelle 3: Projektbudgets (TEUR)", styles["Heading2"]),
        Table(PROJEKTBUDGET, style=grid),
        Spacer(1, 12),
    ]
    SimpleDocTemplate(_p("quartalsbericht_tabellen.pdf"), pagesize=A4).build(story)


# --------------------------------------------------------------------------
# 6. personal_budget.xlsx — 2 sheets
# --------------------------------------------------------------------------

SACHKOSTEN = [
    ["Position", "Betrag (EUR)"],
    ["Softwarelizenzen", 84000],
    ["Hardware", 52000],
    ["Schulungen", 18000],
    ["Reisekosten", 26500],
]


def make_budget_xlsx() -> None:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Personal"
    for row in PERSONALBESTAND:
        ws.append(row)
    ws2 = wb.create_sheet("Sachkosten")
    for row in SACHKOSTEN:
        ws2.append(row)
    wb.save(_p("personal_budget.xlsx"))


# --------------------------------------------------------------------------
# 7. kennzahlen_charts.pdf — values ONLY inside rendered chart images
# --------------------------------------------------------------------------

UMSATZ_QUARTAL = [("Q1", 12), ("Q2", 15), ("Q3", 18), ("Q4", 21)]           # Mio. EUR 2025
MITARBEITER_JAHR = [("2021", 180), ("2022", 210), ("2023", 235), ("2024", 260), ("2025", 300)]
BUDGET_ANTEILE = [("IT", 40), ("Produktion", 30), ("Vertrieb", 20), ("Verwaltung", 10)]  # %


def _bar_chart_png() -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (640, 420), "white")
    d = ImageDraw.Draw(img)
    d.text((180, 10), "Umsatz je Quartal 2025 (Mio. EUR)", fill="black")
    base_y, scale = 360, 14
    d.line([60, base_y, 600, base_y], fill="black", width=2)   # x-axis
    d.line([60, 40, 60, base_y], fill="black", width=2)        # y-axis
    for i, (label, v) in enumerate(UMSATZ_QUARTAL):
        x0 = 110 + i * 120
        d.rectangle([x0, base_y - v * scale, x0 + 70, base_y], fill="steelblue")
        d.text((x0 + 25, base_y - v * scale - 18), str(v), fill="black")
        d.text((x0 + 22, base_y + 8), label, fill="black")
    for yv in (5, 10, 15, 20):
        d.text((30, base_y - yv * scale - 6), str(yv), fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _line_chart_png() -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (640, 420), "white")
    d = ImageDraw.Draw(img)
    d.text((190, 10), "Mitarbeiterzahl 2021-2025", fill="black")
    base_y = 360
    d.line([60, base_y, 600, base_y], fill="black", width=2)
    d.line([60, 40, 60, base_y], fill="black", width=2)
    pts = []
    for i, (label, v) in enumerate(MITARBEITER_JAHR):
        x = 100 + i * 115
        y = base_y - (v - 150) * 1.8
        pts.append((x, y))
        d.text((x - 12, base_y + 8), label, fill="black")
        d.text((x - 10, y - 22), str(v), fill="black")
    d.line(pts, fill="darkred", width=3)
    for p in pts:
        d.ellipse([p[0] - 4, p[1] - 4, p[0] + 4, p[1] + 4], fill="darkred")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _pie_chart_png() -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (640, 420), "white")
    d = ImageDraw.Draw(img)
    d.text((200, 10), "Budgetverteilung 2025 (%)", fill="black")
    colors_ = ["steelblue", "darkorange", "seagreen", "gray"]
    start = 0.0
    for (label, pct), col in zip(BUDGET_ANTEILE, colors_):
        end = start + pct * 3.6
        d.pieslice([120, 60, 440, 380], start, end, fill=col, outline="black")
        start = end
    for i, ((label, pct), col) in enumerate(zip(BUDGET_ANTEILE, colors_)):
        y = 100 + i * 34
        d.rectangle([470, y, 494, y + 18], fill=col, outline="black")
        d.text((502, y + 2), f"{label}: {pct}%", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_charts_pdf() -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    charts = [
        ("Abbildung 1: Umsatzentwicklung nach Quartal", _bar_chart_png()),
        ("Abbildung 2: Entwicklung der Mitarbeiterzahl", _line_chart_png()),
        ("Abbildung 3: Verteilung des Gesamtbudgets", _pie_chart_png()),
    ]
    c = canvas.Canvas(_p("kennzahlen_charts.pdf"), pagesize=A4)
    for caption, png in charts:
        c.setFont("Helvetica-Bold", 14)
        c.drawString(MARGIN, PAGE_H - MARGIN, "Kennzahlenbericht 2025")
        c.drawImage(ImageReader(io.BytesIO(png)), MARGIN, 320, width=480, height=315)
        c.setFont("Helvetica", 11)
        c.drawString(MARGIN, 290, caption)  # caption carries NO numeric values
        c.showPage()
    c.save()


# --------------------------------------------------------------------------
# 8. systemarchitektur_diagramm.pdf — labels only inside the image
# --------------------------------------------------------------------------

def _diagram_png() -> bytes:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (760, 480), "white")
    d = ImageDraw.Draw(img)

    def box(x, y, label):
        d.rectangle([x, y, x + 170, y + 56], outline="black", width=2)
        d.text((x + 14, y + 20), label, fill="black")
        return (x + 85, y + 28)

    def arrow(a, b):
        d.line([a, b], fill="black", width=2)
        d.ellipse([b[0] - 4, b[1] - 4, b[0] + 4, b[1] + 4], fill="black")

    web = box(40, 60, "Web-Portal")
    gw = box(290, 60, "API-Gateway")
    auth = box(540, 20, "Auth-Dienst")
    docs = box(540, 120, "Dokumenten-Dienst")
    db = box(540, 320, "PostgreSQL")
    arrow((web[0] + 85, web[1]), (gw[0] - 85, gw[1]))
    arrow((gw[0] + 85, gw[1] - 10), (auth[0] - 85, auth[1]))
    arrow((gw[0] + 85, gw[1] + 10), (docs[0] - 85, docs[1]))
    arrow((docs[0], docs[1] + 28), (db[0], db[1] - 28))
    d.text((40, 430), "Alle Verbindungen sind TLS-verschluesselt.", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_diagram_pdf() -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(_p("systemarchitektur_diagramm.pdf"), pagesize=A4)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(MARGIN, PAGE_H - MARGIN, "Systemarchitektur Dokumentenplattform")
    c.drawImage(ImageReader(io.BytesIO(_diagram_png())), MARGIN, 350, width=475, height=300)
    c.setFont("Helvetica", 11)
    c.drawString(MARGIN, 320, "Abbildung 1: Komponenten und Datenfluesse der Plattform")
    c.showPage()
    c.save()


# --------------------------------------------------------------------------
# 9. betriebsanweisung_scan.pdf — image-only (rasterized) German pages
# --------------------------------------------------------------------------

BETRIEBSANWEISUNG = [
    ("Betriebsanweisung Lagerhalle - Teil 1", [
        "In der Lagerhalle besteht Schutzhelmpflicht.",
        "Die maximale Stapelhoehe betraegt 4 Paletten.",
        "Gabelstapler duerfen hoechstens 10 km/h fahren.",
        "Fluchtwege und Notausgaenge sind jederzeit freizuhalten.",
    ]),
    ("Betriebsanweisung Lagerhalle - Teil 2", [
        "Der Erste-Hilfe-Kasten befindet sich an Tor 3.",
        "Ersthelfer ist Herr Krause, Durchwahl -210.",
        "Unfaelle sind sofort dem Schichtleiter zu melden.",
        "Das Rauchen ist auf dem gesamten Gelaende verboten.",
    ]),
]
# NOTE: ASCII-transliterated umlauts (ae/oe/ue) — the backend image ships only
# the English tesseract model (see docs/AUDIT.md §8), which cannot read ä/ö/ü.
# Keeps the scanned baseline about the VISUAL path, not about a known OCR gap.


def make_scanned_pdf() -> None:
    import fitz
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    # First produce a normal text PDF in memory...
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    for heading, lines in BETRIEBSANWEISUNG:
        c.setFont("Helvetica-Bold", 16)
        c.drawString(MARGIN, PAGE_H - MARGIN, heading)
        text = c.beginText(MARGIN, PAGE_H - MARGIN - 40)
        text.setFont("Helvetica", 14)
        for line in lines:
            text.textLine(line)
            text.textLine("")
        c.drawText(text)
        c.showPage()
    c.save()

    # ...then rasterize every page so no text layer survives.
    src = fitz.open(stream=buf.getvalue(), filetype="pdf")
    out = fitz.open()
    for page in src:
        pix = page.get_pixmap(dpi=200)
        new = out.new_page(width=pix.width, height=pix.height)
        new.insert_image(new.rect, stream=pix.tobytes("png"))
    src.close()
    out.save(_p("betriebsanweisung_scan.pdf"), deflate=True, deflate_images=True)
    out.close()


# --------------------------------------------------------------------------

def main() -> None:
    write_text_pdf("it_richtlinie_de.pdf",
                   "IT-Sicherheitsrichtlinie — Muster Industrie GmbH", IT_RICHTLINIE)
    write_text_pdf("employee_handbook_en.pdf",
                   "Employee Handbook — Nordwind Logistics GmbH", HANDBOOK)
    write_text_pdf("reisekosten_mixed.pdf",
                   "Reisekostenrichtlinie / Travel Expense Policy", REISEKOSTEN)
    make_onboarding_docx()
    make_tables_pdf()
    make_budget_xlsx()
    make_charts_pdf()
    make_diagram_pdf()
    make_scanned_pdf()
    print("corpus written to", os.path.abspath(OUT))
    for f in sorted(os.listdir(OUT)):
        print(f"  {f}  {os.path.getsize(_p(f))} bytes")


if __name__ == "__main__":
    main()
