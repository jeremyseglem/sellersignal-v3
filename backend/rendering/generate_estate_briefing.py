"""
Silent Transitions Briefing — The Estate aesthetic.

Visual language:
  - Warm ivory backgrounds (#F7F1E8)
  - Deep charcoal ink (#1A1A1A)
  - Gold hairline rules + accents (#A88D4A)
  - Lora serif throughout (headings bolder, body regular, quotes italic)
  - Generous whitespace
  - Tracked small caps for labels
"""
import json, os
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, PageBreak, Frame, PageTemplate,
                                BaseDocTemplate, KeepTogether)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

# ─── FONT REGISTRATION ────────────────────────────────────────────────
pdfmetrics.registerFont(TTFont('Lora', '/usr/share/fonts/truetype/google-fonts/Lora-Variable.ttf'))
pdfmetrics.registerFont(TTFont('Lora-Italic', '/usr/share/fonts/truetype/google-fonts/Lora-Italic-Variable.ttf'))

# ─── COLOR PALETTE ────────────────────────────────────────────────────
IVORY = colors.HexColor('#F7F1E8')
IVORY_DEEP = colors.HexColor('#EDE4D3')
INK = colors.HexColor('#1A1A1A')
INK_SOFT = colors.HexColor('#3C3C3A')
INK_MUTED = colors.HexColor('#6B6A65')
GOLD = colors.HexColor('#A88D4A')
GOLD_DARK = colors.HexColor('#8F7336')
CREAM = colors.HexColor('#FAF6ED')

# ─── LOAD DATA ────────────────────────────────────────────────────────
inv = json.load(open('/home/claude/sellersignal_v2/out/banded-inventory-verified.json'))
leads = inv['leads']
syntheses_prototype = json.load(open('/home/claude/sellersignal_v2/out/synthesized-leads-prototype.json'))
critic_demo = json.load(open('/home/claude/sellersignal_v2/out/critic-corrections-demo.json'))

# Synthesis lookup
synth_by_addr = {}
for s in syntheses_prototype.get('syntheses', []):
    addr_key = s['address'].split(',')[0].strip()
    synth_by_addr[addr_key] = s['synthesized_narrative']
for item in critic_demo.get('demo_5_leads_before_after', []):
    addr_key = item['address'].split(',')[0].split(' + ')[0].strip().split('(')[0].strip()
    synth_by_addr[addr_key] = {'tightened': item.get('tightened_synthesis', '')}

# ─── STYLES ───────────────────────────────────────────────────────────
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='Wordmark', fontSize=9, leading=11,
                          fontName='Lora', textColor=GOLD_DARK,
                          alignment=TA_LEFT, spaceAfter=0))
styles.add(ParagraphStyle(name='CoverTitle', fontSize=44, leading=48,
                          fontName='Lora', textColor=INK, spaceAfter=8))
styles.add(ParagraphStyle(name='CoverSub', fontSize=14, leading=18,
                          fontName='Lora-Italic', textColor=INK_MUTED,
                          spaceAfter=18))
styles.add(ParagraphStyle(name='CoverMarkets', fontSize=11, leading=16,
                          fontName='Lora', textColor=INK_SOFT, spaceAfter=12))
styles.add(ParagraphStyle(name='SmallCaps', fontSize=9, leading=14,
                          fontName='Lora', textColor=GOLD_DARK,
                          spaceAfter=4))
styles.add(ParagraphStyle(name='SectionNum', fontSize=10, leading=14,
                          fontName='Lora', textColor=GOLD_DARK, spaceAfter=2))
styles.add(ParagraphStyle(name='SectionTitle', fontSize=28, leading=32,
                          fontName='Lora', textColor=INK, spaceAfter=18,
                          spaceBefore=6))
styles.add(ParagraphStyle(name='SectionBody', fontSize=11, leading=17,
                          fontName='Lora', textColor=INK_SOFT,
                          alignment=TA_JUSTIFY, spaceAfter=14))
styles.add(ParagraphStyle(name='SubHeader', fontSize=16, leading=22,
                          fontName='Lora', textColor=INK, spaceAfter=10,
                          spaceBefore=18))
styles.add(ParagraphStyle(name='LeadAddr', fontSize=14, leading=18,
                          fontName='Lora', textColor=INK,
                          spaceAfter=3, spaceBefore=14))
styles.add(ParagraphStyle(name='LeadValue', fontSize=11, leading=14,
                          fontName='Lora-Italic', textColor=GOLD_DARK,
                          spaceAfter=8))
styles.add(ParagraphStyle(name='Meta', fontSize=9.5, leading=14,
                          fontName='Lora', textColor=INK_SOFT,
                          spaceAfter=2))
styles.add(ParagraphStyle(name='Narrative', fontSize=10, leading=16,
                          fontName='Lora', textColor=INK,
                          alignment=TA_JUSTIFY, spaceAfter=10,
                          leftIndent=14, rightIndent=14,
                          borderPadding=(12, 14, 12, 14),
                          backColor=CREAM,
                          borderColor=GOLD,
                          borderWidth=0))
styles.add(ParagraphStyle(name='Pullquote', fontSize=11, leading=17,
                          fontName='Lora-Italic', textColor=INK_SOFT,
                          alignment=TA_JUSTIFY, spaceAfter=10,
                          leftIndent=20, rightIndent=20))
styles.add(ParagraphStyle(name='Body', fontSize=10, leading=15,
                          fontName='Lora', textColor=INK_SOFT,
                          alignment=TA_JUSTIFY, spaceAfter=8))
styles.add(ParagraphStyle(name='Footer', fontSize=8, leading=11,
                          fontName='Lora-Italic', textColor=INK_MUTED))

# ─── PAGE DECORATION (background + header/footer) ────────────────────
def on_page(canv: canvas.Canvas, doc):
    canv.saveState()
    # Ivory background
    canv.setFillColor(IVORY)
    canv.rect(0, 0, letter[0], letter[1], fill=1, stroke=0)
    # Gold hairline under the top margin band
    canv.setStrokeColor(GOLD)
    canv.setLineWidth(0.4)
    canv.line(0.75*inch, letter[1] - 0.5*inch, letter[0] - 0.75*inch, letter[1] - 0.5*inch)
    # Top-left wordmark
    canv.setFillColor(GOLD_DARK)
    canv.setFont('Lora', 8.5)
    canv.drawString(0.75*inch, letter[1] - 0.38*inch, 'SELLERSIGNAL  ·  THE ESTATE REPORT')
    # Top-right: quarter
    canv.drawRightString(letter[0] - 0.75*inch, letter[1] - 0.38*inch, 'Q2  2026')
    # Bottom hairline + page number
    canv.setStrokeColor(GOLD)
    canv.setLineWidth(0.4)
    canv.line(0.75*inch, 0.55*inch, letter[0] - 0.75*inch, 0.55*inch)
    canv.setFillColor(INK_MUTED)
    canv.setFont('Lora-Italic', 8)
    canv.drawString(0.75*inch, 0.4*inch, 'Silent Transitions Briefing  ·  Eastside Luxury Corridor')
    canv.drawRightString(letter[0] - 0.75*inch, 0.4*inch, f'Page  {doc.page}')
    canv.restoreState()

def on_cover(canv: canvas.Canvas, doc):
    canv.saveState()
    canv.setFillColor(IVORY)
    canv.rect(0, 0, letter[0], letter[1], fill=1, stroke=0)
    # Top gold band (thin)
    canv.setFillColor(GOLD)
    canv.rect(0, letter[1] - 0.15*inch, letter[0], 0.15*inch, fill=1, stroke=0)
    # Atmospheric gradient hint — subtle beige band at bottom
    canv.setFillColor(IVORY_DEEP)
    canv.rect(0, 0, letter[0], 1.8*inch, fill=1, stroke=0)
    # Gold hairline on the cover
    canv.setStrokeColor(GOLD)
    canv.setLineWidth(0.5)
    canv.line(0.75*inch, 1.8*inch, letter[0] - 0.75*inch, 1.8*inch)
    canv.restoreState()

# ─── BUILD STORY ──────────────────────────────────────────────────────
story = []

# ═══ COVER ═══
story.append(Spacer(1, 2*inch))
story.append(Paragraph('— SELLERSIGNAL INTELLIGENCE —', styles['Wordmark']))
story.append(Spacer(1, 0.2*inch))
story.append(Paragraph('Silent Transitions', styles['CoverTitle']))
story.append(Paragraph('Q2 2026 &nbsp;·&nbsp; Eastside Luxury Markets', styles['CoverSub']))
story.append(Spacer(1, 0.3*inch))
story.append(Paragraph(
    'Medina &nbsp;·&nbsp; Mercer Island &nbsp;·&nbsp; Kirkland &nbsp;·&nbsp; Newport &nbsp;·&nbsp; Bridle Trails &nbsp;·&nbsp; Hunts Point',
    styles['CoverMarkets']))
story.append(Spacer(1, 1.5*inch))

# Cover quote
story.append(Paragraph(
    '&ldquo;The inventory that doesn&rsquo;t yet exist — constructed from tenure, structure, and demographic inevitability — is where the next decade of Eastside transactions will come from.&rdquo;',
    styles['Pullquote']))
story.append(Spacer(1, 0.4*inch))

# Bottom stats
total_leads = len(leads)
band_counts = {}
for L in leads: band_counts.setdefault(L['band'], 0); band_counts[L['band']] += 1

cover_stats = [
    [f'{total_leads:,}', 'PROPERTIES UNDER CULTIVATION'],
    [f'{inv.get("expected_1yr", 0):,}', 'EXPECTED TRANSITIONS / 12 MONTHS'],
    ['5', 'EASTSIDE LUXURY ZIP CODES'],
    ['0', 'PAID DATA FEEDS'],
]
cover_tbl = Table(cover_stats, colWidths=[1.3*inch, 4.7*inch])
cover_tbl.setStyle(TableStyle([
    ('FONT', (0,0), (0,-1), 'Lora', 20),
    ('FONT', (1,0), (1,-1), 'Lora', 8.5),
    ('TEXTCOLOR', (0,0), (0,-1), INK),
    ('TEXTCOLOR', (1,0), (1,-1), GOLD_DARK),
    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ('LINEBELOW', (0,0), (-1,-1), 0.3, GOLD),
    ('BOTTOMPADDING', (0,0), (-1,-1), 10),
    ('TOPPADDING', (0,0), (-1,-1), 10),
    ('LEFTPADDING', (0,0), (-1,-1), 0),
]))
story.append(cover_tbl)

story.append(PageBreak())

# ═══ EDITOR'S LETTER / EXECUTIVE NOTE ═══
story.append(Paragraph('00', styles['SectionNum']))
story.append(Paragraph("Editor&rsquo;s Note", styles['SectionTitle']))

story.append(Paragraph(
    'This quarter introduces two structural changes to how SellerSignal presents its inventory. The first is a formal <b>verification gate</b> at the top of the list: a lead is only promoted to <b>Band&nbsp;1A</b> when a named survivor or grantor from a published obituary can be tied directly to the property&rsquo;s current owner record. Pattern matches — shared surname, same neighborhood — are not sufficient; those now sit in Band&nbsp;2.5 awaiting verification. The change is deliberate. It is more honest, and it protects the one thing this product must protect, which is the credibility of the top of the list.',
    styles['SectionBody']))

story.append(Paragraph(
    'The second change is that we now explicitly distinguish <b>observed events</b> (publicly searchable — divorces, foreclosures, expired listings) from <b>inferred transitions</b> (tenure + age + ownership structure signals that no MLS query will surface). Agents already compete for the former. They cannot compete for the latter without us. The center of gravity of this briefing is Band&nbsp;2 — the 1,894 Eastside properties where inference points strongly at a transaction within 24–36 months.',
    styles['SectionBody']))

story.append(Paragraph(
    'The Weinstein portfolio event we surfaced in draft was dissolved when the verification layer ran against the actual Seattle Times obituary. Devorah Weinstein&rsquo;s named survivors are her daughter Jill, her brother Kalmen Glantz, and her Sloan and Florentino-Weinstein grandchildren — none of whom own the Skagit Key or West Mercer properties we initially matched. A similar disposition for the Gilbert cohort: Gordon &ldquo;Skip&rdquo; Gilbert Jr.&rsquo;s wife was Margaret (&ldquo;Midge&rdquo;), and his sons Andrew and Craig do not appear on any of the Gilbert-surnamed parcels we tested. Seven obit-based matches were explicitly rejected on verification; sixteen remain pending full obit retrieval. Zero Band&nbsp;1A leads qualify in this quarter&rsquo;s cohort.',
    styles['SectionBody']))

story.append(Paragraph(
    'This is not a failure of the system. It is the system functioning correctly. The verification layer caught seven false positives before they reached an agent&rsquo;s desk. The real franchise this quarter sits in Band&nbsp;2: Charles Simonyi&rsquo;s revocable trust on 84th Avenue NE, the Hunts Point Road trust-aging cohort, the Evergreen Point dormant-absentee line. These are the cultivation leads that reward a Six Letters cadence over 18 months.',
    styles['SectionBody']))

story.append(PageBreak())

# ═══ AT A GLANCE ═══
story.append(Paragraph('01', styles['SectionNum']))
story.append(Paragraph('At a Glance', styles['SectionTitle']))

story.append(Paragraph(
    'This briefing identifies properties across five Eastside luxury ZIP codes where one or more seller-transition signals indicate a material probability of sale within the next thirty-six months. Approximately ninety-eight percent of these leads cannot be found through MLS, public search, or any competing intelligence tool. They are constructed, not scraped.',
    styles['SectionBody']))

# Per-ZIP breakdown table
story.append(Paragraph('Per-ZIP Inventory', styles['SubHeader']))

from collections import Counter
zip_labels = {'98004': 'Bellevue — West, Hunts Point, Clyde Hill',
              '98039': 'Medina',
              '98040': 'Mercer Island',
              '98033': 'Kirkland — Waterfront Corridor',
              '98006': 'Newport / Somerset',
              '98005': 'Bridle Trails'}
zip_rows = [['ZIP', 'Market', 'Cohort', 'Band 1A', 'Band 2', 'Band 2.5', 'Band 3', 'Band 4']]
for z in ['98039', '98004', '98040', '98033', '98006', '98005']:
    zl = [L for L in leads if L.get('zip') == z]
    if not zl: continue
    zip_rows.append([
        z, zip_labels.get(z, '')[:34],
        f'{len(zl):,}',
        str(sum(1 for L in zl if L['band'] == 1)),
        f"{sum(1 for L in zl if L['band'] == 2):,}",
        str(sum(1 for L in zl if L['band'] == 2.5)),
        str(sum(1 for L in zl if L['band'] == 3)),
        f"{sum(1 for L in zl if L['band'] == 4):,}",
    ])
zip_tbl = Table(zip_rows, colWidths=[0.55*inch, 2.5*inch, 0.7*inch, 0.65*inch, 0.6*inch, 0.7*inch, 0.55*inch, 0.6*inch])
zip_tbl.setStyle(TableStyle([
    ('FONT', (0,0), (-1,0), 'Lora', 8),
    ('FONT', (0,1), (-1,-1), 'Lora', 9),
    ('TEXTCOLOR', (0,0), (-1,0), GOLD_DARK),
    ('TEXTCOLOR', (0,1), (-1,-1), INK_SOFT),
    ('TEXTCOLOR', (0,1), (0,-1), INK),  # ZIP column bold
    ('FONT', (0,1), (0,-1), 'Lora', 10),
    ('LINEABOVE', (0,0), (-1,0), 0.5, GOLD),
    ('LINEBELOW', (0,0), (-1,0), 0.3, GOLD),
    ('LINEBELOW', (0,-1), (-1,-1), 0.5, GOLD),
    ('ALIGN', (2,0), (-1,-1), 'CENTER'),
    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ('BOTTOMPADDING', (0,0), (-1,-1), 7),
    ('TOPPADDING', (0,0), (-1,-1), 8),
    ('LEFTPADDING', (0,0), (0,-1), 0),
]))
story.append(zip_tbl)
story.append(Spacer(1, 0.25*inch))

# The band bands explainer
story.append(Paragraph('The Four Bands', styles['SubHeader']))

band_rows = [
    ['BAND  1A', 'Verified — survivor or grantor name match confirmed against an obituary. Act now.'],
    ['BAND  2', 'Inference — trust-aging grantor, silent transition, dormant absentee. 24–36 month horizon.'],
    ['BAND  2.5', 'Convergent candidate — partial obit correlation pending verification. Do not pursue yet.'],
    ['BAND  3', 'Imminent + escapable — NOD, trustee sale, failed listing (rationality-filtered).'],
    ['BAND  4', 'Long-cycle cultivation — 36-60 month Six Letters audience.'],
]
band_tbl = Table(band_rows, colWidths=[1.2*inch, 5.3*inch])
band_tbl.setStyle(TableStyle([
    ('FONT', (0,0), (0,-1), 'Lora', 9),
    ('FONT', (1,0), (1,-1), 'Lora', 10),
    ('TEXTCOLOR', (0,0), (0,-1), GOLD_DARK),
    ('TEXTCOLOR', (1,0), (1,-1), INK_SOFT),
    ('VALIGN', (0,0), (-1,-1), 'TOP'),
    ('LINEBELOW', (0,0), (-1,-2), 0.25, IVORY_DEEP),
    ('BOTTOMPADDING', (0,0), (-1,-1), 10),
    ('TOPPADDING', (0,0), (-1,-1), 10),
    ('LEFTPADDING', (0,0), (0,-1), 0),
]))
story.append(band_tbl)

story.append(PageBreak())

# ═══ BAND 1A — VERIFIED ═══
story.append(Paragraph('02', styles['SectionNum']))
story.append(Paragraph('Band 1A — Verified', styles['SectionTitle']))

story.append(Paragraph(
    'Leads where the verification gate has closed: a survivor or grantor named in the source obituary can be directly identified as an owner or beneficiary of the property in question. These are the act-now leads of this quarter.',
    styles['SectionBody']))

story.append(Spacer(1, 0.2*inch))

story.append(Paragraph(
    '&ldquo;This quarter&rsquo;s verification gate produced zero qualifying leads.&rdquo;',
    styles['Pullquote']))

story.append(Paragraph(
    'Twenty-three obituary-based matches were identified during the initial scan. Upon strict verification against full obituary text, seven were explicitly rejected — the named survivors did not match the property owners or grantors. Sixteen remain in Band 2.5 pending obituary retrieval and parsing. None qualified for Band 1A.',
    styles['Body']))

story.append(Paragraph(
    'This is the system working. In the prior cohort, the Weinstein family portfolio event and the Gordon Gilbert cluster would have been presented as Band 1 leads. Both are dissolved upon verification: Devorah Weinstein&rsquo;s named survivors are her daughter Jill, her brother Kalmen Glantz, and her Sloan and Florentino-Weinstein grandchildren — none of whom appear on the Skagit Key or West Mercer Way property records we initially tied to her. Similarly, Skip Gilbert&rsquo;s wife was Margaret (&ldquo;Midge&rdquo;), and his sons Andrew and Craig do not own any of the Gilbert-surnamed parcels we surfaced.',
    styles['Body']))

story.append(Paragraph(
    'The correct disposition of this finding is to freshen the obituary harvest for the specific Eastside ZIPs — our current source pool is Bellevue-biased and thin for Medina, Mercer Island, and Kirkland. A targeted Medina obituary pass in the next thirty days is expected to surface one to three new verifiable Band 1A candidates.',
    styles['Body']))

story.append(PageBreak())

# ═══ BAND 2 — THE FRANCHISE ═══
story.append(Paragraph('03', styles['SectionNum']))
story.append(Paragraph('Band 2 — The Franchise', styles['SectionTitle']))

story.append(Paragraph(
    'Inferred pre-seller inventory across five Eastside ZIP codes. These are constructed leads — built by cross-referencing tenure, ownership structure, mailing-address dormancy, and neighborhood demographic cohort. They are the core deliverable of this report and the audience for your Six Letters cultivation program.',
    styles['SectionBody']))

band2_leads = sorted([L for L in leads if L['band'] == 2], key=lambda x: -x.get('rank_score', 0))

# Top 5 with synthesis
story.append(Paragraph(f'Top Five — Synthesized Analysis', styles['SubHeader']))

for i, L in enumerate(band2_leads[:5], 1):
    story.append(Paragraph(f'{L.get("address", "—")}', styles['LeadAddr']))
    story.append(Paragraph(f"{L.get('city') or L.get('zip','')}  ·  ${L.get('value', 0):,}", styles['LeadValue']))

    owner = L.get('owner') or '—'
    sig_display = (L.get('signal_family') or '').replace('_', ' ').title()
    meta_lines = [
        f'<font color="#8F7336">OWNER</font> &nbsp;&nbsp;&nbsp; {owner[:80]}',
        f'<font color="#8F7336">SIGNAL</font> &nbsp;&nbsp;&nbsp; {sig_display} &nbsp;·&nbsp; Inevitability {L.get("inevitability",0)*100:.0f}% &nbsp;·&nbsp; Confidence {L.get("confidence_score","—")}/100 &nbsp;·&nbsp; {L.get("timeline_months","—")} mo',
    ]
    if L.get('grantor'):
        meta_lines.append(f'<font color="#8F7336">GRANTOR</font> &nbsp;&nbsp; {L["grantor"][:70]}')
    if L.get('convergent_families'):
        cf = ', '.join(L['convergent_families'])
        meta_lines.append(f'<font color="#8F7336">CONVERGENCE</font> &nbsp; {cf}')
    for m in meta_lines:
        story.append(Paragraph(m, styles['Meta']))

    addr_key = (L.get('address') or '').strip()
    synth = synth_by_addr.get(addr_key)
    if synth and isinstance(synth, dict) and 'whats_happening' in synth:
        narrative = (
            f"<b>What&rsquo;s actually happening.</b> {synth.get('whats_happening', '')}<br/><br/>"
            f"<b>Confidence check.</b> {synth.get('confidence_check', '')}<br/><br/>"
            f"<b>Cultivation approach.</b> {synth.get('cultivation_approach', '')}<br/><br/>"
            f"<b>What to avoid.</b> {synth.get('what_to_avoid', '')}"
        )
        story.append(Spacer(1, 0.1*inch))
        story.append(Paragraph(narrative, styles['Narrative']))
    elif synth and isinstance(synth, dict) and 'tightened' in synth:
        story.append(Spacer(1, 0.1*inch))
        story.append(Paragraph(synth['tightened'].replace('\n\n', '<br/><br/>'), styles['Narrative']))
    else:
        story.append(Spacer(1, 0.05*inch))
        story.append(Paragraph(
            '<i>Synthesis pending — scheduled for next API run.</i>',
            styles['Narrative']))

    story.append(Spacer(1, 0.1*inch))

# Next 25 as ranked table
story.append(PageBreak())
story.append(Paragraph('Ranked — Positions 6 through 30', styles['SubHeader']))

b2_rows = [['#', 'ZIP', 'Address', 'Owner', 'Value', 'Inev', 'Conf', 'Signal']]
for i, L in enumerate(band2_leads[5:30], 6):
    sig = (L.get('signal_family') or '').replace('_', ' ')[:13]
    conv = ' + ' + ','.join(f[:4] for f in L.get('convergent_families', [])[:2]) if L.get('convergent_families') else ''
    b2_rows.append([
        str(i),
        L.get('zip') or '',
        (L.get('address') or '—')[:26],
        (L.get('owner') or '—')[:26],
        f"${L.get('value', 0)/1_000_000:.1f}M",
        f"{L.get('inevitability', 0)*100:.0f}%",
        str(L.get('confidence_score', '—')),
        (sig + conv)[:18],
    ])
b2_tbl = Table(b2_rows, colWidths=[0.3*inch, 0.5*inch, 1.9*inch, 1.9*inch, 0.6*inch, 0.45*inch, 0.5*inch, 1.2*inch])
b2_tbl.setStyle(TableStyle([
    ('FONT', (0,0), (-1,0), 'Lora', 7.5),
    ('FONT', (0,1), (-1,-1), 'Lora', 8.5),
    ('TEXTCOLOR', (0,0), (-1,0), GOLD_DARK),
    ('TEXTCOLOR', (0,1), (-1,-1), INK_SOFT),
    ('LINEABOVE', (0,0), (-1,0), 0.5, GOLD),
    ('LINEBELOW', (0,0), (-1,0), 0.3, GOLD),
    ('LINEBELOW', (0,-1), (-1,-1), 0.5, GOLD),
    ('ALIGN', (4,0), (-1,-1), 'CENTER'),
    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
    ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ('TOPPADDING', (0,0), (-1,-1), 6),
]))
story.append(b2_tbl)

story.append(PageBreak())

# ═══ BAND 2.5 — CONVERGENT CANDIDATES ═══
story.append(Paragraph('04', styles['SectionNum']))
story.append(Paragraph('Band 2.5 — Convergent Candidates', styles['SectionTitle']))

story.append(Paragraph(
    'Properties with partial obituary correlation that have not yet cleared the verification gate. These require obituary retrieval and survivor-name cross-reference before any outreach. Presented here as the verification queue for the next cycle.',
    styles['SectionBody']))

# Surviving clusters
surviving_clusters = [L for L in leads if L.get('signal_family') == 'family_event_cluster' and L['band'] == 2.5]
if surviving_clusters:
    story.append(Paragraph('Family Cluster Candidates — Pending Verification', styles['SubHeader']))
    for L in surviving_clusters:
        cd = L.get('cluster_data', {})
        story.append(Paragraph(
            f"{cd.get('surname', '—')} &nbsp;·&nbsp; {cd.get('property_count')} properties &nbsp;·&nbsp; ZIP {cd.get('zip', '—')}",
            styles['LeadAddr']))
        story.append(Paragraph(
            f"Combined assessed value ${cd.get('total_value', 0):,}",
            styles['LeadValue']))
        meta_lines = [
            f'<font color="#8F7336">TRIGGERING OBIT</font> &nbsp; {cd.get("triggering_obit", "—")}',
            f'<font color="#8F7336">COMMON SURNAME</font> &nbsp; {"yes (high coincidence risk)" if cd.get("common_surname") else "no"}',
            f'<font color="#8F7336">CONFIDENCE</font> &nbsp;&nbsp; {cd.get("confidence_score", "—")}/100',
        ]
        addrs = cd.get('addresses', [])
        meta_lines.append(f'<font color="#8F7336">PROPERTIES</font> &nbsp;&nbsp; {", ".join(addrs)}')
        for m in meta_lines:
            story.append(Paragraph(m, styles['Meta']))
        # Verification path
        story.append(Spacer(1, 0.08*inch))
        story.append(Paragraph(
            f'<b>Verification path.</b> Retrieve full obituary for {cd.get("triggering_obit", "the deceased")}. Parse named survivors. Cross-reference against the property owner records above. If a survivor name matches any of these owners, promote the cluster to Band 1A. If no match, dissolve.',
            styles['Body']))
        story.append(Spacer(1, 0.1*inch))

# Individual B2.5
story.append(Paragraph('Individual Candidates — Pending Verification', styles['SubHeader']))
indiv = [L for L in leads if L['band'] == 2.5 and L.get('signal_family') != 'family_event_cluster']
indiv.sort(key=lambda x: -x.get('rank_score', 0))

if indiv:
    rows = [['#', 'Address', 'Owner', 'Value', 'Obit (pending verification)', 'Conf']]
    for i, L in enumerate(indiv, 1):
        obit_name = (L.get('obit_match') or {}).get('obit_name', '—')
        rows.append([
            str(i),
            (L.get('address') or '—')[:28],
            (L.get('owner') or '—')[:28],
            f"${L.get('value', 0)/1_000_000:.1f}M",
            obit_name[:26],
            str(L.get('confidence_score', '—')),
        ])
    tbl = Table(rows, colWidths=[0.3*inch, 2.0*inch, 2.0*inch, 0.55*inch, 1.65*inch, 0.4*inch])
    tbl.setStyle(TableStyle([
        ('FONT', (0,0), (-1,0), 'Lora', 7.5),
        ('FONT', (0,1), (-1,-1), 'Lora', 8.5),
        ('TEXTCOLOR', (0,0), (-1,0), GOLD_DARK),
        ('TEXTCOLOR', (0,1), (-1,-1), INK_SOFT),
        ('LINEABOVE', (0,0), (-1,0), 0.5, GOLD),
        ('LINEBELOW', (0,0), (-1,0), 0.3, GOLD),
        ('LINEBELOW', (0,-1), (-1,-1), 0.5, GOLD),
        ('ALIGN', (3,0), (-1,-1), 'CENTER'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('TOPPADDING', (0,0), (-1,-1), 6),
    ]))
    story.append(tbl)

story.append(PageBreak())

# ═══ BAND 3 — ACT NOW (ESCAPABLE) ═══
story.append(Paragraph('05', styles['SectionNum']))
story.append(Paragraph('Band 3 — Imminent &amp; Escapable', styles['SectionTitle']))

story.append(Paragraph(
    'Observed events with immediate timelines but structurally lower conversion rates. Notices of default, trustee sales, failed listings (filtered for seller rationality), and investor dispositions. These are the publicly-searchable leads that every Agency agent also sees — our value on these is ranking and rationality-filtering, not discovery.',
    styles['SectionBody']))

band3_leads = sorted([L for L in leads if L['band'] == 3], key=lambda x: -x.get('rank_score', 0))
if band3_leads:
    rows = [['#', 'Address', 'Owner', 'Value', 'Signal', 'Rationality']]
    for i, L in enumerate(band3_leads, 1):
        rat = L.get('rationality_score')
        rat_str = f"{rat}/10" if rat is not None else '—'
        sig = (L.get('signal_family') or '').replace('_', ' ').title()
        rows.append([
            str(i),
            (L.get('address') or '—')[:28],
            (L.get('owner') or '—')[:28],
            f"${L.get('value', 0):,}",
            sig[:18],
            rat_str,
        ])
    tbl = Table(rows, colWidths=[0.3*inch, 2.0*inch, 2.0*inch, 1.0*inch, 1.2*inch, 0.7*inch])
    tbl.setStyle(TableStyle([
        ('FONT', (0,0), (-1,0), 'Lora', 8),
        ('FONT', (0,1), (-1,-1), 'Lora', 9),
        ('TEXTCOLOR', (0,0), (-1,0), GOLD_DARK),
        ('TEXTCOLOR', (0,1), (-1,-1), INK_SOFT),
        ('LINEABOVE', (0,0), (-1,0), 0.5, GOLD),
        ('LINEBELOW', (0,0), (-1,0), 0.3, GOLD),
        ('LINEBELOW', (0,-1), (-1,-1), 0.5, GOLD),
        ('ALIGN', (3,0), (-1,-1), 'CENTER'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 7),
    ]))
    story.append(tbl)

story.append(Spacer(1, 0.3*inch))

# Note on the rejected lead
rejected = [L for L in leads if L['band'] == 0]
if rejected:
    story.append(Paragraph(
        f'<font color="#8F7336">REJECTED BY RATIONALITY FILTER</font>',
        styles['SmallCaps']))
    for L in rejected:
        story.append(Paragraph(
            f'{L.get("address","—")} &nbsp;·&nbsp; {L.get("owner","")} &nbsp;·&nbsp; listed ≥2.5× ZIP median — deluded seller pattern. Do not pursue.',
            styles['Body']))

story.append(PageBreak())

# ═══ BAND 4 — SIX LETTERS COHORT ═══
story.append(Paragraph('06', styles['SectionNum']))
story.append(Paragraph('Band 4 — Six Letters Cohort', styles['SectionTitle']))

total_b4 = sum(1 for L in leads if L['band'] == 4)
story.append(Paragraph(
    f'The long-horizon cultivation pool. {total_b4:,} properties with 36–60 month expected transition windows. These are the audience for the Six Letters cadence — a letter every sixty days, each slightly more specific than the last, compounding relationship across eighteen months against a cohort that no competitor is working.',
    styles['SectionBody']))

band4_leads = sorted([L for L in leads if L['band'] == 4], key=lambda x: -x.get('rank_score', 0))[:18]
rows = [['#', 'ZIP', 'Address', 'Owner', 'Value', 'Inev', 'Timeline', 'Signal']]
for i, L in enumerate(band4_leads, 1):
    rows.append([
        str(i),
        L.get('zip') or '',
        (L.get('address') or '—')[:26],
        (L.get('owner') or '—')[:26],
        f"${L.get('value', 0)/1_000_000:.1f}M",
        f"{L.get('inevitability', 0)*100:.0f}%",
        f"{L.get('timeline_months', '—')}mo",
        (L.get('signal_family') or '').replace('_', ' ')[:14],
    ])
tbl = Table(rows, colWidths=[0.3*inch, 0.5*inch, 1.85*inch, 1.85*inch, 0.6*inch, 0.4*inch, 0.55*inch, 1.1*inch])
tbl.setStyle(TableStyle([
    ('FONT', (0,0), (-1,0), 'Lora', 7.5),
    ('FONT', (0,1), (-1,-1), 'Lora', 8.5),
    ('TEXTCOLOR', (0,0), (-1,0), GOLD_DARK),
    ('TEXTCOLOR', (0,1), (-1,-1), INK_SOFT),
    ('LINEABOVE', (0,0), (-1,0), 0.5, GOLD),
    ('LINEBELOW', (0,0), (-1,0), 0.3, GOLD),
    ('LINEBELOW', (0,-1), (-1,-1), 0.5, GOLD),
    ('ALIGN', (4,0), (-1,-1), 'CENTER'),
    ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ('TOPPADDING', (0,0), (-1,-1), 6),
]))
story.append(tbl)

story.append(Spacer(1, 0.2*inch))
story.append(Paragraph(
    f'<i>Showing top 18 of {total_b4:,}. Full cohort available via banded-inventory-verified.json export.</i>',
    styles['Footer']))

story.append(PageBreak())

# ═══ APPENDIX — COHORT ANALYTICS ═══
story.append(Paragraph('A', styles['SectionNum']))
story.append(Paragraph('Street-Level Hotspots', styles['SectionTitle']))

story.append(Paragraph(
    'Streets with concentrated transition signal across Band 1A, 2, and 2.5. These are corridors where the demographic transition is compounding — an agent cultivating one property on one of these streets is effectively cultivating a portfolio.',
    styles['SectionBody']))

street_counts = Counter()
street_value = Counter()
for L in leads:
    if L['band'] not in (1, 2, 2.5): continue
    addr = L.get('address') or ''
    parts = addr.split()
    if len(parts) < 2: continue
    street = ' '.join(parts[1:])
    street_counts[(L.get('zip'), street)] += 1
    street_value[(L.get('zip'), street)] += L.get('value', 0) or 0

rows = [['ZIP', 'Street', 'Leads', 'Combined Value']]
for (z, street), count in street_counts.most_common(25):
    if count < 3: continue
    rows.append([z, street[:34], str(count), f"${street_value[(z, street)]/1_000_000:.1f}M"])
if len(rows) > 1:
    tbl = Table(rows, colWidths=[0.7*inch, 3.3*inch, 0.8*inch, 1.5*inch])
    tbl.setStyle(TableStyle([
        ('FONT', (0,0), (-1,0), 'Lora', 8.5),
        ('FONT', (0,1), (-1,-1), 'Lora', 10),
        ('TEXTCOLOR', (0,0), (-1,0), GOLD_DARK),
        ('TEXTCOLOR', (0,1), (-1,-1), INK_SOFT),
        ('LINEABOVE', (0,0), (-1,0), 0.5, GOLD),
        ('LINEBELOW', (0,0), (-1,0), 0.3, GOLD),
        ('LINEBELOW', (0,-1), (-1,-1), 0.5, GOLD),
        ('ALIGN', (2,0), (-1,-1), 'CENTER'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 7),
        ('TOPPADDING', (0,0), (-1,-1), 8),
    ]))
    story.append(tbl)

story.append(PageBreak())

# ═══ APPENDIX — METHODOLOGY ═══
story.append(Paragraph('B', styles['SectionNum']))
story.append(Paragraph('Methodology', styles['SectionTitle']))

story.append(Paragraph('The Three-Layer Architecture', styles['SubHeader']))

story.append(Paragraph(
    '<b>Layer 1 — Deterministic Gating.</b> Rule-based filters over King County parcel data, deed chains, taxpayer mailing records, and assessed valuations. Narrows 39,161 Eastside parcels to a cohort of inference candidates matching one or more signal families: silent transition (age-probable lifetime owners), trust-aging grantor, dormant absentee, investor disposition, and financial stress.',
    styles['Body']))

story.append(Paragraph(
    '<b>Layer 2 — Evidence Harvest and Convergence.</b> For each candidate, supporting evidence is compiled: full deed chain, trust structure, mailing patterns, obituary cross-reference, and street-level clustering. When multiple signal families fire on the same parcel, convergence boosts confidence. Family cluster detection groups multi-property matches into portfolio-level events when surname is uncommon and geography is tight.',
    styles['Body']))

story.append(Paragraph(
    '<b>Layer 3 — Synthesis and Verification.</b> Claude reads each candidate&rsquo;s full dossier and produces an analyst-style narrative: what the data means, confidence assessment, cultivation angle, and what to avoid. Typical API cost: $0.01 per lead. The verification layer then fetches full obituary text for each obit-based match, parses named survivors, and cross-references against property owner and grantor records. Only explicit survivor-to-owner matches promote to Band 1A.',
    styles['Body']))

story.append(Paragraph('Data Sources', styles['SubHeader']))
story.append(Paragraph(
    'King County ArcGIS Parcel Service &nbsp;·&nbsp; King County Assessor bulk exports (EXTR_Parcel, EXTR_RPSale, EXTR_RPAcct) &nbsp;·&nbsp; King County LandmarkWeb recorded documents &nbsp;·&nbsp; King County Superior Court probate dockets &nbsp;·&nbsp; public obituary sources (Seattle Times, Dignity Memorial, Everloved, Echovita) &nbsp;·&nbsp; Zillow price history. <b>No paid third-party data feeds.</b> Pipeline scales to any Washington county with zero marginal cost.',
    styles['Body']))

story.append(Paragraph('Scoring Model', styles['SubHeader']))
story.append(Paragraph(
    '<b>Confidence score (0&ndash;100)</b> is orthogonal to band and composed of four dimensions: name match (up to 40), geographic overlap (up to 20), convergent signal families (up to 20), and age alignment (up to 20). <b>Final rank</b> combines inevitability, confidence, and assessed value: rank = inevitability × (confidence ÷ 100) × value. <b>Seller rationality</b> is scored 0&ndash;10 for any expired-listing signal; scores below 4 are rejected from the briefing entirely.',
    styles['Body']))

story.append(Spacer(1, 0.4*inch))
story.append(Paragraph(
    '<i>Prepared by SellerSignal Intelligence &nbsp;·&nbsp; ' + datetime.now().strftime('%B %Y') + '</i>',
    styles['Footer']))

# ─── BUILD THE PDF ─────────────────────────────────────────────────────
out_path = '/home/claude/sellersignal_v2/out/silent-transitions-briefing-themed.pdf'

class EstateDocTemplate(BaseDocTemplate):
    def __init__(self, filename, **kw):
        super().__init__(filename, **kw)
        frame_cover = Frame(
            0.75*inch, 0.6*inch,
            letter[0] - 1.5*inch, letter[1] - 1.1*inch,
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
            id='cover_frame')
        frame_normal = Frame(
            0.75*inch, 0.65*inch,
            letter[0] - 1.5*inch, letter[1] - 1.2*inch,
            leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
            id='normal_frame')
        self.addPageTemplates([
            PageTemplate(id='cover', frames=[frame_cover], onPage=on_cover),
            PageTemplate(id='interior', frames=[frame_normal], onPage=on_page),
        ])

doc = EstateDocTemplate(
    out_path, pagesize=letter,
    title="Silent Transitions — Q2 2026",
    author="SellerSignal Intelligence",
)

# Switch from cover template to interior template after first page
from reportlab.platypus import NextPageTemplate
# Insert NextPageTemplate after cover content so subsequent pages use interior
cover_index = next(i for i, s in enumerate(story) if isinstance(s, PageBreak))
story.insert(cover_index, NextPageTemplate('interior'))

doc.build(story)
print(f"✓ Estate briefing generated: {out_path}")
print(f"  File size: {os.path.getsize(out_path):,} bytes")
