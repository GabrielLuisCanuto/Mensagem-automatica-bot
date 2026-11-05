import asyncio
import csv
import re
import sys
from pathlib import Path
from playwright.async_api import async_playwright, Page

BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
OUTPUTS_DIR = PROJECT_DIR / "outputs"
NUMBERS_FILE = OUTPUTS_DIR / "numeros.txt"
CSV_FILE = OUTPUTS_DIR / "empresas_sem_site.csv"


def clean_brazilian_phone(raw: str) -> str | None:
    if not raw:
        return None
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return None
    # Remove leading 0 (ex: 011986866281 -> 11986866281)
    if digits.startswith("0"):
        digits = digits[1:]
    # Remove leading country code 55 if already present
    if digits.startswith("55") and len(digits) in (12, 13):
        digits = digits[2:]

    # DDD (2) + 9 digits starting with 9 -> Celular / WhatsApp
    if len(digits) == 11 and digits[2] == "9":
        return f"55{digits}"
    # DDD (2) + 8 digits -> Fixo / WhatsApp Business
    elif len(digits) == 10:
        return f"55{digits}"
    return None


def is_mobile_whatsapp(formatted_number: str) -> bool:
    # 55 + DDD (2) + 9 digits starting with 9 = 13 digits
    return len(formatted_number) == 13 and formatted_number[4] == "9"


def load_existing_numbers(file_path: Path) -> set[str]:
    if not file_path.exists():
        return set()
    existing = set()
    for line in file_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digits = "".join(ch for ch in line if ch.isdigit())
        if digits:
            existing.add(digits)
    return existing


def append_number_to_file(file_path: Path, number: str) -> None:
    if not file_path.exists():
        file_path.write_text(
            "# Um numero por linha, somente digitos (codigo do pais + DDD + numero).\n"
            "# Exemplo Brasil: 5511999999999\n\n",
            encoding="utf-8",
        )
    with file_path.open("a", encoding="utf-8") as f:
        f.write(f"{number}\n")


def append_to_csv(csv_path: Path, row: dict) -> None:
    file_exists = csv_path.exists()
    fieldnames = [
        "nome",
        "telefone_original",
        "numero_formatado",
        "tipo",
        "categoria",
        "endereco",
        "url_maps",
        "termo_busca",
    ]
    with csv_path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


async def dismiss_consent(page: Page):
    for btn_text in ["Aceitar tudo", "Aceito", "Concordo", "I agree", "Accept all"]:
        try:
            btn = await page.query_selector(f'button:has-text("{btn_text}")')
            if btn:
                await btn.click()
                await page.wait_for_timeout(1000)
                break
        except Exception:
            pass


async def scrape_google_maps_for_query(
    page: Page,
    query: str,
    max_scrolls: int = 6,
    only_mobile: bool = False,
    existing_numbers: set[str] = None,
) -> list[dict]:
    if existing_numbers is None:
        existing_numbers = set()

    url = f"https://www.google.com/maps/search/{query.replace(' ', '+')}"
    print(f"\n==================================================")
    print(f"Buscando no Google Maps: '{query}'")
    print(f"URL: {url}")
    print(f"==================================================")

    await page.goto(url, wait_until="domcontentloaded", timeout=60000)
    await dismiss_consent(page)

    try:
        await page.wait_for_selector('div[role="feed"]', timeout=15000)
    except Exception:
        print("Aviso: Container de resultados (feed) nao encontrado.")
        return []

    feed = await page.query_selector('div[role="feed"]')
    if not feed:
        print("Feed nulo.")
        return []

    # Scroll para carregar mais empresas
    print(f"Rolando a lista de resultados ({max_scrolls} vezes)...")
    for s in range(max_scrolls):
        await page.evaluate('(feed) => feed.scrollBy(0, 1800)', feed)
        await page.wait_for_timeout(1500)

    # Identificar itens
    cards = await page.query_selector_all('div[role="feed"] > div > div[jsaction]')
    print(f"Total de cartoes carregados: {len(cards)}")

    results = []

    for idx, card in enumerate(cards):
        try:
            # Pegar link principal do local
            place_link = await card.query_selector('a[href*="/maps/place/"]')
            if not place_link:
                continue

            name = await place_link.get_attribute("aria-label")
            href = await place_link.get_attribute("href")
            if not name:
                continue

            card_text = await card.inner_text()

            # 1. Checar se tem botao/link de site no proprio cartao
            links = await card.query_selector_all("a")
            has_website = False
            for l in links:
                h = await l.get_attribute("href")
                aria = (await l.get_attribute("aria-label") or "").lower()
                text = (await l.inner_text() or "").lower()
                if h and "google.com/maps" not in h:
                    has_website = True
                    break
                if "site" in aria or "website" in aria or "website" in text or "site" in text:
                    has_website = True
                    break

            if has_website:
                # Empresa TEM site, ignorar!
                continue

            # Se nao tem site no cartao, vamos tentar extrair o telefone
            phone_raw = None

            # Tenta achar telefone diretamente no texto do cartao
            # Padrao telefone brasileiro: (11) 98888-8888 ou (11) 2222-3333
            phone_matches = re.findall(
                r'(?:\(?\b\d{2}\)?\s*)?(?:9\s*)?\d{4,5}[-\s]?\d{4}', card_text
            )
            for m in phone_matches:
                cleaned = clean_brazilian_phone(m)
                if cleaned:
                    phone_raw = m
                    break

            # Se nao achou telefone no cartao, clica para abrir detalhes
            if not phone_raw:
                await place_link.click()
                await page.wait_for_timeout(2000)

                # Checagem extra de site no painel de detalhes
                website_elem = await page.query_selector('a[data-item-id="authority"]')
                if website_elem:
                    # Tem site no painel de detalhes! Pular.
                    continue

                phone_btn = await page.query_selector('button[data-item-id^="phone:tel:"]')
                if phone_btn:
                    phone_raw = await phone_btn.get_attribute("data-item-id")
                else:
                    phone_aria = await page.query_selector('button[aria-label*="Telefone:"]')
                    if phone_aria:
                        phone_raw = await phone_aria.get_attribute("aria-label")

            if not phone_raw:
                # Nao tem telefone cadastrado no Google Meu Negocio
                continue

            formatted = clean_brazilian_phone(phone_raw)
            if not formatted:
                continue

            is_mobile = is_mobile_whatsapp(formatted)
            if only_mobile and not is_mobile:
                continue

            if formatted in existing_numbers:
                print(f"[DUPLICADO] {name} -> {formatted} ja esta na lista.")
                continue

            existing_numbers.add(formatted)
            tipo_desc = "Celular/WhatsApp" if is_mobile else "Fixo"

            lead = {
                "nome": name,
                "telefone_original": phone_raw,
                "numero_formatado": formatted,
                "tipo": tipo_desc,
                "categoria": "",
                "endereco": "",
                "url_maps": href or "",
                "termo_busca": query,
            }

            # Salvar imediatamente nos arquivos
            append_number_to_file(NUMBERS_FILE, formatted)
            append_to_csv(CSV_FILE, lead)
            results.append(lead)

            print(f"[CAPTURADO] {name} | {tipo_desc}: {formatted} (sem site no Google Meu Negócio)")

        except Exception as e:
            # Continuar para o proximo
            continue

    return results


async def main():
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    existing_numbers = load_existing_numbers(NUMBERS_FILE)
    print(f"Numeros ja existentes no arquivo numeros.txt: {len(existing_numbers)}")

    # Lista de buscas para o nicho de Clinicas, Dentistas e Estetica em Sao Paulo
    queries = [
        "clinica odontologica sao paulo",
        "dentista consultorio sao paulo",
        "clinica de estetica sao paulo",
        "estetica facial corporal sao paulo",
        "harmonizacao orofacial sao paulo",
        "clinica odontologia zona leste sao paulo",
        "clinica estetica zona sul sao paulo",
    ]

    # Pode permitir passar termos via linha de comando: python scraper.py "meu termo"
    if len(sys.argv) > 1:
        queries = [" ".join(sys.argv[1:])]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="pt-BR",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )
        page = await context.new_page()

        total_captured = 0
        for q in queries:
            captured = await scrape_google_maps_for_query(
                page=page,
                query=q,
                max_scrolls=8,
                only_mobile=False,  # Captura WhatsApp e telefones fixos (priorizando ambos no formato 55+DDD+numero)
                existing_numbers=existing_numbers,
            )
            total_captured += len(captured)
            print(f"Termo '{q}' finalizado. Novos contatos encontrados: {len(captured)}")
            await asyncio.sleep(2)

        await browser.close()

    print(f"\n==================================================")
    print(f"Extracao finalizada com sucesso!")
    print(f"Total de novos numeros adicionados: {total_captured}")
    print(f"Arquivo de numeros: {NUMBERS_FILE}")
    print(f"Arquivo CSV com dados completos: {CSV_FILE}")
    print(f"==================================================")


if __name__ == "__main__":
    asyncio.run(main())
