"""Teste ponta a ponta: gravação simulada -> transcrição -> inserção.

Roda sem teclado/microfone reais: usa o wav sintetizado pelo Windows
(scripts/make_test_audio.ps1) como se fosse a gravação do microfone.

Uso:  python tests/test_pipeline.py
"""
import os
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

import flow.engine as engine_mod  # noqa: E402
from flow import typer  # noqa: E402
from flow.commands import parse_commands  # noqa: E402
from flow.config import Config  # noqa: E402
from flow.engine import DictationEngine  # noqa: E402
from flow.transcriber import Transcriber  # noqa: E402
from flow.qt_app import CtrlWinHotkey  # noqa: E402
from PySide6.QtCore import QCoreApplication  # noqa: E402

WAV = os.path.join(os.environ.get("TEMP", "/tmp"), "flow_test.wav")
REAL_RECORDER = engine_mod.Recorder


def load_wav(path):
    with wave.open(path, "rb") as w:
        rate = w.getframerate()
        data = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    return data, rate


class FakeOverlay:
    def __init__(self):
        self.events = []

    def show_recording(self, recorder=None):
        self.events.append("recording")

    def show_transcribing(self):
        self.events.append("transcribing")

    def show_error(self, msg):
        self.events.append(("error", msg))

    def hide(self):
        self.events.append("hide")


def make_fake_recorder(audio, real_rate):
    """Classe que imita o Recorder mas devolve áudio pré-gravado."""
    class FakeRecorder:
        resample = staticmethod(REAL_RECORDER.resample)
        auto_gain = staticmethod(REAL_RECORDER.auto_gain)

        def __init__(self, device=None, rate=16000):
            self.audio = audio
            self.rate = real_rate

        def start(self):
            pass

        def stop(self):
            audio, self.audio = self.audio, np.zeros(0, dtype=np.float32)
            return audio

    return FakeRecorder


def run_dictation(audio, rate, **cfg_kwargs):
    """Roda um ditado completo e devolve (texto inserido, overlay, engine)."""
    captured = {}
    original = typer.type_text
    typer.type_text = lambda t, mode="type": captured.update(text=t, mode=mode)
    try:
        overlay = FakeOverlay()
        cfg = Config(model="tiny", language="pt", **cfg_kwargs)
        engine = DictationEngine(cfg, overlay)
        engine_mod.Recorder = make_fake_recorder(audio, rate)
        engine._stop.set()  # "solta" a tecla imediatamente
        engine._recording = True
        engine._dictate()
    finally:
        typer.type_text = original
        engine_mod.Recorder = REAL_RECORDER
    return captured, overlay, engine


def test_dictation_transcribes_and_types():
    if not os.path.exists(WAV):
        print(f"[SKIP] wav de teste não encontrado: {WAV}")
        return
    audio, rate = load_wav(WAV)
    captured, overlay, engine = run_dictation(audio, rate)

    assert "recording" in overlay.events, overlay.events
    assert "transcribing" in overlay.events, overlay.events
    assert overlay.events[-1] == "hide", overlay.events
    assert captured.get("mode") == "paste", captured
    assert len(captured.get("text", "")) > 10, f"texto curto demais: {captured!r}"
    assert engine._recording is False
    print(f"OK: ditado -> {captured['text']!r}")


def test_silence_is_ignored():
    silence = np.zeros(8000, dtype=np.float32)
    captured, overlay, _ = run_dictation(silence, 16000)
    assert captured == {}, f"silêncio não deveria digitar nada: {captured!r}"
    assert "hide" in overlay.events
    print("OK: silêncio ignorado")


# ------------------------------------------------------------------ comandos

def test_commands_punctuation_pt():
    clean, actions = parse_commands("hoje virgula vamos sair ponto final", "pt")
    assert clean == "hoje, vamos sair.", (clean, actions)
    assert actions == []


def test_commands_punctuation_variants():
    clean, actions = parse_commands("sera ponto de interrogação ponto de exclamação", "pt")
    assert clean == "sera?!", (clean, actions)


def test_commands_action_mid_utterance():
    clean, actions = parse_commands("vamos sair e apagar a ultima palavra", "pt")
    assert clean == "vamos sair e", (clean, actions)
    assert actions == ["delete_last_word"]


def test_commands_pure_action():
    clean, actions = parse_commands("apagar ultima palavra", "pt")
    assert clean == "" and actions == ["delete_last_word"], (clean, actions)


def test_commands_pure_action_with_whisper_period():
    # Whisper costuma colocar ponto no fim da fala
    clean, actions = parse_commands("apagar ultima palavra.", "pt")
    assert clean == "" and actions == ["delete_last_word"], (clean, actions)


def test_commands_newline_and_paragraph():
    clean, actions = parse_commands("primeira linha nova linha segunda novo paragrafo terceira", "pt")
    assert clean == "primeira linha\nsegunda\n\nterceira", (clean, actions)
    assert actions == []


def test_commands_cursor():
    clean, actions = parse_commands("mover cursor para cima e acesse a pagina", "pt")
    assert actions == ["cursor_up"], (clean, actions)
    assert clean == "e acesse a pagina", clean


def test_commands_url_style():
    clean, _ = parse_commands("acesse https dois pontos barra barra site ponto com", "pt")
    assert "https://" in clean, clean


def test_commands_do_not_match_inside_words():
    clean, actions = parse_commands("o paragrafo do texto", "pt")
    assert clean == "o paragrafo do texto" and actions == [], (clean, actions)


def test_commands_english():
    clean, actions = parse_commands("delete the last word and type hello comma world", "en")
    assert clean == "and type hello, world", (clean, actions)
    assert actions == ["delete_last_word"]


# ------------------------------------------------------- atalho (chord/toggle)

def _fake_event(name):
    return type("Ev", (), {"name": name})()


def test_hold_single_key():
    silence = np.zeros(1600, dtype=np.float32)  # < mínimo: não digita nada
    cfg = Config(model="tiny", language="pt", hotkey="right alt", hotkey_mode="hold")
    overlay = FakeOverlay()
    engine = DictationEngine(cfg, overlay)
    engine_mod.Recorder = make_fake_recorder(silence, 16000)
    try:
        engine._on_press(_fake_event("right alt"))
        assert engine._recording is True
        engine._on_release(_fake_event("right alt"))
        assert engine._stop.is_set()
    finally:
        engine_mod.Recorder = REAL_RECORDER
    print("OK: hold tecla única")


def test_hold_chord_needs_all_keys():
    silence = np.zeros(1600, dtype=np.float32)
    cfg = Config(model="tiny", language="pt", hotkey="ctrl+win", hotkey_mode="hold")
    overlay = FakeOverlay()
    engine = DictationEngine(cfg, overlay)
    engine_mod.Recorder = make_fake_recorder(silence, 16000)
    try:
        # só ctrl pressionado: não inicia
        engine._on_press(_fake_event("ctrl"))
        assert engine._recording is False
        # ctrl + win: inicia
        engine._on_press(_fake_event("windows"))
        assert engine._recording is True
        # soltou win: para
        engine._on_release(_fake_event("windows"))
        assert engine._stop.is_set()
    finally:
        engine_mod.Recorder = REAL_RECORDER
    print("OK: hold com combinação")


def test_toggle_mode():
    silence = np.zeros(1600, dtype=np.float32)
    cfg = Config(model="tiny", language="pt", hotkey="ctrl+space", hotkey_mode="toggle")
    overlay = FakeOverlay()
    engine = DictationEngine(cfg, overlay)
    engine_mod.Recorder = make_fake_recorder(silence, 16000)
    try:
        # primeiro toque: liga (combinação completa no 2º evento)
        engine._on_press(_fake_event("ctrl"))
        assert engine._recording is False
        engine._on_press(_fake_event("space"))
        assert engine._recording is True
        assert not engine._stop.is_set()
        # soltar teclas não desliga (modo alternar)
        engine._on_release(_fake_event("space"))
        engine._on_release(_fake_event("ctrl"))
        assert engine._recording is True
        # segundo toque: desliga e processa
        engine._on_press(_fake_event("ctrl"))
        engine._on_press(_fake_event("space"))
        assert engine._stop.is_set()
    finally:
        engine_mod.Recorder = REAL_RECORDER
    print("OK: modo alternar")


def test_recorder_flattens_2d_frames():
    """Bug real: o sounddevice entrega (N, 1) e o Recorder precisa devolver 1D
    (senão a transcrição e a forma de onda quebram)."""
    rec = engine_mod.Recorder()
    block = np.arange(500, dtype=np.float32).reshape(-1, 1)  # (500, 1)
    with rec._lock:
        rec._frames = [block.copy(), block.copy()]
    rec.rate = 16000
    recent = rec.recent(0.2)
    audio = rec.stop()
    assert recent.ndim == 1 and recent.shape[0] == 1000, recent.shape
    assert audio.ndim == 1 and audio.shape[0] == 1000, audio.shape
    print("OK: Recorder achata (N,1) -> 1D")


def test_recorder_recent_returns_last_chunk():
    rec = engine_mod.Recorder()  # real, sem abrir stream
    block = np.arange(1000, dtype=np.float32)
    for _ in range(30):
        with rec._lock:
            rec._frames.append(block.copy())
    rec.rate = 16000
    recent = rec.recent(0.1)  # ~1600 amostras = últimos 2 blocos
    assert recent.shape[0] == 2000, recent.shape
    assert recent[-1] == 999.0  # últimos blocos, não os primeiros
    empty = engine_mod.Recorder().recent(0.1)
    assert empty.size == 0
    print("OK: recent() do Recorder")


def test_chord_keys_normalization():
    cfg = Config(model="tiny", language="pt", hotkey="ctrl+win")
    overlay = FakeOverlay()
    engine = DictationEngine(cfg, overlay)
    assert engine._chord_keys() == ["ctrl", "windows"]
    print("OK: normalização do chord")


def test_ctrl_win_first_double_tap_does_not_need_keyboard_hook():
    """O novo atalho consulta as teclas nativamente, sem evento de mouse."""
    _app = QCoreApplication.instance() or QCoreApplication([])
    hotkey = CtrlWinHotkey(None)
    starts = []
    hotkey.start_requested.connect(lambda: starts.append(True))
    # Primeiro toque curto: aguarda uma possível segunda batida.
    hotkey._process_chord_state(True)
    hotkey._process_chord_state(False)
    # Segundo toque curto: inicia o modo travado imediatamente.
    hotkey._process_chord_state(True)
    hotkey._process_chord_state(False)
    assert starts == [True], starts
    hotkey.close()
    print("OK: primeiro toque duplo Ctrl+Win inicia sem clique")


def test_new_defaults_use_ctrl_win_and_paste():
    cfg = Config()
    assert cfg.hotkey == "ctrl+win" and cfg.hotkey_mode == "hold"
    assert cfg.output_mode == "paste"
    print("OK: padrão Ctrl+Win + colar")


def test_vocabulary_becomes_whisper_context():
    transcriber = Transcriber("tiny", "pt", "Codex, Wispr Flow, AcmeTech")
    prompt = transcriber._initial_prompt()
    assert "português brasileiro" in prompt and "AcmeTech" in prompt
    assert Transcriber("tiny", "pt")._initial_prompt() is None
    print("OK: vocabulário vira contexto do Whisper")


def test_user_profile_learns_and_reuses_confirmed_correction():
    cfg = Config(vocabulary="Oiee")
    learned = cfg.learn_corrections("fale com jece sobre oie", "fale com Jesse sobre Oiee")
    assert learned == 2, cfg.corrections
    assert cfg.apply_corrections("jece abriu o oie") == "Jesse abriu o Oiee"
    context = cfg.learned_vocabulary()
    assert "Jesse" in context and "Oiee" in context
    print("OK: perfil aprende correções confirmadas localmente")


def test_auto_gain_boosts_quiet_voice_without_changing_silence():
    quiet = np.full(1600, 0.02, dtype=np.float32)
    boosted = REAL_RECORDER.auto_gain(quiet)
    assert float(np.max(boosted)) > 0.1
    silence = np.zeros(1600, dtype=np.float32)
    assert np.array_equal(REAL_RECORDER.auto_gain(silence), silence)
    print("OK: ganho automático seguro")


def test_engine_executes_voice_commands():
    """Engine: transcrição com comando -> digita texto limpo + executa ação."""
    silence = np.zeros(16000, dtype=np.float32)  # 1s, acima do mínimo
    captured_text, captured_actions = {}, {}
    orig_type, orig_apply = typer.type_text, typer.apply_actions
    typer.type_text = lambda t, mode="type": captured_text.update(text=t, mode=mode)
    typer.apply_actions = lambda acts: captured_actions.update(actions=acts)
    try:
        overlay = FakeOverlay()
        cfg = Config(model="tiny", language="pt")
        engine = DictationEngine(cfg, overlay)
        engine.transcriber.transcribe = lambda audio: "vamos sair e apagar a ultima palavra"
        engine_mod.Recorder = make_fake_recorder(silence, 16000)
        engine._stop.set()
        engine._recording = True
        engine._dictate()
    finally:
        typer.type_text, typer.apply_actions = orig_type, orig_apply
        engine_mod.Recorder = REAL_RECORDER
    assert captured_text.get("text") == "vamos sair e", captured_text
    assert captured_actions.get("actions") == ["delete_last_word"], captured_actions
    print("OK: comandos por voz no engine")


if __name__ == "__main__":
    test_dictation_transcribes_and_types()
    test_silence_is_ignored()
    test_commands_punctuation_pt()
    test_commands_punctuation_variants()
    test_commands_action_mid_utterance()
    test_commands_pure_action()
    test_commands_pure_action_with_whisper_period()
    test_commands_newline_and_paragraph()
    test_commands_cursor()
    test_commands_url_style()
    test_commands_do_not_match_inside_words()
    test_commands_english()
    test_engine_executes_voice_commands()
    test_hold_single_key()
    test_hold_chord_needs_all_keys()
    test_toggle_mode()
    test_chord_keys_normalization()
    test_ctrl_win_first_double_tap_does_not_need_keyboard_hook()
    test_new_defaults_use_ctrl_win_and_paste()
    test_vocabulary_becomes_whisper_context()
    test_user_profile_learns_and_reuses_confirmed_correction()
    test_auto_gain_boosts_quiet_voice_without_changing_silence()
    test_recorder_recent_returns_last_chunk()
    test_recorder_flattens_2d_frames()
    print("\nTodos os testes passaram!")
