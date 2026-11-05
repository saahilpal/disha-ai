import pytest
from app.voice import SentenceBuffer, ContextSynchronizer

def test_sentence_buffer_punctuation_split():
    buf = SentenceBuffer()
    tokens = ["Aaj ", "aapke ", "dinner ", "mein ", "paneer ", "bhurji ", "hai. ", "Yeh ", "kaafi ", "healthy ", "hai!"]
    emitted = []
    for t in tokens:
        ready = buf.push(t)
        emitted.extend(ready)
    
    flushed = buf.flush()
    if flushed:
        emitted.append(flushed)

    assert len(emitted) == 2
    assert emitted[0] == "Aaj aapke dinner mein paneer bhurji hai."
    assert emitted[1] == "Yeh kaafi healthy hai!"

def test_sentence_buffer_word_count_fallback():
    buf = SentenceBuffer(max_words=5)
    # Tokens without punctuation
    res = buf.push("ek do teen chaar paanch chhe")
    assert len(res) == 1
    assert "ek do teen chaar paanch chhe" in res[0]

def test_context_synchronizer_barge_in_truncation():
    full = "Aaj aapke dinner mein 150g paneer bhurji 2 multigrain rotis aur cucumber salad hai"
    # Interrupted halfway through (50% playback)
    truncated = ContextSynchronizer.align_history(full, played_fraction=0.5)
    assert len(truncated.split()) < len(full.split())
    assert truncated.endswith("...")
    assert "paneer bhurji" in truncated

def test_context_synchronizer_complete_playback():
    full = "Aaj aapke dinner mein paneer bhurji hai."
    aligned = ContextSynchronizer.align_history(full, played_fraction=0.98)
    assert aligned == full

def test_context_synchronizer_immediate_interrupt():
    full = "Aaj aapke dinner mein paneer bhurji hai."
    aligned = ContextSynchronizer.align_history(full, played_fraction=0.02)
    assert aligned == ""

def test_sentence_buffer_decimals_and_titles():
    from app.voice import SentenceBuffer
    sents = SentenceBuffer.split_into_sentences("Weight is down by 1.5 kg. Dr. Sharma approved the plan.")
    assert len(sents) == 2
    assert "1.5 kg" in sents[0]
    assert "Dr. Sharma" in sents[1]

def test_spoken_text_normalizer_expansions():
    from app.voice import SpokenTextNormalizer
    norm = SpokenTextNormalizer.normalize_for_speech("Dinner has ~420 kcal. Keep BP 120/80 in check. Plan costs ₹1,499.")
    assert "around 420 calories" in norm
    assert "BP 120 over 80" in norm
    assert "1,499 rupees" in norm
    assert "~" not in norm
    assert "₹" not in norm

