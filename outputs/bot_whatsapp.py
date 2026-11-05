from pathlib import Path
from urllib.parse import quote
import time
import webbrowser

try:
    import pyautogui
except ImportError:
    pyautogui = None

BASE_DIR = Path(__file__).resolve().parent
NUMBERS_FILE = BASE_DIR / "numeros.txt"
MESSAGE = "Olá"
MIN_INTERVAL_SECONDS = 5
APP_CONFIRMATION_WAIT_SECONDS = 3


def load_numbers(path: Path) -> list[str]:
    if not path.exists():
        path.write_text(
            "# Coloque um numero por linha, com codigo do pais e DDD.\n"
            "# Exemplo Brasil: 5511999999999\n",
            encoding="utf-8",
        )
        return []

    numbers = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        digits = "".join(ch for ch in value if ch.isdigit())
        if len(digits) < 10 or len(digits) > 15:
            print(f"Ignorando numero invalido: {value}")
            continue
        numbers.append(digits)
    return numbers


def open_whatsapp_link(url: str) -> None:
    webbrowser.open(url)
    if pyautogui is None:
        print("PyAutoGUI nao esta instalado. Instale com: python -m pip install pyautogui")
        return

    # A janela de confirmacao precisa estar em foco. Na confirmacao mostrada,
    # Cancelar fica selecionado; Shift+Tab seleciona Abrir WhatsApp.
    time.sleep(APP_CONFIRMATION_WAIT_SECONDS)
    pyautogui.hotkey("shift", "tab")
    pyautogui.press("enter")
    pyautogui.sleep(2)
    pyautogui.press("enter")


def main() -> None:
    numbers = load_numbers(NUMBERS_FILE)
    if not numbers:
        print(f"Adicione os numeros em: {NUMBERS_FILE}")
        return

    if pyautogui is None:
        print("Instale a dependencia para aceitar a confirmacao de abrir o WhatsApp:")
        print("python -m pip install pyautogui")
        return

    print(f"{len(numbers)} numero(s) carregado(s).")
    print("Cada conversa sera aberta com OLA preenchido.")
    print("A confirmacao para abrir o WhatsApp sera aceita apos 3 segundos.")
    print("Confira o contato e clique em Enviar manualmente no WhatsApp.")
    print("Use somente com pessoas que aceitaram receber contato.")

    last_opened_at = None
    for index, number in enumerate(numbers, start=1):
        if last_opened_at is not None:
            remaining = MIN_INTERVAL_SECONDS - (time.monotonic() - last_opened_at)
            if remaining > 0:
                print(f"Aguardando {remaining:.0f} segundos para respeitar o intervalo...")
                time.sleep(remaining)

        url = f"https://wa.me/{number}?text={quote(MESSAGE)}"
        print(f"({index}/{len(numbers)}) Abrindo conversa para {number}...")
        open_whatsapp_link(url)
        last_opened_at = time.monotonic()

        if index < len(numbers):
            input("Depois de revisar/enviar (ou pular) esta conversa, pressione Enter para continuar. Ctrl+C encerra. ")

    print("Lista concluida.")


if __name__ == "__main__":
    main()
