"""
Service agreement and NDA generator.
Triggered by legal_agent when customer says YES.
Outputs Markdown + PDF to outputs/reports/.
"""
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("outputs/reports")


def generate_service_agreement(
    customer_name: str,
    customer_email: str,
    service_description: str,
    monthly_fee: float,
    start_date: str | None = None,
    notice_period_days: int = 30,
) -> str:
    """
    Generate a service agreement as a Markdown file.

    Returns:
        Path to the generated .md file
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    contract_id = str(uuid.uuid4())[:8].upper()
    today = start_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    content = f"""# SERVICEAVTALE — {contract_id}

**Dato**: {today}

---

## Parter

**Leverandør**
Nicholas Elvegård
E-post: nicholas@nicholasai.com

**Kunde**
{customer_name}
E-post: {customer_email}

---

## Tjenestebeskrivelse

{service_description}

---

## Pris og Betalingsbetingelser

- Månedlig honorar: **{monthly_fee:,.0f} kr + MVA**
- Faktureres månedlig i forveien
- Betalingsfrist: 30 dager fra fakturadato
- Forsinkelsesrenter påløper etter forfall (forsinkelsesrenteloven)

---

## Varighet og Oppsigelse

- Avtalen løper fra **{today}**
- Oppsigelsestid: **{notice_period_days} dager** skriftlig varsel fra begge parter
- Første fakturaperiode starter ved oppstart av tjenesten

---

## Immaterielle Rettigheter

- Kode og system levert av leverandør forblir leverandørens eiendom
- Kunde får bruksrett til systemet så lenge avtalen er aktiv
- Ved avslutning: leverandør eksporterer kundedata innen 14 dager

---

## Konfidensialitet

Begge parter forplikter seg til å behandle informasjon om hverandres virksomhet konfidensielt.
Denne forpliktelsen gjelder i avtaleperioden og 2 år etter avtalens utløp.

---

## Ansvarsbegrensning

Leverandørens ansvar er begrenset til 3 månedlige honorar.
Leverandør er ikke ansvarlig for indirekte tap eller tapte inntekter.

---

## Tvister

Eventuelle tvister løses etter norsk rett med Bodø tingrett som verneting.

---

## Signaturer

**Leverandør**: _______________________  Dato: ___________
Nicholas Elvegård

**Kunde**: _______________________  Dato: ___________
{customer_name}
"""

    filename = f"{today}_avtale_{contract_id}.md"
    path = OUTPUT_DIR / filename
    path.write_text(content, encoding="utf-8")
    logger.info(f"Service agreement generated: {path}")
    return str(path)


def generate_nda(party_a: str, party_b: str, purpose: str) -> str:
    """Generate a simple NDA as Markdown."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    contract_id = str(uuid.uuid4())[:8].upper()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    content = f"""# TAUSHETSERKLÆRING (NDA) — {contract_id}

**Dato**: {today}

## Parter
- **Part A**: {party_a}
- **Part B**: {party_b}

## Formål
Partene inngår denne avtalen i forbindelse med: {purpose}

## Konfidensialitetsforpliktelse
Ingen av partene skal røpe konfidensiell informasjon til tredjeparter uten skriftlig samtykke.
Konfidensiell informasjon inkluderer: forretningsinformasjon, tekniske løsninger, kundeinformasjon, prisstrukturer.

## Varighet
Denne avtalen gjelder i 3 år fra signeringsdato.

## Signaturer
Part A: _______________________ Dato: ___________
Part B: _______________________ Dato: ___________
"""

    filename = f"{today}_nda_{contract_id}.md"
    path = OUTPUT_DIR / filename
    path.write_text(content, encoding="utf-8")
    return str(path)
