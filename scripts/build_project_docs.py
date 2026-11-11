"""Render versioned documentation Markdown into the five required PDFs.

The README and Markdown sources are preserved. This command never trains,
evaluates, deploys or changes application state. Install reportlab==4.4.9
in a separate documentation environment before running it. The docs folder stays
limited to five PDFs and five Markdown sources; report.md/report.pdf live at root.
"""

import argparse
import html
import math
import re
import textwrap
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    CondPageBreak, Flowable, Image, LongTable, Paragraph, Preformatted,
    PageBreak, SimpleDocTemplate, Spacer, TableStyle,
)


NAVY = colors.HexColor("#17324d")
BLUE = colors.HexColor("#0072b2")
TEAL = colors.HexColor("#006b68")
PALE = colors.HexColor("#eef4fa")


class ArchitectureDiagram(Flowable):
    def __init__(self, width):
        super().__init__()
        self.width = width
        self.height = 215

    def draw(self):
        canvas = self.canv
        gap = 15
        box = (self.width - 2 * gap) / 3
        positions = [(0, 145), (box + gap, 145), (2 * (box + gap), 145),
                     (0, 45), (box + gap, 45), (2 * (box + gap), 45)]
        nodes = [
            ("Independent UI", "React + Nginx", "localhost:3002"),
            ("FastAPI", "Auth / policy / audit", "localhost:8000"),
            ("Model server", "MLflow pyfunc bundle", "private model:5001"),
            ("Terminal worker", "Spark -> train -> evaluate", "fixed DVC commands"),
            ("SQLite volume", "Predictions / feedback", "sessions / pipeline jobs"),
            ("Monitoring", "Prometheus + Grafana", "HTTP / host / reports"),
        ]
        for (x, y), lines in zip(positions, nodes):
            canvas.setFillColor(PALE)
            canvas.setStrokeColor(TEAL)
            canvas.roundRect(x, y, box, 57, 6, fill=1, stroke=1)
            for offset, line in enumerate(lines):
                canvas.setFillColor(NAVY)
                canvas.setFont("Helvetica-Bold" if offset == 0 else "Helvetica", 9 if offset == 0 else 8)
                canvas.drawCentredString(x + box / 2, y + 40 - offset * 14, line)

        def arrow(x1, y1, x2, y2):
            canvas.setStrokeColor(BLUE)
            canvas.setLineWidth(1.2)
            canvas.line(x1, y1, x2, y2)
            angle = math.atan2(y2 - y1, x2 - x1)
            for delta in (-0.55, 0.55):
                canvas.line(x2 - 5 * math.cos(angle + delta),
                            y2 - 5 * math.sin(angle + delta), x2, y2)

        arrow(box, 173, box + gap, 173)
        arrow(2 * box + gap, 173, 2 * (box + gap), 173)
        arrow(box + gap + box / 2, 145, box + gap + box / 2, 102)
        arrow(box, 75, box + gap, 155)
        canvas.setFillColor(NAVY)
        canvas.setFont("Helvetica", 7.5)
        canvas.drawCentredString(self.width / 2, 16, "Git + DVC version code/data/artifacts; optional MLflow tracking records experiments.")


def inline(text):
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = html.escape(text)
    text = re.sub(r"`([^`]+)`", r'<font name="Courier">\1</font>', text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", text)
    return text


def render_pdf(source, destination, title):
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("DocBody", fontName="Helvetica", fontSize=9.5,
                              leading=12.8 if title in ("User Manual", "Test Plan and Results", "Complete Experiment Report") else 13.5,
                              textColor=NAVY, spaceAfter=6 if title in ("User Manual", "Test Plan and Results", "Complete Experiment Report") else 7))
    styles.add(ParagraphStyle("DocTitle", fontName="Helvetica-Bold", fontSize=23,
                              leading=28, textColor=NAVY, spaceAfter=16))
    styles.add(ParagraphStyle("DocHeading", fontName="Helvetica-Bold", fontSize=13,
                              leading=17, textColor=TEAL, spaceBefore=14,
                              spaceAfter=8))
    styles.add(ParagraphStyle("DocSubheading", fontName="Helvetica-Bold", fontSize=10.5,
                              leading=14, textColor=NAVY, spaceBefore=9,
                              spaceAfter=6))
    styles.add(ParagraphStyle("DocCell", fontName="Helvetica", fontSize=7.5,
                              leading=10.5, textColor=NAVY, wordWrap="CJK"))
    styles.add(ParagraphStyle("DocCode", fontName="Courier", fontSize=7.2,
                              leading=10, textColor=NAVY, backColor=PALE,
                              borderPadding=7, spaceBefore=5, spaceAfter=10))
    width = A4[0] - 32 * mm
    story = []
    lines = source.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line in ("[[PAGE_BREAK]]", "<!-- PAGE_BREAK -->"):
            story.append(PageBreak())
            index += 1
            continue
        if line.startswith("```"):
            is_diagram = line == "```mermaid"
            block = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                block.extend(textwrap.wrap(lines[index], width=104,
                                           replace_whitespace=False,
                                           drop_whitespace=False) or [""])
                index += 1
            if is_diagram:
                story.append(ArchitectureDiagram(width))
            else:
                story.append(Preformatted("\n".join(block), styles["DocCode"]))
            index += 1
            continue
        if line == "![AIOpsDesk application and pipeline flow](assets/report-flowchart.png)":
            flowchart_path = destination.parent / "assets/report-flowchart.png"
            image_width, image_height = ImageReader(str(flowchart_path)).getSize()
            flowchart = Image(str(flowchart_path), width=width,
                              height=width * image_height / image_width,
                              hAlign="CENTER")
            story.extend([flowchart, Spacer(1, 8)])
            index += 1
            continue
        if line == "[[ARCHITECTURE_DIAGRAM]]":
            story.append(ArchitectureDiagram(width))
            index += 1
            continue
        if line.startswith("|"):
            rows = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                row = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-+:?", cell.replace(" ", "")) for cell in row):
                    rows.append([Paragraph(inline(cell), styles["DocCell"]) for cell in row])
                index += 1
            n = len(rows[0])
            fractions = {2: [0.29, 0.71], 3: [0.24, 0.30, 0.46],
                         4: [0.34, 0.22, 0.22, 0.22],
                         5: [0.10, 0.34, 0.25, 0.13, 0.18]}.get(n, [1 / n] * n)
            if title == "Complete Experiment Report" and n == 3:
                fractions = [0.19, 0.23, 0.58]
            if title == "Complete Experiment Report" and n == 3 and "validation model" in line:
                fractions = [0.46, 0.27, 0.27]
            if title == "Complete Experiment Report" and n == 5 and "Retained label" in line:
                fractions = [0.28, 0.18, 0.18, 0.18, 0.18]
            if title == "Complete Experiment Report" and n == 5 and "KS distance" in line:
                fractions = [0.30, 0.10, 0.18, 0.18, 0.24]
            if title == "Complete Experiment Report" and n == 5 and "True / predicted" in line:
                fractions = [0.28, 0.18, 0.18, 0.18, 0.18]
            if title == "Complete Experiment Report" and n == 5 and "Fit time" in line:
                fractions = [0.20, 0.10, 0.24, 0.28, 0.18]
            # Metric tables benefit from a wider first column than API tables.
            if n == 5 and "Task / class" in line:
                fractions = [0.36, 0.16, 0.16, 0.16, 0.16]
            grid = LongTable(rows, colWidths=[width * f for f in fractions],
                             repeatRows=1, hAlign="LEFT")
            grid.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#dcebf5")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f6f8fb")]),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.7, BLUE),
                ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#d3dce4")),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4 if title == "Complete Experiment Report" else 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4 if title == "Complete Experiment Report" else 6),
            ]))
            story.append(grid)
            following = next((item.strip() for item in lines[index:] if item.strip()), "")
            if following not in ("[[PAGE_BREAK]]", "<!-- PAGE_BREAK -->"):
                story.append(Spacer(1, 8))
            continue
        if line.startswith("# "):
            story.append(Paragraph(inline(line[2:]), styles["DocTitle"]))
            index += 1
            continue
        if line.startswith("## "):
            story.append(CondPageBreak(70))
            story.append(Paragraph(inline(line[3:]), styles["DocHeading"]))
            index += 1
            continue
        if line.startswith("### "):
            story.append(CondPageBreak(60))
            story.append(Paragraph(inline(line[4:]), styles["DocSubheading"]))
            index += 1
            continue
        if line.startswith("- "):
            story.append(Paragraph(inline(line[2:]), styles["DocBody"], bulletText="-"))
            index += 1
            continue
        if re.match(r"\d+\. ", line):
            story.append(Paragraph(inline(line), styles["DocBody"]))
            index += 1
            continue
        paragraph = [line]
        index += 1
        while index < len(lines) and lines[index].strip() and not re.match(r"^(#|\||```|- |\d+\. )", lines[index].strip()):
            paragraph.append(lines[index].strip())
            index += 1
        story.append(Paragraph(inline(" ".join(paragraph)), styles["DocBody"]))

    def chrome(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(TEAL)
        canvas.line(16 * mm, A4[1] - 13 * mm, A4[0] - 16 * mm, A4[1] - 13 * mm)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(NAVY)
        header = "AIOpsDesk | DA3408" if title == "Complete Experiment Report" else "AIOpsDesk | DA3408 | As-built documentation"
        canvas.drawString(16 * mm, A4[1] - 10 * mm, header)
        canvas.drawString(16 * mm, 10 * mm, title)
        canvas.drawRightString(A4[0] - 16 * mm, 10 * mm, str(doc.page))
        canvas.restoreState()

    document = SimpleDocTemplate(
        str(destination), pagesize=A4, leftMargin=16 * mm,
        rightMargin=16 * mm, topMargin=20 * mm, bottomMargin=18 * mm,
        title=title, author="AIOpsDesk project", pageCompression=1,
    )
    document.build(story, onFirstPage=chrome, onLaterPages=chrome)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument("--out", type=Path)
    parser.add_argument("--report-only", action="store_true",
                        help="Render only root report.md to report.pdf")
    args = parser.parse_args()
    root = args.repo.resolve()
    source = root / "docs"
    out = args.out.resolve() if args.out else source
    titles = {
        "architecture": "Architecture", "hld": "High-Level Design",
        "lld": "Low-Level Design", "test-plan": "Test Plan and Results",
        "user-manual": "User Manual",
    }
    if not args.report_only:
        out.mkdir(parents=True, exist_ok=True)
        for stem, title in titles.items():
            markdown = (source / f"{stem}.md").read_text(encoding="utf-8")
            render_pdf(markdown, out / f"{stem}.pdf", title)
            print(out / f"{stem}.pdf")
    report_source = root / "report.md"
    if report_source.is_file():
        render_pdf(report_source.read_text(encoding="utf-8"),
                   root / "report.pdf", "Complete Experiment Report")
        print(root / "report.pdf")
    elif args.report_only:
        parser.error("report.md is missing")
    print("DOCUMENTATION RENDERED; Markdown and README preserved.")


if __name__ == "__main__":
    main()
