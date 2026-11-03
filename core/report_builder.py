#--------------------#
# report_builder.py
# builds the pdf report (summary table plus one plot per signal) with reportlab
#--------------------#
from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors as rl_colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import (
    Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

from core.log_parser import SignalSummary


class ReportBuilder:
    def __init__(self, session_name: str):
        self.session_name = session_name
        self.styles = getSampleStyleSheet()

    # selected maps signal name to (summary, path to its snapshot png)
    def build(self, out_pdf: Path, selected: dict[str, tuple[SignalSummary, Path]]) -> Path:
        doc = SimpleDocTemplate(str(out_pdf), pagesize=letter)
        story = [
            Paragraph(f"CAN Decoder Report -- {self.session_name}", self.styles["Title"]),
            Spacer(1, 12),
            self._summary_table(selected),
            Spacer(1, 18),
        ]
        for name, (_, png_path) in selected.items():
            story.append(Paragraph(name, self.styles["Heading3"]))
            story.append(Image(str(png_path), width=450, height=225))
            story.append(Spacer(1, 12))
        doc.build(story)
        return out_pdf

    def _summary_table(self, selected: dict[str, tuple[SignalSummary, Path]]) -> Table:
        data = [["Signal", "Max", "Min", "Avg"]]
        for name, (summary, _) in selected.items():
            data.append([
                name, f"{summary.maximum:.2f}", f"{summary.minimum:.2f}", f"{summary.average:.2f}",
            ])
        table = Table(data, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), rl_colors.HexColor("#333333")),
            ("TEXTCOLOR", (0, 0), (-1, 0), rl_colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, rl_colors.grey),
        ]))
        return table
