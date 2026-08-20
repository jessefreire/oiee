"""Ícone na bandeja do sistema com menu (Configurações / Sair)."""
import pystray
from PIL import Image, ImageDraw

ACCENT = (10, 132, 255, 255)


def _make_icon() -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # microfone estilizado
    d.ellipse((17, 6, 47, 36), fill=ACCENT)
    d.rounded_rectangle((14, 44, 50, 49), radius=2, fill=ACCENT)
    d.rounded_rectangle((29, 34, 35, 52), radius=3, fill=ACCENT)
    return img


def start_tray(on_settings, on_quit) -> None:
    icon = pystray.Icon(
        "flow-local",
        _make_icon(),
        "Flow Local — ditado por voz",
        menu=pystray.Menu(
            # default=True faz o clique esquerdo abrir as configurações
            pystray.MenuItem("Configurações", lambda: on_settings(), default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Sair", lambda: on_quit()),
        ),
    )
    icon.run()
