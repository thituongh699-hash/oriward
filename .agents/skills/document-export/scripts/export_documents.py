#!/usr/bin/env python3
"""Bounded, local DOCX/PDF exporter for Oriward generated resumes.

The core accepts a deliberately small JSON document model.  It does not
interpret Markdown or HTML; resume Markdown is accepted only through the
strict parser below after its saved hash and revision status are verified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path


class ExportError(ValueError):
    """Actionable, structured-export failure."""


def _error(code, message):
    raise ExportError(f"{code}: {message}")


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _string(value, label, *, required=False):
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        _error("INVALID_SCHEMA", f"{label} must be a string")
    if required and not value.strip():
        _error("INVALID_SCHEMA", f"{label} must not be blank")
    return value


def _normalise_document(raw):
    if not isinstance(raw, dict):
        _error("INVALID_SCHEMA", "input must be a JSON object")
    unknown = set(raw) - {"title", "subtitle", "sections"}
    if unknown:
        _error("INVALID_SCHEMA", "unknown top-level fields: " + ", ".join(sorted(unknown)))
    sections = raw.get("sections")
    if not isinstance(sections, list) or not sections:
        _error("INVALID_SCHEMA", "sections must be a nonempty array")
    result = {"title": _string(raw.get("title"), "title"),
              "subtitle": _string(raw.get("subtitle"), "subtitle"), "sections": []}
    for number, section in enumerate(sections, 1):
        if not isinstance(section, dict):
            _error("INVALID_SCHEMA", f"sections[{number}] must be an object")
        unknown = set(section) - {"heading", "paragraphs", "bullets", "table"}
        if unknown:
            _error("INVALID_SCHEMA", f"sections[{number}] unknown fields: " + ", ".join(sorted(unknown)))
        item = {"heading": _string(section.get("heading"), f"sections[{number}].heading"),
                "paragraphs": [], "bullets": [], "table": None}
        for key in ("paragraphs", "bullets"):
            values = section.get(key, [])
            if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
                _error("INVALID_SCHEMA", f"sections[{number}].{key} must be an array of strings")
            item[key] = values
        table = section.get("table")
        if table is not None:
            if not isinstance(table, dict) or set(table) != {"headers", "rows"}:
                _error("INVALID_SCHEMA", f"sections[{number}].table requires only headers and rows")
            headers, rows = table["headers"], table["rows"]
            if (not isinstance(headers, list) or not headers or not all(isinstance(v, str) for v in headers)
                    or not isinstance(rows, list)):
                _error("INVALID_SCHEMA", f"sections[{number}].table has invalid headers or rows")
            if any(not isinstance(row, list) or len(row) != len(headers) or not all(isinstance(v, str) for v in row)
                   for row in rows):
                _error("INVALID_SCHEMA", f"sections[{number}].table rows must match headers and contain strings")
            item["table"] = {"headers": headers, "rows": rows}
        if not (item["heading"] or item["paragraphs"] or item["bullets"] or item["table"]):
            _error("INVALID_SCHEMA", f"sections[{number}] must contain text or a table")
        result["sections"].append(item)
    if not (result["title"] or result["subtitle"] or any(
            s["heading"] or s["paragraphs"] or s["bullets"] or s["table"] for s in result["sections"])):
        _error("INVALID_SCHEMA", "document has no exportable text")
    return result


_RESUME_HEADINGS = ("个人简介", "相关经历", "教育经历", "实习经历", "工作经历", "项目经历", "自我评价")


def _looks_like_resume(document):
    """A resume must come from a registered resume ID, not a hand-written JSON."""
    headings = {section["heading"].strip() for section in document["sections"]}
    return any(heading in _RESUME_HEADINGS for heading in headings)


def _all_text(document):
    values = [document["title"], document["subtitle"]]
    for section in document["sections"]:
        values.append(section["heading"])
        values.extend(section["paragraphs"])
        values.extend(section["bullets"])
        if section["table"]:
            values.extend(section["table"]["headers"])
            for row in section["table"]["rows"]:
                values.extend(row)
    return values


def _sfnt_offset(data):
    offset = 0
    if data[:4] == b"ttcf":
        if len(data) < 16:
            _error("INVALID_FONT", "TTC file is truncated")
        count = struct.unpack_from(">I", data, 8)[0]
        if not count:
            _error("INVALID_FONT", "TTC contains no fonts")
        offset = struct.unpack_from(">I", data, 12)[0]
    if offset + 12 > len(data):
        _error("INVALID_FONT", "font has no valid sfnt header")
    return offset


def _table_offset(data, offset, tag):
    tables = struct.unpack_from(">H", data, offset + 4)[0]
    for index in range(tables):
        pos = offset + 12 + index * 16
        if pos + 16 > len(data):
            _error("INVALID_FONT", "font table directory is truncated")
        if data[pos:pos + 4] == tag:
            return struct.unpack_from(">I", data, pos + 8)[0]
    return None


def _cmap(path):
    """Return supported Unicode codepoints using only the TTF/TTC cmap table."""
    data = Path(path).read_bytes()
    offset = _sfnt_offset(data)
    cmap_offset = _table_offset(data, offset, b"cmap")
    if cmap_offset is None or cmap_offset + 4 > len(data):
        _error("INVALID_FONT", "font has no cmap table")
    count = struct.unpack_from(">H", data, cmap_offset + 2)[0]
    records = []
    for index in range(count):
        pos = cmap_offset + 4 + index * 8
        if pos + 8 > len(data):
            _error("INVALID_FONT", "cmap record is truncated")
        platform, encoding, sub = struct.unpack_from(">HHI", data, pos)
        absolute = cmap_offset + sub
        if absolute + 2 <= len(data):
            fmt = struct.unpack_from(">H", data, absolute)[0]
            records.append((fmt, platform, encoding, absolute))
    records.sort(key=lambda value: (value[0] == 12, value[1] == 3, value[2] in (1, 10)), reverse=True)
    supported = set()
    for fmt, _, _, pos in records:
        if fmt == 12 and pos + 16 <= len(data):
            groups = struct.unpack_from(">I", data, pos + 12)[0]
            for index in range(groups):
                start = pos + 16 + index * 12
                if start + 12 > len(data):
                    _error("INVALID_FONT", "cmap format 12 is truncated")
                first, last, _ = struct.unpack_from(">III", data, start)
                supported.update(range(first, last + 1))
        elif fmt == 4 and pos + 14 <= len(data):
            length, segments = struct.unpack_from(">HH", data, pos + 2)[0], struct.unpack_from(">H", data, pos + 6)[0] // 2
            if pos + length > len(data):
                _error("INVALID_FONT", "cmap format 4 is truncated")
            end_pos, start_pos, delta_pos, range_pos = pos + 14, pos + 16 + segments * 2, pos + 16 + segments * 4, pos + 16 + segments * 6
            for index in range(segments):
                end, start = struct.unpack_from(">HH", data, end_pos + index * 2)[0], struct.unpack_from(">HH", data, start_pos + index * 2)[0]
                delta, range_offset = struct.unpack_from(">hH", data, delta_pos + index * 2)[0], struct.unpack_from(">H", data, range_pos + index * 2)[0]
                if start > end or start == 0xFFFF:
                    continue
                if range_offset == 0:
                    supported.update(code for code in range(start, end + 1) if (code + delta) & 0xFFFF)
                else:
                    for code in range(start, end + 1):
                        glyph_pos = range_pos + index * 2 + range_offset + (code - start) * 2
                        if glyph_pos + 2 <= pos + length and struct.unpack_from(">H", data, glyph_pos)[0]:
                            supported.add(code)
    if not supported:
        _error("INVALID_FONT", "font cmap contains no usable Unicode coverage")
    return supported


def _font_family(path):
    """Read name ID 1 from an sfnt name table for DOCX's actual family name."""
    data = Path(path).read_bytes()
    table = _table_offset(data, _sfnt_offset(data), b"name")
    if table is None or table + 6 > len(data):
        _error("INVALID_FONT", "font has no readable name table")
    count, storage = struct.unpack_from(">HH", data, table + 2)
    matches = []
    for index in range(count):
        pos = table + 6 + index * 12
        if pos + 12 > len(data):
            _error("INVALID_FONT", "font name table is truncated")
        platform, encoding, language, name_id, length, relative = struct.unpack_from(">HHHHHH", data, pos)
        start = table + storage + relative
        if name_id != 1 or start + length > len(data):
            continue
        try:
            value = data[start:start + length].decode("utf-16-be" if platform in (0, 3) else "mac_roman").strip()
        except UnicodeDecodeError:
            continue
        if value:
            priority = 0 if (platform, language) == (3, 0x0409) else 1 if platform == 3 else 2
            matches.append((priority, value))
    if not matches:
        _error("INVALID_FONT", "font has no readable family name")
    return sorted(matches)[0][1]


def _vera_path():
    try:
        import reportlab  # optional, only consulted when PDF is requested
        candidate = Path(reportlab.__file__).resolve().parent / "fonts" / "Vera.ttf"
        return candidate if candidate.is_file() else None
    except ImportError:
        return None


def _font_candidates():
    candidates = [_vera_path()]
    roots = [Path(os.environ.get("WINDIR", r"C:\\Windows")) / "Fonts", Path("/Library/Fonts"),
             Path("/System/Library/Fonts"), Path("/System/Library/Fonts/Supplemental"),
             Path("/usr/share/fonts/truetype/dejavu"), Path("/usr/share/fonts/truetype/noto"),
             Path("/usr/share/fonts/opentype/noto"), Path("/usr/local/share/fonts"),
             Path.home() / ".local" / "share" / "fonts", Path.home() / ".fonts"]
    names = ("msyh.ttc", "msyh.ttf", "simhei.ttf", "simsun.ttc", "NotoSansCJK-Regular.ttc",
             "NotoSansCJKsc-Regular.ttc", "DejaVuSans.ttf")
    for root in roots:
        for name in names:
            path = root / name
            if path.is_file():
                candidates.append(path)
    return [path for path in candidates if path]


def _reportlab_embeddable(path):
    try:
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError as exc:
        _error("MISSING_DEPENDENCY", "PDF export needs reportlab: " + str(exc))
    try:
        TTFont("OriwardExportProbe", str(path), subfontIndex=0)
        return True
    except Exception as exc:
        return str(exc)


def _choose_font(text, supplied, *, require_pdf=False):
    candidates = [Path(supplied).expanduser()] if supplied else _font_candidates()
    wanted = {ord(character) for value in text for character in value if not character.isspace()}
    failures = []
    for path in candidates:
        if not path.is_file() or path.suffix.lower() not in {".ttf", ".ttc"}:
            failures.append(f"{path}: missing or unsupported extension")
            continue
        try:
            missing = sorted(wanted - _cmap(path))
        except ExportError as exc:
            failures.append(str(exc))
            continue
        if not missing:
            if require_pdf:
                embeddable = _reportlab_embeddable(path)
                if embeddable is not True:
                    failures.append(f"{path}: ReportLab cannot embed it ({embeddable})")
                    continue
            return path
        failures.append(f"{path}: missing " + " ".join(f"U+{code:04X}" for code in missing[:8]))
    hint = "Provide --font with an embeddable TTF/TTC covering every character." if supplied else "Provide --font with an embeddable CJK-capable TTF/TTC."
    _error("FONT_COVERAGE", hint + " " + "; ".join(failures[:3]))


def _write_docx(document, stream, font_path, font_family):
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml import OxmlElement
        from docx.oxml.ns import qn
        from docx.shared import Cm, Pt, RGBColor
    except ImportError as exc:
        _error("MISSING_DEPENDENCY", "DOCX export needs python-docx: " + str(exc))
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin = section.bottom_margin = Cm(1.7)
    section.left_margin = section.right_margin = Cm(1.8)
    font_name = font_family
    for style_name in ("Normal", "Title", "Subtitle", "Heading 1", "List Bullet"):
        style = doc.styles[style_name]
        style.font.name, style.font.color.rgb = font_name, RGBColor(0, 0, 0)
        style._element.rPr.rFonts.set(qn("w:eastAsia"), font_name)
    doc.styles["Normal"].font.size = Pt(10.5)
    doc.styles["Title"].font.size, doc.styles["Heading 1"].font.size = Pt(18), Pt(13)
    doc.styles["Heading 1"].paragraph_format.keep_with_next = True
    if document["title"]:
        doc.add_paragraph(document["title"], style="Title").alignment = WD_ALIGN_PARAGRAPH.LEFT
    if document["subtitle"]:
        doc.add_paragraph(document["subtitle"], style="Subtitle")
    for section_data in document["sections"]:
        if section_data["heading"]:
            doc.add_paragraph(section_data["heading"], style="Heading 1")
        for paragraph in section_data["paragraphs"]:
            doc.add_paragraph(paragraph)
        for bullet in section_data["bullets"]:
            doc.add_paragraph(bullet, style="List Bullet")
        table_data = section_data["table"]
        if table_data:
            table = doc.add_table(rows=1, cols=len(table_data["headers"]))
            table.style, table.autofit = "Table Grid", True
            borders = OxmlElement("w:tblBorders")
            for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
                border = OxmlElement(f"w:{edge}")
                border.set(qn("w:val"), "single")
                border.set(qn("w:sz"), "4")
                border.set(qn("w:color"), "D9D9D9")
                borders.append(border)
            table._tbl.tblPr.append(borders)
            for cell, value in zip(table.rows[0].cells, table_data["headers"]):
                cell.text = value
            for row in table_data["rows"]:
                cells = table.add_row().cells
                for cell, value in zip(cells, row):
                    cell.text = value
    doc.save(stream)


def _write_pdf(document, stream, font_path):
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import cm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import CondPageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
        from xml.sax.saxutils import escape
    except ImportError as exc:
        _error("MISSING_DEPENDENCY", "PDF export needs reportlab: " + str(exc))
    # ReportLab keeps registered fonts globally.  Tie the name to bytes rather
    # than reusing a stale English face for a later CJK export in this process.
    face = "OriwardExport_" + _digest(font_path)[:12]
    try:
        pdfmetrics.registerFont(TTFont(face, str(font_path), subfontIndex=0))
    except Exception as exc:
        _error("INVALID_FONT", f"ReportLab cannot embed {font_path}: {exc}")
    styles = getSampleStyleSheet()
    normal = ParagraphStyle("ExportNormal", parent=styles["Normal"], fontName=face, fontSize=10.5,
                            leading=15, textColor=colors.black, wordWrap="CJK", alignment=TA_LEFT)
    title = ParagraphStyle("ExportTitle", parent=normal, fontSize=18, leading=24, spaceAfter=7)
    subtitle = ParagraphStyle("ExportSubtitle", parent=normal, fontSize=11, leading=15, spaceAfter=10)
    heading = ParagraphStyle("ExportHeading", parent=normal, fontSize=13, leading=18, spaceBefore=10,
                             spaceAfter=4, keepWithNext=True)
    table_heading = ParagraphStyle("ExportTableHeading", parent=heading, keepWithNext=False)
    bullet = ParagraphStyle("ExportBullet", parent=normal, leftIndent=14, firstLineIndent=-9, spaceAfter=2)
    def paragraph(value, style=normal):
        return Paragraph(escape(value).replace("\n", "<br/>"), style)
    story = []
    if document["title"]:
        story.append(paragraph(document["title"], title))
    if document["subtitle"]:
        story.append(paragraph(document["subtitle"], subtitle))
    for section_data in document["sections"]:
        table_data = section_data["table"]
        table_only = table_data and not section_data["paragraphs"] and not section_data["bullets"]
        if section_data["heading"]:
            if table_only:
                # A splittable Table cannot safely be the target of
                # keepWithNext: ReportLab then moves the whole table to the
                # next page.  Reserve enough room for its heading, header and
                # roughly two ordinary rows; otherwise start a fresh page.
                story.append(CondPageBreak(64))
                story.append(paragraph(section_data["heading"], table_heading))
            else:
                story.append(paragraph(section_data["heading"], heading))
        story.extend(paragraph(value) for value in section_data["paragraphs"])
        story.extend(Paragraph("• " + escape(value).replace("\n", "<br/>"), bullet) for value in section_data["bullets"])
        if table_data:
            rows = [[paragraph(value) for value in table_data["headers"]]]
            rows.extend([paragraph(value) for value in row] for row in table_data["rows"])
            table = Table(rows, repeatRows=1, hAlign="LEFT")
            table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D9D9D9")),
                                       ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                                       ("VALIGN", (0, 0), (-1, -1), "TOP"),
                                       ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                                       ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
            story.append(table)
        story.append(Spacer(1, 4))
    SimpleDocTemplate(stream, pagesize=A4, leftMargin=1.8 * cm, rightMargin=1.8 * cm,
                      topMargin=1.7 * cm, bottomMargin=1.7 * cm).build(story)


def _parse_resume_markdown(content):
    """Parse only Oriward's generated resume grammar; reject every other Markdown."""
    lines = content.replace("\r\n", "\n").split("\n")
    if not lines or not lines[0].startswith("# ") or not lines[0][2:].strip():
        _error("UNSUPPORTED_RESUME", "saved resume must begin with a generated '# Name' line")
    result = {"title": lines[0][2:], "subtitle": "", "sections": []}
    footer = []
    current = None
    index = 1
    while index < len(lines):
        value = lines[index]
        index += 1
        if not value:
            continue
        if value == "---":
            footer = [line for line in lines[index:] if line]
            if (len(footer) != 2 or not footer[0].startswith("*来源记录：") or not footer[0].endswith("*")
                    or not footer[1].startswith("*发布/投递前请人工核对内容；") or not footer[1].endswith("*")):
                _error("UNSUPPORTED_RESUME", "only Oriward generated source-record footer may follow '---'")
            break
        if value.startswith("## ") and value[3:].strip():
            current = {"heading": value[3:], "paragraphs": [], "bullets": [], "table": None}
            result["sections"].append(current)
        elif value.startswith("### ") and value[4:].strip() and current is not None:
            # Keep each experience adjacent to its own bullets.  A flattened
            # parent section would make all experience names precede all
            # bullets in both output formats, changing claim ownership.
            current = {"heading": value[4:], "paragraphs": [], "bullets": [], "table": None}
            result["sections"].append(current)
        elif value.startswith("- ") and value[2:].strip() and current is not None:
            current["bullets"].append(value[2:])
        elif value.startswith("*") and value.endswith("*") and len(value) > 2:
            target = current["paragraphs"] if current else None
            if target is None and not result["subtitle"]:
                result["subtitle"] = value[1:-1]
            elif target is not None:
                target.append(value[1:-1])
            else:
                _error("UNSUPPORTED_RESUME", "unexpected generated emphasis line")
        elif current is None and not result["subtitle"]:
            result["subtitle"] = value
        elif current is not None and not value.startswith(("#", "-", "*")):
            current["paragraphs"].append(value)
        else:
            _error("UNSUPPORTED_RESUME", f"unsupported Markdown line: {value[:60]}")
    if not result["sections"] or not footer:
        _error("UNSUPPORTED_RESUME", "resume is missing generated sections or source-record footer")
    return _normalise_document(result), footer


def _load_resume(resume_id):
    root = Path(__file__).resolve().parents[4]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from oriward import feedback, services
    from oriward.db import connect
    try:
        rid = int(resume_id)
    except (TypeError, ValueError):
        _error("INVALID_RESUME_ID", "resume-id must be an integer")
    with connect() as db:
        feedback.ensure_schema(db)
        row = db.execute("SELECT * FROM resumes WHERE id=?", (rid,)).fetchone()
        if row is None:
            _error("RESUME_NOT_FOUND", f"resume {rid} does not exist")
        resume = dict(row)
        from oriward.experience_library import resume_validity
        validity = resume_validity(db, resume)
        if validity["needs_review"]:
            _error("STALE_RESUME", "experience sources changed or were excluded; rebuild/review before export")
        path = services.resume_path(resume)
        if not path.is_file():
            _error("RESUME_NOT_FOUND", f"resume {rid} has no file at {path}")
        revision = db.execute("SELECT factual_status FROM resume_versions WHERE resume_id=?", (rid,)).fetchone()
        if revision is not None and revision["factual_status"] != "approved":
            _error("UNAPPROVED_REVISION", "resume revision requires direct factual confirmation before export")
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        _error("RESUME_NOT_FOUND", f"cannot read resume {rid}: {exc}")
    except UnicodeDecodeError as exc:
        _error("UNSUPPORTED_RESUME", f"saved resume is not UTF-8 Markdown: {exc}")
    document, footer = _parse_resume_markdown(content)
    return document, {"resume_id": rid, "job_id": resume["job_id"], "omitted_internal_footer": footer}


def probe():
    availability = {}
    for name in ("docx", "reportlab", "pypdf"):
        try:
            __import__(name)
            availability[name] = True
        except ImportError:
            availability[name] = False
    return {"status": "OK", "dependencies": availability, "network": False, "writes": False}


def export_document(*, document=None, resume_id=None, output_dir, formats=("docx", "pdf"), font=None):
    """Export one normalised document into a brand-new directory and return its manifest."""
    if (document is None) == (resume_id is None):
        _error("INVALID_ARGUMENTS", "provide exactly one of document or resume_id")
    if isinstance(formats, str):
        formats = tuple(part.strip().lower() for part in formats.split(",") if part.strip())
    formats = tuple(formats)
    if not formats or set(formats) - {"docx", "pdf"} or len(set(formats)) != len(formats):
        _error("INVALID_ARGUMENTS", "formats must be a unique subset of docx,pdf")
    if resume_id is not None:
        normalized, source = _load_resume(resume_id)
    else:
        normalized = _normalise_document(document)
        if _looks_like_resume(normalized):
            _error("RESUME_REQUIRES_ID",
                   "a resume must be exported from its registered resume ID; structured input is for "
                   "plans, notes and reports")
        source = {"input": "structured"}
    output = Path(output_dir).expanduser()
    if output.exists():
        _error("OUTPUT_COLLISION", f"output directory already exists: {output}")
    if not output.parent.is_dir():
        _error("INVALID_OUTPUT", f"parent directory does not exist: {output.parent}")
    chosen_font = _choose_font(_all_text(normalized), font, require_pdf="pdf" in formats)
    family = _font_family(chosen_font)
    created = []
    owns_output_dir = False
    try:
        try:
            output.mkdir()
            owns_output_dir = True
        except FileExistsError:
            _error("OUTPUT_COLLISION", f"output directory was created concurrently: {output}")
        if "docx" in formats:
            target = output / "document.docx"
            try:
                with target.open("xb") as stream:
                    created.append(target)
                    _write_docx(normalized, stream, chosen_font, family)
            except FileExistsError:
                _error("OUTPUT_COLLISION", f"output file already exists: {target}")
        if "pdf" in formats:
            target = output / "document.pdf"
            try:
                with target.open("xb") as stream:
                    created.append(target)
                    _write_pdf(normalized, stream, chosen_font)
            except FileExistsError:
                _error("OUTPUT_COLLISION", f"output file already exists: {target}")
        manifest = {"status": "GENERATED_PENDING_VISUAL_REVIEW",
                    "exported_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "source": source, "formats": list(formats),
                    "font": {"family": family, "pdf_embedded": "pdf" in formats, "docx_embedded": False},
                    "files": {path.name: {"bytes": path.stat().st_size} for path in created},
                    "layout_note": "DOCX and PDF were independently laid out from the same normalized content; visual review remains required."}
        manifest_path = output / "manifest.json"
        try:
            with manifest_path.open("x", encoding="utf-8", newline="\n") as stream:
                created.append(manifest_path)
                json.dump(manifest, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
        except FileExistsError:
            _error("OUTPUT_COLLISION", f"manifest already exists: {manifest_path}")
        return manifest
    except Exception:
        for path in reversed(created):
            path.unlink(missing_ok=True)
        if owns_output_dir and output.exists():
            try:
                output.rmdir()
            except OSError:
                pass
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description="Bounded Oriward document exporter")
    parser.add_argument("--input", type=Path)
    parser.add_argument("--resume-id")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--formats", default="docx,pdf")
    parser.add_argument("--font")
    parser.add_argument("--probe", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.probe:
            if any((args.input, args.resume_id, args.output_dir, args.font)) or args.formats != "docx,pdf":
                _error("INVALID_ARGUMENTS", "--probe cannot be combined with export options")
            result = probe()
        else:
            if args.output_dir is None:
                _error("INVALID_ARGUMENTS", "--output-dir is required")
            if bool(args.input) == bool(args.resume_id):
                _error("INVALID_ARGUMENTS", "provide exactly one of --input or --resume-id")
            document = None
            if args.input:
                try:
                    document = json.loads(args.input.read_text(encoding="utf-8-sig"))
                except (OSError, json.JSONDecodeError) as exc:
                    _error("INVALID_INPUT", f"cannot read JSON input: {exc}")
            result = export_document(document=document, resume_id=args.resume_id, output_dir=args.output_dir,
                                     formats=args.formats, font=args.font)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except ExportError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({"error": f"EXPORT_FAILED: {exc}"}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
