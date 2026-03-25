"""
PDF invoice generator. Generates professional invoices for Norwegian customers.
Outputs to outputs/reports/YYYY-MM-DD_faktura_<id>.pdf
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("outputs/reports")

try:
    from fpdf import FPDF
    _FPDF_AVAILABLE = True
except ImportError:
    _FPDF_AVAILABLE = False


def generate(
    customer_name: str,
    customer_email: str,
    items: list[dict],
    invoice_number: str | None = None,
    payment_days: int = 30,
    sender_name: str = "Nicholas Elvegård",
    sender_email: str = "nicholas@nicholasai.com",
    org_number: str = "",
) -> str:
    """
    Generate a PDF invoice.

    Args:
        customer_name: Customer's full name or company
        customer_email: Customer email
        items: List of line items: [{"description": str, "qty": int, "unit_price": float}]
        invoice_number: Auto-generated if None
        payment_days: Payment due in N days
        sender_name: Your name
        sender_email: Your email
        org_number: Your org number (for Norwegian VAT)

    Returns:
        Path to generated PDF
    """
    if not _FPDF_AVAILABLE:
        raise ImportError("Install fpdf2: pip install fpdf2")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    invoice_number = invoice_number or f"INV-{datetime.now(timezone.utc).strftime('%Y%m')}-{str(uuid.uuid4())[:4].upper()}"
    today = datetime.now(timezone.utc).date()
    due_date = today + timedelta(days=payment_days)

    # Calculate totals
    subtotal = sum(item["qty"] * item["unit_price"] for item in items)
    vat = subtotal * 0.25  # 25% Norwegian VAT
    total = subtotal + vat

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)

    # Header
    pdf.set_font("Helvetica", "B", 20)
    pdf.cell(0, 10, "FAKTURA", ln=True, align="C")
    pdf.ln(5)

    # Sender info
    pdf.set_font("Helvetica", size=10)
    pdf.cell(0, 5, sender_name, ln=True)
    pdf.cell(0, 5, sender_email, ln=True)
    if org_number:
        pdf.cell(0, 5, f"Org.nr: {org_number}", ln=True)
    pdf.ln(5)

    # Invoice meta
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(40, 5, "Fakturanummer:", ln=False)
    pdf.set_font("Helvetica", size=10)
    pdf.cell(0, 5, invoice_number, ln=True)

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(40, 5, "Fakturadato:", ln=False)
    pdf.set_font("Helvetica", size=10)
    pdf.cell(0, 5, str(today), ln=True)

    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(40, 5, "Forfallsdato:", ln=False)
    pdf.set_font("Helvetica", size=10)
    pdf.cell(0, 5, str(due_date), ln=True)
    pdf.ln(5)

    # Customer
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(0, 5, "Faktureres til:", ln=True)
    pdf.set_font("Helvetica", size=10)
    pdf.cell(0, 5, customer_name, ln=True)
    pdf.cell(0, 5, customer_email, ln=True)
    pdf.ln(8)

    # Line items header
    pdf.set_fill_color(230, 230, 230)
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(90, 7, "Beskrivelse", border=1, fill=True)
    pdf.cell(25, 7, "Ant.", border=1, fill=True, align="C")
    pdf.cell(35, 7, "Enhetspris", border=1, fill=True, align="R")
    pdf.cell(35, 7, "Sum", border=1, fill=True, ln=True, align="R")

    # Line items
    pdf.set_font("Helvetica", size=10)
    for item in items:
        line_total = item["qty"] * item["unit_price"]
        pdf.cell(90, 7, item["description"][:60], border=1)
        pdf.cell(25, 7, str(item["qty"]), border=1, align="C")
        pdf.cell(35, 7, f"{item['unit_price']:,.2f} kr", border=1, align="R")
        pdf.cell(35, 7, f"{line_total:,.2f} kr", border=1, ln=True, align="R")

    pdf.ln(3)
    pdf.set_font("Helvetica", size=10)
    pdf.cell(150, 6, "Subtotal:", align="R")
    pdf.cell(35, 6, f"{subtotal:,.2f} kr", ln=True, align="R")
    pdf.cell(150, 6, "MVA (25%):", align="R")
    pdf.cell(35, 6, f"{vat:,.2f} kr", ln=True, align="R")
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(150, 8, "TOTALT:", align="R")
    pdf.cell(35, 8, f"{total:,.2f} kr", ln=True, align="R")

    # Footer
    pdf.ln(10)
    pdf.set_font("Helvetica", size=9)
    pdf.cell(0, 5, f"Betalingsfrist: {payment_days} dager. Kontonummer oppgis på forespørsel.", ln=True)
    pdf.cell(0, 5, "Takk for at du valgte NicholasAI!", ln=True)

    filename = f"{today}_{invoice_number}.pdf"
    output_path = OUTPUT_DIR / filename
    pdf.output(str(output_path))
    logger.info(f"Invoice generated: {output_path}")
    return str(output_path)
