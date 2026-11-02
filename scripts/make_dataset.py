"""Generate the synthetic W-2 test set and answer key. All people and employers are invented."""
import json
import random
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parent.parent
FIRST = "Maya Arjun Lena Tomas Priya Noah Sara Omar Elena Ravi Grace Luis Hana Ben Zoya Ivan".split()
LAST = "Rao Mehta Silva Cole Nair Park Haddad Lind Ortiz Kim Shah Bell".split()
COMPANIES = ["Northwind Labs", "Bluepine Systems", "Harbor Street Foods", "Cedar Analytics",
             "Quill & Co", "Orbit Freight", "Fernhill Clinic Supply", "Tallgrass Media"]
LAYOUTS = {"boxed": 10, "inline": 8, "inline_fica_first": 6, "payroll_export": 8}
fmt = lambda v: f"{v:,.2f}"


def record(rng, fica=True):
    wages = round(rng.uniform(28000, 118000), 2)
    pretax = rng.choice([0, 0, round(wages * 0.05, 2)])
    box3 = round(wages + pretax, 2) if fica else 0
    return {
        "box1": wages, "box2": round(wages * rng.uniform(0.09, 0.16), 2),
        "box3": box3, "box4": round(box3 * 0.062, 2),
        "box5": box3, "box6": round(box3 * 0.0145, 2),
        "box16": wages, "box17": round(wages * rng.uniform(0.03, 0.055), 2),
    }


def header(c, title, person, company):
    c.setFont("Helvetica-Bold", 13)
    c.drawString(50, 740, title)
    c.setFont("Helvetica", 9)
    c.drawString(50, 724, "SYNTHETIC SAMPLE. Not a real tax document.")
    c.drawString(50, 708, f"Employer: {company}")
    c.drawString(50, 694, f"Employee: {person}")


def boxed(c, r):
    cells = [("Wages, tips, other comp.", r["box1"], "Federal income tax withheld", r["box2"]),
             ("Social security wages", r["box3"], "Social security tax withheld", r["box4"]),
             ("Medicare wages and tips", r["box5"], "Medicare tax withheld", r["box6"]),
             ("State wages, tips, etc.", r["box16"], "State income tax", r["box17"])]
    y = 650
    for left, lv, right, rv in cells:
        for x, label, value in ((50, left, lv), (300, right, rv)):
            c.rect(x, y - 30, 240, 44)
            c.setFont("Helvetica", 8)
            c.drawString(x + 6, y + 2, label)
            c.setFont("Helvetica", 11)
            if value:
                c.drawString(x + 6, y - 16, fmt(value))
        y -= 54


def lines(c, rows):
    y = 650
    c.setFont("Helvetica", 10)
    for label, value in rows:
        if value:
            c.drawString(50, y, f"{label}: {fmt(value)}")
            y -= 18


def draw(path, layout, r, person, company):
    c = canvas.Canvas(str(path), pagesize=letter)
    title = "Form W-2 Wage and Tax Statement 2025"
    std = [("Wages, tips, other comp.", r["box1"]), ("Federal income tax withheld", r["box2"]),
           ("Social security wages", r["box3"]), ("Social security tax withheld", r["box4"]),
           ("Medicare wages and tips", r["box5"]), ("Medicare tax withheld", r["box6"]),
           ("State wages, tips, etc.", r["box16"]), ("State income tax", r["box17"])]
    if layout == "boxed":
        header(c, title, person, company)
        boxed(c, r)
    elif layout == "inline":
        header(c, title, person, company)
        lines(c, std)
    elif layout == "inline_fica_first":
        header(c, title + " (employee copy)", person, company)
        lines(c, std[2:] + std[:2])
    else:
        header(c, "W-2 Annual Earnings Summary 2025", person, company)
        lines(c, [("Gross Taxable Wages", r["box1"]), ("Federal W/H", r["box2"]),
                  ("OASDI Wages", r["box3"]), ("OASDI Tax", r["box4"]),
                  ("Medicare Wages", r["box5"]), ("Medicare Tax", r["box6"]),
                  ("State Wages", r["box16"]), ("State Tax", r["box17"])])
    c.save()


def production_doc():
    """A layout outside the test set: amounts drop .00 when the cents are zero, in two columns."""
    r = {"box1": 62400.0, "box2": 7812.40, "box3": 62400.0, "box4": 3868.80,
         "box5": 62400.0, "box6": 904.80, "box16": 62400.0, "box17": 2914.60}
    path = ROOT / "data" / "production" / "production_export_001.pdf"
    c = canvas.Canvas(str(path), pagesize=letter)
    header(c, "Form W-2 Wage and Tax Statement 2025", "Dana Whitfield", "Marlow Street Bakery")
    y, c_font = 650, c.setFont("Helvetica", 10)
    show = lambda v: f"{v:,.0f}" if v == int(v) else fmt(v)
    for a, av, b, bv in [("Wages, tips, other comp.", r["box1"], "Federal income tax withheld", r["box2"]),
                         ("Social security wages", r["box3"], "Social security tax withheld", r["box4"]),
                         ("Medicare wages and tips", r["box5"], "Medicare tax withheld", r["box6"]),
                         ("State wages, tips, etc.", r["box16"], "State income tax", r["box17"])]:
        c.drawString(50, y, f"{a} {show(av)}    {b} {show(bv)}")
        y -= 18
    c.save()
    return path.name, r


def main():
    rng = random.Random(7)
    golden = ROOT / "data" / "golden"
    key, n = {}, 0
    for layout, count in LAYOUTS.items():
        for i in range(count):
            n += 1
            r = record(rng, fica=(i % 4 != 3))
            name = f"w2_{n:03d}_{layout}.pdf"
            draw(golden / name, layout, r, f"{rng.choice(FIRST)} {rng.choice(LAST)}", rng.choice(COMPANIES))
            key[name] = {"layout": layout, "fields": r}
    (golden / "answer_key.json").write_text(json.dumps(key, indent=1))
    name, fields = production_doc()
    (ROOT / "data" / "production" / "reviewer_correction.json").write_text(
        json.dumps({name: {"layout": "two_column_export", "fields": fields}}, indent=1))
    print(f"Wrote {n} test documents and 1 production document")


if __name__ == "__main__":
    main()
