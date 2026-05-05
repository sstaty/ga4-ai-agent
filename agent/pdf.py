import base64
import io
import json
import re
from datetime import datetime
from pathlib import Path

import markdown as md
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from jinja2 import Environment, FileSystemLoader

from agent.models import AgentResponse

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"

_DATE_KEYWORDS = {"date", "day", "week", "month", "year", "time", "period", "hour"}


def strip_markdown_tables(text: str) -> str:
    # Remove tables followed by a blank line
    text = re.sub(r'\|.+\|[\s\S]*?\n\n', '\n', text)
    # Remove tables at end of string (no trailing blank line)
    text = re.sub(r'\n\|.+\|[\s\S]*$', '', text)
    return text.strip()


def _human_name(name: str) -> str:
    """camelCase / snake_case column name → readable title."""
    s = re.sub(r'([A-Z])', r' \1', name).replace('_', ' ').strip()
    return s.title()


def _dataset_title(headers: list[str]) -> str:
    if not headers:
        return "Data"
    dim = _human_name(headers[0])
    metrics = ", ".join(_human_name(h) for h in headers[1:])
    return f"{metrics} by {dim}" if metrics else dim


def _parse_rows(output) -> list[dict] | None:
    if isinstance(output, str):
        try:
            output = json.loads(output)
        except (json.JSONDecodeError, TypeError):
            return None

    if isinstance(output, list) and output and all(isinstance(r, dict) for r in output):
        return output

    # GA4 RunReport nested format
    if isinstance(output, dict) and "rows" in output:
        dim_names = [h.get("name", f"dim{i}") for i, h in enumerate(output.get("dimension_headers", []))]
        met_names = [h.get("name", f"met{i}") for i, h in enumerate(output.get("metric_headers", []))]
        rows = []
        for row in output.get("rows", []):
            flat: dict = {}
            for i, dv in enumerate(row.get("dimension_values", [])):
                if i < len(dim_names):
                    flat[dim_names[i]] = dv.get("value", "")
            for i, mv in enumerate(row.get("metric_values", [])):
                if i < len(met_names):
                    flat[met_names[i]] = mv.get("value", "")
            if flat:
                rows.append(flat)
        return rows or None

    return None


def _format_rows(rows: list[dict]) -> list[dict]:
    """Reformat YYYYMMDD date strings to YYYY-MM-DD in date-like columns."""
    if not rows:
        return rows
    date_cols = {k for k in rows[0] if any(kw in k.lower() for kw in _DATE_KEYWORDS)}
    result = []
    for row in rows:
        new_row = {}
        for k, v in row.items():
            if k in date_cols and isinstance(v, str) and re.match(r'^\d{8}$', v):
                new_row[k] = f"{v[:4]}-{v[4:6]}-{v[6:]}"
            else:
                new_row[k] = v
        result.append(new_row)
    return result


def _chart_type(rows: list[dict]) -> str:
    keys = list(rows[0].keys())
    first_col = keys[0].lower()
    if any(kw in first_col for kw in _DATE_KEYWORDS):
        return "line"
    if len(keys) == 2 and len(rows) <= 6:
        return "pie"
    return "bar"


def _chart_b64(rows: list[dict], chart_type: str, title: str = "") -> str:
    keys = list(rows[0].keys())
    label_col = keys[0]
    value_cols = keys[1:]
    if not value_cols:
        return ""

    fig, ax = plt.subplots(figsize=(8, 4))
    labels = [str(r.get(label_col, "")) for r in rows]

    def _val(r: dict, col: str) -> float:
        try:
            return float(r.get(col) or 0)
        except (ValueError, TypeError):
            return 0.0

    if chart_type == "line":
        for col in value_cols:
            ax.plot(labels, [_val(r, col) for r in rows], marker="o", label=col)
        if len(value_cols) > 1:
            ax.legend()
        plt.xticks(rotation=45, ha="right")
    elif chart_type == "pie":
        values = [_val(r, value_cols[0]) for r in rows]
        ax.pie(values, labels=labels, autopct="%1.1f%%")
    else:
        x = range(len(rows))
        bar_width = 0.8 / max(len(value_cols), 1)
        for i, col in enumerate(value_cols):
            offsets = [xi + i * bar_width for xi in x]
            ax.bar(offsets, [_val(r, col) for r in rows], width=bar_width, label=col)
        ax.set_xticks([xi + bar_width * (len(value_cols) - 1) / 2 for xi in x])
        ax.set_xticklabels(labels, rotation=45, ha="right")
        if len(value_cols) > 1:
            ax.legend()

    ax.set_title(title)
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100)
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


def _md_to_rl(text: str) -> str:
    """Convert basic markdown to ReportLab XML markup."""
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"\*(.+?)\*", r"<i>\1</i>", text)
    text = text.replace("\n", "<br/>")
    return text


def _reportlab_pdf(query: str, answer: str, datasets: list[dict]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    heading = ParagraphStyle("Heading", parent=styles["Heading1"], spaceAfter=6)
    small = ParagraphStyle("Small", parent=styles["Normal"], fontSize=9)
    italic = ParagraphStyle("Italic", parent=styles["Normal"], fontSize=10,
                            textColor=colors.HexColor("#555555"))

    story = [
        Paragraph("GA4 Analytics Report", heading),
        Paragraph(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", small),
        Spacer(1, 0.4*cm),
        Paragraph("Question", heading),
        Paragraph(f"<i>{query}</i>", italic),
        Spacer(1, 0.4*cm),
        Paragraph("Answer", heading),
        Paragraph(_md_to_rl(strip_markdown_tables(answer)), small),
        Spacer(1, 0.5*cm),
    ]

    for ds in datasets:
        story.append(Paragraph(ds["title"], heading))
        headers = ds["headers"]
        table_data = [headers] + [[str(row.get(h, "")) for h in headers] for row in ds["rows"]]
        col_width = (A4[0] - 4*cm) / max(len(headers), 1)
        tbl = Table(table_data, colWidths=[col_width] * len(headers))
        tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a73e8")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#dee2e6")),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("PADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 0.3*cm))

        if ds.get("chart_b64"):
            img_data = base64.b64decode(ds["chart_b64"])
            img_buf = io.BytesIO(img_data)
            img = Image(img_buf, width=16*cm, height=8*cm)
            story.append(img)
            story.append(Spacer(1, 0.5*cm))

    doc.build(story)
    return buf.getvalue()


def generate_pdf(response: AgentResponse, query: str = "") -> bytes:
    datasets = []
    for tc in response.tool_calls:
        if tc.name == "run_report" and tc.output:
            rows = _parse_rows(tc.output)
            if rows:
                rows = _format_rows(rows)
                ct = _chart_type(rows)
                title = _dataset_title(list(rows[0].keys()))
                datasets.append({
                    "rows": rows,
                    "headers": list(rows[0].keys()),
                    "chart_b64": _chart_b64(rows, ct, title),
                    "title": title,
                })

    answer_clean = strip_markdown_tables(response.answer)
    answer_html = md.markdown(answer_clean)

    try:
        from weasyprint import HTML
        env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
        html = env.get_template("report.html").render(
            query=query,
            answer_html=answer_html,
            datasets=datasets,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        )
        return HTML(string=html).write_pdf()
    except Exception:
        return _reportlab_pdf(query, response.answer, datasets)
