"""
render_playbook.py — Render the weekly plays from this-weeks-picks.json.

Separates selection (weekly_selector.py) from rendering so they can be tested
independently and so the same picks could be rendered to multiple formats later.
"""
import json, os
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.platypus import (Paragraph, Spacer, Table, TableStyle,
                                Frame, PageTemplate, BaseDocTemplate, KeepTogether)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

pdfmetrics.registerFont(TTFont('Lora', '/usr/share/fonts/truetype/google-fonts/Lora-Variable.ttf'))
pdfmetrics.registerFont(TTFont('Lora-Italic', '/usr/share/fonts/truetype/google-fonts/Lora-Italic-Variable.ttf'))

IVORY = colors.HexColor('#F7F1E8')
INK = colors.HexColor('#1A1A1A')
INK_SOFT = colors.HexColor('#3C3C3A')
INK_MUTED = colors.HexColor('#6B6A65')
GOLD = colors.HexColor('#A88D4A')
GOLD_DARK = colors.HexColor('#8F7336')
RED_SIG = colors.HexColor('#8C3B36')

S = {
    'wordmark': ParagraphStyle('wm', fontName='Lora', fontSize=8, textColor=GOLD_DARK),
    'title':    ParagraphStyle('tt', fontName='Lora', fontSize=22, leading=26, textColor=INK, spaceAfter=2),
    'subtitle': ParagraphStyle('st', fontName='Lora-Italic', fontSize=9.5, leading=12, textColor=INK_MUTED, spaceAfter=4),
    'section_badge': ParagraphStyle('sb', fontName='Lora', fontSize=10, textColor=colors.white, leading=12),
    'num_addr': ParagraphStyle('na', fontName='Lora', fontSize=10.5, leading=13, textColor=INK, spaceAfter=1),
    'value_inline': ParagraphStyle('vi', fontName='Lora-Italic', fontSize=9.5, textColor=GOLD_DARK, alignment=TA_RIGHT),
    'happening': ParagraphStyle('h', fontName='Lora', fontSize=9, leading=11.5, textColor=INK_SOFT, spaceAfter=0),
    'why':       ParagraphStyle('w', fontName='Lora-Italic', fontSize=9, leading=11.5, textColor=INK_MUTED, spaceAfter=0),
    'action':    ParagraphStyle('a', fontName='Lora', fontSize=9, leading=11.5, textColor=GOLD_DARK, spaceAfter=4),
}

ZIP_TO_CITY = {'98004': 'Bellevue', '98039': 'Medina', '98040': 'Mercer Island',
               '98033': 'Kirkland', '98006': 'Newport', '98005': 'Bridle Trails'}


def on_page(week_of_str):
    def _draw(canv, doc):
        canv.saveState()
        canv.setFillColor(IVORY)
        canv.rect(0, 0, letter[0], letter[1], fill=1, stroke=0)
        canv.setStrokeColor(GOLD); canv.setLineWidth(0.4)
        canv.line(0.55*inch, letter[1] - 0.4*inch, letter[0] - 0.55*inch, letter[1] - 0.4*inch)
        canv.setFillColor(GOLD_DARK); canv.setFont('Lora', 7.5)
        canv.drawString(0.55*inch, letter[1] - 0.3*inch, 'SELLERSIGNAL  ·  OPERATOR PLAYBOOK')
        canv.drawRightString(letter[0] - 0.55*inch, letter[1] - 0.3*inch, week_of_str.upper())
        canv.setStrokeColor(GOLD); canv.setLineWidth(0.4)
        canv.line(0.55*inch, 0.4*inch, letter[0] - 0.55*inch, 0.4*inch)
        canv.restoreState()
    return _draw


def section_bar(text, color):
    t = Table([[Paragraph(text, S['section_badge'])]], colWidths=[6.9*inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), color),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('TOPPADDING', (0,0), (-1,-1), 4), ('BOTTOMPADDING', (0,0), (-1,-1), 4),
    ]))
    return t


def format_value(v):
    if not v: return '—'
    if v >= 100_000_000: return f"~${v/1_000_000:.1f}M"
    if v >= 10_000_000:  return f"~${v/1_000_000:.1f}M"
    return f"~${v/1_000_000:.1f}M"


def move(num, pick):
    addr = pick.get('address', '—')
    city = ZIP_TO_CITY.get(pick.get('zip'), '')
    value_str = format_value(pick.get('value'))
    c = pick['copy']

    header = Table([[
        Paragraph(f"<b>{num}.  {addr}  ·  {city}</b>", S['num_addr']),
        Paragraph(value_str, S['value_inline']),
    ]], colWidths=[5.0*inch, 1.9*inch])
    header.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'BOTTOM'),
        ('LEFTPADDING', (0,0), (-1,-1), 0), ('RIGHTPADDING', (0,0), (-1,-1), 0),
        ('TOPPADDING', (0,0), (-1,-1), 0), ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]))
    return KeepTogether([
        header,
        Paragraph(c['happening'], S['happening']),
        Paragraph(c['why'], S['why']),
        Paragraph(f'→ &nbsp; {c["action"]}', S['action']),
    ])


def render(picks_path, out_path):
    picks = json.load(open(picks_path))
    week_of = datetime.strptime(picks['week_of'], '%Y-%m-%d').strftime('WEEK OF  %B %-d,  %Y')

    story = []
    story.append(Paragraph('— SELLERSIGNAL INTELLIGENCE —', S['wordmark']))
    story.append(Spacer(1, 4))
    story.append(Paragraph("This Week's Plays", S['title']))
    story.append(Paragraph('Ten moves.', S['subtitle']))
    story.append(Spacer(1, 8))

    story.append(section_bar("CALL NOW", RED_SIG))
    story.append(Spacer(1, 6))
    for i, p in enumerate(picks['call_now'], 1):
        story.append(move(str(i), p))
    story.append(Spacer(1, 8))

    story.append(section_bar("BUILD NOW  ·  NEXT 6–24 MONTHS", GOLD_DARK))
    story.append(Spacer(1, 6))
    start = len(picks['call_now']) + 1
    for i, p in enumerate(picks['build_now'], start):
        story.append(move(str(i), p))
    story.append(Spacer(1, 8))

    story.append(section_bar("STRATEGIC HOLDS  ·  LONGER SETUP, HIGH PAYOFF", INK_SOFT))
    story.append(Spacer(1, 6))
    start = len(picks['call_now']) + len(picks['build_now']) + 1
    for i, p in enumerate(picks['strategic_holds'], start):
        story.append(move(str(i), p))

    class PlaybookDoc(BaseDocTemplate):
        def __init__(self, filename, **kw):
            super().__init__(filename, **kw)
            fr = Frame(0.55*inch, 0.45*inch, letter[0]-1.1*inch, letter[1]-0.9*inch,
                       leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
            self.addPageTemplates([PageTemplate(id='p', frames=[fr], onPage=on_page(week_of))])

    doc = PlaybookDoc(out_path, pagesize=letter, title="This Week's Plays",
                      author="SellerSignal",
                      leftMargin=0.55*inch, rightMargin=0.55*inch,
                      topMargin=0.45*inch, bottomMargin=0.45*inch)
    doc.build(story)

    from pypdf import PdfReader
    return {'path': out_path, 'size': os.path.getsize(out_path),
            'pages': len(PdfReader(out_path).pages)}


if __name__ == "__main__":
    result = render(
        '/home/claude/sellersignal_v2/out/this-weeks-picks.json',
        '/home/claude/sellersignal_v2/out/this-weeks-plays-auto.pdf',
    )
    print(f"✓ {result['path']}")
    print(f"  {result['size']:,} bytes  ·  {result['pages']} page(s)")
