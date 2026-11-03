#--------------------#
# test_report_builder.py
# tests for the pdf report and its plot snapshots
#--------------------#
import numpy as np
import pytest

from core.log_parser import SignalSummary
from core.report_builder import ReportBuilder

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication  # noqa: E402

from core.plot_engine import render_static_snapshot  # noqa: E402

# the snapshot is drawn with pyqtgraph, which needs a qt app
_qt_app = QApplication.instance() or QApplication([])


def test_report_builder_produces_a_real_pdf(tmp_path):
    timestamps = np.linspace(0, 10, 100)
    values = np.sin(timestamps)
    png_path = render_static_snapshot("TestSignal", timestamps, values, tmp_path / "TestSignal.png")
    assert png_path.exists()

    summary = SignalSummary(
        name="TestSignal", maximum=float(values.max()),
        minimum=float(values.min()), average=float(values.mean()),
    )
    builder = ReportBuilder("test_session")
    out_pdf = tmp_path / "report.pdf"
    builder.build(out_pdf, {"TestSignal": (summary, png_path)})

    assert out_pdf.exists()
    assert out_pdf.stat().st_size > 500  # a real rendered pdf, not an empty stub
    assert out_pdf.read_bytes()[:4] == b"%PDF"


# forced-decode enums leave nan gaps, the snapshot must still render at full size
def test_snapshot_handles_nan_gaps_and_is_full_size(tmp_path):
    from PySide6.QtGui import QImage

    timestamps = np.linspace(0, 10, 5000)
    values = np.sin(timestamps)
    values[1000:1500] = np.nan
    png_path = render_static_snapshot("Gappy", timestamps, values, tmp_path / "gappy.png")

    image = QImage(str(png_path))
    assert (image.width(), image.height()) == (1200, 600)
