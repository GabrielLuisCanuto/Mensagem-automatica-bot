from pathlib import Path
from urllib.parse import urlencode
import sys
import time
import webbrowser

try:
    import pyautogui
except ImportError:
    pyautogui = None

BASE_DIR = Path(__file__).resolve().parent
NUMBERS_FILE = BASE_DIR / "numeros.txt"

# ==============================================================================
# CONFIGURACOES DO BOT
# ==============================================================================
# Mensagem a ser enviada
MESSAGE = "Olá tudo bem?"

# A partir de qual contato iniciar o envio (80 = comecar do contato 80 em diante)
# Pode ser alterado aqui ou passado no terminal: python bot_whatsapp_web.py 80
START_INDEX = 80

# Ate qual contato enviar (None para ir ate o final da lista)
END_INDEX = None

# Se True, filtra e envia APENAS para telefones celulares (9 digitos no WhatsApp).
# Telefones fixos (8 digitos) quase nunca possuem WhatsApp e geram erro de numero invalido.
ONLY_MOBILE = True

# Tempo de espera inicial (em segundos) para o WhatsApp Web abrir e carregar a conversa
PAGE_LOAD_WAIT_SECONDS = 20

# Tentativas de envio / confirmacao de erro
ENTER_RETRIES = 3
RETRY_INTERVAL_SECONDS = 2

# Intervalo minimo de seguranca entre envios (em segundos)
MIN_INTERVAL_SECONDS = 5

# Se True, continua para o proximo contato 100% no automatico sem parar o codigo
AUTO_NEXT = True

# Se True, fecha a aba da conversa atual com Ctrl+W apos enviar ou confirmar o erro.
# Recomendado: TRUE (evita acumular centenas de abas abertas no navegador).
# DICA: Deixe uma aba principal do WhatsApp Web ja aberta e logada antes de iniciar!
CLOSE_TAB_AFTER_SEND = True
# ==============================================================================


def is_mobile_number(digits: str) -> bool:
    """Verifica se o numero e um celular brasileiro (9 digitos apos o DDD)."""
    # 55 + DDD (2 digitos) + 9 + 8 digitos = 13 digitos
    if len(digits) == 13 and digits.startswith("55") and digits[4] == "9":
        return True
    # Sem codigo do pais: DDD (2) + 9 + 8 = 11 digitos
    if len(digits) == 11 and digits[2] == "9":
        return True
    return False


def load_numbers(path: Path, only_mobile: bool = ONLY_MOBILE) -> tuple[list[str], int]:
    """Carrega os numeros do arquivo, opcionalmente filtrando apenas celulares."""
    if not path.exists():
        path.write_text(
            "# Coloque um numero por linha, com codigo do pais e DDD.\n"
            "# Exemplo Brasil: 5511999999999\n",
            encoding="utf-8",
        )
        return [], 0

    numbers = []
    skipped_landlines = 0

    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        digits = "".join(ch for ch in value if ch.isdigit())
        if not 10 <= len(digits) <= 15:
            continue

        if only_mobile and not is_mobile_number(digits):
            skipped_landlines += 1
            continue

        numbers.append(digits)

    return numbers, skipped_landlines


def send_and_handle_screen(
    url: str,
    wait_seconds: int = PAGE_LOAD_WAIT_SECONDS,
    retries: int = ENTER_RETRIES,
    retry_delay: int = RETRY_INTERVAL_SECONDS,
    close_tab: bool = CLOSE_TAB_AFTER_SEND,
) -> None:
    webbrowser.open(url)

    if pyautogui is None:
        print("Aviso: PyAutoGUI nao esta instalado. Instale com: pip install pyautogui")
        return

    print(f"Aguardando {wait_seconds}s para o WhatsApp Web carregar...")
    for remaining in range(wait_seconds, 0, -1):
        print(f"\r[Aguardando] Processando em {remaining:2d} segundos... ", end="", flush=True)
        time.sleep(1)
    print("\r[Executando] Enviando mensagem ou confirmando erro...            ")

    # Tenta enviar a mensagem ou confirmar o botao "OK" do erro
    for attempt in range(1, retries + 1):
        print(f"  -> Tentativa {attempt}/{retries}: Disparando Enter e confirmacao de tela...")
        # 1. Pressiona Enter (se a conversa abriu, envia o texto; se apareceu pop-up de erro com foco no OK, confirma)
        pyautogui.press("enter")
        time.sleep(1)

        # 2. Se for a tela de erro "Numero invalido", Esc fecha o pop-up caso o Enter nao tenha sido focado
        pyautogui.press("esc")
        time.sleep(0.5)

        # 3. Enter adicional para confirmar qualquer caixa restante
        pyautogui.press("enter")

        if attempt < retries:
            time.sleep(retry_delay)

    # Fecha a aba para nao sobrecarregar o navegador com centenas de abas
    if close_tab:
        print("  -> Fechando aba da conversa (Ctrl+W)...")
        time.sleep(1)
        pyautogui.hotkey("ctrl", "w")
        time.sleep(0.5)


def main() -> None:
    # Permite passar o indice inicial pela linha de comando: python bot_whatsapp_web.py 80
    start_index = START_INDEX
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        start_index = int(sys.argv[1])

    numbers, skipped_landlines = load_numbers(NUMBERS_FILE, only_mobile=ONLY_MOBILE)
    if not numbers:
        print(f"Nenhum numero valido encontrado em: {NUMBERS_FILE}")
        return

    total_contatos = len(numbers)
    start_pos = max(1, min(start_index, total_contatos))
    end_pos = total_contatos if END_INDEX is None else min(END_INDEX, total_contatos)
    total_a_enviar = max(0, end_pos - start_pos + 1)

    if pyautogui is None:
        print("Instale a dependencia pyautogui para envio automatico com Enter:")
        print("pip install pyautogui")
        return

    print("=" * 65)
    print("      BOT WHATSAPP WEB - ENVIO E TRATAMENTO DE ERROS")
    print("=" * 65)
    print(f"- Total de contatos na lista: {total_contatos}")
    print(f"- Ponto de partida: Contato {start_pos} ate {end_pos} ({total_a_enviar} contatos para enviar)")
    if ONLY_MOBILE:
        print(f"- Filtro Celulares: ATIVADO ({skipped_landlines} telefones fixos ignorados)")
    print(f"- Mensagem padrao: '{MESSAGE}'")
    print(f"- Tempo de espera por contato: {PAGE_LOAD_WAIT_SECONDS} segundos")
    print(f"- Tratamento de erro ('Numero invalido'): Confirmar OK e fechar pop-up")
    print(f"- Fechar aba apos envio (Ctrl+W): {'SIM' if CLOSE_TAB_AFTER_SEND else 'NAO'}")
    print(f"- Modo automatico (AUTO_NEXT): {'ATIVADO (sem paradas)' if AUTO_NEXT else 'MANUAL'}")
    print("=" * 65)
    print("IMPORTANTE:")
    print("1. Deixe uma aba do WhatsApp Web aberta e logada no seu navegador padrao.")
    print("2. Nao mexa no teclado/mouse enquanto o bot estiver processando.")
    print("3. Pressione Ctrl+C no terminal a qualquer momento para pausar/encerrar.")
    print("=" * 65)

    last_opened_at = None
    for index, number in enumerate(numbers, start=1):
        if index < start_pos:
            continue
        if end_pos is not None and index > end_pos:
            break

        if last_opened_at is not None:
            elapsed = time.monotonic() - last_opened_at
            remaining = MIN_INTERVAL_SECONDS - elapsed
            if remaining > 0:
                print(f"\nAguardando {remaining:.0f}s de intervalo entre contatos...")
                time.sleep(remaining)

        query = urlencode({"phone": number, "text": MESSAGE})
        url = f"https://web.whatsapp.com/send?{query}"
        print(f"\n({index}/{total_contatos}) Processando contato: {number}...")

        send_and_handle_screen(
            url,
            wait_seconds=PAGE_LOAD_WAIT_SECONDS,
            retries=ENTER_RETRIES,
            retry_delay=RETRY_INTERVAL_SECONDS,
            close_tab=CLOSE_TAB_AFTER_SEND,
        )
        last_opened_at = time.monotonic()

        is_last = (index == end_pos)
        if not is_last:
            if AUTO_NEXT:
                print("Contato finalizado. Avancando para o proximo automaticamente...")
            else:
                input("\nPressione Enter para ir ao proximo contato (Ctrl+C encerra): ")

    print("\n" + "=" * 65)
    print(f"  PROCESSAMENTO CONCLUIDO (DO CONTATO {start_pos} AO {end_pos})!")
    print("=" * 65)


if __name__ == "__main__":
    main()
