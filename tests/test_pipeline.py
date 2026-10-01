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
from flow.cleanup import cleanup  # noqa: E402
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


def _make_hotkey():
    _app = QCoreApplication.instance() or QCoreApplication([])
    hotkey = CtrlWinHotkey(None)
    starts, stops = [], []
    hotkey.start_requested.connect(lambda: starts.append(True))
    hotkey.stop_requested.connect(lambda: stops.append(True))
    return hotkey, starts, stops


def _tap(hotkey):
    """Um toque curto: pressiona e solta (rápido demais p/ virar hold)."""
    hotkey._process_chord_state(True)
    hotkey._process_chord_state(False)


def test_double_tap_starts_and_single_press_stops():
    hk, starts, stops = _make_hotkey()
    _tap(hk)
    _tap(hk)
    assert starts == [True] and stops == [], (starts, stops)
    # um toque para parar: soltura não pode armar outro duplo
    hk._process_chord_state(True)
    assert stops == [True], (starts, stops)
    hk._process_chord_state(False)
    # um tap isolado depois de parar não faz nada (prova que não armou)
    _tap(hk)
    assert starts == [True] and stops == [True], (starts, stops)
    hk.close()
    print("OK: duplo inicia, toque para, sem reiniciar")


def test_double_tap_to_stop_does_not_restart():
    """Parar com toque duplo não pode reiniciar a gravação (bug real)."""
    hk, starts, stops = _make_hotkey()
    _tap(hk)
    _tap(hk)
    assert starts == [True]
    # toque duplo para parar: 1º toque para, 2º não pode iniciar
    hk._process_chord_state(True)   # para
    hk._process_chord_state(False)  # soltura ignorada
    hk._process_chord_state(True)   # 2º toque: seria "tap1" se tivesse armado
    hk._process_chord_state(False)
    assert stops == [True] and starts == [True], (starts, stops)
    hk.close()
    print("OK: parar com toque duplo não reinicia")


def test_slow_first_tap_then_quick_second_starts():
    """Tap1 lento (vira hold) + tap2 rápido alterna (antes ficava órfão)."""
    hk, starts, stops = _make_hotkey()
    hk._process_chord_state(True)
    hk._start_hold_if_still_down()  # 250ms com o acorde segurado
    assert starts == [True], (starts, stops)
    hk._process_chord_state(False)  # solta: para e arma o duplo
    assert stops == [True], (starts, stops)
    _tap(hk)
    assert starts == [True, True] and stops == [True], (starts, stops)
    hk.close()
    print("OK: tap lento + tap rápido alterna")


def test_hold_starts_on_timer_and_stops_on_release():
    hk, starts, stops = _make_hotkey()
    hk._process_chord_state(True)
    hk._start_hold_if_still_down()
    assert starts == [True], (starts, stops)
    hk._process_chord_state(False)
    assert stops == [True] and starts == [True], (starts, stops)
    hk.close()
    print("OK: segurar inicia, soltar para")


def test_windows_combo_never_starts_recording():
    """Ctrl+Win+setas/D (desktops virtuais) não vira ditado nem toggle."""
    hk, starts, stops = _make_hotkey()
    # hold: acorde "sujo" não inicia gravação
    hk._process_chord_state(True)
    hk._process_chord_state(True, True)   # tecla extra junto
    hk._start_hold_if_still_down()
    hk._process_chord_state(False)
    # dois combos seguidos não contam como toque duplo
    for _ in range(2):
        hk._process_chord_state(True)
        hk._process_chord_state(True, True)
        hk._process_chord_state(False)
    assert starts == [] and stops == [], (starts, stops)
    # e o gesto volta a funcionar logo depois do combo
    _tap(hk)
    _tap(hk)
    assert starts == [True] and stops == [], (starts, stops)
    hk.close()
    print("OK: combo do Windows não inicia ditado nem toggle")


def test_combo_interrupts_hold_recording():
    """Se o hold já gravando e surge tecla extra, para na hora."""
    hk, starts, stops = _make_hotkey()
    hk._process_chord_state(True)
    hk._start_hold_if_still_down()
    assert starts == [True]
    hk._process_chord_state(True, True)   # Ctrl+Win+D em cima da gravação
    assert stops == [True], stops
    hk._process_chord_state(False)        # soltura suja: não conta como tap
    _tap(hk)
    assert starts == [True] and stops == [True], (starts, stops)
    hk.close()
    print("OK: combo interrompe gravação sem virar toggle")


def test_clean_tap_before_combo_does_not_complete_double():
    """Um tap limpo logo antes do combo não pode ser 'o primeiro toque'."""
    hk, starts, stops = _make_hotkey()
    _tap(hk)                              # tap limpo (arma o duplo)
    hk._process_chord_state(True)         # combo começa...
    hk._process_chord_state(True, True)
    hk._process_chord_state(False)        # soltura suja desarma
    _tap(hk)                              # novo tap limpo = 1º de novo
    assert starts == [], (starts, stops)
    _tap(hk)                              # 2º tap: inicia
    assert starts == [True], (starts, stops)
    hk.close()
    print("OK: tap limpo + combo não completa o duplo-toque")


def test_new_defaults_use_ctrl_win_and_paste():
    cfg = Config()
    assert cfg.hotkey == "ctrl+win" and cfg.hotkey_mode == "hold"
    assert cfg.output_mode == "paste"
    print("OK: padrão Ctrl+Win + colar")


def test_vocabulary_becomes_whisper_hotwords():
    """Bug real: no faster-whisper o initial_prompt anula os hotwords.

    O vocabulário precisa entrar como hotwords, sem nenhum initial_prompt.
    """
    captured = {}

    class _Segments:
        def __iter__(self):
            return iter([type("Seg", (), {"text": " texto"})()])

    class _Model:
        def transcribe(self, audio, **kwargs):
            captured.update(kwargs)
            return _Segments(), None

    with_vocab = Transcriber("tiny", "pt", "Codex, Oiee, AcmeTech")
    with_vocab.load = lambda: _Model()
    assert with_vocab.transcribe(np.zeros(1600, dtype=np.float32)) == "texto"
    assert captured["hotwords"] == "Codex, Oiee, AcmeTech", captured
    assert "initial_prompt" not in captured, captured.keys()

    captured.clear()
    plain = Transcriber("tiny", "pt")
    plain.load = lambda: _Model()
    plain.transcribe(np.zeros(1600, dtype=np.float32))
    assert captured["hotwords"] is None and "initial_prompt" not in captured, captured
    print("OK: vocabulário vira hotwords, sem initial_prompt")


def test_user_profile_learns_and_reuses_confirmed_correction():
    cfg = Config(vocabulary="Oiee")
    learned = cfg.learn_corrections("fale com jece sobre oie", "fale com Jesse sobre Oiee")
    assert learned == 2, cfg.corrections
    assert cfg.apply_corrections("jece abriu o oie") == "Jesse abriu o Oiee"
    context = cfg.learned_vocabulary()
    assert "Jesse" in context and "Oiee" in context
    print("OK: perfil aprende correções confirmadas localmente")


def test_preload_runs_load_in_background():
    """preload() dispara load() em thread daemon sem bloquear nem baixar nada aqui."""
    import threading
    cfg = Config(model="tiny", language="pt")
    engine = DictationEngine(cfg, FakeOverlay())
    done = threading.Event()
    engine.transcriber.load = lambda: done.set()
    engine.preload()
    assert done.wait(5), "preload() não executou load() em background"
    print("OK: pré-carregamento do modelo em background")


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
    # a limpeza automática capitaliza; o comando remove a última frase
    assert captured_text.get("text") == "Vamos sair e", captured_text
    assert captured_actions.get("actions") == ["delete_last_word"], captured_actions
    print("OK: comandos por voz no engine")


# ------------------------------------------------------------------ limpeza (Tier 1)
def test_cleanup_removes_fillers_pt():
    out = cleanup("hum, então vamos ah, fazer isso", "pt")
    assert out == "Então vamos, fazer isso", out
    print("OK: fillers PT removidos")


def test_cleanup_removes_fillers_en():
    out = cleanup("Um, I uh want to go", "en")
    assert out == "I want to go", out
    print("OK: fillers EN removidos")


def test_cleanup_auto_keeps_article_um():
    # em "auto" o "um" é artigo de verdade e não pode sumir
    assert cleanup("um carro vermelho", "auto") == "Um carro vermelho"
    print("OK: 'auto' não remove artigo")


def test_cleanup_dedupes_repetitions():
    assert cleanup("Eu vou sim. Eu vou sim.", "pt") == "Eu vou sim."
    assert cleanup("eu eu eu gosto de café", "pt") == "Eu gosto de café"
    assert cleanup("que que isso", "pt") == "Que que isso"  # 2x é legítimo
    print("OK: repetições deduplicadas")


def test_cleanup_capitalizes_sentences():
    assert cleanup("bom dia. tudo bem? sim!", "pt") == "Bom dia. Tudo bem? Sim!"
    assert cleanup("and i think it works", "en") == "And I think it works"
    print("OK: capitalização de frases")


def test_smart_cleanup_flag_disables_cleaning():
    captured = {}
    original = typer.type_text
    typer.type_text = lambda t, mode="type": captured.update(text=t)
    try:
        engine = DictationEngine(Config(model="tiny", language="pt", smart_cleanup=False), FakeOverlay())
        engine._insert_text("ah hum, vamos lá. vamos lá.")
    finally:
        typer.type_text = original
    assert captured.get("text") == "ah hum, vamos lá. vamos lá.", captured
    print("OK: smart_cleanup=False preserva o texto cru")


def test_app_context_feature_removed():
    """Feature removida: nem o engine nem o transcriber levam o app em foco."""
    import inspect

    from flow import engine as engine_module

    assert "context" not in inspect.signature(Transcriber.transcribe).parameters
    assert not hasattr(Config(), "app_context")
    source = inspect.getsource(engine_module)
    assert "foreground_title" not in source and "app_context" not in source
    print("OK: contexto do app em foco removido do pipeline")


def test_default_overlay_position_is_bottom_center():
    from PySide6.QtCore import QRect

    from flow.qt_app import default_overlay_position

    # área útil 1920x1032 (taskbar de 48px embaixo): centro + 16px acima
    assert default_overlay_position(64, 20, QRect(0, 0, 1920, 1032)) == (928, 996)
    # monitor secundário à direita: acompanha a área útil, não a tela toda
    assert default_overlay_position(64, 20, QRect(1920, 0, 1920, 1080)) == (2848, 1044)
    # sem tela (headless): fallback fixo
    assert default_overlay_position(64, 20, None) == (900, 700)
    print("OK: default da barra = centro inferior acima da taskbar")


def test_config_defaults_and_migration():
    import json
    import os
    import tempfile

    fresh = Config()
    assert fresh.smart_cleanup and fresh.onboarded is False
    assert fresh.model == "small" and fresh.version == 5
    cfg = Config.load()  # config.json atual (ou ausente -> defaults)
    assert isinstance(cfg.smart_cleanup, bool)
    # migração v5: configs antigas com base sobem para small uma única vez
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump({"version": 4, "model": "base", "hotkey": "ctrl"}, f)
        old_path = f.name
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump({"version": 5, "model": "base"}, f)
        v5_path = f.name
    try:
        migrated = Config.load(old_path)
        assert migrated.model == "small" and migrated.version == 5, migrated
        assert migrated.hotkey == "ctrl+win" and migrated.hotkey_mode == "toggle"
        explicit = Config.load(v5_path)
        assert explicit.model == "base" and explicit.version == 5, explicit
    finally:
        os.unlink(old_path)
        os.unlink(v5_path)
    print("OK: defaults novos + migração base->small (v5)")


def test_autostart_safe_outside_frozen_build():
    from flow import autostart

    # fora do .exe nada é registrado (não há o que colocar no Run)
    assert autostart.available() is False
    assert autostart.is_enabled() is False
    assert autostart.set_enabled(True) is False
    print("OK: autostart seguro fora do .exe")


# ------------------------------------------------------------------ snippets (Tier 2)
def test_snippet_expands_in_engine():
    captured = {}
    original = typer.type_text
    typer.type_text = lambda t, mode="type": captured.update(text=t)
    try:
        cfg = Config(model="tiny", language="pt", smart_cleanup=False)
        cfg.snippets = {"agenda": "Reunião de 30 min? https://exemplo.com/reuniao"}
        engine = DictationEngine(cfg, FakeOverlay())
        engine._insert_text("olá snippet agenda")
    finally:
        typer.type_text = original
    assert captured.get("text") == "olá Reunião de 30 min? https://exemplo.com/reuniao", captured
    print("OK: snippet expandido no engine")


def test_snippet_case_insensitive_and_longest_name():
    from flow.snippets import expand_snippets

    table = {"agenda": "A", "agenda semanal": "B"}
    out, count = expand_snippets("vamos a snippet AGENDA", table)
    assert out == "vamos a A" and count == 1, (out, count)
    out, count = expand_snippets("snippet agenda semanal ok", table)
    assert out == "B ok" and count == 1, (out, count)
    print("OK: snippet case-insensitive, nome mais longo primeiro")


def test_snippet_unknown_name_stays():
    from flow.snippets import expand_snippets

    out, count = expand_snippets("snippet inventado aqui", {"agenda": "A"})
    assert out == "snippet inventado aqui" and count == 0, (out, count)
    out, count = expand_snippets("sem marcador", None)
    assert out == "sem marcador" and count == 0, (out, count)
    print("OK: snippet desconhecido/ausente não mexe no texto")


def test_snippet_body_with_newlines():
    from flow.snippets import expand_snippets

    out, count = expand_snippets("assinatura snippet ass", {"ass": "Abraço,\nJesse"})
    assert out == "assinatura Abraço,\nJesse" and count == 1, (out, count)
    print("OK: quebra de linha preservada no corpo")


# ------------------------------------------------------------------ idiomas (Tier 2)
def test_commands_spanish():
    clean, actions = parse_commands("hola mundo punto y coma adiós punto final", "es")
    assert clean == "hola mundo; adiós.", (clean, actions)
    clean, actions = parse_commands("borrar la última palabra", "es")
    assert clean == "" and actions == ["delete_last_word"], (clean, actions)
    print("OK: comandos por voz em espanhol")


def test_commands_french():
    clean, actions = parse_commands("salut virgule monde point d'exclamation", "fr")
    assert clean == "salut, monde!", (clean, actions)
    clean, actions = parse_commands("effacer le dernier mot", "fr")
    assert clean == "" and actions == ["delete_last_word"], (clean, actions)
    print("OK: comandos por voz em francês")


def test_language_names_cover_all_languages():
    from flow.config import LANGUAGES, LANGUAGE_NAMES

    missing = [code for code in LANGUAGES if code not in LANGUAGE_NAMES]
    assert not missing, missing
    assert len(LANGUAGES) >= 99, len(LANGUAGES)
    assert LANGUAGE_NAMES["auto"] == "detectar automaticamente"
    print("OK: rótulos PT para todos os idiomas")


def test_config_snippets_field():
    import json
    import os
    import tempfile

    fresh = Config()
    assert fresh.snippets is None
    # carrega de um config.json temporário: sem arquivo o default é None
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump({"snippets": {"ola": "Oi! Tudo bem?"}}, f)
        path = f.name
    try:
        loaded = Config.load(path)
    finally:
        os.unlink(path)
    assert isinstance(loaded.snippets, dict), type(loaded.snippets)
    assert loaded.snippets["ola"] == "Oi! Tudo bem?"
    print("OK: campo snippets carrega como dict")


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
    test_double_tap_starts_and_single_press_stops()
    test_double_tap_to_stop_does_not_restart()
    test_slow_first_tap_then_quick_second_starts()
    test_hold_starts_on_timer_and_stops_on_release()
    test_windows_combo_never_starts_recording()
    test_combo_interrupts_hold_recording()
    test_clean_tap_before_combo_does_not_complete_double()
    test_default_overlay_position_is_bottom_center()
    test_new_defaults_use_ctrl_win_and_paste()
    test_vocabulary_becomes_whisper_hotwords()
    test_user_profile_learns_and_reuses_confirmed_correction()
    test_auto_gain_boosts_quiet_voice_without_changing_silence()
    test_preload_runs_load_in_background()
    test_recorder_recent_returns_last_chunk()
    test_recorder_flattens_2d_frames()
    test_cleanup_removes_fillers_pt()
    test_cleanup_removes_fillers_en()
    test_cleanup_auto_keeps_article_um()
    test_cleanup_dedupes_repetitions()
    test_cleanup_capitalizes_sentences()
    test_smart_cleanup_flag_disables_cleaning()
    test_app_context_feature_removed()
    test_config_defaults_and_migration()
    test_autostart_safe_outside_frozen_build()
    test_snippet_expands_in_engine()
    test_snippet_case_insensitive_and_longest_name()
    test_snippet_unknown_name_stays()
    test_snippet_body_with_newlines()
    test_commands_spanish()
    test_commands_french()
    test_language_names_cover_all_languages()
    test_config_snippets_field()
    print("\nTodos os testes passaram!")
